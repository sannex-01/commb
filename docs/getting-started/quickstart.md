---
sidebar_position: 1
title: Quickstart Guide
description: Launch your self-hosted AICB assistant using Docker Compose or standalone pip.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# AICB Quickstart Guide

Get a production-ready AICB instance running in under 2 minutes. You can deploy using **Docker Compose** or install directly via **Python (`pip install aicb`)**.

---

## Choose Your Installation Method

<Tabs>
<TabItem value="docker" label="🐳 Docker Compose (Recommended)" default>

### 1. Clone & Configure

```bash
# Clone the open-source repository
git clone https://github.com/sannex-tech/aicb.git
cd aicb

# Copy environment variables template
cp .env.example .env
```

Edit `.env` with your preferred AI provider:

```ini
# Core Security
APP_SECRET=generate-a-strong-random-secret-key-here
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...

# Optional Database (Defaults to SQLite if omitted)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/aicb
```

### 2. Start Services

```bash
docker compose up -d
```

Verify that the containers are healthy:

```bash
docker compose ps
```

Your AICB assistant is now running at `http://localhost:8422`!

</TabItem>
<TabItem value="pip" label="🐍 Python Package (pip)">

### 1. Install AICB via pip

AICB can be installed standalone without Docker on any machine running Python 3.10+:

```bash
pip install aicb
```

### 2. Run Preflight Diagnostics

Validate your environment and database connection:

```bash
aicb doctor
```

### 3. Start the Server

```bash
# Start with default SQLite database on port 8422
aicb start

# Or supply a custom PostgreSQL / MySQL database URL
aicb start --db-url "postgresql+asyncpg://user:password@localhost:5432/aicb" --port 8422
```

</TabItem>
</Tabs>

---

## First-Run Setup Wizard

Once your server is running, navigate to `http://localhost:8422/_/admin/setup` in your browser.

```mermaid
graph LR
    A["Visit /setup"] --> B["Create Admin Account"]
    B --> C["Configure Business Identity & Currency"]
    C --> D["Generate Live Master API Key"]
    D --> E["Access Admin Dashboard"]
```

1. **Create Administrator Account**: Enter your Name, Email, and Master Password.
2. **Business Identity**: Enter your Business Name and Currency (e.g. `NGN`, `USD`, `GHS`, `KES`, `EUR`).
3. **Master API Key**: The wizard securely generates your platform's live API key (`aicb_live_...`).
4. **Permanent Idempotency Lockout**: Once configured, the `/setup` route is permanently locked to protect against unauthorized resets.

---

## Access the Admin Portal

Log in to the management dashboard at:
👉 `http://localhost:8422/_/admin/login`

From the Admin Dashboard, you can:
- 🤖 Customize your AI Assistant prompt & behavioral persona
- 📦 Add store products and configure automated order handling
- 💬 Connect Meta WhatsApp Cloud API, Telegram, or embed the Website Widget
- 👥 Manage human agent access groups, assignments, and conversation escalations
