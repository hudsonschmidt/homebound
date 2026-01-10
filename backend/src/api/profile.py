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
    # Check if user's subscription allows data export
    from src.services.subscription_check import get_limits
    limits = get_limits(user_id)
    if not limits.export:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data export requires Homebound+"
        )

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


# ==================== Friend Visibility Settings ====================

class FriendVisibilitySettings(BaseModel):
    """Settings controlling what friends can see about user's trips and profile."""
    # Trip visibility settings
    friend_share_checkin_locations: bool
    friend_share_live_location: bool
    friend_share_notes: bool
    friend_allow_update_requests: bool
    friend_share_achievements: bool
    # Mini profile stats visibility settings
    friend_share_age: bool = True
    friend_share_total_trips: bool = True
    friend_share_adventure_time: bool = True
    friend_share_favorite_activity: bool = True


@router.get("/friend-visibility", response_model=FriendVisibilitySettings)
def get_friend_visibility(user_id: int = Depends(auth.get_current_user_id)):
    """Get current friend visibility settings.

    These settings control what information friends (app users who are safety contacts)
    can see about the user's trips and profile. Friends get richer info than email contacts.
    """
    with db.engine.begin() as connection:
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT friend_share_checkin_locations, friend_share_live_location,
                       friend_share_notes, friend_allow_update_requests,
                       friend_share_achievements,
                       friend_share_age, friend_share_total_trips,
                       friend_share_adventure_time, friend_share_favorite_activity
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

        # Use defaults if columns don't exist yet (backwards compatibility)
        return FriendVisibilitySettings(
            friend_share_checkin_locations=getattr(user, 'friend_share_checkin_locations', True),
            friend_share_live_location=getattr(user, 'friend_share_live_location', False),
            friend_share_notes=getattr(user, 'friend_share_notes', True),
            friend_allow_update_requests=getattr(user, 'friend_allow_update_requests', True),
            friend_share_achievements=getattr(user, 'friend_share_achievements', True),
            friend_share_age=getattr(user, 'friend_share_age', True),
            friend_share_total_trips=getattr(user, 'friend_share_total_trips', True),
            friend_share_adventure_time=getattr(user, 'friend_share_adventure_time', True),
            friend_share_favorite_activity=getattr(user, 'friend_share_favorite_activity', True)
        )


@router.put("/friend-visibility", response_model=FriendVisibilitySettings)
def update_friend_visibility(
    body: FriendVisibilitySettings,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Update friend visibility settings.

    These settings control what information friends can see:

    Trip visibility:
    - friend_share_checkin_locations: Show check-in locations on map
    - friend_share_live_location: Allow live location sharing (per-trip opt-in still required)
    - friend_share_notes: Share trip notes with friends
    - friend_allow_update_requests: Allow friends to request updates
    - friend_share_achievements: Allow friends to view achievement details

    Mini profile stats:
    - friend_share_age: Show your age on your profile
    - friend_share_total_trips: Show your total completed trips count
    - friend_share_adventure_time: Show your total adventure hours
    - friend_share_favorite_activity: Show your favorite activity
    """
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE users SET
                    friend_share_checkin_locations = :share_checkins,
                    friend_share_live_location = :share_live,
                    friend_share_notes = :share_notes,
                    friend_allow_update_requests = :allow_requests,
                    friend_share_achievements = :share_achievements,
                    friend_share_age = :share_age,
                    friend_share_total_trips = :share_total_trips,
                    friend_share_adventure_time = :share_adventure_time,
                    friend_share_favorite_activity = :share_favorite_activity
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "share_checkins": body.friend_share_checkin_locations,
                "share_live": body.friend_share_live_location,
                "share_notes": body.friend_share_notes,
                "allow_requests": body.friend_allow_update_requests,
                "share_achievements": body.friend_share_achievements,
                "share_age": body.friend_share_age,
                "share_total_trips": body.friend_share_total_trips,
                "share_adventure_time": body.friend_share_adventure_time,
                "share_favorite_activity": body.friend_share_favorite_activity
            }
        )

        return body
