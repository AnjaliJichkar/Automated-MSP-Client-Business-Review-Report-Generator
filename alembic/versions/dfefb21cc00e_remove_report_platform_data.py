
"""remove_report_platform_data

Revision ID: dfefb21cc00e
Revises: af8b81a1526d
Create Date: 2026-04-06 11:29:05.181136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dfefb21cc00e'
down_revision: Union[str, None] = 'af8b81a1526d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table was already dropped directly in Supabase — nothing to do here.
    pass


def downgrade() -> None:
    # Nothing to undo — table was dropped directly in Supabase.
    pass
