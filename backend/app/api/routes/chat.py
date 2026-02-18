"""
Chat API routes for AI-powered paper Q&A.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.core.models import ChatRequest, ChatResponse
from app.services.rag import get_rag_service
from app.utils.streaming import stream_dspy_response

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/basic", response_model=ChatResponse)
async def chat_basic(request: ChatRequest):
    """
    Basic AI chat with papers.
    
    Supports both streaming (default) and non-streaming responses.
    
    **Streaming Example:**
    ```bash
    curl -X POST http://localhost:8000/chat/basic \\
      -H "Content-Type: application/json" \\
      -d '{"question": "What is machine learning?", "stream": true}'
    ```
    
    **Non-Streaming Example:**
    ```bash
    curl -X POST http://localhost:8000/chat/basic \\
      -H "Content-Type: application/json" \\
      -d '{"question": "What is machine learning?", "stream": false}'
    ```
    """
    rag_service = get_rag_service()
    
    if not request.stream:
        # Non-streaming response
        result = await rag_service.chat(request.question)
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            context=result.get("rationale")
        )
    
    # Streaming response via SSE
    rag_module = rag_service.get_module()
    
    return StreamingResponse(
        stream_dspy_response(rag_module, question=request.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


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
