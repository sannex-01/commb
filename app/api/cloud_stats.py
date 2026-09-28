"""Aggregate sales numbers for the CommB Cloud dashboard.

CommB Cloud calls this with the instance's COMMB_API_KEY (the same key that
signs SSO) so a partner or merchant can see how each store is doing without
opening it. It returns counts and sums only: no customer names, contacts,
addresses or messages, so unlike cloud sync (app/cloud_sync) it exports no
personal data and needs no opt-in.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_dashboard_auth
from app.models.business import BusinessProfile
from app.models.customer import Customer
from app.models.order import Order
from app.models.session import ConversationSession

router = APIRouter(prefix="/cloud", tags=["CommB Cloud"])

# Same definition of "money in" as the admin overview.
PAID_STATUSES = ("paid", "processing", "completed")


def _as_utc(dt: datetime) -> datetime:
    # SQLite hands back naive datetimes; Postgres returns aware ones.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/stats")
async def cloud_stats(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_dashboard_auth),
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=days - 1)).date()
    since = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)

    biz = (await db.execute(select(BusinessProfile).limit(1))).scalar_one_or_none()

    total_orders = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    paid_orders = (
        await db.execute(select(func.count(Order.id)).where(Order.status.in_(PAID_STATUSES)))
    ).scalar() or 0
    total_revenue = float(
        (await db.execute(select(func.sum(Order.total_amount)).where(Order.status.in_(PAID_STATUSES)))).scalar()
        or 0.0
    )
    total_customers = (await db.execute(select(func.count(Customer.id)))).scalar() or 0
    conversations = (
        await db.execute(
            select(func.count(ConversationSession.id)).where(ConversationSession.last_active_at >= since)
        )
    ).scalar() or 0

    # Bucketed in Python rather than with date_trunc so it runs the same on
    # SQLite and Postgres; the window is at most 90 days of orders.
    rows = (
        await db.execute(
            select(Order.created_at, Order.total_amount, Order.status, Order.channel).where(Order.created_at >= since)
        )
    ).all()

    series = {
        (start_day + timedelta(days=i)).isoformat(): {"orders": 0, "revenue": 0.0} for i in range(days)
    }
    channels: Dict[str, int] = {}
    for created_at, amount, status, channel in rows:
        if created_at is None:
            continue
        key = _as_utc(created_at).date().isoformat()
        if key not in series:
            continue
        series[key]["orders"] += 1
        if status in PAID_STATUSES:
            series[key]["revenue"] += float(amount or 0)
        channels[channel or "other"] = channels.get(channel or "other", 0) + 1

    return {
        "currency": biz.currency if biz else "NGN",
        "days": days,
        "totals": {
            "orders": total_orders,
            "paid_orders": paid_orders,
            "revenue": total_revenue,
            "customers": total_customers,
        },
        "period": {
            "orders": sum(d["orders"] for d in series.values()),
            "revenue": sum(d["revenue"] for d in series.values()),
            "conversations": conversations,
            "channels": channels,
        },
        "daily": [{"date": k, **v} for k, v in series.items()],
    }
