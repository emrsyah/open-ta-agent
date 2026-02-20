"""Add abstract, embedding column and HNSW index

Revision ID: 002_add_abstract_embedding_hnsw
Revises: 001_initial
Create Date: 2026-02-20

NOTE: If the DB already has these columns (existing deployment), run:
    python db.py pull
instead of push, to stamp the DB as up-to-date without re-running DDL.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "002_add_abstract_embedding_hnsw"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add abstract column (was missing from initial migration)
    op.add_column(
        "catalog",
        sa.Column("abstract", sa.Text(), nullable=True, comment="Paper abstract or summary"),
    )

    # Add embedding column for semantic vector search
    op.add_column(
        "catalog",
        sa.Column(
            "embedding",
            Vector(1024),
            nullable=True,
            comment="Vector embedding of title and abstract (voyage-4-lite, 1024-dim)",
        ),
    )

    # HNSW index for fast approximate nearest-neighbour search.
    # m=16 and ef_construction=64 are conservative defaults that balance
    # build time vs. query speed; tune upward if recall needs improvement.
    op.execute("""
        CREATE INDEX IF NOT EXISTS catalog_embedding_hnsw_idx
        ON catalog
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 24, ef_construction = 128)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS catalog_embedding_hnsw_idx")
    op.drop_column("catalog", "embedding")
    op.drop_column("catalog", "abstract")
