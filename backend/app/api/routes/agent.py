"""
Research Agent API route.

Exposes POST /agent/chat — a streaming-only SSE endpoint powered by the
custom LangChain ResearchAgent (agents.py).

Design choices vs /chat/deepagents:
- Streaming only (the frontend always streams; a non-streaming path adds ~80
  lines for no practical benefit).
- History is managed by AgentMemory (Redis-only, simple).
- DB conversation persistence is fire-and-forget via a background task.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from langfuse import observe, get_client

from app.core.auth import get_current_user_required
from app.core.models import ChatRequest
from app.services.agent_memory import get_agent_memory
from app.services.agents import get_research_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Persistence helpers (background tasks — fire-and-forget)
# ---------------------------------------------------------------------------

async def _save_history_bg(
    conv_id: str,
    question: str,
    answer: str,
    sources: list,
    is_incognito: bool,
) -> None:
    """Save a Q&A turn to AgentMemory (Redis). Skipped for incognito."""
    if is_incognito:
        return
    try:
        memory = get_agent_memory()
        await memory.save_turn(
            conv_id=conv_id,
            question=question,
            answer=answer,
            sources=sources,
        )
    except Exception as exc:
        logger.warning("[AGENT-ROUTE] save_history failed for %s: %s", conv_id, exc)


async def _save_db_turn_bg(
    conv_id: str,
    question: str,
    answer: str,
    sources: list,
    search_query: str | None,
    user_id: str | None,
    is_incognito: bool,
) -> None:
    """Persist the conversation turn to the DB (conversations + messages tables)."""
    if is_incognito:
        return
    try:
        from app.database import get_session_factory
        from app.db.crud import ConversationCRUD

        factory = get_session_factory()
        if factory is None:
            return
        async with factory() as session:
            crud = ConversationCRUD(session)
            await crud.upsert_conversation(
                conversation_id=conv_id,
                is_incognito=False,
                user_id=user_id,
            )
            await crud.add_message(
                conversation_id=conv_id,
                question=question,
                answer=answer,
                sources=sources,
                search_query=search_query,
            )
        logger.debug("[AGENT-ROUTE] DB turn saved for %s", conv_id)
    except Exception as exc:
        logger.warning("[AGENT-ROUTE] DB save failed for %s: %s", conv_id, exc)


async def _save_title_bg(
    conv_id: str,
    title: str,
    user_id: str | None,
) -> None:
    """Update the conversation title in the DB."""
    try:
        from app.database import get_session_factory
        from app.db.crud import ConversationCRUD

        factory = get_session_factory()
        if factory is None:
            return
        async with factory() as session:
            await ConversationCRUD(session).update_conversation_title(
                conv_id, title, user_id=user_id
            )
        logger.info("[AGENT-ROUTE] Title saved for %s: %r", conv_id, title)
    except Exception as exc:
        logger.warning("[AGENT-ROUTE] Title save failed for %s: %s", conv_id, exc)


async def _generate_and_save_title_bg(
    conv_id: str,
    question: str,
    answer: str,
    user_id: str | None,
) -> None:
    """Background task: generate + save title (non-streaming path only)."""
    try:
        title = await get_research_agent().generate_title(question, answer)
        await _save_title_bg(conv_id, title, user_id)
    except Exception as exc:
        logger.warning("[AGENT-ROUTE] Background title gen failed for %s: %s", conv_id, exc)


# ---------------------------------------------------------------------------
# POST /agent/chat
# ---------------------------------------------------------------------------

@router.post("/chat")
@observe(name="agent-chat", capture_output=False)
async def agent_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user_required),
):
    """
    Streaming research chat powered by the custom LangChain ResearchAgent.

    Always returns a streaming SSE response.  The agent autonomously decides
    whether to plan first (create_plan), search (search_papers), or fetch
    paper details (get_paper_details) based on the query complexity.

    SSE events emitted match the existing frontend event contract — see
    agents.py for the full list.
    """
    agent = get_research_agent()
    memory = get_agent_memory()

    query = request.get_query()
    conv_id = request.get_conversation_id()
    user_id = current_user
    meta = request.meta_params

    # Tag Langfuse trace
    try:
        get_client().update_current_trace(
            session_id=conv_id or "anonymous",
            user_id=user_id or "anonymous",
            input={"query": query},
            tags=["agent-chat", "langchain"],
        )
    except Exception:
        pass

    # Load history from Redis (returns [] if Redis is down or key missing)
    history: list[dict] = []
    if conv_id and not meta.is_incognito:
        history = await memory.get_history(conv_id)

    is_first_message = not history

    # ── Callbacks ──────────────────────────────────────────────────────

    async def _on_complete(answer: str, sources: list, search_query: str | None) -> None:
        if not conv_id:
            return
        background_tasks.add_task(
            _save_history_bg,
            conv_id=conv_id,
            question=query,
            answer=answer,
            sources=sources,
            is_incognito=meta.is_incognito,
        )
        background_tasks.add_task(
            _save_db_turn_bg,
            conv_id=conv_id,
            question=query,
            answer=answer,
            sources=sources,
            search_query=search_query,
            user_id=user_id,
            is_incognito=meta.is_incognito,
        )

    async def _title_generator(question: str, answer: str) -> str:
        title = await agent.generate_title(question, answer)
        if conv_id and not meta.is_incognito:
            background_tasks.add_task(_save_title_bg, conv_id, title, user_id)
        return title

    # ── Streaming response ─────────────────────────────────────────────
    return StreamingResponse(
        agent.stream_response(
            question=query,
            history=history,
            language=meta.language,
            source_preference=meta.source_preference,
            catalog_type=meta.catalog_type,
            year_from=meta.year_from,
            year_to=meta.year_to,
            author=meta.author,
            has_electronic_access=meta.has_electronic_access,
            conversation_id=conv_id,
            is_incognito=meta.is_incognito,
            user_id=user_id,
            on_complete=_on_complete,
            generate_title_fn=_title_generator if is_first_message and not meta.is_incognito else None,
            is_first_message=is_first_message,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
