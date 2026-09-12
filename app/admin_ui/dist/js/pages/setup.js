import { state } from '../state.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { showToast, escapeHtml, initAllCustomSelects, initPasswordToggles } from '../utils.js';

export function renderSetupView(container) {
  container.innerHTML = `
    <div class="min-h-screen flex flex-col items-center justify-center p-6 bg-app">
      
      <div class="mb-8 text-center">
        <div class="w-12 h-12 rounded-lg bg-brand mx-auto flex items-center justify-center text-white font-bold text-xl mb-4 shadow-md">
          A
        </div>
        <h1 class="text-2xl font-semibold text-main tracking-tight">Welcome to CommB</h1>
        <p class="text-[14px] text-muted mt-1">Set up your business profile, super admin account & email delivery</p>
      </div>

      <div class="card max-w-xl w-full p-8 relative overflow-hidden shadow-xl">
        
        <!-- Progress Steps -->
        <div class="flex items-center justify-between mb-8 relative px-4">
          <div class="absolute top-1/2 left-4 right-4 h-[2px] bg-subtle -z-10 -translate-y-1/2"></div>
          <div id="progress-bar" class="absolute top-1/2 left-4 w-0 h-[2px] bg-brand -z-10 -translate-y-1/2 transition-all duration-300"></div>
          
          <div class="flex flex-col items-center gap-2 step-indicator bg-surface" data-step="1">
            <div class="w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-brand text-white border-4 border-surface transition-all">1</div>
            <span class="text-[13px] font-medium text-main">Business</span>
          </div>
          <div class="flex flex-col items-center gap-2 step-indicator bg-surface opacity-60" data-step="2">
            <div class="w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-surface-elevated text-muted border-4 border-surface transition-all">2</div>
            <span class="text-[13px] font-medium text-muted">Admin</span>
          </div>
          <div class="flex flex-col items-center gap-2 step-indicator bg-surface opacity-60" data-step="3">
            <div class="w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-surface-elevated text-muted border-4 border-surface transition-all">3</div>
            <span class="text-[13px] font-medium text-muted">Email</span>
          </div>
        </div>

        <form id="setup-form" class="relative min-h-[380px]">
          
          <!-- STEP 1 -->
          <div class="wizard-step absolute inset-0 transition-opacity duration-200 opacity-100" data-step="1">
            <div class="space-y-4">
              <div class="form-group">
                <label class="form-label">Business / Store Name</label>
                <input type="text" id="setup-business-name" class="form-control" required placeholder="e.g. Acme Commerce" />
              </div>
  
              <div class="grid grid-cols-2 gap-4">
                <div class="form-group">
                  <label class="form-label">Store Currency</label>
                  <select id="setup-currency" class="form-control">
                    <option value="NGN">NGN (₦)</option>
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">Contact Phone</label>
                  <input type="tel" id="setup-contact-phone" class="form-control" placeholder="+2348012345678" />
                </div>
              </div>
  
              <div class="form-group">
                <label class="form-label">Contact Email</label>
                <input type="email" id="setup-contact-email" class="form-control" placeholder="support@acme.com" />
              </div>
            </div>

            <div class="absolute bottom-0 right-0 w-full flex justify-end mt-8 pt-5 border-t border-subtle">
              <button type="button" class="btn btn-primary" onclick="goToSetupStep(2)">
                Continue <i data-lucide="arrow-right" class="w-4 h-4 ml-1"></i>
              </button>
            </div>
          </div>
          
          <!-- STEP 2 -->
          <div class="wizard-step absolute inset-0 transition-opacity duration-200 opacity-0 pointer-events-none" data-step="2">
            <div class="space-y-4">
              <div class="form-group">
                <label class="form-label">Admin Full Name</label>
                <input type="text" id="setup-admin-name" class="form-control" required placeholder="John Doe" />
              </div>
  
              <div class="form-group">
                <label class="form-label">Admin Login Email</label>
                <input type="email" id="setup-admin-email" class="form-control" required placeholder="admin@acme.com" />
              </div>
  
              <div class="form-group">
                <label class="form-label">Admin Password</label>
                <div class="relative">
                  <input type="password" id="setup-password" class="form-control pr-10" required minlength="8" placeholder="••••••••••••" />
                  <button type="button" class="password-toggle-btn absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-main focus:outline-none" data-target="setup-password" aria-label="Toggle password visibility">
                    <i data-lucide="eye" class="w-4 h-4"></i>
                  </button>
                </div>
                <p class="text-[12px] text-muted mt-1.5">Minimum 8 characters required</p>
              </div>
            </div>

            <div class="absolute bottom-0 right-0 w-full flex justify-between mt-8 pt-5 border-t border-subtle">
              <button type="button" class="btn btn-secondary" onclick="goToSetupStep(1)">
                <i data-lucide="arrow-left" class="w-4 h-4 mr-1"></i> Back
              </button>
              <button type="button" class="btn btn-primary" onclick="goToSetupStep(3)">
                Continue <i data-lucide="arrow-right" class="w-4 h-4 ml-1"></i>
              </button>
            </div>
          </div>

          <!-- STEP 3 (Email Delivery - Optional) -->
          <div class="wizard-step absolute inset-0 transition-opacity duration-200 opacity-0 pointer-events-none" data-step="3">
            <div class="space-y-4">
              <div class="form-group">
                <div class="flex items-center justify-between">
                  <label class="form-label mb-0">Transactional Email Provider</label>
                  <span class="badge badge-subtle text-[12px]">Optional</span>
                </div>
                <select id="setup-email-provider" class="form-control" onchange="toggleSetupEmailFields(this.value)">
                  <option value="none">None (Skip for now)</option>
                  <option value="resend">Resend (Recommended)</option>
                  <option value="brevo">Brevo (Sendinblue)</option>
                </select>
                <p class="text-[12px] text-muted">Used for password reset links and order notifications.</p>
              </div>

              <div id="setup-email-fields" class="space-y-4 hidden pt-2 border-t border-subtle">
                <div class="form-group">
                  <label class="form-label">Provider API Key</label>
                  <input type="password" id="setup-email-key" class="form-control font-mono text-xs" placeholder="re_... or xkeysib-..." />
                </div>
                <div class="grid grid-cols-2 gap-4">
                  <div class="form-group">
                    <label class="form-label">Sender Email (From)</label>
                    <input type="email" id="setup-email-from" class="form-control text-xs" placeholder="noreply@acme.com" />
                  </div>
                  <div class="form-group">
                    <label class="form-label">Sender Name</label>
                    <input type="text" id="setup-email-name" class="form-control text-xs" placeholder="Acme Support" />
                  </div>
                </div>
              </div>
            </div>

            <div class="absolute bottom-0 right-0 w-full flex justify-between mt-8 pt-5 border-t border-subtle">
              <button type="button" class="btn btn-secondary" onclick="goToSetupStep(2)">
                <i data-lucide="arrow-left" class="w-4 h-4 mr-1"></i> Back
              </button>
              <button type="submit" class="btn btn-primary" id="btn-complete-setup">
                Complete Setup <i data-lucide="check" class="w-4 h-4 ml-1"></i>
              </button>
            </div>
          </div>

        </form>
      </div>
    </div>
  `;

  if (window.lucide) lucide.createIcons();

  window.toggleSetupEmailFields = (val) => {
    const fields = document.getElementById('setup-email-fields');
    if (fields) {
      fields.classList.toggle('hidden', val === 'none');
    }
  };

  window.goToSetupStep = (step) => {
    const s1 = document.querySelector('.wizard-step[data-step="1"]');
    const s2 = document.querySelector('.wizard-step[data-step="2"]');
    const s3 = document.querySelector('.wizard-step[data-step="3"]');
    const i1 = document.querySelector('.step-indicator[data-step="1"]');
    const i2 = document.querySelector('.step-indicator[data-step="2"]');
    const i3 = document.querySelector('.step-indicator[data-step="3"]');
    const bar = document.getElementById('progress-bar');
    
    if (step >= 2) {
      if (!document.getElementById('setup-business-name').value) {
        showToast('Please enter a business name', 'error');
        return;
      }
    }

    if (step >= 3) {
      if (!document.getElementById('setup-admin-name').value || !document.getElementById('setup-admin-email').value) {
        showToast('Please enter admin name and email', 'error');
        return;
      }
      if (document.getElementById('setup-password').value.length < 8) {
        showToast('Admin password must be at least 8 characters', 'error');
        return;
      }
    }

    // Hide all
    [s1, s2, s3].forEach(s => {
      s.classList.replace('opacity-100', 'opacity-0');
      s.classList.add('pointer-events-none');
    });

    if (step === 1) {
      s1.classList.replace('opacity-0', 'opacity-100');
      s1.classList.remove('pointer-events-none');
      
      i1.classList.remove('opacity-60');
      i1.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-brand text-white border-4 border-surface transition-all';
      i1.querySelector('span').className = 'text-[13px] font-medium text-main';
      
      i2.classList.add('opacity-60');
      i2.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-surface-elevated text-muted border-4 border-surface transition-all';
      i2.querySelector('span').className = 'text-[13px] font-medium text-muted';

      i3.classList.add('opacity-60');
      i3.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-surface-elevated text-muted border-4 border-surface transition-all';
      i3.querySelector('span').className = 'text-[13px] font-medium text-muted';
      
      bar.style.width = '0%';
    } else if (step === 2) {
      s2.classList.replace('opacity-0', 'opacity-100');
      s2.classList.remove('pointer-events-none');
      
      i1.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-emerald-500 text-white border-4 border-surface transition-all';
      
      i2.classList.remove('opacity-60');
      i2.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-brand text-white border-4 border-surface transition-all';
      i2.querySelector('span').className = 'text-[13px] font-medium text-main';

      i3.classList.add('opacity-60');
      i3.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-surface-elevated text-muted border-4 border-surface transition-all';
      i3.querySelector('span').className = 'text-[13px] font-medium text-muted';
      
      bar.style.width = '50%';
    } else if (step === 3) {
      s3.classList.replace('opacity-0', 'opacity-100');
      s3.classList.remove('pointer-events-none');

      i1.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-emerald-500 text-white border-4 border-surface transition-all';
      i2.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-emerald-500 text-white border-4 border-surface transition-all';
      
      i3.classList.remove('opacity-60');
      i3.querySelector('div').className = 'w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold bg-brand text-white border-4 border-surface transition-all';
      i3.querySelector('span').className = 'text-[13px] font-medium text-main';

      bar.style.width = '100%';
    }
  };

  document.getElementById('setup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-complete-setup');
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 mr-1 animate-spin"></i> Initializing...`;
    btn.disabled = true;

    const emailProvider = document.getElementById('setup-email-provider').value;
    let emailConfig = {};
    if (emailProvider !== 'none') {
      emailConfig = {
        api_key: document.getElementById('setup-email-key').value.trim(),
        from_email: document.getElementById('setup-email-from').value.trim(),
        from_name: document.getElementById('setup-email-name').value.trim() || document.getElementById('setup-business-name').value.trim(),
      };
    }

    const payload = {
      business_name: document.getElementById('setup-business-name').value,
      currency: document.getElementById('setup-currency').value,
      contact_phone: document.getElementById('setup-contact-phone').value,
      contact_email: document.getElementById('setup-contact-email').value,
      admin_name: document.getElementById('setup-admin-name').value,
      admin_email: document.getElementById('setup-admin-email').value,
      admin_password: document.getElementById('setup-password').value,
      email_provider: emailProvider !== 'none' ? emailProvider : null,
      email_config: emailConfig,
    };

    try {
      const res = await api('/setup/initialize', { method: 'POST', body: JSON.stringify(payload) });
      localStorage.setItem('commb_admin_token', res.access_token);
      state.user = res.user;
      state.business = res.business;
      if (res.business?.name && window.updateAppTitle) window.updateAppTitle(res.business.name);
      showToast('Setup complete! Welcome to CommB.', 'success');
      navigate('/_/admin/overview');
    } catch (err) {
      btn.innerHTML = `Complete Setup <i data-lucide="check" class="w-4 h-4 ml-1"></i>`;
      btn.disabled = false;
      if (window.lucide) lucide.createIcons();
    }
  });

  initAllCustomSelects(container);
  initPasswordToggles(container);
}