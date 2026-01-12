from src.api.activities import Activity, get_activities, get_activity


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

