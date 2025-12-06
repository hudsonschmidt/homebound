"""Add notification_logs table for delivery tracking

Revision ID: b2c3d4e5f6a7
Revises: e1f2a3b4c5d6
Create Date: 2025-12-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notification_logs table for tracking notification delivery."""
    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_token', sa.String(256), nullable=True),  # NULL for email notifications
        sa.Column('notification_type', sa.String(16), nullable=False),  # 'push' or 'email'
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False),  # 'sent', 'failed', 'pending'
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # Index for querying by user
    op.create_index('ix_notification_logs_user_id', 'notification_logs', ['user_id'])
    # Index for querying by status (for retry queue)
    op.create_index('ix_notification_logs_status', 'notification_logs', ['status'])


def downgrade() -> None:
    """Drop notification_logs table."""
    op.drop_index('ix_notification_logs_status', table_name='notification_logs')
    op.drop_index('ix_notification_logs_user_id', table_name='notification_logs')
    op.drop_table('notification_logs')
