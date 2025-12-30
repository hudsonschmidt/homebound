"""Global platform statistics endpoints (public)"""

import sqlalchemy
from fastapi import APIRouter
from pydantic import BaseModel

from src import database as db

router = APIRouter(
    prefix="/api/v1/stats",
    tags=["stats"],
)


class GlobalStatsResponse(BaseModel):
    total_users: int
    total_completed_trips: int


@router.get("/global", response_model=GlobalStatsResponse)
def get_global_stats():
    """Get aggregate platform statistics (public endpoint).

    Returns total active users and total completed trips across the platform.
    Used for social proof in the About section.
    """
    with db.engine.begin() as connection:
        # Count active users
        users_result = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count
                FROM users
                WHERE id NOT IN (1,5)
                """
            )
        ).fetchone()

        # Count completed trips
        trips_result = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count
                FROM trips
                WHERE status = 'completed'
                """
            )
        ).fetchone()

        return GlobalStatsResponse(
            total_users=users_result.count if users_result else 0,
            total_completed_trips=trips_result.count if trips_result else 0
        )
