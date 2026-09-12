import { state } from '../state.js';
import { api } from '../api.js';
import { showToast, escapeHtml, skeletonPage, initAllCustomSelects, initPasswordToggles, uploadMediaFile } from '../utils.js';

// Messaging Channels, Payment Gateways, Email Delivery, Storage & Media,
// Store Connections (Bumpa & similar catalog+checkout platforms), and Order
// Alerts (SMS/Telegram/WhatsApp) — split out of settings.js so "Settings"
// stays just Business Profile / Password / Platform API Key.

export async function loadIntegrationsPage(container) {
  if (!['admin', 'super_admin'].includes(state.user?.role)) {
    container.innerHTML = `
      <div class="card text-center p-12 space-y-4 max-w-lg mx-auto mt-12">
        <div class="w-12 h-12 rounded-full bg-rose/10 text-rose flex items-center justify-center mx-auto">
          <i data-lucide="shield-alert" class="w-6 h-6"></i>
        </div>
        <div>
          <h3 class="font-bold text-lg text-main">Administrator Access Required</h3>
          <p class="text-xs text-muted mt-1">Messaging channels, payment gateways, storage and order alerts can only be managed by team administrators.</p>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="navigate('/_/admin/overview')">Back to Overview</button>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  container.innerHTML = skeletonPage({ stats: 0, rows: 4 });
  try {
    const [storageInfo, emailInfo, paymentInfo, channelsInfo, bumpaInfo, paystackConnectionInfo, smsInfo, telegramAlertsInfo, alertRecipientsInfo] = await Promise.all([
      api('/settings/storage'),
      api('/settings/email').catch(() => ({ provider: null, configured: false, config: {} })),
      api('/settings/payments').catch(() => ({ provider: null, configured: false, config: {}, available_currencies: [] })),
      api('/settings/channels').catch(() => ({ whatsapp: {}, telegram: {}, widget: {} })),
      api('/settings/store-connections/bumpa').catch(() => ({ configured: false, config: {} })),
      api('/settings/store-connections/paystack').catch(() => ({ configured: false, config: {} })),
      api('/settings/sms').catch(() => ({ provider: null, configured: false, config: {} })),
      api('/settings/alerts/telegram').catch(() => ({ configured: false, config: {} })),
      api('/settings/alerts/recipients').catch(() => ({ emails: [], phones: [] })),
    ]);
    state.storageInfo = storageInfo;
    state.emailInfo = emailInfo;
    state.paymentInfo = paymentInfo;
    state.channelsInfo = channelsInfo;
    state.bumpaInfo = bumpaInfo;
    state.paystackConnectionInfo = paystackConnectionInfo;
    state.smsInfo = smsInfo;
    state.telegramAlertsInfo = telegramAlertsInfo;
    state.alertRecipientsInfo = alertRecipientsInfo;

    const tabs = [
      { id: 'store-connections', label: 'Store Connections', icon: 'store' },
      { id: 'payments', label: 'Payment Gateways', icon: 'credit-card' },
      { id: 'channels', label: 'Messaging Channels', icon: 'message-square' },
      { id: 'alerts', label: 'Order Alerts', icon: 'bell-ring' },
      { id: 'email', label: 'Email Delivery', icon: 'mail' },
      { id: 'storage', label: 'Storage & Media', icon: 'hard-drive' },
    ];
    const activeTab = state.integrationsTab && tabs.some(t => t.id === state.integrationsTab) ? state.integrationsTab : 'store-connections';

    container.innerHTML = `
      <div class="space-y-6">
        <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 class="text-2xl font-bold">Integrations</h1>
            <p class="text-sm text-muted">Connect storefronts, payment gateways, messaging channels, order alerts, email delivery & media storage</p>
          </div>
          <button class="btn btn-secondary flex items-center gap-2" onclick="window.toggleTheme()" title="Switch Theme">
            <i data-lucide="${state.theme === 'dark' ? 'sun' : 'moon'}" class="w-4 h-4 text-brand"></i>
            <span>${state.theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
        </div>

        <div class="flex flex-col md:flex-row gap-6 items-start">
          <nav class="w-full md:w-60 flex-shrink-0 flex flex-row md:flex-col gap-1 p-1.5 bg-sidebar rounded-xl border border-subtle overflow-x-auto">
            ${tabs.map(t => `
              <button class="integrations-tab flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg text-[14px] font-medium text-left transition-colors whitespace-nowrap ${activeTab === t.id ? 'bg-surface-hover text-main' : 'text-muted hover:bg-surface-hover hover:text-main'}" data-tab="${t.id}">
                <i data-lucide="${t.icon}" class="w-4 h-4 flex-shrink-0"></i>
                <span>${t.label}</span>
              </button>
            `).join('')}
          </nav>

          <div class="flex-1 min-w-0 w-full" id="integrations-tab-content"></div>
        </div>
      </div>
    `;

    // ------------------------------------------------------------------
    // Store Connections — external platforms whose catalog can be
    // imported (Bumpa today) and which can also, via the share_for_payments
    // toggle, double as a Payment Gateway credential.
    // ------------------------------------------------------------------
    function renderStoreConnectionsTab() {
      const el = document.getElementById('integrations-tab-content');
      const bp = state.bumpaInfo || {};
      const bpCfg = bp.config || {};
      const ps = state.paystackConnectionInfo || {};
      const psCfg = ps.config || {};

      // Mirrors Payment Gateways' own picker: pick which storefront to
      // import from (or none) rather than showing every provider's card
      // stacked on top of each other. Whichever was last configured (has a
      // key saved) is pre-selected; "none" if neither does.
      const current = state.storeConnectionProvider || (bp.configured ? 'bumpa' : (ps.configured ? 'paystack' : 'none'));
      const isBumpa = current === 'bumpa';
      const isPaystack = current === 'paystack';

      const shareToggle = (idPrefix, cfg) => `
        <div class="flex items-start gap-3 p-3 rounded-lg bg-surface border border-subtle">
          <label class="relative inline-flex items-center cursor-pointer flex-shrink-0 mt-0.5">
            <input type="checkbox" id="${idPrefix}-share-payments" class="sr-only peer" ${cfg.share_for_payments ? 'checked' : ''} />
            <div class="w-9 h-5 bg-surface-elevated peer-checked:bg-brand rounded-full peer transition-colors border border-subtle after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4"></div>
          </label>
          <div class="text-xs">
            <div class="font-semibold text-main">Share this credential for payments</div>
            <div class="text-muted mt-0.5">
              Lets this same key be used under Payment Gateways instead of pasting it twice. This does <strong>not</strong> make it your default gateway; you still choose that in Payment Gateways.
            </div>
          </div>
        </div>
      `;

      el.innerHTML = `
        <div class="card space-y-6">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-bold text-base text-main">Store Connection</h3>
              <p class="text-xs text-muted mt-0.5">Import a product catalog from an external storefront, and optionally share the credential for checkout & fulfillment</p>
            </div>
            <span class="badge ${(isBumpa && bp.configured) || (isPaystack && ps.configured) ? 'badge-emerald' : 'badge-subtle'}">
              ${(isBumpa && bp.configured) || (isPaystack && ps.configured) ? `Connected: ${current.charAt(0).toUpperCase() + current.slice(1)}` : 'Not Connected'}
            </span>
          </div>

          <div class="space-y-2">
            <label class="form-label text-xs font-semibold text-main">Storefront</label>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3" id="store-connection-provider-cards">
              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${isPaystack ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="store-connection-provider" value="paystack" ${isPaystack ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchStoreConnectionProviderUI('paystack')" />
                <div>
                  <div class="font-semibold text-sm text-main">Paystack</div>
                  <div class="text-[12px] text-muted mt-0.5">Import products from your Paystack catalog</div>
                </div>
              </label>
              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${isBumpa ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="store-connection-provider" value="bumpa" ${isBumpa ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchStoreConnectionProviderUI('bumpa')" />
                <div>
                  <div class="font-semibold text-sm text-main">Bumpa</div>
                  <div class="text-[12px] text-muted mt-0.5">Import your Bumpa catalog & optionally checkout through it</div>
                </div>
              </label>
              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${!isBumpa && !isPaystack ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="store-connection-provider" value="none" ${!isBumpa && !isPaystack ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchStoreConnectionProviderUI('none')" />
                <div>
                  <div class="font-semibold text-sm text-main">Disabled</div>
                  <div class="text-[12px] text-muted mt-0.5">No external storefront connected</div>
                </div>
              </label>
            </div>
          </div>

          <!-- Paystack Fields -->
          <form id="store-connection-paystack-form" class="${isPaystack ? '' : 'hidden'} space-y-4">
            <div class="p-4 rounded-xl border border-subtle bg-surface-elevated/30 space-y-4">
              <div class="form-group">
                <label class="form-label flex items-center justify-between">
                  <span>Secret API Key</span>
                  ${psCfg.api_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">saved (${escapeHtml(psCfg.api_key_masked || '')})</span>` : ''}
                </label>
                <input type="password" id="paystack-conn-api-key" class="form-control font-mono text-xs" placeholder="${psCfg.api_key_configured ? '•••••••••••••••• (Leave blank to keep saved key)' : 'sk_live_...'}" />
                <p class="text-[12px] text-muted mt-1">Used to fetch your Paystack product catalog for import.</p>
              </div>
              ${shareToggle('paystack-conn', psCfg)}
            </div>
            <div class="flex justify-end">
              <button type="submit" class="btn btn-primary" id="btn-save-store-paystack">Save Paystack Connection</button>
            </div>
          </form>

          <!-- Bumpa Fields -->
          <form id="store-connection-bumpa-form" class="${isBumpa ? '' : 'hidden'} space-y-4">
            <div class="p-4 rounded-xl border border-subtle bg-surface-elevated/30 space-y-4">
              <div class="grid grid-cols-2 gap-4">
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label flex items-center justify-between">
                    <span>Secret API Key</span>
                    ${bpCfg.api_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">saved (${escapeHtml(bpCfg.api_key_masked || '')})</span>` : ''}
                  </label>
                  <input type="password" id="bumpa-api-key" class="form-control font-mono text-xs" placeholder="${bpCfg.api_key_configured ? '•••••••••••••••• (Leave blank to keep saved key)' : 'Bumpa secret API key'}" />
                  <p class="text-[12px] text-muted mt-1">Used for catalog import and order/analytics lookups.</p>
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label flex items-center justify-between">
                    <span>Public API Key</span>
                    ${bpCfg.public_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">saved (${escapeHtml(bpCfg.public_key_masked || '')})</span>` : ''}
                  </label>
                  <input type="password" id="bumpa-public-key" class="form-control font-mono text-xs" placeholder="${bpCfg.public_key_configured ? '•••••••••••••••• (Leave blank to keep saved key)' : 'Bumpa public API key'}" />
                  <p class="text-[12px] text-muted mt-1">Needed for real checkout via Bumpa (cart & payment-intent).</p>
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Store / Location ID</label>
                  <input type="text" id="bumpa-store-id" class="form-control text-xs" value="${escapeHtml(bpCfg.store_id || '')}" placeholder="Optional — defaults to your store's default location" />
                </div>
              </div>
              ${shareToggle('bumpa', bpCfg)}
            </div>
            <div class="flex justify-end">
              <button type="submit" class="btn btn-primary" id="btn-save-store-bumpa">Save Bumpa Connection</button>
            </div>
          </form>

          <!-- Disabled State Info -->
          <div id="store-connection-fields-none" class="${!isBumpa && !isPaystack ? '' : 'hidden'} p-4 rounded-xl border border-dashed border-subtle text-center text-xs text-muted">
            No external storefront is connected. Products are managed directly in your Catalog.
          </div>
        </div>
      `;

      window.switchStoreConnectionProviderUI = (provider) => {
        state.storeConnectionProvider = provider;
        document.getElementById('store-connection-paystack-form')?.classList.toggle('hidden', provider !== 'paystack');
        document.getElementById('store-connection-bumpa-form')?.classList.toggle('hidden', provider !== 'bumpa');
        document.getElementById('store-connection-fields-none')?.classList.toggle('hidden', provider !== 'none');

        document.querySelectorAll('input[name="store-connection-provider"]').forEach(inp => {
          const card = inp.closest('label');
          if (card) {
            card.className = inp.value === provider
              ? 'flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-brand bg-brand/5 shadow-sm'
              : 'flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-subtle bg-surface-elevated/40 hover:bg-surface-hover';
          }
        });
      };

      document.getElementById('store-connection-paystack-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('btn-save-store-paystack');
        const orig = btn.innerHTML;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 mr-1 animate-spin"></i> Saving...`;
        btn.disabled = true;
        if (window.lucide) lucide.createIcons();

        const payload = {
          api_key: document.getElementById('paystack-conn-api-key').value.trim() || undefined,
          share_for_payments: document.getElementById('paystack-conn-share-payments').checked,
        };

        try {
          const res = await api('/settings/store-connections/paystack', { method: 'PUT', body: JSON.stringify(payload) });
          state.paystackConnectionInfo = res;
          showToast('Paystack connection saved successfully', 'success');
          renderStoreConnectionsTab();
        } catch (err) {
          showToast(err.message || 'Failed to save Paystack connection', 'error');
          btn.innerHTML = orig;
          btn.disabled = false;
          if (window.lucide) lucide.createIcons();
        }
      });

      document.getElementById('store-connection-bumpa-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('btn-save-store-bumpa');
        const orig = btn.innerHTML;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 mr-1 animate-spin"></i> Saving...`;
        btn.disabled = true;
        if (window.lucide) lucide.createIcons();

        const payload = {
          api_key: document.getElementById('bumpa-api-key').value.trim() || undefined,
          public_key: document.getElementById('bumpa-public-key').value.trim() || undefined,
          store_id: document.getElementById('bumpa-store-id').value.trim(),
          share_for_payments: document.getElementById('bumpa-share-payments').checked,
        };

        try {
          const res = await api('/settings/store-connections/bumpa', { method: 'PUT', body: JSON.stringify(payload) });
          state.bumpaInfo = res;
          showToast('Bumpa connection saved successfully', 'success');
          renderStoreConnectionsTab();
        } catch (err) {
          showToast(err.message || 'Failed to save Bumpa connection', 'error');
          btn.innerHTML = orig;
          btn.disabled = false;
          if (window.lucide) lucide.createIcons();
        }
      });

      if (window.lucide) lucide.createIcons();
    }

    // ------------------------------------------------------------------
    // Payment Gateways — Paystack (own key, or shared from Store
    // Connections) and Bumpa (always shared from Store Connections).
    // ------------------------------------------------------------------
    function renderPaymentsTab() {
      const el = document.getElementById('integrations-tab-content');
      const pm = state.paymentInfo || {};
      const currentProvider = pm.provider || 'none';
      const cfg = pm.config || {};
      const isPaystack = currentProvider === 'paystack';
      const isBumpa = currentProvider === 'bumpa';
      const sharedFrom = cfg.shared_from_connection;

      el.innerHTML = `
        <div class="card space-y-6">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-bold text-base text-main">Payment Gateway</h3>
              <p class="text-xs text-muted mt-0.5">Configure how CommB generates checkout and instant payment links across conversations</p>
            </div>
            <span class="badge ${pm.configured ? 'badge-emerald' : 'badge-subtle'}">
              ${pm.configured ? `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1 animate-pulse"></span> Active: ${escapeHtml(currentProvider.charAt(0).toUpperCase() + currentProvider.slice(1))}` : 'Disabled'}
            </span>
          </div>

          <div class="space-y-2">
            <label class="form-label text-xs font-semibold text-main">Gateway Status</label>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3" id="payment-provider-cards">
              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${isPaystack ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="payment-provider" value="paystack" ${isPaystack ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchPaymentProviderUI('paystack')" />
                <div>
                  <div class="flex items-center gap-1.5 font-semibold text-sm text-main">
                    Paystack
                    <span class="badge badge-brand text-[12px] py-0 px-1">Confirmed</span>
                  </div>
                  <div class="text-[12px] text-muted mt-0.5">Accept Cards, Bank Transfer, USSD, Apple Pay & Mobile Money</div>
                </div>
              </label>

              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${isBumpa ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="payment-provider" value="bumpa" ${isBumpa ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchPaymentProviderUI('bumpa')" />
                <div>
                  <div class="flex items-center gap-1.5 font-semibold text-sm text-main">Bumpa</div>
                  <div class="text-[12px] text-muted mt-0.5">Checkout through Bumpa's own cart & payment flow</div>
                </div>
              </label>

              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${!isPaystack && !isBumpa ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="payment-provider" value="none" ${!isPaystack && !isBumpa ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchPaymentProviderUI('none')" />
                <div>
                  <div class="font-semibold text-sm text-main">Disabled</div>
                  <div class="text-[12px] text-muted mt-0.5">Turn off automated checkout link generation</div>
                </div>
              </label>
            </div>
          </div>

          <form id="payments-settings-form" class="space-y-4">
            <!-- Paystack Fields -->
            <div id="payment-fields-paystack" class="${isPaystack ? '' : 'hidden'} space-y-4 p-4 rounded-xl border border-subtle bg-surface-elevated/30">
              ${isPaystack && sharedFrom ? `
                <div class="p-3 rounded-lg bg-brand/5 border border-brand/20 text-xs text-main flex items-start gap-2">
                  <i data-lucide="link" class="w-4 h-4 text-brand flex-shrink-0 mt-0.5"></i>
                  <div>
                    Using the shared credential from <strong>Store Connections → ${escapeHtml(sharedFrom.charAt(0).toUpperCase() + sharedFrom.slice(1))}</strong>.
                    Turn off "Share for payments" there to set a separate Paystack key here instead.
                  </div>
                </div>
              ` : `
                <div class="flex items-center justify-between">
                  <div class="font-semibold text-xs text-main">Paystack API Credentials</div>
                  <a href="https://dashboard.paystack.com/#/settings/developer" target="_blank" class="text-[12px] text-brand hover:underline flex items-center gap-1">
                    Developer Dashboard <i data-lucide="external-link" class="w-3 h-3"></i>
                  </a>
                </div>
                <div class="grid grid-cols-2 gap-4">
                  <div class="form-group col-span-2 sm:col-span-1">
                    <label class="form-label flex items-center justify-between">
                      <span>Secret Key</span>
                      ${cfg.secret_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">saved (${escapeHtml(cfg.secret_key_masked || '')})</span>` : ''}
                    </label>
                    <input type="password" id="paystack-secret-key" class="form-control font-mono text-xs" placeholder="${cfg.secret_key_configured ? '•••••••••••••••• (Leave blank to keep saved key)' : 'sk_live_...'}" />
                  </div>
                  <div class="form-group col-span-2 sm:col-span-1">
                    <label class="form-label">Public Key</label>
                    <input type="text" id="paystack-public-key" class="form-control font-mono text-xs" value="${escapeHtml(cfg.public_key || '')}" placeholder="pk_live_..." />
                  </div>
                </div>
              `}
              <div class="p-3 rounded-lg bg-surface text-xs text-muted flex items-start gap-2 border border-subtle">
                <i data-lucide="info" class="w-4 h-4 text-brand flex-shrink-0 mt-0.5"></i>
                <div>
                  Set your Paystack Webhook URL to: <code class="text-brand font-mono text-[12px] select-all">${window.location.origin}/api/v1/payments/webhook/paystack</code>
                </div>
              </div>
              ${pm.configured && isPaystack && pm.available_currencies && pm.available_currencies.length ? `
                <div class="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs text-main">
                  <div class="flex items-center gap-1.5 font-semibold text-emerald-600 dark:text-emerald-400 mb-1.5">
                    <i data-lucide="check-circle" class="w-3.5 h-3.5"></i>
                    <span>Discovered Merchant Currencies</span>
                  </div>
                  <div class="flex flex-wrap gap-1.5">
                    ${pm.available_currencies.map(c => `
                      <span class="badge badge-emerald text-[12px] font-mono">${escapeHtml(c.code)} (${escapeHtml(c.symbol)})</span>
                    `).join('')}
                  </div>
                </div>
              ` : ''}
            </div>

            <!-- Bumpa Fields -->
            <div id="payment-fields-bumpa" class="${isBumpa ? '' : 'hidden'} p-4 rounded-xl border border-subtle bg-surface-elevated/30 text-xs text-main space-y-2">
              ${cfg.shared_from_connection === 'bumpa' ? `
                <div class="flex items-center gap-1.5 font-semibold text-emerald-600 dark:text-emerald-400">
                  <i data-lucide="check-circle" class="w-3.5 h-3.5"></i> Using the credential shared from Store Connections → Bumpa.
                </div>
              ` : `
                <div class="flex items-center gap-1.5 font-semibold text-amber-600 dark:text-amber-400">
                  <i data-lucide="alert-triangle" class="w-3.5 h-3.5"></i> Bumpa has no separate payment key here.
                </div>
                <p class="text-muted">Turn on "Share for payments" on the Bumpa card under Store Connections first — Bumpa's checkout uses that same credential.</p>
                <button type="button" class="btn btn-secondary btn-sm mt-1" onclick="document.querySelector('[data-tab=store-connections]').click()">Go to Store Connections</button>
              `}
            </div>

            <!-- Disabled State Info -->
            <div id="payment-fields-none" class="${!isPaystack && !isBumpa ? '' : 'hidden'} p-4 rounded-xl border border-dashed border-subtle text-center text-xs text-muted">
              Payment link generation is disabled. Customer orders will be recorded with pending payment status.
            </div>

            <div class="flex justify-end pt-4 border-t border-subtle">
              <button type="submit" class="btn btn-primary" id="btn-save-payments">Save Payment Settings</button>
            </div>
          </form>
        </div>
      `;

      window.switchPaymentProviderUI = (provider) => {
        document.getElementById('payment-fields-paystack')?.classList.toggle('hidden', provider !== 'paystack');
        document.getElementById('payment-fields-bumpa')?.classList.toggle('hidden', provider !== 'bumpa');
        document.getElementById('payment-fields-none')?.classList.toggle('hidden', provider !== 'none');

        document.querySelectorAll('input[name="payment-provider"]').forEach(inp => {
          const card = inp.closest('label');
          if (card) {
            card.className = inp.value === provider
              ? 'flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-brand bg-brand/5 shadow-sm'
              : 'flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-subtle bg-surface-elevated/40 hover:bg-surface-hover';
          }
        });
      };

      document.getElementById('payments-settings-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const selected = document.querySelector('input[name="payment-provider"]:checked')?.value || 'none';
        let configPayload = {};
        if (selected === 'paystack' && !sharedFrom) {
          configPayload = {
            secret_key: document.getElementById('paystack-secret-key')?.value.trim() || undefined,
            public_key: document.getElementById('paystack-public-key')?.value.trim(),
          };
        }

        try {
          const res = await api('/settings/payments', {
            method: 'PUT',
            body: JSON.stringify({ provider: selected === 'none' ? null : selected, config: configPayload })
          });
          state.paymentInfo = res;
          showToast('Payment gateway settings saved successfully', 'success');
          renderPaymentsTab();
        } catch (err) {
          showToast(err.message || 'Failed to save payment settings', 'error');
        }
      });

      initAllCustomSelects(el);
      if (window.lucide) lucide.createIcons();
    }

    // ------------------------------------------------------------------
    // Order Alerts — SMS (Africa's Talking / Termii), Telegram (dedicated
    // alerts bot). WhatsApp template alerts are a documented future
    // channel (needs a Meta-approved template) not yet built.
    // ------------------------------------------------------------------
    function renderAlertsTab() {
      const el = document.getElementById('integrations-tab-content');
      const sms = state.smsInfo || {};
      const email = state.emailInfo || {};
      const tg = state.telegramAlertsInfo || {};
      const tgCfg = tg.config || {};
      const recipients = state.alertRecipientsInfo || { emails: [], phones: [] };

      const emailReady = Boolean(email.configured);
      const smsReady = Boolean(sms.configured);
      const tgBotReady = Boolean(tgCfg.has_telegram_bot);

      el.innerHTML = `
        <div class="space-y-6">
          <div class="card space-y-6">
            <div>
              <h3 class="font-bold text-base text-main">Order Alerts</h3>
              <p class="text-xs text-muted mt-0.5">Get notified the moment a customer pays — each channel below only works once its underlying setup is done elsewhere.</p>
            </div>

            <!-- Who Gets Notified -->
            <div class="p-4 rounded-xl border border-subtle bg-surface-elevated/20 space-y-4">
              <div class="flex items-center gap-2 text-xs font-semibold text-main">
                <i data-lucide="users" class="w-4 h-4 text-brand"></i> Who Gets Notified
              </div>
              <form id="alert-recipients-form" class="space-y-3">
                <div class="form-group">
                  <label class="form-label flex items-center justify-between">
                    <span>Alert Email Addresses</span>
                    <span class="badge ${emailReady ? 'badge-emerald' : 'badge-subtle'} text-[12px]">${emailReady ? 'Ready' : 'Needs Email Delivery'}</span>
                  </label>
                  <input type="text" id="alert-recipient-emails" class="form-control text-xs" ${emailReady ? '' : 'disabled'} value="${escapeHtml((recipients.emails || []).join(', '))}" placeholder="owner@example.com, manager@example.com" />
                  <p class="text-[12px] text-muted mt-1">${emailReady ? 'Comma-separated.' : 'Set up Email Delivery below to enable this.'}</p>
                </div>
                <div class="form-group">
                  <label class="form-label flex items-center justify-between">
                    <span>Alert Phone Numbers</span>
                    <span class="badge ${smsReady ? 'badge-emerald' : 'badge-subtle'} text-[12px]">${smsReady ? 'Ready' : 'Needs SMS'}</span>
                  </label>
                  <input type="text" id="alert-recipient-phones" class="form-control text-xs" ${smsReady ? '' : 'disabled'} value="${escapeHtml((recipients.phones || []).join(', '))}" placeholder="+2348012345678, +2348098765432" />
                  <p class="text-[12px] text-muted mt-1">${smsReady ? 'Comma-separated.' : 'Set up SMS under Integrations → Messaging Channels to enable this.'}</p>
                </div>
                <div class="form-group">
                  <label class="form-label flex items-center justify-between">
                    <span>Telegram Alert Group ID</span>
                    <span class="badge ${tgBotReady ? 'badge-emerald' : 'badge-subtle'} text-[12px]">${tgBotReady ? 'Ready' : 'Needs a Telegram Bot'}</span>
                  </label>
                  <input type="text" id="alert-telegram-chat-id" class="form-control text-xs" ${tgBotReady ? '' : 'disabled'} value="${escapeHtml(tgCfg.chat_id || '')}" placeholder="e.g. -1001234567890 (or a personal chat ID)" />
                  <p class="text-[12px] text-muted mt-1">
                    ${tgBotReady
                      ? 'Alerts for an order are sent via whichever agent sold it (falling back to any agent with a Telegram bot). Follow the steps below to get your Group ID.'
                      : 'Connect a Telegram bot on at least one agent in AI Agents Studio to enable this — no separate alerts-only bot needed.'}
                  </p>
                </div>
                <div class="flex items-center justify-between gap-3">
                  ${tgBotReady && tg.configured ? `<button type="button" id="btn-test-tg-alert" class="btn btn-secondary btn-sm">Send Test Telegram Alert</button>` : '<div></div>'}
                  <button type="submit" class="btn btn-primary btn-sm">Save</button>
                </div>
              </form>

              <!-- Telegram Alert Group Setup Guide -->
              <div class="p-4 rounded-xl border border-subtle bg-surface space-y-2.5 text-xs">
                <div class="font-bold text-main flex items-center gap-1.5 text-sky">
                  <i data-lucide="check-circle-2" class="w-4 h-4"></i> Telegram Alert Group — Setup Instructions
                </div>
                <ol class="list-decimal list-inside space-y-1.5 text-muted leading-relaxed">
                  <li>Add your agent's <span class="font-semibold text-main">Telegram bot</span> to the desired group chat with your team.</li>
                  <li>Add <a href="https://t.me/getidsbot" target="_blank" class="font-mono text-[12px] text-brand hover:underline">@getidsbot</a> to the exact same group chat.</li>
                  <li>As soon as it's added, <span class="font-semibold text-main">@getidsbot</span> replies with the group's info — no need to send a message first.</li>
                  <li>Copy the <span class="font-semibold text-main">"id"</span> value from its reply (Note: group IDs in Telegram always start with a minus sign, like <span class="font-mono text-[12px] text-main">-1001234567890</span>).</li>
                  <li>Paste this ID into the <span class="font-semibold text-main">Telegram Alert Group ID</span> field above and click <span class="font-semibold text-main">Save</span>.</li>
                  <li>Remove <span class="font-semibold text-main">@getidsbot</span> from the group once you have copied the ID, for security and cleanliness.</li>
                </ol>
              </div>
            </div>

            <!-- WhatsApp (not yet built) -->
            <div class="p-4 rounded-xl border border-dashed border-subtle bg-surface-elevated/10 space-y-1.5">
              <div class="flex items-center gap-2 text-xs font-semibold text-muted">
                <i data-lucide="message-circle" class="w-4 h-4"></i> WhatsApp Template Alerts
                <span class="badge badge-subtle text-[12px]">Coming Soon</span>
              </div>
              <p class="text-[12px] text-muted">Requires a Meta-approved message template — full setup guide and configuration will land here once ready.</p>
            </div>
          </div>
        </div>
      `;

      document.getElementById('alert-recipients-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const emails = emailReady ? document.getElementById('alert-recipient-emails').value.split(',').map(s => s.trim()).filter(Boolean) : (recipients.emails || []);
        const phones = smsReady ? document.getElementById('alert-recipient-phones').value.split(',').map(s => s.trim()).filter(Boolean) : (recipients.phones || []);

        try {
          const res = await api('/settings/alerts/recipients', { method: 'PUT', body: JSON.stringify({ emails, phones }) });
          state.alertRecipientsInfo = res;

          if (tgBotReady) {
            const chatId = document.getElementById('alert-telegram-chat-id').value.trim();
            const tgRes = await api('/settings/alerts/telegram', { method: 'PUT', body: JSON.stringify({ chat_id: chatId }) });
            state.telegramAlertsInfo = tgRes;
          }

          showToast('Order alert settings saved successfully', 'success');
          renderAlertsTab();
        } catch (err) {
          showToast(err.message || 'Failed to save order alert settings', 'error');
        }
      });

      document.getElementById('btn-test-tg-alert')?.addEventListener('click', async () => {
        const btn = document.getElementById('btn-test-tg-alert');
        const orig = btn.innerHTML;
        btn.innerHTML = 'Sending...'; btn.disabled = true;
        try {
          const res = await api('/settings/alerts/telegram/test', { method: 'POST' });
          showToast(res.message || 'Test alert sent', 'success');
        } catch (err) {
          showToast(err.message || 'Failed to send test alert', 'error');
        } finally {
          btn.innerHTML = orig; btn.disabled = false;
        }
      });

      if (window.lucide) lucide.createIcons();
    }

    // ------------------------------------------------------------------
    // Messaging Channels (unchanged from prior settings.js — moved as-is)
    // ------------------------------------------------------------------
    function renderChannelsTab() {
      const el = document.getElementById('integrations-tab-content');
      const ch = state.channelsInfo || { whatsapp: {}, telegram: {} };
      const wa = ch.whatsapp || {};
      const tg = ch.telegram || {};
      const domain = ch.domain || window.location.origin;
      const sms = state.smsInfo || {};
      const smsProvider = sms.provider || 'none';
      const smsCfg = sms.config || {};

      const subTabs = [
        { id: 'telegram', label: 'Telegram', icon: 'send', badge: tg.webhook_secret_configured ? 'badge-sky' : 'badge-subtle', badgeLabel: tg.webhook_secret_configured ? 'Secret Token Active' : 'Auto-Generated' },
        { id: 'whatsapp', label: 'Whatsapp', icon: 'message-circle', badge: wa.app_secret_configured ? 'badge-emerald' : 'badge-subtle', badgeLabel: wa.app_secret_configured ? 'App Secret Configured' : 'Open / Unverified' },
        { id: 'sms', label: 'SMS', icon: 'message-square-text', badge: sms.configured ? 'badge-emerald' : 'badge-subtle', badgeLabel: sms.configured ? 'Active' : 'Not Configured' },
      ];
      const activeSubTab = state.channelsSubTab && subTabs.some(t => t.id === state.channelsSubTab) ? state.channelsSubTab : 'telegram';

      el.innerHTML = `
        <div class="card space-y-6">
          <div>
            <h3 class="font-bold text-base text-main">Messaging Channels</h3>
            <p class="text-xs text-muted mt-0.5">Configure global webhook verification tokens, channel secrets, and test live webhooks</p>
          </div>

          <div class="flex gap-1 p-1 bg-sidebar rounded-xl border border-subtle overflow-x-auto">
            ${subTabs.map(t => `
              <button type="button" class="channels-sub-tab flex items-center gap-2 px-3.5 py-2 rounded-lg text-[13px] font-medium transition-colors whitespace-nowrap ${activeSubTab === t.id ? 'bg-surface-hover text-main' : 'text-muted hover:bg-surface-hover hover:text-main'}" data-subtab="${t.id}">
                <i data-lucide="${t.icon}" class="w-3.5 h-3.5 flex-shrink-0"></i>
                <span>${t.label}</span>
                <span class="badge ${t.badge} text-[10px] !py-0 !px-1.5">${t.badgeLabel}</span>
              </button>
            `).join('')}
          </div>

          <form id="channels-settings-form" class="space-y-6">
            <!-- WhatsApp Cloud API -->
            <div class="p-4 rounded-xl border border-subtle bg-surface-elevated/20 space-y-4 channels-subtab-panel" data-subtab-panel="whatsapp" ${activeSubTab === 'whatsapp' ? '' : 'hidden'}>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2 text-xs font-semibold text-emerald">
                  <i data-lucide="message-circle" class="w-4 h-4"></i> WhatsApp Cloud API
                </div>
                <span class="badge ${wa.app_secret_configured ? 'badge-emerald' : 'badge-subtle'} text-[12px]">
                  ${wa.app_secret_configured ? 'App Secret Configured' : 'Open / Unverified'}
                </span>
              </div>

              <div class="space-y-3">
                <div class="form-group">
                  <label class="form-label flex items-center justify-between">
                    <span>Webhook Callback URL</span>
                    <span class="text-[12px] text-muted normal-case font-normal">Paste in Meta WhatsApp Configuration</span>
                  </label>
                  <div class="code-preview text-xs">
                    <span class="truncate">${escapeHtml(wa.webhook_url || `${domain}/api/v1/webhooks/whatsapp`)}</span>
                    <button type="button" class="btn btn-secondary btn-sm flex-shrink-0" onclick="navigator.clipboard.writeText('${wa.webhook_url || `${domain}/api/v1/webhooks/whatsapp`}'); showToast('WhatsApp Webhook URL copied!', 'success');">Copy</button>
                  </div>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div class="form-group">
                    <label class="form-label flex items-center justify-between">
                      <span>Webhook Verify Token</span>
                      <button type="button" id="btn-rotate-wa-token" class="text-[12px] text-brand hover:underline flex items-center gap-1 cursor-pointer" title="Generate fresh random verify token">
                        <i data-lucide="refresh-cw" class="w-3 h-3"></i> Generate New
                      </button>
                    </label>
                    <div class="relative flex items-center">
                      <button type="button" id="btn-rotate-wa-token-icon" class="absolute left-2.5 text-muted hover:text-brand transition-colors p-1" title="Rotate verify token">
                        <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
                      </button>
                      <input type="text" id="wa-verify-token" class="form-control text-xs font-mono pl-9 pr-14" value="${escapeHtml(wa.verify_token || 'commb_webhook_verification_token_secret')}" placeholder="commb_webhook_verify_token" />
                      <button type="button" class="btn btn-ghost btn-sm absolute right-1.5 text-xs text-muted hover:text-main px-2 py-0.5" onclick="navigator.clipboard.writeText(document.getElementById('wa-verify-token').value); showToast('Verify token copied!', 'success');">Copy</button>
                    </div>
                  </div>

                  <div class="form-group">
                    <label class="form-label flex items-center justify-between">
                      <span>Meta App Secret (HMAC)</span>
                      ${wa.app_secret_configured ? `<span class="badge badge-emerald text-[12px] font-mono">Configured: ${escapeHtml(wa.app_secret_masked)}</span>` : ''}
                    </label>
                    <div class="relative flex items-center">
                      <input type="password" id="wa-app-secret" class="form-control pr-10 font-mono text-xs" placeholder="${wa.app_secret_configured ? 'Leave blank to keep current secret' : 'Meta App Secret for HMAC-SHA256'}" autocomplete="new-password" />
                      <button type="button" class="password-toggle-btn absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-main focus:outline-none p-1" data-target="wa-app-secret" title="Toggle secret visibility">
                        <i data-lucide="eye" class="w-4 h-4"></i>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- WhatsApp Guide -->
              <div class="p-4 rounded-xl border border-subtle bg-surface space-y-2.5 text-xs">
                <div class="font-bold text-main flex items-center gap-1.5 text-emerald">
                  <i data-lucide="check-circle-2" class="w-4 h-4"></i> WhatsApp Setup Instructions
                </div>
                <ol class="list-decimal list-inside space-y-1.5 text-muted leading-relaxed">
                  <li>Open your <span class="font-semibold text-main">Meta Developer App Dashboard</span>.</li>
                  <li>Go to <span class="font-semibold text-main">WhatsApp &rarr; Configuration</span>.</li>
                  <li>In <span class="font-semibold text-main">Webhook</span>, click <span class="font-semibold text-main">Edit</span>.</li>
                  <li>Paste the <span class="font-mono text-[12px] text-main">Webhook Callback URL</span> and <span class="font-mono text-[12px] text-main">Verify Token</span> above.</li>
                  <li>Click <span class="font-semibold text-main">Verify and Save</span>, then subscribe to the <code class="px-1 py-0.5 rounded bg-surface-elevated border border-subtle text-brand font-mono">messages</code> field.</li>
                </ol>
              </div>

              <div class="flex justify-end pt-2 border-t border-subtle">
                <button type="submit" class="btn btn-primary" id="btn-save-channels-whatsapp">Save WhatsApp Settings</button>
              </div>
            </div>

            <!-- Telegram Bot API -->
            <div class="p-4 rounded-xl border border-subtle bg-surface-elevated/20 space-y-4 channels-subtab-panel" data-subtab-panel="telegram" ${activeSubTab === 'telegram' ? '' : 'hidden'}>
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2 text-xs font-semibold text-sky">
                  <i data-lucide="send" class="w-4 h-4"></i> Telegram Bot API
                </div>
                <span class="badge ${tg.webhook_secret_configured ? 'badge-sky' : 'badge-subtle'} text-[12px]">
                  ${tg.webhook_secret_configured ? 'Secret Token Active' : 'Auto-Generated'}
                </span>
              </div>

              <div class="space-y-3">
                <div class="form-group">
                  <label class="form-label flex items-center justify-between">
                    <span>Webhook Callback URL</span>
                    <span class="text-[12px] text-muted normal-case font-normal">Registered automatically via Telegram API</span>
                  </label>
                  <div class="code-preview text-xs">
                    <span class="truncate">${escapeHtml(tg.webhook_url || `${domain}/api/v1/webhooks/telegram`)}</span>
                    <button type="button" class="btn btn-secondary btn-sm flex-shrink-0" onclick="navigator.clipboard.writeText('${tg.webhook_url || `${domain}/api/v1/webhooks/telegram`}'); showToast('Telegram Webhook URL copied!', 'success');">Copy</button>
                  </div>
                </div>

                <div class="form-group">
                  <label class="form-label flex items-center justify-between">
                    <span>Webhook Secret Token (X-Telegram-Bot-Api-Secret-Token)</span>
                    <button type="button" id="btn-rotate-tg-token" class="text-[12px] text-brand hover:underline flex items-center gap-1 cursor-pointer" title="Generate fresh secret token">
                      <i data-lucide="refresh-cw" class="w-3 h-3"></i> Generate New
                    </button>
                  </label>
                  <div class="relative flex items-center">
                    <button type="button" id="btn-rotate-tg-token-icon" class="absolute left-2.5 text-muted hover:text-brand transition-colors p-1" title="Rotate secret token">
                      <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
                    </button>
                    <input type="password" id="tg-webhook-secret" class="form-control pr-20 pl-9 font-mono text-xs" value="${escapeHtml(tg.webhook_secret || '')}" placeholder="whsec_••••••••••••" autocomplete="new-password" />
                    <div class="absolute right-2 flex items-center gap-1">
                      <button type="button" class="password-toggle-btn text-muted hover:text-main focus:outline-none p-1" data-target="tg-webhook-secret" title="Toggle secret visibility">
                        <i data-lucide="eye" class="w-4 h-4"></i>
                      </button>
                      <button type="button" class="btn btn-ghost btn-sm text-xs text-muted hover:text-main px-2 py-0.5" onclick="navigator.clipboard.writeText(document.getElementById('tg-webhook-secret').value); showToast('Secret token copied!', 'success');">Copy</button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Telegram Tester -->
              <div class="p-4 rounded-xl border border-subtle bg-surface space-y-3 text-xs">
                <div class="font-bold text-main flex items-center gap-1.5 text-sky">
                  <i data-lucide="zap" class="w-4 h-4"></i> Telegram Webhook Live Tester
                </div>
                <p class="text-muted leading-relaxed">
                  Once an agent has a Telegram Bot Token, the webhook is registered automatically. You can also test or register it directly here:
                </p>
                <div class="space-y-2">
                  <div class="flex gap-2">
                    <input type="text" id="tg-test-token" class="form-control text-xs font-mono flex-1" placeholder="123456789:ABCdefGHIjklMNOpqr..." />
                    <button type="button" id="btn-test-tg-webhook" class="btn btn-secondary text-xs flex-shrink-0 flex items-center gap-1.5">
                      <i data-lucide="zap" class="w-3.5 h-3.5 text-amber-500"></i>
                      <span>Test & Set</span>
                    </button>
                  </div>
                  <div id="tg-test-result" class="hidden text-xs p-2.5 rounded-lg"></div>
                </div>

                <div class="pt-2 border-t border-subtle space-y-2">
                  <p class="text-muted leading-relaxed">
                    Running more than one agent with its own bot? Re-sync so each agent's webhook is scoped to it —
                    otherwise inbound messages and inline search can all be handled by the first agent.
                  </p>
                  <button type="button" id="btn-resync-tg-webhooks" class="btn btn-secondary text-xs flex items-center gap-1.5">
                    <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
                    <span>Re-sync all agent webhooks</span>
                  </button>
                  <div id="tg-resync-result" class="hidden text-xs p-2.5 rounded-lg"></div>
                </div>
              </div>

              <div class="flex justify-end pt-2 border-t border-subtle">
                <button type="submit" class="btn btn-primary" id="btn-save-channels-telegram">Save Telegram Settings</button>
              </div>
            </div>
          </form>

          <!-- SMS -->
          <div class="p-4 rounded-xl border border-subtle bg-surface-elevated/20 space-y-4 channels-subtab-panel" data-subtab-panel="sms" ${activeSubTab === 'sms' ? '' : 'hidden'}>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2 text-xs font-semibold text-main">
                <i data-lucide="message-square-text" class="w-4 h-4 text-brand"></i> SMS
              </div>
              <span class="badge ${sms.configured ? 'badge-emerald' : 'badge-subtle'} text-[12px]">${sms.configured ? 'Active' : 'Not Configured'}</span>
            </div>
            <p class="text-[12px] text-muted -mt-2">Used for order alerts (Integrations → Order Alerts) once configured here.</p>

            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <label class="flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${smsProvider === 'africastalking' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="sms-provider" value="africastalking" ${smsProvider === 'africastalking' ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchSmsProviderUI('africastalking')" />
                <div>
                  <div class="font-semibold text-sm text-main">Africa's Talking</div>
                  <div class="text-[12px] text-muted mt-0.5">Pan-African SMS API</div>
                </div>
              </label>
              <label class="flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${smsProvider === 'termii' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="sms-provider" value="termii" ${smsProvider === 'termii' ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchSmsProviderUI('termii')" />
                <div>
                  <div class="font-semibold text-sm text-main">Termii</div>
                  <div class="text-[12px] text-muted mt-0.5">Nigerian SMS/OTP API</div>
                </div>
              </label>
              <label class="flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${smsProvider === 'none' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="sms-provider" value="none" ${smsProvider === 'none' ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchSmsProviderUI('none')" />
                <div>
                  <div class="font-semibold text-sm text-main">Disabled</div>
                </div>
              </label>
            </div>

            <form id="sms-settings-form" class="space-y-3">
              <div id="sms-fields-africastalking" class="${smsProvider === 'africastalking' ? '' : 'hidden'} grid grid-cols-2 gap-3 p-3 rounded-lg border border-subtle bg-surface">
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label flex items-center justify-between">
                    <span>API Key</span>
                    ${smsProvider === 'africastalking' && smsCfg.api_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">saved</span>` : ''}
                  </label>
                  <input type="password" id="sms-at-key" class="form-control font-mono text-xs" placeholder="${smsProvider === 'africastalking' && smsCfg.api_key_configured ? '•••••••••• (leave blank to keep)' : 'atsk_...'}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Username</label>
                  <input type="text" id="sms-at-username" class="form-control text-xs" value="${smsProvider === 'africastalking' ? escapeHtml(smsCfg.username || '') : ''}" placeholder="sandbox (or your live username)" />
                </div>
                <div class="form-group col-span-2">
                  <label class="form-label">Sender ID (Optional)</label>
                  <input type="text" id="sms-at-sender" class="form-control text-xs" value="${smsProvider === 'africastalking' ? escapeHtml(smsCfg.sender_id || '') : ''}" placeholder="e.g. your brand's approved short code" />
                </div>
              </div>
              <div id="sms-fields-termii" class="${smsProvider === 'termii' ? '' : 'hidden'} grid grid-cols-2 gap-3 p-3 rounded-lg border border-subtle bg-surface">
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label flex items-center justify-between">
                    <span>API Key</span>
                    ${smsProvider === 'termii' && smsCfg.api_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">saved</span>` : ''}
                  </label>
                  <input type="password" id="sms-termii-key" class="form-control font-mono text-xs" placeholder="${smsProvider === 'termii' && smsCfg.api_key_configured ? '•••••••••• (leave blank to keep)' : 'TL...'}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Sender ID</label>
                  <input type="text" id="sms-termii-sender" class="form-control text-xs" value="${smsProvider === 'termii' ? escapeHtml(smsCfg.sender_id || '') : ''}" placeholder="Your approved sender ID" />
                </div>
              </div>
              <div class="flex items-center justify-between gap-3">
                ${sms.configured ? `
                  <div class="flex items-center gap-2 flex-1">
                    <input type="tel" id="sms-test-to" class="form-control text-xs flex-1" placeholder="+2348012345678" />
                    <button type="button" id="btn-test-sms" class="btn btn-secondary btn-sm flex-shrink-0">Send Test</button>
                  </div>
                ` : '<div></div>'}
                <button type="submit" class="btn btn-primary btn-sm flex-shrink-0">Save SMS Settings</button>
              </div>
            </form>
          </div>
        </div>
      `;

      initPasswordToggles(el);
      if (window.lucide) lucide.createIcons();

      el.querySelectorAll('.channels-sub-tab').forEach((btn) => {
        btn.addEventListener('click', () => {
          state.channelsSubTab = btn.dataset.subtab;
          renderChannelsTab();
        });
      });

      const rotateWa = async () => {
        try {
          const res = await api('/settings/channels/generate-secret', { method: 'POST' });
          if (res?.verify_token) {
            document.getElementById('wa-verify-token').value = res.verify_token;
            showToast('New WhatsApp Verify Token generated. Remember to click Save!', 'success');
          }
        } catch (err) {
          showToast('Failed to generate token: ' + err.message, 'error');
        }
      };
      document.getElementById('btn-rotate-wa-token')?.addEventListener('click', rotateWa);
      document.getElementById('btn-rotate-wa-token-icon')?.addEventListener('click', rotateWa);

      const rotateTg = async () => {
        try {
          const res = await api('/settings/channels/generate-secret', { method: 'POST' });
          if (res?.webhook_secret) {
            document.getElementById('tg-webhook-secret').value = res.webhook_secret;
            showToast('New Telegram Secret Token generated. Remember to click Save!', 'success');
          }
        } catch (err) {
          showToast('Failed to generate secret: ' + err.message, 'error');
        }
      };
      document.getElementById('btn-rotate-tg-token')?.addEventListener('click', rotateTg);
      document.getElementById('btn-rotate-tg-token-icon')?.addEventListener('click', rotateTg);

      document.getElementById('btn-test-tg-webhook')?.addEventListener('click', async () => {
        const tokenInput = document.getElementById('tg-test-token');
        const resultDiv = document.getElementById('tg-test-result');
        const botToken = tokenInput.value.trim();

        if (!botToken) {
          showToast('Please enter a Telegram Bot Token to test.', 'warning');
          return;
        }

        const btn = document.getElementById('btn-test-tg-webhook');
        const orig = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Testing...`;
        if (window.lucide) lucide.createIcons();

        try {
          const res = await api('/settings/channels/telegram/test-webhook', {
            method: 'POST',
            body: JSON.stringify({ bot_token: botToken }),
          });

          resultDiv.classList.remove('hidden', 'bg-emerald/10', 'text-emerald', 'border-emerald/20', 'bg-rose/10', 'text-rose', 'border-rose/20');
          resultDiv.classList.add('border');

          if (res.ok) {
            resultDiv.classList.add('bg-emerald/10', 'text-emerald', 'border-emerald/20');
            resultDiv.innerHTML = `
              <div class="flex items-center gap-1.5 font-bold mb-0.5">
                <i data-lucide="check" class="w-4 h-4"></i> Webhook Set Successfully!
              </div>
              <p class="text-[12px] text-emerald/90 leading-relaxed">${escapeHtml(res.description || 'Webhook URL registered with Telegram Bot API.')}</p>
            `;
          } else {
            resultDiv.classList.add('bg-rose/10', 'text-rose', 'border-rose/20');
            resultDiv.innerHTML = `
              <div class="flex items-center gap-1.5 font-bold mb-0.5">
                <i data-lucide="alert-circle" class="w-4 h-4"></i> Telegram API Error
              </div>
              <p class="text-[12px] text-rose/90 leading-relaxed">${escapeHtml(res.description || 'Failed to register webhook.')}</p>
            `;
          }
          if (window.lucide) lucide.createIcons();
        } catch (err) {
          resultDiv.classList.remove('hidden');
          resultDiv.className = 'text-xs p-2.5 rounded-lg border bg-rose/10 text-rose border-rose/20';
          resultDiv.innerHTML = `
            <div class="flex items-center gap-1.5 font-bold mb-0.5">
              <i data-lucide="alert-circle" class="w-4 h-4"></i> Test Error
            </div>
            <p class="text-[12px]">${escapeHtml(err.message || 'Connection failed')}</p>
          `;
          if (window.lucide) lucide.createIcons();
        } finally {
          btn.disabled = false;
          btn.innerHTML = orig;
          if (window.lucide) lucide.createIcons();
        }
      });

      document.getElementById('btn-resync-tg-webhooks')?.addEventListener('click', async () => {
        const btn = document.getElementById('btn-resync-tg-webhooks');
        const resultDiv = document.getElementById('tg-resync-result');
        const orig = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Re-syncing...`;
        if (window.lucide) lucide.createIcons();

        try {
          const res = await api('/agents/telegram/resync-webhooks', { method: 'POST' });
          const okCount = (res.results || []).filter(r => r.ok).length;
          const failed = (res.results || []).filter(r => !r.ok);
          resultDiv.classList.remove('hidden');
          resultDiv.className = `text-xs p-2.5 rounded-lg border ${failed.length ? 'bg-amber-500/10 text-amber-600 border-amber-500/20' : 'bg-emerald/10 text-emerald border-emerald/20'}`;
          resultDiv.innerHTML = `
            <div class="font-bold mb-0.5">${okCount}/${res.count || 0} agent webhook(s) re-synced${failed.length ? ` — ${failed.length} failed` : ''}</div>
            ${failed.length ? `<p class="text-[12px] leading-relaxed">${failed.map(f => escapeHtml(`${f.name}: ${f.detail || 'error'}`)).join('<br>')}</p>` : ''}
          `;
          if (window.lucide) lucide.createIcons();
          if (okCount) showToast(`${okCount} agent webhook(s) re-synced`, 'success');
        } catch (err) {
          resultDiv.classList.remove('hidden');
          resultDiv.className = 'text-xs p-2.5 rounded-lg border bg-rose/10 text-rose border-rose/20';
          resultDiv.innerHTML = `<p class="text-[12px]">${escapeHtml(err.message || 'Re-sync failed')}</p>`;
        } finally {
          btn.disabled = false;
          btn.innerHTML = orig;
          if (window.lucide) lucide.createIcons();
        }
      });

      document.getElementById('channels-settings-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.submitter || document.getElementById('btn-save-channels-telegram') || document.getElementById('btn-save-channels-whatsapp');
        const orig = btn.innerHTML;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 mr-1 animate-spin"></i> Saving...`;
        btn.disabled = true;
        if (window.lucide) lucide.createIcons();

        const waSecret = document.getElementById('wa-app-secret').value.trim();
        const tgSecret = document.getElementById('tg-webhook-secret').value.trim();

        const payload = {
          whatsapp: { verify_token: document.getElementById('wa-verify-token').value.trim() },
          telegram: {},
        };

        if (waSecret) payload.whatsapp.app_secret = waSecret;
        if (tgSecret) payload.telegram.webhook_secret = tgSecret;

        try {
          const res = await api('/settings/channels', { method: 'PUT', body: JSON.stringify(payload) });
          state.channelsInfo = res;
          showToast('Messaging channels updated successfully', 'success');
          renderChannelsTab();
        } catch (err) {
          showToast(err.message || 'Failed to save channel settings', 'error');
          btn.innerHTML = orig;
          btn.disabled = false;
          if (window.lucide) lucide.createIcons();
        }
      });

      window.switchSmsProviderUI = (provider) => {
        document.getElementById('sms-fields-africastalking')?.classList.toggle('hidden', provider !== 'africastalking');
        document.getElementById('sms-fields-termii')?.classList.toggle('hidden', provider !== 'termii');
        document.querySelectorAll('input[name="sms-provider"]').forEach(inp => {
          const card = inp.closest('label');
          if (card) {
            card.className = inp.value === provider
              ? 'flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all border-brand bg-brand/5 shadow-sm'
              : 'flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all border-subtle bg-surface-elevated/40 hover:bg-surface-hover';
          }
        });
      };

      document.getElementById('sms-settings-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const selected = document.querySelector('input[name="sms-provider"]:checked')?.value || 'none';
        let configPayload = {};
        if (selected === 'africastalking') {
          configPayload = {
            api_key: document.getElementById('sms-at-key').value.trim() || undefined,
            username: document.getElementById('sms-at-username').value.trim(),
            sender_id: document.getElementById('sms-at-sender').value.trim(),
          };
        } else if (selected === 'termii') {
          configPayload = {
            api_key: document.getElementById('sms-termii-key').value.trim() || undefined,
            sender_id: document.getElementById('sms-termii-sender').value.trim(),
          };
        }
        try {
          const res = await api('/settings/sms', { method: 'PUT', body: JSON.stringify({ provider: selected === 'none' ? null : selected, config: configPayload }) });
          state.smsInfo = res;
          showToast('SMS settings saved successfully', 'success');
          renderChannelsTab();
        } catch (err) {
          showToast(err.message || 'Failed to save SMS settings', 'error');
        }
      });

      document.getElementById('btn-test-sms')?.addEventListener('click', async () => {
        const to = document.getElementById('sms-test-to').value.trim();
        if (!to) { showToast('Enter a phone number to test.', 'warning'); return; }
        const btn = document.getElementById('btn-test-sms');
        const orig = btn.innerHTML;
        btn.innerHTML = 'Sending...'; btn.disabled = true;
        try {
          const res = await api('/settings/sms/test', { method: 'POST', body: JSON.stringify({ to_phone: to }) });
          showToast(res.message || 'Test SMS sent', 'success');
        } catch (err) {
          showToast(err.message || 'Failed to send test SMS', 'error');
        } finally {
          btn.innerHTML = orig; btn.disabled = false;
        }
      });
    }

    // ------------------------------------------------------------------
    // Email Delivery (unchanged from prior settings.js — moved as-is)
    // ------------------------------------------------------------------
    function renderEmailTab() {
      const el = document.getElementById('integrations-tab-content');
      const em = state.emailInfo || {};
      const currentProvider = em.provider || 'none';
      const cfg = em.config || {};

      el.innerHTML = `
        <div class="card space-y-6">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-bold text-base text-main">Transactional Email Delivery</h3>
              <p class="text-xs text-muted mt-0.5">Configure an email delivery provider for password resets, order notifications & customer alerts</p>
            </div>
            <span class="badge ${em.configured ? 'badge-emerald' : 'badge-subtle'}">
              ${em.configured ? `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1 animate-pulse"></span> Active: ${escapeHtml(em.provider ? (em.provider.charAt(0).toUpperCase() + em.provider.slice(1)) : '')}` : 'Not Configured'}
            </span>
          </div>

          <div class="space-y-2">
            <label class="form-label text-xs font-semibold text-main">Select Email Provider</label>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3" id="email-provider-cards">
              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${currentProvider === 'resend' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="email-provider" value="resend" ${currentProvider === 'resend' ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchEmailProviderUI('resend')" />
                <div>
                  <div class="flex items-center gap-1.5 font-semibold text-sm text-main">
                    Resend
                    <span class="badge badge-brand text-[12px] py-0 px-1">Recommended</span>
                  </div>
                  <div class="text-[12px] text-muted mt-0.5">3,000 free emails/mo • Modern DX</div>
                </div>
              </label>

              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${currentProvider === 'brevo' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="email-provider" value="brevo" ${currentProvider === 'brevo' ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchEmailProviderUI('brevo')" />
                <div>
                  <div class="flex items-center gap-1.5 font-semibold text-sm text-main">Brevo</div>
                  <div class="text-[12px] text-muted mt-0.5">300 free emails/day (Sendinblue)</div>
                </div>
              </label>

              <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${currentProvider === 'none' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="email-provider" value="none" ${currentProvider === 'none' ? 'checked' : ''} class="mt-1 text-brand focus:ring-brand" onchange="window.switchEmailProviderUI('none')" />
                <div>
                  <div class="font-semibold text-sm text-main">Disabled</div>
                  <div class="text-[12px] text-muted mt-0.5">Email sending turned off</div>
                </div>
              </label>
            </div>
          </div>

          <form id="email-settings-form" class="space-y-4">
            <!-- Resend Fields -->
            <div id="email-fields-resend" class="${currentProvider === 'resend' ? '' : 'hidden'} space-y-4 p-4 rounded-xl border border-subtle bg-surface-elevated/30">
              <div class="flex items-center justify-between">
                <div class="font-semibold text-xs text-main">Resend Configuration</div>
                <a href="https://resend.com/api-keys" target="_blank" class="text-[12px] text-brand hover:underline flex items-center gap-1">
                  Get API Key <i data-lucide="external-link" class="w-3 h-3"></i>
                </a>
              </div>
              <div class="form-group">
                <label class="form-label flex items-center justify-between">
                  <span>API Key</span>
                  ${currentProvider === 'resend' && cfg.api_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">configured (${cfg.api_key_masked})</span>` : ''}
                </label>
                <input type="password" id="resend-api-key" class="form-control font-mono text-xs" placeholder="${currentProvider === 'resend' && cfg.api_key_configured ? '•••••••••••••••• (Leave blank to keep saved key)' : 're_123456789...'}" />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Sender Email (From)</label>
                  <input type="email" id="resend-from-email" class="form-control text-xs" value="${escapeHtml(currentProvider === 'resend' ? (cfg.from_email || '') : '')}" placeholder="noreply@yourdomain.com" />
                  <p class="text-[12px] text-muted mt-1">Must be verified under your Resend Domains.</p>
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Sender Display Name</label>
                  <input type="text" id="resend-from-name" class="form-control text-xs" value="${escapeHtml(currentProvider === 'resend' ? (cfg.from_name || state.business?.name || '') : (state.business?.name || ''))}" placeholder="Acme Support" />
                </div>
              </div>
            </div>

            <!-- Brevo Fields -->
            <div id="email-fields-brevo" class="${currentProvider === 'brevo' ? '' : 'hidden'} space-y-4 p-4 rounded-xl border border-subtle bg-surface-elevated/30">
              <div class="flex items-center justify-between">
                <div class="font-semibold text-xs text-main">Brevo (Sendinblue) Configuration</div>
                <a href="https://app.brevo.com/settings/keys/api" target="_blank" class="text-[12px] text-brand hover:underline flex items-center gap-1">
                  Get v3 API Key <i data-lucide="external-link" class="w-3 h-3"></i>
                </a>
              </div>
              <div class="form-group">
                <label class="form-label flex items-center justify-between">
                  <span>v3 API Key</span>
                  ${currentProvider === 'brevo' && cfg.api_key_configured ? `<span class="badge badge-emerald text-[12px] font-mono lowercase">configured (${cfg.api_key_masked})</span>` : ''}
                </label>
                <input type="password" id="brevo-api-key" class="form-control font-mono text-xs" placeholder="${currentProvider === 'brevo' && cfg.api_key_configured ? '•••••••••••••••• (Leave blank to keep saved key)' : 'xkeysib-...'}" />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Sender Email (From)</label>
                  <input type="email" id="brevo-from-email" class="form-control text-xs" value="${escapeHtml(currentProvider === 'brevo' ? (cfg.from_email || '') : '')}" placeholder="support@yourdomain.com" />
                  <p class="text-[12px] text-muted mt-1">Must be an authorized sender in Brevo.</p>
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Sender Display Name</label>
                  <input type="text" id="brevo-from-name" class="form-control text-xs" value="${escapeHtml(currentProvider === 'brevo' ? (cfg.from_name || state.business?.name || '') : (state.business?.name || ''))}" placeholder="Acme Support" />
                </div>
              </div>
            </div>

            <!-- Disabled State Info -->
            <div id="email-fields-none" class="${currentProvider === 'none' ? '' : 'hidden'} p-4 rounded-xl border border-dashed border-subtle text-center text-xs text-muted">
              Transactional email delivery is disabled. Password reset requests will require manual administrator intervention.
            </div>

            <div class="flex justify-end pt-4 border-t border-subtle">
              <button type="submit" class="btn btn-primary" id="btn-save-email">Save Email Settings</button>
            </div>
          </form>
        </div>

        <!-- Test Email Card -->
        ${em.configured ? `
          <div class="card space-y-4 mt-6">
            <div>
              <h4 class="font-bold text-sm text-main">Send Verification Email</h4>
              <p class="text-xs text-muted mt-0.5">Send a test email to verify your API credentials and sender domain delivery</p>
            </div>
            <form id="email-test-form" class="flex items-center gap-3">
              <input type="email" id="email-test-to" class="form-control text-xs flex-1" required placeholder="admin@example.com" value="${escapeHtml(state.user?.email || '')}" />
              <button type="submit" class="btn btn-secondary btn-sm flex-shrink-0" id="btn-send-test-email">
                <i data-lucide="send" class="w-3.5 h-3.5 mr-1"></i> Send Test Email
              </button>
            </form>
          </div>
        ` : ''}
      `;

      window.switchEmailProviderUI = (provider) => {
        document.getElementById('email-fields-resend')?.classList.toggle('hidden', provider !== 'resend');
        document.getElementById('email-fields-brevo')?.classList.toggle('hidden', provider !== 'brevo');
        document.getElementById('email-fields-none')?.classList.toggle('hidden', provider !== 'none');

        document.querySelectorAll('input[name="email-provider"]').forEach(inp => {
          const card = inp.closest('label');
          if (card) {
            card.className = inp.value === provider
              ? 'flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-brand bg-brand/5 shadow-sm'
              : 'flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-subtle bg-surface-elevated/40 hover:bg-surface-hover';
          }
        });
      };

      document.getElementById('email-settings-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const selected = document.querySelector('input[name="email-provider"]:checked')?.value || 'none';
        let configPayload = {};
        if (selected === 'resend') {
          configPayload = {
            api_key: document.getElementById('resend-api-key').value.trim() || undefined,
            from_email: document.getElementById('resend-from-email').value.trim(),
            from_name: document.getElementById('resend-from-name').value.trim(),
          };
        } else if (selected === 'brevo') {
          configPayload = {
            api_key: document.getElementById('brevo-api-key').value.trim() || undefined,
            from_email: document.getElementById('brevo-from-email').value.trim(),
            from_name: document.getElementById('brevo-from-name').value.trim(),
          };
        }

        try {
          const res = await api('/settings/email', { method: 'PUT', body: JSON.stringify({ provider: selected === 'none' ? null : selected, config: configPayload }) });
          state.emailInfo = res;
          showToast('Email delivery settings saved successfully', 'success');
          renderEmailTab();
        } catch (err) {
          showToast(err.message || 'Failed to save email settings', 'error');
        }
      });

      const testForm = document.getElementById('email-test-form');
      if (testForm) {
        testForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          const btn = document.getElementById('btn-send-test-email');
          const original = btn.innerHTML;
          btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin mr-1"></i> Sending...`;
          btn.disabled = true;
          if (window.lucide) lucide.createIcons();

          try {
            const to = document.getElementById('email-test-to').value.trim();
            const res = await api('/settings/email/test', { method: 'POST', body: JSON.stringify({ to_email: to }) });
            showToast(res.message || 'Test email sent successfully', 'success');
          } catch (err) {
            showToast(err.message || 'Failed to send test email', 'error');
          } finally {
            btn.innerHTML = original;
            btn.disabled = false;
            if (window.lucide) lucide.createIcons();
          }
        });
      }

      initAllCustomSelects(el);
      if (window.lucide) lucide.createIcons();
    }

    // ------------------------------------------------------------------
    // Storage & Media (unchanged from prior settings.js — moved as-is)
    // ------------------------------------------------------------------
    function renderStorageTab() {
      const el = document.getElementById('integrations-tab-content');
      const st = state.storageInfo || {};
      const currentProvider = st.provider || 'none';
      const conf = st.config || {};

      el.innerHTML = `
        <div class="card space-y-6">
          <div class="flex items-start justify-between">
            <div>
              <h3 class="font-bold text-base text-main flex items-center gap-2">
                <i data-lucide="hard-drive" class="w-5 h-5 text-brand"></i>
                Media & File Storage Settings
              </h3>
              <p class="text-xs text-muted mt-0.5">
                Connect your cloud bucket or image CDN to enable file uploads for product photos, store logos, and agent media.
              </p>
            </div>
            <span class="badge ${st.configured ? 'badge-emerald' : 'badge-amber'}">
              ${st.configured ? `Active (${st.provider})` : 'Not Configured'}
            </span>
          </div>

          <div class="space-y-2">
            <label class="form-label">Storage Provider</label>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <label class="flex items-center gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${currentProvider === 'cloudinary' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="storage-provider" value="cloudinary" ${currentProvider === 'cloudinary' ? 'checked' : ''} class="text-brand focus:ring-brand" onchange="window.switchStorageProviderUI('cloudinary')" />
                <div>
                  <div class="font-semibold text-sm text-main">Cloudinary</div>
                  <div class="text-[12px] text-muted">Image CDN & Optimization</div>
                </div>
              </label>

              <label class="flex items-center gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${currentProvider === 'cloudflare_r2' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="storage-provider" value="cloudflare_r2" ${currentProvider === 'cloudflare_r2' ? 'checked' : ''} class="text-brand focus:ring-brand" onchange="window.switchStorageProviderUI('cloudflare_r2')" />
                <div>
                  <div class="font-semibold text-sm text-main">Cloudflare R2</div>
                  <div class="text-[12px] text-muted">Zero Egress S3 Bucket</div>
                </div>
              </label>

              <label class="flex items-center gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${currentProvider === 'none' ? 'border-brand bg-brand/5 shadow-sm' : 'border-subtle bg-surface-elevated/40 hover:bg-surface-hover'}">
                <input type="radio" name="storage-provider" value="none" ${currentProvider === 'none' ? 'checked' : ''} class="text-brand focus:ring-brand" onchange="window.switchStorageProviderUI('none')" />
                <div>
                  <div class="font-semibold text-sm text-main">Disabled</div>
                  <div class="text-[12px] text-muted">URL Links Only</div>
                </div>
              </label>
            </div>
          </div>

          <form id="storage-settings-form" class="space-y-4">
            <!-- Cloudinary Fields -->
            <div id="storage-fields-cloudinary" class="${currentProvider === 'cloudinary' ? '' : 'hidden'} space-y-4 p-4 rounded-xl border border-subtle bg-surface-elevated/30">
              <div class="font-semibold text-xs text-main">Cloudinary Credentials</div>
              <div class="grid grid-cols-2 gap-4">
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Cloud Name</label>
                  <input type="text" id="cld-name" class="form-control" placeholder="e.g. dxyz123" value="${escapeHtml(conf.cloud_name || '')}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">API Key</label>
                  <input type="text" id="cld-key" class="form-control" placeholder="123456789012345" value="${escapeHtml(conf.api_key || '')}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">API Secret ${conf.api_secret_masked ? '<span class="text-emerald text-[12px]">(Saved)</span>' : ''}</label>
                  <input type="password" id="cld-secret" class="form-control" placeholder="${conf.api_secret_masked ? '••••••••••••••••••••••••••••' : 'Cloudinary API Secret'}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Upload Folder</label>
                  <input type="text" id="cld-folder" class="form-control" placeholder="commb_uploads" value="${escapeHtml(conf.folder || 'commb_uploads')}" />
                </div>
              </div>
            </div>

            <!-- Cloudflare R2 Fields -->
            <div id="storage-fields-cloudflare_r2" class="${currentProvider === 'cloudflare_r2' ? '' : 'hidden'} space-y-4 p-4 rounded-xl border border-subtle bg-surface-elevated/30">
              <div class="font-semibold text-xs text-main">Cloudflare R2 Bucket Details</div>
              <div class="grid grid-cols-2 gap-4">
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Account ID</label>
                  <input type="text" id="r2-account" class="form-control" placeholder="Cloudflare Account ID hex" value="${escapeHtml(conf.account_id || '')}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Bucket Name</label>
                  <input type="text" id="r2-bucket" class="form-control" placeholder="my-commb-media" value="${escapeHtml(conf.bucket_name || '')}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Access Key ID</label>
                  <input type="text" id="r2-key" class="form-control" placeholder="R2 Token Access Key" value="${escapeHtml(conf.access_key_id || '')}" />
                </div>
                <div class="form-group col-span-2 sm:col-span-1">
                  <label class="form-label">Secret Access Key ${conf.secret_access_key_masked ? '<span class="text-emerald text-[12px]">(Saved)</span>' : ''}</label>
                  <input type="password" id="r2-secret" class="form-control" placeholder="${conf.secret_access_key_masked ? '••••••••••••••••••••••••••••' : 'R2 Secret Access Key'}" />
                </div>
                <div class="form-group col-span-2">
                  <label class="form-label">Public Base URL / Custom Domain (Optional)</label>
                  <input type="url" id="r2-public-url" class="form-control" placeholder="https://pub-xxxxxx.r2.dev or https://media.mybrand.com" value="${escapeHtml(conf.public_url || '')}" />
                </div>
              </div>
            </div>

            <div class="flex items-center justify-between pt-4 border-t border-subtle">
              <div id="storage-test-status" class="text-xs text-muted"></div>
              <button type="submit" class="btn btn-primary" id="btn-save-storage">Save Storage Configuration</button>
            </div>
          </form>

          <!-- Upload Sandbox Test -->
          ${st.configured ? `
            <div class="p-4 rounded-xl border border-subtle bg-surface-elevated/20 space-y-3">
              <div class="font-semibold text-xs text-main flex items-center gap-2">
                <i data-lucide="test-tube" class="w-4 h-4 text-brand"></i>
                Test Live Upload
              </div>
              <div class="flex items-center gap-3">
                <label class="btn btn-secondary btn-sm cursor-pointer text-xs">
                  <i data-lucide="upload" class="w-3.5 h-3.5 text-brand"></i> Choose Test File
                  <input type="file" id="sandbox-test-file" class="hidden" accept="image/*" />
                </label>
                <div id="sandbox-test-output" class="text-xs text-muted truncate flex-1"></div>
              </div>
            </div>
          ` : ''}
        </div>
      `;

      window.switchStorageProviderUI = (provider) => {
        document.getElementById('storage-fields-cloudinary')?.classList.toggle('hidden', provider !== 'cloudinary');
        document.getElementById('storage-fields-cloudflare_r2')?.classList.toggle('hidden', provider !== 'cloudflare_r2');

        document.querySelectorAll('input[name="storage-provider"]').forEach(inp => {
          const card = inp.closest('label');
          if (card) {
            card.className = inp.value === provider
              ? 'flex items-center gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-brand bg-brand/5 shadow-sm'
              : 'flex items-center gap-3 p-3.5 rounded-xl border cursor-pointer transition-all border-subtle bg-surface-elevated/40 hover:bg-surface-hover';
          }
        });
      };

      document.getElementById('storage-settings-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const selected = document.querySelector('input[name="storage-provider"]:checked')?.value || 'none';

        let configPayload = {};
        if (selected === 'cloudinary') {
          configPayload = {
            cloud_name: document.getElementById('cld-name').value.trim(),
            api_key: document.getElementById('cld-key').value.trim(),
            api_secret: document.getElementById('cld-secret').value.trim(),
            folder: document.getElementById('cld-folder').value.trim() || 'commb_uploads',
          };
        } else if (selected === 'cloudflare_r2') {
          configPayload = {
            account_id: document.getElementById('r2-account').value.trim(),
            bucket_name: document.getElementById('r2-bucket').value.trim(),
            access_key_id: document.getElementById('r2-key').value.trim(),
            secret_access_key: document.getElementById('r2-secret').value.trim(),
            public_url: document.getElementById('r2-public-url').value.trim(),
          };
        }

        try {
          const res = await api('/settings/storage', {
            method: 'PUT',
            body: JSON.stringify({ provider: selected === 'none' ? null : selected, config: configPayload })
          });
          state.storageInfo = res;
          showToast('Storage settings saved successfully', 'success');
          renderStorageTab();
        } catch (err) {
          showToast(err.message || 'Failed to save storage settings', 'error');
        }
      });

      const sandboxFile = document.getElementById('sandbox-test-file');
      if (sandboxFile) {
        sandboxFile.addEventListener('change', async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          const out = document.getElementById('sandbox-test-output');
          if (out) out.innerHTML = `<span class="text-brand flex items-center gap-1.5"><i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Uploading test file...</span>`;
          if (window.lucide) lucide.createIcons();

          try {
            const url = await uploadMediaFile(file);
            if (out) {
              out.innerHTML = `
                <span class="text-emerald font-medium">Uploaded: </span>
                <a href="${url}" target="_blank" class="font-mono text-brand underline truncate max-w-sm">${url}</a>
              `;
            }
            showToast('Test upload succeeded!', 'success');
          } catch (err) {
            if (out) out.innerHTML = `<span class="text-rose">${escapeHtml(err.message || 'Upload failed')}</span>`;
          }
        });
      }

      if (window.lucide) lucide.createIcons();
    }

    function switchTab(tabId) {
      state.integrationsTab = tabId;
      document.querySelectorAll('.integrations-tab').forEach((btn) => {
        const isActive = btn.dataset.tab === tabId;
        // Matches the sidebar's own active-menu-item background (see
        // main.js) — bg-surface-hover/text-main, not the old bg-brand/10
        // tint. This toggle previously still referenced that old class
        // pair, so a tab click never visually updated (only a full page
        // reload did, since the initial render's template string already
        // used the new classes but this click handler didn't).
        btn.classList.toggle('bg-surface-hover', isActive);
        btn.classList.toggle('text-main', isActive);
        btn.classList.toggle('text-muted', !isActive);
      });
      if (tabId === 'store-connections') renderStoreConnectionsTab();
      else if (tabId === 'payments') renderPaymentsTab();
      else if (tabId === 'channels') renderChannelsTab();
      else if (tabId === 'alerts') renderAlertsTab();
      else if (tabId === 'email') renderEmailTab();
      else renderStorageTab();
    }

    document.querySelectorAll('.integrations-tab').forEach((btn) => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    switchTab(activeTab);

    if (window.lucide) lucide.createIcons();
  } catch (err) {
    container.innerHTML = `<div class="p-8 text-center text-rose">Failed to load integrations: ${escapeHtml(err.message)}</div>`;
  }
}
