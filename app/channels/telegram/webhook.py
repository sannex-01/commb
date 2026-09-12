import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_telegram_secret
from app.core.logger import logger
from app.channels.telegram.client import TelegramClient
from app.channels.telegram.render import TelegramRenderer
from app.ai.orchestrator import AIOrchestrator
from app.ai.memory import MemoryManager
from app.flows.engine import FlowEngine
from app.flows.definitions import MAIN_MENU_BUTTONS
from app.schemas.bot_response import BotResponse
from app.cloud_sync.client import cloud_client

router = APIRouter(prefix="/webhooks/telegram", tags=["Telegram Webhook"])


async def _deliver(tg_client: TelegramClient, chat_id: int | str, resp: BotResponse) -> None:
    """Sends a BotResponse to Telegram:
    1. If product cards have valid image URLs, send the swipeable media-group album FIRST.
    2. Then send the main message text with its complete inline keyboard (buy buttons, search, view cart).
    """
    rendered = TelegramRenderer.render(resp)
    if rendered["photo_items"]:
        album = TelegramRenderer.product_album(rendered["photo_items"])
        if album["media_items"]:
            await tg_client.send_media_group(chat_id=chat_id, items=album["media_items"])

    if rendered["inline_keyboard"]:
        await tg_client.send_inline_buttons(chat_id=chat_id, text=rendered["text"], buttons=rendered["inline_keyboard"])
    else:
        await tg_client.send_message(chat_id=chat_id, text=rendered["text"])


@router.post("")
@router.post("/{agent_id}")
async def handle_telegram_webhook(
    request: Request,
    agent_id: Optional[str] = None,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Processes incoming updates from Telegram Bot API."""
    if not verify_telegram_secret(x_telegram_bot_api_secret_token):
        logger.warning(
            f"Telegram webhook auth rejected: Secret token mismatch or missing. "
            f"Received header: '{x_telegram_bot_api_secret_token}'"
        )
        raise HTTPException(status_code=401, detail="Invalid Telegram secret token")

    raw_body = await request.body()
    try:
        update = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse Telegram webhook body as JSON: {e}")
        return {"ok": True}

    logger.info(f"=== TELEGRAM INCOMING UPDATE ===\n{json.dumps(update, indent=2)}")

    from app.models.agent import Agent
    from sqlalchemy.orm import selectinload

    agent = None
    if agent_id:
        if agent_id.isdigit():
            stmt = select(Agent).where(Agent.id == int(agent_id), Agent.is_active == True)
        else:
            stmt = select(Agent).where(Agent.slug == agent_id, Agent.is_active == True)
        res = await db.execute(stmt.options(selectinload(Agent.group)))
        agent = res.scalar_one_or_none()
        if not agent:
            logger.warning(f"Telegram webhook: no active agent matched path id/slug '{agent_id}' — falling back.")

    # Fallbacks only when the URL carried no agent discriminator (legacy
    # single-bot setup, or a webhook registered before per-agent scoping).
    # With 2+ token-bearing agents there is no reliable way to tell them
    # apart from the payload alone, so we must NOT silently answer as the
    # first one — that is exactly the "agent 2's messages answered by agent
    # 1" bug. Re-register each agent's webhook (PUT the agent, or the
    # Settings > Channels sync) so its URL is /webhooks/telegram/<id>.
    if not agent:
        tokened = (await db.execute(
            select(Agent)
            .where(Agent.telegram_bot_token.is_not(None), Agent.is_active == True)
            .options(selectinload(Agent.group))
        )).scalars().all()
        if len(tokened) == 1:
            agent = tokened[0]
        elif len(tokened) > 1:
            logger.error(
                f"Telegram webhook received with no agent id in the URL but {len(tokened)} active agents "
                f"have bot tokens ({[a.id for a in tokened]}). Cannot route reliably — re-register each "
                f"agent's Telegram webhook so its URL is /webhooks/telegram/<agent_id>. Dropping update."
            )
            return {"ok": True}

    if not agent:
        res = await db.execute(
            select(Agent).where(Agent.is_active == True).options(selectinload(Agent.group)).limit(1)
        )
        agent = res.scalar_one_or_none()

    tg_client = TelegramClient(token=agent.telegram_bot_token if agent and agent.telegram_bot_token else None)

    # 0. Handle Inline Mode Search Queries (bots/inline) — "@botname <query>"
    if "inline_query" in update:
        iq = update["inline_query"]
        iq_id = iq.get("id")
        query_text = (iq.get("query") or "").strip()
        from_user = iq.get("from", {})
        chat_type = iq.get("chat_type", "")

        logger.info(f"=== TELEGRAM INLINE QUERY RECEIVED ===")
        logger.info(f"Query ID: {iq_id} | User: {from_user.get('id')} (@{from_user.get('username')}) | Query: '{query_text}' | Chat Type: {chat_type}")

        from app.commerce.catalog_provider import CatalogManager
        from app.schemas.bot_response import ProductCard
        from app.core.access import get_effective_agent_tags

        # Scope search results to THIS agent's catalog (its access groups /
        # tags) — the same scoping the AI-orchestrator path uses. Without it,
        # inline search returns every agent's products (in practice the first
        # agent's, since that's who the update used to resolve to).
        allowed_tags = get_effective_agent_tags(agent) if agent else None

        if not query_text:
            products = await CatalogManager.get_featured_products(db, limit=10, allowed_access_tags=allowed_tags)
        else:
            products = await CatalogManager.search_products(db, query=query_text, limit=10, allowed_access_tags=allowed_tags)

        logger.info(f"Found {len(products)} matching products for inline query '{query_text}'")

        # Resolve the bot @username for cross-chat "Buy" deep links. Prefer the
        # configured value; otherwise ask Telegram (getMe) once and cache it
        # back onto the agent so foreign-chat buys always route into the bot DM
        # via t.me/<bot>?start=... instead of an unreliable callback button.
        bot_username = agent.telegram_username if agent else None
        if not bot_username:
            try:
                me = await tg_client.get_me()
                if me.get("ok"):
                    bot_username = me["result"].get("username")
                    if bot_username and agent:
                        agent.telegram_username = bot_username
                        await db.commit()
            except Exception as e:
                logger.warning(f"getMe lookup for inline-search deep link failed: {e}")

        cards = [
            ProductCard(
                id=p.id,
                title=p.title,
                description=p.description,
                price=p.price,
                currency=p.currency,
                image_url=p.image_url or None,
                buy_action_id=f"cart_add_{p.id}",
            )
            for p in products
        ]
        results = TelegramRenderer.inline_query_results(
            cards=cards,
            chat_type=chat_type,
            bot_username=bot_username,
        )
        logger.info(f"Generated {len(results)} inline article cards to return to Telegram:\n{json.dumps(results, indent=2)}")

        res = await tg_client.answer_inline_query(iq_id, results=results)
        logger.info(f"Telegram answerInlineQuery response: {res}")

        return {"ok": True}

    # 0b. Handle Chosen Inline Result (when user taps an inline item)
    if "chosen_inline_result" in update:
        cir = update["chosen_inline_result"]
        logger.info(f"=== TELEGRAM CHOSEN INLINE RESULT ===\n{json.dumps(cir, indent=2)}")
        return {"ok": True}

    # 1. Handle Inline Button Clicks (callback_query)
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb.get("id")
        action_data = cb.get("data", "")
        from_user = cb.get("from", {})
        user_id = str(from_user.get("id"))
        message_obj = cb.get("message", {})
        chat_id = message_obj.get("chat", {}).get("id") or from_user.get("id")
        message_id = message_obj.get("message_id")
        inline_message_id = cb.get("inline_message_id")

        # A click that carries only inline_message_id (no message object) came
        # from an inline-search result card — either dropped in the bot's own DM
        # or shared into a foreign chat/group. Either way we cannot edit that
        # card in place; we always send a fresh follow-up message into the
        # clicking user's DM with the bot (their user id == the DM chat id).
        from_inline_card = bool(inline_message_id) and not message_id
        if from_inline_card:
            chat_id = from_user.get("id")

        # For a normal in-chat button we ack immediately. For an inline-search
        # card click we defer the ack until after we've tried to deliver the DM
        # follow-up, so we can surface an error toast if delivery is blocked
        # (Telegram only honours the first answerCallbackQuery per click).
        callback_answered = False
        if not from_inline_card:
            await tg_client.answer_callback_query(cb_id)
            callback_answered = True

        session = await MemoryManager.get_or_create_session(db, channel="telegram", customer_identifier=user_id)
        flow_res = await FlowEngine.handle_action(
            db=db,
            session=session,
            action_id=action_data,
            user_input=action_data,
        )
        rendered = TelegramRenderer.render(flow_res)

        # If product cards with images are present, send the media album first,
        # then send the main catalog text with buttons below the album.
        if rendered["photo_items"]:
            album = TelegramRenderer.product_album(rendered["photo_items"])
            if album["media_items"]:
                await tg_client.send_media_group(chat_id=chat_id, items=album["media_items"])

            if chat_id:
                if rendered["inline_keyboard"]:
                    await tg_client.send_inline_buttons(chat_id=chat_id, text=rendered["text"], buttons=rendered["inline_keyboard"])
                else:
                    await tg_client.send_message(chat_id=chat_id, text=rendered["text"])
        else:
            # When no photos are present, edit the existing message in-place for a clean single-message UI
            edit_success = False

            # For inline messages, we DO NOT want to edit the inline message itself
            # because that replaces the user's sent message instead of the bot sending a response.
            if message_id and chat_id and not inline_message_id:
                try:
                    res = await tg_client.edit_inline_buttons(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=rendered["text"],
                        buttons=rendered["inline_keyboard"],
                    )
                    if res.get("ok"):
                        edit_success = True
                except Exception as e:
                    logger.warning(f"In-place message edit failed, will send fresh message: {e}")

            if not edit_success and chat_id:
                if rendered["inline_keyboard"]:
                    send_res = await tg_client.send_inline_buttons(chat_id=chat_id, text=rendered["text"], buttons=rendered["inline_keyboard"])
                else:
                    send_res = await tg_client.send_message(chat_id=chat_id, text=rendered["text"])

                # If the follow-up DM couldn't be delivered (Telegram forbids a
                # bot from messaging a user who has never started it), tell the
                # user in-place via the callback toast to open the bot first.
                if from_inline_card and isinstance(send_res, dict) and not send_res.get("ok"):
                    bot_handle = agent.telegram_username if agent and agent.telegram_username else None
                    hint = f"Open @{bot_handle} and tap Start" if bot_handle else "Open a chat with the bot and tap Start"
                    await tg_client.answer_callback_query(
                        cb_id,
                        text=f"⚠️ I couldn't message you directly. {hint}, then try again.",
                    )
                    callback_answered = True

        # Ensure every inline-card click is acknowledged even on the happy path.
        if from_inline_card and not callback_answered:
            await tg_client.answer_callback_query(cb_id)

        # Track interactive button action telemetry
        cloud_client.track(
            channel="telegram",
            customer_id=user_id,
            event="button_click",
            metadata={"action": action_data[:100]},
        )

        return {"ok": True}

    # 2. Handle Inbound Text Messages
    if "message" in update:
        msg = update["message"]
        chat_id = msg.get("chat", {}).get("id")
        from_user = msg.get("from", {})
        user_id = str(from_user.get("id"))
        customer_name = from_user.get("first_name", "Telegram User")
        full_name = " ".join(filter(None, [from_user.get("first_name"), from_user.get("last_name")])) or None
        text = msg.get("text", "").strip()

        # Handle native Telegram successful payment notification
        if "successful_payment" in msg:
            sp = msg["successful_payment"]
            logger.info(f"Telegram in-app payment successful for user {user_id}: {sp}")
            cloud_client.track(
                channel="telegram",
                customer_id=user_id,
                event="payment_success",
                amount=sp.get("total_amount", 0) / 100.0,
                status="success",
            )
            await tg_client.send_message(
                chat_id=chat_id,
                text="🎉 *Payment Confirmed!* Thank you for your purchase. We are processing your order right away.",
            )
            return {"ok": True}

        if not text:
            return {"ok": True}

        # Parse /start deep links
        if text.startswith("/start ") and len(text.split(" ", 1)) > 1:
            text = text.split(" ", 1)[1]

        logger.info(f"Incoming Telegram message from {user_id} (@{from_user.get('username')}): '{text}'")

        cloud_client.track(
            channel="telegram",
            customer_id=user_id,
            event="message_received",
            metadata={"text": text[:100]},
        )

        session = await MemoryManager.get_or_create_session(db, channel="telegram", customer_identifier=user_id)

        # Handle Fast-Path System Handlers (0 LLM Tokens)
        fast_path_triggers = [
            "/start", "start", "menu", "/menu", "help", "/cart", "cart", "checkout",
            "clear cart", "profile", "my profile", "create profile", "update profile", "edit profile",
            "my purchases", "my orders",
        ]
        is_fast_path = (
            text.lower().strip() in fast_path_triggers
            or text.lower().startswith("cart_")
            or text.lower().startswith("flow_")
            or text.lower().startswith("qty_")
        )

        sent_reply_text = ""
        if is_fast_path:
            flow_res = await FlowEngine.handle_action(
                db=db,
                session=session,
                action_id=text,
                user_input=text,
                prefill_name=full_name,
            )
            sent_reply_text = flow_res.text
            await _deliver(tg_client, chat_id, flow_res)
        elif session.active_flow or text.upper().startswith("ORD-"):
            # Active flow state processing (e.g. order tracking or cart input)
            flow_res = await FlowEngine.handle_action(
                db=db,
                session=session,
                action_id=text,
                user_input=text,
                prefill_name=full_name,
            )
            sent_reply_text = flow_res.text
            await _deliver(tg_client, chat_id, flow_res)
        else:
            # Route to AI Orchestrator with graceful button fallback if LLM is unconfigured or errors
            try:
                ai_resp = await AIOrchestrator.process_message(
                    db=db,
                    channel="telegram",
                    customer_identifier=user_id,
                    user_message=text,
                    customer_name=customer_name,
                    agent=agent,
                )
                sent_reply_text = ai_resp.text
                await _deliver(tg_client, chat_id, ai_resp)
            except Exception as e:
                logger.warning(f"AI Orchestrator unavailable ({e}). Falling back to interactive menu buttons.")
                fallback_kb = [
                    [{"text": b["title"], "callback_data": b["id"]}]
                    for b in MAIN_MENU_BUTTONS
                ]
                sent_reply_text = "👋 I received your message! Please select from our interactive menu below to browse products, check your cart, or track an order:"
                await tg_client.send_inline_buttons(
                    chat_id=chat_id,
                    text=sent_reply_text,
                    buttons=fallback_kb,
                )

        cloud_client.track(
            channel="telegram",
            customer_id=user_id,
            event="message_sent",
        )

        # Sync conversation transcript so Conversations CRM in AgentOS updates in real time
        cloud_client.sync_conversation(
            channel="telegram",
            customer_id=user_id,
            messages=[
                {"role": "user", "content": text},
                {"role": "assistant", "content": sent_reply_text or "Interactive menu sent"},
            ],
        )

    # 3. Handle Pre-Checkout Query for Telegram Payments
    if "pre_checkout_query" in update:
        pcq = update["pre_checkout_query"]
        pcq_id = pcq.get("id")
        await tg_client.answer_pre_checkout_query(pcq_id, ok=True)
        return {"ok": True}

    return {"ok": True}
