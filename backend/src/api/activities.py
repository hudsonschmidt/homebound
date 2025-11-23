from fastapi import APIRouter, status, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any
import sqlalchemy
import json
from src import database as db
from src.api import auth

router = APIRouter(
    prefix="/api/v1/activities",
    tags=["activities"]
)

class Activity(BaseModel):
    id: int | None = None
    name: str
    icon: str
    default_grace_minutes: int
    colors: Dict[str, str]
    messages: Dict[str, Any]  # Can contain strings or lists
    safety_tips: List[str]
    order: int


@router.get("/", response_model=List[Activity])
def get_activities():
    """
    Returns all activity types and their data
    """
    with db.engine.begin() as connection:
        activities = connection.execute(
            sqlalchemy.text(
                """
                SELECT *
                FROM activities
                """
            )
        ).mappings().all()

    return [Activity(**row) for row in activities]


@router.get("/{name}", response_model=Activity)
def get_activity(name: str):
    """
    Returns individual activity
    """
    with db.engine.begin() as connection:
        activity = connection.execute(
            sqlalchemy.text(
                """
                SELECT *
                FROM activities
                WHERE LOWER(name) = LOWER(:name)
                """
            ),
            {"name": name},
        ).mappings().one_or_none()

    return Activity(**activity) if activity else None


@router.post("/new", status_code=status.HTTP_200_OK)
def new_activity(activity: Activity, user_id: int = Depends(auth.get_current_user_id)):
    """
    Adds new activity type to the database (requires authentication)
    """
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO activities (name, icon, default_grace_minutes, colors, messages, safety_tips, "order")
                VALUES (:name, :icon, :default_grace_minutes, :colors, :messages, :safety_tips, :order)
                """
            ),
            {"name": activity.name,
             "icon": activity.icon,
             "default_grace_minutes": activity.default_grace_minutes,
             "colors": json.dumps(activity.colors),
             "messages": json.dumps(activity.messages),
             "safety_tips": json.dumps(activity.safety_tips),
             "order": activity.order},
        ) 


@router.delete("/{name}", status_code=status.HTTP_200_OK)
def delete_activity(name: str, user_id: int = Depends(auth.get_current_user_id)):
    """
    Deletes activity from the database (requires authentication)
    """
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                DELETE FROM activities
                WHERE name = :name
                """
            ),
            {"name": name},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Activity not found")
        