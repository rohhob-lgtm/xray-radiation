import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  ChevronLeft, ChevronRight, Download, ZoomIn, ZoomOut,
  RotateCcw, Check, X, Plus, Trash2, Edit3, Eye, EyeOff,
  RefreshCw, Loader2, AlertTriangle, CheckCircle2, Image as ImageIcon,
  Layers, Move, Type, Palette,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

// ── Types ─────────────────────────────────────────────────────────────────────

interface BBox { x: number; y: number; w: number; h: number }

interface Region {
  id: string;
  bbox: BBox;
  source_text: string;
  translated_text: string;
  confidence: number;
  is_technical_code: boolean;
  font_size: number;
  font_color: string;
  edited: boolean;
  approved: boolean;
  keep_english: boolean;
  quality_issues?: { type: string; severity: string; message: string }[];
}

interface ProjectImage {
  id: string;
  project_id: string;
  doc_page: number;
  doc_type: string;
  image_index: number;
  width_px: number;
  height_px: number;
  region_count: number;
  status: string;
  error_msg: string | null;
  has_original: boolean;
  has_rendered: boolean;
  regions?: Region[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const _BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
const API = (path: string) => `${_BASE}/api${path}`;

async function apiFetch(path: string, opts?: RequestInit) {
  const r = await fetch(API(path), { credentials: 'include', ...opts });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

const STATUS_BADGE: Record<string, string> = {
  done:       'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  no_text:    'bg-slate-500/10 text-slate-400 border-slate-500/20',
  pending:    'bg-amber-500/10 text-amber-400 border-amber-500/20',
  processing: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  error:      'bg-red-500/10 text-red-400 border-red-500/20',
};

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TranslationImageEditor() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [, setLocation] = useLocation();
  const { toast } = useToast();

  const [images, setImages] = useState<ProjectImage[]>([]);
  const [selectedImgId, setSelectedImgId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProjectImage & { regions: Region[] } | null>(null);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'original' | 'translated' | 'side-by-side'>('side-by-side');
  const [zoom, setZoom] = useState(100);
  const [showBoxes, setShowBoxes] = useState(true);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [analyzeProgress, setAnalyzeProgress] = useState<{ done: number; total: number; current: string }>({ done: 0, total: 0, current: '' });
  const [undoStack, setUndoStack] = useState<Region[][]>([]);
  const abortRef = useRef<AbortController | null>(null);

  // ── Load image list ──────────────────────────────────────────────────────

  const loadImages = useCallback(async () => {
    try {
      const data = await apiFetch(`/translation/projects/${projectId}/images`);
      setImages(data.images || []);
      if (!selectedImgId && data.images?.length > 0) {
        setSelectedImgId(data.images[0].id);
      }
    } catch (e: any) {
      toast({ title: 'Error loading images', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [projectId, selectedImgId]);

  useEffect(() => { loadImages(); }, [loadImages]);

  // ── Load detail when selection changes ───────────────────────────────────

  useEffect(() => {
    if (!selectedImgId) return;
    setDetail(null);
    setSelectedRegionId(null);
    apiFetch(`/translation/projects/${projectId}/images/${selectedImgId}`)
      .then(d => {
        setDetail(d);
        const vals: Record<string, string> = {};
        (d.regions || []).forEach((r: Region) => { vals[r.id] = r.translated_text; });
        setEditValues(vals);
      })
      .catch(e => toast({ title: 'Error', description: e.message, variant: 'destructive' }));
  }, [selectedImgId, projectId]);

  // ── Analyze all images SSE ────────────────────────────────────────────────

  const analyzeImages = async () => {
    setAnalyzing(true);
    setAnalyzeProgress({ done: 0, total: 0, current: 'Starting…' });
    abortRef.current = new AbortController();
    try {
      const resp = await fetch(API(`/translation/projects/${projectId}/images/analyze`), {
        method: 'POST',
        credentials: 'include',
        signal: abortRef.current.signal,
      });
      const reader = resp.body?.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const d = JSON.parse(line.slice(6));
            if (d.type === 'extract_done') {
              setAnalyzeProgress(p => ({ ...p, total: d.found, current: `Found ${d.found} images` }));
            } else if (d.type === 'image_start') {
              setAnalyzeProgress(p => ({ ...p, current: `Processing page ${d.page} (${d.num}/${d.total})` }));
            } else if (d.type === 'image_done') {
              setAnalyzeProgress(p => ({ ...p, done: p.done + 1, current: `Done: ${d.regions} regions` }));
            } else if (d.type === 'done') {
              setAnalyzeProgress({ done: d.total, total: d.total, current: `Complete — ${d.with_text} images translated` });
              await loadImages();
            }
          } catch {}
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        toast({ title: 'Analysis failed', description: e.message, variant: 'destructive' });
      }
    } finally {
      setAnalyzing(false);
    }
  };

  // ── Save a region edit ────────────────────────────────────────────────────

  const saveRegion = async (regionId: string, patch: Partial<Region>) => {
    if (!detail) return;
    // Push undo snapshot
    setUndoStack(s => [...s.slice(-19), detail.regions]);
    try {
      await apiFetch(`/translation/projects/${projectId}/images/${selectedImgId}/regions/${regionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      setDetail(d => d ? {
        ...d,
        regions: d.regions.map(r => r.id === regionId ? { ...r, ...patch } : r),
      } : d);
      toast({ title: 'Region updated' });
    } catch (e: any) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    }
  };

  // ── Re-render image after edits ───────────────────────────────────────────

  const renderImage = async () => {
    if (!selectedImgId) return;
    setRendering(true);
    try {
      await apiFetch(`/translation/projects/${projectId}/images/${selectedImgId}/render`, { method: 'POST' });
      // Bust cache by re-selecting
      const prev = selectedImgId;
      setSelectedImgId(null);
      setTimeout(() => setSelectedImgId(prev), 50);
      await loadImages();
      toast({ title: 'Image re-rendered' });
    } catch (e: any) {
      toast({ title: 'Render failed', description: e.message, variant: 'destructive' });
    } finally {
      setRendering(false);
    }
  };

  // ── Delete region ─────────────────────────────────────────────────────────

  const deleteRegion = async (regionId: string) => {
    if (!confirm('Delete this text region?')) return;
    if (!detail) return;
    setUndoStack(s => [...s.slice(-19), detail.regions]);
    try {
      await apiFetch(`/translation/projects/${projectId}/images/${selectedImgId}/regions/${regionId}`, { method: 'DELETE' });
      setDetail(d => d ? { ...d, regions: d.regions.filter(r => r.id !== regionId) } : d);
      if (selectedRegionId === regionId) setSelectedRegionId(null);
      toast({ title: 'Region deleted' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  // ── Re-translate single region ────────────────────────────────────────────

  const retranslateRegion = async (regionId: string) => {
    try {
      const data = await apiFetch(
        `/translation/projects/${projectId}/images/${selectedImgId}/regions/${regionId}/retranslate`,
        { method: 'POST' }
      );
      setDetail(d => d ? {
        ...d,
        regions: d.regions.map(r => r.id === regionId
          ? { ...r, translated_text: data.translated_text, edited: true }
          : r),
      } : d);
      setEditValues(v => ({ ...v, [regionId]: data.translated_text }));
      toast({ title: 'Region re-translated' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  // ── Undo ─────────────────────────────────────────────────────────────────

  const undo = () => {
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    setUndoStack(s => s.slice(0, -1));
    setDetail(d => d ? { ...d, regions: prev } : d);
    toast({ title: 'Undo applied' });
  };

  const selectedRegion = detail?.regions.find(r => r.id === selectedRegionId);
  const selectedImage = images.find(i => i.id === selectedImgId);

  // ── Image URL helpers (cache-bust by including timestamp on render) ────────
  const imgCacheBust = Date.now();
  const originalUrl  = selectedImgId ? API(`/translation/projects/${projectId}/images/${selectedImgId}/original`) : '';
  const renderedUrl  = selectedImgId ? API(`/translation/projects/${projectId}/images/${selectedImgId}/rendered?t=${imgCacheBust}`) : '';

  if (loading) return (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );

  return (
    <div className="flex h-full overflow-hidden bg-background">

      {/* ── Left panel: image list ─────────────────────────────────────────── */}
      <div className="w-56 shrink-0 border-r border-border bg-card/30 flex flex-col overflow-hidden">
        <div className="px-3 py-3 border-b border-border flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs px-2"
            onClick={() => setLocation(`/translation`)}>
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span className="text-xs font-semibold text-foreground truncate">Images</span>
          <Badge variant="outline" className="text-[10px] ml-auto">{images.length}</Badge>
        </div>

        {/* Analyze button */}
        <div className="px-3 py-2 border-b border-border">
          <Button size="sm" className="w-full h-8 text-xs gap-1.5"
            onClick={analyzeImages} disabled={analyzing}>
            {analyzing
              ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Analyzing…</>
              : <><RefreshCw className="h-3.5 w-3.5" /> Analyze Images</>}
          </Button>
          {analyzing && (
            <div className="mt-2 text-[10px] text-muted-foreground leading-tight">
              {analyzeProgress.current}
              {analyzeProgress.total > 0 && ` (${analyzeProgress.done}/${analyzeProgress.total})`}
            </div>
          )}
        </div>

        {/* Image list */}
        <div className="flex-1 overflow-y-auto py-1">
          {images.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              No images found.<br />Click "Analyze Images" to extract and translate.
            </div>
          ) : (
            images.map(img => (
              <button key={img.id}
                onClick={() => setSelectedImgId(img.id)}
                className={`w-full text-left px-3 py-2 text-xs transition-all border-l-2
                  ${selectedImgId === img.id
                    ? 'bg-primary/10 border-primary text-foreground'
                    : 'border-transparent hover:bg-accent text-muted-foreground hover:text-foreground'}`}>
                <div className="flex items-center gap-2">
                  <ImageIcon className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">P{img.doc_page} #{img.image_index + 1}</span>
                  <span className={`ml-auto shrink-0 px-1.5 py-0.5 rounded text-[9px] border ${STATUS_BADGE[img.status] || STATUS_BADGE.pending}`}>
                    {img.status === 'done' ? `${img.region_count}r` : img.status}
                  </span>
                </div>
                <div className="text-[10px] mt-0.5 opacity-60">{img.doc_type.replace('_', ' ')}</div>
              </button>
            ))
          )}
        </div>

        {/* Downloads */}
        <div className="px-3 py-2 border-t border-border space-y-1">
          <a href={API(`/translation/projects/${projectId}/export/zip`)} download>
            <Button size="sm" variant="outline" className="w-full h-7 text-[11px] gap-1.5">
              <Download className="h-3 w-3" /> Download ZIP
            </Button>
          </a>
          <a href={API(`/translation/projects/${projectId}/export/quality-report`)} download>
            <Button size="sm" variant="ghost" className="w-full h-7 text-[11px] gap-1.5">
              <Download className="h-3 w-3" /> Quality Report
            </Button>
          </a>
        </div>
      </div>

      {/* ── Center: image viewer ───────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Toolbar */}
        <div className="border-b border-border bg-card/30 px-4 py-2 flex items-center gap-3 shrink-0">
          {/* View mode */}
          <div className="flex items-center bg-muted rounded-lg p-0.5 gap-0.5">
            {(['original', 'translated', 'side-by-side'] as const).map(m => (
              <button key={m}
                onClick={() => setViewMode(m)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all
                  ${viewMode === m ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
                {m === 'side-by-side' ? 'Side by Side' : m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>

          {/* Zoom */}
          <div className="flex items-center gap-1.5">
            <button onClick={() => setZoom(z => Math.max(30, z - 20))}
              className="h-7 w-7 rounded hover:bg-accent flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors">
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <span className="text-xs text-muted-foreground w-10 text-center">{zoom}%</span>
            <button onClick={() => setZoom(z => Math.min(300, z + 20))}
              className="h-7 w-7 rounded hover:bg-accent flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors">
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <button onClick={() => setZoom(100)}
              className="text-[10px] text-muted-foreground hover:text-foreground px-1.5">Reset</button>
          </div>

          {/* Bounding boxes toggle */}
          <button onClick={() => setShowBoxes(!showBoxes)}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md transition-colors
              ${showBoxes ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground'}`}>
            {showBoxes ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            Boxes
          </button>

          {/* Actions */}
          <div className="ml-auto flex items-center gap-2">
            <button onClick={undo} disabled={undoStack.length === 0}
              className="h-7 px-2.5 rounded-md border border-border text-xs text-muted-foreground hover:text-foreground disabled:opacity-40 transition-colors flex items-center gap-1.5">
              <RotateCcw className="h-3 w-3" /> Undo
            </button>
            <Button size="sm" className="h-7 text-xs gap-1.5" onClick={renderImage} disabled={rendering || !selectedImgId}>
              {rendering ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Re-Render
            </Button>
          </div>
        </div>

        {/* Image canvas area */}
        <div className="flex-1 overflow-auto bg-[#0d1117] p-4">
          {!selectedImgId ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <div className="text-center">
                <ImageIcon className="h-12 w-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">Select an image from the list</p>
              </div>
            </div>
          ) : !detail ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : (
            <div className={`flex gap-4 ${viewMode === 'side-by-side' ? 'flex-row items-start' : 'flex-col items-start'}`}>
              {/* Original */}
              {(viewMode === 'original' || viewMode === 'side-by-side') && (
                <ImagePanel
                  label="Original"
                  imgUrl={originalUrl}
                  regions={detail.regions}
                  selectedRegionId={selectedRegionId}
                  showBoxes={showBoxes}
                  zoom={zoom}
                  showTranslated={false}
                  onSelectRegion={setSelectedRegionId}
                />
              )}
              {/* Translated */}
              {(viewMode === 'translated' || viewMode === 'side-by-side') && (
                <ImagePanel
                  label="Translated"
                  imgUrl={renderedUrl}
                  regions={detail.regions}
                  selectedRegionId={selectedRegionId}
                  showBoxes={showBoxes}
                  zoom={zoom}
                  showTranslated
                  onSelectRegion={setSelectedRegionId}
                />
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Right panel: region editor ─────────────────────────────────────── */}
      <div className="w-72 shrink-0 border-l border-border bg-card/30 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-xs font-semibold text-foreground uppercase tracking-widest">
            {selectedRegion ? 'Edit Region' : 'Region Inspector'}
          </h3>
          {selectedImage && (
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Page {selectedImage.doc_page} — {detail?.regions.length ?? 0} regions
            </p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {!selectedRegion ? (
            <div className="px-4 py-6 text-center text-xs text-muted-foreground">
              <Layers className="h-8 w-8 mx-auto mb-2 opacity-20" />
              Click a bounding box on the image to select a text region.
            </div>
          ) : (
            <RegionEditor
              region={selectedRegion}
              editValue={editValues[selectedRegion.id] ?? selectedRegion.translated_text}
              onEditValueChange={v => setEditValues(ev => ({ ...ev, [selectedRegion.id]: v }))}
              onSave={async () => {
                await saveRegion(selectedRegion.id, {
                  translated_text: editValues[selectedRegion.id] ?? selectedRegion.translated_text,
                });
              }}
              onDelete={() => deleteRegion(selectedRegion.id)}
              onRetranslate={() => retranslateRegion(selectedRegion.id)}
              onApprove={() => saveRegion(selectedRegion.id, { approved: !selectedRegion.approved })}
              onFontSizeChange={s => saveRegion(selectedRegion.id, { font_size: s })}
              onFontColorChange={c => saveRegion(selectedRegion.id, { font_color: c })}
              onKeepEnglishChange={k => saveRegion(selectedRegion.id, { keep_english: k })}
            />
          )}

          {/* All regions list */}
          {detail && detail.regions.length > 0 && (
            <div className="border-t border-border mt-2 pt-2">
              <div className="px-4 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
                All Regions ({detail.regions.length})
              </div>
              <div className="space-y-0.5 pb-4">
                {detail.regions.map(r => (
                  <button key={r.id}
                    onClick={() => setSelectedRegionId(r.id)}
                    className={`w-full text-left px-4 py-2 text-xs transition-all border-l-2
                      ${selectedRegionId === r.id
                        ? 'bg-primary/10 border-primary text-foreground'
                        : 'border-transparent hover:bg-accent text-muted-foreground hover:text-foreground'}`}>
                    <div className="flex items-center gap-2">
                      {r.approved && <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />}
                      {r.is_technical_code && <span className="text-[9px] bg-slate-500/20 text-slate-400 px-1 rounded shrink-0">code</span>}
                      {r.confidence < 0.5 && <AlertTriangle className="h-3 w-3 text-amber-400 shrink-0" />}
                      <span className="truncate">{r.source_text || '(empty)'}</span>
                    </div>
                    <div className="text-[10px] mt-0.5 text-primary/60 truncate" dir="rtl">
                      {r.translated_text}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Image panel with bbox overlays ────────────────────────────────────────────

function ImagePanel({
  label, imgUrl, regions, selectedRegionId, showBoxes, zoom, showTranslated, onSelectRegion,
}: {
  label: string;
  imgUrl: string;
  regions: Region[];
  selectedRegionId: string | null;
  showBoxes: boolean;
  zoom: number;
  showTranslated: boolean;
  onSelectRegion: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-mono font-semibold text-muted-foreground uppercase tracking-widest">{label}</span>
        {showTranslated && (
          <span className="text-[9px] text-primary/60 bg-primary/10 px-1.5 rounded">Arabic RTL</span>
        )}
      </div>
      <div className="relative inline-block" style={{ width: 'fit-content' }}>
        <img
          src={imgUrl}
          alt={label}
          draggable={false}
          style={{ display: 'block', transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }}
          className="rounded-lg max-w-none border border-border/40 shadow-xl"
          onError={e => (e.currentTarget.style.display = 'none')}
        />
        {showBoxes && (
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }}>
            {regions.map(r => (
              <BBoxOverlay
                key={r.id}
                region={r}
                selected={selectedRegionId === r.id}
                showTranslated={showTranslated}
                onClick={() => onSelectRegion(r.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Bounding box overlay ──────────────────────────────────────────────────────

function BBoxOverlay({ region, selected, showTranslated, onClick }: {
  region: Region;
  selected: boolean;
  showTranslated: boolean;
  onClick: () => void;
}) {
  const { bbox } = region;
  const hasIssues = (region.quality_issues?.length ?? 0) > 0;
  const isTechCode = region.is_technical_code || region.keep_english;

  const borderColor = selected
    ? '#60a5fa'
    : hasIssues
    ? '#f59e0b'
    : isTechCode
    ? '#8b5cf6'
    : region.approved
    ? '#22c55e'
    : 'rgba(96,165,250,0.5)';

  return (
    <div
      onClick={e => { e.stopPropagation(); onClick(); }}
      style={{
        position: 'absolute',
        left: `${bbox.x}%`,
        top: `${bbox.y}%`,
        width: `${bbox.w}%`,
        height: `${bbox.h}%`,
        border: `2px solid ${borderColor}`,
        background: selected ? 'rgba(96,165,250,0.1)' : 'transparent',
        boxSizing: 'border-box',
        cursor: 'pointer',
        pointerEvents: 'all',
        zIndex: selected ? 20 : 10,
        borderRadius: '2px',
      }}>
      {selected && (
        <div
          style={{
            position: 'absolute',
            top: '-18px',
            left: 0,
            background: '#1e3a5f',
            color: '#93c5fd',
            fontSize: '9px',
            padding: '1px 5px',
            borderRadius: '3px',
            whiteSpace: 'nowrap',
            maxWidth: '200px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
          {showTranslated ? region.translated_text : region.source_text}
        </div>
      )}
    </div>
  );
}

// ── Region editor panel ───────────────────────────────────────────────────────

function RegionEditor({
  region, editValue, onEditValueChange, onSave, onDelete, onRetranslate, onApprove,
  onFontSizeChange, onFontColorChange, onKeepEnglishChange,
}: {
  region: Region;
  editValue: string;
  onEditValueChange: (v: string) => void;
  onSave: () => void;
  onDelete: () => void;
  onRetranslate: () => void;
  onApprove: () => void;
  onFontSizeChange: (s: number) => void;
  onFontColorChange: (c: string) => void;
  onKeepEnglishChange: (k: boolean) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [retranslating, setRetranslating] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try { await onSave(); } finally { setSaving(false); }
  };
  const handleRetranslate = async () => {
    setRetranslating(true);
    try { await onRetranslate(); } finally { setRetranslating(false); }
  };

  return (
    <div className="px-4 py-3 space-y-4">
      {/* Status badges */}
      <div className="flex flex-wrap gap-1.5">
        <span className={`px-2 py-0.5 rounded-full text-[10px] border
          ${region.confidence >= 0.8 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
            region.confidence >= 0.5 ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
            'bg-red-500/10 text-red-400 border-red-500/20'}`}>
          {(region.confidence * 100).toFixed(0)}% conf
        </span>
        {region.is_technical_code && (
          <span className="px-2 py-0.5 rounded-full text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20">
            Technical Code
          </span>
        )}
        {region.approved && (
          <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            ✓ Approved
          </span>
        )}
        {region.edited && (
          <span className="px-2 py-0.5 rounded-full text-[10px] bg-violet-500/10 text-violet-400 border border-violet-500/20">
            Edited
          </span>
        )}
      </div>

      {/* Source text (read-only) */}
      <div>
        <Label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5 block">
          Original Text
        </Label>
        <div className="text-xs bg-muted/40 rounded-lg p-2.5 text-foreground/80 leading-relaxed border border-border/50">
          {region.source_text || <span className="italic text-muted-foreground">(empty)</span>}
        </div>
      </div>

      {/* Arabic translation (editable) */}
      <div>
        <Label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5 block">
          Arabic Translation
        </Label>
        <textarea
          value={editValue}
          onChange={e => onEditValueChange(e.target.value)}
          dir="rtl"
          className="w-full text-sm bg-background border border-border/60 rounded-lg p-2.5 resize-none focus:outline-none focus:ring-1 focus:ring-primary min-h-[80px] text-right leading-relaxed"
          placeholder="ترجمة عربية…"
        />
        <div className="flex gap-2 mt-2">
          <Button size="sm" className="flex-1 h-7 text-xs gap-1" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
            Save
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1 px-2"
            onClick={handleRetranslate} disabled={retranslating}
            title="Re-translate with GPT-4o">
            {retranslating ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          </Button>
        </div>
      </div>

      {/* Font controls */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5 block">
            Font Size (px)
          </Label>
          <Input
            type="number"
            min={8} max={72}
            value={region.font_size}
            onChange={e => onFontSizeChange(parseInt(e.target.value) || 14)}
            className="h-7 text-xs"
          />
        </div>
        <div>
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5 block">
            Text Color
          </Label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={region.font_color || '#000000'}
              onChange={e => onFontColorChange(e.target.value)}
              className="h-7 w-10 cursor-pointer rounded border border-border bg-transparent"
            />
            <span className="text-[10px] text-muted-foreground font-mono">{region.font_color}</span>
          </div>
        </div>
      </div>

      {/* Keep English toggle */}
      <div className="flex items-center justify-between py-1">
        <div>
          <div className="text-xs font-medium text-foreground">Keep English</div>
          <div className="text-[10px] text-muted-foreground">Don't overlay translation on this region</div>
        </div>
        <button
          onClick={() => onKeepEnglishChange(!region.keep_english)}
          className={`w-9 h-5 rounded-full transition-colors relative ${region.keep_english ? 'bg-primary' : 'bg-muted'}`}>
          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform
            ${region.keep_english ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
      </div>

      {/* Position info */}
      <div className="bg-muted/30 rounded-lg p-2.5 text-[10px] font-mono text-muted-foreground space-y-0.5 border border-border/50">
        <div className="font-semibold text-muted-foreground/60 uppercase mb-1">Position</div>
        <div>X: {region.bbox.x.toFixed(1)}%  Y: {region.bbox.y.toFixed(1)}%</div>
        <div>W: {region.bbox.w.toFixed(1)}%  H: {region.bbox.h.toFixed(1)}%</div>
      </div>

      {/* Quality issues */}
      {region.quality_issues && region.quality_issues.length > 0 && (
        <div className="space-y-1.5">
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider block">
            Quality Issues
          </Label>
          {region.quality_issues.map((qi, i) => (
            <div key={i} className={`text-[10px] rounded-lg p-2 border
              ${qi.severity === 'error'
                ? 'bg-red-500/5 border-red-500/20 text-red-400'
                : 'bg-amber-500/5 border-amber-500/20 text-amber-400'}`}>
              <div className="font-semibold uppercase text-[9px] mb-0.5">{qi.severity}</div>
              {qi.message}
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1 border-t border-border">
        <Button
          size="sm" variant="outline"
          className={`flex-1 h-7 text-xs gap-1 ${region.approved ? 'border-emerald-500/30 text-emerald-400' : ''}`}
          onClick={onApprove}>
          <CheckCircle2 className="h-3 w-3" />
          {region.approved ? 'Approved' : 'Approve'}
        </Button>
        <Button size="sm" variant="ghost"
          className="h-7 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10"
          onClick={onDelete}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
