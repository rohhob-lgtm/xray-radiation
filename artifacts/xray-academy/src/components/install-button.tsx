import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';

// "Install app" button for the PWA. Chrome/Edge/Android fire
// `beforeinstallprompt`; we capture it and show a button that triggers the
// native install dialog. Hidden once installed or when already running
// standalone. (iOS Safari has no prompt event — users install via
// Share → Add to Home Screen; a hint is shown there instead.)
export function InstallButton() {
  const [deferred, setDeferred] = useState<any>(null);
  const [hide, setHide] = useState(false);

  useEffect(() => {
    const standalone =
      window.matchMedia?.('(display-mode: standalone)').matches ||
      (window.navigator as any).standalone === true;
    if (standalone) { setHide(true); return; }
    const onPrompt = (e: any) => { e.preventDefault(); setDeferred(e); };
    const onInstalled = () => { setHide(true); setDeferred(null); };
    window.addEventListener('beforeinstallprompt', onPrompt);
    window.addEventListener('appinstalled', onInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, []);

  if (hide || !deferred) return null;

  const install = async () => {
    try {
      deferred.prompt();
      await deferred.userChoice;
    } catch {}
    setDeferred(null);
  };

  return (
    <button
      onClick={install}
      className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
      title="Install Smart Translation AI as an app"
    >
      <Download className="h-3.5 w-3.5" /> Install app
    </button>
  );
}
