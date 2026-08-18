import { useState, useEffect } from 'react';
import { ImageIcon, Search, X, ChevronLeft, ChevronRight, ZoomIn, Database, Layers, Sparkles, Loader2, AlertCircle, RefreshCw, CheckCircle2, XCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import ReactMarkdown from 'react-markdown';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

interface PageItem {
  id: string;
  doc_filename: string;
  page_num: number;
  indexed: boolean;
  backend: string | null;
}

interface GalleryData {
  total: number;
  pages: PageItem[];
}

interface RagStatus {
  pages_total: number;
  pages_indexed: number;
  images_total: number;
  images_captioned: number;
  colpali_backend: string;
}

interface GalleryStats {
  total_pages: number;
  indexed: number;
  unindexed: number;
}

interface ReindexProgress {
  event: string;
  total?: number;
  done?: number;
  newly_indexed?: number;
  skipped?: number;
  failed?: number;
  total_indexed?: number;
  doc?: string;
  page_num?: number;
  title?: string;
  error?: string;
}

interface IdentifyResult {
  description: string;
}

export default function GalleryPage() {
  const [data, setData] = useState<GalleryData>({ total: 0, pages: [] });
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [galleryStats, setGalleryStats] = useState<GalleryStats | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<PageItem | null>(null);
  const [loading, setLoading] = useState(false);

  // Identify panel state
  const [identifying, setIdentifying] = useState(false);
  const [identifyResult, setIdentifyResult] = useState<IdentifyResult | null>(null);
  const [identifyError, setIdentifyError] = useState<string | null>(null);

  // Reindex state
  const [reindexing, setReindexing] = useState(false);
  const [reindexLog, setReindexLog] = useState<ReindexProgress[]>([]);
  const [reindexDone, setReindexDone] = useState<ReindexProgress | null>(null);
  const [showReindexPanel, setShowReindexPanel] = useState(false);

  const LIMIT = 48;

  const fetchData = () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (debouncedSearch) params.set('doc_filename', debouncedSearch);

    Promise.all([
      fetch(`${API}/api/rag/pages?${params}`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/rag/status`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/gallery/stats`, { credentials: 'include' }).then(r => r.json()),
    ]).then(([pages, st, gs]) => {
      setData(pages);
      setStatus(st);
      setGalleryStats(gs);
    }).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search); setOffset(0); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => { fetchData(); }, [debouncedSearch, offset]);

  // Keyboard navigation for lightbox
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!selected) return;
      if (e.key === 'Escape') setSelected(null);
      if (e.key === 'ArrowRight') navigateLightbox(1);
      if (e.key === 'ArrowLeft') navigateLightbox(-1);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [selected, data]);

  const openLightbox = (page: PageItem) => {
    setSelected(page);
    setIdentifyResult(null);
    setIdentifyError(null);
    setIdentifying(false);
  };

  const navigateLightbox = (dir: number) => {
    if (!selected) return;
    const idx = data.pages.findIndex(p => p.id === selected.id);
    const next = data.pages[idx + dir];
    if (next) openLightbox(next);
  };

  const handleIdentify = async () => {
    if (!selected || identifying) return;
    setIdentifying(true);
    setIdentifyResult(null);
    setIdentifyError(null);
    try {
      const resp = await fetch(`${API}/api/rag/pages/${selected.id}/identify`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || 'Identification failed');
      }
      const result = await resp.json();
      setIdentifyResult(result);
    } catch (e: any) {
      setIdentifyError(e.message || 'Identification failed');
    } finally {
      setIdentifying(false);
    }
  };

  const handleReindex = async () => {
    if (reindexing) return;
    setReindexing(true);
    setReindexLog([]);
    setReindexDone(null);
    setShowReindexPanel(true);

    try {
      const resp = await fetch(`${API}/api/gallery/reindex`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!resp.ok || !resp.body) throw new Error('Reindex request failed');

      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const ev: ReindexProgress = JSON.parse(line);
            if (ev.event === 'complete') {
              setReindexDone(ev);
            } else {
              setReindexLog(prev => [...prev.slice(-49), ev]);
            }
          } catch {}
        }
      }
    } catch (e: any) {
      setReindexLog(prev => [...prev, { event: 'error', error: String(e) }]);
    } finally {
      setReindexing(false);
      fetchData(); // Refresh stats
    }
  };

  // Group pages by document
  const byDoc: Record<string, PageItem[]> = {};
  for (const page of data.pages) {
    const key = page.doc_filename;
    if (!byDoc[key]) byDoc[key] = [];
    byDoc[key].push(page);
  }
  const docNames = Object.keys(byDoc);

  return (
    <div className="flex flex-col h-full bg-background overflow-y-auto">
      {/* Header */}
      <div className="bg-card border-b border-border p-6 shrink-0">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-4 mb-4">
            <div className="h-10 w-10 rounded-lg bg-cyan-500/10 flex items-center justify-center ring-1 ring-cyan-500/30">
              <ImageIcon className="h-5 w-5 text-cyan-400" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold tracking-tight">Image Gallery</h1>
              <p className="text-sm text-muted-foreground font-mono uppercase tracking-wider">Visual Knowledge Base · ColPali Visual Index</p>
            </div>
            {/* Reindex button */}
            <Button
              onClick={handleReindex}
              disabled={reindexing}
              variant="outline"
              size="sm"
              className="shrink-0 border-violet-500/30 text-violet-400 hover:bg-violet-500/10 hover:border-violet-500/50 gap-2"
            >
              {reindexing
                ? <><Loader2 className="h-4 w-4 animate-spin" />Indexing…</>
                : <><RefreshCw className="h-4 w-4" />Reindex Image Gallery</>
              }
            </Button>
          </div>

          {/* Stats */}
          <div className="flex flex-wrap gap-3 mb-4">
            {status && (
              <>
                <Badge variant="outline" className="gap-1.5 text-cyan-400 border-cyan-400/20 bg-cyan-400/5">
                  <Layers className="h-3 w-3" />{status.pages_indexed}/{status.pages_total} pages indexed
                </Badge>
                <Badge variant="outline" className="gap-1.5 text-emerald-400 border-emerald-400/20 bg-emerald-400/5">
                  <ImageIcon className="h-3 w-3" />{status.images_captioned}/{status.images_total} figures captioned
                </Badge>
                <Badge variant="outline" className="gap-1.5 text-violet-400 border-violet-400/20 bg-violet-400/5">
                  <Database className="h-3 w-3" />Backend: {status.colpali_backend}
                </Badge>
              </>
            )}
            {galleryStats && (
              <Badge
                variant="outline"
                className={`gap-1.5 ${galleryStats.unindexed > 0 ? 'text-amber-400 border-amber-400/20 bg-amber-400/5' : 'text-emerald-400 border-emerald-400/20 bg-emerald-400/5'}`}
              >
                <Sparkles className="h-3 w-3" />
                {galleryStats.indexed}/{galleryStats.total_pages} AI-indexed
                {galleryStats.unindexed > 0 && ` · ${galleryStats.unindexed} pending`}
              </Badge>
            )}
          </div>

          {/* Reindex progress panel */}
          {showReindexPanel && (
            <div className="mb-4 rounded-xl border border-violet-500/20 bg-violet-500/5 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-violet-500/20">
                <div className="flex items-center gap-2 text-sm font-semibold text-violet-400">
                  <RefreshCw className={`h-4 w-4 ${reindexing ? 'animate-spin' : ''}`} />
                  {reindexing ? 'Reindexing…' : 'Reindex Complete'}
                </div>
                {!reindexing && (
                  <button onClick={() => setShowReindexPanel(false)} className="text-muted-foreground hover:text-foreground">
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>

              {reindexDone && (
                <div className="px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-3 border-b border-violet-500/10">
                  {[
                    { label: 'Total', value: reindexDone.total ?? 0, color: 'text-foreground' },
                    { label: 'Newly Indexed', value: reindexDone.newly_indexed ?? 0, color: 'text-emerald-400' },
                    { label: 'Skipped', value: reindexDone.skipped ?? 0, color: 'text-muted-foreground' },
                    { label: 'Failed', value: reindexDone.failed ?? 0, color: 'text-rose-400' },
                  ].map(s => (
                    <div key={s.label} className="text-center">
                      <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                      <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">{s.label}</div>
                    </div>
                  ))}
                </div>
              )}

              <div className="max-h-40 overflow-y-auto px-4 py-2 space-y-1">
                {reindexLog.slice(-20).map((ev, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs font-mono">
                    {ev.event === 'indexed' && <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0 mt-0.5" />}
                    {ev.event === 'skip' && <CheckCircle2 className="h-3 w-3 text-muted-foreground shrink-0 mt-0.5" />}
                    {ev.event === 'error' && <XCircle className="h-3 w-3 text-rose-400 shrink-0 mt-0.5" />}
                    {ev.event === 'start' && <Loader2 className="h-3 w-3 text-violet-400 shrink-0 mt-0.5 animate-spin" />}
                    <span className="text-muted-foreground">
                      {ev.event === 'indexed' && `[${ev.done}/${ev.total}] ✓ ${ev.doc} p.${ev.page_num} — ${ev.title}`}
                      {ev.event === 'skip' && `[${ev.done}/${ev.total}] — ${ev.doc} p.${ev.page_num} (already indexed)`}
                      {ev.event === 'error' && `Error: ${ev.error}`}
                      {ev.event === 'start' && `Starting reindex of ${ev.total} pages…`}
                    </span>
                  </div>
                ))}
                {reindexing && (
                  <div className="flex items-center gap-2 text-xs font-mono text-violet-400">
                    <Loader2 className="h-3 w-3 animate-spin" />Processing…
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Search */}
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter by document name..."
              className="pl-10 bg-background"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Gallery Content */}
      <div className="flex-1 p-6 max-w-7xl mx-auto w-full">
        {loading && (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
              Loading gallery...
            </div>
          </div>
        )}

        {!loading && data.total === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
            <div className="h-16 w-16 rounded-2xl bg-card border border-border flex items-center justify-center">
              <ImageIcon className="h-8 w-8 text-muted-foreground opacity-40" />
            </div>
            <p className="text-muted-foreground font-medium">No pages indexed yet</p>
            <p className="text-sm text-muted-foreground/60">Upload a PDF in the Knowledge Base to start building your visual index</p>
          </div>
        )}

        {!loading && docNames.map(docName => (
          <div key={docName} className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-6 w-1 rounded-full bg-cyan-500/60" />
              <h2 className="text-sm font-semibold text-foreground truncate max-w-xl">{docName}</h2>
              <Badge variant="outline" className="text-[10px] font-mono shrink-0">
                {byDoc[docName].length} pages
              </Badge>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-3">
              {byDoc[docName].map(page => (
                <button
                  key={page.id}
                  onClick={() => openLightbox(page)}
                  className="group relative aspect-[3/4] rounded-lg overflow-hidden border border-border/50 hover:border-cyan-500/50 hover:shadow-[0_0_20px_-4px_rgba(6,182,212,0.3)] transition-all bg-black"
                >
                  <img
                    src={`/api/rag/pages/${page.id}`}
                    alt={`${docName} page ${page.page_num}`}
                    className="w-full h-full object-contain"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <ZoomIn className="h-5 w-5 text-white" />
                  </div>
                  <div className="absolute bottom-0 inset-x-0 bg-black/70 px-1.5 py-1 text-[9px] font-mono text-white/80">
                    p.{page.page_num}
                    {page.indexed && <span className="ml-1 text-cyan-400">●</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}

        {/* Pagination */}
        {data.total > LIMIT && (
          <div className="flex items-center justify-center gap-4 pt-6">
            <Button variant="outline" size="sm" onClick={() => setOffset(Math.max(0, offset - LIMIT))} disabled={offset === 0}>
              <ChevronLeft className="h-4 w-4 mr-1" />Prev
            </Button>
            <span className="text-sm text-muted-foreground font-mono">
              {offset + 1}–{Math.min(offset + LIMIT, data.total)} of {data.total}
            </span>
            <Button variant="outline" size="sm" onClick={() => setOffset(offset + LIMIT)} disabled={offset + LIMIT >= data.total}>
              Next<ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        )}
      </div>

      {/* Lightbox */}
      {selected && (
        <div className="fixed inset-0 z-50 bg-black/92 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <button className="absolute top-4 right-4 text-white/60 hover:text-white p-2 rounded-lg hover:bg-white/10 transition-colors z-10" onClick={() => setSelected(null)}>
            <X className="h-6 w-6" />
          </button>
          <button className="absolute left-4 top-1/2 -translate-y-1/2 text-white/60 hover:text-white p-3 rounded-xl hover:bg-white/10 transition-colors z-10" onClick={e => { e.stopPropagation(); navigateLightbox(-1); }}>
            <ChevronLeft className="h-6 w-6" />
          </button>

          <div className="flex flex-col lg:flex-row items-start gap-4 max-w-7xl w-full max-h-[92vh]" onClick={e => e.stopPropagation()}>
            {/* Image column */}
            <div className="flex flex-col items-center gap-3 lg:flex-1 min-w-0">
              <img
                src={`/api/rag/pages/${selected.id}`}
                alt={`Page ${selected.page_num}`}
                className="max-h-[70vh] lg:max-h-[80vh] max-w-full object-contain rounded-lg shadow-2xl"
              />
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm text-white/70 font-medium truncate max-w-xs">{selected.doc_filename}</span>
                <span className="text-white/30">·</span>
                <span className="text-sm text-white/70">Page {selected.page_num}</span>
                {selected.indexed && (
                  <>
                    <span className="text-white/30">·</span>
                    <span className="text-cyan-400 flex items-center gap-1 text-xs">
                      <Database className="h-3 w-3" />{selected.backend} indexed
                    </span>
                  </>
                )}
              </div>
              <Button onClick={handleIdentify} disabled={identifying} className="bg-violet-600 hover:bg-violet-500 text-white border-0 gap-2 px-5" size="sm">
                {identifying ? <><Loader2 className="h-4 w-4 animate-spin" />Analysing…</> : <><Sparkles className="h-4 w-4" />Identify Image</>}
              </Button>
            </div>

            {/* Identify result panel */}
            {(identifyResult || identifyError || identifying) && (
              <div className="lg:w-[420px] xl:w-[480px] shrink-0 bg-zinc-900/95 border border-white/10 rounded-xl overflow-hidden flex flex-col max-h-[80vh]">
                <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10 shrink-0">
                  <Sparkles className="h-4 w-4 text-violet-400" />
                  <span className="text-sm font-semibold text-white">AI Image Identification</span>
                  <span className="ml-auto text-[10px] font-mono text-white/40 truncate max-w-[180px]">
                    {selected.doc_filename} · p.{selected.page_num}
                  </span>
                </div>
                <div className="overflow-y-auto flex-1 p-4">
                  {identifying && (
                    <div className="flex flex-col items-center justify-center py-12 gap-3 text-white/50">
                      <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
                      <p className="text-sm">GPT Vision is analysing the image…</p>
                    </div>
                  )}
                  {identifyError && !identifying && (
                    <div className="flex items-start gap-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                      <AlertCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                      <p className="text-sm text-red-300">{identifyError}</p>
                    </div>
                  )}
                  {identifyResult && !identifying && (
                    <div className="prose prose-sm prose-invert max-w-none
                      prose-headings:text-white prose-headings:font-semibold prose-headings:text-sm
                      prose-p:text-white/80 prose-p:leading-relaxed
                      prose-strong:text-white prose-strong:font-semibold
                      prose-ul:text-white/80 prose-li:marker:text-violet-400
                      prose-li:text-white/80">
                      <ReactMarkdown>{identifyResult.description}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <button className="absolute right-4 top-1/2 -translate-y-1/2 text-white/60 hover:text-white p-3 rounded-xl hover:bg-white/10 transition-colors z-10" onClick={e => { e.stopPropagation(); navigateLightbox(1); }}>
            <ChevronRight className="h-6 w-6" />
          </button>
        </div>
      )}
    </div>
  );
}
