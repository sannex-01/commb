---
sidebar_position: 3
title: Messaging Channels
description: Connect WhatsApp Cloud API, Telegram Bot, and Website Widget.
---

# Messaging Channels

AICB natively supports omnichannel conversational commerce with unified session tracking.

## 1. WhatsApp Cloud API (Meta)

Connect official Meta WhatsApp Cloud API credentials in **Settings &rarr; Messaging Channels**:

- **System User Access Token**: Long-lived Meta API token with `whatsapp_business_messaging` permissions.
- **Phone Number ID**: 15-digit ID from the Meta Developer App Dashboard.
- **Webhook Verify Token**: Security verification token matching `META_VERIFY_TOKEN`.
- **Webhook URL**: `https://your-domain.com/api/v1/webhooks/whatsapp`

Supported rich formats: **Product Swipeable Carousels**, **Interactive List Messages**, and **Quick Reply Action Buttons**.

---

## 2. Telegram Bot API

Connect any Telegram Bot created via `@BotFather`:

- **Bot Token**: Provided by `@BotFather` (e.g., `123456789:ABCdef...`).
- **Auto Webhook Registration**: AICB auto-registers the Telegram Webhook and sets the generated secret token.
- **Webhook URL**: `https://your-domain.com/api/v1/webhooks/telegram/{agent_id}`

Supported rich formats: **Media Group Photo Albums** and **Inline Interactive Keyboards**.

---

## 3. Embeddable Website Widget

Embed the autonomous assistant on any website or e-commerce store with one script tag:

```html
<script 
  src="https://aicb.sannex.ng/widget.js" 
  data-bot-id="default" 
  async>
</script>
```

### Attributes:
- `data-bot-id`: The agent slug or ID to route chats to (e.g. `sales-bot` or `default`).
- Supports **Server-Sent Events (SSE)** for ultra-fast streaming responses and instant product cards.
