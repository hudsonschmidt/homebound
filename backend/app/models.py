from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    phone: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    age: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    plans: Mapped[List["Plan"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    devices: Mapped[List["Device"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    login_tokens: Mapped[List["LoginToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(6))  # 6-digit code
    email: Mapped[str] = mapped_column(String(255), index=True)  # Store email for lookup
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), default=None)

    user: Mapped[User] = relationship(back_populates="login_tokens")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    activity_type: Mapped[str] = mapped_column(String(50), default="other")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    eta_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    grace_minutes: Mapped[int] = mapped_column(Integer, default=30)
    location_text: Mapped[Optional[str]] = mapped_column(Text, default=None)
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), default=None)
    extended_count: Mapped[int] = mapped_column(Integer, default=0)
    last_checkin_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="plans")
    contacts: Mapped[List["Contact"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    events: Mapped[List["Event"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    email: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    notify_on_overdue: Mapped[bool] = mapped_column(Boolean, default=True)

    plan: Mapped[Plan] = relationship(back_populates="contacts")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))  # created | checkin | checkout | overdue | notify
    at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    meta: Mapped[Optional[str]] = mapped_column(Text, default=None)

    plan: Mapped[Plan] = relationship(back_populates="events")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(16), default="ios")  # 'ios'
    token: Mapped[str] = mapped_column(String(256), unique=True)
    bundle_id: Mapped[str] = mapped_column(String(256))
    env: Mapped[str] = mapped_column(String(16), default="sandbox")  # 'sandbox' | 'prod'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="devices")