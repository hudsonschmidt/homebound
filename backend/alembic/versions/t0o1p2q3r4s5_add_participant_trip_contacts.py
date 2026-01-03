"""Add participant_trip_contacts table for per-participant safety contacts in group trips

When a user joins a group trip, they select their own safety contacts.
This table stores those per-participant contacts, separate from the trip owner's contacts.

Revision ID: t0o1p2q3r4s5
Revises: s9n0o1p2q3r4
Create Date: 2026-01-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 't0o1p2q3r4s5'
down_revision: Union[str, None] = 's9n0o1p2q3r4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create participant_trip_contacts junction table."""
    op.create_table('participant_trip_contacts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('participant_user_id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=False),
        # Position 1, 2, or 3 for each participant's contacts
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # Each participant can only have one contact at each position per trip
        sa.UniqueConstraint('trip_id', 'participant_user_id', 'position', name='unique_participant_trip_position')
    )
    # Index for efficient lookup by trip + participant
    op.create_index('idx_participant_trip_contacts_trip_user', 'participant_trip_contacts', ['trip_id', 'participant_user_id'])
    # Index for efficient lookup by contact (for cascade operations)
    op.create_index('idx_participant_trip_contacts_contact', 'participant_trip_contacts', ['contact_id'])


def downgrade() -> None:
    """Drop participant_trip_contacts table."""
    op.drop_index('idx_participant_trip_contacts_contact', table_name='participant_trip_contacts')
    op.drop_index('idx_participant_trip_contacts_trip_user', table_name='participant_trip_contacts')
    op.drop_table('participant_trip_contacts')
