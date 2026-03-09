"""
Chat API routes for AI-powered paper Q&A.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langfuse import observe, get_client

from app.core.models import ChatRequest, ChatResponse, CitationAudit
from app.services.rag import get_rag_service
from app.core.auth import get_current_user_required
from app.services.session_manager import get_session_manager
from app.utils.streaming import _audit_citations, stream_dspy_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])



async def _load_history(
    conversation_id: str | None, is_incognito: bool, user_id: str | None = None
) -> list | None:
    """Load conversation history from Redis → DB fallback. Returns None when no history exists."""
    if not conversation_id or is_incognito:
        return None
    try:
        session_manager = get_session_manager()
        return await session_manager.get_history(conversation_id, user_id=user_id) or None
    except Exception as e:
        logger.warning("[CHAT] Failed to load history for %s: %s", conversation_id, e)
        return None


async def _save_history(
    conversation_id: str,
    question: str,
    answer: str,
    sources: list,
    search_query: str | None,
    is_incognito: bool,
    user_id: str | None = None,
) -> None:
    """Persist a Q&A turn to Redis + DB (skipped for incognito)."""
    if is_incognito:
        return
    try:
        session_manager = get_session_manager()
        await session_manager.add_message(
            conversation_id=conversation_id,
            question=question,
            answer=answer,
            sources=sources,
            context=None,
            metadata={"search_query": search_query, "is_incognito": is_incognito},
            user_id=user_id,
        )
        logger.debug("[CHAT] Saved history for conversation: %s", conversation_id)
    except Exception as e:
        logger.warning("[CHAT] Failed to save history for %s: %s", conversation_id, e)


async def _save_title(
    conversation_id: str, title: str, user_id: str | None = None
) -> None:
    """Persist the generated title to the conversations table."""
    try:
        from app.database import get_session_factory
        from app.db.crud import ConversationCRUD

        factory = get_session_factory()
        if factory:
            async with factory() as session:
                await ConversationCRUD(session).update_conversation_title(
                    conversation_id, title, user_id=user_id
                )
        logger.info("[CHAT] Title saved for %s: '%s'", conversation_id, title)
    except Exception as e:
        logger.warning("[CHAT] Failed to save title for %s: %s", conversation_id, e)


@router.post("/basic", response_model=ChatResponse)
@observe(name="chat-basic", capture_output=False)
async def chat_basic(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user_required),
):
    """Basic AI chat with papers. Supports streaming (SSE) and non-streaming responses."""
    rag_service = get_rag_service()
    query = request.get_query()
    stream = request.get_stream()
    conversation_id = request.get_conversation_id()
    user_id = current_user  # From verified JWT, not request body
    meta_params = request.meta_params

    # Tag this Langfuse trace with useful metadata
    try:
        langfuse = get_client()
        langfuse.update_current_trace(
            session_id=conversation_id or "anonymous",
            user_id=user_id or "anonymous",
            input={"query": query},
            tags=["chat-basic", "dspy"],
        )
    except Exception as exc:
        logger.debug("Langfuse trace tagging skipped: %s", exc)

    # Load history (Redis → DB fallback, capped at last 5 turns)
    raw_history = await _load_history(conversation_id, meta_params.is_incognito, user_id)
    is_first_message = not raw_history
    # Cap to last 5 turns to avoid LLM context bloat
    if raw_history and len(raw_history) > 5:
        raw_history = raw_history[-5:]
    dspy_history = rag_service._convert_to_dspy_history(raw_history)

    if not stream:
        result = await rag_service.chat(
            query,
            history=raw_history,
            language=meta_params.language,
            source_preference=meta_params.source_preference,
            catalog_type=meta_params.catalog_type,
            year_from=meta_params.year_from,
            year_to=meta_params.year_to,
            author=meta_params.author,
            has_electronic_access=meta_params.has_electronic_access,
        )
        
        if conversation_id:
            background_tasks.add_task(
                _save_history,
                conversation_id=conversation_id,
                question=query,
                answer=result["answer"],
                sources=[s.model_dump() if hasattr(s, "model_dump") else s for s in result.get("sources", [])],
                search_query=result.get("search_query"),
                is_incognito=meta_params.is_incognito,
                user_id=user_id,
            )
            if is_first_message and not meta_params.is_incognito:
                background_tasks.add_task(
                    _generate_and_save_title_bg,
                    conversation_id=conversation_id,
                    question=query,
                    answer=result["answer"],
                    user_id=user_id,
                )
        # Citation audit on non-streaming path (pure Python, no LLM)
        raw_sources = result.get("sources", [])
        audit_data = _audit_citations(result["answer"], raw_sources)
        citation_audit = CitationAudit(**audit_data)

        return ChatResponse(
            answer=result["answer"],
            sources=raw_sources,
            context=result.get("rationale"),
            search_query=result.get("search_query"),
            citation_audit=citation_audit,
        )
    # ------------------------------------------------------------------ #
    # Streaming path                                                       #
    # ------------------------------------------------------------------ #
    
    async def _on_complete(answer: str, sources: list, search_query: str | None) -> None:
        if conversation_id:
            await _save_history(
                conversation_id=conversation_id,
                question=query,
                answer=answer,
                sources=sources,
                search_query=search_query,
                is_incognito=meta_params.is_incognito,
                user_id=user_id,
            )

    # Only generate+emit title on the first message of a non-incognito conversation
    async def _title_generator(question: str, answer: str) -> str:
        title = await rag_service.generate_title(question, answer)
        if conversation_id and not meta_params.is_incognito:
            await _save_title(conversation_id, title, user_id)
        return title

    # Callback to save title early (when generated from question only)
    async def _save_title_callback(title: str) -> None:
        if conversation_id and not meta_params.is_incognito:
            await _save_title(conversation_id, title, user_id)

    return StreamingResponse(
        stream_dspy_response(
            rag_service.get_module(),
            rag_service.get_retriever(),
            question=query,
            query_generator=rag_service.query_generator,
            intent_classifier=rag_service.intent_classifier,
            acknowledgment_generator=rag_service.acknowledgment_generator,
            cheap_lm=rag_service.cheap_lm,
            history=dspy_history,
            language=meta_params.language,
            source_preference=meta_params.source_preference,
            planner=rag_service.planner,
            on_complete=_on_complete,
            generate_title=_title_generator if is_first_message and not meta_params.is_incognito else None,
            query_reformulator=rag_service.query_reformulator,
            query_decomposer=rag_service.query_decomposer,
            gap_detector=rag_service.gap_detector,
            catalog_type=meta_params.catalog_type,
            year_from=meta_params.year_from,
            year_to=meta_params.year_to,
            author=meta_params.author,
            has_electronic_access=meta_params.has_electronic_access,
            title_from_question_generator=rag_service.title_from_question_generator if is_first_message and not meta_params.is_incognito else None,
            save_title_callback=_save_title_callback if is_first_message and not meta_params.is_incognito else None,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

async def _generate_and_save_title_bg(
    conversation_id: str, question: str, answer: str, user_id: str | None = None
) -> None:
    """Background task for non-streaming path: generate title and save it."""
    try:
        title = await get_rag_service().generate_title(question, answer)
        await _save_title(conversation_id, title, user_id)
    except Exception as e:
        logger.warning("[CHAT] Background title generation failed for %s: %s", conversation_id, e)


# ------------------------------------------------------------------ #
# /chat/new — LangGraph-powered RAG pipeline                          #
# ------------------------------------------------------------------ #

@router.post("/new", response_model=ChatResponse)
@observe(name="chat-new-lg", capture_output=False)
async def chat_new(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user_required),
):
    """LangGraph-powered AI chat with papers.
    
    Same functionality as /chat/basic but orchestrated via LangGraph
    with DSPy modules as the prompt layer. Supports streaming (SSE)
    and non-streaming responses.
    """
    from app.services.rag_langgraph import get_rag_service_lg

    rag_service_lg = get_rag_service_lg()
    query = request.get_query()
    stream = request.get_stream()
    conversation_id = request.get_conversation_id()
    user_id = current_user
    meta_params = request.meta_params

    # Tag this Langfuse trace with useful metadata
    try:
        langfuse = get_client()
        langfuse.update_current_trace(
            session_id=conversation_id or "anonymous",
            user_id=user_id or "anonymous",
            input={"query": query},
            tags=["chat-new", "langgraph"],
        )
    except Exception as exc:
        logger.debug("Langfuse trace tagging skipped: %s", exc)

    # Load history (same logic as /chat/basic)
    raw_history = await _load_history(conversation_id, meta_params.is_incognito, user_id)
    is_first_message = not raw_history
    if raw_history and len(raw_history) > 5:
        raw_history = raw_history[-5:]

    if not stream:
        result = await rag_service_lg.chat(
            query,
            history=raw_history,
            language=meta_params.language,
            source_preference=meta_params.source_preference,
            catalog_type=meta_params.catalog_type,
            year_from=meta_params.year_from,
            year_to=meta_params.year_to,
            author=meta_params.author,
            has_electronic_access=meta_params.has_electronic_access,
        )

        if conversation_id:
            background_tasks.add_task(
                _save_history,
                conversation_id=conversation_id,
                question=query,
                answer=result["answer"],
                sources=[s.model_dump() if hasattr(s, "model_dump") else s for s in result.get("sources", [])],
                search_query=result.get("search_query"),
                is_incognito=meta_params.is_incognito,
                user_id=user_id,
            )
            if is_first_message and not meta_params.is_incognito:
                background_tasks.add_task(
                    _generate_and_save_title_lg_bg,
                    conversation_id=conversation_id,
                    question=query,
                    answer=result["answer"],
                    user_id=user_id,
                )

        raw_sources = result.get("sources", [])
        audit_data = _audit_citations(result["answer"], raw_sources)
        citation_audit = CitationAudit(**audit_data)

        return ChatResponse(
            answer=result["answer"],
            sources=raw_sources,
            context=result.get("rationale"),
            search_query=result.get("search_query"),
            citation_audit=citation_audit,
        )

    # ── Streaming path (LangGraph) ───────────────────────────────────
    async def _on_complete_lg(answer: str, sources: list, search_query: str | None) -> None:
        if conversation_id:
            await _save_history(
                conversation_id=conversation_id,
                question=query,
                answer=answer,
                sources=sources,
                search_query=search_query,
                is_incognito=meta_params.is_incognito,
                user_id=user_id,
            )

    async def _title_generator_lg(question: str, answer: str) -> str:
        title = await rag_service_lg.generate_title(question, answer)
        if conversation_id and not meta_params.is_incognito:
            await _save_title(conversation_id, title, user_id)
        return title

    return StreamingResponse(
        rag_service_lg.stream_response(
            question=query,
            history=raw_history,
            language=meta_params.language,
            source_preference=meta_params.source_preference,
            catalog_type=meta_params.catalog_type,
            year_from=meta_params.year_from,
            year_to=meta_params.year_to,
            author=meta_params.author,
            has_electronic_access=meta_params.has_electronic_access,
            conversation_id=conversation_id,
            is_incognito=meta_params.is_incognito,
            user_id=user_id,
            on_complete=_on_complete_lg,
            generate_title_fn=_title_generator_lg if is_first_message and not meta_params.is_incognito else None,
            is_first_message=is_first_message,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _generate_and_save_title_lg_bg(
    conversation_id: str, question: str, answer: str, user_id: str | None = None
) -> None:
    """Background task: generate title via LangGraph service and save it."""
    try:
        from app.services.rag_langgraph import get_rag_service_lg
        title = await get_rag_service_lg().generate_title(question, answer)
        await _save_title(conversation_id, title, user_id)
    except Exception as e:
        logger.warning("[CHAT-LG] Background title generation failed for %s: %s", conversation_id, e)


@router.post("/deep")
async def chat_deep(request: ChatRequest):
    """
    Deep research chat with RLM (Recursive Language Model).
    
    This endpoint will implement recursive research for complex queries
    that require multi-step exploration and synthesis.
    
    **Status:** 🚧 Not yet implemented - returns 501
    """
    raise HTTPException(
        status_code=501,
        detail="Deep research with RLM is not yet implemented. Use /chat/basic for now."
    )

# ------------------------------------------------------------------ #
# /chat/deepagents — DeepAgents-powered RAG pipeline                   #
# ------------------------------------------------------------------ #

@router.post("/deepagents", response_model=ChatResponse)
@observe(name="chat-deepagents", capture_output=False)
async def chat_deepagents(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user_required),
):
    """DeepAgents-powered AI chat with papers.
    
    Uses LangChain's DeepAgents for orchestration with custom tools
    for paper search and RAG. Supports streaming (SSE) and non-streaming responses.
    """
    from app.services.rag_deepagents import get_rag_service_da

    rag_service_da = get_rag_service_da()
    query = request.get_query()
    stream = request.get_stream()
    conversation_id = request.get_conversation_id()
    user_id = current_user
    meta_params = request.meta_params

    # Tag this Langfuse trace with useful metadata
    try:
        langfuse = get_client()
        langfuse.update_current_trace(
            session_id=conversation_id or "anonymous",
            user_id=user_id or "anonymous",
            input={"query": query},
            tags=["chat-deepagents", "deepagents"],
        )
    except Exception as exc:
        logger.debug("Langfuse trace tagging skipped: %s", exc)

    # Load history (same logic as /chat/basic)
    raw_history = await _load_history(conversation_id, meta_params.is_incognito, user_id)
    is_first_message = not raw_history
    if raw_history and len(raw_history) > 5:
        raw_history = raw_history[-5:]

    if not stream:
        result = await rag_service_da.chat(
            query,
            history=raw_history,
            language=meta_params.language,
            source_preference=meta_params.source_preference,
            catalog_type=meta_params.catalog_type,
            year_from=meta_params.year_from,
            year_to=meta_params.year_to,
            author=meta_params.author,
            has_electronic_access=meta_params.has_electronic_access,
        )

        if conversation_id:
            background_tasks.add_task(
                _save_history,
                conversation_id=conversation_id,
                question=query,
                answer=result["answer"],
                sources=[s.model_dump() if hasattr(s, "model_dump") else s for s in result.get("sources", [])],
                search_query=result.get("search_query"),
                is_incognito=meta_params.is_incognito,
                user_id=user_id,
            )
            if is_first_message and not meta_params.is_incognito:
                background_tasks.add_task(
                    _generate_and_save_title_da_bg,
                    conversation_id=conversation_id,
                    question=query,
                    answer=result["answer"],
                    user_id=user_id,
                )

        raw_sources = result.get("sources", [])
        audit_data = _audit_citations(result["answer"], raw_sources)
        citation_audit = CitationAudit(**audit_data)

        return ChatResponse(
            answer=result["answer"],
            sources=raw_sources,
            context=result.get("rationale"),
            search_query=result.get("search_query"),
            citation_audit=citation_audit,
        )

    # ── Streaming path (DeepAgents) ───────────────────────────────────
    async def _on_complete_da(answer: str, sources: list, search_query: str | None) -> None:
        if conversation_id:
            await _save_history(
                conversation_id=conversation_id,
                question=query,
                answer=answer,
                sources=sources,
                search_query=search_query,
                is_incognito=meta_params.is_incognito,
                user_id=user_id,
            )

    async def _title_generator_da(question: str, answer: str) -> str:
        title = await rag_service_da.generate_title(question, answer)
        if conversation_id and not meta_params.is_incognito:
            await _save_title(conversation_id, title, user_id)
        return title

    return StreamingResponse(
        rag_service_da.stream_response(
            question=query,
            history=raw_history,
            language=meta_params.language,
            source_preference=meta_params.source_preference,
            catalog_type=meta_params.catalog_type,
            year_from=meta_params.year_from,
            year_to=meta_params.year_to,
            author=meta_params.author,
            has_electronic_access=meta_params.has_electronic_access,
            conversation_id=conversation_id,
            is_incognito=meta_params.is_incognito,
            user_id=user_id,
            on_complete=_on_complete_da,
            generate_title_fn=_title_generator_da if is_first_message and not meta_params.is_incognito else None,
            is_first_message=is_first_message,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _generate_and_save_title_da_bg(
    conversation_id: str, question: str, answer: str, user_id: str | None = None
) -> None:
    """Background task: generate title via DeepAgents service and save it."""
    try:
        from app.services.rag_deepagents import get_rag_service_da
        title = await get_rag_service_da().generate_title(question, answer)
        await _save_title(conversation_id, title, user_id)
    except Exception as e:
        logger.warning("[CHAT-DA] Background title generation failed for %s: %s", conversation_id, e)

