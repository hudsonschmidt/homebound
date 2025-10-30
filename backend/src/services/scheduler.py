from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..config import settings
from ..models import Plan, Event, Contact
from .notifications import send_overdue_notifications

log = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None

# Create a separate engine for scheduler to avoid connection issues
# Convert sync SQLite URL to async if needed
DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("sqlite"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
else:
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

scheduler_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
SchedulerSession = sessionmaker(scheduler_engine, class_=AsyncSession, expire_on_commit=False)


async def check_overdue_plans():
    """Check for overdue plans and send notifications."""
    async with SchedulerSession() as session:
        try:
            now = datetime.utcnow()

            # Find active plans that are overdue
            result = await session.execute(
                select(Plan)
                .where(Plan.status == "active")
                .where(Plan.eta_at < now)
            )
            overdue_plans = result.scalars().all()

            for plan in overdue_plans:
                # Check if we've already marked this plan as overdue
                event_result = await session.execute(
                    select(Event)
                    .where(Event.plan_id == plan.id)
                    .where(Event.kind == "overdue")
                    .limit(1)
                )
                existing_overdue = event_result.scalar_one_or_none()

                if existing_overdue:
                    # Already marked as overdue, check if grace period expired
                    grace_expired = plan.eta_at + timedelta(minutes=plan.grace_minutes)
                    if now > grace_expired:
                        # Check if we've already notified
                        notify_result = await session.execute(
                            select(Event)
                            .where(Event.plan_id == plan.id)
                            .where(Event.kind == "notify")
                            .limit(1)
                        )
                        existing_notify = notify_result.scalar_one_or_none()

                        if not existing_notify:
                            # Send notifications to contacts
                            contacts_result = await session.execute(
                                select(Contact)
                                .where(Contact.plan_id == plan.id)
                                .where(Contact.notify_on_overdue == True)
                            )
                            contacts = contacts_result.scalars().all()

                            if contacts:
                                log.info(f"Sending overdue notifications for plan {plan.id} to {len(contacts)} contacts")
                                await send_overdue_notifications(plan, contacts)

                                # Mark as notified
                                notify_event = Event(
                                    plan_id=plan.id,
                                    kind="notify",
                                    meta=f"Notified {len(contacts)} contacts"
                                )
                                session.add(notify_event)

                            # Update plan status
                            plan.status = "overdue_notified"
                else:
                    # Mark as overdue
                    log.info(f"Marking plan {plan.id} as overdue")
                    overdue_event = Event(
                        plan_id=plan.id,
                        kind="overdue"
                    )
                    session.add(overdue_event)
                    plan.status = "overdue"

                await session.commit()

        except Exception as e:
            log.error(f"Error checking overdue plans: {e}")
            await session.rollback()


async def clean_expired_tokens():
    """Clean up expired login tokens."""
    async with SchedulerSession() as session:
        try:
            from ..services.auth import clean_expired_tokens as cleanup
            deleted = await cleanup(session)
            if deleted > 0:
                log.info(f"Cleaned up {deleted} expired login tokens")
        except Exception as e:
            log.error(f"Error cleaning expired tokens: {e}")


def init_scheduler() -> AsyncIOScheduler:
    """Initialize and configure the scheduler."""
    global scheduler

    if scheduler is not None:
        return scheduler

    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

    # Check for overdue plans every minute
    scheduler.add_job(
        check_overdue_plans,
        IntervalTrigger(minutes=1),
        id="check_overdue",
        name="Check for overdue plans",
        replace_existing=True,
        max_instances=1,
    )

    # Clean expired tokens every 10 minutes
    scheduler.add_job(
        clean_expired_tokens,
        IntervalTrigger(minutes=10),
        id="clean_tokens",
        name="Clean expired tokens",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler


def start_scheduler():
    """Start the scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = init_scheduler()

    if not scheduler.running:
        scheduler.start()
        log.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        log.info("Scheduler stopped")