import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Lightbulb, Loader2, Copy, Download, Trash2, Check, ChevronRight,
  BookOpen, FileText, Layers, AlertTriangle,
  Sparkles, Clock, Database, Globe, Pencil, History,
  FileDown, Printer, Save, X, RotateCcw, Languages,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ScrollArea } from '@/components/ui/scroll-area';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── Domain catalogue ──────────────────────────────────────────────────────

const DOMAINS = [
  { id: 'cargo_scanner',           label: 'Cargo Scanners',             icon: '📦', desc: 'Large-object pallet & freight inspection' },
  { id: 'vehicle_scanner',         label: 'Vehicle Scanners',           icon: '🚗', desc: 'Drive-through portal vehicle X-ray' },
  { id: 'container_scanner',       label: 'Container Scanners',         icon: '🏗️', desc: 'ISO shipping container & rail car' },
  { id: 'baggage_scanner',         label: 'Baggage Scanners',           icon: '🧳', desc: 'Airport cabin & hold baggage screening' },
  { id: 'ct_xray',                 label: 'CT X-Ray Systems',           icon: '🔬', desc: 'Computed tomography security & industrial' },
  { id: 'backscatter',             label: 'Backscatter Systems',        icon: '🌊', desc: 'Compton backscatter imaging technology' },
  { id: 'dual_energy',             label: 'Dual-Energy Systems',        icon: '⚡', desc: 'Two-beam material discrimination imaging' },
  { id: 'multi_energy',            label: 'Multi-Energy Systems',       icon: '🌈', desc: 'Spectral / multi-energy discrimination' },
  { id: 'photon_counting',         label: 'Photon-Counting Detectors',  icon: '🔵', desc: 'Direct-conversion energy-resolving detectors' },
  { id: 'ai_reconstruction',       label: 'AI Reconstruction',          icon: '🤖', desc: 'Deep learning image quality & reconstruction' },
  { id: 'detector_electronics',    label: 'Detector Electronics',       icon: '💻', desc: 'ASIC readout, signal chain, digitisation' },
  { id: 'dose_optimization',       label: 'Dose Optimization',          icon: '🛡️', desc: 'ALARA dose reduction techniques & algorithms' },
  { id: 'auto_calibration',        label: 'Auto Calibration',           icon: '🎯', desc: 'Self-calibrating detector & system methods' },
  { id: 'image_enhancement',       label: 'Image Enhancement',          icon: '🖼️', desc: 'Noise reduction, sharpening, contrast' },
  { id: 'threat_detection',        label: 'Threat Detection',           icon: '🚨', desc: 'Explosive, weapon & contraband recognition' },
  { id: 'material_discrimination', label: 'Material Discrimination',    icon: '🔍', desc: 'Atomic number & density-based material ID' },
  { id: 'scatter_correction',      label: 'Scatter Correction',         icon: '🌀', desc: 'Anti-scatter grids, algorithms & measurements' },
  { id: 'detector_cooling',        label: 'Detector Cooling',           icon: '❄️', desc: 'Thermal management for detector arrays' },
  { id: 'generator_technology',    label: 'Generator Technology',       icon: '⚙️', desc: 'X-ray tube, anode & high-frequency generators' },
  { id: 'high_voltage',            label: 'High-Voltage Engineering',   icon: '🔋', desc: 'HV power supplies, switching & conditioning' },
  { id: 'mechanical_design',       label: 'Mechanical Design',          icon: '🔧', desc: 'Gantry, conveyor, shielding & motion systems' },
];

const MODES = [
  {
    id: 'patent',
    label: 'Patent Mode',
    icon: FileText,
    color: 'text-blue-400',
    border: 'border-blue-500/30',
    bg: 'bg-blue-500/10',
    desc: '12-section invention disclosure: Title → Problem → Novel Concept → Claims → Comparison',
    sections: 12,
  },
  {
    id: 'research',
    label: 'Research Mode',
    icon: BookOpen,
    color: 'text-violet-400',
    border: 'border-violet-500/30',
    bg: 'bg-violet-500/10',
    desc: '8-section research programme: Proposal → Conference Paper → Methodology → Simulation → Roadmap',
    sections: 8,
  },
  {
    id: 'full',
    label: 'Full Disclosure',
    icon: Layers,
    color: 'text-amber-400',
    border: 'border-amber-500/30',
    bg: 'bg-amber-500/10',
    desc: 'All 20 sections — Patent Mode + Research Mode combined. Full IP + academic package.',
    sections: 20,
  },
];

// ── Language options ───────────────────────────────────────────────────────

const LANGUAGES = [
  { id: 'en',        label: 'English',          labelShort: 'EN'    },
  { id: 'ar',        label: 'العربية',           labelShort: 'AR'    },
  { id: 'bilingual', label: 'English + Arabic', labelShort: 'EN+AR' },
] as const;
type LangId = 'en' | 'ar' | 'bilingual';

const BILINGUAL_LAYOUTS = [
  { id: 'sequential', label: 'Sequential (Arabic then English)' },
  { id: 'sidebyside', label: 'Side-by-Side (two columns)'       },
] as const;
type LayoutId = 'sequential' | 'sidebyside';

// ── SSE streaming helper ──────────────────────────────────────────────────

async function streamInnovation(
  domain: string,
  topic: string,
  mode: string,
  context: string,
  onChunk: (c: string) => void,
  onStart: (outputId: string, chunks: number) => void,
  onDone: (outputId: string, wordCount: number, kbChunks: number) => void,
  onSectionsAppended?: (tail: string) => void,
  onBuildingStatus?: (msg: string) => void,
) {
  const resp = await fetch(`${API}/api/innovation/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain, topic, mode, context: context || null }),
    credentials: 'include',
  });
  if (!resp.ok) throw new Error(await resp.text());
  if (!resp.body) throw new Error('No response body');

  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const d = JSON.parse(line.slice(6));
        if (d.type === 'start')             onStart(d.output_id, d.kb_chunks);
        else if (d.type === 'chunk')        onChunk(d.chunk);
        else if (d.type === 'done')         onDone(d.output_id, d.word_count, d.kb_chunks);
        else if (d.type === 'error')        throw new Error(d.error);
        else if (d.type === 'sections_appended') onSectionsAppended?.(d.tail);
        else if (d.type === 'building_sections') onBuildingStatus?.(d.message);
      } catch (parseErr: any) {
        if (parseErr.message && !parseErr.message.includes('JSON')) throw parseErr;
      }
    }
  }
}

// ── Download helper (POST → blob) ─────────────────────────────────────────

async function downloadBlob(
  url: string,
  body: object,
  filename: string,
): Promise<void> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    credentials: 'include',
  });
  if (!resp.ok) throw new Error(`Download failed: ${resp.statusText}`);
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
}

// ── Domain quick examples ─────────────────────────────────────────────────

function getExamples(domain: string): string[] {
  const MAP: Record<string, string[]> = {
    cargo_scanner:           ['Adaptive beam shaping for heterogeneous cargo density compensation', 'Real-time 3D reconstruction from single-pass linear scan geometry'],
    vehicle_scanner:         ['Autonomous threat zone mapping using multi-view fusion for drive-through portals', 'Dose-adaptive kVp modulation based on vehicle silhouette pre-scan'],
    container_scanner:       ['Passive cooling mega-focal-spot tube for 9 MeV container inspection', 'Distributed detector panel with gap-filling reconstruction for ISO containers'],
    baggage_scanner:         ['Photon-counting CT with sub-millimetre resolution for prohibited item micro-detection', 'Federated learning across airport networks for threat signature sharing'],
    ct_xray:                 ['Helical multi-source CT for security screening with 1-second acquisition', 'Sparse-view reconstruction using physics-informed neural networks'],
    backscatter:             ['Coded-aperture backscatter for 3D surface mapping without forward detector', 'Compton camera concept for stand-off explosive detection'],
    dual_energy:             ['Kilo-voltage switching at 5 kHz for submillimetre registered dual-energy images', 'K-edge subtraction imaging for simultaneous multi-material decomposition'],
    multi_energy:            ['Five-bin photon-counting spectral CT with basis material decomposition', 'Energy-weighted iterative reconstruction for multi-energy security CT'],
    photon_counting:         ['CdTe direct-conversion detector with charge-sharing correction for 200 µm pixels', 'Room-temperature GaAs photon-counting array with integrated ASIC readout'],
    ai_reconstruction:       ['Diffusion model prior for ultra-low-dose CT reconstruction', 'Unrolled network for scatter correction and denoising in a single inference pass'],
    detector_electronics:    ['Low-noise charge-integrating ASIC with adaptive gain switching for wide dynamic range', 'Time-over-threshold readout for energy discrimination in scintillator arrays'],
    dose_optimization:       ['Real-time organ dose tracking with closed-loop kVp/mAs feedback using scout image', 'Automatic collimation using AI body landmark detection to minimise field size'],
    auto_calibration:        ['In-situ flat-field calibration using structured beam modulation without beam interruption', 'Self-referencing gain drift correction using embedded calibration pixels'],
    image_enhancement:       ['Frequency-selective neural denoising preserving fine wire resolution', 'Iterative metal artefact reduction using dual-energy consistency constraints'],
    threat_detection:        ['Multi-task CNN for simultaneous prohibited item localisation and material classification', 'Ensemble threat scoring with uncertainty quantification for false alarm reduction'],
    material_discrimination: ['Compton-to-photoelectric ratio mapping for sub-centimetre material discrimination', 'K-edge imaging with contrast agents for explosives-specific detection'],
    scatter_correction:      ['Beam-stop array scatter estimation using sparse measurements and inpainting', 'Anti-scatter grid with variable pitch optimised for cone-beam geometry'],
    detector_cooling:        ['Thermoelectric micro-cooler array integrated directly on ASIC for CdTe detector', 'Phase-change material thermal buffer for pulsed-mode scanner operation'],
    generator_technology:    ['Distributed multi-focus X-ray tube for simultaneous multi-view acquisition', 'Solid-state high-frequency inverter with 100 kHz switching for sub-millisecond kVp control'],
    high_voltage:            ['Resonant converter topology for ripple-free 160 kV supply at 10 kW', 'Digitally controlled filament supply with closed-loop mA feedback at 0.1% stability'],
    mechanical_design:       ['Rope-less cable-free gantry for mobile field CT using wireless power transfer', 'Self-shielding modular conveyor insert for rapid airport security line reconfiguration'],
  };
  return MAP[domain] || ['Novel X-ray innovation concept for this technology domain'];
}

// ── Main component ────────────────────────────────────────────────────────

export default function InnovationPage() {
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [selectedMode, setSelectedMode] = useState('patent');
  const [topic, setTopic] = useState('');
  const [context, setContext] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const [refPatched, setRefPatched] = useState(false);
  const [buildingStatus, setBuildingStatus] = useState<string | null>(null);
  const [outputId, setOutputId] = useState<string | null>(null);
  const [wordCount, setWordCount] = useState(0);
  const [kbChunks, setKbChunks] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [domainSearch, setDomainSearch] = useState('');

  // Language & translation
  const [language, setLanguage] = useState<LangId>('en');
  const [bilingualLayout, setBilingualLayout] = useState<LayoutId>('sequential');
  const [translatedContent, setTranslatedContent] = useState<string | null>(null);
  const [isTranslating, setIsTranslating] = useState(false);
  const [showBilingualOptions, setShowBilingualOptions] = useState(false);

  // Edit mode
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [versionNote, setVersionNote] = useState('');

  // Version history
  const [versions, setVersions] = useState<any[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [isLoadingVersions, setIsLoadingVersions] = useState(false);

  // Download state
  const [isDownloading, setIsDownloading] = useState<string | null>(null); // 'docx' | 'pdf'

  const outputRef = useRef<HTMLDivElement>(null);

  const domain = DOMAINS.find(d => d.id === selectedDomain);
  const mode = MODES.find(m => m.id === selectedMode)!;

  // ── Content to display (translated vs original) ─────────────────────────
  const displayContent = (language !== 'en' && translatedContent) ? translatedContent : streamContent;
  const isRTL = language === 'ar';
  const needsTranslation = language !== 'en' && !translatedContent && !!outputId && !isStreaming;

  // ── Data fetchers ────────────────────────────────────────────────────────
  const fetchHistory = useCallback(() => {
    fetch(`${API}/api/innovation/history`, { credentials: 'include' })
      .then(r => r.json()).then(setHistory).catch(() => {});
  }, []);

  const fetchVersions = useCallback((id: string) => {
    setIsLoadingVersions(true);
    fetch(`${API}/api/innovation/${id}/versions`, { credentials: 'include' })
      .then(r => r.json()).then(setVersions).catch(() => setVersions([]))
      .finally(() => setIsLoadingVersions(false));
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);
  useEffect(() => { if (outputId) fetchHistory(); }, [outputId, fetchHistory]);
  useEffect(() => {
    if (showVersions && outputId) fetchVersions(outputId);
  }, [showVersions, outputId, fetchVersions]);

  // ── Reset translation when language switches ─────────────────────────────
  useEffect(() => {
    setTranslatedContent(null);
    setShowBilingualOptions(language === 'bilingual');
  }, [language]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!selectedDomain || !topic.trim() || isStreaming) return;
    setError(null);
    setStreamContent('');
    setRefPatched(false);
    setBuildingStatus(null);
    setOutputId(null);
    setWordCount(0);
    setKbChunks(0);
    setTranslatedContent(null);
    setLanguage('en');
    setEditMode(false);
    setIsStreaming(true);

    try {
      await streamInnovation(
        selectedDomain, topic, selectedMode, context,
        (chunk) => {
          setStreamContent(prev => prev + chunk);
          setBuildingStatus(null);
          if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
        },
        (id, chunks) => { setOutputId(id); setKbChunks(chunks); },
        (id, wc, chunks) => { setOutputId(id); setWordCount(wc); setKbChunks(chunks); },
        (tail) => {
          // Mandatory sections 13-17 built by the pipeline — append to display.
          setStreamContent(prev => prev + tail);
          setRefPatched(true);
          setBuildingStatus(null);
          if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
        },
        (msg) => {
          // Pipeline is building the mandatory sections — show status indicator.
          setBuildingStatus(msg);
        },
      );
    } catch (e: any) {
      setError(e.message || 'Generation failed. Please try again.');
    } finally {
      setIsStreaming(false);
      setBuildingStatus(null);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(displayContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDeleteHistory = async (id: string) => {
    await fetch(`${API}/api/innovation/history/${id}`, { method: 'DELETE', credentials: 'include' });
    setHistory(prev => prev.filter(h => h.id !== id));
  };

  const loadFromHistory = (item: any) => {
    setSelectedDomain(item.domain);
    setSelectedMode(item.mode);
    setTopic(item.topic);
    setStreamContent(item.preview || '');
    setOutputId(item.id);
    setWordCount(item.word_count);
    setKbChunks(item.kb_chunks);
    setHistoryOpen(false);
    setLanguage('en');
    setTranslatedContent(null);
    setEditMode(false);
  };

  const handleTranslate = async () => {
    if (!outputId || isTranslating) return;
    setIsTranslating(true);
    setError(null);
    try {
      const resp = await fetch(`${API}/api/innovation/${outputId}/translate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: language, bilingual_layout: bilingualLayout }),
        credentials: 'include',
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setTranslatedContent(data.content);
    } catch (e: any) {
      setError('Translation failed: ' + (e.message || 'Unknown error'));
    } finally {
      setIsTranslating(false);
    }
  };

  // ── Edit mode ─────────────────────────────────────────────────────────────
  const enterEditMode = () => {
    setEditContent(displayContent);
    setEditMode(true);
    setVersionNote('');
  };

  const discardEdit = () => {
    setEditMode(false);
    setVersionNote('');
  };

  const handleSaveDraft = async () => {
    if (!outputId) return;
    setIsSaving(true);
    try {
      const resp = await fetch(`${API}/api/innovation/${outputId}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent }),
        credentials: 'include',
      });
      if (!resp.ok) throw new Error(await resp.text());
      // Update display
      if (language !== 'en') {
        setTranslatedContent(editContent);
      } else {
        setStreamContent(editContent);
      }
      setSavedOk(true);
      setTimeout(() => setSavedOk(false), 2500);
      setEditMode(false);
    } catch (e: any) {
      setError('Save failed: ' + e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveVersion = async () => {
    if (!outputId) return;
    setIsSaving(true);
    try {
      const resp = await fetch(`${API}/api/innovation/${outputId}/save-version`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent, language, note: versionNote || null }),
        credentials: 'include',
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setSavedOk(true);
      setTimeout(() => setSavedOk(false), 2500);
      if (showVersions) fetchVersions(outputId);
      setEditMode(false);
      setVersionNote('');
    } catch (e: any) {
      setError('Save version failed: ' + e.message);
    } finally {
      setIsSaving(false);
    }
  };

  const loadVersion = (ver: any) => {
    if (ver.language === 'ar' || ver.language === 'bilingual') {
      setTranslatedContent(ver.content);
      setLanguage(ver.language as LangId);
    } else {
      setStreamContent(ver.content);
      setLanguage('en');
    }
    setShowVersions(false);
  };

  // ── Download handlers ────────────────────────────────────────────────────
  const slug = topic.slice(0, 40).replace(/[^a-z0-9]/gi, '_');
  const docId = outputId ? outputId.slice(0, 8).toUpperCase() : 'DRAFT';
  const langSuffix = { en: 'EN', ar: 'AR', bilingual: 'Bilingual' }[language];

  const handleDownloadDocx = async () => {
    if (!outputId) return;
    setIsDownloading('docx');
    try {
      await downloadBlob(
        `/api/innovation/${outputId}/export/docx`,
        { lang: language, layout: bilingualLayout, ar_content: translatedContent || null },
        `Invention_${slug}_${docId}_${langSuffix}.docx`,
      );
    } catch (e: any) {
      setError('Word download failed: ' + e.message);
    } finally {
      setIsDownloading(null);
    }
  };

  const handleDownloadPdf = async () => {
    if (!outputId) return;
    setIsDownloading('pdf');
    try {
      await downloadBlob(
        `/api/innovation/${outputId}/export/pdf`,
        { lang: language, layout: bilingualLayout, ar_content: translatedContent || null },
        `Invention_${slug}_${docId}_${langSuffix}.pdf`,
      );
    } catch (e: any) {
      setError('PDF download failed: ' + e.message);
    } finally {
      setIsDownloading(null);
    }
  };

  const handlePrint = () => {
    if (outputId) window.open(`/api/innovation/export/${outputId}`, '_blank');
  };

  const isDone = !isStreaming && streamContent.length > 0;

  const filteredDomains = DOMAINS.filter(d =>
    !domainSearch ||
    d.label.toLowerCase().includes(domainSearch.toLowerCase()) ||
    d.desc.toLowerCase().includes(domainSearch.toLowerCase())
  );

  // ── LANDING: domain picker ────────────────────────────────────────────────

  if (!selectedDomain) {
    return (
      <div className="flex flex-col h-full overflow-y-auto bg-background">
        <div className="bg-gradient-to-br from-background via-primary/5 to-background border-b border-border px-8 py-10">
          <div className="max-w-5xl mx-auto text-center">
            <div className="mb-6 space-y-2">
              <div className="text-xs font-bold uppercase tracking-widest text-primary">Innovation Engine</div>
              <div className="text-xs font-bold uppercase tracking-[0.3em] text-primary/80">Research by</div>
              <div className="text-4xl font-black tracking-tight text-foreground">Mohamed Noaman</div>
              <div className="text-base leading-relaxed text-muted-foreground">
                <div>International Instructor &amp; Researcher</div>
                <div>X-Ray and Security Inspection Systems</div>
              </div>
            </div>
            <p className="text-muted-foreground text-base max-w-2xl mx-auto leading-relaxed">
              Select a technology domain to invent novel engineering concepts grounded in your knowledge base.
              Generates patent disclosures, research proposals, and feasibility analysis.
            </p>
            <div className="flex flex-wrap justify-center gap-3 mt-6">
              {['RAG-grounded', 'Patent-ready output', 'Research proposals', '21 domains', 'Word & PDF export', 'Arabic RTL'].map(b => (
                <Badge key={b} variant="outline" className="text-xs font-mono">{b}</Badge>
              ))}
            </div>
          </div>
        </div>

        <div className="flex-1 p-6 max-w-6xl mx-auto w-full space-y-6">
          <Input
            value={domainSearch}
            onChange={e => setDomainSearch(e.target.value)}
            placeholder="Filter domains…"
            className="bg-card border-border h-10"
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filteredDomains.map(d => (
              <button
                key={d.id}
                onClick={() => setSelectedDomain(d.id)}
                className="group flex items-start gap-4 p-4 rounded-xl border border-border bg-card hover:border-primary/40 hover:bg-primary/5 transition-all text-left"
              >
                <span className="text-2xl leading-none mt-0.5 grayscale group-hover:grayscale-0 transition-all">{d.icon}</span>
                <div className="min-w-0">
                  <div className="font-bold text-sm text-foreground group-hover:text-primary transition-colors">{d.label}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 leading-snug">{d.desc}</div>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground/30 group-hover:text-primary ml-auto shrink-0 mt-0.5" />
              </button>
            ))}
          </div>

          {history.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground font-mono">Recent Inventions</span>
              </div>
              <div className="flex gap-3 overflow-x-auto pb-2">
                {history.slice(0, 6).map(item => (
                  <button key={item.id} onClick={() => loadFromHistory(item)}
                    className="w-56 shrink-0 p-3 rounded-xl border border-border bg-card hover:border-primary/30 transition-all text-left">
                    <div className="text-lg mb-1">{DOMAINS.find(d => d.id === item.domain)?.icon || '🔬'}</div>
                    <div className="text-xs font-bold truncate text-foreground">{item.topic}</div>
                    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                      <Badge variant="outline" className="text-[9px] font-mono px-1.5 py-0 h-4">{item.domain_label}</Badge>
                      <Badge variant="outline" className="text-[9px] font-mono px-1.5 py-0 h-4">{item.mode}</Badge>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1.5 font-mono">{item.word_count.toLocaleString()}w · {new Date(item.created_at).toLocaleDateString()}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── ACTIVE: two-panel generate + output ────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-hidden bg-background">
      <div className="flex flex-1 min-h-0">

        {/* ─ Left panel: controls ─ */}
        <div className="w-72 shrink-0 border-r border-border bg-card/30 flex flex-col overflow-hidden">
          {/* Domain header */}
          <div className="p-4 border-b border-border bg-card shrink-0">
            <button
              onClick={() => { setSelectedDomain(null); setStreamContent(''); setError(null); setEditMode(false); }}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-3"
            >
              <ChevronRight className="h-3 w-3 rotate-180" />Back to domains
            </button>
            <div className="flex items-center gap-3">
              <span className="text-2xl">{domain?.icon}</span>
              <div>
                <h2 className="font-bold text-sm">{domain?.label}</h2>
                <p className="text-[10px] text-muted-foreground leading-tight">{domain?.desc}</p>
              </div>
            </div>
          </div>

          {/* Scrollable controls */}
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-5">
              {/* Mode */}
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-bold mb-2 block">Generation Mode</label>
                <div className="space-y-2">
                  {MODES.map(m => {
                    const MIcon = m.icon;
                    const active = selectedMode === m.id;
                    return (
                      <button
                        key={m.id}
                        onClick={() => setSelectedMode(m.id)}
                        className={`w-full text-left p-3 rounded-lg border transition-all ${active ? `${m.border} ${m.bg}` : 'border-border hover:bg-card/80'}`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <MIcon className={`h-3.5 w-3.5 ${active ? m.color : 'text-muted-foreground'}`} />
                          <span className={`text-xs font-bold ${active ? 'text-foreground' : 'text-muted-foreground'}`}>{m.label}</span>
                          <Badge variant="outline" className="text-[9px] font-mono ml-auto h-4 px-1">{m.sections}§</Badge>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-snug">{m.desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Topic */}
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-bold mb-1.5 block">
                  Invention Topic <span className="text-primary">*</span>
                </label>
                <Textarea
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  placeholder={`Describe the specific innovation…\n\nE.g. "Adaptive dual-energy filtering using real-time material thickness estimation"`}
                  className="min-h-24 bg-background border-border resize-none text-xs"
                  disabled={isStreaming}
                />
              </div>

              {/* Context */}
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-bold mb-1.5 block">Additional Context</label>
                <Textarea
                  value={context}
                  onChange={e => setContext(e.target.value)}
                  placeholder="Prior art, constraints, target specs, regulation context…"
                  className="min-h-14 bg-background border-border resize-none text-xs"
                  disabled={isStreaming}
                />
              </div>

              {/* Quick examples */}
              {!topic && (
                <div>
                  <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-bold mb-2">Quick Examples</p>
                  <div className="space-y-1.5">
                    {getExamples(selectedDomain!).map((ex, i) => (
                      <button
                        key={i}
                        onClick={() => setTopic(ex)}
                        className="w-full text-left p-2.5 rounded-lg border border-border/50 bg-background/50 hover:border-primary/30 hover:bg-primary/5 transition-all text-xs text-muted-foreground hover:text-foreground"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Building mandatory sections status */}
              {buildingStatus && isStreaming && (
                <div className="flex items-center gap-2 text-[10px] text-violet-600 p-2 rounded-lg bg-violet-500/5 border border-violet-500/20">
                  <Loader2 className="h-3 w-3 animate-spin shrink-0" />
                  <span>{buildingStatus}</span>
                </div>
              )}

              {/* Mandatory sections appended notice */}
              {refPatched && !isStreaming && (
                <Alert className="border-emerald-500/30 bg-emerald-500/5">
                  <AlertTriangle className="h-4 w-4 text-emerald-600" />
                  <AlertDescription className="text-xs text-emerald-700">
                    Sections §13–§17 (References, KB Sources, Related Patents, Standards, Revision History) were built by the pipeline and appended to the report.
                  </AlertDescription>
                </Alert>
              )}

              {/* Error */}
              {error && (
                <Alert className="border-destructive/30 bg-destructive/5">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription className="text-xs text-destructive">{error}</AlertDescription>
                </Alert>
              )}

              {/* Generate */}
              <Button
                onClick={handleGenerate}
                disabled={!topic.trim() || isStreaming}
                className="w-full h-10 font-bold text-xs"
              >
                {isStreaming
                  ? <><Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />Generating…</>
                  : <><Sparkles className="h-3.5 w-3.5 mr-2" />Generate Invention</>
                }
              </Button>

              {/* KB indicator */}
              {kbChunks > 0 && (
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground p-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                  <Database className="h-3 w-3 text-emerald-400 shrink-0" />
                  <span>{kbChunks} knowledge base chunks used</span>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* History */}
          {history.length > 0 && (
            <div className="border-t border-border p-3 shrink-0">
              <button
                onClick={() => setHistoryOpen(!historyOpen)}
                className="w-full flex items-center justify-between text-[10px] font-mono uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
              >
                <span className="flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />History ({history.length})
                </span>
                <ChevronRight className={`h-3 w-3 transition-transform ${historyOpen ? 'rotate-90' : ''}`} />
              </button>
              {historyOpen && (
                <div className="mt-2 space-y-1.5 max-h-48 overflow-y-auto">
                  {history.slice(0, 10).map(item => (
                    <div key={item.id} className="flex items-start gap-2 p-2 rounded-lg border border-border/50 bg-background/50 group">
                      <button className="flex-1 text-left" onClick={() => loadFromHistory(item)}>
                        <div className="text-xs font-medium text-foreground leading-tight truncate">{item.topic}</div>
                        <div className="text-[10px] text-muted-foreground font-mono mt-0.5">{item.domain_label} · {item.mode}</div>
                      </button>
                      <button onClick={() => handleDeleteHistory(item.id)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ─ Right panel: output ─ */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

          {/* ── Toolbar ─ */}
          <div className="shrink-0 border-b border-border bg-card/50">

            {/* Row 1: title + status + language selector */}
            <div className="flex items-center justify-between px-5 py-2.5 gap-3 border-b border-border/40">
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-sm font-semibold uppercase tracking-wider text-muted-foreground shrink-0">Innovation Output</span>
                {isStreaming && (
                  <div className="flex items-center gap-1.5 text-xs text-primary">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span className="font-mono truncate">Generating {mode.label}…</span>
                  </div>
                )}
                {isDone && !editMode && (
                  <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs font-mono shrink-0">
                    <Check className="h-3 w-3 mr-1" />{wordCount.toLocaleString()}w · {kbChunks} chunks
                  </Badge>
                )}
                {savedOk && (
                  <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs font-mono shrink-0 animate-in fade-in">
                    <Check className="h-3 w-3 mr-1" />Saved
                  </Badge>
                )}
              </div>

              {/* Language selector */}
              {isDone && !editMode && (
                <div className="flex items-center gap-1.5 shrink-0">
                  <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                  <div className="flex rounded-lg border border-border overflow-hidden text-[10px] font-mono">
                    {LANGUAGES.map(lang => (
                      <button
                        key={lang.id}
                        onClick={() => setLanguage(lang.id as LangId)}
                        className={`px-2.5 py-1.5 transition-colors ${
                          language === lang.id
                            ? 'bg-primary text-primary-foreground font-bold'
                            : 'bg-card text-muted-foreground hover:bg-card/80 hover:text-foreground'
                        }`}
                        title={lang.label}
                      >
                        {lang.labelShort}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Row 2: action buttons */}
            {isDone && (
              <div className="flex items-center gap-2 px-5 py-2 flex-wrap">
                {!editMode ? (
                  <>
                    {/* Translate button */}
                    {needsTranslation && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs border-primary/40 text-primary hover:bg-primary/10"
                        onClick={handleTranslate}
                        disabled={isTranslating}
                      >
                        {isTranslating
                          ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Translating…</>
                          : <><Languages className="h-3 w-3 mr-1" />Translate</>
                        }
                      </Button>
                    )}

                    {/* Bilingual layout selector */}
                    {language === 'bilingual' && translatedContent && (
                      <select
                        value={bilingualLayout}
                        onChange={e => setBilingualLayout(e.target.value as LayoutId)}
                        className="h-7 text-xs bg-card border border-border rounded px-2 text-foreground"
                      >
                        {BILINGUAL_LAYOUTS.map(l => (
                          <option key={l.id} value={l.id}>{l.label}</option>
                        ))}
                      </select>
                    )}

                    <div className="w-px h-5 bg-border mx-0.5" />

                    {/* Copy */}
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleCopy}>
                      {copied ? <Check className="h-3 w-3 mr-1 text-emerald-400" /> : <Copy className="h-3 w-3 mr-1" />}
                      Copy
                    </Button>

                    {/* Markdown */}
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => {
                      const blob = new Blob([displayContent], { type: 'text/markdown' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${topic.slice(0, 40).replace(/[^a-z0-9]/gi, '-')}_${langSuffix}.md`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}>
                      <Download className="h-3 w-3 mr-1" />.md
                    </Button>

                    {/* HTML Report */}
                    {outputId && (
                      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handlePrint}>
                        <FileText className="h-3 w-3 mr-1" />Report
                      </Button>
                    )}

                    <div className="w-px h-5 bg-border mx-0.5" />

                    {/* Word */}
                    {outputId && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs border-blue-500/30 text-blue-400 hover:bg-blue-500/10"
                        onClick={handleDownloadDocx}
                        disabled={isDownloading === 'docx' || (language !== 'en' && !translatedContent)}
                        title={language !== 'en' && !translatedContent ? 'Translate first to download in this language' : ''}
                      >
                        {isDownloading === 'docx'
                          ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Word…</>
                          : <><FileDown className="h-3 w-3 mr-1" />Word</>
                        }
                      </Button>
                    )}

                    {/* PDF */}
                    {outputId && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs border-rose-500/30 text-rose-400 hover:bg-rose-500/10"
                        onClick={handleDownloadPdf}
                        disabled={isDownloading === 'pdf' || (language !== 'en' && !translatedContent)}
                        title={language !== 'en' && !translatedContent ? 'Translate first to download in this language' : ''}
                      >
                        {isDownloading === 'pdf'
                          ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />PDF…</>
                          : <><FileDown className="h-3 w-3 mr-1" />PDF</>
                        }
                      </Button>
                    )}

                    {/* Print */}
                    {outputId && (
                      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handlePrint}>
                        <Printer className="h-3 w-3 mr-1" />Print
                      </Button>
                    )}

                    <div className="w-px h-5 bg-border mx-0.5" />

                    {/* Edit */}
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={enterEditMode}>
                      <Pencil className="h-3 w-3 mr-1" />Edit
                    </Button>

                    {/* Versions */}
                    {outputId && (
                      <Button
                        variant="outline"
                        size="sm"
                        className={`h-7 text-xs ${showVersions ? 'bg-card border-primary/40 text-primary' : ''}`}
                        onClick={() => setShowVersions(v => !v)}
                      >
                        <History className="h-3 w-3 mr-1" />Versions
                        {versions.length > 0 && (
                          <Badge className="ml-1 h-4 px-1 text-[9px] font-mono bg-primary/20 text-primary border-0">
                            {versions.length}
                          </Badge>
                        )}
                      </Button>
                    )}
                  </>
                ) : (
                  /* Edit mode toolbar */
                  <>
                    <span className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                      <Pencil className="h-3 w-3" />Edit Mode
                    </span>
                    <div className="flex-1 mx-2">
                      <Input
                        value={versionNote}
                        onChange={e => setVersionNote(e.target.value)}
                        placeholder="Version note (optional)…"
                        className="h-7 text-xs bg-background border-border"
                      />
                    </div>
                    <Button size="sm" className="h-7 text-xs" onClick={handleSaveDraft} disabled={isSaving}>
                      {isSaving ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}
                      Save Draft
                    </Button>
                    <Button variant="outline" size="sm" className="h-7 text-xs border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                      onClick={handleSaveVersion} disabled={isSaving}>
                      <History className="h-3 w-3 mr-1" />Save Version
                    </Button>
                    <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground" onClick={discardEdit}>
                      <X className="h-3 w-3 mr-1" />Discard
                    </Button>
                  </>
                )}
              </div>
            )}

            {/* Bilingual layout info (non-edit, bilingual, no translation yet) */}
            {isDone && !editMode && language === 'bilingual' && !translatedContent && !isTranslating && (
              <div className="px-5 pb-2 flex items-center gap-2">
                <select
                  value={bilingualLayout}
                  onChange={e => setBilingualLayout(e.target.value as LayoutId)}
                  className="h-7 text-xs bg-card border border-border rounded px-2 text-foreground"
                >
                  {BILINGUAL_LAYOUTS.map(l => (
                    <option key={l.id} value={l.id}>{l.label}</option>
                  ))}
                </select>
                <span className="text-[10px] text-muted-foreground">— then click Translate</span>
              </div>
            )}
          </div>

          {/* ── Content area ─ */}
          <div className="flex flex-1 min-h-0">

            {/* Main output */}
            <div
              ref={outputRef}
              className={`flex-1 min-h-0 overflow-y-auto p-6 md:p-10 ${showVersions ? 'border-r border-border' : ''}`}
            >
              {!streamContent && !isStreaming ? (
                /* Empty state */
                <div className="flex flex-col items-center justify-center text-center gap-5 py-20 opacity-60">
                  <div className="h-24 w-24 rounded-2xl bg-primary/5 flex items-center justify-center ring-1 ring-primary/10">
                    <Lightbulb className="h-12 w-12 text-primary/40" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold tracking-tight mb-2">Ready to Innovate</h3>
                    <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
                      Enter an invention topic and click Generate to produce a full technical disclosure grounded in your knowledge base.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 justify-center max-w-md">
                    {['[ESTABLISHED]', '[HYPOTHESIS]', '[SPECULATIVE]'].map(tag => (
                      <span key={tag} className="px-2 py-1 rounded border border-border/50 font-mono text-[10px] text-muted-foreground/70">{tag}</span>
                    ))}
                  </div>
                </div>
              ) : editMode ? (
                /* Edit mode */
                <div className="max-w-4xl mx-auto space-y-4">
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
                    <Pencil className="h-4 w-4 text-amber-400 shrink-0" />
                    <p className="text-xs text-amber-300">
                      Editing {language !== 'en' ? (language === 'ar' ? 'Arabic' : 'bilingual') : 'English'} version.
                      Use markdown formatting. Save Draft overwrites the current record; Save Version creates a new revision.
                    </p>
                  </div>
                  <Textarea
                    value={editContent}
                    onChange={e => setEditContent(e.target.value)}
                    className="min-h-[600px] font-mono text-xs bg-card border-border resize-y leading-relaxed"
                    dir={isRTL ? 'rtl' : 'ltr'}
                  />
                </div>
              ) : (
                /* Generated content */
                <div className="max-w-4xl mx-auto">
                  {/* Header card */}
                  <div className="mb-6 p-4 rounded-xl border border-border bg-card/50 flex items-center gap-4 flex-wrap">
                    <span className="text-3xl">{domain?.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-muted-foreground font-mono uppercase tracking-widest mb-0.5">
                        {domain?.label} · {mode.label}
                        {language !== 'en' && translatedContent && (
                          <span className="ml-2 text-primary">
                            · {language === 'ar' ? 'العربية' : 'EN + AR'}
                          </span>
                        )}
                      </div>
                      <div className="font-bold text-sm text-foreground leading-snug">{topic}</div>
                    </div>
                    <Badge variant="outline" className={`text-xs font-mono shrink-0 ${mode.color} ${mode.border}`}>
                      {mode.sections} sections
                    </Badge>
                  </div>

                  {/* Translate prompt banner */}
                  {needsTranslation && (
                    <div className="mb-4 p-3 rounded-lg bg-primary/5 border border-primary/20 flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-xs text-primary">
                        <Languages className="h-4 w-4 shrink-0" />
                        <span>
                          {language === 'ar' ? 'Click Translate to generate the Arabic version of this document.' : 'Click Translate to generate the bilingual version.'}
                        </span>
                      </div>
                      <Button size="sm" className="h-7 text-xs shrink-0" onClick={handleTranslate} disabled={isTranslating}>
                        {isTranslating ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Translate'}
                      </Button>
                    </div>
                  )}

                  {/* Translation loading */}
                  {isTranslating && (
                    <div className="mb-4 p-4 rounded-lg bg-primary/5 border border-primary/20 flex items-center gap-3">
                      <Loader2 className="h-4 w-4 text-primary animate-spin shrink-0" />
                      <div>
                        <div className="text-xs font-bold text-primary">Translating…</div>
                        <div className="text-[10px] text-muted-foreground">Professional scientific Arabic translation in progress</div>
                      </div>
                    </div>
                  )}

                  {/* Bilingual side-by-side display */}
                  {language === 'bilingual' && translatedContent && bilingualLayout === 'sidebyside' ? (
                    <div className="grid grid-cols-2 gap-6">
                      {/* Arabic right column */}
                      <div
                        dir="rtl"
                        className="prose prose-sm max-w-none text-right
                          prose-headings:text-foreground prose-headings:font-bold
                          prose-h2:text-base prose-h2:border-b prose-h2:border-border/50 prose-h2:pb-2
                          prose-p:text-foreground/80 prose-p:leading-relaxed
                          prose-ul:text-foreground/80 prose-li:text-foreground/80"
                        style={{ fontFamily: "'Noto Naskh Arabic', Arial, sans-serif" }}
                      >
                        <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-3 text-right">العربية</div>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{translatedContent}</ReactMarkdown>
                      </div>
                      {/* English left column */}
                      <div className="prose prose-sm prose-invert max-w-none
                        prose-headings:text-foreground prose-headings:font-bold
                        prose-h2:text-base prose-h2:border-b prose-h2:border-border/50 prose-h2:pb-2
                        prose-p:text-foreground/80 prose-p:leading-relaxed
                        prose-ul:text-foreground/80 prose-li:text-foreground/80">
                        <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-3">English</div>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamContent}</ReactMarkdown>
                      </div>
                    </div>
                  ) : (
                    /* Standard markdown output */
                    <div
                      dir={isRTL ? 'rtl' : 'ltr'}
                      className={`prose prose-sm prose-invert max-w-none
                        prose-headings:text-foreground prose-headings:font-bold prose-headings:tracking-tight
                        prose-h1:text-2xl prose-h1:font-black prose-h1:text-primary
                        prose-h2:text-lg prose-h2:border-b prose-h2:border-border/50 prose-h2:pb-2 prose-h2:mb-4
                        prose-h3:text-base prose-h3:text-foreground/90
                        prose-p:text-foreground/80 prose-p:leading-relaxed
                        prose-strong:text-foreground prose-strong:font-bold
                        prose-code:bg-secondary/80 prose-code:text-primary prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono
                        prose-pre:bg-card prose-pre:border prose-pre:border-border prose-pre:rounded-xl prose-pre:text-xs
                        prose-blockquote:border-l-primary prose-blockquote:text-muted-foreground prose-blockquote:bg-primary/5 prose-blockquote:rounded-r
                        prose-ul:text-foreground/80 prose-li:text-foreground/80 prose-li:marker:text-primary
                        prose-table:text-xs prose-th:bg-card prose-th:font-bold prose-td:align-top
                        ${isRTL ? 'text-right' : ''}`}
                      style={isRTL ? { fontFamily: "'Noto Naskh Arabic', Arial, sans-serif" } : undefined}
                    >
                      {/* Sequential bilingual: Arabic then English */}
                      {language === 'bilingual' && translatedContent && bilingualLayout === 'sequential' ? (
                        <>
                          <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2" dir="rtl">العربية</div>
                          <div dir="rtl" style={{ fontFamily: "'Noto Naskh Arabic', Arial, sans-serif", textAlign: 'right' }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{translatedContent}</ReactMarkdown>
                          </div>
                          <hr className="my-8 border-border" />
                          <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2" dir="ltr">English</div>
                          <div dir="ltr">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamContent}</ReactMarkdown>
                          </div>
                        </>
                      ) : (
                        <>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayContent}</ReactMarkdown>
                          {isStreaming && (
                            <span className="inline-block w-2 h-5 bg-primary rounded-sm animate-pulse align-middle ml-1" />
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ── Version history panel ─ */}
            {showVersions && outputId && (
              <div className="w-72 shrink-0 flex flex-col overflow-hidden bg-card/30">
                <div className="p-3 border-b border-border flex items-center justify-between shrink-0">
                  <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground font-mono flex items-center gap-1.5">
                    <History className="h-3.5 w-3.5" />Version History
                  </span>
                  <button onClick={() => setShowVersions(false)} className="text-muted-foreground hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                <ScrollArea className="flex-1">
                  <div className="p-3 space-y-2">
                    {isLoadingVersions ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : versions.length === 0 ? (
                      <div className="text-center py-8">
                        <History className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                        <p className="text-xs text-muted-foreground">No versions saved yet.</p>
                        <p className="text-[10px] text-muted-foreground/70 mt-1">Use Edit → Save Version to create one.</p>
                      </div>
                    ) : (
                      versions.map(ver => (
                        <div key={ver.id} className="p-3 rounded-lg border border-border bg-background/50 space-y-1.5">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1.5">
                              <Badge variant="outline" className="text-[9px] font-mono px-1.5 py-0 h-4">
                                v{ver.version_num}
                              </Badge>
                              <Badge variant="outline" className="text-[9px] font-mono px-1.5 py-0 h-4 uppercase">
                                {ver.language}
                              </Badge>
                            </div>
                            <button
                              onClick={() => loadVersion(ver)}
                              className="text-[10px] text-primary hover:underline font-mono"
                            >
                              <RotateCcw className="h-3 w-3 inline mr-0.5" />Load
                            </button>
                          </div>
                          {ver.note && (
                            <p className="text-[10px] text-foreground/80 italic">{ver.note}</p>
                          )}
                          <div className="text-[9px] text-muted-foreground font-mono">
                            {ver.word_count.toLocaleString()}w · {new Date(ver.created_at).toLocaleString()}
                          </div>
                          <p className="text-[10px] text-muted-foreground leading-snug line-clamp-2 opacity-60">
                            {ver.preview}…
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </ScrollArea>

                {/* Save current as version quick action */}
                {!editMode && isDone && (
                  <div className="p-3 border-t border-border shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full h-8 text-xs"
                      onClick={async () => {
                        if (!outputId) return;
                        const resp = await fetch(`${API}/api/innovation/${outputId}/save-version`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ content: displayContent, language, note: 'Quick save' }),
                          credentials: 'include',
                        });
                        if (resp.ok) fetchVersions(outputId);
                      }}
                    >
                      <Save className="h-3 w-3 mr-1.5" />Save Current as Version
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
