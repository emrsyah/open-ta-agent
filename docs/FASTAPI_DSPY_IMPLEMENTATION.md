# FastAPI + DSPy: Complete Backend Implementation Guide

## 🎯 Overview

This guide shows how to build a production-ready FastAPI backend with DSPy, supporting:
- ✅ Streaming responses (SSE)
- ✅ Async processing
- ✅ Paper search with vector retrieval
- ✅ Basic AI chat (RAG)
- ✅ Deep research (RLM)
- ✅ Conversation history

---

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   /search    │    │  /chat/basic │    │ /chat/deep   │ │
│  │  (String)    │    │   (RAG)      │    │   (RLM)      │ │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘ │
│         │                    │                    │          │
│         ▼                    ▼                    ▼          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │ String Match │    │ RAG + History│    │ RLM + Recurs │ │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘ │
│                              │                    │          │
│                              └────────┬───────────┘          │
│                                       │                      │
│                                       ▼                      │
│                              ┌──────────────┐              │
│                              │  dspy.LM     │              │
│                              │  (OpenAI)    │              │
│                              └──────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start: Complete Implementation

### 1. Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Configuration
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py          # Pydantic models
│   │   └── paper.py            # Paper data model
│   ├── dspy_modules/
│   │   ├── __init__.py
│   │   ├── rag.py              # RAG module
│   │   ├── retriever.py        # Paper retriever
│   │   └── history.py          # Conversation history
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── search.py       # Basic search
│   │   │   ├── chat.py         # AI chat endpoints
│   │   │   └── health.py       # Health check
│   │   └── dependencies.py     # Dependencies
│   └── utils/
│       ├── __init__.py
│       └── streaming.py        # Streaming utilities
├── requirements.txt
└── .env
```

### 2. Core Implementation

#### `app/config.py`
```python
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    
    # DSPy Config
    DSPY_MODEL: str = "openai/gpt-4o-mini"
    DSPY_MAX_WORKERS: int = 4
    
    # Retrieval Config
    RETRIEVAL_TOP_K: int = 5
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_DIM: int = 512
    
    # App Config
    APP_NAME: str = "Telkom Paper Research API"
    VERSION: str = "1.0.0"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

#### `app/models/schemas.py`
```python
from pydantic import BaseModel
from typing import List, Optional, Literal
from dspy import History

class SearchRequest(BaseModel):
    query: str
    search_field: Literal["title", "abstract"] = "abstract"
    limit: int = 10

class PaperResult(BaseModel):
    paper_id: str
    title: str
    authors: List[str]
    abstract: str
    year: int
    relevance_score: float

class SearchResponse(BaseModel):
    results: List[PaperResult]
    total: int

class ChatRequest(BaseModel):
    question: str
    mode: Literal["basic", "deep"] = "basic"
    session_id: Optional[str] = None
    stream: bool = True

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: Optional[List[str]] = None

class StreamChunk(BaseModel):
    type: Literal["token", "reasoning", "sources", "done"]
    content: str
    sources: Optional[List[str]] = None
```

#### `app/dspy_modules/retriever.py`
```python
import dspy
from typing import List
from app.models.paper import Paper

class PaperRetriever:
    """Retrieve papers using vector search"""
    
    def __init__(self, papers: List[Paper], embedder=None):
        self.papers = papers
        self.embedder = embedder or dspy.Embedder(
            'openai/text-embedding-3-small',
            dimensions=512
        )
        
        # Build corpus from abstracts
        self.corpus = [
            f"{paper.title} {paper.abstract}"
            for paper in papers
        ]
        
        # Initialize retriever
        self.retriever = dspy.retrievers.Embeddings(
            embedder=self.embedder,
            corpus=self.corpus,
            k=5
        )
    
    def __call__(self, query: str) -> str:
        """Retrieve relevant papers and return formatted context"""
        results = self.retriever(query)
        
        # Format as context
        context_parts = []
        for i, result in enumerate(results, 1):
            paper = self.papers[i]
            context_parts.append(
                f"Paper {i}:\n"
                f"Title: {paper.title}\n"
                f"Authors: {', '.join(paper.authors)}\n"
                f"Abstract: {paper.abstract}\n"
            )
        
        return "\n\n".join(context_parts)
```

#### `app/dspy_modules/rag.py`
```python
import dspy
from typing import Optional, List
from dspy import History

class PaperChatSignature(dspy.Signature):
    """Answer questions about research papers with context."""
    question: str = dspy.InputField(desc="User's question")
    context: str = dspy.InputField(desc="Relevant paper excerpts")
    history: Optional[History] = dspy.InputField(desc="Conversation history", default=None)
    answer: str = dspy.OutputField(desc="Answer with citations")
    sources: List[str] = dspy.OutputField(desc="Referenced paper IDs")

class BasicPaperChat(dspy.Module):
    """Basic RAG for paper chat"""
    
    def __init__(self, retriever):
        super().__init__()
        self.retriever = retriever
        self.generate = dspy.ChainOfThought(PaperChatSignature)
    
    def forward(self, question: str, history: Optional[History] = None):
        # Retrieve context
        context = self.retriever(question)
        
        # Generate response
        result = self.generate(
            question=question,
            context=context,
            history=history or History(messages=[])
        )
        
        return dspy.Prediction(
            answer=result.answer,
            sources=result.sources
        )
```

#### `app/utils/streaming.py`
```python
import json
import dspy
from typing import AsyncGenerator
import orjson

async def stream_dspy_response(
    dspy_program,
    **kwargs
) -> AsyncGenerator[str, None]:
    """
    Stream DSPy response as SSE events
    
    Usage:
        async for chunk in stream_dspy_response(program, question="..."):
            yield chunk
    """
    
    # Streamify the DSPy program
    streaming_program = dspy.streamify(dspy_program)
    
    async for value in streaming_program(**kwargs):
        if isinstance(value, dspy.Prediction):
            # Final prediction
            data = {
                "type": "done",
                "content": value.answer,
                "sources": getattr(value, 'sources', [])
            }
        elif hasattr(value, 'choices'):
            # Streaming token from LM
            delta = value.choices[0].delta.content or ""
            if delta:
                data = {"type": "token", "content": delta}
            else:
                continue
        else:
            continue
        
        # Format as SSE
        yield f"data: {orjson.dumps(data).decode()}\n\n"
    
    # Send completion signal
    yield "data: [DONE]\n\n"


def format_sse(data: dict) -> str:
    """Format dictionary as Server-Sent Event"""
    return f"data: {orjson.dumps(data).decode()}\n\n"
```

#### `app/api/routes/chat.py`
```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest, ChatMessage
from app.dspy_modules.rag import BasicPaperChat
from app.utils.streaming import stream_dspy_response
import dspy

router = APIRouter(prefix="/chat", tags=["chat"])

# Initialize DSPy
lm = dspy.LM('openai/gpt-4o-mini', api_key='your-api-key')
dspy.configure(lm=lm, async_max_workers=4)

# Initialize RAG module (assuming retriever is set up)
# retriever = PaperRetriever(papers=papers_list)
# rag_module = BasicPaperChat(retriever=retriever)
# rag_module = dspy.asyncify(rag_module)

@router.post("/basic")
async def chat_basic(request: ChatRequest):
    """Basic AI chat with RAG (streaming)"""
    
    if not request.stream:
        # Non-streaming response
        result = await rag_module(
            question=request.question,
            history=None  # TODO: Load from session
        )
        return {
            "answer": result.answer,
            "sources": result.sources
        }
    
    # Streaming response
    async def generate():
        async for chunk in stream_dspy_response(
            rag_module,
            question=request.question,
            history=None  # TODO: Load from session
        ):
            yield chunk
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/deep")
async def chat_deep(request: ChatRequest):
    """Deep research with RLM (future implementation)"""
    raise HTTPException(status_code=501, detail="Not implemented yet")
```

#### `app/main.py`
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import chat, search, health
from app.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="AI-powered paper research platform"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router)
app.include_router(search.router)
app.include_router(health.router)

@app.on_event("startup")
async def startup_event():
    """Initialize DSPy and retrievers"""
    import dspy
    from app.config import settings
    
    # Configure DSPy
    lm = dspy.LM(
        settings.DSPY_MODEL,
        api_key=settings.OPENAI_API_KEY
    )
    dspy.configure(lm=lm, async_max_workers=settings.DSPY_MAX_WORKERS)
    
    print("✅ DSPy configured successfully")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 🔑 Key Implementation Details

### 1. DSPy Async Configuration

```python
import dspy

# Configure LM with async workers
lm = dspy.LM('openai/gpt-4o-mini', api_key='your-key')
dspy.configure(lm=lm, async_max_workers=4)

# Make module async
rag_module = BasicPaperChat(retriever=retriever)
rag_module = dspy.asyncify(rag_module)  # ✅ Important!
```

### 2. Streaming with DSPy

```python
# Method 1: Using streamify
streaming_program = dspy.streamify(rag_module)

async for value in streaming_program(question="..."):
    if isinstance(value, dspy.Prediction):
        # Final result
        print(value.answer)
    elif hasattr(value, 'choices'):
        # Streaming token
        print(value.choices[0].delta.content)
```

### 3. SSE Response Format

```python
# Frontend expects this format:
data: {"type": "token", "content": "Hello"}
data: {"type": "token", "content": " there"}
data: {"type": "sources", "sources": ["paper1", "paper2"]}
data: {"type": "done", "content": "...", "sources": [...]}
data: [DONE]
```

---

## 🎨 Frontend Integration

### React Example

```typescript
// chat.tsx
async function sendMessage(question: string) {
  const response = await fetch('/api/chat/basic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, stream: true })
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        
        if (data.type === 'token') {
          // Append token to message
          setMessage(prev => prev + data.content);
        } else if (data.type === 'sources') {
          // Show sources
          setSources(data.sources);
        } else if (data.type === 'done') {
          // Complete
          setLoading(false);
        }
      }
    }
  }
}
```

---

## 📊 Complete Endpoints Summary

| Endpoint | Method | Description | Streaming |
|----------|--------|-------------|-----------|
| `/api/search` | POST | String search (title/abstract) | ❌ |
| `/api/chat/basic` | POST | RAG chat with papers | ✅ |
| `/api/chat/deep` | POST | Deep research (RLM) | ✅ |
| `/health` | GET | Health check | ❌ |

---

## 🔧 Configuration Options

### DSPy Settings
```python
# For faster responses
dspy.configure(lm=lm, async_max_workers=8)

# For cheaper responses
lm = dspy.LM('openai/gpt-4o-mini', max_tokens=1000)

# For better reasoning
lm = dspy.LM('openai/gpt-4o', max_tokens=2000)
```

### Retriever Settings
```python
# For speed
retriever = dspy.retrievers.Embeddings(
    embedder=embedder,
    corpus=corpus,
    k=3  # Fewer papers
)

# For quality
retriever = dspy.retrievers.Embeddings(
    embedder=embedder,
    corpus=corpus,
    k=10  # More papers
)
```

---

## 🚀 Running the Backend

```bash
# Install dependencies
pip install fastapi uvicorn dspy-ai pydantic-settings orjson

# Set environment variables
export OPENAI_API_KEY="sk-..."

# Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📝 Next Steps

1. ✅ Implement paper retriever with your data
2. ✅ Add conversation history storage (Redis/DB)
3. ✅ Implement deep research with RLM
4. ✅ Add authentication
5. ✅ Deploy with Docker

---

**Ready to implement the retriever with your Telkom paper data?**
