"""Add participant_trip_contacts table and notification settings for group trip participants

When a user joins a group trip, they select their own safety contacts and
configure their personal notification settings (check-in frequency, quiet hours).

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
    """Create participant_trip_contacts table and add notification settings to trip_participants."""

    # Create participant_trip_contacts junction table
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

    # Add personal notification settings to trip_participants table
    # Each participant can set their own check-in frequency and quiet hours
    op.add_column('trip_participants', sa.Column('checkin_interval_min', sa.Integer(), nullable=True))
    op.add_column('trip_participants', sa.Column('notify_start_hour', sa.Integer(), nullable=True))
    op.add_column('trip_participants', sa.Column('notify_end_hour', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Drop participant_trip_contacts table and notification columns."""
    # Remove notification settings from trip_participants
    op.drop_column('trip_participants', 'notify_end_hour')
    op.drop_column('trip_participants', 'notify_start_hour')
    op.drop_column('trip_participants', 'checkin_interval_min')

    # Drop participant_trip_contacts table
    op.drop_index('idx_participant_trip_contacts_contact', table_name='participant_trip_contacts')
    op.drop_index('idx_participant_trip_contacts_trip_user', table_name='participant_trip_contacts')
    op.drop_table('participant_trip_contacts')
