import { state } from '../state.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { showToast, escapeHtml } from '../utils.js';

export async function renderForgotPasswordView(container) {
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

  container.innerHTML = `
    <div class="min-h-screen flex flex-col items-center justify-center p-6 bg-app">
      
      <div class="mb-6 text-center">
        ${logoMarkup}
        <h1 class="text-2xl font-bold text-main tracking-tight">Forgot Password</h1>
        <p class="text-[13px] text-muted mt-1 max-w-sm">Enter your administrative email and we'll send you a link to reset your password.</p>
      </div>

      <div class="card max-w-md w-full p-8 relative shadow-xl">
        <form id="forgot-password-form" class="space-y-5">
          <div class="form-group">
            <label class="form-label">Email Address</label>
            <div class="relative">
              <i data-lucide="mail" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted"></i>
              <input type="email" id="forgot-email" class="form-control pl-9 bg-app" required placeholder="admin@example.com" />
            </div>
          </div>

          <button type="submit" id="btn-forgot-submit" class="btn btn-primary w-full justify-center py-2.5">
            Send Reset Link
          </button>

          <div class="text-center pt-2">
            <a href="/_/admin/login" onclick="event.preventDefault(); navigate('/_/admin/login')" class="text-xs font-semibold text-brand hover:underline inline-flex items-center gap-1">
              <i data-lucide="arrow-left" class="w-3.5 h-3.5"></i> Back to Sign In
            </a>
          </div>
        </form>

        <div id="forgot-success-state" class="hidden text-center py-4 space-y-4">
          <div class="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
            <i data-lucide="check-circle-2" class="w-6 h-6"></i>
          </div>
          <div>
            <h3 class="font-bold text-main text-base">Check Your Inbox</h3>
            <p class="text-xs text-muted mt-1 leading-relaxed" id="forgot-success-msg">
              If an account matches that email address, a password reset link has been sent. Please check your inbox and spam folder.
            </p>
          </div>
          <a href="/_/admin/login" onclick="event.preventDefault(); navigate('/_/admin/login')" class="btn btn-secondary btn-sm w-full justify-center">
            Return to Login
          </a>
        </div>
      </div>
    </div>
  `;

  if (window.lucide) lucide.createIcons();

  document.getElementById('forgot-password-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-forgot-submit');
    const originalText = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 mr-1 animate-spin"></i> Sending...`;
    btn.disabled = true;
    if (window.lucide) lucide.createIcons();

    const email = document.getElementById('forgot-email').value;

    try {
      const res = await api('/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email }),
      });
      document.getElementById('forgot-password-form').classList.add('hidden');
      const successState = document.getElementById('forgot-success-state');
      successState.classList.remove('hidden');
      if (res.message) {
        document.getElementById('forgot-success-msg').textContent = res.message;
      }
      showToast('Reset request submitted', 'success');
    } catch (err) {
      btn.innerHTML = originalText;
      btn.disabled = false;
      if (window.lucide) lucide.createIcons();
    }
  });
}
