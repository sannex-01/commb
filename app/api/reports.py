"""
Commerce & AI Analytics Reporting API
Provides aggregated analytics on GMV, order conversion, AI resolution efficiency, and channel distribution.
"""

import io
import csv
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.models.user import AdminUser
from app.models.order import Order
from app.models.session import ConversationSession
from app.models.catalog import CatalogItem
from app.models.agent import Agent


router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


class ChannelMetric(BaseModel):
    channel: str
    conversations_count: int
    orders_count: int
    revenue: float
    percentage: float


class ProductPerformance(BaseModel):
    id: int
    name: str
    price: float
    currency: str
    orders_count: int
    total_sales: float


class ReportsSummaryResponse(BaseModel):
    timeframe: str
    total_revenue: float
    total_orders: int
    paid_orders: int
    pending_orders: int
    conversion_rate: float
    average_order_value: float
    total_conversations: int
    ai_resolved_conversations: int
    human_escalated_conversations: int
    ai_resolution_rate: float
    channels: List[ChannelMetric]
    top_products: List[ProductPerformance]
    currency: str


@router.get("/summary", response_model=ReportsSummaryResponse)
async def get_reports_summary(
    days: int = Query(7, description="Number of days to analyze (0 for all time)", ge=0, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
):

    """Aggregate commerce and AI performance metrics over the requested timeframe."""
    now = datetime.now(timezone.utc)
    since_date = (now - timedelta(days=days)) if days > 0 else None

    # 1. Fetch Orders
    order_stmt = select(Order)
    if since_date:
        order_stmt = order_stmt.where(Order.created_at >= since_date)
    orders_result = await db.scalars(order_stmt)
    orders = orders_result.all()

    total_orders = len(orders)
    paid_orders = [o for o in orders if o.status == "paid"]
    pending_orders = [o for o in orders if o.status in ["pending", "created"]]
    
    total_revenue = sum(o.total_amount for o in paid_orders if o.total_amount)
    paid_count = len(paid_orders)
    conversion_rate = round((paid_count / total_orders * 100), 1) if total_orders > 0 else 0.0
    average_order_value = round((total_revenue / paid_count), 2) if paid_count > 0 else 0.0

    primary_currency = paid_orders[0].currency if paid_orders and paid_orders[0].currency else "NGN"

    # 2. Fetch Conversations
    conv_stmt = select(ConversationSession)
    if since_date:
        conv_stmt = conv_stmt.where(ConversationSession.created_at >= since_date)
    conv_result = await db.scalars(conv_stmt)
    conversations = conv_result.all()

    total_conversations = len(conversations)
    # Human escalation occurs if assigned to human or state has escalation flag
    escalated_convs = [c for c in conversations if getattr(c, "assigned_human_id", None) or "escalat" in str(getattr(c, "current_intent", "")).lower()]
    escalated_count = len(escalated_convs)
    ai_resolved_count = max(0, total_conversations - escalated_count)
    ai_resolution_rate = round((ai_resolved_count / total_conversations * 100), 1) if total_conversations > 0 else 100.0

    # 3. Channel breakdown
    # Deliberately a fixed allowlist of the three real customer channels,
    # not a dynamic bucket-per-distinct-value. A dynamic bucket meant any
    # stray channel string ever written to a row (a manual test insert, an
    # internal debug session, a future typo) would permanently show up as
    # its own "channel" on this dashboard for as long as that row existed
    # in the DB — real production-analytics UI, not somewhere test/internal
    # data should ever be able to leak into. Anything outside the three
    # known channels folds into "widget" (the same fallback already used
    # for a null/missing channel) rather than being dropped silently.
    KNOWN_CHANNELS = {"whatsapp", "telegram", "widget"}
    channels_map = {"whatsapp": 0, "telegram": 0, "widget": 0}
    channel_revenue = {"whatsapp": 0.0, "telegram": 0.0, "widget": 0.0}
    channel_orders = {"whatsapp": 0, "telegram": 0, "widget": 0}

    for c in conversations:
        ch = (c.channel or "widget").lower()
        if ch not in KNOWN_CHANNELS:
            ch = "widget"
        channels_map[ch] += 1

    for o in orders:
        ch = (o.channel or "widget").lower()
        if ch not in KNOWN_CHANNELS:
            ch = "widget"
        channel_orders[ch] += 1
        if o.status == "paid":
            channel_revenue[ch] += (o.total_amount or 0.0)

    total_channel_activity = sum(channels_map.values()) or 1
    channels_list: List[ChannelMetric] = []
    for ch_name, conv_cnt in channels_map.items():
        channels_list.append(
            ChannelMetric(
                channel=ch_name.capitalize(),
                conversations_count=conv_cnt,
                orders_count=channel_orders.get(ch_name, 0),
                revenue=round(channel_revenue.get(ch_name, 0.0), 2),
                percentage=round((conv_cnt / total_channel_activity) * 100, 1),
            )
        )

    # 4. Top Products
    products_stmt = select(CatalogItem).where(CatalogItem.in_stock == True).limit(5)
    products_res = await db.scalars(products_stmt)
    products = products_res.all()

    top_products: List[ProductPerformance] = []
    for p in products:
        # Count real purchases of this exact product by its own id, not a
        # title substring match (which could also false-match an unrelated
        # product whose title happens to contain this one's title as a
        # substring). Sums actual quantity across matching cart lines
        # rather than counting 1 per order, so a customer buying 3 units
        # in one order reflects as 3, not 1.
        units_sold = 0
        matched_order_count = 0
        for o in paid_orders:
            try:
                items = json.loads(o.items_json or "[]")
            except Exception:
                continue
            line_qty = sum(
                int(item.get("quantity", 1))
                for item in items
                if item.get("item_id") == p.id or item.get("product_id") == p.id
            )
            if line_qty > 0:
                units_sold += line_qty
                matched_order_count += 1

        # A product genuinely never purchased shows 0, not a fabricated 1 —
        # `len(...) or 1` here previously meant EVERY product displayed at
        # least one fake sale regardless of real order history.
        top_products.append(
            ProductPerformance(
                id=p.id,
                name=p.title or f"Product #{p.id}",
                price=p.price or 0.0,
                currency=p.currency or "NGN",
                orders_count=matched_order_count,
                total_sales=round((p.price or 0.0) * units_sold, 2),
            )
        )

    top_products.sort(key=lambda x: x.total_sales, reverse=True)

    return ReportsSummaryResponse(
        timeframe=f"{days}d" if days > 0 else "all",
        total_revenue=round(total_revenue, 2),
        total_orders=total_orders,
        paid_orders=paid_count,
        pending_orders=len(pending_orders),
        conversion_rate=conversion_rate,
        average_order_value=average_order_value,
        total_conversations=total_conversations,
        ai_resolved_conversations=ai_resolved_count,
        human_escalated_conversations=escalated_count,
        ai_resolution_rate=ai_resolution_rate,
        channels=channels_list,
        top_products=top_products,
        currency=primary_currency,
    )


# ==========================================
# WhatsApp & LLM Cost Tracking Data Models
# ==========================================

class WhatsAppCategoryCost(BaseModel):
    category: str
    label: str
    count: int
    unit_rate_usd: float
    unit_rate_ngn: float
    cost_usd: float
    cost_ngn: float
    description: str


class WhatsAppDailyTrend(BaseModel):
    date: str
    services: int
    utilities: int
    marketing: int
    total_count: int
    cost_usd: float
    cost_ngn: float


class WhatsAppCostSummary(BaseModel):
    total_conversations: int
    total_cost_usd: float
    total_cost_ngn: float
    services: WhatsAppCategoryCost
    utilities: WhatsAppCategoryCost
    marketing: WhatsAppCategoryCost
    pricing_policy_note: str
    daily_trends: List[WhatsAppDailyTrend]


class LLMModelUsage(BaseModel):
    model_name: str
    provider: str
    requests_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    cost_ngn: float


class LLMDailyTrend(BaseModel):
    date: str
    total_tokens: int
    cost_usd: float
    cost_ngn: float


class LLMCostSummary(BaseModel):
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    total_cost_ngn: float
    models: List[LLMModelUsage]
    daily_trends: List[LLMDailyTrend]


class CostTrackingResponse(BaseModel):
    timeframe: str
    exchange_rate_usd_to_ngn: float
    whatsapp: WhatsAppCostSummary
    llm: LLMCostSummary


# Standard WhatsApp Cloud API Pricing Rates (Effective October 1st Pricing Model)
# Nigeria / Emerging Market Rates (in USD)
WA_RATES_USD = {
    "service": 0.0100,      # ~$0.0100 per 24-hr user-initiated service conversation
    "utility": 0.0160,      # ~$0.0160 per transactional/order/shipping update
    "marketing": 0.0516,    # ~$0.0516 per marketing/broadcast conversation
    "authentication": 0.0160,
}

# LLM Token Pricing per 1,000,000 Tokens (in USD)
LLM_PRICING_PER_MILLION = {
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "provider": "Google DeepMind"},
    "gemini-2.0-flash": {"input": 0.100, "output": 0.40, "provider": "Google DeepMind"},
    "gemini-1.5-pro": {"input": 1.250, "output": 5.00, "provider": "Google DeepMind"},
    "gpt-4o-mini": {"input": 0.150, "output": 0.60, "provider": "OpenAI"},
    "gpt-4o": {"input": 2.500, "output": 10.00, "provider": "OpenAI"},
    "claude-3-5-sonnet": {"input": 3.000, "output": 15.00, "provider": "Anthropic"},
    "claude-3-5-haiku": {"input": 0.800, "output": 4.00, "provider": "Anthropic"},
    "default": {"input": 0.150, "output": 0.60, "provider": "AI Provider"},
}

EXCHANGE_RATE_NGN = 1600.0


@router.get("/costs", response_model=CostTrackingResponse)
async def get_cost_tracking(
    days: int = Query(7, description="Number of days to analyze (0 for all time)", ge=0, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
):
    """
    Detailed cost and usage tracking for WhatsApp Cloud API (reflecting Meta's October 1st conversation pricing)
    and LLM Token Consumption across providers in NGN and USD.
    """
    now = datetime.now(timezone.utc)
    num_days = days if days > 0 else 30
    since_date = (now - timedelta(days=num_days)) if days > 0 else None

    # 1. Fetch Conversations & Messages
    conv_stmt = select(ConversationSession)
    if since_date:
        conv_stmt = conv_stmt.where(ConversationSession.created_at >= since_date)
    conv_res = await db.scalars(conv_stmt)
    conversations = conv_res.all()

    # Fetch Agents to map default LLM models
    agent_stmt = select(Agent)
    agent_res = await db.scalars(agent_stmt)
    agents_map = {a.id: a for a in agent_res.all()}

    # Initialize daily buckets for chart
    daily_data: Dict[str, Dict[str, Any]] = {}
    for i in range(num_days - 1, -1, -1):
        d_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_data[d_str] = {
            "services": 0,
            "utilities": 0,
            "marketing": 0,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "llm_cost_usd": 0.0,
        }

    # WhatsApp Counters
    services_count = 0
    utilities_count = 0
    marketing_count = 0

    # LLM Counters
    model_aggregates: Dict[str, Dict[str, Any]] = {}

    for c in conversations:
        c_date = c.created_at.strftime("%Y-%m-%d") if c.created_at else now.strftime("%Y-%m-%d")
        if c_date not in daily_data:
            daily_data[c_date] = {
                "services": 0,
                "utilities": 0,
                "marketing": 0,
                "llm_prompt_tokens": 0,
                "llm_completion_tokens": 0,
                "llm_cost_usd": 0.0,
            }

        # Classify WhatsApp Category
        is_whatsapp = (c.channel or "").lower() == "whatsapp"
        if is_whatsapp:
            flow_name = str(getattr(c, "active_flow", "") or "").lower()
            state_text = str(getattr(c, "state_data", "") or "").lower()
            
            if any(k in flow_name or k in state_text for k in ["marketing", "campaign", "promo", "broadcast", "announcement"]):
                marketing_count += 1
                daily_data[c_date]["marketing"] += 1
            elif any(k in flow_name or k in state_text for k in ["order", "checkout", "receipt", "tracking", "utility", "payment"]):
                utilities_count += 1
                daily_data[c_date]["utilities"] += 1
            else:
                # Default user-initiated inquiry within 24hr customer service window
                services_count += 1
                daily_data[c_date]["services"] += 1

        # Calculate LLM tokens for session
        agent = agents_map.get(c.agent_id) if c.agent_id else None
        model_name = (agent.llm_model if agent and agent.llm_model else "gemini-1.5-flash").lower()
        if model_name not in model_aggregates:
            cfg = LLM_PRICING_PER_MILLION.get(model_name, LLM_PRICING_PER_MILLION["default"])
            model_aggregates[model_name] = {
                "model_name": model_name,
                "provider": cfg["provider"],
                "requests_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": 0.0,
                "cost_ngn": 0.0,
            }

        # Estimate tokens from conversation memory & activity
        memory_str = c.memory_json or "[]"
        char_count = len(memory_str)
        # Average heuristic: ~4 characters per token
        session_tokens = max(120, int(char_count / 4))
        p_tokens = int(session_tokens * 0.70)
        c_tokens = int(session_tokens * 0.30)

        cfg = LLM_PRICING_PER_MILLION.get(model_name, LLM_PRICING_PER_MILLION["default"])
        cost_usd = (p_tokens / 1_000_000 * cfg["input"]) + (c_tokens / 1_000_000 * cfg["output"])

        model_aggregates[model_name]["requests_count"] += 1
        model_aggregates[model_name]["prompt_tokens"] += p_tokens
        model_aggregates[model_name]["completion_tokens"] += c_tokens
        model_aggregates[model_name]["cost_usd"] += cost_usd

        daily_data[c_date]["llm_prompt_tokens"] += p_tokens
        daily_data[c_date]["llm_completion_tokens"] += c_tokens
        daily_data[c_date]["llm_cost_usd"] += cost_usd

    # If no WhatsApp sessions yet, provide clean baseline
    total_wa_convs = services_count + utilities_count + marketing_count
    
    # Calculate WhatsApp Costs
    service_cost_usd = services_count * WA_RATES_USD["service"]
    utility_cost_usd = utilities_count * WA_RATES_USD["utility"]
    marketing_cost_usd = marketing_count * WA_RATES_USD["marketing"]
    total_wa_cost_usd = service_cost_usd + utility_cost_usd + marketing_cost_usd

    wa_daily_trends: List[WhatsAppDailyTrend] = []
    llm_daily_trends: List[LLMDailyTrend] = []

    for d_str in sorted(daily_data.keys()):
        d_val = daily_data[d_str]
        d_wa_cost_usd = (
            d_val["services"] * WA_RATES_USD["service"]
            + d_val["utilities"] * WA_RATES_USD["utility"]
            + d_val["marketing"] * WA_RATES_USD["marketing"]
        )
        d_wa_count = d_val["services"] + d_val["utilities"] + d_val["marketing"]

        wa_daily_trends.append(
            WhatsAppDailyTrend(
                date=d_str,
                services=d_val["services"],
                utilities=d_val["utilities"],
                marketing=d_val["marketing"],
                total_count=d_wa_count,
                cost_usd=round(d_wa_cost_usd, 4),
                cost_ngn=round(d_wa_cost_usd * EXCHANGE_RATE_NGN, 2),
            )
        )

        d_llm_tokens = d_val["llm_prompt_tokens"] + d_val["llm_completion_tokens"]
        llm_daily_trends.append(
            LLMDailyTrend(
                date=d_str,
                total_tokens=d_llm_tokens,
                cost_usd=round(d_val["llm_cost_usd"], 5),
                cost_ngn=round(d_val["llm_cost_usd"] * EXCHANGE_RATE_NGN, 2),
            )
        )

    # Format Model Usage List
    models_list: List[LLMModelUsage] = []
    tot_p_tokens = 0
    tot_c_tokens = 0
    tot_reqs = 0
    tot_llm_cost_usd = 0.0

    for m_k, m_val in model_aggregates.items():
        m_tot_tokens = m_val["prompt_tokens"] + m_val["completion_tokens"]
        m_cost_usd = m_val["cost_usd"]
        m_cost_ngn = m_cost_usd * EXCHANGE_RATE_NGN

        tot_p_tokens += m_val["prompt_tokens"]
        tot_c_tokens += m_val["completion_tokens"]
        tot_reqs += m_val["requests_count"]
        tot_llm_cost_usd += m_cost_usd

        models_list.append(
            LLMModelUsage(
                model_name=m_val["model_name"],
                provider=m_val["provider"],
                requests_count=m_val["requests_count"],
                prompt_tokens=m_val["prompt_tokens"],
                completion_tokens=m_val["completion_tokens"],
                total_tokens=m_tot_tokens,
                cost_usd=round(m_cost_usd, 4),
                cost_ngn=round(m_cost_ngn, 2),
            )
        )

    models_list.sort(key=lambda x: x.total_tokens, reverse=True)

    whatsapp_summary = WhatsAppCostSummary(
        total_conversations=total_wa_convs,
        total_cost_usd=round(total_wa_cost_usd, 4),
        total_cost_ngn=round(total_wa_cost_usd * EXCHANGE_RATE_NGN, 2),
        services=WhatsAppCategoryCost(
            category="service",
            label="Service Conversations",
            count=services_count,
            unit_rate_usd=WA_RATES_USD["service"],
            unit_rate_ngn=round(WA_RATES_USD["service"] * EXCHANGE_RATE_NGN, 2),
            cost_usd=round(service_cost_usd, 4),
            cost_ngn=round(service_cost_usd * EXCHANGE_RATE_NGN, 2),
            description="User-initiated support & product inquiries within the 24-hr customer service window (Meta Oct 1st rate).",
        ),
        utilities=WhatsAppCategoryCost(
            category="utility",
            label="Utility Conversations",
            count=utilities_count,
            unit_rate_usd=WA_RATES_USD["utility"],
            unit_rate_ngn=round(WA_RATES_USD["utility"] * EXCHANGE_RATE_NGN, 2),
            cost_usd=round(utility_cost_usd, 4),
            cost_ngn=round(utility_cost_usd * EXCHANGE_RATE_NGN, 2),
            description="Transactional messages, automated order confirmations, receipts, and payment link updates.",
        ),
        marketing=WhatsAppCategoryCost(
            category="marketing",
            label="Marketing Conversations",
            count=marketing_count,
            unit_rate_usd=WA_RATES_USD["marketing"],
            unit_rate_ngn=round(WA_RATES_USD["marketing"] * EXCHANGE_RATE_NGN, 2),
            cost_usd=round(marketing_cost_usd, 4),
            cost_ngn=round(marketing_cost_usd * EXCHANGE_RATE_NGN, 2),
            description="Outbound promotional broadcasts, product drops, catalog announcements, and re-engagement campaigns.",
        ),
        pricing_policy_note="Calculated using Meta's official WhatsApp Business Cloud API pricing structure, including the October 1st updated service charging model.",
        daily_trends=wa_daily_trends,
    )

    llm_summary = LLMCostSummary(
        total_requests=tot_reqs,
        total_prompt_tokens=tot_p_tokens,
        total_completion_tokens=tot_c_tokens,
        total_tokens=tot_p_tokens + tot_c_tokens,
        total_cost_usd=round(tot_llm_cost_usd, 4),
        total_cost_ngn=round(tot_llm_cost_usd * EXCHANGE_RATE_NGN, 2),
        models=models_list,
        daily_trends=llm_daily_trends,
    )

    return CostTrackingResponse(
        timeframe=f"{days}d" if days > 0 else "all",
        exchange_rate_usd_to_ngn=EXCHANGE_RATE_NGN,
        whatsapp=whatsapp_summary,
        llm=llm_summary,
    )


@router.get("/export-csv")
async def export_reports_csv(
    days: int = Query(30, description="Timeframe in days", ge=0, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
):

    """Export orders and sales analytics report as CSV."""
    now = datetime.now(timezone.utc)
    since_date = (now - timedelta(days=days)) if days > 0 else None

    stmt = select(Order).order_by(desc(Order.id))
    if since_date:
        stmt = stmt.where(Order.created_at >= since_date)
    res = await db.scalars(stmt)
    orders = res.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Order ID", "Reference", "Customer Name", "Customer Phone", 
        "Amount", "Currency", "Status", "Channel", "Payment Provider", "Created At"
    ])

    for o in orders:
        writer.writerow([
            o.id,
            getattr(o, "reference", "") or getattr(o, "id", ""),
            getattr(o, "customer_name", "Anonymous"),
            getattr(o, "customer_phone", "") or getattr(o, "customer_id", ""),
            o.total_amount or 0.0,
            o.currency or "NGN",
            o.status,
            o.channel or "Widget",
            getattr(o, "payment_provider", "paystack"),
            o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "",
        ])

    output.seek(0)
    filename = f"commb_commerce_report_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

