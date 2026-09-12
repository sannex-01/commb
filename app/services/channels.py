import json
import secrets
from typing import Optional, Dict, Any
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import BusinessProfile
from app.core.config import settings
from app.core.logger import logger


def _mask_secret(val: Optional[str]) -> str:
    if not val:
        return ""
    val = val.strip()
    if len(val) <= 8:
        return "••••••••"
    return f"{val[:4]}••••••••{val[-4:]}"


def generate_webhook_secret() -> str:
    """Generates a Telegram-compliant secret token (A-Z, a-z, 0-9, _, -)."""
    # Using token_hex guarantees only standard alphanumeric characters (no '=' padding)
    return f"whsec_{secrets.token_hex(20)}"


def generate_verify_token() -> str:
    """Generates a random verify token for WhatsApp webhook challenge verification."""
    return f"commb_vt_{secrets.token_hex(16)}"


class ChannelService:
    @staticmethod
    async def get_config(db: AsyncSession) -> Dict[str, Any]:
        """Returns the current messaging channels configuration and webhook URLs."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()

        meta = json.loads(biz.metadata_json or "{}") if biz else {}
        channels_data = meta.get("channels", {})

        domain = (settings.COMMB_DOMAIN or settings.BOT_DOMAIN or "https://commb.app").rstrip("/")

        wa_data = channels_data.get("whatsapp", {})
        wa_verify_token = wa_data.get("verify_token") or settings.META_VERIFY_TOKEN or "commb_webhook_verification_token_secret"
        wa_app_secret = wa_data.get("app_secret") or settings.META_APP_SECRET or ""

        tg_data = channels_data.get("telegram", {})
        tg_secret = tg_data.get("webhook_secret") or settings.TELEGRAM_WEBHOOK_SECRET
        if not tg_secret:
            tg_secret = generate_webhook_secret()
            if biz:
                if "channels" not in meta:
                    meta["channels"] = {}
                meta["channels"]["telegram"] = {"webhook_secret": tg_secret}
                biz.metadata_json = json.dumps(meta)
                await db.commit()

        return {
            "domain": domain,
            "whatsapp": {
                "verify_token": wa_verify_token,
                "app_secret_configured": bool(wa_app_secret),
                "app_secret_masked": _mask_secret(wa_app_secret),
                "webhook_url": f"{domain}/api/v1/webhooks/whatsapp",
            },
            "telegram": {
                "webhook_secret": tg_secret,
                "webhook_secret_configured": bool(tg_secret),
                "webhook_secret_masked": _mask_secret(tg_secret),
                "webhook_url": f"{domain}/api/v1/webhooks/telegram",
            },
        }

    @staticmethod
    async def save_config(db: AsyncSession, config: Dict[str, Any]) -> Dict[str, Any]:
        """Saves messaging channel settings and automatically synchronizes webhooks."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            biz = BusinessProfile()
            db.add(biz)

        meta = json.loads(biz.metadata_json or "{}")
        existing_channels = meta.get("channels", {})
        existing_wa = existing_channels.get("whatsapp", {})
        existing_tg = existing_channels.get("telegram", {})

        new_wa = config.get("whatsapp", {})
        new_tg = config.get("telegram", {})

        # Merge WhatsApp
        wa_app_secret = new_wa.get("app_secret")
        if wa_app_secret is None or wa_app_secret == "":
            wa_app_secret = existing_wa.get("app_secret", "")

        wa_verify_token = (new_wa.get("verify_token") or existing_wa.get("verify_token") or "commb_webhook_verification_token_secret").strip()

        merged_wa = {
            "verify_token": wa_verify_token,
            "app_secret": wa_app_secret.strip() if wa_app_secret else "",
        }

        # Merge Telegram
        tg_secret = new_tg.get("webhook_secret")
        if tg_secret is None or tg_secret == "":
            tg_secret = existing_tg.get("webhook_secret") or generate_webhook_secret()

        merged_tg = {
            "webhook_secret": tg_secret.strip() if tg_secret else "",
        }

        meta["channels"] = {
            "whatsapp": merged_wa,
            "telegram": merged_tg,
        }

        biz.metadata_json = json.dumps(meta)
        await db.commit()
        await db.refresh(biz)

        logger.info("Updated global messaging channels settings.")

        # Auto-sync with Telegram if bot_token was supplied in payload
        bot_token = new_tg.get("bot_token")
        if bot_token:
            await ChannelService.set_telegram_webhook(bot_token=bot_token, db=db, drop_pending_updates=True)

        return await ChannelService.get_config(db)

    @staticmethod
    async def set_telegram_webhook(
        bot_token: str,
        db: AsyncSession,
        drop_pending_updates: bool = False,
        agent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Registers or refreshes the Telegram webhook URL and secret token with Telegram Bot API.

        When agent_id is given the webhook URL is suffixed with /{agent_id} so
        the inbound webhook handler can tell which agent (and which bot token,
        catalog scope, AI config) an update belongs to. Without it, multiple
        agents sharing the one global URL all resolve to the first active agent
        — the cause of "agent 2's messages get answered by agent 1" and inline
        search only ever returning agent 1's products.
        """
        if not bot_token or not bot_token.strip():
            return {"ok": False, "description": "No Telegram bot token provided."}

        token = bot_token.strip()
        cfg = await ChannelService.get_config(db)
        webhook_url = cfg["telegram"]["webhook_url"]
        if agent_id is not None:
            webhook_url = f"{webhook_url.rstrip('/')}/{agent_id}"
        secret_token = cfg["telegram"].get("webhook_secret") or settings.TELEGRAM_WEBHOOK_SECRET or ""

        url = f"https://api.telegram.org/bot{token}/setWebhook"
        payload: Dict[str, Any] = {
            "url": webhook_url,
            "drop_pending_updates": drop_pending_updates,
            "allowed_updates": [
                "message",
                "edited_message",
                "callback_query",
                "inline_query",
                "chosen_inline_result",
                "pre_checkout_query",
            ],
        }

        if secret_token:
            payload["secret_token"] = secret_token

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload)
                data = res.json()
                if not data.get("ok"):
                    logger.error(f"Telegram setWebhook failed: {data.get('description')}")
                else:
                    logger.info(f"Telegram setWebhook succeeded: {data}")
                return data
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
            return {"ok": False, "description": str(e)}

