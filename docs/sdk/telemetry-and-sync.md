---
sidebar_position: 2
title: Telemetry & Remote Sync Protocol
description: Architecture of background event batching and remote config sync.
---

# Telemetry & Remote Sync Protocol

AgentOS ingestion is built with a **fire-and-forget** resilient design so telemetry tracking never blocks the host application or fails a customer checkout request.

## Event Batching Lifecycle

1. **In-Memory Queue**: Calls to `client.track()` append the event payload to an in-memory queue.
2. **Periodic Flusher**:
   - In Python, a background daemon thread flushes batches every 5 seconds or when 20 events accumulate.
   - In JavaScript/TypeScript, a `setInterval` worker flushes queued batches via native `fetch`.
3. **Silent Error Handling**: If AgentOS is unreachable or temporarily offline, events are discarded safely without raising uncaught exceptions in the host process.

---

## Remote Configuration Pull

At application boot, instances call `GET /api/v1/sync` to fetch:
- Organization branding and tenant status.
- Available system updates and release notes.
- Recommended prompt tuning parameters.
