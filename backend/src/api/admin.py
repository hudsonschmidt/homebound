"""Administrative endpoints"""
from fastapi import APIRouter
from pydantic import BaseModel
from src import database as db
import sqlalchemy

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class SystemStats(BaseModel):
    total_users: int
    total_plans: int
    active_plans: int
    completed_plans: int


@router.get("/stats", response_model=SystemStats)
def get_system_stats():
    """Get system-wide statistics"""
    with db.engine.begin() as conn:
        stats = conn.execute(
            sqlalchemy.text("""
                SELECT
                    (SELECT COUNT(*) FROM users) as total_users,
                    (SELECT COUNT(*) FROM plans) as total_plans,
                    (SELECT COUNT(*) FROM plans WHERE status = 'active') as active_plans,
                    (SELECT COUNT(*) FROM plans WHERE status = 'completed') as completed_plans
            """)
        ).fetchone()

        return SystemStats(
            total_users=stats.total_users,
            total_plans=stats.total_plans,
            active_plans=stats.active_plans,
            completed_plans=stats.completed_plans
        )