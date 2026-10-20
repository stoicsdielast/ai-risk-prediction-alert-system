"""Saved locations, opt-in preferences and durable operational browser outbox."""
from alembic import op
import sqlalchemy as sa

revision = "20261023_notifications"
down_revision = "20261022_alert_expiry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("saved_locations",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("notification_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("browser_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("notification_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(500)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("claimed_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "alert_id", name="uq_notification_user_alert"),
        sa.CheckConstraint("status IN ('PENDING','DELIVERED','FAILED','CANCELLED')", name="ck_notification_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_notification_attempts"))
    op.create_index("ix_notification_user_status", "notification_outbox", ["user_id", "status"])
    op.create_table("notification_attempts",
        sa.Column("token", sa.String(36), primary_key=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notification_outbox.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("error", sa.String(500)))
    op.create_index("ix_notification_attempts_notification_id", "notification_attempts", ["notification_id"])


def downgrade():
    op.drop_table("notification_attempts")
    op.drop_table("notification_outbox")
    op.drop_table("notification_preferences")
    op.drop_table("saved_locations")
