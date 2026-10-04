"""DataUpdateCoordinator for ownCloud Infinite Scale."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
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
    users: dict[str, OcisUser]
    groups_total: int | None
    drives_total: int
    drives: dict[str, DriveData]
    storage_used: int
    storage_state: str | None
    storage_last_modified: datetime | None
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


class OcisUser(TypedDict, total=False):
    id: str
    username: str | None
    display_name: str
    enabled: bool
    user_type: str | None


def parse_users(users: list[dict[str, Any]]) -> dict[str, OcisUser]:
    """Index users by id for switch entities (skips entries without id)."""
    parsed: dict[str, OcisUser] = {}
    for u in users:
        uid = u.get("id")
        if not uid:
            continue
        uid = str(uid)
        parsed[uid] = OcisUser(
            id=uid,
            username=u.get("onPremisesSamAccountName"),
            display_name=str(u.get("displayName") or uid),
            enabled=u.get("accountEnabled", True) is not False,
            user_type=u.get("userType"),
        )
    return parsed


def is_primary_user(
    user: OcisUser, primary_username: str | None, primary_user_id: str | None
) -> bool:
    """True for the account used to configure the integration (never switched)."""
    if primary_user_id and user.get("id") == primary_user_id:
        return True
    if primary_username and isinstance(user.get("username"), str):
        return user["username"].lower() == primary_username.strip().lower()  # type: ignore[index]
    return False


def summarize_drives(
    drives: list[dict[str, Any]],
) -> tuple[dict[str, DriveData], int]:
    """Per-drive quota map + total used bytes (virtual drives excluded)."""
    parsed: dict[str, DriveData] = {}
    used = 0
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
        used += q_used
    return parsed, used


_STATE_SEVERITY = {"normal": 1, "nearing": 2, "critical": 3, "exceeded": 4}


def summarize_global_state(
    drives: list[dict[str, Any]],
) -> tuple[str | None, datetime | None]:
    """Worst quota state across real drives + latest modification time."""
    worst: str | None = None
    worst_rank = 0
    latest: datetime | None = None
    for d in drives:
        if str(d.get("driveType") or "unknown") == "virtual":
            continue
        state = (d.get("quota") or {}).get("state")
        if isinstance(state, str) and _STATE_SEVERITY.get(state, 0) > worst_rank:
            worst_rank = _STATE_SEVERITY[state]
            worst = state
        raw_ts = d.get("lastModifiedDateTime")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if latest is None or ts > latest:
                latest = ts
    return worst, latest


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
        parsed, s_used = summarize_drives(drives)
        state, last_modified = summarize_global_state(drives)

        version = status.get("productversion") or status.get("version")
        return OcisData(
            status=status,
            users_total=users_total,
            users_active=active,
            users_disabled=disabled,
            users=parse_users(users),
            groups_total=bundle.get("groups_total"),
            drives_total=len(parsed),
            drives=parsed,
            storage_used=s_used,
            storage_state=state,
            storage_last_modified=last_modified,
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

    def get_user(self, user_id: str) -> OcisUser | None:
        if not self.data:
            return None
        return self.data.get("users", {}).get(user_id)
