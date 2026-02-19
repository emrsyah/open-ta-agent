"""
Streaming utilities for Server-Sent Events (SSE).
"""

import json
import logging
import dspy
from typing import AsyncGenerator, Any, List
from app.core.models import StreamChunk, CitedPaper

logger = logging.getLogger(__name__)


def format_sse(data: dict) -> str:
    """Format dictionary as Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


def _build_cited_papers(source_ids: List[str], retrieved_papers: list) -> List[CitedPaper]:
    """Match source IDs from DSPy output against retrieved papers."""
    paper_map = {p.id: p for p in retrieved_papers}
    cited = []
    seen: set = set()
    for i, pid in enumerate(source_ids, 1):
        if pid in seen:
            continue
        seen.add(pid)
        paper = paper_map.get(pid)
        if paper:
            cited.append(CitedPaper(
                id=paper.id,
                title=paper.title,
                authors=paper.authors,
                abstract=paper.abstract,
                year=paper.year,
                citation_number=i,
            ))
    return cited


async def stream_dspy_response(
    dspy_program: Any,
    retriever: Any,
    question: str,
    query_generator: Any = None,
    intent_classifier: Any = None,
    cheap_lm: Any = None,
    history: Any = None,
    language: str = "en-US",
    source_preference: str = "all",
    include_metadata: bool = False
) -> AsyncGenerator[str, None]:
    """
    Stream DSPy response as SSE events with conversation history support.
    
    Based on DSPy streaming best practices from:
    https://dspy.ai/tutorials/streaming/
    
    Args:
        dspy_program: DSPy module for generation
        retriever: Context retriever
        question: User's question
        query_generator: Optional query generator module
        intent_classifier: Optional intent classifier module
        cheap_lm: Optional cheap LM for query generation
        history: Optional dspy.History object for conversation context
        language: User's preferred language
        source_preference: Filter for sources
        include_metadata: Include stream metadata (timing, token count)
    
    Yields:
        SSE formatted strings with streaming tokens and final prediction
    """
    from datetime import datetime
    import time
    
    start_time = time.time()
    token_count = 0
    duration_ms = 0  # Initialize to avoid UnboundLocalError
    
    logger.info(f"[STREAM] Starting stream for question: '{question}'")
    
    # Step 0: Classify intent
    is_research = True
    context = ""
    
    if intent_classifier:
        logger.info("[STREAM] Classifying intent...")
        if cheap_lm:
            with dspy.context(lm=cheap_lm):
                intent_res = intent_classifier(question=question)
        else:
            intent_res = intent_classifier(question=question)
            
        logger.info(f"[STREAM] Intent classified: {intent_res.category}")
        if intent_res.category == "general":
            is_research = False
            context = "No paper context needed for this general query."

    retrieved_papers = []

    # Step 1: Generate optimized search query (only if research)
    if is_research:
        if query_generator:
            logger.info("[STREAM] Generating optimized search query...")
            if cheap_lm:
                with dspy.context(lm=cheap_lm):
                    query_result = query_generator(user_question=question)
            else:
                query_result = query_generator(user_question=question)
            search_query = query_result.search_query
            logger.info(f"[STREAM] Generated query: '{search_query}'")
        else:
            search_query = question
            logger.info(f"[STREAM] Using original question as search query")

        # Step 2: Retrieve context + papers together
        logger.info("[STREAM] Retrieving context...")
        context, retrieved_papers = await retriever.get_papers_with_context(search_query)
        logger.info(f"[STREAM] Context retrieved (length: {len(context)} chars, {len(retrieved_papers)} papers)")
    
    # Use empty history if none provided
    if history is None:
        history = dspy.History(messages=[])
    
    # Optional: Send start metadata
    if include_metadata:
        yield format_sse({
            "type": "start",
            "timestamp": datetime.utcnow().isoformat(),
            "language": language
        })
    
    try:
        # Streamify the DSPy program with a listener for the 'answer' output field
        streaming_program = dspy.streamify(
            dspy_program,
            stream_listeners=[dspy.streaming.StreamListener(signature_field_name="answer")]
        )
        
        logger.info("[STREAM] Starting DSPy stream generation with conversation history...")
        
        async for value in streaming_program(question=question, context=context, history=history):
            if isinstance(value, dspy.streaming.StreamResponse):
                # Streaming token for the 'answer' field
                if value.chunk:
                    token_count += 1
                    yield format_sse({"type": "token", "content": value.chunk})
            
            elif isinstance(value, dspy.Prediction):
                logger.debug("[STREAM] Received final prediction")

                if hasattr(value, 'rationale') and value.rationale:
                    yield format_sse({
                        "type": "rationale",
                        "content": value.rationale
                    })

                # Enrich source IDs with full paper metadata
                cited_papers = _build_cited_papers(
                    getattr(value, 'sources', []),
                    retrieved_papers
                )

                data = {
                    "type": "done",
                    "content": value.answer if hasattr(value, 'answer') else str(value),
                    "sources": [p.model_dump() for p in cited_papers]
                }
                yield format_sse(data)
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Optional: Send completion metadata
        if include_metadata:
            yield format_sse({
                "type": "metadata",
                "token_count": token_count,
                "duration_ms": duration_ms
            })
        
        # Send completion signal
        logger.info(f"[STREAM] Stream completed ({token_count} tokens, {duration_ms}ms)")
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        # Error handling: send error to client
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"[STREAM] Streaming error after {duration_ms}ms: {e}", exc_info=True)
        yield format_sse({
            "type": "error",
            "content": f"Streaming error: {str(e)}"
        })
        yield "data: [DONE]\n\n"


def create_stream_chunk(
    chunk_type: str,
    content: str | None = None,
    sources: list[str] | None = None
) -> str:
    """Create a formatted SSE chunk."""
    data = {"type": chunk_type}
    if content is not None:
        data["content"] = content
    if sources is not None:
        data["sources"] = sources
    return format_sse(data)
