from src.api.activities import Activity, delete_activity, get_activities, get_activity, new_activity


def test_get_all() -> None:
    activities = get_activities()

    assert isinstance(activities, list)
    assert all(isinstance(activity, Activity) for activity in activities)
    names = [activity.name for activity in activities]

    # Check for some expected activities that should be in the database
    assert "Hiking" in names
    assert "Biking" in names
    assert "Running" in names
    assert "Driving" in names
    assert "Camping" in names
    assert "Climbing" in names


def test_get_one():
    activity = get_activity("Hiking")

    assert isinstance(activity, Activity)
    assert activity.name == "Hiking"
    assert activity.icon == "🥾"
    assert activity.default_grace_minutes == 45
    assert isinstance(activity.colors, dict)
    assert isinstance(activity.messages, dict)
    assert isinstance(activity.safety_tips, list)

def test_new_delete():
    new_act = Activity(
        name="Test Activity",
        icon="🧪",
        default_grace_minutes=15,
        colors={"primary": "#FFFFFF", "secondary": "#000000"},
        messages={"start": "Starting test activity", "end": "Ending test activity"},
        safety_tips=["Always test safely.", "Use proper equipment."],
        order=999
    )

    new_activity(new_act)

    activity = get_activity("Test Activity")

    assert activity.name == new_act.name
    assert activity.icon == new_act.icon
    assert activity.default_grace_minutes == new_act.default_grace_minutes
    assert activity.colors == new_act.colors
    assert activity.messages == new_act.messages
    assert activity.safety_tips == new_act.safety_tips
    assert activity.order == new_act.order

    delete_activity("Test Activity")

    activity = get_activity("Test Activity")
    assert activity is None

