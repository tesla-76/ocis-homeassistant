"""Minimal async client for ownCloud Infinite Scale (OCIS 8.x).

Auth: app token created via ``ocis auth-app create``. Sent as HTTP Basic
``username:app_token`` (per OCIS auth-app docs: "passed as Basic Auth header").
``/status.php`` needs no auth.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import ssl
from typing import Any

import aiohttp

from .const import DEFAULT_TIMEOUT_SECONDS, DRIVES_PAGE_SIZE, USERS_PAGE_SIZE
from .exceptions import OcisAuthError, OcisConnectionError, OcisError

_LOGGER = logging.getLogger(__name__)


def normalize_base_url(raw: str) -> str:
    """Normalize user input to ``https://host`` without trailing slash."""
    value = (raw or "").strip().rstrip("/")
    if not value:
        return value
    if "://" not in value:
        value = f"https://{value}"
    return value


def gb_to_bytes(gb: float | None) -> int | None:
    """Convert GB to bytes for quota PATCH (0 = unlimited)."""
    if gb is None or isinstance(gb, bool):
        return None
    try:
        return max(int(float(gb) * 1024**3), 0)
    except (TypeError, ValueError):
        return None


class OcisApi:
    """Lightweight OCIS API wrapper with a single shared session."""

    def __init__(
        self,
        base_url: str,
        username: str,
        app_token: str,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.username = username
        self.app_token = app_token
        # aiohttp verifies by default; opt-out only via explicit UI flag.
        self.verify_ssl: bool | ssl.SSLContext = (
            verify_ssl if verify_ssl else ssl._create_unverified_context()  # noqa: SLF001
        )
        self._session: aiohttp.ClientSession | None = None

    def _basic_header(self) -> str:
        raw = f"{self.username}:{self.app_token}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)
            connector = aiohttp.TCPConnector(limit=4)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def async_close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        session = await self._get_session()
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = self._basic_header()
        url = self.base_url + path
        try:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                ssl=self.verify_ssl,
            ) as resp:
                if resp.status in (401, 403):
                    raise OcisAuthError(f"HTTP {resp.status} for {path}")
                if resp.status == 429:
                    retry = resp.headers.get("Retry-After", "unknown")
                    raise OcisError(f"Rate limited (Retry-After: {retry})")
                if resp.status >= 400:
                    body = (await resp.text())[:200]
                    raise OcisError(f"HTTP {resp.status} for {path}: {body}")
                if "json" in resp.content_type:
                    return await resp.json()
                return await resp.text()
        except (OcisAuthError, OcisError):
            raise
        except asyncio.TimeoutError as err:
            raise OcisConnectionError(f"Timeout for {path}: {err}") from err
        except aiohttp.ClientError as err:
            raise OcisConnectionError(f"Connection failed for {path}: {err}") from err

    async def async_get_status(self) -> dict[str, Any]:
        """GET /status.php — no auth. Returns version/productversion/edition."""
        data = await self._request("/status.php", auth=False)
        return data if isinstance(data, dict) else {}

    async def async_validate(self) -> dict[str, Any]:
        """Validate connectivity + credentials. Returns status dict."""
        status = await self.async_get_status()
        # Cheap auth probe: one user is enough to prove the app token works.
        await self._request("/graph/v1.0/users", params={"$top": 1}, auth=True)
        return status

    async def async_get_users_page(
        self, *, top: int = USERS_PAGE_SIZE
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "/graph/v1.0/users",
            params={
                "$top": top,
                "$select": "id,displayName,accountEnabled,userType,onPremisesSamAccountName",
            },
        )
        if isinstance(data, dict) and isinstance(data.get("value"), list):
            return data["value"]
        return []

    async def async_resolve_user_id(self, username: str) -> str | None:
        """Return the Graph id for a login name, None when not found."""
        wanted = (username or "").strip().lower()
        if not wanted:
            return None
        for user in await self.async_get_users_page():
            candidates = (
                user.get("onPremisesSamAccountName"),
                user.get("displayName"),
            )
            if any(isinstance(c, str) and c.lower() == wanted for c in candidates):
                uid = user.get("id")
                return str(uid) if uid else None
        return None

    async def async_set_user_enabled(self, user_id: str, enabled: bool) -> None:
        """Enable/disable an account (needs a write-enabled LDAP/IDM)."""
        await self._request(
            f"/graph/v1.0/users/{user_id}",
            method="PATCH",
            json_body={"accountEnabled": enabled},
        )

    async def async_set_drive_quota(
        self, drive_id: str, total_bytes: int | None
    ) -> None:
        """Set a Space quota in bytes (0 = unlimited, needs write permissions)."""
        await self._request(
            f"/graph/v1.0/drives/{drive_id}",
            method="PATCH",
            json_body={"quota": {"total": total_bytes if total_bytes else 0}},
        )

    async def async_get_groups_count(self) -> int | None:
        """Best-effort: None when forbidden so polling still succeeds."""
        try:
            data = await self._request(
                "/graph/v1.0/groups",
                params={"$top": 1, "$select": "id"},
            )
        except OcisAuthError:
            _LOGGER.debug("Groups endpoint forbidden for this token, skipping")
            return None
        if isinstance(data, dict):
            # Prefer odata count when present, else len of page.
            if "@odata.count" in data:
                try:
                    return int(data["@odata.count"])
                except (TypeError, ValueError):
                    pass
            value = data.get("value")
            if isinstance(value, list):
                return len(value)
        return None

    async def async_get_drives(self) -> list[dict[str, Any]]:
        data = await self._request(
            "/graph/v1.0/drives",
            params={
                "$top": DRIVES_PAGE_SIZE,
                "$select": "id,name,driveType,quota,owner,lastModifiedDateTime",
            },
        )
        if isinstance(data, dict) and isinstance(data.get("value"), list):
            return data["value"]
        return []

    async def async_get_all(self) -> dict[str, Any]:
        """Fetch users/drives/groups in parallel (3 calls per cycle)."""
        users, drives, groups_total = await asyncio.gather(
            self.async_get_users_page(),
            self.async_get_drives(),
            self.async_get_groups_count(),
        )
        return {"users": users, "drives": drives, "groups_total": groups_total}
