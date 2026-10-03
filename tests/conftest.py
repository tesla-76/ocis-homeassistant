"""Fixtures for OCIS tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ocis.const import (
    CONF_APP_TOKEN,
    CONF_BASE_URL,
    CONF_VERIFY_SSL,
)

MOCK_CONFIG = {
    CONF_BASE_URL: "https://ocis.example.com",
    "username": "admin",
    CONF_APP_TOKEN: "test-token",
    CONF_VERIFY_SSL: False,
}

MOCK_STATUS = {
    "version": "8.2.1",
    "productversion": "8.2.1",
    "edition": "Community",
    "installed": True,
}

MOCK_USERS = [
    {"id": "1", "displayName": "Admin", "accountEnabled": True, "userType": "Member"},
    {"id": "2", "displayName": "User", "accountEnabled": True, "userType": "Member"},
    {"id": "3", "displayName": "Old", "accountEnabled": False, "userType": "Member"},
]

MOCK_DRIVES = [
    {
        "id": "drive-1",
        "name": "Personal",
        "driveType": "personal",
        "quota": {"total": 1000, "used": 250, "remaining": 750, "state": "normal"},
        "owner": {"user": {"displayName": "Admin"}},
    },
    {
        "id": "drive-2",
        "name": "Project",
        "driveType": "project",
        "quota": {"used": 100},
        "owner": {},
    },
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    with patch(
        "custom_components.ocis.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_api() -> Generator[AsyncMock]:
    with (
        patch("custom_components.ocis.config_flow.OcisApi", autospec=True) as cls,
        patch("custom_components.ocis.coordinator.OcisApi", autospec=True) as cls2,
    ):
        inst = cls.return_value
        inst.async_validate = AsyncMock(return_value=MOCK_STATUS)
        inst.async_close = AsyncMock(return_value=None)
        inst2 = cls2.return_value
        inst2.async_get_status = AsyncMock(return_value=MOCK_STATUS)
        inst2.async_get_all = AsyncMock(
            return_value={
                "users": MOCK_USERS,
                "drives": MOCK_DRIVES,
                "groups_total": 2,
            }
        )
        inst2.async_close = AsyncMock(return_value=None)
        yield inst2
