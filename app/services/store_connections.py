import json
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import BusinessProfile
from app.core.config import settings
from app.core.logger import logger


def _mask_key(key: Optional[str]) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


# Providers that can supply BOTH a catalog (Store Connections) AND process
# payments (Payment Gateways) get a fallback to the matching legacy env var
# when nothing has been saved to the DB yet — same pattern PaymentService
# already uses for Paystack. Bumpa is the first Store Connection; Paystack
# also lives here even though its "connection" only exists in this table
# once a business actually toggles sharing on, since it's the same
# dual-purpose shape (import catalog + checkout).
#
# "public_key" is a SECOND, separate credential some providers split out
# (Bumpa's confirmed real API: a public key for cart/checkout/catalog
# routes, a secret/"api_key" for merchant order/analytics routes) — only
# declared here for providers that actually need it; absent means the
# provider uses one key for everything.
_ENV_FALLBACKS = {
    "bumpa": {"api_key": "BUMPA_API_KEY", "public_key": "BUMPA_PUBLIC_API_KEY", "store_id": "BUMPA_STORE_ID"},
    "paystack": {"api_key": "PAYSTACK_SECRET_KEY"},
}


class StoreConnectionService:
    """BYO-key settings for external platforms that provide a catalog commb
    can import (Bumpa, Paystack, ...) and — for some of them — can *also*
    process payments/checkout on their own. A business can toggle
    "share_for_payments" per provider so the one credential saved here
    doubles as that provider's Payment Gateway config, instead of pasting
    the same key twice in two different tabs. Toggling it on does NOT make
    that provider the active checkout gateway — a business can still have
    a different gateway selected in Payment Gateways; it only means "if/when
    this provider is used for payments, use this same credential."

    Storage shape: BusinessProfile.metadata_json["store_connections"][provider]
    = {"api_key": ..., "store_id": ..., "share_for_payments": bool, ...}.
    Provider-specific extra fields (e.g. Bumpa's store_id) are just carried
    through in the same dict; generic methods below don't need to know about
    them beyond api_key/share_for_payments."""

    @staticmethod
    async def get_connection_config(db: AsyncSession, provider: str) -> Dict[str, Any]:
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        meta = json.loads(biz.metadata_json or "{}") if biz else {}
        raw_config = meta.get("store_connections", {}).get(provider, {})

        env_fallback = _ENV_FALLBACKS.get(provider, {})
        env_key = getattr(settings, env_fallback.get("api_key", ""), None) if env_fallback.get("api_key") else None
        env_store_id = getattr(settings, env_fallback.get("store_id", ""), None) if env_fallback.get("store_id") else None

        api_key = raw_config.get("api_key") or env_key
        store_id = raw_config.get("store_id") or env_store_id

        result = {
            "configured": bool(api_key),
            "config": {
                "api_key_masked": _mask_key(api_key),
                "api_key_configured": bool(api_key),
                "source": "database" if raw_config.get("api_key") else ("env" if env_key else None),
                "share_for_payments": bool(raw_config.get("share_for_payments")),
            },
        }
        if env_fallback.get("store_id") is not None or "store_id" in raw_config:
            result["config"]["store_id"] = store_id or ""

        if "public_key" in env_fallback or "public_key" in raw_config:
            env_public_key = getattr(settings, env_fallback.get("public_key", ""), None) if env_fallback.get("public_key") else None
            public_key = raw_config.get("public_key") or env_public_key
            result["config"]["public_key_masked"] = _mask_key(public_key)
            result["config"]["public_key_configured"] = bool(public_key)

        return result

    @staticmethod
    async def save_connection_config(db: AsyncSession, provider: str, config: Dict[str, Any]) -> Dict[str, Any]:
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            biz = BusinessProfile()
            db.add(biz)

        meta = json.loads(biz.metadata_json or "{}")
        store_connections = meta.get("store_connections", {})
        existing = store_connections.get(provider, {})

        def _resolve_key(field: str) -> str:
            raw_val = config.get(field)
            if raw_val is None:
                return existing.get(field, "")
            stripped = raw_val.strip()
            return existing.get(field, "") if (stripped.startswith("***") or "..." in stripped) else stripped

        entry = {
            "api_key": _resolve_key("api_key"),
            "share_for_payments": bool(config.get("share_for_payments", existing.get("share_for_payments", False))),
        }
        if "store_id" in config or "store_id" in existing:
            entry["store_id"] = (config.get("store_id") if config.get("store_id") is not None else existing.get("store_id", "")) or ""
            entry["store_id"] = entry["store_id"].strip() if isinstance(entry["store_id"], str) else entry["store_id"]

        env_fallback = _ENV_FALLBACKS.get(provider, {})
        if "public_key" in env_fallback or "public_key" in config or "public_key" in existing:
            entry["public_key"] = _resolve_key("public_key")

        store_connections[provider] = entry
        meta["store_connections"] = store_connections
        biz.metadata_json = json.dumps(meta)
        await db.commit()

        return await StoreConnectionService.get_connection_config(db, provider)

    @staticmethod
    async def get_effective_key(db: AsyncSession, provider: str) -> Optional[str]:
        """The actual key to use for a real API call to this provider — DB
        value takes priority over env."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        meta = json.loads(biz.metadata_json or "{}") if biz else {}
        raw_config = meta.get("store_connections", {}).get(provider, {})
        env_fallback = _ENV_FALLBACKS.get(provider, {})
        env_key = getattr(settings, env_fallback.get("api_key", ""), None) if env_fallback.get("api_key") else None
        return raw_config.get("api_key") or env_key

    @staticmethod
    async def get_effective_public_key(db: AsyncSession, provider: str) -> Optional[str]:
        """The public-key counterpart to get_effective_key, for providers
        that split their credentials (Bumpa). Returns None for providers
        with no public_key concept."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        meta = json.loads(biz.metadata_json or "{}") if biz else {}
        raw_config = meta.get("store_connections", {}).get(provider, {})
        env_fallback = _ENV_FALLBACKS.get(provider, {})
        env_key = getattr(settings, env_fallback.get("public_key", ""), None) if env_fallback.get("public_key") else None
        return raw_config.get("public_key") or env_key

    @staticmethod
    async def get_shared_payment_key(db: AsyncSession, provider: str) -> Optional[str]:
        """Returns this provider's Store Connection API key ONLY if the
        business has explicitly toggled "share_for_payments" on for it —
        used by PaymentService to decide whether to hide that gateway's own
        key fields and point back to Store Connections instead. Works for
        ANY provider that has an entry here (Bumpa, Paystack, or any future
        catalog-and-checkout platform) — not hardcoded to one name."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        meta = json.loads(biz.metadata_json or "{}") if biz else {}
        raw_config = meta.get("store_connections", {}).get(provider, {})
        if not raw_config.get("share_for_payments"):
            return None
        return await StoreConnectionService.get_effective_key(db, provider)

    # --- Bumpa-named wrappers, kept so existing callers (catalog import,
    # settings API routes) don't need to change --------------------------

    @staticmethod
    async def get_bumpa_config(db: AsyncSession) -> Dict[str, Any]:
        return await StoreConnectionService.get_connection_config(db, "bumpa")

    @staticmethod
    async def save_bumpa_config(db: AsyncSession, config: Dict[str, Any]) -> Dict[str, Any]:
        return await StoreConnectionService.save_connection_config(db, "bumpa", config)

    @staticmethod
    async def get_effective_bumpa_key(db: AsyncSession) -> Optional[str]:
        return await StoreConnectionService.get_effective_key(db, "bumpa")
