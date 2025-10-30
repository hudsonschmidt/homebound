from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, validator


# Valid activity types
ACTIVITY_TYPES = [
    'hiking', 'biking', 'running', 'climbing', 'camping', 'backpacking',
    'skiing', 'snowboarding', 'kayaking', 'sailing', 'fishing', 'surfing',
    'scuba_diving', 'free_diving', 'snorkeling', 'horseback_riding',
    'driving', 'flying', 'other'
]


# ---- Contacts / Plans ----
class ContactIn(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notify_on_overdue: bool = True


class PlanCreate(BaseModel):
    title: str
    activity_type: str = "other"
    start_at: datetime
    eta_at: datetime
    grace_minutes: int = Field(default=30, ge=0)  # Allow 0 for immediate notifications
    location_text: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    notes: Optional[str] = None
    contacts: List[ContactIn] = Field(default_factory=list)

    @validator('activity_type')
    def validate_activity_type(cls, v):
        if v not in ACTIVITY_TYPES:
            raise ValueError(f'Invalid activity type. Must be one of: {", ".join(ACTIVITY_TYPES)}')
        return v


class PlanOut(BaseModel):
    id: int
    title: str
    activity_type: str
    start_at: datetime
    eta_at: datetime
    grace_minutes: int
    location_text: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
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
