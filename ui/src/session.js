import { useSyncExternalStore } from 'react';

// Who is logged in. `authEnabled` is false in single-user mode (no users configured on the server).
let state = { loaded: false, authEnabled: false, user: null };
const listeners = new Set();
const emit = () => listeners.forEach((l) => l());

export async function loadSession() {
  try {
    const r = await fetch('/api/auth/me');
    const me = await r.json();
    state = { loaded: true, authEnabled: me.auth_enabled, user: me.user };
  } catch {
    state = { ...state, loaded: true };
  }
  emit();
  return state;
}

export async function login(username, password) {
  const r = await fetch('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  state = { loaded: true, authEnabled: true, user: body.user };
  emit();
}

export async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
  state = { ...state, user: null };
  emit();
}

export function useSession() {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => state);
}

const ROLES = ['VIEWER', 'ANALYST', 'SUPERVISOR', 'ADMIN'];
export const hasRole = (user, role) => !!user && ROLES.indexOf(user.role) >= ROLES.indexOf(role);

// Any API call rejected with 401 (session expired) sends the user back to the login screen.
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const res = await nativeFetch(input, init);
  const url = typeof input === 'string' ? input : input.url;
  if (res.status === 401 && url.startsWith('/api/') && !url.startsWith('/api/auth/') && state.user) {
    state = { ...state, user: null };
    emit();
  }
  return res;
};
