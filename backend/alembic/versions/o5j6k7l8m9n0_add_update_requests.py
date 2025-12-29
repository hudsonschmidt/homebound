"""Add update_requests table

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Create Date: 2025-12-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'o5j6k7l8m9n0'
down_revision: Union[str, None] = 'n4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create update_requests table for friend ping functionality."""
    # Create update_requests table to track when friends request updates from trip owners
    op.create_table(
        'update_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('requester_user_id', sa.Integer(), nullable=False),  # Friend requesting update
        sa.Column('owner_user_id', sa.Integer(), nullable=False),  # Trip owner
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),  # When owner saw request
        sa.Column('resolved_at', sa.DateTime(), nullable=True),  # When owner checked in
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requester_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    # Index for finding recent requests by trip (for rate limiting)
    op.create_index('idx_update_requests_trip', 'update_requests', ['trip_id'])
    # Index for finding pending requests for a user
    op.create_index('idx_update_requests_owner', 'update_requests', ['owner_user_id', 'requested_at'])


def downgrade() -> None:
    """Remove update_requests table."""
    op.drop_index('idx_update_requests_owner', table_name='update_requests')
    op.drop_index('idx_update_requests_trip', table_name='update_requests')
    op.drop_table('update_requests')
