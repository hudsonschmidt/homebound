"""Add live_activity_tokens table for Live Activity push updates

Stores push tokens for Live Activities, enabling real-time updates
via APNs liveactivity push type. Each active trip can have one token.

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2025-12-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l2g3h4i5j6k7'
down_revision: Union[str, None] = 'k1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create live_activity_tokens table."""
    op.create_table(
        'live_activity_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=256), nullable=False),
        sa.Column('bundle_id', sa.String(length=256), nullable=False),
        sa.Column('env', sa.String(length=16), nullable=False),  # 'production' or 'development'
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # One token per trip (upsert pattern)
    op.create_index('ix_live_activity_tokens_trip_id', 'live_activity_tokens', ['trip_id'], unique=True)
    op.create_index('ix_live_activity_tokens_user_id', 'live_activity_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    """Drop live_activity_tokens table."""
    op.drop_index('ix_live_activity_tokens_user_id', table_name='live_activity_tokens')
    op.drop_index('ix_live_activity_tokens_trip_id', table_name='live_activity_tokens')
    op.drop_table('live_activity_tokens')
