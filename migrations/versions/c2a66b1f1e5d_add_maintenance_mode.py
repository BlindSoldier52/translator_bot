"""add maintenance mode

Revision ID: c2a66b1f1e5d
Revises: 077c4d772fa9
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2a66b1f1e5d'
down_revision: Union[str, None] = '077c4d772fa9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('app_settings', sa.Column('maintenance_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('app_settings', sa.Column('maintenance_message', sa.Text(), nullable=True))
    op.alter_column('app_settings', 'maintenance_enabled', server_default=None)

    op.create_table(
        'group_maintenance_notices',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.PrimaryKeyConstraint('group_id'),
    )


def downgrade() -> None:
    op.drop_table('group_maintenance_notices')
    op.drop_column('app_settings', 'maintenance_message')
    op.drop_column('app_settings', 'maintenance_enabled')
