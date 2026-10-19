"""Weather observations with physically separate research/demo storage."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_weather"
down_revision = "20261019_synthetic"
branch_labels = None
depends_on = None


def upgrade():
    for table, prefix, allowed in [
        ("weather_observations", "weather", "source_type IN ('manual', 'provider')"),
        ("demo_weather_observations", "demo_weather", "source_type = 'synthetic'"),
    ]:
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source", sa.String(100), nullable=False),
            sa.Column("source_type", sa.String(20), nullable=False),
            sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("rainfall_period_minutes", sa.Integer()),
            *[sa.Column(name, sa.Float()) for name in (
                "rainfall_mm", "temperature_c", "humidity_pct", "pressure_hpa", "wind_speed_mps",
                "wind_direction_deg", "river_level_m", "river_discharge_m3s", "soil_moisture_pct")],
            sa.UniqueConstraint("location_id", "source_type", "source", "observed_at", name=f"uq_{prefix}_identity"),
            sa.CheckConstraint(allowed, name="ck_weather_genuine" if prefix == "weather" else "ck_weather_synthetic"),
        )
        op.create_index(f"ix_{table}_location_id", table, ["location_id"])
        op.create_index(f"ix_{table}_observed_at", table, ["observed_at"])


def downgrade():
    op.drop_table("demo_weather_observations")
    op.drop_table("weather_observations")
