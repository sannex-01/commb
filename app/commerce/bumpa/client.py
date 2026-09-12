from typing import Dict, Any, Optional, List
import httpx
from app.core.config import settings
from app.core.logger import logger


class BumpaClient:
    """Bumpa Commerce API client — confirmed against docs.bumpa.io.

    Base path: /api/commerce/v1. Auth is split in two:
      - a PUBLIC key for catalog/cart/checkout routes (customer-facing)
      - a SECRET key for merchant order/analytics routes (business-facing)
    Guest cart/checkout flows additionally carry an X-Cart-Token once a cart
    has been created — see checkout_via_bumpa below for the full sequence.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        public_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.secret_key = api_key or settings.BUMPA_API_KEY
        self.public_key = public_key or settings.BUMPA_PUBLIC_API_KEY
        self.base_url = (base_url or settings.BUMPA_API_BASE_URL).rstrip("/")

    def _public_headers(self, cart_token: Optional[str] = None) -> Dict[str, str]:
        # Prefer the real public key, but fall back to the secret key when
        # only that's configured — existing deployments/callers (catalog
        # import) were built before the public/secret split was confirmed
        # against the real docs, and only ever set one key. Bumpa's own
        # docs don't document what a secret key does against a public-only
        # route, so this fallback is a best-effort compatibility shim, not
        # a guarantee — a business relying on real checkout should set both.
        key = self.public_key or self.secret_key
        if not key:
            raise ValueError("Bumpa public API key is not configured.")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": key,
        }
        if cart_token:
            headers["X-Cart-Token"] = cart_token
        return headers

    def _secret_headers(self) -> Dict[str, str]:
        if not self.secret_key:
            raise ValueError("Bumpa secret API key is not configured.")
        return {
            "Accept": "application/json",
            "X-Api-Key": self.secret_key,
        }

    async def fetch_products(self, limit: int = 50, location_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches published products from the public commerce catalog.
        Uses the PUBLIC key — catalog listing is a public-key route per
        docs.bumpa.io, not the secret/merchant key."""
        params = {"limit": limit}
        if location_id or settings.BUMPA_STORE_ID:
            params["location_id"] = location_id or settings.BUMPA_STORE_ID
        url = f"{self.base_url}/products"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._public_headers(), params=params)
                data = res.json()
                if res.status_code == 200:
                    products = []
                    items = data.get("data", []) if isinstance(data.get("data"), list) else data.get("products", [])
                    for p in items:
                        products.append({
                            "external_id": str(p.get("id")),
                            "title": p.get("name") or p.get("title"),
                            "description": p.get("description", ""),
                            "price": float(p.get("price", 0.0)),
                            "currency": p.get("currency", "NGN"),
                            "in_stock": p.get("quantity", 1) > 0,
                            "stock_quantity": int(p.get("quantity", 100)),
                            # Real Bumpa response has a ready-to-use top-level
                            # image_url (confirmed against a real API call);
                            # its "images" array entries only carry relative
                            # "path"/"thumbnail_path" fields, not a "url" —
                            # optimized_image_url (CDN-resized) is preferred
                            # when present.
                            "image_url": p.get("optimized_image_url") or p.get("image_url"),
                            "source": "bumpa",
                        })
                    return products
                else:
                    logger.error(f"Bumpa products fetch failed: {res.text}")
                    return []
        except Exception as e:
            logger.error(f"Bumpa client error: {e}")
            return []

    # ------------------------------------------------------------------
    # Checkout flow — cart -> checkout -> totals -> payment intent ->
    # (customer pays on the returned Paystack authorization_url) -> finalize.
    # Every step here uses the PUBLIC key + the cart token minted by
    # create_cart. See docs.bumpa.io "Public Cart" / "Public Checkout".
    # ------------------------------------------------------------------

    async def create_cart(self, location_id: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/carts"
        body = {"location_id": location_id or settings.BUMPA_STORE_ID}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=body, headers=self._public_headers())
            data = res.json()
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Bumpa create_cart failed: {res.status_code} {res.text}")
            return data

    async def add_cart_item(
        self,
        cart_token: str,
        product_id: str,
        quantity: int,
        location_id: Optional[str] = None,
        product_variation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/carts/items"
        body: Dict[str, Any] = {
            "location_id": location_id or settings.BUMPA_STORE_ID,
            "product_id": product_id,
            "quantity": quantity,
        }
        if product_variation_id:
            body["product_variation_id"] = product_variation_id
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=body, headers=self._public_headers(cart_token))
            data = res.json()
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Bumpa add_cart_item failed ({product_id}): {res.status_code} {res.text}")
            return data

    async def get_shipping_options(
        self,
        cart_token: str,
        cart_id: str,
        fulfillment_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """fulfillment_context: {type: "delivery", first_name, last_name,
        email, phone, street, city, state, country, zip, continent?,
        latitude?, longitude?, pickup_date?}."""
        url = f"{self.base_url}/shipping-options"
        body = {"cart_id": cart_id, "fulfillment_context": fulfillment_context}
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=body, headers=self._public_headers(cart_token))
            data = res.json()
            if res.status_code != 200:
                raise RuntimeError(f"Bumpa get_shipping_options failed: {res.status_code} {res.text}")
            return data

    async def create_checkout(
        self,
        cart_token: str,
        cart_id: str,
        customer_context: Dict[str, Any],
        fulfillment_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/checkouts"
        body = {
            "cart_id": cart_id,
            "customer_context": customer_context,
            "fulfillment_context": fulfillment_context,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=body, headers=self._public_headers(cart_token))
            data = res.json()
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Bumpa create_checkout failed: {res.status_code} {res.text}")
            return data

    async def calculate_totals(self, cart_token: str, checkout_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/checkouts/{checkout_id}/calculate-totals"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json={}, headers=self._public_headers(cart_token))
            data = res.json()
            if res.status_code != 200:
                raise RuntimeError(f"Bumpa calculate_totals failed: {res.status_code} {res.text}")
            return data

    async def create_payment_intent(self, cart_token: str, checkout_id: str) -> Dict[str, Any]:
        """Creates (or retries) a Paystack payment intent for this checkout.
        Response includes authorization_url, reference, amount, amount_minor,
        currency, order_id — per docs.bumpa.io."""
        url = f"{self.base_url}/checkouts/{checkout_id}/payment-intent"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json={}, headers=self._public_headers(cart_token))
            data = res.json()
            if res.status_code != 200:
                raise RuntimeError(f"Bumpa create_payment_intent failed: {res.status_code} {res.text}")
            return data

    async def finalize_checkout(
        self,
        cart_token: str,
        checkout_id: str,
        payment_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call after the customer's payment is confirmed (commb's own
        Paystack webhook/verify already did this) to close the loop on
        Bumpa's side. Idempotent — safe to call more than once.
        payment_details, when given: {"data": {id, currency, reference,
        amount, status}} using the SAME values Paystack returned."""
        url = f"{self.base_url}/checkouts/{checkout_id}/finalize"
        body = {"payment_details": payment_details} if payment_details else {}
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=body, headers=self._public_headers(cart_token))
            data = res.json()
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Bumpa finalize_checkout failed: {res.status_code} {res.text}")
            return data

    async def checkout_via_bumpa(
        self,
        items: List[Dict[str, Any]],
        customer_email: str,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        shipping_address: Optional[Dict[str, Any]] = None,
        location_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """High-level orchestration of the full cart -> checkout ->
        payment-intent sequence, returning just what UnifiedPaymentManager's
        callers expect: {checkout_url, reference, amount, currency, order_id,
        bumpa_checkout_id, bumpa_cart_token}. The last two are stashed by the
        caller (into Order.metadata_json) so finalize_checkout can be called
        later once our own Paystack webhook confirms the charge.

        items: [{"external_id": "<bumpa product id>", "quantity": int,
                 "variant_external_id": Optional[str]}, ...] — every item
        MUST be Bumpa-sourced (checked by the caller before this is invoked;
        this method doesn't itself filter mixed carts).
        """
        if not shipping_address:
            # Bumpa requires pickup_location_id for type=pickup — commb has
            # no pickup-location concept today, so this only works once a
            # shipping_address is actually supplied. Checked up front,
            # before any real API calls, rather than discovered midway
            # through cart creation.
            raise RuntimeError(
                "Bumpa checkout needs a delivery address — pickup isn't "
                "supported yet (commb has no pickup-location selection)."
            )

        cart_res = await self.create_cart(location_id=location_id)
        cart_token = cart_res.get("cart_token") or cart_res.get("data", {}).get("cart_token")
        cart_id = cart_res.get("cart_id") or cart_res.get("id") or cart_res.get("data", {}).get("id")
        if not cart_token or not cart_id:
            raise RuntimeError(f"Bumpa create_cart returned an unexpected shape: {cart_res}")

        for item in items:
            await self.add_cart_item(
                cart_token=cart_token,
                product_id=item["external_id"],
                quantity=int(item.get("quantity", 1)),
                location_id=location_id,
                product_variation_id=item.get("variant_external_id"),
            )

        name_parts = (customer_name or "Valued Customer").split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Real docs.bumpa.io flow: a delivery checkout needs a real
        # shipping_method_id, obtained by first calling /shipping-options
        # with the delivery details — Create Checkout itself does not
        # compute or accept raw address fields for rating, only the
        # resolved shipping_id from that call.
        shipping_fulfillment_context = {
            "type": "delivery",
            "first_name": first_name,
            "last_name": last_name,
            "email": customer_email,
            "phone": customer_phone or "",
            **shipping_address,
        }
        shipping_res = await self.get_shipping_options(cart_token, cart_id, shipping_fulfillment_context)
        shipping_options = shipping_res.get("data", {}).get("shipping_options") or shipping_res.get("shipping_options") or []
        if not shipping_options:
            raise RuntimeError(
                "Bumpa returned no shipping options for this address — cannot "
                "complete a delivery checkout. Try pickup, or a different address."
            )
        shipping_id = shipping_options[0].get("shipping_id")
        fulfillment_context: Dict[str, Any] = {"type": "delivery", "shipping_method_id": shipping_id}

        checkout_res = await self.create_checkout(
            cart_token=cart_token,
            cart_id=cart_id,
            customer_context={"email": customer_email, "first_name": first_name, "last_name": last_name},
            fulfillment_context=fulfillment_context,
        )
        checkout_data = checkout_res.get("data", checkout_res)
        checkout_id = checkout_data.get("id") or checkout_data.get("checkout_id")
        if not checkout_id:
            raise RuntimeError(f"Bumpa create_checkout returned an unexpected shape: {checkout_res}")

        await self.calculate_totals(cart_token, checkout_id)
        intent_res = await self.create_payment_intent(cart_token, checkout_id)
        intent_data = intent_res.get("data", intent_res)

        authorization_url = intent_data.get("authorization_url")
        reference = intent_data.get("reference")
        if not authorization_url or not reference:
            raise RuntimeError(f"Bumpa create_payment_intent returned an unexpected shape: {intent_res}")

        return {
            "checkout_url": authorization_url,
            "reference": reference,
            "amount": intent_data.get("amount"),
            "currency": intent_data.get("currency"),
            "order_id": intent_data.get("order_id"),
            "bumpa_checkout_id": checkout_id,
            "bumpa_cart_token": cart_token,
        }

    async def create_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """NOTE: docs.bumpa.io's confirmed public API has no direct
        "create order" write endpoint — orders only come into existence via
        the checkout -> finalize flow above. This method predates that
        confirmation and is kept only so app/commerce/fulfillment.py (which
        pushes an order that was PAID ELSEWHERE to Bumpa for fulfillment)
        doesn't hard-fail on import; it is NOT verified against the real API
        and should not be trusted until fulfillment.py's Bumpa path is
        re-verified against a live sandbox."""
        url = f"{self.base_url}/orders"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=order_data, headers=self._secret_headers())
            return res.json()
