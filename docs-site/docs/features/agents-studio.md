---
sidebar_position: 1
title: Multi-Agent Studio
description: Create and configure specialized AI assistant personas.
---

# Multi-Agent Studio

The **Multi-Agent Studio** allows businesses to deploy multiple AI agents from a single CommB instance. Each agent can represent a distinct role or brand personality (e.g. *Sales Consultant*, *Technical Support*, *VIP Concierge*).

## Creating an AI Agent

Navigate to **Admin Portal &rarr; AI Agents Studio &rarr; Create Agent**.

### 1. Persona & Identity
- **Agent Name**: Display name shown in transcripts and widget panels.
- **Agent Slug**: URL-safe identifier (e.g. `sales-bot`, `support-rep`).
- **System Prompt**: Core instructions defining persona, voice, tone, and operational boundaries.

### 2. Brain & LLM Engine
- **Provider**: Select Gemini, OpenAI, Claude (Anthropic), or Groq.
- **Model**: e.g., `gemini-2.5-flash`, `gpt-4o`, `claude-3-5-sonnet-20241022`.
- **Temperature**: Control creativity (0.0 = deterministic, 1.0 = creative).
- **Provider API Key Override**: Optional custom API key specific to this agent.

### 3. Access Groups & Tag Scoping
Select one or more **Access Groups** (e.g. `sales`, `wholesale`, `tech_support`) to restrict what catalog products and knowledge base documents the agent can reference.

### 4. Messaging Channel Credentials
Connect dedicated channel numbers or tokens:
- **WhatsApp**: Dedicated WhatsApp Phone Number ID & Access Token.
- **Telegram**: Dedicated Telegram Bot Token & Webhook auto-registration.
- **Website Widget**: Embeddable script with custom launcher positioning and profile capture mode.
