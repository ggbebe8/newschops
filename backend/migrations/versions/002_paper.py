"""Public Donga newspaper index metadata, never PDF assets."""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"


def upgrade():
    op.create_table(
        "paper_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.String(10), nullable=True),
        sa.Column("section", sa.String(10)),
        sa.Column("page", sa.Integer()),
        sa.Column("position", sa.Integer()),
        sa.Column("title", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("evidence_url", sa.Text()),
        sa.Column("observed", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("date", "section", "page", "position"),
    )
    op.create_index("ix_paper_entries_date", "paper_entries", ["date"])


def downgrade():
    op.drop_table("paper_entries")
