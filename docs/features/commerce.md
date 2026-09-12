---
sidebar_position: 4
title: Conversational Commerce & Payments
description: Automated cart management, checkout links, and Paystack integration.
---

# Conversational Commerce & Payments

CommB turns chat conversations into instant revenue by managing customer carts, collecting delivery profiles, and generating real-time payment links.

## Dynamic Paystack Integration

CommB natively integrates with **Paystack** for multi-currency processing (`NGN`, `USD`, `GHS`, `KES`, `ZAR`):

1. Configure your **Paystack Secret Key** and **Public Key** in **Settings &rarr; Payment Gateways**.
2. CommB dynamically queries your Paystack merchant account to verify supported currencies.
3. Configure your webhook endpoint: `https://your-domain.com/api/v1/webhooks/paystack`.

---

## The Conversational Checkout Flow

```
[Customer] "I want to buy 2 wireless earbuds"
   │
   ▼
[CommB Flow Engine]
   ├─ Checks catalog inventory & pricing
   ├─ Adds item to session cart
   ├─ Turn-by-turn or upfront profile collection (Name, Email, Delivery Address)
   ├─ Generates Paystack Hosted Checkout URL
   └─ Dispatches interactive Payment Link with reference
   │
   ▼
[Customer Pays on Paystack]
   │
   ▼
[Paystack Webhook] --> POST /api/v1/webhooks/paystack
   ├─ Verifies HMAC SHA512 signature
   ├─ Updates Order status to 'paid'
   ├─ Increments Agent revenue & order counters
   └─ Sends instant confirmation receipt to Customer on chat
```
