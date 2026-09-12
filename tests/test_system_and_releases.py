import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.models.release import ReleaseNote
from app.telemetry.sync_worker import perform_remote_sync
from unittest.mock import patch, MagicMock


@pytest.fixture
async def async_session():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session_factory() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_system_version_endpoint(async_session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: async_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/system/version")
        assert res.status_code == 200
        data = res.json()
        assert data["version"] == "0.2.0"
        assert data["name"] == "CommB Assistant"
        assert "support" in data
        assert data["support"]["enabled"] is True
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_system_releases_endpoint_fallback(async_session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: async_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/system/releases")
        assert res.status_code == 200
        releases = res.json()
        assert len(releases) >= 1
        assert releases[0]["version"] == "0.2.0"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_perform_remote_sync_ingests_release_notes(async_session: AsyncSession):
    from unittest.mock import AsyncMock
    from sannex_agent.client import ReleaseNote as SannexReleaseNote, SannexConfigResponse

    mock_release = SannexReleaseNote(
        version="0.1.0",
        title="AgentOS Dynamic Release Sync",
        description="Release notes synced from AgentOS to CommB instance.",
        changelog=["Sync release notes", "Read-only config"],
        release_date="2026-09-05",
        is_critical=False,
    )

    with patch("app.telemetry.sync_worker.AsyncCommBClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.get_config = AsyncMock(return_value=SannexConfigResponse(status="success", releases=[mock_release]))
        mock_instance.get_releases = AsyncMock(return_value=[mock_release])
        mock_client_cls.return_value = mock_instance
        with patch("app.telemetry.sync_worker.settings.COMMB_TELEMETRY_KEY", "dummy_key"):

            summary = await perform_remote_sync(async_session)
            assert summary["status"] == "success"
            assert summary["releases_synced"] == 1

            # Check DB
            rel = await async_session.scalar(select(ReleaseNote).where(ReleaseNote.version == "0.1.0"))
            assert rel is not None
            assert rel.title == "AgentOS Dynamic Release Sync"
            assert "Read-only config" in rel.changelog_json

