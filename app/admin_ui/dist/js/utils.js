// Toast Notifications
export function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type === 'error' ? 'border-rose text-rose' : ''}`;
  const icon = type === 'error' ? 'alert-circle' : type === 'success' ? 'check-circle-2' : 'info';
  toast.innerHTML = `<i data-lucide="${icon}" class="w-5 h-5"></i><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  if (window.lucide) lucide.createIcons();
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

import { createCustomSelect, enhanceSelect, initAllCustomSelects } from './components/custom-select.js';
export { createCustomSelect, enhanceSelect, initAllCustomSelects };
export { DataTable, renderDataTable } from './components/datatable.js';

/**
 * Renders a modern, reusable multi-select / single-select card grid where the entire card is clickable.
 */
export function renderSelectCards({
  name,
  type = 'checkbox',
  items = [],
  selectedValues = [],
  gridClass = 'select-card-grid',
  emptyMessage = 'No options available.',
  renderExtra = null,
} = {}) {
  if (!items || !items.length) {
    return `
      <div class="p-4 rounded-xl border border-dashed border-subtle text-center text-xs text-muted">
        ${escapeHtml(emptyMessage)}
      </div>
    `;
  }

  const selectedSet = selectedValues instanceof Set ? selectedValues : new Set(selectedValues);

  return `
    <div class="${gridClass}">
      ${items.map(item => {
        const val = item.value ?? item.id;
        const isChecked = selectedSet.has(val) || selectedSet.has(String(val)) || selectedSet.has(Number(val));
        const title = item.title ?? item.name ?? '';
        const desc = item.description ?? item.desc ?? '';
        const badge = item.badge ?? '';
        const metaHtml = item.metaHtml ?? (renderExtra ? renderExtra(item) : '');
        
        return `
          <label class="select-card ${type === 'radio' ? 'radio' : ''} ${isChecked ? 'is-selected' : ''}" tabindex="0" onkeydown="if(event.key===' '||event.key==='Enter'){event.preventDefault();this.querySelector('input').click();}">
            <input type="${type}" name="${name}" value="${escapeHtml(String(val))}" ${isChecked ? 'checked' : ''} onchange="this.closest('.select-card').classList.toggle('is-selected', this.checked);" />
            <div class="select-card-indicator">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </div>
            <div class="select-card-content">
              <div class="flex items-center justify-between gap-1.5">
                <span class="select-card-title truncate">${escapeHtml(title)}</span>
                ${badge ? `<span class="badge ${item.badgeClass || 'badge-subtle'} text-[12px] py-0.5 px-1.5">${escapeHtml(badge)}</span>` : ''}
              </div>
              ${desc ? `<div class="select-card-desc line-clamp-2">${escapeHtml(desc)}</div>` : ''}
              ${metaHtml ? `<div class="select-card-meta">${metaHtml}</div>` : ''}
            </div>
          </label>
        `;
      }).join('')}
    </div>
  `;
}

// Modal Helpers
export function openModal(html) {
  const root = document.getElementById('modal-root');
  root.innerHTML = `<div class="modal-overlay" id="active-modal">${html}</div>`;
  if (window.lucide) lucide.createIcons();
  initAllCustomSelects(root);
}

export function closeModal() {
  const root = document.getElementById('modal-root');
  root.innerHTML = '';
}

// Global modal closer binding
window.closeModal = closeModal;

/**
 * Reusable confirmation modal supporting confirm-by-typing mode.
 */
export function openConfirmModal({
  title = 'Are you sure?',
  message = 'This action cannot be undone.',
  confirmText = 'Delete',
  confirmType = 'danger',
  confirmInput = null,
  inputLabel = null,
  inputPlaceholder = '',
  onConfirm = async () => {},
}) {
  const modalId = 'confirm_modal_' + Math.random().toString(36).substring(2, 9);
  const requiresInput = Boolean(confirmInput);
  const confirmBtnClass = confirmType === 'danger' ? 'btn-danger' : 'btn-primary';

  openModal(`
    <div class="modal-center-dialog">
      <div class="modal-header">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-full ${confirmType === 'danger' ? 'bg-rose/10 text-rose' : 'bg-brand/10 text-brand'} flex items-center justify-center flex-shrink-0">
            <i data-lucide="${confirmType === 'danger' ? 'alert-triangle' : 'help-circle'}" class="w-4 h-4"></i>
          </div>
          <h3 class="font-bold text-base text-main">${escapeHtml(title)}</h3>
        </div>
        <button class="btn btn-icon btn-secondary btn-sm" onclick="closeModal()"><i data-lucide="x" class="w-4 h-4"></i></button>
      </div>

      <div class="modal-body space-y-4 text-sm">
        <p class="text-muted leading-relaxed">${escapeHtml(message)}</p>

        ${requiresInput ? `
          <div class="p-3 bg-surface-elevated rounded-lg border border-subtle space-y-2">
            <div class="text-xs font-semibold text-main">
              ${inputLabel || `To confirm, please type <span class="font-mono px-1.5 py-0.5 rounded bg-app border border-subtle text-rose font-bold">${escapeHtml(confirmInput)}</span> below:`}
            </div>
            <input 
              type="text" 
              id="${modalId}-input" 
              class="form-control text-xs font-mono" 
              placeholder="${escapeHtml(inputPlaceholder || confirmInput)}" 
              autocomplete="off" 
              autofocus
            />
          </div>
        ` : ''}
      </div>

      <div class="modal-footer">
        <button type="button" class="btn btn-secondary btn-sm" onclick="closeModal()">Cancel</button>
        <button 
          type="button" 
          id="${modalId}-btn-confirm" 
          class="btn btn-sm ${confirmBtnClass} ${requiresInput ? 'opacity-40 cursor-not-allowed' : ''}" 
          ${requiresInput ? 'disabled' : ''}
        >
          <span id="${modalId}-btn-text">${escapeHtml(confirmText)}</span>
        </button>
      </div>
    </div>
  `);

  const confirmBtn = document.getElementById(`${modalId}-btn-confirm`);
  const inputEl = document.getElementById(`${modalId}-input`);

  if (requiresInput && inputEl) {
    setTimeout(() => inputEl.focus(), 50);
    inputEl.addEventListener('input', (e) => {
      const isMatch = e.target.value.trim() === confirmInput.trim();
      confirmBtn.disabled = !isMatch;
      confirmBtn.classList.toggle('opacity-40', !isMatch);
      confirmBtn.classList.toggle('cursor-not-allowed', !isMatch);
    });

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !confirmBtn.disabled) {
        confirmBtn.click();
      }
    });
  }

  confirmBtn.addEventListener('click', async () => {
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin mr-1"></i> Processing...`;
    if (window.lucide) lucide.createIcons();

    try {
      await onConfirm();
      closeModal();
    } catch (err) {
      showToast(err.message || 'Action failed', 'error');
      confirmBtn.disabled = false;
      confirmBtn.innerHTML = escapeHtml(confirmText);
    }
  });

  if (window.lucide) lucide.createIcons();
}

window.openConfirmModal = openConfirmModal;

// Reusable Offcanvas — a right-docked panel (same visual shell as
// .modal-dialog) with a header, a scrollable body, and a footer that is
// ALWAYS pinned to the bottom of the panel regardless of content height
// (fixes the earlier bug where per-step buttons left dead space below
// them in tall panels). Used for both single-step forms and multi-step
// wizards — pass 1 step for a plain form, 2+ for a wizard with an
// automatic progress bar at the top of the body.
//
// steps: [{ label: string, render: () => htmlString }]
// options.formId: the <form> id, so callers can attach their own submit handler
// options.extraFooterLeft: optional HTML rendered at the left of the footer
//   (e.g. a "Delete" button), shown only on the step index given by
//   options.extraFooterStep (defaults to the last step).
// options.submitLabel: label for the final step's submit button
export function openOffcanvas({
  title,
  steps,
  formId = 'offcanvas-form',
  extraFooterLeft = '',
  extraFooterStep = null,
  submitLabel = 'Save',
  maxWidth = '600px',
  mode = 'wizard', // 'wizard' | 'tabs'
}) {
  const totalSteps = steps.length;
  const isTabsMode = mode === 'tabs';
  const isWizard = !isTabsMode && totalSteps > 1;
  const lastStepIndex = totalSteps - 1;
  const footerStepIndex = extraFooterStep ?? lastStepIndex;

  let topNavigation = '';
  if (isTabsMode && totalSteps > 1) {
    topNavigation = `
      <div class="px-5 pt-3 pb-2.5 border-b border-subtle flex items-center gap-1.5 overflow-x-auto bg-surface">
        ${steps.map((s, i) => `
          <button type="button" class="tab-pill px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer select-none transition-all flex items-center gap-1.5 ${i === 0 ? 'bg-surface-elevated text-main border border-strong shadow-xs font-bold' : 'text-muted hover:text-main hover:bg-surface-hover border border-transparent'}" data-tab-pill="${i}">
            <span>${escapeHtml(s.label)}</span>
          </button>
        `).join('')}
      </div>
    `;
  } else if (isWizard) {
    topNavigation = `
      <div class="px-5 pt-4 pb-3 border-b border-subtle">
        <div class="flex items-center justify-between mb-2">
          ${steps.map((s, i) => `<span class="text-[12px] font-medium cursor-pointer select-none hover:opacity-80 transition-all ${i === 0 ? 'text-brand font-semibold' : 'text-faint'}" data-progress-label="${i}" title="Jump to ${escapeHtml(s.label)}">${escapeHtml(s.label)}</span>`).join('')}
        </div>
        <div class="h-1 bg-subtle rounded-full overflow-hidden">
          <div id="${formId}-progress-fill" class="h-full bg-brand transition-all duration-200" style="width: ${(1 / totalSteps * 100).toFixed(1)}%"></div>
        </div>
      </div>
    `;
  }

  openModal(`
    <div class="modal-dialog" style="max-width: ${maxWidth}">
      <div class="modal-header">
        <h3 class="font-bold text-lg">${escapeHtml(title)}</h3>
        <button class="btn btn-icon btn-secondary btn-sm" onclick="closeModal()"><i data-lucide="x" class="w-4 h-4"></i></button>
      </div>
      ${topNavigation}
      <form id="${formId}" class="flex flex-col flex-1 min-h-0">
        <div class="modal-body">
          ${steps.map((s, i) => `<div class="offcanvas-step ${i === 0 ? '' : 'hidden'}" data-step="${i}">${s.render()}</div>`).join('')}
        </div>
        <div class="modal-footer justify-between">
          <div class="flex items-center gap-2" id="${formId}-footer-left"></div>
          <div class="flex items-center gap-2">
            <button type="button" id="${formId}-btn-back" class="btn btn-secondary ${isTabsMode ? 'hidden' : 'hidden'}">
              <i data-lucide="arrow-left" class="w-4 h-4 mr-1"></i> Back
            </button>
            <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
            ${isWizard ? `<button type="button" id="${formId}-btn-next" class="btn btn-primary">Next Step <i data-lucide="arrow-right" class="w-4 h-4 ml-1"></i></button>` : ''}
            <button type="submit" id="${formId}-btn-submit" class="btn btn-primary ${isWizard ? 'hidden' : ''}">${escapeHtml(submitLabel)}</button>
          </div>
        </div>
      </form>
    </div>
  `);

  const form = document.getElementById(formId);
  const footerLeft = document.getElementById(`${formId}-footer-left`);

  const refresh = () => {
    const current = Number(form.querySelector('.offcanvas-step:not(.hidden)').dataset.step);
    
    if (isTabsMode) {
      document.querySelectorAll(`[data-tab-pill]`).forEach((el) => {
        const idx = Number(el.dataset.tabPill);
        const isActive = idx === current;
        el.className = `tab-pill px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer select-none transition-all flex items-center gap-1.5 ${
          isActive 
            ? 'bg-surface-elevated text-main border border-strong shadow-xs font-bold' 
            : 'text-muted hover:text-main hover:bg-surface-hover border border-transparent'
        }`;
      });
      footerLeft.innerHTML = extraFooterLeft || '';
    } else if (isWizard) {
      document.getElementById(`${formId}-btn-back`).classList.toggle('hidden', current === 0);
      document.getElementById(`${formId}-btn-next`).classList.toggle('hidden', current === lastStepIndex);
      document.getElementById(`${formId}-btn-submit`).classList.toggle('hidden', current !== lastStepIndex);
      const fill = document.getElementById(`${formId}-progress-fill`);
      if (fill) fill.style.width = `${((current + 1) / totalSteps * 100).toFixed(1)}%`;
      document.querySelectorAll(`[data-progress-label]`).forEach((el) => {
        const stepNum = Number(el.dataset.progressLabel);
        el.classList.toggle('text-brand', stepNum <= current);
        el.classList.toggle('font-bold', stepNum === current);
        el.classList.toggle('text-faint', stepNum > current);
      });
      footerLeft.innerHTML = current === footerStepIndex ? extraFooterLeft : '';
    } else {
      footerLeft.innerHTML = extraFooterLeft || '';
    }
    
    initPasswordToggles(form);
    if (window.lucide) lucide.createIcons();
  };

  const goToStep = (index) => {
    const stepsEls = form.querySelectorAll('.offcanvas-step');
    stepsEls.forEach((el) => el.classList.toggle('hidden', Number(el.dataset.step) !== index));
    refresh();
  };

  // Clickable tab pill navigation in tabs mode
  if (isTabsMode) {
    document.querySelectorAll(`[data-tab-pill]`).forEach((el) => {
      el.addEventListener('click', () => {
        goToStep(Number(el.dataset.tabPill));
      });
    });
  }

  // Clickable progress label navigation in wizard mode
  if (isWizard) {
    document.querySelectorAll(`[data-progress-label]`).forEach((el) => {
      el.addEventListener('click', () => {
        goToStep(Number(el.dataset.progressLabel));
      });
    });
    
    document.getElementById(`${formId}-btn-back`).addEventListener('click', () => {
      const current = Number(form.querySelector('.offcanvas-step:not(.hidden)').dataset.step);
      goToStep(Math.max(0, current - 1));
    });

    document.getElementById(`${formId}-btn-next`).addEventListener('click', () => {
      const current = form.querySelector('.offcanvas-step:not(.hidden)');
      const inputs = current.querySelectorAll('input, select, textarea');
      for (const el of inputs) {
        if (!el.checkValidity()) { el.reportValidity(); return; }
      }
      goToStep(Number(current.dataset.step) + 1);
    });
  }

  initAllCustomSelects(form);
  initPasswordToggles(form);
  refresh();
  return form;
}

export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}

export function formatCurrency(amount, currency = 'NGN') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount || 0);
}

// Shimmer skeleton shown while a page's first API call is in flight,
// standing in for a generic "Loading..." message. Roughly mimics a
// heading + stat row + table so the layout doesn't jump much once real
// content replaces it.
export function skeletonPage({ stats = 4, rows = 5 } = {}) {
  const statBlocks = Array.from({ length: stats }, () => `
    <div class="card p-5">
      <div class="shimmer shimmer-line w-24 mb-3"></div>
      <div class="shimmer shimmer-line w-16 h-6"></div>
    </div>
  `).join('');

  const rowBlocks = Array.from({ length: rows }, () => `
    <div class="flex items-center gap-4 px-4 py-3.5 border-b border-subtle last:border-b-0">
      <div class="shimmer shimmer-line w-1/4"></div>
      <div class="shimmer shimmer-line w-1/3"></div>
      <div class="shimmer shimmer-line w-16 ml-auto"></div>
    </div>
  `).join('');

  return `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <div class="shimmer shimmer-line w-48 h-5 mb-2"></div>
          <div class="shimmer shimmer-line w-64"></div>
        </div>
        <div class="shimmer shimmer-block w-28 h-8"></div>
      </div>
      ${stats > 0 ? `<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">${statBlocks}</div>` : ''}
      <div class="card p-0 overflow-hidden">${rowBlocks}</div>
    </div>
  `;
}

export function formatDate(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return dateStr;
  }
}

// Wizard Helpers (Globally attached for inline onclick)
window.nextWizardStep = function(formId) {
  const form = document.getElementById(formId);
  const current = form.querySelector('.wizard-step:not(.hidden)');
  
  // Validate current step
  const inputs = current.querySelectorAll('input, select, textarea');
  let valid = true;
  for (const i of inputs) {
    if (!i.checkValidity()) {
      i.reportValidity();
      valid = false;
      break;
    }
  }
  if (!valid) return;

  const next = current.nextElementSibling;
  if (next && next.classList.contains('wizard-step')) {
    current.classList.add('hidden');
    next.classList.remove('hidden');
    if (window.lucide) lucide.createIcons();
  }
};

window.prevWizardStep = function(formId) {
  const form = document.getElementById(formId);
  const current = form.querySelector('.wizard-step:not(.hidden)');
  const prev = current.previousElementSibling;
  if (prev && prev.classList.contains('wizard-step')) {
    current.classList.add('hidden');
    prev.classList.remove('hidden');
    if (window.lucide) lucide.createIcons();
  }
};

// ============================================================================
// Media Upload Helpers (Cloudinary / Cloudflare R2 / Fallback URL)
// ============================================================================

export async function uploadMediaFile(file) {
  const token = localStorage.getItem('commb_admin_token');
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch('/api/v1/settings/storage/upload', {
    method: 'POST',
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    body: formData,
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Upload failed');
  }
  return data.url;
}

export function renderImageUploadField({
  id = 'img-url',
  label = 'Image / Logo',
  value = '',
  storageConfigured = false,
  placeholder = 'https://...',
}) {
  const hasValue = Boolean(value);
  return `
    <div class="form-group" id="${id}-upload-wrapper">
      <div class="flex items-center justify-between mb-1.5">
        <label class="form-label">${escapeHtml(label)}</label>
        ${storageConfigured ? `
          <span class="text-[12px] text-emerald flex items-center gap-1 font-semibold">
            <i data-lucide="cloud" class="w-3.5 h-3.5"></i> Cloud Upload Ready
          </span>
        ` : `
          <span class="text-[12px] text-amber flex items-center gap-1 font-medium">
            <i data-lucide="alert-circle" class="w-3.5 h-3.5"></i> Storage Not Configured
          </span>
        `}
      </div>

      <div class="flex items-start gap-3.5">
        <!-- Thumbnail Preview -->
        <div id="${id}-preview-box" class="w-16 h-16 rounded-xl border border-subtle bg-surface-elevated/60 flex items-center justify-center overflow-hidden flex-shrink-0 relative group shadow-inner">
          ${hasValue ? `
            <img src="${escapeHtml(value)}" id="${id}-preview-img" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<i data-lucide=\\'image\\' class=\\'w-5 h-5 text-muted\\'></i>';" />
          ` : `
            <i data-lucide="image" class="w-5 h-5 text-muted" id="${id}-placeholder-icon"></i>
          `}
          <div id="${id}-spinner" class="absolute inset-0 bg-black/60 hidden flex items-center justify-center text-white">
            <i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i>
          </div>
        </div>

        <!-- Controls Area -->
        <div class="flex-1 space-y-2 min-w-0">
          ${storageConfigured ? `
            <div class="flex items-center gap-2">
              <label class="btn btn-secondary btn-sm cursor-pointer inline-flex items-center gap-1.5 text-xs py-1.5">
                <i data-lucide="upload" class="w-3.5 h-3.5 text-brand"></i>
                <span>Choose File</span>
                <input type="file" id="${id}-file-input" class="hidden" accept="image/*" />
              </label>
              <button type="button" class="btn btn-secondary btn-sm text-xs py-1.5 ${hasValue ? '' : 'hidden'}" id="${id}-clear-btn" onclick="window.clearImageUploadField('${id}')">
                <i data-lucide="trash-2" class="w-3.5 h-3.5 text-rose"></i> Clear
              </button>
            </div>
            <input type="text" id="${id}" class="form-control text-xs font-mono" placeholder="${escapeHtml(placeholder)}" value="${escapeHtml(value || '')}" />
          ` : `
            <input type="text" id="${id}" class="form-control text-xs font-mono" placeholder="${escapeHtml(placeholder)}" value="${escapeHtml(value || '')}" oninput="window.updateImageUploadPreview('${id}', this.value)" />
            <div class="text-[12px] text-amber flex items-start gap-1.5 mt-1 leading-normal bg-amber/5 p-2 rounded-lg border border-amber/10">
              <i data-lucide="info" class="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-amber"></i>
              <span>To enable direct drag-and-drop file uploads, set up Cloudinary or Cloudflare R2 in <a href="/_/admin/integrations" onclick="event.preventDefault(); closeModal(); navigate('/_/admin/integrations')" class="font-semibold underline hover:text-amber-300">Integrations &rarr; Storage & Media</a>.</span>
            </div>
          `}
        </div>
      </div>
    </div>
  `;
}

export function initImageUploadControl(id) {
  const fileInput = document.getElementById(`${id}-file-input`);
  const textInput = document.getElementById(id);
  const previewBox = document.getElementById(`${id}-preview-box`);
  const spinner = document.getElementById(`${id}-spinner`);
  const clearBtn = document.getElementById(`${id}-clear-btn`);

  if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const sp = document.getElementById(`${id}-spinner`);
      if (sp) sp.classList.remove('hidden');

      try {
        const url = await uploadMediaFile(file);
        if (textInput) textInput.value = url;
        if (previewBox) {
          previewBox.innerHTML = `
            <img src="${url}" id="${id}-preview-img" class="w-full h-full object-cover" />
            <div id="${id}-spinner" class="absolute inset-0 bg-black/60 hidden flex items-center justify-center text-white">
              <i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i>
            </div>
          `;
        }
        if (clearBtn) clearBtn.classList.remove('hidden');
        showToast('Image uploaded successfully', 'success');
      } catch (err) {
        showToast(err.message || 'Upload failed', 'error');
      } finally {
        const currentSp = document.getElementById(`${id}-spinner`);
        if (currentSp) currentSp.classList.add('hidden');
        if (window.lucide) lucide.createIcons();
      }
    });
  }

  if (textInput) {
    textInput.addEventListener('input', (e) => {
      window.updateImageUploadPreview(id, e.target.value);
    });
  }
}

window.clearImageUploadField = function(id) {
  const textInput = document.getElementById(id);
  const previewBox = document.getElementById(`${id}-preview-box`);
  const clearBtn = document.getElementById(`${id}-clear-btn`);
  if (textInput) textInput.value = '';
  if (clearBtn) clearBtn.classList.add('hidden');
  if (previewBox) {
    previewBox.innerHTML = `
      <i data-lucide="image" class="w-5 h-5 text-muted"></i>
      <div id="${id}-spinner" class="absolute inset-0 bg-black/60 hidden flex items-center justify-center text-white">
        <i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
  }
};

window.updateImageUploadPreview = function(id, url) {
  const previewBox = document.getElementById(`${id}-preview-box`);
  const clearBtn = document.getElementById(`${id}-clear-btn`);
  if (!previewBox) return;

  if (url && url.trim().startsWith('http')) {
    previewBox.innerHTML = `
      <img src="${url.trim()}" id="${id}-preview-img" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<i data-lucide=\\'image\\' class=\\'w-5 h-5 text-muted\\'></i>';" />
      <div id="${id}-spinner" class="absolute inset-0 bg-black/60 hidden flex items-center justify-center text-white">
        <i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i>
      </div>
    `;
    if (clearBtn) clearBtn.classList.remove('hidden');
  } else {
    previewBox.innerHTML = `
      <i data-lucide="image" class="w-5 h-5 text-muted"></i>
      <div id="${id}-spinner" class="absolute inset-0 bg-black/60 hidden flex items-center justify-center text-white">
        <i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i>
      </div>
    `;
    if (clearBtn) clearBtn.classList.add('hidden');
  }
  if (window.lucide) lucide.createIcons();
};

window.renderImageUploadField = renderImageUploadField;
window.initImageUploadControl = initImageUploadControl;
window.uploadMediaFile = uploadMediaFile;

/**
 * Initializes eye toggle buttons on password inputs.
 */
export function initPasswordToggles(container = document) {
  const btns = container.querySelectorAll('.password-toggle-btn');
  btns.forEach(btn => {
    if (btn.dataset.toggleBound) return;
    btn.dataset.toggleBound = 'true';
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = btn.dataset.target;
      const input = targetId ? document.getElementById(targetId) : btn.parentElement.querySelector('input');
      if (!input) return;

      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      btn.innerHTML = `<i data-lucide="${isPassword ? 'eye-off' : 'eye'}" class="w-4 h-4 text-muted hover:text-main transition-colors"></i>`;
      if (window.lucide) lucide.createIcons();
    });
  });
}

/**
 * Evaluates password strength and returns score & criteria.
 */
export function checkPasswordStrength(password = '') {
  const p = password || '';
  const lengthValid = p.length >= 8;
  const upperValid = /[A-Z]/.test(p);
  const lowerValid = /[a-z]/.test(p);
  const numOrSymbolValid = /[0-9]/.test(p);

  let score = 0;
  if (p.length >= 6) score += 1;
  if (lengthValid) score += 1;
  if (upperValid && lowerValid) score += 1;
  if (numOrSymbolValid) score += 1;

  let label = 'Too Weak';
  let color = 'rose';
  let barWidth = '25%';

  if (score <= 1) {
    label = 'Weak';
    color = 'rose';
    barWidth = '25%';
  } else if (score === 2) {
    label = 'Fair';
    color = 'amber';
    barWidth = '50%';
  } else if (score === 3) {
    label = 'Good';
    color = 'brand';
    barWidth = '75%';
  } else if (score >= 4) {
    label = 'Strong';
    color = 'emerald';
    barWidth = '100%';
  }

  const isStrong = lengthValid && score >= 3;

  return {
    score,
    label,
    color,
    barWidth,
    isStrong,
    requirements: {
      length: lengthValid,
      uppercase: upperValid,
      lowercase: lowerValid,
      numberOrSpecial: numOrSymbolValid,
    }
  };
}

/**
 * Renders the HTML markup for password strength meter and requirement checklist.
 */
export function renderPasswordStrengthMarkup(idPrefix = 'pwd') {
  return `
    <div id="${idPrefix}-strength-wrap" class="space-y-2 pt-1 hidden">
      <div class="flex items-center justify-between text-[12px]">
        <span class="text-muted">Password Security:</span>
        <span id="${idPrefix}-strength-label" class="font-semibold text-rose">Weak</span>
      </div>
      <div class="w-full bg-surface-elevated rounded-full h-1.5 overflow-hidden">
        <div id="${idPrefix}-strength-bar" class="h-full bg-rose transition-all duration-300 rounded-full" style="width: 25%"></div>
      </div>
      <div class="grid grid-cols-2 gap-x-2 gap-y-1 text-[12px] text-muted pt-1">
        <div id="${idPrefix}-req-length" class="flex items-center gap-1.5 transition-colors">
          <span class="w-1.5 h-1.5 rounded-full bg-subtle"></span> 8+ characters
        </div>
        <div id="${idPrefix}-req-upper" class="flex items-center gap-1.5 transition-colors">
          <span class="w-1.5 h-1.5 rounded-full bg-subtle"></span> Uppercase letter
        </div>
        <div id="${idPrefix}-req-lower" class="flex items-center gap-1.5 transition-colors">
          <span class="w-1.5 h-1.5 rounded-full bg-subtle"></span> Lowercase letter
        </div>
        <div id="${idPrefix}-req-num" class="flex items-center gap-1.5 transition-colors">
          <span class="w-1.5 h-1.5 rounded-full bg-subtle"></span> Number or symbol
        </div>
      </div>
    </div>
  `;
}

/**
 * Binds live password strength and confirm-match validation.
 */
export function bindPasswordValidator({
  passwordInputId,
  confirmInputId,
  submitBtnId,
  idPrefix = 'pwd',
  onValidate = () => {},
}) {
  const pwdInput = document.getElementById(passwordInputId);
  const confirmInput = document.getElementById(confirmInputId);
  const submitBtn = document.getElementById(submitBtnId);
  const strengthWrap = document.getElementById(`${idPrefix}-strength-wrap`);
  const strengthLabel = document.getElementById(`${idPrefix}-strength-label`);
  const strengthBar = document.getElementById(`${idPrefix}-strength-bar`);

  const reqLength = document.getElementById(`${idPrefix}-req-length`);
  const reqUpper = document.getElementById(`${idPrefix}-req-upper`);
  const reqLower = document.getElementById(`${idPrefix}-req-lower`);
  const reqNum = document.getElementById(`${idPrefix}-req-num`);

  function update() {
    const val = pwdInput?.value || '';
    const confirmVal = confirmInput?.value || '';

    if (strengthWrap) {
      strengthWrap.classList.toggle('hidden', val.length === 0);
    }

    const res = checkPasswordStrength(val);

    if (strengthLabel) {
      strengthLabel.textContent = res.label;
      strengthLabel.className = `font-semibold ${res.color === 'rose' ? 'text-rose' : res.color === 'amber' ? 'text-amber-500' : res.color === 'brand' ? 'text-brand' : 'text-emerald-500'}`;
    }

    if (strengthBar) {
      strengthBar.style.width = res.barWidth;
      strengthBar.className = `h-full transition-all duration-300 rounded-full ${res.color === 'rose' ? 'bg-rose' : res.color === 'amber' ? 'bg-amber-500' : res.color === 'brand' ? 'bg-brand' : 'bg-emerald-500'}`;
    }

    const updateReq = (el, valid) => {
      if (!el) return;
      const dot = el.querySelector('span');
      if (valid) {
        el.className = 'flex items-center gap-1.5 text-emerald-500 font-medium';
        if (dot) dot.className = 'w-1.5 h-1.5 rounded-full bg-emerald-500';
      } else {
        el.className = 'flex items-center gap-1.5 text-muted';
        if (dot) dot.className = 'w-1.5 h-1.5 rounded-full bg-subtle';
      }
    };

    updateReq(reqLength, res.requirements.length);
    updateReq(reqUpper, res.requirements.uppercase);
    updateReq(reqLower, res.requirements.lowercase);
    updateReq(reqNum, res.requirements.numberOrSpecial);

    // Password input outline validation
    if (pwdInput) {
      if (val.length > 0 && !res.isStrong) {
        pwdInput.classList.add('border-rose', 'focus:ring-rose');
        pwdInput.classList.remove('border-emerald', 'focus:ring-emerald');
      } else if (val.length > 0 && res.isStrong) {
        pwdInput.classList.remove('border-rose', 'focus:ring-rose');
        pwdInput.classList.add('border-emerald', 'focus:ring-emerald');
      } else {
        pwdInput.classList.remove('border-rose', 'focus:ring-rose', 'border-emerald', 'focus:ring-emerald');
      }
    }

    // Confirm password matching validation
    let matches = false;
    if (confirmInput) {
      if (confirmVal.length > 0) {
        matches = confirmVal === val;
        if (!matches) {
          confirmInput.classList.add('border-rose', 'focus:ring-rose');
          confirmInput.classList.remove('border-emerald', 'focus:ring-emerald');
        } else {
          confirmInput.classList.remove('border-rose', 'focus:ring-rose');
          confirmInput.classList.add('border-emerald', 'focus:ring-emerald');
        }
      } else {
        confirmInput.classList.remove('border-rose', 'focus:ring-rose', 'border-emerald', 'focus:ring-emerald');
      }
    }

    const isValid = res.isStrong && matches;

    if (submitBtn) {
      submitBtn.disabled = !isValid;
      if (!isValid) {
        submitBtn.classList.add('opacity-50', 'cursor-not-allowed');
      } else {
        submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
      }
    }

    onValidate({ isValid, isStrong: res.isStrong, matches, score: res.score });
  }

  if (pwdInput) {
    pwdInput.addEventListener('input', update);
    pwdInput.addEventListener('keyup', update);
  }
  if (confirmInput) {
    confirmInput.addEventListener('input', update);
    confirmInput.addEventListener('keyup', update);
  }

  update();
}

window.initPasswordToggles = initPasswordToggles;
window.checkPasswordStrength = checkPasswordStrength;
window.renderPasswordStrengthMarkup = renderPasswordStrengthMarkup;
window.bindPasswordValidator = bindPasswordValidator;



