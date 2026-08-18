import { Link, useLocation } from 'wouter';
import { PUBLIC_MODE } from '@/lib/config';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { 
  Shield, 
  MessageSquare, 
  Image as ImageIcon, 
  Linkedin, 
  BookOpen, 
  Settings, 
  Trash2, 
  LogOut,
  Eye,
  Loader2,
  Grid,
  FlaskConical,
  ShieldCheck,
  FileText,
  GraduationCap,
  Network,
  Images,
  Lightbulb,
  BookMarked,
  Languages,
  Atom,
  TestTube2,
  BarChart2,
  Brain,
  DollarSign,
  LayoutDashboard,
  Plug
} from 'lucide-react';
import { useListConversations, useDeleteConversation, getListConversationsQueryKey } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@workspace/replit-auth-web';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useEffect, useState } from 'react';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

type UIProvider = {
  id: string;
  name: string;
  is_active: boolean;
};

function normalizeProviders(raw: unknown): UIProvider[] {
  const list = Array.isArray(raw) ? raw : [];
  const rows: UIProvider[] = [];
  for (const item of list) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const id = String(row.id || '').trim();
    if (!id) continue;
    rows.push({
      id,
      name: String(row.name || id),
      is_active: Boolean(row.is_active),
    });
  }
  return rows;
}

function useSearchParam(key: string) {
  const [value, setValue] = useState<string | null>(
    new URLSearchParams(window.location.search).get(key)
  );

  useEffect(() => {
    const handlePopState = () => setValue(new URLSearchParams(window.location.search).get(key));
    window.addEventListener('popstate', handlePopState);
    const interval = setInterval(handlePopState, 200);
    return () => {
      window.removeEventListener('popstate', handlePopState);
      clearInterval(interval);
    }
  }, [key]);

  return value;
}

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const [location, setLocation] = useLocation();
  const convId = useSearchParam('id');
  const { data: conversations, isLoading: isLoadingConversations } = useListConversations();
  const [providers, setProviders] = useState<UIProvider[]>([]);
  const activeProvider = providers.find(p => p.is_active) || null;
  const queryClient = useQueryClient();
  const { user, logout } = useAuth();

  useEffect(() => {
    let cancelled = false;
    const loadProviders = async () => {
      try {
        const response = await fetch(`${API}/api/providers`, {
          method: 'GET',
          credentials: 'include',
          cache: 'no-store',
        });
        if (!response.ok) return;
        const data = await response.json();
        if (!cancelled) setProviders(normalizeProviders(data));
      } catch {
        if (!cancelled) setProviders([]);
      }
    };
    void loadProviders();
    return () => {
      cancelled = true;
    };
  }, []);
  
  const { mutate: deleteConversation, isPending: isDeleting } = useDeleteConversation({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListConversationsQueryKey() });
      }
    }
  });

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    deleteConversation({ conversationId: id });
    if (convId === id) {
      setLocation('/chat');
    }
  };

  // Translation Studio clone — navigation scoped to the translation feature.
  const navGroups = [
    {
      label: 'TRANSLATION',
      items: [
        { href: '/translation', icon: Languages, label: 'Translation Studio', exact: true },
        // Dashboard, Glossary & Memory and Cost & Usage hold internal data — admin-only.
        ...(PUBLIC_MODE ? [] : [
          { href: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
          { href: '/translation-dictionary', icon: BookMarked, label: 'Glossary & Memory' },
          { href: '/translation/cost', icon: BarChart2, label: 'Cost & Usage' },
        ]),
      ]
    },
    {
      label: 'SYSTEM',
      items: [
        // Settings is admin-only; hidden from public users. When admin mode is
        // unlocked, also surface the Admin page (to exit admin mode).
        ...(PUBLIC_MODE ? [] : [
          { href: '/settings', icon: Settings, label: 'Settings' },
          { href: '/admin', icon: ShieldCheck, label: 'Admin' },
        ]),
      ]
    }
  ].filter(g => g.items.length > 0);

  const NavItemRender = ({ item }: { item: any }) => {
    const isActive = item.exact 
      ? location === item.href && !convId 
      : location.startsWith(item.href) || (item.href === '/chat' && convId);

    return (
      <Link
        href={item.href}
        onClick={onClose}
        className={`flex items-center gap-3 px-3 py-2 text-sm rounded-md transition-colors ${
          isActive
            ? 'bg-primary text-primary-foreground font-medium shadow-sm'
            : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'
        }`}
        data-testid={`link-nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
      >
        <item.icon className="h-4 w-4 shrink-0" />
        <span>{item.label}</span>
      </Link>
    );
  };

  return (
    <div className="flex flex-col h-full bg-sidebar">
      {/* Header */}
      <div className="p-4 flex flex-col gap-3 border-b border-sidebar-border shrink-0">
        <Link href="/" onClick={onClose} className="flex items-center gap-3 text-sidebar-foreground hover:opacity-80 transition-opacity">
          <div className="h-8 w-8 rounded bg-primary/20 flex items-center justify-center ring-1 ring-primary/30">
            <Shield className="h-5 w-5 text-primary" />
          </div>
          <div className="flex flex-col">
            <span className="font-bold tracking-tight text-sm leading-tight uppercase">Smart Translation AI</span>
            <span className="text-[10px] text-muted-foreground font-mono tracking-widest leading-tight uppercase mt-0.5">Technical · Engineering</span>
          </div>
        </Link>
        {!PUBLIC_MODE && activeProvider && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-sidebar-accent/50 border border-sidebar-border/50">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">Provider: {activeProvider.name}</span>
          </div>
        )}
      </div>

      <ScrollArea className="flex-1 px-3 py-4">
        <div className="flex flex-col gap-6">
          {navGroups.map((group, i) => (
            <div key={i} className="flex flex-col gap-1">
              {group.label && (
                <div className="text-[10px] font-mono font-bold text-muted-foreground/70 px-2 uppercase tracking-widest mb-1">
                  {group.label}
                </div>
              )}
              {group.items.map(item => <NavItemRender key={item.href} item={item} />)}
            </div>
          ))}

          {/* Conversation List (Only show if we're in chat) */}
          {location === '/chat' && (
            <div className="flex flex-col gap-1 pt-4 border-t border-sidebar-border/50">
              <div className="flex items-center justify-between px-2 mb-2">
                <span className="text-[10px] font-mono font-bold text-muted-foreground/70 uppercase tracking-widest">
                  Recent Sessions
                </span>
                <Link href="/chat" onClick={onClose} className="text-[10px] text-primary hover:underline">
                  + New
                </Link>
              </div>
              
              {isLoadingConversations ? (
                <div className="flex items-center justify-center p-4">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : conversations?.length === 0 ? (
                <div className="px-2 text-xs text-muted-foreground italic">No recent sessions</div>
              ) : (
                conversations?.map((conv) => {
                  const isActive = location === '/chat' && convId === conv.id;
                  return (
                    <Link 
                      key={conv.id} 
                      href={`/chat?id=${conv.id}`}
                      onClick={onClose}
                      className={`group relative flex items-center gap-2 px-2 py-2 text-sm rounded-md transition-colors ${
                        isActive 
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium' 
                          : 'text-muted-foreground hover:bg-sidebar-accent/50 hover:text-foreground'
                      }`}
                      data-testid={`link-conversation-${conv.id}`}
                    >
                      <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-70" />
                      <div className="flex flex-col flex-1 min-w-0">
                        <span className="truncate text-xs">{conv.title || 'Untitled Session'}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 opacity-0 group-hover:opacity-100 shrink-0 hover:bg-destructive/20 hover:text-destructive absolute right-1"
                        onClick={(e) => handleDelete(e, conv.id)}
                        disabled={isDeleting}
                        data-testid={`button-delete-conv-${conv.id}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </Link>
                  );
                })
              )}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Bottom card — admin only. Public users get no user card / exit control. */}
      {!PUBLIC_MODE && (
        <div className="p-3 border-t border-sidebar-border shrink-0 space-y-2">
          <div className="flex items-center gap-3 px-2 py-2 rounded-md bg-card/50 border border-border/50">
            <Avatar className="h-8 w-8 rounded-md bg-primary/20 border border-primary/20">
              <AvatarImage src={user?.profile_image || undefined} />
              <AvatarFallback className="rounded-md bg-transparent text-primary text-xs font-bold">
                {user?.name?.substring(0, 2).toUpperCase() || 'AD'}
              </AvatarFallback>
            </Avatar>
            <div className="flex flex-col flex-1 min-w-0">
              <span className="text-sm font-medium truncate leading-tight">{user?.name || 'Admin'}</span>
              <span className="text-[10px] text-muted-foreground uppercase font-mono truncate">Administrator</span>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full gap-2"
            onClick={() => { try { localStorage.setItem('ts_preview_public', '1'); } catch {} window.location.href = '/translation'; }}
            data-testid="button-preview-public"
          >
            <Eye className="h-4 w-4" /> Preview as public
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-2"
            onClick={async () => {
              try { await fetch('/api/auth/admin-logout', { method: 'POST', credentials: 'include' }); } catch {}
              try { localStorage.removeItem('ts_admin'); localStorage.removeItem('ts_preview_public'); } catch {}
              window.location.href = '/translation';
            }}
            data-testid="button-exit-admin"
          >
            <LogOut className="h-4 w-4" /> Exit admin mode
          </Button>
        </div>
      )}
    </div>
  );
}
