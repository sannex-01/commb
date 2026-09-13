"""Plan entitlements for a managed CommB instance.

READ THIS BEFORE ADDING A CHECK HERE.

CommB is AGPL-3.0 free software. Every feature is available to everyone, for
free, forever. What CommB Cloud sells is operations -- provisioning, DNS, TLS,
upgrades, backups -- NOT access to functionality. This module must never become
a way to withhold a feature from the open-source project.

That is why every default below is unlimited:

    PLAN_NAME        unset  -> not a managed instance, no limits apply at all
    PLAN_CHANNELS    unset  -> every channel
    PLAN_MAX_*       0      -> unlimited
    ALLOW_CUSTOM_DOMAIN     -> True

A self-hoster who clones the repo and runs it gets the complete product: all
channels, unlimited products, agents and knowledge documents, custom domains. No
nag screens, no degraded mode, no "upgrade" prompts. These functions simply do
nothing unless CommB Cloud set PLAN_* when provisioning.

This is also NOT a licensing or anti-tamper mechanism. Anyone running their own
instance can edit or delete these checks -- that is their right under the AGPL,
and nothing here tries to prevent it. The purpose is narrower and honest: on an
instance we operate, the running configuration should match what the customer is
paying for, enforced where it cannot be bypassed via the instance's own admin API
rather than only hidden in the dashboard.

Rule of thumb for anything added here: if a limit would make the SELF-HOSTED
product worse, it does not belong in this file.
"""

from typing import List, Optional

from fastapi import HTTPException, status

from app.core.config import settings

ALL_CHANNELS = ("widget", "telegram", "whatsapp")


def is_managed() -> bool:
    """True when this instance was provisioned by CommB Cloud on a plan."""
    return bool(settings.PLAN_NAME)


def allowed_channels() -> List[str]:
    """Channels this plan may use. Every channel when unset (self-hosted)."""
    raw = (settings.PLAN_CHANNELS or "").strip()
    if not raw:
        return list(ALL_CHANNELS)
    return [c.strip().lower() for c in raw.split(",") if c.strip()]


def channel_allowed(channel: str) -> bool:
    return channel.strip().lower() in allowed_channels()


def require_channel(channel: str) -> None:
    """Raise 402 unless `channel` is included in the plan.

    402 Payment Required rather than 403: this is not a permissions problem, and
    the distinction lets the admin UI offer an upgrade instead of an error.
    """
    if channel_allowed(channel):
        return
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=(
            f"The {channel.title()} channel is not included in your "
            f"{settings.PLAN_NAME or 'current'} plan. Upgrade at "
            f"https://commb.app to enable it."
        ),
    )


def require_custom_domain() -> None:
    if settings.PLAN_ALLOW_CUSTOM_DOMAIN:
        return
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=(
            f"Custom domains are not included in your "
            f"{settings.PLAN_NAME or 'current'} plan. Upgrade at https://commb.app."
        ),
    )


def _check_limit(current: int, limit: int, noun: str) -> None:
    # 0 means unlimited, which is what a self-hosted install always gets.
    if limit <= 0 or current < limit:
        return
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=(
            f"Your {settings.PLAN_NAME or 'current'} plan includes {limit} {noun}. "
            f"Upgrade at https://commb.app to add more."
        ),
    )


def require_product_capacity(current_count: int) -> None:
    _check_limit(current_count, settings.PLAN_MAX_PRODUCTS, "products")


def require_agent_capacity(current_count: int) -> None:
    _check_limit(current_count, settings.PLAN_MAX_AGENTS, "agents")


def require_knowledge_capacity(current_count: int) -> None:
    _check_limit(current_count, settings.PLAN_MAX_KNOWLEDGE_DOCS, "knowledge documents")


def plan_summary() -> dict:
    """What the admin UI shows, and what the cloud reads back for support."""
    return {
        "managed": is_managed(),
        "plan_name": settings.PLAN_NAME,
        "channels": allowed_channels(),
        "limits": {
            # None rather than 0 so the UI can render "Unlimited" without
            # having to know that 0 is a sentinel.
            "products": settings.PLAN_MAX_PRODUCTS or None,
            "agents": settings.PLAN_MAX_AGENTS or None,
            "knowledge_docs": settings.PLAN_MAX_KNOWLEDGE_DOCS or None,
        },
        "allow_custom_domain": settings.PLAN_ALLOW_CUSTOM_DOMAIN,
    }
