"""Reviewed alert expiry timestamp for public visibility."""
from alembic import op
import sqlalchemy as sa

revision = "20261022_alert_expiry"
down_revision = "20261021_generation"
branch_labels = None
depends_on = None


def upgrade():
    # Existing reviewed alerts stay non-expiring (NULL) until a future approval.
    op.add_column("alerts", sa.Column("expires_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("alerts", "expires_at")
