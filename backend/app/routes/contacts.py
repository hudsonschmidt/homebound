"""
Emergency contacts management endpoints
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes
from pydantic import BaseModel

from ..core.db import get_session
from ..models import User
from ..services.auth import get_current_user_id

router = APIRouter(prefix="/api/v1", tags=["contacts"])


class SavedContactIn(BaseModel):
    """Input model for creating a saved contact"""
    name: str
    phone: str
    email: str | None = None


class SavedContactOut(BaseModel):
    """Output model for saved contacts"""
    id: str
    name: str
    phone: str
    email: str | None = None


class SavedContactsStore(BaseModel):
    """Model for storing contacts in user's JSON field"""
    contacts: List[SavedContactOut] = []


@router.get("/contacts", response_model=List[SavedContactOut])
async def get_saved_contacts(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Get all saved emergency contacts for the user."""
    user_id = get_current_user_id(request)

    # Get user and their saved contacts
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get contacts from user's saved_contacts JSON field (handle NULL values)
    saved_contacts = user.saved_contacts or {}
    contacts_list = saved_contacts.get('contacts', [])

    return [SavedContactOut(**contact) for contact in contacts_list]


@router.post("/contacts", response_model=SavedContactOut)
async def add_saved_contact(
    request: Request,
    contact: SavedContactIn,
    session: AsyncSession = Depends(get_session),
):
    """Add a new saved emergency contact."""
    user_id = get_current_user_id(request)

    # Get user
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get existing contacts (handle NULL values)
    saved_contacts = user.saved_contacts or {}
    contacts_list = saved_contacts.get('contacts', [])

    # Check limit (10 max saved contacts)
    if len(contacts_list) >= 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum of 10 saved contacts allowed"
        )

    # Create new contact with unique ID
    import uuid
    new_contact = SavedContactOut(
        id=str(uuid.uuid4()),
        name=contact.name,
        phone=contact.phone,
        email=contact.email
    )

    # Add to list
    contacts_list.append(new_contact.model_dump())

    # Update user's saved_contacts field
    user.saved_contacts = {'contacts': contacts_list}

    # Mark the JSON field as modified so SQLAlchemy knows to update it
    attributes.flag_modified(user, 'saved_contacts')

    await session.commit()
    await session.refresh(user)

    return new_contact


@router.delete("/contacts/{contact_id}")
async def delete_saved_contact(
    contact_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Delete a saved emergency contact."""
    user_id = get_current_user_id(request)

    # Get user
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get existing contacts (handle NULL values)
    saved_contacts = user.saved_contacts or {}
    contacts_list = saved_contacts.get('contacts', [])

    # Find and remove the contact
    original_count = len(contacts_list)
    contacts_list = [c for c in contacts_list if c.get('id') != contact_id]

    if len(contacts_list) == original_count:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Update user's saved_contacts field
    user.saved_contacts = {'contacts': contacts_list}

    # Mark the JSON field as modified so SQLAlchemy knows to update it
    attributes.flag_modified(user, 'saved_contacts')

    await session.commit()

    return {"ok": True, "message": "Contact deleted successfully"}