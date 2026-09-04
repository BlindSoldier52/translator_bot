"""stop storing message content

Drops every column of the translations table that held message content or
identified who sent it. What is left is one row per translation, for counting.

Revision ID: a7f2e91c4d80
Revises: 8b41c07d5e92
Create Date: 2026-08-26 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7f2e91c4d80'
down_revision: Union[str, None] = '8b41c07d5e92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('translations', 'translated_text')
    op.drop_column('translations', 'original_text')
    op.drop_column('translations', 'source_display_name')
    op.drop_column('translations', 'source_telegram_user_id')
    op.drop_column('translations', 'telegram_message_id')


def downgrade() -> None:
    op.add_column('translations', sa.Column('telegram_message_id', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('translations', sa.Column('source_telegram_user_id', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('translations', sa.Column('source_display_name', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('translations', sa.Column('original_text', sa.Text(), nullable=False, server_default=''))
    op.add_column('translations', sa.Column('translated_text', sa.Text(), nullable=False, server_default=''))
    for column in ('telegram_message_id', 'source_telegram_user_id', 'source_display_name', 'original_text', 'translated_text'):
        op.alter_column('translations', column, server_default=None)
