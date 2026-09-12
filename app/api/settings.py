from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin_user, require_admin_role, require_operator_or_above, generate_platform_api_key
from app.models.user import AdminUser
from app.models.business import BusinessProfile

router = APIRouter(prefix="/settings", tags=["Business Settings & API Keys"])


class UpdateBusinessProfileRequest(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None


@router.get("/profile")
async def get_business_profile(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the business profile and settings."""
    res = await db.execute(select(BusinessProfile).limit(1))
    biz = res.scalar_one_or_none()
    if not biz:
        biz = BusinessProfile(name="My Business", currency="NGN")
        db.add(biz)
        await db.commit()
        await db.refresh(biz)

    return {
        "id": biz.id,
        "name": biz.name,
        "currency": biz.currency,
        "contact_email": biz.contact_email,
        "contact_phone": biz.contact_phone,
        "address": biz.address,
        "logo_url": biz.logo_url,
        "is_configured": biz.is_configured,
        "updated_at": biz.updated_at,
    }


@router.put("/profile")
async def update_business_profile(
    req: UpdateBusinessProfileRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates business profile information."""
    res = await db.execute(select(BusinessProfile).limit(1))
    biz = res.scalar_one_or_none()
    if not biz:
        biz = BusinessProfile()
        db.add(biz)

    if req.name is not None:
        name_val = req.name.strip()
        if not name_val:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business name cannot be empty.")
        biz.name = name_val

    if req.currency is not None:
        curr_val = req.currency.upper().strip()
        if not curr_val:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business currency cannot be empty.")
        biz.currency = curr_val

    if req.contact_email is not None:
        email_val = req.contact_email.lower().strip()
        if email_val and "@" not in email_val:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide a valid contact email address.")
        biz.contact_email = email_val or None

    if req.contact_phone is not None:
        biz.contact_phone = req.contact_phone.strip() if req.contact_phone else None
    if req.address is not None:
        biz.address = req.address.strip() if req.address else None
    if req.logo_url is not None:
        biz.logo_url = req.logo_url.strip() if req.logo_url else None

    biz.is_configured = True
    await db.commit()
    await db.refresh(biz)

    return {
        "status": "ok",
        "message": "Business profile updated successfully.",
        "business": {
            "name": biz.name,
            "currency": biz.currency,
            "contact_email": biz.contact_email,
            "contact_phone": biz.contact_phone,
            "address": biz.address,
            "logo_url": biz.logo_url,
        },
    }


@router.get("/api-key")
async def get_api_key_status(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Returns the masked preview and creation timestamp of the platform API key."""
    res = await db.execute(select(BusinessProfile).limit(1))
    biz = res.scalar_one_or_none()

    if not biz or not biz.api_key_hash:
        return {
            "has_api_key": False,
            "masked_key": None,
            "created_at": None,
        }

    return {
        "has_api_key": True,
        "masked_key": biz.api_key_prefix or "commb_live_••••••••••••",
        "api_key_prefix": biz.api_key_prefix or "commb_live_••••••••••••",
        "created_at": biz.api_key_created_at,
        "api_key_created_at": biz.api_key_created_at,
        "last_rotated_at": biz.api_key_created_at,
    }


@router.post("/api-key/rotate")
async def rotate_api_key(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """One-click API key rotation. Generates a fresh secure platform key and invalidates the previous one."""
    res = await db.execute(select(BusinessProfile).limit(1))
    biz = res.scalar_one_or_none()
    if not biz:
        biz = BusinessProfile()
        db.add(biz)

    raw_key, key_hash, key_prefix = generate_platform_api_key()
    biz.api_key_hash = key_hash
    biz.api_key_prefix = key_prefix
    biz.api_key_created_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "status": "ok",
        "message": "Platform API Key rotated successfully. Copy and store it securely now.",
        "raw_api_key": raw_key,
        "api_key": raw_key,  # Returned in full exactly once upon rotation
        "masked_key": key_prefix,
        "api_key_prefix": key_prefix,
        "created_at": biz.api_key_created_at,
        "last_rotated_at": biz.api_key_created_at,
    }


class UpdateStorageConfigRequest(BaseModel):
    provider: Optional[str] = None  # "cloudinary", "cloudflare_r2", or None
    config: Optional[dict] = {}


@router.get("/storage")
async def get_storage_settings(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns current media storage configuration status and settings."""
    from app.services.storage import StorageService
    return await StorageService.get_config(db)


@router.put("/storage")
async def update_storage_settings(
    req: UpdateStorageConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates media storage configuration (Cloudinary or Cloudflare R2)."""
    from app.services.storage import StorageService
    try:
        return await StorageService.save_config(db, req.provider, req.config or {})
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/storage/upload")
async def upload_media_file(
    file: UploadFile = File(...),
    current_user: AdminUser = Depends(require_operator_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Uploads an image or file to the configured storage provider (Cloudinary or Cloudflare R2)."""
    from app.services.storage import StorageService
    try:
        contents = await file.read()
        if len(contents) > 15 * 1024 * 1024:  # 15MB limit
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size exceeds 15MB limit.")

        url = await StorageService.upload_file(
            db=db,
            file_bytes=contents,
            filename=file.filename or "upload.jpg",
            content_type=file.content_type or "image/jpeg",
        )
        return {
            "status": "ok",
            "url": url,
            "filename": file.filename,
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload error: {str(e)}")


class UpdateEmailConfigRequest(BaseModel):
    provider: Optional[str] = None  # "resend", "brevo", or None
    config: Optional[dict] = {}


class SendTestEmailRequest(BaseModel):
    to_email: str


@router.get("/email")
async def get_email_settings(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Returns current email delivery configuration status and masked settings."""
    from app.services.email import EmailService
    return await EmailService.get_config(db)


@router.put("/email")
async def update_email_settings(
    req: UpdateEmailConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates email delivery provider configuration (Resend or Brevo)."""
    from app.services.email import EmailService
    try:
        return await EmailService.save_config(db, req.provider, req.config or {})
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/email/test")
async def send_test_email(
    req: SendTestEmailRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Sends a test email to verify credentials and delivery."""
    from app.services.email import EmailService
    try:
        biz_res = await db.execute(select(BusinessProfile).limit(1))
        biz = biz_res.scalar_one_or_none()
        biz_name = biz.name if biz else "CommB Studio"

        subject = f"Test Email from {biz_name}"
        html = f"""
        <div style="font-family: sans-serif; padding: 24px; border: 1px solid #e5e7eb; border-radius: 8px; max-width: 500px;">
          <h2 style="color: #008060; margin-top: 0;">✓ Email Delivery Verified</h2>
          <p>Your transactional email delivery provider is configured correctly and working seamlessly for <strong>{biz_name}</strong>.</p>
          <p style="color: #6b7280; font-size: 12px; margin-top: 24px;">Sent via CommB Email Engine</p>
        </div>
        """
        await EmailService.send_email(
            db=db,
            to_email=req.to_email.strip(),
            subject=subject,
            html_content=html,
            text_content="Your transactional email delivery is configured correctly.",
        )
        return {"status": "ok", "message": f"Test email sent successfully to {req.to_email}."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class UpdateSMSConfigRequest(BaseModel):
    provider: Optional[str] = None  # "africastalking", "termii", or None
    config: Optional[dict] = {}


class SendTestSMSRequest(BaseModel):
    to_phone: str


@router.get("/sms")
async def get_sms_settings(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Returns current SMS delivery configuration status and masked settings."""
    from app.services.sms import SMSService
    return await SMSService.get_config(db)


@router.put("/sms")
async def update_sms_settings(
    req: UpdateSMSConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates SMS delivery provider configuration (Africa's Talking or Termii)."""
    from app.services.sms import SMSService
    try:
        return await SMSService.save_config(db, req.provider, req.config or {})
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/sms/test")
async def send_test_sms(
    req: SendTestSMSRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Sends a test SMS to verify credentials and delivery."""
    from app.services.sms import SMSService
    try:
        biz_res = await db.execute(select(BusinessProfile).limit(1))
        biz = biz_res.scalar_one_or_none()
        biz_name = biz.name if biz else "CommB Studio"

        await SMSService.send_sms(
            db=db,
            to_phone=req.to_phone.strip(),
            message=f"Test SMS from {biz_name}: your CommB order alert SMS delivery is configured correctly.",
        )
        return {"status": "ok", "message": f"Test SMS sent successfully to {req.to_phone}."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class UpdateTelegramAlertsConfigRequest(BaseModel):
    chat_id: Optional[str] = None


@router.get("/alerts/telegram")
async def get_telegram_alerts_settings(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Returns the current Telegram order-alerts group chat_id, plus whether
    any agent has a Telegram bot connected (the actual sending bot — see
    TelegramAlertService, no separate alerts-only bot to configure)."""
    from app.services.telegram_alerts import TelegramAlertService
    return await TelegramAlertService.get_config(db)


@router.put("/alerts/telegram")
async def update_telegram_alerts_settings(
    req: UpdateTelegramAlertsConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates the group chat_id order alerts are sent to."""
    from app.services.telegram_alerts import TelegramAlertService
    try:
        return await TelegramAlertService.save_config(db, {"chat_id": req.chat_id})
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/alerts/telegram/test")
async def send_test_telegram_alert(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Sends a test alert message to verify the group chat_id and that some
    agent's Telegram bot can actually deliver to it."""
    from app.services.telegram_alerts import TelegramAlertService
    try:
        biz_res = await db.execute(select(BusinessProfile).limit(1))
        biz = biz_res.scalar_one_or_none()
        biz_name = biz.name if biz else "CommB Studio"

        await TelegramAlertService.send_alert(
            db=db,
            message=f"✅ Test alert from {biz_name}: your CommB order alerts are configured correctly.",
        )
        return {"status": "ok", "message": "Test alert sent successfully."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class UpdateAlertRecipientsRequest(BaseModel):
    emails: List[str] = []
    phones: List[str] = []


@router.get("/alerts/recipients")
async def get_alert_recipients(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Who order alerts actually get sent to for Email/SMS (Telegram's
    chat_id already IS the recipient, stored on its own config)."""
    from app.services.alert_recipients import AlertRecipientsService
    return await AlertRecipientsService.get_recipients(db)


@router.put("/alerts/recipients")
async def update_alert_recipients(
    req: UpdateAlertRecipientsRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    from app.services.alert_recipients import AlertRecipientsService
    try:
        return await AlertRecipientsService.save_recipients(db, req.emails, req.phones)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


class UpdateBumpaConfigRequest(BaseModel):
    api_key: Optional[str] = None
    public_key: Optional[str] = None
    store_id: Optional[str] = None
    share_for_payments: Optional[bool] = None


@router.get("/store-connections/bumpa")
async def get_bumpa_settings(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Returns Bumpa connection status and masked config — backs the Store
    Connections tab and the catalog Import Catalog button's provider check."""
    from app.services.store_connections import StoreConnectionService
    return await StoreConnectionService.get_bumpa_config(db)


@router.put("/store-connections/bumpa")
async def update_bumpa_settings(
    req: UpdateBumpaConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates the Bumpa secret/public API keys and store id, stored in the
    database instead of requiring env vars — this is what a business
    actually sets from the dashboard. api_key is the secret key (merchant
    order/analytics routes); public_key is required separately for the
    customer-facing cart/checkout routes (real checkout via Bumpa)."""
    from app.services.store_connections import StoreConnectionService
    try:
        return await StoreConnectionService.save_bumpa_config(db, {
            "api_key": req.api_key,
            "public_key": req.public_key,
            "store_id": req.store_id,
            "share_for_payments": req.share_for_payments,
        })
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


class UpdatePaystackConnectionRequest(BaseModel):
    api_key: Optional[str] = None
    share_for_payments: Optional[bool] = None


@router.get("/store-connections/paystack")
async def get_paystack_connection_settings(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Paystack's Store Connection entry — same shape as Bumpa's, but a
    single api_key (Paystack has no separate public/secret split for this
    purpose) since it's already used elsewhere. Lets a business import
    Paystack's product catalog without necessarily using Paystack as their
    active Payment Gateway, and share_for_payments works the same way
    Bumpa's does (see StoreConnectionService.get_shared_payment_key)."""
    from app.services.store_connections import StoreConnectionService
    return await StoreConnectionService.get_connection_config(db, "paystack")


@router.put("/store-connections/paystack")
async def update_paystack_connection_settings(
    req: UpdatePaystackConnectionRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    from app.services.store_connections import StoreConnectionService
    try:
        return await StoreConnectionService.save_connection_config(db, "paystack", {
            "api_key": req.api_key,
            "share_for_payments": req.share_for_payments,
        })
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


class UpdatePaymentConfigRequest(BaseModel):
    provider: Optional[str] = None  # "paystack", "bumpa", "flutterwave", "monnify", "stripe", or None
    config: Optional[dict] = {}
    default_gateway: Optional[str] = None
    gateways: Optional[dict] = None


@router.get("/payments")
async def get_payment_settings(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Returns the active payment gateway configuration status and masked settings."""
    from app.services.payments import PaymentService
    return await PaymentService.get_config(db)


@router.get("/payments/currencies")
async def get_payment_currencies(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns available currencies discovered from the active Paystack merchant integration."""
    from app.services.payments import PaymentService
    currencies = await PaymentService.get_currencies(db)
    return {"currencies": currencies}


@router.put("/payments")
async def update_payment_settings(
    req: UpdatePaymentConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates payment gateway configuration for the single active provider."""
    from app.services.payments import PaymentService
    provider = req.provider or req.default_gateway
    config = req.config
    if config is None or config == {}:
        if req.gateways and provider:
            config = req.gateways.get(provider, {})
    try:
        return await PaymentService.save_config(db, provider, config or {})
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))



class UpdateChannelsConfigRequest(BaseModel):
    whatsapp: Optional[dict] = {}
    telegram: Optional[dict] = {}
    widget: Optional[dict] = {}


class TelegramTestWebhookRequest(BaseModel):
    bot_token: str


@router.get("/channels")
async def get_channels_settings(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Returns the messaging channels configuration, webhook tokens, and URLs."""
    from app.services.channels import ChannelService
    return await ChannelService.get_config(db)


@router.put("/channels")
async def update_channels_settings(
    req: UpdateChannelsConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Updates global messaging channel tokens, secrets, and URLs."""
    from app.services.channels import ChannelService
    try:
        return await ChannelService.save_config(db, req.model_dump())
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/channels/generate-secret")
async def generate_channel_secret(
    current_user: AdminUser = Depends(require_admin_role),
):
    """Generates a fresh cryptographically secure random token for webhook signatures or verification."""
    from app.services.channels import generate_webhook_secret, generate_verify_token
    return {
        "webhook_secret": generate_webhook_secret(),
        "verify_token": generate_verify_token(),
    }


@router.post("/channels/telegram/test-webhook")
async def test_and_set_telegram_webhook(
    req: TelegramTestWebhookRequest,
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Tests connection to Telegram Bot API and configures setWebhook with the active secret."""
    from app.services.channels import ChannelService
    result = await ChannelService.set_telegram_webhook(req.bot_token, db)
    return result


class UpdateAnalyticsConfigRequest(BaseModel):
    posthog_api_key: Optional[str] = None
    posthog_host: Optional[str] = "https://us.i.posthog.com"


@router.get("/analytics")
async def get_analytics_settings(
    current_user: AdminUser = Depends(get_current_admin_user),
):
    """Returns host analytics and PostHog configuration."""
    from app.core.config import settings
    return {
        "posthog_api_key": settings.POSTHOG_API_KEY,
        "posthog_host": settings.POSTHOG_HOST or "https://us.i.posthog.com",
        "posthog_configured": bool(settings.POSTHOG_API_KEY),
    }


@router.put("/analytics")
async def update_analytics_settings(
    req: UpdateAnalyticsConfigRequest,
    current_user: AdminUser = Depends(require_admin_role),
):
    """Updates host PostHog analytics configuration."""
    from app.core.config import settings
    if req.posthog_api_key is not None:
        key_val = req.posthog_api_key.strip()
        settings.POSTHOG_API_KEY = key_val or None
    if req.posthog_host is not None:
        host_val = req.posthog_host.strip()
        settings.POSTHOG_HOST = host_val or "https://us.i.posthog.com"

    return {
        "status": "ok",
        "message": "Analytics settings updated successfully.",
        "posthog_api_key": settings.POSTHOG_API_KEY,
        "posthog_host": settings.POSTHOG_HOST,
        "posthog_configured": bool(settings.POSTHOG_API_KEY),
    }






