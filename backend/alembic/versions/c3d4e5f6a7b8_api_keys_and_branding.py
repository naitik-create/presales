"""Encrypted API keys and branding permissions

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=False, server_default=""),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("last4", sa.String(4), nullable=False, server_default=""),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("""
        INSERT INTO permissions (code, area, label) VALUES
            ('admin.api_keys', 'Administration', 'Manage API keys'),
            ('admin.branding', 'Administration', 'Manage branding')
        ON CONFLICT (code) DO NOTHING;
        INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r, permissions p
            WHERE r.name = 'System Administrator' AND p.code IN ('admin.api_keys', 'admin.branding')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('admin.api_keys', 'admin.branding')")
    op.drop_table("api_credentials")
