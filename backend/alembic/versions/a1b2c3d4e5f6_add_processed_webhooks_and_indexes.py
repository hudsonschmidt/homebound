"""Add processed webhooks table and performance indexes

Adds:
- processed_webhooks table for persisting Apple webhook deduplication
- Performance indexes on frequently queried columns

Revision ID: a1b2c3d4e5f6
Revises: z5a6b7c8d9e0
Create Date: 2026-01-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'z5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add processed webhooks table and performance indexes."""

    # Create processed_webhooks table for Apple App Store webhook deduplication
    op.create_table(
        'processed_webhooks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('notification_uuid', sa.String(255), unique=True, nullable=False),
        sa.Column('notification_type', sa.String(100), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Index for looking up by notification UUID (primary lookup)
    op.create_index('idx_processed_webhooks_notification_uuid', 'processed_webhooks', ['notification_uuid'])
    # Index for cleanup of expired entries
    op.create_index('idx_processed_webhooks_expires_at', 'processed_webhooks', ['expires_at'])

    # Performance indexes on frequently queried tables
    # trips table
    op.create_index('ix_trips_owner_id', 'trips', ['owner_id'])
    op.create_index('ix_trips_status', 'trips', ['status'])
    op.create_index('ix_trips_created_at', 'trips', ['created_at'])

    # contacts table
    op.create_index('ix_contacts_owner_id', 'contacts', ['owner_id'])

    # login_tokens table
    op.create_index('ix_login_tokens_user_id', 'login_tokens', ['user_id'])
    op.create_index('ix_login_tokens_email', 'login_tokens', ['email'])


def downgrade() -> None:
    """Remove processed webhooks table and performance indexes."""

    # Drop performance indexes
    op.drop_index('ix_login_tokens_email', 'login_tokens')
    op.drop_index('ix_login_tokens_user_id', 'login_tokens')
    op.drop_index('ix_contacts_owner_id', 'contacts')
    op.drop_index('ix_trips_created_at', 'trips')
    op.drop_index('ix_trips_status', 'trips')
    op.drop_index('ix_trips_owner_id', 'trips')

    # Drop processed_webhooks table
    op.drop_table('processed_webhooks')
