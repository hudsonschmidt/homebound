"""Make friend_invites support permanent (reusable) links

Revision ID: q7l8m9n0o1p2
Revises: p6k7l8m9n0o1
Create Date: 2025-12-29

Changes:
- Make expires_at nullable (NULL = permanent, never expires)
- Make max_uses nullable (NULL = unlimited uses)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q7l8m9n0o1p2'
down_revision: Union[str, None] = 'p6k7l8m9n0o1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make expires_at and max_uses nullable for permanent invites."""
    # Make expires_at nullable (NULL = never expires)
    op.alter_column('friend_invites', 'expires_at',
        existing_type=sa.DateTime(),
        nullable=True
    )

    # Make max_uses nullable (NULL = unlimited uses)
    op.alter_column('friend_invites', 'max_uses',
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default='1'
    )


def downgrade() -> None:
    """Revert expires_at and max_uses to NOT NULL."""
    # Note: This will fail if there are any NULL values in the columns
    # First, update any NULL values to defaults
    op.execute("""
        UPDATE friend_invites
        SET expires_at = CURRENT_TIMESTAMP + INTERVAL '7 days'
        WHERE expires_at IS NULL
    """)
    op.execute("""
        UPDATE friend_invites
        SET max_uses = 1
        WHERE max_uses IS NULL
    """)

    # Then make columns NOT NULL again
    op.alter_column('friend_invites', 'expires_at',
        existing_type=sa.DateTime(),
        nullable=False
    )
    op.alter_column('friend_invites', 'max_uses',
        existing_type=sa.Integer(),
        nullable=False,
        existing_server_default='1'
    )
