"""
FastAPI + DSPy Streaming Example
Run this to test DSPy streaming with FastAPI
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Literal
import dspy
import orjson
import os

# =============================================================================
# CONFIGURATION
# =============================================================================

app = FastAPI(title="DSPy Streaming API with OpenRouter")

# Configure DSPy with OpenRouter (recommended)
# Get your key at: https://openrouter.ai/settings/keys
api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENROUTER_API_KEY or OPENAI_API_KEY environment variable required")

# Use OpenRouter if OPENROUTER_API_KEY is set
if os.getenv("OPENROUTER_API_KEY"):
    print("🚀 Using OpenRouter API")
    lm = dspy.LM(
        'openai/openai/gpt-4o-mini',
        api_base='https://openrouter.ai/api/v1',
        api_key=api_key,
        model_type='chat'
    )
else:
    print("🔑 Using OpenAI API directly")
    lm = dspy.LM('openai/gpt-4o-mini', api_key=api_key)

dspy.configure(lm=lm, async_max_workers=4)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ChatRequest(BaseModel):
    question: str
    stream: bool = True

class ChatResponse(BaseModel):
    answer: str
    reasoning: Optional[str] = None


# =============================================================================
# DSPy SIGNATURES & MODULES
# =============================================================================

class BasicQA(dspy.Signature):
    """Answer questions with reasoning."""
    question: str = dspy.InputField(desc="The question to answer")
    answer: str = dspy.OutputField(desc="The answer")


class QAWithReasoning(dspy.Signature):
    """Answer questions with step-by-step reasoning."""
    question: str = dspy.InputField(desc="The question to answer")
    reasoning: str = dspy.OutputField(desc="Step-by-step thinking")
    answer: str = dspy.OutputField(desc="The final answer")


# =============================================================================
# STREAMING UTILITIES
# =============================================================================

def format_sse(data: dict) -> str:
    """Format dictionary as Server-Sent Event"""
    return f"data: {orjson.dumps(data).decode()}\n\n"


async def stream_dspy_prediction(dspy_module, **kwargs) -> StreamingResponse:
    """
    Stream DSPy module output as SSE
    
    Based on: https://dspy.ai/tutorials/deployment
    """
    async def generate():
        # Streamify the module
        streaming_module = dspy.streamify(dspy_module)
        
        # Iterate through streaming values
        async for value in streaming_module(**kwargs):  # type: ignore
            if isinstance(value, dspy.Prediction):
                # Final prediction
                data = {
                    "type": "done",
                    "answer": value.answer if hasattr(value, 'answer') else str(value),
                    "reasoning": getattr(value, 'reasoning', None)
                }
                yield format_sse(data)
            elif hasattr(value, 'choices'):
                # Streaming chunk from LM
                if value.choices and hasattr(value.choices[0], 'delta'):
                    delta = value.choices[0].delta
                    content = getattr(delta, 'content', None)
                    if content:
                        data = {"type": "token", "content": content}
                        yield format_sse(data)
        
        # Send completion signal
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Health check"""
    return {
        "message": "DSPy Streaming API",
        "endpoints": {
            "/chat/basic": "Basic Q&A (streaming)",
            "/chat/reasoning": "Q&A with Chain of Thought (streaming)",
            "/chat/basic-sync": "Basic Q&A (non-streaming)"
        }
    }


@app.post("/chat/basic")
async def chat_basic(request: ChatRequest):
    """Basic Q&A with streaming"""
    
    if not request.stream:
        # Non-streaming
        qa = dspy.Predict(BasicQA)
        result = qa(question=request.question)
        return ChatResponse(answer=result.answer)
    
    # Streaming
    qa = dspy.Predict(BasicQA)
    qa_async = dspy.asyncify(qa)
    
    return await stream_dspy_prediction(qa_async, question=request.question)


@app.post("/chat/reasoning")
async def chat_reasoning(request: ChatRequest):
    """Q&A with Chain of Thought reasoning"""
    
    if not request.stream:
        # Non-streaming
        cot = dspy.ChainOfThought(QAWithReasoning)
        result = cot(question=request.question)
        return ChatResponse(
            answer=result.answer,
            reasoning=result.rationale
        )
    
    # Streaming
    cot = dspy.ChainOfThought(QAWithReasoning)
    cot_async = dspy.asyncify(cot)
    
    return await stream_dspy_prediction(cot_async, question=request.question)


@app.post("/chat/basic-sync")
async def chat_basic_sync(request: ChatRequest):
    """Synchronous (non-streaming) endpoint"""
    
    qa = dspy.Predict(BasicQA)
    result = qa(question=request.question)
    
    return ChatResponse(answer=result.answer)


# =============================================================================
# TEST CLIENT (for testing streaming)
# =============================================================================

@app.post("/test")
async def test_streaming():
    """Test endpoint that simulates streaming"""
    
    async def generate():
        words = ["Hello", " there", "! This", " is", " a", " test", " stream", "."]
        for word in words:
            data = {"type": "token", "content": word}
            yield format_sse(data)
        
        yield format_sse({"type": "done", "content": " ".join(words)})
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║           DSPy FastAPI Streaming Example                    ║
    ╠════════════════════════════════════════════════════════════╣
    ║  Running on: http://localhost:8000                          ║
    ║                                                              ║
    ║  Endpoints:                                                  ║
    ║    - POST /chat/basic         Basic Q&A                     ║
    ║    - POST /chat/reasoning     Q&A with reasoning            ║
    ║    - POST /test               Test streaming                ║
    ║                                                              ║
    ║  Test with curl:                                            ║
    ║    curl -X POST http://localhost:8000/chat/basic \\         ║
    ║      -H "Content-Type: application/json" \\                 ║
    ║      -d '{"question": "What is DSPy?", "stream": true}'     ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
