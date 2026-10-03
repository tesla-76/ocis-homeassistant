"""Exceptions for the ownCloud Infinite Scale integration."""

from __future__ import annotations


class OcisError(Exception):
    """Base error for OCIS API failures."""


class OcisAuthError(OcisError):
    """Authentication failed (invalid/expired app token or forbidden)."""


class OcisConnectionError(OcisError):
    """Network, DNS, TLS or timeout failure reaching OCIS."""
