import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.session import ConversationSession
from app.models.order import Order
from app.models.customer import Customer
from app.ai.memory import MemoryManager
from app.commerce.catalog_provider import CatalogManager
from app.commerce.cart import CartManager
from app.commerce.customer_profile import (
    get_customer,
    upsert_customer,
    is_profile_complete,
    is_valid_email,
    is_valid_phone,
    get_delivery_address,
    save_delivery_address,
)
from app.commerce.address import (
    parse_free_text_address,
    format_address_confirmation,
    address_to_single_line,
    ADDRESS_TEMPLATE_HINT,
    match_state,
    match_country,
)
from app.commerce.payments.unified import UnifiedPaymentManager
from app.channels.slack.fallback import get_support_contact_message
from app.flows.definitions import (
    MAIN_MENU_BUTTONS,
    WIDGET_MAIN_MENU_BUTTONS,
    get_main_menu_buttons,
    CART_BUTTONS,
    CART_EMPTY_BUTTONS,
    get_main_menu_text,
    get_quantity_buttons,
)
from app.schemas.bot_response import BotResponse, ResponseButton, ProductCard
from app.core.logger import logger


def _buttons(raw: List[Dict[str, Any]]) -> List[ResponseButton]:
    return [ResponseButton(**b) for b in raw]


# How long a customer can go without replying mid profile_collect before the
# flow is auto-abandoned and their next message is treated as a fresh normal
# message instead of a (likely nonsensical) answer to a stale question —
# e.g. someone who types /start after walking away shouldn't get stuck being
# told "/start" isn't a valid email.
PROFILE_COLLECT_TIMEOUT_MINUTES = 10

# Words that explicitly cancel profile_collect and return to the main menu,
# checked before treating the message as an answer to the current step.
_PROFILE_COLLECT_CANCEL_WORDS = {"/start", "start", "menu", "/menu", "cancel", "/cancel", "stop"}


class FlowEngine:
    """State machine for deterministic interactive buttons and step-by-step flows (0 LLM Tokens)."""

    @staticmethod
    async def handle_action(
        db: AsyncSession,
        session: ConversationSession,
        action_id: str,
        user_input: Optional[str] = None,
        prefill_name: Optional[str] = None,
    ) -> BotResponse:
        """Handles interactive button callbacks and progression."""
        action = action_id.lower().strip()
        logger.info(f"Flow engine processing action: {action}")

        # Log the user's action into memory to ensure it appears in the conversation UI
        await MemoryManager.add_message(
            db=db,
            session=session,
            role="user",
            content=user_input or action_id,
        )

        response = await FlowEngine._process_action(
            db, session, action, user_input, prefill_name
        )

        # Log the bot's response into memory
        await MemoryManager.add_message(
            db=db,
            session=session,
            role="assistant",
            content=response.text,
        )

        return response

    @staticmethod
    async def _process_action(
        db: AsyncSession,
        session: ConversationSession,
        action: str,
        user_input: Optional[str] = None,
        prefill_name: Optional[str] = None,
    ) -> BotResponse:

        # `action` is the normalized lowercase string, but we need `action_id`
        # which is the original user input text for ORD- checking in track_order.
        action_id = user_input or action

        # 0. Profile Collection Flow (interrupts any other action while active)
        if session.active_flow == "profile_collect":
            timed_out = False
            if session.last_active_at:
                last_active = session.last_active_at
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=timezone.utc)
                timed_out = datetime.now(timezone.utc) - last_active > timedelta(minutes=PROFILE_COLLECT_TIMEOUT_MINUTES)

            cancelled = action in _PROFILE_COLLECT_CANCEL_WORDS

            if timed_out or cancelled:
                # Abandon the flow — drop the draft (but never the cart, a
                # sibling key) — and let this same message fall through to be
                # processed normally below instead of being rejected as a
                # bad answer to a stale question (e.g. "/start" mid-collect
                # was previously scored as an invalid email and the user got
                # stuck with no way out).
                state = MemoryManager.get_flow_state_data(session)
                state.pop("profile_draft", None)
                await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None, state_data=state)
                if cancelled:
                    logger.info("profile_collect cancelled by user command")
                else:
                    logger.info(f"profile_collect abandoned after {PROFILE_COLLECT_TIMEOUT_MINUTES}min inactivity")
            else:
                return await FlowEngine._handle_profile_collect_step(db, session, user_input or action_id)

        # 0a. Delivery Address Collection Flow (interrupts any other action
        # while active) — same shape/timeout/cancel-word handling as
        # profile_collect above, kept as a fully separate flow rather than
        # folded into it since it's conditional (only carts needing
        # delivery trigger it) and can also be entered standalone from
        # "My Profile" → "Update Delivery Address".
        if session.active_flow == "address_collect":
            timed_out = False
            if session.last_active_at:
                last_active = session.last_active_at
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=timezone.utc)
                timed_out = datetime.now(timezone.utc) - last_active > timedelta(minutes=PROFILE_COLLECT_TIMEOUT_MINUTES)

            cancelled = action in _PROFILE_COLLECT_CANCEL_WORDS

            if timed_out or cancelled:
                state = MemoryManager.get_flow_state_data(session)
                state.pop("address_draft", None)
                await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None, state_data=state)
                if cancelled:
                    logger.info("address_collect cancelled by user command")
                else:
                    logger.info(f"address_collect abandoned after {PROFILE_COLLECT_TIMEOUT_MINUTES}min inactivity")
            else:
                return await FlowEngine._handle_address_collect_step(db, session, action_id, user_input or action_id)

        # 0b. Quantity Selection Flow (intercept custom numbers sent in chat)
        if session.active_flow == "quantity_select" and not action.startswith("flow_") and not action.startswith("cart_") and not action.startswith("qty_set_"):
            state = MemoryManager.get_flow_state_data(session)
            selected_id = state.get("selected_product_id")
            selected_title = state.get("selected_product_title")
            raw_text = (user_input or action_id).strip()

            # Match single integer or "qty 4" / "quantity 5" / "4 pcs"
            qty_match = re.search(r'^(?:qty|quantity|buy|need|want)?\s*[:#]?\s*(\d{1,4})(?:\s*(?:pcs|pieces|items|units|x))?$', raw_text, re.IGNORECASE)
            if not qty_match and raw_text.isdigit():
                qty_match = re.search(r'(\d+)', raw_text)

            if qty_match and selected_id is not None:
                new_qty = int(qty_match.group(1))
                if 1 <= new_qty <= 9999:
                    cart = await CartManager.set_item_quantity(
                        db=db,
                        session=session,
                        item_id=selected_id,
                        quantity=new_qty,
                        title=selected_title,
                    )
                    cart_msg = CartManager.format_cart_message(cart)
                    qty_buttons = get_quantity_buttons(selected_id, current_qty=new_qty)
                    item_name = selected_title or f"Item #{selected_id}"

                    return BotResponse(
                        text=(
                            f"✅ *Updated quantity: {new_qty}x {item_name} in your cart!*\n\n"
                            f"🔢 *Want to adjust quantity?*\n"
                            f"• Tap an example number below\n"
                            f"• Or type any number directly in chat\n\n"
                            f"{cart_msg}"
                        ),
                        buttons=_buttons(qty_buttons),
                    )

        # 1. Main Menu Trigger
        if action in ["flow_main_menu", "/start", "menu", "start"]:
            await MemoryManager.update_flow_state(db, session, active_flow="main_menu", current_step="root")
            menu_buttons = get_main_menu_buttons(session.channel)
            return BotResponse(
                text=get_main_menu_text(),
                buttons=_buttons(menu_buttons),
            )

        # 2. Browse Products Flow
        elif action == "flow_browse_catalog":
            products = await CatalogManager.get_featured_products(db, limit=10)
            if not products:
                return BotResponse(
                    text="🛍️ Our catalog is currently being updated. Please check back shortly!",
                    buttons=_buttons(MAIN_MENU_BUTTONS),
                )

            product_lines = []
            buttons = []
            product_cards = []
            for p in products:
                product_lines.append(f"• *{p.title}* — {p.price:,.2f} {p.currency}\n  _{p.description or 'In stock'}_")
                buttons.append({"id": f"cart_add_{p.id}", "title": f"{p.title[:24]}"})
                product_cards.append(
                    ProductCard(
                        id=p.id,
                        title=p.title,
                        description=p.description,
                        price=p.price,
                        currency=p.currency,
                        # Whether THIS server's storage provider is configured
                        # for new uploads (StorageManager.is_configured) is a
                        # different question from whether an already-saved
                        # image_url is a valid, servable URL — a product
                        # imported from Bumpa or uploaded while a different
                        # provider was configured still has a perfectly good
                        # external URL. Gating display on the former hid
                        # every product image regardless of whether it would
                        # actually load.
                        image_url=p.image_url or None,
                        buy_action_id=f"cart_add_{p.id}",
                    )
                )

            if session.channel == "telegram":
                # Telegram-only: opens bots/inline search (@botname <query>)
                # scoped to this chat. WhatsApp/widget renderers drop
                # "inline_search" buttons automatically (no equivalent).
                buttons.append({"id": "noop_inline_search", "title": "🔍 Search Products", "kind": "inline_search"})
            buttons.append({"id": "flow_view_cart", "title": "🛒 View Cart"})
            buttons.append({"id": "flow_main_menu", "title": "🏠 Menu"})

            reply_text = "🛍️ *Available Products & Services:*\n\n" + "\n\n".join(product_lines)

            await MemoryManager.update_flow_state(db, session, active_flow="catalog", current_step="viewing")
            return BotResponse(
                text=reply_text,
                buttons=_buttons(buttons),
                product_cards=product_cards,
            )

        # 3. Add to Cart via Button Click (e.g. "cart_add_1", or
        # "cart_add_1_variant_3" once a specific variant has been chosen —
        # see 3a below for the variant-selection step this can trigger.
        elif action.startswith("cart_add_"):
            remainder = action.replace("cart_add_", "")
            variant_id: Optional[int] = None
            item_id_str = remainder
            if "_variant_" in remainder:
                item_id_str, variant_part = remainder.split("_variant_", 1)
                if variant_part.isdigit():
                    variant_id = int(variant_part)

            product = None
            if item_id_str.isdigit():
                product = await CatalogManager.get_product_by_id(db, int(item_id_str))

            if not product:
                return BotResponse(
                    text="Could not find that product. Please select from our catalog:",
                    buttons=_buttons(MAIN_MENU_BUTTONS),
                )

            # If this product has variants and none was chosen yet, show
            # the variant options instead of adding the base product
            # straight to cart — mirrors the existing qty-selection step's
            # pattern (intercept before the default add, resume once a
            # choice is made) rather than a new subsystem.
            if product.has_variants and variant_id is None:
                variants = await CatalogManager.get_variants_for_product(db, product.id)
                if variants:
                    variant_buttons = [
                        {"id": f"cart_add_{product.id}_variant_{v.id}", "title": v.name[:24]}
                        for v in variants
                        if v.in_stock
                    ]
                    if not variant_buttons:
                        return BotResponse(
                            text=f"😔 *{product.title}* is currently out of stock in all variants.",
                            buttons=_buttons(MAIN_MENU_BUTTONS),
                        )
                    variant_buttons.append({"id": "flow_browse_catalog", "title": "🛍️ Back to Catalog"})
                    return BotResponse(
                        text=f"*{product.title}* comes in a few options — which would you like?",
                        buttons=_buttons(variant_buttons),
                    )

            selected_variant = None
            if variant_id is not None:
                selected_variant = await CatalogManager.get_variant_by_id(db, variant_id)
                if not selected_variant or selected_variant.catalog_item_id != product.id:
                    return BotResponse(
                        text="That option is no longer available. Please pick again:",
                        buttons=_buttons([{"id": f"cart_add_{product.id}", "title": "🔄 Choose Again"}]),
                    )
                if not selected_variant.in_stock:
                    return BotResponse(
                        text=f"😔 *{selected_variant.name}* just went out of stock. Please pick a different option:",
                        buttons=_buttons([{"id": f"cart_add_{product.id}", "title": "🔄 Choose Again"}]),
                    )

            effective_price = selected_variant.price_override if (selected_variant and selected_variant.price_override is not None) else product.price
            display_title = f"{product.title} ({selected_variant.name})" if selected_variant else product.title

            cart = await CartManager.add_item(
                db=db,
                session=session,
                item_id=product.id,
                title=product.title,
                price=effective_price,
                quantity=1,
                currency=product.currency,
                external_id=product.external_id,
                variant_id=selected_variant.id if selected_variant else None,
                variant_name=selected_variant.name if selected_variant else None,
                source=product.source,
                requires_shipping=product.requires_shipping,
                fulfillment_type=product.fulfillment_type or "physical",
            )

            # Get current quantity of this exact item+variant combination
            item_qty = 1
            for entry in cart:
                same_item = entry.get("item_id") == product.id or entry.get("title", "").lower() == product.title.lower()
                same_variant = entry.get("variant_id") == (selected_variant.id if selected_variant else None)
                if same_item and same_variant:
                    item_qty = entry.get("quantity", 1)
                    break

            state = MemoryManager.get_flow_state_data(session)
            state["selected_product_id"] = product.id
            state["selected_product_title"] = product.title
            state["selected_variant_id"] = selected_variant.id if selected_variant else None
            await MemoryManager.update_flow_state(
                db,
                session,
                active_flow="quantity_select",
                current_step=f"qty_{product.id}",
                state_data=state,
            )

            cart_msg = CartManager.format_cart_message(cart)
            qty_buttons = get_quantity_buttons(product.id, current_qty=item_qty)

            return BotResponse(
                text=(
                    f"✅ *Added 1x {display_title} to your cart!* (Total in cart: {item_qty})\n\n"
                    f"🔢 *Select how many you'd like to buy:*\n"
                    f"• Tap an example number below (*1*, *2*, *3*, *5*, *10*)\n"
                    f"• Or type any custom number directly in chat (e.g. `4` or `12`)\n\n"
                    f"{cart_msg}"
                ),
                buttons=_buttons(qty_buttons),
            )

        # 3b. Quantity Preset Button Selection (e.g. "qty_set_1_3")
        elif action.startswith("qty_set_"):
            parts = action.split("_")
            if len(parts) >= 4 and parts[2].isdigit() and parts[3].isdigit():
                prod_id = int(parts[2])
                qty = int(parts[3])
                product = await CatalogManager.get_product_by_id(db, prod_id)
                prod_title = product.title if product else None
                prod_price = product.price if product else 0.0
                prod_curr = product.currency if product else "NGN"

                cart = await CartManager.set_item_quantity(
                    db=db,
                    session=session,
                    item_id=prod_id,
                    quantity=qty,
                    title=prod_title,
                    price=prod_price,
                    currency=prod_curr,
                )

                state = MemoryManager.get_flow_state_data(session)
                state["selected_product_id"] = prod_id
                if prod_title:
                    state["selected_product_title"] = prod_title
                await MemoryManager.update_flow_state(
                    db,
                    session,
                    active_flow="quantity_select",
                    current_step=f"qty_{prod_id}",
                    state_data=state,
                )

                cart_msg = CartManager.format_cart_message(cart)
                qty_buttons = get_quantity_buttons(prod_id, current_qty=qty)
                item_name = prod_title or f"Item #{prod_id}"

                return BotResponse(
                    text=(
                        f"✅ *Selected {qty}x {item_name}!* (Updated in cart)\n\n"
                        f"🔢 *Want to change quantity?*\n"
                        f"• Tap another number below\n"
                        f"• Or type any custom number directly in chat\n\n"
                        f"{cart_msg}"
                    ),
                    buttons=_buttons(qty_buttons),
                )

        # 4. View Cart
        elif action in ["flow_view_cart", "cart", "view_cart"]:
            cart = CartManager.get_cart(session)
            if not cart:
                return BotResponse(
                    text="🛒 *Your Shopping Cart is Empty!*\n\nBrowse our products to start adding items.",
                    buttons=_buttons(CART_EMPTY_BUTTONS),
                )
            return BotResponse(
                text=CartManager.format_cart_message(cart),
                buttons=_buttons(CART_BUTTONS),
            )

        # 5. Clear Cart
        elif action in ["flow_clear_cart", "clear_cart"]:
            await CartManager.clear_cart(db, session)
            return BotResponse(
                text="🗑️ *Your cart has been cleared.*",
                buttons=_buttons(CART_EMPTY_BUTTONS),
            )

        # 6. Checkout Flow (Zero LLM Tokens)
        elif action in ["flow_checkout", "checkout"]:
            cart = CartManager.get_cart(session)
            if not cart:
                return BotResponse(
                    text="🛒 *Your cart is currently empty!* Please add items first before checking out.",
                    buttons=_buttons(CART_EMPTY_BUTTONS),
                )

            needs_shipping = CartManager.cart_requires_shipping(cart)

            if session.channel == "widget":
                widget_profile = FlowEngine._get_widget_profile(session)
                if widget_profile and widget_profile.get("name") and widget_profile.get("email") and widget_profile.get("phone"):
                    if needs_shipping and not FlowEngine._get_widget_address(session):
                        return FlowEngine._widget_address_required_response()
                    widget_address = FlowEngine._get_widget_address(session) if needs_shipping else None
                    return await FlowEngine._build_checkout_response(
                        db, session, None,
                        name_override=widget_profile["name"], email_override=widget_profile["email"], phone_override=widget_profile["phone"],
                        shipping_address_override=address_to_single_line(widget_address) if widget_address else None,
                    )
                # Submitted-on-open form was skipped or never reached (e.g. API
                # client bypassing the panel) — fall back to the same turn-by-turn
                # chat collection WhatsApp/Telegram use.
                return await FlowEngine._start_profile_collect(db, session, None, resume_intent={"path": "cart"})

            customer = await get_customer(db, session.channel, session.customer_identifier)
            if not is_profile_complete(customer):
                return await FlowEngine._start_profile_collect(
                    db, session, customer, resume_intent={"path": "cart"}, prefill_name=prefill_name,
                )

            if needs_shipping and not get_delivery_address(customer):
                return await FlowEngine._start_address_collect(db, session, customer, resume_intent={"path": "cart"})

            return await FlowEngine._build_checkout_response(db, session, customer)

        # 7. Confirm Payment (Manual Fallback Button)
        elif action.startswith("flow_confirm_payment_"):
            order_ref = action_id.replace("flow_confirm_payment_", "").strip().upper()
            if order_ref:
                stmt = select(Order).where(Order.order_reference == order_ref)
                res = await db.execute(stmt)
                order = res.scalars().first()
                await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None)

                if not order:
                    return BotResponse(
                        text=f"❌ No order found for reference `{order_ref}`.",
                        buttons=_buttons(MAIN_MENU_BUTTONS),
                    )

                if order.status == "paid":
                    return BotResponse(
                        text=f"✅ *Payment Already Confirmed!*\n\nYour payment for Order *{order_ref}* has been received. Thank you!",
                        buttons=_buttons(MAIN_MENU_BUTTONS),
                    )

                # Attempt verification via payment gateway
                try:
                    result = await UnifiedPaymentManager.verify_payment(
                        reference=order_ref,
                        gateway=order.payment_gateway or "paystack",
                    )
                    if result.get("status") == "success":
                        order.status = "paid"
                        order.payment_reference = order_ref
                        await db.commit()

                        from app.cloud_sync.client import cloud_client
                        cloud_client.track(
                            channel=session.channel,
                            customer_id=session.customer_identifier,
                            event="payment_success",
                            status="success",
                            amount=order.total_amount,
                            metadata={"gateway": order.payment_gateway, "order_ref": order_ref, "source": "manual_confirm"},
                        )

                        return BotResponse(
                            text=(
                                f"🎉 *Payment Confirmed!*\n\n"
                                f"We have received your payment of *{order.total_amount:,.2f} {order.currency}* for Order *{order_ref}*.\n\n"
                                f"Your order is now being processed! Thank you for your business."
                            ),
                            buttons=_buttons(MAIN_MENU_BUTTONS),
                        )
                    else:
                        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                        checkout_link = f"\n\n👉 *Pay Now via Paystack:*\n{order.checkout_url}" if order.checkout_url else ""
                        return BotResponse(
                            text=(
                                f"⏳ *Payment Not Yet Received*\n\n"
                                f"We haven't received payment for Order *{order_ref}* yet (Checked at `{now_str}`).\n\n"
                                f"If you've already paid, please wait a few moments and tap **Check Again** below.{checkout_link}"
                            ),
                            buttons=_buttons([
                                {"id": f"flow_confirm_payment_{order_ref}", "title": "🔄 Check Again"},
                                {"id": "flow_track_order", "title": "📦 Track Order"},
                                {"id": "flow_main_menu", "title": "🏠 Main Menu"},
                            ]),
                            checkout_url=order.checkout_url,
                        )
                except Exception as e:
                    logger.error(f"Payment verification error for {order_ref}: {e}")
                    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                    return BotResponse(
                        text=f"⚠️ Could not verify payment for Order *{order_ref}* right now (Checked at `{now_str}`). Please try again in a moment.",
                        buttons=_buttons([
                            {"id": f"flow_confirm_payment_{order_ref}", "title": "🔄 Try Again"},
                            {"id": "flow_track_order", "title": "📦 Track Order"},
                            {"id": "flow_main_menu", "title": "🏠 Main Menu"},
                        ]),
                    )

            return BotResponse(
                text="❌ Invalid payment confirmation request.",
                buttons=_buttons(MAIN_MENU_BUTTONS),
            )

        # 8. Track Order Flow
        elif action == "flow_track_order" or session.active_flow == "track_order" or action_id.upper().startswith("ORD-"):
            ref_to_check = (user_input or action_id).strip().upper()
            if ref_to_check.startswith("ORD-"):
                stmt = select(Order).where(Order.order_reference == ref_to_check)
                res = await db.execute(stmt)
                order = res.scalars().first()
                await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None)
                if order:
                    status_emoji = "✅" if order.status == "paid" else "⏳" if order.status == "pending" else "📦"
                    items_detail = ""
                    try:
                        parsed_items = json.loads(order.items_json) if order.items_json else []
                        items_detail = "\n" + "\n".join([f"  • {it.get('quantity', 1)}x {it.get('title', 'Item')} ({it.get('price', 0):,.2f} {order.currency})" for it in parsed_items])
                    except Exception:
                        pass

                    checkout_url_val: Optional[str] = None
                    if order.status == "pending":
                        buttons = [
                            {"id": f"flow_confirm_payment_{order.order_reference}", "title": "✅ I've Paid"},
                            {"id": "flow_browse_products", "title": "🛍️ Browse Products"},
                            {"id": "flow_main_menu", "title": "🏠 Main Menu"},
                        ]
                        pay_now_section = f"\n\n👉 *Pay Now via Paystack:*\n{order.checkout_url}" if order.checkout_url else ""
                        checkout_url_val = order.checkout_url
                    else:
                        buttons = MAIN_MENU_BUTTONS
                        pay_now_section = ""

                    fulfillment_line = ""
                    if order.fulfillment_status:
                        f_emoji = {"delivered": "✅", "delivered_digital": "✅", "shipped": "🚚", "dispatched": "📦", "failed": "⚠️"}.get(order.fulfillment_status, "📦")
                        fulfillment_label = order.fulfillment_status.replace("_", " ").title()
                        fulfillment_line = f"\n• *Fulfillment:* {f_emoji} {fulfillment_label}"
                        if order.courier_name:
                            fulfillment_line += f" via {order.courier_name}"
                        if order.tracking_url:
                            fulfillment_line += f"\n  🔗 {order.tracking_url}"

                    return BotResponse(
                        text=(
                            f"{status_emoji} *Order #{order.order_reference} Details*\n\n"
                            f"• *Status:* {order.status.upper()}\n"
                            f"• *Total:* {order.total_amount:,.2f} {order.currency}\n"
                            f"• *Items:*{items_detail}\n"
                            f"• *Date:* {order.created_at.strftime('%Y-%m-%d %H:%M UTC') if order.created_at else 'Recent'}"
                            f"{fulfillment_line}"
                            f"{pay_now_section}"
                        ),
                        buttons=_buttons(buttons),
                        checkout_url=checkout_url_val,
                    )
                else:
                    return BotResponse(
                        text=f"❌ No order found matching reference `{ref_to_check}`. Please double check your order number or tap below:",
                        buttons=_buttons(MAIN_MENU_BUTTONS),
                    )

            await MemoryManager.update_flow_state(db, session, active_flow="track_order", current_step="awaiting_reference")
            return BotResponse(
                text="📦 Please reply with your *Order Reference* (e.g. `ORD-AB12CD34`) to check your order status.",
            )

        # 8b. My Purchases — this customer's own order history, no reference
        # needed (unlike Track Order, which requires already knowing/typing
        # a specific ORD-xxxx code). Looked up by customer_identifier.
        elif action in ["flow_my_purchases", "my purchases", "my_purchases", "my orders"]:
            await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None)
            ORDER_LIST_LIMIT = 8
            PENDING_BUTTON_LIMIT = 4  # keep the button count comfortably under WhatsApp's list-row cap

            stmt = (
                select(Order)
                .where(Order.customer_identifier == session.customer_identifier)
                .order_by(Order.created_at.desc())
                .limit(ORDER_LIST_LIMIT)
            )
            res = await db.execute(stmt)
            orders = res.scalars().all()

            if not orders:
                return BotResponse(
                    text="🧾 *My Purchases*\n\nYou haven't placed any orders with us yet. Browse our catalog to get started!",
                    buttons=_buttons(MAIN_MENU_BUTTONS),
                )

            status_emoji = {"paid": "✅", "pending": "⏳", "processing": "⚙️", "completed": "✅", "cancelled": "❌"}
            lines = ["🧾 *My Purchases* — your recent orders:\n"]
            buttons: List[Dict[str, str]] = []
            pending_shown = 0
            for order in orders:
                emoji = status_emoji.get(order.status, "📦")
                date_str = order.created_at.strftime("%Y-%m-%d") if order.created_at else "Recent"
                fulfillment_suffix = f" — {order.fulfillment_status.replace('_', ' ').title()}" if order.fulfillment_status else ""
                lines.append(
                    f"{emoji} *#{order.order_reference}* — {order.total_amount:,.2f} {order.currency} "
                    f"({order.status.upper()}, {date_str}){fulfillment_suffix}"
                )
                if order.status == "pending" and pending_shown < PENDING_BUTTON_LIMIT:
                    buttons.append({"id": f"flow_confirm_payment_{order.order_reference}", "title": f"✅ Pay {order.order_reference}"})
                    pending_shown += 1

            if len(orders) == ORDER_LIST_LIMIT:
                lines.append(f"\n_Showing your {ORDER_LIST_LIMIT} most recent orders._")

            buttons.append({"id": "flow_main_menu", "title": "🏠 Main Menu"})
            return BotResponse(text="\n".join(lines), buttons=_buttons(buttons))

        # 9. Talk to Human / Contact Support
        elif action == "flow_contact_support":
            support_msg = get_support_contact_message()
            await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None)
            return BotResponse(text=support_msg)

        # 10. My Profile — view saved profile details with Create/Update actions
        elif action in ["flow_my_profile", "profile", "my profile", "my_profile"]:
            if session.channel == "widget":
                await MemoryManager.update_flow_state(db, session, active_flow="main_menu", current_step="root")
                return BotResponse(
                    text=get_main_menu_text(),
                    buttons=_buttons(WIDGET_MAIN_MENU_BUTTONS),
                )

            customer = await get_customer(db, session.channel, session.customer_identifier)
            name_val = (customer.name if customer and customer.name else "").strip() or "[Not Set]"
            email_val = (customer.email if customer and customer.email else "").strip() or "[Not Set]"

            raw_phone = customer.phone_number if customer and customer.phone_number else (
                session.customer_identifier if session.channel == "whatsapp" else None
            )
            phone_val = (raw_phone or "").strip() or "[Not Set]"

            has_profile = bool(customer and (customer.name or customer.email or customer.phone_number))
            btn_title = "✏️ Update Profile" if has_profile else "➕ Create Profile"

            saved_address = get_delivery_address(customer)
            address_line = f"\n\n📦 *Delivery Address:*\n{format_address_confirmation(saved_address)}" if saved_address else "\n\n📦 *Delivery Address:* [Not Set]"
            address_btn_title = "📦 Update Delivery Address" if saved_address else "📦 Add Delivery Address"

            buttons = [
                {"id": "flow_start_profile_edit", "title": btn_title},
                {"id": "flow_update_address", "title": address_btn_title},
                {"id": "flow_main_menu", "title": "🏠 Main Menu"},
            ]

            await MemoryManager.update_flow_state(db, session, active_flow="profile_view", current_step="overview")
            return BotResponse(
                text=(
                    "👤 *Your Profile Details*\n\n"
                    f"• *Full Name:* {name_val}\n"
                    f"• *Email Address:* {email_val}\n"
                    f"• *Phone Number:* {phone_val}"
                    f"{address_line}\n\n"
                    "Please select an option below:"
                ),
                buttons=_buttons(buttons),
            )

        # 11. Start Profile Create / Update Flow
        elif action in ["flow_start_profile_edit", "create profile", "update profile", "edit profile", "flow_edit_profile"]:
            if session.channel == "widget":
                await MemoryManager.update_flow_state(db, session, active_flow="main_menu", current_step="root")
                return BotResponse(
                    text=get_main_menu_text(),
                    buttons=_buttons(WIDGET_MAIN_MENU_BUTTONS),
                )

            customer = await get_customer(db, session.channel, session.customer_identifier)
            return await FlowEngine._start_profile_collect(
                db, session, customer, resume_intent={"path": "profile_view"}, prefill_name=prefill_name, force_full=True,
            )

        # 12. Start Delivery Address Collection — standalone, from "My Profile".
        # Customers can update their delivery address at any time, not just
        # when a delivery-requiring cart forces it at checkout.
        elif action in ["flow_update_address", "update address", "update delivery address"]:
            if session.channel == "widget":
                await MemoryManager.update_flow_state(db, session, active_flow="main_menu", current_step="root")
                return BotResponse(
                    text=get_main_menu_text(),
                    buttons=_buttons(WIDGET_MAIN_MENU_BUTTONS),
                )

            customer = await get_customer(db, session.channel, session.customer_identifier)
            return await FlowEngine._start_address_collect(db, session, customer, resume_intent={"path": "profile_view"})

        return BotResponse(text="How else can we assist you today?")

    # ------------------------------------------------------------------
    # Profile Collection — lightweight 3-turn state machine reusing
    # session.active_flow/current_step/state_data, the same mechanism the
    # single-step track_order flow already uses. See "profile_draft" key
    # in state_data, kept as a sibling to "cart" so an in-progress cart is
    # never disturbed by an interrupting profile-collection turn.
    #
    # Widget is the one exception: it collects via a native autofill-friendly
    # <form> shown immediately on panel open (not turn-by-turn chat), whose
    # single-shot submission is stashed in state_data["widget_profile"] by
    # WidgetEndpoints.submit_profile — see _get_widget_profile below.
    # ------------------------------------------------------------------

    @staticmethod
    def _get_widget_profile(session: ConversationSession) -> Optional[Dict[str, Any]]:
        state = MemoryManager.get_flow_state_data(session)
        return state.get("widget_profile")

    @staticmethod
    async def set_widget_profile(
        db: AsyncSession,
        session: ConversationSession,
        name: Optional[str],
        email: Optional[str],
        phone: Optional[str],
    ) -> None:
        """Stores the widget's one-shot form submission for this session only —
        no Customer row is created (widget has no durable identity; a fresh
        form is shown again next session, per product requirement)."""
        state = MemoryManager.get_flow_state_data(session)
        state["widget_profile"] = {"name": name, "email": email, "phone": phone}
        await MemoryManager.update_flow_state(
            db, session, active_flow=session.active_flow, current_step=session.current_step, state_data=state,
        )

    @staticmethod
    async def _start_profile_collect(
        db: AsyncSession,
        session: ConversationSession,
        customer: Optional[Customer],
        resume_intent: Dict[str, Any],
        prefill_name: Optional[str] = None,
        force_full: bool = False,
    ) -> BotResponse:
        """Enters the profile_collect flow. `force_full=True` (the standalone
        "My Profile" entry point) always starts at ask_name, pre-filled with
        the current saved value if any. Otherwise (checkout-triggered), a
        WhatsApp/Telegram prefill name (from the channel payload) is offered
        for confirmation first, before falling back to ask_name."""
        state = MemoryManager.get_flow_state_data(session)
        saved = {
            "name": customer.name if customer else None,
            "email": customer.email if customer else None,
            "phone": customer.phone_number if customer else None,
        }

        if force_full:
            # "My Profile" always re-asks every field explicitly (so the customer
            # can genuinely change any of them) — the draft starts empty and each
            # step's prompt shows the saved value as a hint; "skip" falls back to
            # `saved` (see _handle_profile_collect_step), not a pre-filled draft.
            if session.channel == "whatsapp" and not saved.get("phone"):
                saved["phone"] = session.customer_identifier

            draft: Dict[str, Any] = {
                "resume_intent": resume_intent,
                "name": None,
                "email": None,
                "phone": session.customer_identifier if session.channel == "whatsapp" else None,
                "saved": saved,
            }
            state["profile_draft"] = draft
            await MemoryManager.update_flow_state(
                db, session, active_flow="profile_collect", current_step="ask_name", state_data=state,
            )
            has_existing = bool(saved.get("name") or saved.get("email") or saved.get("phone"))
            action_word = "update" if has_existing else "create"
            current = f" (currently: *{saved['name']}*)" if saved.get("name") else ""
            skip_hint = "\nReply 'skip' to keep it as-is." if saved.get("name") else ""
            return BotResponse(text=f"👤 Let's {action_word} your profile.\n\nWhat's your full name?{current}{skip_hint}")

        draft = {"resume_intent": resume_intent, **saved}
        # WhatsApp's own identifier IS the phone number — never ask for it separately.
        if session.channel == "whatsapp" and not draft["phone"]:
            draft["phone"] = session.customer_identifier

        offered_name = draft["name"] or prefill_name
        if session.channel in ("whatsapp", "telegram") and offered_name:
            draft["name"] = offered_name
            state["profile_draft"] = draft
            await MemoryManager.update_flow_state(
                db, session, active_flow="profile_collect", current_step="confirm_prefill", state_data=state,
            )
            return BotResponse(
                text=(
                    f"Before we checkout — we have your name as *{offered_name}*. "
                    f"Is that correct? We also need your email (and phone, for receipts and order tracking)."
                ),
                buttons=_buttons([
                    {"id": "profile_keep_name", "title": "✅ Yes, that's correct"},
                    {"id": "profile_change_name", "title": "✏️ Change it"},
                ]),
            )

        state["profile_draft"] = draft
        await MemoryManager.update_flow_state(
            db, session, active_flow="profile_collect", current_step="ask_name", state_data=state,
        )
        return BotResponse(text="Before we checkout, we need a few details for your receipt and order tracking.\n\nWhat's your full name?")

    @staticmethod
    def _next_missing_step(draft: Dict[str, Any]) -> Optional[str]:
        """Decides the next profile_collect step given what's already in the
        draft (name/email/phone — phone is pre-filled for WhatsApp before this
        is ever consulted, so it's naturally skipped there). None = complete."""
        if not draft.get("name"):
            return "ask_name"
        if not draft.get("email"):
            return "ask_email"
        if not draft.get("phone"):
            return "ask_phone"
        return None

    @staticmethod
    async def _advance_profile_collect(
        db: AsyncSession, session: ConversationSession, state: Dict[str, Any], draft: Dict[str, Any]
    ) -> BotResponse:
        """Moves to the next missing step, or completes the flow if nothing's left."""
        state["profile_draft"] = draft
        next_step = FlowEngine._next_missing_step(draft)
        if not next_step:
            return await FlowEngine._complete_profile_collect(db, session, draft)
        await MemoryManager.update_flow_state(db, session, active_flow="profile_collect", current_step=next_step, state_data=state)
        return await FlowEngine._prompt_for_step(session, next_step, draft)

    @staticmethod
    async def _handle_profile_collect_step(db: AsyncSession, session: ConversationSession, reply: str) -> BotResponse:
        state = MemoryManager.get_flow_state_data(session)
        draft: Dict[str, Any] = state.get("profile_draft", {"resume_intent": {"path": "none"}})
        step = session.current_step
        text = (reply or "").strip()
        skip = text.lower() == "skip"

        if step == "confirm_prefill":
            if text == "profile_change_name" or text.lower() in ("no", "change it", "change"):
                draft["name"] = None
                state["profile_draft"] = draft
                await MemoryManager.update_flow_state(db, session, active_flow="profile_collect", current_step="ask_name", state_data=state)
                return BotResponse(text="No problem — what's your full name?")
            # Accept ("yes"/profile_keep_name/anything else) and move on.
            return await FlowEngine._advance_profile_collect(db, session, state, draft)

        saved = draft.get("saved", {})

        if step == "ask_name":
            if not skip:
                if not text:
                    return BotResponse(text="Please send your full name to continue (or reply 'skip' to keep the saved one).")
                draft["name"] = text
            elif saved.get("name"):
                draft["name"] = saved["name"]
            elif not draft.get("name"):
                return BotResponse(text="We don't have a name on file yet — please send your full name.")
            return await FlowEngine._advance_profile_collect(db, session, state, draft)

        if step == "ask_email":
            if not skip:
                if not text or not is_valid_email(text):
                    return BotResponse(text="That doesn't look like a valid email — please try again (e.g. name@example.com).")
                draft["email"] = text
            elif saved.get("email"):
                draft["email"] = saved["email"]
            elif not draft.get("email"):
                return BotResponse(text="We don't have an email on file yet — please send a valid email address.")
            return await FlowEngine._advance_profile_collect(db, session, state, draft)

        if step == "ask_phone":
            if not skip:
                if not text or not is_valid_phone(text):
                    return BotResponse(text="That doesn't look like a valid phone number — please try again (e.g. +2348012345678).")
                draft["phone"] = text
            elif saved.get("phone"):
                draft["phone"] = saved["phone"]
            elif not draft.get("phone"):
                return BotResponse(text="We don't have a phone number on file yet — please send one.")
            return await FlowEngine._advance_profile_collect(db, session, state, draft)

        # Unknown step — bail out to main menu rather than get stuck.
        await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None)
        return BotResponse(text=get_main_menu_text(), buttons=_buttons(MAIN_MENU_BUTTONS))

    @staticmethod
    async def _prompt_for_step(session: ConversationSession, step: str, draft: Dict[str, Any]) -> BotResponse:
        saved = draft.get("saved", {})
        skip_hint = " Reply 'skip' to keep it as-is." if draft.get("saved") else ""
        if step == "ask_name":
            hint_val = draft.get("name") or saved.get("name")
            current = f" (currently: *{hint_val}*)" if hint_val else ""
            return BotResponse(text=f"What's your full name?{current}{skip_hint}")
        if step == "ask_email":
            hint_val = draft.get("email") or saved.get("email")
            current = f" (currently: *{hint_val}*)" if hint_val else ""
            return BotResponse(text=f"What's your email address? We'll use it for your receipt.{current}{skip_hint}")
        if step == "ask_phone":
            hint_val = draft.get("phone") or saved.get("phone")
            current = f" (currently: *{hint_val}*)" if hint_val else ""
            return BotResponse(text=f"What's your phone number?{current}{skip_hint}")
        return BotResponse(text="How else can we assist you today?")

    @staticmethod
    async def _complete_profile_collect(db: AsyncSession, session: ConversationSession, draft: Dict[str, Any]) -> BotResponse:
        customer = None
        if session.channel in ("whatsapp", "telegram"):
            customer = await upsert_customer(
                db, session.channel, session.customer_identifier,
                name=draft.get("name"), email=draft.get("email"), phone=draft.get("phone"),
            )
            try:
                from app.cloud_sync.client import cloud_client
                cloud_client.track(
                    channel=session.channel,
                    customer_id=session.customer_identifier,
                    event="profile_saved",
                    metadata={
                        "customer_name": draft.get("name") or (customer.name if customer else None),
                        "customer_email": draft.get("email") or (customer.email if customer else None),
                        "customer_phone": draft.get("phone") or (customer.phone_number if customer else None),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to track profile_saved telemetry: {e}")

        state = MemoryManager.get_flow_state_data(session)
        state.pop("profile_draft", None)
        if session.channel == "widget":
            # Widget has no durable Customer row (upsert_customer no-ops for
            # it above) — this chat-collected fallback profile (shown only
            # when the upfront form was skipped) needs to land in the SAME
            # session-only widget_profile slot the upfront form itself
            # writes to, so a later retry (e.g. after address_collect closes
            # the shipping gate) finds a complete profile via
            # _get_widget_profile instead of restarting profile collection
            # from scratch.
            state["widget_profile"] = {"name": draft.get("name"), "email": draft.get("email"), "phone": draft.get("phone")}
        await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None, state_data=state)

        resume_intent = draft.get("resume_intent", {"path": "none"})
        path = resume_intent.get("path")

        if path == "cart":
            cart = CartManager.get_cart(session)
            needs_shipping = CartManager.cart_requires_shipping(cart)
            if needs_shipping and session.channel == "widget" and not FlowEngine._get_widget_address(session):
                return FlowEngine._widget_address_required_response()
            widget_address = FlowEngine._get_widget_address(session) if (needs_shipping and session.channel == "widget") else None
            if needs_shipping and session.channel != "widget" and not get_delivery_address(customer):
                return await FlowEngine._start_address_collect(
                    db, session, customer, resume_intent={"path": "cart", "name": draft.get("name"), "email": draft.get("email"), "phone": draft.get("phone")},
                )
            return await FlowEngine._build_checkout_response(
                db, session, customer,
                name_override=draft.get("name"), email_override=draft.get("email"), phone_override=draft.get("phone"),
                shipping_address_override=address_to_single_line(widget_address) if widget_address else None,
            )
        if path == "ai_tool":
            return await FlowEngine._resume_ai_checkout_intent(db, session, customer, resume_intent, draft)

        name_display = draft.get("name") or (customer.name if customer else None) or "[Not Set]"
        email_display = draft.get("email") or (customer.email if customer else None) or "[Not Set]"
        phone_display = (
            draft.get("phone")
            or (customer.phone_number if customer else None)
            or (session.customer_identifier if session.channel == "whatsapp" else None)
            or "[Not Set]"
        )

        return BotResponse(
            text=(
                "✅ *Profile saved successfully!*\n\n"
                f"• *Full Name:* {name_display}\n"
                f"• *Email Address:* {email_display}\n"
                f"• *Phone Number:* {phone_display}\n\n"
                "What would you like to do next?"
            ),
            buttons=_buttons([
                {"id": "flow_start_profile_edit", "title": "✏️ Update Profile"},
                {"id": "flow_browse_catalog", "title": "🛍️ Browse Products"},
                {"id": "flow_main_menu", "title": "🏠 Main Menu"},
            ]),
        )

    # ------------------------------------------------------------------
    # Delivery Address Collection — Telegram/WhatsApp: one free-text
    # message parsed into street/city/state/zip/country (see
    # app/commerce/address.py), then a confirm screen with per-field edit
    # buttons before saving. Only triggered when the cart actually needs
    # delivery (CartManager.cart_requires_shipping) or when explicitly
    # entered from "My Profile" → "Update Delivery Address". Widget uses a
    # real form instead (see _get_widget_address/_widget_address_required_response
    # below) — no chat state machine needed there.
    # ------------------------------------------------------------------

    @staticmethod
    async def _start_address_collect(
        db: AsyncSession,
        session: ConversationSession,
        customer: Optional[Customer],
        resume_intent: Dict[str, Any],
    ) -> BotResponse:
        state = MemoryManager.get_flow_state_data(session)
        saved = get_delivery_address(customer) or {}
        draft: Dict[str, Any] = {"resume_intent": resume_intent, "fields": dict(saved), "missing": []}
        state["address_draft"] = draft
        await MemoryManager.update_flow_state(db, session, active_flow="address_collect", current_step="ask_address", state_data=state)

        current_hint = ""
        if saved:
            current_hint = f"\n\n_You currently have an address on file:_\n{format_address_confirmation(saved)}\n\nReply 'skip' to keep it, or send a new one below."
        return BotResponse(text=f"📦 We need a delivery address for this order.\n\n{ADDRESS_TEMPLATE_HINT}{current_hint}")

    @staticmethod
    async def _handle_address_collect_step(db: AsyncSession, session: ConversationSession, action_id: str, reply: str) -> BotResponse:
        state = MemoryManager.get_flow_state_data(session)
        draft: Dict[str, Any] = state.get("address_draft", {"resume_intent": {"path": "none"}, "fields": {}, "missing": []})
        step = session.current_step
        text = (reply or "").strip()
        action = action_id.strip()

        if step == "ask_address":
            if text.lower() == "skip" and draft.get("fields"):
                return await FlowEngine._advance_address_collect(db, session, state, draft)
            if not text:
                return BotResponse(text=f"Please send your address to continue.\n\n{ADDRESS_TEMPLATE_HINT}")
            fields, missing = parse_free_text_address(text)
            draft["fields"] = fields
            draft["missing"] = missing
            return await FlowEngine._advance_address_collect(db, session, state, draft)

        if step.startswith("ask_missing_"):
            field = step.replace("ask_missing_", "")
            if not text:
                return BotResponse(text=f"Please send your {field} to continue.")
            if field == "state":
                matched = match_state(text)
                if not matched:
                    return BotResponse(text=f"We don't recognize \"{text}\" as a state we deliver to — please check the spelling and try again (e.g. Lagos, Rivers, FCT).")
                draft["fields"]["state"] = matched
            elif field == "country":
                matched = match_country(text)
                if not matched:
                    return BotResponse(text=f"We don't currently deliver to \"{text}\" — supported countries: Nigeria, Ghana, Kenya, South Africa. Please try again.")
                draft["fields"]["country"] = matched
            else:
                draft["fields"][field] = text
            draft["missing"] = [f for f in draft.get("missing", []) if f != field]
            return await FlowEngine._advance_address_collect(db, session, state, draft)

        if step == "confirm_address":
            if action == "address_confirm" or text.lower() in ("yes", "confirm", "correct"):
                return await FlowEngine._complete_address_collect(db, session, draft)
            if action.startswith("address_edit_"):
                field = action.replace("address_edit_", "")
                draft["missing"] = [field]
                state["address_draft"] = draft
                await MemoryManager.update_flow_state(db, session, active_flow="address_collect", current_step=f"ask_missing_{field}", state_data=state)
                current_val = draft["fields"].get(field)
                current_hint = f" (currently: *{current_val}*)" if current_val else ""
                return BotResponse(text=f"What should the {field} be?{current_hint}")
            return BotResponse(
                text="Please confirm your address, or tap a field to change it.",
                buttons=_buttons(FlowEngine._address_confirm_buttons()),
            )

        # Unknown step — bail out to main menu rather than get stuck.
        await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None)
        return BotResponse(text=get_main_menu_text(), buttons=_buttons(MAIN_MENU_BUTTONS))

    @staticmethod
    def _address_confirm_buttons() -> List[Dict[str, str]]:
        return [
            {"id": "address_confirm", "title": "✅ Confirm Address"},
            {"id": "address_edit_street", "title": "✏️ Street"},
            {"id": "address_edit_city", "title": "✏️ City"},
            {"id": "address_edit_state", "title": "✏️ State"},
            {"id": "address_edit_zip", "title": "✏️ Zip Code"},
            {"id": "address_edit_country", "title": "✏️ Country"},
        ]

    @staticmethod
    async def _advance_address_collect(db: AsyncSession, session: ConversationSession, state: Dict[str, Any], draft: Dict[str, Any]) -> BotResponse:
        state["address_draft"] = draft
        missing = draft.get("missing", [])
        if missing:
            next_field = missing[0]
            await MemoryManager.update_flow_state(db, session, active_flow="address_collect", current_step=f"ask_missing_{next_field}", state_data=state)
            prompts = {
                "street": "What's the street address?",
                "city": "What city is this for?",
                "state": "Which state? (e.g. Lagos, Rivers, FCT)",
                "zip": "What's the zip/postal code?",
                "country": "Which country? (Nigeria, Ghana, Kenya, or South Africa)",
            }
            return BotResponse(text=prompts.get(next_field, f"What's the {next_field}?"))

        await MemoryManager.update_flow_state(db, session, active_flow="address_collect", current_step="confirm_address", state_data=state)
        return BotResponse(
            text=f"📦 Please confirm your delivery address:\n\n{format_address_confirmation(draft['fields'])}",
            buttons=_buttons(FlowEngine._address_confirm_buttons()),
        )

    @staticmethod
    async def _complete_address_collect(db: AsyncSession, session: ConversationSession, draft: Dict[str, Any]) -> BotResponse:
        customer = None
        if session.channel in ("whatsapp", "telegram"):
            customer = await get_customer(db, session.channel, session.customer_identifier)
            if not customer:
                customer = await upsert_customer(db, session.channel, session.customer_identifier)
            if customer:
                await save_delivery_address(db, customer, draft["fields"])
                try:
                    from app.cloud_sync.client import cloud_client
                    cloud_client.track(
                        channel=session.channel,
                        customer_id=session.customer_identifier,
                        event="delivery_address_saved",
                        metadata={"fields": draft["fields"]},
                    )
                except Exception as e:
                    logger.warning(f"Failed to track delivery_address_saved telemetry: {e}")

        state = MemoryManager.get_flow_state_data(session)
        state.pop("address_draft", None)
        await MemoryManager.update_flow_state(db, session, active_flow=None, current_step=None, state_data=state)

        resume_intent = draft.get("resume_intent", {"path": "none"})
        path = resume_intent.get("path")

        if path == "cart":
            return await FlowEngine._build_checkout_response(
                db, session, customer,
                name_override=resume_intent.get("name"), email_override=resume_intent.get("email"), phone_override=resume_intent.get("phone"),
            )
        # Note: no "ai_tool" resume path here (unlike profile_collect) — the
        # AI-tool checkout path (create_order/generate_payment_link) never
        # triggers address_collect today; it just passes through whatever
        # shipping_address string the LLM already extracted. Wiring the LLM
        # tool-calling loop to pause on a missing structured address is a
        # separate, real piece of work, not yet built.

        return BotResponse(
            text=(
                "✅ *Delivery address saved!*\n\n"
                f"{format_address_confirmation(draft['fields'])}\n\n"
                "What would you like to do next?"
            ),
            buttons=_buttons([
                {"id": "flow_my_profile", "title": "👤 Back to Profile"},
                {"id": "flow_browse_catalog", "title": "🛍️ Browse Products"},
                {"id": "flow_main_menu", "title": "🏠 Main Menu"},
            ]),
        )

    @staticmethod
    def _get_widget_address(session: ConversationSession) -> Optional[Dict[str, Any]]:
        state = MemoryManager.get_flow_state_data(session)
        return state.get("widget_address")

    @staticmethod
    async def set_widget_address(db: AsyncSession, session: ConversationSession, fields: Dict[str, Any]) -> None:
        """Stores the widget's one-shot structured address form submission for
        this session only — mirrors set_widget_profile (no durable Customer
        row for widget sessions)."""
        state = MemoryManager.get_flow_state_data(session)
        state["widget_address"] = fields
        await MemoryManager.update_flow_state(
            db, session, active_flow=session.active_flow, current_step=session.current_step, state_data=state,
        )

    @staticmethod
    def _widget_address_required_response() -> BotResponse:
        return BotResponse(
            text="📦 This order needs a delivery address. Please fill in the address form to continue.",
            buttons=_buttons([{"id": "flow_view_cart", "title": "🛒 Back to Cart"}]),
            requires_widget_form="address",
        )

    @staticmethod
    async def _build_checkout_response(
        db: AsyncSession,
        session: ConversationSession,
        customer: Optional[Customer],
        name_override: Optional[str] = None,
        email_override: Optional[str] = None,
        phone_override: Optional[str] = None,
        shipping_address_override: Optional[str] = None,
    ) -> BotResponse:
        """Builds the order + Paystack checkout link from the current cart, using
        a resolved customer profile instead of a synthetic placeholder email."""
        cart = CartManager.get_cart(session)
        if not cart:
            return BotResponse(
                text="🛒 *Your cart is currently empty!* Please add items first before checking out.",
                buttons=_buttons(CART_EMPTY_BUTTONS),
            )

        customer_name = name_override or (customer.name if customer else None)
        customer_email = email_override or (customer.email if customer else None)
        customer_phone = phone_override or (customer.phone_number if customer else None)

        shipping_address = shipping_address_override
        if not shipping_address:
            saved_address = get_delivery_address(customer)
            if saved_address:
                shipping_address = address_to_single_line(saved_address)

        currency = cart[0].get("currency", "NGN") if cart else "NGN"

        from app.commerce.checkout import create_checkout_orders
        order_results = await create_checkout_orders(
            db,
            items=cart,
            currency=currency,
            customer_identifier=session.customer_identifier,
            channel=session.channel,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            shipping_address=shipping_address,
            gateway="paystack",
        )

        await CartManager.clear_cart(db, session)

        from app.cloud_sync.client import cloud_client
        for res in order_results:
            cloud_client.track(
                channel=session.channel,
                customer_id=session.customer_identifier,
                event="payment_initiated",
                status="pending" if res.get("checkout_url") else "failed",
                amount=res.get("total_amount", 0.0),
                metadata={
                    "order_reference": res["order_reference"],
                    "currency": res.get("currency"),
                    "checkout_url": res.get("checkout_url"),
                    "gateway": res.get("gateway"),
                },
            )

        # A mixed cart (some items sold via commb's own catalog, some
        # Bumpa-sourced) produces two separate orders/payments — each needs
        # its own link and its own "I've Paid" confirmation, since they're
        # two independent charges even though the customer experienced it
        # as one checkout.
        if len(order_results) == 1 and order_results[0].get("checkout_url"):
            res = order_results[0]
            order_summary = [
                f"🎉 *Order #{res['order_reference']} Created!*",
                f"\n💵 *Total to Pay:* {res['total_amount']:,.2f} {res['currency']}",
                f"\n👉 *Pay Now:*",
                f"{res['checkout_url']}",
                f"\n_We will notify you immediately once payment is confirmed!_",
            ]
            return BotResponse(
                text="\n".join(order_summary),
                buttons=_buttons([
                    {"id": f"flow_confirm_payment_{res['order_reference']}", "title": "✅ I've Paid"},
                    {"id": "flow_track_order", "title": "📦 Track Order"},
                    {"id": "flow_main_menu", "title": "🏠 Main Menu"},
                ]),
                checkout_url=res["checkout_url"],
            )

        lines = ["🎉 *Your order was split into separate payments* (some items ship via a different store):"]
        buttons = []
        for res in order_results:
            if res.get("checkout_url"):
                lines.append(f"\n*Order #{res['order_reference']}* — {res['total_amount']:,.2f} {res['currency']}\n{res['checkout_url']}")
                buttons.append({"id": f"flow_confirm_payment_{res['order_reference']}", "title": f"✅ Paid {res['order_reference']}"})
            else:
                lines.append(f"\n*Order #{res['order_reference']}* — ⚠️ couldn't generate a payment link right now. Please try again shortly.")
        lines.append("\n_We will notify you immediately once each payment is confirmed!_")
        buttons.append({"id": "flow_track_order", "title": "📦 Track Orders"})
        buttons.append({"id": "flow_main_menu", "title": "🏠 Main Menu"})

        return BotResponse(text="\n".join(lines), buttons=_buttons(buttons))

    @staticmethod
    async def _resume_ai_checkout_intent(
        db: AsyncSession,
        session: ConversationSession,
        customer: Optional[Customer],
        resume_intent: Dict[str, Any],
        draft: Dict[str, Any],
    ) -> BotResponse:
        """Replays an AI-tool-triggered checkout (create_order / generate_payment_link)
        now that a complete profile exists, since the AI path doesn't share the
        button path's cart and can't simply resume through _build_checkout_response."""
        from app.ai.tools import ToolExecutor

        customer_name = draft.get("name") or (customer.name if customer else None)
        customer_email = draft.get("email") or (customer.email if customer else None)
        customer_phone = draft.get("phone") or (customer.phone_number if customer else None)

        tool = resume_intent.get("tool")
        if tool == "create_order":
            result = await ToolExecutor._create_order_with_profile(
                db, session,
                items=resume_intent.get("items", []),
                shipping_address=resume_intent.get("shipping_address"),
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
        elif tool == "generate_payment_link":
            result = await ToolExecutor._generate_payment_link_with_profile(
                db, session,
                order_reference=resume_intent.get("order_reference"),
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
        else:
            result = None

        if not result:
            return BotResponse(text="Thanks! Your details are saved. Please try checking out again.", buttons=_buttons(MAIN_MENU_BUTTONS))

        checkout_url = result.get("checkout_url")
        order_ref = result.get("order_reference", "")
        total_amount = result.get("total_amount", 0)
        currency = result.get("currency", "NGN")

        order_summary = [
            f"🎉 *Order #{order_ref} Created!*",
            f"\n💵 *Total to Pay:* {total_amount:,.2f} {currency}" if total_amount else "",
            f"\n👉 *Pay Now via Paystack:*" if checkout_url else "",
            f"{checkout_url}" if checkout_url else "",
        ]
        return BotResponse(
            text="\n".join([line for line in order_summary if line]),
            buttons=_buttons([
                {"id": f"flow_confirm_payment_{order_ref}", "title": "✅ I've Paid"},
                {"id": "flow_main_menu", "title": "🏠 Main Menu"},
            ]) if order_ref else _buttons(MAIN_MENU_BUTTONS),
            checkout_url=checkout_url,
        )
