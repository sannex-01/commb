/**
 * Custom Select Component for CommB Admin UI
 * Provides theme-aware, searchable, accessible custom dropdowns
 * with instant two-way synchronization with native <select> elements.
 */

import { escapeHtml } from '../utils.js';

export function createCustomSelect({
  container,
  id,
  name,
  value = '',
  options = [],
  placeholder = 'Select an option',
  searchable = null,
  disabled = false,
  onChange = null,
}) {
  const el = typeof container === 'string' ? document.querySelector(container) : container;
  if (!el) return null;

  const isSearchable = searchable !== null ? searchable : options.length > 5;
  let currentValue = value !== undefined && value !== null ? String(value) : '';
  let currentOptions = [...options];
  let isOpen = false;
  let searchFilter = '';
  let highlightedIndex = -1;

  const selectId = id || `custom-select-${Math.random().toString(36).substring(2, 9)}`;

  el.innerHTML = `
    <div class="custom-select" id="${selectId}">
      <input type="hidden" name="${name || ''}" value="${escapeHtml(currentValue)}" />
      <button type="button" class="custom-select-trigger ${disabled ? 'disabled' : ''}" aria-haspopup="listbox" aria-expanded="false" ${disabled ? 'disabled' : ''}>
        <div class="custom-select-value"></div>
        <i data-lucide="chevron-down" class="custom-select-icon"></i>
      </button>
      <div class="custom-select-dropdown" style="display: none;">
        ${isSearchable ? `
        <div class="custom-select-search">
          <input type="text" class="custom-select-search-input" placeholder="Search..." autocomplete="off" />
        </div>
        ` : ''}
        <div class="custom-select-options" role="listbox"></div>
      </div>
    </div>
  `;

  const root = el.querySelector(`#${selectId}`);
  const hiddenInput = root.querySelector('input[type="hidden"]');
  const trigger = root.querySelector('.custom-select-trigger');
  const valueDisplay = root.querySelector('.custom-select-value');
  const dropdown = root.querySelector('.custom-select-dropdown');
  const searchInput = root.querySelector('.custom-select-search-input');
  const optionsList = root.querySelector('.custom-select-options');

  function renderValue() {
    const selected = currentOptions.find(o => String(o.value) === String(currentValue));
    if (selected) {
      valueDisplay.innerHTML = `
        ${selected.icon ? `<i data-lucide="${selected.icon}" class="w-4 h-4 flex-shrink-0 text-muted"></i>` : ''}
        <span class="truncate font-medium text-main">${escapeHtml(selected.label || selected.value)}</span>
        ${selected.badge ? `<span class="badge badge-subtle ml-auto text-[12px]">${escapeHtml(selected.badge)}</span>` : ''}
      `;
    } else {
      valueDisplay.innerHTML = `<span class="placeholder">${escapeHtml(placeholder)}</span>`;
    }
    if (window.lucide) lucide.createIcons();
  }

  function getFilteredOptions() {
    if (!searchFilter) return currentOptions;
    const term = searchFilter.toLowerCase();
    return currentOptions.filter(o => 
      (o.label || '').toLowerCase().includes(term) || 
      (String(o.value) || '').toLowerCase().includes(term) ||
      (o.description || '').toLowerCase().includes(term)
    );
  }

  function renderOptions() {
    const filtered = getFilteredOptions();
    if (filtered.length === 0) {
      optionsList.innerHTML = `<div class="custom-select-empty">No matching options</div>`;
      return;
    }

    optionsList.innerHTML = filtered.map((opt, idx) => {
      const isSelected = String(opt.value) === String(currentValue);
      const isHigh = idx === highlightedIndex;
      return `
        <div class="custom-select-option ${isSelected ? 'selected' : ''} ${isHigh ? 'highlighted' : ''}" data-value="${escapeHtml(String(opt.value))}" role="option" aria-selected="${isSelected}">
          <div class="option-label">
            ${opt.icon ? `<i data-lucide="${opt.icon}" class="w-3.5 h-3.5 flex-shrink-0 text-muted"></i>` : ''}
            <div class="min-w-0">
              <div class="text-main leading-snug truncate">${escapeHtml(opt.label || opt.value)}</div>
              ${opt.description ? `<div class="text-[12px] text-muted truncate">${escapeHtml(opt.description)}</div>` : ''}
            </div>
            ${opt.badge ? `<span class="badge badge-subtle ml-auto text-[12px]">${escapeHtml(opt.badge)}</span>` : ''}
          </div>
          <i data-lucide="check" class="option-check"></i>
        </div>
      `;
    }).join('');

    if (window.lucide) lucide.createIcons();

    optionsList.querySelectorAll('.custom-select-option').forEach(optEl => {
      optEl.addEventListener('click', (e) => {
        e.stopPropagation();
        const val = optEl.getAttribute('data-value');
        setValue(val, true);
        close();
      });
    });
  }

  function open() {
    if (disabled || isOpen) return;
    
    // Close other open selects
    document.querySelectorAll('.custom-select.open').forEach(s => {
      if (s !== root && s._closeSelect) s._closeSelect();
    });

    isOpen = true;
    root.classList.add('open');
    trigger.setAttribute('aria-expanded', 'true');
    dropdown.style.display = 'flex';

    // Position check (flip up if near bottom edge of screen)
    const rect = trigger.getBoundingClientRect();
    const dropdownHeight = 250;
    const spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow < dropdownHeight && rect.top > dropdownHeight) {
      root.classList.add('drop-up');
    } else {
      root.classList.remove('drop-up');
    }

    searchFilter = '';
    if (searchInput) {
      searchInput.value = '';
      setTimeout(() => searchInput.focus(), 50);
    }

    highlightedIndex = currentOptions.findIndex(o => String(o.value) === String(currentValue));
    renderOptions();
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    root.classList.remove('open');
    root.classList.remove('drop-up');
    trigger.setAttribute('aria-expanded', 'false');
    dropdown.style.display = 'none';
  }

  root._closeSelect = close;

  function setValue(newVal, triggerEvent = true) {
    currentValue = newVal !== undefined && newVal !== null ? String(newVal) : '';
    hiddenInput.value = currentValue;
    renderValue();
    if (isOpen) renderOptions();

    if (triggerEvent) {
      hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
      if (typeof onChange === 'function') {
        const selectedObj = currentOptions.find(o => String(o.value) === String(currentValue));
        onChange(currentValue, selectedObj);
      }
    }
  }

  // Events
  trigger.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isOpen) close();
    else open();
  });

  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      searchFilter = e.target.value;
      highlightedIndex = 0;
      renderOptions();
    });
    searchInput.addEventListener('keydown', (e) => {
      const filtered = getFilteredOptions();
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        highlightedIndex = Math.min(highlightedIndex + 1, filtered.length - 1);
        renderOptions();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlightedIndex = Math.max(highlightedIndex - 1, 0);
        renderOptions();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filtered[highlightedIndex]) {
          setValue(filtered[highlightedIndex].value, true);
          close();
        }
      } else if (e.key === 'Escape') {
        close();
        trigger.focus();
      }
    });
  }

  // Global document click to close
  function onDocClick(e) {
    if (!root.contains(e.target)) {
      close();
    }
  }
  document.addEventListener('click', onDocClick);

  // Initial render
  renderValue();

  return {
    root,
    hiddenInput,
    getValue: () => currentValue,
    setValue,
    setOptions: (newOpts, keepValue = true) => {
      currentOptions = [...newOpts];
      if (!keepValue || !currentOptions.some(o => String(o.value) === String(currentValue))) {
        currentValue = currentOptions[0] ? String(currentOptions[0].value) : '';
      }
      setValue(currentValue, false);
    },
    enable: () => {
      disabled = false;
      trigger.disabled = false;
      trigger.classList.remove('disabled');
    },
    disable: () => {
      disabled = true;
      trigger.disabled = true;
      trigger.classList.add('disabled');
      close();
    },
    destroy: () => {
      document.removeEventListener('click', onDocClick);
      el.innerHTML = '';
    }
  };
}

/**
 * Enhances an existing native <select> element in place.
 * Hides the native element and mounts custom select right next to it, keeping values in sync.
 */
export function enhanceSelect(nativeSelect, customOpts = {}) {
  if (!nativeSelect || nativeSelect._customSelectInstance) return nativeSelect._customSelectInstance;

  const selectEl = typeof nativeSelect === 'string' ? document.querySelector(nativeSelect) : nativeSelect;
  if (!selectEl || selectEl.tagName !== 'SELECT') return null;

  // Extract options from native select
  const rawOptions = Array.from(selectEl.options).map(opt => ({
    value: opt.value,
    label: opt.textContent.trim(),
    disabled: opt.disabled,
  }));

  const placeholder = selectEl.getAttribute('placeholder') || (rawOptions[0]?.value === '' ? rawOptions[0].label : 'Select an option');
  const isSearchable = selectEl.getAttribute('data-searchable') !== null 
    ? selectEl.getAttribute('data-searchable') === 'true' 
    : rawOptions.length > 5;

  // Create wrapper container
  const wrapper = document.createElement('div');
  wrapper.className = 'custom-select-wrapper';
  selectEl.parentNode.insertBefore(wrapper, selectEl);
  selectEl.style.display = 'none';

  const instance = createCustomSelect({
    container: wrapper,
    id: selectEl.id ? `cs-${selectEl.id}` : null,
    name: selectEl.name || '',
    value: selectEl.value,
    options: rawOptions,
    placeholder,
    searchable: isSearchable,
    disabled: selectEl.disabled,
    onChange: (val) => {
      selectEl.value = val;
      selectEl.dispatchEvent(new Event('change', { bubbles: true }));
      selectEl.dispatchEvent(new Event('input', { bubbles: true }));
    },
    ...customOpts
  });

  // Watch native select changes
  selectEl.addEventListener('change', () => {
    if (instance.getValue() !== selectEl.value) {
      instance.setValue(selectEl.value, false);
    }
  });

  selectEl._customSelectInstance = instance;
  return instance;
}

/**
 * Automatically scans and enhances all <select class="form-control"> within container
 */
export function initAllCustomSelects(root = document) {
  const selects = root.querySelectorAll('select.form-control:not([data-no-custom])');
  selects.forEach(sel => {
    if (!sel._customSelectInstance) {
      enhanceSelect(sel);
    }
  });
}
