import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import init_db, get_db
from app.core.logger import logger
from app.core.rate_limit import limiter
from app.core.security import verify_dashboard_auth, get_current_admin_user
from app.commerce.storage.manager import StorageManager
from app.channels.whatsapp.webhook import router as whatsapp_router
from app.channels.telegram.webhook import router as telegram_router
from app.channels.widget.endpoints import router as widget_router
from app.commerce.payments.webhooks import router as payments_router
from app.commerce.bumpa.webhook import router as bumpa_router
from app.commerce.catalog_upload import router as catalog_upload_router
from app.cloud_sync.client import cloud_client
from app.cloud_sync.sync_worker import router as sync_router, start_sync_scheduler, shutdown_sync_scheduler
from typing import Optional
from app.models.catalog import CatalogItem
from app.models.agent import Agent
from app.core.access import get_effective_agent_tags, filter_items_by_access_tags

from app.api.setup import router as setup_router
from app.api.auth import router as auth_router
from app.api.sso import router as sso_router
from app.api.users import router as users_router
from app.api.settings import router as settings_router
from app.api.access_groups import router as access_groups_router
from app.api.agents import router as agents_router
from app.api.customers import router as customers_router
from app.api.overview import router as overview_router
from app.api.catalog import router as admin_catalog_router
from app.api.knowledge import router as admin_knowledge_router
from app.api.conversations import router as conversations_router
from app.api.system import router as system_router
from app.api.reports import router as reports_router
from app.api.orders import router as orders_router

WIDGET_BUNDLE_PATH = os.path.join(os.path.dirname(__file__), "..", "widget", "dist", "widget.js")
ADMIN_DIST_DIR = os.path.join(os.path.dirname(__file__), "admin_ui", "dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Database Schema
    await init_db()

    # 2. Start Background 30m Sync Scheduler
    start_sync_scheduler()

    logger.info(f"CommB Assistant is active and ready (Mode: {settings.BOT_MODE.upper()})")

    yield

    # Shutdown hooks
    shutdown_sync_scheduler()
    cloud_client.close()
    logger.info(f"CommB Assistant shut down gracefully.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Modular Plug-and-Play AI & Interactive Chatbot Engine for WhatsApp, Telegram, Payments & Commerce",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root & Health Endpoints
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "mode": settings.BOT_MODE,
        "llm_provider": settings.LLM_PROVIDER,
        "catalog_source": settings.CATALOG_SOURCE,
    }


@app.get("/", tags=["Health"])
async def root(request: Request):
    """Serves the interactive System Health Status page or JSON API summary."""
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header or "*/*" in accept_header:
        health_file = os.path.join(ADMIN_DIST_DIR, "health.html")
        if os.path.isfile(health_file):
            return FileResponse(health_file, media_type="text/html")

    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs_url": "https://commb.app/docs",
        "health": "/health",
        "admin_url": "/_/admin",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Returns empty 204 No Content for favicon requests if no icon file exists."""
    icon_path = os.path.join(ADMIN_DIST_DIR, "favicon.ico")
    if os.path.isfile(icon_path):
        return FileResponse(icon_path)
    return Response(status_code=204)



def _mask_key(key: str | None) -> str | None:
    """Returns a masked preview of a secret key: first 12 chars + ... + last 4 chars."""
    if not key:
        return None
    if len(key) <= 16:
        return key[:4] + "..." + key[-2:]
    return key[:12] + "..." + key[-4:]


@app.get("/api/v1/gateway-info", tags=["Gateway"])
async def gateway_info(
    agent_id: Optional[str] = None,
    agent_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_dashboard_auth),
):
    """Returns masked key previews, active gateway configuration, and optional agent details for AgentOS."""
    agent_data = None
    if agent_id or agent_slug:
        stmt = select(Agent)
        if agent_id:
            stmt = stmt.where(Agent.id == agent_id)
        else:
            stmt = stmt.where(Agent.slug == agent_slug)
        res = await db.execute(stmt)
        ag = res.scalars().first()
        if ag:
            agent_data = {
                "id": ag.id,
                "name": ag.name,
                "slug": ag.slug,
                "is_active": ag.is_active,
                "model_name": ag.model_name,
                "whatsapp_phone_number_id": ag.whatsapp_phone_number_id,
                "telegram_username": ag.telegram_username,
                "widget_enabled": ag.widget_enabled,
                "access_tags": ag.access_tags,
            }

    agents_res = await db.execute(select(Agent))
    agents_list = agents_res.scalars().all()

    return {
        "active_gateway": settings.DEFAULT_PAYMENT_GATEWAY,
        "bot_domain": settings.BOT_DOMAIN,
        "agents_count": len(agents_list),
        "agent": agent_data,
        "paystack": {
            "configured": bool(settings.PAYSTACK_SECRET_KEY),
            "secret_key_preview": _mask_key(settings.PAYSTACK_SECRET_KEY),
            "public_key_preview": _mask_key(settings.PAYSTACK_PUBLIC_KEY),
        },
        "flutterwave": {
            "configured": bool(settings.FLUTTERWAVE_SECRET_KEY),
            "secret_key_preview": _mask_key(settings.FLUTTERWAVE_SECRET_KEY),
            "public_key_preview": _mask_key(settings.FLUTTERWAVE_PUBLIC_KEY),
        },
        "monnify": {
            "configured": bool(settings.MONNIFY_API_KEY),
            "api_key_preview": _mask_key(settings.MONNIFY_API_KEY),
        },
        "stripe": {
            "configured": bool(settings.STRIPE_SECRET_KEY),
            "secret_key_preview": _mask_key(settings.STRIPE_SECRET_KEY),
        },
        "storage": {
            "provider": settings.STORAGE_PROVIDER,
            "configured": StorageManager.is_configured(),
            "cloudinary": {
                "configured": bool(settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_CLOUD_NAME),
                "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
                "api_key_preview": _mask_key(settings.CLOUDINARY_API_KEY),
                "folder": settings.CLOUDINARY_FOLDER,
            },
            "cloudflare_r2": {
                "configured": bool(settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID),
                "account_id": settings.R2_ACCOUNT_ID,
                "bucket_name": settings.R2_BUCKET_NAME,
                "access_key_preview": _mask_key(settings.R2_ACCESS_KEY_ID),
                "public_url": settings.R2_PUBLIC_URL,
            },
        },
    }


# Include Routers under /api/v1
app.include_router(whatsapp_router, prefix="/api/v1")
app.include_router(telegram_router, prefix="/api/v1")
app.include_router(widget_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(bumpa_router, prefix="/api/v1")
app.include_router(catalog_upload_router, prefix="/api/v1")
app.include_router(sync_router, prefix="/api/v1")

# Standalone Admin & Multi-Agent Routers
app.include_router(setup_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(sso_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(access_groups_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(customers_router, prefix="/api/v1")
app.include_router(overview_router, prefix="/api/v1")
app.include_router(admin_catalog_router, prefix="/api/v1")
app.include_router(admin_knowledge_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")



@app.get("/widget.js", tags=["Website Widget"])
async def widget_bundle():
    """Serves the embeddable widget script. Businesses install it via
    <script src="{instanceUrl}/widget.js" data-bot-id="..."></script>."""
    if not os.path.isfile(WIDGET_BUNDLE_PATH):
        raise HTTPException(status_code=404, detail="Widget bundle not built for this instance yet.")
    return FileResponse(WIDGET_BUNDLE_PATH, media_type="application/javascript")


# Dashboard-Facing Endpoints (Admin JWT or API Key)
@app.get("/api/v1/catalog", tags=["Catalog"])
async def list_catalog_items(
    agent_id: Optional[str] = None,
    agent_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_admin_user),
):
    stmt = select(CatalogItem).limit(50)
    res = await db.execute(stmt)
    items = list(res.scalars().all())

    if agent_id or agent_slug:
        ag_stmt = select(Agent)
        if agent_id:
            ag_stmt = ag_stmt.where(Agent.id == agent_id)
        else:
            ag_stmt = ag_stmt.where(Agent.slug == agent_slug)
        ag_res = await db.execute(ag_stmt)
        agent = ag_res.scalars().first()
        if agent:
            allowed_tags = await get_effective_agent_tags(agent, db)
            items = filter_items_by_access_tags(items, allowed_tags)

    return items


# Standalone Admin Embedded SPA Routes (served at /_/admin)
@app.get("/_/admin/{full_path:path}", tags=["Admin Dashboard"])
@app.get("/_/admin", tags=["Admin Dashboard"])
async def serve_admin_spa(full_path: str = ""):
    """Serves the standalone Admin Single Page Application (SPA) with routing fallback."""
    if full_path:
        candidate = os.path.join(ADMIN_DIST_DIR, full_path)
        if os.path.isfile(candidate):
            media_type = None
            if candidate.endswith(".css"):
                media_type = "text/css"
            elif candidate.endswith(".js"):
                media_type = "application/javascript"
            elif candidate.endswith(".html"):
                media_type = "text/html"
            elif candidate.endswith(".svg"):
                media_type = "image/svg+xml"
            return FileResponse(
                candidate,
                media_type=media_type,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    index_file = os.path.join(ADMIN_DIST_DIR, "index.html")
    if not os.path.isfile(index_file):
        raise HTTPException(status_code=404, detail="Admin UI bundle not found.")
    return FileResponse(
        index_file,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )

