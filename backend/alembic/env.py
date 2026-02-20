"""
Alembic environment configuration.
Run migrations: alembic upgrade head
Create migration: alembic revision --autogenerate -m "description"
"""

import asyncio
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from alembic import context

from app.config import get_settings
from app.database import Base
from app.db.models import Catalog, CatalogType  # noqa: F401 — registers models with metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Build synchronous DB URL for Alembic (psycopg2) from app settings
# ---------------------------------------------------------------------------
settings = get_settings()
from app.database import _ensure_async_driver
_async_url = _ensure_async_driver(settings.get_database_url())
_sync_url = _async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

# Supabase requires SSL; append sslmode if not already present
if "supabase" in _sync_url and "sslmode" not in _sync_url:
    _sep = "&" if "?" in _sync_url else "?"
    _sync_url = f"{_sync_url}{_sep}sslmode=require"

config.set_main_option("sqlalchemy.url", _sync_url)


# ---------------------------------------------------------------------------
# pgvector autogenerate hooks
# Prevents Vector columns from being flagged as "changed" on every run.
# ---------------------------------------------------------------------------

def _render_item(obj_type, obj, autogen_context):
    """Teach Alembic how to render pgvector Vector columns."""
    if obj_type == "type":
        try:
            from pgvector.sqlalchemy import Vector
            if isinstance(obj, Vector):
                autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
                return f"Vector({obj.dim})"
        except ImportError:
            pass
    return False  # fall back to default rendering


def _compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """
    Skip type-change detection for Vector columns so autogenerate doesn't
    emit spurious ALTER COLUMN statements every time.
    """
    try:
        from pgvector.sqlalchemy import Vector
        if isinstance(metadata_type, Vector):
            return False  # False = "no change"
    except ImportError:
        pass
    return None  # None = use default comparison


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=_render_item,
        compare_type=_compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=_render_item,
        compare_type=_compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    # Build the async URL directly — the config URL was overwritten with the
    # psycopg2 variant for offline/autogenerate use, so we re-derive it here.
    async_url = _async_url
    connect_args = {}
    if "supabase" in async_url:
        connect_args["ssl"] = "require"
        if "pooler" in async_url:
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0

    connectable = create_async_engine(
        async_url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
