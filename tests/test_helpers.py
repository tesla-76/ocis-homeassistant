"""Tests for pure helpers (no HA needed): quota math + normalization."""

from datetime import datetime, timezone

from custom_components.ocis.api import normalize_base_url
from custom_components.ocis.coordinator import (
    is_primary_user,
    latest_activity_for,
    parse_users,
    summarize_drives,
    summarize_global_state,
    summarize_users,
)

from .conftest import MOCK_DRIVES, MOCK_USERS


def test_normalize_base_url() -> None:
    assert normalize_base_url("ocis.example.com/") == "https://ocis.example.com"
    assert normalize_base_url("https://ocis.example.com/") == "https://ocis.example.com"


def test_summarize_users() -> None:
    assert summarize_users(MOCK_USERS) == (3, 2, 1)


def test_summarize_drives_missing_total() -> None:
    """drive-2 has no quota.total: per-drive unknown, used still summed."""
    parsed, used = summarize_drives(MOCK_DRIVES)
    assert parsed["drive-1"]["usage_percent"] == 25.0
    assert parsed["drive-2"]["total"] is None
    assert parsed["drive-2"]["usage_percent"] is None
    assert used == 350


def test_summarize_drives_virtual_excluded_from_used() -> None:
    drives = [
        {
            "id": "a",
            "name": "P",
            "driveType": "personal",
            "quota": {"total": 1000, "used": 250, "remaining": 750},
        },
        {"id": "c", "name": "Shares", "driveType": "virtual", "quota": None},
    ]
    parsed, used = summarize_drives(drives)
    assert used == 250
    assert "c" in parsed  # entities still created, just out of totals


def test_summarize_drives_zero_total_is_unlimited() -> None:
    """Real OCIS shape: total=0 + remaining=max-int64 means unlimited."""
    drives = [
        {
            "id": "a",
            "name": "Admin",
            "driveType": "personal",
            "quota": {
                "total": 0,
                "used": 254286989946,
                "remaining": 9223372036854775807,
                "state": "normal",
            },
        },
    ]
    parsed, used = summarize_drives(drives)
    assert parsed["a"]["total"] is None
    assert parsed["a"]["usage_percent"] is None
    assert used == 254286989946


def test_summarize_global_state_worst_and_latest() -> None:
    drives = [
        {
            "id": "a",
            "driveType": "personal",
            "quota": {"state": "normal"},
            "lastModifiedDateTime": "2026-09-01T10:00:00Z",
        },
        {
            "id": "b",
            "driveType": "project",
            "quota": {"state": "nearing"},
            "lastModifiedDateTime": "2026-10-02T08:30:00Z",
        },
        {"id": "c", "driveType": "virtual", "quota": {"state": "exceeded"}},
    ]
    state, latest = summarize_global_state(drives)
    assert state == "nearing"  # virtual drive ignored even though worse
    assert latest == datetime(2026, 10, 2, 8, 30, tzinfo=timezone.utc)


def test_summarize_global_state_empty() -> None:
    assert summarize_global_state([]) == (None, None)


def test_parse_users_and_primary_exclusion() -> None:
    users = parse_users(MOCK_USERS)
    assert set(users) == {"1", "2", "3"}
    assert users["1"]["username"] is None  # mocks carry no login name
    admin = {
        "id": "81990925-ede7-4763-ae9e-2e597a9a32d4",
        "username": "admin",
        "display_name": "Admin",
        "enabled": True,
        "user_type": "Member",
    }
    # Match by id (robust against renames)...
    assert is_primary_user(admin, "someone", admin["id"]) is True
    # ...fallback to username for entries created before user_id existed.
    assert is_primary_user(admin, "Admin", None) is True
    assert is_primary_user(admin, "other", None) is False
    assert is_primary_user(admin, None, None) is False


def test_drive_owner_id_parsed() -> None:
    drives = [
        {
            "id": "d1",
            "name": "Admin",
            "driveType": "personal",
            "quota": {"total": 10, "used": 1},
            "owner": {"user": {"id": "u-1", "displayName": "Admin"}},
        },
        {"id": "d2", "name": "Orphan", "driveType": "personal", "quota": {}},
    ]
    parsed, _ = summarize_drives(drives)
    assert parsed["d1"]["owner_id"] == "u-1"
    assert parsed["d1"]["owner"] == "Admin"
    assert parsed["d2"]["owner_id"] is None


def test_latest_activity_for_owner_and_shared() -> None:
    from datetime import datetime, timezone

    t1 = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 2, 8, 30, tzinfo=timezone.utc)
    drives = {
        "a": {"drive_type": "personal", "owner_id": "u-1", "last_modified": t1},
        "b": {"drive_type": "project", "owner_id": "u-1", "last_modified": t2},
        "c": {"drive_type": "project", "owner_id": None, "last_modified": t1},
        "v": {"drive_type": "virtual", "owner_id": None, "last_modified": t2},
    }
    assert latest_activity_for(drives, "u-1", {"u-1", "u-2"}) == t2
    assert latest_activity_for(drives, "u-2", {"u-1", "u-2"}) is None
    # Shared: unattributed drives only (virtual excluded even if newer).
    assert latest_activity_for(drives, None, {"u-1", "u-2"}) == t1
