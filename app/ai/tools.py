import json
import uuid
from typing import List, Dict, Any, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.commerce.catalog_provider import CatalogManager
from app.commerce.cart import CartManager
from app.commerce.customer_profile import get_customer, is_profile_complete
from app.commerce.payments.unified import UnifiedPaymentManager
from app.channels.slack.client import SlackDispatcher
from app.channels.slack.fallback import get_support_contact_message
from app.models.order import Order
from app.ai.memory import MemoryManager
from app.core.logger import logger

PROFILE_COLLECT_SENTINEL = "__profile_collect_prompt__"


TOOL_DEFINITIONS = [
    {
        "name": "search_catalog",
        "description": "Searches for products or services in the catalog by keyword, name, or category.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords or a natural description of what the customer wants (e.g. 'shoes', 'blue wireless earbuds', 'something for the office') — matching is flexible and word-based, not an exact phrase.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                },
            },
        },
    },
    {
        "name": "add_to_cart",
        "description": "Adds one or more items to the customer's active shopping cart.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "List of products to add to cart",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "title": {"type": "string"},
                            "quantity": {"type": "integer"},
                            "price": {"type": "number"},
                        },
                        "required": ["title", "price"],
                    },
                },
            },
            "required": ["items"],
        },
    },
    {
        "name": "view_cart",
        "description": "Retrieves the customer's current shopping cart, including all items and subtotal.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "clear_cart",
        "description": "Clears all items from the customer's active shopping cart.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "create_order",
        "description": (
            "Creates an order for the customer with chosen products. Call this "
            "immediately once the customer has confirmed what they want to buy — "
            "do NOT ask the customer for their name, email, or phone number "
            "yourself first. The system already handles collecting and "
            "verifying those details outside of this conversation; if they are "
            "still missing, this tool's result will tell you so and the "
            "customer will be prompted directly by the system, not by you."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "List of items to order with id or title, and quantity",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "title": {"type": "string"},
                            "quantity": {"type": "integer"},
                            "price": {"type": "number"},
                        },
                        "required": ["title", "quantity", "price"],
                    },
                },
                "shipping_address": {"type": "string", "description": "Customer delivery address if applicable"},
            },
            "required": ["items"],
        },
    },
    {
        "name": "generate_payment_link",
        "description": "Generates a secure online payment checkout link for an order using Paystack, Flutterwave, Monnify, or Stripe.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_reference": {
                    "type": "string",
                    "description": "The unique reference of the created order (e.g. 'ORD-123456')",
                },
                "gateway": {
                    "type": "string",
                    "description": "Optional payment gateway: 'paystack', 'flutterwave', 'monnify', or 'stripe'",
                },
            },
            "required": ["order_reference"],
        },
    },
    {
        "name": "get_order_status",
        "description": "Checks the status of an existing customer order by order reference.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_reference": {
                    "type": "string",
                    "description": "The order reference code (e.g. 'ORD-123456')",
                },
            },
            "required": ["order_reference"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Escalates the conversation to human support staff when the customer requests an agent or has an unresolvable issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why human assistance is required"},
                "urgency": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Urgency level",
                },
            },
            "required": ["reason"],
        },
    },
]


class ToolExecutor:
    """Executes AI tool calls against the database, commerce layer, and channels."""

    @staticmethod
    async def execute(
        db: AsyncSession,
        name: str,
        arguments: Dict[str, Any],
        customer_identifier: str,
        channel: str,
        allowed_access_tags: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        logger.info(f"Executing tool {name} with args: {arguments}")

        if name == "search_catalog":
            query = arguments.get("query")
            category = arguments.get("category")
            MIN_RESULTS = 3
            SEARCH_LIMIT = 8

            items = await CatalogManager.search_products(
                db, query=query, category=category, limit=SEARCH_LIMIT, allowed_access_tags=allowed_access_tags
            )
            matched_count = len(items)

            # "Append possible ones too" — when a search comes back thin,
            # backfill with the same newest+popular ranking used for the
            # undirected browse case, so the customer still sees something
            # relevant instead of a bare "no results". The LLM's reply
            # already distinguishes these in its own words (it can see
            # matched_count below) — no separate schema field needed.
            if matched_count < MIN_RESULTS:
                seen_ids = {item.id for item in items}
                featured = await CatalogManager.get_featured_products(
                    db, limit=SEARCH_LIMIT, allowed_access_tags=allowed_access_tags
                )
                for extra in featured:
                    if len(items) >= SEARCH_LIMIT:
                        break
                    if extra.id not in seen_ids:
                        items.append(extra)
                        seen_ids.add(extra.id)

            if not items:
                return {"results": [], "message": "No matching products found."}

            return {
                "results": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "description": item.description,
                        "price": item.price,
                        "currency": item.currency,
                        "in_stock": item.in_stock,
                    }
                    for item in items
                ],
                "matched_count": matched_count,
                "message": (
                    f"{matched_count} product(s) matched your search."
                    + (f" Added {len(items) - matched_count} more you might also like since exact matches were limited." if matched_count < MIN_RESULTS and len(items) > matched_count else "")
                ),
                "presentation": {
                    "product_cards": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "description": item.description,
                            "price": item.price,
                            "currency": item.currency,
                            # See app/flows/engine.py's flow_browse_catalog for
                            # why this isn't gated on StorageManager.is_configured
                            # (that answers "can this server upload new images
                            # right now", not "is this saved image_url valid").
                            "image_url": item.image_url or None,
                            "buy_action_id": f"cart_add_{item.id}",
                        }
                        for item in items
                    ]
                },
            }

        elif name == "add_to_cart":
            session = await MemoryManager.get_or_create_session(db, channel=channel, customer_identifier=customer_identifier)
            items = arguments.get("items", [])
            added_titles = []
            for itm in items:
                # Resolve source/external_id from the DB rather than trusting
                # the LLM's arguments for them — needed so a Bumpa-sourced
                # item added via this AI-tool path is still correctly routed
                # to Bumpa checkout later (see FlowEngine's split-checkout
                # logic), the same way the button-driven cart_add_ path
                # already threads product.source through.
                product_id = itm.get("product_id")
                item_source = None
                item_external_id = None
                item_requires_shipping = True
                item_fulfillment_type = "physical"
                if product_id is not None:
                    catalog_item = await CatalogManager.get_product_by_id(db, product_id)
                    if catalog_item:
                        item_source = catalog_item.source
                        item_external_id = catalog_item.external_id
                        item_requires_shipping = catalog_item.requires_shipping
                        item_fulfillment_type = catalog_item.fulfillment_type or "physical"

                await CartManager.add_item(
                    db=db,
                    session=session,
                    item_id=product_id,
                    title=itm.get("title"),
                    price=float(itm.get("price", 0.0)),
                    quantity=int(itm.get("quantity", 1)),
                    external_id=item_external_id,
                    source=item_source,
                    requires_shipping=item_requires_shipping,
                    fulfillment_type=item_fulfillment_type,
                )
                added_titles.append(itm.get("title"))

            cart = CartManager.get_cart(session)
            return {
                "status": "success",
                "message": f"Added {', '.join(added_titles)} to your cart.",
                "cart_summary": CartManager.format_cart_message(cart),
                "items_count": len(cart),
                "subtotal": CartManager.calculate_subtotal(cart),
            }

        elif name == "view_cart":
            session = await MemoryManager.get_or_create_session(db, channel=channel, customer_identifier=customer_identifier)
            cart = CartManager.get_cart(session)
            return {
                "cart_summary": CartManager.format_cart_message(cart),
                "items": cart,
                "subtotal": CartManager.calculate_subtotal(cart),
            }

        elif name == "clear_cart":
            session = await MemoryManager.get_or_create_session(db, channel=channel, customer_identifier=customer_identifier)
            await CartManager.clear_cart(db, session)
            return {
                "status": "success",
                "message": "Cart has been cleared.",
            }

        elif name == "create_order":
            items = arguments.get("items", [])
            if not items:
                return {"error": "Order items list cannot be empty."}

            profile = await ToolExecutor._resolve_profile(db, channel, customer_identifier, arguments)
            if profile is None:
                session = await MemoryManager.get_or_create_session(db, channel=channel, customer_identifier=customer_identifier)
                prompt = await ToolExecutor._trigger_profile_collect(
                    db, session,
                    resume_intent={
                        "path": "ai_tool",
                        "tool": "create_order",
                        "items": items,
                        "shipping_address": arguments.get("shipping_address"),
                    },
                )
                return {PROFILE_COLLECT_SENTINEL: prompt}

            result = await ToolExecutor._create_order_with_profile(
                db, None, items=items, shipping_address=arguments.get("shipping_address"),
                customer_name=profile["name"], customer_email=profile["email"], customer_phone=profile["phone"],
                customer_identifier=customer_identifier, channel=channel,
            )
            return {
                "order_reference": result["order_reference"],
                "total_amount": result["total_amount"],
                "currency": result["currency"],
                "status": "pending",
                "message": f"Order {result['order_reference']} created successfully. Total: {result['total_amount']:,.2f} {result['currency']}.",
            }

        elif name == "generate_payment_link":
            order_ref = arguments.get("order_reference")
            gateway = arguments.get("gateway")

            stmt = select(Order).where(Order.order_reference == order_ref)
            result = await db.execute(stmt)
            order = result.scalars().first()

            if not order:
                return {"error": f"Order {order_ref} not found."}

            if not order.customer_email:
                profile = await ToolExecutor._resolve_profile(db, channel, customer_identifier, {})
                if profile is None:
                    session = await MemoryManager.get_or_create_session(db, channel=channel, customer_identifier=customer_identifier)
                    prompt = await ToolExecutor._trigger_profile_collect(
                        db, session,
                        resume_intent={"path": "ai_tool", "tool": "generate_payment_link", "order_reference": order_ref},
                    )
                    return {PROFILE_COLLECT_SENTINEL: prompt}
                order.customer_name = order.customer_name or profile["name"]
                order.customer_email = profile["email"]
                order.customer_phone = order.customer_phone or profile["phone"]
                await db.commit()

            try:
                result = await ToolExecutor._generate_payment_link_with_profile(
                    db, None,
                    order_reference=order_ref,
                    customer_name=order.customer_name,
                    customer_email=order.customer_email,
                    customer_phone=order.customer_phone,
                    gateway=gateway,
                    channel=channel,
                    customer_identifier=customer_identifier,
                )
                checkout_url = result["checkout_url"]
                return {
                    "order_reference": order_ref,
                    "amount": result["total_amount"],
                    "currency": result["currency"],
                    "checkout_url": checkout_url,
                    "message": f"Please complete your payment of {result['total_amount']:,.2f} {result['currency']} via this secure link: {checkout_url}",
                    "presentation": {"checkout_url": checkout_url},
                }
            except Exception as e:
                logger.error(f"Payment link creation error: {e}")
                return {"error": f"Could not generate payment link: {str(e)}"}

        elif name == "get_order_status":
            order_ref = arguments.get("order_reference")
            stmt = select(Order).where(Order.order_reference == order_ref)
            result = await db.execute(stmt)
            order = result.scalars().first()

            if not order:
                return {"error": f"No order found with reference {order_ref}."}

            return {
                "order_reference": order.order_reference,
                "status": order.status,
                "total_amount": order.total_amount,
                "currency": order.currency,
                "created_at": order.created_at.isoformat() if order.created_at else None,
            }

        elif name == "escalate_to_human":
            reason = arguments.get("reason", "Customer requested assistance")
            urgency = arguments.get("urgency", "medium")

            # Post to Slack if configured
            await SlackDispatcher.dispatch_escalation(
                customer_identifier=customer_identifier,
                channel=channel,
                reason=reason,
                urgency=urgency,
            )

            # Return fallback contact info for AI to include in customer reply
            support_card = get_support_contact_message()
            return {
                "status": "escalated",
                "support_message": support_card,
            }

        else:
            return {"error": f"Unknown tool: {name}"}

    @staticmethod
    async def _resolve_profile(
        db: AsyncSession, channel: str, customer_identifier: str, arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Optional[str]]]:
        """Resolves a complete {name, email, phone} profile for checkout, preferring
        explicit tool-call arguments, falling back to a stored Customer profile
        (WhatsApp/Telegram) or the widget's one-shot form submission for this
        session (widget). Returns None if no complete profile is available —
        callers must then interrupt with the profile_collect flow rather than
        proceeding with placeholder data."""
        name = arguments.get("customer_name")
        email = arguments.get("customer_email")
        phone = arguments.get("customer_phone")

        if channel in ("whatsapp", "telegram"):
            stored = await get_customer(db, channel, customer_identifier)
            if stored:
                name = name or stored.name
                email = email or stored.email
                phone = phone or stored.phone_number
            if channel == "whatsapp":
                phone = phone or customer_identifier
        elif channel == "widget":
            from app.flows.engine import FlowEngine

            session = await MemoryManager.get_or_create_session(db, channel=channel, customer_identifier=customer_identifier)
            widget_profile = FlowEngine._get_widget_profile(session)
            if widget_profile:
                name = name or widget_profile.get("name")
                email = email or widget_profile.get("email")
                phone = phone or widget_profile.get("phone")

        if name and email and phone:
            return {"name": name, "email": email, "phone": phone}
        return None

    @staticmethod
    async def _trigger_profile_collect(db: AsyncSession, session, resume_intent: Dict[str, Any]) -> str:
        """Hijacks the session into the same profile_collect state machine
        FlowEngine uses for the button path, and returns the first prompt's
        text so the orchestrator can short-circuit the LLM loop with it."""
        from app.flows.engine import FlowEngine

        customer = None
        if session.channel != "widget":
            customer = await get_customer(db, session.channel, session.customer_identifier)
        resp = await FlowEngine._start_profile_collect(db, session, customer, resume_intent=resume_intent)
        return resp.text

    @staticmethod
    async def _create_order_with_profile(
        db: AsyncSession,
        session,
        items: List[Dict[str, Any]],
        shipping_address: Optional[str],
        customer_name: Optional[str],
        customer_email: Optional[str],
        customer_phone: Optional[str],
        customer_identifier: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Shared order-creation logic used by both the normal create_order tool
        call and the profile_collect resume path (FlowEngine._resume_ai_checkout_intent).

        If any item is Bumpa-sourced, this actually creates it as its own
        separate Order sharing a group_reference (Bumpa's checkout can only
        ever settle its own catalog's items — see app/commerce/checkout.py) —
        but since generate_payment_link's tool contract expects a single
        order_reference, the PRIMARY order returned here is whichever group
        has more items; the other group's reference is surfaced under
        additional_order_references so the assistant can still mention it
        and a second generate_payment_link call can be made for it."""
        customer_identifier = customer_identifier or (session.customer_identifier if session else None)
        channel = channel or (session.channel if session else None)

        bumpa_items = [i for i in items if i.get("source") == "bumpa" and i.get("external_id")]
        other_items = [i for i in items if not (i.get("source") == "bumpa" and i.get("external_id"))]
        groups = [g for g in (other_items, bumpa_items) if g]
        group_reference = f"GRP-{uuid.uuid4().hex[:8].upper()}" if len(groups) > 1 else None

        created = []
        for group_items in groups:
            total_amount = sum(float(item.get("price", 0)) * int(item.get("quantity", 1)) for item in group_items)
            order_ref = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            is_bumpa_group = bool(group_items and group_items[0].get("source") == "bumpa" and group_items[0].get("external_id"))
            order = Order(
                order_reference=order_ref,
                customer_identifier=customer_identifier,
                channel=channel,
                items_json=json.dumps(group_items),
                total_amount=total_amount,
                currency="NGN",
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                shipping_address=shipping_address,
                status="pending",
                group_reference=group_reference,
                # Pre-set here (rather than left to generate_payment_link's
                # gateway argument) so a Bumpa-sourced order is ALWAYS routed
                # to Bumpa checkout regardless of what gateway the LLM
                # happens to pass later — only Bumpa's own checkout can sell
                # Bumpa's own catalog items.
                payment_gateway="bumpa" if is_bumpa_group else None,
            )
            db.add(order)
            await db.commit()
            await db.refresh(order)
            created.append({"order_reference": order_ref, "total_amount": total_amount, "currency": order.currency})

        primary = created[0]
        return {
            "order_reference": primary["order_reference"],
            "total_amount": primary["total_amount"],
            "currency": primary["currency"],
            "additional_order_references": [c["order_reference"] for c in created[1:]],
        }

    @staticmethod
    async def _generate_payment_link_with_profile(
        db: AsyncSession,
        session,
        order_reference: str,
        customer_name: Optional[str],
        customer_email: Optional[str],
        customer_phone: Optional[str],
        gateway: Optional[str] = None,
        channel: Optional[str] = None,
        customer_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Shared payment-link logic used by both the normal generate_payment_link
        tool call and the profile_collect resume path."""
        channel = channel or (session.channel if session else None)
        customer_identifier = customer_identifier or (session.customer_identifier if session else None)

        stmt = select(Order).where(Order.order_reference == order_reference)
        result = await db.execute(stmt)
        order = result.scalars().first()
        if not order:
            raise ValueError(f"Order {order_reference} not found.")

        items_summary = ""
        if order.items_json:
            try:
                items_data = json.loads(order.items_json)
                if isinstance(items_data, list):
                    items_summary = ", ".join(
                        f"{item.get('quantity', 1)}x {item.get('title', 'Item')}"
                        for item in items_data
                    )
            except Exception:
                pass

        custom_fields = []
        if items_summary:
            custom_fields.append({
                "display_name": "Items Purchased",
                "variable_name": "items_purchased",
                "value": items_summary[:255],
            })
        custom_fields.append({
            "display_name": "Order Reference",
            "variable_name": "order_reference",
            "value": order.order_reference,
        })
        if customer_name:
            custom_fields.append({
                "display_name": "Customer Name",
                "variable_name": "customer_name",
                "value": customer_name,
            })
        if customer_phone:
            custom_fields.append({
                "display_name": "Customer Phone",
                "variable_name": "customer_phone",
                "value": customer_phone,
            })

        metadata = {
            "channel": channel,
            "customer_id": customer_identifier,
            "order_reference": order.order_reference,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "custom_fields": custom_fields,
        }

        # An order created as a Bumpa group (see _create_order_with_profile)
        # already has payment_gateway="bumpa" pre-set — that always wins over
        # whatever gateway argument the LLM passes, since only Bumpa's own
        # checkout can sell Bumpa's own catalog items.
        effective_gateway = order.payment_gateway if order.payment_gateway == "bumpa" else gateway
        bumpa_items = None
        shipping_ctx = None
        if effective_gateway == "bumpa":
            from app.commerce.checkout import shipping_context_from_address
            try:
                order_items = json.loads(order.items_json or "[]")
            except Exception:
                order_items = []
            bumpa_items = [
                {"external_id": i.get("external_id"), "quantity": i.get("quantity", 1), "variant_external_id": i.get("variant_external_id")}
                for i in order_items
            ]
            shipping_ctx = shipping_context_from_address(order.shipping_address)

        payment_res = await UnifiedPaymentManager.create_payment_link(
            amount=order.total_amount,
            currency=order.currency,
            customer_email=customer_email,
            reference=order.order_reference,
            gateway=effective_gateway,
            customer_name=customer_name,
            customer_phone=customer_phone,
            metadata=metadata,
            items=bumpa_items,
            shipping_address=shipping_ctx,
        )
        checkout_url = payment_res.get("checkout_url")
        order.checkout_url = checkout_url
        order.payment_gateway = effective_gateway or "default"
        order.customer_name = order.customer_name or customer_name
        order.customer_email = order.customer_email or customer_email
        order.customer_phone = order.customer_phone or customer_phone

        if effective_gateway == "bumpa":
            # Bumpa settles via its own Paystack reference, not commb's
            # order_reference — the Paystack webhook/callback matches on
            # payment_reference too (see app/commerce/payments/webhooks.py)
            # so this order gets marked paid correctly.
            order.payment_reference = payment_res.get("reference")
            meta = json.loads(order.metadata_json or "{}")
            meta["bumpa_checkout_id"] = payment_res.get("bumpa_checkout_id")
            meta["bumpa_cart_token"] = payment_res.get("bumpa_cart_token")
            order.metadata_json = json.dumps(meta)

        await db.commit()

        return {
            "order_reference": order_reference,
            "checkout_url": checkout_url,
            "total_amount": order.total_amount,
            "currency": order.currency,
        }
