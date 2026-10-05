"""Number platform: set personal Space quotas (GB, 0 = unlimited)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OcisConfigEntry
from .api import gb_to_bytes
from .coordinator import OcisCoordinator
from .entity import OcisDriveEntity
from .exceptions import OcisError

PARALLEL_UPDATES = 0

MAX_QUOTA_GB = 10240


class OcisDriveQuotaNumber(OcisDriveEntity, NumberEntity):
    """Quota limit for one personal Space. Only personal Spaces have quotas."""

    _attr_device_class = NumberDeviceClass.DATA_SIZE
    _attr_translation_key = "drive_quota"
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_QUOTA_GB
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: OcisCoordinator, drive_id: str) -> None:
        super().__init__(coordinator, drive_id)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_drive_{drive_id}_quota"
        )

    @property
    def native_value(self) -> float | None:
        drive = self.coordinator.get_drive(self._drive_id)
        if not drive:
            return None
        total = drive.get("total")
        if total is None:
            return None  # unlimited
        return round(total / 1024**3)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        drive = self.coordinator.get_drive(self._drive_id)
        if not drive:
            return None
        return {
            "drive_name": drive.get("name"),
            "unlimited": drive.get("total") is None,
        }

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.api.async_set_drive_quota(
                self._drive_id, gb_to_bytes(value)
            )
        except OcisError as err:
            raise HomeAssistantError(f"Failed to set quota: {err}") from err
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OcisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    def _personal_drives() -> list[str]:
        return [
            did
            for did in coordinator.get_drive_ids()
            if (coordinator.get_drive(did) or {}).get("drive_type") == "personal"
        ]

    for drive_id in _personal_drives():
        known.add(drive_id)
    async_add_entities(OcisDriveQuotaNumber(coordinator, did) for did in known)

    def _check_new_drives() -> None:
        if new := set(_personal_drives()) - known:
            known.update(new)
            async_add_entities(
                OcisDriveQuotaNumber(coordinator, did) for did in sorted(new)
            )

    entry.async_on_unload(coordinator.async_add_listener(_check_new_drives))
