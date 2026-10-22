"""Add isolated synthetic demonstration tables to the existing application."""
from alembic import op
import sqlalchemy as sa

revision = "20261019_synthetic"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("synthetic_datasets", sa.Column("version", sa.String(100), primary_key=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True)))
    op.create_table("synthetic_observations", sa.Column("dataset_version", sa.String(100), sa.ForeignKey("synthetic_datasets.version"), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), primary_key=True), sa.Column("values", sa.JSON(), nullable=False))
    op.create_index("ix_synthetic_observations_observed_at", "synthetic_observations", ["observed_at"])
    op.create_table("synthetic_predictions", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_version", sa.String(100), sa.ForeignKey("synthetic_datasets.version"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("model_version", sa.String(150), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False), sa.Column("risk_category", sa.String(20), nullable=False),
        sa.UniqueConstraint("dataset_version", "location_id", "observed_at", "model_version", name="uq_synthetic_prediction"),
        sa.CheckConstraint("probability >= 0 AND probability <= 1", name="ck_synthetic_probability"))
    op.create_table("synthetic_alerts", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("synthetic_predictions.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_synthetic_alert_status"))


def downgrade():
    # Explicit operator-controlled rollback only; never invoked by import/replay.
    for name in ["synthetic_alerts", "synthetic_predictions", "synthetic_observations", "synthetic_datasets"]:
        op.drop_table(name)
