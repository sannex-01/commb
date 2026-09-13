import csv
import io
import json
from typing import Optional, List, Literal
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core import entitlements
from app.core.database import get_db
from app.core.security import get_current_admin_user, require_admin_role
from app.models.catalog import CatalogItem
from app.models.product_variant import ProductVariant
from app.models.access_group import AccessGroup
from app.models.user import AdminUser
from app.models.business import BusinessProfile
from app.core.access import parse_tags_json, parse_ids_json

router = APIRouter(prefix="/admin/catalog", tags=["Admin Catalog Management"])


class ProductVariantRequest(BaseModel):
    id: Optional[int] = None  # present on update = keep/edit this row; absent = new row
    name: str
    sku: Optional[str] = None
    price_override: Optional[float] = None
    stock_quantity: int = 100
    in_stock: bool = True
    track_stock: bool = True  # False = unlimited, never decremented


class CatalogItemCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    # No longer settable per-product from the dashboard form — a locally
    # created product always uses the business's own default currency
    # (see create_catalog_item, which overwrites this regardless of what's
    # sent). Kept as a field, not removed outright, because catalog rows
    # imported from Paystack/Bumpa (a different code path, sync_external_catalog)
    # DO carry a real per-item currency from that platform, and every
    # existing read site (cart, checkout, AI tool responses) already
    # depends on CatalogItem.currency existing — this only changes what a
    # LOCAL product's currency is set to, not the column itself.
    currency: str = "NGN"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: bool = True
    stock_quantity: int = 100
    # None = derive from fulfillment_type (physical -> True, service/digital
    # -> False). An explicit bool always wins.
    track_stock: Optional[bool] = None
    access_group_ids: Optional[List[int]] = []
    access_tags: Optional[List[str]] = []
    variants: Optional[List[ProductVariantRequest]] = None
    fulfillment_type: Literal["physical", "digital", "service"] = "physical"
    digital_asset_url: Optional[str] = None
    requires_shipping: Optional[bool] = None  # None = derive from fulfillment_type


class CatalogItemUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: Optional[bool] = None
    stock_quantity: Optional[int] = None
    track_stock: Optional[bool] = None
    access_group_ids: Optional[List[int]] = None
    access_tags: Optional[List[str]] = None
    fulfillment_type: Optional[Literal["physical", "digital", "service"]] = None
    digital_asset_url: Optional[str] = None
    requires_shipping: Optional[bool] = None
    # Sentinel: None = "don't touch variants" (a normal field edit that
    # doesn't mention variants at all); [] = "explicitly clear all
    # variants"; a populated list = "replace variants with these rows."
    # A plain Optional[List[...]] can't tell "field omitted" apart from
    # "field sent as null" once deserialized, so callers must send `[]`
    # (not omit the key, not send `null`) to intentionally clear variants —
    # documented on the dashboard form's save handler too.
    variants: Optional[List[ProductVariantRequest]] = None


def _serialize_variant(v: ProductVariant) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "sku": v.sku,
        "price_override": v.price_override,
        "stock_quantity": v.stock_quantity,
        "in_stock": v.in_stock,
        "track_stock": bool(getattr(v, "track_stock", True)),
    }


def _serialize_catalog_item(itm: CatalogItem, groups_map: Optional[dict] = None, variants: Optional[List[ProductVariant]] = None) -> dict:
    group_ids = parse_ids_json(getattr(itm, "access_group_ids_json", "[]"))
    tags = parse_tags_json(itm.access_tags_json)

    group_names = []
    if groups_map:
        for gid in group_ids:
            if gid in groups_map:
                group_names.append(groups_map[gid])

    return {
        "id": itm.id,
        "source": itm.source,
        "external_id": itm.external_id,
        "title": itm.title,
        "description": itm.description,
        "price": itm.price,
        "currency": itm.currency,
        "category": itm.category,
        "subcategory": itm.subcategory,
        "image_url": itm.image_url,
        "in_stock": itm.in_stock,
        "stock_quantity": itm.stock_quantity,
        "track_stock": bool(getattr(itm, "track_stock", True)),
        "access_group_ids": group_ids,
        "access_group_names": group_names,
        "access_tags": tags,
        "is_global": not bool(group_ids or tags),
        "has_variants": bool(itm.has_variants),
        "variants": [_serialize_variant(v) for v in variants] if variants is not None else None,
        "fulfillment_type": itm.fulfillment_type or "physical",
        "digital_asset_url": itm.digital_asset_url,
        "requires_shipping": bool(itm.requires_shipping),
        "created_at": itm.created_at.isoformat() if itm.created_at else None,
    }


async def _replace_variants(db: AsyncSession, catalog_item_id: int, variant_reqs: List[ProductVariantRequest]) -> None:
    """Deletes any existing variants not present in variant_reqs (by id) and
    creates/updates the rest. Called only when the caller explicitly sent a
    `variants` list (see the sentinel note on CatalogItemUpdateRequest)."""
    stmt = select(ProductVariant).where(ProductVariant.catalog_item_id == catalog_item_id)
    res = await db.execute(stmt)
    existing = {v.id: v for v in res.scalars().all()}

    keep_ids = set()
    for vr in variant_reqs:
        if vr.id and vr.id in existing:
            v = existing[vr.id]
            v.name = vr.name.strip()
            v.sku = vr.sku.strip() if vr.sku else None
            v.price_override = vr.price_override
            v.stock_quantity = vr.stock_quantity
            v.in_stock = vr.in_stock
            v.track_stock = vr.track_stock
            keep_ids.add(vr.id)
        else:
            new_variant = ProductVariant(
                catalog_item_id=catalog_item_id,
                name=vr.name.strip(),
                sku=vr.sku.strip() if vr.sku else None,
                price_override=vr.price_override,
                stock_quantity=vr.stock_quantity,
                in_stock=vr.in_stock,
                track_stock=vr.track_stock,
            )
            db.add(new_variant)

    for vid, v in existing.items():
        if vid not in keep_ids:
            await db.delete(v)


@router.get("/stats")
async def get_catalog_stats(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Catalog-wide summary stats for the Products & Catalog page's stat
    cards (mirrors the shape of Bumpa's own catalog stats row). Computed
    across the WHOLE catalog, not just the current page of results —
    list_admin_catalog is paginated (default 50/page), so summing its
    `items` alone would undercount any store with more than one page of
    products.

    "Total Inventory Value" (Bumpa's own metric, cost-basis) isn't shown
    here — CatalogItem has no separate cost_price field, only the selling
    price, so a true cost-based figure isn't derivable. "Total Units in
    Stock" is shown instead as a real, honestly-computed number from data
    we actually track, rather than faking a cost figure."""
    from app.models.order import Order

    all_items_res = await db.execute(select(CatalogItem))
    all_items = all_items_res.scalars().all()

    # Unlimited-stock items (track_stock=False — services, digital goods)
    # have no meaningful unit count, so they're excluded from unit/value
    # totals and can never be "out of stock".
    tracked_in_stock = [itm for itm in all_items if itm.in_stock and getattr(itm, "track_stock", True)]
    total_retail_value = sum((itm.price or 0.0) * (itm.stock_quantity or 0) for itm in tracked_in_stock)
    total_units_in_stock = sum((itm.stock_quantity or 0) for itm in tracked_in_stock)
    out_of_stock_count = sum(
        1 for itm in all_items
        if getattr(itm, "track_stock", True) and (not itm.in_stock or (itm.stock_quantity or 0) <= 0)
    )

    # Products sold: real units sold across PAID orders, matched by the
    # cart line's own item_id/product_id (same approach as the Reports
    # page's top-products fix) rather than a fabricated or title-guessed
    # count.
    paid_orders_res = await db.execute(select(Order).where(Order.status == "paid"))
    paid_orders = paid_orders_res.scalars().all()
    products_sold = 0
    for o in paid_orders:
        try:
            items = json.loads(o.items_json or "[]")
        except Exception:
            continue
        products_sold += sum(int(item.get("quantity", 1)) for item in items)

    return {
        "total_retail_value": round(total_retail_value, 2),
        "total_units_in_stock": total_units_in_stock,
        "products_sold": products_sold,
        "out_of_stock_count": out_of_stock_count,
    }


@router.get("")
async def list_admin_catalog(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Lists catalog items with search and access tags / group scopes."""
    stmt = select(CatalogItem)
    conditions = []

    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(CatalogItem.title.ilike(term), CatalogItem.description.ilike(term)))
    if category:
        conditions.append(CatalogItem.category.ilike(f"%{category.strip()}%"))

    if conditions:
        stmt = stmt.where(*conditions)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    offset = (page - 1) * limit
    stmt = stmt.order_by(desc(CatalogItem.created_at)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    items = res.scalars().all()

    # Fetch access groups map
    grp_res = await db.execute(select(AccessGroup))
    groups_map = {g.id: g.name for g in grp_res.scalars().all()}

    return {
        "items": [_serialize_catalog_item(itm, groups_map) for itm in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


async def _build_catalog_item_from_request(db: AsyncSession, req: CatalogItemCreateRequest) -> CatalogItem:
    """Shared construction logic for a new local catalog item — used by both
    the single-product create endpoint and the CSV bulk importer below, so
    the two never drift on business rules (effective currency, derived
    requires_shipping, access tag/group merging). Adds the item (and any
    variants) to the session via db.add/flush but does NOT commit — callers
    decide whether to commit per-item or batch the whole import in one
    transaction."""
    group_ids = [int(gid) for gid in (req.access_group_ids or []) if gid]
    tags_clean = [t.strip().lower() for t in (req.access_tags or []) if t.strip()]

    # If group_ids are provided, also record group IDs in tags for dual-query compatibility
    combined_tags = list(set(tags_clean + [str(gid) for gid in group_ids]))

    # requires_shipping defaults to "does this actually ship" — physical
    # items ship by default, digital/service items don't — unless the
    # caller explicitly overrides it (e.g. a physical item picked up
    # in-store, no delivery address needed even though it's a real good).
    effective_requires_shipping = req.requires_shipping if req.requires_shipping is not None else (req.fulfillment_type == "physical")

    # track_stock defaults to "does this have countable inventory" — physical
    # goods are tracked, service/digital items aren't (nothing to count) —
    # unless the caller explicitly sets it either way.
    effective_track_stock = req.track_stock if req.track_stock is not None else (req.fulfillment_type == "physical")

    # A locally-created product always uses the business's own default
    # currency — no per-product currency picker on the dashboard form
    # anymore. Whatever req.currency carries (the field still exists for
    # API compatibility) is ignored here; only sync_external_catalog
    # (Paystack/Bumpa imports) sets a real per-item currency, since those
    # platforms can genuinely differ from the business's own default.
    biz_res = await db.execute(select(BusinessProfile).limit(1))
    biz = biz_res.scalar_one_or_none()
    effective_currency = (biz.currency if biz and biz.currency else "NGN").strip().upper()

    item = CatalogItem(
        source="local",
        title=req.title.strip(),
        description=req.description.strip() if req.description else None,
        price=req.price,
        currency=effective_currency,
        category=req.category.strip() if req.category else None,
        subcategory=req.subcategory.strip() if req.subcategory else None,
        image_url=req.image_url.strip() if req.image_url else None,
        in_stock=req.in_stock,
        stock_quantity=req.stock_quantity,
        track_stock=effective_track_stock,
        access_group_ids_json=json.dumps(group_ids),
        access_tags_json=json.dumps(combined_tags),
        has_variants=bool(req.variants),
        fulfillment_type=req.fulfillment_type,
        digital_asset_url=req.digital_asset_url.strip() if req.digital_asset_url else None,
        requires_shipping=effective_requires_shipping,
    )
    db.add(item)
    await db.flush()  # assigns item.id before variants reference it

    if req.variants:
        for vr in req.variants:
            db.add(ProductVariant(
                catalog_item_id=item.id,
                name=vr.name.strip(),
                sku=vr.sku.strip() if vr.sku else None,
                price_override=vr.price_override,
                stock_quantity=vr.stock_quantity,
                in_stock=vr.in_stock,
                track_stock=vr.track_stock,
            ))

    return item


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_catalog_item(
    req: CatalogItemCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin_role),
):
    """Creates a new catalog product with access group assignments."""
    # No-op unless CommB Cloud provisioned this instance on a plan; a
    # self-hosted install has no product limit. See app/core/entitlements.py.
    existing = (await db.execute(select(func.count(CatalogItem.id)))).scalar() or 0
    entitlements.require_product_capacity(existing)

    item = await _build_catalog_item_from_request(db, req)
    await db.commit()
    await db.refresh(item)

    return _serialize_catalog_item(item)


@router.get("/{item_id}")
async def get_catalog_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    stmt = select(CatalogItem).where(CatalogItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog item not found")

    grp_res = await db.execute(select(AccessGroup))
    groups_map = {g.id: g.name for g in grp_res.scalars().all()}

    variant_res = await db.execute(select(ProductVariant).where(ProductVariant.catalog_item_id == item.id))
    variants = variant_res.scalars().all()

    return _serialize_catalog_item(item, groups_map, variants=variants)


@router.put("/{item_id}")
async def update_catalog_item(
    item_id: int,
    req: CatalogItemUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin_role),
):
    stmt = select(CatalogItem).where(CatalogItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog item not found")

    if req.title is not None:
        item.title = req.title.strip()
    if req.description is not None:
        item.description = req.description.strip() if req.description else None
    if req.price is not None:
        item.price = req.price
    if req.currency is not None:
        item.currency = req.currency.strip().upper()
    if req.category is not None:
        item.category = req.category.strip() if req.category else None
    if req.subcategory is not None:
        item.subcategory = req.subcategory.strip() if req.subcategory else None
    if req.image_url is not None:
        item.image_url = req.image_url.strip() if req.image_url else None
    if req.in_stock is not None:
        item.in_stock = req.in_stock
    if req.stock_quantity is not None:
        item.stock_quantity = req.stock_quantity
    if req.track_stock is not None:
        item.track_stock = req.track_stock
    if req.fulfillment_type is not None:
        item.fulfillment_type = req.fulfillment_type
    if req.digital_asset_url is not None:
        item.digital_asset_url = req.digital_asset_url.strip() if req.digital_asset_url else None
    if req.requires_shipping is not None:
        item.requires_shipping = req.requires_shipping

    if req.access_group_ids is not None:
        group_ids = [int(gid) for gid in req.access_group_ids if gid]
        item.access_group_ids_json = json.dumps(group_ids)
        tags_clean = [t.strip().lower() for t in (req.access_tags or parse_tags_json(item.access_tags_json)) if t.strip() and not t.isdigit()]
        combined_tags = list(set(tags_clean + [str(gid) for gid in group_ids]))
        item.access_tags_json = json.dumps(combined_tags)
    elif req.access_tags is not None:
        tags_clean = [t.strip().lower() for t in req.access_tags if t.strip()]
        item.access_tags_json = json.dumps(tags_clean)

    if req.variants is not None:
        # Sentinel: caller explicitly sent a variants list — [] clears all
        # variants, a populated list replaces them. Omitting the key
        # entirely (req.variants stays None) leaves existing variants
        # untouched, so a plain "edit the price" PUT doesn't need to know
        # or resend variant data.
        await _replace_variants(db, item.id, req.variants)
        item.has_variants = bool(req.variants)

    await db.commit()
    await db.refresh(item)

    return {"status": "ok", "message": "Catalog item updated successfully"}


@router.delete("/{item_id}")
async def delete_catalog_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_role),
):
    stmt = select(CatalogItem).where(CatalogItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog item not found")

    await db.delete(item)
    await db.commit()

    return {"status": "ok", "message": "Catalog item deleted"}


class CatalogImportRequest(BaseModel):
    source: Literal["bumpa", "paystack"]


@router.get("/import/status")
async def get_import_status(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Cheap, DB-only check of which external sources have a key configured
    — just enough to decide whether to show the "Import Catalog" button on
    page load. Deliberately does NOT call out to Bumpa/Paystack (unlike
    /import/providers below, which fetches the real product list for a
    live preview count) — that live fetch only needs to happen once the
    business actually opens the Import Catalog modal, not on every catalog
    page load/background refresh."""
    from app.services.store_connections import StoreConnectionService

    bumpa_secret_key = await StoreConnectionService.get_effective_bumpa_key(db)
    bumpa_public_key = await StoreConnectionService.get_effective_public_key(db, "bumpa")
    bumpa_configured = bool(bumpa_secret_key or bumpa_public_key)

    paystack_key = await StoreConnectionService.get_effective_key(db, "paystack")
    if not paystack_key:
        biz_res = await db.execute(select(BusinessProfile).limit(1))
        biz = biz_res.scalar_one_or_none()
        meta = json.loads(biz.metadata_json or "{}") if biz else {}
        if meta.get("payments", {}).get("provider") == "paystack":
            paystack_key = meta.get("payments", {}).get("config", {}).get("secret_key")
    paystack_key = paystack_key or settings.PAYSTACK_SECRET_KEY

    return {
        "bumpa": {"configured": bumpa_configured},
        "paystack": {"configured": bool(paystack_key)},
    }


@router.get("/import/providers")
async def list_import_providers(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Reports which external catalog sources are configured and ready to
    import from, with a live preview count — backs the dashboard's Import
    Catalog button (shown only when at least one provider is configured)
    and its confirmation screen ("We found 42 products in your Bumpa
    store"). Fetches the real product list to count it, but writes nothing.

    Keys are read the same way PaymentService/StoreConnectionService
    already resolve them elsewhere: a database-saved key (Store
    Connections tab for Bumpa, Payment Gateways tab for Paystack) takes
    priority, falling back to the instance's env var only if nothing is
    saved in the dashboard — .env is a deploy-time default, not where a
    business is expected to manage these keys day to day.

    Note: both BumpaClient.fetch_products and PaystackClient.fetch_products
    already swallow their own request errors and return [] rather than
    raising (see their own try/except blocks) — so a bad key or network
    issue surfaces here as preview_count: 0, not an exception. The
    try/except below is defensive for any error that isn't already
    caught upstream, not the primary path for a bad-credentials case."""
    from app.services.store_connections import StoreConnectionService

    providers = {}

    bumpa_secret_key = await StoreConnectionService.get_effective_bumpa_key(db)
    bumpa_public_key = await StoreConnectionService.get_effective_public_key(db, "bumpa")
    if bumpa_secret_key or bumpa_public_key:
        from app.commerce.bumpa.client import BumpaClient
        bumpa_cfg = await StoreConnectionService.get_connection_config(db, "bumpa")
        bumpa_location_id = bumpa_cfg.get("config", {}).get("store_id") or None
        try:
            products = await BumpaClient(api_key=bumpa_secret_key, public_key=bumpa_public_key).fetch_products(location_id=bumpa_location_id)
            providers["bumpa"] = {"configured": True, "preview_count": len(products)}
        except Exception:
            providers["bumpa"] = {"configured": True, "preview_count": None}
    else:
        providers["bumpa"] = {"configured": False, "preview_count": None}

    # Paystack's key for catalog import can come from either side: a
    # Store Connection entry (used for import only, or shared into
    # Payment Gateways via the toggle) or the Payment Gateway's own
    # independently-set key — check both, DB before env either way.
    paystack_key = await StoreConnectionService.get_effective_key(db, "paystack")
    if not paystack_key:
        biz_res = await db.execute(select(BusinessProfile).limit(1))
        biz = biz_res.scalar_one_or_none()
        meta = json.loads(biz.metadata_json or "{}") if biz else {}
        if meta.get("payments", {}).get("provider") == "paystack":
            paystack_key = meta.get("payments", {}).get("config", {}).get("secret_key")
    paystack_key = paystack_key or settings.PAYSTACK_SECRET_KEY

    if paystack_key:
        from app.commerce.payments.paystack import PaystackClient
        try:
            products = await PaystackClient(secret_key=paystack_key).fetch_products()
            providers["paystack"] = {"configured": True, "preview_count": len(products)}
        except Exception:
            providers["paystack"] = {"configured": True, "preview_count": None}
    else:
        providers["paystack"] = {"configured": False, "preview_count": None}

    return providers


@router.post("/import")
async def import_catalog(
    req: CatalogImportRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin_role),
):
    """Imports (creates new / updates existing) catalog items from the
    given external source. Reuses the same sync logic the background sync
    worker and Bumpa's product webhook already rely on — this just adds a
    business-triggered, confirmable entry point with a real result count."""
    from app.commerce.catalog_provider import CatalogManager
    from app.services.store_connections import StoreConnectionService

    resolved_key = None
    resolved_public_key = None
    resolved_location_id = None
    if req.source == "bumpa":
        resolved_key = await StoreConnectionService.get_effective_bumpa_key(db)
        resolved_public_key = await StoreConnectionService.get_effective_public_key(db, "bumpa")
        if not resolved_key and not resolved_public_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bumpa is not configured. Set it up under Integrations → Store Connections.")
        bumpa_cfg = await StoreConnectionService.get_connection_config(db, "bumpa")
        resolved_location_id = bumpa_cfg.get("config", {}).get("store_id") or None
    elif req.source == "paystack":
        resolved_key = await StoreConnectionService.get_effective_key(db, "paystack")
        if not resolved_key:
            biz_res = await db.execute(select(BusinessProfile).limit(1))
            biz = biz_res.scalar_one_or_none()
            meta = json.loads(biz.metadata_json or "{}") if biz else {}
            if meta.get("payments", {}).get("provider") == "paystack":
                resolved_key = meta.get("payments", {}).get("config", {}).get("secret_key")
        resolved_key = resolved_key or settings.PAYSTACK_SECRET_KEY
        if not resolved_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Paystack is not configured. Set it up under Integrations → Store Connections or Payment Gateways.")

    result = await CatalogManager.sync_external_catalog_detailed(db, source=req.source, api_key=resolved_key, public_key=resolved_public_key, location_id=resolved_location_id)
    return {"status": "ok", "source": req.source, **result}


# ---------------------------------------------------------------------------
# CSV bulk import — a business's own spreadsheet, not a connected storefront.
# Deliberately a separate pair of endpoints from /import (Bumpa/Paystack)
# above, since a CSV has no "source" to check credentials for and no live
# preview-count step; the dashboard's Import Catalog offcanvas offers both
# side by side.
# ---------------------------------------------------------------------------

# Column order also drives the downloaded template — keep in sync with
# _csv_row_to_request below, and with CatalogItemCreateRequest's fields.
# "currency" is deliberately NOT a column: a locally-created product always
# uses the business's own default currency (see _build_catalog_item_from_request).
# "in_stock" is deliberately NOT a column either: every CSV-imported product
# is always in stock (see _csv_row_to_request) — a business bulk-uploading a
# spreadsheet of products they're about to sell has no reason to import
# something already marked out of stock; they'd just toggle that later, per
# product, once real stock/sales data exists.
CSV_COLUMNS = [
    "title", "description", "price", "category", "subcategory",
    "image_url", "stock_quantity", "fulfillment_type",
    "digital_asset_url", "requires_shipping",
]

CSV_TEMPLATE_SAMPLE_ROWS = [
    {
        "title": "Velvet Silk Evening Gown",
        "description": "Handcrafted emerald green velvet gown with crystal details.",
        "price": "500.00",
        "category": "Fashion & Apparel",
        "subcategory": "Dresses & Gowns",
        "image_url": "https://example.com/images/gown.jpg",
        "stock_quantity": "20",
        "fulfillment_type": "physical",
        "digital_asset_url": "",
        "requires_shipping": "TRUE",
    },
    {
        "title": "Brand Style Guide (PDF)",
        "description": "Downloadable PDF sent automatically after payment.",
        "price": "15.00",
        "category": "Digital Products",
        "subcategory": "Ebooks & Guides",
        "image_url": "",
        "stock_quantity": "9999",
        "fulfillment_type": "digital",
        "digital_asset_url": "https://example.com/files/style-guide.pdf",
        "requires_shipping": "FALSE",
    },
]


@router.get("/import/csv-template")
async def download_csv_template(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Downloads a starter CSV with the exact headers /import/csv expects,
    pre-filled with two example rows (one physical, one digital) so a
    business can see the expected format at a glance rather than guessing
    column names from documentation."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in CSV_TEMPLATE_SAMPLE_ROWS:
        writer.writerow(row)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=commb_product_import_template.csv"},
    )


def _parse_csv_bool(raw: str, default: Optional[bool]) -> Optional[bool]:
    val = (raw or "").strip().lower()
    if val in ("true", "1", "yes", "y"):
        return True
    if val in ("false", "0", "no", "n"):
        return False
    return default  # blank/unrecognized — keep the field's own schema default


def _csv_row_to_request(row: dict) -> CatalogItemCreateRequest:
    """Converts one CSV row (raw strings from csv.DictReader) into the same
    request shape create_catalog_item validates against, so a CSV import
    gets the exact same field validation and defaults as the single-product
    form — no separate, drifting validation logic for this path."""
    title = (row.get("title") or "").strip()
    if not title:
        raise ValueError("Missing required 'title'")

    price_raw = (row.get("price") or "").strip()
    try:
        price = float(price_raw) if price_raw else 0.0
    except ValueError:
        raise ValueError(f"'price' must be a number, got {price_raw!r}")

    stock_raw = (row.get("stock_quantity") or "").strip()
    try:
        stock_quantity = int(float(stock_raw)) if stock_raw else 100
    except ValueError:
        raise ValueError(f"'stock_quantity' must be a whole number, got {stock_raw!r}")

    fulfillment_type = (row.get("fulfillment_type") or "physical").strip().lower() or "physical"
    if fulfillment_type not in ("physical", "digital", "service"):
        raise ValueError(f"'fulfillment_type' must be physical, digital, or service — got {fulfillment_type!r}")

    requires_shipping = _parse_csv_bool(row.get("requires_shipping", ""), default=None)

    return CatalogItemCreateRequest(
        title=title,
        description=(row.get("description") or "").strip() or None,
        price=price,
        category=(row.get("category") or "").strip() or None,
        subcategory=(row.get("subcategory") or "").strip() or None,
        image_url=(row.get("image_url") or "").strip() or None,
        in_stock=True,  # always true for a CSV import — see CSV_COLUMNS's comment
        stock_quantity=stock_quantity,
        fulfillment_type=fulfillment_type,
        digital_asset_url=(row.get("digital_asset_url") or "").strip() or None,
        requires_shipping=requires_shipping,
    )


@router.post("/import/csv")
async def import_catalog_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin_role),
):
    """Bulk-creates catalog products from an uploaded CSV (see CSV_COLUMNS /
    the downloadable template above for the expected headers). Every row is
    a NEW product — unlike the Bumpa/Paystack import above, there is no
    stable external id to match against for an "update existing" path, so
    re-uploading the same CSV twice creates duplicates rather than silently
    overwriting anything. Partial success is allowed: valid rows are
    created, invalid rows are collected into per-row errors and reported
    back rather than failing the whole batch on one bad line."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a .csv file.")

    raw_bytes = await file.read()
    if len(raw_bytes) > 5 * 1024 * 1024:  # 5MB — generous for a product spreadsheet, not for arbitrary uploads
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file exceeds 5MB limit.")

    try:
        text = raw_bytes.decode("utf-8-sig")  # -sig strips a leading BOM (common from Excel-saved CSVs)
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read file as UTF-8 text. Please save the CSV with UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "title" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV is missing a 'title' column. Download the template to see the expected format.")

    # DictReader keys off the file's actual header casing/spacing; normalize
    # once so a business's own slightly-different header capitalization
    # ("Title", "Price ") still matches.
    normalized_rows = [{(k or "").strip().lower(): v for k, v in row.items()} for row in reader]

    created = 0
    errors: List[dict] = []
    for idx, row in enumerate(normalized_rows, start=2):  # start=2: row 1 is the header line
        try:
            req = _csv_row_to_request(row)
        except (ValueError, ValidationError) as e:
            errors.append({"row": idx, "title": row.get("title", ""), "error": str(e)})
            continue
        try:
            await _build_catalog_item_from_request(db, req)
            created += 1
        except Exception as e:
            errors.append({"row": idx, "title": req.title, "error": str(e)})

    await db.commit()

    return {
        "status": "ok",
        "created": created,
        "failed": len(errors),
        "errors": errors[:50],  # cap the echoed error list — a business with a badly-malformed 5000-row file doesn't need all 5000 back
    }
