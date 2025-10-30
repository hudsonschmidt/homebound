"""Activity types and configurations - read-only endpoints"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict

router = APIRouter(prefix="/api/v1/activities", tags=["activities"])


# Activity configurations with themes, messages, and defaults
ACTIVITIES = {
    "hiking": {
        "name": "Hiking",
        "icon": "🥾",
        "default_grace_minutes": 45,
        "description": "Mountain trails and nature walks"
    },
    "biking": {
        "name": "Biking",
        "icon": "🚴",
        "default_grace_minutes": 30,
        "description": "Cycling and bike rides"
    },
    "running": {
        "name": "Running",
        "icon": "🏃",
        "default_grace_minutes": 20,
        "description": "Jogging and running"
    },
    "walking": {
        "name": "Walking",
        "icon": "🚶",
        "default_grace_minutes": 30,
        "description": "Casual walking"
    },
    "driving": {
        "name": "Driving",
        "icon": "🚗",
        "default_grace_minutes": 30,
        "description": "Road trips and commutes"
    },
    "other": {
        "name": "Other",
        "icon": "📍",
        "default_grace_minutes": 30,
        "description": "Other activities"
    }
}


class ActivityType(BaseModel):
    type: str
    name: str
    icon: str
    default_grace_minutes: int
    description: str


@router.get("", response_model=List[ActivityType])
def list_activities():
    """Get list of all activity types"""
    return [
        ActivityType(
            type=key,
            name=activity["name"],
            icon=activity["icon"],
            default_grace_minutes=activity["default_grace_minutes"],
            description=activity["description"]
        )
        for key, activity in ACTIVITIES.items()
    ]


@router.get("/{activity_type}", response_model=ActivityType)
def get_activity(activity_type: str):
    """Get details for a specific activity type"""
    if activity_type not in ACTIVITIES:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Activity type not found")

    activity = ACTIVITIES[activity_type]
    return ActivityType(
        type=activity_type,
        name=activity["name"],
        icon=activity["icon"],
        default_grace_minutes=activity["default_grace_minutes"],
        description=activity["description"]
    )