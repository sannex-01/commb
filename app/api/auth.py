from datetime import datetime, timezone
import re
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import verify_password, hash_password, create_admin_jwt, get_current_admin_user, create_password_reset_jwt, decode_password_reset_jwt
from app.models.user import AdminUser
from app.models.business import BusinessProfile

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/login")
@limiter.limit("20/minute")
async def admin_login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Logs in an admin/operator user and issues a signed JWT token & cookie."""
    res = await db.execute(select(AdminUser).where(AdminUser.email == req.email.lower().strip()))
    user = res.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your user account is deactivated. Contact an administrator.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token = create_admin_jwt(user.id, user.email, user.role)
    response.set_cookie(
        key="commb_admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=172800,  # 48 hours
    )

    biz_res = await db.execute(select(BusinessProfile).limit(1))
    biz = biz_res.scalar_one_or_none()

    return {
        "status": "ok",
        "access_token": token,
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
        "business": {
            "name": biz.name if biz else "CommB Business",
            "currency": biz.currency if biz else "NGN",
            "contact_email": biz.contact_email if biz else None,
            "logo_url": biz.logo_url if biz else None,
        },
    }


@router.get("/me")
async def get_current_user_profile(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the profile of the currently logged-in admin user."""
    biz_res = await db.execute(select(BusinessProfile).limit(1))
    biz = biz_res.scalar_one_or_none()

    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role,
            "last_login_at": current_user.last_login_at,
            "created_at": current_user.created_at,
        },
        "business": {
            "name": biz.name if biz else "CommB Business",
            "currency": biz.currency if biz else "NGN",
            "contact_email": biz.contact_email if biz else None,
            "logo_url": biz.logo_url if biz else None,
        },
    }


@router.post("/logout")
async def admin_logout(response: Response):
    """Logs out the user and clears session cookie."""
    response.delete_cookie("commb_admin_session")
    return {"status": "ok", "message": "Logged out successfully."}


@router.post("/forgot-password")
@limiter.limit("10/minute")
async def forgot_password(req: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Sends a password reset email if the user exists and email service is configured."""
    email_clean = req.email.lower().strip()
    res = await db.execute(select(AdminUser).where(AdminUser.email == email_clean, AdminUser.is_active == True))
    user = res.scalar_one_or_none()

    if not user:
        return {
            "status": "ok",
            "message": "If an account matches that email address, a password reset link has been sent.",
        }

    biz_res = await db.execute(select(BusinessProfile).limit(1))
    biz = biz_res.scalar_one_or_none()
    biz_name = biz.name if biz else "CommB Studio"
    logo_url = biz.logo_url if biz else None

    from app.services.email import EmailService
    cfg = await EmailService.get_config(db)
    if not cfg.get("configured"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured on this instance. Please contact an administrator to configure Resend or Brevo in Settings.",
        )

    token = create_password_reset_jwt(user.id, user.email, user.password_hash, expires_minutes=60)
    base_url = str(request.base_url).rstrip("/")
    reset_link = f"{base_url}/_/admin/reset-password?token={token}"

    try:
        await EmailService.send_password_reset_email(
            db=db,
            user=user,
            reset_link=reset_link,
            business_name=biz_name,
            logo_url=logo_url,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send password reset email: {str(e)}",
        )

    return {
        "status": "ok",
        "message": "If an account matches that email address, a password reset link has been sent.",
    }


@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(req: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Validates password reset token and updates the user's password."""
    payload = decode_password_reset_jwt(req.token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset link. Please request a new one.",
        )

    if len(req.password) < 8 or not re.search(r"[a-z]", req.password) or not re.search(r"[A-Z]", req.password) or not re.search(r"[0-9]", req.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, and one number.",
        )

    user_id = int(payload["sub"])
    res = await db.execute(select(AdminUser).where(AdminUser.id == user_id, AdminUser.is_active == True))
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found or deactivated.",
        )

    import hashlib
    expected_v = hashlib.sha256(user.password_hash.encode("utf-8")).hexdigest()[:16] if user.password_hash else ""
    token_v = payload.get("pwd_v")
    if token_v and token_v != expected_v:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link has already been used or has expired. Please request a new one.",
        )

    user.password_hash = hash_password(req.password)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "ok",
        "message": "Password reset successfully. You may now sign in with your new password.",
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Allows an authenticated admin or operator to update their password."""
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if len(req.new_password) < 8 or not re.search(r"[a-z]", req.new_password) or not re.search(r"[A-Z]", req.new_password) or not re.search(r"[0-9]", req.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, and one number.",
        )

    current_user.password_hash = hash_password(req.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "ok",
        "message": "Password changed successfully.",
    }

