from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class ContactIn(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notify_on_overdue: bool = True


class PlanCreate(BaseModel):
    title: str
    start_at: datetime
    eta_at: datetime
    grace_minutes: int = Field(default=30, ge=0)
    location_text: Optional[str] = None
    notes: Optional[str] = None
    contacts: List[ContactIn] = Field(default_factory=list)


class PlanOut(BaseModel):
    id: int
    title: str
    start_at: datetime
    eta_at: datetime
    grace_minutes: int
    location_text: Optional[str] = None
    notes: Optional[str] = None
    status: str
    checkin_token: str
    checkout_token: str

    class Config:
        from_attributes = True
