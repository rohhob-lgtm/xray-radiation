import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ShieldCheck, Loader2, LogOut, Eye, EyeOff } from 'lucide-react';
import { isAdminUnlocked } from '@/lib/config';

// Admin unlock door. Reachable at /admin even in public (locked) mode. Entering
// the correct ADMIN_KEY flags the backend session is_admin and stores a local
// flag, then reloads into the full admin control panel.
export default function AdminPage() {
  const [key, setKey] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const unlocked = isAdminUnlocked();

  const login = async () => {
    setBusy(true);
    setErr('');
    try {
      const r = await fetch('/api/auth/admin-login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      });
      if (r.ok) {
        localStorage.setItem('ts_admin', '1');
        window.location.href = '/translation';
      } else {
        const d = await r.json().catch(() => ({}));
        setErr(d.detail || 'Incorrect admin key.');
      }
    } catch {
      setErr('Network error — is the server running?');
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    try {
      await fetch('/api/auth/admin-logout', { method: 'POST', credentials: 'include' });
    } catch {}
    localStorage.removeItem('ts_admin');
    window.location.href = '/translation';
  };

  return (
    <div className="flex-1 flex items-center justify-center p-6 bg-background">
      <div className="w-full max-w-sm border border-border bg-card rounded-2xl shadow-2xl shadow-black/40 p-8 flex flex-col items-center">
        <div className="h-16 w-16 rounded-full bg-primary/10 ring-1 ring-primary/30 flex items-center justify-center mb-5">
          <ShieldCheck className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-xl font-bold text-foreground">Admin Access</h1>
        <p className="text-sm text-muted-foreground text-center mt-1 mb-6">
          {unlocked
            ? 'Admin mode is active on this browser.'
            : 'Enter the admin key to unlock the full control panel.'}
        </p>

        {unlocked ? (
          <Button variant="outline" className="w-full gap-2" onClick={logout}>
            <LogOut className="h-4 w-4" /> Exit admin mode
          </Button>
        ) : (
          <div className="w-full space-y-3">
            <div className="relative">
              <Input
                type={show ? 'text' : 'password'}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && key && !busy && login()}
                placeholder="Admin key"
                autoFocus
                className="pr-10"
                data-testid="input-admin-key"
              />
              <button
                type="button"
                onClick={() => setShow((s) => !s)}
                aria-label={show ? 'Hide admin key' : 'Show admin key'}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {err && <p className="text-xs text-red-400">{err}</p>}
            <Button className="w-full gap-2" disabled={!key || busy} onClick={login} data-testid="button-admin-login">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Unlock admin panel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
