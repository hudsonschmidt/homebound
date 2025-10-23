from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    eta_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    grace_minutes: Mapped[int] = mapped_column(Integer, default=30)
    location_text: Mapped[Optional[str]] = mapped_column(Text, default=None)
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

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
