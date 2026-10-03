"""Binary sensor platform for ownCloud Infinite Scale."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OcisConfigEntry
from .coordinator import OcisCoordinator
from .entity import OcisEntity

PARALLEL_UPDATES = 0


class OcisOnlineSensor(OcisEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "server_online"

    def __init__(self, coordinator: OcisCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_server_online"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.last_update_success:
            return False
        if not self.coordinator.data:
            return None
        return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OcisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([OcisOnlineSensor(coordinator)])
