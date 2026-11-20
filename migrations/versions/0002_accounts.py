"""Verified accounts, opaque sessions, granular authorization and audit."""
from alembic import op
from sqlalchemy import text
from pathlib import Path
revision = '0002_accounts'
down_revision = '0001_private'


def upgrade():
    op.get_bind().execute(text((Path(__file__).parents[1]/'accounts.sql').read_text()))


def downgrade():
    raise RuntimeError('Restore a coordinated private checkpoint; destructive authentication downgrade is disabled.')
