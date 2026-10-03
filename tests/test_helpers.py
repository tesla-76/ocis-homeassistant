"""Tests for pure helpers (no HA needed): quota math + normalization."""

from datetime import datetime, timezone

from custom_components.ocis.api import normalize_base_url
from custom_components.ocis.coordinator import (
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
