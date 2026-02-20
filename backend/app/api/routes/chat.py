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
    
    **New API Structure:**
    ```bash
    curl -X POST http://localhost:8000/chat/basic \\
      -H "Content-Type: application/json" \\
      -d '{
        "query": "What is machine learning?",
        "meta_params": {
          "mode": "basic",
          "stream": false,
          "language": "id-ID",
          "source_preference": "only_papers",
          "conversation_id": "conv_123"
        }
      }'
    ```
    
    **Backwards Compatible (Old API):**
    ```bash
    curl -X POST http://localhost:8000/chat/basic \\
      -H "Content-Type: application/json" \\
      -d '{"question": "What is machine learning?", "stream": false}'
    ```
    """
    rag_service = get_rag_service()
    
    # Extract parameters with backwards compatibility
    query = request.get_query()
    stream = request.get_stream()
    conversation_id = request.get_conversation_id()
    meta_params = request.meta_params
    
    # TODO: Load conversation history from Redis/DB using conversation_id
    # For now, we'll use empty history. See session_manager.py for implementation
    history = None
    if conversation_id:
        # from app.services.session_manager import get_session_manager
        # session_manager = get_session_manager()
        # history = await session_manager.get_history(conversation_id)
        pass
    
    if not stream:
        # Non-streaming response with history support
        result = await rag_service.chat(
            query, 
            history=history,
            language=meta_params.language,
            source_preference=meta_params.source_preference
        )
        
        # TODO: Save to history if not incognito
        # if not meta_params.is_incognito and conversation_id:
        #     await session_manager.add_message(
        #         conversation_id,
        #         question=query,
        #         answer=result["answer"],
        #         sources=result.get("sources", [])
        #     )
        
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            context=result.get("rationale"),
            search_query=result.get("search_query")
        )
    
    # Streaming response via SSE with history support
    rag_module = rag_service.get_module()
    retriever = rag_service.get_retriever()
    query_generator = rag_service.query_generator
    intent_classifier = rag_service.intent_classifier
    cheap_lm = rag_service.cheap_lm
    planner = rag_service.planner

    # Convert history to dspy.History format
    import dspy
    dspy_history = rag_service._convert_to_dspy_history(history)

    return StreamingResponse(
        stream_dspy_response(
            rag_module,
            retriever,
            question=query,
            query_generator=query_generator,
            intent_classifier=intent_classifier,
            cheap_lm=cheap_lm,
            history=dspy_history,
            language=meta_params.language,
            source_preference=meta_params.source_preference,
            planner=planner,
        ),
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
