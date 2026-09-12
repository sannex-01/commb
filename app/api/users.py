import re
import secrets
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, create_password_reset_jwt, get_current_admin_user, require_admin_role
from app.models.user import AdminUser
from app.models.business import BusinessProfile
from app.services.email import EmailService

router = APIRouter(prefix="/users", tags=["Team Users Management"])


class UserCreateRequest(BaseModel):
    email: str
    password: Optional[str] = None
    name: Optional[str] = None
    role: str = "operator"  # admin, operator, viewer


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_users(
    current_user: AdminUser = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
):
    """Lists all team user accounts on this CommB instance."""
    res = await db.execute(select(AdminUser).order_by(AdminUser.created_at.desc()))
    users = res.scalars().all()

    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "last_login_at": u.last_login_at,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreateRequest,
    request: Request,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new team member or sends an invitation email if email is configured."""
    if current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can add new team members.",
        )

    clean_email = req.email.lower().strip()
    if not clean_email:
        raise HTTPException(status_code=400, detail="Email address is required.")

    # Check email duplicate
    res = await db.execute(select(AdminUser).where(AdminUser.email == clean_email))
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    email_cfg = await EmailService.get_config(db)
    email_is_configured = email_cfg.get("configured", False)

    invited = False
    if req.password and req.password.strip():
        if len(req.password.strip()) < 8 or not re.search(r"[a-z]", req.password.strip()) or not re.search(r"[A-Z]", req.password.strip()) or not re.search(r"[0-9]", req.password.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, and one number.",
            )
        pwd_hash = hash_password(req.password.strip())
    else:
        if not email_is_configured:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required because email delivery is not configured on this instance.",
            )
        # Generate random temporary secret for initial hash
        temp_secret = secrets.token_urlsafe(32)
        pwd_hash = hash_password(temp_secret)
        invited = True

    new_user = AdminUser(
        name=(req.name or "").strip(),
        email=clean_email,
        password_hash=pwd_hash,
        role=req.role or "operator",
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # If invited, send invitation email with 24-hour setup token
    if invited:
        token = create_password_reset_jwt(new_user.id, new_user.email, new_user.password_hash, expires_minutes=1440)
        base_url = str(request.base_url).rstrip("/")
        invite_link = f"{base_url}/_/admin/reset-password?token={token}"

        biz_res = await db.execute(select(BusinessProfile).limit(1))
        biz = biz_res.scalar_one_or_none()
        biz_name = biz.name if biz and biz.name else "CommB Studio"
        logo_url = biz.logo_url if biz else None

        try:
            await EmailService.send_invitation_email(
                db=db,
                user=new_user,
                invite_link=invite_link,
                business_name=biz_name,
                logo_url=logo_url,
                role=new_user.role,
            )
        except Exception as e:
            # Don't fail the user creation if email send failed, but return warning
            return {
                "id": new_user.id,
                "name": new_user.name,
                "email": new_user.email,
                "role": new_user.role,
                "is_active": new_user.is_active,
                "invited": True,
                "invite_warning": f"Member added, but invitation email could not be sent: {str(e)}",
                "invite_link": invite_link,
                "created_at": new_user.created_at,
            }

    return {
        "id": new_user.id,
        "name": new_user.name,
        "email": new_user.email,
        "role": new_user.role,
        "is_active": new_user.is_active,
        "invited": invited,
        "created_at": new_user.created_at,
    }


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates an existing team user account."""
    if current_user.role not in ["super_admin", "admin"] and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this user.",
        )

    res = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if req.name is not None:
        user.name = req.name.strip()
    if req.email is not None:
        user.email = req.email.lower().strip()
    if req.password is not None and req.password.strip():
        if len(req.password.strip()) < 8 or not re.search(r"[a-z]", req.password.strip()) or not re.search(r"[A-Z]", req.password.strip()) or not re.search(r"[0-9]", req.password.strip()):
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, and one number.")
        user.password_hash = hash_password(req.password.strip())
    if req.role is not None and current_user.role in ["super_admin", "admin"]:
        user.role = req.role
    if req.is_active is not None and current_user.role in ["super_admin", "admin"]:
        user.is_active = req.is_active

    await db.commit()
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
    }


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletes a team user account."""
    if current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account.")

    res = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    await db.delete(user)
    await db.commit()
    return {"status": "ok", "message": "User deleted."}
