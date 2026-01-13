from typing import Any

import sqlalchemy
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src import database as db

router = APIRouter(
    prefix="/api/v1/activities",
    tags=["activities"]
)

class Activity(BaseModel):
    id: int | None = None
    name: str
    icon: str
    default_grace_minutes: int
    colors: dict[str, str]
    messages: dict[str, Any]  # Can contain strings or lists
    safety_tips: list[str]
    order: int


@router.get("/", response_model=list[Activity])
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

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity '{name}' not found"
        )
    return Activity(**activity)


