from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base, get_db
from app.core.config import settings
from app.main import app
from app.models.order import Order

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
TEST_API_KEY = "test-commb-api-key"


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    original_key = settings.COMMB_API_KEY
    settings.COMMB_API_KEY = TEST_API_KEY
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()
    settings.COMMB_API_KEY = original_key


def _order(ref, amount, status, channel, days_ago=0):
    return Order(
        order_reference=ref,
        customer_identifier="2348000000000",
        customer_name="Should Not Leak",
        channel=channel,
        total_amount=amount,
        status=status,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


@pytest.mark.asyncio
async def test_stats_requires_the_instance_key(client):
    assert (await client.get("/api/v1/cloud/stats")).status_code == 401
    bad = await client.get("/api/v1/cloud/stats", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_stats_aggregates_orders_without_personal_data(client, db_session):
    db_session.add_all(
        [
            _order("A1", 18500, "paid", "whatsapp"),
            _order("A2", 20000, "pending", "telegram"),
            _order("A3", 5000, "completed", "whatsapp", days_ago=3),
            _order("OLD", 99999, "paid", "whatsapp", days_ago=60),
        ]
    )
    await db_session.commit()

    res = await client.get("/api/v1/cloud/stats?days=7", headers={"Authorization": f"Bearer {TEST_API_KEY}"})
    assert res.status_code == 200
    body = res.json()

    assert body["totals"]["orders"] == 4
    assert body["totals"]["paid_orders"] == 3
    assert body["period"]["orders"] == 3
    assert body["period"]["revenue"] == 23500
    assert body["period"]["channels"] == {"whatsapp": 2, "telegram": 1}
    assert len(body["daily"]) == 7
    assert body["daily"][-1]["orders"] == 2
    assert body["daily"][-1]["revenue"] == 18500
    assert "Should Not Leak" not in res.text
