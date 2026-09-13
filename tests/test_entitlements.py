"""Entitlement tests.

The most important case here is the FIRST one: a self-hosted CommB must be
completely unlimited. CommB is AGPL-3.0 and every feature belongs to everyone;
CommB Cloud sells operations, not access. If a future change makes the
self-hosted product worse, these tests should fail loudly.
"""

import pytest
from fastapi import HTTPException

from app.core import entitlements
from app.core.config import settings


@pytest.fixture(autouse=True)
def reset_plan():
    """Each test starts from the self-hosted defaults."""
    original = (
        settings.PLAN_NAME,
        settings.PLAN_CHANNELS,
        settings.PLAN_MAX_PRODUCTS,
        settings.PLAN_MAX_AGENTS,
        settings.PLAN_MAX_KNOWLEDGE_DOCS,
        settings.PLAN_ALLOW_CUSTOM_DOMAIN,
    )
    settings.PLAN_NAME = None
    settings.PLAN_CHANNELS = None
    settings.PLAN_MAX_PRODUCTS = 0
    settings.PLAN_MAX_AGENTS = 0
    settings.PLAN_MAX_KNOWLEDGE_DOCS = 0
    settings.PLAN_ALLOW_CUSTOM_DOMAIN = True
    yield
    (
        settings.PLAN_NAME,
        settings.PLAN_CHANNELS,
        settings.PLAN_MAX_PRODUCTS,
        settings.PLAN_MAX_AGENTS,
        settings.PLAN_MAX_KNOWLEDGE_DOCS,
        settings.PLAN_ALLOW_CUSTOM_DOMAIN,
    ) = original


# ---------------------------------------------------------------------------
# The open-source guarantee
# ---------------------------------------------------------------------------

def test_self_hosted_install_is_completely_unlimited():
    """No PLAN_* set: every channel, no caps, custom domains allowed."""
    assert entitlements.is_managed() is False

    for channel in ("widget", "telegram", "whatsapp"):
        entitlements.require_channel(channel)  # must not raise

    entitlements.require_custom_domain()

    # Deliberately absurd counts: there is no ceiling without a plan.
    entitlements.require_product_capacity(1_000_000)
    entitlements.require_agent_capacity(1_000_000)
    entitlements.require_knowledge_capacity(1_000_000)


def test_self_hosted_plan_summary_advertises_no_plan():
    """The admin UI uses this to hide plan and upgrade wording entirely."""
    summary = entitlements.plan_summary()
    assert summary["managed"] is False
    assert summary["plan_name"] is None
    assert summary["channels"] == ["widget", "telegram", "whatsapp"]
    assert summary["limits"] == {"products": None, "agents": None, "knowledge_docs": None}
    assert summary["allow_custom_domain"] is True


# ---------------------------------------------------------------------------
# Managed instances
# ---------------------------------------------------------------------------

def test_channel_outside_the_plan_is_refused():
    settings.PLAN_NAME = "Starter"
    settings.PLAN_CHANNELS = "widget,telegram"

    entitlements.require_channel("widget")
    entitlements.require_channel("telegram")

    with pytest.raises(HTTPException) as exc:
        entitlements.require_channel("whatsapp")
    # 402, not 403: this is a billing state, so the UI can offer an upgrade
    # rather than showing a permissions error.
    assert exc.value.status_code == 402
    assert "Starter" in exc.value.detail


def test_limits_allow_up_to_the_cap_then_refuse():
    settings.PLAN_NAME = "Starter"
    settings.PLAN_MAX_PRODUCTS = 50

    entitlements.require_product_capacity(0)
    entitlements.require_product_capacity(49)  # creating the 50th

    with pytest.raises(HTTPException) as exc:
        entitlements.require_product_capacity(50)  # would be the 51st
    assert exc.value.status_code == 402


def test_zero_means_unlimited_even_on_a_named_plan():
    """An unlimited tier sets the limit to 0 rather than a large number."""
    settings.PLAN_NAME = "Business"
    settings.PLAN_MAX_PRODUCTS = 0
    entitlements.require_product_capacity(999_999)


def test_custom_domain_gate():
    settings.PLAN_NAME = "Growth"
    settings.PLAN_ALLOW_CUSTOM_DOMAIN = False
    with pytest.raises(HTTPException) as exc:
        entitlements.require_custom_domain()
    assert exc.value.status_code == 402

    settings.PLAN_ALLOW_CUSTOM_DOMAIN = True
    entitlements.require_custom_domain()


def test_channel_list_tolerates_untidy_configuration():
    """PLAN_CHANNELS is set by an operator, so parsing must be forgiving."""
    settings.PLAN_NAME = "Growth"
    settings.PLAN_CHANNELS = " Widget , WHATSAPP ,, "
    assert entitlements.allowed_channels() == ["widget", "whatsapp"]
    entitlements.require_channel("whatsapp")
    with pytest.raises(HTTPException):
        entitlements.require_channel("telegram")


def test_empty_channel_string_means_all_channels_not_none():
    """An empty value must not be read as 'no channels allowed'."""
    settings.PLAN_NAME = "Starter"
    settings.PLAN_CHANNELS = "   "
    assert entitlements.allowed_channels() == ["widget", "telegram", "whatsapp"]
    entitlements.require_channel("whatsapp")
