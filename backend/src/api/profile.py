"""User profile management endpoints"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from src import database as db
from src.api import auth
import sqlalchemy

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["profile"],
    dependencies=[Depends(auth.get_current_user_id)]
)


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None


class ProfileResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]
    phone: Optional[str]
    age: Optional[int]


@router.get("", response_model=ProfileResponse)
def get_profile(user_id: int = Depends(auth.get_current_user_id)):
    """Get current user's profile"""

    with db.engine.begin() as conn:
        user = conn.execute(
            sqlalchemy.text("""
                SELECT id, email, name, phone, age
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id}
        ).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return ProfileResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            phone=user.phone,
            age=user.age
        )


@router.put("", response_model=ProfileResponse)
def update_profile( profile: ProfileUpdate):
    """Update current user's profile"""

    with db.engine.begin() as conn:
        # Build dynamic update query
        updates = []
        params = {"user_id": user_id}

        if profile.name is not None:
            updates.append("name = :name")
            params["name"] = profile.name

        if profile.phone is not None:
            updates.append("phone = :phone")
            params["phone"] = profile.phone

        if profile.age is not None:
            updates.append("age = :age")
            params["age"] = profile.age

        if updates:
            query = f"UPDATE users SET {', '.join(updates)} WHERE id = :user_id"
            conn.execute(sqlalchemy.text(query), params)

        # Return updated profile
        user = conn.execute(
            sqlalchemy.text("""
                SELECT id, email, name, phone, age
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id}
        ).fetchone()

        return ProfileResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            phone=user.phone,
            age=user.age
        )


@router.delete("/account")
def delete_account(user_id: int = Depends(auth.get_current_user_id)):
    """Delete current user's account"""

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )

        return {"ok": True, "message": "Account deleted successfully"}