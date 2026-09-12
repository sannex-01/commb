from datetime import datetime, timezone
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import hash_password, create_admin_jwt, generate_platform_api_key
from app.models.user import AdminUser
from app.models.business import BusinessProfile
from app.models.agent import Agent

router = APIRouter(prefix="/setup", tags=["Setup & Onboarding"])


class SetupInitRequest(BaseModel):
    admin_name: str
    admin_email: str
    admin_password: str
    business_name: str
    currency: Optional[str] = "NGN"
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    email_provider: Optional[str] = None
    email_config: Optional[dict] = {}


@router.get("/status")
async def get_setup_status(db: AsyncSession = Depends(get_db)):
    """Returns whether the standalone CommB instance has been initialized with a Super Admin."""
    user_count_res = await db.execute(select(func.count(AdminUser.id)))
    user_count = user_count_res.scalar() or 0

    biz_res = await db.execute(select(BusinessProfile).limit(1))
    biz = biz_res.scalar_one_or_none()

    return {
        "initialized": user_count > 0,
        "business_configured": bool(biz and biz.is_configured),
        "app_name": biz.name if biz else settings.APP_NAME,
        "business_name": biz.name if biz else "CommB Studio",
        "logo_url": biz.logo_url if biz else None,
        "currency": biz.currency if biz else "NGN",
        "business": {
            "name": biz.name if biz else "CommB Studio",
            "logo_url": biz.logo_url if biz else None,
            "currency": biz.currency if biz else "NGN",
        } if biz else None,
    }


@router.post("/initialize")
async def initialize_instance(req: SetupInitRequest, db: AsyncSession = Depends(get_db)):
    """One-time onboarding wizard. Creates the Super Admin and Business Profile."""
    # 1. Lockout Guard: Disallow if any admin user exists
    user_count_res = await db.execute(select(func.count(AdminUser.id)))
    if (user_count_res.scalar() or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instance is already initialized. Please log in at /_/admin/login.",
        )

    if len(req.admin_password) < 8 or not re.search(r"[a-z]", req.admin_password) or not re.search(r"[A-Z]", req.admin_password) or not re.search(r"[0-9]", req.admin_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, and one number.",
        )

    # 2. Create Super Admin User
    admin = AdminUser(
        email=req.admin_email.lower().strip(),
        password_hash=hash_password(req.admin_password),
        name=req.admin_name.strip(),
        role="super_admin",
        is_active=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(admin)
    await db.flush()

    # 3. Create or update Business Profile
    biz_res = await db.execute(select(BusinessProfile).limit(1))
    biz = biz_res.scalar_one_or_none()
    if not biz:
        biz = BusinessProfile()
        db.add(biz)

    biz.name = req.business_name.strip()
    biz.currency = (req.currency or "NGN").upper()
    biz.contact_email = req.contact_email
    biz.contact_phone = req.contact_phone
    biz.address = req.address
    if req.logo_url:
        biz.logo_url = req.logo_url

    # 4. Generate Initial Platform API Key
    raw_key, key_hash, key_prefix = generate_platform_api_key()
    biz.api_key_hash = key_hash
    biz.api_key_prefix = key_prefix
    biz.api_key_created_at = datetime.now(timezone.utc)
    biz.is_configured = True
    await db.flush()

    # Configure email provider if provided
    if req.email_provider in ["resend", "brevo"] and req.email_config:
        from app.services.email import EmailService
        await EmailService.save_config(db, req.email_provider, req.email_config)

    # 5. Seed default primary agent if none exist
    agent_count_res = await db.execute(select(func.count(Agent.id)))
    if (agent_count_res.scalar() or 0) == 0:
        default_agent = Agent(
            name=f"{biz.name} Assistant",
            slug="primary-agent",
            description="Default autonomous customer service and commerce assistant.",
            system_prompt=f"You are the helpful AI assistant for {biz.name}. Assist customers warmly with product inquiries, order placement, and support.",
            llm_provider=settings.LLM_PROVIDER,
            model_name="gemini-2.5-flash",
            temperature=0.7,
            bot_mode=settings.BOT_MODE,
            whatsapp_phone_number_id=settings.META_PHONE_NUMBER_ID or None,
            whatsapp_access_token=settings.META_WHATSAPP_TOKEN or None,
            telegram_bot_token=settings.TELEGRAM_BOT_TOKEN or None,
            widget_enabled=True,
            is_active=True,
            is_default=True,
        )
        db.add(default_agent)

    await db.commit()

    token = create_admin_jwt(admin.id, admin.email, admin.role)

    return {
        "status": "initialized",
        "message": "CommB Instance successfully initialized.",
        "access_token": token,
        "token": token,
        "platform_api_key": raw_key,
        "api_key": raw_key,  # Returned only once upon initialization
        "user": {
            "id": admin.id,
            "email": admin.email,
            "name": admin.name,
            "role": admin.role,
        },
        "business": {
            "name": biz.name,
            "currency": biz.currency,
            "contact_email": biz.contact_email,
            "logo_url": biz.logo_url,
        },
    }
