import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.commerce.payments.unified import UnifiedPaymentManager
from app.core.logger import logger


def shipping_context_from_address(shipping_address: Optional[str]) -> Optional[Dict[str, Any]]:
    """commb stores shipping_address as a single free-text string; Bumpa's
    /shipping-options (called by BumpaClient.checkout_via_bumpa before
    Create Checkout) needs REAL structured street/city/state/country/zip to
    rate a shipment — a blank city/state/country will very likely make
    Bumpa's own rating fail or return zero options, not a graceful partial
    match. commb has no structured address collection today (only this one
    free-text field), so this is a known, real limitation: Bumpa checkout
    only works reliably once a business's customer actually supplies a full
    structured address elsewhere. Not silently faking city/state/country
    here — leaving them blank surfaces as Bumpa's own "no shipping options"
    error (see checkout_via_bumpa), which is at least an honest failure
    rather than a wrong delivery quote."""
    if not shipping_address:
        return None
    return {"street": shipping_address, "city": "", "state": "", "country": "", "zip": ""}


async def create_checkout_orders(
    db: AsyncSession,
    items: List[Dict[str, Any]],
    currency: str,
    customer_identifier: Optional[str],
    channel: Optional[str],
    customer_name: Optional[str],
    customer_email: Optional[str],
    customer_phone: Optional[str],
    shipping_address: Optional[str] = None,
    gateway: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Creates one or more Order rows from a cart and generates a checkout
    link for each, splitting the cart when it contains a mix of
    Bumpa-sourced items and everything else — Bumpa's checkout can only
    process items that actually exist in Bumpa's own catalog (real
    product_id per line), so a mixed cart can't be a single payment.

    One Order/one payment per "routing group":
      - "bumpa" group: every item with source == "bumpa" and a real
        external_id — routed through Bumpa's own cart/checkout/payment-intent
        flow regardless of which gateway is otherwise selected, since only
        Bumpa's checkout knows how to sell Bumpa's own products.
      - "default" group: everything else — routed through whichever gateway
        parameter is passed (or the business's configured default).

    Sibling orders share Order.group_reference so they can be reassembled
    into one customer-facing view later. Returns a list of dicts:
    [{"order_reference", "checkout_url", "total_amount", "currency",
      "gateway", "group_reference"}], one per resulting order — a single-group
    cart returns a single-element list, unchanged from today's behavior."""

    bumpa_items = [i for i in items if i.get("source") == "bumpa" and i.get("external_id")]
    other_items = [i for i in items if not (i.get("source") == "bumpa" and i.get("external_id"))]

    groups: List[Dict[str, Any]] = []
    if bumpa_items:
        groups.append({"gateway": "bumpa", "items": bumpa_items})
    if other_items:
        groups.append({"gateway": gateway, "items": other_items})

    if not groups:
        return []

    group_reference = f"GRP-{uuid.uuid4().hex[:8].upper()}" if len(groups) > 1 else None
    results: List[Dict[str, Any]] = []

    for group in groups:
        group_items = group["items"]
        group_gateway = group["gateway"]
        total_amount = sum(float(i.get("price", 0.0)) * int(i.get("quantity", 1)) for i in group_items)
        order_ref = f"ORD-{uuid.uuid4().hex[:8].upper()}"

        order = Order(
            order_reference=order_ref,
            customer_identifier=customer_identifier,
            channel=channel,
            items_json=json.dumps(group_items),
            total_amount=total_amount,
            currency=currency,
            status="pending",
            payment_gateway=group_gateway,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            shipping_address=shipping_address,
            group_reference=group_reference,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        items_summary = ", ".join(f"{i.get('quantity', 1)}x {i.get('title', 'Item')}" for i in group_items)
        custom_fields = [
            {"display_name": "Items Purchased", "variable_name": "items_purchased", "value": items_summary[:255]},
            {"display_name": "Order Reference", "variable_name": "order_reference", "value": order_ref},
        ]
        if customer_name:
            custom_fields.append({"display_name": "Customer Name", "variable_name": "customer_name", "value": customer_name})
        if customer_phone:
            custom_fields.append({"display_name": "Customer Phone", "variable_name": "customer_phone", "value": customer_phone})

        try:
            payment_res = await UnifiedPaymentManager.create_payment_link(
                amount=total_amount,
                currency=currency,
                customer_email=customer_email,
                reference=order_ref,
                gateway=group_gateway,
                customer_name=customer_name,
                customer_phone=customer_phone,
                metadata={
                    "channel": channel,
                    "customer_id": customer_identifier,
                    "order_reference": order_ref,
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "custom_fields": custom_fields,
                },
                items=[
                    {
                        "external_id": i.get("external_id"),
                        "quantity": i.get("quantity", 1),
                        "variant_external_id": i.get("variant_external_id"),
                    }
                    for i in group_items
                ] if group_gateway == "bumpa" else None,
                shipping_address=shipping_context_from_address(shipping_address) if group_gateway == "bumpa" else None,
            )
        except Exception as e:
            logger.error(f"Checkout link generation failed for order {order_ref} (gateway={group_gateway}): {e}")
            order.status = "failed"
            meta = json.loads(order.metadata_json or "{}")
            meta["checkout_error"] = str(e)
            order.metadata_json = json.dumps(meta)
            await db.commit()
            results.append({
                "order_reference": order_ref,
                "checkout_url": None,
                "total_amount": total_amount,
                "currency": currency,
                "gateway": group_gateway,
                "group_reference": group_reference,
                "error": str(e),
            })
            continue

        order.checkout_url = payment_res.get("checkout_url")

        # Bumpa-specific: its payment-intent settles via a real Paystack
        # charge under its own reference (not commb's ORD-xxxx), so the
        # Paystack webhook/callback needs to match THIS order by that
        # reference too — see payment_reference matching in
        # app/commerce/payments/webhooks.py. order_reference stays commb's
        # own human-readable ORD-xxxx (used everywhere else: tracking,
        # button ids, custom fields) rather than being overwritten.
        # bumpa_checkout_id/bumpa_cart_token are stashed so
        # _notify_customer_payment_success can call finalize_checkout once
        # that Paystack charge is confirmed.
        if group_gateway == "bumpa":
            order.payment_reference = payment_res.get("reference")
            meta = json.loads(order.metadata_json or "{}")
            meta["bumpa_checkout_id"] = payment_res.get("bumpa_checkout_id")
            meta["bumpa_cart_token"] = payment_res.get("bumpa_cart_token")
            order.metadata_json = json.dumps(meta)

        await db.commit()

        results.append({
            "order_reference": order_ref,
            "checkout_url": order.checkout_url,
            "total_amount": total_amount,
            "currency": currency,
            "gateway": group_gateway,
            "group_reference": group_reference,
        })

    return results
