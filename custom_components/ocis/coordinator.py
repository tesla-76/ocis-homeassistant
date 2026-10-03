"""DataUpdateCoordinator for ownCloud Infinite Scale."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OcisApi
from .const import (
    CONF_APP_TOKEN,
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .exceptions import OcisAuthError, OcisConnectionError, OcisError

_LOGGER = logging.getLogger(__name__)


class DriveData(TypedDict, total=False):
    id: str
    name: str
    drive_type: str
    total: int | None
    used: int | None
    free: int | None
    usage_percent: float | None
    quota_state: str | None
    owner: str | None


class OcisData(TypedDict):
    status: dict[str, Any]
    users_total: int
    users_active: int
    users_disabled: int
    groups_total: int | None
    drives_total: int
    drives: dict[str, DriveData]
    storage_total: int | None
    storage_used: int
    storage_free: int | None
    storage_usage_percent: float | None
    version: str | None
    edition: str | None


def _as_int(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def summarize_users(users: list[dict[str, Any]]) -> tuple[int, int, int]:
    total = len(users)
    disabled = sum(1 for u in users if u.get("accountEnabled") is False)
    return total, total - disabled, disabled


def summarize_drives(
    drives: list[dict[str, Any]],
) -> tuple[dict[str, DriveData], int | None, int, int | None, float | None]:
    """Build per-drive map + storage totals. Missing quota.total (OCIS #4328) -> None."""
    parsed: dict[str, DriveData] = {}
    total = 0
    used = 0
    complete = True  # False when any real (non-virtual) drive lacks a quota total
    counted = 0
    for d in drives:
        drive_id = str(d.get("id", ""))
        if not drive_id:
            continue
        drive_type = str(d.get("driveType") or "unknown")
        quota = d.get("quota") or {}
        q_total = _as_int(quota.get("total"))
        # OCIS uses total=0 for "unlimited/no quota" (remaining=max-int64).
        # Treat as unknown so usage % and storage totals stay sane.
        if not q_total:
            q_total = None
        q_used = _as_int(quota.get("used")) or 0
        q_remaining = _as_int(quota.get("remaining"))
        free = q_remaining
        if free is None and q_total is not None:
            free = max(q_total - q_used, 0)
        pct: float | None = None
        if q_total:
            pct = round(q_used / q_total * 100, 1)
        owner = d.get("owner") or {}
        owner_name: str | None = None
        if isinstance(owner, dict):
            user = owner.get("user") or {}
            owner_name = user.get("displayName") or user.get("id")
        parsed[drive_id] = DriveData(
            id=drive_id,
            name=str(d.get("name") or drive_id),
            drive_type=drive_type,
            total=q_total,
            used=q_used,
            free=free,
            usage_percent=pct,
            quota_state=quota.get("state"),
            owner=owner_name,
        )
        if drive_type == "virtual":
            continue  # Shares/Jail mounts: no real storage, keep out of totals
        counted += 1
        used += q_used
        if q_total is not None:
            total += q_total
        else:
            complete = False
    # Totals are only meaningful when every real drive has a limited quota;
    # otherwise report used bytes and leave total/percent unknown (honest).
    storage_total = total if (counted and complete) else None
    storage_free: int | None = None
    storage_pct: float | None = None
    if storage_total:
        storage_free = max(storage_total - used, 0)
        storage_pct = round(used / storage_total * 100, 1)
    return parsed, storage_total, used, storage_free, storage_pct


class OcisCoordinator(DataUpdateCoordinator[OcisData]):
    """Poll OCIS status + Graph users/drives. Lightweight: ~4 calls/cycle."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=minutes),
            always_update=False,
        )
        data = entry.data
        self.api = OcisApi(
            base_url=data[CONF_BASE_URL],
            username=data.get(CONF_USERNAME, "admin"),
            app_token=data[CONF_APP_TOKEN],
            verify_ssl=data.get(CONF_VERIFY_SSL, True),
        )

    async def _async_update_data(self) -> OcisData:
        try:
            # status.php is tiny + unauthenticated: also serves as online probe.
            # All independent -> single gather, one RTT per cycle.
            status, bundle = await asyncio.gather(
                self.api.async_get_status(), self.api.async_get_all()
            )
        except OcisAuthError as err:
            raise ConfigEntryAuthFailed(f"OCIS authentication failed: {err}") from err
        except OcisConnectionError as err:
            raise UpdateFailed(f"OCIS connection failed: {err}") from err
        except OcisError as err:
            raise UpdateFailed(f"OCIS request failed: {err}") from err

        users = bundle.get("users", [])
        drives = bundle.get("drives", [])
        users_total, active, disabled = summarize_users(users)
        parsed, s_total, s_used, s_free, s_pct = summarize_drives(drives)

        version = status.get("productversion") or status.get("version")
        return OcisData(
            status=status,
            users_total=users_total,
            users_active=active,
            users_disabled=disabled,
            groups_total=bundle.get("groups_total"),
            drives_total=len(parsed),
            drives=parsed,
            storage_total=s_total,
            storage_used=s_used,
            storage_free=s_free,
            storage_usage_percent=s_pct,
            version=str(version) if version else None,
            edition=status.get("edition"),
        )

    def get_drive_ids(self) -> list[str]:
        if not self.data:
            return []
        return list(self.data.get("drives", {}).keys())

    def get_drive(self, drive_id: str) -> DriveData | None:
        if not self.data:
            return None
        return self.data.get("drives", {}).get(drive_id)
