import json
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.logger import logger
from app.ai.memory import MemoryManager
from app.ai.orchestrator import AIOrchestrator
from app.flows.engine import FlowEngine
from app.flows.definitions import WIDGET_MAIN_MENU_BUTTONS
from app.models.config_override import ConfigOverride
from app.schemas.bot_response import BotResponse

router = APIRouter(prefix="/widget", tags=["Website Widget"])

# NOTE: unlike every other inbound surface in this service (signed webhooks),
# /api/v1/widget/* is reachable directly from arbitrary third-party browser JS
# since widget.js is by design embedded in public page source — its endpoint
# URLs are trivially discoverable and there is no per-request auth. Rate
# limited below (per client IP — session_id is client-supplied and trivially
# spoofable) via slowapi; chat/stream is limited tighter since it costs a
# real LLM call.


class WidgetActionRequest(BaseModel):
    action_id: str
    session_id: str
    user_input: Optional[str] = None


class WidgetChatRequest(BaseModel):
    message: str
    session_id: str
    bot_id: Optional[str] = None


class WidgetProfileRequest(BaseModel):
    session_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skipped: bool = False


@router.get("/history")
@limiter.limit("30/minute")
async def widget_history(request: Request, session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Returns this widget session's recent transcript so a page reload can
    restore the conversation instead of restarting it — the session_id
    itself already survives a reload via localStorage (see panel.ts's
    getOrCreateSessionId), but until now nothing replayed the messages
    already logged against it (MessageLog, written by MemoryManager.add_message
    on every turn — the same log every other channel already accumulates)."""
    from app.models.session import ConversationSession, MessageLog

    stmt = select(ConversationSession).where(
        ConversationSession.channel == "widget",
        ConversationSession.customer_identifier == session_id,
    )
    session = (await db.execute(stmt)).scalars().first()
    if not session:
        return {"messages": []}

    msg_filters = [MessageLog.session_id == session.id, MessageLog.role.in_(["user", "assistant"])]
    if session.session_started_at:
        # Only replay messages from the CURRENT conversation, not the
        # session row's entire lifetime — a session_key is reused forever
        # (see ConversationSession), and once MemoryManager resets an
        # expired session's AI/flow state, replaying everything logged
        # before that reset showed a stale transcript (old buttons whose
        # underlying flow state no longer existed) even though the backend
        # had genuinely started a fresh conversation.
        msg_filters.append(MessageLog.created_at >= session.session_started_at)
    msg_stmt = (
        select(MessageLog)
        .where(*msg_filters)
        .order_by(MessageLog.created_at.asc())
        .limit(50)
    )
    logs = (await db.execute(msg_stmt)).scalars().all()
    return {
        "messages": [{"role": m.role, "content": m.content} for m in logs],
        "has_profile": bool(FlowEngine._get_widget_profile(session)),
    }


@router.post("/profile")
@limiter.limit("10/minute")
async def widget_submit_profile(request: Request, req: WidgetProfileRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """One-shot submission of the autofill-friendly form shown immediately on
    panel open (see widget/src/profile-form.ts) — collected fresh every
    session, never persisted as a Customer row (widget has no durable
    identity). 'skipped' stores an empty profile so checkout falls back to
    the same turn-by-turn chat collection WhatsApp/Telegram use."""
    session = await MemoryManager.get_or_create_session(db, channel="widget", customer_identifier=req.session_id)
    await FlowEngine.set_widget_profile(
        db, session,
        name=None if req.skipped else req.name,
        email=None if req.skipped else req.email,
        phone=None if req.skipped else req.phone,
    )
    return {"status": "ok"}


class WidgetAddressRequest(BaseModel):
    session_id: str
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None


@router.post("/address")
@limiter.limit("10/minute")
async def widget_submit_address(request: Request, req: WidgetAddressRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Structured delivery-address form, shown before checkout only when the
    cart contains at least one item needing delivery (see
    CartManager.cart_requires_shipping) — collected fresh every session,
    never persisted (widget has no durable Customer identity), same
    session-only shape as widget_submit_profile above."""
    session = await MemoryManager.get_or_create_session(db, channel="widget", customer_identifier=req.session_id)
    await FlowEngine.set_widget_address(db, session, fields={
        "street": req.street, "city": req.city, "state": req.state, "zip": req.zip, "country": req.country,
    })
    return {"status": "ok"}


@router.post("/chat/stream")
@limiter.limit("15/minute")
async def widget_chat_stream(request: Request, req: WidgetChatRequest, db: AsyncSession = Depends(get_db)):
    """Streams the LLM response to the website widget using SSE."""

    session = await MemoryManager.get_or_create_session(db, channel="widget", customer_identifier=req.session_id)

    # Dynamic Agent Resolution
    from app.models.agent import Agent
    agent = None
    if req.bot_id:
        if req.bot_id.isdigit():
            stmt = select(Agent).where(Agent.id == int(req.bot_id), Agent.is_active == True)
        else:
            stmt = select(Agent).where(Agent.slug == req.bot_id, Agent.is_active == True)
        res = await db.execute(stmt)
        agent = res.scalar_one_or_none()

    if not agent:
        stmt = select(Agent).where(Agent.widget_enabled == True, Agent.is_active == True).limit(1)
        res = await db.execute(stmt)
        agent = res.scalar_one_or_none()

    if not agent:
        stmt = select(Agent).where(Agent.is_active == True).limit(1)
        res = await db.execute(stmt)
        agent = res.scalar_one_or_none()

    # Flows that expect a specific free-text reply as their very next step
    # (as opposed to "catalog"/"main_menu"/"profile_view", which just mark
    # the last screen shown — free text there is a normal question for the
    # AI, e.g. "do you have this in blue?") — intercept and route to
    # FlowEngine instead of the LLM, exactly like Telegram/WhatsApp already
    # do via FlowEngine._process_action's own routing. Missing "track_order"
    # here (and "address_collect", added alongside it) previously meant
    # replying with an order reference after tapping "Track Order" fell
    # through to the AI orchestrator instead, which threw when no LLM
    # provider key was configured — automatic order lookup shouldn't depend
    # on an LLM being set up at all.
    if session.active_flow in ["profile_collect", "quantity_select", "address_collect", "track_order"]:
        resp = await FlowEngine.handle_action(
            db=db, session=session, action_id=req.message, user_input=req.message,
        )

        async def flow_event_generator():
            yield f"data: {json.dumps({'content': resp.text})}\n\n"
            yield f"data: {json.dumps({'final': resp.model_dump()})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(flow_event_generator(), media_type="text/event-stream")

    async def event_generator():
        # Mirrors Telegram/WhatsApp's own try/except around AIOrchestrator
        # (see telegram/webhook.py) — an unconfigured or failing LLM
        # provider must never surface as a raw exception here: with SSE
        # already streaming, an uncaught error mid-generator tears down the
        # connection outright (net::ERR_INCOMPLETE_CHUNKED_ENCODING in the
        # browser) instead of returning a normal reply. Falls back to the
        # same deterministic main-menu buttons every other channel uses so
        # the widget stays usable with zero AI configured.
        try:
            stream = AIOrchestrator.process_message_stream(
                db=db,
                channel="widget",
                customer_identifier=req.session_id,
                user_message=req.message,
                agent=agent,
            )
            async for chunk in stream:
                if isinstance(chunk, str):
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                elif isinstance(chunk, dict) and chunk.get("type") == "final":
                    yield f"data: {json.dumps({'final': chunk['data'].model_dump()})}\n\n"
        except Exception as e:
            # Falling back to menu buttons is a supported way to run a bot, not a
            # failure: `interactive_flow` is a first-class mode and a store can
            # sell entirely through browse/cart/checkout with no LLM configured.
            # So a missing key is logged at INFO -- it is a configuration choice --
            # while anything else stays a warning, because that IS an outage.
            if "is not configured" in str(e):
                logger.info(
                    "No LLM key configured; serving interactive menu flow. "
                    "Add a key per agent (Admin > Agents) or per access group to "
                    "enable conversational replies."
                )
            else:
                logger.warning(f"AI Orchestrator unavailable for widget ({e}). Falling back to interactive menu buttons.")
            fallback_text = "👋 I received your message! Please select from the menu below to browse products, check your cart, or track an order:"
            fallback_resp = BotResponse(text=fallback_text, buttons=[
                {"id": b["id"], "title": b["title"], "kind": "action", "url": None}
                for b in WIDGET_MAIN_MENU_BUTTONS
            ])
            yield f"data: {json.dumps({'content': fallback_text})}\n\n"
            yield f"data: {json.dumps({'final': fallback_resp.model_dump()})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/action", response_model=BotResponse)
@limiter.limit("30/minute")
async def widget_action(request: Request, req: WidgetActionRequest, db: AsyncSession = Depends(get_db)) -> BotResponse:
    """Dispatches a widget button/product-card click (e.g. cart_add_12, flow_checkout)
    into the same deterministic flow engine every other channel uses."""
    session = await MemoryManager.get_or_create_session(
        db, channel="widget", customer_identifier=req.session_id
    )
    return await FlowEngine.handle_action(
        db=db,
        session=session,
        action_id=req.action_id,
        user_input=req.user_input,
    )


@router.get("/config")
@limiter.limit("60/minute")
async def widget_config(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Minimal launcher metadata for the floating widget (business name, welcome
    message, and whether to show the profile form immediately on open vs. defer
    it to the same chat-based collection WhatsApp/Telegram use at checkout)."""
    stmt = select(ConfigOverride).where(ConfigOverride.key == "business_name")
    res = await db.execute(stmt)
    override = res.scalars().first()
    business_name = override.value if override else settings.APP_NAME

    stmt = select(ConfigOverride).where(ConfigOverride.key == "widget_profile_collection")
    res = await db.execute(stmt)
    mode_override = res.scalars().first()
    profile_collection_mode = mode_override.value if mode_override and mode_override.value in ("upfront", "checkout") else "upfront"

    return {
        "business_name": business_name,
        "welcome_message": f"👋 Hi! How can {business_name} help you today?",
        "profile_collection_mode": profile_collection_mode,
    }
