import base64
import hashlib
import hmac
import json
import time

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base, get_db
from app.core.config import settings
from app.main import app

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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_sso_token(email: str, name: str = "Test Operator", exp_offset: int = 120) -> str:
    """Builds a token identical in shape to the one commb-cloud mints in
    app/api/v1/instances/[id]/sso/route.ts, signed with TEST_API_KEY."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps({"email": email, "name": name, "exp": int(time.time()) + exp_offset}).encode()
    )
    sig = hmac.new(TEST_API_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


@pytest.mark.asyncio
async def test_sso_via_form_post_matches_the_browser_form_submission(client):
    """This is the path that was broken: commb-cloud hands off SSO by
    submitting a real HTML <form> (method="POST", target="_blank"), which the
    browser always sends as application/x-www-form-urlencoded, never JSON.
    The endpoint previously only accepted a Pydantic JSON body, so every real
    SSO handoff failed with 'Input should be a valid dictionary or object'."""
    token = _make_sso_token("owner@example.com")

    res = await client.post(
        "/api/v1/auth/sso",
        data={"token": token},  # httpx sends dict `data=` as form-encoded
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert body["user"]["email"] == "owner@example.com"
    assert "commb_admin_session" in res.cookies


@pytest.mark.asyncio
async def test_sso_via_json_body_still_works(client):
    """JSON stays supported for any non-browser caller."""
    token = _make_sso_token("owner@example.com")

    res = await client.post("/api/v1/auth/sso", json={"token": token})

    assert res.status_code == 200, res.text
    assert res.json()["user"]["email"] == "owner@example.com"


@pytest.mark.asyncio
async def test_sso_rejects_bad_signature_regardless_of_encoding(client):
    token = _make_sso_token("owner@example.com")
    tampered = token[:-4] + "AAAA"

    form_res = await client.post("/api/v1/auth/sso", data={"token": tampered})
    json_res = await client.post("/api/v1/auth/sso", json={"token": tampered})

    assert form_res.status_code == 401
    assert json_res.status_code == 401


@pytest.mark.asyncio
async def test_sso_rejects_expired_token(client):
    token = _make_sso_token("owner@example.com", exp_offset=-60)

    res = await client.post("/api/v1/auth/sso", data={"token": token})

    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sso_missing_token_is_a_clean_400_not_a_500(client):
    res = await client.post("/api/v1/auth/sso", data={})

    assert res.status_code == 400


@pytest.mark.asyncio
async def test_sso_auto_provisions_an_admin_on_first_login(client):
    token = _make_sso_token("new-operator@example.com", name="New Operator")

    res = await client.post("/api/v1/auth/sso", data={"token": token})

    assert res.status_code == 200
    user = res.json()["user"]
    assert user["email"] == "new-operator@example.com"
    assert user["role"] == "admin"
