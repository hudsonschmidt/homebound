"""User profile management endpoints"""

from datetime import datetime, UTC

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["profile"],
    dependencies=[Depends(auth.get_current_user_id)]
)


class ProfileUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    age: int | None = None
    notify_trip_reminders: bool | None = None
    notify_checkin_alerts: bool | None = None


class ProfileResponse(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    age: int
    profile_completed: bool
    notify_trip_reminders: bool
    notify_checkin_alerts: bool
    created_at: str | None = None


class ProfileUpdateResponse(BaseModel):
    ok: bool
    user: dict


@router.get("", response_model=ProfileResponse)
def get_profile(user_id: int = Depends(auth.get_current_user_id)):
    """Get current user's profile"""
    with db.engine.begin() as connection:
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email, first_name, last_name, age, notify_trip_reminders, notify_checkin_alerts, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Check if profile is complete
        profile_completed = bool(
            user.first_name and
            user.last_name and
            user.age and
            user.age > 0
        )

        return ProfileResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            age=user.age,
            profile_completed=profile_completed,
            notify_trip_reminders=user.notify_trip_reminders,
            notify_checkin_alerts=user.notify_checkin_alerts,
            created_at=user.created_at.isoformat() if user.created_at else None
        )


@router.put("", response_model=ProfileUpdateResponse)
def update_profile(body: ProfileUpdate, user_id: int = Depends(auth.get_current_user_id)):
    """Update current user's profile"""
    with db.engine.begin() as connection:
        # Build dynamic update query
        updates: list[str] = []
        params: dict[str, str | int | bool] = {"user_id": user_id}

        if body.first_name is not None:
            updates.append("first_name = :first_name")
            params["first_name"] = body.first_name

        if body.last_name is not None:
            updates.append("last_name = :last_name")
            params["last_name"] = body.last_name

        if body.age is not None:
            updates.append("age = :age")
            params["age"] = body.age

        if body.notify_trip_reminders is not None:
            updates.append("notify_trip_reminders = :notify_trip_reminders")
            params["notify_trip_reminders"] = body.notify_trip_reminders

        if body.notify_checkin_alerts is not None:
            updates.append("notify_checkin_alerts = :notify_checkin_alerts")
            params["notify_checkin_alerts"] = body.notify_checkin_alerts

        if updates:
            connection.execute(
                sqlalchemy.text(f"UPDATE users SET {', '.join(updates)} WHERE id = :user_id"),
                params
            )

        # Return updated profile
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email, first_name, last_name, age, notify_trip_reminders, notify_checkin_alerts
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Check if profile is complete (non-empty strings and valid age)
        profile_completed = bool(
            user.first_name and
            user.last_name and
            user.age and
            user.age > 0
        )

        return ProfileUpdateResponse(
            ok=True,
            user={
                "first_name": user.first_name,
                "last_name": user.last_name,
                "age": user.age,
                "profile_completed": profile_completed,
                "notify_trip_reminders": user.notify_trip_reminders,
                "notify_checkin_alerts": user.notify_checkin_alerts
            }
        )


@router.patch("")
def patch_profile(body: ProfileUpdate, user_id: int = Depends(auth.get_current_user_id)):
    """Partially update current user's profile"""
    with db.engine.begin() as connection:
        # Build dynamic update query
        updates: list[str] = []
        params: dict[str, str | int | bool] = {"user_id": user_id}

        if body.first_name is not None:
            updates.append("first_name = :first_name")
            params["first_name"] = body.first_name

        if body.last_name is not None:
            updates.append("last_name = :last_name")
            params["last_name"] = body.last_name

        if body.age is not None:
            updates.append("age = :age")
            params["age"] = body.age

        if body.notify_trip_reminders is not None:
            updates.append("notify_trip_reminders = :notify_trip_reminders")
            params["notify_trip_reminders"] = body.notify_trip_reminders

        if body.notify_checkin_alerts is not None:
            updates.append("notify_checkin_alerts = :notify_checkin_alerts")
            params["notify_checkin_alerts"] = body.notify_checkin_alerts

        if updates:
            connection.execute(
                sqlalchemy.text(f"UPDATE users SET {', '.join(updates)} WHERE id = :user_id"),
                params
            )

        return {"ok": True, "message": "Profile updated successfully"}


@router.get("/export")
def export_user_data(user_id: int = Depends(auth.get_current_user_id)):
    """Export all user data (profile, trips, contacts) for GDPR compliance"""
    with db.engine.begin() as connection:
        # Get user profile
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email, first_name, last_name, age, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get all trips
        trips = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.*, a.name as activity_name, a.icon as activity_icon
                FROM trips t
                LEFT JOIN activities a ON t.activity = a.id
                WHERE t.user_id = :user_id
                ORDER BY t.created_at DESC
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        # Get all contacts
        contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, name, email
                FROM contacts
                WHERE user_id = :user_id
                ORDER BY id DESC
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        # Format response
        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "profile": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "age": user.age,
                "created_at": str(user.created_at) if user.created_at else None
            },
            "trips": [
                {
                    "id": t.id,
                    "title": t.title,
                    "activity": t.activity_name,
                    "activity_icon": t.activity_icon,
                    "start_at": str(t.start) if t.start else None,
                    "eta_at": str(t.eta) if t.eta else None,
                    "grace_minutes": t.grace_min,
                    "location_text": t.location_text,
                    "location_lat": float(t.gen_lat) if t.gen_lat else None,
                    "location_lng": float(t.gen_lon) if t.gen_lon else None,
                    "notes": t.notes,
                    "status": t.status,
                    "completed_at": str(t.completed_at) if hasattr(t, 'completed_at') and t.completed_at else None,
                    "created_at": str(t.created_at) if hasattr(t, 'created_at') and t.created_at else None
                }
                for t in trips
            ],
            "contacts": [
                {
                    "id": c.id,
                    "name": c.name,
                    "email": c.email
                }
                for c in contacts
            ],
            "total_trips": len(trips),
            "total_contacts": len(contacts)
        }


@router.delete("/account")
def delete_account(user_id: int = Depends(auth.get_current_user_id)):
    """Delete current user's account and all associated data"""
    with db.engine.begin() as connection:
        # Delete in order to satisfy foreign key constraints:
        # Events reference trips, trips reference contacts
        # So delete order: events → trips → contacts

        # 1. Delete events (they reference trips via trip_id)
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id = :user_id"),
            {"user_id": user_id}
        )

        # 2. Delete trips (they reference contacts via contact1/2/3)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        )

        # 3. Delete saved contacts (now safe since trips are deleted)
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        )

        # 4. Delete devices
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        )

        # 5. Delete login tokens
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id = :user_id"),
            {"user_id": user_id}
        )

        # 6. Finally delete the user
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )

        return {"ok": True, "message": "Account deleted successfully"}
