"""Base entity for ownCloud Infinite Scale."""

from __future__ import annotations

from urllib.parse import urlparse

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OcisCoordinator


class OcisEntity(CoordinatorEntity[OcisCoordinator]):
    """Server-level entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OcisCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        base_url: str = self.coordinator.config_entry.data.get("base_url", "")
        host = urlparse(base_url).netloc or base_url
        sw = (self.coordinator.data or {}).get("version")
        return DeviceInfo(
            identifiers={(DOMAIN, f"ocis_{host}".lower())},
            name=f"OCIS {host}",
            manufacturer="ownCloud",
            model="Infinite Scale",
            sw_version=sw,
            configuration_url=base_url or None,
        )


class OcisDriveEntity(CoordinatorEntity[OcisCoordinator]):
    """Entity grouped under one drive/space device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OcisCoordinator, drive_id: str) -> None:
        super().__init__(coordinator)
        self._drive_id = drive_id

    @property
    def device_info(self) -> DeviceInfo:
        base_url: str = self.coordinator.config_entry.data.get("base_url", "")
        host = urlparse(base_url).netloc or base_url
        drive = self.coordinator.get_drive(self._drive_id) or {}
        return DeviceInfo(
            identifiers={(DOMAIN, f"drive_{self._drive_id}")},
            name=str(drive.get("name") or self._drive_id[:8]),
            manufacturer="ownCloud",
            model=f"Space ({drive.get('drive_type', 'unknown')})",
            via_device=(DOMAIN, f"ocis_{host}".lower()),
        )

    @property
    def available(self) -> bool:
        return (
            super().available and self.coordinator.get_drive(self._drive_id) is not None
        )
