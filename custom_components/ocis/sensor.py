"""Sensor platform for ownCloud Infinite Scale."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OcisConfigEntry
from .const import DRIVES_PAGE_SIZE, USERS_PAGE_SIZE
from .coordinator import OcisCoordinator, OcisData, latest_activity_for
from .entity import OcisDriveEntity, OcisEntity, OcisUserEntity, shared_device_info

PARALLEL_UPDATES = 0


def _gb(value_bytes: Any) -> float | None:
    """Present bytes as GB (2 decimals) — raw bytes stay in coordinator data."""
    if value_bytes is None or isinstance(value_bytes, bool):
        return None
    try:
        return round(float(value_bytes) / 1024**3, 2)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, kw_only=True)
class OcisSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OcisData], Any]


@dataclass(frozen=True, kw_only=True)
class OcisDriveSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


GLOBAL_DESCRIPTIONS: tuple[OcisSensorDescription, ...] = (
    OcisSensorDescription(
        key="version",
        translation_key="version",
        value_fn=lambda d: d.get("version"),
    ),
    OcisSensorDescription(
        key="edition",
        translation_key="edition",
        value_fn=lambda d: d.get("edition"),
    ),
    OcisSensorDescription(
        key="users_total",
        translation_key="users_total",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("users_total"),
    ),
    OcisSensorDescription(
        key="users_disabled",
        translation_key="users_disabled",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("users_disabled"),
    ),
    OcisSensorDescription(
        key="groups_total",
        translation_key="groups_total",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("groups_total"),
    ),
    OcisSensorDescription(
        key="drives_total",
        translation_key="drives_total",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("drives_total"),
    ),
    OcisSensorDescription(
        key="storage_used",
        translation_key="storage_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda d: _gb(d.get("storage_used")),
    ),
    OcisSensorDescription(
        key="storage_state",
        translation_key="storage_state",
        value_fn=lambda d: d.get("storage_state"),
    ),
    OcisSensorDescription(
        key="storage_last_modified",
        translation_key="storage_last_modified",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.get("storage_last_modified"),
    ),
    OcisSensorDescription(
        key="scan_interval",
        translation_key="scan_interval",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("scan_interval_minutes"),
    ),
)

# Per-drive: only Used + Quota state (both enabled by default).
DRIVE_DESCRIPTIONS: tuple[OcisDriveSensorDescription, ...] = (
    OcisDriveSensorDescription(
        key="used",
        translation_key="drive_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda d: _gb(d.get("used")),
    ),
    OcisDriveSensorDescription(
        key="quota_state",
        translation_key="drive_quota_state",
        value_fn=lambda d: d.get("quota_state"),
    ),
)


class OcisSensor(OcisEntity, SensorEntity):
    entity_description: OcisSensorDescription

    def __init__(
        self, coordinator: OcisCoordinator, description: OcisSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key == "version":
            status = (self.coordinator.data or {}).get("status", {})
            return {
                "productversion": status.get("productversion"),
                "product": status.get("product"),
            }
        return None


class OcisUserActivitySensor(OcisUserEntity, SensorEntity):
    """Latest file activity across one user's Spaces."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "user_last_activity"

    def __init__(self, coordinator: OcisCoordinator, user_id: str) -> None:
        super().__init__(coordinator, user_id)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_user_{user_id}_last_activity"
        )

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        return latest_activity_for(
            data.get("drives", {}), self._user_id, set(data.get("users", {}))
        )


class OcisSharedActivitySensor(OcisEntity, SensorEntity):
    """Latest file activity across shared/unowned Spaces."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "shared_last_activity"

    def __init__(self, coordinator: OcisCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_shared_last_activity"
        )

    @property
    def device_info(self) -> DeviceInfo:
        return shared_device_info(self.coordinator)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        return latest_activity_for(
            data.get("drives", {}), None, set(data.get("users", {}))
        )


class OcisDriveSensor(OcisDriveEntity, SensorEntity):
    entity_description: OcisDriveSensorDescription

    def __init__(
        self,
        coordinator: OcisCoordinator,
        description: OcisDriveSensorDescription,
        drive_id: str,
    ) -> None:
        super().__init__(coordinator, drive_id)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_drive_{drive_id}_{description.key}"
        )

    @property
    def native_value(self) -> Any:
        drive = self.coordinator.get_drive(self._drive_id)
        if not drive:
            return None
        return self.entity_description.value_fn(drive)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        drive = self.coordinator.get_drive(self._drive_id)
        if not drive:
            return None
        return {
            "drive_name": drive.get("name"),
            "drive_type": drive.get("drive_type"),
            "owner": drive.get("owner"),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OcisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        OcisSensor(coordinator, desc) for desc in GLOBAL_DESCRIPTIONS
    ]
    entities.append(OcisSharedActivitySensor(coordinator))
    known_drives: set[str] = set()
    known_users: set[str] = set()

    def _users_now() -> list[str]:
        return list((coordinator.data or {}).get("users", {}))

    def _drives_now() -> list[str]:
        return coordinator.get_drive_ids()

    for drive_id in _drives_now():
        known_drives.add(drive_id)
        entities.extend(
            OcisDriveSensor(coordinator, desc, drive_id) for desc in DRIVE_DESCRIPTIONS
        )
    for user_id in _users_now():
        known_users.add(user_id)
        entities.append(OcisUserActivitySensor(coordinator, user_id))

    async_add_entities(entities)

    def _sync_drives() -> None:
        """Add entities for new drives/users; remove deleted drives, retired keys."""
        if not coordinator.data:
            return  # never wipe entities when we simply have no data yet
        current = set(_drives_now())
        if new := current - known_drives:
            known_drives.update(new)
            async_add_entities(
                OcisDriveSensor(coordinator, desc, did)
                for did in sorted(new)
                for desc in DRIVE_DESCRIPTIONS
            )
        if new_users := set(_users_now()) - known_users:
            known_users.update(new_users)
            async_add_entities(
                OcisUserActivitySensor(coordinator, uid) for uid in sorted(new_users)
            )
        # Suffixes of sensor types that no longer exist (e.g. after an
        # update that drops descriptions): their entities are retired too.
        # "_quota" belongs to the number platform: retired only with its drive.
        valid_suffixes = tuple(f"_{desc.key}" for desc in DRIVE_DESCRIPTIONS)
        retired_suffixes = ("_total", "_usage_percent", "_free")
        foreign_suffixes = ("_quota",)
        # Paginated (truncated) responses must never look like deletions.
        removed = known_drives - current if len(current) < DRIVES_PAGE_SIZE else set()
        # Always scan (cheap: a handful of entities every 15 min) so that
        # entities of dropped sensor types are retired automatically.
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        prefix = f"{entry.entry_id}_drive_"
        uprefix = f"{entry.entry_id}_user_"
        users_now = set(_users_now())
        removed_users = (
            known_users - users_now if len(users_now) < USERS_PAGE_SIZE else set()
        )
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            uid = entity.unique_id
            if uid.startswith(uprefix) and uid.endswith("_last_activity"):
                if uid[len(uprefix) : -len("_last_activity")] in removed_users:
                    registry.async_remove(entity.entity_id)
                continue
            if not uid.startswith(prefix):
                continue
            # unique_id = {entry_id}_drive_{drive_id}_{key}; match the
            # known key suffix explicitly (quota_state contains "_").
            rest = uid[len(prefix) :]
            suffix = next(
                (
                    s
                    for s in valid_suffixes + retired_suffixes + foreign_suffixes
                    if rest.endswith(s)
                ),
                None,
            )
            if suffix is None:
                continue
            drive_id = rest[: -len(suffix)]
            if drive_id in removed or suffix in retired_suffixes:
                registry.async_remove(entity.entity_id)
        known_drives.intersection_update(current)
        known_users.intersection_update(_users_now())

    entry.async_on_unload(coordinator.async_add_listener(_sync_drives))
