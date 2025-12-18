"""Add friends tables (friendships, friend_invites) and profile_photo_url

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2025-12-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h8c9d0e1f2g3'
down_revision: Union[str, None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create friends-related tables and add profile_photo_url to users."""

    # Add profile_photo_url to users table
    op.add_column('users', sa.Column('profile_photo_url', sa.Text(), nullable=True))

    # Create friendships table (mutual friendships)
    op.create_table('friendships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id_1', sa.Integer(), nullable=False),
        sa.Column('user_id_2', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id_1'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id_2'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('user_id_1 < user_id_2', name='chk_user_order'),
        sa.UniqueConstraint('user_id_1', 'user_id_2', name='unique_friendship')
    )
    op.create_index('idx_friendships_user1', 'friendships', ['user_id_1'])
    op.create_index('idx_friendships_user2', 'friendships', ['user_id_2'])

    # Create friend_invites table (shareable invite tokens)
    op.create_table('friend_invites',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('inviter_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_by', sa.Integer(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('max_uses', sa.Integer(), server_default='1', nullable=False),
        sa.Column('use_count', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['inviter_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['accepted_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token', name='unique_invite_token')
    )
    op.create_index('idx_friend_invites_token', 'friend_invites', ['token'])
    op.create_index('idx_friend_invites_inviter', 'friend_invites', ['inviter_id'])


def downgrade() -> None:
    """Drop friends-related tables and remove profile_photo_url from users."""
    op.drop_index('idx_friend_invites_inviter', table_name='friend_invites')
    op.drop_index('idx_friend_invites_token', table_name='friend_invites')
    op.drop_table('friend_invites')

    op.drop_index('idx_friendships_user2', table_name='friendships')
    op.drop_index('idx_friendships_user1', table_name='friendships')
    op.drop_table('friendships')

    op.drop_column('users', 'profile_photo_url')
