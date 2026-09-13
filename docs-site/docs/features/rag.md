---
sidebar_position: 5
title: Knowledge Base & RAG
description: Ground AI agent responses in company FAQs, policies, and documentation.
---

# Knowledge Base & RAG

**Retrieval-Augmented Generation (RAG)** ensures your AI agents answer customer questions with 100% accurate, business-specific knowledge rather than hallucinating.

## Uploading Documents

Under **Admin Portal &rarr; Knowledge Base**, you can upload:
- Text files, PDFs, or Markdown documents (`.md`, `.txt`, `.pdf`).
- Paste raw FAQ text directly into the web interface.
- Assign documents to specific **Access Groups** (e.g. internal support SOPs vs public FAQ).

## Hybrid Vector Search & Injection

1. **Chunking & Embeddings**: Uploaded documents are split into semantic chunks and embedded with vector representations.
2. **Dynamic Top-K Retrieval**: When a customer asks a question, CommB queries the vector store, filters by the agent's authorized access tags, and retrieves the most relevant knowledge chunks.
3. **Context Grounding**: Retrieved context is injected directly into the LLM system prompt for accurate and grounded replies.
