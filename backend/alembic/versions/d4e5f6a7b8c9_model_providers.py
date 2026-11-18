"""AI models from several providers (Anthropic, OpenAI, Google Gemini, Azure OpenAI)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_models", sa.Column("provider", sa.String(40), nullable=False, server_default="anthropic"))
    op.add_column("ai_models", sa.Column("endpoint", sa.String(300), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("ai_models", "endpoint")
    op.drop_column("ai_models", "provider")
