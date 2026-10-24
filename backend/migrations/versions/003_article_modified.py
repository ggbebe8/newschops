"""Store explicit modification time separately from publication time."""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"


def upgrade():
    op.add_column(
        "articles", sa.Column("modified", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "issues",
        sa.Column(
            "time_estimated", sa.Boolean(), server_default=sa.false(), nullable=True
        ),
    )
    op.execute(
        "UPDATE issues SET time_estimated=true WHERE NOT EXISTS (SELECT 1 FROM articles WHERE articles.issue_id=issues.id AND articles.published IS NOT NULL)"
    )


def downgrade():
    op.drop_column("issues", "time_estimated")
    op.drop_column("articles", "modified")
