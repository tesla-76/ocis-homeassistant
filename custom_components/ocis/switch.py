"""Switch platform: enable/disable OCIS accounts (never the primary one)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import CONF_USERNAME

from . import OcisConfigEntry
from .const import CONF_USER_ID
from .coordinator import OcisCoordinator, OcisUser, is_primary_user
from .entity import OcisEntity
from .exceptions import OcisError

PARALLEL_UPDATES = 0


class OcisUserSwitch(OcisEntity, SwitchEntity):
    """Toggle accountEnabled for one OCIS user via Libre Graph PATCH."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: OcisCoordinator, user: OcisUser) -> None:
        super().__init__(coordinator)
        self._user_id = user["id"]
        # Dynamic name (one per user) — static translation_key cannot vary.
        self._attr_name = user["display_name"]
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_user_{self._user_id}_enabled"
        )

    @property
    def is_on(self) -> bool | None:
        user = self.coordinator.get_user(self._user_id)
        if user is None:
            return None
        return user.get("enabled", True)

    @property
    def available(self) -> bool:
        return (
            super().available and self.coordinator.get_user(self._user_id) is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        user = self.coordinator.get_user(self._user_id)
        if user is None:
            return None
        return {
            "username": user.get("username"),
            "user_type": user.get("user_type"),
        }

    async def _async_set(self, enabled: bool) -> None:
        try:
            await self.coordinator.api.async_set_user_enabled(self._user_id, enabled)
        except OcisError as err:
            raise HomeAssistantError(
                f"Failed to {'enable' if enabled else 'disable'} account: {err}"
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OcisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    primary_username = entry.data.get(CONF_USERNAME)
    primary_user_id = entry.data.get(CONF_USER_ID)
    known: set[str] = set()

    def _switchable() -> dict[str, OcisUser]:
        users = (coordinator.data or {}).get("users", {})
        return {
            uid: u
            for uid, u in users.items()
            if not is_primary_user(u, primary_username, primary_user_id)
        }

    switchable = _switchable()
    known.update(switchable)
    async_add_entities(
        OcisUserSwitch(coordinator, user) for user in switchable.values()
    )

    def _check_new_users() -> None:
        current = set(_switchable())
        if new := current - known:
            known.update(new)
            users = _switchable()
            async_add_entities(
                OcisUserSwitch(coordinator, users[uid]) for uid in sorted(new)
            )

    entry.async_on_unload(coordinator.async_add_listener(_check_new_users))
