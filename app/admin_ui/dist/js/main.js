import { state, applyTheme } from './state.js';
import { api } from './api.js';
import { navigate } from './router.js';
import { showToast, escapeHtml } from './utils.js';

// Import Pages
import { renderLoginView } from './pages/login.js';
import { renderForgotPasswordView } from './pages/forgot-password.js';
import { renderResetPasswordView } from './pages/reset-password.js';
import { renderSetupView } from './pages/setup.js';
import { loadOverviewPage } from './pages/overview.js';
import { loadAgentsPage } from './pages/agents.js';
import { loadCustomersPage } from './pages/customers.js';
import { loadSettingsPage } from './pages/settings.js';
import { loadIntegrationsPage } from './pages/integrations.js';
import { loadGroupsPage } from './pages/groups.js';
import { loadKnowledgePage } from './pages/knowledge.js';
import { loadCatalogPage } from './pages/catalog.js';
import { loadUsersPage } from './pages/users.js';
import { loadOrdersPage } from './pages/orders.js';
import { loadConversationsPage } from './pages/conversations.js';
import { loadReportsPage } from './pages/reports.js';

export function updateAppTitle(pageName, isPublic = false) {
  if (isPublic) {
    document.title = pageName ? `AI Commerce Bots | ${pageName}` : 'AI Commerce Bots | Omnichannel AI Support Platform';
  } else {
    document.title = pageName ? `${pageName} | CommB` : 'CommB Studio';
  }
}

window.updateAppTitle = updateAppTitle;
window.showToast = showToast;
window.escapeHtml = escapeHtml;
window.api = api;
window.navigate = navigate;

// Initialize Optional Host PostHog Analytics
async function initHostPostHog() {
  try {
    const analytics = await api('/settings/analytics');
    if (analytics?.posthog_api_key && !window.posthog) {
      const apiKey = analytics.posthog_api_key;
      const apiHost = analytics.posthog_host || 'https://us.i.posthog.com';
      
      // PostHog snippet loader
      (function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.async=!0,p.src=s.api_host+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="capture identify alias people.set people.set_once set_config register register_once unregister opt_out_capturing has_opted_out_capturing opt_in_capturing reset isFeatureEnabled onFeatureFlags getFeatureFlag getFeatureFlagPayload reloadFeatureFlags group updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getActiveMatchingSurveys getSurveys onSessionId".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)})(document,window.posthog||[]);
      window.posthog.init(apiKey, { api_host: apiHost, person_profiles: 'identified_only' });
      console.log("[CommB] Host PostHog initialized.");
    }
  } catch (e) {
    // PostHog setup silently skips on failure
  }
}

export async function initApp() {
  const urlParams = new URLSearchParams(window.location.search);
  const ssoToken = urlParams.get('token');
  if (state.route === '/_/admin/sso' && ssoToken) {
    try {
      const res = await fetch('/api/v1/auth/sso', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: ssoToken })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'SSO failed');
      
      localStorage.setItem('commb_admin_token', data.access_token);
      showToast('Logged in via AgentOS', 'success');
      navigate('/_/admin/overview');
      return;
    } catch (err) {
      showToast('SSO Login Failed: ' + err.message, 'error');
      navigate('/_/admin/login');
      return;
    }
  }

  try {
    const sys = await api('/system/health-summary');
    if (sys?.version) {
      state.appVersion = sys.version;
      state.appName = sys.app_name || 'CommB (AI Commerce Bots)';
      state.instanceId = sys.instance_id || null;
    }
  } catch (e) {
    try {
      const sysVer = await api('/system/version');
      if (sysVer?.version) state.appVersion = sysVer.version;
    } catch {}
  }

  try {
    const status = await api('/setup/status');
    if (status.business?.name) {
      state.business = status.business;
    }
    if (!status.initialized) {
      if (state.route !== '/_/admin/setup') {
        navigate('/_/admin/setup');
        return;
      }
    }
  } catch (e) {
    console.error("Setup check error:", e);
  }

  const storedToken = localStorage.getItem('commb_admin_token');
  if (storedToken) {
    try {
      const authData = await api('/auth/me');
      state.user = authData;
      state.business = authData.business;
      initHostPostHog();
    } catch {
      localStorage.removeItem('commb_admin_token');
      state.user = null;
      state.business = null;
    }
  }

  const publicRoutes = ['/_/admin/setup', '/_/admin/login', '/_/admin/forgot-password', '/_/admin/reset-password'];
  if (!state.user && !publicRoutes.includes(state.route)) {
    navigate('/_/admin/login');
    return;
  }

  renderApp();
  checkPeriodicSponsorPopup();
}

// 7-day periodic sponsor reminder banner
function checkPeriodicSponsorPopup() {
  const lastDismissed = localStorage.getItem('commb_sponsor_dismissed_at');
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
  if (!lastDismissed || (Date.now() - Number(lastDismissed) > sevenDaysMs)) {
    setTimeout(showWeeklySponsorBanner, 3000);
  }
}

function showWeeklySponsorBanner() {
  if (document.getElementById('weekly-sponsor-banner')) return;
  if (!state.user) return; // Only show inside logged-in dashboard

  const banner = document.createElement('div');
  banner.id = 'weekly-sponsor-banner';
  banner.className = 'fixed bottom-4 right-4 z-40 max-w-sm w-full bg-slate-900/95 border border-sky-500/30 dark:border-white/10 rounded-2xl p-4 shadow-2xl backdrop-blur-md animate-scale-in text-slate-100';
  banner.innerHTML = `
    <div class="flex items-start gap-3">
      <div class="w-8 h-8 rounded-xl bg-pink-500/10 text-pink-400 border border-pink-500/20 flex items-center justify-center text-base flex-shrink-0">
        ❤️
      </div>
      <div class="space-y-1 min-w-0 flex-1">
        <div class="flex items-center justify-between">
          <h4 class="text-xs font-bold text-white">Loving CommB?</h4>
          <button onclick="dismissSponsorBanner()" class="text-slate-400 hover:text-white p-0.5 rounded transition-colors" title="Remind in 7 days">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <p class="text-[12px] text-slate-300 leading-relaxed">
          Support ongoing open-source development by starring our repo on GitHub or sponsoring us!
        </p>
        <div class="flex items-center gap-2 pt-2">
          <a href="https://github.com/samakins/commb" target="_blank" rel="noreferrer" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[12px] font-semibold flex items-center gap-1 transition-all">
            ⭐ Star on GitHub
          </a>
          <a href="https://github.com/sponsors/samakins" target="_blank" rel="noreferrer" class="px-2.5 py-1 rounded-lg bg-pink-600 hover:bg-pink-500 text-white text-[12px] font-semibold flex items-center gap-1 transition-all">
            ❤️ Sponsor
          </a>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(banner);
}

window.dismissSponsorBanner = function() {
  const banner = document.getElementById('weekly-sponsor-banner');
  if (banner) banner.remove();
  localStorage.setItem('commb_sponsor_dismissed_at', String(Date.now()));
};

export function renderApp() {
  const app = document.getElementById('app');
  const path = state.route.replace(/\/$/, '') || '/_/admin/overview';

  if (path === '/_/admin/setup') {
    updateAppTitle('First-Run Setup', true);
    renderSetupView(app);
  } else if (path === '/_/admin/login') {
    updateAppTitle('Admin Login', true);
    renderLoginView(app);
  } else if (path === '/_/admin/forgot-password') {
    updateAppTitle('Forgot Password', true);
    renderForgotPasswordView(app);
  } else if (path === '/_/admin/reset-password') {
    updateAppTitle('Reset Password', true);
    renderResetPasswordView(app);
  } else {
    renderAdminShell(app, path);
  }

  if (window.lucide) lucide.createIcons();
}

function updateThemeUI(theme) {
  const lightBtn = document.getElementById('header-theme-btn-light');
  const darkBtn = document.getElementById('header-theme-btn-dark');
  if (lightBtn && darkBtn) {
    if (theme === 'light') {
      lightBtn.className = 'p-1.5 rounded-md transition-colors bg-surface text-brand font-semibold shadow-xs';
      darkBtn.className = 'p-1.5 rounded-md transition-colors text-muted hover:text-main';
    } else {
      lightBtn.className = 'p-1.5 rounded-md transition-colors text-muted hover:text-main';
      darkBtn.className = 'p-1.5 rounded-md transition-colors bg-surface text-brand font-semibold shadow-xs';
    }
  }
}

function renderAdminShell(container, currentPath) {
  const user = state.user || {};
  const isAdmin = ['admin', 'super_admin'].includes(user.role);

  // Route protection: redirect unauthorized roles away from admin-only pages
  if ((currentPath === '/_/admin/users' || currentPath === '/_/admin/settings' || currentPath === '/_/admin/integrations') && !isAdmin) {
    showToast('Access restricted to administrators.', 'warning');
    navigate('/_/admin/overview');
    return;
  }

  // Structured Navigation Categories
  const navSections = [
    {
      title: 'OPERATIONS',
      items: [
        { label: 'Overview', path: '/_/admin/overview', icon: 'layout-dashboard' },
        { label: 'Conversations', path: '/_/admin/conversations', icon: 'message-square' },
        { label: 'Customers', path: '/_/admin/customers', icon: 'users' },
      ]
    },
    {
      title: 'COMMERCE',
      items: [
        { label: 'Products Catalog', path: '/_/admin/catalog', icon: 'shopping-bag' },
        { label: 'Orders & Payments', path: '/_/admin/orders', icon: 'shopping-cart' },
        { label: 'Reports & Analytics', path: '/_/admin/reports', icon: 'bar-chart-3' },
      ]
    },
    {
      title: 'AI STUDIO',
      items: [
        { label: 'AI Agents Studio', path: '/_/admin/agents', icon: 'bot' },
        { label: 'Access Groups', path: '/_/admin/groups', icon: 'shield-check' },
        { label: 'Knowledge Base', path: '/_/admin/knowledge', icon: 'book-open' },
      ]
    },
    {
      title: 'CONFIGURATION',
      items: [
        { label: 'Integrations', path: '/_/admin/integrations', icon: 'plug-zap', adminOnly: true },
        { label: 'Users', path: '/_/admin/users', icon: 'user-check', adminOnly: true },
        { label: 'Settings', path: '/_/admin/settings', icon: 'settings', adminOnly: true },
      ]
    }
  ];

  // Find active item label for header and document title
  let activeLabel = 'Overview';
  for (const sec of navSections) {
    for (const it of sec.items) {
      if (it.path === currentPath) activeLabel = it.label;
    }
  }
  updateAppTitle(activeLabel, false);

  const business = state.business || state.user?.business || {};
  const businessName = business.name || 'CommB Studio';
  const logoUrl = business.logo_url;
  const initial = (businessName.trim().charAt(0) || 'A').toUpperCase();

  const logoMarkup = logoUrl ? `
    <div class="w-8 h-8 rounded-lg bg-surface-elevated border border-subtle flex items-center justify-center overflow-hidden flex-shrink-0 shadow-sm">
      <img src="${escapeHtml(logoUrl)}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-8 h-8 rounded-lg bg-brand flex items-center justify-center text-white font-bold text-sm\\'>${escapeHtml(initial)}</div>';" />
    </div>
  ` : `
    <div class="w-8 h-8 rounded-lg bg-brand flex items-center justify-center text-white font-bold text-sm flex-shrink-0 shadow-sm">
      ${escapeHtml(initial)}
    </div>
  `;

  const roleBadgeClass = isAdmin 
    ? 'badge-emerald' 
    : user.role === 'operator' 
      ? 'badge-sky' 
      : 'badge-subtle';

  container.innerHTML = `
    <div class="flex h-screen bg-app overflow-hidden text-[14px]">
      <!-- Sidebar (Expanded: w-64 / 256px, Collapsed: w-16 / 64px) -->
      <aside class="${state.sidebarCollapsed ? 'w-16' : 'w-64'} bg-sidebar border-r border-subtle flex flex-col flex-shrink-0 z-20 relative transition-all duration-200">

        <!-- Business Identity Card & Sidebar Toggle -->
        <div class="p-3 border-b border-subtle flex items-center ${state.sidebarCollapsed ? 'justify-center flex-col gap-2' : 'justify-between gap-2'}">
          <div class="flex items-center gap-2.5 min-w-0">
            <div id="sidebar-logo-container" class="flex-shrink-0">
              ${logoMarkup}
            </div>
            ${!state.sidebarCollapsed ? `
            <div class="min-w-0 flex-1">
              <p class="font-bold text-[14px] text-main truncate">CommB Studio</p>
              <div class="flex items-center gap-1 mt-0.5">
                <span class="w-1.5 h-1.5 rounded-full bg-brand flex-shrink-0 animate-pulse"></span>
                <p class="text-[12px] text-muted truncate" id="sidebar-business-name">${escapeHtml(businessName)}</p>
              </div>
            </div>
            ` : ''}
          </div>
          <button type="button" class="text-muted hover:text-main p-1.5 rounded-lg hover:bg-surface-hover transition-colors cursor-pointer flex-shrink-0" onclick="window.toggleSidebar()" title="${state.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}">
            <svg class="${state.sidebarCollapsed ? 'w-[18px] h-[18px]' : 'w-4 h-4'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2"/>
              <path d="M9 3v18"/>
            </svg>
          </button>
        </div>

        <!-- Grouped Navigation Menu -->
        <div class="flex-1 overflow-y-auto py-3.5 px-2.5 space-y-4">
          ${navSections.map(section => {
            const visibleItems = section.items.filter(item => !item.adminOnly || isAdmin);
            if (!visibleItems.length) return '';
            return `
              <div>
                ${!state.sidebarCollapsed ? `
                  <div class="px-2.5 pb-1.5 text-[12px] font-semibold text-muted">${section.title}</div>
                ` : ''}
                <nav class="flex flex-col gap-1">
                  ${visibleItems.map(item => {
                    const isActive = currentPath === item.path;
                    // Apply special glowing styles for Agents tab per user request
                    const isAgentTab = item.path === '/_/admin/agents';
                    let linkClass = isActive
                      ? 'bg-surface-hover text-main'
                      : 'text-muted hover:bg-surface-hover hover:text-main';
                    let iconClass = isActive
                      ? 'text-main'
                      : 'text-muted group-hover:text-main transition-colors';

                    if (isAgentTab) {
                      // The FILL itself glows and glitters — a deep
                      // green/black gradient that slowly animates plus a
                      // sweeping highlight pass (see .glow-fill-agents in
                      // style.css) — deliberately no box-shadow at all,
                      // which used to read as a faint halo around the
                      // edges rather than the fill itself glowing.
                      linkClass = isActive
                        ? 'glow-fill-agents text-white font-semibold'
                        : 'glow-fill-agents glow-fill-agents-resting text-white/90 hover:text-white';
                      iconClass = 'text-white';
                    }

                    return `
                      <a href="${item.path}" class="flex items-center ${state.sidebarCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-[14px] font-medium transition-colors group ${linkClass}" onclick="event.preventDefault(); navigate('${item.path}')" title="${item.label}">
                        <i data-lucide="${item.icon}" class="${state.sidebarCollapsed ? 'w-[18px] h-[18px]' : 'w-4 h-4'} flex-shrink-0 ${iconClass}"></i>
                        ${!state.sidebarCollapsed ? `<span class="truncate">${item.label}</span>` : ''}
                      </a>
                    `;
                  }).join('')}
                </nav>
              </div>
            `;
          }).join('')}
        </div>

        <!-- Footer Actions (Help, Theme Switcher & User Identity) -->
        <div class="p-2.5 border-t border-subtle flex flex-col gap-1.5 bg-surface-elevated/30">
          
          <!-- Help Button (Triggers n8n-style Menu Popover) -->
          <div class="relative">
            <button type="button" id="sidebar-help-btn" class="w-full flex items-center ${state.sidebarCollapsed ? 'justify-center' : 'justify-between'} px-2 py-1.5 rounded-lg text-[14px] font-medium text-muted hover:text-main hover:bg-surface-hover transition-colors group cursor-pointer" onclick="window.toggleHelpMenu(event)" title="Help, Documentation & About CommB">
              <div class="flex items-center gap-2 min-w-0">
                <i data-lucide="help-circle" class="${state.sidebarCollapsed ? 'w-[18px] h-[18px]' : 'w-4 h-4'} text-muted group-hover:text-main flex-shrink-0"></i>
                ${!state.sidebarCollapsed ? `<span class="truncate">Help</span>` : ''}
              </div>
              ${!state.sidebarCollapsed ? `
                <i data-lucide="chevron-right" class="w-3.5 h-3.5 text-faint group-hover:text-main transition-transform"></i>
              ` : ''}
            </button>
          </div>



          <!-- User Identity Card -->
          <div class="flex items-center ${state.sidebarCollapsed ? 'justify-center flex-col pt-0.5' : 'gap-2 pt-0.5'}">
            <div class="${state.sidebarCollapsed ? 'w-8 h-8 text-[13px]' : 'w-7 h-7 text-[12px]'} rounded-full bg-brand/10 border border-brand/20 flex items-center justify-center text-brand font-bold flex-shrink-0">
              ${escapeHtml(user.name?.charAt(0) || 'U')}
            </div>
            ${!state.sidebarCollapsed ? `
            <div class="flex-1 min-w-0">
              <div class="text-[14px] font-bold truncate text-main leading-none mb-0.5">${escapeHtml(user.name || 'User')}</div>
              <span class="badge ${roleBadgeClass} text-[12px] px-1.5 py-0 font-medium">
                ${escapeHtml(user.role === 'super_admin' ? 'Super Admin' : (user.role === 'admin' ? 'Admin' : (user.role === 'operator' ? 'Operator' : (user.role || 'User'))))}
              </span>
            </div>
            ` : ''}
            <button class="text-faint hover:text-rose transition-colors p-1 hover:bg-rose/10 rounded-md ${state.sidebarCollapsed ? 'mt-1' : ''}" onclick="window.logout()" title="Logout">
              <i data-lucide="log-out" class="${state.sidebarCollapsed ? 'w-4 h-4' : 'w-3.5 h-3.5'}"></i>
            </button>
          </div>
        </div>
      </aside>

      <!-- Main Content Area (Full Height, No Top Header Bar) -->
      <main class="flex-1 flex flex-col min-w-0 bg-app relative h-screen overflow-hidden">
        <div id="page-content" class="p-6 max-w-[1600px] mx-auto w-full flex-1 min-h-0 flex flex-col overflow-y-auto"></div>
      </main>
    </div>
  `;

  // Attach global shell handlers so inline onclicks work
  window.navigate = navigate;
  window.setTheme = function(t) {
    applyTheme(t);
    // Don't re-render the whole shell, just the active page content!
    const pageContainer = document.getElementById('page-content');
    if (currentPath === '/_/admin/overview') import('./pages/overview.js').then(m => m.loadOverviewPage(pageContainer));
    else if (currentPath === '/_/admin/conversations') import('./pages/conversations.js').then(m => m.loadConversationsPage(pageContainer));
    else if (currentPath === '/_/admin/orders') import('./pages/orders.js').then(m => m.loadOrdersPage(pageContainer));
    else if (currentPath === '/_/admin/reports') import('./pages/reports.js').then(m => m.loadReportsPage(pageContainer));
    else if (currentPath === '/_/admin/agents') import('./pages/agents.js').then(m => m.loadAgentsPage(pageContainer));
    else if (currentPath === '/_/admin/groups') import('./pages/groups.js').then(m => m.loadGroupsPage(pageContainer));
    else if (currentPath === '/_/admin/customers') import('./pages/customers.js').then(m => m.loadCustomersPage(pageContainer));
    else if (currentPath === '/_/admin/catalog') import('./pages/catalog.js').then(m => m.loadCatalogPage(pageContainer));
    else if (currentPath === '/_/admin/knowledge') import('./pages/knowledge.js').then(m => m.loadKnowledgePage(pageContainer));
    else if (currentPath === '/_/admin/users') import('./pages/users.js').then(m => m.loadUsersPage(pageContainer));
    else if (currentPath === '/_/admin/settings') import('./pages/settings.js').then(m => m.loadSettingsPage(pageContainer));
    else if (currentPath === '/_/admin/integrations') import('./pages/integrations.js').then(m => m.loadIntegrationsPage(pageContainer));
    // We update the shell's active state icons where needed, but rendering the whole shell causes page flickers/resets.
    // Instead we rely on CSS classes which CSS variables handle automatically!
    // EXCEPT that the settings page toggles its own Lucide icon, so we must reload that specific page to swap the icon.
  };
  window.toggleTheme = function() {
    const next = state.theme === 'light' ? 'dark' : 'light';
    window.setTheme(next);
  };
  window.updateSidebarBrand = function() {
    const b = state.business || state.user?.business || {};
    const bName = b.name || 'CommB Studio';
    const bLogo = b.logo_url;
    const bInit = (bName.trim().charAt(0) || 'A').toUpperCase();

    const logoContainer = document.getElementById('sidebar-logo-container');
    if (logoContainer) {
      logoContainer.innerHTML = bLogo ? `
        <div class="w-8 h-8 rounded-lg bg-surface-elevated border border-subtle flex items-center justify-center overflow-hidden flex-shrink-0 shadow-sm">
          <img src="${escapeHtml(bLogo)}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-8 h-8 rounded-lg bg-brand flex items-center justify-center text-white font-bold text-[14px]\\'>${escapeHtml(bInit)}</div>';" />
        </div>
      ` : `
        <div class="w-8 h-8 rounded-lg bg-brand flex items-center justify-center text-white font-bold text-[14px] flex-shrink-0 shadow-sm">
          ${escapeHtml(bInit)}
        </div>
      `;
    }
    const nameEl = document.getElementById('sidebar-business-name');
    if (nameEl) nameEl.textContent = bName;
  };

  window.toggleSidebar = function() {
    state.sidebarCollapsed = !state.sidebarCollapsed;
    localStorage.setItem('commb_sidebar_collapsed', String(state.sidebarCollapsed));
    renderAdminShell(container, currentPath);
  };

  window.logout = async function() {
    try { await api('/auth/logout', { method: 'POST' }); } catch {}
    localStorage.removeItem('commb_admin_token');
    state.user = null;
    state.business = null;
    navigate('/_/admin/login');
  };

  // n8n Style Help Menu Popover Handler
  window.toggleHelpMenu = function(e) {
    e?.stopPropagation();
    let menu = document.getElementById('n8n-help-popover');
    if (menu) {
      menu.remove();
      return;
    }

    const popover = document.createElement('div');
    popover.id = 'n8n-help-popover';
    const leftOffset = state.sidebarCollapsed ? '72px' : '248px';
    popover.className = 'fixed z-50 w-72 popover-surface rounded-xl border border-subtle overflow-hidden animate-scale-in text-main font-sans text-[14px]';
    popover.style.left = leftOffset;
    popover.style.bottom = '16px';
    
    popover.innerHTML = `
      <div class="p-1.5 space-y-0.5 text-[14px]">
        <a href="https://commb.app/docs/getting-started/quickstart" target="_blank" rel="noopener noreferrer" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-muted hover:text-main hover:bg-surface-hover transition-colors">
          <svg class="w-4 h-4 text-sky-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
          <span>Quickstart</span>
        </a>

        <a href="https://commb.app/docs" target="_blank" rel="noopener noreferrer" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-muted hover:text-main hover:bg-surface-hover transition-colors">
          <svg class="w-4 h-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
          <span>Documentation</span>
        </a>

        <a href="https://github.com/samakins/commb/discussions" target="_blank" rel="noopener noreferrer" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-muted hover:text-main hover:bg-surface-hover transition-colors">
          <svg class="w-4 h-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
          <span>Forum & Community</span>
        </a>

        <a href="https://commb.app/docs" target="_blank" rel="noopener noreferrer" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-muted hover:text-main hover:bg-surface-hover transition-colors">
          <svg class="w-4 h-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l9-5-9-5-9 5 9 5z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" /></svg>
          <span>Course & Tutorials</span>
        </a>

        <a href="https://github.com/samakins/commb/issues/new?labels=bug-report" target="_blank" rel="noopener noreferrer" class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-muted hover:text-main hover:bg-surface-hover transition-colors">
          <svg class="w-4 h-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
          <span>Report a bug</span>
        </a>

        <button onclick="window.openAboutModal(); document.getElementById('n8n-help-popover')?.remove();" class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-muted hover:text-main hover:bg-surface-hover transition-colors text-left cursor-pointer">
          <svg class="w-4 h-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <span>About CommB</span>
        </button>
      </div>

      <!-- What's New Section -->
      <div class="p-3 border-t border-subtle bg-surface-elevated/50 space-y-2">
        <div class="text-[12px] font-semibold text-muted">What's new</div>
        
        <!-- One Highlight Item (Clickable to open What's New modal) -->
        <button onclick="window.openWhatsNewModal(); document.getElementById('n8n-help-popover')?.remove();" class="w-full flex items-start gap-2 text-left p-1.5 rounded-lg hover:bg-surface-hover transition-colors group cursor-pointer">
          <span class="w-2 h-2 rounded-full bg-rose-500 mt-1 flex-shrink-0 animate-pulse"></span>
          <span class="text-main group-hover:text-rose-500 line-clamp-1 font-semibold text-[13px]">AI Assistant on self-hosted: setup in minutes</span>
        </button>

        <!-- Full Changelog Link (Opens Blog Site Directly) -->
        <a href="https://commb.app/blog" target="_blank" rel="noopener noreferrer" class="w-full flex items-center justify-between text-[13px] text-sky-600 dark:text-sky-400 hover:underline font-semibold pt-1">
          <span>Full changelog</span>
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
        </a>

        <!-- Version Status -->
        <div class="flex items-center gap-1.5 text-[12px] text-emerald-600 dark:text-emerald-400 pt-1 border-t border-subtle font-mono">
          <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
          <span>v${escapeHtml(state.appVersion || '0.1.0')} (Latest)</span>
        </div>
      </div>
    `;

    document.body.appendChild(popover);

    const closeListener = (ev) => {
      if (!popover.contains(ev.target) && ev.target !== e.target) {
        popover.remove();
        document.removeEventListener('click', closeListener);
      }
    };
    setTimeout(() => document.addEventListener('click', closeListener), 10);
  };

  // About CommB Modal
  window.openAboutModal = async function() {
    let existing = document.getElementById('about-commb-modal');
    if (existing) existing.remove();

    const version = state.appVersion || '0.1.0';
    let instanceId = '7966745583d50cb1210cd8041b0817e4ab54c3eaf22487b2c3433d3d07506383';
    let debugData = null;

    try {
      const debugRes = await api('/system/debug-info');
      if (debugRes?.instance_id) instanceId = debugRes.instance_id;
      debugData = debugRes;
    } catch {}

    const modal = document.createElement('div');
    modal.id = 'about-commb-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in font-sans';
    modal.onclick = (e) => {
      if (e.target === modal) modal.remove();
    };

    modal.innerHTML = `
      <div class="modal-surface rounded-xl max-w-lg w-full overflow-hidden animate-scale-in text-main border border-subtle" onclick="event.stopPropagation()">
        
        <!-- Header -->
        <div class="p-5 border-b border-subtle flex items-center justify-between bg-surface-elevated/40">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-brand text-brand-contrast flex items-center justify-center font-bold text-lg shadow-sm">
              A
            </div>
            <div>
              <h3 class="text-sm font-bold text-main">AI Commerce Bots (CommB)</h3>
              <p class="text-[12px] text-muted">Version <span class="font-mono text-emerald-600 dark:text-emerald-400 font-semibold">v${escapeHtml(version)}</span></p>
            </div>
          </div>
          <button class="text-muted hover:text-main p-1.5 rounded-lg hover:bg-surface-hover transition-colors cursor-pointer" onclick="document.getElementById('about-commb-modal')?.remove()" title="Close">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <!-- Body -->
        <div class="p-5 space-y-4 text-xs text-muted leading-relaxed">
          <p class="text-main font-medium">
            Autonomous Omnichannel Conversational Commerce Platform & Multi-Agent Grounding Engine.
          </p>

          <div class="space-y-2.5 p-3.5 rounded-lg bg-surface-elevated/50 border border-subtle text-[12px] font-mono">
            <div class="flex items-start justify-between gap-3">
              <span class="text-muted shrink-0">CommB Version:</span>
              <span class="text-main font-semibold text-right">v${escapeHtml(version)}</span>
            </div>
            <div class="flex items-start justify-between gap-3">
              <span class="text-muted shrink-0">Source Code:</span>
              <a href="https://github.com/samakins/commb" target="_blank" rel="noopener noreferrer" class="text-sky-600 dark:text-sky-400 hover:underline break-all text-right font-sans">
                https://github.com/samakins/commb
              </a>
            </div>
            <div class="flex items-start justify-between gap-3">
              <span class="text-muted shrink-0">License:</span>
              <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noopener noreferrer" class="text-sky-600 dark:text-sky-400 hover:underline text-right font-sans">
                AGPL-3.0-or-later
              </a>
            </div>
            <div class="flex items-start justify-between gap-3">
              <span class="text-muted shrink-0">Third-Party:</span>
              <a href="https://commb.app/docs/licenses" target="_blank" rel="noopener noreferrer" class="text-sky-600 dark:text-sky-400 hover:underline text-right font-sans">
                View all third-party licenses
              </a>
            </div>
            <div class="flex items-start justify-between gap-3">
              <span class="text-muted shrink-0">Instance ID:</span>
              <span class="text-main font-mono text-[12px] break-all select-all text-right">${escapeHtml(instanceId)}</span>
            </div>
            <div class="flex items-start justify-between gap-3">
              <span class="text-muted shrink-0">Debug Info:</span>
              <button type="button" id="copy-debug-btn" class="text-sky-600 dark:text-sky-400 hover:underline cursor-pointer bg-transparent border-0 p-0 text-[12px] font-mono text-right">
                Copy debug information
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between pt-2 border-t border-subtle text-[12px]">
            <a href="https://github.com/samakins/commb" target="_blank" rel="noopener noreferrer" class="text-sky-600 dark:text-sky-400 hover:underline flex items-center gap-1 font-semibold">
              <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
              <span>GitHub Repository</span>
            </a>
            <span class="text-muted">&copy; Sannex Tech LTD</span>
          </div>
        </div>

        <div class="p-3 border-t border-subtle bg-surface-elevated/40 flex justify-end">
          <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('about-commb-modal')?.remove()">
            Close
          </button>
        </div>

      </div>
    `;

    document.body.appendChild(modal);

    const debugBtn = modal.querySelector('#copy-debug-btn');
    if (debugBtn) {
      debugBtn.onclick = async () => {
        try {
          const info = debugData || await api('/system/debug-info').catch(() => null) || {
            commb_version: version,
            instance_id: instanceId,
            user_agent: navigator.userAgent,
            timestamp: new Date().toISOString()
          };
          await navigator.clipboard.writeText(JSON.stringify(info, null, 2));
          window.showToast('Debug information copied to clipboard.', 'success');
        } catch {
          window.showToast('Failed to copy debug information.', 'error');
        }
      };
    }
  };

  // What's New Feature Release Modal (Matching Screenshot 2)
  window.openWhatsNewModal = function() {
    let existing = document.getElementById('whats-new-modal');
    if (existing) existing.remove();

    const version = state.appVersion || '0.1.0';

    const modal = document.createElement('div');
    modal.id = 'whats-new-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in font-sans';
    modal.onclick = (e) => {
      if (e.target === modal) modal.remove();
    };

    modal.innerHTML = `
      <div class="modal-surface rounded-xl max-w-xl w-full overflow-hidden animate-scale-in text-main border border-subtle" onclick="event.stopPropagation()">
        
        <!-- Header -->
        <div class="p-5 border-b border-subtle flex items-center justify-between gap-3 bg-surface-elevated/40">
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-9 h-9 rounded-xl bg-rose-500/10 text-rose-500 border border-rose-500/20 flex items-center justify-center flex-shrink-0">
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
            </div>
            <div class="min-w-0">
              <h3 class="text-[20px] font-bold text-main truncate">AI Assistant on self-hosted</h3>
              <p class="text-[12px] text-muted font-medium">4 September, 2026 &bull; <span class="text-emerald-600 dark:text-emerald-400 font-mono">v${escapeHtml(version)} (Latest)</span></p>
            </div>
          </div>
          <div class="flex items-center gap-2.5">
            <a href="https://commb.app/docs" target="_blank" class="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-[14px] transition-all shadow-sm">
              Update
            </a>
            <button class="text-muted hover:text-main p-1.5 rounded-lg hover:bg-surface-hover transition-colors cursor-pointer" onclick="document.getElementById('whats-new-modal')?.remove()" title="Close">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        <!-- Warning / Update Notice Callout -->
        <div class="p-3.5 mx-6 mt-5 rounded-xl callout-amber flex items-start gap-3 text-[14px] leading-relaxed">
          <span class="text-base flex-shrink-0">⚠️</span>
          <div>
            You're currently on version <strong class="font-mono font-bold">${escapeHtml(version)}</strong>. Update to get all new features, improvements, and fixes. See what changed <a href="https://commb.app/blog" target="_blank" class="underline font-bold">in the full changelog</a>.
          </div>
        </div>

        <!-- Modal Body Content -->
        <div class="p-6 space-y-3.5 text-[14px] text-muted leading-relaxed max-h-[60vh] overflow-y-auto">
          <h4 class="text-[16px] font-bold text-main">AI Assistant on self-hosted: setup in minutes</h4>
          
          <p>
            Setting up the <strong class="text-main font-semibold">AI Assistant</strong> on self-hosted CommB enables automated conversational checkouts, unified multi-agent grounding (RAG), and zero-latency webhook routing across WhatsApp Cloud, Telegram, and the Website Widget.
          </p>

          <p class="font-medium text-main">New instance? Run the following in your terminal:</p>

          <div class="terminal-snippet p-3.5 rounded-xl flex items-center justify-between text-[12px] my-2 font-mono">
            <span class="select-all">curl -fsSL https://get.commb.app | sh</span>
            <button onclick="navigator.clipboard.writeText('curl -fsSL https://get.commb.app | sh'); window.showToast('Copied to clipboard', 'success');" class="text-slate-400 hover:text-white px-2.5 py-1 bg-slate-800 hover:bg-slate-700 rounded-md transition-colors text-[12px] shrink-0 font-sans cursor-pointer">
              Copy
            </button>
          </div>

          <p>
            Pick Anthropic, OpenAI, or Google Gemini, or any OpenAI-compatible endpoint and paste your API key in Settings.
          </p>

          <p>
            Already on Docker? Pull the latest container <code class="text-main font-mono bg-surface-elevated px-1.5 py-0.5 rounded border border-subtle text-[12px]">samakins/commb:latest</code> and follow the setup docs to add payments and web search.
          </p>

          <p>
            The assistant's generated code and conversational checkout runs on your isolated self-hosted instance. After that, the experience matches the Cloud dashboard: configure your catalog, review transcripts, and monitor sales in real-time.
          </p>

          <div class="pt-2">
            <a href="https://commb.app/docs" target="_blank" class="text-rose-500 hover:text-rose-400 font-semibold inline-flex items-center gap-1 hover:underline text-[14px]">
              <span>Learn more here</span>
              <span>&rarr;</span>
            </a>
          </div>
        </div>

      </div>
    `;

    document.body.appendChild(modal);
  };

  // Releases Offcanvas Handlers
  window.openReleasesModal = async function() {
    let existingModal = document.getElementById('releases-offcanvas-backdrop');
    if (existingModal) {
      existingModal.remove();
      return;
    }

    const backdrop = document.createElement('div');
    backdrop.id = 'releases-offcanvas-backdrop';
    backdrop.className = 'fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-fade-in font-sans';
    backdrop.onclick = (e) => {
      if (e.target === backdrop) backdrop.remove();
    };

    backdrop.innerHTML = `
      <div class="modal-surface rounded-2xl max-w-lg w-full max-h-[80vh] flex flex-col overflow-hidden animate-scale-in text-main" onclick="event.stopPropagation()">
        <div class="p-4 border-b border-subtle flex items-center justify-between bg-surface-elevated/40">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="w-8 h-8 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-500 flex-shrink-0">
              <i data-lucide="rocket" class="w-4 h-4"></i>
            </div>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-sm text-main truncate">CommB Releases</h3>
                <span class="badge badge-emerald text-xs font-mono px-1.5 py-0.5">v${escapeHtml(state.appVersion || '0.1.0')}</span>
              </div>
              <p class="text-xs text-muted truncate">Synchronized from AgentOS</p>
            </div>
          </div>
          <button class="text-muted hover:text-main p-1.5 rounded-lg hover:bg-surface-hover transition-colors cursor-pointer" onclick="document.getElementById('releases-offcanvas-backdrop')?.remove()" title="Close">
            <i data-lucide="x" class="w-4 h-4"></i>
          </button>
        </div>

        <div id="releases-modal-content" class="p-4 overflow-y-auto space-y-3 flex-1">
          <div class="flex items-center justify-center py-8">
            <div class="animate-spin w-5 h-5 border-2 border-sky-500 border-t-transparent rounded-full"></div>
          </div>
        </div>

        <div class="p-3 border-t border-subtle bg-surface-elevated/40 flex items-center justify-between gap-2">
          <button type="button" id="releases-sync-btn" class="btn btn-secondary btn-sm flex items-center gap-1.5" onclick="window.syncReleasesFromModal()">
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
            <span>Check Updates</span>
          </button>
          <button type="button" class="btn btn-primary btn-sm" onclick="document.getElementById('releases-offcanvas-backdrop')?.remove()">
            Close
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);
    if (window.lucide) lucide.createIcons();

    await window.loadReleasesModalContent();
  };

  window.loadReleasesModalContent = async function() {
    const container = document.getElementById('releases-modal-content');
    if (!container) return;

    try {
      const releases = await api('/system/releases');
      if (!releases || releases.length === 0) {
        container.innerHTML = `
          <div class="text-center py-8 text-muted">
            <i data-lucide="info" class="w-8 h-8 mx-auto text-muted mb-2"></i>
            <p class="font-medium text-sm text-main">No release notes available</p>
            <p class="text-xs">Click "Check Updates" to sync release notes from AgentOS.</p>
          </div>
        `;
        if (window.lucide) lucide.createIcons();
        return;
      }

      const agentosHost = 'https://commb.app';
      container.innerHTML = releases.map((rel, idx) => `
        <a href="${escapeHtml(rel.download_url || `${agentosHost}/blog`)}" target="_blank" rel="noopener noreferrer" class="block p-3.5 rounded-xl border border-subtle bg-surface-elevated/50 hover:bg-surface-hover transition-all group">
          <div class="flex items-center justify-between gap-2 mb-1">
            <div class="flex items-center gap-2 min-w-0">
              <span class="badge ${idx === 0 ? 'badge-emerald' : 'badge-subtle'} font-mono font-bold text-xs px-2 py-0.5">
                v${escapeHtml(rel.version)}
              </span>
              <h4 class="font-bold text-xs text-main truncate group-hover:text-rose-500 transition-colors">${escapeHtml(rel.title || 'Update')}</h4>
              ${rel.is_critical ? '<span class="badge badge-rose text-xs font-semibold">Critical</span>' : ''}
            </div>
            <i data-lucide="external-link" class="w-3.5 h-3.5 text-muted group-hover:text-rose-500 transition-colors flex-shrink-0"></i>
          </div>
          ${rel.description ? `<p class="text-xs text-muted line-clamp-2 leading-relaxed mt-1">${escapeHtml(rel.description)}</p>` : ''}
          <div class="flex items-center justify-between text-xs text-muted mt-2 pt-1.5 border-t border-subtle/50">
            <span>${rel.release_date ? escapeHtml(rel.release_date) : 'Official Release'}</span>
            <span class="text-rose-500 flex items-center gap-0.5 font-semibold">Read on AgentOS &rarr;</span>
          </div>
        </a>
      `).join('');

      if (window.lucide) lucide.createIcons();
    } catch (e) {
      container.innerHTML = `
        <div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs">
          Failed to load release notes: ${escapeHtml(e.message || 'Network error')}
        </div>
      `;
    }
  };

  window.syncReleasesFromModal = async function() {
    const btn = document.getElementById('releases-sync-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Checking...`;
      if (window.lucide) lucide.createIcons();
    }

    try {
      await api('/system/releases/sync', { method: 'POST' });
      showToast('Release notes synchronized successfully.', 'success');
      await window.loadReleasesModalContent();
    } catch (e) {
      showToast('Sync failed: ' + (e.message || 'Could not reach AgentOS'), 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i> Check Updates`;
        if (window.lucide) lucide.createIcons();
      }
    }
  };

  const pageContainer = document.getElementById('page-content');
  
  if (currentPath === '/_/admin/overview') loadOverviewPage(pageContainer);
  else if (currentPath === '/_/admin/conversations') loadConversationsPage(pageContainer);
  else if (currentPath === '/_/admin/orders') loadOrdersPage(pageContainer);
  else if (currentPath === '/_/admin/reports') loadReportsPage(pageContainer);
  else if (currentPath === '/_/admin/agents') loadAgentsPage(pageContainer);
  else if (currentPath === '/_/admin/groups') loadGroupsPage(pageContainer);
  else if (currentPath === '/_/admin/customers') loadCustomersPage(pageContainer);
  else if (currentPath === '/_/admin/catalog') loadCatalogPage(pageContainer);
  else if (currentPath === '/_/admin/knowledge') loadKnowledgePage(pageContainer);
  else if (currentPath === '/_/admin/users') loadUsersPage(pageContainer);
  else if (currentPath === '/_/admin/settings') loadSettingsPage(pageContainer);
  else if (currentPath === '/_/admin/integrations') loadIntegrationsPage(pageContainer);

  if (window.lucide) lucide.createIcons();
}

// Start SPA on Load
document.addEventListener('DOMContentLoaded', initApp);
