import { useSyncExternalStore } from "react";

// Session store. Access + refresh tokens in memory + localStorage so a refresh
// keeps you in. (Prototype: localStorage is acceptable; production should prefer
// HttpOnly cookies — see roadmap Phase E.)
const ACCESS_KEY = "afm.token";
const REFRESH_KEY = "afm.refresh";
const ROLE_KEY = "afm.role";

let token: string | null = localStorage.getItem(ACCESS_KEY);
let refresh: string | null = localStorage.getItem(REFRESH_KEY);
let role: string | null = localStorage.getItem(ROLE_KEY);

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function getToken(): string | null {
  return token;
}

export function getRefreshToken(): string | null {
  return refresh;
}

export function setSession(newAccess: string, newRefresh: string, newRole: string): void {
  token = newAccess;
  refresh = newRefresh;
  role = newRole;
  localStorage.setItem(ACCESS_KEY, newAccess);
  localStorage.setItem(REFRESH_KEY, newRefresh);
  localStorage.setItem(ROLE_KEY, newRole);
  emit();
}

/** Replace just the access token after a refresh (keeps refresh token + role). */
export function setAccessToken(newAccess: string): void {
  token = newAccess;
  localStorage.setItem(ACCESS_KEY, newAccess);
  emit();
}

export function clearSession(): void {
  token = refresh = role = null;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(ROLE_KEY);
  emit();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useAuth() {
  const t = useSyncExternalStore(subscribe, () => token);
  return { token: t, role, isAuthed: t !== null, logout: clearSession };
}
