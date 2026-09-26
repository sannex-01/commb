import { state } from '../state.js';
import { api } from '../api.js';
import { showToast, formatCurrency, formatDate, skeletonPage, escapeHtml } from '../utils.js';

let currentDays = 7;
let activeTab = 'whatsapp'; // 'whatsapp' | 'llm' | 'commerce'
let selectedCurrency = 'NGN'; // 'NGN' | 'USD'

export async function loadReportsPage(container) {
  container.innerHTML = skeletonPage({ stats: 4, rows: 6 });

  try {
    const [summaryData, costData] = await Promise.all([
      api(`/reports/summary?days=${currentDays}`).catch(() => null),
      api(`/reports/costs?days=${currentDays}`).catch(() => null),
    ]);

    renderReportsView(container, summaryData, costData);
  } catch (err) {
    console.error("Reports loading error:", err);
    container.innerHTML = `
      <div class="card p-10 text-center space-y-4 max-w-lg mx-auto my-8">
        <div class="w-14 h-14 rounded-2xl bg-rose-500/10 text-rose-500 border border-rose-500/20 flex items-center justify-center mx-auto text-2xl">⚠️</div>
        <h2 class="text-lg font-bold text-main">Failed to load reports</h2>
        <p class="text-xs text-muted max-w-md mx-auto">${escapeHtml(err.message || "An error occurred while aggregating analytics.")}</p>
        <button onclick="window.location.reload()" class="btn btn-primary btn-sm mx-auto">Retry</button>
      </div>
    `;
  }
}

function formatCostValue(valNgn, valUsd, curr) {
  if (curr === 'USD') {
    if (valUsd < 0.01 && valUsd > 0) return `$${valUsd.toFixed(4)}`;
    return `$${Number(valUsd || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `₦${Number(Math.round(valNgn || 0)).toLocaleString()}`;
}

function formatUnitRate(rateNgn, rateUsd, curr) {
  if (curr === 'USD') return `$${Number(rateUsd || 0).toFixed(4)}`;
  return `₦${Number(rateNgn || 0).toFixed(2)}`;
}

function renderReportsView(container, summaryData, costData) {
  const commCurrency = summaryData?.currency || state.business?.currency || "NGN";
  const wa = costData?.whatsapp || {
    total_conversations: 0,
    total_cost_usd: 0,
    total_cost_ngn: 0,
    services: { count: 0, unit_rate_usd: 0.01, unit_rate_ngn: 16, cost_usd: 0, cost_ngn: 0 },
    utilities: { count: 0, unit_rate_usd: 0.016, unit_rate_ngn: 25.6, cost_usd: 0, cost_ngn: 0 },
    marketing: { count: 0, unit_rate_usd: 0.0516, unit_rate_ngn: 82.56, cost_usd: 0, cost_ngn: 0 },
    daily_trends: []
  };

  const llm = costData?.llm || {
    total_requests: 0,
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    total_tokens: 0,
    total_cost_usd: 0,
    total_cost_ngn: 0,
    models: [],
    daily_trends: []
  };

  container.innerHTML = `
    <div class="space-y-6 animate-fade-in">
      
      <!-- Top Header & Action Controls -->
      <div class="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-subtle">
        <div>
          <h1 class="text-2xl font-bold text-main tracking-tight flex items-center gap-2.5">
            <span>📊</span> Usage & Cost Analytics
          </h1>
          <p class="text-xs text-muted mt-0.5">
            Real-time tracking for WhatsApp Cloud API conversations, LLM token consumption, and commerce performance.
          </p>
        </div>

        <div class="flex items-center gap-3 w-full lg:w-auto flex-wrap">
          <!-- Currency Switcher -->
          <div class="inline-flex p-1 rounded-xl bg-surface-elevated border border-subtle text-xs font-semibold">
            <button class="currency-toggle-btn px-3 py-1.5 rounded-lg transition-all ${selectedCurrency === 'NGN' ? 'bg-emerald-600 text-white font-bold shadow-xs' : 'text-muted hover:text-main'}" data-currency="NGN">
              ₦ NGN
            </button>
            <button class="currency-toggle-btn px-3 py-1.5 rounded-lg transition-all ${selectedCurrency === 'USD' ? 'bg-emerald-600 text-white font-bold shadow-xs' : 'text-muted hover:text-main'}" data-currency="USD">
              $ USD
            </button>
          </div>

          <!-- Timeframe Selector -->
          <div class="inline-flex p-1 rounded-xl bg-surface-elevated border border-subtle text-xs font-medium">
            <button class="timeframe-btn px-3 py-1.5 rounded-lg transition-all ${currentDays === 7 ? 'bg-surface text-main font-bold shadow-xs border border-subtle' : 'text-muted hover:text-main'}" data-days="7">7 Days</button>
            <button class="timeframe-btn px-3 py-1.5 rounded-lg transition-all ${currentDays === 30 ? 'bg-surface text-main font-bold shadow-xs border border-subtle' : 'text-muted hover:text-main'}" data-days="30">30 Days</button>
            <button class="timeframe-btn px-3 py-1.5 rounded-lg transition-all ${currentDays === 90 ? 'bg-surface text-main font-bold shadow-xs border border-subtle' : 'text-muted hover:text-main'}" data-days="90">90 Days</button>
            <button class="timeframe-btn px-3 py-1.5 rounded-lg transition-all ${currentDays === 0 ? 'bg-surface text-main font-bold shadow-xs border border-subtle' : 'text-muted hover:text-main'}" data-days="0">All Time</button>
          </div>

          <!-- Export CSV -->
          <button id="export-csv-btn" class="btn btn-secondary btn-sm flex items-center gap-2 shrink-0">
            <svg class="w-4 h-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      <!-- Main Navigation Tabs -->
      <div class="flex items-center gap-2 border-b border-subtle pb-px overflow-x-auto">
        <button class="tab-btn pb-3 px-4 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${activeTab === 'whatsapp' ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400' : 'border-transparent text-muted hover:text-main'}" data-tab="whatsapp">
          <span class="text-base">💬</span>
          <span>WhatsApp Usage & Costs</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-mono font-semibold">Oct 1 Pricing</span>
        </button>

        <button class="tab-btn pb-3 px-4 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${activeTab === 'llm' ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400' : 'border-transparent text-muted hover:text-main'}" data-tab="llm">
          <span class="text-base">🤖</span>
          <span>LLM Token Usage</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 font-mono font-semibold">BYOK Models</span>
        </button>

        <button class="tab-btn pb-3 px-4 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${activeTab === 'commerce' ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400' : 'border-transparent text-muted hover:text-main'}" data-tab="commerce">
          <span class="text-base">📈</span>
          <span>Sales & AI Conversion</span>
        </button>
      </div>

      <!-- TAB 1: WHATSAPP USAGE & COSTS -->
      <div id="tab-content-whatsapp" class="space-y-6 ${activeTab === 'whatsapp' ? 'block' : 'hidden'}">
        
        <!-- Pricing Policy Notification Banner -->
        <div class="p-4 rounded-2xl bg-emerald-500/5 border border-emerald-500/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
          <div class="flex items-center gap-3">
            <span class="p-2 rounded-xl bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-base">📌</span>
            <div>
              <div class="font-bold text-main">Meta WhatsApp Cloud API Conversation Pricing (Effective Oct 1st)</div>
              <div class="text-muted text-[11px] mt-0.5">
                Charges are billed per 24-hour conversation window categorized into <strong>Services</strong>, <strong>Utilities</strong>, and <strong>Marketing</strong>.
              </div>
            </div>
          </div>
          <div class="font-mono text-muted text-[11px] shrink-0">
            Exchange Rate: 1 USD = ₦1,600
          </div>
        </div>

        <!-- 4 Top Cards for WhatsApp Usage -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          
          <!-- Services Card -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong border-emerald-500/30">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Services (Support/Inquiries)</span>
              <span class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">💬</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
              ${formatCostValue(wa.services?.cost_ngn, wa.services?.cost_usd, selectedCurrency)}
            </div>
            <div class="text-[12px] text-muted flex items-center justify-between font-mono">
              <span class="font-semibold text-emerald-600 dark:text-emerald-400">${wa.services?.count || 0} convs</span>
              <span>Rate: ${formatUnitRate(wa.services?.unit_rate_ngn, wa.services?.unit_rate_usd, selectedCurrency)}/conv</span>
            </div>
          </div>

          <!-- Utilities Card -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong border-sky-500/30">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Utilities (Orders/Receipts)</span>
              <span class="p-1.5 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400">📦</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
              ${formatCostValue(wa.utilities?.cost_ngn, wa.utilities?.cost_usd, selectedCurrency)}
            </div>
            <div class="text-[12px] text-muted flex items-center justify-between font-mono">
              <span class="font-semibold text-sky-600 dark:text-sky-400">${wa.utilities?.count || 0} convs</span>
              <span>Rate: ${formatUnitRate(wa.utilities?.unit_rate_ngn, wa.utilities?.unit_rate_usd, selectedCurrency)}/conv</span>
            </div>
          </div>

          <!-- Marketing Card -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong border-amber-500/30">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Marketing (Broadcasts)</span>
              <span class="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">📢</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
              ${formatCostValue(wa.marketing?.cost_ngn, wa.marketing?.cost_usd, selectedCurrency)}
            </div>
            <div class="text-[12px] text-muted flex items-center justify-between font-mono">
              <span class="font-semibold text-amber-600 dark:text-amber-400">${wa.marketing?.count || 0} convs</span>
              <span>Rate: ${formatUnitRate(wa.marketing?.unit_rate_ngn, wa.marketing?.unit_rate_usd, selectedCurrency)}/conv</span>
            </div>
          </div>

          <!-- Total WhatsApp Spend -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong bg-gradient-to-br from-surface to-emerald-500/5">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Total WhatsApp Spend</span>
              <span class="p-1.5 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold font-mono">Total</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-emerald-600 dark:text-emerald-400 tracking-tight font-mono">
              ${formatCostValue(wa.total_cost_ngn, wa.total_cost_usd, selectedCurrency)}
            </div>
            <div class="text-[12px] text-muted font-mono">
              ${wa.total_conversations} total billable 24-hr sessions
            </div>
          </div>

        </div>

        <!-- WhatsApp Daily Usage & Cost Trend Chart -->
        <div class="card p-6 space-y-5">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-subtle">
            <div>
              <h3 class="text-sm font-bold text-main flex items-center gap-2">
                <span>📈</span> WhatsApp Daily Conversation Distribution & Estimated Spend
              </h3>
              <p class="text-xs text-muted mt-0.5">Day-by-day volume across Service, Utility, and Marketing categories.</p>
            </div>
            <div class="flex items-center gap-3 text-[11px] font-medium text-muted flex-wrap">
              <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-emerald-500"></span> Services</span>
              <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-sky-500"></span> Utilities</span>
              <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-amber-500"></span> Marketing</span>
            </div>
          </div>

          ${renderWhatsAppChart(wa.daily_trends, selectedCurrency)}
        </div>

        <!-- WhatsApp Category Breakdown Table -->
        <div class="card p-6 space-y-4">
          <div class="flex items-center justify-between pb-3 border-b border-subtle">
            <h3 class="text-sm font-bold text-main flex items-center gap-2">
              <span>📑</span> Category Breakdown & Meta Billing Rules
            </h3>
            <span class="text-xs text-muted font-mono">Oct 1st Rate Card</span>
          </div>

          <div class="overflow-x-auto border border-subtle rounded-xl">
            <table class="w-full text-left text-xs">
              <thead class="bg-surface-elevated text-muted font-semibold border-b border-subtle text-[11px]">
                <tr>
                  <th class="p-3.5">Category</th>
                  <th class="p-3.5">Trigger Criteria & Billing Window</th>
                  <th class="p-3.5">Unit Rate (USD)</th>
                  <th class="p-3.5">Unit Rate (NGN)</th>
                  <th class="p-3.5">Conversations</th>
                  <th class="p-3.5 text-right">Total Cost (${selectedCurrency})</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-subtle font-mono">
                
                <tr class="hover:bg-surface-hover transition-colors">
                  <td class="p-3.5 font-sans font-bold text-main flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                    <span>Services</span>
                  </td>
                  <td class="p-3.5 font-sans text-muted text-[11px]">
                    User-initiated support, catalog queries, and AI customer chats inside the 24h window.
                  </td>
                  <td class="p-3.5 text-main">$0.0100</td>
                  <td class="p-3.5 text-main">₦16.00</td>
                  <td class="p-3.5 font-bold text-emerald-600 dark:text-emerald-400">${wa.services?.count || 0}</td>
                  <td class="p-3.5 text-right font-bold text-main">${formatCostValue(wa.services?.cost_ngn, wa.services?.cost_usd, selectedCurrency)}</td>
                </tr>

                <tr class="hover:bg-surface-hover transition-colors">
                  <td class="p-3.5 font-sans font-bold text-main flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-sky-500"></span>
                    <span>Utilities</span>
                  </td>
                  <td class="p-3.5 font-sans text-muted text-[11px]">
                    Transactional messages: automated checkout receipts, order confirmations, and shipment updates.
                  </td>
                  <td class="p-3.5 text-main">$0.0160</td>
                  <td class="p-3.5 text-main">₦25.60</td>
                  <td class="p-3.5 font-bold text-sky-600 dark:text-sky-400">${wa.utilities?.count || 0}</td>
                  <td class="p-3.5 text-right font-bold text-main">${formatCostValue(wa.utilities?.cost_ngn, wa.utilities?.cost_usd, selectedCurrency)}</td>
                </tr>

                <tr class="hover:bg-surface-hover transition-colors">
                  <td class="p-3.5 font-sans font-bold text-main flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                    <span>Marketing</span>
                  </td>
                  <td class="p-3.5 font-sans text-muted text-[11px]">
                    Outbound promotional broadcasts, product drop announcements, and discounts.
                  </td>
                  <td class="p-3.5 text-main">$0.0516</td>
                  <td class="p-3.5 text-main">₦82.56</td>
                  <td class="p-3.5 font-bold text-amber-600 dark:text-amber-400">${wa.marketing?.count || 0}</td>
                  <td class="p-3.5 text-right font-bold text-main">${formatCostValue(wa.marketing?.cost_ngn, wa.marketing?.cost_usd, selectedCurrency)}</td>
                </tr>

              </tbody>
            </table>
          </div>
        </div>

      </div>

      <!-- TAB 2: LLM TOKEN USAGE & COSTS -->
      <div id="tab-content-llm" class="space-y-6 ${activeTab === 'llm' ? 'block' : 'hidden'}">
        
        <!-- 4 Top Cards for LLM Usage -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          
          <!-- Total Tokens -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong border-purple-500/30">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Total Tokens</span>
              <span class="p-1.5 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400">⚡</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
              ${(llm.total_tokens || 0).toLocaleString()}
            </div>
            <div class="text-[12px] text-muted font-mono">
              ${llm.total_requests || 0} LLM inference turns
            </div>
          </div>

          <!-- Prompt (Input) Tokens -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Prompt (Input) Tokens</span>
              <span class="p-1.5 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400">📥</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
              ${(llm.total_prompt_tokens || 0).toLocaleString()}
            </div>
            <div class="text-[12px] text-muted font-mono">
              Catalog RAG & System context
            </div>
          </div>

          <!-- Completion (Output) Tokens -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Completion (Output) Tokens</span>
              <span class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">📤</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
              ${(llm.total_completion_tokens || 0).toLocaleString()}
            </div>
            <div class="text-[12px] text-muted font-mono">
              AI Generated Chat & Cart responses
            </div>
          </div>

          <!-- Total LLM Cost -->
          <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong bg-gradient-to-br from-surface to-purple-500/5">
            <div class="flex items-center justify-between text-muted text-xs font-semibold">
              <span>Total LLM Cost</span>
              <span class="p-1.5 rounded-lg bg-purple-500/15 text-purple-600 dark:text-purple-400 font-bold font-mono">BYOK</span>
            </div>
            <div class="text-2xl sm:text-3xl font-black text-purple-600 dark:text-purple-400 tracking-tight font-mono">
              ${formatCostValue(llm.total_cost_ngn, llm.total_cost_usd, selectedCurrency)}
            </div>
            <div class="text-[12px] text-muted font-mono">
              Billed directly by your model provider
            </div>
          </div>

        </div>

        <!-- LLM Token Trend Chart -->
        <div class="card p-6 space-y-5">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-subtle">
            <div>
              <h3 class="text-sm font-bold text-main flex items-center gap-2">
                <span>📊</span> Daily Token Consumption & Estimated Cost
              </h3>
              <p class="text-xs text-muted mt-0.5">Token activity across all configured agent workflows.</p>
            </div>
            <div class="text-xs font-mono text-muted">
              Display Currency: <strong>${selectedCurrency}</strong>
            </div>
          </div>

          ${renderLLMChart(llm.daily_trends, selectedCurrency)}
        </div>

        <!-- LLM Models Breakdown Table -->
        <div class="card p-6 space-y-4">
          <div class="flex items-center justify-between pb-3 border-b border-subtle">
            <h3 class="text-sm font-bold text-main flex items-center gap-2">
              <span>🤖</span> Active Model Usage Breakdown
            </h3>
            <span class="text-xs text-muted">Multi-Agent Roster</span>
          </div>

          ${(llm.models && llm.models.length > 0) ? `
            <div class="overflow-x-auto border border-subtle rounded-xl">
              <table class="w-full text-left text-xs">
                <thead class="bg-surface-elevated text-muted font-semibold border-b border-subtle text-[11px]">
                  <tr>
                    <th class="p-3.5">Model Name</th>
                    <th class="p-3.5">Provider</th>
                    <th class="p-3.5">Requests</th>
                    <th class="p-3.5">Prompt Tokens</th>
                    <th class="p-3.5">Completion Tokens</th>
                    <th class="p-3.5">Total Tokens</th>
                    <th class="p-3.5 text-right">Estimated Cost (${selectedCurrency})</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-subtle font-mono">
                  ${llm.models.map(m => `
                    <tr class="hover:bg-surface-hover transition-colors">
                      <td class="p-3.5 font-sans font-bold text-main flex items-center gap-2">
                        <span class="w-2 h-2 rounded-full bg-purple-500"></span>
                        ${escapeHtml(m.model_name)}
                      </td>
                      <td class="p-3.5 text-muted">${escapeHtml(m.provider)}</td>
                      <td class="p-3.5 font-bold">${m.requests_count}</td>
                      <td class="p-3.5 text-sky-600 dark:text-sky-400">${m.prompt_tokens.toLocaleString()}</td>
                      <td class="p-3.5 text-emerald-600 dark:text-emerald-400">${m.completion_tokens.toLocaleString()}</td>
                      <td class="p-3.5 font-black text-main">${m.total_tokens.toLocaleString()}</td>
                      <td class="p-3.5 text-right font-black text-purple-600 dark:text-purple-400">${formatCostValue(m.cost_ngn, m.cost_usd, selectedCurrency)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : `
            <div class="py-8 text-center text-muted text-xs">
              No active LLM requests recorded in this timeframe.
            </div>
          `}
        </div>

      </div>

      <!-- TAB 3: COMMERCE & CONVERSION -->
      <div id="tab-content-commerce" class="space-y-6 ${activeTab === 'commerce' ? 'block' : 'hidden'}">
        ${summaryData ? renderCommerceSummaryContent(summaryData, commCurrency) : `
          <div class="card p-8 text-center text-muted text-xs">Loading commerce summary...</div>
        `}
      </div>

    </div>
  `;

  // Attach Event Listeners
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      activeTab = btn.getAttribute('data-tab');
      renderReportsView(container, summaryData, costData);
    });
  });

  container.querySelectorAll('.currency-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedCurrency = btn.getAttribute('data-currency');
      renderReportsView(container, summaryData, costData);
    });
  });

  container.querySelectorAll('.timeframe-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const days = Number(btn.getAttribute('data-days'));
      currentDays = days;
      loadReportsPage(container);
    });
  });

  const exportBtn = container.querySelector('#export-csv-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      window.location.href = `/api/v1/reports/export-csv?days=${currentDays}`;
    });
  }
}

function renderWhatsAppChart(dailyTrends, currency) {
  if (!dailyTrends || dailyTrends.length === 0) {
    return `<div class="py-12 text-center text-muted text-xs">No daily WhatsApp activity in this range.</div>`;
  }

  const maxCount = Math.max(...dailyTrends.map(d => d.total_count), 10);
  const chartHeight = 180;

  return `
    <div class="space-y-3">
      <div class="h-48 w-full flex items-end gap-2 pt-6 px-2 overflow-x-auto">
        ${dailyTrends.map(d => {
          const sHeight = Math.round((d.services / maxCount) * chartHeight);
          const uHeight = Math.round((d.utilities / maxCount) * chartHeight);
          const mHeight = Math.round((d.marketing / maxCount) * chartHeight);
          const totalCostDisplay = formatCostValue(d.cost_ngn, d.cost_usd, currency);

          return `
            <div class="flex-1 min-w-[36px] flex flex-col items-center gap-1.5 group relative">
              
              <!-- Hover Tooltip -->
              <div class="absolute bottom-full mb-2 hidden group-hover:flex flex-col items-start p-2.5 rounded-xl bg-slate-900 text-white text-[10px] shadow-xl z-20 whitespace-nowrap font-mono pointer-events-none border border-slate-700">
                <div class="font-bold text-emerald-400 mb-1">${d.date}</div>
                <div>Services: <strong class="text-white">${d.services}</strong></div>
                <div>Utilities: <strong class="text-white">${d.utilities}</strong></div>
                <div>Marketing: <strong class="text-white">${d.marketing}</strong></div>
                <div class="mt-1 pt-1 border-t border-slate-700 text-amber-300">Cost: ${totalCostDisplay}</div>
              </div>

              <!-- Stacked Bar -->
              <div class="w-full max-w-[28px] flex flex-col-reverse justify-start rounded-t-md overflow-hidden bg-surface-elevated h-44">
                <div style="height: ${sHeight}px;" class="w-full bg-emerald-500 transition-all"></div>
                <div style="height: ${uHeight}px;" class="w-full bg-sky-500 transition-all"></div>
                <div style="height: ${mHeight}px;" class="w-full bg-amber-500 transition-all"></div>
              </div>

              <!-- X-Axis Date Label -->
              <span class="text-[10px] font-mono text-muted truncate w-full text-center">
                ${d.date.slice(5)}
              </span>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function renderLLMChart(dailyTrends, currency) {
  if (!dailyTrends || dailyTrends.length === 0) {
    return `<div class="py-12 text-center text-muted text-xs">No daily LLM activity in this range.</div>`;
  }

  const maxTokens = Math.max(...dailyTrends.map(d => d.total_tokens), 1000);
  const chartHeight = 180;

  return `
    <div class="space-y-3">
      <div class="h-48 w-full flex items-end gap-2 pt-6 px-2 overflow-x-auto">
        ${dailyTrends.map(d => {
          const tHeight = Math.max(4, Math.round((d.total_tokens / maxTokens) * chartHeight));
          const costDisplay = formatCostValue(d.cost_ngn, d.cost_usd, currency);

          return `
            <div class="flex-1 min-w-[36px] flex flex-col items-center gap-1.5 group relative">
              
              <!-- Hover Tooltip -->
              <div class="absolute bottom-full mb-2 hidden group-hover:flex flex-col items-start p-2.5 rounded-xl bg-slate-900 text-white text-[10px] shadow-xl z-20 whitespace-nowrap font-mono pointer-events-none border border-slate-700">
                <div class="font-bold text-purple-400 mb-1">${d.date}</div>
                <div>Tokens: <strong class="text-white">${d.total_tokens.toLocaleString()}</strong></div>
                <div class="text-emerald-400">Est. Cost: <strong>${costDisplay}</strong></div>
              </div>

              <!-- Bar -->
              <div class="w-full max-w-[28px] flex flex-col justify-end rounded-t-md overflow-hidden bg-surface-elevated h-44">
                <div style="height: ${tHeight}px;" class="w-full bg-purple-500 rounded-t-md transition-all"></div>
              </div>

              <!-- Date -->
              <span class="text-[10px] font-mono text-muted truncate w-full text-center">
                ${d.date.slice(5)}
              </span>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function renderCommerceSummaryContent(data, currency) {
  return `
    <!-- Executive Metric Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      
      <!-- Total Revenue / GMV -->
      <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong">
        <div class="flex items-center justify-between text-muted text-xs font-semibold">
          <span>Total Sales (GMV)</span>
          <span class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">💰</span>
        </div>
        <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
          ${formatCurrency(data.total_revenue, currency)}
        </div>
        <div class="text-[12px] text-muted flex items-center gap-1.5 font-mono">
          <span class="text-emerald-600 dark:text-emerald-400 font-semibold">${data.paid_orders} paid orders</span>
          <span>&bull;</span>
          <span>AOV: ${formatCurrency(data.average_order_value, currency)}</span>
        </div>
      </div>

      <!-- Conversion Rate -->
      <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong">
        <div class="flex items-center justify-between text-muted text-xs font-semibold">
          <span>Order Conversion</span>
          <span class="p-1.5 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400">📈</span>
        </div>
        <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
          ${data.conversion_rate}%
        </div>
        <div class="text-[12px] text-muted font-mono">
          ${data.paid_orders} paid out of ${data.total_orders} total checkouts
        </div>
      </div>

      <!-- AI Resolution Rate -->
      <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong">
        <div class="flex items-center justify-between text-muted text-xs font-semibold">
          <span>AI Resolution Rate</span>
          <span class="p-1.5 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400">🤖</span>
        </div>
        <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
          ${data.ai_resolution_rate}%
        </div>
        <div class="text-[12px] text-muted font-mono">
          ${data.ai_resolved_conversations} autonomous resolutions
        </div>
      </div>

      <!-- Total Conversations -->
      <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong">
        <div class="flex items-center justify-between text-muted text-xs font-semibold">
          <span>Total Conversations</span>
          <span class="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">💬</span>
        </div>
        <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
          ${data.total_conversations}
        </div>
        <div class="text-[12px] text-muted font-mono">
          ${data.human_escalated_conversations} escalated to team
        </div>
      </div>

    </div>

    <!-- Secondary Visualizations -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      
      <!-- Channel Distribution -->
      <div class="card p-6 space-y-5">
        <div class="flex items-center justify-between pb-3 border-b border-subtle">
          <h3 class="text-sm font-bold text-main flex items-center gap-2">
            <span>📡</span> Channel Distribution
          </h3>
          <span class="text-xs text-muted">Omnichannel Traffic</span>
        </div>

        <div class="space-y-4">
          ${data.channels.map(ch => `
            <div class="space-y-1.5">
              <div class="flex items-center justify-between text-xs">
                <span class="font-bold text-main flex items-center gap-1.5">
                  <span class="w-2 h-2 rounded-full ${ch.channel.toLowerCase() === 'whatsapp' ? 'bg-emerald-500' : ch.channel.toLowerCase() === 'telegram' ? 'bg-sky-500' : 'bg-purple-500'}"></span>
                  ${ch.channel}
                </span>
                <div class="space-x-3 font-mono text-[12px]">
                  <span class="text-muted">${ch.conversations_count} convs (${ch.percentage}%)</span>
                  <span class="font-bold text-emerald-600 dark:text-emerald-400">${formatCurrency(ch.revenue, currency)}</span>
                </div>
              </div>
              <div class="h-2 rounded-full bg-surface-elevated overflow-hidden border border-subtle">
                <div class="h-full rounded-full ${ch.channel.toLowerCase() === 'whatsapp' ? 'bg-emerald-500' : ch.channel.toLowerCase() === 'telegram' ? 'bg-sky-500' : 'bg-purple-500'}" style="width: ${ch.percentage}%"></div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- AI Commerce Conversion Funnel -->
      <div class="card p-6 space-y-5">
        <div class="flex items-center justify-between pb-3 border-b border-subtle">
          <h3 class="text-sm font-bold text-main flex items-center gap-2">
            <span>🧠</span> AI Commerce Conversion Funnel
          </h3>
          <span class="badge badge-emerald text-xs font-mono">Real-time</span>
        </div>

        <div class="space-y-3">
          
          <div class="flex items-center justify-between p-3.5 rounded-xl bg-surface-elevated/60 border border-subtle text-xs">
            <div class="flex items-center gap-3">
              <div class="w-7 h-7 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400 flex items-center justify-center font-bold">1</div>
              <div>
                <div class="font-bold text-main">Total Customer Inquiries</div>
                <div class="text-[12px] text-muted">Incoming chat conversations</div>
              </div>
            </div>
            <span class="text-base font-black text-main font-mono">${data.total_conversations}</span>
          </div>

          <div class="flex items-center justify-between p-3.5 rounded-xl bg-surface-elevated/60 border border-subtle text-xs">
            <div class="flex items-center gap-3">
              <div class="w-7 h-7 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400 flex items-center justify-center font-bold">2</div>
              <div>
                <div class="font-bold text-main">Checkouts Generated</div>
                <div class="text-[12px] text-muted">Automated payment checkouts created</div>
              </div>
            </div>
            <span class="text-base font-black text-main font-mono">${data.total_orders}</span>
          </div>

          <div class="flex items-center justify-between p-3.5 rounded-xl bg-emerald-500/5 border border-emerald-500/25 text-xs">
            <div class="flex items-center gap-3">
              <div class="w-7 h-7 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 flex items-center justify-center font-bold">3</div>
              <div>
                <div class="font-bold text-emerald-700 dark:text-emerald-400">Completed Purchases</div>
                <div class="text-[12px] text-muted">Verified paid transactions</div>
              </div>
            </div>
            <span class="text-base font-black text-emerald-700 dark:text-emerald-400 font-mono">${data.paid_orders}</span>
          </div>

        </div>
      </div>

    </div>

    <!-- Top Products Converted by AI -->
    <div class="card p-6 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-subtle">
        <h3 class="text-sm font-bold text-main flex items-center gap-2">
          <span>📦</span> Top Products Converted by AI
        </h3>
        <span class="text-xs text-muted">Catalog Performance</span>
      </div>

      ${(data.top_products && data.top_products.length > 0) ? `
        <div class="overflow-x-auto border border-subtle rounded-xl">
          <table class="w-full text-left text-xs">
            <thead class="bg-surface-elevated text-muted font-semibold border-b border-subtle text-[12px]">
              <tr>
                <th class="p-3">Product Name</th>
                <th class="p-3">Unit Price</th>
                <th class="p-3">Orders</th>
                <th class="p-3 text-right">Total Revenue</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-subtle font-mono">
              ${data.top_products.map(prod => `
                <tr class="hover:bg-surface-hover transition-colors">
                  <td class="p-3 font-sans font-semibold text-main flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-sky-500"></span>
                    ${escapeHtml(prod.name)}
                  </td>
                  <td class="p-3 text-muted">${formatCurrency(prod.price, prod.currency || currency)}</td>
                  <td class="p-3 text-sky-600 dark:text-sky-400 font-semibold">${prod.orders_count}</td>
                  <td class="p-3 text-right font-bold text-emerald-600 dark:text-emerald-400">${formatCurrency(prod.total_sales, prod.currency || currency)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : `
        <div class="py-8 text-center text-muted text-xs">
          No product transactions recorded in this timeframe.
        </div>
      `}
    </div>
  `;
}
