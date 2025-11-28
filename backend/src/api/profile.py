"""User profile management endpoints"""

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


class ProfileResponse(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    age: int
    profile_completed: bool


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
                SELECT id, email, first_name, last_name, age
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
            profile_completed=profile_completed
        )


@router.put("", response_model=ProfileUpdateResponse)
def update_profile(body: ProfileUpdate, user_id: int = Depends(auth.get_current_user_id)):
    """Update current user's profile"""
    with db.engine.begin() as connection:
        # Build dynamic update query
        updates: list[str] = []
        params: dict[str, str | int] = {"user_id": user_id}

        if body.first_name is not None:
            updates.append("first_name = :first_name")
            params["first_name"] = body.first_name

        if body.last_name is not None:
            updates.append("last_name = :last_name")
            params["last_name"] = body.last_name

        if body.age is not None:
            updates.append("age = :age")
            params["age"] = body.age

        if updates:
            connection.execute(
                sqlalchemy.text(f"UPDATE users SET {', '.join(updates)} WHERE id = :user_id"),
                params
            )

        # Return updated profile
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email, first_name, last_name, age
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
                "profile_completed": profile_completed
            }
        )


@router.patch("")
def patch_profile(body: ProfileUpdate, user_id: int = Depends(auth.get_current_user_id)):
    """Partially update current user's profile"""
    with db.engine.begin() as connection:
        # Build dynamic update query
        updates: list[str] = []
        params: dict[str, str | int] = {"user_id": user_id}

        if body.first_name is not None:
            updates.append("first_name = :first_name")
            params["first_name"] = body.first_name

        if body.last_name is not None:
            updates.append("last_name = :last_name")
            params["last_name"] = body.last_name

        if body.age is not None:
            updates.append("age = :age")
            params["age"] = body.age

        if updates:
            connection.execute(
                sqlalchemy.text(f"UPDATE users SET {', '.join(updates)} WHERE id = :user_id"),
                params
            )

        return {"ok": True, "message": "Profile updated successfully"}


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
