---
sidebar_position: 2
title: Coolify & VPS Deployment
description: Deploy AICB on Coolify or any cloud server with automated SSL.
---

# Deploying on Coolify & Cloud VPS

[Coolify](https://coolify.io/) is an open-source, self-hosted PaaS alternative to Heroku/Render that provides automated SSL certificates, zero-downtime deployments, and database backups.

## 1. Add Application in Coolify

1. Open your Coolify Dashboard and click **+ Create New Resource** &rarr; **Application**.
2. Select **Public / Private Git Repository**.
3. Repository URL: `https://github.com/sannex-tech/aicb.git`
4. Branch: `main`
5. Build Pack: **Docker Compose**

---

## 2. Environment Variables Configuration

Under **Configuration &rarr; Environment Variables**, add:

```env
APP_SECRET_KEY=your-random-32-char-secret
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
PORT=8422
```

Attach a managed **PostgreSQL** database service in Coolify and bind `DATABASE_URL`.

---

## 3. Custom Domain & Reverse Proxy

Set your public FQDN (e.g. `https://assistant.yourbrand.com`). Coolify will automatically provision a Let's Encrypt SSL certificate.

---

## 4. Webhook Configuration

Point your WhatsApp Cloud API and Telegram Webhooks to your domain:
- **WhatsApp Webhook URL**: `https://assistant.yourbrand.com/api/v1/webhooks/whatsapp`
- **Telegram Webhook URL**: `https://assistant.yourbrand.com/api/v1/webhooks/telegram`
- **Website Widget**: `https://assistant.yourbrand.com/widget.js`
