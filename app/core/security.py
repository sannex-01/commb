import os
import json
import base64
import hmac
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from fastapi import Header, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.core.database import get_db
from app.models.user import AdminUser
from app.models.business import BusinessProfile


# ============================================================================
# 1. WEBHOOK SIGNATURE VERIFIERS (Preserved)
# ============================================================================

def verify_whatsapp_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """Verifies X-Hub-Signature-256 header sent by Meta WhatsApp Cloud API."""
    if not settings.META_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_hash = signature_header[7:]
    generated_hash = hmac.new(
        settings.META_APP_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated_hash, expected_hash)


def verify_telegram_secret(secret_header: Optional[str]) -> bool:
    """Verifies X-Telegram-Bot-Api-Secret-Token sent by Telegram webhook."""
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        return True
    if not secret_header:
        return False
    return hmac.compare_digest(settings.TELEGRAM_WEBHOOK_SECRET, secret_header)


def verify_paystack_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """Verifies x-paystack-signature header using Paystack Secret Key (HMAC-SHA512)."""
    if not settings.PAYSTACK_SECRET_KEY:
        return True
    if not signature_header:
        return False
    computed_signature = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(computed_signature, signature_header)


def verify_flutterwave_hash(hash_header: Optional[str]) -> bool:
    """Verifies verif-hash header sent by Flutterwave."""
    if not settings.FLUTTERWAVE_SECRET_HASH:
        return True
    if not hash_header:
        return False
    return hmac.compare_digest(settings.FLUTTERWAVE_SECRET_HASH, hash_header)


def verify_stripe_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """Verifies Stripe signature header (t=timestamp,v1=signature)."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        return True
    if not signature_header:
        return False
    try:
        elements = dict(item.split("=", 1) for item in signature_header.split(","))
        timestamp = elements.get("t")
        sig = elements.get("v1")
        if not timestamp or not sig:
            return False
        signed_payload = f"{timestamp}.".encode("utf-8") + payload
        expected_sig = hmac.new(
            settings.STRIPE_WEBHOOK_SECRET.encode("utf-8"),
            signed_payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, sig)
    except Exception as e:
        logger.error(f"Error validating stripe signature: {e}")
        return False


# ============================================================================
# 2. AGENTOS DASHBOARD AUTH (Preserved for agentOS-connected callers)
# ============================================================================

async def verify_dashboard_auth(authorization: Optional[str] = Header(None)) -> None:
    """Verifies static COMMB_API_KEY from environment for agentOS callers."""
    if not settings.COMMB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dashboard API key not configured on this instance.",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    token = authorization[len("Bearer "):]
    if not hmac.compare_digest(token, settings.COMMB_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")


# ============================================================================
# 3. PASSWORD HASHING (PBKDF2-HMAC-SHA256)
# ============================================================================

def hash_password(password: str) -> str:
    """Securely hashes a password using PBKDF2 with 600,000 iterations."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        600000
    )
    return f"pbkdf2_sha256$600000${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored PBKDF2 hash."""
    if not hashed_password or not hashed_password.startswith("pbkdf2_sha256$"):
        return False
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4:
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_key = parts[3]
        key = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations
        )
        return hmac.compare_digest(key.hex(), expected_key)
    except Exception:
        return False


# ============================================================================
# 4. JWT SESSION TOKENS FOR STANDALONE ADMIN
# ============================================================================

JWT_SECRET = settings.APP_SECRET or getattr(settings, "COMMB_API_KEY", None) or "commb-standalone-secret-key-32b-min"

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding < 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)

def create_admin_jwt(user_id: int, email: str, role: str, expires_hours: int = 48) -> str:
    """Generates a signed JWT session token for an admin user."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = datetime.now(timezone.utc)
    exp = int((now + timedelta(hours=expires_hours)).timestamp())
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": exp,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        JWT_SECRET.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_admin_jwt(token: str) -> Optional[dict]:
    """Validates and decodes a signed admin JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        expected_sig = hmac.new(
            JWT_SECRET.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("utf-8"),
            hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url_encode(expected_sig), sig_b64):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except Exception:
        return None


def create_password_reset_jwt(user_id: int, email: str, password_hash: Optional[str] = None, expires_minutes: int = 60) -> str:
    """Generates a secure, single-use signed JWT token specifically for password reset."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = datetime.now(timezone.utc)
    exp = int((now + timedelta(minutes=expires_minutes)).timestamp())
    pwd_v = hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16] if password_hash else ""
    payload = {
        "sub": str(user_id),
        "email": email,
        "purpose": "password_reset",
        "pwd_v": pwd_v,
        "iat": int(now.timestamp()),
        "exp": exp,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        JWT_SECRET.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_password_reset_jwt(token: str) -> Optional[dict]:
    """Validates and decodes a password reset JWT token."""
    payload = decode_admin_jwt(token)
    if not payload or payload.get("purpose") != "password_reset":
        return None
    return payload



# ============================================================================
# 5. PLATFORM API KEY GENERATION & ROTATION (Standalone Mode)
# ============================================================================

def generate_platform_api_key() -> Tuple[str, str, str]:
    """Generates a secure platform API key.
    
    Returns:
        (raw_key, key_hash, masked_preview)
        - raw_key: Full plaintext string to show user once upon creation.
        - key_hash: SHA-256 hex digest to store safely in DB.
        - masked_preview: e.g. 'commb_live_d8a2...3f1a'
    """
    raw_key = f"commb_live_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    masked_preview = f"{raw_key[:14]}...{raw_key[-4:]}"
    return raw_key, key_hash, masked_preview


# ============================================================================
# 6. STANDALONE ADMIN AUTH DEPENDENCY
# ============================================================================

async def get_current_admin_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency to authenticate requests to /api/v1/admin/* via JWT."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
    elif "commb_admin_session" in request.cookies:
        token = request.cookies.get("commb_admin_session")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )

    payload = decode_admin_jwt(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
        )

    user_id = int(payload["sub"])
    res = await db.execute(select(AdminUser).where(AdminUser.id == user_id, AdminUser.is_active == True))
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found or deactivated.",
        )

    return user


async def require_admin_role(
    current_user: AdminUser = Depends(get_current_admin_user),
) -> AdminUser:
    """Ensures caller has super_admin or admin role."""
    if current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Administrator privileges required.",
        )
    return current_user


async def require_operator_or_above(
    current_user: AdminUser = Depends(get_current_admin_user),
) -> AdminUser:
    """Ensures caller has super_admin, admin, or operator role (excludes read-only viewers)."""
    if current_user.role not in ["super_admin", "admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Operator or Administrator privileges required for this action.",
        )
    return current_user


# ============================================================================
# 7. STANDALONE PLATFORM API KEY AUTH DEPENDENCY
# ============================================================================

async def verify_platform_api_key(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_commb_api_key: Optional[str] = Header(None, alias="X-CommB-API-KEY"),
    db: AsyncSession = Depends(get_db),
):
    """Validates platform API key (commb_live_...) against BusinessProfile.api_key_hash for standalone API callers."""
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[len("Bearer "):].strip()
    elif x_commb_api_key:
        raw_token = x_commb_api_key.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide Bearer token or X-CommB-API-KEY header.",
        )

    # First check static COMMB_API_KEY if configured (AgentOS legacy/env fallback)
    if settings.COMMB_API_KEY and hmac.compare_digest(raw_token, settings.COMMB_API_KEY):
        return True

    # Check standalone BusinessProfile key hash
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    res = await db.execute(select(BusinessProfile).where(BusinessProfile.api_key_hash == token_hash))
    profile = res.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid platform API key.",
        )

    return True

