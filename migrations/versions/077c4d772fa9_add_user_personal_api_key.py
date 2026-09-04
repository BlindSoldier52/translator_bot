"""add user personal api key

Revision ID: 077c4d772fa9
Revises: d3aa3cbf9615
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '077c4d772fa9'
down_revision: Union[str, None] = 'd3aa3cbf9615'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('api_key_provider', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('api_key_encrypted', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('api_key_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'api_key_updated_at')
    op.drop_column('users', 'api_key_encrypted')
    op.drop_column('users', 'api_key_provider')
