"""Contact management endpoints"""

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from src import database as db
from src.api import auth

router = APIRouter(
    prefix="/api/v1/contacts",
    tags=["contacts"],
    dependencies=[Depends(auth.get_current_user_id)]
)


class ContactCreate(BaseModel):
    name: str
    email: EmailStr  # Required for email notifications


class ContactUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None


class Contact(BaseModel):
    id: int
    user_id: int
    name: str
    email: str  # Required field


@router.get("/", response_model=list[Contact])
def get_contacts(user_id: int = Depends(auth.get_current_user_id)):
    """Get all contacts for the current user"""
    with db.engine.begin() as connection:
        contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, name, email
                FROM contacts
                WHERE user_id = :user_id
                ORDER BY id
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        return [Contact(**dict(c._mapping)) for c in contacts]


@router.get("/{contact_id}", response_model=Contact)
def get_contact(contact_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific contact"""
    with db.engine.begin() as connection:
        contact = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, name, email
                FROM contacts
                WHERE id = :contact_id AND user_id = :user_id
                """
            ),
            {"contact_id": contact_id, "user_id": user_id}
        ).fetchone()

        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found"
            )

        return Contact(**dict(contact._mapping))


@router.post("/", response_model=Contact, status_code=status.HTTP_201_CREATED)
def create_contact(body: ContactCreate, user_id: int = Depends(auth.get_current_user_id)):
    """Create a new contact"""
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "name": body.name,
                "email": body.email
            }
        )
        row = result.fetchone()
        assert row is not None
        contact_id = row[0]

        # Fetch created contact
        contact = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, name, email
                FROM contacts
                WHERE id = :contact_id
                """
            ),
            {"contact_id": contact_id}
        ).fetchone()
        assert contact is not None

        return Contact(**dict(contact._mapping))


@router.put("/{contact_id}", response_model=Contact)
def update_contact(
    contact_id: int,
    body: ContactUpdate,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Update a contact"""
    with db.engine.begin() as connection:
        # Verify ownership
        existing = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM contacts
                WHERE id = :contact_id AND user_id = :user_id
                """
            ),
            {"contact_id": contact_id, "user_id": user_id}
        ).fetchone()

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found"
            )

        # Build update query
        updates: list[str] = []
        params: dict[str, int | str] = {"contact_id": contact_id}

        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name

        if body.email is not None:
            updates.append("email = :email")
            params["email"] = body.email

        if updates:
            connection.execute(
                sqlalchemy.text(f"UPDATE contacts SET {', '.join(updates)} WHERE id = :contact_id"),
                params
            )

        # Fetch updated contact
        contact = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, name, email
                FROM contacts
                WHERE id = :contact_id
                """
            ),
            {"contact_id": contact_id}
        ).fetchone()
        assert contact is not None

        return Contact(**dict(contact._mapping))


@router.delete("/{contact_id}")
def delete_contact(contact_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Delete a contact"""
    with db.engine.begin() as connection:
        # Verify ownership
        contact = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM contacts
                WHERE id = :contact_id AND user_id = :user_id
                """
            ),
            {"contact_id": contact_id, "user_id": user_id}
        ).fetchone()

        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found"
            )

        # Check if contact is being used by any active or planned trips
        trips_using_contact = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, title
                FROM trips
                WHERE (contact1 = :contact_id OR contact2 = :contact_id OR contact3 = :contact_id)
                AND status IN ('planned', 'active')
                LIMIT 1
                """
            ),
            {"contact_id": contact_id}
        ).fetchone()

        if trips_using_contact:
            trip_title = trips_using_contact.title
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete contact. Used by trip: {trip_title}"
            )

        # NULL out contact references in completed trips (they no longer need the reference)
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET contact1 = CASE WHEN contact1 = :contact_id THEN NULL ELSE contact1 END,
                    contact2 = CASE WHEN contact2 = :contact_id THEN NULL ELSE contact2 END,
                    contact3 = CASE WHEN contact3 = :contact_id THEN NULL ELSE contact3 END
                WHERE (contact1 = :contact_id OR contact2 = :contact_id OR contact3 = :contact_id)
                AND status = 'completed'
                """
            ),
            {"contact_id": contact_id}
        )

        # Delete contact
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE id = :contact_id"),
            {"contact_id": contact_id}
        )

        return {"ok": True, "message": "Contact deleted successfully"}
