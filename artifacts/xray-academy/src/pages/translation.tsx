import { useState, useRef, useCallback, useEffect } from 'react';
import { Link, useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Languages, Upload, Check, Loader2, AlertCircle, FileText,
  ChevronRight, ChevronLeft, Download, BookOpen, Database, ArrowLeftRight,
  Star, AlertTriangle, Edit3, RotateCcw, Copy, Trash2, ChevronDown,
  Plus, Search, Tag, Clock, CheckCircle2, XCircle, ScanLine,
  Image as ImageIcon, Package, BarChart2, ExternalLink, Layers,
  FileImage, FileSpreadsheet, Presentation, Shield, Cpu,
  Wrench, BookMarked, FileCheck, Settings2, Users, Zap, Globe, Bot,
  Lock, WifiOff, ChevronUp, RefreshCw, Activity, TrendingUp,
  FlaskConical, ShieldCheck, Sparkles, Eye,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { SOURCE_LANGUAGES as SOURCE_LANG_OPTIONS, TARGET_LANGUAGES as TARGET_LANG_OPTIONS } from '@/lib/languages';
import { AuthQuotaBar } from '@/components/auth-quota-bar';
import { InstallButton } from '@/components/install-button';
import { PUBLIC_MODE } from '@/lib/config';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── Types ─────────────────────────────────────────────────────────────────────

interface StepStatus {
  step: number; name: string;
  status: 'pending' | 'running' | 'done' | 'error'; data?: any;
}

interface Segment {
  id: string; source: string; target: string; seg_type: string;
  memory_match: boolean; team_match?: boolean; flagged: boolean; flag_reason: string; edited: boolean;
}

interface QualityIssue {
  seg_id: string; type: string; severity: 'error' | 'warning'; message: string;
}

interface QualityBreakdown {
  translation_quality?: number;
  engineering_quality?: number;
  consistency_score?: number;
  formatting_score?: number;
  dnt_score?: number;
  dnt_tokens_found?: string[];
  dnt_tokens_garbled?: string[];
  engineering_review_changes?: number;
  provider_used?: string;
}

interface Project {
  id: string; name: string; source_filename: string; source_file_type: string;
  source_lang: string; target_lang: string; style: string; status: string;
  quality_score: number | null; quality_breakdown?: QualityBreakdown;
  provider_name?: string;
  segment_count: number; version_num: number;
  tags: string[]; created_at: string; updated_at: string;
}

interface ProjectDetail extends Project {
  segments: Segment[];
  quality_issues: QualityIssue[];
  versions: { version_num: number; name: string; created_at: string; quality_score: number | null }[];
  keep_english_terms: boolean; transliterate_names: boolean;
  engineering_review_changes?: Array<{ seg_id: string; before: string; after: string; reason: string }>;
  dnt_tokens?: string[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

// Source/target language lists come from the shared registry
// (src/lib/languages.ts, mirroring backend/api/languages.py) — add a
// language there, not here, and both pickers below pick it up automatically.
// SOURCE_LANG_OPTIONS includes "Auto Detect"; TARGET_LANG_OPTIONS is the
// supported translation targets (Arabic, English, Russian, French, Spanish).
const LANGUAGES = SOURCE_LANG_OPTIONS;

const STYLES = [
  { value: 'technical', label: 'Technical',  desc: 'ISO/IEC engineering terminology, preserves model numbers & codes' },
  { value: 'formal',    label: 'Formal',     desc: 'Standard formal register, professional terminology' },
  { value: 'bilingual', label: 'Bilingual',  desc: 'Translation + English original in parentheses' },
];

const DOC_TYPES = [
  { ext: 'pdf',  label: 'PDF',        icon: FileText,        color: 'text-red-400',    bg: 'bg-red-500/10' },
  { ext: 'docx', label: 'Word',       icon: FileText,        color: 'text-blue-400',   bg: 'bg-blue-500/10' },
  { ext: 'pptx', label: 'PowerPoint', icon: FileImage,       color: 'text-orange-400', bg: 'bg-orange-500/10' },
  { ext: 'xlsx', label: 'Excel',      icon: FileSpreadsheet, color: 'text-green-400',  bg: 'bg-green-500/10' },
  { ext: 'txt',  label: 'Text',       icon: FileText,        color: 'text-slate-400',  bg: 'bg-slate-500/10' },
  { ext: 'html', label: 'HTML',       icon: FileText,        color: 'text-sky-400',    bg: 'bg-sky-500/10' },
];

const ACCEPTED = '.pdf,.docx,.pptx,.xlsx,.txt,.md,.html,.csv,.rtf,.xml';

const PIPELINE_STEPS = [
  'Extracting',
  'OCR',
  'Translating',
  'Formatting',
  'Quality Check',
  'Rebuilding',
  'Completed',
];

// Must match the backend MAX_FILE_SIZE_MB (Render env) — the server rejects
// anything larger, so the UI advertises and pre-checks the same 25 MB cap.
const MAX_UPLOAD_MB = 25;

const PROVIDERS = [
  {
    id: 'auto',
    label: 'Auto',
    icon: Zap,
    description: 'Uses the best available provider (DeepL → Azure → Google → OpenAI)',
    badge: 'Smart',
    badgeColor: 'text-primary bg-primary/10 border-primary/20',
    iconColor: 'text-primary',
  },
  {
    id: 'openai',
    label: 'OpenAI GPT-4o',
    icon: Bot,
    description: 'AI-powered with domain-specific engineering prompts. Always available.',
    badge: 'Default',
    badgeColor: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    iconColor: 'text-emerald-400',
  },
  {
    id: 'deepl',
    label: 'DeepL',
    icon: Globe,
    description: 'Industry-leading quality for European and Arabic documents.',
    badge: 'Best quality',
    badgeColor: 'text-sky-400 bg-sky-500/10 border-sky-500/20',
    iconColor: 'text-sky-400',
  },
  {
    id: 'azure',
    label: 'Azure AI',
    icon: Shield,
    description: 'Enterprise-grade Microsoft translation. Best for corporate environments.',
    badge: 'Enterprise',
    badgeColor: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    iconColor: 'text-blue-400',
  },
  {
    id: 'google',
    label: 'Google Cloud',
    icon: Globe,
    description: 'Fastest throughput for high-volume documents.',
    badge: 'Fastest',
    badgeColor: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    iconColor: 'text-amber-400',
  },
];

const STATUS_COLOR: Record<string, string> = {
  complete:    'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  ready:       'bg-sky-500/10 text-sky-400 border-sky-500/20',
  translating: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
  partial:     'bg-amber-500/10 text-amber-400 border-amber-500/20',
  error:       'bg-red-500/10 text-red-400 border-red-500/20',
};

const CAPABILITIES = [
  { icon: Shield,    text: 'Preserves model, part & error codes' },
  { icon: Cpu,       text: 'X-ray & security domain glossary' },
  { icon: BookMarked, text: 'Translation memory & reuse' },
  { icon: Wrench,    text: 'Field service & maintenance terms' },
  { icon: FileCheck, text: 'Quality validation report' },
  { icon: FileImage, text: 'Diagram & image label translation' },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function getDocType(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  return DOC_TYPES.find(d => d.ext === ext) ?? DOC_TYPES[0];
}

function langLabel(code: string) {
  return LANGUAGES.find(l => l.code === code) ?? { code, label: code.toUpperCase(), flag: '🌐' };
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function scoreColor(score: number | null) {
  if (score === null) return 'text-muted-foreground';
  if (score >= 90) return 'text-emerald-400';
  if (score >= 70) return 'text-amber-400';
  return 'text-red-400';
}

function scoreBg(score: number | null) {
  if (score === null) return 'bg-muted/30 border-border';
  if (score >= 90) return 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400';
  if (score >= 70) return 'bg-amber-500/10 border-amber-500/20 text-amber-400';
  return 'bg-red-500/10 border-red-500/20 text-red-400';
}

// ── Root component ────────────────────────────────────────────────────────────

type Screen = 'hub' | 'translating' | 'translating-multi' | 'resuming' | 'review' | 'provider-settings';

export default function TranslationPage() {
  const [screen, setScreen]           = useState<Screen>('hub');
  const [projects, setProjects]       = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [activeProject, setActiveProject]     = useState<ProjectDetail | null>(null);

  // Shared translation state (hub → translating → review)
  const [file, setFile]               = useState<File | null>(null);
  const [sourceLang, setSourceLang]   = useState('en');
  const [targetLang, setTargetLang]   = useState('ar');
  const [style, setStyle]             = useState('technical');
  const [projectName, setProjectName] = useState('');
  const [keepEnglish, setKeepEnglish] = useState(false);
  const [transliterate, setTransliterate] = useState(true);
  const [providerName, setProviderName] = useState('auto');
  const [aiEngine, setAiEngine] = useState('auto'); // AI engine for the translate/review pipeline: "auto" | "claude"
  // Layout Intelligence
  const [layoutMode, setLayoutMode]             = useState<'original' | 'saved' | 'reference'>('original');
  const [styleProfileId, setStyleProfileId]     = useState('');
  const [templateStrength, setTemplateStrength] = useState<'light' | 'balanced' | 'strong'>('balanced');
  const [layoutOptions, setLayoutOptions]       = useState<Record<string, boolean>>({});
  const [referenceTemplate, setReferenceTemplate] = useState<File | null>(null);
  // Translate to Multiple Languages: when on, targetLang is ignored in favor
  // of multiTargets — each selected language runs as an independent job.
  const [multiMode, setMultiMode]     = useState(false);
  const [multiTargets, setMultiTargets] = useState<string[]>([]);
  // For resume flow
  const [resumeProjectId, setResumeProjectId] = useState<string | null>(null);
  const [resumeProjectName, setResumeProjectName] = useState('');

  const { toast } = useToast();

  useEffect(() => {
    loadProjects();
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const r = await fetch(`${API}/api/translation/settings`, { credentials: 'include' });
      if (!r.ok) return;
      const s = await r.json();
      if (s?.source_lang) setSourceLang(s.source_lang);
      if (s?.target_lang) setTargetLang(s.target_lang);
      if (s?.style) setStyle(s.style);
      if (typeof s?.keep_english_terms === 'boolean') setKeepEnglish(s.keep_english_terms);
      if (typeof s?.transliterate_names === 'boolean') setTransliterate(s.transliterate_names);
      if (s?.provider_name) setProviderName(s.provider_name);
      if (s?.layout_mode) setLayoutMode(s.layout_mode);
      if (s?.style_profile_id !== undefined) setStyleProfileId(s.style_profile_id || '');
      if (s?.template_strength) setTemplateStrength(s.template_strength);
      if (s?.layout_options && typeof s.layout_options === 'object') setLayoutOptions(s.layout_options);
    } catch {}
  };

  const persistSettings = async () => {
    try {
      await fetch(`${API}/api/translation/settings`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_lang: sourceLang,
          target_lang: targetLang,
          style,
          keep_english_terms: keepEnglish,
          transliterate_names: transliterate,
          provider_name: providerName,
          layout_mode: layoutMode,
          style_profile_id: styleProfileId,
          template_strength: templateStrength,
          layout_options: layoutOptions,
          ocr_enabled: true,
          ocr_language: 'eng',
          ocr_force: false,
        }),
      });
    } catch {}
  };

  const loadProjects = async () => {
    try {
      setLoadingProjects(true);
      const r = await fetch(`${API}/api/translation/projects`, { credentials: 'include' });
      if (r.ok) setProjects(await r.json());
    } catch {}
    finally { setLoadingProjects(false); }
  };

  const openProject = async (id: string) => {
    try {
      const r = await fetch(`${API}/api/translation/projects/${id}`, { credentials: 'include' });
      if (!r.ok) throw new Error('Failed to load project');
      setActiveProject(await r.json());
      setScreen('review');
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const deleteProject = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    await fetch(`${API}/api/translation/projects/${id}`, { method: 'DELETE', credentials: 'include' });
    setProjects(p => p.filter(x => x.id !== id));
    toast({ title: 'Project deleted' });
  };

  const duplicateProject = async (id: string) => {
    const r = await fetch(`${API}/api/translation/projects/${id}/duplicate`, { method: 'POST', credentials: 'include' });
    if (r.ok) { await loadProjects(); toast({ title: 'Project duplicated' }); }
  };

  const resumeProject = (p: Project) => {
    setResumeProjectId(p.id);
    setResumeProjectName(p.name);
    setScreen('resuming');
  };

  // ── Screen router ──────────────────────────────────────────────────────────

  if (screen === 'provider-settings') {
    return (
      <ProviderSettingsScreen
        onBack={() => setScreen('hub')}
      />
    );
  }

  if (screen === 'translating') {
    return (
      <TranslatingScreen
        file={file!}
        sourceLang={sourceLang}
        targetLang={targetLang}
        style={style}
        projectName={projectName}
        keepEnglish={keepEnglish}
        transliterate={transliterate}
        providerName={providerName}
        aiEngine={aiEngine}
        layoutMode={layoutMode}
        styleProfileId={styleProfileId}
        templateStrength={templateStrength}
        layoutOptions={layoutOptions}
        referenceTemplate={referenceTemplate}
        onBack={() => setScreen('hub')}
        onComplete={async (id) => { await loadProjects(); await openProject(id); }}
      />
    );
  }

  if (screen === 'translating-multi') {
    return (
      <MultiTranslatingScreen
        file={file!}
        sourceLang={sourceLang}
        targetLangs={multiTargets}
        style={style}
        projectName={projectName}
        keepEnglish={keepEnglish}
        transliterate={transliterate}
        providerName={providerName}
        aiEngine={aiEngine}
        layoutMode={layoutMode}
        styleProfileId={styleProfileId}
        templateStrength={templateStrength}
        layoutOptions={layoutOptions}
        referenceTemplate={referenceTemplate}
        onBack={() => setScreen('hub')}
        onDone={async () => { await loadProjects(); setScreen('hub'); }}
        onOpenProject={async (id) => { await loadProjects(); await openProject(id); }}
      />
    );
  }

  if (screen === 'resuming' && resumeProjectId) {
    return (
      <ResumingScreen
        projectId={resumeProjectId}
        projectName={resumeProjectName}
        onBack={() => { setResumeProjectId(null); setScreen('hub'); }}
        onComplete={async (id) => { await loadProjects(); await openProject(id); }}
      />
    );
  }

  if (screen === 'review' && activeProject) {
    return (
      <ReviewScreen
        project={activeProject}
        onBack={() => { setScreen('hub'); setActiveProject(null); }}
        onRefresh={() => openProject(activeProject.id)}
      />
    );
  }

  return (
    <HubScreen
      file={file}
      setFile={setFile}
      sourceLang={sourceLang} setSourceLang={setSourceLang}
      targetLang={targetLang} setTargetLang={setTargetLang}
      style={style} setStyle={setStyle}
      projectName={projectName} setProjectName={setProjectName}
      keepEnglish={keepEnglish} setKeepEnglish={setKeepEnglish}
      transliterate={transliterate} setTransliterate={setTransliterate}
      providerName={providerName} setProviderName={setProviderName}
      aiEngine={aiEngine} setAiEngine={setAiEngine}
      layoutMode={layoutMode} setLayoutMode={setLayoutMode}
      styleProfileId={styleProfileId} setStyleProfileId={setStyleProfileId}
      templateStrength={templateStrength} setTemplateStrength={setTemplateStrength}
      layoutOptions={layoutOptions} setLayoutOptions={setLayoutOptions}
      referenceTemplate={referenceTemplate} setReferenceTemplate={setReferenceTemplate}
      multiMode={multiMode} setMultiMode={setMultiMode}
      multiTargets={multiTargets} setMultiTargets={setMultiTargets}
      projects={projects}
      loadingProjects={loadingProjects}
      onTranslate={async () => {
        await persistSettings();
        setScreen(multiMode && multiTargets.length > 0 ? 'translating-multi' : 'translating');
      }}
      onOpenProject={openProject}
      onDeleteProject={deleteProject}
      onDuplicateProject={duplicateProject}
      onResumeProject={resumeProject}
      onOpenProviderSettings={() => setScreen('provider-settings')}
    />
  );
}

// ── Admin: API usage & cost panel (renders only for ADMIN_USER_IDS) ──────────

function AdminUsagePanel() {
  const [data, setData] = useState<any>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    // 403 for non-admins → panel simply doesn't render
    fetch(`${API}/api/translation/admin/usage`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => setData(d))
      .catch(() => setData(null));
  }, []);

  if (!data) return null;
  const t = data.totals || {};
  const fmt = (v: any) => `${Number(v ?? 0).toFixed(2)}`;

  return (
    <div className="rounded-xl border border-border bg-card/40 p-4 space-y-3">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between text-left gap-2">
        <span className="text-sm font-semibold flex items-center gap-2">
          <BarChart2 className="h-4 w-4 text-primary" /> API Usage &amp; Cost (Admin)
        </span>
        <span className="text-xs text-muted-foreground font-mono flex items-center gap-1">
          Today {fmt(t.today?.est_cost_usd)} · Month {fmt(t.month?.est_cost_usd)} ·
          <span className={data.config?.translation_enabled ? 'text-emerald-400' : 'text-red-400'}>
            {data.config?.translation_enabled ? 'ENABLED' : 'DISABLED'}
          </span>
          · {data.active_jobs} active
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </span>
      </button>
      {open && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 text-xs">
            {(['today', 'month', 'all_time'] as const).map(k => (
              <div key={k} className="rounded-lg bg-muted/40 p-2">
                <p className="text-muted-foreground uppercase text-[10px]">{k.replace('_', ' ')}</p>
                <p className="font-mono font-bold">{fmt(t[k]?.est_cost_usd)}</p>
                <p className="text-muted-foreground">
                  {t[k]?.jobs ?? 0} jobs · {((t[k]?.input_tokens ?? 0) + (t[k]?.output_tokens ?? 0)).toLocaleString()} tokens
                </p>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-muted-foreground text-left">
                  <th className="py-1 pr-2">When</th><th className="pr-2">User</th><th className="pr-2">File</th>
                  <th className="pr-2">Type</th><th className="pr-2">Model</th><th className="pr-2">Provider</th>
                  <th className="pr-2">Tokens in/out</th><th className="pr-2">Est. cost</th>
                  <th className="pr-2">Duration</th><th className="pr-2">Status</th><th>Retries</th>
                </tr>
              </thead>
              <tbody>
                {(data.jobs || []).slice(0, 25).map((j: any) => (
                  <tr key={j.id} className="border-t border-border/50">
                    <td className="py-1 pr-2 font-mono whitespace-nowrap">{j.created_at ? new Date(j.created_at).toLocaleString() : '—'}</td>
                    <td className="pr-2 font-mono">{(j.user_id || '—').slice(0, 8)}</td>
                    <td className="pr-2 max-w-[160px] truncate">{j.project_name || '—'}</td>
                    <td className="pr-2 uppercase">{j.file_type || '—'}</td>
                    <td className="pr-2 font-mono">{j.model || '—'}</td>
                    <td className="pr-2 max-w-[120px] truncate">{j.provider || '—'}</td>
                    <td className="pr-2 font-mono">{(j.input_tokens ?? 0).toLocaleString()}/{(j.output_tokens ?? 0).toLocaleString()}</td>
                    <td className="pr-2 font-mono">{fmt(j.est_cost_usd)}</td>
                    <td className="pr-2 font-mono">{Math.round(j.duration_secs ?? 0)}s</td>
                    <td className={`pr-2 ${j.status === 'complete' ? 'text-emerald-400' : 'text-red-400'}`}>{j.status || '—'}</td>
                    <td className="font-mono">{j.retries ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Costs are estimates based on published OpenAI token prices — check the OpenAI dashboard for billed amounts.
            Kill switch: set TRANSLATION_ENABLED=false to stop all new translation jobs instantly.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Hub Screen ────────────────────────────────────────────────────────────────

function HubScreen({
  file, setFile,
  sourceLang, setSourceLang,
  targetLang, setTargetLang,
  style, setStyle,
  projectName, setProjectName,
  keepEnglish, setKeepEnglish,
  transliterate, setTransliterate,
  providerName, setProviderName,
  aiEngine, setAiEngine,
  layoutMode, setLayoutMode,
  styleProfileId, setStyleProfileId,
  templateStrength, setTemplateStrength,
  referenceTemplate, setReferenceTemplate,
  multiMode, setMultiMode, multiTargets, setMultiTargets,
  projects, loadingProjects,
  onTranslate, onOpenProject, onDeleteProject, onDuplicateProject, onResumeProject,
  onOpenProviderSettings,
}: {
  file: File | null; setFile: (f: File | null) => void;
  sourceLang: string; setSourceLang: (s: string) => void;
  targetLang: string; setTargetLang: (s: string) => void;
  style: string; setStyle: (s: string) => void;
  projectName: string; setProjectName: (s: string) => void;
  keepEnglish: boolean; setKeepEnglish: (b: boolean) => void;
  transliterate: boolean; setTransliterate: (b: boolean) => void;
  providerName: string; setProviderName: (s: string) => void;
  aiEngine: string; setAiEngine: (s: string) => void;
  layoutMode: 'original' | 'saved' | 'reference'; setLayoutMode: (m: 'original' | 'saved' | 'reference') => void;
  styleProfileId: string; setStyleProfileId: (id: string) => void;
  templateStrength: 'light' | 'balanced' | 'strong'; setTemplateStrength: (s: 'light' | 'balanced' | 'strong') => void;
  referenceTemplate: File | null; setReferenceTemplate: (f: File | null) => void;
  multiMode: boolean; setMultiMode: (b: boolean) => void;
  multiTargets: string[]; setMultiTargets: (fn: string[] | ((prev: string[]) => string[])) => void;
  projects: Project[]; loadingProjects: boolean;
  onTranslate: () => void;
  onOpenProject: (id: string) => void;
  onDeleteProject: (id: string, name: string) => void;
  onDuplicateProject: (id: string) => void;
  onResumeProject: (p: Project) => void;
  onOpenProviderSettings: () => void;
}) {
  const [dragOver, setDragOver]         = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSrcPicker, setShowSrcPicker] = useState(false);
  const [showTgtPicker, setShowTgtPicker] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const refTemplateRef = useRef<HTMLInputElement>(null);

  // Fetch saved layout style profiles for the dropdown
  const [layoutStyles, setLayoutStyles] = useState<any[]>([]);
  useEffect(() => {
    fetch(`${API}/api/learning/styles`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(d => d?.styles && setLayoutStyles(d.styles))
      .catch(() => {});
  }, []);

  const [fileError, setFileError] = useState<string | null>(null);

  const handleFile = (f: File) => {
    setFileError(null);
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setFileError(
        `File too large — ${(f.size / (1024 * 1024)).toFixed(0)} MB exceeds the ${MAX_UPLOAD_MB} MB limit.`
      );
      return;
    }
    setFile(f);
    const name = f.name.replace(/\.[^.]+$/, '').replace(/[_\-]/g, ' ');
    setProjectName(name);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const swapLangs = () => {
    // Target only accepts ar/ru/fr/es — skip the swap if the current source
    // (which would become the new target) isn't one of those.
    if (!TARGET_LANG_OPTIONS.some(l => l.code === sourceLang)) return;
    const tmp = sourceLang;
    setSourceLang(targetLang);
    setTargetLang(tmp);
  };

  const src = langLabel(sourceLang);
  const tgt = langLabel(targetLang);
  const docType = file ? getDocType(file.name) : null;
  const DocIcon = docType?.icon ?? FileText;

  return (
    <div className="flex flex-col h-full overflow-auto bg-background">
      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border bg-card/40 px-6 py-3">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/20">
              <Languages className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-foreground leading-tight">Smart Translation AI</h1>
              <p className="text-[10px] text-muted-foreground leading-tight">Technical &amp; Engineering Document Translation</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <InstallButton />
            {!PUBLIC_MODE && (
              <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8" onClick={onOpenProviderSettings}>
                <Zap className="h-3.5 w-3.5" /> Providers
              </Button>
            )}
            {!PUBLIC_MODE && (
              <Link href="/translation-dictionary">
                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8">
                  <Database className="h-3.5 w-3.5" /> Glossary
                </Button>
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">

          {/* Hero / value proposition — real crawlable H1 for SEO + a clear
              pitch for visitors. Shown to everyone so search engines index it. */}
          <div className="text-center space-y-3 pt-1">
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">
              Accurate technical &amp; engineering document translation
            </h1>
            <p className="text-base text-muted-foreground max-w-2xl mx-auto">
              Precise engineering and technical terminology (ISO / IEC / IEEE) that
              generic translators like Google Translate get wrong — your PDF, Word,
              PowerPoint or Excel translated with the original layout, images and
              formatting kept intact.
              <span className="block mt-1 text-foreground/80 font-medium">
                Arabic · English · French · Russian · Spanish
              </span>
            </p>
          </div>

          {/* Free-tier allowance + Google sign-in (only when auth is enabled). */}
          <AuthQuotaBar />

          {/* ── Upload zone ─────────────────────────────────────────────────── */}
          <div className="space-y-4">
            {/* Drop area */}
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => !file && fileRef.current?.click()}
              className={`relative rounded-2xl border-2 transition-all duration-200 overflow-hidden
                ${file
                  ? 'border-emerald-500/40 bg-emerald-500/5 cursor-default'
                  : dragOver
                  ? 'border-primary bg-primary/8 cursor-copy scale-[1.01]'
                  : 'border-dashed border-border hover:border-primary/50 hover:bg-primary/3 cursor-pointer'
                }`}
            >
              <input
                ref={fileRef} type="file" accept={ACCEPTED} className="hidden"
                onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
              />

              {file ? (
                /* ── File selected state ──────────────────────────────────── */
                <div className="flex items-center gap-5 px-8 py-6">
                  <div className={`h-14 w-14 rounded-xl flex items-center justify-center shrink-0 ring-1 ${docType?.bg} ring-white/10`}>
                    <DocIcon className={`h-7 w-7 ${docType?.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-foreground truncate text-base">{file.name}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs text-muted-foreground">
                        {file.size >= 1024 * 1024
                          ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
                          : `${(file.size / 1024).toFixed(0)} KB`}
                      </span>
                      <span className={`text-xs font-semibold px-1.5 py-0.5 rounded uppercase ${docType?.bg} ${docType?.color}`}>
                        {docType?.label}
                      </span>
                      <span className="text-xs text-emerald-400 flex items-center gap-1">
                        <Check className="h-3 w-3" /> Ready
                      </span>
                    </div>
                  </div>
                  <Button
                    size="sm" variant="ghost"
                    className="shrink-0 text-muted-foreground hover:text-foreground"
                    onClick={e => { e.stopPropagation(); setFile(null); setProjectName(''); }}
                  >
                    Change
                  </Button>
                </div>
              ) : (
                /* ── Empty drop state ─────────────────────────────────────── */
                <div className="flex flex-col items-center py-14 px-6 gap-4 text-center">
                  <div className={`h-16 w-16 rounded-2xl flex items-center justify-center ring-1
                    ${dragOver ? 'bg-primary/20 ring-primary/40' : 'bg-primary/10 ring-primary/20'}`}>
                    <Upload className={`h-8 w-8 ${dragOver ? 'text-primary' : 'text-primary/70'}`} />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-foreground">
                      {dragOver ? 'Release to upload' : 'Drop your document here'}
                    </p>
                    <p className="text-sm text-muted-foreground mt-1">or click to browse</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5 justify-center">
                    {['PDF', 'DOCX', 'PPTX', 'XLSX', 'TXT', 'HTML', 'CSV', 'XML'].map(f => (
                      <span key={f} className="px-2 py-0.5 rounded text-[11px] font-mono bg-muted/40 text-muted-foreground border border-border/50">
                        {f}
                      </span>
                    ))}
                  </div>
                  <p className="text-[11px] text-muted-foreground/60">Max {MAX_UPLOAD_MB} MB</p>
                </div>
              )}
            </div>

            {/* File size error */}
            {fileError && (
              <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-400">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {fileError}
              </div>
            )}

            {/* ── Language pair row ──────────────────────────────────────────── */}
            <div className="flex items-center gap-3">
              {/* Source language picker */}
              <div className="relative flex-1">
                <button
                  onClick={() => { setShowSrcPicker(!showSrcPicker); setShowTgtPicker(false); }}
                  className="w-full flex items-center gap-2.5 px-4 py-3 rounded-xl border border-border bg-card/60 hover:border-primary/40 hover:bg-card/80 transition-all"
                >
                  <span className="text-xl">{src.flag}</span>
                  <div className="flex-1 text-left">
                    <p className="text-xs text-muted-foreground leading-none mb-0.5">Translate from</p>
                    <p className="text-sm font-semibold text-foreground">{src.label}</p>
                  </div>
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                </button>
                {showSrcPicker && (
                  <div className="absolute top-full mt-1 left-0 right-0 z-50 rounded-xl border border-border bg-popover shadow-xl overflow-hidden">
                    {LANGUAGES.map(l => (
                      <button key={l.code} onClick={() => { setSourceLang(l.code); setShowSrcPicker(false); }}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-accent transition-colors
                          ${sourceLang === l.code ? 'bg-primary/10 text-primary font-semibold' : 'text-foreground'}`}>
                        <span className="text-lg">{l.flag}</span> {l.label}
                        {sourceLang === l.code && <Check className="h-3.5 w-3.5 ml-auto" />}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Swap button */}
              <button
                onClick={swapLangs}
                className="shrink-0 h-11 w-11 rounded-xl border border-border bg-card/60 hover:border-primary/40 hover:bg-primary/10 transition-all flex items-center justify-center group"
                title="Swap languages"
              >
                <ArrowLeftRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
              </button>

              {/* Target language picker */}
              <div className="relative flex-1">
                <button
                  onClick={() => { setShowTgtPicker(!showTgtPicker); setShowSrcPicker(false); }}
                  className="w-full flex items-center gap-2.5 px-4 py-3 rounded-xl border border-primary/30 bg-primary/5 hover:border-primary/50 hover:bg-primary/8 transition-all"
                >
                  <span className="text-xl">{tgt.flag}</span>
                  <div className="flex-1 text-left">
                    <p className="text-xs text-primary/60 leading-none mb-0.5">Translate to</p>
                    <p className="text-sm font-semibold text-foreground">{tgt.label}</p>
                  </div>
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                </button>
                {showTgtPicker && (
                  <div className="absolute top-full mt-1 left-0 right-0 z-50 rounded-xl border border-border bg-popover shadow-xl overflow-hidden">
                    {TARGET_LANG_OPTIONS.map(l => (
                      <button key={l.code} onClick={() => { setTargetLang(l.code); setShowTgtPicker(false); }}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-accent transition-colors
                          ${targetLang === l.code ? 'bg-primary/10 text-primary font-semibold' : 'text-foreground'}`}>
                        <span className="text-lg">{l.flag}</span> {l.label}
                        {targetLang === l.code && <Check className="h-3.5 w-3.5 ml-auto" />}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* "Translate to Multiple Languages" was removed — redundant with the
                "Translate to" language picker above. Single-target flow only
                (multiMode stays false). */}

            {/* Public mode: all technical controls below (style, provider, AI
                engine, PPTX layout, advanced options) are hidden — public users
                only upload a file and pick the target language. */}
            {!PUBLIC_MODE && (<>
            {/* ── Translation style ──────────────────────────────────────────── */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-muted-foreground font-mono uppercase tracking-wider shrink-0">Style:</span>
              {STYLES.map(s => (
                <button key={s.value} onClick={() => setStyle(s.value)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all
                    ${style === s.value
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'}`}>
                  {s.label}
                </button>
              ))}
              <span className="text-xs text-muted-foreground/60 ml-1">
                {STYLES.find(s => s.value === style)?.desc}
              </span>
            </div>

            {/* ── Provider selector ──────────────────────────────────────────── */}
            <div className="rounded-xl border border-border/60 overflow-hidden">
              <div className="px-4 py-2.5 flex items-center gap-2 bg-card/30">
                <Zap className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Translation Provider</span>
                <button
                  onClick={onOpenProviderSettings}
                  className="ml-auto text-[10px] text-primary hover:underline flex items-center gap-1"
                >
                  <Settings2 className="h-3 w-3" /> Configure API Keys
                </button>
              </div>
              <div className="px-4 pb-3 pt-1 flex flex-wrap gap-2">
                {PROVIDERS.map(prov => {
                  const PIcon = prov.icon;
                  const isSelected = providerName === prov.id;
                  return (
                    <button
                      key={prov.id}
                      onClick={() => setProviderName(prov.id)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium transition-all
                        ${isSelected
                          ? 'border-primary/50 bg-primary/8 text-foreground'
                          : 'border-border/50 text-muted-foreground hover:border-primary/30 hover:text-foreground hover:bg-accent/30'}`}
                      title={prov.description}
                    >
                      <PIcon className={`h-3.5 w-3.5 shrink-0 ${isSelected ? prov.iconColor : ''}`} />
                      {prov.label}
                      {isSelected && (
                        <span className={`ml-1 text-[9px] px-1.5 py-0.5 rounded border font-semibold ${prov.badgeColor}`}>
                          {prov.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
              <div className="px-4 pb-3 text-[10px] text-muted-foreground/60">
                {PROVIDERS.find(p => p.id === providerName)?.description}
                {' '}
                <span className="text-primary/60">
                  {providerName !== 'openai' && providerName !== 'auto' && '· Requires API key in Provider Settings'}
                </span>
              </div>
            </div>

            {/* ── AI Engine selector (Gemini vs Claude for translate + review) ── */}
            <div className="rounded-xl border border-border/60 overflow-hidden">
              <div className="px-4 py-2.5 flex items-center gap-2 bg-card/30">
                <Zap className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">AI Engine</span>
              </div>
              <div className="px-4 pb-3 pt-1 flex flex-wrap gap-2">
                {[
                  { id: 'auto', label: 'Auto (Gemini)' },
                  { id: 'claude', label: 'Claude' },
                ].map(eng => {
                  const isSelected = aiEngine === eng.id;
                  return (
                    <button
                      key={eng.id}
                      onClick={() => setAiEngine(eng.id)}
                      data-testid={`button-ai-engine-${eng.id}`}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium transition-all
                        ${isSelected
                          ? 'border-primary/50 bg-primary/8 text-foreground'
                          : 'border-border/50 text-muted-foreground hover:border-primary/30 hover:text-foreground hover:bg-accent/30'}`}
                    >
                      {eng.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* ── Layout Style (PPTX only) ──────────────────────────────────── */}
            {file && file.name.toLowerCase().endsWith('.pptx') && (
              <div className="rounded-xl border border-border/60 overflow-hidden">
                <div className="px-4 py-2.5 flex items-center gap-2 bg-card/30">
                  <Layers className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Layout Style</span>
                  {layoutMode !== 'original' && (
                    <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20">
                      {layoutMode === 'saved' ? 'Profile active' : 'Template active'}
                    </span>
                  )}
                </div>
                <div className="px-4 pb-4 pt-2 space-y-3">
                  {/* Mode selector */}
                  <div className="grid grid-cols-1 gap-1.5">
                    {([
                      { mode: 'original' as const, label: 'Preserve Original Layout', desc: 'Keep fonts, colours, and positions exactly as in the source', icon: Shield },
                      { mode: 'saved' as const,    label: 'Apply Saved Style Profile', desc: 'Use a profile learned from a reference deck', icon: Layers },
                      { mode: 'reference' as const, label: 'Upload Reference Template', desc: 'Upload a PPTX to use as style reference for this job only', icon: Upload },
                    ] as const).map(opt => {
                      const Icon = opt.icon;
                      const active = layoutMode === opt.mode;
                      return (
                        <button key={opt.mode} type="button"
                          onClick={() => setLayoutMode(opt.mode)}
                          className={`w-full flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-all
                            ${active ? 'border-violet-500/40 bg-violet-500/8' : 'border-border/50 hover:border-primary/30'}`}
                        >
                          <div className={`h-4 w-4 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5
                            ${active ? 'border-violet-500' : 'border-muted-foreground/40'}`}>
                            {active && <div className="h-1.5 w-1.5 rounded-full bg-violet-500" />}
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <Icon className="h-3 w-3 text-muted-foreground" />
                              <span className="text-xs font-semibold text-foreground">{opt.label}</span>
                            </div>
                            <p className="text-[10px] text-muted-foreground mt-0.5">{opt.desc}</p>
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  {/* Saved profile dropdown */}
                  {layoutMode === 'saved' && (
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">Select style profile</label>
                      {layoutStyles.length === 0 ? (
                        <p className="text-xs text-amber-400/80 flex items-center gap-1.5">
                          <AlertCircle className="h-3.5 w-3.5" />
                          No saved profiles — upload a PPTX in Learning Hub → Learn Style first.
                        </p>
                      ) : (
                        <select
                          value={styleProfileId}
                          onChange={e => setStyleProfileId(e.target.value)}
                          className="w-full h-9 rounded-lg border border-border bg-card/60 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
                        >
                          <option value="">— Choose a profile —</option>
                          {layoutStyles.map((s: any) => (
                            <option key={s.id} value={s.id}>
                              {s.name || s.source_filename}
                              {s.is_default ? ' (Default)' : ''}
                              {s.organisation ? ` · ${s.organisation}` : ''}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}

                  {/* Reference template upload */}
                  {layoutMode === 'reference' && (
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">Reference template (.pptx, max 50 MB)</label>
                      {referenceTemplate ? (
                        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs">
                          <Presentation className="h-4 w-4 text-emerald-400 shrink-0" />
                          <span className="flex-1 truncate text-foreground">{referenceTemplate.name}</span>
                          <button onClick={() => setReferenceTemplate(null)} className="text-muted-foreground hover:text-foreground">
                            <XCircle className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => refTemplateRef.current?.click()}
                          className="w-full flex items-center gap-2 rounded-lg border border-dashed border-border/60 px-3 py-2 text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground transition-all"
                        >
                          <Upload className="h-3.5 w-3.5" /> Click to upload reference .pptx
                        </button>
                      )}
                      <input
                        ref={refTemplateRef} type="file" accept=".pptx" className="hidden"
                        onChange={e => e.target.files?.[0] && setReferenceTemplate(e.target.files[0])}
                      />
                    </div>
                  )}

                  {/* Template strength */}
                  {layoutMode !== 'original' && (
                    <div className="space-y-1.5">
                      <label className="text-xs text-muted-foreground">Template strength</label>
                      <div className="flex gap-2">
                        {([
                          { val: 'light'    as const, label: 'Light',    desc: 'Fonts & colours only' },
                          { val: 'balanced' as const, label: 'Balanced', desc: 'Fonts, colours & RTL layout' },
                          { val: 'strong'   as const, label: 'Strong',   desc: 'Full layout match' },
                        ]).map(s => (
                          <button key={s.val} type="button"
                            onClick={() => setTemplateStrength(s.val)}
                            title={s.desc}
                            className={`flex-1 py-1.5 rounded-lg border text-xs font-semibold transition-all
                              ${templateStrength === s.val
                                ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                                : 'border-border/50 text-muted-foreground hover:border-primary/30'}`}
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        {templateStrength === 'light'    && 'Only fonts and theme colours from the profile will be applied.'}
                        {templateStrength === 'balanced' && `Fonts, colours, and layout mirroring will be applied${tgt.code === 'ar' ? ' (RTL for Arabic)' : ''}.`}
                        {templateStrength === 'strong'   && 'Full layout matching including placeholder geometry.'}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Advanced options ───────────────────────────────────────────── */}
            <div className="rounded-xl border border-border/50 overflow-hidden">
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent/30 transition-colors"
              >
                <Settings2 className="h-3.5 w-3.5" />
                Advanced options
                <ChevronDown className={`h-3.5 w-3.5 ml-auto transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              </button>
              {showAdvanced && (
                <div className="border-t border-border/50 px-4 py-4 space-y-4 bg-card/20">
                  {/* Project name */}
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Project name</label>
                    <Input
                      value={projectName}
                      onChange={e => setProjectName(e.target.value)}
                      placeholder="Auto-set from filename"
                      className="h-8 text-sm"
                    />
                  </div>
                  {/* Options */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {[
                      { key: 'keep', label: 'Keep English technical terms', desc: 'Acronyms & component names stay in English', val: keepEnglish, set: setKeepEnglish },
                      { key: 'trans', label: 'Transliterate product names', desc: `Brand & model names in ${tgt.label} script`, val: transliterate, set: setTransliterate },
                    ].map(opt => (
                      <button key={opt.key} type="button" onClick={() => opt.set(!opt.val)}
                        className={`rounded-lg border p-3 text-left transition-all
                          ${opt.val ? 'border-primary/40 bg-primary/8' : 'border-border/50 hover:border-primary/30'}`}>
                        <div className="flex items-center gap-2">
                          <div className={`h-4 w-4 rounded border flex items-center justify-center shrink-0
                            ${opt.val ? 'bg-primary border-primary' : 'border-muted-foreground/40'}`}>
                            {opt.val && <Check className="h-2.5 w-2.5 text-primary-foreground" />}
                          </div>
                          <span className="text-xs font-medium text-foreground">{opt.label}</span>
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-1 ml-6">{opt.desc}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            </>)}

            {/* ── Translate CTA ─────────────────────────────────────────────── */}
            <Button
              size="lg"
              className="w-full h-12 text-base font-semibold gap-3"
              disabled={!file || (multiMode && multiTargets.length === 0)}
              onClick={onTranslate}
            >
              <Languages className="h-5 w-5" />
              {!file
                ? 'Select a document to translate'
                : multiMode
                ? `Translate "${file.name.replace(/\.[^.]+$/, '')}" to ${multiTargets.length} language${multiTargets.length === 1 ? '' : 's'}`
                : `Translate "${file.name.replace(/\.[^.]+$/, '')}"`}
              {file && <ChevronLeft className="h-4 w-4 rotate-180 ml-auto" />}
            </Button>

            {/* ── Capabilities strip (hidden in public mode) ──────────────────── */}
            {!PUBLIC_MODE && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {CAPABILITIES.map(c => (
                <div key={c.text} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-card/30 border border-border/40">
                  <c.icon className="h-3.5 w-3.5 text-primary/60 shrink-0" />
                  <span className="text-[11px] text-muted-foreground">{c.text}</span>
                </div>
              ))}
            </div>
            )}
          </div>

          {/* ── Admin-only API usage & cost dashboard ────────────────────────── */}
          <AdminUsagePanel />

          {/* ── Recent projects ──────────────────────────────────────────────── */}
          {/* Hidden in public mode: with shared/anonymous sessions this list could
              expose one user's files to another. Public users download their result
              from the review screen right after translating. */}
          {!PUBLIC_MODE && !loadingProjects && projects.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-mono font-bold text-muted-foreground/60 uppercase tracking-widest">
                  Recent Projects
                </h2>
                <span className="text-xs text-muted-foreground">{projects.length} project{projects.length !== 1 ? 's' : ''}</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                {projects.map(p => {
                  const dt = getDocType(p.source_filename);
                  const DIcon = dt.icon;
                  const srcL = langLabel(p.source_lang);
                  const tgtL = langLabel(p.target_lang);
                  return (
                    <div key={p.id}
                      className="group rounded-xl border border-border bg-card/50 hover:border-primary/30 hover:bg-card/70 transition-all overflow-hidden flex flex-col">
                      {/* Card header */}
                      <div className="px-4 pt-4 pb-3 flex items-start gap-3">
                        <div className={`h-10 w-10 rounded-lg flex items-center justify-center shrink-0 ring-1 ${dt.bg} ring-white/10`}>
                          <DIcon className={`h-5 w-5 ${dt.color}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${STATUS_COLOR[p.status] ?? STATUS_COLOR.ready}`}>
                              {p.status.toUpperCase()}
                            </span>
                            {p.quality_score !== null && (
                              <span className={`text-[10px] font-bold ${scoreColor(p.quality_score)}`}>
                                {p.quality_score}/100
                              </span>
                            )}
                          </div>
                          <h3 className="text-sm font-semibold text-foreground truncate">{p.name}</h3>
                          <p className="text-[11px] text-muted-foreground truncate">{p.source_filename}</p>
                        </div>
                      </div>

                      {/* Card meta */}
                      <div className="px-4 pb-3 flex items-center gap-3 text-[11px] text-muted-foreground">
                        <span>{srcL.flag} {srcL.label} → {tgtL.flag} {tgtL.label}</span>
                        <span className="ml-auto">{fmtDate(p.updated_at)}</span>
                      </div>

                      {/* Card actions */}
                      <div className="px-3 pb-3 flex items-center gap-1.5 mt-auto border-t border-border/40 pt-3">
                        {p.status === 'partial' ? (
                          <>
                            <Button
                              size="sm"
                              className="flex-1 h-7 text-xs gap-1.5 bg-amber-500 hover:bg-amber-600 text-white border-0"
                              onClick={() => onResumeProject(p)}
                            >
                              <RotateCcw className="h-3 w-3" /> Resume
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 text-xs gap-1.5"
                              onClick={() => onOpenProject(p.id)}
                              title="View partial segments"
                            >
                              <BookOpen className="h-3 w-3" />
                            </Button>
                          </>
                        ) : (
                          <Button
                            size="sm"
                            className="flex-1 h-7 text-xs gap-1.5"
                            onClick={() => onOpenProject(p.id)}
                          >
                            <BookOpen className="h-3 w-3" /> Open
                          </Button>
                        )}
                        {p.status === 'complete' && (
                          <a href={`${API}/api/translation/projects/${p.id}/export/${p.source_file_type === 'pptx' ? 'pptx' : p.source_file_type === 'xlsx' ? 'xlsx' : 'docx'}`} download
                             title={`Download ${(p.source_file_type === 'pptx' ? 'pptx' : p.source_file_type === 'xlsx' ? 'xlsx' : 'docx').toUpperCase()}`}>
                            <Button size="sm" variant="outline" className="h-7 w-7 p-0">
                              <Download className="h-3.5 w-3.5" />
                            </Button>
                          </a>
                        )}
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" title="Duplicate" onClick={() => onDuplicateProject(p.id)}>
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          title="Delete"
                          onClick={() => onDeleteProject(p.id, p.name)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {loadingProjects && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-primary/50" />
            </div>
          )}
        </div>
      </div>

      {/* Close dropdowns on outside click */}
      {(showSrcPicker || showTgtPicker) && (
        <div className="fixed inset-0 z-40" onClick={() => { setShowSrcPicker(false); setShowTgtPicker(false); }} />
      )}
    </div>
  );
}

// ── Verified Download Button ──────────────────────────────────────────────────
// Clicks the link only after confirming the server returns a non-error status.
// Shows a spinner while checking, surfaces HTTP errors if the file is missing.

function VerifiedDownloadButton({
  projectId, fmt, label,
}: { projectId: string; fmt: string; label: string }) {
  const [checking, setChecking] = useState(false);
  const [dlError, setDlError]   = useState<string | null>(null);
  const { toast } = useToast();

  const handleClick = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    setDlError(null);
    setChecking(true);
    try {
      // HEAD check — confirms file exists without downloading it twice
      const url = `/api/translation/projects/${projectId}/export/${fmt}`;
      const check = await fetch(url, { method: 'GET', credentials: 'include' });
      if (!check.ok) {
        let detail = `HTTP ${check.status}`;
        try {
          const body = await check.json();
          detail = body?.detail?.message || body?.detail || detail;
        } catch {}
        throw new Error(`Download not available: ${detail}`);
      }
      // File confirmed — extract filename from Content-Disposition then trigger download
      const blob = await check.blob();
      const disposition = check.headers.get('content-disposition') || '';
      // Prefer RFC 5987 filename*=UTF-8''... over plain filename="..."
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const stdMatch  = disposition.match(/filename="([^"]+)"/i);
      let dlFilename = `translated.${fmt}`;
      if (utf8Match?.[1]) {
        dlFilename = decodeURIComponent(utf8Match[1]);
      } else if (stdMatch?.[1]) {
        dlFilename = stdMatch[1];
      }
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = dlFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
    } catch (err: any) {
      const msg = err?.message || 'Download failed';
      setDlError(msg);
      toast({ title: 'Download failed', description: msg, variant: 'destructive' });
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-1">
      <a href={`${API}/api/translation/projects/${projectId}/export/${fmt}`} onClick={handleClick}>
        <Button size="lg" variant="outline" className="gap-2 font-semibold px-6" disabled={checking}>
          {checking
            ? <><Loader2 className="h-4 w-4 animate-spin" /> Preparing…</>
            : <><Download className="h-4 w-4" /> {label}</>
          }
        </Button>
      </a>
      {dlError && (
        <p className="text-[10px] text-red-400 max-w-xs text-center break-words">{dlError}</p>
      )}
    </div>

  );
}


// ── AI Layout Optimizer Button ────────────────────────────────────────────────
// Clears the cached PPTX on the server and downloads a freshly optimized file
// using the current translated content. Translation is never re-run.
// Only shown for PPTX projects (optimizer acts on PPTX geometry).

function RebuildLayoutButton({
  projectId, fmt, onOptimized,
}: {
  projectId: string;
  fmt: string;
  onOptimized?: () => Promise<void> | void;
}) {
  const [rebuilding, setRebuilding] = useState(false);
  const [done, setDone]             = useState(false);
  const [err, setErr]               = useState<string | null>(null);
  const { toast } = useToast();

  if (fmt !== 'pptx') return null;

  const handleRebuild = async () => {
    setRebuilding(true);
    setErr(null);
    setDone(false);
    try {
      const url = `${API}/api/translation/projects/${projectId}/export/pptx?rebuild=true`;
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try { const b = await res.json(); detail = b?.detail?.message || b?.detail || detail; } catch {}
        throw new Error(detail);
      }
      const blob = await res.blob();
      const disposition = res.headers.get('content-disposition') || '';
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const stdMatch  = disposition.match(/filename="([^"]+)"/i);
      let dlFilename = 'rebuilt.pptx';
      if (utf8Match?.[1]) dlFilename = decodeURIComponent(utf8Match[1]);
      else if (stdMatch?.[1]) dlFilename = stdMatch[1];
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl; a.download = dlFilename;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
      setDone(true);
      if (onOptimized) {
        try { await onOptimized(); } catch {}
      }
      toast({ title: 'AI Layout Optimizer complete', description: 'Fresh PPTX downloaded with automatic layout repairs.' });
    } catch (e: any) {
      const msg = e?.message || 'AI layout optimization failed';
      setErr(msg);
      toast({ title: 'AI Layout Optimizer failed', description: msg, variant: 'destructive' });
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-1">
      <Button
        size="lg" variant="ghost"
        className="gap-2 font-medium px-6 text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 border border-amber-500/20"
        onClick={handleRebuild}
        disabled={rebuilding}
        title="Run AI Layout Optimizer on the translated PPTX without re-running translation. Repairs clipping, overflow, overlap, and readability when possible."
      >
        {rebuilding
          ? <><Loader2 className="h-4 w-4 animate-spin" /> Optimizing…</>
          : done
            ? <><RefreshCw className="h-4 w-4" /> Optimized ✓</>
            : <><RefreshCw className="h-4 w-4" /> AI Layout Optimizer</>
        }
      </Button>
      {err && <p className="text-[10px] text-red-400 max-w-xs text-center">{err}</p>}
    </div>
  );
}


// ── Translating Screen ────────────────────────────────────────────────────────

function TranslatingScreen({
  file, sourceLang, targetLang, style, projectName, keepEnglish, transliterate,
  providerName, aiEngine = 'auto',
  layoutMode, styleProfileId, templateStrength, layoutOptions, referenceTemplate,
  onBack, onComplete,
}: {
  file: File; sourceLang: string; targetLang: string; style: string;
  projectName: string; keepEnglish: boolean; transliterate: boolean;
  providerName?: string;
  aiEngine?: string;
  layoutMode?: string;
  styleProfileId?: string;
  templateStrength?: string;
  layoutOptions?: Record<string, boolean>;
  referenceTemplate?: File | null;
  onBack: () => void; onComplete: (id: string) => void;
}) {
  const [phase, setPhase]     = useState<'uploading' | 'processing' | 'confirm' | 'translating' | 'verifying' | 'done' | 'error'>('uploading');
  const [confirmInfo, setConfirmInfo] = useState<any>(null);
  const [confirmPid, setConfirmPid]   = useState<string>('');
  const startStreamRef = useRef<((pid: string, confirmed: boolean) => Promise<void>) | null>(null);
  const cancelUploadRef = useRef<() => void>(() => {});
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadStarted, setUploadStarted] = useState(false);
  const [steps, setSteps]     = useState<StepStatus[]>([]);
  const [submsgs, setSubmsgs] = useState<string[]>([]);
  const [errorMsg, setErrorMsg]   = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [doneId, setDoneId]   = useState<string | null>(null);
  const [docxSize, setDocxSize] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [layoutQuality, setLayoutQuality] = useState<any>(null);
  const [completionState, setCompletionState] = useState<'completed' | 'completed_with_warnings'>('completed');
  const [warningsCount, setWarningsCount] = useState(0);
  const [slidesRequiringReview, setSlidesRequiringReview] = useState<number[]>([]);
  const [layoutWarnings, setLayoutWarnings] = useState<string[]>([]);
  const { toast } = useToast();

  const docType  = getDocType(file.name);
  const DocIcon  = docType.icon;
  const src      = langLabel(sourceLang);
  const tgt      = langLabel(targetLang);

  const updateStep = (upd: Partial<StepStatus> & { step: number }) => {
    setSteps(prev => {
      const next = [...prev];
      const idx  = next.findIndex(s => s.step === upd.step);
      if (idx >= 0) next[idx] = { ...next[idx], ...upd } as StepStatus;
      else next.push({ name: '', status: 'pending', ...upd } as StepStatus);
      const sorted = next.sort((a, b) => a.step - b.step);
      const done   = sorted.filter(s => s.status === 'done').length;
      setProgress(Math.round((done / PIPELINE_STEPS.length) * 100));
      return sorted;
    });
  };

  const refreshCompletionFromProject = async (projectId: string) => {
    try {
      const r = await fetch(`${API}/api/translation/projects/${projectId}`, { credentials: 'include' });
      if (!r.ok) return;
      const p = await r.json();
      const wc = Number(p?.warnings_count ?? p?.layout_warnings?.length ?? 0) || 0;
      setWarningsCount(wc);
      setSlidesRequiringReview(Array.isArray(p?.slides_requiring_review) ? p.slides_requiring_review : []);
      setLayoutWarnings(Array.isArray(p?.layout_warnings) ? p.layout_warnings : []);
      setCompletionState((p?.completion_state === 'completed_with_warnings' || wc > 0) ? 'completed_with_warnings' : 'completed');
      if (p?.layout_quality) setLayoutQuality(p.layout_quality);
    } catch {}
  };

  useEffect(() => {
    let cancelled = false;
    const fail = (e: any) => {
      if (cancelled) return;
      const msg = e?.message || 'Translation failed';
      setErrorMsg(msg);
      // Extract debug detail from structured errors if available
      if (e?.detail && typeof e.detail === 'object') {
        setErrorDetail(JSON.stringify(e.detail, null, 2));
      }
      setPhase('error');
    };

    (async () => {
      try {
        // ── 1. Upload with real XHR progress ──────────────────────────────────
        const form = new FormData();
        form.append('file', file);
        form.append('name', projectName.trim() || file.name.replace(/\.[^.]+$/, ''));
        form.append('source_lang', sourceLang);
        form.append('target_lang', targetLang);
        form.append('style', style);
        form.append('keep_english_terms', keepEnglish ? 'true' : 'false');
        form.append('transliterate_names', transliterate ? 'true' : 'false');
        form.append('provider_name', providerName || 'auto');
        form.append('layout_mode', layoutMode || 'original');
        form.append('style_profile_id', styleProfileId || '');
        form.append('template_strength', templateStrength || 'balanced');
        form.append('layout_options', JSON.stringify(layoutOptions || {}));
        if (referenceTemplate && layoutMode === 'reference') {
          form.append('reference_template', referenceTemplate);
        }

        const pid: string = await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.withCredentials = true;

          // ── Total request ceiling: 10 minutes (connect + upload + server processing) ──
          xhr.timeout = 10 * 60 * 1000;

          // ── Stall detector: server must begin responding (headers received) within 10 minutes
          // We detect response start via readyState, not upload progress, because
          // upload progress is local to the browser and does NOT mean the server answered.
          let responseStarted = false;
          let userCancelled = false;
          let stallTimerFired = false;
          let stallTimer: number | null = window.setTimeout(() => {
            if (!responseStarted) {
              stallTimerFired = true;
              xhr.abort();
              reject(new Error(
                'Server did not respond within 10 minutes — the backend may be restarting or under load. ' +
                'Please wait a moment and try again.'
              ));
            }
          }, 10 * 60 * 1000);

          const clearStall = () => {
            if (stallTimer != null) {
              window.clearTimeout(stallTimer);
              stallTimer = null;
            }
          };

          // Expose cancellation to the UI
          cancelUploadRef.current = () => {
            userCancelled = true;
            xhr.abort();
          };

          xhr.upload.addEventListener('progress', (e) => {
            setUploadStarted(true);
            if (e.lengthComputable) {
              const pct = Math.round(e.loaded / e.total * 100);
              setUploadPct(pct);
              // Bytes fully sent — the server is now parsing & storing the document
              if (e.loaded >= e.total) setPhase('processing');
            } else {
              // Size unknown — show indeterminate "uploading" state
              setPhase('processing');
            }
          });

          // Detect actual server response start (headers received)
          xhr.onreadystatechange = () => {
            if (xhr.readyState >= XMLHttpRequest.HEADERS_RECEIVED && !responseStarted) {
              responseStarted = true;
              clearStall();
            }
          };

          xhr.addEventListener('load', () => {
            clearStall();
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                const data = JSON.parse(xhr.responseText);
                resolve(data.id);
              } catch {
                reject(new Error('Invalid server response during upload'));
              }
            } else {
              let detail = '';
              try { detail = JSON.parse(xhr.responseText)?.detail || ''; } catch {}
              if (xhr.status === 507) {
                reject(new Error(`Storage failure${detail ? ': ' + detail : ' — the server ran out of disk space.'}`));
              } else if (xhr.status >= 500) {
                reject(new Error(`Backend exception (HTTP ${xhr.status})${detail ? ': ' + detail : ''}`));
              } else {
                reject(new Error(`Server rejected the upload (HTTP ${xhr.status})${detail ? ': ' + detail : ''}`));
              }
            }
          });

          xhr.addEventListener('error', () => {
            clearStall();
            if (userCancelled) {
              reject(new Error('Upload cancelled by user'));
            } else if (xhr.status === 0) {
              reject(new Error('Network interrupted — the connection was dropped before the server responded. Check your network and try again.'));
            } else {
              reject(new Error(`Network error (HTTP ${xhr.status}) — could not reach the server. Check your connection and try again.`));
            }
          });

          xhr.addEventListener('abort', () => {
            clearStall();
            if (userCancelled) {
              reject(new Error('Upload cancelled by user'));
            } else if (stallTimerFired) {
              reject(new Error('Server did not respond within 10 minutes — the backend may be restarting or under load. Please wait a moment and try again.'));
            } else {
              reject(new Error('Browser cancelled the upload — the page may have navigated away, the tab was closed, or the browser throttled a background tab.'));
            }
          });

          xhr.addEventListener('timeout', () => {
            clearStall();
            reject(new Error('Upload timed out after 10 minutes — the file may be too large or the server is under heavy load. Please try again.'));
          });

          xhr.open('POST', '/api/translation/projects');
          xhr.send(form);
        });

        if (cancelled) return;
        setUploadPct(100);
        setPhase('translating');
        await startStream(pid, false);
      } catch (e: any) {
        fail(e);
      }
    })();

    // ── 2. SSE translation pipeline (also called by the cost-confirm button) ──
    async function startStream(pid: string, confirmedFlag: boolean) {
      try {
        const r = await fetch(
          `/api/translation/projects/${pid}/translate?${confirmedFlag ? 'confirmed=true&' : ''}ai_provider=${aiEngine}`,
          { method: 'POST', credentials: 'include' },
        );
        if (r.status === 428) {
          // Server requires explicit cost confirmation for large documents.
          // General users never see cost: auto-confirm and let the server's
          // spending caps (MAX_COST_PER_JOB_USD etc.) bound the job.
          if (PUBLIC_MODE && !confirmedFlag) {
            if (cancelled) return;
            return startStream(pid, true);
          }
          let detail: any = {};
          try { detail = (await r.json())?.detail || {}; } catch {}
          if (cancelled) return;
          setConfirmInfo(detail);
          setConfirmPid(pid);
          setPhase('confirm');
          return;
        }
        if (!r.ok) {
          let msg: any = `Server error ${r.status}`;
          try { msg = (await r.json())?.detail || msg; } catch {}
          throw new Error(typeof msg === 'string' ? msg : (msg?.message || JSON.stringify(msg)));
        }
        if (!r.body) throw new Error('No response stream from server');

        const reader = r.body.getReader();
        const dec    = new TextDecoder();
        let buf      = '';
        let receivedDone = false;

        outer: while (true) {
          const { done: streamDone, value } = await reader.read();
          if (streamDone) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;

            // Separate JSON parse errors from logic errors
            let d: any;
            try { d = JSON.parse(line.slice(6)); } catch { continue; }

            if (d.type === 'step') {
              updateStep({
                step: d.step,
                name: d.name || PIPELINE_STEPS[d.step - 1] || '',
                status: d.status,
              });
            } else if (d.type === 'substep') {
              setSubmsgs(p => [...p, d.message || '']);
            } else if (d.type === 'done') {
              // Backend has confirmed file exists — trust it
              // has_output is the canonical field; fall back to has_docx for older backend responses
              const hasOutput = d.has_output !== undefined ? d.has_output : d.has_docx;
              if (hasOutput === false) {
                throw new Error(
                  'Translation pipeline completed but the output file could not be generated. ' +
                  'Your translated segments were saved — open the project to export manually.'
                );
              }
              setProgress(100);
              setDocxSize(d.output_size ?? d.docx_size ?? null);
              setDoneId(pid);
              const wc = Number(d.warnings_count ?? 0) || 0;
              setWarningsCount(wc);
              setSlidesRequiringReview(Array.isArray(d.slides_requiring_review) ? d.slides_requiring_review : []);
              setLayoutWarnings(Array.isArray(d.layout_warnings) ? d.layout_warnings : []);
              setCompletionState((d.completion_state === 'completed_with_warnings' || wc > 0) ? 'completed_with_warnings' : 'completed');
              if (d.layout_quality) setLayoutQuality(d.layout_quality);
              setPhase('done');
              receivedDone = true;
              break outer;
            } else if (d.type === 'error') {
              if (d.step) {
                updateStep({
                  step: d.step,
                  name: PIPELINE_STEPS[d.step - 1] || '',
                  status: 'error',
                });
              }
              // Surface the exact backend error — never swallow it
              throw new Error(d.error || 'Translation failed');
            }
          }
        }

        // Stream closed without a done event — treat as failure
        if (!receivedDone && !cancelled) {
          throw new Error(
            'Translation stream closed unexpectedly before completing. ' +
            'The server may have run out of memory or timed out.'
          );
        }

      } catch (e: any) {
        fail(e);
      }
    }

    startStreamRef.current = startStream;

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="shrink-0 border-b border-border bg-card/40 px-6 py-3">
        <div className="max-w-3xl mx-auto flex items-center gap-4">
          {phase !== 'translating' && (
            <Button variant="ghost" size="sm" onClick={onBack} className="gap-1 text-xs shrink-0">
              <ChevronLeft className="h-3.5 w-3.5" /> Back
            </Button>
          )}
          {(phase === 'uploading' || phase === 'processing') && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => cancelUploadRef.current?.()}
              className="gap-1 text-xs shrink-0 text-muted-foreground hover:text-red-400"
            >
              <XCircle className="h-3.5 w-3.5" /> Cancel
            </Button>
          )}
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ring-1 ${docType.bg} ring-white/10`}>
              <DocIcon className={`h-4 w-4 ${docType.color}`} />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">{file.name}</p>
              <p className="text-xs text-muted-foreground">
                {src.flag} {src.label} → {tgt.flag} {tgt.label} · {STYLES.find(s => s.value === style)?.label}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto flex items-center justify-center p-6">
        <div className="w-full max-w-2xl space-y-8">

          {/* Progress bar */}
          <div className="space-y-3">
            {/* Upload progress — visible during upload */}
            {(phase === 'uploading' || phase === 'processing') && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground font-mono">
                    {phase === 'processing'
                      ? 'Upload complete · Saving to server…'
                      : !uploadStarted
                        ? 'Connecting to server…'
                        : uploadPct > 0
                          ? `Uploading… ${uploadPct}%`
                          : 'Uploading…'}
                  </span>
                  <span className="font-bold font-mono text-primary">
                    {(phase === 'processing' || !uploadStarted)
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin inline" />
                      : null}
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full bg-primary ${
                      (phase === 'processing' || !uploadStarted)
                        ? 'w-full animate-pulse'
                        : 'transition-all duration-300'
                    }`}
                    style={
                      (phase === 'processing' || !uploadStarted)
                        ? undefined
                        : { width: `${Math.max(uploadPct, 3)}%` }
                    }
                  />
                </div>
                {phase === 'processing' && (
                  <p className="text-[11px] text-muted-foreground">
                    Extracting text and saving the document — large files can take a minute…
                  </p>
                )}
                {!uploadStarted && phase === 'uploading' && (
                  <p className="text-[11px] text-muted-foreground">
                    Waiting for the server to accept the connection…
                  </p>
                )}
              </div>
            )}
            {/* Pipeline progress — visible after upload */}
            {phase !== 'uploading' && phase !== 'processing' && phase !== 'confirm' && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground font-mono">
                    {phase === 'done'       ? 'Complete' :
                     phase === 'error'      ? 'Failed' :
                     phase === 'verifying'  ? 'Verifying download…' :
                     'Translating…'}
                  </span>
                  <span className={`font-bold font-mono ${phase === 'done' ? 'text-emerald-400' : phase === 'error' ? 'text-red-400' : 'text-primary'}`}>
                    {progress}%
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${phase === 'done' ? 'bg-emerald-500' : phase === 'error' ? 'bg-red-500' : 'bg-primary'}`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Pipeline steps */}
          <div className="space-y-0">
            {PIPELINE_STEPS.map((name, i) => {
              const stepNum = i + 1;
              const st      = steps.find(s => s.step === stepNum);
              const status  = st?.status ?? (phase === 'uploading' ? 'pending' : 'pending');
              return (
                <div key={stepNum} className="flex items-start gap-4 py-3 border-b border-border/30 last:border-0">
                  {/* Status icon */}
                  <div className={`h-7 w-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-xs font-bold transition-all
                    ${status === 'done'    ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/30' :
                      status === 'running' ? 'bg-primary/10 text-primary ring-1 ring-primary/30' :
                      status === 'error'   ? 'bg-red-500/10 text-red-400 ring-1 ring-red-500/30' :
                                             'bg-muted/30 text-muted-foreground/30'}`}>
                    {status === 'done'    ? <Check className="h-3.5 w-3.5" /> :
                     status === 'running' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                     status === 'error'   ? <XCircle className="h-3.5 w-3.5" /> :
                     <span className="text-[10px]">{stepNum}</span>}
                  </div>

                  {/* Step info */}
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium transition-colors
                      ${status === 'done'    ? 'text-emerald-400' :
                        status === 'running' ? 'text-foreground' :
                        status === 'error'   ? 'text-red-400' :
                                               'text-muted-foreground/40'}`}>
                      {st?.name || name}
                    </p>
                    {stepNum === 1 && submsgs.length > 0 && (
                      <div className="mt-1 space-y-0.5">
                        {submsgs.slice(-3).map((msg, mi) => (
                          <p key={mi} className="text-[10px] text-fuchsia-400/70 flex items-center gap-1.5">
                            <ScanLine className="h-2.5 w-2.5 shrink-0" /> {msg}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Status pill */}
                  <div className="shrink-0">
                    {status === 'running' && (
                      <span className="text-[10px] font-semibold text-primary bg-primary/10 px-2 py-0.5 rounded-full">
                        Running
                      </span>
                    )}
                    {status === 'done' && (
                      <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                        Done
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Cost confirmation for large documents */}
          {phase === 'confirm' && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 space-y-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                <p className="text-sm font-semibold text-foreground">
                  Large document — confirm before translating
                </p>
              </div>
              <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-xs">
                <span className="text-muted-foreground">File type</span>
                <span className="text-foreground font-mono">{file.name.split('.').pop()?.toUpperCase() || '—'}</span>
                <span className="text-muted-foreground">Pages / slides</span>
                <span className="text-foreground font-mono">{confirmInfo?.pages ?? '—'}</span>
                <span className="text-muted-foreground">Text segments</span>
                <span className="text-foreground font-mono">{confirmInfo?.segments ?? '—'}</span>
                <span className="text-muted-foreground">Text volume</span>
                <span className="text-foreground font-mono">{(confirmInfo?.chars ?? 0).toLocaleString()} characters</span>
                <span className="text-muted-foreground">Estimated API cost</span>
                <span className="text-foreground font-mono">
                  ${Number(confirmInfo?.est_cost_usd_low ?? 0).toFixed(2)} – ${Number(confirmInfo?.est_cost_usd_high ?? 0).toFixed(2)} USD
                </span>
              </div>
              <Button
                className="w-full gap-2 font-semibold"
                onClick={() => {
                  setPhase('translating');
                  void startStreamRef.current?.(confirmPid, true);
                }}
              >
                <Check className="h-4 w-4" /> Confirm Translation and Estimated Cost
              </Button>
              <p className="text-[10px] text-muted-foreground text-center">
                Translation starts only after you confirm. The cost range is an estimate of OpenAI API usage.
              </p>
            </div>
          )}

          {/* Error state */}
          {phase === 'error' && errorMsg && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 space-y-3">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-red-400">Translation failed</p>
                  <p className="text-xs text-muted-foreground mt-1 break-words">{errorMsg}</p>
                </div>
                <Button size="sm" variant="outline" className="shrink-0" onClick={onBack}>
                  Try again
                </Button>
              </div>
              {errorDetail && (
                <pre className="text-[10px] text-red-300/70 bg-red-950/30 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
                  {errorDetail}
                </pre>
              )}
            </div>
          )}

          {/* Done state */}
          {phase === 'done' && doneId && (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-8 flex flex-col items-center gap-5 text-center">
              <div className="h-16 w-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center ring-1 ring-emerald-500/30">
                <CheckCircle2 className="h-8 w-8 text-emerald-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-foreground">
                  {completionState === 'completed_with_warnings' && !PUBLIC_MODE ? 'Translation completed with warnings' : 'Translation complete'}
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  {completionState === 'completed_with_warnings' && !PUBLIC_MODE
                    ? 'Output file generated successfully. Review the warnings below.'
                    : 'Output file verified and ready.'}
                  {docxSize != null && (
                    <span className="ml-1 text-emerald-400/80 font-mono text-xs">
                      ({(docxSize / 1024).toFixed(0)} KB)
                    </span>
                  )}
                </p>
              </div>

              {!PUBLIC_MODE && completionState === 'completed_with_warnings' && (
                <div className="w-full rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 space-y-2 text-left">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-amber-300">QA Warnings</span>
                    <span className="text-xs font-mono text-amber-200">{warningsCount} warning(s)</span>
                  </div>
                  <p className="text-[11px] text-amber-100/80">
                    Slides requiring review: {slidesRequiringReview.length > 0 ? slidesRequiringReview.join(', ') : 'n/a'}
                  </p>
                  {layoutWarnings.length > 0 && (
                    <ul className="space-y-1 max-h-36 overflow-auto pr-1">
                      {layoutWarnings.slice(0, 8).map((w, i) => (
                        <li key={i} className="text-[11px] text-amber-100/85">- {String(w)}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* Layout quality score badge (only when a style profile was applied) */}
              {!PUBLIC_MODE && layoutQuality && layoutQuality.overall_score != null && (
                <div className="w-full rounded-xl border border-violet-500/20 bg-violet-500/5 px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-violet-300 flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5" /> Layout Quality Score
                    </span>
                    <span className={`text-xl font-bold ${scoreColor(layoutQuality.overall_score)}`}>
                      {layoutQuality.overall_score}/100
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                    {layoutQuality.font_match_pct != null && (
                      <><span className="text-muted-foreground">Font match</span><span className="text-right font-mono text-foreground">{layoutQuality.font_match_pct}%</span></>
                    )}
                    {layoutQuality.color_match_pct != null && (
                      <><span className="text-muted-foreground">Color match</span><span className="text-right font-mono text-foreground">{layoutQuality.color_match_pct}%</span></>
                    )}
                    {layoutQuality.arabic_readability_pct != null && (
                      <><span className="text-muted-foreground">Arabic readability</span><span className="text-right font-mono text-foreground">{layoutQuality.arabic_readability_pct}%</span></>
                    )}
                    {layoutQuality.overflow_count != null && layoutQuality.overflow_count > 0 && (
                      <><span className="text-muted-foreground">Overflow warnings</span><span className="text-right font-mono text-amber-400">{layoutQuality.overflow_count}</span></>
                    )}
                  </div>
                </div>
              )}

              <div className="flex flex-wrap gap-3 justify-center">
                {PUBLIC_MODE ? (
                  /* Public user: a single Download button for the chosen language. */
                  <VerifiedDownloadButton
                    projectId={doneId}
                    fmt={'arabic'}
                    label={`Download ${tgt.label}`}
                  />
                ) : (
                  <>
                    <Button size="lg" className="gap-2 font-semibold px-8" onClick={() => onComplete(doneId)}>
                      <BookOpen className="h-4 w-4" /> Review & Export
                    </Button>
                    <VerifiedDownloadButton projectId={doneId} fmt={'arabic'} label={`${tgt.label} Only`} />
                    {sourceLang === 'en' && (
                      <VerifiedDownloadButton projectId={doneId} fmt={'english'} label={'English Only'} />
                    )}
                    <VerifiedDownloadButton projectId={doneId} fmt={'original'} label={'Original'} />
                    {sourceLang === 'en' && (
                      <VerifiedDownloadButton projectId={doneId} fmt={'package'} label={`${tgt.label} + English Package`} />
                    )}
                    <RebuildLayoutButton
                      projectId={doneId}
                      fmt={(() => { const ext = file.name.split('.').pop()?.toLowerCase() ?? ''; return ext === 'pptx' ? 'pptx' : 'other'; })()}
                      onOptimized={() => refreshCompletionFromProject(doneId)}
                    />
                  </>
                )}
              </div>
              <Button
                size="sm" variant="ghost"
                className="text-muted-foreground gap-2 mt-1"
                onClick={() => {
                  setPhase('translating');
                  setSteps([]);
                  setSubmsgs([]);
                  setErrorMsg(null);
                  setErrorDetail(null);
                  setProgress(0);
                  // Re-trigger the SSE pipeline on the same project.
                  // confirmed=true: the user explicitly clicked re-run.
                  fetch(`${API}/api/translation/projects/${doneId}/translate?confirmed=true&ai_provider=${aiEngine}`, {
                    method: 'POST', credentials: 'include',
                  }).then(async r => {
                    if (!r.ok || !r.body) throw new Error(`Server error ${r.status}`);
                    const reader = r.body.getReader();
                    const dec = new TextDecoder();
                    let buf = '';
                    let receivedDone = false;
                    try {
                      while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        buf += dec.decode(value, { stream: true });
                        const lines = buf.split('\n');
                        buf = lines.pop() ?? '';
                        for (const line of lines) {
                          if (!line.startsWith('data:')) continue;
                          let d: Record<string,unknown>;
                          try { d = JSON.parse(line.slice(5)); } catch { continue; }
                          if (d.type === 'step') {
                            updateStep({ step: d.step as number, name: (d.name || PIPELINE_STEPS[(d.step as number) - 1] || '') as string, status: d.status as StepStatus['status'] });
                          } else if (d.type === 'substep') {
                            setSubmsgs(prev => [...prev.slice(-4), d.message as string]);
                          } else if (d.type === 'done') {
                            receivedDone = true;
                            setDocxSize(((d.output_size ?? d.docx_size) as number) ?? null);
                            setDoneId(d.project_id as string);
                            setPhase('done');
                          } else if (d.type === 'error') {
                            setErrorMsg(d.error as string);
                            setPhase('error');
                          }
                        }
                      }
                      if (!receivedDone && phase !== 'done') {
                        setErrorMsg('Translation stream closed without completing.');
                        setPhase('error');
                      }
                    } catch (err: unknown) {
                      setErrorMsg(err instanceof Error ? err.message : String(err));
                      setPhase('error');
                    }
                  }).catch(err => {
                    setErrorMsg(err instanceof Error ? err.message : String(err));
                    setPhase('error');
                  });
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" /> Re-run Translation
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Multi-Language Translation ────────────────────────────────────────────────
// "Translate to Multiple Languages": one uploaded file, several target
// languages. Each language is a fully independent project/job — its own
// upload, its own SSE pipeline run, its own progress/status/error/download —
// so one language failing never blocks or corrupts the others.

type MultiCardPhase = 'uploading' | 'translating' | 'confirm' | 'done' | 'error';

function MultiLanguageCard({
  file, sourceLang, targetLang, style, projectName, keepEnglish, transliterate,
  providerName, aiEngine, layoutMode, styleProfileId, templateStrength, layoutOptions,
  referenceTemplate, onOpenProject,
}: {
  file: File; sourceLang: string; targetLang: string; style: string;
  projectName: string; keepEnglish: boolean; transliterate: boolean;
  providerName?: string; aiEngine?: string;
  layoutMode?: string; styleProfileId?: string; templateStrength?: string;
  layoutOptions?: Record<string, boolean>; referenceTemplate?: File | null;
  onOpenProject: (id: string) => void;
}) {
  const [phase, setPhase]     = useState<MultiCardPhase>('uploading');
  const [step, setStep]       = useState('Uploading…');
  const [progress, setProgress] = useState(0);
  const [pid, setPid]         = useState<string | null>(null);
  const [confirmInfo, setConfirmInfo] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const tgt = langLabel(targetLang);

  const runStream = async (projectId: string, confirmed: boolean) => {
    try {
      const r = await fetch(
        `/api/translation/projects/${projectId}/translate?${confirmed ? 'confirmed=true&' : ''}ai_provider=${aiEngine || 'auto'}`,
        { method: 'POST', credentials: 'include' },
      );
      if (r.status === 428) {
        // General users never see cost: auto-confirm and let the server's
        // spending caps bound the job.
        if (PUBLIC_MODE && !confirmed) {
          return runStream(projectId, true);
        }
        let detail: any = {};
        try { detail = (await r.json())?.detail || {}; } catch {}
        setConfirmInfo(detail);
        setPhase('confirm');
        return;
      }
      if (!r.ok || !r.body) {
        let msg: any = `Server error ${r.status}`;
        try { msg = (await r.json())?.detail || msg; } catch {}
        throw new Error(typeof msg === 'string' ? msg : (msg?.message || JSON.stringify(msg)));
      }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      let receivedDone = false;
      let doneSteps = 0;
      outer: while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let d: any;
          try { d = JSON.parse(line.slice(6)); } catch { continue; }
          if (d.type === 'step') {
            setStep(d.name || PIPELINE_STEPS[d.step - 1] || 'Working…');
            if (d.status === 'done') doneSteps += 1;
            setProgress(Math.round((doneSteps / PIPELINE_STEPS.length) * 100));
          } else if (d.type === 'done') {
            const hasOutput = d.has_output !== undefined ? d.has_output : d.has_docx;
            if (hasOutput === false) {
              throw new Error('Pipeline completed but no output file was generated.');
            }
            setProgress(100);
            setPhase('done');
            receivedDone = true;
            break outer;
          } else if (d.type === 'error') {
            throw new Error(d.error || 'Translation failed');
          }
        }
      }
      if (!receivedDone) {
        throw new Error('Translation stream closed unexpectedly before completing.');
      }
    } catch (e: any) {
      setErrorMsg(e?.message || 'Translation failed');
      setPhase('error');
    }
  };

  const startUpload = async () => {
    setPhase('uploading');
    setErrorMsg(null);
    setStep('Uploading…');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('name', `${projectName.trim() || file.name.replace(/\.[^.]+$/, '')} (${tgt.label})`);
      form.append('source_lang', sourceLang);
      form.append('target_lang', targetLang);
      form.append('style', style);
      form.append('keep_english_terms', keepEnglish ? 'true' : 'false');
      form.append('transliterate_names', transliterate ? 'true' : 'false');
      form.append('provider_name', providerName || 'auto');
      form.append('layout_mode', layoutMode || 'original');
      form.append('style_profile_id', styleProfileId || '');
      form.append('template_strength', templateStrength || 'balanced');
      form.append('layout_options', JSON.stringify(layoutOptions || {}));
      if (referenceTemplate && layoutMode === 'reference') {
        form.append('reference_template', referenceTemplate);
      }
      const r = await fetch(`${API}/api/translation/projects`, {
        method: 'POST', credentials: 'include', body: form,
      });
      if (!r.ok) {
        let detail = '';
        try { detail = (await r.json())?.detail || ''; } catch {}
        throw new Error(`Upload failed (HTTP ${r.status})${detail ? ': ' + detail : ''}`);
      }
      const data = await r.json();
      setPid(data.id);
      setPhase('translating');
      setStep('Starting pipeline…');
      await runStream(data.id, false);
    } catch (e: any) {
      setErrorMsg(e?.message || 'Upload failed');
      setPhase('error');
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => { if (!cancelled) await startUpload(); })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className={`rounded-xl border p-4 space-y-3 transition-colors
      ${phase === 'done' ? 'border-emerald-500/30 bg-emerald-500/5'
        : phase === 'error' ? 'border-red-500/30 bg-red-500/5'
        : 'border-border bg-card/40'}`}>
      <div className="flex items-center gap-2.5">
        <span className="text-xl">{tgt.flag}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-foreground">{tgt.label}</p>
          <p className="text-[11px] text-muted-foreground truncate">
            {phase === 'done' ? 'Completed'
              : phase === 'error' ? errorMsg
              : phase === 'confirm' ? 'Awaiting cost confirmation'
              : step}
          </p>
        </div>
        {phase === 'done' && <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />}
        {phase === 'error' && <XCircle className="h-5 w-5 text-red-400 shrink-0" />}
        {(phase === 'uploading' || phase === 'translating') && (
          <Loader2 className="h-5 w-5 text-primary animate-spin shrink-0" />
        )}
      </div>

      {(phase === 'uploading' || phase === 'translating') && (
        <div className="h-1.5 rounded-full bg-muted/50 overflow-hidden">
          <div className="h-full bg-primary transition-all" style={{ width: `${Math.max(progress, phase === 'uploading' ? 5 : progress)}%` }} />
        </div>
      )}

      {phase === 'confirm' && (
        <Button
          size="sm" className="w-full gap-1.5"
          onClick={() => pid && runStream(pid, true)}
        >
          Confirm & Continue{confirmInfo?.est_cost_usd ? ` (~$${Number(confirmInfo.est_cost_usd).toFixed(2)})` : ''}
        </Button>
      )}

      {phase === 'error' && (
        <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={startUpload}>
          <RotateCcw className="h-3.5 w-3.5" /> Retry
        </Button>
      )}

      {phase === 'done' && pid && (
        <div className="flex gap-2">
          <Button size="sm" className="flex-1 gap-1.5" onClick={() => onOpenProject(pid)}>
            <BookOpen className="h-3.5 w-3.5" /> Review
          </Button>
          <VerifiedDownloadButton projectId={pid} fmt="arabic" label="Download" />
        </div>
      )}
    </div>
  );
}

function MultiTranslatingScreen({
  file, sourceLang, targetLangs, style, projectName, keepEnglish, transliterate,
  providerName, aiEngine, layoutMode, styleProfileId, templateStrength, layoutOptions,
  referenceTemplate, onBack, onDone, onOpenProject,
}: {
  file: File; sourceLang: string; targetLangs: string[]; style: string;
  projectName: string; keepEnglish: boolean; transliterate: boolean;
  providerName?: string; aiEngine?: string;
  layoutMode?: string; styleProfileId?: string; templateStrength?: string;
  layoutOptions?: Record<string, boolean>; referenceTemplate?: File | null;
  onBack: () => void; onDone: () => void; onOpenProject: (id: string) => void;
}) {
  const docType = getDocType(file.name);
  const DocIcon = docType.icon;
  const src = langLabel(sourceLang);

  return (
    <div className="flex flex-col h-full bg-background">
      <div className="shrink-0 border-b border-border bg-card/40 px-6 py-3">
        <div className="max-w-3xl mx-auto flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={onBack} className="gap-1 text-xs shrink-0">
            <ChevronLeft className="h-3.5 w-3.5" /> Back
          </Button>
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ring-1 ${docType.bg} ring-white/10`}>
              <DocIcon className={`h-4 w-4 ${docType.color}`} />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">{file.name}</p>
              <p className="text-xs text-muted-foreground">
                {src.flag} {src.label} → {targetLangs.length} languages · {STYLES.find(s => s.value === style)?.label}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-3xl mx-auto space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {targetLangs.map(tl => (
              <MultiLanguageCard
                key={tl}
                file={file}
                sourceLang={sourceLang}
                targetLang={tl}
                style={style}
                projectName={projectName}
                keepEnglish={keepEnglish}
                transliterate={transliterate}
                providerName={providerName}
                aiEngine={aiEngine}
                layoutMode={layoutMode}
                styleProfileId={styleProfileId}
                templateStrength={templateStrength}
                layoutOptions={layoutOptions}
                referenceTemplate={referenceTemplate}
                onOpenProject={onOpenProject}
              />
            ))}
          </div>
          <div className="flex justify-center pt-2">
            <Button variant="outline" onClick={onDone} className="gap-1.5">
              Done — back to Translation Studio
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Resuming Screen ───────────────────────────────────────────────────────────

/**
 * Resumes a partial translation project by calling the translate endpoint
 * on an already-created project (skips the upload step).
 * Previously-translated segments are retrieved from translation memory and
 * reused without additional GPT calls.
 */
function ResumingScreen({
  projectId, projectName, onBack, onComplete,
}: {
  projectId: string; projectName: string;
  onBack: () => void; onComplete: (id: string) => void;
}) {
  const [phase, setPhase]     = useState<'translating' | 'done' | 'error'>('translating');
  const [steps, setSteps]     = useState<StepStatus[]>([]);
  const [submsgs, setSubmsgs] = useState<string[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const { toast } = useToast();

  const updateStep = (upd: Partial<StepStatus> & { step: number }) => {
    setSteps(prev => {
      const next = [...prev];
      const idx  = next.findIndex(s => s.step === upd.step);
      if (idx >= 0) next[idx] = { ...next[idx], ...upd } as StepStatus;
      else next.push({ name: '', status: 'pending', ...upd } as StepStatus);
      const sorted = next.sort((a, b) => a.step - b.step);
      const done   = sorted.filter(s => s.status === 'done').length;
      setProgress(Math.round((done / PIPELINE_STEPS.length) * 100));
      return sorted;
    });
  };

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/translation/projects/${projectId}/translate`, {
          method: 'POST', credentials: 'include',
        });
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        if (!r.body) throw new Error('No response stream');

        const reader = r.body.getReader();
        const dec    = new TextDecoder();
        let buf      = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() || '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const d = JSON.parse(line.slice(6));
              if (d.type === 'step') {
                updateStep({ step: d.step, name: d.name || PIPELINE_STEPS[d.step - 1] || '', status: d.status });
              } else if (d.type === 'substep') {
                setSubmsgs(p => [...p, d.message || '']);
              } else if (d.type === 'done') {
                setProgress(100);
                setPhase('done');
              } else if (d.type === 'error') {
                if (d.step) updateStep({ step: d.step, name: PIPELINE_STEPS[d.step - 1] || '', status: 'error' });
                throw new Error(d.error || 'Translation failed');
              }
            } catch {}
          }
        }
      } catch (e: any) {
        setErrorMsg(e.message || 'Resume failed');
        setPhase('error');
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="shrink-0 border-b border-border bg-card/40 px-6 py-3">
        <div className="max-w-3xl mx-auto flex items-center gap-4">
          {phase !== 'translating' && (
            <Button variant="ghost" size="sm" onClick={onBack} className="gap-1 text-xs shrink-0">
              <ChevronLeft className="h-3.5 w-3.5" /> Back
            </Button>
          )}
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ring-1 bg-amber-500/10 ring-amber-500/20">
              <RotateCcw className="h-4 w-4 text-amber-400" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">{projectName}</p>
              <p className="text-xs text-amber-400/80">Resuming partial translation — reusing saved segments</p>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto flex items-center justify-center p-6">
        <div className="w-full max-w-2xl space-y-8">

          {/* Progress bar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground font-mono">
                {phase === 'done'  ? 'Complete' :
                 phase === 'error' ? 'Failed' : 'Resuming translation…'}
              </span>
              <span className={`font-bold font-mono ${phase === 'done' ? 'text-emerald-400' : phase === 'error' ? 'text-red-400' : 'text-amber-400'}`}>
                {progress}%
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${phase === 'done' ? 'bg-emerald-500' : phase === 'error' ? 'bg-red-500' : 'bg-amber-500'}`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Info banner */}
          <div className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs text-amber-300">
            <RotateCcw className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <span>Previously translated segments are being reused from translation memory — only missing segments will be sent to GPT.</span>
          </div>

          {/* Pipeline steps */}
          <div className="space-y-0">
            {PIPELINE_STEPS.map((name, i) => {
              const stepNum = i + 1;
              const st      = steps.find(s => s.step === stepNum);
              const status  = st?.status ?? 'pending';
              return (
                <div key={stepNum} className="flex items-start gap-4 py-3 border-b border-border/30 last:border-0">
                  <div className={`h-7 w-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-xs font-bold transition-all
                    ${status === 'done'    ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/30' :
                      status === 'running' ? 'bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/30' :
                      status === 'error'   ? 'bg-red-500/10 text-red-400 ring-1 ring-red-500/30' :
                                             'bg-muted/30 text-muted-foreground/30'}`}>
                    {status === 'done'    ? <Check className="h-3.5 w-3.5" /> :
                     status === 'running' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                     status === 'error'   ? <XCircle className="h-3.5 w-3.5" /> :
                     <span className="text-[10px]">{stepNum}</span>}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium transition-colors
                      ${status === 'done'    ? 'text-emerald-400' :
                        status === 'running' ? 'text-foreground' :
                        status === 'error'   ? 'text-red-400' :
                                               'text-muted-foreground/40'}`}>
                      {st?.name || name}
                    </p>
                    {stepNum === 1 && submsgs.length > 0 && (
                      <div className="mt-1 space-y-0.5">
                        {submsgs.slice(-3).map((msg, mi) => (
                          <p key={mi} className="text-[10px] text-fuchsia-400/70 flex items-center gap-1.5">
                            <ScanLine className="h-2.5 w-2.5 shrink-0" /> {msg}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0">
                    {status === 'running' && (
                      <span className="text-[10px] font-semibold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">Running</span>
                    )}
                    {status === 'done' && (
                      <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">Done</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Error state */}
          {phase === 'error' && errorMsg && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-400">Resume failed</p>
                <p className="text-xs text-muted-foreground mt-1">{errorMsg}</p>
              </div>
              <Button size="sm" variant="outline" className="shrink-0 ml-auto" onClick={onBack}>Back</Button>
            </div>
          )}

          {/* Done state */}
          {phase === 'done' && (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-8 flex flex-col items-center gap-5 text-center">
              <div className="h-16 w-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center ring-1 ring-emerald-500/30">
                <CheckCircle2 className="h-8 w-8 text-emerald-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-foreground">Translation complete</h2>
                <p className="text-sm text-muted-foreground mt-1">Review and edit the translation, then export in any format.</p>
              </div>
              <div className="flex flex-wrap gap-3 justify-center">
                <Button size="lg" className="gap-2 font-semibold px-8" onClick={() => onComplete(projectId)}>
                  <BookOpen className="h-4 w-4" /> Review & Export
                </Button>
                <VerifiedDownloadButton
                  projectId={projectId}
                  fmt={(() => { const ext = file.name.split('.').pop()?.toLowerCase() ?? ''; return ext === 'pptx' ? 'pptx' : ext === 'xlsx' ? 'xlsx' : 'docx'; })()}
                  label={`Download ${(() => { const ext = file.name.split('.').pop()?.toLowerCase() ?? ''; return ext === 'pptx' ? 'PPTX' : ext === 'xlsx' ? 'XLSX' : 'DOCX'; })()}`}
                />
                <RebuildLayoutButton
                  projectId={projectId}
                  fmt={(() => { const ext = file.name.split('.').pop()?.toLowerCase() ?? ''; return ext === 'pptx' ? 'pptx' : 'other'; })()}
                />
              </div>
              <Button
                size="sm" variant="ghost"
                className="text-muted-foreground gap-2 mt-1"
                onClick={() => {
                  setPhase('translating');
                  setSteps([]);
                  setSubmsgs([]);
                  setErrorMsg(null);
                  setProgress(0);
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" /> Re-run Translation
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Review Screen ─────────────────────────────────────────────────────────────

function ReviewScreen({
  project, onBack, onRefresh,
}: {
  project: ProjectDetail; onBack: () => void; onRefresh: () => void;
}) {
  const [segments, setSegments]       = useState<Segment[]>(project.segments ?? []);
  const [activeTab, setActiveTab]     = useState<'review' | 'images' | 'quality' | 'history'>('review');
  const [, setLocation]               = useLocation();
  const [editingId, setEditingId]     = useState<string | null>(null);
  const [editValue, setEditValue]     = useState('');
  const [saving, setSaving]           = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterMode, setFilterMode]   = useState<'all' | 'flagged' | 'edited' | 'memory'>('all');
  const [versionName, setVersionName] = useState('');
  const [savingVersion, setSavingVersion] = useState(false);
  const { toast } = useToast();

  const isRtl       = ['ar', 'he', 'fa', 'ur'].includes(project.target_lang);
  const src         = langLabel(project.source_lang);
  const tgt         = langLabel(project.target_lang);
  const errorCount  = project.quality_issues.filter(i => i.severity === 'error').length;
  const warnCount   = project.quality_issues.filter(i => i.severity === 'warning').length;
  const memHits     = segments.filter(s => s.memory_match).length;
  const editedCount = segments.filter(s => s.edited).length;
  const imgSegs     = segments.filter(s => s.seg_type === 'image_text');
  const docType     = getDocType(project.source_filename);
  const DocIcon     = docType.icon;

  const filtered = segments.filter(seg => {
    if (filterMode === 'flagged' && !seg.flagged) return false;
    if (filterMode === 'edited'  && !seg.edited)  return false;
    if (filterMode === 'memory'  && !seg.memory_match) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return seg.source.toLowerCase().includes(q) || seg.target.toLowerCase().includes(q);
    }
    return true;
  });

  const saveEdit = async (segId: string) => {
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/translation/projects/${project.id}/segments/${segId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ target: editValue }),
      });
      if (!r.ok) throw new Error('Save failed');
      setSegments(segs => segs.map(s =>
        s.id === segId ? { ...s, target: editValue, edited: true, flagged: false, flag_reason: '' } : s
      ));
      setEditingId(null);
      toast({ title: 'Segment saved' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  const saveVersion = async () => {
    if (!versionName.trim()) return;
    setSavingVersion(true);
    try {
      const r = await fetch(`${API}/api/translation/projects/${project.id}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name: versionName }),
      });
      if (!r.ok) throw new Error('Save failed');
      const data = await r.json();
      toast({ title: `Version "${data.name}" saved` });
      setVersionName(''); onRefresh();
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally { setSavingVersion(false); }
  };

  const restoreVersion = async (vn: number) => {
    if (!confirm(`Restore version ${vn}? Current text will be replaced.`)) return;
    const r = await fetch(`${API}/api/translation/projects/${project.id}/versions/${vn}/restore`, {
      method: 'POST', credentials: 'include',
    });
    if (r.ok) { toast({ title: `Restored to version ${vn}` }); onRefresh(); }
  };

  // Native format always appears first — the export must match the source document type.
  // "english"/"package" are a legacy English↔Arabic bilingual export pair — only
  // meaningful (and only shown) when the source document is actually English.
  const EXPORT_FORMATS = [
    { fmt: 'arabic', label: tgt.label, color: 'text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10 font-semibold' },
    ...(project.source_lang === 'en'
      ? [{ fmt: 'english', label: 'English', color: 'text-sky-400 border-sky-500/30 hover:bg-sky-500/10' }]
      : []),
    { fmt: 'original', label: 'Original', color: 'text-slate-300 border-slate-500/30 hover:bg-slate-500/10' },
    ...(project.source_lang === 'en'
      ? [{ fmt: 'package', label: `${tgt.label}+English`, color: 'text-violet-400 border-violet-500/30 hover:bg-violet-500/10' }]
      : []),
    ...(project.source_file_type === 'pptx'
      ? [{ fmt: 'pptx', label: 'PPTX ★', color: 'text-orange-400 border-orange-500/50 hover:bg-orange-500/10 font-semibold' }]
      : []),
    ...(project.source_file_type === 'xlsx'
      ? [{ fmt: 'xlsx', label: 'XLSX ★', color: 'text-green-400 border-green-500/50 hover:bg-green-500/10 font-semibold' }]
      : []),
    { fmt: 'docx', label: 'DOCX', color: 'text-blue-400 border-blue-500/30 hover:bg-blue-500/10' },
    { fmt: 'pdf',  label: 'PDF',  color: 'text-red-400 border-red-500/30 hover:bg-red-500/10' },
    { fmt: 'txt',  label: 'TXT',  color: 'text-slate-400 border-slate-500/30 hover:bg-slate-500/10' },
    { fmt: 'zip',  label: 'ZIP',  color: 'text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10' },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden bg-background">

      {/* ── Review header ──────────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border bg-card/40">
        <div className="px-4 py-3">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Back */}
            <Button variant="ghost" size="sm" onClick={onBack} className="gap-1 text-xs shrink-0 h-8">
              <ChevronLeft className="h-3.5 w-3.5" /> Projects
            </Button>

            <div className="h-4 w-px bg-border shrink-0" />

            {/* Doc info */}
            <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ring-1 ${docType.bg} ring-white/10`}>
              <DocIcon className={`h-4 w-4 ${docType.color}`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-sm font-bold text-foreground truncate max-w-[280px]">{project.name}</h1>
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${STATUS_COLOR[project.status] ?? STATUS_COLOR.ready}`}>
                  {project.status.toUpperCase()}
                </span>
                <span className="text-xs text-muted-foreground shrink-0">
                  {src.flag} {src.label} → {tgt.flag} {tgt.label}
                </span>
              </div>
            </div>

            {/* Quality score */}
            {project.quality_score !== null && (
              <div className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm font-bold ${scoreBg(project.quality_score)}`}>
                <CheckCircle2 className="h-3.5 w-3.5" />
                {project.quality_score}/100
              </div>
            )}

            {/* Export buttons */}
            <div className="flex items-center gap-1.5 flex-wrap ml-auto">
              {EXPORT_FORMATS.map(({ fmt, label, color }) => (
                <a key={fmt} href={`${API}/api/translation/projects/${project.id}/export/${fmt}`} download>
                  <Button size="sm" variant="outline" className={`h-7 gap-1.5 text-xs px-2.5 ${color}`}>
                    <Download className="h-3 w-3" /> {label}
                  </Button>
                </a>
              ))}
              <a href={`${API}/api/translation/projects/${project.id}/export/quality-report`} download>
                <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs px-2.5 text-sky-400 border-sky-500/30 hover:bg-sky-500/10">
                  <BarChart2 className="h-3 w-3" /> Report
                </Button>
              </a>
            </div>
          </div>
        </div>

        {/* Tabs + stats row */}
        <div className="px-4 pb-2 flex items-center gap-1 border-t border-border/30">
          {[
            { id: 'review',  label: 'Review',         count: segments.length },
            { id: 'images',  label: 'Image Translator', count: null },
            { id: 'quality', label: 'Quality',        count: errorCount + warnCount > 0 ? errorCount + warnCount : null },
            { id: 'history', label: 'History',        count: project.versions.length > 0 ? project.versions.length : null },
          ].map(tab => (
            <button key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all
                ${activeTab === tab.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'}`}>
              {tab.label}
              {tab.count != null && tab.count > 0 && (
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${activeTab === tab.id ? 'bg-white/20' : 'bg-muted'}`}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}

          <div className="ml-auto flex items-center gap-2 text-xs">
            {memHits > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20 text-[10px]">
                {memHits} memory
              </span>
            )}
            {imgSegs.length > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-fuchsia-500/10 text-fuchsia-400 border border-fuchsia-500/20 text-[10px] flex items-center gap-1">
                <ScanLine className="h-2.5 w-2.5" /> {imgSegs.length} diagrams
              </span>
            )}
            {editedCount > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20 text-[10px]">
                {editedCount} edited
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Tab: Review ──────────────────────────────────────────────────────── */}
      {activeTab === 'review' && (
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Toolbar */}
          <div className="shrink-0 bg-background/95 backdrop-blur-sm border-b border-border px-4 py-2 flex items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search segments…"
                className="w-full h-8 pl-8 pr-3 text-xs rounded-lg border border-border bg-card/60 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {/* Filter pills */}
            <div className="flex items-center gap-1">
              {([
                ['all',     'All'],
                ['flagged', `Issues${errorCount + warnCount > 0 ? ` (${errorCount + warnCount})` : ''}`],
                ['memory',  'Memory'],
                ['edited',  'Edited'],
              ] as const).map(([mode, label]) => (
                <button key={mode}
                  onClick={() => setFilterMode(mode)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all border
                    ${filterMode === mode
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'}`}>
                  {label}
                </button>
              ))}
            </div>

            <span className="text-xs text-muted-foreground ml-auto">
              {filtered.length} / {segments.length}
            </span>
          </div>

          {/* Split pane */}
          <div className="flex-1 overflow-hidden flex flex-col">
            {/* Column headers */}
            <div className="shrink-0 grid grid-cols-2 border-b border-border bg-card/30">
              <div className="px-5 py-2.5 text-[11px] font-semibold font-mono text-muted-foreground/60 uppercase tracking-widest border-r border-border">
                {src.flag} {src.label.toUpperCase()} — SOURCE
              </div>
              <div className={`px-5 py-2.5 text-[11px] font-semibold font-mono text-muted-foreground/60 uppercase tracking-widest ${isRtl ? 'text-right' : ''}`}>
                {tgt.flag} {tgt.label.toUpperCase()} — TRANSLATION
              </div>
            </div>

            {/* Segments scroll area */}
            <div className="flex-1 overflow-auto">
              {filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
                  <Search className="h-8 w-8 opacity-30" />
                  <p className="text-sm">No segments match your filter.</p>
                  <button onClick={() => { setFilterMode('all'); setSearchQuery(''); }}
                    className="text-xs text-primary hover:underline">
                    Clear filter
                  </button>
                </div>
              ) : (
                filtered.map((seg, idx) => {
                  const isImgTxt = seg.seg_type === 'image_text';
                  const isEditing = editingId === seg.id;
                  return (
                    <div key={seg.id}
                      className={`grid grid-cols-2 border-b border-border/40 group transition-colors
                        ${isImgTxt    ? 'bg-fuchsia-500/3 hover:bg-fuchsia-500/5' :
                          seg.flagged ? 'bg-amber-500/3 hover:bg-amber-500/5' :
                          seg.edited  ? 'bg-violet-500/3 hover:bg-violet-500/5' :
                          seg.memory_match ? 'bg-sky-500/3 hover:bg-sky-500/5' :
                          'hover:bg-accent/30'}`}>

                      {/* Source cell */}
                      <div className="px-5 py-3 border-r border-border/40">
                        <div className="flex items-center gap-1.5 mb-1">
                          <span className="text-[10px] font-mono text-muted-foreground/40">#{idx + 1}</span>
                          {isImgTxt && (
                            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-fuchsia-500/15 text-fuchsia-400 flex items-center gap-0.5">
                              <ScanLine className="h-2.5 w-2.5" /> Diagram
                            </span>
                          )}
                          {!isImgTxt && seg.seg_type !== 'paragraph' && (
                            <span className="text-[9px] text-muted-foreground/40 capitalize">{seg.seg_type.replace('_', ' ')}</span>
                          )}
                        </div>
                        <p className="text-sm text-foreground/80 leading-relaxed">{seg.source}</p>
                      </div>

                      {/* Target cell */}
                      <div className="px-5 py-3 relative">
                        <div className="flex items-center gap-1.5 mb-1 h-4">
                          {seg.memory_match && !seg.team_match && (
                            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-400">Memory</span>
                          )}
                          {seg.team_match && (
                            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-500 flex items-center gap-0.5">
                              <Users className="h-2.5 w-2.5" /> Team memory
                            </span>
                          )}
                          {seg.edited && (
                            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-400">Edited</span>
                          )}
                          {seg.flagged && (
                            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 flex items-center gap-0.5">
                              <AlertTriangle className="h-2.5 w-2.5" /> {seg.flag_reason.replace(/_/g, ' ')}
                            </span>
                          )}
                          {!isEditing && (
                            <button
                              onClick={() => { setEditingId(seg.id); setEditValue(seg.target); }}
                              className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-primary p-0.5 rounded"
                              title="Edit translation"
                            >
                              <Edit3 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>

                        {isEditing ? (
                          <div className="space-y-2">
                            <textarea
                              value={editValue}
                              onChange={e => setEditValue(e.target.value)}
                              dir={isRtl ? 'rtl' : 'ltr'}
                              className={`w-full text-sm bg-background border border-primary/40 rounded-lg p-2.5 resize-none focus:outline-none focus:ring-1 focus:ring-primary min-h-[80px] ${isRtl ? 'text-right' : ''}`}
                              autoFocus
                            />
                            <div className="flex gap-1.5">
                              <Button size="sm" className="h-7 text-xs px-3" onClick={() => saveEdit(seg.id)} disabled={saving}>
                                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                                Save
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditingId(null)}>
                                Cancel
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <p
                            className={`text-sm leading-relaxed cursor-pointer
                              ${seg.target ? 'text-foreground/90' : 'text-muted-foreground/30 italic'}
                              ${isRtl ? 'text-right' : ''}`}
                            dir={isRtl ? 'rtl' : 'ltr'}
                            onClick={() => { setEditingId(seg.id); setEditValue(seg.target); }}
                            title="Click to edit"
                          >
                            {seg.target || '[not translated — click to add]'}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: Image Translator ─────────────────────────────────────────────── */}
      {activeTab === 'images' && (
        <ImagesTab
          projectId={project.id}
          onOpenEditor={() => setLocation(`/translation/images/${project.id}`)}
        />
      )}

      {/* ── Tab: Quality ──────────────────────────────────────────────────────── */}
      {activeTab === 'quality' && (
        <div className="flex-1 overflow-auto p-6">
          <div className="max-w-3xl mx-auto space-y-6">

            {/* Score card */}
            <div className="rounded-2xl border border-border bg-card/60 p-6 flex items-center gap-6">
              <div className={`h-20 w-20 rounded-2xl flex items-center justify-center text-2xl font-black border-2 shrink-0 ${scoreBg(project.quality_score)}`}>
                {project.quality_score ?? '—'}
              </div>
              <div className="flex-1">
                <h3 className="font-bold text-lg text-foreground">Translation Quality Score</h3>
                <div className="flex items-center gap-2 mt-0.5 mb-2">
                  <p className="text-sm text-muted-foreground">{segments.length} segments analysed</p>
                  {project.provider_name && project.provider_name !== 'auto' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-primary/20 bg-primary/8 text-primary/80 font-semibold">
                      via {project.quality_breakdown?.provider_used || project.provider_name}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-4">
                  <span className="flex items-center gap-1.5 text-xs text-red-400">
                    <XCircle className="h-3.5 w-3.5" /> {errorCount} error{errorCount !== 1 ? 's' : ''}
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-amber-400">
                    <AlertTriangle className="h-3.5 w-3.5" /> {warnCount} warning{warnCount !== 1 ? 's' : ''}
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-sky-400">
                    <Database className="h-3.5 w-3.5" /> {memHits} memory hit{memHits !== 1 ? 's' : ''}
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-violet-400">
                    <Edit3 className="h-3.5 w-3.5" /> {editedCount} manually edited
                  </span>
                </div>
              </div>
            </div>

            {/* ── 5 Quality Dimensions ───────────────────────────────────────── */}
            {project.quality_breakdown && Object.keys(project.quality_breakdown).length > 0 && (() => {
              const qb = project.quality_breakdown!;
              const dims = [
                { key: 'translation_quality',  label: 'Translation Quality',    icon: Languages,   color: 'text-primary',    bg: 'bg-primary/10',    bar: 'bg-primary' },
                { key: 'engineering_quality',   label: 'Engineering Quality',    icon: Cpu,         color: 'text-emerald-400', bg: 'bg-emerald-500/10', bar: 'bg-emerald-500' },
                { key: 'consistency_score',     label: 'Terminology Consistency', icon: TrendingUp,  color: 'text-violet-400',  bg: 'bg-violet-500/10',  bar: 'bg-violet-500' },
                { key: 'formatting_score',      label: 'Formatting Preserved',   icon: FileCheck,   color: 'text-sky-400',     bg: 'bg-sky-500/10',     bar: 'bg-sky-500' },
                { key: 'dnt_score',             label: 'Technical Codes Protected', icon: ShieldCheck, color: 'text-amber-400', bg: 'bg-amber-500/10',  bar: 'bg-amber-500' },
              ] as const;
              return (
                <div className="rounded-2xl border border-border bg-card/60 p-5 space-y-4">
                  <h3 className="text-xs font-mono font-bold text-muted-foreground/60 uppercase tracking-widest">5 Quality Dimensions</h3>
                  <div className="space-y-3">
                    {dims.map(dim => {
                      const score = qb[dim.key as keyof QualityBreakdown] as number | undefined;
                      if (score === undefined) return null;
                      const DIcon = dim.icon;
                      const numScore = typeof score === 'number' ? score : 0;
                      return (
                        <div key={dim.key} className="flex items-center gap-3">
                          <div className={`h-7 w-7 rounded-lg flex items-center justify-center shrink-0 ${dim.bg}`}>
                            <DIcon className={`h-3.5 w-3.5 ${dim.color}`} />
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-foreground/80">{dim.label}</span>
                              <span className={`text-xs font-bold ${dim.color}`}>{numScore}%</span>
                            </div>
                            <div className="h-1.5 w-full rounded-full bg-muted/50 overflow-hidden">
                              <div
                                className={`h-full rounded-full transition-all duration-700 ${dim.bar}`}
                                style={{ width: `${numScore}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

            {/* ── DNT Audit ─────────────────────────────────────────────────── */}
            {project.dnt_tokens && project.dnt_tokens.length > 0 && (
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-8 w-8 rounded-lg bg-amber-500/10 flex items-center justify-center shrink-0">
                    <ShieldCheck className="h-4 w-4 text-amber-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-amber-300">
                      Do-Not-Translate Audit — {project.dnt_tokens.length} protected token{project.dnt_tokens.length !== 1 ? 's' : ''}
                    </p>
                    <p className="text-xs text-muted-foreground">Part numbers, error codes, voltages, measurements preserved verbatim</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                  {project.dnt_tokens.map((tok, i) => (
                    <span key={i} className="px-2 py-0.5 rounded text-[11px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/20">
                      {tok}
                    </span>
                  ))}
                </div>
                {(project.quality_breakdown?.dnt_tokens_garbled?.length ?? 0) > 0 && (
                  <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/5 p-2.5">
                    <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />
                    <p className="text-[11px] text-red-300">
                      {project.quality_breakdown!.dnt_tokens_garbled!.length} token(s) may need review:{' '}
                      {project.quality_breakdown!.dnt_tokens_garbled!.join(', ')}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* ── Engineering Review Changes ──────────────────────────────────── */}
            {project.engineering_review_changes && project.engineering_review_changes.length > 0 && (
              <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-8 w-8 rounded-lg bg-violet-500/10 flex items-center justify-center shrink-0">
                    <Sparkles className="h-4 w-4 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-violet-300">
                      AI Engineering Review — {project.engineering_review_changes.length} improvement{project.engineering_review_changes.length !== 1 ? 's' : ''}
                    </p>
                    <p className="text-xs text-muted-foreground">X-ray domain terminology, radiation safety, and technical precision improvements</p>
                  </div>
                </div>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {project.engineering_review_changes.slice(0, 10).map((change, i) => (
                    <div key={i} className="rounded-lg border border-violet-500/10 bg-violet-500/5 p-2.5 space-y-1">
                      <div className="flex items-start gap-2">
                        <span className="text-[9px] font-bold text-red-400/70 uppercase mt-0.5 shrink-0">Before</span>
                        <p className="text-[11px] text-muted-foreground line-through">{change.before}</p>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="text-[9px] font-bold text-emerald-400/70 uppercase mt-0.5 shrink-0">After</span>
                        <p className="text-[11px] text-violet-300">{change.after}</p>
                      </div>
                      {change.reason && (
                        <p className="text-[10px] text-muted-foreground/60 italic ml-0.5">{change.reason}</p>
                      )}
                    </div>
                  ))}
                  {project.engineering_review_changes.length > 10 && (
                    <p className="text-[11px] text-muted-foreground/60 text-center pt-1">
                      +{project.engineering_review_changes.length - 10} more improvements
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* ── Image text summary ─────────────────────────────────────────── */}
            {imgSegs.length > 0 && (
              <div className="rounded-xl border border-fuchsia-500/20 bg-fuchsia-500/5 p-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-8 w-8 rounded-lg bg-fuchsia-500/10 flex items-center justify-center shrink-0">
                    <ScanLine className="h-4 w-4 text-fuchsia-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-fuchsia-300">
                      {imgSegs.length} diagram label{imgSegs.length !== 1 ? 's' : ''} translated
                    </p>
                    <p className="text-xs text-muted-foreground">Text overlaid on translated images in exported document</p>
                  </div>
                </div>
                <div className="space-y-1.5 max-h-40 overflow-y-auto">
                  {imgSegs.map(seg => (
                    <div key={seg.id} className="flex items-start gap-3 rounded-lg p-2 bg-fuchsia-500/5 border border-fuchsia-500/10">
                      <ScanLine className="h-3.5 w-3.5 text-fuchsia-400 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] text-muted-foreground truncate">{seg.source}</p>
                        <p className="text-[11px] text-fuchsia-300 mt-0.5" dir="rtl">{seg.target || '…'}</p>
                      </div>
                      {seg.edited && <span className="text-[9px] text-violet-400 shrink-0">Edited</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── Issues ────────────────────────────────────────────────────── */}
            {project.quality_issues.length === 0 ? (
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5 flex items-center gap-4">
                <CheckCircle2 className="h-8 w-8 text-emerald-400 shrink-0" />
                <div>
                  <p className="font-semibold text-emerald-400">No quality issues found</p>
                  <p className="text-xs text-muted-foreground">All segments passed terminology and consistency checks.</p>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <h3 className="text-xs font-mono font-bold text-muted-foreground/60 uppercase tracking-widest">Quality Issues</h3>
                {project.quality_issues.map((issue, i) => (
                  <div key={i} className={`rounded-lg border p-3 flex items-start gap-3
                    ${issue.severity === 'error' ? 'border-red-500/20 bg-red-500/5' : 'border-amber-500/20 bg-amber-500/5'}`}>
                    {issue.severity === 'error'
                      ? <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                      : <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />}
                    <div>
                      <p className={`text-xs font-semibold ${issue.severity === 'error' ? 'text-red-400' : 'text-amber-400'}`}>
                        {issue.type.replace(/_/g, ' ').toUpperCase()}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">{issue.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: History ──────────────────────────────────────────────────────── */}
      {activeTab === 'history' && (
        <div className="flex-1 overflow-auto p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="rounded-xl border border-border bg-card/60 p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3">Save current version</h3>
              <div className="flex gap-2">
                <Input
                  value={versionName}
                  onChange={e => setVersionName(e.target.value)}
                  placeholder="e.g. After review round 1"
                  className="h-8 text-sm flex-1"
                  onKeyDown={e => e.key === 'Enter' && saveVersion()}
                />
                <Button size="sm" onClick={saveVersion} disabled={savingVersion || !versionName.trim()} className="gap-1.5">
                  {savingVersion ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clock className="h-3.5 w-3.5" />}
                  Save
                </Button>
              </div>
            </div>

            {project.versions.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <Clock className="h-8 w-8 mx-auto mb-3 opacity-30" />
                <p className="text-sm">No saved versions yet.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {[...project.versions].reverse().map(v => (
                  <div key={v.version_num} className="rounded-xl border border-border bg-card/60 p-4 flex items-center gap-4">
                    <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <span className="text-sm font-bold text-primary">v{v.version_num}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-foreground">{v.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {fmtDate(v.created_at)}
                        {v.quality_score != null && ` · Quality: ${v.quality_score}/100`}
                      </p>
                    </div>
                    <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={() => restoreVersion(v.version_num)}>
                      <RotateCcw className="h-3 w-3" /> Restore
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Images Tab ────────────────────────────────────────────────────────────────

interface ProjectImageSummary {
  id: string; doc_page: number; doc_type: string; image_index: number;
  region_count: number; status: string; has_original: boolean; has_rendered: boolean;
}

const IMG_STATUS: Record<string, string> = {
  done:       'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  no_text:    'bg-slate-500/10 text-slate-400 border-slate-500/20',
  pending:    'bg-amber-500/10 text-amber-400 border-amber-500/20',
  processing: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  error:      'bg-red-500/10 text-red-400 border-red-500/20',
};

// ── Provider Settings Screen ────────────────────────────────────────────────────

interface ProviderStatus {
  id: string; name: string; is_configured: boolean; is_enabled: boolean;
  latency_ms?: number; error?: string; message?: string;
}

interface LoadedProviderConfig {
  provider_id: string;
  is_configured: boolean;
  is_enabled: boolean;
}

// Parse "Usage: 12,345 / 500,000 characters" from DeepL health check
function parseDeepLUsage(message?: string): { used: number; limit: number } | null {
  if (!message) return null;
  const m = message.match(/Usage:\s*([\d,]+)\s*\/\s*([\d,]+)/);
  if (!m) return null;
  return {
    used: parseInt(m[1].replace(/,/g, ''), 10),
    limit: parseInt(m[2].replace(/,/g, ''), 10),
  };
}

function ProviderSettingsScreen({ onBack }: { onBack: () => void }) {
  const API = import.meta.env.BASE_URL?.replace(/\/$/, '');
  const [saving, setSaving] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ProviderStatus>>({});
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  const [loadedConfigs, setLoadedConfigs] = useState<Record<string, LoadedProviderConfig>>({});
  const [loadingConfigs, setLoadingConfigs] = useState(true);

  const apiProviders = PROVIDERS.filter(p => p.id !== 'auto');

  // Load current provider configuration status on mount
  useEffect(() => {
    async function loadProviders() {
      try {
        const res = await fetch(`${API}/api/translation/providers`, { credentials: 'include' });
        if (!res.ok) return;
        const data: LoadedProviderConfig[] = await res.json();
        const map: Record<string, LoadedProviderConfig> = {};
        for (const cfg of data) map[cfg.provider_id] = cfg;
        setLoadedConfigs(map);
        // Pre-populate enabled toggles from server config
        const enabledMap: Record<string, boolean> = {};
        for (const cfg of data) enabledMap[cfg.provider_id] = cfg.is_enabled;
        setEnabled(enabledMap);
      } catch {}
      finally { setLoadingConfigs(false); }
    }
    loadProviders();
  }, [API]);

  async function saveKey(providerId: string) {
    setSaving(providerId);
    try {
      const res = await fetch(`${API}/api/translation/providers`, {
        method: 'PUT', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider_id: providerId,
          api_key: keys[providerId] || undefined,
          is_enabled: enabled[providerId] ?? true,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setSaved(prev => ({ ...prev, [providerId]: true }));
      // Refresh loaded configs after save
      setLoadedConfigs(prev => ({
        ...prev,
        [providerId]: { ...prev[providerId], provider_id: providerId, is_enabled: enabled[providerId] ?? true, is_configured: keys[providerId] ? true : (prev[providerId]?.is_configured ?? false) },
      }));
      setTimeout(() => setSaved(prev => ({ ...prev, [providerId]: false })), 3000);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(null);
    }
  }

  async function testProvider(providerId: string) {
    setTesting(providerId);
    try {
      const res = await fetch(`${API}/api/translation/providers/${providerId}/health`, { credentials: 'include' });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setTestResults(prev => ({ ...prev, [providerId]: { ...data, id: providerId, name: providerId } }));
    } catch (e: any) {
      setTestResults(prev => ({
        ...prev,
        [providerId]: { id: providerId, name: providerId, is_configured: false, is_enabled: false, error: e.message },
      }));
    } finally {
      setTesting(null);
    }
  }

  const deepLResult = testResults['deepl'];
  const deepLUsage = parseDeepLUsage(deepLResult?.message);
  const deepLConfig = loadedConfigs['deepl'];
  const deepLActive = deepLConfig?.is_configured && deepLConfig?.is_enabled;

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Top bar */}
      <div className="shrink-0 h-14 border-b border-border/60 flex items-center gap-3 px-4">
        <button onClick={onBack} className="h-8 w-8 rounded-lg hover:bg-accent flex items-center justify-center transition-colors">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/20">
            <Zap className="h-3.5 w-3.5 text-primary" />
          </div>
          <div>
            <h1 className="text-sm font-bold leading-tight">Translation Providers</h1>
            <p className="text-[10px] text-muted-foreground leading-tight">Configure API keys for external translation engines</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-2xl mx-auto space-y-4">
          {/* Info banner */}
          <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-start gap-3">
            <Bot className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <div className="text-xs text-muted-foreground space-y-1">
              <p><span className="text-foreground font-semibold">OpenAI GPT-4o</span> is always available via your workspace integration. All other providers need an API key below.</p>
              <p>Keys are encrypted before storage. GPT-4o is always used for DNT enforcement and AI Engineering Review regardless of active provider.</p>
            </div>
          </div>

          {/* ── DeepL Free Activation Card (featured) ──────────────────────── */}
          {!loadingConfigs && (() => {
            const prov = PROVIDERS.find(p => p.id === 'deepl')!;
            const PIcon = prov.icon;
            const isSaving = saving === 'deepl';
            const isTesting = testing === 'deepl';
            const isSaved = saved['deepl'];
            const result = testResults['deepl'];

            return (
              <div className="rounded-2xl border-2 border-emerald-500/40 bg-gradient-to-br from-emerald-500/5 to-sky-500/5 p-5 space-y-4 relative overflow-hidden">
                {/* "Free" ribbon */}
                <div className="absolute top-3 right-3 flex items-center gap-1.5">
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    FREE TIER
                  </span>
                </div>

                <div className="flex items-start gap-3 pr-20">
                  <div className="h-10 w-10 rounded-xl bg-sky-500/10 flex items-center justify-center shrink-0 ring-1 ring-sky-500/20">
                    <PIcon className="h-5 w-5 text-sky-400" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-bold text-foreground">Activate DeepL Free</h3>
                      <span className="text-[9px] px-1.5 py-0.5 rounded border font-semibold text-sky-400 bg-sky-500/10 border-sky-500/20">Best quality</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Industry-leading neural machine translation. 500,000 characters/month at no cost — best quality for Arabic, European, and scientific documents.
                    </p>

                    {/* Status badge */}
                    {deepLActive && !deepLResult && (
                      <div className="mt-2 flex items-center gap-1.5 text-xs text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span className="font-semibold">Active — 500K chars/month free</span>
                        <span className="text-muted-foreground">· Click "Test" to see usage</span>
                      </div>
                    )}
                    {deepLResult && !deepLResult.error && deepLResult.is_configured && (
                      <div className="mt-2 flex items-center gap-1.5 text-xs text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span className="font-semibold">
                          {deepLUsage
                            ? `Active — ${deepLUsage.used.toLocaleString()} / ${deepLUsage.limit.toLocaleString()} chars used`
                            : 'Active — 500K chars/month free'}
                        </span>
                        {deepLResult.latency_ms && (
                          <span className="text-muted-foreground">· {deepLResult.latency_ms}ms</span>
                        )}
                      </div>
                    )}
                    {deepLResult?.error && (
                      <div className="mt-2 flex items-center gap-1.5 text-xs text-red-400">
                        <WifiOff className="h-3.5 w-3.5" />
                        <span>{deepLResult.error}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Signup link */}
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 flex items-center gap-3">
                  <div className="h-7 w-7 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0">
                    <ExternalLink className="h-3.5 w-3.5 text-emerald-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-foreground">Get your free API key</p>
                    <p className="text-[10px] text-muted-foreground">No credit card required · 500K characters/month free forever</p>
                  </div>
                  <a
                    href="https://www.deepl.com/en/pro-api"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="shrink-0 text-xs font-semibold text-emerald-400 hover:text-emerald-300 underline underline-offset-2 flex items-center gap-1"
                  >
                    deepl.com/en/pro-api <ExternalLink className="h-3 w-3" />
                  </a>
                </div>

                {/* Key input */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      placeholder="Paste your DeepL Free API key here…"
                      value={keys['deepl'] || ''}
                      onChange={e => setKeys(prev => ({ ...prev, deepl: e.target.value }))}
                      className="flex-1 h-9 px-3 rounded-lg border border-emerald-500/30 bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
                    />
                    <Button
                      size="sm"
                      className="h-9 gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white border-0"
                      onClick={() => saveKey('deepl')}
                      disabled={isSaving || !keys['deepl']}
                    >
                      {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                       isSaved ? <Check className="h-3.5 w-3.5" /> :
                       <Zap className="h-3.5 w-3.5" />}
                      {isSaved ? 'Saved!' : 'Activate'}
                    </Button>
                  </div>
                  <p className="text-[10px] text-muted-foreground/60 flex items-center gap-1">
                    <Shield className="h-3 w-3" /> Encrypted with Fernet (AES-128-CBC) before storage · DeepL Free keys end in <code className="font-mono">:fx</code>
                  </p>
                </div>

                {/* Toggle + test row */}
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Enabled for auto-routing</span>
                    <button
                      onClick={() => setEnabled(prev => ({ ...prev, deepl: !(prev['deepl'] ?? true) }))}
                      className={`h-5 w-9 rounded-full transition-colors relative ${enabled['deepl'] !== false ? 'bg-emerald-600' : 'bg-muted'}`}
                    >
                      <div className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${enabled['deepl'] !== false ? 'translate-x-4' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                  <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                    onClick={() => testProvider('deepl')} disabled={isTesting}>
                    {isTesting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Activity className="h-3 w-3" />}
                    Test &amp; Check Usage
                  </Button>
                </div>
              </div>
            );
          })()}

          {/* ── Other providers ──────────────────────────────────────────────── */}
          {apiProviders.filter(p => p.id !== 'deepl').map(prov => {
            const PIcon = prov.icon;
            const result = testResults[prov.id];
            const isSaving = saving === prov.id;
            const isTesting = testing === prov.id;
            const isSaved = saved[prov.id];
            const isOpenAI = prov.id === 'openai';
            const cfg = loadedConfigs[prov.id];

            return (
              <div key={prov.id} className="rounded-2xl border border-border bg-card/60 p-5 space-y-4">
                <div className="flex items-start gap-3">
                  <div className={`h-9 w-9 rounded-xl flex items-center justify-center shrink-0 ${isOpenAI ? 'bg-emerald-500/10' : 'bg-primary/5'}`}>
                    <PIcon className={`h-4 w-4 ${prov.iconColor}`} />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-foreground">{prov.label}</h3>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${prov.badgeColor}`}>{prov.badge}</span>
                      {!isOpenAI && cfg?.is_configured && cfg?.is_enabled && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded border font-semibold text-emerald-400 bg-emerald-500/10 border-emerald-500/20">Active</span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{prov.description}</p>
                  </div>
                  {!isOpenAI && (
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs text-muted-foreground">On</span>
                      <button
                        onClick={() => setEnabled(prev => ({ ...prev, [prov.id]: !(prev[prov.id] ?? true) }))}
                        className={`h-5 w-9 rounded-full transition-colors relative ${enabled[prov.id] !== false ? 'bg-primary' : 'bg-muted'}`}
                      >
                        <div className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${enabled[prov.id] !== false ? 'translate-x-4' : 'translate-x-0.5'}`} />
                      </button>
                    </div>
                  )}
                </div>

                {!isOpenAI && (
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">API Key</label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        placeholder={`Enter ${prov.label} API key…`}
                        value={keys[prov.id] || ''}
                        onChange={e => setKeys(prev => ({ ...prev, [prov.id]: e.target.value }))}
                        className="flex-1 h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/50"
                      />
                      <Button size="sm" variant="outline" className="h-9 gap-1.5 text-xs"
                        onClick={() => saveKey(prov.id)} disabled={isSaving}>
                        {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                         isSaved ? <Check className="h-3.5 w-3.5 text-emerald-400" /> :
                         <Lock className="h-3.5 w-3.5" />}
                        {isSaved ? 'Saved!' : 'Save'}
                      </Button>
                    </div>
                    <p className="text-[10px] text-muted-foreground/60 flex items-center gap-1">
                      <Shield className="h-3 w-3" /> Encrypted with Fernet (AES-128-CBC) before storage
                    </p>
                  </div>
                )}

                <div className="flex items-center gap-3">
                  <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs"
                    onClick={() => testProvider(prov.id)} disabled={isTesting}>
                    {isTesting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Activity className="h-3 w-3" />}
                    Test Connection
                  </Button>
                  {result && (
                    <div className={`flex items-center gap-1.5 text-xs ${result.error || !result.is_configured ? 'text-red-400' : 'text-emerald-400'}`}>
                      {result.error || !result.is_configured
                        ? <><WifiOff className="h-3 w-3" /> {result.error || 'Not configured'}</>
                        : <><CheckCircle2 className="h-3 w-3" /> Connected{result.latency_ms ? ` · ${result.latency_ms}ms` : ''}</>
                      }
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          <div className="pt-2">
            <Button variant="outline" className="gap-2" onClick={onBack}>
              <ChevronLeft className="h-4 w-4" /> Back to Translation Studio
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ImagesTab({ projectId, onOpenEditor }: { projectId: string; onOpenEditor: () => void }) {
  const [images, setImages]     = useState<ProjectImageSummary[]>([]);
  const [loading, setLoading]   = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState('');
  const { toast }               = useToast();

  const loadImages = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/translation/projects/${projectId}/images`, { credentials: 'include' });
      if (r.ok) { const d = await r.json(); setImages(d.images ?? []); }
    } catch {}
    setLoading(false);
  }, [projectId]);

  useEffect(() => { loadImages(); }, [loadImages]);

  const analyzeImages = async () => {
    setAnalyzing(true); setProgress('Starting…');
    try {
      const resp = await fetch(`${API}/api/translation/projects/${projectId}/images/analyze`, {
        method: 'POST', credentials: 'include',
      });
      const reader = resp.body?.getReader();
      const dec    = new TextDecoder();
      let buf      = '';
      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n\n'); buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const d = JSON.parse(line.slice(6));
            if (d.type === 'extract_done') setProgress(`Found ${d.found} image${d.found !== 1 ? 's' : ''}…`);
            else if (d.type === 'image_start') setProgress(`Processing ${d.num}/${d.total}…`);
            else if (d.type === 'done') { setProgress(`Done — ${d.with_text} translated`); await loadImages(); }
          } catch {}
        }
      }
    } catch (e: any) {
      toast({ title: 'Analysis failed', description: e.message, variant: 'destructive' });
    } finally { setAnalyzing(false); }
  };

  const doneCount    = images.filter(i => i.status === 'done').length;
  const noTextCount  = images.filter(i => i.status === 'no_text').length;
  const totalRegions = images.reduce((s, i) => s + i.region_count, 0);

  return (
    <div className="flex-1 overflow-auto p-6">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-base font-bold text-foreground flex items-center gap-2">
              <ScanLine className="h-4 w-4 text-fuchsia-400" />
              Diagram & Image Translation
            </h2>
            <p className="text-xs text-muted-foreground mt-1 max-w-xl">
              GPT-4o Vision detects text in diagrams, schematics, and screenshots, translates each label,
              and renders the translated text in the original position with correct alignment and direction.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={loadImages}>
              <RotateCcw className="h-3 w-3" /> Refresh
            </Button>
            <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={analyzeImages} disabled={analyzing}>
              {analyzing
                ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> {progress}</>
                : <><ScanLine className="h-3.5 w-3.5" /> Analyse & Translate Images</>}
            </Button>
            {images.length > 0 && (
              <Button size="sm" variant="outline"
                className="h-8 gap-1.5 text-xs border-fuchsia-500/30 text-fuchsia-400 hover:bg-fuchsia-500/10"
                onClick={onOpenEditor}>
                <ExternalLink className="h-3 w-3" /> Open Image Editor
              </Button>
            )}
          </div>
        </div>

        {/* Stats */}
        {images.length > 0 && (
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Images', value: images.length, color: 'text-foreground' },
              { label: 'Translated', value: doneCount, color: 'text-emerald-400' },
              { label: 'No Text', value: noTextCount, color: 'text-slate-400' },
              { label: 'Regions', value: totalRegions, color: 'text-fuchsia-400' },
            ].map(s => (
              <div key={s.label} className="rounded-xl border border-border bg-card/60 p-3 text-center">
                <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Image grid */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : images.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-border/50 p-16 text-center">
            <div className="h-16 w-16 rounded-2xl bg-fuchsia-500/10 flex items-center justify-center ring-1 ring-fuchsia-500/20 mx-auto mb-4">
              <ImageIcon className="h-8 w-8 text-fuchsia-400/50" />
            </div>
            <h3 className="text-sm font-semibold text-foreground mb-1">No images analysed yet</h3>
            <p className="text-xs text-muted-foreground mb-5 max-w-sm mx-auto">
              Click "Analyse & Translate Images" to extract diagrams and translate embedded text labels.
            </p>
            <Button size="sm" className="gap-1.5" onClick={analyzeImages} disabled={analyzing}>
              {analyzing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ScanLine className="h-3.5 w-3.5" />}
              Analyse Images
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {images.map(img => (
              <div key={img.id}
                className="rounded-xl border border-border bg-card/60 overflow-hidden hover:border-fuchsia-500/30 transition-colors group cursor-pointer"
                onClick={onOpenEditor}>
                <div className="aspect-video bg-muted/30 relative overflow-hidden">
                  {img.has_rendered ? (
                    <img
                      src={`/api/translation/projects/${projectId}/images/${img.id}/rendered`}
                      alt={`Page ${img.doc_page} image ${img.image_index}`}
                      className="w-full h-full object-contain"
                    />
                  ) : img.has_original ? (
                    <img
                      src={`/api/translation/projects/${projectId}/images/${img.id}/original`}
                      alt={`Page ${img.doc_page} image ${img.image_index}`}
                      className="w-full h-full object-contain opacity-40"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <ImageIcon className="h-8 w-8 text-muted-foreground/20" />
                    </div>
                  )}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/25 transition-colors flex items-center justify-center">
                    <span className="opacity-0 group-hover:opacity-100 transition-opacity text-xs font-medium text-white bg-black/70 px-3 py-1 rounded-full">
                      Open Editor
                    </span>
                  </div>
                </div>
                <div className="p-2 flex items-center justify-between gap-1">
                  <div className="min-w-0">
                    <p className="text-[11px] font-medium text-foreground truncate">Pg {img.doc_page} · #{img.image_index + 1}</p>
                    <p className="text-[10px] text-muted-foreground">{img.region_count} region{img.region_count !== 1 ? 's' : ''}</p>
                  </div>
                  <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-semibold border ${IMG_STATUS[img.status] ?? IMG_STATUS.pending}`}>
                    {img.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Downloads */}
        {images.length > 0 && (
          <div className="rounded-xl border border-border bg-card/40 p-4">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Download className="h-3.5 w-3.5" /> Export with Translated Images
            </h3>
            <div className="flex flex-wrap gap-2">
              <a href={`${API}/api/translation/projects/${projectId}/export/zip`} download>
                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10">
                  <Package className="h-3 w-3" /> Full ZIP Package
                </Button>
              </a>
              <a href={`${API}/api/translation/projects/${projectId}/export/quality-report`} download>
                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8 border-sky-500/30 text-sky-400 hover:bg-sky-500/10">
                  <BarChart2 className="h-3 w-3" /> Quality Report (HTML)
                </Button>
              </a>
              <Button size="sm" variant="outline"
                className="gap-1.5 text-xs h-8 border-fuchsia-500/30 text-fuchsia-400 hover:bg-fuchsia-500/10"
                onClick={onOpenEditor}>
                <ExternalLink className="h-3 w-3" /> Full Image Editor
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
