import { useEffect, useState, useCallback } from 'react';
import {
  Plug, CheckCircle2, AlertCircle, XCircle, Loader2, ExternalLink,
  ShieldCheck, Clock, Mail, RefreshCw, Wrench, PlugZap,
  Folder, FileText, Search, ChevronRight, Home,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// Short, honest descriptions — only for connectors we actually describe;
// anything else falls back to its category name.
const PROVIDER_DESCRIPTIONS: Record<string, string> = {
  canva: 'Connect your Canva account to browse designs and open them directly from this platform.',
  google_drive: 'Connect Google Drive to list and read files from your account.',
  onedrive: 'Connect OneDrive to list and read files via Microsoft Graph.',
  dropbox: 'Connect Dropbox to list and download files.',
  github: 'Connect GitHub with a personal access token to browse repos, files, and issues.',
  local_folder: 'Point this at a local directory to list and read its files.',
};

type Capability = {
  action: string;
  description: string;
  required_scopes: string[];
  is_destructive: boolean;
  is_implemented: boolean;
};

type DisplayStatus = 'connected' | 'error' | 'expired' | 'configuration_required' | 'not_connected' | 'disabled';

type ConnectorEntry = {
  provider: string;
  display_name: string;
  category: string;
  auth_strategy_type: string;
  icon: string;
  enabled: boolean;
  configured: boolean;
  supports_sync: boolean;
  supports_health_check: boolean;
  capabilities: Capability[];
  connection_status: 'connected' | 'disconnected' | 'error' | 'expired';
  external_account_email: string | null;
  granted_scopes: string[];
  last_connected_at: string | null;
  last_successful_action_at: string | null;
  error_message: string | null;
};

type CredentialField = {
  name: string;
  label: string;
  type: string;
  required: boolean;
};

type Diagnostics = {
  configured: boolean;
  missingVariables: string[];
  callbackUrl: string | null;
  backendPort: number;
};

type CanvaDesign = {
  id: string;
  title: string;
  thumbnail?: { url?: string; width?: number; height?: number };
  urls?: { edit_url?: string; view_url?: string };
  updated_at?: number; // Unix seconds, from the real Canva API response
  created_at?: number;
};

type DriveFile = {
  id: string;
  name: string;
  mimeType?: string;
  size?: string;
  modifiedTime?: string;
  webViewLink?: string;
  iconLink?: string;
  thumbnailLink?: string;
};

const DRIVE_FOLDER_MIME = 'application/vnd.google-apps.folder';

function isDriveFolder(file: DriveFile): boolean {
  return file.mimeType === DRIVE_FOLDER_MIME;
}

function driveFileKindLabel(file: DriveFile): string {
  if (isDriveFolder(file)) return 'Folder';
  const m = file.mimeType || '';
  if (m === 'application/vnd.google-apps.document') return 'Google Doc';
  if (m === 'application/vnd.google-apps.presentation') return 'Google Slides';
  if (m === 'application/vnd.google-apps.spreadsheet') return 'Google Sheet';
  if (m.startsWith('image/')) return 'Image';
  if (m === 'application/pdf') return 'PDF';
  return 'File';
}

function formatUnixSeconds(ts: number | undefined): string {
  if (!ts) return 'Unknown';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return 'Unknown';
  }
}

function normalizeConnectors(raw: unknown): ConnectorEntry[] {
  const list = Array.isArray(raw) ? raw : [];
  const rows: ConnectorEntry[] = [];
  for (const item of list) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const provider = String(row.provider || '').trim();
    if (!provider) continue;
    rows.push({
      provider,
      display_name: String(row.display_name || provider),
      category: String(row.category || 'custom'),
      auth_strategy_type: String(row.auth_strategy_type || 'no_auth'),
      icon: String(row.icon || '🔌'),
      enabled: Boolean(row.enabled),
      configured: Boolean(row.configured),
      supports_sync: Boolean(row.supports_sync),
      supports_health_check: Boolean(row.supports_health_check),
      capabilities: Array.isArray(row.capabilities) ? (row.capabilities as Capability[]) : [],
      connection_status: (row.connection_status as ConnectorEntry['connection_status']) || 'disconnected',
      external_account_email: typeof row.external_account_email === 'string' ? row.external_account_email : null,
      granted_scopes: Array.isArray(row.granted_scopes) ? (row.granted_scopes as string[]) : [],
      last_connected_at: typeof row.last_connected_at === 'string' ? row.last_connected_at : null,
      last_successful_action_at: typeof row.last_successful_action_at === 'string' ? row.last_successful_action_at : null,
      error_message: typeof row.error_message === 'string' ? row.error_message : null,
    });
  }
  return rows;
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatCategory(category: string): string {
  return category.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// Single source of truth for "what state is this card actually in" —
// never show a disabled or unconfigured connector as operational.
function displayStatus(connector: ConnectorEntry): DisplayStatus {
  if (!connector.enabled) return 'disabled';
  if (!connector.configured) return 'configuration_required';
  if (connector.connection_status === 'connected') return 'connected';
  if (connector.connection_status === 'error') return 'error';
  if (connector.connection_status === 'expired') return 'expired';
  return 'not_connected';
}

function statusBadge(status: DisplayStatus) {
  switch (status) {
    case 'connected':
      return (
        <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 font-mono text-xs uppercase tracking-widest px-3 py-1">
          <CheckCircle2 className="h-3 w-3 mr-1.5" /> Connected
        </Badge>
      );
    case 'error':
      return (
        <Badge variant="outline" className="bg-destructive/10 text-destructive border-destructive/20 font-mono text-xs uppercase tracking-widest px-3 py-1">
          <XCircle className="h-3 w-3 mr-1.5" /> Connection Error
        </Badge>
      );
    case 'expired':
      return (
        <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/20 font-mono text-xs uppercase tracking-widest px-3 py-1">
          <AlertCircle className="h-3 w-3 mr-1.5" /> Expired
        </Badge>
      );
    case 'configuration_required':
      return (
        <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/20 font-mono text-xs uppercase tracking-widest px-3 py-1">
          <Wrench className="h-3 w-3 mr-1.5" /> Configuration Required
        </Badge>
      );
    case 'disabled':
      return (
        <Badge variant="outline" className="bg-secondary text-muted-foreground border-border font-mono text-xs uppercase tracking-widest px-3 py-1">
          Coming Soon
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="bg-secondary text-muted-foreground border-border font-mono text-xs uppercase tracking-widest px-3 py-1">
          <PlugZap className="h-3 w-3 mr-1.5" /> Available — Not Connected
        </Badge>
      );
  }
}

export default function ConnectorsPage() {
  const { toast } = useToast();
  const [connectors, setConnectors] = useState<ConnectorEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [disconnectTarget, setDisconnectTarget] = useState<ConnectorEntry | null>(null);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [permissionsTarget, setPermissionsTarget] = useState<ConnectorEntry | null>(null);
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [canvaDesigns, setCanvaDesigns] = useState<CanvaDesign[]>([]);
  const [designsLoading, setDesignsLoading] = useState(false);
  const [designsError, setDesignsError] = useState<string | null>(null);

  // Google Drive file browser — first 20 items, search + folder navigation
  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([]);
  const [driveLoading, setDriveLoading] = useState(false);
  const [driveError, setDriveError] = useState<string | null>(null);
  const [driveSearch, setDriveSearch] = useState('');
  const [driveSearchInput, setDriveSearchInput] = useState('');
  const [driveFolderStack, setDriveFolderStack] = useState<{ id: string; name: string }[]>([]);

  // Credential-form connect flow (every non-OAuth auth strategy)
  const [credentialTarget, setCredentialTarget] = useState<ConnectorEntry | null>(null);
  const [credentialFields, setCredentialFields] = useState<CredentialField[]>([]);
  const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
  const [credentialSubmitting, setCredentialSubmitting] = useState(false);
  const [credentialError, setCredentialError] = useState<string | null>(null);

  // Setup Instructions dialog (shows missing env var names + callback URL — never secret values)
  const [diagnosticsTarget, setDiagnosticsTarget] = useState<ConnectorEntry | null>(null);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);

  const loadConnectors = useCallback(async () => {
    try {
      const response = await fetch(`${API}/api/connectors`, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
      });
      if (!response.ok) throw new Error('Failed to load connectors');
      const data = await response.json();
      setConnectors(normalizeConnectors(data));
    } catch {
      setConnectors([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadDiagnostics = useCallback(async (connector: ConnectorEntry) => {
    setDiagnosticsTarget(connector);
    setDiagnostics(null);
    setDiagnosticsLoading(true);
    try {
      const response = await fetch(`${API}/api/connectors/${connector.provider}/diagnostics`, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
      });
      if (!response.ok) throw new Error('Failed to load diagnostics');
      const data = await response.json();
      setDiagnostics(data);
      // Keep the card behind the dialog in sync — if credentials were just
      // added and the backend restarted, this flips Connect back on live.
      void loadConnectors();
    } catch {
      setDiagnostics(null);
    } finally {
      setDiagnosticsLoading(false);
    }
  }, [loadConnectors]);

  // Automatically re-check configuration status when the user comes back to
  // this tab (e.g. after editing backend/.env and restarting the backend in
  // another window) — no manual refresh needed to see Connect re-enable.
  useEffect(() => {
    const onFocus = () => { void loadConnectors(); };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
    };
  }, [loadConnectors]);

  const loadCanvaDesigns = useCallback(async () => {
    setDesignsLoading(true);
    setDesignsError(null);
    try {
      // /canva/designs was a Phase-1-only route removed when the generic
      // Connector Framework replaced it with the provider-agnostic
      // /{provider}/actions dispatcher — this is the current, real route.
      const response = await fetch(`${API}/api/connectors/canva/actions`, {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'canva.list_designs', parameters: { limit: 10 } }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || !body.success) {
        throw new Error(body?.detail?.error_message || body?.detail || 'Failed to load Canva designs');
      }
      const items = Array.isArray(body?.data?.items) ? body.data.items : [];
      setCanvaDesigns(items.slice(0, 10));
    } catch (err) {
      setDesignsError(err instanceof Error ? err.message : 'Failed to load Canva designs');
      setCanvaDesigns([]);
    } finally {
      setDesignsLoading(false);
    }
  }, []);

  const loadDriveFiles = useCallback(async (folderId: string | null, query: string) => {
    setDriveLoading(true);
    setDriveError(null);
    try {
      const action = query
        ? 'google_drive.search_files'
        : folderId
          ? 'google_drive.list_folder'
          : 'google_drive.list_files';
      const parameters: Record<string, unknown> = { limit: 20 };
      if (query) parameters.query = query;
      if (folderId) parameters.folder_id = folderId;
      const response = await fetch(`${API}/api/connectors/google_drive/actions`, {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, parameters }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || !body.success) {
        throw new Error(body?.detail?.error_message || body?.detail || 'Failed to load Google Drive files');
      }
      const items = Array.isArray(body?.data?.files) ? body.data.files : [];
      setDriveFiles(items.slice(0, 20));
    } catch (err) {
      setDriveError(err instanceof Error ? err.message : 'Failed to load Google Drive files');
      setDriveFiles([]);
    } finally {
      setDriveLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConnectors();
  }, [loadConnectors]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const error = params.get('error');
    const connector = params.get('connector');
    if (connected) {
      toast({ title: 'Connected', description: `${connected} was connected successfully.` });
    } else if (error) {
      toast({
        title: 'Connection Failed',
        description: `${connector || 'Connector'} authorization did not complete (${error}).`,
        variant: 'destructive',
      });
    }
    if (connected || error) {
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [toast]);

  const canva = connectors.find((c) => c.provider === 'canva');
  useEffect(() => {
    if (canva?.connection_status === 'connected') {
      void loadCanvaDesigns();
    } else {
      setCanvaDesigns([]);
    }
  }, [canva?.connection_status, loadCanvaDesigns]);

  const googleDrive = connectors.find((c) => c.provider === 'google_drive');
  useEffect(() => {
    if (googleDrive?.connection_status === 'connected') {
      setDriveFolderStack([]);
      setDriveSearch('');
      setDriveSearchInput('');
      void loadDriveFiles(null, '');
    } else {
      setDriveFiles([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [googleDrive?.connection_status]);

  const currentDriveFolder = driveFolderStack[driveFolderStack.length - 1] || null;

  const handleDriveSearchSubmit = () => {
    setDriveSearch(driveSearchInput.trim());
    void loadDriveFiles(currentDriveFolder?.id || null, driveSearchInput.trim());
  };

  const handleDriveOpenFolder = (file: DriveFile) => {
    const next = [...driveFolderStack, { id: file.id, name: file.name }];
    setDriveFolderStack(next);
    setDriveSearch('');
    setDriveSearchInput('');
    void loadDriveFiles(file.id, '');
  };

  const handleDriveBreadcrumb = (index: number) => {
    // index === -1 means "back to My Drive root"
    const next = index < 0 ? [] : driveFolderStack.slice(0, index + 1);
    setDriveFolderStack(next);
    setDriveSearch('');
    setDriveSearchInput('');
    void loadDriveFiles(next.length ? next[next.length - 1].id : null, '');
  };

  const handleConnect = async (connector: ConnectorEntry) => {
    if (connector.auth_strategy_type === 'oauth2_pkce') {
      // Full page navigation — the backend responds with a 302 redirect to the real OAuth provider.
      window.location.href = `${API}/api/connectors/${connector.provider}/connect`;
      return;
    }
    try {
      const response = await fetch(`${API}/api/connectors/${connector.provider}/connect`, {
        method: 'GET',
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || data.mode !== 'form') {
        toast({
          title: 'Connect Failed',
          description: data?.error_message || 'Could not start the connection.',
          variant: 'destructive',
        });
        return;
      }
      setCredentialTarget(connector);
      setCredentialFields(data.fields || []);
      setCredentialValues({});
      setCredentialError(null);
    } catch {
      toast({ title: 'Connect Failed', description: 'Please try again.', variant: 'destructive' });
    }
  };

  const handleCredentialSubmit = async () => {
    if (!credentialTarget) return;
    setCredentialSubmitting(true);
    setCredentialError(null);
    try {
      const response = await fetch(`${API}/api/connectors/${credentialTarget.provider}/credentials`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentialValues),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail?.error_message || data?.error_message || 'Connection failed');
      }
      toast({ title: 'Connected', description: `${credentialTarget.display_name} was connected successfully.` });
      setCredentialTarget(null);
      await loadConnectors();
    } catch (err) {
      setCredentialError(err instanceof Error ? err.message : 'Connection failed');
    } finally {
      setCredentialSubmitting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!disconnectTarget) return;
    setIsDisconnecting(true);
    try {
      const response = await fetch(`${API}/api/connectors/${disconnectTarget.provider}/disconnect`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Disconnect failed');
      toast({ title: 'Disconnected', description: `${disconnectTarget.display_name} was disconnected.` });
      setDisconnectTarget(null);
      await loadConnectors();
    } catch {
      toast({ title: 'Disconnect Failed', description: 'Please try again.', variant: 'destructive' });
    } finally {
      setIsDisconnecting(false);
    }
  };

  const handleTest = async (connector: ConnectorEntry) => {
    setTestingProvider(connector.provider);
    try {
      const response = await fetch(`${API}/api/connectors/${connector.provider}/test`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.success) {
        toast({ title: 'Connection OK', description: `${connector.display_name} responded successfully.` });
      } else {
        toast({
          title: 'Test Failed',
          description: data?.detail?.error_message || data?.detail || 'The provider did not respond successfully.',
          variant: 'destructive',
        });
      }
      await loadConnectors();
    } catch {
      toast({ title: 'Test Failed', description: 'Please try again.', variant: 'destructive' });
    } finally {
      setTestingProvider(null);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-background">
      <div className="p-6 md:p-8 max-w-4xl mx-auto w-full space-y-8">
        <div className="flex flex-col gap-2 border-b border-border pb-6">
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Plug className="h-8 w-8 text-primary" />
            Connectors
          </h1>
          <p className="text-muted-foreground uppercase font-mono tracking-wider text-sm">
            External Platform Integrations
          </p>
        </div>

        <div className="grid gap-6">
          {isLoading ? (
            <div className="py-12 text-center text-muted-foreground animate-pulse font-mono text-xs uppercase tracking-widest">
              Loading connectors...
            </div>
          ) : (
            connectors.map((connector) => {
              const status = displayStatus(connector);
              const description = PROVIDER_DESCRIPTIONS[connector.provider];
              return (
                <div
                  key={connector.provider}
                  className={`bg-card border rounded-xl p-6 transition-all duration-300 ${
                    status === 'connected' ? 'border-primary shadow-[0_0_20px_-5px_rgba(37,99,235,0.2)]' : 'border-border'
                  } ${status === 'disabled' ? 'opacity-60' : ''}`}
                  data-testid={`card-connector-${connector.provider}`}
                >
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-4">
                      <div className={`h-12 w-12 rounded-lg flex items-center justify-center text-2xl ring-1 ${
                        status === 'connected' ? 'bg-primary/20 ring-primary/50' : 'bg-secondary ring-border'
                      }`}>
                        {connector.icon}
                      </div>
                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          <h3 className="text-lg font-bold tracking-tight">{connector.display_name}</h3>
                          <Badge variant="outline" className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                            {formatCategory(connector.category)}
                          </Badge>
                        </div>
                        {description && (
                          <p className="text-xs text-muted-foreground/80 mt-0.5 max-w-md">{description}</p>
                        )}
                        {status === 'connected' && connector.external_account_email ? (
                          <p className="text-sm text-muted-foreground flex items-center gap-1.5 mt-1">
                            <Mail className="h-3.5 w-3.5" /> {connector.external_account_email}
                          </p>
                        ) : status === 'disabled' ? (
                          <p className="text-sm text-muted-foreground mt-1">Not yet implemented</p>
                        ) : status === 'configuration_required' ? (
                          <p className="text-sm text-muted-foreground mt-1">App credentials not set on the server</p>
                        ) : (
                          <p className="text-sm text-muted-foreground mt-1">Not connected</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {statusBadge(status)}
                    </div>
                  </div>

                  {status === 'error' && connector.error_message && (
                    <div className="mt-4 flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
                      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>{connector.error_message}</span>
                    </div>
                  )}

                  {status === 'connected' && (
                    <div className="mt-4 flex flex-wrap gap-4 text-xs text-muted-foreground font-mono">
                      <span className="flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" /> Last connected: {formatDate(connector.last_connected_at)}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <ShieldCheck className="h-3.5 w-3.5" /> Last action: {formatDate(connector.last_successful_action_at)}
                      </span>
                      {connector.supports_sync && (
                        <span className="flex items-center gap-1.5">
                          <RefreshCw className="h-3.5 w-3.5" /> Sync enabled
                        </span>
                      )}
                    </div>
                  )}

                  {connector.capabilities.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {connector.capabilities.map((cap) => (
                        <Badge
                          key={cap.action}
                          variant="outline"
                          title={cap.description}
                          className={`text-[10px] font-mono px-2 py-0.5 ${
                            cap.is_implemented
                              ? 'text-foreground/80 border-border'
                              : 'text-muted-foreground/50 border-border/50 border-dashed'
                          }`}
                        >
                          {cap.action}
                        </Badge>
                      ))}
                    </div>
                  )}

                  {connector.enabled && (
                    <div className="mt-5 flex items-center gap-3 flex-wrap">
                      {status === 'connected' ? (
                        <>
                          {connector.supports_health_check && (
                            <Button
                              variant="outline"
                              onClick={() => handleTest(connector)}
                              disabled={testingProvider === connector.provider}
                              data-testid={`button-test-${connector.provider}`}
                            >
                              {testingProvider === connector.provider ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                              ) : null}
                              Test Connection
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            onClick={() => setPermissionsTarget(connector)}
                            data-testid={`button-manage-permissions-${connector.provider}`}
                          >
                            Manage Permissions
                          </Button>
                          <Button
                            variant="destructive"
                            onClick={() => setDisconnectTarget(connector)}
                            data-testid={`button-disconnect-${connector.provider}`}
                          >
                            Disconnect
                          </Button>
                        </>
                      ) : status === 'error' || status === 'expired' ? (
                        <Button onClick={() => handleConnect(connector)} data-testid={`button-reconnect-${connector.provider}`}>
                          Reconnect
                        </Button>
                      ) : status === 'configuration_required' ? (
                        <>
                          <Button disabled variant="outline" data-testid={`button-connect-${connector.provider}`}>
                            Connect (needs server configuration)
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => loadDiagnostics(connector)}
                            data-testid={`button-setup-instructions-${connector.provider}`}
                          >
                            <Wrench className="h-4 w-4 mr-2" />Setup Instructions
                          </Button>
                        </>
                      ) : (
                        <Button onClick={() => handleConnect(connector)} data-testid={`button-connect-${connector.provider}`}>
                          Connect
                        </Button>
                      )}
                    </div>
                  )}

                  {connector.provider === 'canva' && status === 'connected' && (
                    <div className="mt-6 pt-6 border-t border-border">
                      <h4 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-3">Your Canva Designs</h4>
                      {designsLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading designs...
                        </div>
                      ) : designsError ? (
                        <p className="text-sm text-destructive">{designsError}</p>
                      ) : canvaDesigns.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No designs found in your Canva account.</p>
                      ) : (
                        <div className="grid gap-3 sm:grid-cols-2">
                          {canvaDesigns.map((design) => (
                            <div
                              key={design.id}
                              className="flex gap-3 rounded-lg border border-border bg-secondary/20 p-3"
                              data-testid={`card-canva-design-${design.id}`}
                            >
                              {design.thumbnail?.url ? (
                                <img
                                  src={design.thumbnail.url}
                                  alt={design.title || 'Untitled design'}
                                  className="h-16 w-16 shrink-0 rounded object-cover border border-border/50"
                                />
                              ) : (
                                <div className="h-16 w-16 shrink-0 rounded bg-secondary flex items-center justify-center text-2xl">🎨</div>
                              )}
                              <div className="flex flex-col gap-1 min-w-0 flex-1">
                                <span className="text-sm font-medium truncate">{design.title || 'Untitled design'}</span>
                                <span className="text-[10px] font-mono text-muted-foreground/70 truncate">ID: {design.id}</span>
                                <span className="text-[10px] font-mono text-muted-foreground/70">
                                  Last modified: {formatUnixSeconds(design.updated_at)}
                                </span>
                                <a
                                  href={design.urls?.edit_url || '#'}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="mt-1 inline-flex items-center gap-1 self-start px-2 py-1 rounded text-[11px] font-mono border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
                                  data-testid={`link-canva-design-${design.id}`}
                                >
                                  <ExternalLink className="h-3 w-3" />Open in Canva
                                </a>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {connector.provider === 'google_drive' && status === 'connected' && (
                    <div className="mt-6 pt-6 border-t border-border">
                      <h4 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-3">Your Google Drive Files</h4>

                      <div className="flex items-center gap-2 mb-3">
                        <div className="relative flex-1">
                          <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            value={driveSearchInput}
                            onChange={(e) => setDriveSearchInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleDriveSearchSubmit(); }}
                            placeholder="Search Drive files by name..."
                            className="pl-8 h-9 text-sm"
                            data-testid="input-drive-search"
                          />
                        </div>
                        <Button variant="outline" size="sm" onClick={handleDriveSearchSubmit} data-testid="button-drive-search">
                          Search
                        </Button>
                      </div>

                      {!driveSearch && (
                        <div className="flex items-center flex-wrap gap-1 mb-3 text-xs font-mono text-muted-foreground">
                          <button
                            onClick={() => handleDriveBreadcrumb(-1)}
                            className="flex items-center gap-1 hover:text-foreground transition-colors"
                            data-testid="button-drive-breadcrumb-root"
                          >
                            <Home className="h-3 w-3" /> My Drive
                          </button>
                          {driveFolderStack.map((f, i) => (
                            <span key={f.id} className="flex items-center gap-1">
                              <ChevronRight className="h-3 w-3" />
                              <button
                                onClick={() => handleDriveBreadcrumb(i)}
                                className="hover:text-foreground transition-colors truncate max-w-[160px]"
                              >
                                {f.name}
                              </button>
                            </span>
                          ))}
                        </div>
                      )}

                      {driveLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading Drive files...
                        </div>
                      ) : driveError ? (
                        <p className="text-sm text-destructive">{driveError}</p>
                      ) : driveFiles.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          {driveSearch ? `No files matching "${driveSearch}".` : 'No files found in this folder.'}
                        </p>
                      ) : (
                        <div className="grid gap-3 sm:grid-cols-2">
                          {driveFiles.map((file) => {
                            const folder = isDriveFolder(file);
                            return (
                              <div
                                key={file.id}
                                className="flex gap-3 rounded-lg border border-border bg-secondary/20 p-3"
                                data-testid={`card-drive-file-${file.id}`}
                              >
                                {file.thumbnailLink ? (
                                  <img
                                    src={file.thumbnailLink}
                                    alt={file.name}
                                    className="h-16 w-16 shrink-0 rounded object-cover border border-border/50"
                                  />
                                ) : (
                                  <div className="h-16 w-16 shrink-0 rounded bg-secondary flex items-center justify-center">
                                    {folder ? (
                                      <Folder className="h-6 w-6 text-muted-foreground" />
                                    ) : (
                                      <FileText className="h-6 w-6 text-muted-foreground" />
                                    )}
                                  </div>
                                )}
                                <div className="flex flex-col gap-1 min-w-0 flex-1">
                                  {folder ? (
                                    <button
                                      onClick={() => handleDriveOpenFolder(file)}
                                      className="text-sm font-medium truncate text-left hover:underline"
                                      data-testid={`button-drive-open-folder-${file.id}`}
                                    >
                                      {file.name}
                                    </button>
                                  ) : (
                                    <span className="text-sm font-medium truncate">{file.name}</span>
                                  )}
                                  <span className="text-[10px] font-mono text-muted-foreground/70">{driveFileKindLabel(file)}</span>
                                  <span className="text-[10px] font-mono text-muted-foreground/70 truncate">ID: {file.id}</span>
                                  <span className="text-[10px] font-mono text-muted-foreground/70">
                                    Modified: {formatDate(file.modifiedTime || null)}
                                  </span>
                                  {file.webViewLink && (
                                    <a
                                      href={file.webViewLink}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="mt-1 inline-flex items-center gap-1 self-start px-2 py-1 rounded text-[11px] font-mono border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
                                      data-testid={`link-drive-file-${file.id}`}
                                    >
                                      <ExternalLink className="h-3 w-3" />Open in Google Drive
                                    </a>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Credential-form connect flow — API key / basic auth / SSH key / no-auth / custom header */}
      <Dialog open={!!credentialTarget} onOpenChange={(open) => !open && setCredentialTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Connect {credentialTarget?.display_name}</DialogTitle>
            <DialogDescription>
              These values are encrypted at rest and never exposed back to the browser after saving.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {credentialFields.map((field) => (
              <div key={field.name} className="space-y-1.5">
                <Label htmlFor={`cred-${field.name}`}>
                  {field.label}{field.required && <span className="text-destructive"> *</span>}
                </Label>
                {field.type === 'textarea' ? (
                  <Textarea
                    id={`cred-${field.name}`}
                    value={credentialValues[field.name] || ''}
                    onChange={(e) => setCredentialValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
                    rows={4}
                    data-testid={`input-credential-${field.name}`}
                  />
                ) : (
                  <Input
                    id={`cred-${field.name}`}
                    type={field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'}
                    value={credentialValues[field.name] || ''}
                    onChange={(e) => setCredentialValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
                    data-testid={`input-credential-${field.name}`}
                  />
                )}
              </div>
            ))}
            {credentialError && <p className="text-sm text-destructive">{credentialError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCredentialTarget(null)} disabled={credentialSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleCredentialSubmit} disabled={credentialSubmitting} data-testid="button-submit-credentials">
              {credentialSubmitting ? 'Connecting...' : 'Connect'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!disconnectTarget} onOpenChange={(open) => !open && setDisconnectTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect {disconnectTarget?.display_name}?</DialogTitle>
            <DialogDescription>
              This revokes the platform's access and removes the stored connection. You can reconnect at any time.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectTarget(null)} disabled={isDisconnecting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDisconnect} disabled={isDisconnecting} data-testid="button-confirm-disconnect">
              {isDisconnecting ? 'Disconnecting...' : 'Disconnect'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!permissionsTarget} onOpenChange={(open) => !open && setPermissionsTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{permissionsTarget?.display_name} Permissions</DialogTitle>
            <DialogDescription>Scopes granted during authorization.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2 py-2">
            {permissionsTarget?.granted_scopes?.length ? (
              permissionsTarget.granted_scopes.map((scope) => (
                <Badge key={scope} variant="outline" className="font-mono text-xs">
                  {scope}
                </Badge>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No scope information available.</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPermissionsTarget(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!diagnosticsTarget} onOpenChange={(open) => !open && setDiagnosticsTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{diagnosticsTarget?.display_name} Setup Instructions</DialogTitle>
            <DialogDescription>
              Add these to <code className="text-xs">backend/.env</code> and restart the backend. Values are never shown here — only which names are missing.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {diagnosticsLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Checking configuration...
              </div>
            ) : !diagnostics ? (
              <p className="text-sm text-destructive">Could not load diagnostics. Please try again.</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  {diagnostics.configured ? (
                    <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                      <CheckCircle2 className="h-3 w-3 mr-1.5" /> Configured
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/20">
                      <AlertCircle className="h-3 w-3 mr-1.5" /> Not Configured
                    </Badge>
                  )}
                </div>

                {diagnostics.missingVariables.length > 0 && (
                  <div className="space-y-1.5">
                    <Label>Missing environment variables</Label>
                    <div className="flex flex-col gap-1.5">
                      {diagnostics.missingVariables.map((name) => (
                        <code key={name} className="text-xs font-mono bg-secondary px-2 py-1.5 rounded border border-border">
                          {name}=
                        </code>
                      ))}
                    </div>
                  </div>
                )}

                {diagnostics.callbackUrl && (
                  <div className="space-y-1.5">
                    <Label>Register this exact redirect/callback URL with the provider</Label>
                    <code className="block text-xs font-mono bg-secondary px-2 py-1.5 rounded border border-border break-all">
                      {diagnostics.callbackUrl}
                    </code>
                  </div>
                )}

                <p className="text-xs text-muted-foreground">
                  Backend port: <span className="font-mono">{diagnostics.backendPort}</span> · File: <code className="font-mono">backend/.env</code>
                </p>
              </>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => diagnosticsTarget && loadDiagnostics(diagnosticsTarget)}
              disabled={diagnosticsLoading}
              data-testid="button-recheck-diagnostics"
            >
              <RefreshCw className="h-4 w-4 mr-2" />Re-check
            </Button>
            <Button onClick={() => setDiagnosticsTarget(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
