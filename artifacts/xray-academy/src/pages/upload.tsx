import { useState, useRef } from 'react';
import {
  UploadCloud, FileImage, ShieldAlert, CheckCircle, AlertTriangle, AlertCircle,
  Trash2, X, Activity, Info, Download, Eye, ChevronDown, ChevronRight,
  BarChart2, Shield, Maximize2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useListXrayAnalyses, useAnalyzeXrayImage, useDeleteXrayAnalysis, getListXrayAnalysesQueryKey } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid
} from 'recharts';

const THREAT_COLORS: Record<string, string> = {
  clear: '#10b981', low: '#f59e0b', medium: '#f97316', high: '#ef4444', critical: '#dc2626',
};
const THREAT_BADGE: Record<string, string> = {
  clear:    'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  low:      'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  medium:   'bg-orange-500/10 text-orange-400 border-orange-500/20',
  high:     'bg-red-500/10 text-red-400 border-red-500/20',
  critical: 'bg-red-600 text-white border-red-500',
};

const THREAT_LEVELS = ['clear', 'low', 'medium', 'high', 'critical'];

function getThreatIcon(level?: string) {
  switch (level) {
    case 'clear': return <CheckCircle className="h-4 w-4" />;
    case 'low': return <Info className="h-4 w-4" />;
    case 'medium': return <AlertCircle className="h-4 w-4" />;
    case 'high':
    case 'critical': return <AlertTriangle className="h-4 w-4" />;
    default: return <ShieldAlert className="h-4 w-4" />;
  }
}

function ThreatBadge({ level }: { level?: string }) {
  const cls = THREAT_BADGE[level || ''] || 'bg-secondary text-muted-foreground border-border';
  return (
    <Badge variant="outline" className={`px-3 py-1 border font-bold uppercase tracking-widest text-xs shadow-sm flex items-center gap-1.5 w-fit ${cls} ${level === 'critical' ? 'animate-pulse' : ''}`}>
      {getThreatIcon(level)}{level || 'unknown'} threat
    </Badge>
  );
}

function ConfidenceBar({ level }: { level?: string }) {
  const idx = THREAT_LEVELS.indexOf(level || 'clear');
  const pct = Math.max(5, ((idx + 1) / THREAT_LEVELS.length) * 100);
  const color = THREAT_COLORS[level || 'clear'];
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2.5 bg-secondary rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs font-mono text-muted-foreground w-10 text-right">{pct.toFixed(0)}%</span>
    </div>
  );
}

function AnalysisDetailModal({ analysis, open, onClose }: { analysis: any; open: boolean; onClose: () => void }) {
  const recs = Array.isArray(analysis?.recommendations) ? analysis.recommendations
    : typeof analysis?.recommendations === 'string' ? JSON.parse(analysis.recommendations || '[]')
    : [];

  const exportReport = () => {
    window.open(`/api/export/analysis/${analysis.id}`, '_blank');
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between text-base font-bold pr-6">
            <div className="flex items-center gap-3">
              <Shield className="h-5 w-5 text-primary" />
              Analysis Detail
            </div>
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={exportReport}>
              <Download className="h-3 w-3 mr-1" />Export Report
            </Button>
          </DialogTitle>
        </DialogHeader>

        {analysis && (
          <div className="space-y-5 mt-2">
            {/* Meta */}
            <div className="flex flex-wrap gap-3 items-center">
              <ThreatBadge level={analysis.threat_level} />
              <Badge variant="outline" className="font-mono text-[10px]">{analysis.scanner_type}</Badge>
              <span className="text-xs text-muted-foreground font-mono">{new Date(analysis.created_at).toLocaleString()}</span>
            </div>

            {/* Threat bar */}
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Threat Level Indicator</div>
              <div className="flex gap-1">
                {THREAT_LEVELS.map(lvl => (
                  <div key={lvl} className="flex-1 text-center">
                    <div className={`h-3 rounded-sm ${lvl === analysis.threat_level ? 'opacity-100' : 'opacity-20'}`}
                         style={{ background: THREAT_COLORS[lvl] }} />
                    <div className="text-[8px] font-mono text-muted-foreground mt-1 capitalize">{lvl}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Image */}
            {analysis.image_url && (
              <div className="rounded-xl overflow-hidden border border-border bg-black">
                <img src={analysis.image_url} alt="Scan" className="w-full h-auto object-contain max-h-64" />
              </div>
            )}

            {/* Findings */}
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Detailed Findings</div>
              <div className="p-4 rounded-lg bg-background border border-border text-sm leading-relaxed whitespace-pre-wrap text-foreground/90">
                {analysis.findings || 'No findings recorded.'}
              </div>
            </div>

            {/* Recommendations */}
            {recs.length > 0 && (
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Required Protocols</div>
                <div className="space-y-2">
                  {recs.map((rec: string, i: number) => (
                    <div key={i} className="flex gap-3 items-start p-3 rounded-lg bg-background border border-border">
                      <span className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center font-mono text-[10px] shrink-0 font-bold">{i+1}</span>
                      <span className="text-sm leading-snug">{rec}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end">
              <Button onClick={exportReport} className="bg-primary hover:bg-primary/90 text-white">
                <Download className="h-4 w-4 mr-2" />Export Full Report
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function UploadPage() {
  const queryClient = useQueryClient();
  const { data: analyses, isLoading: isListLoading } = useListXrayAnalyses();

  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [scannerType, setScannerType] = useState<string>('baggage');
  const [context, setContext] = useState('');
  const [selectedAnalysis, setSelectedAnalysis] = useState<any>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { mutate: analyze, isPending: isAnalyzing, data: currentAnalysis } = useAnalyzeXrayImage({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListXrayAnalysesQueryKey() });
        setImageFile(null); setImageBase64(null); setContext('');
        if (imagePreview) URL.revokeObjectURL(imagePreview);
        setImagePreview(null);
      }
    }
  });

  const { mutate: deleteAnalysis } = useDeleteXrayAnalysis({
    mutation: { onSuccess: () => queryClient.invalidateQueries({ queryKey: getListXrayAnalysesQueryKey() }) }
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    setImagePreview(URL.createObjectURL(file));
    const reader = new FileReader();
    reader.onload = (ev) => { setImageBase64((ev.target?.result as string).split(',')[1]); };
    reader.readAsDataURL(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file?.type.startsWith('image/')) {
      setImageFile(file);
      setImagePreview(URL.createObjectURL(file));
      const reader = new FileReader();
      reader.onload = (ev) => { setImageBase64((ev.target?.result as string).split(',')[1]); };
      reader.readAsDataURL(file);
    }
  };

  const handleAnalyze = () => {
    if (!imageBase64 || !imageFile) return;
    analyze({ data: { image_base64: imageBase64, filename: imageFile.name, scanner_type: scannerType as any, context: context || undefined } });
  };

  const openDetail = (analysis: any) => {
    setSelectedAnalysis(analysis);
    setModalOpen(true);
  };

  // Threat distribution for chart
  const threatDist = THREAT_LEVELS.map(lvl => ({
    level: lvl,
    count: (analyses || []).filter((a: any) => a.threat_level === lvl).length,
    color: THREAT_COLORS[lvl],
  })).filter(d => d.count > 0);

  const currentRecs = Array.isArray(currentAnalysis?.recommendations) ? currentAnalysis.recommendations
    : typeof currentAnalysis?.recommendations === 'string'
      ? JSON.parse(currentAnalysis.recommendations || '[]') : [];

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-background">
      {/* Header */}
      <div className="bg-card border-b border-border p-6 shrink-0">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/30">
              <ShieldAlert className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">X-Ray Analysis</h1>
              <p className="text-sm text-muted-foreground font-mono uppercase tracking-wider">Automated Threat Recognition · AI Vision Module</p>
            </div>
          </div>
          {analyses && analyses.length > 0 && (
            <div className="flex items-center gap-3">
              <Badge variant="outline" className="font-mono text-xs">{analyses.length} analyses</Badge>
              {analyses.filter((a: any) => ['high','critical'].includes(a.threat_level)).length > 0 && (
                <Badge className="bg-destructive text-destructive-foreground text-xs animate-pulse">
                  {analyses.filter((a: any) => ['high','critical'].includes(a.threat_level)).length} high-risk
                </Badge>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Upload Panel */}
          <Card className="border-border">
            <CardContent className="p-6 space-y-5">
              <h2 className="font-bold text-base flex items-center gap-2 border-b border-border pb-4">
                <UploadCloud className="h-5 w-5 text-primary" />Submit X-Ray Scan
              </h2>

              <div
                className={`relative border-2 border-dashed rounded-xl transition-all cursor-pointer ${
                  imagePreview ? 'border-primary/50 bg-primary/5' : 'border-border hover:border-primary/40 hover:bg-card'
                }`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => !imagePreview && fileInputRef.current?.click()}
              >
                {imagePreview ? (
                  <div className="relative">
                    <img src={imagePreview} alt="Preview" className="w-full rounded-xl object-contain bg-black max-h-60" />
                    {isAnalyzing && (
                      <div className="absolute inset-0 bg-primary/20 flex flex-col items-center justify-center backdrop-blur-[2px] rounded-xl border border-primary overflow-hidden">
                        <div className="absolute top-0 left-0 right-0 h-1 bg-primary animate-[scan_2s_ease-in-out_infinite] shadow-[0_0_10px_2px_rgba(37,99,235,0.7)]" />
                        <Activity className="h-10 w-10 text-white animate-pulse mb-2" />
                        <span className="text-white font-mono text-sm font-bold uppercase tracking-widest">Deep Scanning...</span>
                      </div>
                    )}
                    <Button
                      variant="destructive" size="icon"
                      className="absolute -top-3 -right-3 h-7 w-7 rounded-full shadow-lg"
                      onClick={(e) => { e.stopPropagation(); setImageFile(null); setImagePreview(null); setImageBase64(null); }}
                      disabled={isAnalyzing}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ) : (
                  <div className="py-10 flex flex-col items-center justify-center text-center px-6">
                    <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center mb-4 ring-1 ring-primary/20">
                      <FileImage className="h-8 w-8 text-primary" />
                    </div>
                    <p className="text-sm font-medium mb-1">Drag & drop X-ray scan</p>
                    <p className="text-xs text-muted-foreground mb-4">or click to browse · PNG, JPG, WEBP</p>
                    <Button variant="outline" size="sm" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>Browse Files</Button>
                  </div>
                )}
                <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleFileChange} />
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-semibold mb-1.5 block">Scanner Profile</label>
                  <Select value={scannerType} onValueChange={setScannerType} disabled={isAnalyzing}>
                    <SelectTrigger className="bg-background"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="baggage">Baggage / Cabin Screening</SelectItem>
                      <SelectItem value="cargo">Cargo / Pallet X-ray</SelectItem>
                      <SelectItem value="vehicle">Vehicle / Container</SelectItem>
                      <SelectItem value="body">Body Scanner</SelectItem>
                      <SelectItem value="parcel">Parcel / Mail Screening</SelectItem>
                      <SelectItem value="general">General Purpose X-Ray</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-semibold mb-1.5 block">Operator Context (Optional)</label>
                  <Textarea
                    placeholder="Flight origin, flagged route, prior alerts, operator notes..."
                    value={context} onChange={(e) => setContext(e.target.value)}
                    disabled={isAnalyzing} className="resize-none h-16 bg-background text-sm"
                  />
                </div>

                <Button
                  onClick={handleAnalyze} disabled={!imageFile || isAnalyzing}
                  className="w-full h-11 text-sm font-bold shadow-sm" data-testid="button-analyze"
                >
                  {isAnalyzing ? (
                    <><Activity className="h-4 w-4 mr-2 animate-pulse" />Processing Scan...</>
                  ) : (
                    <><ShieldAlert className="h-4 w-4 mr-2" />Initiate Analysis</>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Results Panel */}
          <Card className="border-border">
            <CardContent className="p-6 space-y-5">
              <h2 className="font-bold text-base flex items-center justify-between border-b border-border pb-4">
                <span className="flex items-center gap-2"><Activity className="h-5 w-5 text-primary" />Analysis Results</span>
                {currentAnalysis && (
                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => window.open(`/api/export/analysis/${currentAnalysis.id}`, '_blank')}>
                    <Download className="h-3 w-3 mr-1" />Export
                  </Button>
                )}
              </h2>

              {!currentAnalysis ? (
                <div className="flex flex-col items-center justify-center text-center py-16 space-y-3">
                  <div className="h-16 w-16 rounded-2xl bg-card border border-border flex items-center justify-center">
                    <ShieldAlert className="h-8 w-8 text-muted-foreground opacity-30" />
                  </div>
                  <p className="text-sm text-muted-foreground font-mono uppercase tracking-wider">Awaiting Input Scan</p>
                </div>
              ) : (
                <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-500">
                  {/* Threat header */}
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                      <h3 className="font-bold text-base truncate max-w-xs">{currentAnalysis.filename}</h3>
                      <div className="flex gap-2 mt-1 flex-wrap">
                        <Badge variant="outline" className="font-mono text-[10px] uppercase">{currentAnalysis.scanner_type}</Badge>
                        <span className="text-xs text-muted-foreground font-mono">{new Date(currentAnalysis.created_at).toLocaleTimeString()}</span>
                      </div>
                    </div>
                    <ThreatBadge level={currentAnalysis.threat_level} />
                  </div>

                  {/* Confidence bar */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between">
                      <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Threat Confidence</span>
                      <span className="text-[10px] font-mono text-muted-foreground capitalize">{currentAnalysis.threat_level}</span>
                    </div>
                    <ConfidenceBar level={currentAnalysis.threat_level} />
                    <div className="flex justify-between text-[8px] font-mono text-muted-foreground/50">
                      {THREAT_LEVELS.map(l => <span key={l} className="capitalize">{l}</span>)}
                    </div>
                  </div>

                  {/* Findings */}
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Findings</div>
                    <div className="p-3 rounded-lg bg-background border border-border text-sm leading-relaxed max-h-40 overflow-y-auto text-foreground/90">
                      {currentAnalysis.findings}
                    </div>
                  </div>

                  {/* Recommendations */}
                  {currentRecs.length > 0 && (
                    <div>
                      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Required Protocols</div>
                      <div className="space-y-1.5">
                        {currentRecs.slice(0, 3).map((rec: string, i: number) => (
                          <div key={i} className="flex gap-2.5 text-sm p-2.5 bg-background border border-border rounded-lg items-start">
                            <span className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center font-mono text-[10px] shrink-0 font-bold mt-0.5">{i+1}</span>
                            <span className="leading-snug text-xs">{rec}</span>
                          </div>
                        ))}
                        {currentRecs.length > 3 && (
                          <button onClick={() => openDetail(currentAnalysis)} className="text-xs text-primary underline underline-offset-2 pl-7">
                            +{currentRecs.length - 3} more protocols...
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  <Button variant="outline" size="sm" className="w-full text-xs" onClick={() => openDetail(currentAnalysis)}>
                    <Eye className="h-3.5 w-3.5 mr-2" />View Full Report
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Threat distribution chart */}
        {threatDist.length > 0 && (
          <Card className="border-border">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <BarChart2 className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">Threat Level Distribution</h3>
                <Badge variant="outline" className="font-mono text-[10px] ml-auto">{(analyses || []).length} total scans</Badge>
              </div>
              <div className="h-32">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={threatDist} margin={{ top: 4, right: 20, bottom: 4, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="level" tick={{ fontSize: 10, fill: '#64748b', textTransform: 'capitalize' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#64748b' }} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', fontSize: '11px' }} itemStyle={{ color: '#94a3b8' }} />
                    <Bar dataKey="count" radius={[4,4,0,0]}>
                      {threatDist.map((entry, index) => (
                        <Cell key={index} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        )}

        {/* History Table */}
        <Card className="border-border">
          <CardContent className="p-0">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold text-sm flex items-center gap-2"><Activity className="h-4 w-4 text-muted-foreground" />Analysis History</h2>
              {analyses && analyses.length > 0 && <Badge variant="outline" className="font-mono text-[10px]">{analyses.length} records</Badge>}
            </div>

            {isListLoading ? (
              <div className="p-8 text-center text-muted-foreground font-mono text-xs uppercase tracking-widest animate-pulse">Loading...</div>
            ) : !analyses?.length ? (
              <div className="p-8 text-center text-muted-foreground font-mono text-xs uppercase tracking-widest">No analyses yet</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-secondary/30">
                      <th className="px-5 py-3 text-left text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Filename</th>
                      <th className="px-5 py-3 text-left text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Profile</th>
                      <th className="px-5 py-3 text-left text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Assessment</th>
                      <th className="px-5 py-3 text-left text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Timestamp</th>
                      <th className="px-5 py-3 text-right text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analyses.map((item: any) => (
                      <tr key={item.id} className="border-b border-border/50 hover:bg-secondary/10 transition-colors group cursor-pointer" onClick={() => openDetail(item)}>
                        <td className="px-5 py-3 font-medium max-w-[200px] truncate" title={item.filename}>{item.filename}</td>
                        <td className="px-5 py-3"><Badge variant="outline" className="font-mono text-[10px]">{item.scanner_type}</Badge></td>
                        <td className="px-5 py-3">
                          <span className={`inline-flex items-center gap-1.5 text-xs font-bold uppercase ${(THREAT_BADGE[item.threat_level] || '').split(' ').filter(c => c.startsWith('text-')).join(' ')}`}>
                            {getThreatIcon(item.threat_level)}{item.threat_level}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-muted-foreground font-mono text-xs">{new Date(item.created_at).toLocaleString()}</td>
                        <td className="px-5 py-3 text-right">
                          <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-all">
                            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-primary"
                              onClick={(e) => { e.stopPropagation(); window.open(`/api/export/analysis/${item.id}`, '_blank'); }}>
                              <Download className="h-3.5 w-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                              onClick={(e) => { e.stopPropagation(); deleteAnalysis({ analysisId: item.id }); }}
                              data-testid={`button-delete-analysis-${item.id}`}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Detail Modal */}
      <AnalysisDetailModal analysis={selectedAnalysis} open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}
