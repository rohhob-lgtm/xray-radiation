import { useState, useRef, useCallback, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Brain, CheckCircle2, Clock, XCircle, ChevronDown, ChevronRight,
  BarChart3, BookOpen, Network, Zap, AlertTriangle,
  RefreshCw, FileText, Target, Lightbulb,
  Wrench, TrendingUp, Activity, Search, Upload, Globe, FolderOpen,
  Layers, GraduationCap, Tag, Eye, Database, BookMarked,
  Presentation, Link2, Sparkles, CheckCheck, FileUp, X,
  PlayCircle, Cpu, Info, ChevronUp, Pause, Play, RotateCcw,
  DollarSign, Shield, HardDrive, Timer, Wifi, Rocket,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/use-toast';
import { AutonomousResearchPanel } from '@/components/autonomous-research-panel';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${API}${path}`, { credentials: 'include', ...opts });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Data hooks ─────────────────────────────────────────────────────────────────

function useLearningStats() {
  return useQuery({
    queryKey: ['learning-stats'],
    queryFn: () => apiFetch('/api/learning/stats'),
    refetchInterval: 15_000,
  });
}

function useStudyJobs(status?: string) {
  return useQuery({
    queryKey: ['study-jobs', status],
    queryFn: () => apiFetch(`/api/study/jobs${status ? `?status=${status}` : ''}`),
    refetchInterval: 10_000,
  });
}

function useReport() {
  return useQuery({
    queryKey: ['study-report'],
    queryFn: () => apiFetch('/api/study/report'),
    refetchInterval: 60_000,
  });
}

function useTerminology(query: string, category: string) {
  return useQuery({
    queryKey: ['terminology', query, category],
    queryFn: () => apiFetch(`/api/learning/terminology?query=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&limit=100`),
    refetchInterval: 60_000,
  });
}

function useLayoutStyles() {
  return useQuery({
    queryKey: ['layout-styles'],
    queryFn: () => apiFetch('/api/learning/styles'),
    refetchInterval: 60_000,
  });
}

function useExamPatterns(topic: string, bloom: string, difficulty: string) {
  return useQuery({
    queryKey: ['exam-patterns', topic, bloom, difficulty],
    queryFn: () => apiFetch(`/api/learning/exam-patterns?topic=${encodeURIComponent(topic)}&bloom=${encodeURIComponent(bloom)}&difficulty=${encodeURIComponent(difficulty)}&limit=50`),
    refetchInterval: 60_000,
  });
}

function useTranslationProjects() {
  return useQuery({
    queryKey: ['translation-projects'],
    queryFn: () => apiFetch('/api/translation/projects'),
    staleTime: 30_000,
  });
}

function useLearningReport() {
  return useQuery({
    // The Report tab renders the { summary, knowledge_bank, quality } shape,
    // which /api/study/report returns. /api/learning/report returns a different
    // period/totals shape and would render an empty report.
    queryKey: ['learning-report'],
    queryFn: () => apiFetch('/api/study/report'),
    refetchInterval: 120_000,
  });
}

function useVisionStats() {
  return useQuery({
    queryKey: ['vision-stats'],
    queryFn: () => apiFetch('/api/vision/stats'),
    staleTime: 60_000,
  });
}

// ── Shared helpers ─────────────────────────────────────────────────────────────

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const v = value ?? 0;
  const color = v >= 80 ? 'bg-green-500' : v >= 60 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-36 text-muted-foreground shrink-0 text-xs">{label}</span>
      <div className="flex-1 bg-muted rounded-full h-1.5">
        <div className={`h-1.5 rounded-full transition-all ${color}`} style={{ width: `${v}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-xs tabular-nums">{v}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string }> = {
    pending:           { label: 'Uploaded',    className: 'bg-slate-500/20 text-slate-400 border-slate-500/30' },
    processing:        { label: 'Extracting', className: 'bg-blue-500/20 text-blue-400 border-blue-500/30 animate-pulse' },
    studying:          { label: 'Studying…',  className: 'bg-blue-500/20 text-blue-400 border-blue-500/30 animate-pulse' },
    validating:        { label: 'Validating', className: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30 animate-pulse' },
    learning:          { label: 'Learning…',  className: 'bg-purple-500/20 text-purple-400 border-purple-500/30 animate-pulse' },
    integrated:        { label: 'Integrated', className: 'bg-green-500/20 text-green-400 border-green-500/30' },
    approved:          { label: 'Integrated', className: 'bg-green-500/20 text-green-400 border-green-500/30' },
    awaiting_approval: { label: 'Validating', className: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' },
    stalled:           { label: 'Stalled',    className: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
    failed:            { label: 'Failed',     className: 'bg-red-500/20 text-red-400 border-red-500/30' },
    error:             { label: 'Failed',     className: 'bg-red-500/20 text-red-400 border-red-500/30' },
    cancelled:         { label: 'Cancelled',  className: 'bg-slate-500/20 text-slate-400 border-slate-500/30' },
    rejected:          { label: 'Cancelled',  className: 'bg-slate-500/20 text-slate-400 border-slate-500/30' },
  };
  const cfg = map[status] ?? { label: status, className: 'bg-muted text-muted-foreground' };
  return <Badge variant="outline" className={`text-[10px] font-mono uppercase ${cfg.className}`}>{cfg.label}</Badge>;
}

// ── File upload with real pipeline-stage progress ──────────────────────────────

type UploadStage = 'uploading' | 'extracting' | 'studying' | 'generating' | 'integrating' | 'completed' | 'error';

interface UploadEntry {
  id: string;
  name: string;
  pct: number;           // 0-100 overall progress
  uploadPct: number;     // raw byte progress during chunked upload
  stage: UploadStage;
  label: string;         // human-readable stage label
  error?: string;
  docId?: string;
  jobId?: string;        // ProcessingJob id (persisted to localStorage)
  nodes?: number;
  edges?: number;
  // Chunked upload fields
  uploadedBytes?: number;
  totalBytes?: number;
  speedBps?: number;
  etaSeconds?: number;
  currentChunk?: number;
  totalChunks?: number;
  retryCount?: number;
  isPaused?: boolean;
  // Cost gate
  costData?: { estimated_cost_usd: number; limit_usd: number };
}

interface UploadLimits {
  max_upload_size_mb: number;
  chunked_upload_threshold_mb: number;
  upload_chunk_size_mb: number;
  max_study_cost_per_file_usd: number;
}

const STAGE_ORDER: UploadStage[] = ['uploading', 'extracting', 'studying', 'generating', 'integrating', 'completed'];

const LS_KEY = 'xray_upload_jobs';

function loadPersistedJobs(): UploadEntry[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function persistJobs(uploads: UploadEntry[]) {
  try {
    // Keep all non-uploading entries that have a jobId.
    // This includes error/failed so the user can retry after a page reload.
    // Pure 'uploading' entries without a jobId cannot be resumed and are excluded.
    const toSave = uploads
      .filter(u => u.jobId && u.stage !== 'uploading')
      .map(u => ({
        id: u.id, name: u.name, pct: u.pct, uploadPct: 0,
        stage: u.stage, label: u.label,
        docId: u.docId, jobId: u.jobId,
        nodes: u.nodes, edges: u.edges,
      }));
    localStorage.setItem(LS_KEY, JSON.stringify(toSave));
  } catch {}
}

function formatBytes(b: number): string {
  if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(1)} GB`;
  if (b >= 1024 ** 2) return `${(b / 1024 ** 2).toFixed(1)} MB`;
  if (b >= 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${b} B`;
}

function formatEta(s: number): string {
  if (s < 60) return `${Math.ceil(s)}s`;
  return `${Math.floor(s / 60)}m ${Math.ceil(s % 60)}s`;
}

// Vision Cost Protection types
interface VisionEstimate {
  total_images: number;
  vision_eligible: number;
  vision_skipped_local: number;
  estimated_cost_usd: number;
  saved_by_filter_usd: number;
  over_limit: boolean;
  limit: number;
  status: string;
  model: string;
}

// ── Chunked upload hook (replaces useXhrUpload) ────────────────────────────────

const CHUNK_THRESHOLD_MB = 10; // files >= this use chunked protocol

function useChunkedUpload(onDone?: () => void, onDocUploaded?: (docId: string) => void) {
  // Restore persisted jobs on mount
  const [uploads, setUploads] = useState<UploadEntry[]>(loadPersistedJobs);
  const pollRefs = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const pauseFlags = useRef<Record<string, boolean>>({});   // id → paused?
  const abortFlags = useRef<Record<string, boolean>>({});   // id → cancelled?

  const setEntry = useCallback((id: string, patch: Partial<UploadEntry>) => {
    setUploads(prev => {
      const next = prev.map(u => u.id === id ? { ...u, ...patch } : u);
      persistJobs(next);
      return next;
    });
  }, []);

  // Re-attach polling for persisted jobs on mount
  useEffect(() => {
    const persisted = loadPersistedJobs();
    for (const entry of persisted) {
      if (entry.jobId && !['completed', 'error'].includes(entry.stage)) {
        startJobPolling(entry.id, entry.jobId, entry.docId);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startJobPolling = useCallback((id: string, jobId: string, docId?: string) => {
    // Adaptive polling interval: start fast, slow down for long-running jobs.
    // No hard timeout — large files can take 30+ minutes on slow connections.
    // Polling stops only when the backend reports a terminal state.
    let consecutiveErrors = 0;
    let pollCount = 0;

    const nextInterval = () => {
      if (pollCount < 10)  return 2000;   // first 20s: poll every 2s
      if (pollCount < 30)  return 5000;   // next 100s: every 5s
      return 10_000;                       // thereafter: every 10s
    };

    const poll = async () => {
      pollCount++;
      try {
        const resp = await fetch(`${API}/api/rag/jobs/${jobId}/status`, { credentials: 'include' });
        if (!resp.ok) {
          // 404 means job disappeared; 401/403 means session expired
          if ([404, 401, 403].includes(resp.status)) {
            setEntry(id, { stage: 'error', label: resp.status === 404 ? 'Job not found — may have been cleaned up' : 'Session expired — please sign in again', pct: 0 });
            return;
          }
          throw new Error(`HTTP ${resp.status}`);
        }
        const data = await resp.json();
        consecutiveErrors = 0; // reset on success

        const stage: UploadStage = data.stage ?? 'extracting';
        const label: string      = data.label  ?? 'Processing…';
        const pct: number        = data.pct    ?? 30;

        const patch: Partial<UploadEntry> = { stage, label, pct, nodes: data.nodes, edges: data.edges };

        if (data.current_batch > 0 && data.total_batches > 0 && !['completed', 'error'].includes(stage)) {
          patch.label = data.label || `Processing batch ${data.current_batch} of ${data.total_batches}`;
        }

        if (data.status === 'awaiting_cost_approval') {
          patch.costData = { estimated_cost_usd: data.estimated_cost_usd, limit_usd: data.limit_usd };
        } else {
          patch.costData = undefined;
        }

        setEntry(id, patch);

        // Terminal states — stop polling
        if (stage === 'completed') {
          if (docId) onDocUploaded?.(docId);
          onDone?.();
          return;
        }
        if (stage === 'error') return; // backend failed; keep in list so user can retry
      } catch {
        consecutiveErrors++;
        // After 5 consecutive network errors, show a warning but keep polling
        if (consecutiveErrors === 5) {
          setEntry(id, { label: 'Connection issues — still retrying…' });
        }
        // Cap interval at 30s during network trouble
        pollRefs.current[id] = setTimeout(poll, Math.min(30_000, nextInterval() * consecutiveErrors));
        return;
      }
      pollRefs.current[id] = setTimeout(poll, nextInterval());
    };

    pollRefs.current[id] = setTimeout(poll, 1500);
  }, [setEntry, onDone, onDocUploaded]);

  // Legacy small-file path (XHR single request)
  const uploadSmall = useCallback((id: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.withCredentials = true;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const bytePct = Math.round((e.loaded / e.total) * 100);
        setEntry(id, {
          uploadedBytes: e.loaded, totalBytes: e.total,
          uploadPct: bytePct,
          pct: Math.round(bytePct * 0.25),
          label: bytePct < 100 ? `Uploading… ${bytePct}%` : 'Uploaded — extracting…',
        });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        let docId: string | undefined;
        try { docId = JSON.parse(xhr.responseText)?.id; } catch {}
        if (docId) {
          setEntry(id, { docId, stage: 'extracting', label: 'Extracting text…', pct: 26 });
          // Poll the old pipeline-status endpoint for small files
          let attempts = 0;
          const poll = async () => {
            attempts++;
            if (attempts > 120) { setEntry(id, { stage: 'error', label: 'Timed out', pct: 0 }); return; }
            try {
              const resp = await fetch(`${API}/api/rag/documents/${docId}/pipeline-status`, { credentials: 'include' });
              if (!resp.ok) throw new Error(`${resp.status}`);
              const data = await resp.json();
              const stage: UploadStage = data.stage ?? 'extracting';
              setEntry(id, { stage, label: data.label ?? 'Processing…', pct: data.pct ?? 30, nodes: data.nodes, edges: data.edges });
              if (stage === 'completed') { onDocUploaded?.(docId!); onDone?.(); return; }
              if (stage === 'error') return;
            } catch {}
            pollRefs.current[id] = setTimeout(poll, 2000);
          };
          pollRefs.current[id] = setTimeout(poll, 1500);
        } else {
          setEntry(id, { stage: 'error', label: 'No document ID returned', pct: 0 });
        }
      } else {
        const msg = (() => { try { return JSON.parse(xhr.responseText)?.detail || xhr.statusText; } catch { return xhr.statusText || 'Upload failed'; } })();
        setEntry(id, { stage: 'error', label: msg, pct: 0 });
      }
    };
    xhr.onerror = () => setEntry(id, { stage: 'error', label: 'Network error', pct: 0 });
    xhr.ontimeout = () => setEntry(id, { stage: 'error', label: 'Upload timed out', pct: 0 });
    xhr.open('POST', `${API}/api/rag/documents/upload`);
    xhr.send(fd);
  }, [setEntry, onDone, onDocUploaded]);

  // Chunked upload path for large files
  const uploadChunked = useCallback(async (id: string, file: File) => {
    const CHUNK_SIZE = CHUNK_THRESHOLD_MB * 1024 * 1024;
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    setEntry(id, { totalBytes: file.size, totalChunks, currentChunk: 0, retryCount: 0 });

    // 1. Start session
    let sessionId: string;
    try {
      const res = await fetch(`${API}/api/rag/upload/start`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, total_size: file.size, document_type: 'other' }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setEntry(id, { stage: 'error', label: err.detail || 'Failed to start upload', pct: 0 });
        return;
      }
      const data = await res.json();
      sessionId = data.session_id;
    } catch (e: any) {
      setEntry(id, { stage: 'error', label: `Network error: ${e.message}`, pct: 0 });
      return;
    }

    // 2. Upload chunks
    let uploadedBytes = 0;
    let lastTime = Date.now();
    let lastBytes = 0;

    for (let chunkIdx = 0; chunkIdx < totalChunks; chunkIdx++) {
      if (abortFlags.current[id]) {
        setEntry(id, { stage: 'error', label: 'Upload cancelled', pct: 0 });
        return;
      }

      // Pause: wait until unpaused
      while (pauseFlags.current[id]) {
        setEntry(id, { isPaused: true, label: `Paused at chunk ${chunkIdx + 1}/${totalChunks}` });
        await new Promise(r => setTimeout(r, 500));
        if (abortFlags.current[id]) { setEntry(id, { stage: 'error', label: 'Upload cancelled', pct: 0 }); return; }
      }
      setEntry(id, { isPaused: false });

      const start = chunkIdx * CHUNK_SIZE;
      const chunk = file.slice(start, start + CHUNK_SIZE);

      let retries = 0;
      const MAX_RETRIES = 3;
      let success = false;

      while (retries <= MAX_RETRIES && !success) {
        if (retries > 0) {
          setEntry(id, { retryCount: retries, label: `Retrying chunk ${chunkIdx + 1}… (attempt ${retries + 1})` });
          await new Promise(r => setTimeout(r, 1500 * retries));
        }
        try {
          const res = await fetch(`${API}/api/rag/upload/${sessionId}/chunk/${chunkIdx}`, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: chunk,
          });
          if (res.ok) {
            success = true;
          } else {
            retries++;
          }
        } catch {
          retries++;
        }
      }

      if (!success) {
        setEntry(id, { stage: 'error', label: `Chunk ${chunkIdx + 1} failed after ${MAX_RETRIES} retries`, pct: 0 });
        return;
      }

      uploadedBytes += chunk.size;
      const now = Date.now();
      const elapsed = (now - lastTime) / 1000;
      const bytesDelta = uploadedBytes - lastBytes;
      const speedBps = elapsed > 0 ? bytesDelta / elapsed : 0;
      const etaSeconds = speedBps > 0 ? (file.size - uploadedBytes) / speedBps : 0;
      lastTime = now;
      lastBytes = uploadedBytes;

      const uploadPct = Math.round((uploadedBytes / file.size) * 100);
      setEntry(id, {
        uploadedBytes, uploadPct,
        currentChunk: chunkIdx + 1, totalChunks,
        speedBps, etaSeconds,
        pct: Math.round(uploadPct * 0.4),   // 0-40% of overall bar
        label: `Uploading… ${uploadPct}% · ${formatBytes(uploadedBytes)} / ${formatBytes(file.size)}`,
      });
    }

    // 3. Assemble
    setEntry(id, { stage: 'extracting', label: 'Assembling file on server…', pct: 42 });
    try {
      const res = await fetch(`${API}/api/rag/upload/${sessionId}/complete`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setEntry(id, { stage: 'error', label: err.detail || 'Assembly failed', pct: 0 });
        return;
      }
      const data = await res.json();

      if (data.duplicate) {
        setEntry(id, { stage: 'completed', label: `Already in knowledge base (${data.existing_filename})`, pct: 100 });
        onDone?.();
        return;
      }

      const docId: string = data.doc_id;
      const jobId: string = data.job_id;

      setEntry(id, { docId, jobId, stage: 'extracting', label: 'Queued for processing…', pct: 45 });
      startJobPolling(id, jobId, docId);
    } catch (e: any) {
      setEntry(id, { stage: 'error', label: `Assembly failed: ${e.message}`, pct: 0 });
    }
  }, [setEntry, startJobPolling, onDone]);

  const upload = useCallback(async (file: File) => {
    const id = Math.random().toString(36).slice(2);
    const isLarge = file.size >= CHUNK_THRESHOLD_MB * 1024 * 1024;

    setUploads(prev => [...prev, {
      id, name: file.name,
      pct: 0, uploadPct: 0,
      stage: 'uploading', label: 'Uploading…',
    }]);

    if (isLarge) {
      uploadChunked(id, file);
    } else {
      uploadSmall(id, file);
    }
  }, [uploadSmall, uploadChunked]);

  const pause = useCallback((id: string) => {
    pauseFlags.current[id] = true;
    // Also pause server-side job
    const entry = uploads.find(u => u.id === id);
    if (entry?.jobId) {
      fetch(`${API}/api/rag/jobs/${entry.jobId}/pause`, { method: 'POST', credentials: 'include' }).catch(() => {});
    }
    setEntry(id, { isPaused: true, label: 'Paused' });
  }, [uploads, setEntry]);

  const resume = useCallback((id: string) => {
    pauseFlags.current[id] = false;
    const entry = uploads.find(u => u.id === id);
    if (entry?.jobId) {
      fetch(`${API}/api/rag/jobs/${entry.jobId}/resume`, { method: 'POST', credentials: 'include' }).catch(() => {});
    }
    setEntry(id, { isPaused: false, label: 'Resuming…' });
  }, [uploads, setEntry]);

  const cancel = useCallback((id: string) => {
    abortFlags.current[id] = true;
    pauseFlags.current[id] = false;
    if (pollRefs.current[id]) { clearTimeout(pollRefs.current[id]); delete pollRefs.current[id]; }
    const entry = uploads.find(u => u.id === id);
    if (entry?.jobId) {
      fetch(`${API}/api/rag/jobs/${entry.jobId}/cancel`, { method: 'POST', credentials: 'include' }).catch(() => {});
    }
    setEntry(id, { stage: 'error', label: 'Cancelled' });
  }, [uploads, setEntry]);

  const retry = useCallback((id: string) => {
    const entry = uploads.find(u => u.id === id);
    if (!entry?.jobId) return;
    fetch(`${API}/api/rag/jobs/${entry.jobId}/retry`, { method: 'POST', credentials: 'include' })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(() => {
        setEntry(id, { stage: 'extracting', label: 'Retrying…', pct: 20, error: undefined });
        startJobPolling(id, entry.jobId!, entry.docId);
      })
      .catch(() => setEntry(id, { label: 'Retry failed — try uploading again' }));
  }, [uploads, setEntry, startJobPolling]);

  const approveCost = useCallback((id: string) => {
    const entry = uploads.find(u => u.id === id);
    if (!entry?.jobId) return;
    fetch(`${API}/api/rag/jobs/${entry.jobId}/approve-cost`, { method: 'POST', credentials: 'include' })
      .then(() => setEntry(id, { costData: undefined, label: 'Cost approved — resuming…' }))
      .catch(() => {});
  }, [uploads, setEntry]);

  const dismiss = useCallback((id: string) => {
    if (pollRefs.current[id]) { clearTimeout(pollRefs.current[id]); delete pollRefs.current[id]; }
    setUploads(prev => {
      const next = prev.filter(u => u.id !== id);
      persistJobs(next);
      return next;
    });
  }, []);

  useEffect(() => {
    return () => { Object.values(pollRefs.current).forEach(clearTimeout); };
  }, []);

  return { uploads, upload, dismiss, pause, resume, cancel, retry, approveCost };
}

// ── Upload status list ─────────────────────────────────────────────────────────

const STAGE_COLORS: Record<UploadStage, string> = {
  uploading:   'bg-blue-500',
  extracting:  'bg-sky-500',
  studying:    'bg-violet-500',
  generating:  'bg-purple-500 animate-pulse',
  integrating: 'bg-indigo-500 animate-pulse',
  completed:   'bg-green-500',
  error:       'bg-red-500',
};

const STAGE_ICONS: Record<UploadStage, string> = {
  uploading:   '⬆',
  extracting:  '📄',
  studying:    '🔍',
  generating:  '🧠',
  integrating: '🔗',
  completed:   '✓',
  error:       '✕',
};

interface UploadListProps {
  uploads: UploadEntry[];
  dismiss: (id: string) => void;
  pause?: (id: string) => void;
  resume?: (id: string) => void;
  cancel?: (id: string) => void;
  retry?: (id: string) => void;
  approveCost?: (id: string) => void;
}

function UploadList({ uploads, dismiss, pause, resume, cancel, retry, approveCost }: UploadListProps) {
  if (uploads.length === 0) return null;
  return (
    <div className="space-y-2 mt-3">
      {uploads.map(u => (
        <div key={u.id} className="bg-muted/40 rounded-lg px-3 py-2.5 space-y-1.5">
          {/* Row 1: file name + dismiss */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium truncate flex-1">{u.name}</span>
            <div className="flex items-center gap-1 shrink-0">
              {/* Pause / Resume during upload */}
              {u.stage === 'uploading' && !u.isPaused && pause && (
                <button onClick={() => pause(u.id)} title="Pause" className="text-muted-foreground hover:text-foreground">
                  <Pause className="h-3.5 w-3.5" />
                </button>
              )}
              {u.stage === 'uploading' && u.isPaused && resume && (
                <button onClick={() => resume(u.id)} title="Resume" className="text-muted-foreground hover:text-foreground">
                  <Play className="h-3.5 w-3.5" />
                </button>
              )}
              {/* Cancel during active upload/processing */}
              {!['completed', 'error'].includes(u.stage) && cancel && (
                <button onClick={() => cancel(u.id)} title="Cancel" className="text-muted-foreground hover:text-red-400">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
              {/* Dismiss completed/errored */}
              {(u.stage === 'completed' || u.stage === 'error') && (
                <button onClick={() => dismiss(u.id)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Row 2: stage label + speed/ETA */}
          <div className="flex items-center justify-between gap-2">
            <span className={`text-[10px] font-medium ${
              u.stage === 'error' ? 'text-red-400' :
              u.stage === 'completed' ? 'text-green-500' :
              u.isPaused ? 'text-amber-400' : 'text-muted-foreground'
            }`}>
              {STAGE_ICONS[u.stage]} {u.label}
            </span>
            {u.stage === 'uploading' && u.speedBps && u.speedBps > 0 && (
              <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                {formatBytes(u.speedBps)}/s · {u.etaSeconds ? formatEta(u.etaSeconds) : '…'} left
              </span>
            )}
            {u.stage === 'uploading' && u.currentChunk && u.totalChunks && (
              <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                chunk {u.currentChunk}/{u.totalChunks}
              </span>
            )}
          </div>

          {/* Row 3: progress bar */}
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${STAGE_COLORS[u.stage]}`}
              style={{ width: `${u.pct}%` }}
            />
          </div>

          {/* Row 4: stage dots */}
          <div className="flex gap-1">
            {STAGE_ORDER.map(s => {
              const idx   = STAGE_ORDER.indexOf(s);
              const cur   = STAGE_ORDER.indexOf(u.stage);
              const done  = idx < cur || u.stage === 'completed';
              const active = s === u.stage && u.stage !== 'completed';
              return (
                <div key={s} title={s} className={`h-1 flex-1 rounded-full transition-all duration-300 ${
                  u.stage === 'error' ? 'bg-muted' :
                  done   ? 'bg-green-400' :
                  active ? 'bg-blue-400' : 'bg-muted'
                }`} />
              );
            })}
          </div>

          {/* Bytes progress for chunked upload */}
          {u.stage === 'uploading' && u.uploadedBytes != null && u.totalBytes != null && (
            <p className="text-[10px] text-muted-foreground">
              {formatBytes(u.uploadedBytes)} / {formatBytes(u.totalBytes)}
              {u.retryCount ? ` · ${u.retryCount} chunk retry` : ''}
            </p>
          )}

          {/* Completion summary */}
          {u.stage === 'completed' && u.nodes != null && (
            <p className="text-[10px] text-green-600">
              {u.nodes} knowledge nodes · {u.edges ?? 0} connections added
            </p>
          )}

          {/* Error with retry */}
          {u.stage === 'error' && u.label !== 'Cancelled' && u.jobId && retry && (
            <button
              onClick={() => retry(u.id)}
              className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300"
            >
              <RotateCcw className="h-3 w-3" /> Retry processing
            </button>
          )}

          {/* Cost approval gate */}
          {u.costData && approveCost && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 mt-1 space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs text-amber-300">
                <DollarSign className="h-3.5 w-3.5 shrink-0" />
                <span className="font-medium">Cost confirmation required</span>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Estimated AI analysis cost: <strong className="text-foreground">${u.costData.estimated_cost_usd.toFixed(3)}</strong> — exceeds the ${u.costData.limit_usd.toFixed(2)} limit.
              </p>
              <Button size="sm" className="h-6 text-[10px] bg-amber-600 hover:bg-amber-500" onClick={() => approveCost(u.id)}>
                Approve & Continue
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Dropzone ───────────────────────────────────────────────────────────────────

function Dropzone({ accept, label, onFiles }: { accept: string; label: string; onFiles: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) onFiles(files);
  };

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all select-none ${
        dragging
          ? 'border-blue-500 bg-blue-500/10'
          : 'border-border hover:border-blue-500/50 hover:bg-muted/30'
      }`}
    >
      <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
      <p className="text-sm font-medium">{label}</p>
      <p className="text-xs text-muted-foreground mt-1">Drag & drop or click to browse</p>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        onChange={e => {
          const files = Array.from(e.target.files || []);
          if (files.length) { onFiles(files); e.target.value = ''; }
        }}
      />
    </div>
  );
}

// ── Vision Confirm Dialog ──────────────────────────────────────────────────────

function VisionConfirmDialog({
  estimate,
  onConfirm,
  onSkip,
  loading,
}: {
  estimate: VisionEstimate;
  onConfirm: (override?: boolean) => void;
  onSkip: () => void;
  loading: boolean;
}) {
  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
      <div className="flex items-start gap-3">
        <Eye className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-amber-300">Vision Captioning Ready</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {estimate.vision_eligible} of {estimate.total_images} images selected for AI captioning
            {estimate.vision_skipped_local > 0 && ` · ${estimate.vision_skipped_local} filtered out locally`}.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-muted/40 rounded-lg px-3 py-2">
          <p className="text-muted-foreground">Estimated cost</p>
          <p className="font-semibold text-foreground">${estimate.estimated_cost_usd.toFixed(4)}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">{estimate.model}</p>
        </div>
        <div className="bg-green-500/10 rounded-lg px-3 py-2">
          <p className="text-muted-foreground">Saved by filter</p>
          <p className="font-semibold text-green-400">−${estimate.saved_by_filter_usd.toFixed(4)}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">{estimate.vision_skipped_local} skipped</p>
        </div>
      </div>

      {estimate.over_limit && (
        <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/10 rounded-lg px-3 py-1.5">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>Exceeds {estimate.limit}-image safety limit. Default continues with first {estimate.limit}.</span>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <Button size="sm" variant="outline" className="text-xs h-7" onClick={onSkip} disabled={loading}>
          Skip
        </Button>
        <Button size="sm" className="text-xs h-7" onClick={() => onConfirm(false)} disabled={loading}>
          {loading ? 'Starting…' : `Continue (${Math.min(estimate.vision_eligible, estimate.limit)} images)`}
        </Button>
        {estimate.over_limit && (
          <Button
            size="sm" variant="outline"
            className="text-xs h-7 border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
            onClick={() => onConfirm(true)}
            disabled={loading}
          >
            Process all {estimate.vision_eligible}
          </Button>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TEACH AI — 7 Method Panels
// ══════════════════════════════════════════════════════════════════════════════

// ── 1. Upload Documents ────────────────────────────────────────────────────────

const DOCUMENT_TYPES = ['.pdf', '.docx', '.pptx', '.xlsx', '.txt', '.zip'];
const DOCUMENT_TYPE_COLORS: Record<string, string> = {
  '.pdf': 'text-red-400 border-red-400/30 bg-red-500/10',
  '.docx': 'text-blue-400 border-blue-400/30 bg-blue-500/10',
  '.pptx': 'text-orange-400 border-orange-400/30 bg-orange-500/10',
  '.xlsx': 'text-green-400 border-green-400/30 bg-green-500/10',
  '.txt': 'text-slate-400 border-slate-400/30 bg-slate-500/10',
  '.zip': 'text-purple-400 border-purple-400/30 bg-purple-500/10',
};

// ── Folder upload — recursive scan, client-side filtering + intra-folder dedup ──
// Kept in sync manually with backend/api/routes/knowledge_library.py's allowlist.
const FOLDER_SUPPORTED_EXT = new Set(['pdf', 'docx', 'pptx', 'xlsx', 'txt', 'csv', 'md', 'html', 'xml']);
const FOLDER_IMAGE_EXT = new Set(['png', 'jpg', 'jpeg']);
const FOLDER_HIDDEN_NAMES = new Set(['thumbs.db', 'desktop.ini', '.ds_store']);

function isHiddenSegment(name: string): boolean {
  // `~$…` files are Microsoft Office owner/lock files created while a document
  // is open. They carry an Office extension (.pptx/.docx/.xlsx) but are tiny
  // binary stubs, not real OOXML packages, so the server's magic-byte check
  // rejects them. Skip them like any other junk file.
  return name.startsWith('.') || name.startsWith('~$') || FOLDER_HIDDEN_NAMES.has(name.toLowerCase());
}

async function sha256Hex(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}

interface FolderScanSummary {
  toUpload: File[];
  skippedHidden: number;
  skippedUnsupported: number;
  skippedImages: number;
  skippedDuplicate: number;
}

// SHA-256 every candidate file so duplicate copies within the same folder pick
// are caught before upload — the server only registers a hash once a study job
// finishes, so two identical files uploaded back-to-back would otherwise both
// get queued.
async function scanFolderFiles(fileList: FileList): Promise<FolderScanSummary> {
  const summary: FolderScanSummary = { toUpload: [], skippedHidden: 0, skippedUnsupported: 0, skippedImages: 0, skippedDuplicate: 0 };
  const seenHashes = new Set<string>();

  for (const file of Array.from(fileList)) {
    const relPath: string = (file as any).webkitRelativePath || file.name;
    const segments = relPath.split('/');
    const baseName = segments[segments.length - 1] || relPath;

    if (segments.some(isHiddenSegment)) { summary.skippedHidden++; continue; }

    const ext = baseName.includes('.') ? baseName.split('.').pop()!.toLowerCase() : '';
    if (FOLDER_IMAGE_EXT.has(ext)) { summary.skippedImages++; continue; }
    if (!FOLDER_SUPPORTED_EXT.has(ext)) { summary.skippedUnsupported++; continue; }

    let hash: string | null = null;
    try { hash = await sha256Hex(file); } catch { /* unreadable — let the server report it */ }

    if (hash) {
      if (seenHashes.has(hash)) { summary.skippedDuplicate++; continue; }
      seenHashes.add(hash);
    }
    summary.toUpload.push(new File([file], relPath, { type: file.type }));
  }
  return summary;
}

interface FolderUploadStats {
  discovered: number;
  queued: number;
  skippedHidden: number;
  skippedUnsupported: number;
  skippedImages: number;
  skippedDuplicate: number;
}

function GenericUploadPanel({
  onLearnDone,
  dropLabel,
  successHint,
  allowFolder = false,
}: {
  onLearnDone: () => void;
  dropLabel: string;
  successHint: React.ReactNode;
  allowFolder?: boolean;
}) {
  const qc = useQueryClient();
  const [pendingVision, setPendingVision] = useState<{ docId: string; estimate: VisionEstimate } | null>(null);
  const [startingVision, setStartingVision] = useState(false);
  const [folderScanning, setFolderScanning] = useState(false);
  const [folderStats, setFolderStats] = useState<FolderUploadStats | null>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  const {
    uploads, upload, dismiss,
    pause, resume, cancel, retry, approveCost,
  } = useChunkedUpload(
    () => {
      qc.invalidateQueries({ queryKey: ['study-jobs'] });
      qc.invalidateQueries({ queryKey: ['learning-stats'] });
      onLearnDone();
    },
    async (docId) => {
      try {
        const est: VisionEstimate = await apiFetch(`/api/vision/estimate/${docId}`);
        if (est?.vision_eligible > 0) setPendingVision({ docId, estimate: est });
      } catch { /* non-critical */ }
    },
  );

  const handleVisionConfirm = async (override = false) => {
    if (!pendingVision) return;
    setStartingVision(true);
    try {
      await apiFetch(`/api/vision/start/${pendingVision.docId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override }),
      });
      toast({
        title: 'Vision captioning started',
        description: `Processing ${Math.min(pendingVision.estimate.vision_eligible, override ? Infinity : pendingVision.estimate.limit)} images`,
      });
      qc.invalidateQueries({ queryKey: ['vision-stats'] });
    } catch {
      toast({ title: 'Error', description: 'Failed to start vision processing', variant: 'destructive' });
    } finally {
      setStartingVision(false);
      setPendingVision(null);
    }
  };

  const handleVisionSkip = async () => {
    if (!pendingVision) return;
    try {
      await apiFetch(`/api/vision/skip/${pendingVision.docId}`, { method: 'POST' });
    } catch { /* best-effort */ }
    setPendingVision(null);
  };

  const handleFolderFiles = async (fileList: FileList) => {
    setFolderScanning(true);
    setFolderStats(null);
    try {
      const scan = await scanFolderFiles(fileList);
      setFolderStats({
        discovered: fileList.length,
        queued: scan.toUpload.length,
        skippedHidden: scan.skippedHidden,
        skippedUnsupported: scan.skippedUnsupported,
        skippedImages: scan.skippedImages,
        skippedDuplicate: scan.skippedDuplicate,
      });
      // Bounded concurrency — a folder of hundreds of files shouldn't fire
      // hundreds of simultaneous study jobs (and chunked-upload sessions) at once.
      const CONCURRENCY = 3;
      let idx = 0;
      const worker = async () => {
        while (idx < scan.toUpload.length) {
          const file = scan.toUpload[idx++];
          await upload(file);
        }
      };
      await Promise.all(Array.from({ length: Math.min(CONCURRENCY, scan.toUpload.length) }, worker));
    } finally {
      setFolderScanning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        {DOCUMENT_TYPES.map(t => (
          <span key={t} className={`px-2 py-0.5 rounded-md border text-[11px] font-mono font-medium ${DOCUMENT_TYPE_COLORS[t]}`}>
            {t}
          </span>
        ))}
      </div>
      <Dropzone
        accept=".pdf,.docx,.pptx,.xlsx,.txt,.zip"
        label={dropLabel}
        onFiles={files => files.forEach(f => upload(f))}
      />
      {allowFolder && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => folderInputRef.current?.click()}
            disabled={folderScanning}
            className="w-full flex items-center justify-center gap-2 rounded-lg border border-dashed border-border hover:border-blue-500/50 hover:bg-muted/30 transition-all py-3 text-sm font-medium disabled:opacity-60"
          >
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
            {folderScanning ? 'Scanning folder…' : 'Upload Folder (recursive)'}
            <input
              ref={folderInputRef}
              type="file"
              multiple
              className="hidden"
              {...({ webkitdirectory: '', directory: '' } as any)}
              onChange={e => {
                const files = e.target.files;
                if (files && files.length) handleFolderFiles(files);
                e.target.value = '';
              }}
            />
          </button>
          {folderStats && (
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground bg-muted/30 rounded-lg px-3 py-2">
              <span className="text-foreground font-medium">{folderStats.discovered} files found</span>
              <span className="text-green-400">{folderStats.queued} queued for learning</span>
              {folderStats.skippedDuplicate > 0 && <span>{folderStats.skippedDuplicate} duplicate copies skipped</span>}
              {folderStats.skippedUnsupported > 0 && <span>{folderStats.skippedUnsupported} unsupported type skipped</span>}
              {folderStats.skippedImages > 0 && <span>{folderStats.skippedImages} images found (OCR support coming soon)</span>}
              {folderStats.skippedHidden > 0 && <span>{folderStats.skippedHidden} hidden/system files skipped</span>}
            </div>
          )}
        </div>
      )}
      <UploadList
        uploads={uploads}
        dismiss={dismiss}
        pause={pause}
        resume={resume}
        cancel={cancel}
        retry={retry}
        approveCost={approveCost}
      />
      {pendingVision && (
        <VisionConfirmDialog
          estimate={pendingVision.estimate}
          onConfirm={handleVisionConfirm}
          onSkip={handleVisionSkip}
          loading={startingVision}
        />
      )}
      {!pendingVision && uploads.some(u => u.stage === 'completed') && (
        <div className="flex items-center gap-2 text-xs text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">
          <CheckCheck className="h-3.5 w-3.5 shrink-0" />
          <span>{successHint}</span>
        </div>
      )}
    </div>
  );
}

// ── Collapsible subsection shell (Upload / Knowledge Library / Watched / Cloud) ─

function CollapsibleSubsection({
  icon: Icon, title, badge, defaultOpen = false, children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  badge?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border rounded-lg overflow-hidden bg-card">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-muted/30 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {title}
          {badge && (
            <span className="text-[9px] font-bold uppercase tracking-wide text-muted-foreground bg-muted rounded-full px-1.5 py-0.5">
              {badge}
            </span>
          )}
        </span>
        {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>
      {open && <div className="px-3 pb-3 border-t border-border pt-3">{children}</div>}
    </div>
  );
}

// ── Knowledge Library — persistent, re-scannable local folders ─────────────────

interface LibraryScanSummary {
  discovered: number;
  queued: number;
  skipped_duplicate: number;
  skipped_unsupported: number;
  errors: string[];
}

interface LibraryFolder {
  id: string;
  path: string;
  label: string;
  enabled: boolean;
  scan_status: 'idle' | 'scanning' | 'completed' | 'error';
  last_scanned_at: string | null;
  last_scan_summary: LibraryScanSummary | null;
  created_at: string;
}

function useLibraryFolders() {
  return useQuery<LibraryFolder[]>({
    queryKey: ['library-folders'],
    queryFn: () => apiFetch('/api/library/folders'),
    refetchInterval: (query) => {
      const data = query.state.data as LibraryFolder[] | undefined;
      return data?.some(f => f.scan_status === 'scanning') ? 2000 : 20_000;
    },
  });
}

function KnowledgeLibrarySection() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: folders } = useLibraryFolders();
  const [newPath, setNewPath] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [registering, setRegistering] = useState(false);

  const refresh = () => qc.invalidateQueries({ queryKey: ['library-folders'] });

  const registerFolder = async () => {
    const path = newPath.trim();
    if (!path) return;
    setRegistering(true);
    try {
      await apiFetch('/api/library/folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, label: newLabel.trim() }),
      });
      setNewPath('');
      setNewLabel('');
      refresh();
      toast({ title: 'Folder registered', description: path });
    } catch (e: any) {
      toast({ title: 'Could not register folder', description: e.message || String(e), variant: 'destructive' });
    } finally {
      setRegistering(false);
    }
  };

  const scanFolder = async (id: string) => {
    try {
      await apiFetch(`/api/library/folders/${id}/scan`, { method: 'POST' });
      refresh();
    } catch (e: any) {
      toast({ title: 'Scan failed to start', description: e.message || String(e), variant: 'destructive' });
    }
  };

  const removeFolder = async (id: string) => {
    try {
      await apiFetch(`/api/library/folders/${id}`, { method: 'DELETE' });
      refresh();
    } catch (e: any) {
      toast({ title: 'Could not remove folder', description: e.message || String(e), variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Register a folder on this machine once, then re-scan it any time instead of re-selecting files. Already-learned files are skipped automatically.
      </p>
      <div className="flex flex-col sm:flex-row gap-2">
        <Input
          placeholder={'e.g. D:\\Training Manuals'}
          value={newPath}
          onChange={e => setNewPath(e.target.value)}
          className="text-xs h-8"
        />
        <Input
          placeholder="Label (optional)"
          value={newLabel}
          onChange={e => setNewLabel(e.target.value)}
          className="text-xs h-8 sm:max-w-[180px]"
        />
        <Button size="sm" className="h-8 shrink-0" onClick={registerFolder} disabled={registering || !newPath.trim()}>
          Register
        </Button>
      </div>

      {(folders ?? []).length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No folders registered yet.</p>
      ) : (
        <div className="space-y-2">
          {folders!.map(f => (
            <div key={f.id} className="border border-border rounded-lg px-3 py-2 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{f.label || f.path}</p>
                  <p className="text-[11px] text-muted-foreground truncate">{f.path}</p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button
                    size="sm" variant="outline" className="h-7 text-xs"
                    disabled={f.scan_status === 'scanning'}
                    onClick={() => scanFolder(f.id)}
                  >
                    {f.scan_status === 'scanning'
                      ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" />Scanning…</>
                      : <><RefreshCw className="h-3 w-3 mr-1" />Scan Now</>}
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => removeFolder(f.id)}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              {f.last_scan_summary && (
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
                  <span>{f.last_scan_summary.discovered} found</span>
                  <span className="text-green-400">{f.last_scan_summary.queued} queued</span>
                  {f.last_scan_summary.skipped_duplicate > 0 && <span>{f.last_scan_summary.skipped_duplicate} already learned</span>}
                  {f.last_scan_summary.skipped_unsupported > 0 && <span>{f.last_scan_summary.skipped_unsupported} unsupported</span>}
                  {f.last_scan_summary.errors.length > 0 && <span className="text-red-400">{f.last_scan_summary.errors.length} errors</span>}
                  {f.last_scanned_at && <span>· last scan {new Date(f.last_scanned_at).toLocaleString()}</span>}
                </div>
              )}
              {f.scan_status === 'error' && (
                <p className="text-[11px] text-red-400">Scan failed — check server logs and try again.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DocumentUploadPanel({ onLearnDone }: { onLearnDone: () => void }) {
  return (
    <div className="space-y-3">
      <CollapsibleSubsection icon={FolderOpen} title="Upload Folder / Files" defaultOpen>
        <GenericUploadPanel
          onLearnDone={onLearnDone}
          dropLabel="Drop documents to teach the AI"
          successHint={<>Uploaded &amp; indexed — AI is analysing. Results appear in the <strong>Integrated</strong> tab once complete</>}
          allowFolder
        />
      </CollapsibleSubsection>
      <CollapsibleSubsection icon={BookMarked} title="Knowledge Library">
        <KnowledgeLibrarySection />
      </CollapsibleSubsection>
      <CollapsibleSubsection icon={Eye} title="Watched Folders" badge="Coming soon">
        <p className="text-xs text-muted-foreground">
          Automatic background watching for registered folders is planned for a future release. For now, use <strong>Scan Now</strong> in Knowledge Library to re-check a folder on demand.
        </p>
      </CollapsibleSubsection>
      <CollapsibleSubsection icon={Globe} title="Cloud Sources" badge="Coming soon">
        <p className="text-xs text-muted-foreground">
          Google Drive, OneDrive, SharePoint, and other cloud connectors are planned for a future release.
        </p>
      </CollapsibleSubsection>
    </div>
  );
}

// ── 2. Web Knowledge Sources ───────────────────────────────────────────────────

type WebsiteStatus = 'idle' | 'crawling' | 'done' | 'error';

type KnowledgeSource =
  | 'entire_website'
  | 'documentation'
  | 'technical_manuals'
  | 'standards'
  | 'pdfs_only'
  | 'sitemap'
  | 'selected_urls';

const WEB_SOURCE_TYPES = [
  {
    id: 'entire_website' as KnowledgeSource,
    shortLabel: 'Website',
    icon: Globe,
    desc: 'Crawl all accessible pages on this domain',
    color: 'text-cyan-400',
    borderActive: 'border-cyan-500/60 bg-cyan-500/10',
    urlLabel: 'Website URL',
    placeholder: 'https://example.com',
    buttonLabel: 'Crawl & Learn',
  },
  {
    id: 'documentation' as KnowledgeSource,
    shortLabel: 'Docs',
    icon: BookOpen,
    desc: 'Focus on /docs, /guide, /wiki, /help paths',
    color: 'text-blue-400',
    borderActive: 'border-blue-500/60 bg-blue-500/10',
    urlLabel: 'Documentation URL',
    placeholder: 'https://example.com/docs',
    buttonLabel: 'Crawl Docs',
  },
  {
    id: 'technical_manuals' as KnowledgeSource,
    shortLabel: 'Manuals',
    icon: Wrench,
    desc: 'Focus on /manual, /spec, /datasheet paths',
    color: 'text-purple-400',
    borderActive: 'border-purple-500/60 bg-purple-500/10',
    urlLabel: 'Manual / Tech URL',
    placeholder: 'https://example.com/technical',
    buttonLabel: 'Crawl Manuals',
  },
  {
    id: 'standards' as KnowledgeSource,
    shortLabel: 'Standards',
    icon: Shield,
    desc: 'Focus on /standard, /safety, /compliance paths',
    color: 'text-green-400',
    borderActive: 'border-green-500/60 bg-green-500/10',
    urlLabel: 'Standards / Safety URL',
    placeholder: 'https://iaea.org/resources/safety-standards',
    buttonLabel: 'Crawl Standards',
  },
  {
    id: 'pdfs_only' as KnowledgeSource,
    shortLabel: 'PDFs',
    icon: FileText,
    desc: 'Scan site for PDF links and extract them',
    color: 'text-red-400',
    borderActive: 'border-red-500/60 bg-red-500/10',
    urlLabel: 'Website to scan for PDFs',
    placeholder: 'https://example.com/resources',
    buttonLabel: 'Scan for PDFs',
  },
  {
    id: 'sitemap' as KnowledgeSource,
    shortLabel: 'Sitemap',
    icon: Network,
    desc: 'Auto-discover URLs via sitemap.xml',
    color: 'text-amber-400',
    borderActive: 'border-amber-500/60 bg-amber-500/10',
    urlLabel: 'Website URL (sitemap auto-discovered)',
    placeholder: 'https://example.com',
    buttonLabel: 'Import Sitemap',
  },
  {
    id: 'selected_urls' as KnowledgeSource,
    shortLabel: 'URLs',
    icon: Link2,
    desc: 'Crawl only the specific pages you list',
    color: 'text-teal-400',
    borderActive: 'border-teal-500/60 bg-teal-500/10',
    urlLabel: 'URLs — one per line',
    placeholder: 'https://example.com/page-1\nhttps://example.com/page-2\nhttps://example.com/page-3',
    buttonLabel: 'Learn from URLs',
  },
] as const;

const DEFAULT_BLOCKED_PATHS = [
  '/news', '/blog', '/careers', '/jobs', '/privacy',
  '/contact', '/events', '/media', '/store', '/login',
  '/register', '/cart', '/checkout', '/about-us', '/press',
];

function WebSourcePanel({ onLearnDone }: { onLearnDone: () => void }) {
  const [sourceType, setSourceType] = useState<KnowledgeSource>('entire_website');
  const [url, setUrl] = useState('');
  const [urlsText, setUrlsText] = useState('');
  const [status, setStatus] = useState<WebsiteStatus>('idle');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  // Advanced options
  const [maxPages, setMaxPages] = useState(10);
  const [maxDepth, setMaxDepth] = useState(3);
  const [blockedPaths, setBlockedPaths] = useState<string[]>(DEFAULT_BLOCKED_PATHS);
  const [blockedInput, setBlockedInput] = useState('');
  const [minRelevance, setMinRelevance] = useState(0);
  const [fileTypes, setFileTypes] = useState({
    html: true, pdf: true, docx: true, pptx: true, xlsx: false, markdown: true,
  });
  const { toast } = useToast();
  const qc = useQueryClient();

  const src = WEB_SOURCE_TYPES.find(s => s.id === sourceType)!;
  const isMultiUrl = sourceType === 'selected_urls';
  const SrcIcon = src.icon;

  const handleCrawl = async () => {
    const primaryUrl = url.trim();
    const urlsList = isMultiUrl ? urlsText.split('\n').map(u => u.trim()).filter(Boolean) : [];
    if (isMultiUrl ? urlsList.length === 0 : !primaryUrl) return;

    setStatus('crawling');
    setError('');
    setResult(null);

    try {
      const body: Record<string, unknown> = {
        knowledge_source: sourceType,
        max_pages: maxPages,
        max_depth: maxDepth,
        blocked_paths: blockedPaths,
        min_relevance_score: minRelevance,
        include_sitemap: sourceType !== 'selected_urls',
        file_types: Object.entries(fileTypes).filter(([, v]) => v).map(([k]) => k),
      };
      if (isMultiUrl) {
        body.urls = urlsList;
        body.url = urlsList[0] ?? '';
      } else {
        body.url = primaryUrl;
      }

      const data = await apiFetch('/api/learning/teach/website', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setResult(data);
      setStatus('done');
      qc.invalidateQueries({ queryKey: ['study-jobs'] });
      qc.invalidateQueries({ queryKey: ['learning-stats'] });
      onLearnDone();
      toast({ title: 'Content queued for learning', description: data.message });
    } catch (e: any) {
      setError(e.message || 'Failed to crawl');
      setStatus('error');
    }
  };

  const addBlockedPath = (val: string) => {
    const p = val.trim();
    if (p && !blockedPaths.includes(p)) setBlockedPaths(prev => [...prev, p]);
    setBlockedInput('');
  };

  return (
    <div className="space-y-4">

      {/* ── Source type selector ── */}
      <div>
        <label className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider mb-2 block">
          Knowledge Source
        </label>
        <div className="flex flex-wrap gap-1.5">
          {WEB_SOURCE_TYPES.map(s => {
            const SI = s.icon;
            const active = sourceType === s.id;
            return (
              <button
                key={s.id}
                onClick={() => { setSourceType(s.id); setStatus('idle'); setResult(null); setError(''); }}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                  active
                    ? `${s.color} ${s.borderActive}`
                    : 'text-muted-foreground border-border hover:border-muted-foreground/40 hover:text-foreground'
                }`}
              >
                <SI className="h-3 w-3" />
                {s.shortLabel}
              </button>
            );
          })}
        </div>
        <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">{src.desc}</p>
      </div>

      {/* ── URL / URLs input ── */}
      <div className="space-y-1.5">
        <label className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider block">
          {src.urlLabel}
        </label>
        {isMultiUrl ? (
          <Textarea
            placeholder={src.placeholder}
            value={urlsText}
            onChange={e => setUrlsText(e.target.value)}
            className="bg-muted border-border text-xs font-mono resize-y min-h-[80px]"
            disabled={status === 'crawling'}
            rows={4}
          />
        ) : (
          <div className="relative">
            <SrcIcon className={`absolute left-3 top-2.5 h-4 w-4 ${src.color}`} />
            <Input
              placeholder={src.placeholder}
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCrawl()}
              className="pl-9 bg-muted border-border"
              disabled={status === 'crawling'}
            />
          </div>
        )}
      </div>

      {/* ── Advanced options (collapsible) ── */}
      <div className="border border-border rounded-lg overflow-hidden">
        <button
          onClick={() => setShowAdvanced(v => !v)}
          className="w-full flex items-center justify-between px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors"
        >
          <span className="font-medium">Advanced Options</span>
          {showAdvanced ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>

        {showAdvanced && (
          <div className="px-3 pb-3 space-y-3 border-t border-border/50 pt-3">
            {/* Max pages & depth */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium block mb-1">
                  Max Pages <span className="text-muted-foreground/50">(1–50)</span>
                </label>
                <Input
                  type="number" min={1} max={50} value={maxPages}
                  onChange={e => setMaxPages(Math.max(1, Math.min(50, parseInt(e.target.value) || 10)))}
                  className="bg-muted border-border text-xs h-7"
                />
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium block mb-1">
                  Max Depth <span className="text-muted-foreground/50">(1–5)</span>
                </label>
                <Input
                  type="number" min={1} max={5} value={maxDepth}
                  onChange={e => setMaxDepth(Math.max(1, Math.min(5, parseInt(e.target.value) || 3)))}
                  className="bg-muted border-border text-xs h-7"
                />
              </div>
            </div>

            {/* Technical relevance filter */}
            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium block mb-1">
                Technical Relevance Filter
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range" min={0} max={0.6} step={0.1} value={minRelevance}
                  onChange={e => setMinRelevance(parseFloat(e.target.value))}
                  className="flex-1 accent-cyan-500 h-1"
                />
                <span className="text-[11px] text-muted-foreground shrink-0 w-20 text-right">
                  {minRelevance === 0 ? 'All pages' :
                   minRelevance <= 0.2 ? 'Light filter' :
                   minRelevance <= 0.4 ? 'Moderate' : 'High filter'}
                </span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                Skip pages with low technical content (removes ads, careers, cookie pages)
              </p>
            </div>

            {/* File types */}
            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium block mb-1.5">
                File Types
              </label>
              <div className="flex flex-wrap gap-3">
                {Object.entries(fileTypes).map(([type, checked]) => (
                  <label key={type} className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer hover:text-foreground">
                    <input
                      type="checkbox" checked={checked}
                      onChange={e => setFileTypes(prev => ({ ...prev, [type]: e.target.checked }))}
                      className="accent-cyan-500 w-3 h-3 rounded"
                    />
                    {type.toUpperCase()}
                  </label>
                ))}
              </div>
            </div>

            {/* Blocked paths */}
            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium block mb-1.5">
                Blocked Paths
              </label>
              <div className="flex flex-wrap gap-1 mb-1.5 max-h-20 overflow-y-auto">
                {blockedPaths.map(p => (
                  <span key={p} className="flex items-center gap-0.5 text-[10px] bg-muted border border-border rounded px-1.5 py-0.5 text-muted-foreground font-mono">
                    {p}
                    <button onClick={() => setBlockedPaths(prev => prev.filter(x => x !== p))} className="ml-0.5 hover:text-red-400">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex gap-1">
                <Input
                  placeholder="/path-to-block"
                  value={blockedInput}
                  onChange={e => setBlockedInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addBlockedPath(blockedInput); }
                  }}
                  className="bg-muted border-border text-xs h-7 font-mono"
                />
                <Button size="sm" variant="outline" onClick={() => addBlockedPath(blockedInput)} className="h-7 px-2 text-xs shrink-0">
                  Add
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Action button ── */}
      <Button
        onClick={handleCrawl}
        disabled={status === 'crawling' || (isMultiUrl ? !urlsText.trim() : !url.trim())}
        className="w-full bg-cyan-600 hover:bg-cyan-500 text-white"
      >
        {status === 'crawling'
          ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" /> Crawling…</>
          : <><SrcIcon className="h-4 w-4 mr-2" /> {src.buttonLabel}</>
        }
      </Button>

      {/* ── Crawling state ── */}
      {status === 'crawling' && (
        <div className="bg-muted/30 rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-2 text-xs text-cyan-400">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            Crawling {src.shortLabel.toLowerCase()} — scoring technical relevance…
          </div>
          <div className="space-y-1 text-[11px] text-muted-foreground">
            <div className="flex items-center gap-1.5"><CheckCircle2 className="h-3 w-3 text-green-400" /> Connected to server</div>
            {sourceType === 'sitemap' && <div className="flex items-center gap-1.5 text-cyan-400"><RefreshCw className="h-3 w-3 animate-spin" /> Discovering sitemap URLs…</div>}
            <div className="flex items-center gap-1.5 text-cyan-400 animate-pulse"><RefreshCw className="h-3 w-3 animate-spin" /> Fetching & scoring pages…</div>
          </div>
        </div>
      )}

      {/* ── Success result ── */}
      {status === 'done' && result && (
        <div className="space-y-3 bg-green-500/10 border border-green-500/20 rounded-lg p-4">
          <div className="flex items-center gap-2 text-sm text-green-400 font-medium">
            <CheckCircle2 className="h-4 w-4" /> Content extracted successfully
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>Pages indexed: <strong className="text-foreground">{result.pages_indexed ?? 1} / {result.pages_attempted ?? 1}</strong></span>
            <span>Characters: <strong className="text-foreground">{(result.text_length || 0).toLocaleString()}</strong></span>
            {result.sitemap_urls_found > 0 && (
              <span>Sitemap URLs: <strong className="text-foreground">{result.sitemap_urls_found}</strong></span>
            )}
            {result.avg_technical_relevance != null && result.avg_technical_relevance > 0 && (
              <span>Avg relevance: <strong className={result.avg_technical_relevance >= 0.4 ? 'text-green-400' : 'text-amber-400'}>
                {Math.round(result.avg_technical_relevance * 100)}%
              </strong></span>
            )}
            <span>robots.txt: <strong className="text-foreground">{result.robots_txt_honored ? 'honored' : 'skipped'}</strong></span>
            <span>Browser render: <strong className="text-foreground">{result.playwright_available ? 'ready' : 'unavailable'}</strong></span>
          </div>

          {(result.page_diagnostics || []).length > 0 && (
            <div className="space-y-1 border-t border-green-500/10 pt-2">
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Page details</p>
              {(result.page_diagnostics as any[]).slice(0, 10).map((p: any) => (
                <div key={p.url} className="flex items-start gap-2 text-[11px]">
                  <span className={p.accessible ? 'text-green-400 shrink-0' : 'text-red-400 shrink-0'}>{p.accessible ? '✓' : '✗'}</span>
                  <div className="min-w-0 flex-1">
                    <span className="text-muted-foreground truncate block">{p.url}</span>
                    <span className="text-muted-foreground/60 flex flex-wrap gap-1">
                      <span>HTTP {p.http_status}</span>
                      {p.blocking_mechanism && <span className="text-amber-400">[{p.blocking_mechanism}]</span>}
                      {p.technical_relevance != null && p.accessible && (
                        <span className={p.technical_relevance >= 0.4 ? 'text-cyan-400' : 'text-muted-foreground/40'}>
                          [{Math.round(p.technical_relevance * 100)}% relevant]
                        </span>
                      )}
                      {p.depth > 0 && <span className="text-muted-foreground/40">depth:{p.depth}</span>}
                    </span>
                  </div>
                </div>
              ))}
              {result.page_diagnostics.length > 10 && (
                <p className="text-[10px] text-muted-foreground">+ {result.page_diagnostics.length - 10} more pages</p>
              )}
            </div>
          )}

          <p className="text-xs text-muted-foreground border-t border-green-500/10 pt-2">
            AI is studying the content. Results appear in the <strong>Integrated</strong> tab.
          </p>
        </div>
      )}

      {/* ── Error ── */}
      {status === 'error' && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="font-medium mb-0.5">Could not crawl</p>
            <p className="text-xs text-red-300/80 whitespace-pre-wrap">{error}</p>
          </div>
        </div>
      )}

      {/* ── Idle hint ── */}
      {status === 'idle' && (
        <div className="text-xs text-muted-foreground space-y-1.5 border-t border-border pt-3">
          <p className="font-medium text-foreground/70">Extracted automatically:</p>
          <div className="grid grid-cols-2 gap-y-1">
            {['Text & headings', 'Technical terminology', 'Procedures & steps', 'Safety warnings',
              'Equipment specs', 'Standards & references'].map(i => (
              <div key={i} className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3 w-3 text-cyan-400 shrink-0" />
                <span>{i}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 3. Learn from Existing Project ────────────────────────────────────────────

function ProjectLearnPanel({ onLearnDone }: { onLearnDone: () => void }) {
  const { data: projectsData, isLoading } = useTranslationProjects();
  const projects = Array.isArray(projectsData) ? projectsData : (projectsData?.projects ?? []);
  const [selected, setSelected] = useState<string>('');
  const [status, setStatus] = useState<'idle' | 'learning' | 'done' | 'error'>('idle');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const qc = useQueryClient();
  const { toast } = useToast();

  const selectedProj = projects.find((p: any) => p.id === selected);

  const learn = async () => {
    if (!selected) return;
    setStatus('learning');
    setError('');
    try {
      const data = await apiFetch('/api/learning/teach/project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: selected }),
      });
      setResult(data);
      setStatus('done');
      qc.invalidateQueries({ queryKey: ['study-jobs'] });
      qc.invalidateQueries({ queryKey: ['learning-stats'] });
      onLearnDone();
      toast({ title: 'Learning from project!', description: data.message });
    } catch (e: any) {
      setError(e.message || 'Failed to learn from project');
      setStatus('error');
    }
  };

  return (
    <div className="space-y-4">
      {isLoading && <p className="text-sm text-muted-foreground">Loading projects…</p>}

      {!isLoading && projects.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <FolderOpen className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No translation projects found</p>
          <p className="text-xs mt-1">Create a translation project first</p>
        </div>
      )}

      {projects.length > 0 && (
        <>
          <div className="space-y-2">
            <label className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Select Project</label>
            <select
              value={selected}
              onChange={e => { setSelected(e.target.value); setStatus('idle'); setResult(null); }}
              className="w-full h-9 text-sm bg-muted border border-border rounded-md px-3 text-foreground"
            >
              <option value="">Choose a project…</option>
              {projects.map((p: any) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.title || 'Untitled'} · {p.source_lang}→{p.target_lang}
                </option>
              ))}
            </select>
          </div>

          {selectedProj && (
            <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-3 text-xs space-y-1">
              <p className="font-medium text-purple-300">{selectedProj.name || selectedProj.title}</p>
              <div className="grid grid-cols-2 gap-1 text-muted-foreground">
                <span>Languages: <strong className="text-foreground">{selectedProj.source_lang} → {selectedProj.target_lang}</strong></span>
                <span>Segments: <strong className="text-foreground">{(selectedProj.segments?.length ?? 0).toLocaleString()}</strong></span>
                <span>Style: <strong className="text-foreground capitalize">{selectedProj.style || 'technical'}</strong></span>
                <span>Status: <strong className="text-foreground capitalize">{selectedProj.status || 'ready'}</strong></span>
              </div>
            </div>
          )}

          <div className="text-xs text-muted-foreground space-y-1">
            <p className="font-medium text-foreground/70">What the AI will learn:</p>
            <div className="grid grid-cols-2 gap-1">
              {['Terminology pairs (EN↔AR)', 'Technical vocabulary', 'Layout patterns', 'Writing style', 'Slide design decisions', 'Translation choices'].map(i => (
                <div key={i} className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3 w-3 text-purple-400 shrink-0" />
                  <span>{i}</span>
                </div>
              ))}
            </div>
          </div>

          <Button
            onClick={learn}
            disabled={!selected || status === 'learning'}
            className="w-full bg-purple-600 hover:bg-purple-500 text-white"
          >
            {status === 'learning' ? (
              <><Cpu className="h-4 w-4 mr-2 animate-spin" /> Learning…</>
            ) : (
              <><Brain className="h-4 w-4 mr-2" /> Learn from this Project</>
            )}
          </Button>
        </>
      )}

      {status === 'done' && result && (
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-sm text-green-400">
          <div className="flex items-center gap-2 font-medium mb-1">
            <CheckCircle2 className="h-4 w-4" /> Learning started!
          </div>
          <p className="text-xs text-muted-foreground">{result.message} — check Review Queue for approval.</p>
        </div>
      )}

      {status === 'error' && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

// ── 4. Learn PowerPoint Style ─────────────────────────────────────────────────

const PPTX_STAGES = [
  'Reading PowerPoint…',
  'Extracting layouts…',
  'Extracting fonts…',
  'Extracting colors…',
  'Learning style…',
  'Saving style profile…',
  'Completed.',
];

function PptxStylePanel({ onLearnDone }: { onLearnDone: () => void }) {
  const [status, setStatus] = useState<'idle' | 'processing' | 'done' | 'error'>('idle');
  const [stageIdx, setStageIdx] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [filename, setFilename] = useState('');
  const { toast } = useToast();
  const qc = useQueryClient();
  const stageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearStageTimer = () => {
    if (stageTimerRef.current) { clearInterval(stageTimerRef.current); stageTimerRef.current = null; }
  };

  const processFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pptx')) {
      setError('Only .pptx files are supported. Please drop a .pptx file.');
      setStatus('error');
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      setError('File too large (max 100 MB).');
      setStatus('error');
      return;
    }

    setFilename(file.name);
    setStatus('processing');
    setStageIdx(0);
    setError('');
    setResult(null);

    // Animate through stages while waiting for the response
    let idx = 0;
    stageTimerRef.current = setInterval(() => {
      idx = Math.min(idx + 1, PPTX_STAGES.length - 2); // don't advance past "Saving…"
      setStageIdx(idx);
    }, 600);

    try {
      const fd = new FormData();
      fd.append('file', file);

      const resp = await fetch(`${API}/api/learning/teach/pptx`, {
        method: 'POST',
        credentials: 'include',
        body: fd,
      });

      clearStageTimer();

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `Server error: HTTP ${resp.status}`);
      }

      const data = await resp.json();
      setStageIdx(PPTX_STAGES.length - 1); // "Completed."
      await new Promise(r => setTimeout(r, 300));

      setResult(data);
      setStatus('done');
      qc.invalidateQueries({ queryKey: ['layout-styles'] });
      qc.invalidateQueries({ queryKey: ['learning-stats'] });
      onLearnDone();
      toast({ title: 'Style profile extracted!', description: data.message });
    } catch (e: any) {
      clearStageTimer();
      setError(e.message || 'Upload failed');
      setStatus('error');
    }
  };

  const reset = () => { setStatus('idle'); setResult(null); setError(''); setFilename(''); setStageIdx(0); };

  const EXTRACTS = [
    'Slide layouts & master templates', 'Title fonts & sizes',
    'Body fonts & paragraph styles', 'Color palette & themes',
    'Arabic text alignment rules', 'Slide dimensions (4:3 / 16:9)',
    'Table styles & borders', 'Image placement zones',
    'Icon & SmartArt usage patterns', 'Animation sequences',
  ];

  return (
    <div className="space-y-4">

      {/* What gets extracted */}
      <div className="grid grid-cols-2 gap-1.5 text-xs text-muted-foreground">
        {EXTRACTS.map(item => (
          <div key={item} className="flex items-center gap-1.5">
            <CheckCircle2 className="h-3 w-3 text-pink-400 shrink-0" />
            <span>{item}</span>
          </div>
        ))}
      </div>

      {/* Dropzone — only shown in idle state */}
      {status === 'idle' && (
        <Dropzone
          accept=".pptx"
          label="Drop a PowerPoint file (.pptx) to learn its style"
          onFiles={files => files[0] && processFile(files[0])}
        />
      )}

      {/* Processing stages */}
      {status === 'processing' && (
        <div className="bg-muted/30 border border-pink-500/15 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm text-pink-400 font-medium truncate">
            <Presentation className="h-4 w-4 shrink-0 animate-pulse" />
            <span className="truncate">{filename}</span>
          </div>
          <div className="space-y-1.5">
            {PPTX_STAGES.slice(0, -1).map((s, i) => {
              const done = i < stageIdx;
              const active = i === stageIdx;
              return (
                <div key={s} className={`flex items-center gap-2 text-xs transition-colors ${done ? 'text-green-400' : active ? 'text-pink-400' : 'text-muted-foreground/30'}`}>
                  {done
                    ? <CheckCircle2 className="h-3 w-3 shrink-0" />
                    : active
                    ? <RefreshCw className="h-3 w-3 shrink-0 animate-spin" />
                    : <div className="h-3 w-3 rounded-full border border-current/30 shrink-0" />
                  }
                  {s}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Success result */}
      {status === 'done' && result && (
        <div className="space-y-4">
          <div className="bg-pink-500/10 border border-pink-500/20 rounded-lg p-4 space-y-3">
            {/* Header */}
            <div className="flex items-center gap-2 text-sm text-pink-400 font-medium">
              <CheckCheck className="h-4 w-4" /> Style Profile Extracted
            </div>
            <p className="text-sm font-semibold text-foreground leading-tight">{result.style_name}</p>
            <p className="text-[11px] text-muted-foreground">Uploaded {new Date().toLocaleTimeString()}</p>

            {/* Stats grid */}
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'Slides Analyzed', value: result.slides_analyzed, color: 'text-pink-400' },
                { label: 'Layouts Detected', value: result.layouts_detected, color: 'text-purple-400' },
                { label: 'Fonts Detected', value: result.fonts_detected, color: 'text-blue-400' },
                { label: 'Colors Detected', value: result.colors_detected, color: 'text-amber-400' },
              ].map(s => (
                <div key={s.label} className="bg-muted/50 rounded-lg p-2 text-center">
                  <div className={`text-xl font-bold tabular-nums ${s.color}`}>{s.value}</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{s.label}</div>
                </div>
              ))}
            </div>

            {/* Style detail */}
            {result.properties && (
              <div className="space-y-1.5 border-t border-pink-500/10 pt-2 text-xs">
                <div className="flex justify-between text-muted-foreground">
                  <span>Slide size</span>
                  <span className="text-foreground font-mono">
                    {result.properties.slide_width_in}" × {result.properties.slide_height_in}" ({result.properties.aspect_ratio})
                  </span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Title font</span>
                  <span className="text-foreground font-mono">
                    {result.properties.title_font_name} {result.properties.title_font_size}pt
                    {result.properties.title_bold ? ' Bold' : ''}
                  </span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Body font</span>
                  <span className="text-foreground font-mono">
                    {result.properties.body_font_name} {result.properties.body_font_size}pt
                  </span>
                </div>
                {result.properties.theme_colors?.length > 0 && (
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>Theme colors</span>
                    <div className="flex gap-1">
                      {result.properties.theme_colors.slice(0, 8).map((c: string) => (
                        <div
                          key={c}
                          className="h-4 w-4 rounded border border-white/10 shrink-0"
                          style={{ backgroundColor: `#${c}` }}
                          title={`#${c}`}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            View and manage this profile in the <strong>Layout Styles</strong> tab below. You can set it as the default for training generation.
          </p>

          <Button variant="outline" size="sm" className="w-full text-xs border-pink-500/30 hover:border-pink-500/60" onClick={reset}>
            <FileUp className="h-3.5 w-3.5 mr-1.5" /> Upload Another PPTX
          </Button>
        </div>
      )}

      {/* Error */}
      {status === 'error' && (
        <div className="space-y-3">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-400 mb-0.5">Upload failed</p>
              <p className="text-xs text-red-300/80">{error}</p>
            </div>
          </div>
          <Button variant="outline" size="sm" className="w-full text-xs" onClick={reset}>Try again</Button>
        </div>
      )}
    </div>
  );
}

// ── 5. Learn Terminology ──────────────────────────────────────────────────────

function TerminologyLearnPanel() {
  const { data: stats } = useLearningStats();
  const { data: terms } = useTerminology('', '');
  const topTerms = (terms?.entries ?? []).slice(0, 6);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total Terms', value: stats?.terminology_entries ?? 0, color: 'text-green-400' },
          { label: 'Images Classified', value: stats?.image_classifications ?? 0, color: 'text-blue-400' },
          { label: 'Slide Corrections', value: stats?.slide_corrections ?? 0, color: 'text-amber-400' },
        ].map(s => (
          <div key={s.label} className="bg-muted/40 rounded-lg p-3 text-center">
            <div className={`text-2xl font-bold tabular-nums ${s.color}`}>{s.value}</div>
            <div className="text-[10px] text-muted-foreground mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2 text-xs text-green-400">
        <Zap className="h-3.5 w-3.5 shrink-0" />
        <span>Runs automatically on every document upload — no manual action required</span>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">What gets extracted:</p>
        <div className="grid grid-cols-2 gap-1.5 text-xs text-muted-foreground">
          {['Technical abbreviations (e.g. HV, kV, CT)', 'Equipment & component names', 'Procedures & workflows', 'Safety warnings & cautions', 'Specification values', 'Bilingual glossary pairs'].map(i => (
            <div key={i} className="flex items-center gap-1.5">
              <Tag className="h-3 w-3 text-green-400 shrink-0" />
              <span>{i}</span>
            </div>
          ))}
        </div>
      </div>

      {topTerms.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">Recently extracted terms:</p>
          <div className="flex flex-wrap gap-1.5">
            {topTerms.map((t: any) => (
              <span key={t.id} className="px-2 py-0.5 bg-green-500/10 text-green-300 border border-green-500/20 rounded-md text-xs font-mono">
                {t.term}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 6. Learn Training Methodology ─────────────────────────────────────────────

function MethodologyLearnPanel() {
  const { data: stats } = useLearningStats();
  const { data: patterns } = useExamPatterns('', '', '');
  const recentPatterns = (patterns?.patterns ?? []).slice(0, 3);

  const BLOOM_LEVELS = ['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'];
  const bloomColors: Record<string, string> = {
    remember: 'bg-blue-500/20 text-blue-300', understand: 'bg-cyan-500/20 text-cyan-300',
    apply: 'bg-green-500/20 text-green-300', analyze: 'bg-amber-500/20 text-amber-300',
    evaluate: 'bg-orange-500/20 text-orange-300', create: 'bg-purple-500/20 text-purple-300',
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: 'Exam Patterns', value: stats?.exam_patterns ?? 0, color: 'text-amber-400' },
          { label: 'Knowledge Nodes', value: stats?.knowledge_nodes ?? 0, color: 'text-cyan-400' },
        ].map(s => (
          <div key={s.label} className="bg-muted/40 rounded-lg p-3 text-center">
            <div className={`text-2xl font-bold tabular-nums ${s.color}`}>{s.value}</div>
            <div className="text-[10px] text-muted-foreground mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 text-xs text-amber-400">
        <Zap className="h-3.5 w-3.5 shrink-0" />
        <span>Runs automatically on every document upload — no manual action required</span>
      </div>

      <div className="grid grid-cols-2 gap-1.5 text-xs text-muted-foreground">
        {['Course structure detection', 'Learning objective extraction', 'Practical exercise patterns', 'Assessment question styles', 'Knowledge progression mapping', 'Bloom\'s taxonomy classification'].map(i => (
          <div key={i} className="flex items-center gap-1.5">
            <GraduationCap className="h-3 w-3 text-amber-400 shrink-0" />
            <span>{i}</span>
          </div>
        ))}
      </div>

      {recentPatterns.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">Recent exam patterns:</p>
          <div className="space-y-2">
            {recentPatterns.map((p: any) => (
              <div key={p.id} className="bg-muted/30 rounded-lg px-3 py-2 text-xs">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] ${bloomColors[p.bloom_level] ?? 'bg-muted text-muted-foreground'}`}>
                    {p.bloom_level}
                  </span>
                  <span className="text-muted-foreground">Difficulty: {p.difficulty ?? 'medium'}</span>
                </div>
                <p className="text-foreground/80 line-clamp-2">{p.question_text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 7. Learn References ───────────────────────────────────────────────────────

function ReferencesLearnPanel({ onLearnDone }: { onLearnDone: () => void }) {
  const { data: report } = useReport();
  const { data: stats } = useLearningStats();

  const kb = report?.knowledge_bank ?? {};
  const categories = [
    { label: 'Technical Concepts', value: kb.total_concepts ?? 0, color: 'text-blue-400' },
    { label: 'Procedures', value: kb.total_procedures ?? 0, color: 'text-green-400' },
    { label: 'Components', value: kb.total_components ?? 0, color: 'text-cyan-400' },
    { label: 'Safety Warnings', value: kb.safety_warnings ?? 0, color: 'text-amber-400' },
    { label: 'Unique Terms', value: kb.unique_terms ?? 0, color: 'text-purple-400' },
    { label: 'Knowledge Nodes', value: stats?.knowledge_nodes ?? 0, color: 'text-teal-400' },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        {categories.map(c => (
          <div key={c.label} className="bg-muted/40 rounded-lg p-2.5 text-center">
            <div className={`text-xl font-bold tabular-nums ${c.color}`}>{c.value}</div>
            <div className="text-[10px] text-muted-foreground mt-0.5">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 bg-teal-500/10 border border-teal-500/20 rounded-lg px-3 py-2 text-xs text-teal-400">
        <Zap className="h-3.5 w-3.5 shrink-0" />
        <span>Runs automatically on every document upload — or upload a reference directly below</span>
      </div>

      <div className="grid grid-cols-2 gap-1.5 text-xs text-muted-foreground">
        {['ISO / IEC standards', 'Manufacturer manuals', 'Technical specifications', 'Scientific papers', 'Regulatory documents', 'Citation extraction'].map(i => (
          <div key={i} className="flex items-center gap-1.5">
            <BookOpen className="h-3 w-3 text-teal-400 shrink-0" />
            <span>{i}</span>
          </div>
        ))}
      </div>

      <GenericUploadPanel
        onLearnDone={onLearnDone}
        dropLabel="Drop standards, manuals, or reference documents"
        successHint={<>Uploaded &amp; indexed — references are being extracted. Results appear above once complete</>}
      />
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TEACH AI SECTION
// ══════════════════════════════════════════════════════════════════════════════

const TEACH_METHODS = [
  {
    id: 'documents' as const,
    icon: FileUp,
    label: 'Upload Documents',
    desc: 'PDF, DOCX, PPTX, XLSX, TXT, ZIP',
    badge: 'Manual',
    color: 'text-blue-400',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/20',
    activeBorder: 'border-blue-500',
    glow: 'hover:border-blue-500/50',
  },
  {
    id: 'website' as const,
    icon: Globe,
    label: 'Manual Source',
    desc: 'Give a URL yourself — website, docs, standards, sitemaps, PDFs',
    badge: 'Manual',
    color: 'text-cyan-400',
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/20',
    activeBorder: 'border-cyan-500',
    glow: 'hover:border-cyan-500/50',
  },
  {
    id: 'autonomous_research' as const,
    icon: Rocket,
    label: 'Autonomous Research',
    desc: 'Give a mission — the agent discovers, crawls, and learns on its own',
    badge: 'Auto',
    color: 'text-indigo-400',
    bg: 'bg-indigo-500/10',
    border: 'border-indigo-500/20',
    activeBorder: 'border-indigo-500',
    glow: 'hover:border-indigo-500/50',
  },
  {
    id: 'project' as const,
    icon: FolderOpen,
    label: 'Learn from Project',
    desc: 'Extract from translated projects',
    badge: 'Manual',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/20',
    activeBorder: 'border-purple-500',
    glow: 'hover:border-purple-500/50',
  },
  {
    id: 'pptx' as const,
    icon: Presentation,
    label: 'Learn PowerPoint Style',
    desc: 'Fonts, colors, layouts, animations',
    badge: 'Manual',
    color: 'text-pink-400',
    bg: 'bg-pink-500/10',
    border: 'border-pink-500/20',
    activeBorder: 'border-pink-500',
    glow: 'hover:border-pink-500/50',
  },
  {
    id: 'terminology' as const,
    icon: BookMarked,
    label: 'Learn Terminology',
    desc: 'Technical terms & bilingual glossary',
    badge: 'Auto',
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/20',
    activeBorder: 'border-green-500',
    glow: 'hover:border-green-500/50',
  },
  {
    id: 'methodology' as const,
    icon: GraduationCap,
    label: 'Learn Methodology',
    desc: 'Course structure, objectives, assessments',
    badge: 'Auto',
    color: 'text-amber-400',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    activeBorder: 'border-amber-500',
    glow: 'hover:border-amber-500/50',
  },
  {
    id: 'references' as const,
    icon: BookOpen,
    label: 'Learn References',
    desc: 'Standards, manuals, citations',
    badge: 'Auto',
    color: 'text-teal-400',
    bg: 'bg-teal-500/10',
    border: 'border-teal-500/20',
    activeBorder: 'border-teal-500',
    glow: 'hover:border-teal-500/50',
  },
] as const;

type TeachMethodId = typeof TEACH_METHODS[number]['id'];

function TeachSection({ onLearnDone }: { onLearnDone: () => void }) {
  const [active, setActive] = useState<TeachMethodId | null>(null);

  const toggle = (id: TeachMethodId) => setActive(prev => prev === id ? null : id);
  const activeMethod = TEACH_METHODS.find(m => m.id === active);

  return (
    <div className="space-y-4">
      {/* Method grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {TEACH_METHODS.map(method => {
          const Icon = method.icon;
          const isActive = active === method.id;
          return (
            <button
              key={method.id}
              onClick={() => toggle(method.id)}
              className={`relative text-left rounded-xl border p-4 transition-all group ${
                isActive
                  ? `${method.bg} ${method.activeBorder} shadow-lg`
                  : `bg-card border-border ${method.glow} hover:bg-muted/30`
              }`}
            >
              {/* Auto badge */}
              {method.badge === 'Auto' && (
                <div className="absolute top-2 right-2">
                  <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide text-green-400 bg-green-500/10 border border-green-500/20 rounded-full px-1.5 py-0.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                    Auto
                  </span>
                </div>
              )}

              <div className={`p-2 rounded-lg ${method.bg} w-fit mb-3`}>
                <Icon className={`h-5 w-5 ${method.color}`} />
              </div>
              <div className="text-sm font-semibold leading-tight">{method.label}</div>
              <div className="text-[11px] text-muted-foreground mt-1 leading-snug">{method.desc}</div>
              <div className={`flex items-center gap-1 mt-2 text-[11px] font-medium ${method.color}`}>
                {isActive ? <><ChevronUp className="h-3 w-3" /> Close</> : <><ChevronDown className="h-3 w-3" /> Open</>}
              </div>
            </button>
          );
        })}
      </div>

      {/* Expanded panel */}
      {activeMethod && (
        <Card className={`border ${activeMethod.border} ${activeMethod.bg}`}>
          <CardHeader className="pb-3">
            <CardTitle className={`text-base flex items-center gap-2 ${activeMethod.color}`}>
              <activeMethod.icon className="h-5 w-5" />
              {activeMethod.label}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {active === 'documents'   && <DocumentUploadPanel onLearnDone={onLearnDone} />}
            {active === 'website'     && <WebSourcePanel onLearnDone={onLearnDone} />}
            {active === 'autonomous_research' && <AutonomousResearchPanel onLearnDone={onLearnDone} />}
            {active === 'project'     && <ProjectLearnPanel onLearnDone={onLearnDone} />}
            {active === 'pptx'        && <PptxStylePanel onLearnDone={onLearnDone} />}
            {active === 'terminology' && <TerminologyLearnPanel />}
            {active === 'methodology' && <MethodologyLearnPanel />}
            {active === 'references'  && <ReferencesLearnPanel onLearnDone={onLearnDone} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// LIVE STATS STRIP
// ══════════════════════════════════════════════════════════════════════════════

function LiveStatsStrip() {
  const { data: stats } = useLearningStats();
  const { data: report } = useReport();
  const { data: vStats } = useVisionStats();
  const confidence = Math.round((report?.quality?.avg_confidence_score ?? 0) * 100);

  const kb = report?.knowledge_bank ?? {};
  const kg = report?.knowledge_graph ?? {};

  const items = [
    { icon: Database,      label: 'Docs Studied',     value: stats?.documents_studied ?? 0,          color: 'text-blue-400'   },
    { icon: Brain,         label: 'Knowledge Nodes',  value: kg.nodes ?? (stats?.knowledge_nodes ?? 0), color: 'text-cyan-400'   },
    { icon: Network,       label: 'Relationships',    value: kg.edges ?? 0,                           color: 'text-indigo-400' },
    { icon: Tag,           label: 'Terms Extracted',  value: stats?.terminology_entries ?? 0,         color: 'text-green-400'  },
    { icon: Wrench,        label: 'Procedures',       value: kb.total_procedures ?? 0,                color: 'text-amber-400'  },
    { icon: Shield,        label: 'Safety Rules',     value: kb.safety_warnings ?? 0,                 color: 'text-red-400'    },
    { icon: Target,        label: 'Training Obj.',    value: kb.learning_objectives ?? 0,             color: 'text-purple-400' },
    { icon: GraduationCap, label: 'Exam Patterns',    value: stats?.exam_patterns ?? 0,               color: 'text-pink-400'   },
    { icon: Layers,        label: 'Layouts Learned',  value: stats?.layout_styles ?? 0,               color: 'text-teal-400'   },
    { icon: Eye,           label: 'Images Captioned', value: stats?.image_classifications ?? 0,       color: 'text-violet-400' },
    {
      icon: Sparkles,
      label: 'Avg Confidence',
      value: `${confidence}%`,
      color: confidence >= 70 ? 'text-green-400' : confidence >= 40 ? 'text-amber-400' : 'text-red-400',
    },
  ];

  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
      {items.map(item => {
        const Icon = item.icon;
        // Hide zero-value items (except confidence, which always shows)
        const numVal = typeof item.value === 'number' ? item.value : -1;
        if (numVal === 0 && item.label !== 'Avg Confidence') return null;
        return (
          <div key={item.label} className="flex items-center gap-2 bg-card border border-border rounded-lg px-3 py-2 shrink-0">
            <Icon className={`h-3.5 w-3.5 ${item.color}`} />
            <div>
              <div className={`text-base font-bold tabular-nums leading-none ${item.color}`}>{item.value}</div>
              <div className="text-[10px] text-muted-foreground leading-none mt-0.5 whitespace-nowrap">{item.label}</div>
            </div>
          </div>
        );
      })}
      {vStats && (vStats.total_saved_usd ?? 0) > 0 && (
        <div className="flex items-center gap-2 bg-card border border-border rounded-lg px-3 py-2 shrink-0">
          <TrendingUp className="h-3.5 w-3.5 text-green-400" />
          <div>
            <div className="text-base font-bold tabular-nums leading-none text-green-400">
              ${(vStats.total_saved_usd ?? 0).toFixed(2)}
            </div>
            <div className="text-[10px] text-muted-foreground leading-none mt-0.5">Vision Saved</div>
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// ACTIVE JOBS FEED
// ══════════════════════════════════════════════════════════════════════════════

function ActiveJobsFeed({ onSwitchTab }: { onSwitchTab: (tab: TabId) => void }) {
  const { data: allJobs } = useStudyJobs();
  // Active = currently being processed (studying, validating, learning, etc.)
  const active = (allJobs ?? []).filter((j: any) =>
    ['pending', 'studying', 'validating', 'learning', 'awaiting_approval'].includes(j.status)
  );

  if (active.length === 0) return null;

  return (
    <Card className="border-border bg-card">
      <CardHeader className="pb-2 flex-row items-center justify-between">
        <CardTitle className="text-sm flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-400" />
          Active Learning
        </CardTitle>
        <button
          onClick={() => onSwitchTab('integrated')}
          className="text-xs text-green-400 hover:text-green-300 flex items-center gap-1 font-medium"
        >
          View integrated →
        </button>
      </CardHeader>
      <CardContent className="pt-0 space-y-2">
        {active.map((job: any) => {
          const stageLabel =
            job.status === 'pending'            ? 'Queued — waiting to start' :
            job.status === 'processing'         ? 'Extracting text & structure…' :
            job.status === 'studying'           ? 'Analysing & building knowledge graph…' :
            job.status === 'validating'         ? 'Validating extracted knowledge…' :
            job.status === 'learning'           ? 'Generating terminology & exam bank…' :
            job.status === 'awaiting_approval'  ? 'Integrating into knowledge base…' :
            'Processing…';
          return (
            <div key={job.id} className="flex items-center gap-3 bg-blue-500/5 border border-blue-500/10 rounded-lg px-3 py-2">
              <Cpu className="h-4 w-4 text-blue-400 animate-spin shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{job.filename}</div>
                <div className="text-[10px] text-blue-400 mt-0.5">{stageLabel}</div>
              </div>
              <StatusBadge status={job.status} />
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// KNOWLEDGE BASE TABS (preserved from original)
// ══════════════════════════════════════════════════════════════════════════════

// ── Integrated Knowledge tab ──────────────────────────────────────────────────

// Stat row with green checkmark — used inside IntegratedJobCard
function StatRow({ label, value, isYesNo = false }: { label: string; value: number | boolean; isYesNo?: boolean }) {
  const hasValue = isYesNo ? !!value : (value as number) > 0;
  if (!hasValue) return null;
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border/40 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
        <svg className="h-3.5 w-3.5 text-green-400 shrink-0" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
          <path d="M5 8.5l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        {isYesNo ? 'Yes' : (value as number)}
      </span>
    </div>
  );
}

function UsageChip({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-foreground/80">
      <div className="h-3.5 w-3.5 rounded border border-green-400 bg-green-500/20 flex items-center justify-center shrink-0">
        <svg viewBox="0 0 10 10" className="h-2 w-2 text-green-400" fill="none">
          <path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      {label}
    </div>
  );
}

function IntegratedJobCard({ job, onRefresh }: { job: any; onRefresh: () => void }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [showDetail, setShowDetail] = useState(false);

  const undo = useMutation({
    mutationFn: () => apiFetch(`/api/study/jobs/${job.id}/undo`, { method: 'POST' }),
    onSuccess: (data: any) => {
      toast({ title: 'Import undone', description: `${data.nodes_removed ?? 0} knowledge nodes removed` });
      qc.invalidateQueries({ queryKey: ['study-jobs'] });
      qc.invalidateQueries({ queryKey: ['learning-stats'] });
      onRefresh();
    },
    onError: (e: any) => toast({ title: 'Undo failed', description: e.message, variant: 'destructive' }),
  });

  const archive = useMutation({
    mutationFn: () => apiFetch(`/api/study/jobs/${job.id}/archive`, { method: 'POST' }),
    onSuccess: () => {
      toast({ title: 'Archived', description: 'Source excluded from future generation' });
      qc.invalidateQueries({ queryKey: ['study-jobs'] });
      onRefresh();
    },
    onError: (e: any) => toast({ title: 'Archive failed', description: e.message, variant: 'destructive' }),
  });

  const r = job.report ?? {};
  const overall = job.scores?.overall ?? 0;
  const scoreColor =
    overall >= 85 ? 'text-green-400' :
    overall >= 65 ? 'text-amber-400' :
    overall > 0   ? 'text-red-400' :
    'text-muted-foreground';

  return (
    <Card className={`bg-[#0d1117] border border-border/60 ${job.archived ? 'opacity-50' : ''}`}>
      <CardContent className="p-0">

        {/* ── Header ── */}
        <div className="px-4 pt-4 pb-3 border-b border-border/40">
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
            Document learned from:
          </p>
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-semibold text-foreground leading-snug flex-1 min-w-0">{job.filename}</p>
            {job.archived && (
              <Badge variant="outline" className="text-[10px] border-slate-600 text-slate-400 shrink-0">Archived</Badge>
            )}
          </div>
          {job.understanding?.purpose && (
            <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">{job.understanding.purpose}</p>
          )}
        </div>

        {/* ── Score ── */}
        {overall > 0 && (
          <div className="px-4 py-3 border-b border-border/40 flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground font-medium">Knowledge Score</span>
            <span className={`text-2xl font-bold tabular-nums ${scoreColor}`}>{overall}%</span>
          </div>
        )}

        {/* ── Stats grid ── */}
        <div className="px-4 py-2 border-b border-border/40">
          <StatRow label="Concepts"                     value={r.concepts ?? 0} />
          <StatRow label="Procedures"                   value={r.procedures ?? 0} />
          <StatRow label="Components"                   value={r.components ?? 0} />
          <StatRow label="Safety Rules"                 value={r.safety_rules ?? 0} />
          <StatRow label="Troubleshooting Cases"        value={r.troubleshooting ?? 0} />
          <StatRow label="Exam Questions learned"       value={r.exam_questions ?? 0} />
          <StatRow label="PowerPoint Layout extracted"  value={r.pptx_layout ?? false} isYesNo />
          <StatRow label="Animations extracted"         value={r.animations ?? false}   isYesNo />
          <StatRow label="Figures extracted"            value={r.figures ?? 0} />
          <StatRow label="References extracted"         value={r.references ?? 0} />
        </div>

        {/* ── Can be used in ── */}
        <div className="px-4 py-3 border-b border-border/40">
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-2">Can be used in:</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            <UsageChip label="Training Generator" />
            <UsageChip label="AI Chat" />
            <UsageChip label="Exam Generator" />
            <UsageChip label="Innovation Engine" />
            <UsageChip label="Image Analysis" />
          </div>
        </div>

        {/* ── Expandable knowledge detail ── */}
        <button
          className="w-full flex items-center justify-between px-4 py-2.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
          onClick={() => setShowDetail(!showDetail)}
        >
          <span className="flex items-center gap-1.5">
            <Network className="h-3 w-3" />
            {showDetail ? 'Hide extracted detail' : 'Show extracted knowledge'}
          </span>
          {showDetail ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>

        {showDetail && (
          <div className="px-4 pb-4 space-y-3 text-xs border-t border-border/40 pt-3">
            {/* Technical components / systems */}
            {((job.extracted?.systems?.length ?? 0) + (job.extracted?.components?.length ?? 0)) > 0 && (
              <div>
                <p className="font-semibold text-foreground mb-1.5">
                  Technical Concepts ({(job.extracted.systems?.length ?? 0) + (job.extracted.components?.length ?? 0)})
                </p>
                <div className="flex flex-wrap gap-1">
                  {[...(job.extracted.systems || []), ...(job.extracted.components || [])].slice(0, 30).map((s: string, i: number) => (
                    <span key={i} className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px]">{s}</span>
                  ))}
                </div>
              </div>
            )}
            {/* Terminology */}
            {job.extracted?.terminology?.length > 0 && (
              <div>
                <p className="font-semibold text-foreground mb-1.5">Terminology ({job.extracted.terminology.length})</p>
                <div className="space-y-1 max-h-32 overflow-y-auto pr-1">
                  {job.extracted.terminology.slice(0, 12).map((t: any, i: number) => (
                    <div key={i} className="flex gap-1.5">
                      <span className="font-medium text-foreground shrink-0">{typeof t === 'object' ? t.term : t}:</span>
                      <span className="text-muted-foreground">{typeof t === 'object' ? (t.definition || t.description || '') : ''}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* Safety warnings */}
            {job.extracted?.warnings?.length > 0 && (
              <div>
                <p className="font-semibold text-amber-400 mb-1.5 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" /> Safety Items ({job.extracted.warnings.length})
                </p>
                <ul className="list-disc list-inside space-y-0.5 text-amber-400/80">
                  {job.extracted.warnings.slice(0, 5).map((w: string, i: number) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            {/* Quiz ideas */}
            {job.training_profile?.quiz_ideas?.length > 0 && (
              <div>
                <p className="font-semibold text-foreground mb-1.5 flex items-center gap-1">
                  <GraduationCap className="h-3 w-3" /> Exam Patterns ({job.training_profile.quiz_ideas.length})
                </p>
                <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                  {job.training_profile.quiz_ideas.slice(0, 4).map((q: string, i: number) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </div>
            )}
            {/* Knowledge graph */}
            {job.graph?.nodes?.length > 0 && (
              <div>
                <p className="font-semibold text-foreground mb-1.5 flex items-center gap-1">
                  <Network className="h-3 w-3" /> Knowledge Graph ({job.graph.nodes.length} nodes, {job.graph.edges?.length ?? 0} edges)
                </p>
                <div className="flex flex-wrap gap-1">
                  {job.graph.nodes.slice(0, 16).map((n: any, i: number) => (
                    <span key={i} className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 text-[10px]">{n.label || n}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Footer: timestamp + actions ── */}
        <div className="px-4 py-3 flex items-center justify-between gap-2 flex-wrap">
          <p className="text-[10px] text-muted-foreground">
            {job.approved_at
              ? `Integrated ${new Date(job.approved_at).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })}`
              : 'Pending integration'}
            {(job.cost_usd ?? 0) > 0 && ` · ${job.cost_usd.toFixed(4)}`}
          </p>
          {!job.archived && (job.status === 'integrated' || job.status === 'approved') && (
            <div className="flex gap-1.5">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[11px] text-muted-foreground hover:text-foreground px-2"
                onClick={() => undo.mutate()}
                disabled={undo.isPending || archive.isPending}
              >
                <X className="h-3 w-3 mr-1" />
                {undo.isPending ? 'Undoing…' : 'Remove'}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[11px] text-muted-foreground hover:text-foreground px-2"
                onClick={() => archive.mutate()}
                disabled={undo.isPending || archive.isPending}
              >
                {archive.isPending ? 'Archiving…' : 'Archive'}
              </Button>
            </div>
          )}
        </div>

      </CardContent>
    </Card>
  );
}

// ── Failed / Stalled job card (with Resume Analysis button) ───────────────────

function FailedJobCard({ job, onRefresh }: { job: any; onRefresh: () => void }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const isStalled = job.status === 'stalled';

  const retry = useMutation({
    mutationFn: () => apiFetch(`/api/study/jobs/${job.id}/retry`, { method: 'POST' }),
    onSuccess: (data: any) => {
      toast({ title: 'Analysis started', description: `${data.filename} — results appear in a few minutes` });
      qc.invalidateQueries({ queryKey: ['study-jobs'] });
      onRefresh();
    },
    onError: (e: any) => toast({ title: 'Resume failed', description: e.message, variant: 'destructive' }),
  });

  return (
    <Card className={`bg-card border-border ${isStalled ? 'border-amber-500/20' : 'border-red-500/20'}`}>
      <CardContent className="pt-4 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              {isStalled
                ? <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 text-[10px]">Analysis Stalled</Badge>
                : <Badge className="bg-red-500/20 text-red-400 border-red-500/30 text-[10px]">Analysis Failed</Badge>
              }
            </div>
            <p className="text-sm font-medium truncate">{job.filename}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {isStalled
                ? 'Analysis was interrupted before it could start (server restart). No processing was done — document text is preserved.'
                : (job.stalled_reason || 'Knowledge extraction failed at a specific stage.')}
            </p>
            {job.stalled_reason && (
              <p className="text-[10px] text-muted-foreground/70 mt-1 font-mono">{job.stalled_reason}</p>
            )}
            <p className="text-[10px] text-muted-foreground mt-1">
              Document text is available. Resume continues from AI analysis (no re-parse) with automatic OpenAI/Gemini fallback.
            </p>
          </div>
          <Button
            size="sm"
            className={`shrink-0 text-white text-xs ${isStalled ? 'bg-amber-600 hover:bg-amber-500' : 'bg-blue-600 hover:bg-blue-500'}`}
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
          >
            <RefreshCw className={`h-3 w-3 mr-1 ${retry.isPending ? 'animate-spin' : ''}`} />
            {retry.isPending ? 'Starting…' : isStalled ? 'Resume Analysis' : 'Retry Analysis'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function IntegratedTab() {
  const integrated = useStudyJobs('integrated');
  const approved   = useStudyJobs('approved');   // backward compat
  const errors     = useStudyJobs('error');
  const failed     = useStudyJobs('failed');
  const stalled    = useStudyJobs('stalled');    // orphaned by server restart
  const qc = useQueryClient();

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['study-jobs'] });
    qc.invalidateQueries({ queryKey: ['learning-stats'] });
  };

  // Merge integrated + legacy approved, dedup by id
  const raw = [...(integrated.data ?? []), ...(approved.data ?? [])];
  const seen = new Set<string>();
  const jobs = raw.filter((j: any) => { if (seen.has(j.id)) return false; seen.add(j.id); return true; });

  // Stalled jobs shown at the top with amber "Resume Analysis" button — not as errors
  const stalledJobs = stalled.data ?? [];
  const failedJobs  = [...(errors.data ?? []), ...(failed.data ?? [])];

  const isLoading = integrated.isLoading && approved.isLoading;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <CheckCheck className="h-4 w-4 text-green-400" />
          Integrated Knowledge
          {jobs.length > 0 && <Badge className="bg-green-500/20 text-green-400 border-green-500/30 text-[10px]">{jobs.length}</Badge>}
        </h2>
        <div className="flex items-center gap-2">
          {failedJobs.length > 0 && (
            <RetryAllButton failedJobs={failedJobs} onRefresh={refresh} />
          )}
          <Button size="sm" variant="outline" onClick={refresh}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}

      {/* Stalled jobs — interrupted by server restart, shown with amber Resume button */}
      {stalledJobs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-amber-400 font-medium flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            {stalledJobs.length} document{stalledJobs.length > 1 ? 's' : ''} stalled — analysis was interrupted
          </p>
          {stalledJobs.map((job: any) => (
            <FailedJobCard key={job.id} job={job} onRefresh={refresh} />
          ))}
        </div>
      )}

      {/* Failed jobs — encountered an error, show with retry option */}
      {failedJobs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-red-400 font-medium flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            {failedJobs.length} document{failedJobs.length > 1 ? 's' : ''} need analysis
          </p>
          {failedJobs.map((job: any) => (
            <FailedJobCard key={job.id} job={job} onRefresh={refresh} />
          ))}
        </div>
      )}

      {jobs.length === 0 && failedJobs.length === 0 && stalledJobs.length === 0 && !isLoading && (
        <Card className="bg-card border-border">
          <CardContent className="pt-8 pb-8 text-center text-muted-foreground">
            <Brain className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No integrated knowledge yet</p>
            <p className="text-xs mt-1">Upload documents in the Teach AI section above — knowledge integrates automatically</p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4">
        {jobs.map((job: any) => (
          <IntegratedJobCard key={job.id} job={job} onRefresh={refresh} />
        ))}
      </div>
    </div>
  );
}

function RetryAllButton({ failedJobs, onRefresh }: { failedJobs: any[]; onRefresh: () => void }) {
  const { toast } = useToast();
  const qc = useQueryClient();

  const retryAll = useMutation({
    mutationFn: () => apiFetch('/api/study/jobs/retry-all', { method: 'POST' }),
    onSuccess: (data: any) => {
      toast({ title: `${data.count} analyses started`, description: 'Results appear in a few minutes per document' });
      qc.invalidateQueries({ queryKey: ['study-jobs'] });
      onRefresh();
    },
    onError: (e: any) => toast({ title: 'Retry all failed', description: e.message, variant: 'destructive' }),
  });

  return (
    <Button
      size="sm"
      className="bg-blue-600 hover:bg-blue-500 text-white text-xs h-7"
      onClick={() => retryAll.mutate()}
      disabled={retryAll.isPending}
    >
      <RefreshCw className={`h-3 w-3 mr-1 ${retryAll.isPending ? 'animate-spin' : ''}`} />
      {retryAll.isPending ? 'Starting…' : `Retry All (${failedJobs.length})`}
    </Button>
  );
}

// ── Terminology Browser tab ───────────────────────────────────────────────────

const TERM_CATEGORIES = ['', 'abbreviation', 'equipment', 'component', 'procedure', 'safety', 'specification', 'general'];

function TerminologyTab() {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const { data, isLoading } = useTerminology(query, category);
  const entries = data?.entries ?? [];

  const categoryColors: Record<string, string> = {
    abbreviation:  'bg-purple-500/10 text-purple-300 border-purple-500/20',
    equipment:     'bg-blue-500/10 text-blue-300 border-blue-500/20',
    component:     'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
    procedure:     'bg-green-500/10 text-green-300 border-green-500/20',
    safety:        'bg-amber-500/10 text-amber-300 border-amber-500/20',
    specification: 'bg-orange-500/10 text-orange-300 border-orange-500/20',
    general:       'bg-slate-500/10 text-slate-300 border-slate-500/20',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-purple-400" />
          Terminology Bank
          {data?.total != null && <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30 text-[10px]">{data.total} terms</Badge>}
        </h2>
      </div>

      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input placeholder="Search terms…" value={query} onChange={e => setQuery(e.target.value)} className="pl-8 h-8 text-sm bg-muted border-border" />
        </div>
        <select value={category} onChange={e => setCategory(e.target.value)} className="h-8 text-xs bg-muted border border-border rounded-md px-2 text-foreground">
          {TERM_CATEGORIES.map(c => (
            <option key={c} value={c}>{c ? c.charAt(0).toUpperCase() + c.slice(1) : 'All categories'}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}

      {entries.length === 0 && !isLoading && (
        <Card className="bg-card border-border">
          <CardContent className="pt-8 pb-8 text-center text-muted-foreground">
            <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No terminology entries yet</p>
            <p className="text-xs mt-1">Terms are extracted automatically when you upload documents</p>
          </CardContent>
        </Card>
      )}

      {entries.length > 0 && (
        <div className="overflow-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground">Term</th>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground">Category</th>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground">Definition</th>
                <th className="text-right px-3 py-2 font-medium text-muted-foreground">Uses</th>
                <th className="text-right px-3 py-2 font-medium text-muted-foreground">Conf</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {entries.map((e: any) => (
                <tr key={e.id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-3 py-2 font-medium text-foreground">{e.term}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${categoryColors[e.category] ?? 'bg-muted text-muted-foreground'}`}>{e.category}</span>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground max-w-xs truncate">{e.definition || '—'}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{e.use_count}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{Math.round(e.confidence * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Layout Styles tab ─────────────────────────────────────────────────────────

function StyleCard({ s, onRefetch }: { s: any; onRefetch: () => void }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(s.name || '');
  const [org, setOrg]   = useState(s.organisation || '');
  const [dept, setDept] = useState(s.department || '');
  const [lang, setLang] = useState(s.language || '');
  const [saving, setSaving] = useState(false);

  const profile = s.style_profile ?? s.properties ?? {};
  const colors = profile.theme_colors ?? [];

  const setDefault = useMutation({
    mutationFn: () => apiFetch('/api/learning/styles/default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ style_id: s.id }),
    }),
    onSuccess: () => { toast({ title: 'Default style updated' }); qc.invalidateQueries({ queryKey: ['layout-styles'] }); },
    onError: (e: any) => toast({ title: 'Error', description: e.message, variant: 'destructive' }),
  });

  const deleteStyle = useMutation({
    mutationFn: () => fetch(`${API}/api/learning/styles/${s.id}`, { method: 'DELETE', credentials: 'include' }),
    onSuccess: () => { toast({ title: 'Style deleted' }); qc.invalidateQueries({ queryKey: ['layout-styles'] }); },
    onError: (e: any) => toast({ title: 'Error', description: e.message, variant: 'destructive' }),
  });

  const saveEdit = async () => {
    setSaving(true);
    try {
      await apiFetch(`/api/learning/styles/${s.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, organisation: org, department: dept, language: lang }),
      });
      toast({ title: 'Style updated' });
      setEditing(false);
      qc.invalidateQueries({ queryKey: ['layout-styles'] });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className={`bg-card border-border transition-colors ${s.is_default ? 'border-cyan-500/50' : ''}`}>
      <CardContent className="pt-4 pb-4">
        {editing ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="col-span-2 space-y-1">
                <label className="text-[10px] text-muted-foreground">Profile name</label>
                <Input value={name} onChange={e => setName(e.target.value)} className="h-7 text-xs" />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground">Organisation</label>
                <Input value={org} onChange={e => setOrg(e.target.value)} placeholder="e.g. Rapiscan" className="h-7 text-xs" />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground">Department</label>
                <Input value={dept} onChange={e => setDept(e.target.value)} placeholder="e.g. Training" className="h-7 text-xs" />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground">Language</label>
                <Input value={lang} onChange={e => setLang(e.target.value)} placeholder="e.g. Arabic" className="h-7 text-xs" />
              </div>
            </div>
            <div className="flex gap-2">
              <Button size="sm" className="h-7 text-xs gap-1" onClick={saveEdit} disabled={saving}>
                {saving ? <RefreshCw className="h-3 w-3 animate-spin" /> : <CheckCheck className="h-3 w-3" />} Save
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              {/* Name + badges row */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <p className="font-medium text-sm truncate">{s.name || s.source_filename}</p>
                {s.is_default && <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/30 text-[10px] shrink-0">Default</Badge>}
                {s.organisation && <Badge className="bg-slate-500/10 text-slate-400 border-slate-500/20 text-[10px] shrink-0">{s.organisation}</Badge>}
                {s.department && <Badge className="bg-slate-500/10 text-slate-400 border-slate-500/20 text-[10px] shrink-0">{s.department}</Badge>}
              </div>
              <p className="text-[10px] text-muted-foreground/70 mt-0.5 truncate">{s.source_filename}</p>

              {/* Typography details */}
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-muted-foreground">
                {profile.title_font_name && <span>Title: <strong className="text-foreground">{profile.title_font_name} {profile.title_font_size}pt</strong></span>}
                {profile.body_font_name  && <span>Body: <strong className="text-foreground">{profile.body_font_name} {profile.body_font_size}pt</strong></span>}
                {profile.slide_width_in  && <span>Size: <strong className="text-foreground">{profile.slide_width_in}"×{profile.slide_height_in}"</strong></span>}
                {profile.slide_count     && <span>Slides: <strong className="text-foreground">{profile.slide_count}</strong></span>}
              </div>

              {/* Color swatches */}
              {colors.length > 0 && (
                <div className="flex gap-1 mt-2">
                  {colors.slice(0, 8).map((c: string, i: number) => (
                    <div key={i} className="h-5 w-5 rounded border border-border shrink-0"
                      style={{ backgroundColor: `#${c.length === 6 ? c : c}` }} title={`#${c}`} />
                  ))}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex flex-col gap-1.5 shrink-0">
              {!s.is_default && (
                <Button size="sm" variant="outline"
                  className="h-7 text-[10px] border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10"
                  onClick={() => setDefault.mutate()} disabled={setDefault.isPending}>
                  ★ Default
                </Button>
              )}
              <Button size="sm" variant="outline"
                className="h-7 text-[10px]"
                onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button size="sm" variant="ghost"
                className="h-7 text-[10px] text-red-400/70 hover:text-red-400 hover:bg-red-500/10"
                onClick={() => { if (confirm(`Delete "${s.name}"? This cannot be undone.`)) deleteStyle.mutate(); }}
                disabled={deleteStyle.isPending}>
                Delete
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function LayoutStylesTab() {
  const { data, isLoading, refetch } = useLayoutStyles();

  const styles = data?.styles ?? [];

  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold flex items-center gap-2">
        <Layers className="h-4 w-4 text-cyan-400" />
        Learned Layout Styles
        <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/30 text-[10px]">{styles.length}</Badge>
      </h2>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}

      {styles.length === 0 && !isLoading && (
        <Card className="bg-card border-border">
          <CardContent className="pt-8 pb-8 text-center text-muted-foreground">
            <Layers className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No layout styles learned yet</p>
            <p className="text-xs mt-1">Upload a PowerPoint file in the "Learn Style" tab to extract its visual profile</p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3">
        {styles.map((s: any) => (
          <StyleCard key={s.id} s={s} onRefetch={refetch} />
        ))}
      </div>
    </div>
  );
}

// ── Exam Patterns tab ─────────────────────────────────────────────────────────

const BLOOM_LEVELS = ['', 'remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'];
const DIFFICULTY_LEVELS = ['', 'easy', 'medium', 'hard'];

function ExamPatternsTab() {
  const [topic, setTopic] = useState('');
  const [bloom, setBloom] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const { data, isLoading } = useExamPatterns(topic, bloom, difficulty);
  const patterns = data?.patterns ?? [];

  const bloomColors: Record<string, string> = {
    remember: 'bg-blue-500/20 text-blue-300 border-blue-500/20',
    understand: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/20',
    apply: 'bg-green-500/20 text-green-300 border-green-500/20',
    analyze: 'bg-amber-500/20 text-amber-300 border-amber-500/20',
    evaluate: 'bg-orange-500/20 text-orange-300 border-orange-500/20',
    create: 'bg-purple-500/20 text-purple-300 border-purple-500/20',
  };

  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold flex items-center gap-2">
        <GraduationCap className="h-4 w-4 text-amber-400" />
        Exam Pattern Bank
        {data?.total != null && <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 text-[10px]">{data.total} patterns</Badge>}
      </h2>

      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-40">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input placeholder="Filter by topic…" value={topic} onChange={e => setTopic(e.target.value)} className="pl-8 h-8 text-sm bg-muted border-border" />
        </div>
        <select value={bloom} onChange={e => setBloom(e.target.value)} className="h-8 text-xs bg-muted border border-border rounded-md px-2 text-foreground">
          {BLOOM_LEVELS.map(l => <option key={l} value={l}>{l ? l.charAt(0).toUpperCase() + l.slice(1) : 'All Bloom levels'}</option>)}
        </select>
        <select value={difficulty} onChange={e => setDifficulty(e.target.value)} className="h-8 text-xs bg-muted border border-border rounded-md px-2 text-foreground">
          {DIFFICULTY_LEVELS.map(l => <option key={l} value={l}>{l ? l.charAt(0).toUpperCase() + l.slice(1) : 'All difficulties'}</option>)}
        </select>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}

      {patterns.length === 0 && !isLoading && (
        <Card className="bg-card border-border">
          <CardContent className="pt-8 pb-8 text-center text-muted-foreground">
            <GraduationCap className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No exam patterns yet</p>
            <p className="text-xs mt-1">Patterns are extracted from training materials automatically</p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {patterns.map((p: any) => (
          <Card key={p.id} className="bg-card border-border">
            <CardContent className="pt-3 pb-3">
              <div className="flex items-center gap-2 mb-2">
                <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${bloomColors[p.bloom_level] ?? 'bg-muted text-muted-foreground'}`}>
                  {p.bloom_level}
                </span>
                {p.difficulty && (
                  <span className="text-[10px] text-muted-foreground font-mono">{p.difficulty}</span>
                )}
                {p.source_doc_type && (
                  <span className="text-[10px] text-muted-foreground">{p.source_doc_type}</span>
                )}
              </div>
              <p className="text-sm font-medium text-foreground">{p.question_text}</p>
              {p.answer_text && (
                <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{p.answer_text}</p>
              )}
              {p.distractors?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {p.distractors.slice(0, 3).map((d: string, i: number) => (
                    <span key={i} className="px-2 py-0.5 bg-muted text-muted-foreground rounded text-[10px]">{d}</span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ── Learning Report tab ────────────────────────────────────────────────────────

function LearningReportTab() {
  const { data, isLoading, isFetching, refetch } = useLearningReport();

  const r = data;
  const kb = r?.knowledge_bank ?? {};
  const quality = r?.quality ?? {};
  const summary = r?.summary ?? {};

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-blue-400" />
          Learning Report
        </h2>
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}

      {r && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Total Docs',   value: summary.total_documents_studied ?? 0, color: 'text-blue-400' },
              { label: 'Approved',     value: summary.approved ?? 0,                color: 'text-green-400' },
              { label: 'Pending',      value: summary.awaiting_approval ?? 0,       color: 'text-amber-400' },
              { label: 'Rejected',     value: summary.rejected ?? 0, color: 'text-red-400' },
            ].map(s => (
              <div key={s.label} className="bg-muted/40 rounded-lg p-3 text-center">
                <div className={`text-2xl font-bold tabular-nums ${s.color}`}>{s.value}</div>
                <div className="text-[10px] text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </div>

          {Object.keys(quality).length > 0 && (
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2"><TrendingUp className="h-4 w-4 text-green-400" /> Quality Metrics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <ScoreBar label="Avg Overall Score" value={quality.avg_overall_score ?? 0} />
                <ScoreBar label="Avg Tech Quality"  value={quality.avg_technical_quality ?? 0} />
                <ScoreBar label="Safety Coverage"   value={quality.avg_safety_coverage ?? 0} />
                <div className="text-xs text-muted-foreground mt-2">
                  Confidence: <strong className="text-foreground">{Math.round((quality.avg_confidence_score ?? 0) * 100)}%</strong>
                </div>
              </CardContent>
            </Card>
          )}

          {Object.keys(kb).length > 0 && (
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2"><Database className="h-4 w-4 text-purple-400" /> Knowledge Bank</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs text-muted-foreground">
                  <span>Unique terms: <strong className="text-foreground">{kb.unique_terms ?? 0}</strong></span>
                  <span>Abbreviations: <strong className="text-foreground">{kb.unique_abbreviations ?? 0}</strong></span>
                  <span>Concepts: <strong className="text-foreground">{kb.total_concepts ?? 0}</strong></span>
                  <span>Procedures: <strong className="text-foreground">{kb.total_procedures ?? 0}</strong></span>
                  <span>Components: <strong className="text-foreground">{kb.total_components ?? 0}</strong></span>
                  <span>Safety warnings: <strong className="text-foreground">{kb.safety_warnings ?? 0}</strong></span>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PAGE SHELL
// ══════════════════════════════════════════════════════════════════════════════

const KB_TABS = [
  { id: 'integrated', label: 'Integrated',  icon: CheckCheck },
  { id: 'terminology', label: 'Terminology', icon: BookOpen },
  { id: 'styles',      label: 'Layouts',     icon: Layers },
  { id: 'exams',       label: 'Exam Bank',   icon: GraduationCap },
  { id: 'report',      label: 'Report',      icon: BarChart3 },
] as const;

type TabId = typeof KB_TABS[number]['id'];

export default function LearningHubPage() {
  const [activeTab, setActiveTab] = useState<TabId>('integrated');
  const { data: stats } = useLearningStats();
  const kbRef = useRef<HTMLDivElement>(null);

  // Auto-process any documents left in awaiting_approval from before the
  // trusted-owner workflow was enabled. Runs once on mount, silently.
  useEffect(() => {
    apiFetch('/api/study/jobs/process-pending', { method: 'POST' }).catch(() => {});
  }, []);

  const switchToTab = (tab: TabId) => {
    setActiveTab(tab);
    setTimeout(() => kbRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 py-6 space-y-8">

        {/* ── Hero ──────────────────────────────────────────────────────────── */}
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-blue-500/30">
              <Brain className="h-7 w-7 text-blue-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">AI Training Center</h1>
              <p className="text-sm text-muted-foreground">
                Teach the AI once — it remembers forever and applies knowledge to every future generation
              </p>
            </div>
          </div>
        </div>

        {/* ── Live stats strip ─────────────────────────────────────────────── */}
        <LiveStatsStrip />

        {/* ── Teach AI ─────────────────────────────────────────────────────── */}
        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-border" />
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Sparkles className="h-4 w-4 text-blue-400" />
              TEACH AI
            </div>
            <div className="flex-1 h-px bg-border" />
          </div>
          <TeachSection onLearnDone={() => switchToTab('integrated')} />
        </section>

        {/* ── Active jobs ───────────────────────────────────────────────────── */}
        <ActiveJobsFeed onSwitchTab={switchToTab} />

        {/* ── Knowledge Base ────────────────────────────────────────────────── */}
        <section ref={kbRef} className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-border" />
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Database className="h-4 w-4 text-purple-400" />
              KNOWLEDGE BASE
            </div>
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Tab bar */}
          <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
            {KB_TABS.map(tab => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors relative ${
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          {activeTab === 'integrated'  && <IntegratedTab />}
          {activeTab === 'terminology' && <TerminologyTab />}
          {activeTab === 'styles'      && <LayoutStylesTab />}
          {activeTab === 'exams'       && <ExamPatternsTab />}
          {activeTab === 'report'      && <LearningReportTab />}
        </section>
      </div>
    </div>
  );
}
