"""Weather inputs and isolated V1 inference provenance."""
from alembic import op
import sqlalchemy as sa

revision = "20261021_generation"
down_revision = "20261020_weather"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("weather_observations", "demo_weather_observations"):
        op.add_column(table, sa.Column("upstream_rainfall_mm", sa.Float()))
        op.add_column(table, sa.Column("upstream_rainfall_period_minutes", sa.Integer()))
        op.add_column(table, sa.Column("coastal_tide_m", sa.Float()))
        op.add_column(table, sa.Column("gauge_datum", sa.String(100)))
    op.create_table("v1_weather_profiles",
        sa.Column("source", sa.String(100), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), primary_key=True),
        sa.Column("dataset_version", sa.String(100), sa.ForeignKey("synthetic_datasets.version"), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False))
    op.create_table("generated_prediction_provenance",
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("synthetic_predictions.id"), primary_key=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("model_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("generated_prediction_provenance")
    op.drop_table("v1_weather_profiles")
    for table in ("weather_observations", "demo_weather_observations"):
        for column in ("gauge_datum", "coastal_tide_m", "upstream_rainfall_period_minutes", "upstream_rainfall_mm"):
            op.drop_column(table, column)
