"""Diagnostics for ownCloud Infinite Scale (Gold tier, PII redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OcisConfigEntry

TO_REDACT = {
    "app_token",
    "token",
    "password",
    "access_token",
    "refresh_token",
    "secret",
    "username",
    "email",
    "owner",
    "displayName",
    "user_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OcisConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    # Redact drive owners/names partially: keep counts, drop raw user lists.
    safe = {
        "users_total": data.get("users_total"),
        "users_active": data.get("users_active"),
        "users_disabled": data.get("users_disabled"),
        "groups_total": data.get("groups_total"),
        "drives_total": data.get("drives_total"),
        "storage_used": data.get("storage_used"),
        "storage_state": data.get("storage_state"),
        "storage_last_modified": (
            data["storage_last_modified"].isoformat()
            if data.get("storage_last_modified")
            else None
        ),
        "version": data.get("version"),
        "edition": data.get("edition"),
        "drive_ids": sorted((data.get("drives") or {}).keys()),
    }
    return {
        "config_entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "domain": entry.domain,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "data": async_redact_data(safe, TO_REDACT),
        },
    }
