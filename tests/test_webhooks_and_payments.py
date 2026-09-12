import pytest
import pytest_asyncio
import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base, get_db
from app.core.config import settings
from app.models.order import Order
from app.models.catalog import CatalogItem
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_session: AsyncSession):
    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_whatsapp_webhook_verification(client: AsyncClient):
    # Test valid challenge
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "commb_webhook_verification_token_secret",
        "hub.challenge": "1122334455",
    }
    res = await client.get("/api/v1/webhooks/whatsapp", params=params)
    assert res.status_code == 200
    assert res.text == "1122334455"

    # Test invalid token
    params["hub.verify_token"] = "wrong_token"
    res = await client.get("/api/v1/webhooks/whatsapp", params=params)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_paystack_webhook_payment_success(client: AsyncClient, test_session: AsyncSession):
    order = Order(
        order_reference="ORD-TEST1234",
        customer_identifier="+2348011223344",
        channel="whatsapp",
        total_amount=15000.0,
        currency="NGN",
        status="pending",
    )
    test_session.add(order)
    await test_session.commit()

    payload = {
        "event": "charge.success",
        "data": {
            "reference": "ORD-TEST1234",
            "amount": 1500000, # 15,000 NGN in kobo
            "currency": "NGN",
            "status": "success",
        }
    }
    raw_payload = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.PAYSTACK_SECRET_KEY:
        import hmac
        import hashlib
        sig = hmac.new(settings.PAYSTACK_SECRET_KEY.encode("utf-8"), raw_payload, hashlib.sha512).hexdigest()
        headers["x-paystack-signature"] = sig

    res = await client.post("/api/v1/webhooks/payments/paystack", content=raw_payload, headers=headers)
    assert res.status_code == 200

    # Refresh order from DB to verify status updated to 'paid'
    await test_session.refresh(order)
    assert order.status == "paid"
    assert order.payment_gateway == "paystack"


@pytest.mark.asyncio
async def test_stripe_webhook_checkout_completed(client: AsyncClient, test_session: AsyncSession):
    order = Order(
        order_reference="ORD-STRIPE99",
        customer_identifier="tg_123456",
        channel="telegram",
        total_amount=50.0,
        currency="USD",
        status="pending",
    )
    test_session.add(order)
    await test_session.commit()

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": "ORD-STRIPE99",
                "amount_total": 5000,
                "currency": "usd",
                "payment_status": "paid",
            }
        }
    }
    res = await client.post("/api/v1/webhooks/payments/stripe", json=payload)
    assert res.status_code == 200

    await test_session.refresh(order)
    assert order.status == "paid"
    assert order.payment_gateway == "stripe"
