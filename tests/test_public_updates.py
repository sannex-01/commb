"""Tests for the keyless public update check.

The point of app.updates is that release notes and the sponsor banner reach
EVERY install without a key, an account, or the optional SDK -- so these tests
assert the no-key path explicitly rather than relying on the cloud-sync tests.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

from app.core.database import Base
from app.models.release import ReleaseNote
from app.cloud_sync.sync_worker import perform_remote_sync
from app.updates.client import fetch_public_updates, DEFAULT_SUPPORT_CONFIG


@pytest.fixture
async def async_session():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await test_engine.dispose()


def _mock_response(payload):
    resp = MagicMock()
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock(return_value=None)
    return resp


def _patch_get(resp):
    """Patch httpx.AsyncClient.get used inside app.updates.client."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=resp)
    return patch("app.updates.client.httpx.AsyncClient", return_value=client), client


@pytest.mark.asyncio
async def test_public_update_check_sends_no_auth_header_and_no_key():
    """The whole point: a plain GET, no Authorization header, version only."""
    payload = {"releases": [{"version": "9.9.9", "title": "Test"}], "support": None}
    patcher, client = _patch_get(_mock_response(payload))
    with patcher:
        with patch("app.updates.client.settings.CHECK_FOR_UPDATES", True):
            result = await fetch_public_updates(app_version="0.2.0")

    assert result["connected"] is True
    assert result["releases"][0]["version"] == "9.9.9"

    # No credentials of any kind may be attached to a public update check.
    _, kwargs = client.get.call_args
    assert "headers" not in kwargs or "Authorization" not in (kwargs.get("headers") or {})
    assert kwargs["params"] == {"app_version": "0.2.0"}


@pytest.mark.asyncio
async def test_releases_sync_without_any_key_or_sdk(async_session: AsyncSession):
    """A self-hosted instance -- no cloud key, no SDK -- still gets releases."""
    payload = {
        "releases": [{
            "version": "1.2.3",
            "title": "Security Update",
            "description": "Important fix",
            "changelog": ["Fixed a thing"],
            "is_critical": True,
        }],
        "support": None,
    }
    patcher, _ = _patch_get(_mock_response(payload))
    with patcher, \
         patch("app.cloud_sync.sync_worker.AsyncCommBClient", None), \
         patch("app.cloud_sync.sync_worker.settings.COMMB_CLOUD_KEY", None), \
         patch("app.cloud_sync.sync_worker.settings.COMMB_TELEMETRY_KEY", None), \
         patch("app.updates.client.settings.CHECK_FOR_UPDATES", True):
        summary = await perform_remote_sync(async_session)

    assert summary["status"] == "success"
    assert summary["collector_connected"] is False   # never touched the cloud
    assert summary["releases_synced"] == 1

    rel = await async_session.scalar(select(ReleaseNote).where(ReleaseNote.version == "1.2.3"))
    assert rel is not None
    assert rel.is_critical is True


@pytest.mark.asyncio
async def test_update_check_can_be_disabled_for_offline_installs():
    with patch("app.updates.client.settings.CHECK_FOR_UPDATES", False):
        result = await fetch_public_updates(app_version="0.2.0")
    assert result == {"releases": [], "support": None, "connected": False}


@pytest.mark.asyncio
async def test_unreachable_endpoint_degrades_quietly():
    """An offline or firewalled instance must not raise."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(side_effect=OSError("no network"))
    with patch("app.updates.client.httpx.AsyncClient", return_value=client), \
         patch("app.updates.client.settings.CHECK_FOR_UPDATES", True):
        result = await fetch_public_updates(app_version="0.2.0")

    assert result["connected"] is False
    assert result["releases"] == []


@pytest.mark.asyncio
async def test_malformed_release_payload_is_ignored():
    """The endpoint is public, so its response is untrusted input."""
    payload = {"releases": ["not-a-dict", {"no_version": True}, {"version": "2.0.0"}]}
    patcher, _ = _patch_get(_mock_response(payload))
    with patcher, patch("app.updates.client.settings.CHECK_FOR_UPDATES", True):
        result = await fetch_public_updates(app_version="0.2.0")

    assert [r["version"] for r in result["releases"]] == ["2.0.0"]


def test_default_support_config_available_before_any_fetch():
    """Sponsor banner has a sane built-in default; no network required."""
    assert DEFAULT_SUPPORT_CONFIG["enabled"] is True
    assert DEFAULT_SUPPORT_CONFIG["url"].startswith("https://")
