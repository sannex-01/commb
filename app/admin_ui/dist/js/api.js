import { navigate } from './router.js';
import { showToast } from './utils.js';

// API Helper
export async function api(path, options = {}) {
  const token = localStorage.getItem('commb_admin_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  try {
    const res = await fetch(`/api/v1${path}`, { ...options, headers });
    if (res.status === 401 && !path.startsWith('/auth/login') && !path.startsWith('/setup')) {
      localStorage.removeItem('commb_admin_token');
      navigate('/_/admin/login');
      throw new Error('Session expired. Please log in.');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || data.message || 'API request failed');
    }
    return data;
  } catch (err) {
    showToast(err.message, 'error');
    throw err;
  }
}
