import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_admin_jwt

from app.models.user import AdminUser

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        admin = AdminUser(
            id=1,
            email="admin@test.com",
            password_hash="test_hash",
            name="Super Admin",
            role="super_admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    token = create_admin_jwt(user_id=1, email="admin@test.com", role="super_admin")
    return {"Authorization": f"Bearer {token}"}



@pytest.mark.asyncio
async def test_root_endpoint_serves_html(client: AsyncClient):
    """Test GET / serves HTML when requested by browser."""
    response = await client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "AI Commerce Bots | System Health" in response.text


@pytest.mark.asyncio
async def test_root_endpoint_serves_json(client: AsyncClient):
    """Test GET / serves JSON when requested with application/json."""
    response = await client.get("/", headers={"Accept": "application/json"})
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["version"] == "0.2.0"


@pytest.mark.asyncio
async def test_system_health_summary_endpoint(client: AsyncClient):
    """Test /api/v1/system/health-summary returns detailed subsystem statuses."""
    response = await client.get("/api/v1/system/health-summary")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["operational", "degraded"]
    assert "database" in data
    assert "llm" in data
    assert "channels" in data
    assert "instance_id" in data


@pytest.mark.asyncio
async def test_system_debug_info_endpoint(client: AsyncClient):
    """Test /api/v1/system/debug-info returns structured debug information."""
    response = await client.get("/api/v1/system/debug-info")
    assert response.status_code == 200
    data = response.json()
    assert data["commb_version"] == "0.2.0"
    assert "instance_id" in data
    assert "python_version" in data
    assert "platform" in data


@pytest.mark.asyncio
async def test_reports_summary_endpoint(client: AsyncClient, admin_headers):
    """Test /api/v1/reports/summary aggregates commerce and AI metrics."""
    response = await client.get("/api/v1/reports/summary?days=7", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_revenue" in data
    assert "total_orders" in data
    assert "conversion_rate" in data
    assert "ai_resolution_rate" in data
    assert "channels" in data
    assert len(data["channels"]) >= 1


@pytest.mark.asyncio
async def test_reports_export_csv_endpoint(client: AsyncClient, admin_headers):
    """Test /api/v1/reports/export-csv streams formatted CSV."""
    response = await client.get("/api/v1/reports/export-csv?days=30", headers=admin_headers)
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    assert "Order ID,Reference,Customer Name" in response.text


@pytest.mark.asyncio
async def test_settings_analytics_endpoints(client: AsyncClient, admin_headers):
    """Test GET and PUT /api/v1/settings/analytics for host PostHog configuration."""
    get_res = await client.get("/api/v1/settings/analytics", headers=admin_headers)
    assert get_res.status_code == 200

    put_res = await client.put(
        "/api/v1/settings/analytics",
        json={"posthog_api_key": "phc_test_12345", "posthog_host": "https://us.i.posthog.com"},
        headers=admin_headers,
    )
    assert put_res.status_code == 200
    assert put_res.json()["posthog_api_key"] == "phc_test_12345"
    assert put_res.json()["posthog_configured"] is True
