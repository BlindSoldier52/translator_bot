"""add file translation settings

Revision ID: 564d21879e24
Revises: c2a66b1f1e5d
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '564d21879e24'
down_revision: Union[str, None] = 'c2a66b1f1e5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_EXTENSIONS = sa.text("'[\".txt\", \".pdf\"]'::jsonb")


def upgrade() -> None:
    op.add_column('groups', sa.Column('file_translation_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('groups', sa.Column('file_allowed_extensions', postgresql.JSONB(), nullable=False, server_default=DEFAULT_EXTENSIONS))
    op.add_column('groups', sa.Column('file_max_size_mb', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('groups', sa.Column('file_output_mode', sa.String(length=10), nullable=False, server_default='text'))
    op.add_column('groups', sa.Column('file_uses_separate_daily_limit', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('groups', sa.Column('file_daily_limit', sa.Integer(), nullable=True))

    op.add_column('users', sa.Column('file_translation_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('file_allowed_extensions', postgresql.JSONB(), nullable=False, server_default=DEFAULT_EXTENSIONS))
    op.add_column('users', sa.Column('file_max_size_mb', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('users', sa.Column('file_output_mode', sa.String(length=10), nullable=False, server_default='text'))

    for table in ('groups', 'users'):
        op.alter_column(table, 'file_translation_enabled', server_default=None)
        op.alter_column(table, 'file_allowed_extensions', server_default=None)
        op.alter_column(table, 'file_max_size_mb', server_default=None)
        op.alter_column(table, 'file_output_mode', server_default=None)
    op.alter_column('groups', 'file_uses_separate_daily_limit', server_default=None)

    op.create_table(
        'group_file_daily_counters',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('translated_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.PrimaryKeyConstraint('group_id', 'date'),
    )


def downgrade() -> None:
    op.drop_table('group_file_daily_counters')

    op.drop_column('users', 'file_output_mode')
    op.drop_column('users', 'file_max_size_mb')
    op.drop_column('users', 'file_allowed_extensions')
    op.drop_column('users', 'file_translation_enabled')

    op.drop_column('groups', 'file_daily_limit')
    op.drop_column('groups', 'file_uses_separate_daily_limit')
    op.drop_column('groups', 'file_output_mode')
    op.drop_column('groups', 'file_max_size_mb')
    op.drop_column('groups', 'file_allowed_extensions')
    op.drop_column('groups', 'file_translation_enabled')
