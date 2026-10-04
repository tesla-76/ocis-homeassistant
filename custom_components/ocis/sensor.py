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
from homeassistant.const import UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OcisConfigEntry
from .coordinator import OcisCoordinator, OcisData
from .entity import OcisDriveEntity, OcisEntity


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
    known: set[str] = set()

    def _drives_now() -> list[str]:
        return coordinator.get_drive_ids()

    for drive_id in _drives_now():
        known.add(drive_id)
        entities.extend(
            OcisDriveSensor(coordinator, desc, drive_id) for desc in DRIVE_DESCRIPTIONS
        )

    async_add_entities(entities)

    def _sync_drives() -> None:
        """Add entities for new drives; remove deleted drives and retired keys."""
        current = set(_drives_now())
        if new := current - known:
            known.update(new)
            async_add_entities(
                OcisDriveSensor(coordinator, desc, did)
                for did in sorted(new)
                for desc in DRIVE_DESCRIPTIONS
            )
        # Suffixes of sensor types that no longer exist (e.g. after an
        # update that drops descriptions): their entities are retired too.
        valid_suffixes = tuple(f"_{desc.key}" for desc in DRIVE_DESCRIPTIONS)
        retired_suffixes = ("_total", "_usage_percent", "_free")
        removed = known - current
        # Always scan (cheap: a handful of entities every 15 min) so that
        # entities of dropped sensor types are retired automatically.
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        prefix = f"{entry.entry_id}_drive_"
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            uid = entity.unique_id
            if not uid.startswith(prefix):
                continue
            # unique_id = {entry_id}_drive_{drive_id}_{key}; match the
            # known key suffix explicitly (quota_state contains "_").
            rest = uid[len(prefix) :]
            suffix = next(
                (s for s in valid_suffixes + retired_suffixes if rest.endswith(s)),
                None,
            )
            if suffix is None:
                continue
            drive_id = rest[: -len(suffix)]
            if drive_id in removed or suffix in retired_suffixes:
                registry.async_remove(entity.entity_id)
        known.intersection_update(current)

    entry.async_on_unload(coordinator.async_add_listener(_sync_drives))
