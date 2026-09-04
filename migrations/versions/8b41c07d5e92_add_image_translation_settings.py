"""add image translation settings

Revision ID: 8b41c07d5e92
Revises: 564d21879e24
Create Date: 2026-08-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8b41c07d5e92'
down_revision: Union[str, None] = '564d21879e24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('groups', sa.Column('image_translation_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('groups', sa.Column('image_max_size_mb', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('groups', sa.Column('image_output_mode', sa.String(length=10), nullable=False, server_default='text'))
    op.add_column('groups', sa.Column('image_uses_separate_daily_limit', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('groups', sa.Column('image_daily_limit', sa.Integer(), nullable=True))

    op.add_column('users', sa.Column('image_translation_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('image_max_size_mb', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('users', sa.Column('image_output_mode', sa.String(length=10), nullable=False, server_default='text'))

    for table in ('groups', 'users'):
        op.alter_column(table, 'image_translation_enabled', server_default=None)
        op.alter_column(table, 'image_max_size_mb', server_default=None)
        op.alter_column(table, 'image_output_mode', server_default=None)
    op.alter_column('groups', 'image_uses_separate_daily_limit', server_default=None)

    op.create_table(
        'group_image_daily_counters',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('translated_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.PrimaryKeyConstraint('group_id', 'date'),
    )


def downgrade() -> None:
    op.drop_table('group_image_daily_counters')

    op.drop_column('users', 'image_output_mode')
    op.drop_column('users', 'image_max_size_mb')
    op.drop_column('users', 'image_translation_enabled')

    op.drop_column('groups', 'image_daily_limit')
    op.drop_column('groups', 'image_uses_separate_daily_limit')
    op.drop_column('groups', 'image_output_mode')
    op.drop_column('groups', 'image_max_size_mb')
    op.drop_column('groups', 'image_translation_enabled')
