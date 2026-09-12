import { state } from '../state.js';
import { api } from '../api.js';
import { showToast, formatCurrency, formatDate, skeletonPage, escapeHtml } from '../utils.js';

let currentDays = 7;

export async function loadReportsPage(container) {
  container.innerHTML = skeletonPage({ stats: 4, rows: 6 });

  try {
    const data = await api(`/reports/summary?days=${currentDays}`);
    renderReportsView(container, data);
  } catch (err) {
    console.error("Reports loading error:", err);
    container.innerHTML = `
      <div class="card p-10 text-center space-y-4 max-w-lg mx-auto my-8">
        <div class="w-14 h-14 rounded-2xl bg-rose-500/10 text-rose-500 border border-rose-500/20 flex items-center justify-center mx-auto text-2xl">⚠️</div>
        <h2 class="text-lg font-bold text-main">Failed to load reports</h2>
        <p class="text-xs text-muted max-w-md mx-auto">${escapeHtml(err.message || "An error occurred while aggregating commerce analytics.")}</p>
        <button onclick="window.location.reload()" class="btn btn-primary btn-sm mx-auto">Retry</button>
      </div>
    `;
  }
}

function renderReportsView(container, data) {
  const currency = data.currency || state.business?.currency || "NGN";

  container.innerHTML = `
    <div class="space-y-6 animate-fade-in">
      
      <!-- Top Action Bar -->
      <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-subtle">
        <div>
          <h1 class="text-2xl font-bold text-main tracking-tight flex items-center gap-2.5">
            <span>📊</span> Reports & Analytics
          </h1>
          <p class="text-xs text-muted mt-0.5">
            Real-time Gross Merchandise Value (GMV), order conversion funnel, AI resolution efficiency, and channel distribution.
          </p>
        </div>

        <div class="flex items-center gap-2.5 w-full sm:w-auto flex-wrap">
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
            ${data.ai_resolved_conversations} solved / ${data.human_escalated_conversations} escalated
          </div>
        </div>

        <!-- Total Sessions -->
        <div class="card p-5 space-y-2 relative overflow-hidden transition-all hover:border-strong">
          <div class="flex items-center justify-between text-muted text-xs font-semibold">
            <span>Total Sessions</span>
            <span class="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">💬</span>
          </div>
          <div class="text-2xl sm:text-3xl font-black text-main tracking-tight font-mono">
            ${data.total_conversations}
          </div>
          <div class="text-[12px] text-muted font-mono">
            Across WhatsApp, Telegram & Widget
          </div>
        </div>

      </div>

      <!-- Channel Breakdown & AI Efficiency -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        <!-- Channels Performance -->
        <div class="card p-6 space-y-5">
          <div class="flex items-center justify-between pb-3 border-b border-subtle">
            <h3 class="text-sm font-bold text-main flex items-center gap-2">
              <span>📡</span> Channel Distribution & Revenue
            </h3>
            <span class="badge badge-subtle text-xs font-mono">${data.channels?.length || 0} Channels</span>
          </div>

          <div class="space-y-3.5">
            ${(data.channels || []).map(ch => `
              <div class="space-y-2 p-3.5 rounded-xl bg-surface-elevated/60 border border-subtle">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-semibold text-main flex items-center gap-2">
                    ${ch.channel === 'Whatsapp' ? '🟢' : ch.channel === 'Telegram' ? '🔵' : '🟣'} ${ch.channel}
                  </span>
                  <div class="flex items-center gap-3 font-mono">
                    <span class="text-muted">${ch.conversations_count} chats (${ch.percentage}%)</span>
                    <span class="text-emerald-600 dark:text-emerald-400 font-bold">${formatCurrency(ch.revenue, currency)}</span>
                  </div>
                </div>
                <!-- Progress Bar -->
                <div class="w-full bg-surface-elevated h-2 rounded-full overflow-hidden border border-subtle">
                  <div class="bg-gradient-to-r from-sky-500 to-indigo-500 h-full rounded-full transition-all duration-500" style="width: ${ch.percentage > 0 ? ch.percentage : 0}%"></div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- AI Deflection & Efficiency Funnel -->
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

      <!-- Top Recommended Products -->
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

    </div>
  `;

  // Attach Event Listeners
  container.querySelectorAll('.timeframe-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const days = Number(btn.getAttribute('data-days'));
      currentDays = days;
      loadReportsPage(container);
    });
  });

  const exportBtn = container.querySelector('#export-csv-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', async () => {
      exportBtn.disabled = true;
      exportBtn.innerHTML = `<span>Exporting...</span>`;
      try {
        const token = localStorage.getItem("commb_admin_token") || localStorage.getItem("token");
        const headers = token ? { "Authorization": `Bearer ${token}` } : {};
        const res = await fetch(`/api/v1/reports/export-csv?days=${currentDays}`, { headers });
        if (!res.ok) throw new Error("CSV Export failed");
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `commb_report_${currentDays}d_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        showToast("Commerce report downloaded successfully", "success");
      } catch (e) {
        showToast(e.message || "Failed to download CSV", "error");
      } finally {
        exportBtn.disabled = false;
        exportBtn.innerHTML = `
          <svg class="w-4 h-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          <span>Export CSV</span>
        `;
      }
    });
  }
}
