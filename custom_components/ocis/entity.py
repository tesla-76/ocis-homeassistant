"""Base entities for ownCloud Infinite Scale.

Device layout:
- server device: global sensors + binary sensor;
- one device per OCIS user: account switch + that user's Space sensors;
- "shared spaces" device: Spaces without a known single owner.
"""

from __future__ import annotations

from urllib.parse import urlparse

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OcisCoordinator, OcisUser


def _server_identifiers(coordinator: OcisCoordinator) -> set[tuple[str, str]]:
    base_url: str = coordinator.config_entry.data.get("base_url", "")
    host = urlparse(base_url).netloc or base_url
    return {(DOMAIN, f"ocis_{host}".lower())}


def _server_name(coordinator: OcisCoordinator) -> str:
    base_url: str = coordinator.config_entry.data.get("base_url", "")
    host = urlparse(base_url).netloc or base_url
    return f"OCIS {host}"


def shared_device_info(coordinator: OcisCoordinator) -> DeviceInfo:
    """Device for project/shared Spaces with no single owner."""
    return DeviceInfo(
        identifiers={(DOMAIN, "shared_spaces")},
        name="OCIS shared spaces",
        manufacturer="ownCloud",
        model="Shared spaces",
        via_device=next(iter(_server_identifiers(coordinator))),
    )


def user_device_info(
    coordinator: OcisCoordinator, user_id: str, fallback_name: str | None = None
) -> DeviceInfo:
    """Device for one OCIS user (switch + their Spaces)."""
    users = (coordinator.data or {}).get("users", {})
    user: OcisUser | None = users.get(user_id)
    name = (user or {}).get("display_name") or fallback_name or user_id[:8]
    return DeviceInfo(
        identifiers={(DOMAIN, f"user_{user_id}")},
        name=str(name),
        manufacturer="ownCloud",
        model="OCIS account",
        via_device=next(iter(_server_identifiers(coordinator))),
    )


class OcisEntity(CoordinatorEntity[OcisCoordinator]):
    """Server-level entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OcisCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        base_url: str = self.coordinator.config_entry.data.get("base_url", "")
        sw = (self.coordinator.data or {}).get("version")
        return DeviceInfo(
            identifiers=_server_identifiers(self.coordinator),
            name=_server_name(self.coordinator),
            manufacturer="ownCloud",
            model="Infinite Scale",
            sw_version=sw,
            configuration_url=base_url or None,
        )


class OcisUserEntity(CoordinatorEntity[OcisCoordinator]):
    """Entity grouped under one OCIS user device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OcisCoordinator, user_id: str) -> None:
        super().__init__(coordinator)
        self._user_id = user_id

    @property
    def device_info(self) -> DeviceInfo:
        return user_device_info(self.coordinator, self._user_id)

    @property
    def available(self) -> bool:
        users = (self.coordinator.data or {}).get("users", {})
        return super().available and self._user_id in users


class OcisDriveEntity(CoordinatorEntity[OcisCoordinator]):
    """Space sensor, grouped under its owner's user device (or shared)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OcisCoordinator, drive_id: str) -> None:
        super().__init__(coordinator)
        self._drive_id = drive_id

    def _owner_user_id(self) -> str | None:
        drive = self.coordinator.get_drive(self._drive_id)
        owner_id = (drive or {}).get("owner_id")
        if owner_id and (self.coordinator.data or {}).get("users", {}).get(owner_id):
            return owner_id
        return None

    @property
    def device_info(self) -> DeviceInfo:
        if (owner_id := self._owner_user_id()) is not None:
            drive = self.coordinator.get_drive(self._drive_id) or {}
            return user_device_info(
                self.coordinator, owner_id, fallback_name=drive.get("owner")
            )
        return shared_device_info(self.coordinator)

    @property
    def available(self) -> bool:
        return (
            super().available and self.coordinator.get_drive(self._drive_id) is not None
        )
