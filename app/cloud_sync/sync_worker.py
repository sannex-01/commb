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
from app.updates.client import fetch_public_updates, get_support_config
from app.updates import client as _updates

# Optional CommB Cloud SDK — see app/cloud_sync/client.py. Absent on a plain
# self-hosted install, where only the keyless public update check runs.
try:  # pragma: no cover - depends on optional extra being installed
    from commb_agent import AsyncCommBClient
except ImportError:  # pragma: no cover
    AsyncCommBClient = None

router = APIRouter(prefix="/sync", tags=["Updates & Cloud Sync"])
scheduler = AsyncIOScheduler()

# The sponsor banner is owned by app.updates (it arrives over the keyless public
# fetch). Re-exported here so existing importers keep working.
__all__ = ["router", "perform_remote_sync", "get_support_config",
           "start_sync_scheduler", "shutdown_sync_scheduler", "scheduler"]


async def _upsert_releases(db: AsyncSession, releases: List[Any]) -> int:
    """Write release notes into the local DB. Accepts SDK objects or plain dicts.

    Release payloads arrive from a public endpoint, so every field is treated as
    untrusted input: anything without a version is skipped.
    """
    synced_count = 0
    for r in releases:
        get = (lambda k: r.get(k)) if isinstance(r, dict) else (lambda k: getattr(r, k, None))

        version = get("version")
        if not version:
            continue

        changelog = get("changelog")
        changelog_str = json.dumps(changelog) if isinstance(changelog, list) else str(changelog or "[]")
        title = get("title") or f"Version {version}"

        existing = await db.scalar(select(ReleaseNote).where(ReleaseNote.version == version))
        if existing:
            existing.title = title
            existing.description = get("description")
            existing.changelog_json = changelog_str
            existing.release_date = get("release_date")
            existing.is_critical = bool(get("is_critical"))
            existing.download_url = get("download_url")
        else:
            db.add(
                ReleaseNote(
                    version=version,
                    title=title,
                    description=get("description"),
                    changelog_json=changelog_str,
                    release_date=get("release_date"),
                    is_critical=bool(get("is_critical")),
                    download_url=get("download_url"),
                )
            )
        synced_count += 1

    if synced_count:
        await db.commit()
    return synced_count


async def perform_remote_sync(db: AsyncSession) -> Dict[str, Any]:
    """Run the periodic sync.

    Three independent concerns, deliberately not gated behind one another:

    1. Release notes + sponsor banner -- a keyless PUBLIC fetch, so every
       install (self-hosted included) gets update and security notices.
    2. External catalog sync (Paystack/Bumpa) -- local, runs whenever configured.
    3. CommB Cloud connectivity check -- only when a cloud key is set; this is
       the sole step that requires the optional SDK and exports personal data.
    """
    logger.info("Executing CommB synchronization...")
    summary: Dict[str, Any] = {
        "status": "success",
        "collector_connected": False,
        "releases_synced": 0,
        "catalog_items_synced": 0,
        "update_check": False,
    }

    # 1. Public update check -- no key, no SDK, no personal data.
    try:
        updates = await fetch_public_updates(app_version=settings.APP_VERSION)
        summary["update_check"] = updates.get("connected", False)
        if updates.get("support"):
            _updates._cached_support_config = updates["support"]
        if updates.get("releases"):
            summary["releases_synced"] = await _upsert_releases(db, updates["releases"])
            logger.info(f"Synced {summary['releases_synced']} release note(s) from the public endpoint.")
    except Exception as e:
        # An update check must never break the rest of the sync.
        logger.warning(f"Public update check failed: {e}")

    # 2. CommB Cloud connectivity -- opt-in, exports personal data. Skipped
    #    entirely without a key, which is the normal self-hosted case.
    if settings.cloud_key and AsyncCommBClient is not None:
        client_kwargs: Dict[str, Any] = {"api_key": settings.cloud_key}
        if settings.cloud_host:
            client_kwargs["host"] = settings.cloud_host
        try:
            async with AsyncCommBClient(**client_kwargs) as client:
                config_resp = await client.get_config()
                summary["collector_connected"] = True
                logger.info("CommB Cloud connection verified successfully.")

                # A workspace may override the sponsor banner for its instances.
                if config_resp and isinstance(getattr(config_resp, "support", None), dict):
                    _updates._cached_support_config = config_resp.support

                # Fall back to cloud-provided releases only if the public
                # endpoint returned none (e.g. an air-gapped private mirror).
                if not summary["releases_synced"]:
                    releases = await client.get_releases(app_version=settings.APP_VERSION)
                    if not releases and config_resp:
                        releases = getattr(config_resp, "releases", None)
                    if releases:
                        summary["releases_synced"] = await _upsert_releases(db, releases)
        except Exception as e:
            logger.error(f"Error during CommB Cloud sync check: {e}")
            summary["status"] = "error"
            summary["error"] = str(e)
    elif settings.cloud_key and AsyncCommBClient is None:
        logger.info(
            "COMMB_CLOUD_KEY is set but the optional SDK is not installed "
            "(`pip install commb[cloud]`). Skipping cloud sync."
        )

    # 3. Paystack/Bumpa external catalog sync if configured.
    summary["catalog_items_synced"] = await CatalogManager.sync_external_catalog(db)

    return summary


@router.post("")
async def trigger_manual_sync(db: AsyncSession = Depends(get_db)):
    """Manual sync trigger (e.g. from the CommB Cloud dashboard or admin API)."""
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
