"""Config flow for ownCloud Infinite Scale."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_USERNAME
from homeassistant.core import callback

from .api import OcisApi, normalize_base_url
from .const import (
    CONF_APP_TOKEN,
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    CONF_USER_ID,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)
from .exceptions import OcisAuthError, OcisConnectionError, OcisError

_LOGGER = logging.getLogger(__name__)


def _unique_id_for(base_url: str) -> str:
    parsed = urlparse(normalize_base_url(base_url).lower())
    return f"ocis_{parsed.netloc}".replace(":", "_")


class OcisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup + reauth for OCIS."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = normalize_base_url(user_input[CONF_BASE_URL])
            try:
                _, user_id = await self._async_validate(
                    base_url,
                    user_input[CONF_USERNAME],
                    user_input[CONF_APP_TOKEN],
                    user_input.get(CONF_VERIFY_SSL, True),
                )
            except OcisAuthError:
                errors["base"] = "invalid_auth"
            except OcisConnectionError:
                errors["base"] = "cannot_connect"
            except OcisError:
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001 - map to form error, never crash flow
                _LOGGER.exception("Unexpected OCIS validation error")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(_unique_id_for(base_url))
                self._abort_if_unique_id_configured()
                title = f"OCIS {urlparse(base_url).netloc}"
                data = {
                    CONF_BASE_URL: base_url,
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_APP_TOKEN: user_input[CONF_APP_TOKEN],
                    CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, True),
                    CONF_USER_ID: user_id,
                }
                options = {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES}
                return self.async_create_entry(title=title, data=data, options=options)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BASE_URL, default="https://ocis.example.com"
                    ): str,
                    vol.Required(CONF_USERNAME, default="admin"): str,
                    vol.Required(CONF_APP_TOKEN): str,
                    vol.Optional(CONF_VERIFY_SSL, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def _async_validate(
        self, base_url: str, username: str, app_token: str, verify_ssl: bool
    ) -> tuple[dict[str, Any], str | None]:
        """Validate connectivity + credentials; resolve the user id (best-effort)."""
        api = OcisApi(base_url, username, app_token, verify_ssl=verify_ssl)
        try:
            status = await api.async_validate()
            try:
                user_id = await api.async_resolve_user_id(username)
            except OcisError:
                _LOGGER.debug("Could not resolve user id, using username fallback")
                user_id = None
            return status, user_id
        finally:
            await api.async_close()

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            data = {
                **reauth_entry.data,
                CONF_APP_TOKEN: user_input[CONF_APP_TOKEN],
                CONF_VERIFY_SSL: user_input.get(
                    CONF_VERIFY_SSL, reauth_entry.data.get(CONF_VERIFY_SSL, True)
                ),
            }
            try:
                _, user_id = await self._async_validate(
                    data[CONF_BASE_URL],
                    data.get(CONF_USERNAME, "admin"),
                    data[CONF_APP_TOKEN],
                    data.get(CONF_VERIFY_SSL, True),
                )
                # Keep the primary-account id fresh (rename-safe).
                data[CONF_USER_ID] = user_id
            except OcisAuthError:
                errors["base"] = "invalid_auth"
            except OcisConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected OCIS reauth error")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(_unique_id_for(data[CONF_BASE_URL]))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(reauth_entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APP_TOKEN): str,
                    vol.Optional(
                        CONF_VERIFY_SSL,
                        default=reauth_entry.data.get(CONF_VERIFY_SSL, True),
                    ): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OcisOptionsFlow()


class OcisOptionsFlow(OptionsFlow):
    """Polling interval only — connection stays in entry.data."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_SCAN_INTERVAL_MINUTES,
                            max=MAX_SCAN_INTERVAL_MINUTES,
                        ),
                    ),
                }
            ),
        )
