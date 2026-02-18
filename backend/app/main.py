"""
Telkom Paper Research API - Main Application Entry Point

This is the refactored, maintainable version of the backend.
"""

import dspy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import get_session_factory, close_db, get_engine
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
    
    # Configure DSPy with dual models
    if settings.is_openrouter():
        print("🚀 Using OpenRouter API")
        # Main model for high-quality answer generation
        main_lm = dspy.LM(
            settings.DSPY_MODEL,
            api_base=settings.OPENROUTER_BASE_URL,
            api_key=settings.get_api_key(),
            model_type="chat"
        )
        # Cheap model for query generation and simple tasks
        cheap_lm = dspy.LM(
            settings.DSPY_CHEAP_MODEL,
            api_base=settings.OPENROUTER_BASE_URL,
            api_key=settings.get_api_key(),
            model_type="chat"
        )
        print(f"   Main model: {settings.DSPY_MODEL}")
        print(f"   Cheap model: {settings.DSPY_CHEAP_MODEL}")
    else:
        print("🔑 Using OpenAI API")
        main_lm = dspy.LM(
            settings.DSPY_FALLBACK_MODEL,
            api_key=settings.get_api_key()
        )
        cheap_lm = dspy.LM(
            "gpt-3.5-turbo",  # Cheap fallback
            api_key=settings.get_api_key()
        )
    
    # Configure default LM (main model)
    dspy.configure(lm=main_lm, async_max_workers=settings.DSPY_MAX_WORKERS)
    
    # Store both models in app state
    app.state.main_lm = main_lm
    app.state.cheap_lm = cheap_lm
    
    # Initialize database connection and services
    db_session = None
    try:
        # Try to initialize database
        session_factory = get_session_factory()
        
        if session_factory is not None:
            # Create a database session for the retriever
            db_session = session_factory()
            retriever = PaperRetriever()
            retriever.set_session(db_session)
            
            # Store retriever in app state for dependency injection
            app.state.retriever = retriever
            app.state.db_session = db_session
            
            init_rag_service(retriever, cheap_lm=cheap_lm)
            
            # Get paper count from database
            all_papers = await retriever.get_all_papers(limit=1000)
            paper_count = len(all_papers)
            
            # Close the session - it will be recreated per-request
            await db_session.close()
            db_session = None
            
            print(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} started")
            print(f"🗄️  Database connected")
            print(f"📚 Loaded {paper_count} papers from database")
        else:
            # Database not configured
            print("⚠️  Database not configured")
            print("📚 Using mock data (set DATABASE_URL in .env to use real database)")
            retriever = PaperRetriever()
            init_rag_service(retriever, cheap_lm=cheap_lm)
            app.state.retriever = retriever
        
    except Exception as e:
        print(f"⚠️  Database connection failed: {e}")
        print("📚 Falling back to mock data")
        if db_session:
            await db_session.close()
        retriever = PaperRetriever()
        init_rag_service(retriever, cheap_lm=cheap_lm)
        app.state.retriever = retriever
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")
    
    # Close database connections
    try:
        if hasattr(app.state, 'db_session'):
            await app.state.db_session.close()
        await close_db()
        print("🗄️  Database connections closed")
    except Exception as e:
        print(f"⚠️  Error closing database: {e}")


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
    
    # Check if database is configured
    try:
        settings.get_database_url()
        db_status = "🗄️  Database: Configured"
    except ValueError:
        db_status = "⚠️  Database: Not configured"
    
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║            {settings.APP_NAME:<42} ║
    ╠══════════════════════════════════════════════════════════╣
    ║                                                          ║
    ║  🚀 Running at: http://{settings.HOST}:{settings.PORT:<4}                    ║
    ║  {db_status:<54}║
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
