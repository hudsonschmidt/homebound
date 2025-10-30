"""Plan management endpoints with raw SQL"""
from datetime import datetime, timedelta
import secrets
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from src import database as db
from src.api import auth
import sqlalchemy

router = APIRouter(
    prefix="/api/v1/plans",
    tags=["plans"],
    dependencies=[Depends(auth.get_current_user_id)]
)


def parse_datetime(dt):
    """Parse datetime from SQLite string or return datetime object"""
    if isinstance(dt, str):
        return datetime.fromisoformat(dt.replace(' ', 'T'))
    return dt


class ContactCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    notify_on_overdue: bool = True


class PlanCreate(BaseModel):
    title: str
    activity_type: str
    start_at: datetime
    eta_at: datetime
    grace_minutes: int
    location_text: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    notes: Optional[str] = None
    contacts: List[ContactCreate] = []


class PlanResponse(BaseModel):
    id: int
    title: str
    activity_type: str
    start_at: str
    eta_at: str
    grace_minutes: int
    location_text: Optional[str]
    location_lat: Optional[float]
    location_lng: Optional[float]
    notes: Optional[str]
    status: str
    completed_at: Optional[str]
    extended_count: int
    last_checkin_at: Optional[str]
    created_at: str
    checkin_token: Optional[str] = None
    checkout_token: Optional[str] = None


class ContactResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    notify_on_overdue: bool


@router.post("", response_model=PlanResponse)
def create_plan(body: PlanCreate, user_id: int = Depends(auth.get_current_user_id)):
    """Create a new safety plan"""

    with db.engine.begin() as conn:
        # Generate unique tokens for checkin/checkout
        checkin_token = secrets.token_urlsafe(32)
        checkout_token = secrets.token_urlsafe(32)

        # Insert plan
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO plans (
                    user_id, title, activity_type, start_at, eta_at, grace_minutes,
                    location_text, location_lat, location_lng, notes, status,
                    extended_count, created_at, checkin_token, checkout_token
                ) VALUES (
                    :user_id, :title, :activity_type, :start_at, :eta_at, :grace_minutes,
                    :location_text, :location_lat, :location_lng, :notes, 'active',
                    0, :created_at, :checkin_token, :checkout_token
                )
            """),
            {
                "user_id": user_id,
                "title": body.title,
                "activity_type": body.activity_type,
                "start_at": body.start_at.isoformat(),
                "eta_at": body.eta_at.isoformat(),
                "grace_minutes": body.grace_minutes,
                "location_text": body.location_text,
                "location_lat": body.location_lat,
                "location_lng": body.location_lng,
                "notes": body.notes,
                "created_at": datetime.utcnow().isoformat(),
                "checkin_token": checkin_token,
                "checkout_token": checkout_token
            }
        )
        plan_id = result.lastrowid

        # Insert contacts
        for contact in body.contacts:
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO contacts (plan_id, name, phone, email, notify_on_overdue)
                    VALUES (:plan_id, :name, :phone, :email, :notify_on_overdue)
                """),
                {
                    "plan_id": plan_id,
                    "name": contact.name,
                    "phone": contact.phone,
                    "email": contact.email,
                    "notify_on_overdue": contact.notify_on_overdue
                }
            )

        # Fetch created plan
        plan = conn.execute(
            sqlalchemy.text("""
                SELECT id, user_id, title, activity_type, start_at, eta_at, grace_minutes,
                       location_text, location_lat, location_lng, notes, status, completed_at,
                       extended_count, last_checkin_at, created_at, checkin_token, checkout_token
                FROM plans WHERE id = :plan_id
            """),
            {"plan_id": plan_id}
        ).fetchone()

        return PlanResponse(
            id=plan.id,
            title=plan.title,
            activity_type=plan.activity_type,
            start_at=str(plan.start_at),
            eta_at=str(plan.eta_at),
            grace_minutes=plan.grace_minutes,
            location_text=plan.location_text,
            location_lat=plan.location_lat,
            location_lng=plan.location_lng,
            notes=plan.notes,
            status=plan.status,
            completed_at=str(plan.completed_at) if plan.completed_at else None,
            extended_count=plan.extended_count,
            last_checkin_at=str(plan.last_checkin_at) if plan.last_checkin_at else None,
            created_at=str(plan.created_at),
            checkin_token=plan.checkin_token,
            checkout_token=plan.checkout_token
        )


@router.get("", response_model=List[PlanResponse])
def list_plans(user_id: int = Depends(auth.get_current_user_id)):
    """List all plans for the current user"""

    with db.engine.begin() as conn:
        plans = conn.execute(
            sqlalchemy.text("""
                SELECT id, user_id, title, activity_type, start_at, eta_at, grace_minutes,
                       location_text, location_lat, location_lng, notes, status, completed_at,
                       extended_count, last_checkin_at, created_at, checkin_token, checkout_token
                FROM plans
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """),
            {"user_id": user_id}
        ).fetchall()

        return [
            PlanResponse(
                id=p.id,
                title=p.title,
                activity_type=p.activity_type,
                start_at=str(p.start_at),
                eta_at=str(p.eta_at),
                grace_minutes=p.grace_minutes,
                location_text=p.location_text,
                location_lat=p.location_lat,
                location_lng=p.location_lng,
                notes=p.notes,
                status=p.status,
                completed_at=str(p.completed_at) if p.completed_at else None,
                extended_count=p.extended_count,
                last_checkin_at=str(p.last_checkin_at) if p.last_checkin_at else None,
                created_at=str(p.created_at),
                checkin_token=p.checkin_token,
                checkout_token=p.checkout_token
            )
            for p in plans
        ]


@router.get("/active", response_model=Optional[PlanResponse])
def get_active_plan(user_id: int = Depends(auth.get_current_user_id)):
    """Get the current active plan"""

    with db.engine.begin() as conn:
        plan = conn.execute(
            sqlalchemy.text("""
                SELECT id, user_id, title, activity_type, start_at, eta_at, grace_minutes,
                       location_text, location_lat, location_lng, notes, status, completed_at,
                       extended_count, last_checkin_at, created_at, checkin_token, checkout_token
                FROM plans
                WHERE user_id = :user_id AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"user_id": user_id}
        ).fetchone()

        if not plan:
            return None

        return PlanResponse(
            id=plan.id,
            title=plan.title,
            activity_type=plan.activity_type,
            start_at=str(plan.start_at),
            eta_at=str(plan.eta_at),
            grace_minutes=plan.grace_minutes,
            location_text=plan.location_text,
            location_lat=plan.location_lat,
            location_lng=plan.location_lng,
            notes=plan.notes,
            status=plan.status,
            completed_at=str(plan.completed_at) if plan.completed_at else None,
            extended_count=plan.extended_count,
            last_checkin_at=str(plan.last_checkin_at) if plan.last_checkin_at else None,
            created_at=str(plan.created_at),
            checkin_token=plan.checkin_token,
            checkout_token=plan.checkout_token
        )


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific plan"""

    with db.engine.begin() as conn:
        plan = conn.execute(
            sqlalchemy.text("""
                SELECT id, user_id, title, activity_type, start_at, eta_at, grace_minutes,
                       location_text, location_lat, location_lng, notes, status, completed_at,
                       extended_count, last_checkin_at, created_at, checkin_token, checkout_token
                FROM plans
                WHERE id = :plan_id AND user_id = :user_id
            """),
            {"plan_id": plan_id, "user_id": user_id}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        return PlanResponse(
            id=plan.id,
            title=plan.title,
            activity_type=plan.activity_type,
            start_at=str(plan.start_at),
            eta_at=str(plan.eta_at),
            grace_minutes=plan.grace_minutes,
            location_text=plan.location_text,
            location_lat=plan.location_lat,
            location_lng=plan.location_lng,
            notes=plan.notes,
            status=plan.status,
            completed_at=str(plan.completed_at) if plan.completed_at else None,
            extended_count=plan.extended_count,
            last_checkin_at=str(plan.last_checkin_at) if plan.last_checkin_at else None,
            created_at=str(plan.created_at),
            checkin_token=plan.checkin_token,
            checkout_token=plan.checkout_token
        )


@router.get("/{plan_id}/contacts", response_model=List[ContactResponse])
def get_plan_contacts(plan_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get contacts for a specific plan"""

    with db.engine.begin() as conn:
        # Verify plan ownership
        plan = conn.execute(
            sqlalchemy.text("SELECT id FROM plans WHERE id = :plan_id AND user_id = :user_id"),
            {"plan_id": plan_id, "user_id": user_id}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        contacts = conn.execute(
            sqlalchemy.text("""
                SELECT id, name, phone, email, notify_on_overdue
                FROM contacts
                WHERE plan_id = :plan_id
                ORDER BY id
            """),
            {"plan_id": plan_id}
        ).fetchall()

        return [
            ContactResponse(
                id=c.id,
                name=c.name,
                phone=c.phone,
                email=c.email,
                notify_on_overdue=bool(c.notify_on_overdue)
            )
            for c in contacts
        ]


@router.post("/{plan_id}/complete")
def complete_plan(plan_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Mark a plan as completed"""

    with db.engine.begin() as conn:
        # Verify plan ownership and status
        plan = conn.execute(
            sqlalchemy.text("SELECT id, status FROM plans WHERE id = :plan_id AND user_id = :user_id"),
            {"plan_id": plan_id, "user_id": user_id}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if plan.status != "active":
            raise HTTPException(status_code=400, detail="Plan is not active")

        # Update plan status
        conn.execute(
            sqlalchemy.text("""
                UPDATE plans
                SET status = 'completed', completed_at = :completed_at
                WHERE id = :plan_id
            """),
            {"plan_id": plan_id, "completed_at": datetime.utcnow().isoformat()}
        )

        return {"ok": True, "message": "Plan completed successfully"}


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Delete a plan"""

    with db.engine.begin() as conn:
        # Verify plan ownership
        plan = conn.execute(
            sqlalchemy.text("SELECT id FROM plans WHERE id = :plan_id AND user_id = :user_id"),
            {"plan_id": plan_id, "user_id": user_id}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        # Delete plan (contacts will cascade)
        conn.execute(
            sqlalchemy.text("DELETE FROM plans WHERE id = :plan_id"),
            {"plan_id": plan_id}
        )

        return {"ok": True, "message": "Plan deleted successfully"}


class TimelineEvent(BaseModel):
    id: int
    kind: str
    at: str
    meta: Optional[str]


@router.get("/{plan_id}/timeline", response_model=List[TimelineEvent])
def get_plan_timeline(plan_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get timeline events for a specific plan"""

    with db.engine.begin() as conn:
        # Verify plan ownership
        plan = conn.execute(
            sqlalchemy.text("SELECT id FROM plans WHERE id = :plan_id AND user_id = :user_id"),
            {"plan_id": plan_id, "user_id": user_id}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        # Fetch timeline events
        events = conn.execute(
            sqlalchemy.text("""
                SELECT id, kind, at, meta
                FROM events
                WHERE plan_id = :plan_id
                ORDER BY at DESC
            """),
            {"plan_id": plan_id}
        ).fetchall()

        return [
            TimelineEvent(
                id=e.id,
                kind=e.kind,
                at=str(e.at),
                meta=e.meta
            )
            for e in events
        ]
