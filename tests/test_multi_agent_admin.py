import pytest
import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base, get_db
from app.main import app
from app.models.catalog import CatalogItem
from app.models.knowledge import KnowledgeDoc
from app.models.customer import Customer
from app.models.order import Order
from app.models.agent import Agent
from app.models.access_group import AccessGroup
from app.commerce.catalog_provider import CatalogManager
from app.ai.rag import RAGEngine
from app.core.security import generate_platform_api_key

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
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


@pytest.mark.asyncio
async def test_platform_api_key_generation():
    raw_key, key_hash, masked = generate_platform_api_key()
    assert raw_key.startswith("commb_live_")
    assert len(key_hash) == 64
    assert "..." in masked


@pytest.mark.asyncio
async def test_first_run_setup_and_idempotency_lockout(client: AsyncClient):
    # 1. Initial status check should report uninitialized
    res = await client.get("/api/v1/setup/status")
    assert res.status_code == 200
    assert res.json()["initialized"] is False

    # 2. Complete first-run setup
    setup_payload = {
        "admin_name": "Test Super Admin",
        "admin_email": "admin@example.com",
        "admin_password": "SuperSecretPassword123!",
        "business_name": "Apex Retail NG",
        "currency": "NGN",
        "contact_email": "hello@apexretail.ng",
        "contact_phone": "+2348011223344",
    }
    res = await client.post("/api/v1/setup/initialize", json=setup_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "initialized"
    assert "access_token" in data
    assert data["platform_api_key"].startswith("commb_live_")

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Subsequent status check must report initialized
    res = await client.get("/api/v1/setup/status")
    assert res.status_code == 200
    assert res.json()["initialized"] is True

    # 4. Lockout guard: attempting to initialize again must return 403
    res_repeat = await client.post("/api/v1/setup/initialize", json=setup_payload)
    assert res_repeat.status_code == 403

    # 5. Test Admin Login with the newly created credentials
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "SuperSecretPassword123!",
    })
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # 6. Test Auth Me
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "admin@example.com"
    assert me_res.json()["role"] in ("super_admin", "admin")

    # 7. Test API Key preview & Rotation
    key_info_res = await client.get("/api/v1/settings/api-key", headers=headers)
    assert key_info_res.status_code == 200
    assert "commb_live_" in key_info_res.json()["api_key_prefix"]

    rotate_res = await client.post("/api/v1/settings/api-key/rotate", headers=headers)
    assert rotate_res.status_code == 200
    new_raw_key = rotate_res.json()["raw_api_key"]
    assert new_raw_key.startswith("commb_live_")
    assert new_raw_key != data["platform_api_key"]


@pytest.mark.asyncio
async def test_access_groups_and_multi_agent_crud(client: AsyncClient, db_session: AsyncSession):
    # Initialize super admin
    setup_res = await client.post("/api/v1/setup/initialize", json={
        "admin_name": "Admin",
        "admin_email": "admin2@example.com",
        "admin_password": "Password12345!",
        "business_name": "Multi Agent Store",
    })
    token = setup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Access Group
    grp_res = await client.post("/api/v1/access-groups", json={
        "name": "Wholesale & VIP Group",
        "description": "Access to wholesale items",
        "tags": ["wholesale", "vip"],
    }, headers=headers)
    assert grp_res.status_code == 201
    group_id = grp_res.json()["id"]

    # 2. Create Multi-Agent tied to group
    agent_res = await client.post("/api/v1/agents", json={
        "name": "VIP Concierge Bot",
        "slug": "vip-concierge",
        "description": "Assists high-value buyers",
        "system_prompt": "You are a VIP concierge consultant.",
        "model_name": "gpt-4o",
        "llm_provider": "openai",
        "temperature": 0.5,
        "max_tokens": 1500,
        "group_id": group_id,
        "access_tags": ["special_order"],
        "whatsapp_phone_id": "10992384723",
        "whatsapp_token": "EAABsecretwa12345678",
        "telegram_username": "@vip_concierge_bot",
        "telegram_bot_token": "712345678:AAF-testsecrettoken99",
        "widget_enabled": True,
        "is_active": True,
    }, headers=headers)
    assert agent_res.status_code == 201
    agent_id = agent_res.json()["id"]

    # 3. List agents and verify effective tags & masked tokens
    list_res = await client.get("/api/v1/agents", headers=headers)
    assert list_res.status_code == 200
    agents = list_res.json()
    assert len(agents) >= 1
    created_agent = next((a for a in agents if a["slug"] == "vip-concierge"), None)
    assert created_agent is not None
    effective_tags = set(created_agent["effective_tags"])
    assert "wholesale" in effective_tags
    assert "vip" in effective_tags
    assert "special_order" in effective_tags

    # Verify channels & masked tokens
    assert created_agent["whatsapp_phone_number_id"] == "10992384723"
    assert created_agent["whatsapp_access_token_set"] is True
    assert "EAAB••••••••5678" in created_agent["whatsapp_token_masked"]
    assert "EAABsecretwa12345678" not in created_agent.values()
    assert created_agent["telegram_username"] == "@vip_concierge_bot"
    assert created_agent["telegram_bot_token_set"] is True
    assert "7123••••••••en99" in created_agent["telegram_bot_token_masked"]
    assert created_agent["widget_enabled"] is True

    # 4. Update agent: toggle widget off and update model without losing token
    update_res = await client.put(f"/api/v1/agents/{agent_id}", json={
        "widget_enabled": False,
        "model_name": "gpt-4o-mini",
    }, headers=headers)
    assert update_res.status_code == 200
    updated_agent = update_res.json()
    assert updated_agent["widget_enabled"] is False
    assert updated_agent["model_name"] == "gpt-4o-mini"
    assert updated_agent["whatsapp_access_token_set"] is True
    assert updated_agent["telegram_bot_token_set"] is True

    # 5. Test sandbox run endpoint
    test_run_res = await client.post(f"/api/v1/agents/{agent_id}/test-run", json={
        "message": "Hello VIP bot!",
    }, headers=headers)
    assert test_run_res.status_code == 200
    assert "reply" in test_run_res.json()


@pytest.mark.asyncio
async def test_access_tag_filtering_on_catalog_and_rag(db_session: AsyncSession):
    # Seed Products: 1 Public (empty tags), 1 VIP tagged, 1 Wholesale tagged
    prod1 = CatalogItem(
        title="Standard Sneaker",
        price=15000.0,
        currency="NGN",
        access_tags_json="[]", # Public to all
    )
    prod2 = CatalogItem(
        title="VIP Diamond Watch",
        price=500000.0,
        currency="NGN",
        access_tags_json=json.dumps(["vip", "luxury"]),
    )
    prod3 = CatalogItem(
        title="Wholesale 50-Pack T-Shirts",
        price=120000.0,
        currency="NGN",
        access_tags_json=json.dumps(["wholesale"]),
    )
    db_session.add_all([prod1, prod2, prod3])

    # Seed Knowledge Docs: 1 Public policy, 1 VIP perk guide
    doc1 = KnowledgeDoc(
        title="General Shipping Policy",
        content="Standard shipping takes 3-5 business days across Nigeria.",
        access_tags_json="[]", # Public
    )
    doc2 = KnowledgeDoc(
        title="VIP Concierge Perks",
        content="VIP members receive dedicated account manager and free 24-hour priority dispatch.",
        access_tags_json=json.dumps(["vip"]),
    )
    db_session.add_all([doc1, doc2])
    await db_session.commit()

    # Case A: Standard agent with no tags (only sees public products and docs)
    public_products = await CatalogManager.search_products(db_session, query="watch sneaker pack", allowed_access_tags=set())
    assert len(public_products) == 1
    assert public_products[0].title == "Standard Sneaker"

    public_rag = await RAGEngine.retrieve_relevant_context(db_session, query="shipping perks", allowed_access_tags=set())
    assert "General Shipping Policy" in public_rag
    assert "VIP Concierge Perks" not in public_rag

    # Case B: VIP Agent with {"vip"} tag
    vip_tags = {"vip"}
    vip_products = await CatalogManager.search_products(db_session, query="watch sneaker pack", allowed_access_tags=vip_tags)
    assert len(vip_products) == 2
    titles = [p.title for p in vip_products]
    assert "Standard Sneaker" in titles
    assert "VIP Diamond Watch" in titles
    assert "Wholesale 50-Pack T-Shirts" not in titles

    vip_rag = await RAGEngine.retrieve_relevant_context(db_session, query="shipping perks", allowed_access_tags=vip_tags)
    assert "General Shipping Policy" in vip_rag
    assert "VIP Concierge Perks" in vip_rag


@pytest.mark.asyncio
async def test_customers_directory_and_overview(client: AsyncClient, db_session: AsyncSession):
    # Initialize
    setup_res = await client.post("/api/v1/setup/initialize", json={
        "admin_name": "Admin",
        "admin_email": "admin3@example.com",
        "admin_password": "Password12345!",
        "business_name": "Apex Store",
    })
    token = setup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add customer and order
    cust = Customer(
        name="Chidi Obi",
        phone_number="+2348099887766",
        email="chidi@example.com",
        wa_id="2348099887766",
        total_orders=1,
        total_spent=35000.0,
    )
    db_session.add(cust)

    order = Order(
        order_reference="ORD-TEST99",
        customer_identifier="2348099887766",
        customer_name="Chidi Obi",
        customer_email="chidi@example.com",
        total_amount=35000.0,
        currency="NGN",
        channel="whatsapp",
        status="paid",
    )
    db_session.add(order)
    await db_session.commit()

    # 1. Test Customers List
    cust_res = await client.get("/api/v1/customers", headers=headers)
    assert cust_res.status_code == 200
    cust_data = cust_res.json()
    assert cust_data["total"] >= 1
    assert cust_data["items"][0]["name"] == "Chidi Obi"
    assert "whatsapp" in cust_data["items"][0]["channels"]

    # 2. Test Customer Details
    cust_id = cust.id
    detail_res = await client.get(f"/api/v1/customers/{cust_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["customer"]["email"] == "chidi@example.com"
    assert len(detail_res.json()["orders"]) >= 1

    # 3. Test Overview Metrics
    ov_res = await client.get("/api/v1/overview", headers=headers)
    assert ov_res.status_code == 200
    ov_data = ov_res.json()
    assert ov_data["business"]["name"] == "Apex Store"
    assert ov_data["stats"]["total_customers"] >= 1
    assert ov_data["stats"]["total_orders"] >= 1
    assert ov_data["stats"]["total_revenue"] >= 35000.0


@pytest.mark.asyncio
async def test_admin_spa_static_and_fallback_routes(client: AsyncClient):
    # 1. Root /_/admin should serve index.html
    res = await client.get("/_/admin")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "CommB Admin" in res.text

    # 2. Static CSS file
    res_css = await client.get("/_/admin/style.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.headers.get("content-type", "")

    # 3. Static JS file
    res_js = await client.get("/_/admin/js/main.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.headers.get("content-type", "")

    # 4. SPA deep link fallback (e.g. /_/admin/setup, /_/admin/agents)
    res_deep = await client.get("/_/admin/agents")
    assert res_deep.status_code == 200
    assert "text/html" in res_deep.headers.get("content-type", "")
    assert "CommB Admin" in res_deep.text


@pytest.mark.asyncio
async def test_operator_rbac_permissions(client: AsyncClient):
    # Setup instance
    await client.post("/api/v1/setup/initialize", json={
        "admin_name": "Super Admin",
        "admin_email": "admin@example.com",
        "admin_password": "SuperSecretPassword123!",
        "business_name": "Apex Retail NG",
        "currency": "NGN",
    })
    
    # Login as admin to create operator
    login_admin = await client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "SuperSecretPassword123!",
    })
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create operator user
    create_op_res = await client.post("/api/v1/users", headers=admin_headers, json={
        "name": "Operator Sam",
        "email": "sam@example.com",
        "password": "OperatorSamSecret123!",
        "role": "operator",
    })
    assert create_op_res.status_code in [200, 201]

    # Login as operator
    login_op = await client.post("/api/v1/auth/login", json={
        "email": "sam@example.com",
        "password": "OperatorSamSecret123!",
    })
    assert login_op.status_code == 200
    op_token = login_op.json()["access_token"]
    op_headers = {"Authorization": f"Bearer {op_token}"}

    # 1. Operator CAN read catalog without error
    res_cat = await client.get("/api/v1/admin/catalog", headers=op_headers)
    assert res_cat.status_code == 200

    # 2. Operator CAN read storage settings (safe masked) without error
    res_storage = await client.get("/api/v1/settings/storage", headers=op_headers)
    assert res_storage.status_code == 200

    # 3. Operator CANNOT create or delete products (Admin only -> 403 Forbidden)
    res_create_prod = await client.post("/api/v1/admin/catalog", headers=op_headers, json={
        "title": "Unauthorized Product",
        "price": 1000,
    })
    assert res_create_prod.status_code == 403


@pytest.mark.asyncio
async def test_access_groups_llm_keys_multi_agent_and_product_scoping(client: AsyncClient, db_session: AsyncSession):
    # 1. Setup instance
    setup_res = await client.post("/api/v1/setup/initialize", json={
        "admin_name": "Multi Group Admin",
        "admin_email": "admin_multigroup@example.com",
        "admin_password": "MultiGroupPassword123!",
        "business_name": "Omni Brand Store",
    })
    token = setup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Access Groups with LLM keys (no tags required)
    grp1_res = await client.post("/api/v1/access-groups", headers=headers, json={
        "name": "Enterprise Sales Group",
        "description": "Handles B2B enterprise tier sales",
        "llm_provider": "openai",
        "api_key": "sk-proj-enterprise-secret-key-123456",
        "model_name": "gpt-4o",
    })
    assert grp1_res.status_code == 201
    grp1 = grp1_res.json()
    assert grp1["llm_provider"] == "openai"
    assert grp1["has_api_key"] is True
    assert "••••" in grp1["api_key_masked"]

    grp2_res = await client.post("/api/v1/access-groups", headers=headers, json={
        "name": "Support & Retention Group",
        "description": "Handles customer complaints and tickets",
        "llm_provider": "gemini",
        "api_key": "AIzaSy-gemini-support-key-7890",
        "model_name": "gemini-2.5-flash",
    })
    assert grp2_res.status_code == 201
    grp2 = grp2_res.json()

    # 3. Create Agent with MULTIPLE access groups [grp1, grp2] and custom api_key override
    agent_res = await client.post("/api/v1/agents", headers=headers, json={
        "name": "Hybrid Omni Agent",
        "slug": "hybrid-omni",
        "system_prompt": "You are an omnichannel AI assistant with enterprise and support permissions.",
        "llm_provider": "openai",
        "model_name": "gpt-4o",
        "api_key": "sk-proj-agent-custom-override-key-999",
        "group_ids": [grp1["id"], grp2["id"]],
    })
    assert agent_res.status_code == 201
    agent_data = agent_res.json()
    assert agent_data["group_ids"] == [grp1["id"], grp2["id"]]
    assert agent_data["api_key_configured"] is True
    assert "••••" in agent_data["api_key_masked"]

    # 4. Create Products with access group multi-select and global access
    # Product A: Global (empty access_group_ids)
    prod_global_res = await client.post("/api/v1/admin/catalog", headers=headers, json={
        "title": "Global Basic T-Shirt",
        "price": 5000,
        "access_group_ids": [],
    })
    assert prod_global_res.status_code == 201
    prod_global = prod_global_res.json()
    assert prod_global["is_global"] is True

    # Product B: Scoped to Enterprise Sales Group [grp1["id"]]
    prod_b2b_res = await client.post("/api/v1/admin/catalog", headers=headers, json={
        "title": "Enterprise Server Rack",
        "price": 500000,
        "access_group_ids": [grp1["id"]],
    })
    assert prod_b2b_res.status_code == 201
    prod_b2b = prod_b2b_res.json()
    assert prod_b2b["access_group_ids"] == [grp1["id"]]
    assert prod_b2b["is_global"] is False

    # 5. Verify catalog listing returns serialized access group data
    cat_list = await client.get("/api/v1/admin/catalog", headers=headers)
    assert cat_list.status_code == 200
    items = cat_list.json()["items"]
    assert len(items) >= 2

    # 6. Knowledge base documents scope by access group the same way
    kb_scoped = await client.post("/api/v1/admin/knowledge", headers=headers, json={
        "title": "Enterprise SLA Terms",
        "content": "Enterprise customers get a 4-hour response SLA.",
        "access_group_ids": [grp1["id"]],
    })
    assert kb_scoped.status_code == 201
    assert kb_scoped.json()["access_group_ids"] == [grp1["id"]]

    kb_public = await client.post("/api/v1/admin/knowledge", headers=headers, json={
        "title": "General Returns Policy",
        "content": "Return any item within 14 days.",
        "access_group_ids": [],
    })
    assert kb_public.status_code == 201
    assert kb_public.json()["access_group_ids"] == []

    kb_list = await client.get("/api/v1/admin/knowledge", headers=headers)
    by_title = {d["title"]: d for d in kb_list.json()["items"]}
    assert by_title["Enterprise SLA Terms"]["access_group_ids"] == [grp1["id"]]
    # The mirrored group id must not leak into the free-tag list shown in the UI.
    assert by_title["Enterprise SLA Terms"]["access_tags"] == []


@pytest.mark.asyncio
async def test_conversations_filter_by_channel_agent_and_search(client: AsyncClient, db_session: AsyncSession):
    # Setup business
    setup_res = await client.post("/api/v1/setup/initialize", json={
        "admin_name": "Conv Admin",
        "admin_email": "convadmin@example.com",
        "admin_password": "SuperSecretPassword123!",
        "business_name": "Conv Testing Corp",
    })
    token = setup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create Agent 1 (Sales) and Agent 2 (Support)
    ag1_res = await client.post("/api/v1/agents", headers=headers, json={
        "name": "Sales Bot",
        "slug": "sales-bot",
        "system_prompt": "You are a sales assistant.",
    })
    assert ag1_res.status_code == 201
    ag1_id = ag1_res.json()["id"]

    ag2_res = await client.post("/api/v1/agents", headers=headers, json={
        "name": "Support Bot",
        "slug": "support-bot",
        "system_prompt": "You are a support assistant.",
    })
    assert ag2_res.status_code == 201
    ag2_id = ag2_res.json()["id"]

    # Create Customers
    c1 = Customer(
        wa_id="+2348011111111",
        phone_number="+2348011111111",
        name="John Doe",
        email="john@doe.ng",
    )
    c2 = Customer(
        telegram_id="alice_tg",
        phone_number="+2348022222222",
        name="Alice Smith",
        email="alice@smith.ng",
    )
    db_session.add_all([c1, c2])
    await db_session.commit()

    # Create Sessions
    from app.models.session import ConversationSession, MessageLog
    s1 = ConversationSession(
        session_key="whatsapp:+2348011111111",
        channel="whatsapp",
        customer_identifier="+2348011111111",
        agent_id=ag1_id,
    )
    s2 = ConversationSession(
        session_key="telegram:alice_tg",
        channel="telegram",
        customer_identifier="alice_tg",
        agent_id=ag2_id,
    )
    s3 = ConversationSession(
        session_key="widget:anon_widget_user_99",
        channel="widget",
        customer_identifier="anon_widget_user_99",
        agent_id=ag1_id,
    )
    db_session.add_all([s1, s2, s3])
    await db_session.commit()
    await db_session.refresh(s1)
    await db_session.refresh(s2)
    await db_session.refresh(s3)

    # Add a message to s1
    msg1 = MessageLog(session_id=s1.id, role="user", content="Hi I want to buy")
    msg2 = MessageLog(session_id=s1.id, role="assistant", content="Sure, here is our menu")
    db_session.add_all([msg1, msg2])
    await db_session.commit()

    # 1. Test All Conversations
    all_res = await client.get("/api/v1/conversations", headers=headers)
    assert all_res.status_code == 200
    assert len(all_res.json()["items"]) == 3

    # 2. Test Channel Filter
    wa_res = await client.get("/api/v1/conversations?channel=whatsapp", headers=headers)
    assert wa_res.status_code == 200
    assert len(wa_res.json()["items"]) == 1
    assert wa_res.json()["items"][0]["channel"] == "whatsapp"

    tg_res = await client.get("/api/v1/conversations?channel=telegram", headers=headers)
    assert tg_res.status_code == 200
    assert len(tg_res.json()["items"]) == 1
    assert tg_res.json()["items"][0]["channel"] == "telegram"

    # 3. Test Agent ID Filter
    ag1_filter_res = await client.get(f"/api/v1/conversations?agent_id={ag1_id}", headers=headers)
    assert ag1_filter_res.status_code == 200
    ag1_items = ag1_filter_res.json()["items"]
    assert len(ag1_items) == 2
    assert all(item["agent_id"] == ag1_id for item in ag1_items)

    ag2_filter_res = await client.get(f"/api/v1/conversations?agent_id={ag2_id}", headers=headers)
    assert ag2_filter_res.status_code == 200
    assert len(ag2_filter_res.json()["items"]) == 1
    assert ag2_filter_res.json()["items"][0]["agent"]["name"] == "Support Bot"

    # 4. Test Search Filters (Customer Name, Phone, Email, Identifier)
    name_search = await client.get("/api/v1/conversations?search=John", headers=headers)
    assert name_search.status_code == 200
    assert len(name_search.json()["items"]) == 1
    assert name_search.json()["items"][0]["customer"]["name"] == "John Doe"

    email_search = await client.get("/api/v1/conversations?search=alice@smith.ng", headers=headers)
    assert email_search.status_code == 200
    assert len(email_search.json()["items"]) == 1
    assert email_search.json()["items"][0]["customer"]["email"] == "alice@smith.ng"

    ident_search = await client.get("/api/v1/conversations?search=anon_widget_user", headers=headers)
    assert ident_search.status_code == 200
    assert len(ident_search.json()["items"]) == 1
    assert ident_search.json()["items"][0]["customer_identifier"] == "anon_widget_user_99"

    # 5. Test Thread Detail returns agent metadata and messages
    thread_res = await client.get(f"/api/v1/conversations/{s1.id}", headers=headers)
    assert thread_res.status_code == 200
    thread_data = thread_res.json()
    assert thread_data["agent"]["name"] == "Sales Bot"
    assert len(thread_data["messages"]) == 2



