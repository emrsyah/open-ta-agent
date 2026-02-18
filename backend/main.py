"""
Paper Research API - Minimal FastAPI + DSPy Backend
Simple setup for Telkom University paper catalog
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal
import dspy
import os
import json

# =============================================================================
# CONFIGURATION
# =============================================================================

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

if not OPENROUTER_API_KEY:
    print("⚠️  Warning: OPENROUTER_API_KEY not set. Using OpenAI instead.")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("Please set OPENROUTER_API_KEY or OPENAI_API_KEY")

# Configure DSPy
if OPENROUTER_API_KEY:
    print("🚀 Using OpenRouter")
    lm = dspy.LM(
        "openrouter/google/gemini-2.5-pro-preview",
        api_base=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        model_type="chat"
    )
else:
    print("🔑 Using OpenAI")
    lm = dspy.LM("openai/gpt-4o-mini", api_key=OPENAI_API_KEY)

dspy.configure(lm=lm, async_max_workers=4)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class SearchRequest(BaseModel):
    query: str
    limit: int = 5

class Paper(BaseModel):
    id: str
    title: str
    authors: List[str]
    abstract: str
    year: int

class SearchResponse(BaseModel):
    results: List[Paper]
    total: int

class ChatRequest(BaseModel):
    question: str
    stream: bool = True

class ChatResponse(BaseModel):
    answer: str
    sources: List[str]


# =============================================================================
# MOCK DATA (Replace with your Telkom paper data)
# =============================================================================

PAPERS_DB = [
    Paper(
        id="paper_001",
        title="Deep Learning Approaches for Natural Language Processing",
        authors=["Dr. Ahmad Rizky", "Dr. Siti Nurhaliza"],
        abstract="This paper explores various deep learning techniques including transformers and BERT for NLP tasks. We evaluate performance on Indonesian language datasets.",
        year=2023
    ),
    Paper(
        id="paper_002",
        title="Machine Learning Applications in Telecommunications",
        authors=["Prof. Budi Santoso", "Dr. Maya Sari"],
        abstract="A comprehensive study on applying machine learning algorithms to optimize network traffic and predict system failures in telecom infrastructure.",
        year=2024
    ),
    Paper(
        id="paper_003",
        title="Computer Vision for Smart Cities",
        authors=["Dr. Dedi Kurniawan"],
        abstract="Implementation of computer vision algorithms for traffic monitoring, pedestrian detection, and smart surveillance systems in urban environments.",
        year=2023
    ),
    Paper(
        id="paper_004",
        title="Blockchain Technology in Supply Chain Management",
        authors=["Dr. Eko Prasetyo", "Dr. Fitriani", "Rizal Maulana"],
        abstract="This research investigates the application of blockchain technology to improve transparency and traceability in supply chain management systems.",
        year=2024
    ),
    Paper(
        id="paper_005",
        title="IoT Security: Challenges and Solutions",
        authors=["Dr. Gita Permata"],
        abstract="An analysis of security vulnerabilities in IoT devices and proposed cryptographic solutions to protect against common attack vectors.",
        year=2022
    ),
]


# =============================================================================
# DSPy MODULES
# =============================================================================

class PaperChatSignature(dspy.Signature):
    """Answer questions about research papers with citations."""
    question: str = dspy.InputField(desc="User's question about papers")
    context: str = dspy.InputField(desc="Relevant paper abstracts and titles")
    answer: str = dspy.OutputField(desc="Comprehensive answer with citations")
    sources: List[str] = dspy.OutputField(desc="List of paper IDs referenced")


class PaperRAG(dspy.Module):
    """Simple RAG for paper Q&A"""
    
    def __init__(self, papers_db):
        super().__init__()
        self.papers = papers_db
        self.generate = dspy.ChainOfThought(PaperChatSignature)
    
    def forward(self, question: str):
        # Simple keyword-based retrieval (replace with vector search)
        context = self._retrieve(question)
        
        # Generate answer
        result = self.generate(question=question, context=context)
        
        return dspy.Prediction(
            answer=result.answer,
            sources=result.sources
        )
    
    def _retrieve(self, query: str) -> str:
        """Simple retrieval - returns top 3 matching papers"""
        query_lower = query.lower()
        matches = []
        
        for paper in self.papers:
            score = 0
            # Check title
            if any(word in paper.title.lower() for word in query_lower.split()):
                score += 3
            # Check abstract
            if any(word in paper.abstract.lower() for word in query_lower.split()):
                score += 1
            # Check authors
            if any(word in " ".join(paper.authors).lower() for word in query_lower.split()):
                score += 2
            
            if score > 0:
                matches.append((score, paper))
        
        # Sort by relevance and take top 3
        matches.sort(key=lambda x: x[0], reverse=True)
        top_papers = [paper for _, paper in matches[:3]]
        
        # Format as context
        context_parts = []
        for paper in top_papers:
            context_parts.append(
                f"Paper ID: {paper.id}\n"
                f"Title: {paper.title}\n"
                f"Authors: {', '.join(paper.authors)}\n"
                f"Year: {paper.year}\n"
                f"Abstract: {paper.abstract}\n"
            )
        
        return "\n---\n".join(context_parts)


# Initialize RAG
rag_module = PaperRAG(PAPERS_DB)
rag_async = dspy.asyncify(rag_module)


# =============================================================================
# STREAMING UTILITIES
# =============================================================================

def format_sse(data: dict) -> str:
    """Format as Server-Sent Event"""
    return f"data: {json.dumps(data)}\n\n"


async def stream_response(question: str):
    """Stream DSPy response"""
    streaming_module = dspy.streamify(rag_async)
    
    async for value in streaming_module(question=question):
        if isinstance(value, dspy.Prediction):
            # Final result
            data = {
                "type": "done",
                "answer": value.answer,
                "sources": value.sources
            }
            yield format_sse(data)
        elif hasattr(value, 'choices') and value.choices:
            # Streaming token
            delta = value.choices[0].delta
            content = getattr(delta, 'content', '')
            if content:
                yield format_sse({"type": "token", "content": content})
    
    yield "data: [DONE]\n\n"


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Paper Research API",
    description="AI-powered paper research for Telkom University catalog",
    version="1.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:5500", "http://localhost:5500", "null"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """API info"""
    return {
        "message": "Paper Research API",
        "endpoints": {
            "GET /search": "Search papers by keyword",
            "POST /search": "Search papers (POST)",
            "POST /chat": "AI chat with papers (streaming)",
            "GET /papers": "List all papers"
        }
    }


@app.get("/papers")
async def list_papers():
    """List all papers"""
    return {"papers": PAPERS_DB, "total": len(PAPERS_DB)}


@app.get("/search")
async def search_get(query: str, limit: int = 5):
    """Search papers by keyword (GET)"""
    query_lower = query.lower()
    results = []
    
    for paper in PAPERS_DB:
        if (query_lower in paper.title.lower() or 
            query_lower in paper.abstract.lower() or
            any(query_lower in author.lower() for author in paper.authors)):
            results.append(paper)
    
    return SearchResponse(results=results[:limit], total=len(results))


@app.post("/search")
async def search_post(request: SearchRequest):
    """Search papers by keyword (POST)"""
    return await search_get(request.query, request.limit)


@app.post("/chat")
async def chat(request: ChatRequest):
    """AI chat with papers"""
    
    if not request.stream:
        # Non-streaming response
        result = await rag_async(question=request.question)
        return ChatResponse(answer=result.answer, sources=result.sources)
    
    # Streaming response
    return StreamingResponse(
        stream_response(request.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║            Paper Research API - Telkom Univ              ║
    ╠══════════════════════════════════════════════════════════╣
    ║                                                          ║
    ║  🚀 Running at: http://localhost:8000                    ║
    ║                                                          ║
    ║  Endpoints:                                              ║
    ║    GET  /search?query=machine+learning                   ║
    ║    POST /chat                                            ║
    ║    GET  /papers                                          ║
    ║                                                          ║
    ║  Test:                                                   ║
    ║    curl http://localhost:8000/search?query=deep          ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
