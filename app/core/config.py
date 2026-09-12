import os
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "CommB Assistant"
    APP_VERSION: str = "0.2.0"
    APP_SECRET: Optional[str] = None
    ENVIRONMENT: Literal["development", "production"] = "development"
    DEBUG: bool = True
    PORT: int = 8422
    HOST: str = "0.0.0.0"
    # Public base URL of THIS instance — used to build callback URLs and the
    # webhook endpoints registered with Telegram/WhatsApp/payment gateways.
    # Self-hosters must set this; there is deliberately no vendor default.
    COMMB_DOMAIN: Optional[str] = None
    BOT_DOMAIN: Optional[str] = None  # Alias accepted for the same value

    # Bot Operating Mode: 'conversational' | 'interactive_flow' | 'hybrid'
    BOT_MODE: Literal["conversational", "interactive_flow", "hybrid"] = "hybrid"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./commb.db"

    # Memory & Session
    SESSION_EXPIRY_HOURS: int = 24
    MEMORY_WINDOW_SIZE: int = 10

    # LLM Providers & Active Setting
    LLM_PROVIDER: Literal["gemini", "openai", "claude"] = "gemini"

    # Gemini
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Claude
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-20241022"

    # Baseline LLM Config
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 1024
    DEFAULT_SYSTEM_PROMPT: str = (
        "You are a helpful, professional AI business assistant. You assist customers with product inquiries, "
        "order placement, payments, and general customer service. Always be concise, warm, and helpful."
    )

    # WhatsApp Cloud API (Meta)
    META_WHATSAPP_TOKEN: Optional[str] = None
    META_PHONE_NUMBER_ID: Optional[str] = None
    META_BUSINESS_ACCOUNT_ID: Optional[str] = None
    META_APP_SECRET: Optional[str] = None
    META_VERIFY_TOKEN: str = "commb_webhook_verification_token_secret"
    WHATSAPP_FLOW_PRIVATE_KEY: Optional[str] = None
    WHATSAPP_FLOW_PRIVATE_KEY_PASSPHRASE: Optional[str] = None
    # The business's human-dialable WhatsApp number in E.164, e.g. "2348012345678"
    # (no "+", no leading 0) — used to build wa.me/<number> deep links. Distinct
    # from META_PHONE_NUMBER_ID, which is Cloud API's internal numeric ID and
    # cannot be used to build a wa.me link.
    WHATSAPP_BUSINESS_PHONE_NUMBER: Optional[str] = None

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_USERNAME: Optional[str] = None  # e.g. "my_store_bot" (no @) — used to build t.me/<username> deep links
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None
    TELEGRAM_PAYMENT_PROVIDER_TOKEN: Optional[str] = None

    # Escalations & Slack
    SLACK_WEBHOOK_URL: Optional[str] = None
    SUPPORT_PHONE_NUMBER: str = "+2348000000000"
    SUPPORT_EMAIL: str = "support@example.com"

    # Catalog Provider: 'local' | 'paystack' | 'bumpa'
    CATALOG_SOURCE: Literal["local", "paystack", "bumpa"] = "local"

    # Bumpa — real API confirmed against docs.bumpa.io: base path is
    # /api/commerce/v1, split auth (a "public key" for catalog/cart/checkout,
    # a "secret key" for merchant order/analytics routes). BUMPA_API_KEY is
    # kept as the secret-key env fallback (matches what was already deployed
    # for catalog import); BUMPA_PUBLIC_API_KEY is new, needed for the
    # customer-facing cart/checkout endpoints.
    BUMPA_API_KEY: Optional[str] = None
    BUMPA_PUBLIC_API_KEY: Optional[str] = None
    BUMPA_STORE_ID: Optional[str] = None
    BUMPA_API_BASE_URL: str = "https://api.getbumpa.com/api/commerce/v1"

    # Payments
    DEFAULT_PAYMENT_GATEWAY: Literal["paystack", "flutterwave", "monnify", "stripe"] = "paystack"
    PAYSTACK_SECRET_KEY: Optional[str] = None
    PAYSTACK_PUBLIC_KEY: Optional[str] = None
    PAYSTACK_CALLBACK_URL: str = ""  # Auto-derived from COMMB_DOMAIN if empty
    FLUTTERWAVE_SECRET_KEY: Optional[str] = None
    FLUTTERWAVE_PUBLIC_KEY: Optional[str] = None
    FLUTTERWAVE_SECRET_HASH: Optional[str] = None
    MONNIFY_API_KEY: Optional[str] = None
    MONNIFY_SECRET_KEY: Optional[str] = None
    MONNIFY_CONTRACT_CODE: Optional[str] = None
    MONNIFY_BASE_URL: str = "https://sandbox.monnify.com"

    # Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_SUCCESS_URL: str = "https://yourdomain.com/payments/stripe/success"
    STRIPE_CANCEL_URL: str = "https://yourdomain.com/payments/stripe/cancel"

    # Media & Storage (Cloudinary / Cloudflare R2)
    STORAGE_PROVIDER: Literal["cloudinary", "cloudflare_r2", "local"] = "cloudinary"
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None
    CLOUDINARY_FOLDER: str = "commb_assets"

    R2_ACCOUNT_ID: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_BUCKET_NAME: Optional[str] = None
    R2_PUBLIC_URL: Optional[str] = None

    COMMB_API_KEY: Optional[str] = None

    # Optional telemetry backend. Disabled by default: a self-hosted CommB
    # instance must never phone home. Set COMMB_TELEMETRY_KEY (and optionally
    # a host) to send analytics to a compatible collector, e.g. Commb.app.
    COMMB_TELEMETRY_KEY: Optional[str] = None
    COMMB_TELEMETRY_HOST: Optional[str] = None
    SYNC_INTERVAL_MINUTES: int = 30
    SYNC_INTERVAL_HOURS: Optional[int] = None
    ENABLE_TELEMETRY: bool = False

    # Host PostHog Analytics (Optional)
    POSTHOG_API_KEY: Optional[str] = None
    POSTHOG_HOST: str = "https://us.i.posthog.com"

    # Instance Identity
    INSTANCE_ID: Optional[str] = None

    def model_post_init(self, __context) -> None:
        # Fall back to the local server address rather than a vendor domain so
        # a fresh self-hosted instance boots without any CommB-owned host.
        domain = self.COMMB_DOMAIN or self.BOT_DOMAIN or f"http://localhost:{self.PORT}"
        self.COMMB_DOMAIN = domain
        self.BOT_DOMAIN = domain

        if not self.INSTANCE_ID:
            instance_file = os.path.join(os.path.dirname(__file__), "..", "..", ".instance_id")
            if os.path.exists(instance_file):
                try:
                    with open(instance_file, "r") as f:
                        self.INSTANCE_ID = f.read().strip()
                except Exception:
                    pass
            if not self.INSTANCE_ID:
                import uuid
                new_id = uuid.uuid4().hex
                self.INSTANCE_ID = new_id
                try:
                    with open(instance_file, "w") as f:
                        f.write(new_id)
                except Exception:
                    pass


settings = Settings()


def get_settings() -> Settings:
    return settings

