---
sidebar_position: 2
title: Access Groups & Scoping
description: Isolate catalog products and RAG documents per agent persona.
---

# Access Groups & Tag Scoping

**Access Groups** allow you to partition your business resources (Products and Knowledge Base documents) so different AI agents only see information relevant to their domain.

## How Access Scoping Works

```
┌────────────────────────────────────────────────────────┐
│                   CommB Workspace                       │
│                                                        │
│  ┌──────────────────────┐    ┌──────────────────────┐  │
│  │   "Sales" Group      │    │  "Support" Group     │  │
│  │  - Catalog Items     │    │  - Troubleshooting   │  │
│  │  - Pricing Sheets    │    │  - Warranty Docs     │  │
│  └──────────┬───────────┘    └──────────┬───────────┘  │
│             │                           │              │
│      ┌──────▼──────┐             ┌──────▼──────┐       │
│      │  Sales Bot  │             │ Support Bot │       │
│      └─────────────┘             └─────────────┘       │
└────────────────────────────────────────────────────────┘
```

1. **Global Access Items**: Products or Docs created without an assigned group are visible to **all** agents.
2. **Scoped Items**: When an item is assigned to one or more Access Groups, only agents that belong to those groups can search or recommend them.
3. **Shared LLM Keys**: An Access Group can store a dedicated LLM API Key (e.g., an Enterprise OpenAI key) that is automatically inherited by all member agents.
