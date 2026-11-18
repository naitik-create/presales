"""Immutability triggers for audit and scoring records (§11.5, §14.3)

No one, including administrators, can edit or delete audit records, approved scoring transactions,
or scoring comments through the application account.

Revision ID: a1b2c3d4e5f6
Revises: 50de8a4f949b
"""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "50de8a4f949b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION reject_change() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION '% records cannot be modified or deleted', TG_TABLE_NAME;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER audit_logs_immutable BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION reject_change();

    CREATE TRIGGER scoring_comments_immutable BEFORE UPDATE OR DELETE ON scoring_comments
        FOR EACH ROW EXECUTE FUNCTION reject_change();

    CREATE OR REPLACE FUNCTION scoring_tx_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'scoring transactions cannot be deleted';
        END IF;
        IF OLD.status <> 'Pending Approval' THEN
            RAISE EXCEPTION 'decided scoring transactions cannot be modified';
        END IF;
        IF NEW.employee_id <> OLD.employee_id OR NEW.points <> OLD.points OR NEW.rule_id <> OLD.rule_id
           OR NEW.reason <> OLD.reason OR NEW.evidence <> OLD.evidence THEN
            RAISE EXCEPTION 'only the decision can be recorded on a pending transaction';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER scoring_transactions_guard BEFORE UPDATE OR DELETE ON scoring_transactions
        FOR EACH ROW EXECUTE FUNCTION scoring_tx_guard();

    CREATE OR REPLACE FUNCTION warning_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'warning records cannot be deleted';
        END IF;
        IF OLD.acknowledged_at IS NOT NULL OR NEW.level <> OLD.level OR NEW.score_at <> OLD.score_at
           OR NEW.reason <> OLD.reason OR NEW.employee_id <> OLD.employee_id THEN
            RAISE EXCEPTION 'only the acknowledgement can be recorded on a warning';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER warning_records_guard BEFORE UPDATE OR DELETE ON warning_records
        FOR EACH ROW EXECUTE FUNCTION warning_guard();

    CREATE INDEX IF NOT EXISTS ix_clauses_tags ON clauses USING gin (tags);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TRIGGER IF EXISTS warning_records_guard ON warning_records;
    DROP TRIGGER IF EXISTS scoring_transactions_guard ON scoring_transactions;
    DROP TRIGGER IF EXISTS scoring_comments_immutable ON scoring_comments;
    DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;
    DROP FUNCTION IF EXISTS warning_guard();
    DROP FUNCTION IF EXISTS scoring_tx_guard();
    DROP FUNCTION IF EXISTS reject_change();
    DROP INDEX IF EXISTS ix_clauses_tags;
    """)
