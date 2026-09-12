#!/usr/bin/env python3
"""
CommB Starter Kit & Production Preflight System Doctor
Validates environment variables, database access, LLM providers, and external services.
"""

import sys
import os
import asyncio
import httpx
from datetime import datetime

# Configure UTF-8 stdout if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.config import settings


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"[*] {title}")
    print("=" * 60)


async def check_database():
    print("\n[DB] 1. Database Connection Check...")
    try:
        from app.core.database import engine, init_db
        await init_db()
        print(f"  [OK] Database connected successfully! ({settings.DATABASE_URL.split('://')[0]})")
        return True
    except Exception as e:
        print(f"  [FAIL] Database initialization failed: {e}")
        return False


async def check_llm_provider():
    print(f"\n[AI] 2. LLM Provider Check (Active: {settings.LLM_PROVIDER.upper()})...")
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            print("  [WARN] GEMINI_API_KEY is not set in .env (add key for AI generation)")
            return True
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents="Ping! Reply with 'pong'.",
            )
            print(f"  [OK] Google Gemini ({settings.GEMINI_MODEL}) connected! Reply: {response.text.strip()}")
            return True
        except Exception as e:
            print(f"  [WARN] Gemini connection test failed: {e}")
            return False

    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            print("  [WARN] OPENAI_API_KEY is not set in .env")
            return True
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": "Ping! Reply with pong."}],
                max_tokens=10,
            )
            print(f"  [OK] OpenAI ({settings.OPENAI_MODEL}) connected! Reply: {response.choices[0].message.content.strip()}")
            return True
        except Exception as e:
            print(f"  [WARN] OpenAI connection test failed: {e}")
            return False

    elif provider == "claude":
        if not settings.ANTHROPIC_API_KEY:
            print("  [WARN] ANTHROPIC_API_KEY is not set in .env")
            return True
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "Ping! Reply with pong."}],
            )
            print(f"  [OK] Anthropic Claude ({settings.ANTHROPIC_MODEL}) connected! Reply: {response.content[0].text.strip()}")
            return True
        except Exception as e:
            print(f"  [WARN] Claude connection test failed: {e}")
            return False
    else:
        print(f"  [FAIL] Unknown LLM provider: {provider}")
        return False


async def check_channels():
    print("\n[CHANNELS] 3. Customer Channels Configuration...")
    ok = True

    # WhatsApp
    if settings.META_WHATSAPP_TOKEN and settings.META_PHONE_NUMBER_ID:
        print(f"  [OK] WhatsApp Cloud API configured (Phone Number ID: {settings.META_PHONE_NUMBER_ID})")
    else:
        print("  [INFO] WhatsApp: META_WHATSAPP_TOKEN or META_PHONE_NUMBER_ID not set (Fill to enable WhatsApp).")

    # Telegram
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe")
                if res.status_code == 200:
                    bot_data = res.json().get("result", {})
                    print(f"  [OK] Telegram Bot connected! (@{bot_data.get('username')})")
                else:
                    print(f"  [FAIL] Telegram Bot Token invalid: {res.text}")
        except Exception as e:
            print(f"  [WARN] Telegram ping failed: {e}")
    else:
        print("  [INFO] Telegram: TELEGRAM_BOT_TOKEN not set (Fill to enable Telegram bot).")

    # Slack
    if settings.SLACK_WEBHOOK_URL:
        print("  [OK] Slack Escalation Webhook configured.")
    else:
        print(f"  [INFO] Slack Webhook not set. Direct fallback contact ({settings.SUPPORT_PHONE_NUMBER} / {settings.SUPPORT_EMAIL}) will be used.")

    return ok


async def check_payments():
    print(f"\n[PAYMENTS] 4. Payment Gateways & Catalog...")
    print(f"  Active Catalog Source: {settings.CATALOG_SOURCE.upper()}")
    print(f"  Default Payment Gateway: {settings.DEFAULT_PAYMENT_GATEWAY.upper()}")

    # Paystack
    if settings.PAYSTACK_SECRET_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    "https://api.paystack.co/product",
                    headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
                )
                if res.status_code == 200:
                    print("  [OK] Paystack Secret Key is valid & Products API reachable.")
                else:
                    print(f"  [WARN] Paystack Auth check status: {res.status_code}")
        except Exception as e:
            print(f"  [WARN] Paystack ping failed: {e}")
    else:
        print("  [INFO] PAYSTACK_SECRET_KEY not set.")

    # Flutterwave
    if settings.FLUTTERWAVE_SECRET_KEY:
        print("  [OK] Flutterwave Secret Key is configured.")

    # Monnify
    if settings.MONNIFY_API_KEY and settings.MONNIFY_SECRET_KEY:
        print("  [OK] Monnify API credentials configured.")

    # Stripe
    if settings.STRIPE_SECRET_KEY:
        print("  [OK] Stripe Secret Key is configured.")

    return True


async def check_telemetry():
    print("\n[SYNC] 5. Telemetry & Remote Sync Check...")
    if not settings.COMMB_TELEMETRY_KEY:
        print("  [INFO] COMMB_TELEMETRY_KEY is not configured. Telemetry & remote the telemetry collector sync will run locally.")
        return True
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(
                f"{settings.COMMB_TELEMETRY_HOST.rstrip('/')}/v1/events",
                json={"batch": [{"channel": "healthcheck", "customer_id": "doctor_test", "event": "ping"}]},
                headers={"Authorization": f"Bearer {settings.COMMB_TELEMETRY_KEY}"}
            )
            if res.status_code in [200, 202]:
                print(f"  [OK] Telemetry collector connected successfully! ({settings.COMMB_TELEMETRY_HOST})")
                return True
            else:
                print(f"  [WARN] Telemetry collector returned status {res.status_code}: {res.text}")
                return False
    except Exception as e:
        print(f"  [WARN] Could not connect to telemetry collector: {e}")
        return False


async def main():
    print_header("CommB SYSTEM DOCTOR: ENVIRONMENT HEALTH CHECK")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"App Mode: {settings.BOT_MODE.upper()} | Env: {settings.ENVIRONMENT.upper()}")

    db_ok = await check_database()
    llm_ok = await check_llm_provider()
    channels_ok = await check_channels()
    payments_ok = await check_payments()
    telemetry_ok = await check_telemetry()

    print_header("SYSTEM DIAGNOSTIC SUMMARY")
    if db_ok:
        print("  [+] SUCCESS: CommB Engine is healthy and ready to run!")
        print("  [+] Start the server: commb start --port 8422")
        print("  [+] Or with Docker:   docker compose up -d\n")
    else:
        print("  [-] ATTENTION: Please review database configuration errors above.\n")


run_diagnostics = main


if __name__ == "__main__":
    asyncio.run(main())


