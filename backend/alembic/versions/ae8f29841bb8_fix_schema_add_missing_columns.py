"""Fix schema add missing columns

Revision ID: ae8f29841bb8
Revises: f1e33823bb97
Create Date: 2025-10-27 18:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'ae8f29841bb8'
down_revision: Union[str, Sequence[str], None] = 'f1e33823bb97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns to existing tables."""

    # Check and add saved_contacts to users table if it doesn't exist
    conn = op.get_bind()

    # Check if saved_contacts column exists
    result = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'saved_contacts'
    """))

    if not result.fetchone():
        op.add_column('users', sa.Column('saved_contacts', sa.JSON(), nullable=True))

    # Check if location_lat column exists in plans
    result = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'plans' AND column_name = 'location_lat'
    """))

    if not result.fetchone():
        op.add_column('plans', sa.Column('location_lat', sa.Float(), nullable=True))

    # Check if location_lng column exists in plans
    result = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'plans' AND column_name = 'location_lng'
    """))

    if not result.fetchone():
        op.add_column('plans', sa.Column('location_lng', sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove added columns."""
    op.drop_column('plans', 'location_lng')
    op.drop_column('plans', 'location_lat')
    op.drop_column('users', 'saved_contacts')
