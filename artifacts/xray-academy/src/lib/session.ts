// Anonymous session isolation for the Persistent AI Memory System.
//
// Not-logged-in visitors are never scoped to a shared user_id=NULL bucket
// server-side — each browser gets its own UUID, generated once and kept in
// localStorage, sent as X-Anon-Session-Id on every API call. Authenticated
// requests ignore this header entirely (the backend resolves identity from
// the session cookie first — see api.services.identity.get_identity).

const STORAGE_KEY = 'xray_anon_session_id';

export const ANON_SESSION_HEADER = 'X-Anon-Session-Id';

let cached: string | null = null;

export function getAnonSessionId(): string {
  if (cached) return cached;
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing) {
      cached = existing;
      return existing;
    }
    const id = crypto.randomUUID();
    window.localStorage.setItem(STORAGE_KEY, id);
    cached = id;
    return id;
  } catch {
    // localStorage unavailable (private browsing, etc.) — fall back to an
    // in-memory id for this page load; isolation still holds within the tab.
    if (!cached) cached = crypto.randomUUID();
    return cached;
  }
}

/** Merge the anon-session header into an existing fetch headers object/init. */
export function withAnonSessionHeader(headers: HeadersInit = {}): HeadersInit {
  return { ...headers, [ANON_SESSION_HEADER]: getAnonSessionId() };
}
