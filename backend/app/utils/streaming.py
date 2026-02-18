"""
Streaming utilities for Server-Sent Events (SSE).
"""

import json
import dspy
from typing import AsyncGenerator, Any
from app.core.models import StreamChunk


def format_sse(data: dict) -> str:
    """Format dictionary as Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


async def stream_dspy_response(
    dspy_program: Any,
    **kwargs
) -> AsyncGenerator[str, None]:
    """
    Stream DSPy response as SSE events.
    
    Args:
        dspy_program: The DSPy module to stream
        **kwargs: Arguments to pass to the module
        
    Yields:
        SSE formatted strings
    """
    # Streamify the DSPy program
    streaming_program = dspy.streamify(dspy_program)
    
    async for value in streaming_program(**kwargs):
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
