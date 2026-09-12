import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.models.release import ReleaseNote
from app.models.business import BusinessProfile
from app.cloud_sync.sync_worker import perform_remote_sync, get_support_config

router = APIRouter(prefix="/system", tags=["System & Releases"])


class ReleaseNoteResponse(BaseModel):
    id: Optional[int] = None
    version: str
    title: str
    description: Optional[str] = None
    changelog: List[str] = []
    release_date: Optional[str] = None
    is_critical: bool = False
    download_url: Optional[str] = None


class SystemVersionResponse(BaseModel):
    name: str
    version: str
    environment: str
    # None on a self-hosted instance with no telemetry collector configured.
    telemetry_host: Optional[str] = None
    support: Optional[Dict[str, Any]] = None


@router.get("/version", response_model=SystemVersionResponse)
async def get_system_version():
    """Retrieve the current running application version, instance info, and support configuration."""
    return SystemVersionResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        telemetry_host=settings.COMMB_TELEMETRY_HOST,
        support=get_support_config(),
    )


@router.get("/support")
async def get_system_support_info():
    """Retrieve the latest community support and donation settings."""
    return get_support_config()


@router.get("/releases", response_model=List[ReleaseNoteResponse])
async def list_release_notes(db: AsyncSession = Depends(get_db)):
    """Retrieve all synchronized release notes and changelogs."""
    stmt = select(ReleaseNote).order_by(desc(ReleaseNote.id))
    result = await db.scalars(stmt)
    records = result.all()

    if not records:
        # Provide current version fallback if no releases have been synced yet
        return [
            ReleaseNoteResponse(
                id=1,
                version=settings.APP_VERSION,
                title="CommB Stable Operations",
                description="Core AI Commerce and Operations Platform with Multi-Agent Studio, Access Groups, and Communication Channels.",
                changelog=[
                    "Multi-Agent Studio with custom Access Groups and LLM Provider overrides",
                    "Dynamic Communication Channels (WhatsApp, Telegram, Live Widget)",
                    "Granular payment and storage runtime configuration",
                    "the telemetry collector telemetry and real-time release notes synchronization",
                ],
                release_date="2026-09-05",
                is_critical=False,
            )
        ]

    response_list: List[ReleaseNoteResponse] = []
    for r in records:
        try:
            cl = json.loads(r.changelog_json) if r.changelog_json else []
            if not isinstance(cl, list):
                cl = [str(cl)]
        except Exception:
            cl = []

        response_list.append(
            ReleaseNoteResponse(
                id=r.id,
                version=r.version,
                title=r.title,
                description=r.description,
                changelog=cl,
                release_date=r.release_date,
                is_critical=r.is_critical or False,
                download_url=r.download_url,
            )
        )

    return response_list


@router.post("/releases/sync")
async def sync_system_releases(db: AsyncSession = Depends(get_db)):
    """Trigger a manual synchronization of release notes from the telemetry collector."""
    sync_result = await perform_remote_sync(db)
    releases = await list_release_notes(db)
    return {
        "status": "success",
        "sync_summary": sync_result,
        "releases": releases,
    }


@router.get("/health-summary")
async def get_health_summary(db: AsyncSession = Depends(get_db)):
    """Detailed health check and subsystem status for the public health dashboard."""
    import time
    start_time = time.time()

    # DB ping
    db_ok = True
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_latency_ms = round((time.time() - start_time) * 1000, 2)
    except Exception:
        db_ok = False
        db_latency_ms = -1

    db_type = "PostgreSQL" if "postgres" in settings.DATABASE_URL.lower() else "SQLite"

    # LLM Model Name
    if settings.LLM_PROVIDER == "openai":
        active_model = settings.OPENAI_MODEL
    elif settings.LLM_PROVIDER == "claude":
        active_model = settings.ANTHROPIC_MODEL
    else:
        active_model = settings.GEMINI_MODEL

    biz_res = await db.execute(select(BusinessProfile).limit(1))
    biz = biz_res.scalar_one_or_none()

    return {
        "status": "operational" if db_ok else "degraded",
        "app_name": biz.name if biz else "CommB (AI Commerce Bots)",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "instance_id": settings.INSTANCE_ID,
        "business": {
            "name": biz.name if biz else "CommB Business",
            "logo_url": biz.logo_url if biz else None,
            "currency": biz.currency if biz else "NGN",
        } if biz else None,
        "database": {
            "status": "operational" if db_ok else "disconnected",
            "type": db_type,
            "latency_ms": db_latency_ms,
        },
        "llm": {
            "status": "operational",
            "provider": settings.LLM_PROVIDER.upper(),
            "model": active_model,
        },
        "channels": [
            {
                "name": "WhatsApp Cloud API",
                "status": "configured" if settings.META_WHATSAPP_TOKEN else "unconfigured",
                "enabled": bool(settings.META_WHATSAPP_TOKEN),
            },
            {
                "name": "Telegram Bot API",
                "status": "configured" if settings.TELEGRAM_BOT_TOKEN else "unconfigured",
                "enabled": bool(settings.TELEGRAM_BOT_TOKEN),
            },
            {
                "name": "Website Chat Widget",
                "status": "operational",
                "enabled": True,
            },
        ],
        "commerce": {
            "status": "operational",
            "provider": settings.DEFAULT_PAYMENT_GATEWAY.capitalize(),
            "currency": biz.currency if (biz and biz.currency) else "NGN",
        },
        "docs_url": "https://commb.app/docs",
        "github_url": "https://github.com/sannex-01/commb",
    }


@router.get("/debug-info")
async def get_debug_info():
    """Returns structured system debug information for one-click copy in About modal."""
    import sys
    import platform

    return {
        "commb_version": settings.APP_VERSION,
        "instance_id": settings.INSTANCE_ID,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "environment": settings.ENVIRONMENT,
        "database_type": "PostgreSQL" if "postgres" in settings.DATABASE_URL.lower() else "SQLite",
        "llm_provider": settings.LLM_PROVIDER,
        "bot_mode": settings.BOT_MODE,
        "posthog_enabled": bool(settings.POSTHOG_API_KEY),
        "telemetry_sync_enabled": bool(settings.COMMB_TELEMETRY_KEY),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

