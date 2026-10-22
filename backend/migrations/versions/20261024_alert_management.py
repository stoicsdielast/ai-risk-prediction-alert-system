"""Retain alert acknowledgement and closure audit; mark isolated low-risk tests.

Additive upgrade: no alert, prediction, observation or user is deleted or rewritten.
PostgreSQL enum literals in the new check are compared as text so the new enum
labels are not used before the migration transaction commits.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_alert_management"
down_revision = "20261023_notifications"
branch_labels = None
depends_on = None


def upgrade():
    for label in ("RESOLVED", "CANCELLED"):
        op.execute(f"ALTER TYPE alert_status ADD VALUE IF NOT EXISTS '{label}'")
    for table, suffix in (("alerts", "_user_id"), ("synthetic_alerts", "")):
        for prefix in ("acknowledged", "closed"):
            op.add_column(table, sa.Column(f"{prefix}_by{suffix}", sa.Integer(),
                sa.ForeignKey("users.id", name=f"fk_{table}_{prefix}_by", ondelete="RESTRICT")))
            op.add_column(table, sa.Column(f"{prefix}_at", sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column("closure_reason", sa.String(1000)))
        op.create_check_constraint(f"ck_{'alert' if table == 'alerts' else 'synthetic'}_closure_audit", table,
            f"CAST(status AS VARCHAR) NOT IN ('RESOLVED','CANCELLED') OR (closed_by{suffix} IS NOT NULL "
            "AND closed_at IS NOT NULL AND closure_reason IS NOT NULL AND length(trim(closure_reason)) > 0)")
    op.create_check_constraint("ck_alert_acknowledgement_audit", "alerts",
        "(acknowledged_by_user_id IS NULL) = (acknowledged_at IS NULL)")
    op.add_column("synthetic_alerts", sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_constraint("ck_synthetic_alert_status", "synthetic_alerts", type_="check")
    op.create_check_constraint("ck_synthetic_alert_status", "synthetic_alerts",
        "status IN ('PENDING','APPROVED','REJECTED','RESOLVED','CANCELLED')")


def downgrade():
    # Refuse to discard audit history. Export/migrate reviewed records before rollback.
    bind = op.get_bind()
    for table in ("alerts", "synthetic_alerts"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE acknowledged_at IS NOT NULL OR closed_at IS NOT NULL")):
            raise RuntimeError("Cannot downgrade: alert acknowledgement/closure audit exists")
    if bind.scalar(sa.text("SELECT count(*) FROM synthetic_alerts WHERE is_test")):
        raise RuntimeError("Cannot downgrade: isolated test-alert records exist")
    op.drop_constraint("ck_alert_acknowledgement_audit", "alerts", type_="check")
    for table, prefix, suffix in (("alerts", "alert", "_user_id"), ("synthetic_alerts", "synthetic", "")):
        op.drop_constraint(f"ck_{prefix}_closure_audit", table, type_="check")
        for name in (f"acknowledged_by{suffix}", "acknowledged_at", f"closed_by{suffix}", "closed_at", "closure_reason"):
            op.drop_column(table, name)
    op.drop_column("synthetic_alerts", "is_test")
    op.drop_constraint("ck_synthetic_alert_status", "synthetic_alerts", type_="check")
    op.create_check_constraint("ck_synthetic_alert_status", "synthetic_alerts", "status IN ('PENDING','APPROVED','REJECTED')")
    # PostgreSQL enum labels remain; removing them requires rebuilding the type.
