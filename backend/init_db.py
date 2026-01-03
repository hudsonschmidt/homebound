"""Initialize SQLite database with current schema.

Run this to set up a fresh local development database:
    python init_db.py
"""
import json
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# Load .env
from dotenv import load_dotenv
load_dotenv()

import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./homebound.db")

print(f"[init_db] Using database: {DATABASE_URL}")

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Base = declarative_base()

# Define tables using SQLAlchemy ORM (just for table creation)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(Text, nullable=False, unique=True)
    first_name = Column(Text, nullable=False, default="")
    last_name = Column(Text, nullable=False, default="")
    age = Column(Integer, nullable=False, default=0)
    apple_user_id = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class Activity(Base):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    icon = Column(Text, nullable=False)
    default_grace_minutes = Column(Integer, nullable=False)
    colors = Column(JSON, nullable=False)
    messages = Column(JSON, nullable=False)
    safety_tips = Column(JSON, nullable=False)
    order = Column(Integer, nullable=False)


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(Text, nullable=False)
    phone = Column(Text, nullable=True)
    email = Column(Text, nullable=True)


class Trip(Base):
    __tablename__ = "trips"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(Text, nullable=False)
    start = Column(DateTime, nullable=False)
    eta = Column(DateTime, nullable=False)
    activity = Column(Integer, ForeignKey("activities.id"), nullable=False)
    grace_min = Column(Integer, nullable=False)
    location_text = Column(Text, nullable=False)
    gen_lat = Column(Float, nullable=False)
    gen_lon = Column(Float, nullable=False)
    start_location_text = Column(Text, nullable=True)
    start_lat = Column(Float, nullable=True)
    start_lon = Column(Float, nullable=True)
    contact1 = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    contact2 = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    contact3 = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="scheduled")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    last_checkin = Column(Integer, nullable=True)
    checkin_token = Column(Text, nullable=True)
    checkout_token = Column(Text, nullable=True)
    timezone = Column(Text, nullable=True)
    last_grace_warning = Column(DateTime, nullable=True)
    last_checkin_reminder = Column(DateTime, nullable=True)
    eta_notified_at = Column(DateTime, nullable=True)
    grace_notified_at = Column(DateTime, nullable=True)
    notify_self = Column(Boolean, nullable=True, default=False)
    # Group trip fields
    is_group_trip = Column(Boolean, nullable=False, default=False)
    group_settings = Column(JSON, nullable=True)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    what = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    extended_by = Column(Integer, nullable=True)


class LoginToken(Base):
    __tablename__ = "login_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(Text, nullable=False)
    token = Column(Text, nullable=False, unique=True)
    bundle_id = Column(Text, nullable=False)
    env = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    notification_type = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    recipient = Column(Text, nullable=True)
    success = Column(Boolean, default=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    push_enabled = Column(Boolean, default=True)
    email_enabled = Column(Boolean, default=True)
    sms_enabled = Column(Boolean, default=False)


class Friendship(Base):
    __tablename__ = "friendships"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    friend_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)


class TripSafetyContact(Base):
    __tablename__ = "trip_safety_contacts"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    friend_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    position = Column(Integer, nullable=False, default=1)


class LiveActivityToken(Base):
    __tablename__ = "live_activity_tokens"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(256), nullable=False)
    bundle_id = Column(String(128), nullable=False)
    env = Column(String(32), nullable=False, default="development")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TripParticipant(Base):
    __tablename__ = "trip_participants"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False, default="participant")  # 'owner' or 'participant'
    status = Column(String(32), nullable=False, default="invited")  # 'invited', 'accepted', 'declined', 'left'
    invited_at = Column(DateTime, default=datetime.utcnow)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    joined_at = Column(DateTime, nullable=True)
    left_at = Column(DateTime, nullable=True)
    last_checkin_at = Column(DateTime, nullable=True)
    last_lat = Column(Float, nullable=True)
    last_lon = Column(Float, nullable=True)


class CheckoutVote(Base):
    __tablename__ = "checkout_votes"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    voted_at = Column(DateTime, default=datetime.utcnow)


# Activity seed data
ACTIVITIES = [
    {'name': 'Hiking', 'icon': '🥾', 'default_grace_minutes': 45, 'colors': {"accent": "#87CEEB", "primary": "#2D5016", "secondary": "#8B4513"}, 'messages': {"start": "Happy trails!", "checkin": "Good job checking in!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Trail conquered!"}, 'safety_tips': ["Pack water", "Check weather"], 'order': 1},
    {'name': 'Biking', 'icon': '🚴', 'default_grace_minutes': 30, 'colors': {"accent": "#2ECC71", "primary": "#FF6B35", "secondary": "#4A90E2"}, 'messages': {"start": "Ride safe!", "checkin": "Good job!", "overdue": "How's the ride?", "checkout": "Ride complete!"}, 'safety_tips': ["Wear helmet", "Check brakes"], 'order': 2},
    {'name': 'Running', 'icon': '🏃', 'default_grace_minutes': 20, 'colors': {"accent": "#F39C12", "primary": "#E74C3C", "secondary": "#34495E"}, 'messages': {"start": "Let's go!", "checkin": "Good job!", "overdue": "Check in!", "checkout": "Run complete!"}, 'safety_tips': ["Warm up", "Stay visible"], 'order': 3},
    {'name': 'Climbing', 'icon': '🧗', 'default_grace_minutes': 60, 'colors': {"accent": "#3498DB", "primary": "#7F8C8D", "secondary": "#E67E22"}, 'messages': {"start": "Climb safe!", "checkin": "Good job!", "overdue": "Everything good?", "checkout": "Summit reached!"}, 'safety_tips': ["Check gear", "Never climb alone"], 'order': 4},
    {'name': 'Camping', 'icon': '🏕️', 'default_grace_minutes': 90, 'colors': {"accent": "#4CAF50", "primary": "#1A237E", "secondary": "#FF6F00"}, 'messages': {"start": "Enjoy nature!", "checkin": "Good job!", "overdue": "Everything good?", "checkout": "Back to civilization!"}, 'safety_tips': ["Share location", "Store food properly"], 'order': 5},
    {'name': 'Driving', 'icon': '🚗', 'default_grace_minutes': 30, 'colors': {"accent": "#ECF0F1", "primary": "#2C3E50", "secondary": "#16A085"}, 'messages': {"start": "Safe travels!", "checkin": "Good job!", "overdue": "Arrived safely?", "checkout": "Arrived safely!"}, 'safety_tips': ["Take breaks", "Check route"], 'order': 17},
    {'name': 'Other Activity', 'icon': '📍', 'default_grace_minutes': 30, 'colors': {"accent": "#4ECDC4", "primary": "#6C63FF", "secondary": "#A8A8A8"}, 'messages': {"start": "Have a great adventure!", "checkin": "Thanks for checking in!", "overdue": "Everything OK?", "checkout": "Welcome back!"}, 'safety_tips': ["Stay aware", "Keep phone charged"], 'order': 19},
]


def init_database():
    """Create all tables and seed data."""
    print("[init_db] Creating tables...")
    Base.metadata.create_all(engine)
    print("[init_db] Tables created!")

    # Seed activities
    Session = sessionmaker(bind=engine)
    session = Session()

    existing = session.query(Activity).count()
    if existing == 0:
        print("[init_db] Seeding activities...")
        for act in ACTIVITIES:
            session.add(Activity(**act))
        session.commit()
        print(f"[init_db] Added {len(ACTIVITIES)} activities")
    else:
        print(f"[init_db] Activities already exist ({existing} found)")

    session.close()
    print("[init_db] Done!")


if __name__ == "__main__":
    init_database()
