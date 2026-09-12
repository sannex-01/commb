# CommB — Commercial Bots

Open-source AI commerce bots for WhatsApp Cloud API, Telegram, and an embeddable website widget, with conversational commerce powered by Paystack and Bumpa.

**Self-host it for free, forever.** CommB is a complete, standalone application — there is no vendor lock-in, no phone-home telemetry, and no paid tier hiding features. If you would rather not run it yourself, managed hosting is available at [commb.app](https://commb.app).

```bash
docker run -p 8422:8000 samakins/commb:latest
# then open http://localhost:8422/_/admin
```

---

## Architecture & Deployment

CommB runs as a standalone, autonomous conversational commerce hub with a built-in single-page admin UI at **`/_/admin`**. One instance serves one business, backed entirely by its own database — which is what makes it trivial to self-host and to run isolated per-tenant instances.

### 1. Standalone Multi-Agent Instance

A single CommB instance runs its own complete admin studio at **`/_/admin`**, backed entirely by its database (SQLite in development, PostgreSQL in production):

- **First-Run Onboarding (`/_/admin/setup`)**: Instantly creates the Super Admin account and business profile with store currency and brand assets.
- **Multi-Agent Studio (`/_/admin/agents`)**: Deploy multiple distinct AI personas on the same deployment. Each agent can configure its own system prompt, LLM provider (Google Gemini, OpenAI, Groq, Anthropic), model parameters, access groups, and messaging channel credentials.
- **Messaging Channels**:
  - **WhatsApp Cloud API**: Interactive buttons, list pickers, carousels, and encrypted Meta flows.
  - **Telegram Bot**: Automated webhook registration upon agent creation, inline secret token rotators, and interactive keyboards.
  - **Website Widget**: Embeddable single-line script tag (`<script src="https://commb.app/widget.js" data-bot-id="default" async></script>`).
- **Unified Commerce & Payments**: Direct integration with **Paystack** for automated checkout generation and instant order confirmations across conversations.
- **Knowledge Base (RAG) & Catalog**: In-process hybrid BM25 + vector search and catalog scoping via access tags and access groups.
- **Platform API Keys**: One-click generation and instant rotation for secure programmatic API access (`commb_live_...`).

### 2. Optional Telemetry (off by default)

A self-hosted CommB instance never phones home. Telemetry is disabled unless you
explicitly enable it and point it at a collector, and the SDK that implements it
is an optional extra:

```bash
pip install "commb[telemetry]"
# then set ENABLE_TELEMETRY=true and COMMB_TELEMETRY_KEY / COMMB_TELEMETRY_HOST
```

With it enabled, release notes are synced into the admin UI's releases drawer and
usage analytics are dispatched in the background. With it disabled — the default —
every one of those code paths is a no-op.

---

## Key Features

1. **Messaging Channels**:
   - **WhatsApp Cloud API**: Text messages, Quick-Reply Interactive Buttons, List Pickers, Interactive Media Carousels, and Interactive WhatsApp Flows.
   - **Telegram**: Text messages, Inline Keyboards, automatic webhook synchronization (`setWebhook`), and in-place secret token rotators.
   - **Website Widget**: Lightweight embeddable chat widget with product card browsing, responsive drawer, dark/light theme, and direct checkout handoff.
   - **Slack Escalation**: Seamless handoff to human agents via Slack incoming webhooks.

2. **Multi-LLM Provider Engine**:
   - Out-of-the-box support for **Google Gemini**, **OpenAI GPT**, **Groq**, and **Anthropic Claude**.
   - Model parameters (`temperature`, `model_name`, `max_tokens`, `system_prompt`) configured per agent.
   - Per-agent API key overrides or centralized `.env` fallback.

3. **Multi-Source Catalog & Knowledge Base (RAG)**:
   - Synchronizes products from **Paystack Products**, **Bumpa Store**, or local database.
   - Smart multi-word keyword ranking (`CatalogManager.search_products`).
   - Access-group tagging for restricted product visibility across specific agents.
   - Grounded RAG document ingestion for accurate business FAQs and policies.

4. **Paystack Payment Gateway**:
   - Generates secure, instant checkout links and handles webhook events (`/api/v1/payments/webhook/paystack`).
   - Multi-currency support (`NGN`, `USD`, `GHS`, `KES`, `ZAR`, `EUR`, `GBP`).
   - Automatic order status confirmation and real-time customer messaging notifications upon payment receipt.

5. **Customer Profiles & Order Tracking**:
   - Pre-checkout customer detail collection (Name, Email, Phone).
   - "My Purchases" and order status lookup directly from chat conversations.
   - Customer directory in Admin UI with lifetime value and order history.

6. **Interactive Overview & Setup Guide**:
   - Onboarding milestone checklist on the dashboard overview (`/_/admin/overview`) with real-time completion tracking.
   - Multi-Agent Studio empty state with instant agent creation wizards.

---

## Quick Start

### 1. Configure Environment
```bash
cp .env.example .env
# Configure DATABASE_URL, APP_SECRET, and optional COMMB_TELEMETRY_KEY
```

### 2. Run Pre-flight System Doctor
```bash
python doctor.py
```

### 3. Start Local Server
```bash
# Using Python / Uvicorn
uvicorn app.main:app --port 8422 --reload

# Or using Docker Compose
docker compose up -d
```

### 4. First Run Onboarding
Open [http://localhost:8422/_/admin](http://localhost:8422/_/admin) to complete the setup wizard and launch your AI agents.

Open [http://localhost:8422/docs](http://localhost:8422/docs) to explore the interactive OpenAPI documentation.

---

## Webhook & API Endpoints

| Service | Endpoint | Method |
| :--- | :--- | :--- |
| **WhatsApp Cloud API** | `/api/v1/webhooks/whatsapp` | `GET` (Challenge), `POST` (Updates) |
| **Telegram Bot API** | `/api/v1/webhooks/telegram` or `/api/v1/webhooks/telegram/{agent_id}` | `POST` (Updates & Commands) |
| **Paystack Webhook** | `/api/v1/payments/webhook/paystack` | `POST` (Charge events) |
| **Bumpa Webhook** | `/api/v1/webhooks/bumpa` | `POST` (Product/Order updates) |
| **Manual Releases Sync** | `/api/v1/sync` | `POST` (Triggers remote release sync, if telemetry is enabled) |
| **Setup Wizard** | `/api/v1/setup/status`, `/api/v1/setup/initialize` | `GET`, `POST` (First-run onboarding) |
| **Admin Auth** | `/api/v1/auth/login`, `/api/v1/auth/me`, `/api/v1/auth/logout` | `POST`, `GET`, `POST` |
| **Multi-Agent CRUD** | `/api/v1/agents` | `GET`, `POST`, `PUT /{id}`, `DELETE /{id}` |
| **Access Groups** | `/api/v1/access-groups` | `GET`, `POST`, `PUT /{id}`, `DELETE /{id}` |
| **Team Accounts** | `/api/v1/users` | `GET`, `POST`, `PUT /{id}`, `DELETE /{id}` |
| **Platform Settings** | `/api/v1/settings/profile`, `/api/v1/settings/payments` | `GET`, `PUT` |
| **Admin Dashboard UI** | `/_/admin` | `GET` (SPA) |

---

## Project Structure

```text
commb/
├── app/
│   ├── main.py                     # FastAPI application & lifespan
│   ├── admin_ui/                   # Standalone Admin SPA (served at /_/admin)
│   │   └── dist/js/pages/          # Overview, Agents, Catalog, RAG, Orders, Users, Settings
│   ├── api/                        # REST APIs (setup, auth, users, agents, access groups, settings, overview)
│   ├── core/                       # Config, database, security (JWT, platform keys, webhook verifiers)
│   ├── channels/                   # WhatsApp, Telegram, Slack, Website Widget handlers
│   ├── commerce/                   # CartManager, Catalog & Paystack integration, image storage
│   ├── ai/                         # Multi-LLM providers (Gemini, OpenAI, Groq, Claude), RAG & memory
│   ├── flows/                      # Deterministic 0-token fast-path conversational engine
│   ├── telemetry/                  # Optional telemetry dispatcher & release sync worker
│   └── models/                     # SQLAlchemy models (Customer, Order, CatalogItem, BusinessProfile, AdminUser, Agent, AccessGroup)
├── widget/                         # Embeddable website chat widget (Vite, builds to widget.js)
├── doctor.py                       # Pre-flight diagnostic tool
├── Dockerfile                      # Production container image
├── docker-compose.yml              # Local development compose (port 8422)
├── docker-compose.prod.yml         # Production deployment stack
├── requirements.txt
└── .env.example
```

---

## Authentication Model

| Mechanism | Direction | Used for | Configured via |
| :--- | :--- | :--- | :--- |
| `commb_live_...` platform key | External caller → CommB API | Programmatic API access | Generated and rotated from `/_/admin/settings` |
| Admin JWT session | Browser → CommB Admin | `/_/admin` dashboard sessions | Signed with `APP_SECRET`, issued by `/api/v1/auth/login` |
| `COMMB_TELEMETRY_KEY` | CommB → telemetry collector | Telemetry & Release Notes synchronization | `.env` |
| Webhook Secrets | Provider → CommB | Meta, Telegram & Paystack verification | Verified cryptographically with rotation support |

---

## Licence

CommB is licensed under the **GNU Affero General Public License v3.0 or later**
([AGPL-3.0-or-later](LICENSE)).

In plain terms:

- **Self-hosting is free and unrestricted.** Run it for your own business, modify
  it, and you owe nothing to anyone.
- **If you modify CommB and offer it to others over a network**, you must make
  your modified source available to those users under the same licence.
- Copyright © 2026 **Sannex Tech LTD**.

Managed hosting at [commb.app](https://commb.app) is a separate, optional
commercial service — it sells convenience (provisioning, backups, custom domains,
support), never features withheld from this repository.
