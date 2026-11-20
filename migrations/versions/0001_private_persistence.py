"""Private workspace persistence; no account registration or authentication."""
from alembic import op

revision = "0001_private"
down_revision = None


def upgrade():
    from pathlib import Path
    sql = (Path(__file__).parents[1] / "private_schema.sql").read_text()
    from sqlalchemy import text
    op.get_bind().execute(text(sql))


def downgrade():
    raise RuntimeError("Destructive downgrade disabled. Restore a verified private checkpoint into a new DB.")
