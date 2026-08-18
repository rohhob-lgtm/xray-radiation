import { useState, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useListResearchOutputs, getListResearchOutputsQueryKey } from '@workspace/api-client-react';
import { FileText, Cpu, GraduationCap, Loader2, Copy, Download, Check, X, FileBarChart } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import TrainingCourseReportPanel from '@/components/training-course-report/TrainingCourseReportPanel';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

const streamResearch = async (
  mode: string,
  topic: string,
  context: string,
  keywords: string[],
  onChunk: (c: string) => void,
  onDone: (id: string, wc: number) => void
) => {
  const resp = await fetch(`${API}/api/research/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mode,
      topic,
      context: context || null,
      keywords: keywords.length ? keywords : null,
    }),
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

export default function ReportsPage() {
  const queryClient = useQueryClient();
  const { data: outputs } = useListResearchOutputs();

  const reportOutputs = outputs?.filter(o => o.mode === 'technical_report' || o.mode === 'security_algorithm') || [];

  const [activeTab, setActiveTab] = useState('technical_report');

  // Technical Report State
  const [reportTitle, setReportTitle] = useState('');
  const [reportScope, setReportScope] = useState('');
  const [systemDesc, setSystemDesc] = useState('');
  const [reportKeywords, setReportKeywords] = useState<string[]>([]);
  const [reportKwInput, setReportKwInput] = useState('');

  // Algorithm Design State
  const [algoName, setAlgoName] = useState('');
  const [algoPurpose, setAlgoPurpose] = useState('');
  const [algoDomain, setAlgoDomain] = useState('');
  const [algoKeywords, setAlgoKeywords] = useState<string[]>([]);
  const [algoKwInput, setAlgoKwInput] = useState('');

  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [currentWordCount, setCurrentWordCount] = useState(0);
  const [isDone, setIsDone] = useState(false);
  const [copied, setCopied] = useState(false);

  const outputRef = useRef<HTMLDivElement>(null);

  const handleAddKeyword = (type: 'report' | 'algo', e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      if (type === 'report') {
        const kw = reportKwInput.trim().replace(/,$/, '');
        if (kw && !reportKeywords.includes(kw)) setReportKeywords([...reportKeywords, kw]);
        setReportKwInput('');
      } else {
        const kw = algoKwInput.trim().replace(/,$/, '');
        if (kw && !algoKeywords.includes(kw)) setAlgoKeywords([...algoKeywords, kw]);
        setAlgoKwInput('');
      }
    }
  };

  const removeKeyword = (type: 'report' | 'algo', kw: string) => {
    if (type === 'report') setReportKeywords(reportKeywords.filter(k => k !== kw));
    else setAlgoKeywords(algoKeywords.filter(k => k !== kw));
  };

  useEffect(() => {
    if (isStreaming) {
      const words = streamingContent.trim().split(/\s+/).filter(w => w.length > 0).length;
      setCurrentWordCount(words);
    }
  }, [streamingContent, isStreaming]);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isStreaming) return;

    let topic = '';
    let context = '';
    let keywords: string[] = [];

    if (activeTab === 'technical_report') {
      if (!reportTitle.trim()) return;
      topic = reportTitle;
      context = `Scope: ${reportScope}\nSystem Description: ${systemDesc}`;
      keywords = reportKeywords;
    } else {
      if (!algoName.trim()) return;
      topic = algoName;
      context = `Domain: ${algoDomain}\nPurpose & Targets: ${algoPurpose}`;
      keywords = algoKeywords;
    }

    setIsStreaming(true);
    setIsDone(false);
    setStreamingContent('');
    setCurrentWordCount(0);
    setCopied(false);

    try {
      await streamResearch(
        activeTab,
        topic,
        context,
        keywords,
        (chunk) => setStreamingContent(prev => prev + chunk),
        (id, wc) => {
          setIsStreaming(false);
          setIsDone(true);
          setCurrentWordCount(wc);
          queryClient.invalidateQueries({ queryKey: getListResearchOutputsQueryKey() });
        }
      );
    } catch (e) {
      console.error(e);
      setIsStreaming(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(streamingContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([streamingContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeTab}_${new Date().getTime()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full bg-background overflow-y-auto">
      <div className="p-6 md:p-8 max-w-5xl mx-auto w-full space-y-6">

        {/* Header */}
        <div className="flex items-center gap-4 mb-2">
          <div className="h-12 w-12 rounded-lg bg-emerald-500/10 flex items-center justify-center ring-1 ring-emerald-500/30">
            <FileBarChart className="h-6 w-6 text-emerald-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Engineering Documents</h1>
            <p className="text-sm text-muted-foreground uppercase font-mono tracking-wider">System Specs & Algorithms</p>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3 max-w-[640px] mb-6 bg-card border border-border">
            <TabsTrigger value="technical_report" className="data-[state=active]:bg-emerald-500/20 data-[state=active]:text-emerald-500">
              <FileText className="h-4 w-4 mr-2" /> Technical Report
            </TabsTrigger>
            <TabsTrigger value="security_algorithm" className="data-[state=active]:bg-emerald-500/20 data-[state=active]:text-emerald-500">
              <Cpu className="h-4 w-4 mr-2" /> Algorithm Design
            </TabsTrigger>
            <TabsTrigger value="training_course_report" className="data-[state=active]:bg-emerald-500/20 data-[state=active]:text-emerald-500">
              <GraduationCap className="h-4 w-4 mr-2" /> Training Course Report
            </TabsTrigger>
          </TabsList>

          {activeTab === 'training_course_report' ? (
            <TabsContent value="training_course_report" className="mt-0 animate-in fade-in">
              <TrainingCourseReportPanel />
            </TabsContent>
          ) : (
            <>
              <Card className="bg-card border-border shadow-lg p-6">
                <form onSubmit={handleGenerate} className="space-y-6">

                  <TabsContent value="technical_report" className="mt-0 space-y-6 animate-in fade-in">
                    <div>
                      <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">
                        Report Title <span className="text-emerald-500">*</span>
                      </label>
                      <Input
                        placeholder="e.g. Next-Gen Baggage Scanner Specifications"
                        className="bg-background focus-visible:ring-emerald-500"
                        value={reportTitle}
                        onChange={e => setReportTitle(e.target.value)}
                        required
                      />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">Report Scope / Topic</label>
                        <Textarea
                          placeholder="Outline the goals and boundaries of this report..."
                          className="min-h-[100px] resize-y bg-background focus-visible:ring-emerald-500"
                          value={reportScope}
                          onChange={e => setReportScope(e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">System / Method Description</label>
                        <Textarea
                          placeholder="Describe the hardware/software being documented..."
                          className="min-h-[100px] resize-y bg-background focus-visible:ring-emerald-500"
                          value={systemDesc}
                          onChange={e => setSystemDesc(e.target.value)}
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">Keywords</label>
                      <div className="flex flex-wrap gap-1.5 mb-2 min-h-[24px]">
                        {reportKeywords.map(kw => (
                          <Badge key={kw} variant="secondary" className="bg-background border-border text-xs px-2 py-0 h-6 gap-1 pr-1">
                            {kw} <div role="button" onClick={() => removeKeyword('report', kw)} className="hover:bg-destructive/20 rounded-full p-0.5"><X className="h-3 w-3" /></div>
                          </Badge>
                        ))}
                      </div>
                      <Input
                        placeholder="Add keyword..."
                        className="bg-background max-w-[300px]"
                        value={reportKwInput}
                        onChange={e => setReportKwInput(e.target.value)}
                        onKeyDown={e => handleAddKeyword('report', e)}
                      />
                    </div>
                  </TabsContent>

                  <TabsContent value="security_algorithm" className="mt-0 space-y-6 animate-in fade-in">
                    <div>
                      <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">
                        Algorithm Name <span className="text-emerald-500">*</span>
                      </label>
                      <Input
                        placeholder="e.g. Adaptive Dual-Energy Material Discrimination"
                        className="bg-background focus-visible:ring-emerald-500"
                        value={algoName}
                        onChange={e => setAlgoName(e.target.value)}
                        required
                      />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">Technical Domain</label>
                        <Input
                          placeholder="e.g. CT Reconstruction, Threat Detection"
                          className="bg-background focus-visible:ring-emerald-500"
                          value={algoDomain}
                          onChange={e => setAlgoDomain(e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">Keywords</label>
                        <div className="flex flex-wrap gap-1.5 mb-2 min-h-[24px]">
                          {algoKeywords.map(kw => (
                            <Badge key={kw} variant="secondary" className="bg-background border-border text-xs px-2 py-0 h-6 gap-1 pr-1">
                              {kw} <div role="button" onClick={() => removeKeyword('algo', kw)} className="hover:bg-destructive/20 rounded-full p-0.5"><X className="h-3 w-3" /></div>
                            </Badge>
                          ))}
                        </div>
                        <Input
                          placeholder="Add keyword..."
                          className="bg-background"
                          value={algoKwInput}
                          onChange={e => setAlgoKwInput(e.target.value)}
                          onKeyDown={e => handleAddKeyword('algo', e)}
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">Purpose & Performance Targets</label>
                      <Textarea
                        placeholder="What does it detect? False alarm rate goals? Latency constraints?"
                        className="min-h-[100px] resize-y bg-background focus-visible:ring-emerald-500"
                        value={algoPurpose}
                        onChange={e => setAlgoPurpose(e.target.value)}
                      />
                    </div>
                  </TabsContent>

                  <div className="pt-2 border-t border-border/50">
                    <Button
                      type="submit"
                      className={`w-full md:w-auto md:min-w-[240px] h-12 font-bold transition-all ${
                        isStreaming
                          ? 'bg-emerald-500/20 text-emerald-500 cursor-not-allowed'
                          : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                      }`}
                      disabled={isStreaming || (activeTab === 'technical_report' ? !reportTitle.trim() : !algoName.trim())}
                    >
                      {isStreaming ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Generating...
                        </>
                      ) : (
                        <>
                          {activeTab === 'technical_report' ? <FileText className="h-4 w-4 mr-2" /> : <Cpu className="h-4 w-4 mr-2" />}
                          Generate {activeTab === 'technical_report' ? 'Report' : 'Algorithm'}
                        </>
                      )}
                    </Button>
                  </div>
                </form>
              </Card>

              {/* Output Area */}
              {(isStreaming || isDone || streamingContent) && (
                <Card className="bg-card border-emerald-500/20 shadow-[0_0_30px_-10px_rgba(16,185,129,0.1)] overflow-hidden animate-in slide-in-from-bottom-4 mt-6">
                  <div className="h-12 border-b border-border/50 bg-emerald-500/5 flex items-center justify-between px-4">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-semibold uppercase tracking-wider text-emerald-500">Output Document</span>
                      <Badge variant="outline" className="font-mono text-xs border-emerald-500/30 text-emerald-400">
                        {currentWordCount} words
                      </Badge>
                    </div>
                    <div className="flex gap-2">
                      {isDone && (
                        <>
                          <Button variant="outline" size="sm" className="h-8 border-border/50 hover:bg-background" onClick={handleCopy}>
                            {copied ? <Check className="h-4 w-4 mr-2 text-emerald-500" /> : <Copy className="h-4 w-4 mr-2" />}
                            Copy
                          </Button>
                          <Button variant="outline" size="sm" className="h-8 border-border/50 hover:bg-background" onClick={handleDownload}>
                            <Download className="h-4 w-4 mr-2" />
                            Save .md
                          </Button>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="p-6 md:p-8 bg-background max-h-[600px] overflow-y-auto" ref={outputRef}>
                    <div className="prose prose-invert max-w-none prose-headings:font-bold prose-headings:text-emerald-100 prose-a:text-emerald-400 prose-p:leading-relaxed font-sans">
                      <div className="whitespace-pre-wrap font-sans text-sm md:text-base leading-relaxed text-foreground/90">
                        {streamingContent}
                        {isStreaming && <span className="inline-block w-2 h-4 bg-emerald-500 ml-1 animate-pulse align-middle" />}
                      </div>
                    </div>
                  </div>
                </Card>
              )}
            </>
          )}
        </Tabs>

      </div>
    </div>
  );
}
