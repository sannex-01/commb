import json
import asyncio
from typing import Dict, Any, Optional, List
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import settings
from app.core.database import get_db, AsyncSessionLocal
from app.core.logger import logger
from app.models.config_override import ConfigOverride
from app.models.catalog import CatalogItem
from app.models.knowledge import KnowledgeDoc
from app.models.agent import Agent
from app.models.release import ReleaseNote
from app.commerce.catalog_provider import CatalogManager

# Optional telemetry SDK — see app/telemetry/client.py. Absent on a plain
# self-hosted install, in which case remote sync degrades to local catalog sync.
try:  # pragma: no cover - depends on optional extra being installed
    from commb_agent import AsyncCommBClient
except ImportError:  # pragma: no cover
    AsyncCommBClient = None

router = APIRouter(prefix="/sync", tags=["Telemetry & Remote Sync"])
scheduler = AsyncIOScheduler()

_cached_support_config: Dict[str, Any] = {
    "enabled": True,
    "url": "https://github.com/sponsors/sannex-01",
    "title": "Support Open-Source CommB",
    "message": "Enjoying CommB? Consider supporting future open-source development and maintenance.",
}


def get_support_config() -> Dict[str, Any]:
    return _cached_support_config


async def perform_remote_sync(db: AsyncSession) -> Dict[str, Any]:
    """Polls the telemetry collector in read-only mode for connectivity health and syncs release notes (only allowable write from the telemetry collector)."""
    global _cached_support_config
    logger.info("Executing CommB remote synchronization...")
    summary: Dict[str, Any] = {
        "status": "success",
        "collector_connected": False,
        "releases_synced": 0,
        "catalog_items_synced": 0,
    }

    if not settings.COMMB_TELEMETRY_KEY or AsyncCommBClient is None:
        if settings.COMMB_TELEMETRY_KEY and AsyncCommBClient is None:
            logger.info(
                "COMMB_TELEMETRY_KEY is set but the optional telemetry SDK is not installed "
                "(`pip install commb[telemetry]`). Running local catalog sync only."
            )
        else:
            logger.info("COMMB_TELEMETRY_KEY not configured. Running local catalog sync only.")
        summary["catalog_items_synced"] = await CatalogManager.sync_external_catalog(db)
        return summary

    client_kwargs: Dict[str, Any] = {"api_key": settings.COMMB_TELEMETRY_KEY}
    if settings.COMMB_TELEMETRY_HOST:
        client_kwargs["host"] = settings.COMMB_TELEMETRY_HOST

    try:
        async with AsyncCommBClient(**client_kwargs) as client:
            config_resp = await client.get_config()
            summary["collector_connected"] = True
            logger.info("the telemetry collector connection verified successfully.")

            # Ingest support config if provided by the telemetry collector
            if config_resp and getattr(config_resp, "support", None):
                if isinstance(config_resp.support, dict):
                    _cached_support_config = config_resp.support

            # Ingest Release Notes (the only allowable write from the telemetry collector to CommB)
            releases = await client.get_releases(app_version=settings.APP_VERSION)
            if not releases and config_resp and getattr(config_resp, "releases", None):
                releases = config_resp.releases

            if releases:
                synced_count = 0
                for r in releases:
                    if not getattr(r, "version", None):
                        continue
                    existing = await db.scalar(select(ReleaseNote).where(ReleaseNote.version == r.version))
                    changelog_str = json.dumps(r.changelog) if isinstance(r.changelog, list) else str(r.changelog or "[]")
                    if existing:
                        existing.title = r.title or f"Version {r.version}"
                        existing.description = r.description
                        existing.changelog_json = changelog_str
                        existing.release_date = r.release_date
                        existing.is_critical = bool(r.is_critical)
                        existing.download_url = r.download_url
                    else:
                        new_rel = ReleaseNote(
                            version=r.version,
                            title=r.title or f"Version {r.version}",
                            description=r.description,
                            changelog_json=changelog_str,
                            release_date=r.release_date,
                            is_critical=bool(r.is_critical),
                            download_url=r.download_url,
                        )
                        db.add(new_rel)
                    synced_count += 1
                await db.commit()
                summary["releases_synced"] = synced_count
                logger.info(f"Successfully synced {synced_count} release note(s) from the telemetry collector.")

    except Exception as e:
        logger.error(f"Error during remote sync check: {e}")
        summary["status"] = "error"
        summary["error"] = str(e)

    # Also run Paystack/Bumpa external catalog sync if configured
    ext_synced = await CatalogManager.sync_external_catalog(db)
    summary["catalog_items_synced"] = ext_synced

    return summary


@router.post("")
async def trigger_manual_sync(db: AsyncSession = Depends(get_db)):
    """Manual sync trigger (e.g. from the telemetry collector dashboard or admin API)."""
    return await perform_remote_sync(db)


async def _scheduled_sync_job():
    """Background wrapper for APScheduler."""
    async with AsyncSessionLocal() as session:
        try:
            await perform_remote_sync(session)
        except Exception as e:
            logger.error(f"Scheduled sync failed: {e}")
        finally:
            await session.close()


def start_sync_scheduler():
    """Starts the periodic background sync job (every 30 minutes by default) and triggers an immediate sync on startup."""
    if settings.SYNC_INTERVAL_HOURS is not None:
        minutes = max(settings.SYNC_INTERVAL_HOURS * 60, 1)
    else:
        minutes = max(settings.SYNC_INTERVAL_MINUTES, 1)

    scheduler.add_job(_scheduled_sync_job, "interval", minutes=minutes, id="remote_sync_job", replace_existing=True)
    if not scheduler.running:
        scheduler.start()
    logger.info(f"Periodic remote sync worker started (Interval: {minutes}m).")

    # Trigger immediate sync in background on container startup so catalogs and prompts are never stale or empty
    asyncio.create_task(_scheduled_sync_job())


def shutdown_sync_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Remote sync worker shut down.")
