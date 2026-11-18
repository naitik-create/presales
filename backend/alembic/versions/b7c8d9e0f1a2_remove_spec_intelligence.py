"""Remove Spec Intelligence (module withdrawn by the owner, 18 Nov 2026)

Drops the spec pack and clause library tables, the RFP seeded-clause link, the demo POC flag,
the spec/clauses permissions and the two spec agents. Audit and usage history is kept.
Downgrade is not supported: restore the pre-removal backup instead.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
"""
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

SPEC_TABLES = ["pack_exports", "pack_reviews", "tailoring_runs", "spec_pack_versions", "spec_packs",
               "clause_compliance_checks", "clause_versions", "clauses", "spec_files", "spec_config"]


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clauses_tags")
    for t in SPEC_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("ALTER TABLE rfp_requirements DROP COLUMN IF EXISTS seeded_clause_key")
    op.execute("ALTER TABLE demo_use_cases DROP COLUMN IF EXISTS is_poc")
    op.execute("DELETE FROM permissions WHERE code LIKE 'spec.%' OR code LIKE 'clauses.%'")  # role links cascade
    op.execute("DELETE FROM ai_agent_configurations WHERE agent_key IN ('clause_tailoring', 'clause_compliance')")
    op.execute("""
        UPDATE knowledge_sections SET used_by = 'Ask Motadata, RFP Intelligence' WHERE key IN
            ('specifications', 'datasheets', 'prerequisites', 'architecture_and_deployment', 'integrations', 'licensing');
        UPDATE knowledge_sections SET used_by = 'Ask Motadata sizing rules, RFP Intelligence' WHERE key = 'hardware_requirements_and_sizing';
        UPDATE knowledge_sections SET used_by = 'Demo Intelligence' WHERE key IN ('competitor_information', 'demo_use_cases');
        UPDATE knowledge_sections SET used_by = 'RFP Intelligence' WHERE key = 'templates_and_samples';
        UPDATE knowledge_sections SET used_by = 'Ask Motadata, RFP Intelligence' WHERE key = 'internal_presales_knowledge';
        UPDATE roles SET description = 'All modules; approves RFP answers and scoring transactions' WHERE name = 'Presales Manager';
        UPDATE roles SET description = 'Uploads, approves and maintains Knowledge Hub sources' WHERE name = 'Knowledge Administrator';
    """)


def downgrade() -> None:
    raise RuntimeError("Spec Intelligence removal cannot be downgraded; restore the pre-removal backup")
