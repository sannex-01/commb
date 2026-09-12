// State Management
export const state = {
  user: null,
  business: null,
  apiKeyInfo: null,
  appVersion: '0.2.1',
  appName: 'CommB Assistant',
  support: null,
  route: window.location.pathname || '/_/admin/overview',
  theme: localStorage.getItem('commb_theme') || 'light',
  sidebarCollapsed: localStorage.getItem('commb_sidebar_collapsed') === 'true',
};

// Apply Theme
export function applyTheme(theme) {
  state.theme = theme;
  localStorage.setItem('commb_theme', theme);
  document.documentElement.className = theme;
}

// Initial theme application
applyTheme(state.theme);
