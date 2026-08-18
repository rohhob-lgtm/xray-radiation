import { useState, useRef, useEffect } from 'react';
import { useLocation } from 'wouter';
import { useListResearchModes, useListResearchOutputs, useDeleteResearchOutput, getListResearchOutputsQueryKey } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { 
  FlaskConical, Loader2, Copy, Download, Trash2, Check, X, FileText, ChevronDown, ChevronUp, ChevronRight,
  FileType2, Globe
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Card } from '@/components/ui/card';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

const DEPTH_OPTIONS = [
  { value: 'research_brief', label: 'Research Brief' },
  { value: 'technical_paper', label: 'Technical Paper' },
  { value: 'full_journal_paper', label: 'Full Journal Paper' },
  { value: 'technical_dossier', label: 'Technical Dossier' },
];

const extractPaperTitle = (content: string, fallback: string) => {
  const match = content.match(/^#\s+(.+)$/m);
  return (match?.[1] || fallback).trim();
};

const sanitizeFilename = (name: string) => name.replace(/[\\/:*?"<>|]+/g, '_').replace(/\s+/g, ' ').trim();

const filenameFromDisposition = (value: string | null, fallback: string) => {
  if (!value) return fallback;
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(value);
  return decodeURIComponent(m?.[1] || m?.[2] || fallback);
};

const streamResearch = async (
  mode: string, 
  topic: string, 
  context: string, 
  keywords: string[], 
  depth: string, 
  wordCount: number | null, 
  onChunk: (c: string) => void, 
  onDone: (payload: Record<string, any>) => void
) => {
  const resp = await fetch(`${API}/api/research/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      mode, 
      topic, 
      context: context || null, 
      keywords: keywords.length ? keywords : null, 
      depth,
      word_count: wordCount || null 
    }),
    credentials: 'include',
  });
  if (!resp.ok) {
    let msg = `Server error ${resp.status}`;
    try { msg = (await resp.json()).detail || msg; } catch { try { msg = await resp.text() || msg; } catch {} }
    throw new Error(msg);
  }
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
      // Parse JSON separately so malformed lines are skipped without swallowing real errors
      let d: Record<string, any>;
      try { d = JSON.parse(line.slice(6)); } catch { continue; }
      if (d.type === 'chunk') onChunk(d.chunk);
      if (d.type === 'done') onDone(d);
      if (d.type === 'error') throw new Error(d.error || 'Generation failed');
    }
  }
};

export default function ResearchPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useState(new URLSearchParams(window.location.search));
  const initialMode = searchParams.get('mode') || 'paper_ieee';

  const { data: modesData } = useListResearchModes();
  const { data: outputs } = useListResearchOutputs();
  const { mutate: deleteOutput } = useDeleteResearchOutput({
    mutation: {
      onSuccess: () => queryClient.invalidateQueries({ queryKey: getListResearchOutputsQueryKey() })
    }
  });

  const fallbackModes = [
    { id: 'paper_ieee', label: 'IEEE Paper', desc: 'Standard format' },
    { id: 'paper_elsevier', label: 'Elsevier Paper', desc: 'Journal format' },
    { id: 'literature_review', label: 'Literature Review', desc: 'Academic synth' },
    { id: 'research_ideas', label: 'Research Ideas', desc: 'Novel concepts' },
    { id: 'research_gaps', label: 'Gap Analysis', desc: 'Missing tech' },
    { id: 'experiment_plan', label: 'Experiment Plan', desc: 'Methodology' },
    { id: 'security_algorithm', label: 'Security Algo', desc: 'Detector design' }
  ];

  const displayModes = modesData?.map(m => {
    const fb = fallbackModes.find(f => f.id === m.id);
    return { ...m, desc: fb?.desc || 'Research task' };
  }) || fallbackModes;

  const [selectedMode, setSelectedMode] = useState(initialMode);
  const [topic, setTopic] = useState('');
  const [context, setContext] = useState('');
  const [keywordInput, setKeywordInput] = useState('');
  const [keywords, setKeywords] = useState<string[]>([]);
  const [wordCount, setWordCount] = useState<number | ''>('');
  const [outputDepth, setOutputDepth] = useState('full_journal_paper');
  const [optionsOpen, setOptionsOpen] = useState(false);

  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [currentWordCount, setCurrentWordCount] = useState(0);
  const [currentOutputId, setCurrentOutputId] = useState<string | null>(null);
  const [isDone, setIsDone] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isDownloading, setIsDownloading] = useState<'docx' | 'pdf' | null>(null);
  const [kbChunks, setKbChunks] = useState(0);
  const [genError, setGenError] = useState('');
  const [evidenceArtifacts, setEvidenceArtifacts] = useState<Record<string, any> | null>(null);
  const [activeProviderName, setActiveProviderName] = useState<string>('');

  const outputRef = useRef<HTMLDivElement>(null);
  const outputPanelRef = useRef<HTMLDivElement>(null);

  const handleAddKeyword = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const kw = keywordInput.trim().replace(/,$/, '');
      if (kw && !keywords.includes(kw)) {
        setKeywords([...keywords, kw]);
      }
      setKeywordInput('');
    }
  };

  const removeKeyword = (kw: string) => {
    setKeywords(keywords.filter(k => k !== kw));
  };

  useEffect(() => {
    if (isStreaming) {
      const words = streamingContent.trim().split(/\s+/).filter(w => w.length > 0).length;
      setCurrentWordCount(words);
      if (outputRef.current) {
        outputRef.current.scrollTop = outputRef.current.scrollHeight;
      }
    }
  }, [streamingContent, isStreaming]);

  const loadActiveProvider = async () => {
    const response = await fetch(`${API}/api/providers`, {
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
    });
    if (!response.ok) {
      throw new Error('Failed to load active provider');
    }
    const rows = (await response.json()) as Array<Record<string, any>>;
    const active = rows.find((p) => Boolean(p?.is_active));
    const id = String(active?.id || '').trim();
    const name = String(active?.name || '').trim();
    setActiveProviderName(name);
    return { id, name };
  };

  useEffect(() => {
    void loadActiveProvider().catch(() => {
      setActiveProviderName('');
    });
  }, []);

  const handleGenerate = async () => {
    if (!topic.trim() || isStreaming) return;
    setIsStreaming(true);
    setIsDone(false);
    setStreamingContent('');
    setCurrentWordCount(0);
    setCopied(false);
    setGenError('');
    setEvidenceArtifacts(null);

    try {
      const active = await loadActiveProvider();
      if (!active.id || active.id === 'mock') {
        setIsStreaming(false);
        setGenError('No LLM configured. Activate Gemini or another real provider in Settings.');
        return;
      }
    } catch {
      setIsStreaming(false);
      setGenError('Could not verify active provider. Please refresh and try again.');
      return;
    }

    // On mobile, scroll the output panel into view immediately
    setTimeout(() => {
      outputPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 80);

    try {
      await streamResearch(
        selectedMode,
        topic,
        context,
        keywords,
        outputDepth,
        wordCount === '' ? null : Number(wordCount),
        (chunk) => setStreamingContent(prev => prev + chunk),
        (payload) => {
          setIsStreaming(false);
          setIsDone(true);
          if (payload.content) setStreamingContent(payload.content);
          setCurrentWordCount(payload.word_count || payload.content?.split(/\s+/).filter(Boolean).length || 0);
          setCurrentOutputId(payload.output_id || payload.run_id || null);
          setKbChunks(payload.kb_chunks || 0);
          setEvidenceArtifacts(payload.artifacts || null);
          queryClient.invalidateQueries({ queryKey: getListResearchOutputsQueryKey() });
        }
      );
    } catch (e: any) {
      console.error(e);
      setIsStreaming(false);
      setGenError(e?.message || 'Generation failed. Please try again.');
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(streamingContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const paperTitle = sanitizeFilename(extractPaperTitle(streamingContent, topic || selectedModeLabel));
    const blob = new Blob([streamingContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${paperTitle}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadBlob = async (outputId: string, type: 'docx' | 'pdf') => {
    setIsDownloading(type);
    setGenError('');
    try {
      const ext = type === 'docx' ? 'docx' : 'pdf';
      const resp = await fetch(`${API}/api/research/outputs/${outputId}/export/${type}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang: 'en', layout: 'sequential' }),
        credentials: 'include',
      });
      if (!resp.ok) {
        const bodyText = await resp.text();
        let message = `Download failed (${resp.status}).`;
        try {
          const parsed = JSON.parse(bodyText);
          const detail = parsed?.detail;
          // Backend only ever sends one plain sentence here (see
          // _enforce_publication_readiness) — no scores or issue lists are
          // exposed to the UI by design.
          if (typeof detail === 'string') {
            message = detail;
          } else if (detail?.message) {
            message = detail.message;
          }
        } catch {
          // Body wasn't JSON — fall back to the generic status-based message above.
        }
        throw new Error(message);
      }
      const blob = await resp.blob();
      const headerName = filenameFromDisposition(resp.headers.get('content-disposition'), `${sanitizeFilename(extractPaperTitle(streamingContent, topic || selectedModeLabel))}.${ext}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = headerName.endsWith(`.${ext}`) ? headerName : `${headerName}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      setGenError(e instanceof Error ? e.message : 'Download failed.');
    } finally {
      setIsDownloading(null);
    }
  };

  const selectedModeLabel = displayModes.find(m => m.id === selectedMode)?.label || 'Research';

  return (
    // On mobile: flex-col + overflow-y-auto so the output panel is reachable by scrolling.
    // On desktop (md+): flex-row + overflow-hidden for the fixed two-column layout.
    <div className="flex bg-background flex-col md:flex-row md:h-full md:overflow-hidden overflow-y-auto">
      {/* Left Panel: Config */}
      <div className="w-full md:w-[360px] md:shrink-0 border-r border-border bg-card/30 flex flex-col md:h-full z-10 shadow-[4px_0_24px_-10px_rgba(0,0,0,0.2)]">
        <div className="p-4 border-b border-border bg-card">
          <h2 className="font-bold text-lg flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-research" />
            Research Studio
          </h2>
          <p className="text-xs text-muted-foreground uppercase font-mono tracking-wider mt-1">Generative Academic Output</p>
          {activeProviderName ? (
            <p className="text-[10px] text-muted-foreground font-mono uppercase tracking-wider mt-2">
              Active Engine: {activeProviderName}
            </p>
          ) : null}
        </div>

        <ScrollArea className="flex-1 p-4">
          <div className="space-y-6">
            {/* Mode Selection */}
            <div>
              <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-3 block">Research Mode</label>
              <div className="grid grid-cols-2 gap-2">
                {displayModes.map(m => (
                  <button
                    key={m.id}
                    onClick={() => setSelectedMode(m.id)}
                    className={`text-left p-2 rounded-lg border transition-all ${
                      selectedMode === m.id 
                        ? 'bg-research/10 border-research text-foreground shadow-[0_0_10px_-2px_rgba(245,158,11,0.2)]' 
                        : 'bg-background border-border/50 text-muted-foreground hover:border-border hover:bg-card'
                    }`}
                  >
                    <div className={`font-semibold text-xs ${selectedMode === m.id ? 'text-research' : ''}`}>{m.label}</div>
                    <div className="text-[10px] opacity-70 mt-0.5 truncate">{m.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Topic Input */}
            <div>
              <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 flex items-center justify-between">
                Research Topic <span className="text-research">*</span>
              </label>
              <Textarea 
                placeholder="Enter your research topic, question, or hypothesis..."
                className="min-h-[100px] resize-none bg-background focus-visible:ring-research"
                value={topic}
                onChange={e => setTopic(e.target.value)}
              />
            </div>

            {/* Advanced Options */}
            <Collapsible open={optionsOpen} onOpenChange={setOptionsOpen} className="border border-border/50 rounded-lg bg-background/50 overflow-hidden">
              <CollapsibleTrigger className="flex items-center justify-between w-full p-3 text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground hover:bg-card/50 transition-colors">
                Advanced Parameters
                {optionsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </CollapsibleTrigger>
              <CollapsibleContent className="p-3 pt-0 space-y-4 border-t border-border/50 mt-1">
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1.5 block">Keywords & Topics</label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {keywords.map(kw => (
                      <Badge key={kw} variant="secondary" className="bg-card border-border text-xs px-2 py-0 h-6 gap-1 pr-1">
                        {kw}
                        <div role="button" onClick={() => removeKeyword(kw)} className="hover:bg-destructive/20 rounded-full p-0.5 text-muted-foreground hover:text-destructive transition-colors">
                          <X className="h-3 w-3" />
                        </div>
                      </Badge>
                    ))}
                  </div>
                  <Input 
                    placeholder="Type keyword and press Enter..." 
                    className="h-8 text-xs bg-background"
                    value={keywordInput}
                    onChange={e => setKeywordInput(e.target.value)}
                    onKeyDown={handleAddKeyword}
                  />
                </div>
                
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1.5 block">Target Word Count</label>
                  <Input 
                    type="number" 
                    placeholder="e.g. 3000 (optional)" 
                    className="h-8 text-xs bg-background"
                    value={wordCount}
                    onChange={e => setWordCount(e.target.value === '' ? '' : Number(e.target.value))}
                  />
                </div>

                <div>
                  <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1.5 block">Output Depth</label>
                  <select
                    className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs"
                    value={outputDepth}
                    onChange={e => setOutputDepth(e.target.value)}
                  >
                    {DEPTH_OPTIONS.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1.5 block">Additional Context</label>
                  <Textarea 
                    placeholder="Methodology notes, specific sources to include..." 
                    className="min-h-[60px] text-xs resize-none bg-background"
                    value={context}
                    onChange={e => setContext(e.target.value)}
                  />
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-border bg-card space-y-2">
          {genError && (
            <div className="flex items-start gap-2 px-3 py-2 bg-destructive/10 border border-destructive/30 rounded-lg text-xs text-destructive">
              <span className="flex-1 leading-snug whitespace-pre-line">{genError}</span>
              <button onClick={() => setGenError('')} className="shrink-0 opacity-70 hover:opacity-100 mt-0.5">
                <X className="h-3 w-3" />
              </button>
            </div>
          )}
          <Button 
            className={`w-full h-12 font-bold transition-all shadow-lg ${
              isStreaming 
                ? 'bg-research/20 text-research cursor-not-allowed'
                : !topic.trim()
                  ? 'bg-muted text-muted-foreground cursor-not-allowed opacity-60'
                  : 'bg-research hover:bg-research/90 text-research-foreground'
            }`}
            onClick={handleGenerate}
            disabled={!topic.trim() || isStreaming}
          >
            {isStreaming ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Generating... ({currentWordCount}w)
              </>
            ) : !topic.trim() ? (
              'Enter a topic to generate'
            ) : (
              `Generate ${selectedModeLabel}`
            )}
          </Button>
        </div>
      </div>

      {/* Right Panel: Output — on mobile gets min-height so content is visible without needing scroll */}
      <div ref={outputPanelRef} className="flex-1 flex flex-col min-w-0 bg-background relative min-h-[60vh] md:min-h-0">
        {/* Output Header */}
        <div className="h-14 border-b border-border bg-card/50 flex items-center justify-between px-4 shrink-0 backdrop-blur-sm sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Output Console</span>
            {(isStreaming || isDone) && (
              <Badge variant="outline" className="font-mono text-xs bg-background/50">
                {currentWordCount} words
              </Badge>
            )}
          </div>
          <div className="flex gap-2 flex-wrap">
            {isDone && (
              <>
                <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/20 px-3">
                  <Check className="h-3 w-3 mr-1" /> Saved
                </Badge>
                {kbChunks > 0 && (
                  <Badge variant="outline" className="font-mono text-xs bg-background/50 border-blue-500/30 text-blue-400">
                    {kbChunks} KB sources
                  </Badge>
                )}
                <Button variant="outline" size="sm" className="h-8 border-border/50 hover:bg-card" onClick={handleCopy}>
                  {copied ? <Check className="h-4 w-4 mr-2 text-emerald-500" /> : <Copy className="h-4 w-4 mr-2" />}
                  Copy
                </Button>
                <Button variant="outline" size="sm" className="h-8 border-border/50 hover:bg-card" onClick={handleDownload}>
                  <Download className="h-4 w-4 mr-2" />
                  .md
                </Button>
                {currentOutputId && (
                  <>
                    <Button
                      variant="outline" size="sm"
                      className="h-8 border-border/50 hover:bg-card"
                      onClick={() => window.open(`/api/export/research/${currentOutputId}`, '_blank')}
                    >
                      <Globe className="h-4 w-4 mr-2" />
                      HTML
                    </Button>
                    <Button
                      variant="outline" size="sm"
                      className="h-8 border-blue-500/30 text-blue-400 hover:bg-blue-500/10 hover:border-blue-500/50"
                      onClick={() => downloadBlob(currentOutputId, 'docx')}
                      disabled={isDownloading !== null}
                    >
                      {isDownloading === 'docx'
                        ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        : <FileType2 className="h-4 w-4 mr-2" />}
                      Word
                    </Button>
                    <Button
                      variant="outline" size="sm"
                      className="h-8 border-rose-500/30 text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/50"
                      onClick={() => downloadBlob(currentOutputId, 'pdf')}
                      disabled={isDownloading !== null}
                    >
                      {isDownloading === 'pdf'
                        ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        : <FileText className="h-4 w-4 mr-2" />}
                      PDF
                    </Button>
                  </>
                )}
              </>
            )}
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-auto bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]" ref={outputRef}>
          {!isStreaming && !isDone && !streamingContent ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-8 animate-in fade-in duration-700">
              <div className="h-20 w-20 rounded-full bg-research/5 flex items-center justify-center mb-6 ring-1 ring-research/20">
                <FileText className="h-8 w-8 text-research/50" />
              </div>
              <h3 className="text-xl font-bold tracking-tight mb-2">Awaiting Parameters</h3>
              <p className="text-sm text-muted-foreground max-w-sm">Select a research mode and enter your topic on the left to begin generation.</p>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto p-6 md:p-10">
              <div className="prose prose-invert max-w-none prose-headings:font-bold prose-headings:tracking-tight prose-a:text-research prose-p:leading-relaxed prose-pre:bg-card prose-pre:border prose-pre:border-border font-sans">
                {/* 
                  Ideally we'd use react-markdown here, but using a pre-formatted approach
                  that respects whitespace for simplicity, or just setting raw text since it's md.
                */}
                <div className="whitespace-pre-wrap font-sans text-sm md:text-base leading-relaxed text-foreground/90">
                  {streamingContent}
                  {isStreaming && <span className="inline-block w-2 h-4 bg-research ml-1 animate-pulse align-middle" />}
                </div>
              </div>
            </div>
          )}

          {evidenceArtifacts && (
            <div className="max-w-4xl mx-auto px-6 pb-6 md:px-10">
              <Collapsible className="border border-border/60 bg-card/30 rounded-lg">
                <CollapsibleTrigger className="w-full px-4 py-3 flex items-center justify-between text-left">
                  <span className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Evidence Explorer</span>
                  <ChevronRight className="h-4 w-4" />
                </CollapsibleTrigger>
                <CollapsibleContent className="px-4 pb-4 space-y-4 text-xs">
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Evidence Sources</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.unified_sources || evidenceArtifacts.sources_accepted || []).length} total evidence entries</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Accepted Sources</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.sources_accepted || []).length}</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Rejected Sources</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.sources_rejected || []).length}</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Literature Matrix</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.literature_matrix || []).length} rows</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Research Gap Matrix</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.research_gap_matrix || []).length} rows</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Technology Timeline</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.scientific_analysis?.technology_evolution_timeline || []).length} points</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Standards Used</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.unified_sources || []).filter((s: any) => ['standard', 'regulator'].includes(s?.source_type)).length}</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Patents Used</div>
                    <div className="text-foreground/80">{(evidenceArtifacts.unified_sources || []).filter((s: any) => s?.source_type === 'patent').length}</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">Knowledge Base Contribution</div>
                    <div className="text-foreground/80">{evidenceArtifacts.source_transparency?.knowledge_base_contribution?.supplementary_role || 'Supplementary only'}</div>
                  </div>
                  <div>
                    <div className="font-semibold text-muted-foreground mb-1">External Evidence Contribution</div>
                    <div className="text-foreground/80">
                      {(evidenceArtifacts.source_transparency?.external_evidence_contribution?.external_sources_accepted ?? 0)} accepted external sources
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </div>
          )}
        </div>

        {/* History Footer Bar (collapsible/drawer could be nice, but simple fixed bar is good) */}
        {outputs && outputs.length > 0 && (
          <div className="border-t border-border bg-card shrink-0 p-0">
            <Collapsible>
              <CollapsibleTrigger className="flex items-center justify-between w-full px-4 py-2 text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground hover:bg-muted/50 transition-colors">
                <span className="flex items-center gap-2">
                  <FileText className="h-3.5 w-3.5" /> Recent Outputs ({outputs.length})
                </span>
                <ChevronUp className="h-4 w-4" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="p-3 pt-0 flex gap-3 overflow-x-auto pb-3">
                  {outputs.slice(0, 10).map(out => (
                    <Card key={out.id} className="w-[280px] shrink-0 bg-background/50 border-border/50 p-3 hover:border-research/30 transition-colors group cursor-pointer" onClick={() => {
                      setStreamingContent(out.content);
                      setIsDone(true);
                      setSelectedMode(out.mode);
                      setCurrentWordCount(out.word_count);
                      setCurrentOutputId(out.id);
                      setEvidenceArtifacts(null);
                    }}>
                      <div className="flex justify-between items-start mb-2">
                        <Badge variant="outline" className="text-[10px] uppercase font-mono px-1.5 py-0 h-5">
                          {out.mode_label || out.mode}
                        </Badge>
                        <div className="flex gap-0.5 opacity-0 group-hover:opacity-100">
                          <Button variant="ghost" size="icon" className="h-5 w-5 text-muted-foreground hover:text-primary" onClick={(e) => {
                            e.stopPropagation();
                            window.open(`/api/export/research/${out.id}`, '_blank');
                          }}>
                            <Download className="h-3 w-3" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-5 w-5 text-muted-foreground hover:text-destructive hover:bg-destructive/10" onClick={(e) => {
                            e.stopPropagation();
                            deleteOutput({ outputId: out.id });
                          }}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                      <div className="text-sm font-semibold truncate mb-1" title={out.topic}>{out.topic}</div>
                      <div className="text-[10px] text-muted-foreground font-mono flex justify-between">
                        <span>{new Date(out.created_at).toLocaleDateString()}</span>
                        <span>{out.word_count}w</span>
                      </div>
                    </Card>
                  ))}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        )}
      </div>
    </div>
  );
}
