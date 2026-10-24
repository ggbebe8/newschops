"""Initial newschops schema."""

from backend.migrations.schema_v1 import Base
from alembic import op

revision = "001"
down_revision = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    Base.metadata.drop_all(op.get_bind())
