"""Add group trips support (trip_participants table, group settings)

Revision ID: s9n0o1p2q3r4
Revises: r8m9n0o1p2q3
Create Date: 2026-01-02

Changes:
- Add trip_participants table for tracking group trip members
- Add is_group_trip and group_settings columns to trips table
- Add checkout_votes table for vote-based checkout mode
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 's9n0o1p2q3r4'
down_revision: Union[str, None] = 'r8m9n0o1p2q3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add group trips support."""

    # Add group trip columns to trips table
    op.add_column('trips', sa.Column('is_group_trip', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('trips', sa.Column('group_settings', sa.JSON(), nullable=True))

    # Create trip_participants table
    op.create_table('trip_participants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=32), server_default='participant', nullable=False),  # 'owner' or 'participant'
        sa.Column('status', sa.String(length=32), server_default='invited', nullable=False),  # 'invited', 'accepted', 'declined', 'left'
        sa.Column('invited_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('invited_by', sa.Integer(), nullable=True),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.Column('left_at', sa.DateTime(), nullable=True),
        sa.Column('invitation_expires_at', sa.DateTime(), nullable=True),  # Optional expiration for invitations
        sa.Column('last_checkin_at', sa.DateTime(), nullable=True),
        sa.Column('last_lat', sa.Float(), nullable=True),
        sa.Column('last_lon', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trip_id', 'user_id', name='unique_trip_participant')
    )
    op.create_index('idx_trip_participants_trip', 'trip_participants', ['trip_id'])
    op.create_index('idx_trip_participants_user', 'trip_participants', ['user_id'])
    op.create_index('idx_trip_participants_status', 'trip_participants', ['status'])

    # Create checkout_votes table for vote-based checkout mode
    op.create_table('checkout_votes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('voted_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trip_id', 'user_id', name='unique_checkout_vote')
    )
    op.create_index('idx_checkout_votes_trip', 'checkout_votes', ['trip_id'])


def downgrade() -> None:
    """Remove group trips support."""
    op.drop_index('idx_checkout_votes_trip', table_name='checkout_votes')
    op.drop_table('checkout_votes')

    op.drop_index('idx_trip_participants_status', table_name='trip_participants')
    op.drop_index('idx_trip_participants_user', table_name='trip_participants')
    op.drop_index('idx_trip_participants_trip', table_name='trip_participants')
    op.drop_table('trip_participants')

    op.drop_column('trips', 'group_settings')
    op.drop_column('trips', 'is_group_trip')
