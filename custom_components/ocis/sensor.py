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
from homeassistant.const import PERCENTAGE, UnitOfInformation
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
        key="users_active",
        translation_key="users_active",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("users_active"),
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
        key="storage_total",
        translation_key="storage_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda d: _gb(d.get("storage_total")),
    ),
    OcisSensorDescription(
        key="storage_free",
        translation_key="storage_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda d: _gb(d.get("storage_free")),
    ),
    OcisSensorDescription(
        key="storage_usage_percent",
        translation_key="storage_usage_percent",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("storage_usage_percent"),
    ),
)

# User request: used + total + usage_percent enabled; rest opt-in.
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
        key="total",
        translation_key="drive_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda d: _gb(d.get("total")),
    ),
    OcisDriveSensorDescription(
        key="usage_percent",
        translation_key="drive_usage_percent",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("usage_percent"),
    ),
    OcisDriveSensorDescription(
        key="free",
        translation_key="drive_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _gb(d.get("free")),
    ),
    OcisDriveSensorDescription(
        key="quota_state",
        translation_key="drive_quota_state",
        entity_registry_enabled_default=False,
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
        """Add entities for new drives, remove those of deleted drives."""
        current = set(_drives_now())
        if new := current - known:
            known.update(new)
            async_add_entities(
                OcisDriveSensor(coordinator, desc, did)
                for did in sorted(new)
                for desc in DRIVE_DESCRIPTIONS
            )
        if removed := known - current:
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
                drive_id = next(
                    (
                        rest[: -len(suffix)]
                        for suffix in (
                            "_used",
                            "_total",
                            "_usage_percent",
                            "_free",
                            "_quota_state",
                        )
                        if rest.endswith(suffix)
                    ),
                    None,
                )
                if drive_id in removed:
                    registry.async_remove(entity.entity_id)
            known.intersection_update(current)

    entry.async_on_unload(coordinator.async_add_listener(_sync_drives))
