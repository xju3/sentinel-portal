export const SESSION_KEY = 'portal_session';

export type PortalSession = {
  access_token: string;
  token_type: string;
  expires_in: number;
  account_id: string;
  username: string;
  tenant_id: string;
  tenant_name?: string;
  contact_id?: string;
  contact_name?: string;
  flag: number;
};

export function getSession(): PortalSession | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as PortalSession;
    if (!parsed?.access_token) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return parsed;
  } catch {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      // ignore storage errors
    }
    return null;
  }
}

export function saveSession(session: PortalSession) {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.removeItem(SESSION_KEY);
}
