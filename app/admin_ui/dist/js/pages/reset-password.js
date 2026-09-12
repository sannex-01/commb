import { state } from '../state.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { showToast, escapeHtml, initPasswordToggles, renderPasswordStrengthMarkup, bindPasswordValidator } from '../utils.js';

export async function renderResetPasswordView(container) {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token');

  let bizName = state.business?.name || 'CommB Studio';
  let logoUrl = state.business?.logo_url || null;

  try {
    const status = await api('/setup/status');
    if (status.business) {
      bizName = status.business.name || bizName;
      logoUrl = status.business.logo_url || logoUrl;
      state.business = status.business;
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

  if (!token) {
    container.innerHTML = `
      <div class="min-h-screen flex flex-col items-center justify-center p-6 bg-app">
        <div class="card max-w-md w-full p-8 text-center space-y-4 shadow-xl">
          <div class="w-12 h-12 rounded-full bg-rose/10 text-rose flex items-center justify-center mx-auto">
            <i data-lucide="alert-triangle" class="w-6 h-6"></i>
          </div>
          <h2 class="text-lg font-bold text-main">Invalid Reset Link</h2>
          <p class="text-xs text-muted leading-relaxed">This password reset link is missing a valid security token or has already been used.</p>
          <button id="btn-invalid-req-link" class="btn btn-primary btn-sm w-full justify-center">
            Request New Reset Link
          </button>
        </div>
      </div>
    `;
    document.getElementById('btn-invalid-req-link')?.addEventListener('click', () => {
      navigate('/_/admin/forgot-password');
    });
    if (window.lucide) lucide.createIcons();
    return;
  }

  container.innerHTML = `
    <div class="min-h-screen flex flex-col items-center justify-center p-6 bg-app">
      
      <div class="mb-6 text-center">
        ${logoMarkup}
        <h1 class="text-2xl font-bold text-main tracking-tight">Set New Password</h1>
        <p class="text-[13px] text-muted mt-1 max-w-sm">Enter a new secure password for your administrative account.</p>
      </div>

      <div class="card max-w-md w-full p-8 relative shadow-xl">
        <form id="reset-password-form" class="space-y-4">
          <div class="form-group">
            <label class="form-label">New Password</label>
            <div class="relative">
              <i data-lucide="lock" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted pointer-events-none"></i>
              <input type="password" id="reset-password" class="form-control pl-9 pr-10 bg-app" required placeholder="Min 8 characters (mixed case, numbers)" />
              <button type="button" class="password-toggle-btn absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-main focus:outline-none" data-target="reset-password" aria-label="Toggle password visibility">
                <i data-lucide="eye" class="w-4 h-4"></i>
              </button>
            </div>
          </div>

          ${renderPasswordStrengthMarkup('reset')}

          <div class="form-group">
            <label class="form-label">Confirm New Password</label>
            <div class="relative">
              <i data-lucide="shield-check" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted pointer-events-none"></i>
              <input type="password" id="reset-password-confirm" class="form-control pl-9 pr-10 bg-app" required placeholder="Repeat new password" />
              <button type="button" class="password-toggle-btn absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-main focus:outline-none" data-target="reset-password-confirm" aria-label="Toggle password visibility">
                <i data-lucide="eye" class="w-4 h-4"></i>
              </button>
            </div>
          </div>

          <button type="submit" id="btn-reset-submit" class="btn btn-primary w-full justify-center py-2.5 mt-2 opacity-50 cursor-not-allowed" disabled>
            Update Password
          </button>
        </form>

        <div id="reset-success-state" class="hidden text-center py-4 space-y-4">
          <div class="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
            <i data-lucide="check" class="w-6 h-6"></i>
          </div>
          <div>
            <h3 class="font-bold text-main text-base">Password Updated</h3>
            <p class="text-xs text-muted mt-1">Your password has been changed successfully. You can now sign in with your new credentials.</p>
          </div>
          <button type="button" id="btn-signin-now" class="btn btn-primary btn-sm w-full justify-center py-2.5">
            Sign In Now
          </button>
        </div>
      </div>
    </div>
  `;

  initPasswordToggles(container);
  bindPasswordValidator({
    passwordInputId: 'reset-password',
    confirmInputId: 'reset-password-confirm',
    submitBtnId: 'btn-reset-submit',
    idPrefix: 'reset',
  });

  document.getElementById('btn-signin-now')?.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('/_/admin/login');
  });

  if (window.lucide) lucide.createIcons();

  document.getElementById('reset-password-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const p1 = document.getElementById('reset-password').value;
    const p2 = document.getElementById('reset-password-confirm').value;

    if (p1 !== p2) {
      showToast('Passwords do not match.', 'error');
      return;
    }

    const btn = document.getElementById('btn-reset-submit');
    const originalText = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 mr-1 animate-spin"></i> Updating...`;
    btn.disabled = true;
    if (window.lucide) lucide.createIcons();

    try {
      await api('/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ token, password: p1 }),
      });
      document.getElementById('reset-password-form').classList.add('hidden');
      document.getElementById('reset-success-state').classList.remove('hidden');
      showToast('Password reset successfully', 'success');
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      btn.innerHTML = originalText;
      btn.disabled = false;
      if (window.lucide) lucide.createIcons();
    }
  });
}

