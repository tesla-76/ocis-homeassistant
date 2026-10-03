"""Tests for pure helpers (no HA needed): quota math + normalization."""

from custom_components.ocis.api import normalize_base_url
from custom_components.ocis.coordinator import summarize_drives, summarize_users

from .conftest import MOCK_DRIVES, MOCK_USERS


def test_normalize_base_url() -> None:
    assert normalize_base_url("ocis.example.com/") == "https://ocis.example.com"
    assert normalize_base_url("https://ocis.example.com/") == "https://ocis.example.com"


def test_summarize_users() -> None:
    assert summarize_users(MOCK_USERS) == (3, 2, 1)


def test_summarize_drives_missing_total() -> None:
    """drive-2 has no quota.total (OCIS #4328): per-drive unknown, no global total."""
    parsed, total, used, free, pct = summarize_drives(MOCK_DRIVES)
    assert parsed["drive-1"]["usage_percent"] == 25.0
    assert parsed["drive-2"]["total"] is None
    assert parsed["drive-2"]["usage_percent"] is None
    assert total is None  # incomplete: cannot report a meaningful total
    assert pct is None
    assert free is None
    assert used == 350


def test_summarize_drives_all_limited_and_virtual_excluded() -> None:
    drives = [
        {
            "id": "a",
            "name": "P",
            "driveType": "personal",
            "quota": {"total": 1000, "used": 250, "remaining": 750},
        },
        {
            "id": "b",
            "name": "Proj",
            "driveType": "project",
            "quota": {"total": 1000, "used": 100, "remaining": 900},
        },
        {"id": "c", "name": "Shares", "driveType": "virtual", "quota": None},
    ]
    parsed, total, used, free, pct = summarize_drives(drives)
    assert total == 2000
    assert used == 350
    assert free == 1650
    assert pct == 17.5
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
    parsed, total, used, free, pct = summarize_drives(drives)
    assert parsed["a"]["total"] is None
    assert parsed["a"]["usage_percent"] is None
    assert total is None
    assert pct is None
    assert used == 254286989946
