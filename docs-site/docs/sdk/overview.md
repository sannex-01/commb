---
sidebar_position: 1
title: Sannex Agent SDK Overview
description: Official SDKs for Python and JavaScript / TypeScript.
---

# Sannex Agent SDK Overview

The **Sannex Agent SDK** provides dual-package parity for integrating custom agents, backend services, and e-commerce platforms with AgentOS.

## Dual-Package Parity Standard

Both SDKs expose the exact same public API surface, parameter schemas, and fire-and-forget telemetry batching behavior.

| Feature | Python (`commb-agent`) | JavaScript / TypeScript (`@commb/agent`) |
|---|---|---|
| **Package Manager** | `pip install commb-agent` | `npm install @commb/agent` |
| **Sync Client** | `SannexClient` | `SannexClient` |
| **Async Client** | `AsyncSannexClient` | Native Promise-based client |
| **Telemetry Tracking** | `client.track(...)` | `client.track(...)` |
| **Conversation Sync** | `client.sync_conversation(...)` | `client.syncConversation(...)` |
| **Remote Config** | `client.get_config()` | `await client.getConfig()` |
| **Health Ping** | `client.ping()` | `await client.ping()` |

---

## Python SDK Quickstart

```python
from sannex_agent import SannexClient

client = SannexClient(
    api_key="commb_live_...",
    base_url="https://commb.app"
)

# Track an event (Fire-and-forget background queue)
client.track(
    channel="whatsapp",
    customer_id="+2348012345678",
    event="payment_success",
    amount=25000.0,
    metadata={"order_id": "ORD-1234"}
)
```

---

## TypeScript / Node.js Quickstart

```typescript
import { SannexClient } from '@commb/agent';

const client = new SannexClient({
  apiKey: 'commb_live_...',
  baseUrl: 'https://commb.app',
});

// Track an event
client.track({
  channel: 'widget',
  customerId: 'session_abc123',
  event: 'catalog_view',
  metadata: { productId: 42 },
});
```
