import { ReactNode, useState } from 'react';
import { Sidebar } from './sidebar';
import { Menu, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { isAdminUnlocked, isPreviewingPublic } from '@/lib/config';

export function Layout({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const previewing = isAdminUnlocked() && isPreviewingPublic();

  return (
    <>
      {/* Admin previewing the public UI — a persistent way back to admin. */}
      {previewing && (
        <div className="fixed top-0 inset-x-0 z-[100] flex items-center justify-center gap-3 bg-amber-500 text-black text-xs font-semibold px-4 py-1.5 shadow">
          <span className="flex items-center gap-1.5"><Eye className="h-3.5 w-3.5" /> Previewing as a public user</span>
          <button
            className="underline underline-offset-2 hover:opacity-80"
            onClick={() => { try { localStorage.removeItem('ts_preview_public'); } catch {} window.location.href = '/translation'; }}
          >
            Back to admin
          </button>
        </div>
      )}
    <div className="flex h-[100dvh] w-full overflow-hidden bg-background">
      {/* Desktop Sidebar */}
      <div className="hidden md:flex flex-col w-[220px] lg:w-[260px] border-r border-border bg-sidebar shrink-0">
        <Sidebar />
      </div>

      {/* Mobile Sidebar Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <div className="fixed inset-0 bg-background/80 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <div className="relative z-50 w-[260px] max-w-[80%] h-full bg-sidebar border-r border-border flex flex-col shadow-2xl animate-in slide-in-from-left">
            <Sidebar onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        <div className="md:hidden flex items-center border-b border-border px-4 bg-card h-14 shrink-0">
          <Button variant="ghost" size="icon" onClick={() => setMobileOpen(true)} className="-ml-2 mr-2" data-testid="button-mobile-menu">
            <Menu className="h-5 w-5" />
          </Button>
          <h1 className="font-bold text-lg tracking-tight truncate">X-Ray Research</h1>
        </div>
        <div className="flex-1 overflow-auto bg-background relative flex flex-col">
          {children}
        </div>
      </main>
    </div>
    </>
  );
}
