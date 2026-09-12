"""Keyless client for public release notes and the sponsor banner.

No API key, no SDK, no personal data: a single unauthenticated GET carrying
only the running version. Used by every install, self-hosted included, so that
update and security notices are never gated behind opting into cloud sync.
"""

from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logger import logger

# Shown when the instance has never successfully reached the updates endpoint.
DEFAULT_SUPPORT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "url": "https://github.com/sponsors/sannex-01",
    "title": "Support Open-Source CommB",
    "message": (
        "Enjoying CommB? Consider supporting future open-source development "
        "and maintenance."
    ),
}

_cached_support_config: Dict[str, Any] = dict(DEFAULT_SUPPORT_CONFIG)


def get_support_config() -> Dict[str, Any]:
    """Latest sponsor banner config, or the built-in default."""
    return _cached_support_config


def _coerce_releases(payload: Any) -> List[Dict[str, Any]]:
    """Normalise the releases payload into a list of plain dicts.

    The endpoint is public and its response is untrusted input, so anything
    that is not a well-formed release object is dropped rather than trusted.
    """
    if isinstance(payload, dict):
        payload = payload.get("releases") or payload.get("results") or []
    if not isinstance(payload, list):
        return []

    releases: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        version = item.get("version")
        if not version or not isinstance(version, str):
            continue
        releases.append(item)
    return releases


async def fetch_public_updates(
    app_version: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Fetch release notes and sponsor config from the public endpoint.

    Returns a dict with "releases" and "support" keys. Never raises: a failed
    update check must never affect a running instance, so errors are logged and
    an empty result returned.
    """
    global _cached_support_config

    result: Dict[str, Any] = {"releases": [], "support": None, "connected": False}

    if not settings.CHECK_FOR_UPDATES:
        logger.debug("CHECK_FOR_UPDATES is false; skipping public update check.")
        return result

    version = app_version or settings.APP_VERSION
    url = f"{settings.COMMB_UPDATES_URL.rstrip('/')}/releases"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # No auth header: this endpoint is public by design.
            resp = await client.get(url, params={"app_version": version})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        # Offline, firewalled or endpoint down: degrade quietly.
        logger.info(f"Public update check unavailable ({e}). Continuing without it.")
        return result

    result["connected"] = True
    result["releases"] = _coerce_releases(data)

    support = data.get("support") if isinstance(data, dict) else None
    if isinstance(support, dict):
        _cached_support_config = support
        result["support"] = support

    return result
