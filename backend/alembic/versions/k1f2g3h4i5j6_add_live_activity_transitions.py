"""Add Live Activity transition tracking columns

Tracks whether we've sent push notifications to update Live Activity state
at ETA and grace period end transitions.

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2025-12-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1f2g3h4i5j6'
down_revision: Union[str, None] = 'j0e1f2g3h4i5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add columns to track Live Activity transition notifications."""
    # Track whether we've sent the ETA warning transition push
    op.add_column('trips', sa.Column(
        'notified_eta_transition',
        sa.Boolean(),
        nullable=False,
        server_default='false'
    ))

    # Track whether we've sent the grace period end transition push
    op.add_column('trips', sa.Column(
        'notified_grace_transition',
        sa.Boolean(),
        nullable=False,
        server_default='false'
    ))


def downgrade() -> None:
    """Remove Live Activity transition tracking columns."""
    op.drop_column('trips', 'notified_grace_transition')
    op.drop_column('trips', 'notified_eta_transition')
