import json
from typing import Optional, Dict, Any
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import BusinessProfile
from app.models.user import AdminUser
from app.core.logger import logger


class EmailService:
    @staticmethod
    async def get_config(db: AsyncSession) -> Dict[str, Any]:
        """Returns the current email delivery configuration with API keys masked."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            return {"provider": None, "configured": False, "config": {}}

        meta = json.loads(biz.metadata_json or "{}")
        email_data = meta.get("email", {})
        provider = email_data.get("provider")
        raw_config = email_data.get("config", {})

        safe_config = {}
        if provider == "resend":
            api_key = raw_config.get("api_key", "")
            masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else ("***" if api_key else "")
            safe_config = {
                "api_key_masked": masked_key,
                "api_key_configured": bool(api_key),
                "from_email": raw_config.get("from_email", ""),
                "from_name": raw_config.get("from_name", biz.name or "CommB Admin"),
            }
        elif provider == "brevo":
            api_key = raw_config.get("api_key", "")
            masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else ("***" if api_key else "")
            safe_config = {
                "api_key_masked": masked_key,
                "api_key_configured": bool(api_key),
                "from_email": raw_config.get("from_email", ""),
                "from_name": raw_config.get("from_name", biz.name or "CommB Admin"),
            }

        return {
            "provider": provider,
            "configured": bool(provider and raw_config.get("api_key") and raw_config.get("from_email")),
            "config": safe_config,
        }

    @staticmethod
    async def save_config(db: AsyncSession, provider: Optional[str], config: Dict[str, Any]) -> Dict[str, Any]:
        """Saves email provider settings into business metadata."""
        clean_provider = provider.lower().strip() if provider and provider != "none" else None

        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            biz = BusinessProfile()
            db.add(biz)

        meta = json.loads(biz.metadata_json or "{}")
        existing_email = meta.get("email", {})
        existing_config = existing_email.get("config", {})
        existing_provider = existing_email.get("provider")

        if clean_provider in ["resend", "brevo"]:
            new_api_key = (config.get("api_key") or "").strip()
            # If empty or masked, check if we can reuse the existing key for this provider
            if (not new_api_key or new_api_key.startswith("***") or "..." in new_api_key) and existing_provider == clean_provider:
                final_api_key = existing_config.get("api_key", "").strip()
            else:
                final_api_key = new_api_key

            if not final_api_key:
                raise ValueError(f"API Key is required to configure {clean_provider.capitalize()} email delivery.")

            from_email = (config.get("from_email") or "").strip()
            if not from_email:
                raise ValueError("From Email address is required for email delivery.")
            if "@" not in from_email:
                raise ValueError("Please provide a valid sender email address (e.g. hello@yourdomain.com).")

            from_name = (config.get("from_name") or biz.name or "CommB Admin").strip()

            meta["email"] = {
                "provider": clean_provider,
                "config": {
                    "api_key": final_api_key,
                    "from_email": from_email,
                    "from_name": from_name,
                },
            }
        elif not clean_provider:
            meta["email"] = {
                "provider": None,
                "config": {},
            }
        else:
            raise ValueError(f"Unsupported email provider: {clean_provider}. Choose 'resend' or 'brevo'.")

        biz.metadata_json = json.dumps(meta)
        await db.commit()

        return await EmailService.get_config(db)

    @staticmethod
    async def send_email(
        db: AsyncSession,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Sends an email via the configured provider (Resend or Brevo)."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            raise ValueError("Business profile not found.")

        meta = json.loads(biz.metadata_json or "{}")
        email_data = meta.get("email", {})
        provider = email_data.get("provider")
        config = email_data.get("config", {})

        if not provider or not config.get("api_key"):
            raise ValueError("Email delivery service is not configured. Please configure Resend or Brevo in Settings.")

        api_key = config.get("api_key")
        from_email = config.get("from_email", biz.contact_email or "noreply@example.com")
        from_name = config.get("from_name", biz.name or "CommB Admin")
        sender = f"{from_name} <{from_email}>" if from_name else from_email

        async with httpx.AsyncClient(timeout=15.0) as client:
            if provider == "resend":
                payload = {
                    "from": sender,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content,
                }
                if text_content:
                    payload["text"] = text_content

                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code not in [200, 201]:
                    err_msg = resp.text
                    try:
                        err_msg = resp.json().get("message", resp.text)
                    except Exception:
                        pass
                    raise RuntimeError(f"Resend error ({resp.status_code}): {err_msg}")
                return True

            elif provider == "brevo":
                payload = {
                    "sender": {"name": from_name, "email": from_email},
                    "to": [{"email": to_email}],
                    "subject": subject,
                    "htmlContent": html_content,
                }
                if text_content:
                    payload["textContent"] = text_content

                resp = await client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code not in [200, 201, 202]:
                    err_msg = resp.text
                    try:
                        err_msg = resp.json().get("message", resp.text)
                    except Exception:
                        pass
                    raise RuntimeError(f"Brevo error ({resp.status_code}): {err_msg}")
                return True

            else:
                raise ValueError(f"Unsupported email provider: {provider}")

    @staticmethod
    async def send_password_reset_email(
        db: AsyncSession,
        user: AdminUser,
        reset_link: str,
        business_name: str = "CommB Studio",
        logo_url: Optional[str] = None,
    ) -> bool:
        """Sends a beautifully styled HTML password reset email to the user."""
        subject = f"Reset your password for {business_name}"
        
        logo_html = f'<img src="{logo_url}" alt="{business_name}" style="max-height: 48px; border-radius: 8px; margin-bottom: 20px;" />' if logo_url else f'<h2 style="margin: 0 0 20px; color: #111827; font-size: 20px; font-weight: 700;">{business_name}</h2>'
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Password Reset Request</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f9fafb; margin: 0; padding: 40px 20px; color: #374151; line-height: 1.6;">
  <div style="max-width: 540px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb; padding: 36px;">
    <div style="text-align: center;">
      {logo_html}
    </div>
    
    <h1 style="color: #111827; font-size: 22px; font-weight: 700; margin-top: 0; margin-bottom: 12px;">Password Reset Request</h1>
    
    <p style="margin-bottom: 20px; font-size: 15px; color: #4b5563;">
      Hello <strong>{user.name or 'there'}</strong>,
    </p>
    
    <p style="margin-bottom: 24px; font-size: 15px; color: #4b5563;">
      We received a request to reset your password for your <strong>{business_name}</strong> administrative account ({user.email}). Click the button below to set a new password:
    </p>
    
    <div style="text-align: center; margin: 32px 0;">
      <a href="{reset_link}" style="background-color: #0f172a; color: #ffffff; padding: 13px 28px; font-size: 15px; font-weight: 600; text-decoration: none; border-radius: 8px; display: inline-block; border: 1px solid #0f172a;">
        Reset Password
      </a>
    </div>
    
    <p style="font-size: 13px; color: #6b7280; margin-bottom: 12px;">
      This link will expire in <strong>60 minutes</strong> for your security.
    </p>
    
    <p style="font-size: 13px; color: #9ca3af; margin-bottom: 24px;">
      If you did not request a password reset, you can safely ignore this email. Your account remains secure.
    </p>
    
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />
    
    <p style="font-size: 12px; color: #9ca3af; margin: 0; word-break: break-all;">
      Button not working? Copy and paste this URL into your browser:<br/>
      <a href="{reset_link}" style="color: #0369a1; text-decoration: underline;">{reset_link}</a>
    </p>
  </div>
</body>
</html>
"""
        text_content = f"""Hello {user.name or 'there'},\n\nWe received a request to reset your password for {business_name}.\n\nUse the link below to set a new password (valid for 60 minutes):\n{reset_link}\n\nIf you did not request this, please ignore this email."""
        
        return await EmailService.send_email(
            db=db,
            to_email=user.email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    @staticmethod
    async def send_invitation_email(
        db: AsyncSession,
        user: AdminUser,
        invite_link: str,
        business_name: str = "CommB Studio",
        logo_url: Optional[str] = None,
        role: str = "team member",
    ) -> bool:
        """Sends a beautifully styled HTML team invitation email to set up their password."""
        subject = f"You're invited to join {business_name}"
        role_label = role.capitalize() if role else "Team Member"
        
        logo_html = f'<img src="{logo_url}" alt="{business_name}" style="max-height: 48px; border-radius: 8px; margin-bottom: 20px;" />' if logo_url else f'<h2 style="margin: 0 0 20px; color: #111827; font-size: 20px; font-weight: 700;">{business_name}</h2>'
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Team Invitation</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f9fafb; margin: 0; padding: 40px 20px; color: #374151; line-height: 1.6;">
  <div style="max-width: 540px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb; padding: 36px;">
    <div style="text-align: center;">
      {logo_html}
    </div>
    
    <h1 style="color: #111827; font-size: 22px; font-weight: 700; margin-top: 0; margin-bottom: 12px;">You're Invited!</h1>
    
    <p style="margin-bottom: 20px; font-size: 15px; color: #4b5563;">
      Hello <strong>{user.name or 'there'}</strong>,
    </p>
    
    <p style="margin-bottom: 24px; font-size: 15px; color: #4b5563;">
      You have been invited to join the <strong>{business_name}</strong> workspace as an <strong>{role_label}</strong>. Click the button below to accept your invitation and set up your password:
    </p>
    
    <div style="text-align: center; margin: 32px 0;">
      <a href="{invite_link}" style="background-color: #0f172a; color: #ffffff; padding: 13px 28px; font-size: 15px; font-weight: 600; text-decoration: none; border-radius: 8px; display: inline-block; border: 1px solid #0f172a;">
        Accept Invitation & Set Password
      </a>
    </div>
    
    <p style="font-size: 13px; color: #6b7280; margin-bottom: 12px;">
      This invitation link will expire in <strong>24 hours</strong>.
    </p>
    
    <p style="font-size: 13px; color: #9ca3af; margin-bottom: 24px;">
      If you were not expecting this invitation, you can safely ignore this email.
    </p>
    
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />
    
    <p style="font-size: 12px; color: #9ca3af; margin: 0; word-break: break-all;">
      Button not working? Copy and paste this URL into your browser:<br/>
      <a href="{invite_link}" style="color: #0369a1; text-decoration: underline;">{invite_link}</a>
    </p>
  </div>
</body>
</html>
"""
        text_content = f"""Hello {user.name or 'there'},\n\nYou have been invited to join {business_name} as an {role_label}.\n\nClick the link below to set up your password and get started:\n{invite_link}\n\n(Link is valid for 24 hours)."""
        
        return await EmailService.send_email(
            db=db,
            to_email=user.email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
