import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Response, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_whatsapp_signature
from app.core.logger import logger
from app.channels.whatsapp.client import WhatsAppClient
from app.channels.whatsapp.render import WhatsAppRenderer
from app.ai.orchestrator import AIOrchestrator
from app.ai.memory import MemoryManager
from app.flows.engine import FlowEngine
from app.flows.definitions import MAIN_MENU_BUTTONS
from app.schemas.bot_response import BotResponse
from app.cloud_sync.client import cloud_client

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp Webhook"])


async def _deliver(wa_client: WhatsAppClient, to: str, resp: BotResponse) -> None:
    """Sends a BotResponse to WhatsApp: a swipeable media carousel when there
    are 2+ product cards with images, an interactive list message for other
    product-card/multi-button cases, otherwise quick-reply buttons, otherwise
    plain text."""
    rendered = WhatsAppRenderer.render(resp)
    if rendered["carousel"]:
        await wa_client.send_media_carousel(
            to=to,
            body=rendered["carousel"]["body"],
            cards=rendered["carousel"]["cards"],
        )
    elif rendered["list_sections"]:
        await wa_client.send_list_message(
            to=to,
            body=rendered["text"],
            button_text="View Products",
            sections=rendered["list_sections"],
        )
    elif rendered["buttons"]:
        await wa_client.send_button_message(to=to, body=rendered["text"], buttons=rendered["buttons"])
    else:
        await wa_client.send_text_message(to=to, body=rendered["text"])


@router.get("")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """WhatsApp Cloud API Webhook Verification Challenge."""
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("WhatsApp webhook verification failed.")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("")
async def handle_whatsapp_message(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Receives and processes incoming WhatsApp messages and interactive actions."""
    raw_body = await request.body()
    if not verify_whatsapp_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid WhatsApp signature")

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return {"status": "ok"}

    # Iterate through WhatsApp payload structure
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            messages = value.get("messages", [])

            # Dynamic Agent Resolution
            from app.models.agent import Agent
            agent = None
            if phone_number_id:
                stmt = select(Agent).where(Agent.whatsapp_phone_id == phone_number_id, Agent.is_active == True)
                res = await db.execute(stmt)
                agent = res.scalar_one_or_none()

            if not agent:
                stmt = select(Agent).where(Agent.is_active == True).limit(1)
                res = await db.execute(stmt)
                agent = res.scalar_one_or_none()

            wa_client = WhatsAppClient(
                token=agent.whatsapp_token if agent and agent.whatsapp_token else None,
                phone_number_id=phone_number_id or (agent.whatsapp_phone_id if agent and agent.whatsapp_phone_id else None),
            )

            for msg in messages:
                wa_id = msg.get("from")
                msg_type = msg.get("type")
                user_text = ""
                action_id = None

                # Extract customer name if present
                contacts = value.get("contacts", [])
                customer_name = contacts[0].get("profile", {}).get("name") if contacts else None

                # 1. Text Message
                if msg_type == "text":
                    user_text = msg.get("text", {}).get("body", "").strip()

                # 2. Interactive Quick-Reply Button Click
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    interactive_type = interactive.get("type")
                    if interactive_type == "button_reply":
                        action_id = interactive.get("button_reply", {}).get("id")
                        user_text = interactive.get("button_reply", {}).get("title", "")
                    elif interactive_type == "list_reply":
                        action_id = interactive.get("list_reply", {}).get("id")
                        user_text = interactive.get("list_reply", {}).get("title", "")

                if not user_text and not action_id:
                    continue

                logger.info(f"Incoming WhatsApp message from {wa_id}: '{user_text}' (action: {action_id})")

                # Track telemetry event
                cloud_client.track(
                    channel="whatsapp",
                    customer_id=wa_id,
                    event="message_received",
                    metadata={"msg_type": msg_type, "text": user_text[:100]},
                )

                session = await MemoryManager.get_or_create_session(db, channel="whatsapp", customer_identifier=wa_id)

                # Determine Routing: Fast-Path System Handlers (0 LLM Tokens) vs AI Orchestration
                fast_path_triggers = [
                    "menu", "start", "/start", "help", "cart", "/cart", "checkout",
                    "clear cart", "profile", "my profile", "create profile", "update profile", "edit profile",
                    "my purchases", "my orders",
                ]
                is_fast_path = (
                    action_id
                    or session.active_flow
                    or user_text.lower().strip() in fast_path_triggers
                    or user_text.lower().startswith("cart_")
                    or user_text.lower().startswith("flow_")
                    or user_text.lower().startswith("qty_")
                )

                if is_fast_path:
                    flow_res = await FlowEngine.handle_action(
                        db=db,
                        session=session,
                        action_id=action_id or user_text,
                        user_input=user_text,
                        prefill_name=customer_name,
                    )
                    await _deliver(wa_client, wa_id, flow_res)
                else:
                    # Route to AI Orchestrator with graceful button fallback if LLM is unconfigured
                    try:
                        ai_resp = await AIOrchestrator.process_message(
                            db=db,
                            channel="whatsapp",
                            customer_identifier=wa_id,
                            user_message=user_text,
                            customer_name=customer_name,
                            agent=agent,
                        )
                        await _deliver(wa_client, wa_id, ai_resp)
                    except Exception as e:
                        logger.warning(f"AI Orchestrator unavailable ({e}). Falling back to interactive menu buttons.")
                        fallback_body = "👋 I received your message! Please select an option from our menu below:"
                        if len(MAIN_MENU_BUTTONS) > 3:
                            # WhatsApp quick-reply buttons cap at 3 — MAIN_MENU_BUTTONS
                            # has more, so render as a list message instead (matches
                            # WhatsAppRenderer's own >3-buttons convention).
                            rows = [{"id": b["id"], "title": b["title"][:24]} for b in MAIN_MENU_BUTTONS[:10]]
                            await wa_client.send_list_message(
                                to=wa_id,
                                body=fallback_body,
                                button_text="Menu",
                                sections=[{"title": "Options", "rows": rows}],
                            )
                        else:
                            await wa_client.send_button_message(
                                to=wa_id,
                                body=fallback_body,
                                buttons=MAIN_MENU_BUTTONS,
                            )

                # Track outgoing message telemetry
                cloud_client.track(
                    channel="whatsapp",
                    customer_id=wa_id,
                    event="message_sent",
                )

    return {"status": "ok"}
