import { useEffect, useState } from 'react';
import { Settings2, Cpu, Key, Link as LinkIcon, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useActivateProvider } from '@workspace/api-client-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { useToast } from '@/hooks/use-toast';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

type UIProvider = {
  id: string;
  name: string;
  type: string;
  description: string;
  is_configured: boolean;
  is_active: boolean;
  model?: string | null;
  base_url?: string | null;
  is_online?: boolean | null;
  warning?: string | null;
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
      type: String(row.type || id),
      description: String(row.description || ''),
      is_configured: Boolean(row.is_configured),
      is_active: Boolean(row.is_active),
      model: typeof row.model === 'string' ? row.model : null,
      base_url: typeof row.base_url === 'string' ? row.base_url : null,
      is_online: typeof row.is_online === 'boolean' ? row.is_online : null,
      warning: typeof row.warning === 'string' ? row.warning : null,
    });
  }

  return rows;
}

function getActiveProvider(rows: UIProvider[]): UIProvider | null {
  return rows.find((p) => p.is_active) || null;
}

export default function SettingsPage() {
  const { toast } = useToast();
  const [providers, setProviders] = useState<UIProvider[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  const [openProvider, setOpenProvider] = useState<string | null>(null);
  
  // Form states per provider type
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, string>>({});
  const [baseUrls, setBaseUrls] = useState<Record<string, string>>({});

  const [taskRoutes, setTaskRoutes] = useState<Record<string, string>>({});
  const [taskRoutesLoading, setTaskRoutesLoading] = useState(true);

  const TASK_HINT_LABELS: Record<string, string> = {
    code: 'Code / Programming',
    code_review: 'Code Review',
    debugging: 'Debugging',
    long_document: 'Long Documents',
    ppt: 'PPT Generation',
    pdf: 'PDF Analysis',
    docx: 'DOCX Generation',
    curriculum: 'Curriculum Generation',
    structured_writing: 'Structured Writing',
    translation_refinement: 'Translation Refinement',
    web_search: 'Web Search',
    google_drive: 'Google Drive Workflows',
    image: 'Image Understanding',
    multimodal: 'Multimodal Tasks',
    quick: 'Quick Responses',
  };

  const loadTaskRoutes = async () => {
    try {
      const response = await fetch(`${API}/api/providers/task-routes`, { method: 'GET', credentials: 'include', cache: 'no-store' });
      if (!response.ok) throw new Error('Failed to load task routes');
      setTaskRoutes(await response.json());
    } catch {
      setTaskRoutes({});
    } finally {
      setTaskRoutesLoading(false);
    }
  };

  const setTaskRoute = async (hint: string, providerId: string) => {
    setTaskRoutes((prev) => ({ ...prev, [hint]: providerId }));
    try {
      await fetch(`${API}/api/providers/task-routes/${hint}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId }),
      });
    } catch {
      toast({ title: 'Failed to update routing rule', variant: 'destructive' });
      void loadTaskRoutes();
    }
  };

  useEffect(() => { void loadTaskRoutes(); }, []);

  const loadProviders = async () => {
    try {
      const response = await fetch(`${API}/api/providers`, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error('Failed to load provider registry');
      }
      const data = await response.json();
      const rows = normalizeProviders(data);
      // Ensure UI reflects backend truth: only one active provider from API.
      const active = getActiveProvider(rows);
      setProviders(
        rows.map((p) => ({
          ...p,
          is_active: active ? p.id === active.id : false,
        }))
      );
    } catch {
      setProviders(normalizeProviders([]));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadProviders();
  }, []);

  useEffect(() => {
    if (!providers?.length) return;

    // Populate form defaults from persisted backend config once loaded.
    setModels((prev) => {
      const next = { ...prev };
      for (const provider of providers) {
        if (!next[provider.id] && provider.model) {
          next[provider.id] = provider.model;
        }
      }
      return next;
    });

    setBaseUrls((prev) => {
      const next = { ...prev };
      for (const provider of providers) {
        if (!next[provider.id] && provider.base_url) {
          next[provider.id] = provider.base_url;
        }
      }
      return next;
    });
  }, [providers]);

  const { mutate: activate, isPending } = useActivateProvider({
    mutation: {
      onSuccess: (data) => {
        void loadProviders();
        setOpenProvider(null);
        toast({
          title: "Provider Activated",
          description: `${data.name} is now the active AI engine.`,
        });
      },
      onError: () => {
        toast({
          title: "Activation Failed",
          description: "Please check your credentials and try again.",
          variant: "destructive"
        });
      }
    }
  });

  const handleActivate = (provider: UIProvider) => {
    activate({
      providerId: provider.id,
      data: {
        api_key: apiKeys[provider.id] || 'mock-key',
        model: models[provider.id] || provider.model || undefined,
        base_url: provider.type === 'ollama'
          ? (baseUrls[provider.id] || provider.base_url || 'http://127.0.0.1:11434')
          : (baseUrls[provider.id] || undefined)
      }
    });
  };

  const getStatusColor = (provider: UIProvider) => {
    if (provider.is_active) return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
    if (provider.is_configured) return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    return 'bg-secondary text-muted-foreground border-border';
  };

  const getStatusText = (provider: UIProvider) => {
    if (provider.is_active) return 'Active Engine';
    if (provider.is_configured) return 'Standby (Configured)';
    return 'Offline (Needs Config)';
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-background">
      <div className="p-6 md:p-8 max-w-4xl mx-auto w-full space-y-8">
        
        <div className="flex flex-col gap-2 border-b border-border pb-6">
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Settings2 className="h-8 w-8 text-primary" />
            System Configuration
          </h1>
          <p className="text-muted-foreground uppercase font-mono tracking-wider text-sm">Neural Engine Providers</p>
        </div>

        <div className="grid gap-6">
          {isLoading ? (
            <div className="py-12 text-center text-muted-foreground animate-pulse font-mono text-xs uppercase tracking-widest">
              Initializing provider registry...
            </div>
          ) : (
            providers?.map(provider => (
              <Collapsible 
                key={provider.id} 
                open={openProvider === provider.id || provider.is_active}
                onOpenChange={(isOpen) => setOpenProvider(isOpen ? provider.id : null)}
                className={`bg-card border rounded-xl overflow-hidden transition-all duration-300 ${
                  provider.is_active ? 'border-primary shadow-[0_0_20px_-5px_rgba(37,99,235,0.2)]' : 'border-border'
                }`}
              >
                <CollapsibleTrigger className="w-full flex items-center justify-between p-6 hover:bg-secondary/20 transition-colors">
                  <div className="flex items-center gap-4">
                    <div className={`h-12 w-12 rounded-lg flex items-center justify-center ring-1 ${
                      provider.is_active ? 'bg-primary/20 ring-primary/50' : 'bg-secondary ring-border'
                    }`}>
                      <Cpu className={`h-6 w-6 ${provider.is_active ? 'text-primary' : 'text-muted-foreground'}`} />
                    </div>
                    <div className="flex flex-col items-start">
                      <h3 className="text-lg font-bold tracking-tight flex items-center gap-2">
                        {provider.name}
                        {provider.is_active && (
                          <Badge variant="outline" className="bg-primary text-primary-foreground border-primary px-2 py-0.5 text-[10px] font-mono shadow-sm">
                            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse mr-1.5 inline-block" />
                            ACTIVE
                          </Badge>
                        )}
                      </h3>
                      <p className="text-sm text-muted-foreground">{provider.description}</p>
                      {provider.type === 'ollama' && provider.warning && (
                        <p className="text-xs text-amber-600 mt-1 flex items-center gap-1.5">
                          <AlertCircle className="h-3.5 w-3.5" />
                          {provider.warning}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Badge variant="outline" className={`font-mono text-xs uppercase tracking-widest px-3 py-1 ${getStatusColor(provider)}`}>
                      {provider.is_active ? <CheckCircle2 className="h-3 w-3 mr-1.5" /> : null}
                      {getStatusText(provider)}
                    </Badge>
                  </div>
                </CollapsibleTrigger>
                
                <CollapsibleContent>
                  <div className="p-6 pt-0 border-t border-border bg-secondary/10 mt-4">
                    <div className="max-w-xl space-y-5 pt-6">
                      
                      {provider.type !== 'mock' && (
                        <div className="grid gap-2">
                          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold flex items-center gap-2">
                            <Key className="h-3.5 w-3.5" /> API Key
                          </label>
                          <Input 
                            type="password"
                            placeholder="sk-..." 
                            value={apiKeys[provider.id] || ''}
                            onChange={(e) => setApiKeys({...apiKeys, [provider.id]: e.target.value})}
                            className="bg-background font-mono"
                          />
                        </div>
                      )}

                      {(provider.type === 'gemini' || provider.type === 'claude' || provider.type === 'openai' || provider.type === 'ollama') && (
                        <div className="grid gap-2">
                          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold flex items-center gap-2">
                            <Cpu className="h-3.5 w-3.5" /> Target Model
                          </label>
                          <Input
                            placeholder={provider.type === 'gemini' ? 'gemini-3.1-flash-lite' : provider.type === 'claude' ? 'claude-sonnet-5' : provider.type === 'openai' ? 'gpt-4o' : 'llama3'}
                            value={models[provider.id] || provider.model || ''}
                            onChange={(e) => setModels({...models, [provider.id]: e.target.value})}
                            className="bg-background font-mono"
                          />
                        </div>
                      )}

                      {provider.type === 'ollama' && (
                        <div className="grid gap-2">
                          <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold flex items-center gap-2">
                            <LinkIcon className="h-3.5 w-3.5" /> Base URL
                          </label>
                          <Input 
                            placeholder="http://localhost:11434" 
                            value={baseUrls[provider.id] || ''}
                            onChange={(e) => setBaseUrls({...baseUrls, [provider.id]: e.target.value})}
                            className="bg-background font-mono"
                          />
                        </div>
                      )}

                      <div className="pt-4 flex items-center justify-between">
                        {provider.is_active ? (
                          <p className="text-sm text-muted-foreground font-medium flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4 text-emerald-500" /> Currently handling requests
                          </p>
                        ) : (
                          <div className="flex-1" />
                        )}
                        <Button 
                          onClick={() => handleActivate(provider)}
                          disabled={isPending || provider.is_active}
                          className={provider.is_active ? 'opacity-50' : 'shadow-sm'}
                          data-testid={`button-activate-${provider.id}`}
                        >
                          {isPending ? 'Activating...' : provider.is_active ? 'Already Active' : 'Activate Engine'}
                        </Button>
                      </div>
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            ))
          )}
        </div>

        <div className="flex flex-col gap-2 border-b border-border pb-6 pt-4">
          <h2 className="text-xl font-bold tracking-tight">Automatic Routing Rules</h2>
          <p className="text-muted-foreground text-sm">
            Per-task provider overrides. "Auto" uses the active engine above; a specific
            provider always wins for that task, regardless of which engine is active.
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl divide-y divide-border">
          {taskRoutesLoading ? (
            <div className="py-8 text-center text-muted-foreground animate-pulse font-mono text-xs uppercase tracking-widest">
              Loading routing rules...
            </div>
          ) : (
            Object.keys(TASK_HINT_LABELS).map((hint) => {
              const current = taskRoutes[hint] || 'auto';
              return (
                <div key={hint} className="flex items-center justify-between gap-4 px-5 py-3 flex-wrap">
                  <span className="text-sm font-medium">{TASK_HINT_LABELS[hint]}</span>
                  <div className="flex gap-1.5 flex-wrap">
                    <Button
                      size="sm"
                      variant={current === 'auto' ? 'default' : 'outline'}
                      className="h-7 text-xs px-2.5"
                      onClick={() => setTaskRoute(hint, 'auto')}
                      data-testid={`button-route-${hint}-auto`}
                    >
                      Auto
                    </Button>
                    {providers.filter((p) => p.id !== 'mock' && p.is_configured).map((p) => (
                      <Button
                        key={p.id}
                        size="sm"
                        variant={current === p.id ? 'default' : 'outline'}
                        className="h-7 text-xs px-2.5"
                        onClick={() => setTaskRoute(hint, p.id)}
                        data-testid={`button-route-${hint}-${p.id}`}
                      >
                        {p.name}
                      </Button>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>

      </div>
    </div>
  );
}