"""Test OCIS config flow (PHACC style; runs in CI on HA 2025+)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ocis.const import DOMAIN
from custom_components.ocis.exceptions import OcisAuthError, OcisConnectionError

from .conftest import MOCK_CONFIG, MOCK_STATUS


def _patch_validate():
    return patch(
        "custom_components.ocis.config_flow.OcisApi",
        autospec=True,
    )


async def test_user_flow_success(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Full success path creates one entry with normalized URL."""
    with _patch_validate() as cls:
        inst = cls.return_value
        inst.async_validate = AsyncMock(return_value=MOCK_STATUS)
        inst.async_close = AsyncMock(return_value=None)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], dict(MOCK_CONFIG)
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["base_url"] == "https://ocis.example.com"
        assert result["options"]["scan_interval"] == 15


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    with _patch_validate() as cls:
        cls.return_value.async_validate = AsyncMock(
            side_effect=OcisConnectionError("down")
        )
        cls.return_value.async_close = AsyncMock(return_value=None)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], dict(MOCK_CONFIG)
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    with _patch_validate() as cls:
        cls.return_value.async_validate = AsyncMock(side_effect=OcisAuthError("401"))
        cls.return_value.async_close = AsyncMock(return_value=None)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], dict(MOCK_CONFIG)
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}
