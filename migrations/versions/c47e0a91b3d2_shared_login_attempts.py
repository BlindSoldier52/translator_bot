"""shared login attempts

Moves brute-force lockout state out of process memory and into the database, so
the bot, the web panel, and any number of panel workers enforce one attempt
budget between them rather than one each.

Revision ID: c47e0a91b3d2
Revises: b9c3d51740af
Create Date: 2026-09-04 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c47e0a91b3d2'
down_revision: Union[str, None] = 'b9c3d51740af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'login_attempts',
        sa.Column('guard', sa.String(length=32), nullable=False),
        sa.Column('identifier', sa.String(length=255), nullable=False),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('guard', 'identifier'),
    )
    op.create_index('ix_login_attempts_locked_until', 'login_attempts', ['locked_until'])


def downgrade() -> None:
    op.drop_index('ix_login_attempts_locked_until', table_name='login_attempts')
    op.drop_table('login_attempts')
