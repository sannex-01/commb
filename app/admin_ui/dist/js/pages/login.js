import { state } from '../state.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { showToast, escapeHtml, initPasswordToggles } from '../utils.js';

export async function renderLoginView(container) {
  let bizName = state.business?.name || 'CommB Studio';
  let logoUrl = state.business?.logo_url || null;

  try {
    const status = await api('/setup/status');
    if (status.business) {
      bizName = status.business.name || bizName;
      logoUrl = status.business.logo_url || logoUrl;
      state.business = status.business;
      if (window.updateAppTitle) window.updateAppTitle(bizName);
    }
  } catch {}

  const initial = (bizName.trim().charAt(0) || 'A').toUpperCase();
  const logoMarkup = logoUrl ? `
    <div class="w-14 h-14 rounded-2xl bg-surface-elevated border border-subtle mx-auto flex items-center justify-center overflow-hidden shadow-md mb-4 p-1">
      <img src="${escapeHtml(logoUrl)}" class="w-full h-full object-cover rounded-xl" onerror="this.parentElement.innerHTML='<div class=\\'w-14 h-14 rounded-2xl bg-brand mx-auto flex items-center justify-center text-white font-bold text-2xl\\'>${escapeHtml(initial)}</div>';" />
    </div>
  ` : `
    <div class="w-14 h-14 rounded-2xl bg-brand mx-auto flex items-center justify-center text-white font-bold text-2xl mb-4 shadow-md">
      ${escapeHtml(initial)}
    </div>
  `;

  container.innerHTML = `
    <div class="min-h-screen flex flex-col items-center justify-center p-6 bg-app">
      
      <div class="mb-8 text-center">
        ${logoMarkup}
        <h1 class="text-2xl font-bold text-main tracking-tight">Welcome Back</h1>
        <p class="text-[14px] text-muted mt-1">Sign in to manage <strong>${escapeHtml(bizName)}</strong></p>
      </div>

      <div class="card max-w-md w-full p-8 relative shadow-xl">
        <form id="login-form" class="space-y-5">
          <div class="form-group">
            <label class="form-label">Email Address</label>
            <div class="relative">
              <i data-lucide="mail" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted"></i>
              <input type="email" id="login-email" class="form-control pl-9 bg-app" required placeholder="admin@example.com" />
            </div>
          </div>

          <div class="form-group">
            <div class="flex justify-between items-center mb-1">
              <label class="form-label mb-0">Password</label>
              <a href="/_/admin/forgot-password" onclick="event.preventDefault(); navigate('/_/admin/forgot-password')" class="text-[12px] font-semibold text-brand hover:underline">Forgot password?</a>
            </div>
            <div class="relative">
              <i data-lucide="lock" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted pointer-events-none"></i>
              <input type="password" id="login-password" class="form-control pl-9 pr-10 bg-app" required placeholder="••••••••••••" />
              <button type="button" class="password-toggle-btn absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-main focus:outline-none" data-target="login-password" aria-label="Toggle password visibility">
                <i data-lucide="eye" class="w-4 h-4"></i>
              </button>
            </div>
          </div>

          <button type="submit" id="btn-login-submit" class="btn btn-primary w-full mt-2 justify-center py-2.5">
            Sign In
          </button>
        </form>
      </div>
    </div>
  `;

  initPasswordToggles(container);
  if (window.lucide) lucide.createIcons();

  document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-login-submit');
    const originalText = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 mr-1 animate-spin"></i> Signing In...`;
    btn.disabled = true;
    if (window.lucide) lucide.createIcons();

    const payload = {
      email: document.getElementById('login-email').value,
      password: document.getElementById('login-password').value,
    };

    try {
      const res = await api('/auth/login', { method: 'POST', body: JSON.stringify(payload) });
      localStorage.setItem('commb_admin_token', res.access_token);
      state.user = res.user;
      state.business = res.business;
      if (res.business?.name && window.updateAppTitle) window.updateAppTitle(res.business.name);
      showToast(`Welcome back, ${res.user.name || 'Admin'}!`, 'success');
      navigate('/_/admin/overview');
    } catch (err) {
      btn.innerHTML = originalText;
      btn.disabled = false;
      if (window.lucide) lucide.createIcons();
    }
  });
}