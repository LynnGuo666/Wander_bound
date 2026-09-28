export function sessionToken() {
  try { return sessionStorage.getItem('travel-session') || ''; } catch { return ''; }
}

export function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = sessionToken();
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
  return fetch(path, { ...options, headers });
}
