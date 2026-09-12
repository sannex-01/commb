import { state } from '../state.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { showToast, openModal, closeModal, escapeHtml, formatCurrency, formatDate, skeletonPage } from '../utils.js';

export async function loadOverviewPage(container) {
  container.innerHTML = skeletonPage({ stats: 4, rows: 5 });
  try {
    const [data, paymentInfo] = await Promise.all([
      api('/overview'),
      api('/settings/payments').catch(() => ({ configured: false })),
    ]);
    state.business = data.business;

    const isBizConfigured = Boolean(data.business?.is_configured);
    const isPaymentConfigured = Boolean(paymentInfo?.configured);
    const hasCatalog = Number(data.stats?.total_products || 0) > 0;
    const hasKnowledge = Number(data.stats?.total_docs || 0) > 0;
    const hasAgents = Number(data.stats?.total_agents || 0) > 0;

    const setupSteps = [
      {
        id: 'step-biz',
        title: 'Business Profile',
        desc: 'Configure brand identity, store currency, and contact details',
        icon: 'store',
        route: '/_/admin/settings',
        btnText: 'Edit Settings',
        completed: Boolean(data.business?.name),
        meta: data.business?.name ? 'Configured' : 'Action Required',
      },
      {
        id: 'step-payments',
        title: 'Payment Gateway',
        desc: 'Connect Paystack (or Bumpa) so checkout links can actually collect payment',
        icon: 'credit-card',
        route: '/_/admin/integrations',
        btnText: isPaymentConfigured ? 'Edit Integrations' : 'Configure',
        completed: isPaymentConfigured,
        meta: isPaymentConfigured ? 'Configured' : 'Action Required',
      },
      {
        id: 'step-catalog',
        title: 'Products & Services Catalog',
        desc: 'Add items with pricing and media to enable automated conversational checkout',
        icon: 'package',
        route: '/_/admin/catalog',
        btnText: hasCatalog ? 'Manage Catalog' : 'Add Products',
        completed: hasCatalog,
        meta: hasCatalog ? `${data.stats.total_products} items` : 'Empty',
      },
      {
        id: 'step-rag',
        title: 'Knowledge Base (RAG)',
        desc: 'Upload FAQs, policies, and company documentation for grounded AI responses',
        icon: 'book-open',
        route: '/_/admin/rag',
        btnText: hasKnowledge ? 'View Docs' : 'Upload Docs',
        completed: hasKnowledge,
        meta: hasKnowledge ? `${data.stats.total_docs} docs` : 'Empty',
      },
      {
        id: 'step-agents',
        title: 'Deploy AI Agents',
        desc: 'Create assistant personas and connect WhatsApp, Telegram, or embeddable Website Widget',
        icon: 'bot',
        route: '/_/admin/agents',
        btnText: hasAgents ? 'Manage Agents' : 'Create Agent',
        completed: hasAgents,
        meta: hasAgents ? `${data.stats.total_agents} active` : 'None',
      },
      {
        id: 'step-team',
        title: 'Team Accounts & Roles',
        desc: 'Invite operators and managers to monitor live customer conversations and escalations',
        icon: 'user-check',
        route: '/_/admin/users',
        btnText: 'Manage Team',
        completed: false,
        required: false,
        meta: 'Optional',
      },
    ];

    const completedCount = setupSteps.filter(s => s.completed).length;
    const totalSetupCount = setupSteps.length;
    const progressPercent = Math.round((completedCount / totalSetupCount) * 100);
    const allRequiredCompleted = setupSteps.filter(s => s.required !== false).every(s => s.completed);

    const isGuideCollapsed = localStorage.getItem('commb_hide_setup_guide') === 'true';

    container.innerHTML = `
      <div class="space-y-6">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-2xl font-bold">Instance Overview</h1>
            <p class="text-sm text-muted">Real-time status for <strong>${escapeHtml(data.business.name)}</strong></p>
          </div>
          <button class="btn btn-sm glow-fill-agents text-white font-semibold" onclick="navigate('/_/admin/agents'); setTimeout(() => { if (window.openAgentModal) window.openAgentModal(); }, 100);">
            <i data-lucide="plus" class="w-4 h-4"></i> New Agent
          </button>
        </div>

        ${!allRequiredCompleted ? `
        <!-- Setup Guide Card -->
        <div class="card p-5 sm:p-6 bg-surface-elevated/40 border-brand/20 shadow-sm transition-all" id="setup-guide-card">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-subtle">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl bg-brand/10 text-brand flex items-center justify-center flex-shrink-0">
                <i data-lucide="sparkles" class="w-5 h-5"></i>
              </div>
              <div>
                <h2 class="font-bold text-base text-main flex items-center gap-2">
                  Quick Setup Guide
                  <span class="badge ${progressPercent === 100 ? 'badge-emerald' : 'badge-brand'} text-[12px] py-0.5">
                    ${completedCount} of ${totalSetupCount} Completed
                  </span>
                </h2>
                <p class="text-xs text-muted mt-0.5">Follow these guided steps to launch your AI conversational commerce assistant</p>
              </div>
            </div>
            <button class="btn btn-secondary btn-xs self-start sm:self-auto flex items-center gap-1 text-muted hover:text-main" id="btn-toggle-setup-guide">
              <i data-lucide="${isGuideCollapsed ? 'chevron-down' : 'chevron-up'}" class="w-3.5 h-3.5"></i>
              <span>${isGuideCollapsed ? 'Expand Guide' : 'Collapse'}</span>
            </button>
          </div>

          <div class="mt-3.5 ${isGuideCollapsed ? 'hidden' : ''}" id="setup-guide-content">
            <!-- Progress Bar -->
            <div class="space-y-1.5 mb-5">
              <div class="flex justify-between text-[12px] text-muted">
                <span>Setup Progress</span>
                <span class="font-semibold font-mono text-main">${progressPercent}%</span>
              </div>
              <div class="w-full bg-surface-elevated rounded-full h-2 overflow-hidden border border-subtle">
                <div class="bg-gradient-to-r from-brand to-emerald-500 h-2 transition-all duration-500 rounded-full" style="width: ${progressPercent}%;"></div>
              </div>
            </div>

            <!-- Steps List -->
            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              ${setupSteps.map((step, idx) => `
                <div class="p-3.5 rounded-xl border transition-all flex flex-col justify-between ${step.completed ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-subtle bg-surface/60 hover:bg-surface-hover'}">
                  <div>
                    <div class="flex items-start justify-between gap-2 mb-2">
                      <div class="flex items-center gap-2">
                        <span class="w-5 h-5 rounded-full flex items-center justify-center text-[12px] font-bold ${step.completed ? 'bg-emerald-500 text-white' : 'bg-surface-elevated border border-subtle text-muted'}">
                          ${step.completed ? '<i data-lucide="check" class="w-3 h-3"></i>' : idx + 1}
                        </span>
                        <h3 class="font-semibold text-xs text-main">${escapeHtml(step.title)}</h3>
                      </div>
                      <span class="badge ${step.completed ? 'badge-emerald' : 'badge-subtle'} text-[12px] py-0 px-1.5">
                        ${escapeHtml(step.meta || (step.completed ? 'Done' : 'Pending'))}
                      </span>
                    </div>
                    <p class="text-[12px] text-muted leading-relaxed line-clamp-2 mb-3 pl-7">${escapeHtml(step.desc)}</p>
                  </div>
                  <div class="flex justify-end pt-2 border-t border-subtle/60">
                    <button class="btn ${step.completed ? 'btn-secondary' : 'btn-primary'} btn-xs flex items-center gap-1" onclick="navigate('${step.route}')">
                      <span>${escapeHtml(step.btnText)}</span>
                      <i data-lucide="arrow-right" class="w-3 h-3"></i>
                    </button>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        </div>` : ''}

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div class="card p-5 flex flex-col gap-1">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-semibold text-muted">Active Agents</span>
              <i data-lucide="bot" class="w-4 h-4 text-muted"></i>
            </div>
            <div class="text-2xl font-bold text-main">${data.stats.active_agents} <span class="text-sm text-muted font-medium">/ ${data.stats.total_agents} total</span></div>
          </div>
          <div class="card p-5 flex flex-col gap-1">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-semibold text-muted">Total Customers</span>
              <i data-lucide="users" class="w-4 h-4 text-muted"></i>
            </div>
            <div class="text-2xl font-bold text-main">${data.stats.total_customers}</div>
          </div>
          <div class="card p-5 flex flex-col gap-1">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-semibold text-muted">Total Orders</span>
              <i data-lucide="shopping-cart" class="w-4 h-4 text-muted"></i>
            </div>
            <div class="text-2xl font-bold text-main">${data.stats.total_orders}</div>
          </div>
          <div class="card p-5 flex flex-col gap-1">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-semibold text-muted">Total Revenue</span>
              <i data-lucide="credit-card" class="w-4 h-4 text-muted"></i>
            </div>
            <div class="text-2xl font-bold text-main">${formatCurrency(data.stats.total_revenue, data.business.currency)}</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="card p-6">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-bold text-base">Recent Orders</h3>
              <a class="text-xs text-brand font-medium cursor-pointer" onclick="navigate('/_/admin/customers')">View All</a>
            </div>
            ${data.recent_orders.length === 0 ? '<p class="text-sm text-muted">No orders placed yet.</p>' : `
              <div class="table-container">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Ref</th>
                      <th>Customer</th>
                      <th>Amount</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${data.recent_orders.map(o => `
                      <tr>
                        <td class="font-mono text-xs font-semibold">${escapeHtml(o.order_reference)}</td>
                        <td>${escapeHtml(o.customer_name)}</td>
                        <td>${formatCurrency(o.total_amount, o.currency)}</td>
                        <td><span class="badge badge-emerald">${escapeHtml(o.status)}</span></td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>
            `}
          </div>

          <div class="card">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-bold text-base">Recent Conversations</h3>
              <span class="badge badge-sky">${data.stats.active_sessions_7d} active 7d</span>
            </div>
            ${data.recent_sessions.length === 0 ? '<p class="text-sm text-muted">No conversation sessions yet.</p>' : `
              <div class="table-container">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Channel</th>
                      <th>Identifier</th>
                      <th>Last Active</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${data.recent_sessions.map(s => `
                      <tr>
                        <td><span class="badge badge-subtle">${escapeHtml(s.channel)}</span></td>
                        <td class="font-mono text-xs">${escapeHtml(s.customer_identifier)}</td>
                        <td class="text-xs text-muted">${formatDate(s.last_active_at)}</td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>
            `}
          </div>
        </div>
      </div>
    `;

    const toggleBtn = document.getElementById('btn-toggle-setup-guide');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const content = document.getElementById('setup-guide-content');
        if (content) {
          const isHidden = content.classList.toggle('hidden');
          localStorage.setItem('commb_hide_setup_guide', String(isHidden));
          toggleBtn.innerHTML = `
            <i data-lucide="${isHidden ? 'chevron-down' : 'chevron-up'}" class="w-3.5 h-3.5"></i>
            <span>${isHidden ? 'Expand Guide' : 'Collapse'}</span>
          `;
          if (window.lucide) lucide.createIcons();
        }
      });
    }

    if (window.lucide) lucide.createIcons();
  } catch (err) {
    container.innerHTML = `<div class="p-8 text-center text-rose">Failed to load overview: ${escapeHtml(err.message)}</div>`;
  }
}

// ============================================================================
// 5. MULTI-AGENT STUDIO PAGE
// ============================================================================