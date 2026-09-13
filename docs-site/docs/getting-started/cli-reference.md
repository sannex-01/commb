---
sidebar_position: 3
title: CLI Reference
description: Complete command-line interface reference for the commb terminal utility.
---

# CommB CLI Reference

When installing CommB via `pip install commb` or developing locally, the `commb` executable command is available in your shell.

---

## Commands

### `commb start`

Starts the CommB FastAPI / Uvicorn server.

```bash
commb start [OPTIONS]
```

#### Options

| Option | Flag | Description | Default |
|---|---|---|---|
| `--port` | `-p` | Port number to bind the server | `8422` (or `$PORT`) |
| `--host` | `-H` | Host IP address to bind | `0.0.0.0` (or `$HOST`) |
| `--db-url` | — | Custom async Database connection string | `sqlite+aiosqlite:///./commb.db` |
| `--workers` | `-w` | Number of worker processes (production) | `1` |
| `--reload` | — | Enable hot code reloading for development | `False` |

#### Examples

```bash
# Start on default port 8422 with local SQLite database
commb start

# Run in development mode with auto-reload
commb start --reload

# Start on custom port with remote PostgreSQL instance
commb start -p 8080 --db-url "postgresql+asyncpg://commb_user:secret@db.internal:5432/commb_prod"
```

---

### `commb doctor`

Runs preflight health checks and system diagnostics.

```bash
commb doctor
```

#### What It Checks
1. **Database Connectivity**: Validates dialect formatting (`asyncpg` / `aiosqlite`) and runs schema migrations.
2. **LLM Provider API**: Tests active model generation (Gemini, OpenAI, or Claude).
3. **Omnichannel Credentials**: Validates WhatsApp Cloud API, Telegram Bot token, and Webhook secret keys.
4. **Payment Gateways**: Checks Paystack and Stripe secret keys.
5. **AgentOS Remote Telemetry**: Verifies connection with CommB Cloud ingestion endpoints.

---

### `commb version`

Displays the currently installed CommB platform release version.

```bash
commb version
# Output: CommB Platform v0.1.0
```

