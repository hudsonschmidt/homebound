"""Add failed webhooks table for dead-letter queue

Adds failed_webhooks table to store webhooks that failed processing.
This allows for later retry/investigation of failed webhook events.

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add failed_webhooks table."""

    op.create_table(
        'failed_webhooks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('notification_uuid', sa.String(255), nullable=True),
        sa.Column('notification_type', sa.String(100), nullable=True),
        sa.Column('subtype', sa.String(100), nullable=True),
        sa.Column('payload', sa.Text(), nullable=False),  # Full webhook payload
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('retry_count', sa.Integer(), default=0, nullable=False),
        sa.Column('last_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),  # NULL = unresolved
    )

    # Index for finding unresolved webhooks
    op.create_index('idx_failed_webhooks_resolved_at', 'failed_webhooks', ['resolved_at'])
    # Index for finding by notification UUID (for deduplication)
    op.create_index('idx_failed_webhooks_notification_uuid', 'failed_webhooks', ['notification_uuid'])


def downgrade() -> None:
    """Remove failed_webhooks table."""
    op.drop_index('idx_failed_webhooks_notification_uuid', 'failed_webhooks')
    op.drop_index('idx_failed_webhooks_resolved_at', 'failed_webhooks')
    op.drop_table('failed_webhooks')
