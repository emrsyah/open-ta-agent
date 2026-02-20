"""Add conversations and messages tables for chat history

Revision ID: 003_add_conversations_messages
Revises: 002_add_abstract_embedding_hnsw
Create Date: 2026-02-20
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "003_add_conversations_messages"
down_revision = "002_add_abstract_embedding_hnsw"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(128), primary_key=True, comment="Client-generated conversation ID"),
        sa.Column("title", sa.Text(), nullable=True, comment="Auto-generated from first question"),
        sa.Column("is_incognito", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="Chat conversation sessions",
    )
    op.create_index("conversations_created_at_idx", "conversations", ["created_at"], postgresql_using="btree")

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(128), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources", JSONB(), nullable=True, comment="Array of CitedPaper dicts"),
        sa.Column("search_query", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="Individual Q&A turns within a conversation",
    )
    op.create_index("messages_conversation_id_idx", "messages", ["conversation_id"], postgresql_using="btree")


def downgrade() -> None:
    op.drop_index("messages_conversation_id_idx", table_name="messages")
    op.drop_table("messages")
    op.drop_index("conversations_created_at_idx", table_name="conversations")
    op.drop_table("conversations")
