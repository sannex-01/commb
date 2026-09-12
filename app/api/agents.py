import json
import re
import secrets
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_admin_user, require_admin_role, require_operator_or_above
from app.models.user import AdminUser
from app.models.agent import Agent
from app.models.access_group import AccessGroup
from app.core.access import parse_tags_json, get_effective_agent_tags

router = APIRouter(prefix="/agents", tags=["Agent Management"])


class AgentCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    system_prompt: str
    llm_provider: Optional[str] = "gemini"
    model_name: Optional[str] = "gemini-2.5-flash"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1024
    api_key: Optional[str] = None
    api_key_override: Optional[str] = None
    bot_mode: Optional[str] = "conversational"
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_phone_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    whatsapp_token: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_username: Optional[str] = None
    widget_enabled: Optional[bool] = True
    widget_profile_collection: Optional[str] = "upfront"
    group_ids: Optional[List[int]] = []
    group_id: Optional[int] = None
    access_tags: Optional[List[str]] = []
    is_active: Optional[bool] = True


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_provider: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    api_key: Optional[str] = None
    api_key_override: Optional[str] = None
    bot_mode: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_phone_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    whatsapp_token: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_username: Optional[str] = None
    widget_enabled: Optional[bool] = None
    widget_profile_collection: Optional[str] = None
    group_ids: Optional[List[int]] = None
    group_id: Optional[int] = None
    access_tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class AgentTestRunRequest(BaseModel):
    message: str


def _mask_token(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = val.strip()
    if len(val) <= 8:
        return "••••••••"
    return f"{val[:4]}••••••••{val[-4:]}"


def _serialize_agent(a: Agent) -> dict:
    from app.core.access import get_agent_group_ids
    group_ids = get_agent_group_ids(a)
    return {
        "id": a.id,
        "name": a.name,
        "slug": a.slug,
        "description": a.description,
        "system_prompt": a.system_prompt,
        "llm_provider": a.llm_provider,
        "model_name": a.model_name,
        "temperature": a.temperature,
        "max_tokens": a.max_tokens,
        "api_key_override": bool(a.api_key_override),
        "api_key_configured": bool(a.api_key_override),
        "api_key_masked": _mask_token(a.api_key_override),
        "bot_mode": a.bot_mode,
        "whatsapp_phone_number_id": a.whatsapp_phone_number_id,
        "whatsapp_phone_id": a.whatsapp_phone_number_id,
        "whatsapp_access_token_set": bool(a.whatsapp_access_token),
        "whatsapp_token_masked": _mask_token(a.whatsapp_access_token),
        "telegram_bot_token_set": bool(a.telegram_bot_token),
        "telegram_bot_token_masked": _mask_token(a.telegram_bot_token),
        "telegram_username": a.telegram_username,
        "widget_enabled": a.widget_enabled,
        "widget_profile_collection": a.widget_profile_collection,
        "group_id": a.group_id,
        "group_ids": group_ids,
        "group_name": a.group.name if a.group else None,
        "access_tags": parse_tags_json(a.access_tags_json),
        "effective_tags": sorted(list(get_effective_agent_tags(a))),
        "is_active": a.is_active,
        "is_default": a.is_default,
        "total_messages": a.total_messages,
        "total_orders": a.total_orders,
        "total_revenue": a.total_revenue,
        "last_active_at": a.last_active_at,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", slug) or "agent"


@router.get("")
async def list_agents(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists all agents configured on this CommB instance."""
    res = await db.execute(select(Agent).options(selectinload(Agent.group)).order_by(Agent.created_at.asc()))
    agents = res.scalars().all()
    return [_serialize_agent(a) for a in agents]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    req: AgentCreateRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    slug = _slugify(req.slug) if req.slug and req.slug.strip() else _slugify(req.name)
    
    # Ensure slug uniqueness
    res = await db.execute(select(Agent).where(Agent.slug == slug))
    if res.scalar_one_or_none():
        slug = f"{slug}-{secrets.token_hex(2)}"

    tags = [t.strip().lower() for t in (req.access_tags or []) if t.strip()]
    wa_phone = (req.whatsapp_phone_number_id or req.whatsapp_phone_id or "").strip() or None
    wa_token = (req.whatsapp_access_token or req.whatsapp_token or "").strip() or None
    tg_token = (req.telegram_bot_token or "").strip() or None

    api_key_val = (req.api_key or req.api_key_override or "").strip() or None

    # Handle group_ids / group_id
    assigned_group_ids = []
    if req.group_ids is not None:
        assigned_group_ids = [int(gid) for gid in req.group_ids if gid]
    elif req.group_id is not None and req.group_id > 0:
        assigned_group_ids = [req.group_id]

    primary_group_id = assigned_group_ids[0] if assigned_group_ids else (req.group_id if req.group_id and req.group_id > 0 else None)

    agent = Agent(
        name=req.name.strip(),
        slug=slug,
        description=req.description,
        system_prompt=req.system_prompt.strip(),
        llm_provider=req.llm_provider or "gemini",
        model_name=req.model_name or "gemini-2.5-flash",
        temperature=req.temperature if req.temperature is not None else 0.7,
        max_tokens=req.max_tokens or 1024,
        api_key_override=api_key_val,
        bot_mode=req.bot_mode or "conversational",
        whatsapp_phone_number_id=wa_phone,
        whatsapp_access_token=wa_token,
        telegram_bot_token=tg_token,
        telegram_username=req.telegram_username.strip() if req.telegram_username else None,
        widget_enabled=req.widget_enabled if req.widget_enabled is not None else True,
        widget_profile_collection=req.widget_profile_collection or "upfront",
        group_id=primary_group_id,
        group_ids_json=json.dumps(assigned_group_ids),
        access_tags_json=json.dumps(tags),
        is_active=req.is_active if req.is_active is not None else True,
    )
    db.add(agent)
    await db.commit()
    
    # Reload with relation
    res = await db.execute(select(Agent).options(selectinload(Agent.group)).where(Agent.id == agent.id))
    loaded = res.scalar_one()

    # Automatically set Telegram Webhook if telegram token was supplied.
    # Scope it to this agent's id so inbound updates resolve to THIS agent
    # (its own bot token, catalog, AI config) rather than the first active one.
    if loaded.telegram_bot_token:
        try:
            from app.services.channels import ChannelService
            await ChannelService.set_telegram_webhook(loaded.telegram_bot_token, db, agent_id=loaded.id)
        except Exception:
            pass

    return _serialize_agent(loaded)


@router.post("/telegram/resync-webhooks")
async def resync_telegram_webhooks(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Re-registers every token-bearing agent's Telegram webhook so its URL is
    scoped to that agent (/webhooks/telegram/<id>). Run this once after
    upgrading to per-agent routing, or any time inbound updates seem to reach
    the wrong agent."""
    from app.services.channels import ChannelService

    res = await db.execute(select(Agent).where(Agent.telegram_bot_token.is_not(None), Agent.is_active == True))
    agents = res.scalars().all()

    results = []
    for a in agents:
        try:
            r = await ChannelService.set_telegram_webhook(
                a.telegram_bot_token, db, drop_pending_updates=False, agent_id=a.id
            )
            results.append({"agent_id": a.id, "name": a.name, "ok": bool(r.get("ok")), "detail": r.get("description")})
        except Exception as e:
            results.append({"agent_id": a.id, "name": a.name, "ok": False, "detail": str(e)})

    return {"count": len(results), "results": results}


@router.get("/{agent_id}")
async def get_agent_detail(
    agent_id: int,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetches details for a specific agent."""
    res = await db.execute(select(Agent).options(selectinload(Agent.group)).where(Agent.id == agent_id))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    return _serialize_agent(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int,
    req: AgentUpdateRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates an existing agent's settings, prompt, channels, or access tags."""
    res = await db.execute(select(Agent).options(selectinload(Agent.group)).where(Agent.id == agent_id))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")

    if req.name is not None:
        agent.name = req.name.strip()
    if req.description is not None:
        agent.description = req.description
    if req.system_prompt is not None:
        agent.system_prompt = req.system_prompt.strip()
    if req.llm_provider is not None:
        agent.llm_provider = req.llm_provider
    if req.model_name is not None:
        agent.model_name = req.model_name
    if req.temperature is not None:
        agent.temperature = req.temperature
    if req.max_tokens is not None:
        agent.max_tokens = req.max_tokens
    
    api_key_input = req.api_key if req.api_key is not None else req.api_key_override
    if api_key_input is not None:
        val = api_key_input.strip()
        if "••" not in val and val != "":
            agent.api_key_override = val
        elif val == "":
            agent.api_key_override = None

    if req.bot_mode is not None:
        agent.bot_mode = req.bot_mode
    
    wa_phone = req.whatsapp_phone_number_id if req.whatsapp_phone_number_id is not None else req.whatsapp_phone_id
    if wa_phone is not None:
        agent.whatsapp_phone_number_id = wa_phone.strip() if wa_phone else None
        
    wa_token = req.whatsapp_access_token if req.whatsapp_access_token is not None else req.whatsapp_token
    if wa_token is not None:
        val = wa_token.strip()
        if "••" not in val and val != "":
            agent.whatsapp_access_token = val
        elif val == "":
            agent.whatsapp_access_token = None

    if req.telegram_bot_token is not None:
        val = req.telegram_bot_token.strip()
        if "••" not in val and val != "":
            agent.telegram_bot_token = val
        elif val == "":
            agent.telegram_bot_token = None

    if req.telegram_username is not None:
        agent.telegram_username = req.telegram_username.strip() if req.telegram_username else None
    if req.widget_enabled is not None:
        agent.widget_enabled = req.widget_enabled
    if req.widget_profile_collection is not None:
        agent.widget_profile_collection = req.widget_profile_collection
    
    if req.group_ids is not None:
        assigned_group_ids = [int(gid) for gid in req.group_ids if gid]
        agent.group_ids_json = json.dumps(assigned_group_ids)
        agent.group_id = assigned_group_ids[0] if assigned_group_ids else None
    elif req.group_id is not None:
        if req.group_id > 0:
            agent.group_id = req.group_id
            agent.group_ids_json = json.dumps([req.group_id])
        else:
            agent.group_id = None
            agent.group_ids_json = json.dumps([])

    if req.access_tags is not None:
        clean_tags = [t.strip().lower() for t in req.access_tags if t.strip()]
        agent.access_tags_json = json.dumps(clean_tags)
    if req.is_active is not None:
        agent.is_active = req.is_active

    await db.commit()
    await db.refresh(agent)
    
    # Reload relation
    res = await db.execute(select(Agent).options(selectinload(Agent.group)).where(Agent.id == agent.id))
    loaded = res.scalar_one()

    if loaded.telegram_bot_token:
        try:
            from app.services.channels import ChannelService
            await ChannelService.set_telegram_webhook(loaded.telegram_bot_token, db, agent_id=loaded.id)
        except Exception:
            pass

    return _serialize_agent(loaded)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Deletes an agent."""
    res = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")

    await db.delete(agent)
    await db.commit()
    return {"status": "ok", "message": "Agent deleted successfully."}


@router.post("/{agent_id}/test-run")
async def test_run_agent(
    agent_id: int,
    req: AgentTestRunRequest,
    current_user: AdminUser = Depends(require_operator_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Executes a single test turn against the agent's LLM configuration."""
    res = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")

    # Resolve API Key
    api_key = agent.api_key_override
    if not api_key:
        from app.core.access import get_agent_group_ids
        gids = get_agent_group_ids(agent)
        if gids:
            grp_res = await db.execute(select(AccessGroup).where(AccessGroup.id.in_(gids)))
            groups = grp_res.scalars().all()
            for g in groups:
                if g.api_key:
                    api_key = g.api_key
                    break

    from app.ai.orchestrator import AIOrchestrator
    try:
        reply = await AIOrchestrator.generate_agent_test_reply(
            system_prompt=agent.system_prompt,
            user_message=req.message,
            llm_provider=agent.llm_provider,
            model_name=agent.model_name,
            temperature=agent.temperature,
            api_key_override=api_key,
        )
        return {"status": "ok", "reply": reply}
    except Exception as e:
        return {
            "status": "ok",
            "reply": f"Hello! I am {agent.name}. Ready to assist you. (Simulated response: {str(e)})"
        }
