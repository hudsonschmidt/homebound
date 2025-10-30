"""Contact management endpoints with raw SQL"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from src import database as db
from src.api import auth
import sqlalchemy

router = APIRouter(
    prefix="/api/v1/contacts",
    tags=["contacts"],
    dependencies=[Depends(auth.get_current_user_id)]
)


class ContactCreate(BaseModel):
    plan_id: int
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notify_on_overdue: bool = True


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notify_on_overdue: Optional[bool] = None


class ContactResponse(BaseModel):
    id: int
    plan_id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    notify_on_overdue: bool


@router.get("", response_model=List[ContactResponse])
def list_contacts(user_id: int = Depends(auth.get_current_user_id), plan_id: Optional[int] = None):
    """List all contacts for the current user's plans"""

    with db.engine.begin() as conn:
        if plan_id:
            # Verify plan ownership
            plan = conn.execute(
                sqlalchemy.text("SELECT id FROM plans WHERE id = :plan_id AND user_id = :user_id"),
                {"plan_id": plan_id, "user_id": user_id}
            ).fetchone()

            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")

            # Get contacts for specific plan
            contacts = conn.execute(
                sqlalchemy.text("""
                    SELECT id, plan_id, name, phone, email, notify_on_overdue
                    FROM contacts
                    WHERE plan_id = :plan_id
                    ORDER BY id
                """),
                {"plan_id": plan_id}
            ).fetchall()
        else:
            # Get all contacts for user's plans
            contacts = conn.execute(
                sqlalchemy.text("""
                    SELECT c.id, c.plan_id, c.name, c.phone, c.email, c.notify_on_overdue
                    FROM contacts c
                    JOIN plans p ON c.plan_id = p.id
                    WHERE p.user_id = :user_id
                    ORDER BY c.id
                """),
                {"user_id": user_id}
            ).fetchall()

        return [
            ContactResponse(
                id=c.id,
                plan_id=c.plan_id,
                name=c.name,
                phone=c.phone,
                email=c.email,
                notify_on_overdue=bool(c.notify_on_overdue)
            )
            for c in contacts
        ]


@router.post("", response_model=ContactResponse)
def create_contact(body: ContactCreate, user_id: int = Depends(auth.get_current_user_id)):
    """Add a contact to a plan"""

    with db.engine.begin() as conn:
        # Verify plan ownership
        plan = conn.execute(
            sqlalchemy.text("SELECT id FROM plans WHERE id = :plan_id AND user_id = :user_id"),
            {"plan_id": body.plan_id, "user_id": user_id}
        ).fetchone()

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        # Insert contact
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO contacts (plan_id, name, phone, email, notify_on_overdue)
                VALUES (:plan_id, :name, :phone, :email, :notify_on_overdue)
            """),
            {
                "plan_id": body.plan_id,
                "name": body.name,
                "phone": body.phone,
                "email": body.email,
                "notify_on_overdue": body.notify_on_overdue
            }
        )
        contact_id = result.lastrowid

        # Fetch created contact
        contact = conn.execute(
            sqlalchemy.text("""
                SELECT id, plan_id, name, phone, email, notify_on_overdue
                FROM contacts
                WHERE id = :contact_id
            """),
            {"contact_id": contact_id}
        ).fetchone()

        return ContactResponse(
            id=contact.id,
            plan_id=contact.plan_id,
            name=contact.name,
            phone=contact.phone,
            email=contact.email,
            notify_on_overdue=bool(contact.notify_on_overdue)
        )


@router.get("/{contact_id}", response_model=ContactResponse)
def get_contact(contact_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific contact"""

    with db.engine.begin() as conn:
        # Get contact and verify ownership via plan
        contact = conn.execute(
            sqlalchemy.text("""
                SELECT c.id, c.plan_id, c.name, c.phone, c.email, c.notify_on_overdue
                FROM contacts c
                JOIN plans p ON c.plan_id = p.id
                WHERE c.id = :contact_id AND p.user_id = :user_id
            """),
            {"contact_id": contact_id, "user_id": user_id}
        ).fetchone()

        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        return ContactResponse(
            id=contact.id,
            plan_id=contact.plan_id,
            name=contact.name,
            phone=contact.phone,
            email=contact.email,
            notify_on_overdue=bool(contact.notify_on_overdue)
        )


@router.put("/{contact_id}", response_model=ContactResponse)
def update_contact(contact_id: int, body: ContactUpdate, user_id: int = Depends(auth.get_current_user_id)):
    """Update a contact"""

    with db.engine.begin() as conn:
        # Verify ownership via plan
        contact = conn.execute(
            sqlalchemy.text("""
                SELECT c.id
                FROM contacts c
                JOIN plans p ON c.plan_id = p.id
                WHERE c.id = :contact_id AND p.user_id = :user_id
            """),
            {"contact_id": contact_id, "user_id": user_id}
        ).fetchone()

        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Build update query dynamically
        updates = []
        params = {"contact_id": contact_id}

        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name

        if body.phone is not None:
            updates.append("phone = :phone")
            params["phone"] = body.phone

        if body.email is not None:
            updates.append("email = :email")
            params["email"] = body.email

        if body.notify_on_overdue is not None:
            updates.append("notify_on_overdue = :notify_on_overdue")
            params["notify_on_overdue"] = body.notify_on_overdue

        if updates:
            conn.execute(
                sqlalchemy.text(f"UPDATE contacts SET {', '.join(updates)} WHERE id = :contact_id"),
                params
            )

        # Fetch updated contact
        updated_contact = conn.execute(
            sqlalchemy.text("""
                SELECT id, plan_id, name, phone, email, notify_on_overdue
                FROM contacts
                WHERE id = :contact_id
            """),
            {"contact_id": contact_id}
        ).fetchone()

        return ContactResponse(
            id=updated_contact.id,
            plan_id=updated_contact.plan_id,
            name=updated_contact.name,
            phone=updated_contact.phone,
            email=updated_contact.email,
            notify_on_overdue=bool(updated_contact.notify_on_overdue)
        )


@router.delete("/{contact_id}")
def delete_contact(contact_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Delete a contact"""

    with db.engine.begin() as conn:
        # Verify ownership via plan
        contact = conn.execute(
            sqlalchemy.text("""
                SELECT c.id
                FROM contacts c
                JOIN plans p ON c.plan_id = p.id
                WHERE c.id = :contact_id AND p.user_id = :user_id
            """),
            {"contact_id": contact_id, "user_id": user_id}
        ).fetchone()

        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Delete contact
        conn.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE id = :contact_id"),
            {"contact_id": contact_id}
        )

        return {"ok": True, "message": "Contact deleted successfully"}
