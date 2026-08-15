import time

from models.user import UserNotificationSettings, UserProfile


def test_user_notification_settings_defaults():
    settings = UserNotificationSettings()
    assert settings.start is True
    assert settings.finish is True
    assert settings.pause is True
    assert settings.min_time_to_end == 0
    assert settings.min_filament == 0
    assert settings.notified_filament is False
    assert settings.notified_time is False


def test_user_notification_settings_custom():
    settings = UserNotificationSettings(start=False, min_time_to_end=10)
    assert settings.start is False
    assert settings.finish is True
    assert settings.min_time_to_end == 10


def test_user_profile_defaults():
    profile = UserProfile(user_id="123")
    assert profile.user_id == "123"
    assert profile.is_approved is False
    assert profile.access_admin is False
    assert profile.state == "idle"
    assert profile.selected_printer_id is None
    assert profile.active_spool_id is None
    assert isinstance(profile.notify, UserNotificationSettings)
    assert profile.context_data == {}
    assert isinstance(profile.created_at, float)


def test_user_profile_to_dict():
    profile = UserProfile(
        user_id="123",
        is_approved=True,
        access_admin=True,
        selected_printer_id="p1",
        active_spool_id="s1",
        context_data={"extra": "data"},
    )
    d = profile.to_dict()
    assert d["user_id"] == "123"
    assert d["is_approved"] is True
    assert d["admin"] == {"access_admin": True}
    assert d["personal"] == {}
    assert d["state"] == "idle"
    assert "notify" in d
    assert d["context_data"]["extra"] == "data"
    assert d["context_data"]["selected_printer_id"] == "p1"
    assert d["context_data"]["active_spool_id"] == "s1"
    assert "created_at" in d


def test_user_profile_from_dict_full():
    data = {
        "user_id": "123",
        "is_approved": True,
        "created_at": 1000.0,
        "admin": {"access_admin": True},
        "state": "printing",
        "context_data": {"selected_printer_id": "p1", "active_spool_id": "s1", "extra": "data"},
        "notify": {"start": False, "min_time_to_end": 5},
    }
    profile = UserProfile.from_dict(data)
    assert profile.user_id == "123"
    assert profile.is_approved is True
    assert profile.created_at == 1000.0
    assert profile.access_admin is True
    assert profile.state == "printing"
    assert profile.selected_printer_id == "p1"
    assert profile.active_spool_id == "s1"
    assert profile.context_data == {"selected_printer_id": "p1", "active_spool_id": "s1", "extra": "data"}
    assert profile.notify.start is False
    assert profile.notify.min_time_to_end == 5


def test_user_profile_from_dict_empty():
    profile = UserProfile.from_dict({})
    assert profile.user_id == ""
    assert profile.is_approved is False
    assert profile.access_admin is False


def test_user_profile_from_dict_missing_admin_context():
    data = {"user_id": "456", "admin": None, "context_data": None}
    profile = UserProfile.from_dict(data)
    assert profile.user_id == "456"
    assert profile.access_admin is False
    assert profile.context_data == {}


def test_user_profile_round_trip():
    profile1 = UserProfile(
        user_id="789",
        is_approved=True,
        access_admin=True,
        state="paused",
        selected_printer_id="p2",
        active_spool_id="s2",
        context_data={"key": "val"},
        notify=UserNotificationSettings(start=False),
    )
    d = profile1.to_dict()
    profile2 = UserProfile.from_dict(d)
    assert profile1.user_id == profile2.user_id
    assert profile1.is_approved == profile2.is_approved
    assert profile1.access_admin == profile2.access_admin
    assert profile1.state == profile2.state
    assert profile1.selected_printer_id == profile2.selected_printer_id
    assert profile1.active_spool_id == profile2.active_spool_id
    expected_ctx = dict(profile1.context_data)
    expected_ctx["selected_printer_id"] = profile1.selected_printer_id
    expected_ctx["active_spool_id"] = profile1.active_spool_id
    assert profile2.context_data == expected_ctx
    assert profile1.notify.start == profile2.notify.start
    assert profile1.notify.min_time_to_end == profile2.notify.min_time_to_end


def test_user_notification_settings_from_dict_none():
    settings = UserNotificationSettings.from_dict(None)
    assert settings.start is True


def test_created_at_uses_time_default():
    profile = UserProfile(user_id="1")
    assert time.time() - profile.created_at < 1.0
