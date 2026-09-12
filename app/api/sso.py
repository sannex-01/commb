from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import hmac
import hashlib
import json
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import create_admin_jwt, _b64url_decode, _b64url_encode, hash_password
from app.core.config import settings
from app.models.user import AdminUser

router = APIRouter(prefix="/auth", tags=["SSO"])

class SSORequest(BaseModel):
    token: str

@router.post("/sso")
async def sso_login(req: SSORequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Verifies a short-lived AgentOS SSO token and logs in the operator."""
    if not settings.COMMB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="COMMB_API_KEY not configured. SSO disabled."
        )

    # Decode and verify the SSO token (JWT structure: header.payload.signature)
    parts = req.token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token format")
    
    header_b64, payload_b64, sig_b64 = parts
    expected_sig = hmac.new(
        settings.COMMB_API_KEY.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256
    ).digest()
    
    if not hmac.compare_digest(_b64url_encode(expected_sig), sig_b64):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
        
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
        
    if payload.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token missing email")
        
    # Auto-provision or update user
    res = await db.execute(select(AdminUser).where(AdminUser.email == email))
    user = res.scalar_one_or_none()
    
    if not user:
        user = AdminUser(
            name=payload.get("name", "AgentOS Operator"),
            email=email,
            password_hash=hash_password("AgentOS_SSO_Placeholder_Pass"),
            role="admin",  # Defaulting to admin
            is_active=True
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
        
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    
    # Issue standard admin session JWT
    session_token = create_admin_jwt(user.id, user.email, user.role)
    response.set_cookie(
        key="commb_admin_session",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=172800,
    )
    
    return {
        "status": "ok",
        "access_token": session_token,
        "token": session_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        }
    }
