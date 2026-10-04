"""Constants for the ownCloud Infinite Scale integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ocis"

CONF_BASE_URL: Final = "base_url"
CONF_APP_TOKEN: Final = "app_token"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_USER_ID: Final = "user_id"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 15
MIN_SCAN_INTERVAL_MINUTES: Final = 1
MAX_SCAN_INTERVAL_MINUTES: Final = 60

DEFAULT_TIMEOUT_SECONDS: Final = 10
USERS_PAGE_SIZE: Final = 999
DRIVES_PAGE_SIZE: Final = 200
