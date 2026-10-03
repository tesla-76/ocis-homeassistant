"""The ownCloud Infinite Scale integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN
from .coordinator import OcisCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

OcisConfigEntry = ConfigEntry[OcisCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: OcisConfigEntry) -> bool:
    """Set up OCIS from a config entry."""
    # First refresh raises ConfigEntryNotReady on transport errors (auto-retry)
    # and ConfigEntryAuthFailed on 401/403 (triggers reauth) — both handled by HA.
    coordinator = OcisCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    def _update_interval_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        from datetime import timedelta

        coordinator.update_interval = timedelta(minutes=minutes)

    entry.async_on_unload(entry.add_update_listener(_update_interval_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OcisConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.api.async_close()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries (schema v1 from day one)."""
    if entry.version > 1:
        _LOGGER.error("OCIS entry version %s newer than supported", entry.version)
        return False
    return True
