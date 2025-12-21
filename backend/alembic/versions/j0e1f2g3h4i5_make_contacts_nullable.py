"""Make contact1/2/3 columns nullable

Since trips can now use the trip_safety_contacts junction table for contacts
(including friend contacts), the original contact1/2/3 columns no longer
need to be required.

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2025-12-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j0e1f2g3h4i5'
down_revision: Union[str, None] = 'i9d0e1f2g3h4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make contact columns nullable."""
    op.alter_column('trips', 'contact1',
        existing_type=sa.Integer(),
        nullable=True
    )
    op.alter_column('trips', 'contact2',
        existing_type=sa.Integer(),
        nullable=True
    )
    op.alter_column('trips', 'contact3',
        existing_type=sa.Integer(),
        nullable=True
    )


def downgrade() -> None:
    """Revert contact columns to NOT NULL (will fail if NULLs exist)."""
    op.alter_column('trips', 'contact1',
        existing_type=sa.Integer(),
        nullable=False
    )
    op.alter_column('trips', 'contact2',
        existing_type=sa.Integer(),
        nullable=False
    )
    op.alter_column('trips', 'contact3',
        existing_type=sa.Integer(),
        nullable=False
    )
