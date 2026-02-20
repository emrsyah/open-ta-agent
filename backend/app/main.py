"""
Telkom Paper Research API - Main Application Entry Point

This is the refactored, maintainable version of the backend.
"""

import logging

import dspy
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import get_session_factory, close_db
from app.api.routes import chat, papers, health
from app.services.rag import init_rag_service
from app.services.retriever import PaperRetriever
from app.utils.logging_config import setup_logging


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    settings = get_settings()
    setup_logging(debug=settings.DEBUG)

    # Configure DSPy with dual models
    if settings.is_openrouter():
        logger.info("Using OpenRouter API")
        main_lm = dspy.LM(
            settings.DSPY_MODEL,
            api_base=settings.OPENROUTER_BASE_URL,
            api_key=settings.get_api_key(),
            model_type="chat"
        )
        cheap_lm = dspy.LM(
            settings.DSPY_CHEAP_MODEL,
            api_base=settings.OPENROUTER_BASE_URL,
            api_key=settings.get_api_key(),
            model_type="chat"
        )
        logger.info("Main model: %s", settings.DSPY_MODEL)
        logger.info("Cheap model: %s", settings.DSPY_CHEAP_MODEL)
    else:
        logger.info("Using OpenAI API")
        main_lm = dspy.LM(
            settings.DSPY_FALLBACK_MODEL,
            api_key=settings.get_api_key()
        )
        cheap_lm = dspy.LM(
            "gpt-3.5-turbo",
            api_key=settings.get_api_key()
        )

    dspy.configure(lm=main_lm, async_max_workers=settings.DSPY_MAX_WORKERS)

    app.state.main_lm = main_lm
    app.state.cheap_lm = cheap_lm

    try:
        retriever = PaperRetriever()
        init_rag_service(retriever, cheap_lm=cheap_lm)
        app.state.retriever = retriever

        session_factory = get_session_factory()
        if session_factory is not None:
            # Probe the DB: retriever manages its own session internally
            all_papers = await retriever.get_all_papers(limit=10)
            paper_count = len(all_papers)
            logger.info("%s v%s started", settings.APP_NAME, settings.APP_VERSION)
            logger.info("Database connected")
            logger.info("Loaded %d papers from database", paper_count)
        else:
            logger.warning("Database not configured — using mock data")

    except Exception as e:
        logger.warning("Database connection failed: %s — falling back to mock data", e)
        retriever = PaperRetriever()
        init_rag_service(retriever, cheap_lm=cheap_lm)
        app.state.retriever = retriever

    yield

    # Shutdown
    logger.info("Shutting down...")
    try:
        await close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.warning("Error closing database: %s", e)


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

    # Request logging middleware — logs query for /chat endpoints
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        import time
        import json as _json

        _log = logging.getLogger(__name__)
        start = time.perf_counter()

        # For chat endpoints, parse and log the incoming query
        if request.url.path.startswith("/chat") and request.method == "POST":
            try:
                body_bytes = await request.body()
                body = _json.loads(body_bytes)
                query = body.get("query") or body.get("question") or "<no query>"
                conv_id = (body.get("meta_params") or {}).get("conversation_id") or body.get("conversation_id")
                stream = (body.get("meta_params") or {}).get("stream", body.get("stream", True))
                _log.info(
                    "[REQUEST] %s | query=%r | stream=%s | conversation_id=%s",
                    request.url.path, query, stream, conv_id or "none",
                )

                # Re-attach body so downstream handlers can still read it
                async def receive():
                    return {"type": "http.request", "body": body_bytes, "more_body": False}

                request = Request(request.scope, receive)
            except Exception:
                pass  # Don't break the request if logging fails

        response = await call_next(request)

        duration_ms = int((time.perf_counter() - start) * 1000)
        if request.url.path.startswith("/chat"):
            _log.info(
                "[RESPONSE] %s %s | %dms",
                request.method, request.url.path, duration_ms,
            )

        return response

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
