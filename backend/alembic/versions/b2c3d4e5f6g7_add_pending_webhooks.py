"""Add pending webhooks table for race condition handling

Adds pending_webhooks table to store Apple webhooks that arrive before
the iOS app calls verify-purchase. This handles the race condition where
Apple sends a SUBSCRIBED webhook before the subscription record exists.

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pending_webhooks table."""

    op.create_table(
        'pending_webhooks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('original_transaction_id', sa.String(255), unique=True, nullable=False),
        sa.Column('notification_type', sa.String(100), nullable=False),
        sa.Column('subtype', sa.String(100), nullable=True),
        sa.Column('signed_transaction_info', sa.Text(), nullable=True),
        sa.Column('signed_renewal_info', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Index for lookup by original_transaction_id
    op.create_index('idx_pending_webhooks_original_transaction_id', 'pending_webhooks', ['original_transaction_id'])
    # Index for cleanup of expired entries
    op.create_index('idx_pending_webhooks_expires_at', 'pending_webhooks', ['expires_at'])


def downgrade() -> None:
    """Remove pending_webhooks table."""
    op.drop_index('idx_pending_webhooks_expires_at', 'pending_webhooks')
    op.drop_index('idx_pending_webhooks_original_transaction_id', 'pending_webhooks')
    op.drop_table('pending_webhooks')
