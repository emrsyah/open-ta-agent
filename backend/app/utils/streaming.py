"""
Streaming utilities for Server-Sent Events (SSE).
"""

import json
import logging
import dspy
from typing import AsyncGenerator, Any
from app.core.models import StreamChunk

logger = logging.getLogger(__name__)


def format_sse(data: dict) -> str:
    """Format dictionary as Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


async def stream_dspy_response(
    dspy_program: Any,
    retriever: Any,
    question: str,
    query_generator: Any = None,
    cheap_lm: Any = None
) -> AsyncGenerator[str, None]:
    """
    Stream DSPy response as SSE events.
    
    Args:
        dspy_program: The DSPy module to stream
        retriever: The PaperRetriever to get context
        question: User's question
        query_generator: Optional QueryGenerator for LLM-powered keyword extraction
        cheap_lm: Optional cheap model for query generation
        
    Yields:
        SSE formatted strings
    """
    logger.info(f"[STREAM] Starting stream for question: '{question}'")
    
    # Step 1: Generate optimized search query if generator provided
    if query_generator:
        logger.info("[STREAM] Generating optimized search query...")
        if cheap_lm:
            logger.debug("[STREAM] Using cheap model for query generation")
            with dspy.context(lm=cheap_lm):
                query_result = query_generator(user_question=question)
        else:
            query_result = query_generator(user_question=question)
        search_query = query_result.search_query
        logger.info(f"[STREAM] Generated query: '{search_query}'")
    else:
        search_query = question
        logger.info(f"[STREAM] Using original question as search query")
    
    # Step 2: Retrieve context (async operation)
    logger.info("[STREAM] Retrieving context...")
    context = await retriever.get_context(search_query)
    logger.info(f"[STREAM] Context retrieved (length: {len(context)} chars)")
    
    # Streamify the DSPy program
    streaming_program = dspy.streamify(dspy_program)
    
    logger.info("[STREAM] Starting DSPy stream generation...")
    async for value in streaming_program(question=question, context=context):
        if isinstance(value, dspy.Prediction):
            # Final prediction
            data = {
                "type": "done",
                "content": value.answer if hasattr(value, 'answer') else str(value),
                "sources": getattr(value, 'sources', [])
            }
            yield format_sse(data)
            
        elif hasattr(value, 'choices') and value.choices:
            # Streaming token from LM
            delta = value.choices[0].delta
            content = getattr(delta, 'content', '')
            if content:
                yield format_sse({"type": "token", "content": content})
    
    # Send completion signal
    logger.info("[STREAM] Stream completed")
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
