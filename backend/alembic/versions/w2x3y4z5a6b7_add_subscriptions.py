"""Add subscription tables and user subscription fields

Adds subscription tracking for Homebound+ premium features:
- subscription_tier and subscription_expires_at on users table
- subscriptions table for App Store transaction tracking
- pinned_activities table for premium pinned activities feature
- contact_groups and contact_group_members tables for premium contact groups

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-01-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'w2x3y4z5a6b7'
down_revision: Union[str, None] = 'v1w2x3y4z5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add subscription-related tables and columns."""

    # Add subscription columns to users table
    op.add_column('users',
                  sa.Column('subscription_tier', sa.String(20), nullable=False, server_default='free'))
    op.add_column('users',
                  sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True))

    # Create subscriptions table for App Store transaction tracking
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('original_transaction_id', sa.String(255), unique=True, nullable=True),
        sa.Column('product_id', sa.String(100), nullable=False),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('auto_renew_status', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_family_shared', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('environment', sa.String(20), nullable=False, server_default='production'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for subscriptions table
    op.create_index('idx_subscriptions_user_id', 'subscriptions', ['user_id'])
    op.create_index('idx_subscriptions_original_transaction_id', 'subscriptions', ['original_transaction_id'])
    op.create_index('idx_subscriptions_expires_date', 'subscriptions', ['expires_date'])

    # Create pinned_activities table (premium feature)
    op.create_table(
        'pinned_activities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('activity_id', sa.Integer(), sa.ForeignKey('activities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'activity_id', name='uq_pinned_activity_user_activity'),
        sa.UniqueConstraint('user_id', 'position', name='uq_pinned_activity_user_position'),
    )

    op.create_index('idx_pinned_activities_user_id', 'pinned_activities', ['user_id'])

    # Create contact_groups table (premium feature)
    op.create_table(
        'contact_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('idx_contact_groups_user_id', 'contact_groups', ['user_id'])

    # Create contact_group_members junction table
    op.create_table(
        'contact_group_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('contact_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('friend_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Either contact_id or friend_user_id must be set, but not both
        sa.CheckConstraint(
            '(contact_id IS NOT NULL AND friend_user_id IS NULL) OR (contact_id IS NULL AND friend_user_id IS NOT NULL)',
            name='chk_member_type'
        ),
    )

    op.create_index('idx_contact_group_members_group_id', 'contact_group_members', ['group_id'])
    op.create_index('idx_contact_group_members_contact_id', 'contact_group_members', ['contact_id'])
    op.create_index('idx_contact_group_members_friend_user_id', 'contact_group_members', ['friend_user_id'])


def downgrade() -> None:
    """Remove subscription-related tables and columns."""
    # Drop tables in reverse order
    op.drop_table('contact_group_members')
    op.drop_table('contact_groups')
    op.drop_table('pinned_activities')
    op.drop_table('subscriptions')

    # Remove columns from users
    op.drop_column('users', 'subscription_expires_at')
    op.drop_column('users', 'subscription_tier')
