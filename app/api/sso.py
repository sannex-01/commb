from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
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


async def _extract_token(request: Request) -> str:
    """Reads `token` from either a JSON body or a form POST.

    The cloud control plane hands this off by submitting a real HTML <form>
    (method="POST", target="_blank") rather than calling fetch(), because only
    a genuine browser navigation lets the instance's Set-Cookie response land
    on the instance's own origin -- a fetch()/XHR response cannot set a cookie
    the browser will actually use for subsequent page loads on that origin. A
    submitted form always sends application/x-www-form-urlencoded, never JSON,
    so this endpoint has to accept both.
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        token = body.get("token") if isinstance(body, dict) else None
    else:
        form = await request.form()
        token = form.get("token")

    if not token or not isinstance(token, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing token")
    return token


@router.post("/sso")
async def sso_login(request: Request, db: AsyncSession = Depends(get_db)):
    """Verifies a short-lived CommB Cloud SSO token and logs in the operator."""
    if not settings.COMMB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="COMMB_API_KEY not configured. SSO disabled."
        )

    token = await _extract_token(request)

    # Decode and verify the SSO token (JWT structure: header.payload.signature)
    parts = token.split(".")
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
            name=payload.get("name", "CommB Cloud Operator"),
            email=email,
            # Nobody signs in with this password: SSO is the only entry point
            # for an auto-provisioned account. A fixed placeholder is fine
            # precisely because it grants nothing on its own -- login still
            # requires a valid, freshly-signed SSO token.
            password_hash=hash_password("CommB_SSO_Placeholder_Pass"),
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

    # This endpoint is reached by a real browser navigation (a form POST from
    # the cloud control plane), not by fetch() -- so the operator ends up
    # LOOKING at whatever is returned. Redirect them into the admin rather
    # than rendering a JSON blob at them.
    #
    # The session lives in the httpOnly cookie set below, and deliberately is
    # NOT echoed in a body: this response is rendered in a browser tab and
    # kept in history, so returning the JWT as text would undo the point of
    # httpOnly for no gain -- the cookie is what authenticates the browser.
    redirect = RedirectResponse(url="/_/admin", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key="commb_admin_session",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=172800,
    )
    return redirect
