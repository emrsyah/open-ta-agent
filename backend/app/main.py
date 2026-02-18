"""
Telkom Paper Research API - Main Application Entry Point

This is the refactored, maintainable version of the backend.
"""

import dspy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.api.routes import chat, papers, health
from app.services.rag import init_rag_service
from app.services.retriever import PaperRetriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    settings = get_settings()
    
    # Configure DSPy
    if settings.is_openrouter():
        print("🚀 Using OpenRouter API")
        lm = dspy.LM(
            settings.DSPY_MODEL,
            api_base=settings.OPENROUTER_BASE_URL,
            api_key=settings.get_api_key(),
            model_type="chat"
        )
    else:
        print("🔑 Using OpenAI API")
        lm = dspy.LM(
            settings.DSPY_FALLBACK_MODEL,
            api_key=settings.get_api_key()
        )
    
    dspy.configure(lm=lm, async_max_workers=settings.DSPY_MAX_WORKERS)
    
    # Initialize services
    retriever = PaperRetriever()
    init_rag_service(retriever)
    
    print(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"📚 Loaded {len(retriever.get_all_papers())} papers")
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    
    # Include routers
    app.include_router(health.router)
    app.include_router(papers.router)
    app.include_router(chat.router)
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║            {settings.APP_NAME:<42} ║
    ╠══════════════════════════════════════════════════════════╣
    ║                                                          ║
    ║  🚀 Running at: http://{settings.HOST}:{settings.PORT:<4}                    ║
    ║                                                          ║
    ║  Available Endpoints:                                    ║
    ║    GET  /health              - Health check              ║
    ║    GET  /papers/search       - Search papers             ║
    ║    GET  /papers/list         - List all papers           ║
    ║    POST /chat/basic          - AI chat (streaming)       ║
    ║                                                          ║
    ║  Test Commands:                                          ║
    ║    curl http://localhost:{settings.PORT}/health                         ║
    ║    curl "http://localhost:{settings.PORT}/papers/search?query=ML"       ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
