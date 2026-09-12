import json
import asyncio
from typing import List, Dict, Any, Optional
import httpx
from app.core.config import settings
from app.core.logger import logger


def _optimize_telegram_media_url(url: str) -> str:
    """Optimizes image URLs for Telegram Bot API (e.g. adding fast auto-formatting and resizing for Cloudinary)."""
    if not url or not isinstance(url, str):
        return url
    if "res.cloudinary.com" in url and "/image/upload/" in url:
        # Avoid duplicating transformation flags if already present
        if "/image/upload/f_" not in url and "/image/upload/q_" not in url and "/image/upload/w_" not in url:
            return url.replace("/image/upload/", "/image/upload/f_jpg,q_auto,w_1000/")
    return url


async def _download_photo_bytes(url: str) -> Optional[bytes]:
    """Downloads photo bytes with timeout for fallback multipart upload to Telegram."""
    try:
        opt_url = _optimize_telegram_media_url(url)
        headers = {"User-Agent": "CommB-Telegram-Bot/1.0"}
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(opt_url, headers=headers)
            if res.status_code == 200 and res.content:
                return res.content
    except Exception as e:
        logger.warning(f"Failed to download photo from {url} for Telegram fallback: {e}")
    return None


class TelegramClient:
    """Telegram Bot API Client."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN

    async def _post(
        self,
        method: str,
        payload: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.token:
            logger.info(f"[DEV MOCK] Telegram API {method} payload: {payload}")
            return {"ok": True, "result": {"message_id": 9999, "status": "mocked"}}

        url = f"https://api.telegram.org/bot{self.token}/{method}"
        async with httpx.AsyncClient(timeout=25.0) as client:
            if files:
                data_payload = {}
                if payload:
                    for k, v in payload.items():
                        if isinstance(v, (dict, list)):
                            data_payload[k] = json.dumps(v)
                        else:
                            data_payload[k] = str(v)
                res = await client.post(url, data=data_payload, files=files)
            else:
                res = await client.post(url, json=payload or {})

            try:
                data = res.json()
            except Exception:
                data = {"ok": False, "error_code": res.status_code, "description": res.text}

            if not data.get("ok"):
                logger.error(f"Telegram API {method} error: {data}")
            return data

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sends a text message with optional inline keyboard or custom keyboard, with fallback to plain text."""
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        res = await self._post("sendMessage", payload)
        if not res.get("ok") and parse_mode:
            # Fallback retry without Markdown formatting in case of unescaped characters
            logger.info("Retrying sendMessage without parse_mode markdown formatting...")
            payload.pop("parse_mode", None)
            res = await self._post("sendMessage", payload)
        return res

    async def send_photo(
        self,
        chat_id: int | str,
        photo_url: str,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sends a photo (e.g. a product card image) with an optional caption and inline keyboard."""
        opt_url = _optimize_telegram_media_url(photo_url)
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "photo": opt_url,
        }
        if caption:
            payload["caption"] = caption
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        res = await self._post("sendPhoto", payload)
        if not res.get("ok"):
            desc = res.get("description", "")
            # If failed due to URL curl failure, fallback to uploading bytes directly
            if "WEBPAGE_CURL_FAILED" in desc or "failed to get HTTP URL content" in desc:
                logger.info("Telegram URL curl failed for sendPhoto; falling back to direct multipart upload...")
                raw_bytes = await _download_photo_bytes(photo_url)
                if raw_bytes:
                    files = {"photo": ("product.jpg", raw_bytes, "image/jpeg")}
                    payload.pop("photo", None)
                    res = await self._post("sendPhoto", payload=payload, files=files)
            elif parse_mode:
                logger.info("Retrying sendPhoto without parse_mode markdown formatting...")
                payload.pop("parse_mode", None)
                res = await self._post("sendPhoto", payload)
        return res

    async def get_me(self) -> Dict[str, Any]:
        """Returns the bot's own identity (id, username, ...) via getMe.
        Used to resolve the bot @username for inline-search deep links when it
        hasn't been configured on the agent record."""
        return await self._post("getMe")

    async def answer_inline_query(
        self,
        inline_query_id: str,
        results: List[Dict[str, Any]],
        cache_time: int = 30,
    ) -> Dict[str, Any]:
        """Answers an inline_query (bots/inline) with up to 50 results —
        used for @botname <search> product search from any chat, or from
        the current chat via a switch_inline_query_current_chat button."""
        payload = {
            "inline_query_id": inline_query_id,
            "results": results[:50],
            "cache_time": cache_time,
        }
        return await self._post("answerInlineQuery", payload)

    async def send_media_group(
        self,
        chat_id: int | str,
        items: List[Dict[str, Any]],  # [{"photo_url": str, "caption": Optional[str]}]
    ) -> Dict[str, Any]:
        """Sends up to 10 photos as one native swipeable album (sendMediaGroup) with multipart upload fallback."""
        media = []
        for item in items[:10]:
            opt_url = _optimize_telegram_media_url(item["photo_url"])
            entry: Dict[str, Any] = {"type": "photo", "media": opt_url}
            if item.get("caption"):
                entry["caption"] = item["caption"][:1024]
                entry["parse_mode"] = "Markdown"
            media.append(entry)

        payload = {"chat_id": chat_id, "media": media}
        res = await self._post("sendMediaGroup", payload)

        if not res.get("ok"):
            desc = res.get("description", "")
            # 1. Fallback for WEBPAGE_CURL_FAILED: download images and upload directly via multipart/form-data
            if "WEBPAGE_CURL_FAILED" in desc or "failed to get HTTP URL content" in desc:
                logger.info("Telegram URL curl failed for sendMediaGroup; falling back to direct multipart upload...")
                download_tasks = [_download_photo_bytes(item["photo_url"]) for item in items[:10]]
                downloaded_photos = await asyncio.gather(*download_tasks)

                multipart_media = []
                files = {}
                for idx, (item, photo_bytes) in enumerate(zip(items[:10], downloaded_photos)):
                    if photo_bytes:
                        attach_key = f"photo_{idx}"
                        files[attach_key] = (f"photo_{idx}.jpg", photo_bytes, "image/jpeg")
                        entry = {"type": "photo", "media": f"attach://{attach_key}"}
                        if item.get("caption"):
                            entry["caption"] = item["caption"][:1024]
                        multipart_media.append(entry)

                if multipart_media:
                    res = await self._post(
                        "sendMediaGroup",
                        payload={"chat_id": chat_id, "media": multipart_media},
                        files=files,
                    )
            elif "can't parse entities" in desc.lower() or "markdown" in desc.lower():
                # Retry without Markdown in case a caption has unescaped special chars
                logger.info("Retrying sendMediaGroup without parse_mode markdown formatting...")
                for entry in media:
                    entry.pop("parse_mode", None)
                res = await self._post("sendMediaGroup", {"chat_id": chat_id, "media": media})

        return res

    async def send_inline_buttons(
        self,
        chat_id: int | str,
        text: str,
        buttons: List[List[Dict[str, str]]], # [[{"text": "Btn 1", "callback_data": "btn_1"}]]
    ) -> Dict[str, Any]:
        """Sends inline button grid."""
        markup = {"inline_keyboard": buttons}
        return await self.send_message(chat_id, text, reply_markup=markup)

    async def edit_message_text(
        self,
        chat_id: Optional[int | str] = None,
        message_id: Optional[int] = None,
        text: str = "",
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
        inline_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Edits an existing message text in-place on Telegram."""
        payload: Dict[str, Any] = {
            "text": text,
        }
        if inline_message_id:
            payload["inline_message_id"] = inline_message_id
        else:
            payload["chat_id"] = chat_id
            payload["message_id"] = message_id

        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        res = await self._post("editMessageText", payload)
        if not res.get("ok"):
            desc = res.get("description", "").lower()
            if "message is not modified" in desc:
                return {"ok": True, "not_modified": True}
            if parse_mode:
                # Retry without Markdown formatting in case of unescaped special chars
                payload.pop("parse_mode", None)
                res = await self._post("editMessageText", payload)
                if not res.get("ok") and "message is not modified" in res.get("description", "").lower():
                    return {"ok": True, "not_modified": True}
        return res

    async def edit_inline_buttons(
        self,
        chat_id: Optional[int | str] = None,
        message_id: Optional[int] = None,
        text: str = "",
        buttons: Optional[List[List[Dict[str, str]]]] = None,
        inline_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Edits an existing message's text and its inline keyboard in-place."""
        markup = {"inline_keyboard": buttons} if buttons is not None else None
        return await self.edit_message_text(chat_id, message_id, text, reply_markup=markup, inline_message_id=inline_message_id)

    async def send_invoice(
        self,
        chat_id: int | str,
        title: str,
        description: str,
        payload: str,
        provider_token: str,
        currency: str,
        prices: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Sends a native Telegram payment invoice."""
        body = {
            "chat_id": chat_id,
            "title": title,
            "description": description,
            "payload": payload,
            "provider_token": provider_token or settings.TELEGRAM_PAYMENT_PROVIDER_TOKEN,
            "currency": currency.upper(),
            "prices": prices,
        }
        return await self._post("sendInvoice", body)

    async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> Dict[str, Any]:
        """Acknowledges button clicks on Telegram."""
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        return await self._post("answerCallbackQuery", payload)

    async def answer_pre_checkout_query(self, pre_checkout_query_id: str, ok: bool = True, error_message: Optional[str] = None) -> Dict[str, Any]:
        """Confirms pre-checkout validity before Telegram executes payment."""
        payload: Dict[str, Any] = {
            "pre_checkout_query_id": pre_checkout_query_id,
            "ok": ok,
        }
        if not ok and error_message:
            payload["error_message"] = error_message
        return await self._post("answerPreCheckoutQuery", payload)
