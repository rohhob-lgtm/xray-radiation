import { useEffect, useState } from 'react';
import { LogIn, LogOut, Sparkles } from 'lucide-react';

// Shows the free-tier allowance + a Google sign-in button. Renders nothing when
// the tiered auth model is off (auth_enabled=false), so the open launch is
// unaffected until Google credentials are configured.

interface Quota {
  enabled: boolean;
  authenticated: boolean;
  is_admin: boolean;
  tier: string;
  used: number;
  limit: number;
  remaining: number;
  email?: string | null;
}

export function AuthQuotaBar() {
  const [q, setQ] = useState<Quota | null>(null);

  useEffect(() => {
    fetch('/api/auth/user', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setQ(d?.quota ?? null))
      .catch(() => setQ(null));
  }, []);

  if (!q || !q.enabled) return null;

  const signIn = () => {
    const back = encodeURIComponent(window.location.pathname || '/translation');
    window.location.href = `/api/auth/google/login?returnTo=${back}`;
  };

  const exitAdmin = async () => {
    try { await fetch('/api/auth/admin-logout', { method: 'POST', credentials: 'include' }); } catch {}
    try { localStorage.removeItem('ts_admin'); localStorage.removeItem('ts_preview_public'); } catch {}
    window.location.href = '/';
  };

  if (q.is_admin) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card/40 px-4 py-2.5">
        <span className="text-sm text-muted-foreground">Admin mode — unlimited translations.</span>
        <button
          onClick={exitAdmin}
          className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-muted shrink-0"
        >
          <LogOut className="h-4 w-4" /> Exit admin
        </button>
      </div>
    );
  }

  const plural = q.remaining === 1 ? 'translation' : 'translations';

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card/40 px-4 py-2.5">
      <div className="flex items-center gap-2 text-sm">
        <Sparkles className="h-4 w-4 text-primary shrink-0" />
        {q.authenticated ? (
          <span className="text-muted-foreground">
            {q.email ? <span className="text-foreground font-medium">{q.email}</span> : 'Your account'} ·
            {' '}<span className="font-bold text-foreground">{q.remaining}</span> of {q.limit} free {plural} left
          </span>
        ) : (
          <span className="text-muted-foreground">
            You have <span className="font-bold text-foreground">{q.remaining}</span> free {plural} —
            sign in with Google for more
          </span>
        )}
      </div>
      {!q.authenticated && (
        <button
          onClick={signIn}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 shrink-0"
        >
          <LogIn className="h-4 w-4" /> Sign in with Google
        </button>
      )}
    </div>
  );
}
