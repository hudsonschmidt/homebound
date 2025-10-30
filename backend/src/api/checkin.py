"""Public check-in/check-out endpoints using tokens (no auth required)"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src import database as db
import sqlalchemy
from datetime import datetime

router = APIRouter(prefix="/t", tags=["checkin"])


class CheckinResponse(BaseModel):
    ok: bool
    message: str


@router.get("/{token}/checkin", response_model=CheckinResponse)
def checkin_with_token(token: str):
    """Check in to a plan using a magic token"""
    with db.engine.begin() as conn:
        # Find plan by checkin_token
        plan = conn.execute(
            sqlalchemy.text("""
                SELECT id, user_id, title, status
                FROM plans
                WHERE checkin_token = :token
                AND status = 'active'
            """),
            {"token": token}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Invalid or expired check-in link")

        # Update last check-in time
        conn.execute(
            sqlalchemy.text("""
                UPDATE plans
                SET last_checkin_at = :now
                WHERE id = :plan_id
            """),
            {"now": datetime.utcnow(), "plan_id": plan.id}
        )

        # Log the check-in event
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO events (plan_id, kind, meta, at)
                VALUES (:plan_id, 'checkin', 'Checked in via token', :now)
            """),
            {"plan_id": plan.id, "now": datetime.utcnow()}
        )

        return CheckinResponse(
            ok=True,
            message=f"Successfully checked in to '{plan.title}'"
        )


@router.get("/{token}/checkout", response_model=CheckinResponse)
def checkout_with_token(token: str):
    """Complete/check out of a plan using a magic token"""
    with db.engine.begin() as conn:
        # Find plan by checkout_token
        plan = conn.execute(
            sqlalchemy.text("""
                SELECT id, user_id, title, status
                FROM plans
                WHERE checkout_token = :token
                AND status = 'active'
            """),
            {"token": token}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Invalid or expired check-out link")

        # Mark plan as completed
        now = datetime.utcnow()
        conn.execute(
            sqlalchemy.text("""
                UPDATE plans
                SET status = 'completed',
                    completed_at = :now
                WHERE id = :plan_id
            """),
            {"now": now, "plan_id": plan.id}
        )

        # Log the checkout event
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO events (plan_id, kind, meta, at)
                VALUES (:plan_id, 'complete', 'Checked out via token', :now)
            """),
            {"plan_id": plan.id, "now": now}
        )

        return CheckinResponse(
            ok=True,
            message=f"Successfully completed '{plan.title}' - you're safe!"
        )