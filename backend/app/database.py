"""
Database configuration and session management.
Uses SQLAlchemy 2.0 async pattern for PostgreSQL.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator, Optional

from app.config import get_settings

# Base class for all models
Base = declarative_base()

# Global variables (initialized lazily)
_async_engine = None
_AsyncSessionLocal = None


def _ensure_async_driver(url: str) -> str:
    """Ensure the URL uses an async driver."""
    if url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def get_engine():
    """Get or create the async engine (lazy initialization)."""
    global _async_engine
    if _async_engine is None:
        settings = get_settings()
        try:
            database_url = settings.get_database_url()
            database_url = _ensure_async_driver(database_url)
            
            connect_args = {}
            if 'supabase' in database_url:
                # Supabase requires SSL
                connect_args['ssl'] = 'require'
                # PgBouncer compatibility - disable prepared statements
                if 'pooler' in database_url:
                    connect_args['statement_cache_size'] = 0
                    connect_args['prepared_statement_cache_size'] = 0
            
            _async_engine = create_async_engine(
                database_url,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_POOL_TIMEOUT,
                pool_recycle=settings.DB_POOL_RECYCLE,
                echo=settings.DEBUG,
                future=True,
                connect_args=connect_args,
            )
        except ValueError as e:
            # Database not configured - return None
            print(f"⚠️  Database not configured: {e}")
            return None
    return _async_engine


def get_session_factory():
    """Get or create the session factory."""
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        engine = get_engine()
        if engine is None:
            return None
        
        _AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _AsyncSessionLocal


# Keep AsyncSessionLocal for compatibility
AsyncSessionLocal = get_session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session.
    Usage: async def endpoint(db: AsyncSession = Depends(get_db))
    """
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL in .env file.")
    
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables (for development only)."""
    engine = get_engine()
    if engine is None:
        return
    
    async with engine.begin() as conn:
        # Note: In production, use Alembic migrations instead
        # await conn.run_sync(Base.metadata.create_all)
        pass


async def close_db():
    """Close database connections."""
    global _async_engine
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
