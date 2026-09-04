"""index foreign keys

PostgreSQL indexes the referenced primary key of a foreign key, never the
referencing column, so every lookup by owner, group or user was a sequential
scan. Columns already covered by the leading edge of a unique constraint
(group_warnings.group_id, announcement_deliveries.announcement_id) are left
alone.

Revision ID: b9c3d51740af
Revises: a7f2e91c4d80
Create Date: 2026-09-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b9c3d51740af'
down_revision: Union[str, None] = 'a7f2e91c4d80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = (
    ('ix_groups_owner_user_id', 'groups', 'owner_user_id'),
    ('ix_translations_group_id', 'translations', 'group_id'),
    ('ix_announcements_created_by_admin_id', 'announcements', 'created_by_admin_id'),
    ('ix_announcement_deliveries_user_id', 'announcement_deliveries', 'user_id'),
    ('ix_feedback_user_id', 'feedback', 'user_id'),
)


def upgrade() -> None:
    for name, table, column in INDEXES:
        op.create_index(name, table, [column])


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
