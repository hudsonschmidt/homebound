"""Add trip_safety_contacts junction table for unified contact handling

This table allows trips to have safety contacts that are either:
- Regular email contacts (contact_id references contacts table)
- Friends (friend_user_id references users table)

The existing contact1/2/3 columns are kept for backwards compatibility.

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2025-12-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i9d0e1f2g3h4'
down_revision: Union[str, None] = 'h8c9d0e1f2g3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trip_safety_contacts junction table."""
    op.create_table('trip_safety_contacts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        # Either contact_id OR friend_user_id is set, not both
        sa.Column('contact_id', sa.Integer(), nullable=True),
        sa.Column('friend_user_id', sa.Integer(), nullable=True),
        # Order 1, 2, or 3 for display priority
        sa.Column('position', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['friend_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # Ensure exactly one of contact_id or friend_user_id is set
        sa.CheckConstraint(
            '(contact_id IS NOT NULL AND friend_user_id IS NULL) OR '
            '(contact_id IS NULL AND friend_user_id IS NOT NULL)',
            name='chk_one_contact_type'
        ),
        # Each position (1, 2, 3) can only be used once per trip
        sa.UniqueConstraint('trip_id', 'position', name='unique_trip_position')
    )
    op.create_index('idx_trip_safety_contacts_trip', 'trip_safety_contacts', ['trip_id'])
    op.create_index('idx_trip_safety_contacts_friend', 'trip_safety_contacts', ['friend_user_id'])

    # Migrate existing data from contact1/2/3 columns to the junction table
    # This preserves existing trip-contact relationships
    op.execute("""
        INSERT INTO trip_safety_contacts (trip_id, contact_id, position)
        SELECT id, contact1, 1
        FROM trips
        WHERE contact1 IS NOT NULL
    """)

    op.execute("""
        INSERT INTO trip_safety_contacts (trip_id, contact_id, position)
        SELECT id, contact2, 2
        FROM trips
        WHERE contact2 IS NOT NULL
    """)

    op.execute("""
        INSERT INTO trip_safety_contacts (trip_id, contact_id, position)
        SELECT id, contact3, 3
        FROM trips
        WHERE contact3 IS NOT NULL
    """)


def downgrade() -> None:
    """Drop trip_safety_contacts table."""
    op.drop_index('idx_trip_safety_contacts_friend', table_name='trip_safety_contacts')
    op.drop_index('idx_trip_safety_contacts_trip', table_name='trip_safety_contacts')
    op.drop_table('trip_safety_contacts')
