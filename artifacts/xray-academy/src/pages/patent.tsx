import { useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getListResearchOutputsQueryKey } from '@workspace/api-client-react';
import {
  ShieldCheck, Loader2, Copy, Download, Check, FileText,
  Gavel, Building2, Clock, BarChart2, Sparkles, ChevronRight,
  BookOpen, AlertTriangle, TrendingUp, Globe
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── SSE streaming helper ──────────────────────────────────────────────────

const streamResearch = async (
  mode: string,
  topic: string,
  context: string,
  keywords: string[],
  onChunk: (c: string) => void,
  onDone: (id: string, wc: number) => void,
) => {
  const resp = await fetch(`${API}/api/research/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, topic, context: context || null, keywords: keywords.length ? keywords : null }),
    credentials: 'include',
  });
  if (!resp.ok) throw new Error(await resp.text());
  if (!resp.body) throw new Error('No body');
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
        if (d.type === 'chunk') onChunk(d.chunk);
        if (d.type === 'done') onDone(d.output_id, d.word_count);
        if (d.type === 'error') throw new Error(d.error);
      } catch {}
    }
  }
};

// ── Tab definitions ──────────────────────────────────────────────────────

const TABS = [
  { id: 'analysis',     label: 'Prior Art Analysis',     icon: ShieldCheck,    mode: 'patent_analysis'      },
  { id: 'claims',       label: 'Claims Drafting',         icon: Gavel,          mode: 'patent_claims'        },
  { id: 'competitive',  label: 'Competitive Intel',       icon: Building2,      mode: 'competitor_landscape' },
] as const;

type TabId = typeof TABS[number]['id'];

// ── Shared output panel ──────────────────────────────────────────────────

function OutputPanel({
  content,
  isStreaming,
  outputId,
  wordCount,
  onCopy,
}: {
  content: string;
  isStreaming: boolean;
  outputId: string | null;
  wordCount: number;
  onCopy: () => void;
}) {
  if (!content && !isStreaming) return null;

  const exportReport = () => {
    if (outputId) window.open(`/api/export/research/${outputId}`, '_blank');
  };

  const downloadMd = () => {
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'patent-output.md'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card className="border-border mt-6">
      <div className="flex items-center justify-between px-5 py-3 border-b border-border flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold">Generated Output</span>
          {isStreaming && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
          {!isStreaming && wordCount > 0 && (
            <Badge variant="outline" className="font-mono text-[10px]">{wordCount.toLocaleString()} words</Badge>
          )}
        </div>
        {!isStreaming && content && (
          <div className="flex gap-1.5">
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onCopy}><Copy className="h-3 w-3 mr-1" />Copy</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={downloadMd}><Download className="h-3 w-3 mr-1" />.md</Button>
            {outputId && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={exportReport}><Download className="h-3 w-3 mr-1" />PDF Report</Button>}
          </div>
        )}
      </div>
      <CardContent className="p-5">
        <div className="prose prose-sm prose-invert max-w-none text-foreground/90
          prose-headings:text-foreground prose-headings:font-bold
          prose-h1:text-xl prose-h2:text-lg prose-h2:border-b prose-h2:border-border prose-h2:pb-1 prose-h2:mb-3
          prose-h3:text-base prose-h3:text-primary
          prose-p:text-foreground/80 prose-p:leading-relaxed
          prose-strong:text-foreground prose-strong:font-bold
          prose-code:bg-secondary prose-code:text-primary prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs
          prose-pre:bg-secondary prose-pre:border prose-pre:border-border prose-pre:rounded-lg
          prose-blockquote:border-primary prose-blockquote:text-muted-foreground
          prose-table:text-xs prose-th:bg-secondary prose-th:font-semibold
          prose-ul:text-foreground/80 prose-li:text-foreground/80">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          {isStreaming && <span className="animate-pulse inline-block w-2 h-4 bg-primary align-middle ml-1" />}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Main component ───────────────────────────────────────────────────────

export default function PatentPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabId>('analysis');

  // shared form state
  const [topic, setTopic]       = useState('');
  const [field, setField]       = useState('');
  const [context, setContext]   = useState('');
  const [kwInput, setKwInput]   = useState('');
  const [keywords, setKeywords] = useState<string[]>([]);
  const [copied, setCopied]     = useState(false);
  const [error, setError]       = useState<string | null>(null);

  // per-tab output state
  const [outputs, setOutputs] = useState<Record<TabId, string>>({ analysis: '', claims: '', competitive: '' });
  const [streaming, setStreaming] = useState<Record<TabId, boolean>>({ analysis: false, claims: false, competitive: false });
  const [outputIds, setOutputIds] = useState<Record<TabId, string | null>>({ analysis: null, claims: null, competitive: null });
  const [wordCounts, setWordCounts] = useState<Record<TabId, number>>({ analysis: 0, claims: 0, competitive: 0 });
  const outputRef = useRef<HTMLDivElement>(null);

  const isStreaming = streaming[activeTab];
  const currentOutput = outputs[activeTab];
  const currentOutputId = outputIds[activeTab];
  const currentWc = wordCounts[activeTab];

  const addKeyword = () => {
    const kw = kwInput.trim();
    if (kw && !keywords.includes(kw)) setKeywords(prev => [...prev, kw]);
    setKwInput('');
  };

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setError(null);
    setOutputs(prev => ({ ...prev, [activeTab]: '' }));
    setOutputIds(prev => ({ ...prev, [activeTab]: null }));
    setWordCounts(prev => ({ ...prev, [activeTab]: 0 }));
    setStreaming(prev => ({ ...prev, [activeTab]: true }));

    const tab = TABS.find(t => t.id === activeTab)!;
    const fullContext = [field && `Field: ${field}`, context].filter(Boolean).join('\n\n');

    try {
      await streamResearch(
        tab.mode,
        topic,
        fullContext,
        keywords,
        (chunk) => {
          setOutputs(prev => ({ ...prev, [activeTab]: prev[activeTab] + chunk }));
          outputRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
        },
        (id, wc) => {
          setOutputIds(prev => ({ ...prev, [activeTab]: id }));
          setWordCounts(prev => ({ ...prev, [activeTab]: wc }));
          queryClient.invalidateQueries({ queryKey: getListResearchOutputsQueryKey() });
        },
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setStreaming(prev => ({ ...prev, [activeTab]: false }));
    }
  };

  const handleCopy = () => {
    if (!currentOutput) return;
    navigator.clipboard.writeText(currentOutput);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const tabConfig = {
    analysis: {
      title: 'Invention Description',
      placeholder: 'Describe the invention: technical problem solved, proposed solution, key components, method of operation, advantages over prior art...',
      contextLabel: 'Technical field & additional context',
      contextPlaceholder: 'Field of technology, intended market, known prior art references, geographic markets to protect...',
    },
    claims: {
      title: 'Claims Subject-Matter',
      placeholder: 'Describe what the claims should protect: essential technical features, preferred embodiments, key functional elements...',
      contextLabel: 'Prosecution context (optional)',
      contextPlaceholder: 'Target jurisdictions (US/EP/PCT), claim format preferences, results from prior art search...',
    },
    competitive: {
      title: 'Technology / Market Description',
      placeholder: 'Describe the technology space to map: application area, technical approach, geographic market, time period of interest...',
      contextLabel: 'Specific companies or patents to include',
      contextPlaceholder: 'Name specific competitors, focus on particular sub-technologies, time range...',
    },
  };

  const cfg = tabConfig[activeTab];

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-background">
      {/* Header */}
      <div className="bg-card border-b border-border p-6 shrink-0">
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/30">
            <ShieldCheck className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Patent & IP Intelligence</h1>
            <p className="text-sm text-muted-foreground font-mono uppercase tracking-wider">Prior Art · Claims · Competitive Landscape</p>
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="bg-amber-500/5 border-b border-amber-500/20 px-6 py-2.5">
        <p className="text-xs text-amber-600/80 max-w-5xl mx-auto flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          AI-generated analysis — for research and strategic purposes only. Engage a registered patent attorney for formal prosecution.
        </p>
      </div>

      <div className="flex-1 p-6 max-w-5xl mx-auto w-full">
        {/* Tab navigation */}
        <div className="flex gap-1 mb-6 p-1 rounded-xl bg-card/50 border border-border w-fit">
          {TABS.map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const hasOutput = !!outputs[tab.id];
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive ? 'bg-card border border-border shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? 'text-primary' : ''}`} />
                {tab.label}
                {hasOutput && !streaming[tab.id] && (
                  <span className="ml-1 h-1.5 w-1.5 rounded-full bg-emerald-500" />
                )}
                {streaming[tab.id] && (
                  <Loader2 className="ml-1 h-3 w-3 animate-spin text-primary" />
                )}
              </button>
            );
          })}
        </div>

        {/* Tab description */}
        <div className="mb-5 p-4 rounded-xl bg-card/30 border border-border/50 text-sm text-muted-foreground">
          {activeTab === 'analysis' && (
            <div className="flex gap-3 items-start">
              <ShieldCheck className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <span>Perform a comprehensive <strong className="text-foreground">prior art search and patentability analysis</strong>: invention summary, novelty, non-obviousness, FTO assessment, claim drafting guidance, and prosecution strategy recommendations.</span>
            </div>
          )}
          {activeTab === 'claims' && (
            <div className="flex gap-3 items-start">
              <Gavel className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <span>Draft a complete set of <strong className="text-foreground">patent claims</strong> — independent apparatus, method, and system claims plus 10–15 dependent claims covering preferred embodiments, with prosecution notes.</span>
            </div>
          )}
          {activeTab === 'competitive' && (
            <div className="flex gap-3 items-start">
              <TrendingUp className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <span>Generate a <strong className="text-foreground">competitive technology intelligence report</strong>: competitor matrix, technology cluster analysis, prior art timeline, FTO summary, and strategic recommendations for market entry.</span>
            </div>
          )}
        </div>

        {/* Input form */}
        <div className="space-y-4">
          <div>
            <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-semibold mb-1.5 block">
              {cfg.title} <span className="text-primary">*</span>
            </label>
            <Textarea
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder={cfg.placeholder}
              className="min-h-32 bg-card border-border resize-none text-sm"
              disabled={isStreaming}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-semibold mb-1.5 block">
                Technology Field
              </label>
              <Input
                value={field}
                onChange={e => setField(e.target.value)}
                placeholder="X-ray security screening, medical imaging, CT reconstruction..."
                className="bg-card border-border text-sm"
                disabled={isStreaming}
              />
            </div>
            <div>
              <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-semibold mb-1.5 block">
                Keywords
              </label>
              <div className="flex gap-2">
                <Input
                  value={kwInput}
                  onChange={e => setKwInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addKeyword(); } }}
                  placeholder="dual-energy, AI detection..."
                  className="bg-card border-border text-sm"
                  disabled={isStreaming}
                />
                <Button variant="outline" size="sm" onClick={addKeyword} disabled={isStreaming || !kwInput.trim()} className="shrink-0">Add</Button>
              </div>
            </div>
          </div>

          {keywords.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {keywords.map(kw => (
                <Badge key={kw} variant="secondary" className="text-xs cursor-pointer hover:bg-destructive/10 hover:text-destructive hover:border-destructive/20"
                  onClick={() => setKeywords(prev => prev.filter(k => k !== kw))}>
                  {kw} ×
                </Badge>
              ))}
            </div>
          )}

          <div>
            <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-semibold mb-1.5 block">
              {cfg.contextLabel}
            </label>
            <Textarea
              value={context}
              onChange={e => setContext(e.target.value)}
              placeholder={cfg.contextPlaceholder}
              className="min-h-16 bg-card border-border resize-none text-sm"
              disabled={isStreaming}
            />
          </div>

          {error && (
            <Alert className="border-destructive/30 bg-destructive/5">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="text-sm text-destructive">{error}</AlertDescription>
            </Alert>
          )}

          <Button
            onClick={handleGenerate}
            disabled={!topic.trim() || isStreaming}
            className="w-full h-11 font-bold bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            {isStreaming ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Generating {TABS.find(t => t.id === activeTab)?.label}...</>
            ) : (
              <><Sparkles className="h-4 w-4 mr-2" />Generate {TABS.find(t => t.id === activeTab)?.label}</>
            )}
          </Button>
        </div>

        {/* Output panel */}
        <div ref={outputRef}>
          <OutputPanel
            content={currentOutput}
            isStreaming={isStreaming}
            outputId={currentOutputId}
            wordCount={currentWc}
            onCopy={handleCopy}
          />
        </div>

        {/* Quick-start presets */}
        {!currentOutput && !isStreaming && (
          <div className="mt-8">
            <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-3">Quick-start examples</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                { label: 'Dual-energy CT material classification', desc: 'AI-driven K-edge material detection' },
                { label: 'Photon-counting detector array', desc: 'Spectral X-ray imaging system' },
                { label: 'Real-time threat recognition via CNNs', desc: 'Baggage screening algorithm' },
                { label: 'Portable field X-ray device', desc: 'Low-dose handheld inspection tool' },
              ].map(ex => (
                <button key={ex.label} onClick={() => setTopic(ex.label)}
                  className="flex items-start gap-3 p-3 rounded-lg border border-border hover:border-primary/40 hover:bg-primary/5 text-left transition-colors group">
                  <ChevronRight className="h-4 w-4 text-primary shrink-0 mt-0.5 group-hover:translate-x-0.5 transition-transform" />
                  <div>
                    <div className="text-sm font-medium text-foreground">{ex.label}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{ex.desc}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
