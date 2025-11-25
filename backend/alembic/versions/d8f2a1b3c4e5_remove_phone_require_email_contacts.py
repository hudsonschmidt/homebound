"""Remove phone and require email for contacts

Revision ID: d8f2a1b3c4e5
Revises: fc7f7cf2e99e
Create Date: 2025-11-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f2a1b3c4e5'
down_revision: Union[str, Sequence[str], None] = 'fc7f7cf2e99e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Remove phone column from contacts and make email NOT NULL.
    For existing contacts without email, set their email to the user's email.
    """
    # Step 1: Update contacts that have NULL email to use their user's email
    op.execute("""
        UPDATE contacts
        SET email = (
            SELECT u.email
            FROM users u
            WHERE u.id = contacts.user_id
        )
        WHERE email IS NULL
    """)

    # Step 2: Make email NOT NULL
    op.alter_column('contacts', 'email',
                    existing_type=sa.Text(),
                    nullable=False)

    # Step 3: Drop the phone column
    op.drop_column('contacts', 'phone')


def downgrade() -> None:
    """
    Restore phone column and make email nullable again.
    """
    # Add phone column back (as nullable since we can't restore old values)
    op.add_column('contacts', sa.Column('phone', sa.Text(), nullable=True))

    # Make email nullable again
    op.alter_column('contacts', 'email',
                    existing_type=sa.Text(),
                    nullable=True)

    # Set a placeholder phone for any contacts that existed
    # (Can't restore original values)
    op.execute("""
        UPDATE contacts
        SET phone = '+10000000000'
        WHERE phone IS NULL
    """)

    # Make phone NOT NULL
    op.alter_column('contacts', 'phone',
                    existing_type=sa.Text(),
                    nullable=False)
