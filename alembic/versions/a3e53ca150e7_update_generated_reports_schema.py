
"""update_generated_reports_schema

Revision ID: a3e53ca150e7
Revises: dfefb21cc00e
Create Date: 2026-04-06 14:49:59.586251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3e53ca150e7'
down_revision: Union[str, None] = 'dfefb21cc00e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
