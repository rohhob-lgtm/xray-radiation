import { useState, useRef, useEffect } from 'react';
import { useLocation } from 'wouter';
import { useGetConversation, useListProviders, getListConversationsQueryKey, getGetConversationQueryKey } from '@workspace/api-client-react';
import { useAuth } from '@workspace/replit-auth-web';
import { useQueryClient } from '@tanstack/react-query';
import {
  Paperclip, Send, Square, Bot, User, X, Shield, Terminal, Zap, ImageIcon,
  ChevronDown, Microscope, Calculator, BookOpen, Eye, Wrench, GraduationCap,
  Lightbulb, ExternalLink, Download, ZoomIn, FolderUp, FilePlus2, FolderOpen,
  PanelRightOpen, FolderX, File as FileIcon, Pin, Cpu
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from '@/components/ui/dropdown-menu';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { detectDirection } from '@/lib/rtl';
import { useWorkspace } from '@/hooks/use-workspace';
import { WorkspacePanel } from '@/components/workspace-panel';
import { AgentExecutionPanel, type AgentEvent, type AgentStageDef } from '@/components/agent-execution-panel';
import { listWorkspaces, downloadGeneratedFileUrl, type WorkspaceDict, type GeneratedFileDict } from '@/lib/workspace-api';
import { ANON_SESSION_HEADER, getAnonSessionId } from '@/lib/session';
import { ErrorBoundary } from '@/components/error-boundary';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

const buildChatStreamUrls = (): string[] => {
  const urls = new Set<string>();
  const fromBase = `${API}/api/chat/stream`;
  urls.add(fromBase);
  urls.add('/api/chat/stream');
  return Array.from(urls);
};

// ── Agent definitions ────────────────────────────────────────────────
const AGENTS = [
  { id: 'general',     label: 'General',     icon: Shield,       color: 'text-blue-400',   desc: 'X-ray expert assistant' },
  { id: 'research',    label: 'Research',    icon: Microscope,   color: 'text-violet-400', desc: 'Academic papers & literature' },
  { id: 'physics',     label: 'Physics',     icon: Calculator,   color: 'text-amber-400',  desc: 'Radiation physics & math' },
  { id: 'patent',      label: 'Patent',      icon: BookOpen,     color: 'text-emerald-400',desc: 'IP analysis & claims' },
  { id: 'vision',      label: 'Vision',      icon: Eye,          color: 'text-cyan-400',   desc: 'X-ray image analysis' },
  { id: 'maintenance', label: 'Maintenance', icon: Wrench,       color: 'text-rose-400',   desc: 'Equipment & diagnostics' },
  { id: 'training',    label: 'Training',    icon: GraduationCap,color: 'text-teal-400',   desc: 'Education & courses' },
  { id: 'innovation',  label: 'Innovation',  icon: Lightbulb,    color: 'text-yellow-400', desc: 'Inventions & novel ideas' },
];

interface GalleryImage {
  image_id: string;
  gallery_index_id?: string;
  title: string;
  image_url: string;
  thumbnail_url: string;
  caption: string;
  tags: string[];
  source_document: string;
  page_number?: number | null;
  scanner_model?: string;
  manufacturer?: string;
  category?: string;
  // Multimodal Internet Image Retrieval — present only for images found via
  // the internet fallback (api.services.research_agent.image_discovery),
  // never for Knowledge Base images. source_url is the page the image was
  // found on (not image_url itself, which is hotlinked directly — this
  // platform never downloads/caches the image bytes).
  source_url?: string;
  retrieved_at?: string;
  confidence?: number;
}

interface GalleryResultsPayload {
  type: 'image_results';
  query: string;
  count: number;
  images: GalleryImage[];
  // Which sources actually contributed, e.g. {local: 2, web: 4}. Present from
  // the unified search orchestrator (gallery_service.search_images_with_fallback).
  sources_used?: Record<string, number>;
}

// ── Gallery image results card ────────────────────────────────────────
function GalleryResultsCard({ payload }: { payload: GalleryResultsPayload }) {
  const [lightbox, setLightbox] = useState<GalleryImage | null>(null);

  const handleDownload = async (img: GalleryImage) => {
    // Internet-retrieved images are never proxied/cached by this platform
    // (see image_discovery.py) — open the original source page instead of
    // attempting a cross-origin blob fetch (which would also silently fail
    // for most external hosts due to CORS).
    if (img.source_url) {
      window.open(img.source_url, '_blank', 'noopener,noreferrer');
      return;
    }
    try {
      const resp = await fetch(img.image_url, { credentials: 'include' });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${img.title.replace(/[^a-z0-9]/gi, '_')}.png`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  return (
    <>
      <div className="w-full space-y-3">
        {/* Header */}
        <div className="flex items-center gap-2 px-1">
          <ImageIcon className="h-4 w-4 text-cyan-400 shrink-0" />
          <span className="text-sm font-semibold text-foreground">
            {payload.count > 0
              ? `${payload.count} image${payload.count !== 1 ? 's' : ''} found`
              + (payload.query ? ` for "${payload.query}"` : ' in gallery')
              : 'No matching images found'
            }
          </span>
          {/* Source breakdown — Local (Knowledge Base) vs Web (internet fallback) */}
          {payload.count > 0 && payload.sources_used && (
            <span className="text-[10px] font-mono text-muted-foreground/70 ms-auto">
              {[
                payload.sources_used.local ? `Local ${payload.sources_used.local}` : null,
                payload.sources_used.web ? `Web ${payload.sources_used.web}` : null,
              ].filter(Boolean).join(' · ')}
            </span>
          )}
        </div>

        {payload.images.length === 0 && (
          <div className="px-3 py-4 rounded-lg border border-border/50 bg-card/50 text-sm text-muted-foreground text-center">
            Searched the local knowledge base and the web — no images matched this query.
            Indexing runs automatically on upload, so newly added documents appear here without
            a manual reindex; try rephrasing, or browse all indexed images on the Gallery page.
          </div>
        )}

        {/* Image grid */}
        {payload.images.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {payload.images.map((img) => (
              <div
                key={img.image_id}
                className="group relative rounded-xl overflow-hidden border border-border/50 bg-black
                  hover:border-cyan-500/50 hover:shadow-[0_0_20px_-4px_rgba(6,182,212,0.3)]
                  transition-all cursor-pointer flex flex-col"
              >
                {/* Thumbnail */}
                <div
                  className="relative aspect-[4/3] overflow-hidden"
                  onClick={() => setLightbox(img)}
                >
                  <img
                    src={img.thumbnail_url || img.image_url}
                    alt={img.title}
                    className="w-full h-full object-contain bg-black"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <ZoomIn className="h-6 w-6 text-white" />
                  </div>
                  {img.scanner_model && (
                    <div className="absolute top-1.5 start-1.5">
                      <Badge className="text-[9px] font-mono bg-cyan-500/20 text-cyan-300 border-cyan-500/30 h-4 px-1.5">
                        {img.scanner_model}
                      </Badge>
                    </div>
                  )}
                </div>

                {/* Card footer */}
                <div className="px-2.5 py-2 bg-card/90 border-t border-border/40 flex flex-col gap-1 flex-1">
                  <p className="text-xs font-semibold text-foreground leading-tight line-clamp-1">
                    {img.title}
                  </p>
                  {img.caption && (
                    <p className="text-[10px] text-muted-foreground leading-snug line-clamp-2">
                      {img.caption}
                    </p>
                  )}
                  <p className="text-[10px] font-mono text-muted-foreground/60 truncate mt-0.5">
                    {img.source_document}
                    {img.page_number != null ? ` · p.${img.page_number}` : ''}
                  </p>
                  {/* Internet-retrieval provenance badge — never shown for
                      Knowledge Base images, only ones with source_url set */}
                  {img.source_url && (
                    <p className="text-[9px] font-mono text-cyan-400/70 truncate">
                      🌐 web result
                      {typeof img.confidence === 'number' ? ` · ${Math.round(img.confidence)}% trust` : ''}
                      {img.retrieved_at ? ` · ${new Date(img.retrieved_at).toLocaleDateString()}` : ''}
                    </p>
                  )}
                  {/* Tags */}
                  {img.tags && img.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {img.tags.slice(0, 3).map(tag => (
                        <span key={tag} className="text-[9px] font-mono px-1 py-0.5 rounded bg-primary/10 text-primary/70">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {/* Actions */}
                  <div className="flex gap-1 mt-1">
                    <button
                      className="flex-1 flex items-center justify-center gap-1 py-1 rounded text-[10px] font-mono
                        border border-border/50 text-muted-foreground hover:text-foreground hover:border-cyan-500/50 transition-colors"
                      onClick={() => setLightbox(img)}
                    >
                      <ExternalLink className="h-2.5 w-2.5" />Open
                    </button>
                    <button
                      className="flex-1 flex items-center justify-center gap-1 py-1 rounded text-[10px] font-mono
                        border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-colors"
                      onClick={() => handleDownload(img)}
                    >
                      {img.source_url
                        ? <><ExternalLink className="h-2.5 w-2.5" />Source</>
                        : <><Download className="h-2.5 w-2.5" />Save</>}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[100] bg-black/92 flex items-center justify-center p-6"
          onClick={() => setLightbox(null)}
        >
          <button
            className="absolute top-4 end-4 text-white/60 hover:text-white p-2 rounded-lg hover:bg-white/10"
            onClick={() => setLightbox(null)}
          >
            <X className="h-6 w-6" />
          </button>
          <div className="flex flex-col items-center gap-4 max-w-5xl w-full" onClick={e => e.stopPropagation()}>
            <img
              src={lightbox.image_url}
              alt={lightbox.title}
              className="max-h-[78vh] max-w-full object-contain rounded-xl shadow-2xl"
            />
            <div className="flex flex-wrap items-center gap-3 text-sm text-white/70">
              <span className="font-semibold text-white">{lightbox.title}</span>
              <span className="text-white/30">·</span>
              <span>{lightbox.source_document}{lightbox.page_number != null ? ` p.${lightbox.page_number}` : ''}</span>
              {lightbox.scanner_model && (
                <Badge className="bg-cyan-500/20 text-cyan-300 border-cyan-500/30">
                  {lightbox.scanner_model}
                </Badge>
              )}
              {lightbox.source_url && (
                <a
                  href={lightbox.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
                >
                  View source
                </a>
              )}
            </div>
            {lightbox.confidence != null && (
              <p className="text-xs text-white/40">
                {Math.round(lightbox.confidence)}% source trust
                {lightbox.retrieved_at ? ` · retrieved ${new Date(lightbox.retrieved_at).toLocaleDateString()}` : ''}
              </p>
            )}
            {lightbox.caption && (
              <p className="text-sm text-white/60 text-center max-w-2xl">{lightbox.caption}</p>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ── Parse a saved message content for gallery results ─────────────────
// Saved format is: [KB-grounded explanation text]\n\n__GALLERY__:{json}. The
// marker may therefore appear after the explanation, not only at the start.
const _GALLERY_MARKER = '__GALLERY__:';
function parseGalleryContent(content: string): GalleryResultsPayload | null {
  const idx = content.indexOf(_GALLERY_MARKER);
  if (idx === -1) return null;
  try {
    return JSON.parse(content.slice(idx + _GALLERY_MARKER.length));
  } catch {
    return null;
  }
}

// The human-readable explanation saved before the gallery marker (if any).
function parseGalleryText(content: string): string {
  const idx = content.indexOf(_GALLERY_MARKER);
  if (idx === -1) return '';
  return content.slice(0, idx).trim();
}

// Stage list for the Agent Orchestrator's design+Drive run (see
// backend/api/services/agent_orchestrator/runner.py) — distinct from the
// workspace agent's default stage list in AgentExecutionPanel.
const ORCHESTRATOR_STAGES: AgentStageDef[] = [
  { key: 'understanding', label: 'Understanding request' },
  { key: 'planning', label: 'Planning task' },
  { key: 'using_claude', label: 'Using AI to write content' },
  { key: 'checking_canva', label: 'Checking Canva' },
  { key: 'rendering_design', label: 'Rendering design' },
  { key: 'exporting_png', label: 'Exporting PNG' },
  { key: 'exporting_pdf', label: 'Exporting PDF' },
  { key: 'saving_to_drive', label: 'Saving to Google Drive' },
  { key: 'completed', label: 'Completed' },
];
// Stage keys unique to the orchestrator run (excludes 'understanding'/
// 'planning'/'completed', which the workspace agent's default list also uses)
// — used to detect which stage list to display without misclassifying a
// workspace-agent turn as an orchestrator run.
const ORCHESTRATOR_ONLY_STAGE_KEYS = new Set([
  'using_claude', 'checking_canva', 'rendering_design', 'exporting_png', 'exporting_pdf', 'saving_to_drive',
]);

// ── Canva chat results ──────────────────────────────────────────────────
type CanvaDesignItem = {
  id: string;
  title?: string;
  urls?: { edit_url?: string; view_url?: string };
};

// Result of the Design Orchestrator (AI Tool Router) creating/editing a
// visual design — see backend/api/services/design_orchestrator.py.
// available_actions is populated server-side from what actually succeeded,
// so the UI only ever shows a button whose backend action is real.
type DesignResultPayload = {
  type: 'canva_design_result';
  design_type: string;
  mode: string;
  canva_design_id: string | null;
  title: string | null;
  thumbnail_url: string | null;
  edit_url: string | null;
  view_url: string | null;
  available_actions: string[];
  connect_required: boolean;
  connect_url: string | null;
  error_message: string | null;
  workflow_id: string | null;
  // Present when the Agent Orchestrator ran this as a combined
  // design-and-save-to-Drive request (see runner.py) — absent for a
  // plain design-only request, which still uses the manual button below.
  run_id?: string | null;
  drive_file?: { id: string; name: string; web_view_link: string } | null;
};

type CanvaResultsPayload =
  | { type: 'canva_connect_required'; connect_url: string }
  | { type: 'canva_designs'; items: CanvaDesignItem[] }
  | { type: 'canva_disconnected'; was_connected: boolean }
  | { type: 'canva_error'; error_code?: string; error_message?: string }
  | DesignResultPayload;

async function exportCanvaDesign(designId: string, format: 'png' | 'pdf'): Promise<{ ok: boolean; url?: string; message?: string }> {
  try {
    const resp = await fetch(`${API}/api/connectors/canva/actions`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', [ANON_SESSION_HEADER]: getAnonSessionId() },
      body: JSON.stringify({ action: 'canva.export_design', parameters: { design_id: designId, format } }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) return { ok: false, message: data?.detail?.error_message || data?.error_message || 'Export failed.' };
    const urls: string[] = data?.data?.urls || [];
    if (!urls.length) return { ok: false, message: 'Export is still processing — try again in a moment.' };
    return { ok: true, url: urls[0] };
  } catch {
    return { ok: false, message: 'Export request failed.' };
  }
}

async function saveCanvaDesignToDrive(designId: string, format: 'png' | 'pdf', title: string): Promise<{ ok: boolean; url?: string; message?: string }> {
  try {
    const resp = await fetch(`${API}/api/connectors/canva/${designId}/save-to-drive`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', [ANON_SESSION_HEADER]: getAnonSessionId() },
      body: JSON.stringify({ format, title }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) return { ok: false, message: data?.detail?.error_message || data?.error_message || 'Save to Drive failed.' };
    const webUrl = data?.file?.webViewLink || data?.file?.web_view_link;
    return { ok: true, url: webUrl };
  } catch {
    return { ok: false, message: 'Save to Drive request failed.' };
  }
}

const _ACTION_LABELS: Record<string, string> = {
  open_in_canva: 'Open in Canva', export_png: 'Export PNG', export_pdf: 'Export PDF',
  save_to_drive: 'Save to Google Drive', regenerate: 'Regenerate', edit_content: 'Edit content',
  change_template: 'Change template', download_png: 'Download PNG',
};

function DesignResultCard({ payload, onFollowUp }: { payload: DesignResultPayload; onFollowUp: (message: string) => void }) {
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionNote, setActionNote] = useState<string | null>(null);
  // Re-fetches the persisted AgentRun on mount (including after a page
  // refresh) so the run's status is confirmed from its own record, not just
  // assumed from the chat message's embedded payload.
  const [runStatus, setRunStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!payload.run_id) return;
    let cancelled = false;
    fetch(`${API}/api/agent-runs/${payload.run_id}`, {
      credentials: 'include', headers: { [ANON_SESSION_HEADER]: getAnonSessionId() },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (!cancelled && data) setRunStatus(data.status); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [payload.run_id]);

  const runExport = async (format: 'png' | 'pdf') => {
    if (!payload.canva_design_id) return;
    setBusyAction(`export_${format}`); setActionNote(null);
    const res = await exportCanvaDesign(payload.canva_design_id, format);
    setBusyAction(null);
    if (res.ok && res.url) window.open(res.url, '_blank', 'noopener,noreferrer');
    else setActionNote(res.message || 'Export failed.');
  };

  const runSaveToDrive = async () => {
    if (!payload.canva_design_id) return;
    setBusyAction('save_to_drive'); setActionNote(null);
    const res = await saveCanvaDesignToDrive(payload.canva_design_id, 'png', payload.title || 'design');
    setBusyAction(null);
    setActionNote(res.ok ? 'Saved to Google Drive.' : (res.message || 'Save to Drive failed.'));
    if (res.ok && res.url) window.open(res.url, '_blank', 'noopener,noreferrer');
  };

  const handleAction = (action: string) => {
    switch (action) {
      case 'export_png': return runExport('png');
      case 'export_pdf': return runExport('pdf');
      case 'save_to_drive': return runSaveToDrive();
      case 'regenerate': return onFollowUp('Regenerate this design.');
      case 'edit_content': return onFollowUp('Edit this design: ');
      case 'change_template': return onFollowUp('Use another Canva template for this design.');
      default: return;
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 max-w-md">
      {payload.thumbnail_url && (
        <div className="rounded-md overflow-hidden border border-border/50 bg-black/20">
          <img src={payload.thumbnail_url} alt={payload.title || 'Design preview'} className="w-full h-auto object-contain max-h-80" />
        </div>
      )}
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium truncate">{payload.title || 'Untitled design'}</span>
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          {payload.design_type} · {payload.mode}
          {payload.canva_design_id && <> · {payload.canva_design_id}</>}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {payload.available_actions.includes('open_in_canva') && payload.edit_url && (
          <a
            href={payload.edit_url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
            data-testid="link-open-canva-design"
          >
            <ExternalLink className="h-3 w-3" />Open in Canva
          </a>
        )}
        {payload.available_actions.includes('download_png') && payload.thumbnail_url && (
          <a
            href={payload.thumbnail_url} download={`${payload.title || 'design'}.png`}
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono border border-border text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
            data-testid="link-download-design-png"
          >
            <Download className="h-3 w-3" />Download PNG
          </a>
        )}
        {payload.drive_file && (
          <a
            href={payload.drive_file.web_view_link} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 transition-colors"
            data-testid="link-saved-to-drive"
          >
            <ExternalLink className="h-3 w-3" />Saved to Drive
          </a>
        )}
        {payload.available_actions
          .filter((a) => !['open_in_canva', 'download_png'].includes(a))
          .filter((a) => a !== 'save_to_drive' || !payload.drive_file)
          .map((action) => (
            <button
              key={action}
              type="button"
              onClick={() => handleAction(action)}
              disabled={busyAction === action}
              className="px-2 py-1 rounded text-[11px] font-mono border border-border text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors disabled:opacity-50"
              data-testid={`button-design-${action}`}
            >
              {busyAction === action ? 'Working…' : (_ACTION_LABELS[action] || action)}
            </button>
          ))}
      </div>
      {payload.connect_required && payload.connect_url && (
        <Button
          size="sm" className="self-start"
          onClick={() => goToCanvaConnect(payload.connect_url!, '')}
          data-testid="button-connect-canva-design"
        >
          🎨 Connect Canva
        </Button>
      )}
      {actionNote && <p className="text-[11px] text-muted-foreground">{actionNote}</p>}
      {runStatus && (
        <p className="text-[10px] font-mono text-muted-foreground/60">Agent run: {runStatus}</p>
      )}
    </div>
  );
}

function parseCanvaContent(content: string): CanvaResultsPayload | null {
  if (!content.startsWith('__CANVA__:')) return null;
  try {
    return JSON.parse(content.slice('__CANVA__:'.length));
  } catch {
    return null;
  }
}

// Saves the in-flight message so it can be auto-resumed after the OAuth
// redirect round-trip, then navigates the whole page to Canva's consent screen.
function goToCanvaConnect(connectUrl: string, pendingMessage: string) {
  if (pendingMessage.trim()) {
    sessionStorage.setItem('prefilled_chat_query', pendingMessage);
  }
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  window.location.href = `${base}${connectUrl}`;
}

// ── Connector result payload classification ─────────────────────────────
// The backend's connector tool router (api/services/connector_chat_router.py)
// generalizes the __CANVA__ SSE/save shape to ANY connected provider — a
// Google Drive (or future) tool call that isn't connected, or that fails,
// produces a dynamically-named `{provider}_connect_required` /
// `{provider}_error` type, not just the literal `canva_*` ones. This
// function is the single place that decides how to render whatever shape
// actually arrives, so CanvaResultsCard itself never has to assume a
// payload is Canva-shaped (or shaped at all) before rendering it — a
// regression fix after an unrecognized `google_drive_connect_required`
// payload fell through to the canva_designs branch and crashed on
// `payload.items.length` with `items` undefined.
type ConnectorResultView =
  | { kind: 'design_result' }
  | { kind: 'connect_required'; provider: string; connectUrl: string }
  | { kind: 'error'; provider: string; message: string }
  | { kind: 'disconnected'; wasConnected: boolean }
  | { kind: 'designs'; items: CanvaDesignItem[] }
  | { kind: 'empty' }
  | { kind: 'unsupported' };

function titleCaseProvider(provider: string): string {
  return provider.split('_').filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ') || 'this service';
}

export function classifyConnectorResult(payload: unknown): ConnectorResultView {
  if (!payload || typeof payload !== 'object') return { kind: 'unsupported' };
  const p = payload as Record<string, unknown>;
  if (typeof p.type !== 'string') return { kind: 'unsupported' };
  const type = p.type;

  if (type === 'canva_design_result') return { kind: 'design_result' };

  if (type.endsWith('_connect_required')) {
    return {
      kind: 'connect_required',
      provider: type.slice(0, -'_connect_required'.length),
      connectUrl: typeof p.connect_url === 'string' ? p.connect_url : '',
    };
  }

  if (type.endsWith('_error')) {
    const message =
      (typeof p.error_message === 'string' && p.error_message) ||
      (typeof p.error_code === 'string' && p.error_code) ||
      'Request failed.';
    return { kind: 'error', provider: type.slice(0, -'_error'.length), message };
  }

  if (type === 'canva_disconnected') {
    return { kind: 'disconnected', wasConnected: Boolean(p.was_connected) };
  }

  if (type === 'canva_designs') {
    return Array.isArray(p.items) ? { kind: 'designs', items: p.items as CanvaDesignItem[] } : { kind: 'empty' };
  }

  return { kind: 'unsupported' };
}

function CanvaResultsCard({
  payload, pendingMessage, onImport, onFollowUp,
}: {
  payload: CanvaResultsPayload;
  pendingMessage: string;
  onImport?: (design: CanvaDesignItem) => void;
  onFollowUp?: (message: string) => void;
}) {
  const view = classifyConnectorResult(payload);

  if (view.kind === 'design_result') {
    return <DesignResultCard payload={payload as DesignResultPayload} onFollowUp={onFollowUp || (() => {})} />;
  }

  if (view.kind === 'connect_required') {
    const displayName = titleCaseProvider(view.provider);
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
        <p className="text-sm text-foreground">Connect your {displayName} account to perform this action.</p>
        <Button
          size="sm"
          className="self-start"
          onClick={() => goToCanvaConnect(view.connectUrl, pendingMessage)}
          data-testid="button-connect-connector-inline"
        >
          🔗 Connect {displayName}
        </Button>
      </div>
    );
  }

  if (view.kind === 'error') {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
        {view.message}
      </div>
    );
  }

  if (view.kind === 'disconnected') {
    return (
      <div className="rounded-lg border border-border bg-secondary/20 p-3 text-sm text-muted-foreground">
        {view.wasConnected ? 'Canva has been disconnected.' : 'Canva was not connected.'}
      </div>
    );
  }

  if (view.kind === 'empty') {
    return (
      <div className="rounded-lg border border-border bg-secondary/20 p-3 text-sm text-muted-foreground">
        No designs were found in your Canva account.
      </div>
    );
  }

  if (view.kind === 'unsupported') {
    // Never crash on an unrecognized or malformed result shape — this
    // component is only ever reached for connector-tool results
    // (__CANVA__:-prefixed saves / canva_results SSE events); genuine
    // research/knowledge-router/chat answers stream as plain text and
    // never reach here at all, so there is nothing to hide by rendering
    // nothing for a shape we don't recognize.
    return null;
  }

  // view.kind === 'designs', and items is guaranteed to be an array here.
  if (view.items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-secondary/20 p-3 text-sm text-muted-foreground">
        No designs were found in your Canva account.
      </div>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {view.items.map((design) => (
        <div key={design.id} className="rounded-lg border border-border bg-secondary/10 p-2.5 flex flex-col gap-2">
          <span className="text-sm font-medium truncate">{design.title || 'Untitled design'}</span>
          <div className="flex flex-wrap gap-1.5">
            <a
              href={design.urls?.edit_url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
              data-testid={`link-open-canva-${design.id}`}
            >
              <ExternalLink className="h-3 w-3" />Open in Canva
            </a>
            <button
              type="button"
              onClick={() => onImport?.(design)}
              className="px-2 py-1 rounded text-[11px] font-mono border border-border text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
              data-testid={`button-import-chat-${design.id}`}
            >
              Import into Chat
            </button>
            <span
              title="Requires Canva export capability, not implemented yet"
              className="px-2 py-1 rounded text-[11px] font-mono border border-border/40 text-muted-foreground/40 cursor-not-allowed"
            >
              Save to Knowledge Base
            </span>
            <span
              title="Requires Canva export capability, not implemented yet"
              className="px-2 py-1 rounded text-[11px] font-mono border border-border/40 text-muted-foreground/40 cursor-not-allowed"
            >
              Send to Training Generator
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Parse the workspace agent's generated-files trailer ────────────────
const GENERATED_FILES_MARKER = '\n\n__GENERATED_FILES__:';

function parseGeneratedFilesContent(content: string): { visibleText: string; files: GeneratedFileDict[] } {
  const idx = content.indexOf(GENERATED_FILES_MARKER);
  if (idx === -1) return { visibleText: content, files: [] };
  const visibleText = content.slice(0, idx);
  try {
    const files = JSON.parse(content.slice(idx + GENERATED_FILES_MARKER.length));
    return { visibleText, files: Array.isArray(files) ? files : [] };
  } catch {
    return { visibleText, files: [] };
  }
}

function GeneratedFilesRow({ files }: { files: GeneratedFileDict[] }) {
  if (!files.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {files.map((f) => (
        <a
          key={f.id}
          href={downloadGeneratedFileUrl(f.workspace_id, f.id)}
          download
          className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-primary/30 bg-primary/5 hover:bg-primary/10 text-xs text-foreground transition-colors"
        >
          <FileIcon className="h-3 w-3 text-primary" />
          <span className="truncate max-w-[160px]">{f.filename}</span>
          <Download className="h-3 w-3 text-muted-foreground" />
        </a>
      ))}
    </div>
  );
}

function useSearchParam(key: string) {
  const [value, setValue] = useState<string | null>(
    new URLSearchParams(window.location.search).get(key)
  );
  useEffect(() => {
    const handlePopState = () => setValue(new URLSearchParams(window.location.search).get(key));
    window.addEventListener('popstate', handlePopState);
    const interval = setInterval(handlePopState, 200);
    return () => { window.removeEventListener('popstate', handlePopState); clearInterval(interval); };
  }, [key]);
  return value;
}

const streamMessage = async (
  input: { message: string; conversation_id: string | null; image_base64?: string | null; image_filename?: string | null; agent_mode?: string; workspace_id?: string | null; provider_override?: string },
  onChunk: (c: string) => void,
  signal: AbortSignal,
  onImage?: (url: string) => void,
  onGalleryResults?: (payload: GalleryResultsPayload) => void,
  onAgentEvent?: (event: AgentEvent) => void,
  onCanvaResults?: (payload: CanvaResultsPayload) => void,
): Promise<{ convId: string | null; contentReceived: boolean; cleanDone: boolean }> => {
  // ── Correlation / diagnostics ──────────────────────────────────────────────
  const reqId = Math.random().toString(36).slice(2, 10).toUpperCase();
  const t0 = performance.now();
  const slog = (...args: unknown[]) => console.log(`[stream:${reqId}]`, ...args);
  const swarn = (...args: unknown[]) => console.warn(`[stream:${reqId}]`, ...args);
  const serr  = (...args: unknown[]) => console.error(`[stream:${reqId}]`, ...args);

  let activeConvId = input.conversation_id;
  let chunkCount   = 0;
  let bytesTotal   = 0;
  let cleanDone    = false;   // set when we receive the explicit `done` SSE event
  let model        = input.agent_mode ?? 'general';

  slog('→ request', { model, convId: input.conversation_id });

  // ── HTTP handshake ─────────────────────────────────────────────────────────
  const streamUrls = buildChatStreamUrls();
  let resp: Response | null = null;
  for (let i = 0; i < streamUrls.length; i++) {
    const url = streamUrls[i];
    resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', [ANON_SESSION_HEADER]: getAnonSessionId() },
      body: JSON.stringify(input),
      credentials: 'include',
      signal,
    });
    if (resp.ok) {
      if (i > 0) slog('using fallback stream URL', { url });
      break;
    }
    if (resp.status !== 404 || i === streamUrls.length - 1) break;
    swarn('stream endpoint 404, trying fallback URL', { tried: url });
  }

  if (!resp || !resp.ok) {
    const body = await resp.text().catch(() => '');
    serr('HTTP error', resp.status, resp.statusText, body);
    throw new Error(`Stream failed (HTTP ${resp.status})`);
  }

  const reader = resp.body!.getReader();
  const dec    = new TextDecoder();
  let   buf    = '';

  try {
    while (true) {
      // ── Read one chunk from the transport ──────────────────────────────────
      let done: boolean;
      let value: Uint8Array | undefined;
      try {
        ({ done, value } = await reader.read());
      } catch (readErr: any) {
        // Transport error (proxy drop, network reset, etc.) — NOT an AbortError.
        const elapsed = ((performance.now() - t0) / 1000).toFixed(2);
        swarn('transport closed unexpectedly', {
          reqId, model, elapsed: elapsed + 's',
          chunks: chunkCount, bytes: bytesTotal,
          gotDone: cleanDone,
          reason: readErr?.name ?? readErr?.message ?? String(readErr),
        });
        // If the AI already produced content the backend saved the message.
        // Treat this as a successful (if noisy) completion so the UI never shows an error.
        if (chunkCount > 0 || cleanDone) {
          swarn('content already received — suppressing transport error, treating as complete');
          return { convId: activeConvId, contentReceived: chunkCount > 0, cleanDone };
        }
        throw readErr; // nothing was delivered → propagate so UI can show real error
      }

      if (done) {
        const elapsed = ((performance.now() - t0) / 1000).toFixed(2);
        slog('← closed', { elapsed: elapsed + 's', chunks: chunkCount, bytes: bytesTotal, cleanDone });
        break;
      }

      if (value) {
        bytesTotal += value.byteLength;
        buf += dec.decode(value, { stream: true });
      }

      // ── Parse SSE lines ────────────────────────────────────────────────────
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;

        // Separate JSON parsing (can fail) from event handling (must not be swallowed)
        let d: any;
        try {
          d = JSON.parse(line.slice(6));
        } catch {
          swarn('malformed SSE line, skipping:', line.slice(0, 120));
          continue; // skip this line only; keep the stream alive
        }

        // ── Dispatch event ─────────────────────────────────────────────────
        if (d.type === 'start') {
          activeConvId = d.conversation_id;
          model = d.model ?? model;
          slog('start', { reqId: d.request_id, convId: activeConvId, model });
        }
        else if (d.type === 'chunk') {
          chunkCount++;
          onChunk(d.chunk);
        }
        else if (d.type === 'image' && d.image_url) {
          onImage?.(d.image_url);
        }
        else if (d.type === 'gallery_results' && d.payload) {
          onGalleryResults?.(d.payload);
        }
        else if (d.type === 'canva_results' && d.payload) {
          onCanvaResults?.(d.payload);
        }
        else if (d.type === 'stage' || d.type === 'tool_call' || d.type === 'tool_result') {
          onAgentEvent?.(d as AgentEvent);
        }
        else if (d.type === 'done') {
          cleanDone = true;
          const elapsed = ((performance.now() - t0) / 1000).toFixed(2);
          slog('done', {
            reqId: d.request_id, model: d.model ?? model,
            convId: d.conversation_id,
            chunks: chunkCount, bytes: bytesTotal,
            elapsed: elapsed + 's',
            finish_reason: d.finish_reason ?? 'stop',
            completion_status: 'complete',
          });
          return { convId: activeConvId, contentReceived: chunkCount > 0, cleanDone: true };
        }
        else if (d.type === 'error') {
          // Backend-reported error — propagate; do NOT swallow with a catch
          serr('server error event:', d.error);
          throw new Error(d.error || 'The AI service returned an error.');
        }
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* already released */ }
  }

  // Stream closed naturally (done === true) but no explicit `done` event.
  // If we received content the backend saved it — still a success.
  if (chunkCount > 0) {
    swarn('stream closed without `done` event but content was received — treating as complete');
    return { convId: activeConvId, contentReceived: true, cleanDone: false };
  }

  return { convId: activeConvId, contentReceived: false, cleanDone: false };
};

// Global AI Brain: manual pinning — persists a message into durable memory
// so it can be recalled semantically in future conversations. Authenticated
// users only (persistent memory is gated to login).
async function pinMessage(conversationId: string, messageId: string): Promise<void> {
  const resp = await fetch(`${API}/api/memory/pin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', [ANON_SESSION_HEADER]: getAnonSessionId() },
    credentials: 'include',
    body: JSON.stringify({ conversation_id: conversationId, message_id: messageId }),
  });
  if (!resp.ok) throw new Error(`Failed to pin message (HTTP ${resp.status})`);
}

// ── Markdown message renderer ────────────────────────────────────────
function MessageContent({ content }: { content: string }) {
  const dir = detectDirection(content);
  const isRtl = dir === 'rtl';
  return (
    <div
      dir={dir}
      className={`prose prose-invert prose-sm max-w-none
      prose-headings:font-bold prose-headings:tracking-tight prose-headings:mt-3 prose-headings:mb-1
      prose-p:leading-relaxed prose-p:my-1
      prose-code:text-xs prose-code:bg-background/80 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:border prose-code:border-border/50 prose-code:text-cyan-300 prose-code:before:content-none prose-code:after:content-none
      prose-pre:bg-background prose-pre:border prose-pre:border-border prose-pre:rounded-lg prose-pre:text-xs
      prose-table:text-xs prose-th:text-muted-foreground prose-th:font-mono prose-th:uppercase prose-th:tracking-wider prose-th:text-[10px]
      prose-td:border-border/30 prose-tr:border-border/30
      prose-strong:text-foreground prose-strong:font-semibold
      prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
      prose-blockquote:${isRtl ? 'border-r-primary border-l-0' : 'border-l-primary'} prose-blockquote:text-muted-foreground prose-blockquote:italic
      prose-a:text-primary prose-a:no-underline hover:prose-a:underline
      ${isRtl ? 'rtl-content' : ''}
    `}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

export default function ChatPage() {
  const [location, setLocation] = useLocation();
  const convId = useSearchParam('id');
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(new Set());

  const { data: conversation, isLoading: isConvLoading } = useGetConversation(convId || '', {
    query: { enabled: !!convId, queryKey: getGetConversationQueryKey(convId || '') }
  });
  const { data: providers } = useListProviders();
  const activeProvider = providers?.find(p => p.is_active);

  // Backend response includes workspace_id even though the generated OpenAPI
  // client type doesn't know about it yet (additive route, client not regenerated).
  const conversationWorkspaceId = (conversation as any)?.workspace_id as string | null | undefined;

  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [chatError, setChatError] = useState('');
  const [agentMode, setAgentMode] = useState('general');
  const [agentMenuOpen, setAgentMenuOpen] = useState(false);
  const [providerOverride, setProviderOverride] = useState('auto');
  const [providerMenuOpen, setProviderMenuOpen] = useState(false);
  const [streamingGalleryResults, setStreamingGalleryResults] = useState<GalleryResultsPayload | null>(null);
  const [streamingCanvaResults, setStreamingCanvaResults] = useState<CanvaResultsPayload | null>(null);
  // The message that triggered the in-flight request — used as the
  // resume-after-OAuth payload if the user clicks "Connect Canva" from the
  // streaming card (by then `input` itself has already been cleared).
  const [lastSentMessage, setLastSentMessage] = useState('');
  const [streamingAgentEvents, setStreamingAgentEvents] = useState<AgentEvent[]>([]);
  const [existingWorkspaces, setExistingWorkspaces] = useState<WorkspaceDict[]>([]);

  const workspace = useWorkspace(conversationWorkspaceId);

  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [streamingImageUrl, setStreamingImageUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const filesInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => { scrollToBottom(); }, [conversation?.messages, streamingContent, isThinking, streamingGalleryResults, streamingCanvaResults, streamingAgentEvents]);

  const loadExistingWorkspaces = () => {
    listWorkspaces().then(setExistingWorkspaces).catch(() => {});
  };

  const handleFilesSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    // `e.target.files` is a LIVE FileList — resetting `e.target.value` below
    // (needed so re-selecting the same file later still fires onChange) also
    // empties this same live object. Snapshot into a real array first.
    const files = e.target.files ? Array.from(e.target.files) : [];
    e.target.value = '';
    if (files.length === 0) return;
    try {
      await workspace.uploadFiles(files, { isFolder: false, conversationId: convId });
    } catch { /* surfaced via workspace.uploadStatus */ }
  };

  const handleFolderSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    // Same live-FileList pitfall as handleFilesSelected — snapshot first.
    const files = e.target.files ? Array.from(e.target.files) : [];
    e.target.value = '';
    if (files.length === 0) return;
    try {
      await workspace.uploadFiles(files, { isFolder: true, conversationId: convId });
    } catch { /* surfaced via workspace.uploadStatus */ }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const resumingAfterConnect = params.get('resume_pending') === '1';
    const q = sessionStorage.getItem('prefilled_chat_query');
    // Normal case: prefill a brand-new (no convId) session from another page.
    // Resume case: returning to this SAME conversation after a Connect-Canva
    // (or any connector) OAuth redirect — restore the request that was
    // pending when the user clicked Connect, instead of losing it.
    if (q && (!convId || resumingAfterConnect)) {
      setInput(q);
      sessionStorage.removeItem('prefilled_chat_query');
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
    if (resumingAfterConnect) {
      window.history.replaceState({}, '', window.location.pathname + window.location.search.replace(/[?&]resume_pending=1/, ''));
    }
  }, [convId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result as string;
      setImageBase64(result.split(',')[1]);
    };
    reader.readAsDataURL(file);
  };

  const removeImage = () => {
    setImageFile(null); setImageBase64(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // Clear streaming content once conversation reloads with the saved assistant message
  useEffect(() => {
    if (streamingContent && !isStreaming && conversation?.messages?.length) {
      const last = conversation.messages[conversation.messages.length - 1];
      if (last.role === 'assistant') setStreamingContent('');
    }
  }, [conversation?.messages?.length, isStreaming]); // eslint-disable-line react-hooks/exhaustive-deps

  const stopStreaming = () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setIsStreaming(false); setIsThinking(false);
    setStreamingContent(''); setStreamingAgentEvents([]);
    if (convId) queryClient.invalidateQueries({ queryKey: getGetConversationQueryKey(convId) });
    queryClient.invalidateQueries({ queryKey: getListConversationsQueryKey() });
  };

  const handleSubmit = async (e?: React.FormEvent, overrideMessage?: string) => {
    e?.preventDefault();
    if (!(overrideMessage ?? input).trim() && !imageBase64) return;
    if (isStreaming) { stopStreaming(); return; }

    const currentInput = overrideMessage ?? input;
    const currentBase64 = imageBase64;
    const currentFilename = imageFile?.name;
    const currentWorkspaceId = workspace.workspaceId;
    setLastSentMessage(currentInput);
    setInput(''); removeImage();
    setIsStreaming(true); setIsThinking(true);
    setStreamingContent(''); setStreamingGalleryResults(null); setStreamingCanvaResults(null); setStreamingAgentEvents([]);

    abortControllerRef.current = new AbortController();
    setChatError('');
    try {
      const { convId: newConvId, contentReceived } = await streamMessage(
        {
          message: currentInput, conversation_id: convId, image_base64: currentBase64,
          image_filename: currentFilename, agent_mode: agentMode, workspace_id: currentWorkspaceId,
          provider_override: providerOverride,
        },
        (chunk) => { setIsThinking(false); setStreamingContent(prev => prev + chunk); },
        abortControllerRef.current.signal,
        (url) => { setIsThinking(false); setStreamingImageUrl(url); },
        (payload) => { setIsThinking(false); setStreamingGalleryResults(payload); },
        (event) => { setIsThinking(false); setStreamingAgentEvents(prev => [...prev, event]); },
        (payload) => { setIsThinking(false); setStreamingCanvaResults(payload); },
      );
      // Success path (includes graceful transport-close after content received).
      // Always refresh so the saved assistant message loads from the DB.
      if (newConvId && newConvId !== convId) setLocation(`/chat?id=${newConvId}`);
      else if (convId) queryClient.invalidateQueries({ queryKey: getGetConversationQueryKey(convId) });
      queryClient.invalidateQueries({ queryKey: getListConversationsQueryKey() });
      void contentReceived; // used for logging inside streamMessage
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // User pressed Stop — silent, no banner
        return;
      }
      // True failure: HTTP error or server error event with zero content delivered.
      console.error('Streaming error:', error.name, error.message, error);
      setChatError(error.message || 'Response failed. Please try again.');
      // Only clear the streaming content if nothing was shown — if chunks arrived
      // the user can still read them while the conversation reloads.
      setStreamingContent('');
      // Still try to refresh: the backend may have saved a partial response.
      if (convId) queryClient.invalidateQueries({ queryKey: getGetConversationQueryKey(convId) });
      queryClient.invalidateQueries({ queryKey: getListConversationsQueryKey() });
    } finally {
      setIsStreaming(false); setIsThinking(false);
      // streamingContent is intentionally NOT cleared here — the useEffect above
      // clears it once the conversation query reloads with the saved assistant message,
      // preventing the flash-of-blank between stream-end and query-refetch.
      setStreamingImageUrl(null);
      setStreamingGalleryResults(null);
      setStreamingCanvaResults(null);
      setStreamingAgentEvents([]);
      abortControllerRef.current = null;
      if (workspace.workspaceId) workspace.refreshWorkspace(workspace.workspaceId);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  const activeAgent = AGENTS.find(a => a.id === agentMode)!;
  const ActiveAgentIcon = activeAgent.icon;

  const quickPrompts = [
    "Explain dual-energy X-ray material discrimination",
    "Show me vehicle scanner images",
    "Overview of ATR algorithms for baggage screening",
    "Search gallery for LZBV-S",
  ];

  return (
    <div className="flex flex-col h-full bg-background relative">
      {/* Header */}
      <div className="flex items-center px-6 py-3 border-b border-border bg-card shrink-0 gap-3 shadow-sm z-10">
        <div className="flex flex-col flex-1 min-w-0">
          <h2 className="text-base font-bold text-foreground truncate">
            {convId ? (conversation?.title || 'Active Session') : 'New Analysis Session'}
          </h2>
          {convId && <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">ID: {convId.split('-')[0]}</p>}
        </div>

        {/* Agent Selector */}
        <div className="relative shrink-0">
          <button
            onClick={() => setAgentMenuOpen(o => !o)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all text-sm font-medium ${
              agentMode !== 'general'
                ? 'border-primary/40 bg-primary/10 text-foreground'
                : 'border-border/50 bg-background text-muted-foreground hover:text-foreground hover:border-border'
            }`}
          >
            <ActiveAgentIcon className={`h-3.5 w-3.5 ${activeAgent.color}`} />
            <span className="hidden sm:inline text-xs uppercase tracking-wider font-mono">{activeAgent.label}</span>
            <ChevronDown className="h-3 w-3 opacity-60" />
          </button>

          {agentMenuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setAgentMenuOpen(false)} />
              <div className="absolute end-0 top-full mt-1 z-50 w-56 bg-card border border-border rounded-xl shadow-2xl shadow-black/50 overflow-hidden py-1">
                <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground px-3 py-2">Select Agent</p>
                {AGENTS.map(agent => {
                  const AIcon = agent.icon;
                  return (
                    <button
                      key={agent.id}
                      onClick={() => { setAgentMode(agent.id); setAgentMenuOpen(false); }}
                      className={`w-full flex items-center gap-3 px-3 py-2 text-sm transition-colors text-start ${
                        agentMode === agent.id
                          ? 'bg-primary/15 text-foreground'
                          : 'hover:bg-secondary text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <AIcon className={`h-4 w-4 shrink-0 ${agent.color}`} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold">{agent.label}</div>
                        <div className="text-[10px] text-muted-foreground truncate">{agent.desc}</div>
                      </div>
                      {agentMode === agent.id && <div className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* AI Provider Selector — Auto / Gemini / Claude / ... */}
        <div className="relative shrink-0">
          <button
            onClick={() => setProviderMenuOpen(o => !o)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all text-sm font-medium ${
              providerOverride !== 'auto'
                ? 'border-primary/40 bg-primary/10 text-foreground'
                : 'border-border/50 bg-background text-muted-foreground hover:text-foreground hover:border-border'
            }`}
            data-testid="button-provider-selector"
          >
            <Cpu className="h-3.5 w-3.5" />
            <span className="hidden sm:inline text-xs uppercase tracking-wider font-mono">
              {providerOverride === 'auto'
                ? 'Auto'
                : providers?.find(p => p.id === providerOverride)?.name || providerOverride}
            </span>
            <ChevronDown className="h-3 w-3 opacity-60" />
          </button>

          {providerMenuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setProviderMenuOpen(false)} />
              <div className="absolute end-0 top-full mt-1 z-50 w-56 bg-card border border-border rounded-xl shadow-2xl shadow-black/50 overflow-hidden py-1">
                <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground px-3 py-2">AI Provider</p>
                <button
                  onClick={() => { setProviderOverride('auto'); setProviderMenuOpen(false); }}
                  className={`w-full flex items-center gap-3 px-3 py-2 text-sm transition-colors text-start ${
                    providerOverride === 'auto' ? 'bg-primary/15 text-foreground' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'
                  }`}
                  data-testid="button-provider-auto"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold">Auto</div>
                    <div className="text-[10px] text-muted-foreground truncate">Routes each request automatically</div>
                  </div>
                  {providerOverride === 'auto' && <div className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />}
                </button>
                {(providers || []).filter(p => p.id !== 'mock' && p.is_configured).map(p => (
                  <button
                    key={p.id}
                    onClick={() => { setProviderOverride(p.id); setProviderMenuOpen(false); }}
                    className={`w-full flex items-center gap-3 px-3 py-2 text-sm transition-colors text-start ${
                      providerOverride === p.id ? 'bg-primary/15 text-foreground' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'
                    }`}
                    data-testid={`button-provider-${p.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-semibold">{p.name}</div>
                    </div>
                    {providerOverride === p.id && <div className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {activeProvider && (
          <Badge variant="outline" className="shrink-0 bg-primary/10 text-primary border-primary/20 gap-2 h-7 px-3 hidden md:flex">
            <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            <span className="uppercase tracking-wider font-semibold text-[10px]">{activeProvider.name}</span>
          </Badge>
        )}

        {workspace.workspaceId && (
          <Button
            variant="outline" size="sm"
            className="shrink-0 h-7 gap-1.5 border-primary/30 bg-primary/5 text-xs px-2.5"
            onClick={() => workspace.setPanelOpen(o => !o)}
            data-testid="button-toggle-workspace-panel"
          >
            <PanelRightOpen className="h-3.5 w-3.5 text-primary" />
            <span className="hidden sm:inline max-w-[100px] truncate">{workspace.workspace?.name || 'Workspace'}</span>
          </Button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 space-y-6">
        {!convId && !isStreaming ? (
          <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center space-y-8 animate-in fade-in zoom-in duration-500">
            <div className="h-24 w-24 rounded-2xl bg-primary/5 flex items-center justify-center ring-1 ring-primary/20 shadow-[0_0_40px_-10px_rgba(37,99,235,0.3)]">
              <Shield className="h-12 w-12 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight mb-2">X-Ray AI Platform</h1>
              <p className="text-muted-foreground text-sm uppercase tracking-widest font-mono mb-1">Awaiting Operator Input</p>
              {agentMode !== 'general' && (
                <div className={`inline-flex items-center gap-1.5 mt-2 px-3 py-1 rounded-full text-xs font-semibold border ${activeAgent.color} border-current bg-current/10`}>
                  <ActiveAgentIcon className="h-3 w-3" />{activeAgent.label} Agent Active
                </div>
              )}
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {quickPrompts.map((p, i) => (
                <Button
                  key={i}
                  variant="outline"
                  className="bg-card hover:bg-primary hover:text-primary-foreground border-border/50 text-xs py-1 h-auto transition-colors"
                  onClick={() => { setInput(p); textareaRef.current?.focus(); }}
                >
                  <Terminal className="h-3 w-3 me-2 opacity-50" />{p}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto space-y-6">
            {conversation?.messages.map((msg) => {
              const isAssistant = msg.role === 'assistant';
              const isKbImage = msg.image_url?.includes('/api/rag/images/') || msg.image_url?.includes('/api/rag/pages/');

              // Detect gallery results saved in content
              const galleryPayload = isAssistant ? parseGalleryContent(msg.content) : null;
              // Detect Canva chat-tool results saved in content
              const canvaMsgPayload = isAssistant && !galleryPayload ? parseCanvaContent(msg.content) : null;
              // Detect the workspace agent's generated-files trailer saved in content
              const { visibleText: msgVisibleText, files: msgGeneratedFiles } =
                isAssistant && !galleryPayload && !canvaMsgPayload ? parseGeneratedFilesContent(msg.content) : { visibleText: msg.content, files: [] };
              const msgDir = detectDirection(msgVisibleText);
              const isRtl = msgDir === 'rtl';
              // Bubble side stays fixed by role (assistant vs. user); only the
              // column's internal alignment mirrors so RTL text — and any
              // non-full-width content like the timestamp — hugs the reading edge.
              const columnAlign = isAssistant ? (isRtl ? 'items-end' : 'items-start') : 'items-end';

              return (
                <div key={msg.id} className={`flex gap-4 ${isAssistant ? 'justify-start' : 'justify-end'}`}>
                  {isAssistant && (
                    <div className="w-8 h-8 rounded shrink-0 bg-primary/20 flex items-center justify-center ring-1 ring-primary/30 mt-1">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                  )}

                  <div className={`flex flex-col gap-2 ${columnAlign} ${isAssistant ? 'max-w-[92%]' : 'max-w-[85%]'}`}>
                    {/* User-attached scan */}
                    {!isAssistant && msg.image_url && (
                      <div className="rounded-lg overflow-hidden border border-border/50 max-w-sm">
                        <img src={msg.image_url} alt="Attached scan" className="w-full h-auto object-contain bg-black" />
                      </div>
                    )}

                    {/* ColPali / caption retrieved KB image */}
                    {isAssistant && isKbImage && (
                      <div className="rounded-xl overflow-hidden border border-primary/30 shadow-[0_0_20px_-4px_rgba(37,99,235,0.25)] bg-black w-full max-w-xl">
                        <img
                          src={msg.image_url!}
                          alt="Retrieved from knowledge base"
                          className="w-full h-auto object-contain"
                          style={{ maxHeight: '600px' }}
                        />
                        <div dir={msgDir} className={`px-3 py-1.5 bg-card/80 border-t border-primary/20 flex items-center gap-2 ${isRtl ? 'rtl-content' : ''}`}>
                          <ImageIcon className="h-3 w-3 text-primary opacity-70 shrink-0" />
                          <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                            {msg.image_url!.includes('/pages/') ? 'ColPali visual search · rendered page' : 'Caption search · extracted figure'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Gallery results card (rendered from saved __GALLERY__ message).
                        The KB-grounded explanation saved before the marker is shown
                        above the card, so an image request keeps its real answer. */}
                    {galleryPayload ? (
                      <div className="w-full space-y-2">
                        {parseGalleryText(msg.content) && (
                          <div className="px-4 py-3 rounded-lg text-sm leading-relaxed bg-card text-card-foreground border border-border shadow-sm w-full">
                            <MessageContent content={parseGalleryText(msg.content)} />
                          </div>
                        )}
                        <div className="bg-card border border-border rounded-lg p-3 w-full shadow-sm">
                          <ErrorBoundary>
                            <GalleryResultsCard payload={galleryPayload} />
                          </ErrorBoundary>
                        </div>
                      </div>
                    ) : canvaMsgPayload ? (
                      <div className="bg-card border border-border rounded-lg p-3 w-full shadow-sm">
                        <ErrorBoundary>
                          <CanvaResultsCard
                            payload={canvaMsgPayload}
                            pendingMessage=""
                            onImport={(design) => {
                              setInput(`Here's a Canva design I'd like to use: ${design.title || 'Untitled'} — ${design.urls?.edit_url || ''}`);
                              textareaRef.current?.focus();
                            }}
                            onFollowUp={(msg) => handleSubmit(undefined, msg)}
                          />
                        </ErrorBoundary>
                      </div>
                    ) : (
                      /* Regular message bubble */
                      <div className={`px-4 py-3 rounded-lg text-sm leading-relaxed ${
                        isAssistant
                          ? 'bg-card text-card-foreground border border-border shadow-sm w-full'
                          : 'bg-primary text-primary-foreground font-medium whitespace-pre-wrap'
                      }`}>
                        {isAssistant
                          ? <MessageContent content={msgVisibleText} />
                          : <div dir={msgDir} className={isRtl ? 'rtl-content' : ''}>{msgVisibleText}</div>
                        }
                      </div>
                    )}

                    {isAssistant && msgGeneratedFiles.length > 0 && <GeneratedFilesRow files={msgGeneratedFiles} />}

                    <div className="flex items-center gap-1.5 px-1">
                      <span dir="ltr" className="text-[10px] text-muted-foreground font-mono uppercase opacity-50">
                        {new Date(msg.created_at).toLocaleTimeString()}
                      </span>
                      {user && !galleryPayload && (
                        <button
                          type="button"
                          title={pinnedIds.has(msg.id) ? 'Pinned to memory' : 'Pin to memory'}
                          onClick={() => {
                            if (!convId || pinnedIds.has(msg.id)) return;
                            setPinnedIds((prev) => new Set(prev).add(msg.id));
                            pinMessage(convId, msg.id).catch(() => {
                              setPinnedIds((prev) => { const next = new Set(prev); next.delete(msg.id); return next; });
                            });
                          }}
                          className={`opacity-40 hover:opacity-100 transition-opacity ${pinnedIds.has(msg.id) ? 'text-primary opacity-100' : 'text-muted-foreground'}`}
                        >
                          <Pin className="h-2.5 w-2.5" fill={pinnedIds.has(msg.id) ? 'currentColor' : 'none'} />
                        </button>
                      )}
                    </div>
                  </div>

                  {!isAssistant && (
                    <div className="w-8 h-8 rounded shrink-0 bg-secondary flex items-center justify-center ring-1 ring-border mt-1">
                      <User className="h-4 w-4 text-secondary-foreground" />
                    </div>
                  )}
                </div>
              );
            })}

            {/* Streaming UI — shown during streaming AND while waiting for conversation refetch */}
            {(isStreaming || streamingContent) && (
              <div className="flex gap-4 justify-start">
                <div className="w-8 h-8 rounded shrink-0 bg-primary/20 flex items-center justify-center ring-1 ring-primary/30 mt-1 relative overflow-hidden">
                  <div className="absolute inset-0 bg-primary/20 animate-pulse" />
                  <Bot className="h-4 w-4 text-primary relative z-10" />
                </div>
                <div className={`flex flex-col gap-2 max-w-[92%] w-full ${detectDirection(streamingContent) === 'rtl' ? 'items-end' : 'items-start'}`}>
                  {streamingImageUrl && (
                    <div className="rounded-xl overflow-hidden border border-primary/30 max-w-xl shadow-md w-full">
                      <img src={streamingImageUrl} alt="Retrieved" className="w-full h-auto object-contain bg-black" style={{ maxHeight: '500px' }} />
                    </div>
                  )}
                  {streamingAgentEvents.length > 0 && (
                    <AgentExecutionPanel
                      events={streamingAgentEvents}
                      stages={streamingAgentEvents.some((e) => e.stage && ORCHESTRATOR_ONLY_STAGE_KEYS.has(e.stage))
                        ? ORCHESTRATOR_STAGES : undefined}
                    />
                  )}
                  <div className={`px-4 py-3 rounded-lg text-sm leading-relaxed bg-card text-card-foreground border border-primary/30 shadow-[0_0_15px_-3px_rgba(37,99,235,0.2)] w-full ${streamingGalleryResults || streamingCanvaResults ? 'pb-2' : ''}`}>
                    {isThinking && streamingAgentEvents.length === 0 ? (
                      <div className="flex items-center gap-2 text-primary font-mono text-xs font-bold uppercase tracking-widest">
                        <Zap className="h-3 w-3 animate-pulse" />Processing with {activeAgent.label} Agent...
                      </div>
                    ) : (
                      <>
                        {/* Streaming gallery results */}
                        {streamingGalleryResults && (
                          <div className="mb-3">
                            <ErrorBoundary>
                              <GalleryResultsCard payload={streamingGalleryResults} />
                            </ErrorBoundary>
                          </div>
                        )}
                        {/* Streaming Canva results */}
                        {streamingCanvaResults && (
                          <div className="mb-3">
                            <ErrorBoundary>
                              <CanvaResultsCard
                                payload={streamingCanvaResults}
                                pendingMessage={lastSentMessage}
                                onImport={(design) => {
                                  setInput(`Here's a Canva design I'd like to use: ${design.title || 'Untitled'} — ${design.urls?.edit_url || ''}`);
                                  textareaRef.current?.focus();
                                }}
                                onFollowUp={(msg) => handleSubmit(undefined, msg)}
                              />
                            </ErrorBoundary>
                          </div>
                        )}
                        {/* Streaming text */}
                        {streamingContent && (
                          <>
                            <MessageContent content={streamingContent} />
                            <span className="inline-block w-1.5 h-4 bg-primary animate-pulse ms-1 align-middle rounded-sm" />
                          </>
                        )}
                        {!streamingContent && !streamingGalleryResults && !streamingCanvaResults && (
                          <span className="inline-block w-1.5 h-4 bg-primary animate-pulse align-middle rounded-sm" />
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} className="h-4" />
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="p-4 md:p-6 bg-card border-t border-border shrink-0 z-10 shadow-[0_-10px_40px_-10px_rgba(0,0,0,0.3)]">
        <div className="max-w-4xl mx-auto">
          {chatError && (
            <div className="mb-3 flex items-center gap-2 px-4 py-2.5 bg-destructive/10 border border-destructive/30 rounded-lg text-sm text-destructive">
              <span className="flex-1">{chatError}</span>
              <button onClick={() => setChatError('')} className="shrink-0 opacity-70 hover:opacity-100">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          {imageFile && (
            <div className="mb-3 flex items-center gap-3">
              <div className="relative inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-secondary border border-border">
                <ImageIcon className="h-4 w-4 text-primary" />
                <span className="text-xs font-mono truncate max-w-[200px]">{imageFile.name}</span>
                <Button variant="ghost" size="icon" className="h-5 w-5 ms-1 hover:bg-destructive/20 hover:text-destructive rounded-sm" onClick={removeImage}>
                  <X className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}

          {workspace.uploadStatus.phase === 'uploading' && (
            <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/5 border border-primary/20 text-xs">
              <FolderUp className="h-3.5 w-3.5 text-primary shrink-0 animate-pulse" />
              <span className="flex-1 text-muted-foreground">Uploading workspace files… {workspace.uploadStatus.pct}%</span>
            </div>
          )}
          {workspace.uploadStatus.phase === 'done' && workspace.uploadStatus.summary && (
            <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs">
              <FolderOpen className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
              <span className="flex-1 text-muted-foreground">
                Uploaded {workspace.uploadStatus.summary.uploaded} file(s), processed {workspace.uploadStatus.summary.processed}
                {workspace.uploadStatus.summary.failed > 0 ? `, ${workspace.uploadStatus.summary.failed} failed` : ''}
                {workspace.uploadStatus.summary.errors.length > 0 ? `, ${workspace.uploadStatus.summary.errors.length} rejected` : ''}.
              </span>
              <button onClick={() => workspace.setPanelOpen(true)} className="text-primary hover:underline shrink-0">View</button>
            </div>
          )}
          {workspace.uploadStatus.phase === 'error' && (
            <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-destructive/10 border border-destructive/30 text-xs text-destructive">
              <span className="flex-1">{workspace.uploadStatus.message || 'Workspace upload failed.'}</span>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            className="flex items-end gap-2 bg-background border border-border rounded-xl p-2 focus-within:ring-1 focus-within:ring-primary focus-within:border-primary transition-all shadow-inner"
          >
            <DropdownMenu onOpenChange={(open) => { if (open) loadExistingWorkspaces(); }}>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="ghost" size="icon"
                  className="shrink-0 h-10 w-10 text-muted-foreground hover:text-primary rounded-lg"
                  disabled={isStreaming} data-testid="button-attach">
                  <Paperclip className="h-5 w-5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuLabel className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Attach</DropdownMenuLabel>
                <DropdownMenuItem onClick={() => fileInputRef.current?.click()}>
                  <ImageIcon className="h-4 w-4 me-2 opacity-70" />Attach Image (vision)
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Workspace</DropdownMenuLabel>
                <DropdownMenuItem onClick={() => filesInputRef.current?.click()} data-testid="menuitem-upload-files">
                  <FilePlus2 className="h-4 w-4 me-2 opacity-70" />Upload Files
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => folderInputRef.current?.click()} data-testid="menuitem-upload-folder">
                  <FolderUp className="h-4 w-4 me-2 opacity-70" />Upload Folder
                </DropdownMenuItem>
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger data-testid="menuitem-select-workspace">
                    <FolderOpen className="h-4 w-4 me-2 opacity-70" />Select Existing Workspace
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="w-64">
                    {existingWorkspaces.length === 0 ? (
                      <DropdownMenuItem disabled>No saved workspaces yet</DropdownMenuItem>
                    ) : (
                      existingWorkspaces.map((w) => (
                        <DropdownMenuItem key={w.id} onClick={() => workspace.attachExisting(w.id)}>
                          <span className="truncate">{w.name}</span>
                          <span className="ms-auto text-[10px] font-mono text-muted-foreground shrink-0">{w.total_files}</span>
                        </DropdownMenuItem>
                      ))
                    )}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
                <DropdownMenuItem
                  disabled={!workspace.workspaceId}
                  onClick={() => workspace.setPanelOpen(true)}
                  data-testid="menuitem-view-workspace"
                >
                  <PanelRightOpen className="h-4 w-4 me-2 opacity-70" />View Current Workspace
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={!workspace.workspaceId}
                  onClick={() => workspace.clearWorkspace()}
                  className="text-destructive focus:text-destructive"
                  data-testid="menuitem-clear-workspace"
                >
                  <FolderX className="h-4 w-4 me-2 opacity-70" />Clear Workspace
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Connectors</DropdownMenuLabel>
                <DropdownMenuItem
                  onClick={() => handleSubmit(undefined, 'Show my Canva designs')}
                  data-testid="menuitem-import-canva"
                >
                  🎨<span className="ms-2">Import from Canva</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => setLocation('/connectors')}
                  data-testid="menuitem-import-google-drive"
                >
                  🗂️<span className="ms-2">Import from Google Drive</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => setLocation('/connectors')}
                  data-testid="menuitem-local-folder"
                >
                  📁<span className="ms-2">Local Folder</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => setLocation('/rag')}
                  data-testid="menuitem-knowledge-base"
                >
                  <BookOpen className="h-4 w-4 me-2 opacity-70" />Knowledge Base
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => setLocation('/connectors')}
                  data-testid="menuitem-manage-connectors"
                >
                  <Wrench className="h-4 w-4 me-2 opacity-70" />Manage Connectors
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
            <input type="file" multiple className="hidden" ref={filesInputRef} onChange={handleFilesSelected} data-testid="input-upload-files" />
            <input
              type="file" multiple className="hidden" ref={folderInputRef} onChange={handleFolderSelected}
              data-testid="input-upload-folder"
              // @ts-ignore — non-standard attributes for Chromium/Firefox folder picking
              webkitdirectory="" directory=""
            />

            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Query ${activeAgent.label} Agent...`}
              dir={detectDirection(input)}
              className={`min-h-[40px] max-h-[200px] border-0 focus-visible:ring-0 resize-none px-2 py-2.5 bg-transparent ${
                detectDirection(input) === 'rtl' ? 'text-right' : 'text-left'
              }`}
              rows={1}
              disabled={isStreaming}
              data-testid="input-chat"
            />

            <Button
              type="submit" size="icon"
              className={`shrink-0 h-10 w-10 rounded-lg transition-colors ${
                isStreaming
                  ? 'bg-destructive hover:bg-destructive/90 text-destructive-foreground shadow-[0_0_15px_-3px_rgba(220,38,38,0.5)]'
                  : (input.trim() || imageFile)
                    ? 'bg-primary hover:bg-primary/90 text-primary-foreground shadow-[0_0_15px_-3px_rgba(37,99,235,0.4)]'
                    : 'bg-secondary text-muted-foreground cursor-not-allowed'
              }`}
              disabled={(!input.trim() && !imageFile) && !isStreaming}
              data-testid="button-send"
            >
              {isStreaming ? <Square className="h-4 w-4 fill-current" /> : <Send className="h-4 w-4 ms-0.5" />}
            </Button>
          </form>
          <div className="mt-2 flex items-center justify-between px-1">
            <div className={`flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-wider ${activeAgent.color} opacity-60`}>
              <ActiveAgentIcon className="h-3 w-3" />{activeAgent.label} · {activeAgent.desc}
            </div>
            <span className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/40">Authorized Personnel Only</span>
          </div>
        </div>
      </div>

      {workspace.panelOpen && (
        <WorkspacePanel
          workspace={workspace.workspace}
          tree={workspace.tree}
          generatedFiles={workspace.generatedFiles}
          onClose={() => workspace.setPanelOpen(false)}
          onDeleteFile={workspace.removeFile}
          onReindex={workspace.reindex}
          onDeleteWorkspace={workspace.removeWorkspace}
        />
      )}
    </div>
  );
}
