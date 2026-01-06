"""Add friend_user_id to participant_trip_contacts

Allow participants to select friends (not just email contacts) as their safety contacts.

Revision ID: v1w2x3y4z5a6
Revises: u1p2q3r4s5t6
Create Date: 2026-01-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'v1w2x3y4z5a6'
down_revision: Union[str, None] = 'u1p2q3r4s5t6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add friend_user_id column to participant_trip_contacts.

    Each row now has either contact_id OR friend_user_id (one must be set).
    """
    # Make contact_id nullable (since rows can now have friend_user_id instead)
    op.alter_column('participant_trip_contacts', 'contact_id',
                    existing_type=sa.Integer(),
                    nullable=True)

    # Add friend_user_id column
    op.add_column('participant_trip_contacts',
                  sa.Column('friend_user_id', sa.Integer(), nullable=True))

    # Add foreign key for friend_user_id
    op.create_foreign_key(
        'fk_participant_trip_contacts_friend_user',
        'participant_trip_contacts', 'users',
        ['friend_user_id'], ['id'],
        ondelete='CASCADE'
    )

    # Index for efficient lookup by friend user
    op.create_index('idx_participant_trip_contacts_friend',
                    'participant_trip_contacts', ['friend_user_id'])


def downgrade() -> None:
    """Remove friend_user_id column."""
    op.drop_index('idx_participant_trip_contacts_friend', table_name='participant_trip_contacts')
    op.drop_constraint('fk_participant_trip_contacts_friend_user',
                       'participant_trip_contacts', type_='foreignkey')
    op.drop_column('participant_trip_contacts', 'friend_user_id')

    # Make contact_id NOT NULL again (will fail if there are friend-only rows)
    op.alter_column('participant_trip_contacts', 'contact_id',
                    existing_type=sa.Integer(),
                    nullable=False)
