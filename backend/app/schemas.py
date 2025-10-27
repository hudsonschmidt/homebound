from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---- Contacts / Plans ----
class ContactIn(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notify_on_overdue: bool = True


class PlanCreate(BaseModel):
    title: str
    activity_type: str = "other"  # hiking, biking, running, climbing, driving, flying, camping, other
    start_at: datetime
    eta_at: datetime
    grace_minutes: int = Field(default=30, ge=0)
    location_text: Optional[str] = None
    notes: Optional[str] = None
    contacts: List[ContactIn] = Field(default_factory=list)


class PlanOut(BaseModel):
    id: int
    title: str
    activity_type: str
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


# ---- Devices ----
class DeviceRegisterIn(BaseModel):
    token: str
    platform: str = "ios"
    bundle_id: Optional[str] = None
    env: str = "sandbox"  # 'sandbox' | 'prod'


class DeviceOut(BaseModel):
    id: int
    platform: str
    token: str
    bundle_id: str
    env: str

    class Config:
        from_attributes = True
