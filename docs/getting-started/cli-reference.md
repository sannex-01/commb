---
sidebar_position: 3
title: CLI Reference
description: Complete command-line interface reference for the aicb terminal utility.
---

# AICB CLI Reference

When installing AICB via `pip install aicb` or developing locally, the `aicb` executable command is available in your shell.

---

## Commands

### `aicb start`

Starts the AICB FastAPI / Uvicorn server.

```bash
aicb start [OPTIONS]
```

#### Options

| Option | Flag | Description | Default |
|---|---|---|---|
| `--port` | `-p` | Port number to bind the server | `8422` (or `$PORT`) |
| `--host` | `-H` | Host IP address to bind | `0.0.0.0` (or `$HOST`) |
| `--db-url` | — | Custom async Database connection string | `sqlite+aiosqlite:///./aicb.db` |
| `--workers` | `-w` | Number of worker processes (production) | `1` |
| `--reload` | — | Enable hot code reloading for development | `False` |

#### Examples

```bash
# Start on default port 8422 with local SQLite database
aicb start

# Run in development mode with auto-reload
aicb start --reload

# Start on custom port with remote PostgreSQL instance
aicb start -p 8080 --db-url "postgresql+asyncpg://aicb_user:secret@db.internal:5432/aicb_prod"
```

---

### `aicb doctor`

Runs preflight health checks and system diagnostics.

```bash
aicb doctor
```

#### What It Checks
1. **Database Connectivity**: Validates dialect formatting (`asyncpg` / `aiosqlite`) and runs schema migrations.
2. **LLM Provider API**: Tests active model generation (Gemini, OpenAI, or Claude).
3. **Omnichannel Credentials**: Validates WhatsApp Cloud API, Telegram Bot token, and Webhook secret keys.
4. **Payment Gateways**: Checks Paystack and Stripe secret keys.
5. **AgentOS Remote Telemetry**: Verifies connection with Sannex AgentOS ingestion endpoints.

---

### `aicb version`

Displays the currently installed AICB platform release version.

```bash
aicb version
# Output: AICB Platform v0.1.0
```

