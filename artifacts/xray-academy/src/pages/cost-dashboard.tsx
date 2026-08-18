/**
 * Cost Dashboard — complete OpenAI usage, cost, token, and savings transparency.
 *
 * All data comes from real API usage logs stored in the database:
 *   translation_usage  → Translation Studio
 *   vision_cost_log    → Image Analysis (Vision Guard)
 *   study_jobs         → Learning Hub
 *   chat_usage         → AI Chat (token counts char-estimated)
 *   openai_usage_log   → Innovation Engine, Training Generator, Gallery Reindex,
 *                         RAG Vision, Image Translation, LinkedIn, X-Ray Analysis
 */
import { useState, useCallback, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
  LineChart, Line, AreaChart, Area,
} from 'recharts';
import {
  DollarSign, Cpu, Zap, TrendingUp, TrendingDown, AlertTriangle,
  CheckCircle, RefreshCw, Download, Settings, Database, Eye,
  MessageSquare, Languages, Brain, ChevronRight, Info, Shield,
  Layers, FileText, BarChart2, Clock, Search, Filter, X,
  ArrowUpDown, Lightbulb, Target, FlaskConical, BookOpen, GitCompare,
  Ban, ShieldAlert, ShieldCheck, Lock, Unlock, Activity, History,
  GitCommit, Bug, CircleCheck, TriangleAlert, CircleX, Plus,
  AlertCircle, Building2, ChevronDown, Calendar, ChevronUp,
  Maximize2, ArrowUp, ArrowDown, Minus, Trophy, Flame,
  PieChart as PieChartIcon,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${API}${path}`, { credentials: 'include', ...opts });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ── Color palette ──────────────────────────────────────────────────────────────
const FEATURE_COLORS: Record<string, string> = {
  'Translation Studio':              '#3b82f6',
  'Image Analysis':                  '#8b5cf6',
  'Image Analysis (Vision Guard)':   '#8b5cf6',
  'Learning Hub':                    '#10b981',
  'AI Chat':                         '#f59e0b',
  'AI Chat (non-stream)':            '#f59e0b',
  'Innovation Engine':               '#ef4444',
  'Training Generator':              '#f97316',
  'Gallery Reindex':                 '#a855f7',
  'RAG Vision Analysis':             '#06b6d4',
  'Image Translation':               '#84cc16',
  'LinkedIn Generator':              '#0ea5e9',
  'X-Ray Image Analysis':            '#e879f9',
};

const PERIOD_LABELS: Record<string, string> = {
  today: "Today", yesterday: "Yesterday", "7d": "Last 7 Days",
  "30d": "Last 30 Days", month: "This Month", lifetime: "Lifetime",
};

// ── Shared hooks ───────────────────────────────────────────────────────────────
function useCosts<T>(key: string, path: string, opts?: { refetchInterval?: number }) {
  return useQuery<T>({
    queryKey: ['costs', key],
    queryFn: () => apiFetch(path),
    refetchInterval: opts?.refetchInterval ?? 60_000,
  });
}

// ── Utility components ─────────────────────────────────────────────────────────
function Stat({ label, value, sub, color = 'text-foreground', icon: Icon }: {
  label: string; value: string | number; sub?: string;
  color?: string; icon?: any;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
      <div className="flex items-center gap-2 text-muted-foreground">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function fmt(n: number, decimals = 4) {
  return n === 0 ? '$0.00' : `$${n.toFixed(decimals)}`;
}

function fmtNum(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function fmtSecs(s: number) {
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`;
}

function PeriodBadge({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 text-xs rounded-md font-mono transition-colors ${
        active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/60'
      }`}
    >
      {label}
    </button>
  );
}

function TableHead({ children, onClick, sorted }: { children: React.ReactNode; onClick?: () => void; sorted?: boolean }) {
  return (
    <th
      className={`px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide ${onClick ? 'cursor-pointer hover:text-foreground select-none' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-center gap-1">
        {children}
        {onClick && <ArrowUpDown className={`h-3 w-3 ${sorted ? 'text-primary' : 'opacity-40'}`} />}
      </div>
    </th>
  );
}

function Pill({ color }: { color: string }) {
  return <span className="inline-block w-2.5 h-2.5 rounded-sm mr-1 shrink-0" style={{ background: color }} />;
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
      <Database className="h-8 w-8 opacity-30" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

// ── Custom recharts tooltip ────────────────────────────────────────────────────
function ChartTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-popover border border-border rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold mb-1">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-mono">{typeof p.value === 'number' && p.value < 1 ? `$${p.value.toFixed(4)}` : fmtNum(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Overview
// ══════════════════════════════════════════════════════════════════════════════
function OverviewTab() {
  const [period, setPeriod] = useState('lifetime');
  const { data, isLoading } = useCosts<any>('overview', '/api/costs/overview', { refetchInterval: 30_000 });

  const p = data?.periods?.[period] ?? {};
  const s = data?.stats ?? {};

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex flex-wrap gap-1 bg-card border border-border rounded-xl p-1.5">
        {Object.entries(PERIOD_LABELS).map(([key, label]) => (
          <PeriodBadge key={key} active={period === key} label={label} onClick={() => setPeriod(key)} />
        ))}
      </div>

      {/* Period cost cards */}
      {isLoading ? (
        <div className="text-center text-muted-foreground py-8 text-sm">Loading…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Total Cost" value={fmt(p.total_cost_usd ?? 0)} icon={DollarSign} color="text-amber-400" />
            <Stat label="API Calls" value={fmtNum(p.total_calls ?? 0)} icon={Zap} color="text-blue-400" />
            <Stat label="Prompt Tokens" value={fmtNum(p.prompt_tokens ?? 0)} icon={Cpu} color="text-cyan-400" />
            <Stat label="Completion Tokens" value={fmtNum(p.completion_tokens ?? 0)} icon={Cpu} color="text-purple-400" />
          </div>

          {/* Feature breakdown mini-cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { key: 'translation', label: 'Translation', icon: Languages, color: 'text-blue-400' },
              { key: 'vision',      label: 'Image Analysis', icon: Eye,        color: 'text-purple-400' },
              { key: 'learning',   label: 'Learning Hub',  icon: Brain,      color: 'text-green-400' },
              { key: 'chat',       label: 'AI Chat',       icon: MessageSquare, color: 'text-amber-400' },
            ].map(f => (
              <div key={f.key} className="bg-card border border-border rounded-xl p-3 flex items-center gap-3">
                <f.icon className={`h-5 w-5 ${f.color} shrink-0`} />
                <div>
                  <div className={`text-lg font-bold tabular-nums ${f.color}`}>
                    {fmt(p.breakdown?.[f.key] ?? 0)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">{f.label}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Lifetime stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Lifetime Cost" value={fmt(s.total_cost_usd ?? 0)} icon={DollarSign} color="text-amber-400"
          sub={`Avg ${fmt(s.avg_cost_per_request ?? 0, 6)} / request`} />
        <Stat label="Total API Calls" value={fmtNum(s.total_calls ?? 0)} icon={Zap} color="text-blue-400" />
        <Stat label="Total Prompt Tokens" value={fmtNum(s.total_prompt_tokens ?? 0)} icon={Cpu} color="text-cyan-400" />
        <Stat label="Total Completion Tokens" value={fmtNum(s.total_completion_tokens ?? 0)} icon={Cpu} color="text-purple-400" />
        <Stat label="Cached Tokens" value={fmtNum(s.total_cached_tokens ?? 0)} icon={Database} color="text-green-400" />
        <Stat label="Cache Hit Rate" value={`${s.cache_hit_rate_pct ?? 0}%`} icon={TrendingUp} color={s.cache_hit_rate_pct > 30 ? 'text-green-400' : 'text-amber-400'} />
        <Stat label="Vision Cache Rate" value={`${s.vision_cache_hit_rate_pct ?? 0}%`} icon={Eye} color="text-purple-400" />
        <Stat label="Vision Savings" value={fmt(s.vision_savings_usd ?? 0)} icon={TrendingDown} color="text-green-400"
          sub="Saved by local filter + SHA-256 dedup" />
      </div>

      {/* ── Permanent Vision Cost Protection card ───────────────────────── */}
      <VisionProtectionCard />

      {/* ── Permanent High-Risk Cost Controls summary ──────────────────── */}
      <HighRiskSummaryCard />
    </div>
  );
}

// ── Shared helpers for high-risk status display ───────────────────────────────
const PROT_STATUS: Record<string, { label: string; badge: string; row: string }> = {
  verified:   { label: 'Protected',  badge: 'text-green-400 border-green-400/40 bg-green-400/5',   row: 'border-l-2 border-l-green-500/30' },
  unverified: { label: 'Unverified', badge: 'text-amber-400 border-amber-400/40 bg-amber-400/5',   row: 'border-l-2 border-l-amber-500/30' },
  at_risk:    { label: 'At Risk',    badge: 'text-red-400 border-red-400/40 bg-red-400/5',         row: 'border-l-2 border-l-red-500/40' },
};

/** Permanent High-Risk Cost Controls summary card — always visible in Overview */
function HighRiskSummaryCard() {
  const { data, isLoading } = useCosts<any>('high-risk-summary', '/api/costs/high-risk-summary', { refetchInterval: 60_000 });
  const summary = data?.summary ?? {};

  const overallStatus = summary.overall_status ?? 'unverified';
  const protColor = overallStatus === 'protected' ? 'border-green-500/40 bg-green-500/5'
    : overallStatus === 'at_risk' ? 'border-red-500/50 bg-red-500/10'
    : 'border-amber-500/40 bg-amber-500/5';
  const statusLabel = overallStatus === 'protected' ? 'Protected' : overallStatus === 'at_risk' ? 'At Risk' : 'Unverified';

  return (
    <div className={`rounded-xl border-2 p-4 ${protColor}`}>
      <div className="flex items-center gap-2 mb-4">
        <Shield className="h-5 w-5 text-foreground/70" />
        <span className="font-bold text-sm tracking-wide uppercase">High-Risk Cost Controls</span>
        <Badge variant="outline" className={`text-[10px] ml-1 ${PROT_STATUS[overallStatus]?.badge}`}>
          {statusLabel}
        </Badge>
        <span className="ml-auto text-[10px] text-muted-foreground">See "Risk Controls" tab for full table</span>
      </div>

      {isLoading ? (
        <div className="text-xs text-muted-foreground">Loading…</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-card/60 border border-border/50 rounded-lg p-2.5">
            <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">Historical Risk</div>
            <div className="text-base font-bold text-amber-400 tabular-nums mt-0.5">
              ${summary.total_historical_risk_min_usd?.toFixed(0) ?? '–'}–${summary.total_historical_risk_max_usd?.toFixed(0) ?? '–'}
            </div>
            <div className="text-[10px] text-muted-foreground">total avoidable</div>
          </div>
          <div className="bg-card/60 border border-border/50 rounded-lg p-2.5">
            <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">Current Cost</div>
            <div className="text-base font-bold text-foreground tabular-nums mt-0.5">{fmt(summary.total_current_cost_usd ?? 0)}</div>
            <div className="text-[10px] text-muted-foreground">all tracked features</div>
          </div>
          <div className="bg-card/60 border border-border/50 rounded-lg p-2.5">
            <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">Savings</div>
            <div className="text-base font-bold text-green-400 tabular-nums mt-0.5">{fmt(summary.total_estimated_savings_usd ?? 0)}</div>
            <div className="text-[10px] text-muted-foreground">dedup + cache</div>
          </div>
          <div className="bg-card/60 border border-border/50 rounded-lg p-2.5">
            <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">Protected</div>
            <div className="text-base font-bold text-green-400 tabular-nums mt-0.5">{summary.protected_categories ?? 0} / 7</div>
            <div className="text-[10px] text-muted-foreground">categories</div>
          </div>
          <div className="bg-card/60 border border-border/50 rounded-lg p-2.5">
            <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">At Risk</div>
            <div className={`text-base font-bold tabular-nums mt-0.5 ${(summary.unprotected_categories ?? 0) > 0 ? 'text-red-400' : 'text-muted-foreground'}`}>
              {summary.unprotected_categories ?? 0} / 7
            </div>
            <div className="text-[10px] text-muted-foreground">categories</div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Permanent red Vision Cost Protection card — always visible in Overview */
function VisionProtectionCard() {
  const { data, isLoading } = useCosts<any>('vision-protection', '/api/vision/protection', { refetchInterval: 30_000 });
  const qc = useQueryClient();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);

  const handleKillSwitch = async () => {
    if (!window.confirm('Disable ALL Vision processing immediately? This blocks image captioning, gallery reindex, and RAG vision analysis.')) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/vision/kill-switch`, { method: 'POST', credentials: 'include' });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: '🔴 Vision Disabled', description: 'All image captioning and vision calls are now blocked.' });
      qc.invalidateQueries({ queryKey: ['costs'] });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const handleEnable = async () => {
    if (!window.confirm('Re-enable Vision processing? Ensure limits are set correctly before proceeding.')) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/vision/enable`, { method: 'POST', credentials: 'include' });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: '✅ Vision Enabled', description: 'Vision processing is now active.' });
      qc.invalidateQueries({ queryKey: ['costs'] });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const enabled = data?.kill_switch?.vision_enabled ?? false;
  const limits  = data?.limits ?? {};
  const usage   = data?.current_usage ?? {};
  const remain  = data?.remaining_allowance ?? {};

  return (
    <div className={`rounded-xl border-2 p-4 ${enabled ? 'border-amber-500/40 bg-amber-500/5' : 'border-red-500/60 bg-red-500/10'}`}>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-2">
          <ShieldAlert className={`h-5 w-5 ${enabled ? 'text-amber-400' : 'text-red-400'}`} />
          <span className="font-bold text-sm tracking-wide uppercase">Vision Cost Protection</span>
          <Badge variant="outline" className={`text-[10px] font-mono ${enabled ? 'text-amber-400 border-amber-400/40' : 'text-red-400 border-red-400/40'}`}>
            {enabled ? '⚡ ENABLED' : '🔒 DISABLED'}
          </Badge>
        </div>
        <div className="flex gap-2 shrink-0">
          {enabled ? (
            <Button size="sm" variant="destructive" className="text-xs h-7 gap-1.5" onClick={handleKillSwitch} disabled={busy}>
              <Ban className="h-3 w-3" />
              Disable All Vision
            </Button>
          ) : (
            <Button size="sm" variant="outline" className="text-xs h-7 gap-1.5 border-green-500/40 text-green-400 hover:bg-green-500/10" onClick={handleEnable} disabled={busy}>
              <Unlock className="h-3 w-3" />
              Re-enable Vision
            </Button>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="text-xs text-muted-foreground">Loading protection status…</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Max Calls / Job',       value: limits.max_calls_per_job ?? 10,      unit: 'calls',   used: null },
            { label: 'Max Cost / Job',         value: `${(limits.max_cost_per_job_usd ?? 0.50).toFixed(2)}`, unit: '', used: null },
            { label: 'Daily Limit',            value: `${(limits.max_daily_cost_usd ?? 2).toFixed(2)}`,     unit: '', used: `${(usage.daily_cost_usd ?? 0).toFixed(4)} used` },
            { label: 'Monthly Limit',          value: `${(limits.max_monthly_cost_usd ?? 10).toFixed(2)}`,  unit: '', used: `${(usage.monthly_cost_usd ?? 0).toFixed(4)} used` },
          ].map(item => (
            <div key={item.label} className="bg-card/60 border border-border/50 rounded-lg p-2.5">
              <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">{item.label}</div>
              <div className="text-base font-bold text-foreground mt-0.5 tabular-nums">{item.value}</div>
              {item.used && <div className="text-[10px] text-amber-400 mt-0.5 tabular-nums">{item.used}</div>}
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 text-[10px] text-muted-foreground">
        Remaining today: <span className="text-green-400 font-mono">${(remain.daily_cost_usd ?? 0).toFixed(4)}</span>
        {' · '}Remaining this month: <span className="text-green-400 font-mono">${(remain.monthly_cost_usd ?? 0).toFixed(4)}</span>
        {' · '}Text extraction, OCR, translation, and local image hashing remain active when vision is disabled.
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Cost by Feature
// ══════════════════════════════════════════════════════════════════════════════
function ByFeatureTab() {
  const [period, setPeriod] = useState('lifetime');
  const { data, isLoading } = useCosts<any>(`by-feature-${period}`, `/api/costs/by-feature?period=${period}`);
  const [sortKey, setSortKey] = useState('cost');

  const features = [...(data?.features ?? [])].sort((a, b) => b[sortKey] - a[sortKey]);

  const pieData = features.filter(f => f.cost > 0).map(f => ({
    name: f.feature, value: f.cost, color: FEATURE_COLORS[f.feature] ?? '#6b7280',
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-1 bg-card border border-border rounded-xl p-1.5">
        {Object.entries(PERIOD_LABELS).map(([key, label]) => (
          <PeriodBadge key={key} active={period === key} label={label} onClick={() => setPeriod(key)} />
        ))}
      </div>

      {isLoading ? <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div> : (
        <div className="grid md:grid-cols-2 gap-6">
          {/* Pie chart */}
          <Card>
            <CardHeader><CardTitle className="text-sm">Cost Distribution</CardTitle></CardHeader>
            <CardContent>
              {pieData.length === 0 ? <EmptyState message="No cost data yet" /> : (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label={({ name, pct }) => `${name.split(' ')[0]} ${pct ?? ''}%`}>
                      {pieData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => [`$${v.toFixed(4)}`, 'Cost']} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Table */}
          <Card>
            <CardHeader><CardTitle className="text-sm">Feature Breakdown</CardTitle></CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-muted/30">
                    <tr>
                      <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Feature</th>
                      <TableHead onClick={() => setSortKey('calls')} sorted={sortKey === 'calls'}>Calls</TableHead>
                      <TableHead onClick={() => setSortKey('tokens')} sorted={sortKey === 'tokens'}>Tokens</TableHead>
                      <TableHead onClick={() => setSortKey('cost')} sorted={sortKey === 'cost'}>Cost</TableHead>
                      <TableHead onClick={() => setSortKey('pct')} sorted={sortKey === 'pct'}>%</TableHead>
                      <TableHead onClick={() => setSortKey('avg_cost')} sorted={sortKey === 'avg_cost'}>Avg Cost</TableHead>
                    </tr>
                  </thead>
                  <tbody>
                    {features.map(f => (
                      <tr key={f.feature} className="border-t border-border/50 hover:bg-muted/20">
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1.5">
                            <Pill color={FEATURE_COLORS[f.feature] ?? '#6b7280'} />
                            <span className="font-medium">{f.feature}</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 font-mono">{fmtNum(f.calls)}</td>
                        <td className="px-3 py-2 font-mono">{fmtNum(f.tokens)}</td>
                        <td className="px-3 py-2 font-mono text-amber-400">{fmt(f.cost)}</td>
                        <td className="px-3 py-2 font-mono">{f.pct}%</td>
                        <td className="px-3 py-2 font-mono">{fmt(f.avg_cost, 6)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Documents
// ══════════════════════════════════════════════════════════════════════════════
function DocumentsTab() {
  const [sortKey, setSortKey] = useState('cost_desc');
  const { data, isLoading } = useCosts<any>(`docs-${sortKey}`, `/api/costs/documents?sort=${sortKey}&limit=100`);

  const docs = data?.documents ?? [];

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        {[
          ['cost_desc', 'Highest Cost'], ['cost_asc', 'Lowest Cost'],
          ['recent', 'Recently Used'], ['tokens', 'Most Tokens'],
        ].map(([key, label]) => (
          <PeriodBadge key={key} active={sortKey === key} label={label} onClick={() => setSortKey(key)} />
        ))}
      </div>

      {isLoading ? <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div> : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/30">
                  <tr>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">File Name</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Pages</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Translation</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Vision</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Learning</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Total</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Last Used</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Cache</th>
                  </tr>
                </thead>
                <tbody>
                  {docs.length === 0 ? (
                    <tr><td colSpan={8}><EmptyState message="No documents yet" /></td></tr>
                  ) : docs.map((d: any) => (
                    <tr key={d.doc_id} className="border-t border-border/50 hover:bg-muted/20">
                      <td className="px-3 py-2">
                        <span className="font-medium truncate max-w-48 block">{d.filename}</span>
                      </td>
                      <td className="px-3 py-2 font-mono">{d.pages}</td>
                      <td className="px-3 py-2 font-mono text-blue-400">{fmt(d.translation_cost)}</td>
                      <td className="px-3 py-2 font-mono text-purple-400">{fmt(d.vision_cost)}</td>
                      <td className="px-3 py-2 font-mono text-green-400">{fmt(d.learning_cost)}</td>
                      <td className="px-3 py-2 font-mono text-amber-400 font-semibold">{fmt(d.total_cost)}</td>
                      <td className="px-3 py-2 text-muted-foreground">{d.last_used ? new Date(d.last_used).toLocaleDateString() : '—'}</td>
                      <td className="px-3 py-2">
                        <Badge variant="outline" className={`text-[10px] ${d.cache_status === 'cached' ? 'text-green-400 border-green-400/30' : 'text-muted-foreground'}`}>
                          {d.cache_status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: AI Chat Cost
// ══════════════════════════════════════════════════════════════════════════════
function ChatCostTab() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useCosts<any>(`chat-${page}`, `/api/costs/chat?page=${page}&limit=50`);
  const reqs = data?.requests ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{data?.total ?? 0} total requests · <span className="text-amber-400">{data?.note}</span></p>
      </div>
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Conv ID</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Model</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Prompt Tok</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Completion Tok</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">RAG Chunks</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">OpenAI Calls</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Cost</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Duration</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={9} className="text-center py-8 text-muted-foreground">Loading…</td></tr>
                ) : reqs.length === 0 ? (
                  <tr><td colSpan={9}><EmptyState message="No chat requests tracked yet — start a conversation to see cost data" /></td></tr>
                ) : reqs.map((r: any) => (
                  <tr key={r.id} className="border-t border-border/50 hover:bg-muted/20">
                    <td className="px-3 py-2 font-mono text-muted-foreground">{r.conversation_id?.slice(0, 8) ?? '—'}</td>
                    <td className="px-3 py-2">{r.model ?? r.agent_mode ?? '—'}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(r.prompt_tokens)}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(r.completion_tokens)}</td>
                    <td className="px-3 py-2 font-mono">{r.rag_chunks_used}</td>
                    <td className="px-3 py-2 font-mono">1</td>
                    <td className="px-3 py-2 font-mono text-amber-400">{fmt(r.est_cost_usd, 6)}</td>
                    <td className="px-3 py-2 font-mono text-muted-foreground">{fmtSecs(r.duration_secs)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Page {page} of {data?.pages ?? 1}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>Prev</Button>
          <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => p + 1)} disabled={page >= (data?.pages ?? 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Translation Cost
// ══════════════════════════════════════════════════════════════════════════════
function TranslationCostTab() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useCosts<any>(`trans-${page}`, `/api/costs/translation?page=${page}&limit=50`);
  const jobs = data?.jobs ?? [];

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{data?.total ?? 0} total jobs — all token counts are real API values</p>
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">File Name</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Provider</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">TM Hits</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">API Calls</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Tokens</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Cost</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Cost/Page</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Cost/1K Words</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Time</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={10} className="text-center py-8 text-muted-foreground">Loading…</td></tr>
                ) : jobs.length === 0 ? (
                  <tr><td colSpan={10}><EmptyState message="No translation jobs yet" /></td></tr>
                ) : jobs.map((j: any) => (
                  <tr key={j.id} className="border-t border-border/50 hover:bg-muted/20">
                    <td className="px-3 py-2 font-medium truncate max-w-40">{j.project_name ?? '—'}</td>
                    <td className="px-3 py-2">{j.provider ?? j.model ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-green-400">{j.memory_hits}</td>
                    <td className="px-3 py-2 font-mono">{j.openai_calls}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum((j.prompt_tokens ?? 0) + (j.completion_tokens ?? 0))}</td>
                    <td className="px-3 py-2 font-mono text-amber-400 font-semibold">{fmt(j.total_cost_usd)}</td>
                    <td className="px-3 py-2 font-mono">{fmt(j.cost_per_page, 6)}</td>
                    <td className="px-3 py-2 font-mono">{fmt(j.cost_per_1k_words, 4)}</td>
                    <td className="px-3 py-2 font-mono text-muted-foreground">{fmtSecs(j.processing_time_secs ?? 0)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{j.created_at ? new Date(j.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Page {page} of {data?.pages ?? 1}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>Prev</Button>
          <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => p + 1)} disabled={page >= (data?.pages ?? 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Learning Hub Cost
// ══════════════════════════════════════════════════════════════════════════════
function LearningCostTab() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useCosts<any>(`learn-${page}`, `/api/costs/learning?page=${page}&limit=50`);
  const jobs = data?.jobs ?? [];

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{data?.total ?? 0} study jobs — token counts from 11-phase learning pipeline</p>
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">File</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Status</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Nodes</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Edges</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">API Calls</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Prompt Tok</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Completion Tok</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Cost</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Learn Time</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={10} className="text-center py-8 text-muted-foreground">Loading…</td></tr>
                ) : jobs.length === 0 ? (
                  <tr><td colSpan={10}><EmptyState message="No study jobs yet" /></td></tr>
                ) : jobs.map((j: any) => (
                  <tr key={j.id} className="border-t border-border/50 hover:bg-muted/20">
                    <td className="px-3 py-2 font-medium truncate max-w-40">{j.filename ?? '—'}</td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className={`text-[10px] ${j.status === 'integrated' ? 'text-green-400 border-green-400/30' : 'text-muted-foreground'}`}>
                        {j.status}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 font-mono text-cyan-400">{fmtNum(j.knowledge_nodes)}</td>
                    <td className="px-3 py-2 font-mono text-pink-400">{fmtNum(j.knowledge_edges)}</td>
                    <td className="px-3 py-2 font-mono">{j.openai_calls}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(j.prompt_tokens)}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(j.completion_tokens)}</td>
                    <td className="px-3 py-2 font-mono text-amber-400 font-semibold">{fmt(j.cost_usd)}</td>
                    <td className="px-3 py-2 font-mono text-muted-foreground">{fmtSecs(j.learning_time_secs ?? 0)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{j.created_at ? new Date(j.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Page {page} of {data?.pages ?? 1}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>Prev</Button>
          <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => p + 1)} disabled={page >= (data?.pages ?? 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Token Analytics
// ══════════════════════════════════════════════════════════════════════════════
function TokenAnalyticsTab() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useCosts<any>(`analytics-${days}`, `/api/costs/token-analytics?days=${days}`);
  const daily = data?.daily ?? [];

  return (
    <div className="space-y-6">
      <div className="flex gap-1 bg-card border border-border rounded-xl p-1.5 w-fit">
        {[7, 14, 30, 90].map(d => (
          <PeriodBadge key={d} active={days === d} label={`${d}d`} onClick={() => setDays(d)} />
        ))}
      </div>

      {isLoading ? <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div> : (
        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-sm flex items-center gap-2"><DollarSign className="h-4 w-4 text-amber-400" /> Daily Cost by Feature</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={daily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                  <YAxis tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} tickFormatter={v => `$${v.toFixed(2)}`} />
                  <Tooltip content={<ChartTip />} />
                  <Area type="monotone" dataKey="translation_cost" stackId="a" stroke="#3b82f6" fill="#3b82f610" name="Translation" />
                  <Area type="monotone" dataKey="vision_cost" stackId="a" stroke="#8b5cf6" fill="#8b5cf610" name="Vision" />
                  <Area type="monotone" dataKey="learning_cost" stackId="a" stroke="#10b981" fill="#10b98110" name="Learning" />
                  <Area type="monotone" dataKey="chat_cost" stackId="a" stroke="#f59e0b" fill="#f59e0b10" name="Chat" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Cpu className="h-4 w-4 text-cyan-400" /> Prompt Tokens per Day</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={daily}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="label" tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} tickFormatter={v => fmtNum(v)} />
                    <Tooltip content={<ChartTip />} />
                    <Bar dataKey="prompt_tokens" fill="#06b6d4" name="Prompt Tokens" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Cpu className="h-4 w-4 text-purple-400" /> Completion Tokens per Day</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={daily}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="label" tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} tickFormatter={v => fmtNum(v)} />
                    <Tooltip content={<ChartTip />} />
                    <Bar dataKey="completion_tokens" fill="#a855f7" name="Completion Tokens" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Zap className="h-4 w-4 text-blue-400" /> API Calls per Day</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={160}>
                  <LineChart data={daily}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="label" tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} />
                    <Tooltip content={<ChartTip />} />
                    <Line type="monotone" dataKey="total_calls" stroke="#3b82f6" name="Total Calls" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm flex items-center gap-2"><TrendingDown className="h-4 w-4 text-green-400" /> Vision Savings per Day</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={daily}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="label" tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }} tickFormatter={v => `$${v.toFixed(3)}`} />
                    <Tooltip content={<ChartTip />} />
                    <Bar dataKey="vision_saved" fill="#10b981" name="Vision Saved" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Savings
// ══════════════════════════════════════════════════════════════════════════════
function SavingsTab() {
  const { data, isLoading } = useCosts<any>('savings', '/api/costs/savings');

  if (isLoading) return <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div>;

  const { breakdown = [], total_saved_usd = 0, actual_cost_usd = 0, estimated_without_usd = 0, savings_pct = 0 } = data ?? {};

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Estimated Without Optimization" value={fmt(estimated_without_usd)} icon={TrendingUp} color="text-red-400" />
        <Stat label="Actual Cost" value={fmt(actual_cost_usd)} icon={DollarSign} color="text-amber-400" />
        <Stat label="Total Saved" value={fmt(total_saved_usd)} icon={TrendingDown} color="text-green-400" />
        <Stat label="Savings %" value={`${savings_pct}%`} icon={Target} color={savings_pct > 30 ? 'text-green-400' : 'text-amber-400'} />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Savings Breakdown by Source</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {breakdown.map((b: any) => (
            <div key={b.source} className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-sm font-medium">{b.source}</span>
                  <span className="text-sm font-mono text-green-400">{fmt(b.saved_usd)}</span>
                </div>
                <div className="h-1.5 bg-muted rounded-full">
                  <div
                    className="h-1.5 bg-green-500 rounded-full transition-all"
                    style={{ width: `${total_saved_usd > 0 ? Math.min(100, b.saved_usd / total_saved_usd * 100) : 0}%` }}
                  />
                </div>
                <p className="text-[10px] text-muted-foreground mt-0.5">{b.detail}</p>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Alerts
// ══════════════════════════════════════════════════════════════════════════════
function AlertsTab() {
  const { data, isLoading } = useCosts<any>('alerts', '/api/costs/alerts', { refetchInterval: 30_000 });

  const alerts = data?.alerts ?? [];
  const levelStyle: Record<string, string> = {
    error:   'border-red-500/30 bg-red-500/5 text-red-400',
    warning: 'border-amber-500/30 bg-amber-500/5 text-amber-400',
    info:    'border-blue-500/30 bg-blue-500/5 text-blue-400',
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat label="Today's Cost" value={fmt(data?.today_cost ?? 0)} icon={DollarSign}
          color={(data?.today_cost ?? 0) > (data?.daily_limit ?? 10) ? 'text-red-400' : 'text-amber-400'} />
        <Stat label="Monthly Cost" value={fmt(data?.month_cost ?? 0)} icon={DollarSign}
          color={(data?.month_cost ?? 0) > (data?.monthly_limit ?? 200) ? 'text-red-400' : 'text-green-400'} />
        <Stat label="Alert Threshold" value={`${fmt(data?.daily_limit ?? 10)} / day`} icon={AlertTriangle} color="text-muted-foreground" />
      </div>

      {isLoading ? <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div> : (
        <>
          {alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <CheckCircle className="h-10 w-10 text-green-400 opacity-60" />
              <p className="text-sm font-medium text-green-400">All systems within budget</p>
              <p className="text-xs text-muted-foreground">No alerts at this time</p>
            </div>
          ) : (
            <div className="space-y-3">
              {alerts.map((a: any, i: number) => (
                <div key={i} className={`flex items-start gap-3 border rounded-xl p-4 ${levelStyle[a.level] ?? ''}`}>
                  <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium">{a.message}</p>
                    <p className="text-[10px] opacity-70 mt-0.5 uppercase tracking-wide">{a.type.replace(/_/g, ' ')}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Top Expensive Operations
// ══════════════════════════════════════════════════════════════════════════════
function TopOperationsTab() {
  const { data, isLoading } = useCosts<any>('top-ops', '/api/costs/top-operations?limit=20');
  const ops = data?.operations ?? [];

  const featureColor: Record<string, string> = {
    'Translation':    'text-blue-400',
    'Image Analysis': 'text-purple-400',
    'Learning Hub':   'text-green-400',
    'AI Chat':        'text-amber-400',
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">Top 20 most expensive operations across all features, sorted by actual cost</p>
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">#</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Feature</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">File</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Model</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Prompt Tok</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Completion Tok</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Duration</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Cost</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={9} className="text-center py-8 text-muted-foreground">Loading…</td></tr>
                ) : ops.length === 0 ? (
                  <tr><td colSpan={9}><EmptyState message="No operations tracked yet" /></td></tr>
                ) : ops.map((op: any, i: number) => (
                  <tr key={op.id} className="border-t border-border/50 hover:bg-muted/20">
                    <td className="px-3 py-2 font-mono text-muted-foreground">{i + 1}</td>
                    <td className="px-3 py-2"><span className={`font-medium ${featureColor[op.feature] ?? ''}`}>{op.feature}</span></td>
                    <td className="px-3 py-2 truncate max-w-32">{op.file ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-muted-foreground">{op.model ?? '—'}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(op.prompt_tokens ?? 0)}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(op.completion_tokens ?? 0)}</td>
                    <td className="px-3 py-2 font-mono text-muted-foreground">{fmtSecs(op.duration_secs ?? 0)}</td>
                    <td className="px-3 py-2 font-mono text-amber-400 font-semibold">{fmt(op.cost_usd, 6)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{op.created_at ? new Date(op.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Request Inspector
// ══════════════════════════════════════════════════════════════════════════════
function RequestInspectorTab() {
  const [page, setPage] = useState(1);
  const [featureFilter, setFeatureFilter] = useState('');
  const [modelFilter, setModelFilter] = useState('');
  const [selected, setSelected] = useState<any>(null);

  const path = `/api/costs/logs?page=${page}&limit=50${featureFilter ? `&feature=${featureFilter}` : ''}${modelFilter ? `&model=${modelFilter}` : ''}`;
  const { data, isLoading } = useCosts<any>(`logs-${page}-${featureFilter}-${modelFilter}`, path);
  const logs = data?.logs ?? [];

  const featureColor: Record<string, string> = {
    'Translation': 'text-blue-400',
    'Image Analysis': 'text-purple-400',
    'Learning Hub': 'text-green-400',
    'AI Chat': 'text-amber-400',
  };

  return (
    <div className="grid lg:grid-cols-3 gap-4">
      {/* List pane */}
      <div className="lg:col-span-2 space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Filter className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              className="pl-8 h-8 text-xs"
              placeholder="Filter by feature…"
              value={featureFilter}
              onChange={e => { setFeatureFilter(e.target.value); setPage(1); }}
            />
          </div>
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              className="pl-8 h-8 text-xs"
              placeholder="Filter by model…"
              value={modelFilter}
              onChange={e => { setModelFilter(e.target.value); setPage(1); }}
            />
          </div>
          {(featureFilter || modelFilter) && (
            <Button size="sm" variant="ghost" className="h-8 text-xs px-2" onClick={() => { setFeatureFilter(''); setModelFilter(''); }}>
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/30">
                  <tr>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Timestamp</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Feature</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Model</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Tokens</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground">Cost</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground"></th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={6} className="text-center py-8 text-muted-foreground">Loading…</td></tr>
                  ) : logs.length === 0 ? (
                    <tr><td colSpan={6}><EmptyState message="No logs found" /></td></tr>
                  ) : logs.map((log: any) => (
                    <tr
                      key={log.id}
                      className={`border-t border-border/50 cursor-pointer hover:bg-muted/30 ${selected?.id === log.id ? 'bg-primary/10' : ''}`}
                      onClick={() => setSelected(log)}
                    >
                      <td className="px-3 py-2 font-mono text-muted-foreground text-[10px]">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-3 py-2"><span className={`font-medium ${featureColor[log.feature] ?? ''}`}>{log.feature}</span></td>
                      <td className="px-3 py-2 font-mono text-muted-foreground">{log.model ?? '—'}</td>
                      <td className="px-3 py-2 font-mono">{fmtNum((log.prompt_tokens ?? 0) + (log.completion_tokens ?? 0))}</td>
                      <td className="px-3 py-2 font-mono text-amber-400">{fmt(log.cost_usd, 6)}</td>
                      <td className="px-3 py-2"><ChevronRight className="h-3 w-3 text-muted-foreground" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{data?.total ?? 0} total · Page {page} of {data?.pages ?? 1}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>Prev</Button>
            <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setPage(p => p + 1)} disabled={page >= (data?.pages ?? 1)}>Next</Button>
          </div>
        </div>
      </div>

      {/* Detail pane */}
      <div>
        {selected ? (
          <Card className="sticky top-4">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Request Detail</CardTitle>
                <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => setSelected(null)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              {[
                ['Timestamp', selected.created_at ? new Date(selected.created_at).toLocaleString() : '—'],
                ['Feature', selected.feature],
                ['Endpoint', selected.endpoint],
                ['Model', selected.model ?? '—'],
                ['Prompt Tokens', fmtNum(selected.prompt_tokens ?? 0)],
                ['Completion Tokens', fmtNum(selected.completion_tokens ?? 0)],
                ['Cache Tokens', fmtNum(selected.cache_tokens ?? 0)],
                ['RAG Chunks', selected.rag_chunks ?? 0],
                ['Duration', fmtSecs(selected.duration_secs ?? 0)],
                ['Finish Reason', selected.finish_reason ?? '—'],
                ['Cost', fmt(selected.cost_usd, 6)],
              ].map(([k, v]) => (
                <div key={k as string} className="flex justify-between gap-2 border-b border-border/30 pb-1">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="font-mono font-medium text-right">{v}</span>
                </div>
              ))}

              <div>
                <p className="text-[10px] uppercase text-muted-foreground font-mono mb-1">Raw API Usage</p>
                <pre className="text-[10px] bg-muted/40 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(selected.raw_usage, null, 2)}
                </pre>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col items-center justify-center h-48 text-muted-foreground gap-2">
            <Search className="h-8 w-8 opacity-30" />
            <p className="text-xs">Click a request to inspect it</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Export
// ══════════════════════════════════════════════════════════════════════════════
function ExportTab() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [feature, setFeature] = useState('all');

  const handleExport = async (format: string) => {
    setLoading(true);
    try {
      const url = `${API}/api/costs/export?format=${format}&feature=${feature}`;
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) throw new Error(res.statusText);
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `xray_cost_export.${format}`;
      a.click();
      toast({ title: 'Export complete', description: `${format.toUpperCase()} downloaded` });
    } catch {
      toast({ title: 'Export failed', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-xl space-y-6">
      <div className="space-y-3">
        <Label className="text-xs uppercase font-mono text-muted-foreground">Feature Filter</Label>
        <div className="flex flex-wrap gap-2">
          {['all', 'translation', 'vision', 'learning', 'chat'].map(f => (
            <PeriodBadge key={f} active={feature === f} label={f === 'all' ? 'All Features' : f.charAt(0).toUpperCase() + f.slice(1)} onClick={() => setFeature(f)} />
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <Label className="text-xs uppercase font-mono text-muted-foreground">Export Format</Label>
        <div className="grid grid-cols-3 gap-3">
          {[
            { format: 'csv', label: 'CSV', desc: 'All major apps' },
            { format: 'csv', label: 'Excel', desc: 'Download CSV and open in Excel' },
            { format: 'csv', label: 'PDF', desc: 'Download CSV as report-ready data' },
          ].map(({ format, label, desc }) => (
            <button
              key={label}
              onClick={() => handleExport(format)}
              disabled={loading}
              className="flex flex-col items-center gap-2 p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-primary/5 transition-colors disabled:opacity-50"
            >
              <Download className="h-6 w-6 text-primary" />
              <span className="text-sm font-semibold">{label}</span>
              <span className="text-[10px] text-muted-foreground text-center">{desc}</span>
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Exports include real API usage data from all tracked features. Columns: feature, timestamp, file, model, provider, prompt tokens, completion tokens, cost, duration, status.
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Settings
// ══════════════════════════════════════════════════════════════════════════════
function SettingsTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data } = useCosts<any>('settings', '/api/costs/settings');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    budget_daily_usd: '',
    budget_weekly_usd: '',
    budget_monthly_usd: '',
    alert_threshold_pct: '',
    budget_per_request_usd: '',
  });

  const merged = {
    budget_daily_usd:     form.budget_daily_usd      || data?.budget_daily_usd      || '10',
    budget_weekly_usd:    form.budget_weekly_usd     || data?.budget_weekly_usd     || '50',
    budget_monthly_usd:   form.budget_monthly_usd    || data?.budget_monthly_usd    || '200',
    alert_threshold_pct:  form.alert_threshold_pct   || data?.alert_threshold_pct   || '80',
    budget_per_request_usd: form.budget_per_request_usd || data?.max_cost_per_request || '0.50',
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiFetch('/api/costs/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(merged),
      });
      qc.invalidateQueries({ queryKey: ['costs', 'settings'] });
      qc.invalidateQueries({ queryKey: ['costs', 'alerts'] });
      toast({ title: 'Settings saved' });
    } catch {
      toast({ title: 'Save failed', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const Field = ({ label, name, prefix = '$', hint }: { label: string; name: keyof typeof merged; prefix?: string; hint?: string }) => (
    <div className="space-y-1">
      <Label className="text-xs font-medium">{label}</Label>
      <div className="relative">
        <span className="absolute left-3 top-2 text-xs text-muted-foreground">{prefix}</span>
        <Input
          className="pl-6 h-8 text-xs"
          type="number"
          step="0.01"
          min="0"
          value={merged[name]}
          onChange={e => setForm(f => ({ ...f, [name]: e.target.value }))}
        />
      </div>
      {hint && <p className="text-[10px] text-muted-foreground">{hint}</p>}
    </div>
  );

  return (
    <div className="max-w-md space-y-6">
      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Settings className="h-4 w-4" /> Budget Configuration</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Field label="Daily Budget" name="budget_daily_usd" hint="Alert when today's cost exceeds this amount" />
          <Field label="Weekly Budget" name="budget_weekly_usd" hint="Alert when 7-day cost exceeds this amount" />
          <Field label="Monthly Budget" name="budget_monthly_usd" hint="Alert when monthly cost exceeds this amount" />
          <Field label="Alert Threshold %" name="alert_threshold_pct" prefix="%" hint="Alert at this % of budget (e.g. 80 = warn at 80%)" />
          <Field label="Max Cost per Request" name="budget_per_request_usd" hint="Alert on single requests exceeding this cost" />
        </CardContent>
      </Card>
      <Button onClick={handleSave} disabled={saving} className="w-full">
        {saving ? 'Saving…' : 'Save Settings'}
      </Button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Recommendations
// ══════════════════════════════════════════════════════════════════════════════
function RecommendationsTab() {
  const { data, isLoading } = useCosts<any>('recs', '/api/costs/recommendations');
  const recs = data?.recommendations ?? [];

  const priorityStyle: Record<string, { border: string; badge: string; icon: string }> = {
    high:   { border: 'border-red-500/30 bg-red-500/5',    badge: 'bg-red-500/20 text-red-400',    icon: 'text-red-400' },
    medium: { border: 'border-amber-500/30 bg-amber-500/5', badge: 'bg-amber-500/20 text-amber-400', icon: 'text-amber-400' },
    low:    { border: 'border-blue-500/30 bg-blue-500/5',  badge: 'bg-blue-500/20 text-blue-400',  icon: 'text-blue-400' },
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">Auto-generated recommendations based on actual usage patterns</p>
      {isLoading ? <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div> : (
        <div className="space-y-3">
          {recs.length === 0 ? <EmptyState message="No recommendations — usage looks optimal!" /> : (
            recs.map((r: any, i: number) => {
              const style = priorityStyle[r.priority] ?? priorityStyle.low;
              return (
                <div key={i} className={`border rounded-xl p-4 ${style.border}`}>
                  <div className="flex items-start gap-3">
                    <Lightbulb className={`h-5 w-5 mt-0.5 shrink-0 ${style.icon}`} />
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold">{r.recommendation}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono uppercase ${style.badge}`}>
                          {r.priority}
                        </span>
                        <Badge variant="outline" className="text-[10px]">{r.category}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">{r.detail}</p>
                      <p className="text-[10px] font-medium text-green-400">Potential saving: {r.potential_saving}</p>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: High-Risk Cost Controls — 7 permanent rows, never hidden at $0
// ══════════════════════════════════════════════════════════════════════════════
function HighRiskControlsTab() {
  const { data, isLoading } = useCosts<any>('high-risk-summary', '/api/costs/high-risk-summary', { refetchInterval: 60_000 });
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [verifyBusy,   setVerifyBusy]   = useState(false);
  const [expandedRow,  setExpandedRow]  = useState<string | null>(null);
  const qc = useQueryClient();
  const { toast } = useToast();

  const summary: any = data?.summary ?? {};
  const rows: any[]  = data?.rows    ?? [];

  const handleDisable = async (row: any) => {
    if (!row.disable_endpoint) return;
    if (!window.confirm(`Disable "${row.cost_risk}"? This will block all related processing immediately.`)) return;
    try {
      const res = await fetch(`${API}${row.disable_endpoint}`, { method: 'POST', credentials: 'include' });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: `${row.cost_risk} disabled` });
      qc.invalidateQueries({ queryKey: ['costs'] });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const handleVerify = async () => {
    setVerifyBusy(true);
    try {
      const res = await fetch(`${API}/api/costs/verify-protection`, { method: 'POST', credentials: 'include' });
      if (!res.ok) throw new Error(await res.text());
      setVerifyResult(await res.json());
    } catch (e: any) {
      toast({ title: 'Verify failed', description: e.message, variant: 'destructive' });
    } finally { setVerifyBusy(false); }
  };

  const overallStatus = summary.overall_status ?? 'unverified';
  const headerBg = overallStatus === 'protected' ? 'border-green-500/40 bg-green-500/5'
    : overallStatus === 'at_risk' ? 'border-red-500/50 bg-red-500/10'
    : 'border-amber-500/40 bg-amber-500/5';

  return (
    <div className="space-y-6">

      {/* ── Summary card ──────────────────────────────────────────────── */}
      <div className={`rounded-xl border-2 p-5 ${headerBg}`}>
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5" />
          <span className="font-bold text-sm uppercase tracking-wide">High-Risk Cost Controls</span>
          <Badge variant="outline" className={`text-[10px] ml-1 ${PROT_STATUS[overallStatus]?.badge}`}>
            {PROT_STATUS[overallStatus]?.label ?? 'Unverified'}
          </Badge>
          <Button size="sm" variant="outline" className="ml-auto text-xs h-7 gap-1.5" onClick={handleVerify} disabled={verifyBusy}>
            <ShieldCheck className="h-3.5 w-3.5" />
            {verifyBusy ? 'Checking…' : 'Verify Protection'}
          </Button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            { label: 'Historical Avoidable',  value: '$40–55 / session', sub: 'Image Captioning incident', color: 'text-amber-400' },
            { label: 'Current Protected Cost', value: fmt(summary.total_current_cost_usd ?? 0), sub: 'all tracked features', color: 'text-foreground' },
            { label: 'Estimated Savings',      value: fmt(summary.total_estimated_savings_usd ?? 0), sub: 'dedup + cache hits', color: 'text-green-400' },
            { label: 'Protected Categories',   value: `${summary.protected_categories ?? 0} / 7`, sub: 'verified active', color: 'text-green-400' },
            { label: 'At Risk / Unverified',   value: `${(summary.unprotected_categories ?? 0)} / ${(summary.unverified_categories ?? 0)}`, sub: 'needs attention', color: (summary.unprotected_categories ?? 0) > 0 ? 'text-red-400' : 'text-amber-400' },
          ].map(s => (
            <div key={s.label} className="bg-card/60 border border-border/50 rounded-lg p-3">
              <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">{s.label}</div>
              <div className={`text-lg font-bold tabular-nums mt-0.5 ${s.color}`}>{s.value}</div>
              <div className="text-[10px] text-muted-foreground">{s.sub}</div>
            </div>
          ))}
        </div>

        <div className="mt-3 text-[10px] text-muted-foreground border-t border-border/30 pt-2">
          Distinguishes: <span className="text-foreground">actual current cost</span> ·
          <span className="text-amber-400"> historical cost</span> ·
          <span className="text-green-400"> estimated avoided cost</span> ·
          <span className="text-blue-400"> estimated savings</span> ·
          <span className="text-orange-400"> untracked cost</span>
        </div>
      </div>

      {/* ── Verify protection results ──────────────────────────────────── */}
      {verifyResult && (
        <Card className={verifyResult.overall === 'pass' ? 'border-green-500/30' : verifyResult.overall === 'fail' ? 'border-red-500/30' : 'border-amber-500/30'}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <ShieldCheck className="h-4 w-4" />
              Protection Verification — {verifyResult.passed}/{verifyResult.total} checks passed
              <Badge variant="outline" className={`text-[10px] ml-auto ${verifyResult.overall === 'pass' ? 'text-green-400 border-green-400/40' : verifyResult.overall === 'fail' ? 'text-red-400 border-red-400/40' : 'text-amber-400 border-amber-400/40'}`}>
                {verifyResult.overall.toUpperCase()}
              </Badge>
              <button className="text-muted-foreground hover:text-foreground ml-1" onClick={() => setVerifyResult(null)}><X className="h-3.5 w-3.5" /></button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {verifyResult.checks.map((c: any, i: number) => (
              <div key={i} className={`flex items-start gap-2 text-xs rounded-lg px-3 py-2 ${c.status === 'pass' ? 'bg-green-500/5' : 'bg-red-500/5'}`}>
                {c.status === 'pass'
                  ? <CheckCircle className="h-3.5 w-3.5 text-green-400 shrink-0 mt-0.5" />
                  : <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />}
                <div>
                  <span className="font-medium">{c.name}</span>
                  <span className="text-muted-foreground ml-2">{c.detail}</span>
                  {c.fix && <div className="text-amber-400 mt-0.5">Fix: {c.fix}</div>}
                </div>
              </div>
            ))}
            <p className="text-[10px] text-muted-foreground pt-1">{verifyResult.note}</p>
          </CardContent>
        </Card>
      )}

      {/* ── 7-row permanent table ──────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            High-Risk Cost Categories — Always Visible (7 permanent rows)
            <Badge variant="outline" className="text-[10px] text-muted-foreground ml-auto">
              Zero-value rows are never hidden
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/30">
                  <tr>
                    {['Cost Risk', 'Current Actual Cost', 'Historical Cost', 'Est. Savings', 'Status', 'Protection Applied', 'Last Activity', 'Action'].map(h => (
                      <th key={h} className="px-3 py-2.5 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row: any) => {
                    const st = PROT_STATUS[row.protection_status] ?? PROT_STATUS.unverified;
                    const expanded = expandedRow === row.id;
                    return (
                      <>
                        <tr key={row.id} className={`border-t border-border/50 hover:bg-muted/20 ${st.row}`}>
                          {/* Cost Risk */}
                          <td className="px-3 py-2.5">
                            <button
                              className="text-left font-semibold hover:text-primary flex items-center gap-1"
                              onClick={() => setExpandedRow(expanded ? null : row.id)}
                            >
                              <ChevronRight className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`} />
                              {row.cost_risk}
                            </button>
                          </td>
                          {/* Current Actual Cost */}
                          <td className="px-3 py-2.5 font-mono">
                            {row.actual_cost_usd > 0
                              ? <span className="text-amber-400">{fmt(row.actual_cost_usd, 6)}</span>
                              : <span className="text-muted-foreground">$0</span>}
                          </td>
                          {/* Historical Cost */}
                          <td className="px-3 py-2.5 font-mono text-orange-400 whitespace-nowrap">{row.historical_cost}</td>
                          {/* Estimated Savings */}
                          <td className="px-3 py-2.5 font-mono text-green-400">
                            {row.estimated_savings_usd > 0 ? fmt(row.estimated_savings_usd, 4) : '—'}
                          </td>
                          {/* Status */}
                          <td className="px-3 py-2.5">
                            <Badge variant="outline" className={`text-[10px] ${st.badge}`}>{st.label}</Badge>
                          </td>
                          {/* Protection Applied */}
                          <td className="px-3 py-2.5 max-w-[180px]">
                            <div className="flex flex-wrap gap-0.5">
                              {(row.protection_applied ?? []).map((p: string) => (
                                <span key={p} className="text-[10px] bg-muted/50 rounded px-1 py-0.5 whitespace-nowrap">{p}</span>
                              ))}
                            </div>
                          </td>
                          {/* Last Activity */}
                          <td className="px-3 py-2.5 text-muted-foreground text-[10px] whitespace-nowrap">
                            {row.last_activity ? new Date(row.last_activity).toLocaleDateString() : '—'}
                          </td>
                          {/* Actions */}
                          <td className="px-3 py-2.5">
                            <div className="flex gap-1 flex-wrap">
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-[10px] h-6 px-2"
                                onClick={() => setExpandedRow(expanded ? null : row.id)}
                              >
                                View Details
                              </Button>
                              {row.can_disable && (
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  className="text-[10px] h-6 px-2"
                                  onClick={() => handleDisable(row)}
                                >
                                  Disable
                                </Button>
                              )}
                            </div>
                          </td>
                        </tr>
                        {/* Expanded detail row */}
                        {expanded && (
                          <tr key={`${row.id}-detail`} className="bg-muted/10">
                            <td colSpan={8} className="px-4 py-3">
                              <div className="grid md:grid-cols-3 gap-4 text-xs">
                                <div>
                                  <div className="text-[10px] uppercase font-mono text-muted-foreground mb-1">Cost Breakdown</div>
                                  <div><span className="text-muted-foreground">Actual current:</span> <span className="font-mono text-amber-400">{fmt(row.actual_cost_usd, 6)}</span></div>
                                  <div><span className="text-muted-foreground">Historical:</span> <span className="font-mono text-orange-400">{row.historical_cost}</span></div>
                                  <div><span className="text-muted-foreground">Savings:</span> <span className="font-mono text-green-400">{row.estimated_savings_label}</span></div>
                                </div>
                                <div>
                                  <div className="text-[10px] uppercase font-mono text-muted-foreground mb-1">Protection Details</div>
                                  {(row.protection_applied ?? []).map((p: string) => (
                                    <div key={p} className="flex items-center gap-1">
                                      <CheckCircle className="h-3 w-3 text-green-400 shrink-0" />{p}
                                    </div>
                                  ))}
                                </div>
                                <div>
                                  <div className="text-[10px] uppercase font-mono text-muted-foreground mb-1">Notes</div>
                                  <div className="text-muted-foreground">{row.notes}</div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Historical incident — permanent record ────────────────────── */}
      <Card className="border-orange-500/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-orange-400">
            <AlertTriangle className="h-4 w-4" />
            Historical Incident Record — Always Visible
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-orange-500/20 bg-orange-500/5 p-4 text-xs space-y-1.5">
            <div className="font-semibold text-orange-400">Image Captioning Incident</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2">
              {[
                { label: 'Estimated Cost',    value: '$40–55', color: 'text-red-400' },
                { label: 'Period',            value: 'Per session (pre-fix)', color: 'text-muted-foreground' },
                { label: 'Status',            value: 'Historical / Not Active', color: 'text-orange-400' },
                { label: 'Root Cause',        value: 'No kill switch / no limits', color: 'text-muted-foreground' },
              ].map(item => (
                <div key={item.label}>
                  <div className="text-[10px] font-mono uppercase text-muted-foreground">{item.label}</div>
                  <div className={`font-bold mt-0.5 ${item.color}`}>{item.value}</div>
                </div>
              ))}
            </div>
            <p className="text-muted-foreground pt-1">
              This record is permanent and will remain visible even when current cost is $0.00.
              Protection is now verified via kill switch (VISION_ENABLED=false), per-job cap, local pixel filter,
              SHA-256 deduplication, and SHA-256 caption cache.
            </p>
          </div>
        </CardContent>
      </Card>

    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Vision Protection — 12 permanent categories + kill switch + incident log
// ══════════════════════════════════════════════════════════════════════════════
const VISION_STATUS_COLORS: Record<string, string> = {
  'Active':   'text-green-400 border-green-400/30',
  'Disabled': 'text-red-400 border-red-400/30',
  'Blocked':  'text-orange-400 border-orange-400/30',
  'No usage': 'text-muted-foreground border-muted-foreground/30',
};

function VisionProtectionTab() {
  const [period, setPeriod] = useState('lifetime');
  const { data: cats,  isLoading: catsLoading }  = useCosts<any>(`vision-cats-${period}`,  `/api/vision/categories?period=${period}`);
  const { data: prot,  isLoading: protLoading }  = useCosts<any>('vision-protection',      '/api/vision/protection', { refetchInterval: 30_000 });
  const { data: valerts, isLoading: valLoading } = useCosts<any>('vision-alerts',          '/api/vision/alerts', { refetchInterval: 30_000 });
  const qc = useQueryClient();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);

  const enabled  = prot?.kill_switch?.vision_enabled ?? false;
  const limits   = prot?.limits  ?? {};
  const usage    = prot?.current_usage ?? {};
  const remain   = prot?.remaining_allowance ?? {};
  const incident = prot?.historical_incident ?? {};
  const categories: any[] = cats?.categories ?? [];
  const vAlerts: any[] = valerts?.alerts ?? [];

  const handleKillSwitch = async () => {
    if (!window.confirm('This will immediately block ALL Vision processing — image captioning, gallery reindex, and RAG vision. Continue?')) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/vision/kill-switch`, { method: 'POST', credentials: 'include' });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: '🔴 Vision Disabled', description: 'All vision calls are now blocked.' });
      qc.invalidateQueries({ queryKey: ['costs'] });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally { setBusy(false); }
  };

  const handleEnable = async () => {
    if (!window.confirm('Re-enable Vision? Verify limits below are acceptable before continuing.')) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/vision/enable`, { method: 'POST', credentials: 'include' });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: '✅ Vision Enabled' });
      qc.invalidateQueries({ queryKey: ['costs'] });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">

      {/* ── Emergency kill switch card ─────────────────────────────────── */}
      <div className={`rounded-xl border-2 p-5 ${enabled ? 'border-amber-500/50 bg-amber-500/5' : 'border-red-600/60 bg-red-600/10'}`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <ShieldAlert className={`h-6 w-6 ${enabled ? 'text-amber-400' : 'text-red-400'}`} />
            <div>
              <div className="font-bold text-sm flex items-center gap-2">
                VISION COST PROTECTION
                <Badge variant="outline" className={`text-[10px] ${enabled ? 'text-amber-400 border-amber-400/40' : 'text-red-400 border-red-400/40'}`}>
                  {enabled ? '⚡ ENABLED' : '🔒 DISABLED (safe default)'}
                </Badge>
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">
                {enabled
                  ? 'Vision is active — calls are metered against the limits below.'
                  : 'Vision is OFF. Image captioning, gallery reindex, and RAG vision are all blocked.'}
              </div>
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            {enabled ? (
              <Button variant="destructive" size="sm" className="text-xs gap-1.5 h-8 font-bold" onClick={handleKillSwitch} disabled={busy}>
                <Ban className="h-4 w-4" />
                🚨 Disable All Vision Processing
              </Button>
            ) : (
              <Button variant="outline" size="sm" className="text-xs gap-1.5 h-8 border-green-500/40 text-green-400 hover:bg-green-500/10" onClick={handleEnable} disabled={busy}>
                <Unlock className="h-4 w-4" />
                Re-enable Vision
              </Button>
            )}
          </div>
        </div>

        {/* Hard limits grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
          {[
            { label: 'Max Calls / Job',    value: String(limits.max_calls_per_job ?? 10),              current: `${usage.daily_calls ?? 0} calls today`,    remain: null },
            { label: 'Max Cost / Job',     value: `${(limits.max_cost_per_job_usd ?? 0.50).toFixed(2)}`,  current: null, remain: null },
            { label: 'Max Daily Cost',     value: `${(limits.max_daily_cost_usd ?? 2).toFixed(2)}`,   current: `${(usage.daily_cost_usd ?? 0).toFixed(6)} used`,   remain: `${(remain.daily_cost_usd ?? 0).toFixed(6)} left` },
            { label: 'Max Monthly Cost',   value: `${(limits.max_monthly_cost_usd ?? 10).toFixed(2)}`, current: `${(usage.monthly_cost_usd ?? 0).toFixed(6)} used`, remain: `${(remain.monthly_cost_usd ?? 0).toFixed(6)} left` },
          ].map(item => (
            <div key={item.label} className="bg-card/50 border border-border/40 rounded-lg p-3">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wide font-mono">{item.label}</div>
              <div className="text-xl font-bold tabular-nums mt-0.5">{item.value}</div>
              {item.current && <div className="text-[10px] text-amber-400 tabular-nums mt-0.5">{item.current}</div>}
              {item.remain  && <div className="text-[10px] text-green-400 tabular-nums">{item.remain}</div>}
            </div>
          ))}
        </div>

        <div className="mt-3 text-[10px] text-muted-foreground border-t border-border/30 pt-2">
          🛡 Text extraction · OCR · document parsing · translation · local image hashing remain active when Vision is disabled.
          {' '}No automatic limit overrides are permitted.
        </div>
      </div>

      {/* ── Vision alerts ─────────────────────────────────────────────── */}
      {vAlerts.length > 0 && (
        <div className="space-y-2">
          {vAlerts.map((a: any, i: number) => (
            <div key={i} className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-xs ${
              a.level === 'error'   ? 'border-red-500/40 bg-red-500/10 text-red-300' :
              a.level === 'warning' ? 'border-amber-500/40 bg-amber-500/10 text-amber-300' :
              'border-blue-500/40 bg-blue-500/10 text-blue-300'
            }`}>
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">[{a.type.replace(/_/g, ' ').toUpperCase()}]</span>{' '}
                {a.message}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 12 permanent categories ───────────────────────────────────── */}
      <div className="flex flex-wrap gap-1 bg-card border border-border rounded-xl p-1.5">
        {Object.entries(PERIOD_LABELS).map(([key, label]) => (
          <PeriodBadge key={key} active={period === key} label={label} onClick={() => setPeriod(key)} />
        ))}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Eye className="h-4 w-4 text-purple-400" />
            Vision Cost Categories — Always Visible (12 permanent)
            <Badge variant="outline" className="text-[10px] text-muted-foreground ml-auto">Zero-value categories remain visible per financial visibility policy</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {catsLoading ? (
            <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/30">
                  <tr>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Category</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Status</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Cost</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Requests</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Images</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Tokens</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Cache Hits</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Dupes Skipped</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Blocked</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Cost Avoided</th>
                    <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Last Activity</th>
                  </tr>
                </thead>
                <tbody>
                  {categories.map((cat: any) => {
                    const statusColor = VISION_STATUS_COLORS[cat.status] ?? VISION_STATUS_COLORS['No usage'];
                    return (
                      <tr key={cat.name} className="border-t border-border/50 hover:bg-muted/20">
                        <td className="px-3 py-2">
                          <div className="font-medium">{cat.name}</div>
                          {cat.note && <div className="text-[10px] text-muted-foreground mt-0.5 max-w-xs">{cat.note}</div>}
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant="outline" className={`text-[10px] ${statusColor}`}>{cat.status}</Badge>
                        </td>
                        <td className="px-3 py-2 font-mono text-amber-400">{cat.cost_usd > 0 ? fmt(cat.cost_usd, 6) : <span className="text-muted-foreground">$0</span>}</td>
                        <td className="px-3 py-2 font-mono">{cat.requests}</td>
                        <td className="px-3 py-2 font-mono">{cat.images}</td>
                        <td className="px-3 py-2 font-mono">{fmtNum(cat.tokens)}</td>
                        <td className="px-3 py-2 font-mono text-green-400">{cat.cache_hits}</td>
                        <td className="px-3 py-2 font-mono text-blue-400">{cat.duplicate_images_skipped}</td>
                        <td className="px-3 py-2 font-mono text-orange-400">{cat.requests_blocked}</td>
                        <td className="px-3 py-2 font-mono text-green-400">{cat.estimated_cost_avoided_usd > 0 ? fmt(cat.estimated_cost_avoided_usd, 6) : '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground text-[10px]">
                          {cat.last_activity ? new Date(cat.last_activity).toLocaleDateString() : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Historical incident record ────────────────────────────────── */}
      <Card className="border-orange-500/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-orange-400">
            <AlertTriangle className="h-4 w-4" />
            Historical Incident Record — Permanent
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-start gap-3 rounded-lg border border-orange-500/20 bg-orange-500/5 p-4">
            <div className="space-y-1.5 text-xs">
              <div className="font-semibold text-orange-400">Previous Image Captioning Incident</div>
              <div><span className="text-muted-foreground">Estimated historical cost:</span> <span className="text-amber-400 font-bold font-mono">$40–55</span></div>
              <div><span className="text-muted-foreground">Status:</span> <Badge variant="outline" className="text-[10px] text-orange-400 border-orange-400/30 ml-1">Historical / Not currently active</Badge></div>
              <div className="text-muted-foreground pt-1">{incident.description || 'Auto-captioning ran on every uploaded page without user confirmation, resulting in hundreds of unintended GPT Vision calls.'}</div>
              <div className="text-muted-foreground"><strong className="text-foreground">Root cause:</strong> {incident.root_cause || 'process_rag_image() called automatically with no kill switch, no per-job limit, and no user confirmation dialog.'}</div>
              <div className="text-muted-foreground"><strong className="text-foreground">Resolution:</strong> {incident.resolution || 'vision_guard.py deployed with kill switch, SHA-256 dedup, local pixel filter, and per-job limits. VISION_ENABLED=false by default.'}</div>
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground">
            This record is permanent and will remain visible even when current vision cost is $0.
          </p>
        </CardContent>
      </Card>

    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Reconcile — root-cause report for the billing gap
// ══════════════════════════════════════════════════════════════════════════════
function ReconcileTab() {
  const { data, isLoading } = useCosts<any>('reconcile', '/api/costs/reconcile');

  if (isLoading) return <div className="text-center py-8 text-muted-foreground text-sm">Loading reconciliation report…</div>;
  if (!data) return <EmptyState message="Reconciliation data unavailable" />;

  const legacy = data.legacy_tracked ?? {};
  const unified = data.unified_log ?? {};
  const prevUntracked: any[] = data.previously_untracked_features ?? [];

  return (
    <div className="space-y-6">

      {/* Banner */}
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-400">Historical gap is not recoverable</p>
            <p className="text-xs text-muted-foreground mt-1">{data.coverage_note}</p>
          </div>
        </div>
      </div>

      {/* Grand total */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total Recorded (all time)" value={`${(data.grand_total_recorded_usd ?? 0).toFixed(4)}`}
              color="text-amber-400" icon={DollarSign} />
        <Stat label="Total API Calls Logged" value={fmtNum(data.grand_total_calls ?? 0)} icon={Cpu} />
        <Stat label="Legacy Tables Total" value={`${(legacy.total_usd ?? 0).toFixed(4)}`} icon={Database} />
        <Stat label="Unified Log Total (new)" value={`${(unified.total_usd ?? 0).toFixed(4)}`}
              color={unified.total_usd > 0 ? 'text-green-400' : 'text-muted-foreground'} icon={CheckCircle} />
      </div>

      {/* Legacy breakdown */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Database className="h-4 w-4 text-blue-400" />
            Legacy Tracked Tables (were already in the dashboard)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-xs">
            <thead className="bg-muted/30">
              <tr>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Feature</th>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Recorded Cost</th>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(legacy.breakdown ?? {}).map(([feat, cost]: [string, any]) => (
                <tr key={feat} className="border-t border-border/50">
                  <td className="px-3 py-2 font-medium">{feat}</td>
                  <td className="px-3 py-2 font-mono text-amber-400">{fmt(cost)}</td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className="text-[10px] text-green-400 border-green-400/30">✓ Tracked</Badge>
                  </td>
                </tr>
              ))}
              <tr className="border-t border-border bg-muted/20 font-semibold">
                <td className="px-3 py-2">Subtotal</td>
                <td className="px-3 py-2 font-mono text-amber-400">{fmt(legacy.total_usd ?? 0)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Newly tracked via unified log */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-400" />
            Unified Log — Previously Untracked Features (now captured)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {unified.by_feature?.length === 0 ? (
            <div className="px-4 py-6 text-xs text-muted-foreground">
              No data yet — these features now write to <code>openai_usage_log</code> on every API call.
              Use Innovation Engine, Training Generator, etc. and costs will appear here.
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Feature</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Calls</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Prompt Tokens</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Completion Tokens</th>
                  <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Recorded Cost</th>
                </tr>
              </thead>
              <tbody>
                {(unified.by_feature ?? []).map((f: any) => (
                  <tr key={f.feature} className="border-t border-border/50">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <Pill color={FEATURE_COLORS[f.feature] ?? '#6b7280'} />
                        <span className="font-medium">{f.feature}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 font-mono">{fmtNum(f.calls)}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(f.prompt_tokens)}</td>
                    <td className="px-3 py-2 font-mono">{fmtNum(f.completion_tokens)}</td>
                    <td className="px-3 py-2 font-mono text-amber-400">{fmt(f.cost_usd)}</td>
                  </tr>
                ))}
                <tr className="border-t border-border bg-muted/20 font-semibold">
                  <td className="px-3 py-2">Subtotal</td>
                  <td className="px-3 py-2 font-mono">{fmtNum(unified.total_calls ?? 0)}</td>
                  <td colSpan={2} />
                  <td className="px-3 py-2 font-mono text-amber-400">{fmt(unified.total_usd ?? 0)}</td>
                </tr>
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Root cause breakdown */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            Root Cause Analysis — Why the Dashboard Showed $0.36 vs $53
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-xs">
            <thead className="bg-muted/30">
              <tr>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Feature</th>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Model</th>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Cost Profile</th>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Now Tracked</th>
                <th className="px-3 py-2 text-left text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Recorded</th>
              </tr>
            </thead>
            <tbody>
              {prevUntracked.map((f: any) => (
                <tr key={f.feature} className="border-t border-border/50">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <Pill color={FEATURE_COLORS[f.feature] ?? '#6b7280'} />
                      <div>
                        <div className="font-medium">{f.feature}</div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">{f.note}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground font-mono">{f.model}</td>
                  <td className="px-3 py-2 text-muted-foreground">{f.calls_per_report}</td>
                  <td className="px-3 py-2">
                    {f.tracked_since_fix
                      ? <Badge variant="outline" className="text-[10px] text-green-400 border-green-400/30">✓ Fixed</Badge>
                      : <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-400/30">Awaiting first call</Badge>
                    }
                  </td>
                  <td className="px-3 py-2 font-mono text-amber-400">{fmt(f.recorded_cost_usd ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Cost color scale per spec
// ══════════════════════════════════════════════════════════════════════════════
function costColor(usd: number): { text: string; bg: string; border: string } {
  if (usd >= 50)  return { text: 'text-red-300',    bg: 'bg-red-900/40',    border: 'border-red-700/60' };
  if (usd >= 25)  return { text: 'text-red-400',    bg: 'bg-red-800/20',    border: 'border-red-600/40' };
  if (usd >= 10)  return { text: 'text-orange-400', bg: 'bg-orange-800/20', border: 'border-orange-600/40' };
  if (usd >= 1)   return { text: 'text-yellow-400', bg: 'bg-yellow-900/20', border: 'border-yellow-600/40' };
  return           { text: 'text-green-400',  bg: 'bg-green-900/15',  border: 'border-green-700/30' };
}

const SORT_OPTIONS = [
  { id: 'current',    label: 'Current Cost' },
  { id: 'historical', label: 'Historical Cost' },
  { id: 'incident',   label: 'Highest Incident' },
  { id: 'single',     label: 'Highest Single Request' },
  { id: 'calls',      label: '# API Calls' },
  { id: 'average',    label: 'Average Cost' },
  { id: 'savings',    label: 'Potential Savings' },
] as const;

type SortId = typeof SORT_OPTIONS[number]['id'];

function sortFeatures(features: any[], sortId: SortId): any[] {
  const key: Record<SortId, (f: any) => number> = {
    current:    f => f.current_cost_usd,
    historical: f => f.historical_peak_usd,
    incident:   f => f.historical_peak_usd,
    single:     f => f.highest_single_request_usd,
    calls:      f => f.call_count,
    average:    f => f.average_cost_per_request_usd,
    savings:    f => f.protection_status === 'at_risk' ? f.current_cost_usd * 0.7 : 0,
  };
  return [...features].sort((a, b) => key[sortId](b) - key[sortId](a)).map((f, i) => ({ ...f, rank: i + 1 }));
}

const PROT_BADGE: Record<string, { label: string; cls: string }> = {
  protected: { label: 'Protected', cls: 'text-green-400 border-green-400/40 bg-green-400/5' },
  warning:   { label: 'Warning',   cls: 'text-amber-400 border-amber-400/40 bg-amber-400/5' },
  at_risk:   { label: 'At Risk',   cls: 'text-red-400 border-red-400/40 bg-red-400/5' },
  unknown:   { label: 'Unknown',   cls: 'text-muted-foreground border-border bg-muted/10' },
};

// ── Drill-down modal ──────────────────────────────────────────────────────────
function DrillDownModal({ featureId, featureLabel, onClose }: { featureId: string; featureLabel: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['drill-down', featureId],
    queryFn: () => apiFetch(`/api/costs/drill-down/${featureId}`),
    staleTime: 60_000,
  });
  const requests: any[] = data?.requests ?? [];

  const [filterText, setFilterText] = useState('');
  const filtered = filterText
    ? requests.filter(r => JSON.stringify(r).toLowerCase().includes(filterText.toLowerCase()))
    : requests;

  const totalCost = requests.reduce((s, r) => s + (r.cost_usd ?? 0), 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border shrink-0">
          <Database className="h-4 w-4 text-amber-400" />
          <div>
            <div className="font-bold text-sm">{featureLabel} — All API Requests</div>
            <div className="text-[10px] text-muted-foreground">
              {requests.length} records · total {fmt(totalCost)}
            </div>
          </div>
          <input
            className="ml-auto text-xs bg-muted/30 border border-border rounded-lg px-2 py-1.5 w-48 placeholder:text-muted-foreground"
            placeholder="Filter requests…"
            value={filterText} onChange={e => setFilterText(e.target.value)} />
          <button onClick={onClose} className="ml-2 p-1.5 rounded-lg hover:bg-muted/40 transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto">
          {isLoading ? (
            <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">No requests recorded yet.</div>
          ) : (
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-muted/80 backdrop-blur-sm">
                <tr>
                  {['Time', 'Label / Job', 'Model', 'Status', 'Prompt Tok', 'Completion Tok', 'Cached Tok', 'Images', 'Duration', 'OpenAI Req ID', 'Cost'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left font-mono text-[10px] uppercase text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r: any) => {
                  const cc = costColor(r.cost_usd ?? 0);
                  return (
                    <tr key={r.id} className="border-t border-border/20 hover:bg-muted/10">
                      <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground whitespace-nowrap">
                        {r.created_at ? new Date(r.created_at).toLocaleString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </td>
                      <td className="px-3 py-2 max-w-[180px] truncate" title={r.label}>{r.label ?? '—'}</td>
                      <td className="px-3 py-2 font-mono text-[10px] text-cyan-400 whitespace-nowrap">{r.model ?? '—'}</td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                          r.status === 'completed' ? 'text-green-400 border-green-400/30' :
                          r.status === 'skipped'   ? 'text-muted-foreground border-border' :
                          r.status === 'cache_hit' ? 'text-blue-400 border-blue-400/30' :
                                                     'text-muted-foreground border-border'
                        }`}>{r.status ?? '—'}</span>
                      </td>
                      <td className="px-3 py-2 font-mono text-right">{(r.prompt_tokens ?? 0).toLocaleString()}</td>
                      <td className="px-3 py-2 font-mono text-right">{(r.completion_tokens ?? 0).toLocaleString()}</td>
                      <td className="px-3 py-2 font-mono text-right text-blue-400/70">{(r.cached_tokens ?? 0).toLocaleString()}</td>
                      <td className="px-3 py-2 font-mono text-center">{r.images ?? 0}</td>
                      <td className="px-3 py-2 font-mono text-right text-muted-foreground">{r.duration_secs != null ? `${r.duration_secs}s` : '—'}</td>
                      <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground max-w-[120px] truncate" title={r.openai_request_id}>{r.openai_request_id ?? '—'}</td>
                      <td className={`px-3 py-2 font-mono font-bold text-right whitespace-nowrap ${cc.text}`}>
                        {r.cost_usd != null ? fmt(r.cost_usd) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer summary */}
        {requests.length > 0 && (
          <div className="shrink-0 border-t border-border px-5 py-3 flex flex-wrap gap-4 text-xs">
            <div><span className="text-muted-foreground">Total: </span><span className="font-mono font-bold text-amber-400">{fmt(totalCost)}</span></div>
            <div><span className="text-muted-foreground">Requests: </span><span className="font-mono">{requests.length}</span></div>
            <div><span className="text-muted-foreground">Avg: </span><span className="font-mono">{fmt(totalCost / Math.max(requests.length, 1))}</span></div>
            <div><span className="text-muted-foreground">Prompt tokens: </span><span className="font-mono">{requests.reduce((s, r) => s + (r.prompt_tokens ?? 0), 0).toLocaleString()}</span></div>
            <div><span className="text-muted-foreground">Completion tokens: </span><span className="font-mono">{requests.reduce((s, r) => s + (r.completion_tokens ?? 0), 0).toLocaleString()}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Top Cost Consumers — always-visible section ────────────────────────────────
function TopCostConsumers() {
  const [sortId, setSortId] = useState<SortId>('current');
  const [collapsed, setCollapsed] = useState(false);
  const [drillDown, setDrillDown] = useState<{ id: string; label: string } | null>(null);

  const { data, isLoading } = useCosts<any>(
    'top-consumers',
    '/api/costs/top-consumers',
    { refetchInterval: 60_000 }
  );

  const rawFeatures: any[] = data?.features ?? [];
  const summary = data?.summary ?? {};
  const features = sortFeatures(rawFeatures, sortId);

  // 13-stat summary bar config
  const statBar = [
    { label: 'Highest Cost Feature',        value: summary.highest_cost_feature ?? '—', mono: false },
    { label: 'Historical Peak',             value: summary.highest_historical_cost_usd != null ? fmt(summary.highest_historical_cost_usd) : '—', mono: true },
    { label: 'Current Peak',               value: summary.highest_current_cost_usd != null ? fmt(summary.highest_current_cost_usd) : '—', mono: true },
    { label: 'Largest Single API Call',     value: summary.largest_single_api_request_usd != null ? fmt(summary.largest_single_api_request_usd) : '—', mono: true },
    { label: 'Largest Single Job',          value: summary.largest_single_job_usd != null ? fmt(summary.largest_single_job_usd) : '—', mono: true },
    { label: 'Largest Daily Spend',         value: summary.largest_daily_spend_usd != null ? fmt(summary.largest_daily_spend_usd) : '—', mono: true },
    { label: 'Largest Monthly Spend',       value: summary.largest_monthly_spend_usd != null ? fmt(summary.largest_monthly_spend_usd) : '—', mono: true },
    { label: 'Lifetime Spend',              value: summary.largest_lifetime_spend_usd != null ? fmt(summary.largest_lifetime_spend_usd) : '—', mono: true },
    { label: 'Saved by Protection',         value: summary.money_saved_by_protection_usd != null ? fmt(summary.money_saved_by_protection_usd) : '—', mono: true, green: true },
    { label: 'Saved by Cache',              value: summary.money_saved_by_cache_usd != null ? fmt(summary.money_saved_by_cache_usd) : '—', mono: true, green: true },
    { label: 'Saved by Deduplication',      value: summary.money_saved_by_deduplication_usd != null ? fmt(summary.money_saved_by_deduplication_usd) : '—', mono: true, green: true },
    { label: 'Saved by Model Routing',      value: summary.money_saved_by_model_routing_usd != null ? fmt(summary.money_saved_by_model_routing_usd) : '—', mono: true, green: true },
    { label: 'Potential Savings Remaining', value: summary.potential_savings_remaining_usd != null ? fmt(summary.potential_savings_remaining_usd) : '—', mono: true, amber: true },
  ] as const;

  return (
    <>
      {drillDown && (
        <DrillDownModal featureId={drillDown.id} featureLabel={drillDown.label} onClose={() => setDrillDown(null)} />
      )}

      <div className="border-b border-border shrink-0">
        {/* Section header */}
        <div className="px-6 py-2.5 flex items-center gap-2">
          <Trophy className="h-4 w-4 text-amber-400 shrink-0" />
          <span className="font-bold text-xs uppercase tracking-wider text-amber-400">Top Cost Consumers</span>
          <span className="text-[10px] text-muted-foreground ml-1">
            {isLoading ? 'Loading…' : `${features.length} features · ${fmt(data?.grand_total_usd ?? 0)} total`}
          </span>

          {/* Sort selector */}
          <div className="ml-auto flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground shrink-0">Sort by:</span>
            <select
              className="text-[10px] bg-muted/30 border border-border rounded px-2 py-1"
              value={sortId}
              onChange={e => setSortId(e.target.value as SortId)}
            >
              {SORT_OPTIONS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            <button
              onClick={() => setCollapsed(c => !c)}
              className="ml-1 p-1 rounded hover:bg-muted/40 transition-colors text-muted-foreground hover:text-foreground"
              title={collapsed ? 'Expand' : 'Collapse'}
            >
              {collapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {!collapsed && (
          <>
            {/* Summary stat bar — 13 scrolling pills */}
            <div className="px-6 pb-2 overflow-x-auto scrollbar-none">
              <div className="flex gap-2 min-w-max">
                {statBar.map((s, i) => (
                  <div
                    key={i}
                    className="flex flex-col items-start bg-muted/20 border border-border/50 rounded-lg px-3 py-1.5 shrink-0"
                  >
                    <span className="text-[9px] text-muted-foreground uppercase tracking-wide whitespace-nowrap">{s.label}</span>
                    <span className={`text-xs font-bold mt-0.5 whitespace-nowrap ${
                      'green' in s && s.green ? 'text-green-400' :
                      'amber' in s && s.amber ? 'text-amber-400' :
                      'mono' in s && s.mono   ? 'font-mono text-foreground' :
                                                 'text-foreground'
                    }`}>{s.value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Ranked feature cards — horizontal row */}
            <div className="px-6 pb-3 overflow-x-auto scrollbar-none">
              {isLoading ? (
                <div className="text-xs text-muted-foreground py-4">Loading features…</div>
              ) : (
                <div className="flex gap-2 min-w-max">
                  {features.map((feat: any) => {
                    const cc   = costColor(Math.max(feat.current_cost_usd, feat.historical_peak_usd));
                    const prot = PROT_BADGE[feat.protection_status] ?? PROT_BADGE.unknown;
                    return (
                      <button
                        key={feat.id}
                        onClick={() => setDrillDown({ id: feat.id, label: feat.label })}
                        className={`flex flex-col gap-1 border rounded-xl p-3 text-left min-w-[170px] max-w-[200px] hover:opacity-80 transition-opacity cursor-pointer ${cc.bg} ${cc.border}`}
                      >
                        {/* Rank + label */}
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-mono text-muted-foreground">#{feat.rank}</span>
                          {feat.rank === 1 && <Flame className="h-3 w-3 text-orange-400 shrink-0" />}
                          <span className="text-xs font-semibold truncate">{feat.label}</span>
                        </div>

                        {/* Current cost */}
                        <div className={`text-lg font-bold font-mono leading-tight ${cc.text}`}>
                          {fmt(feat.current_cost_usd)}
                        </div>

                        {/* Stats grid */}
                        <div className="space-y-0.5">
                          <div className="flex justify-between text-[10px]">
                            <span className="text-muted-foreground">Historical Peak</span>
                            <span className="font-mono text-orange-400/80">{fmt(feat.historical_peak_usd)}</span>
                          </div>
                          <div className="flex justify-between text-[10px]">
                            <span className="text-muted-foreground">Highest Job</span>
                            <span className="font-mono">{fmt(feat.highest_single_request_usd)}</span>
                          </div>
                          <div className="flex justify-between text-[10px]">
                            <span className="text-muted-foreground">Avg / Request</span>
                            <span className="font-mono">{fmt(feat.average_cost_per_request_usd)}</span>
                          </div>
                          <div className="flex justify-between text-[10px]">
                            <span className="text-muted-foreground">% of Spend</span>
                            <span className="font-mono">{feat.pct_of_total.toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between text-[10px]">
                            <span className="text-muted-foreground">API Calls</span>
                            <span className="font-mono">{feat.call_count.toLocaleString()}</span>
                          </div>
                        </div>

                        {/* Trend + protection */}
                        <div className="flex items-center gap-1.5 mt-1">
                          {feat.trend === 'up' ? (
                            <span className="flex items-center gap-0.5 text-[10px] text-red-400">
                              <ArrowUp className="h-2.5 w-2.5" />{feat.trend_pct != null ? `${feat.trend_pct}%` : '▲'}
                            </span>
                          ) : feat.trend === 'down' ? (
                            <span className="flex items-center gap-0.5 text-[10px] text-green-400">
                              <ArrowDown className="h-2.5 w-2.5" />{feat.trend_pct != null ? `${Math.abs(feat.trend_pct)}%` : '▼'}
                            </span>
                          ) : (
                            <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                              <Minus className="h-2.5 w-2.5" />flat
                            </span>
                          )}
                          <span className={`ml-auto text-[9px] px-1.5 py-0.5 rounded border font-medium ${prot.cls}`}>
                            {prot.label}
                          </span>
                        </div>

                        <div className="text-[9px] text-muted-foreground text-center mt-0.5 opacity-60">
                          click to drill down →
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Financial Health Banner — SAFE / WARNING / CRITICAL
// ══════════════════════════════════════════════════════════════════════════════
function FinancialHealthBanner() {
  const { data, isLoading } = useCosts<any>('financial-health', '/api/costs/financial-health', { refetchInterval: 60_000 });

  if (isLoading) return null;

  const status  = data?.status ?? 'UNKNOWN';
  const message = data?.status_message ?? '';
  const pass    = data?.pass_count ?? 0;
  const warn    = data?.warn_count ?? 0;
  const fail    = data?.fail_count ?? 0;
  const total   = data?.total_checks ?? 0;

  const cfg = {
    SAFE:     { bar: 'bg-green-500/20 border-green-500/40', badge: 'bg-green-500/20 text-green-400 border-green-500/30', icon: CircleCheck },
    WARNING:  { bar: 'bg-amber-500/20 border-amber-500/40', badge: 'bg-amber-500/20 text-amber-400 border-amber-500/30', icon: TriangleAlert },
    CRITICAL: { bar: 'bg-red-500/20 border-red-500/50',    badge: 'bg-red-500/20 text-red-400 border-red-500/30',    icon: CircleX },
    UNKNOWN:  { bar: 'bg-muted/20 border-border',          badge: 'bg-muted/20 text-muted-foreground border-border',  icon: AlertCircle },
  }[status] ?? { bar: 'bg-muted/20 border-border', badge: 'bg-muted/20 text-muted-foreground border-border', icon: AlertCircle };

  const Icon = cfg.icon;

  return (
    <div className={`rounded-xl border px-4 py-3 flex items-center gap-3 ${cfg.bar}`}>
      <Icon className="h-5 w-5 shrink-0" />
      <div className="flex-1">
        <span className="font-bold text-sm">Financial Health: </span>
        <span className={`font-mono font-bold text-sm px-2 py-0.5 rounded border ${cfg.badge}`}>{status}</span>
        <span className="text-xs text-muted-foreground ml-3">{message}</span>
      </div>
      <div className="flex gap-3 text-xs shrink-0">
        <span className="text-green-400">{pass} PASS</span>
        <span className="text-amber-400">{warn} WARNING</span>
        <span className="text-red-400">{fail} FAIL</span>
        <span className="text-muted-foreground">/ {total} checks</span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Executive Summary
// ══════════════════════════════════════════════════════════════════════════════
function ExecutiveSummaryTab() {
  const { data, isLoading } = useCosts<any>('executive-summary', '/api/costs/executive-summary', { refetchInterval: 60_000 });
  const { data: health } = useCosts<any>('financial-health', '/api/costs/financial-health', { refetchInterval: 60_000 });

  const s = data?.savings_breakdown ?? {};
  const inc = data?.largest_historical_incident ?? {};
  const risk = data?.largest_protected_risk ?? {};

  const healthStatus = health?.status ?? 'UNKNOWN';
  const healthCfg = {
    SAFE:     { color: 'text-green-400', border: 'border-green-500/30', bg: 'bg-green-500/5' },
    WARNING:  { color: 'text-amber-400', border: 'border-amber-500/30', bg: 'bg-amber-500/5' },
    CRITICAL: { color: 'text-red-400',   border: 'border-red-500/40',   bg: 'bg-red-500/5' },
    UNKNOWN:  { color: 'text-muted-foreground', border: 'border-border', bg: '' },
  }[healthStatus] ?? { color: 'text-muted-foreground', border: 'border-border', bg: '' };

  return (
    <div className="space-y-6">
      {/* Global status */}
      <div className={`rounded-xl border-2 p-5 ${healthCfg.border} ${healthCfg.bg}`}>
        <div className="flex items-center gap-3 mb-4">
          <Building2 className="h-5 w-5" />
          <span className="font-bold text-sm uppercase tracking-wide">Executive Financial Summary</span>
          <Badge variant="outline" className={`text-xs ml-1 ${healthCfg.color} border-current`}>
            {healthStatus}
          </Badge>
        </div>

        {isLoading ? (
          <div className="text-xs text-muted-foreground">Loading…</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Spend */}
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Spend</div>
              {[
                { label: "Today's Spend",   value: fmt(data?.today_spend_usd   ?? 0), color: 'text-foreground' },
                { label: 'Monthly Spend',   value: fmt(data?.monthly_spend_usd ?? 0), color: 'text-amber-400' },
                { label: 'Lifetime Spend',  value: fmt(data?.lifetime_spend_usd ?? 0), color: 'text-red-400' },
              ].map(r => (
                <div key={r.label} className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{r.label}</span>
                  <span className={`font-mono font-bold ${r.color}`}>{r.value}</span>
                </div>
              ))}
            </div>

            {/* Largest incidents */}
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Incidents</div>
              <div className="text-sm">
                <div className="text-muted-foreground text-xs">Largest Historical Incident</div>
                <div className="font-semibold text-orange-400">{inc.feature ?? '—'}</div>
                <div className="font-mono font-bold text-red-400">{inc.cost_usd != null ? fmt(inc.cost_usd) : '—'}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {inc.date ? new Date(inc.date).toLocaleDateString() : ''} · {inc.status}
                </div>
              </div>
              <div className="text-sm mt-2">
                <div className="text-muted-foreground text-xs">Largest Protected Risk</div>
                <div className="font-semibold">{risk.feature ?? '—'}</div>
                <div className="text-green-400 text-xs">{risk.protected_by}</div>
                <div className="font-mono text-amber-400 text-xs">{risk.historical_risk_usd != null ? `${risk.historical_risk_usd.toFixed(2)}` : ''} historical risk</div>
              </div>
            </div>

            {/* Potential savings */}
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase text-muted-foreground tracking-wide">Potential Monthly Savings</div>
              <div className={`text-2xl font-bold font-mono text-green-400`}>{fmt(data?.potential_monthly_savings_usd ?? 0)}</div>
              <div className="text-[10px] text-muted-foreground">Based on actual savings rate</div>
            </div>
          </div>
        )}
      </div>

      {/* Savings breakdown */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <TrendingDown className="h-4 w-4 text-green-400" />
            Savings Breakdown — Real Data from Database
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <div className="text-xs text-muted-foreground py-4">Loading…</div> : (
            <div className="space-y-2">
              {[
                { label: 'Money Saved by Cache',            value: s.cache_usd ?? 0,             detail: 'Caption cache + OpenAI prompt cache' },
                { label: 'Money Saved by Dedup',            value: s.dedup_usd ?? 0,             detail: 'SHA-256 duplicate image detection' },
                { label: 'Money Saved by Vision Protection',value: s.vision_protection_usd ?? 0, detail: 'Kill switch + daily/monthly limits' },
                { label: 'Money Saved by Model Routing',    value: s.model_routing_usd ?? 0,     detail: 'gpt-4o vs gpt-5.4 baseline comparison' },
                { label: 'Money Saved by Translation Memory',value: s.translation_memory_usd ?? 0,detail: 'Segment reuse across TM hits' },
              ].map(r => (
                <div key={r.label} className="flex items-center gap-3">
                  <div className="flex-1">
                    <div className="text-sm font-medium">{r.label}</div>
                    <div className="text-[10px] text-muted-foreground">{r.detail}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono font-bold text-green-400">{fmt(r.value)}</div>
                  </div>
                </div>
              ))}
              <div className="border-t border-border/50 pt-2 flex items-center justify-between">
                <span className="font-semibold text-sm">Total Saved</span>
                <span className="font-mono font-bold text-green-400 text-lg">{fmt(s.total_saved_usd ?? 0)}</span>
              </div>
              <p className="text-[10px] text-muted-foreground">{data?.notes}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Protection checks summary */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            14-Point Protection Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {(health?.checks ?? []).map((c: any, i: number) => (
              <div key={i} className={`rounded-lg px-3 py-2 text-xs flex items-center gap-2 ${
                c.status === 'PASS'    ? 'bg-green-500/5 border border-green-500/20' :
                c.status === 'WARNING' ? 'bg-amber-500/5 border border-amber-500/20' :
                                        'bg-red-500/5 border border-red-500/20'
              }`}>
                {c.status === 'PASS'    ? <CircleCheck className="h-3 w-3 text-green-400 shrink-0" /> :
                 c.status === 'WARNING' ? <TriangleAlert className="h-3 w-3 text-amber-400 shrink-0" /> :
                                         <CircleX className="h-3 w-3 text-red-400 shrink-0" />}
                <span className="truncate">{c.name}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Incident History — permanent DB-backed records + timeline
// ══════════════════════════════════════════════════════════════════════════════
function IncidentHistoryTab() {
  const [featureFilter, setFeatureFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Record<string, any>>({});
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data, isLoading, refetch } = useCosts<any>(
    `incidents-${featureFilter}-${severityFilter}`,
    `/api/costs/incidents?feature=${encodeURIComponent(featureFilter)}&severity=${encodeURIComponent(severityFilter)}`,
    { refetchInterval: 120_000 }
  );
  const incidents: any[] = data?.incidents ?? [];

  const SEV_COLOR: Record<string, string> = {
    critical: 'text-red-400 border-red-400/40 bg-red-400/5',
    high:     'text-orange-400 border-orange-400/40 bg-orange-400/5',
    medium:   'text-amber-400 border-amber-400/40 bg-amber-400/5',
    low:      'text-blue-400 border-blue-400/40 bg-blue-400/5',
  };
  const STATUS_COLOR: Record<string, string> = {
    resolved: 'text-green-400', open: 'text-red-400', investigating: 'text-amber-400', monitoring: 'text-blue-400'
  };

  const handleCreate = async () => {
    try {
      const res = await fetch(`${API}/api/costs/incidents`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: 'Incident created' });
      setShowForm(false);
      setForm({});
      qc.invalidateQueries({ queryKey: ['costs'] });
      refetch();
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-6">
      {/* Timeline view */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <History className="h-4 w-4 text-orange-400" />
            Financial Incident Timeline
            <span className="ml-auto text-[10px] text-muted-foreground">Permanent records — never deleted</span>
            <Button size="sm" variant="outline" className="h-7 text-xs ml-2 gap-1" onClick={() => setShowForm(!showForm)}>
              <Plus className="h-3 w-3" />New Incident
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* Filters */}
          <div className="flex gap-2 mb-4 flex-wrap">
            <input
              className="flex-1 min-w-[140px] text-xs bg-muted/30 border border-border rounded-lg px-2 py-1.5 placeholder:text-muted-foreground"
              placeholder="Filter by feature…" value={featureFilter}
              onChange={e => setFeatureFilter(e.target.value)} />
            <select className="text-xs bg-muted/30 border border-border rounded-lg px-2 py-1.5"
              value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}>
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          {/* New incident form */}
          {showForm && (
            <div className="border border-border/50 rounded-xl p-4 mb-4 bg-muted/10 space-y-3">
              <div className="font-semibold text-sm">Record New Incident</div>
              <div className="grid md:grid-cols-3 gap-3">
                {[
                  { key: 'feature', label: 'Feature', placeholder: 'Image Captioning' },
                  { key: 'model', label: 'Model', placeholder: 'gpt-5.4' },
                  { key: 'fixed_by', label: 'Fixed By', placeholder: 'Platform engineer' },
                ].map(f => (
                  <div key={f.key}>
                    <div className="text-[10px] text-muted-foreground mb-1">{f.label}</div>
                    <input className="w-full text-xs bg-muted/30 border border-border rounded px-2 py-1.5"
                      placeholder={f.placeholder} value={form[f.key] ?? ''}
                      onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} />
                  </div>
                ))}
                {[
                  { key: 'total_cost_usd', label: 'Total Cost (USD)', type: 'number', placeholder: '53.18' },
                  { key: 'api_calls', label: 'API Calls', type: 'number', placeholder: '531' },
                  { key: 'vision_calls', label: 'Vision Calls', type: 'number', placeholder: '531' },
                  { key: 'images_processed', label: 'Images', type: 'number', placeholder: '531' },
                  { key: 'prompt_tokens', label: 'Prompt Tokens', type: 'number', placeholder: '0' },
                  { key: 'completion_tokens', label: 'Completion Tokens', type: 'number', placeholder: '0' },
                ].map(f => (
                  <div key={f.key}>
                    <div className="text-[10px] text-muted-foreground mb-1">{f.label}</div>
                    <input type={f.type ?? 'text'} className="w-full text-xs bg-muted/30 border border-border rounded px-2 py-1.5"
                      placeholder={f.placeholder} value={form[f.key] ?? ''}
                      onChange={e => setForm(p => ({ ...p, [f.key]: f.type === 'number' ? Number(e.target.value) : e.target.value }))} />
                  </div>
                ))}
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                {[
                  { key: 'root_cause', label: 'Root Cause' },
                  { key: 'resolution', label: 'Resolution' },
                  { key: 'notes', label: 'Notes' },
                ].map(f => (
                  <div key={f.key}>
                    <div className="text-[10px] text-muted-foreground mb-1">{f.label}</div>
                    <textarea className="w-full text-xs bg-muted/30 border border-border rounded px-2 py-1.5 resize-none h-16"
                      value={form[f.key] ?? ''}
                      onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} />
                  </div>
                ))}
                <div>
                  <div className="text-[10px] text-muted-foreground mb-1">Severity</div>
                  <select className="w-full text-xs bg-muted/30 border border-border rounded px-2 py-1.5"
                    value={form.severity ?? 'high'} onChange={e => setForm(p => ({ ...p, severity: e.target.value }))}>
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" className="text-xs h-7" onClick={handleCreate}>Save Incident</Button>
                <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => { setShowForm(false); setForm({}); }}>Cancel</Button>
              </div>
            </div>
          )}

          {/* Timeline */}
          {isLoading ? (
            <div className="text-xs text-muted-foreground py-6 text-center">Loading…</div>
          ) : incidents.length === 0 ? (
            <div className="text-xs text-muted-foreground py-6 text-center">No incidents recorded</div>
          ) : (
            <div className="relative space-y-0">
              <div className="absolute left-[72px] top-0 bottom-0 w-px bg-border/40" />
              {incidents.map((inc: any) => (
                <div key={inc.id} className="flex gap-4 pb-6 relative">
                  {/* Date column */}
                  <div className="w-[60px] shrink-0 text-right">
                    <div className="text-[10px] text-muted-foreground font-mono leading-tight">
                      {new Date(inc.incident_date).toLocaleDateString('en', { day: 'numeric', month: 'short' })}
                    </div>
                  </div>
                  {/* Timeline dot */}
                  <div className={`w-3 h-3 rounded-full border-2 shrink-0 mt-1 relative z-10 ${
                    inc.severity === 'critical' ? 'bg-red-500 border-red-400' :
                    inc.severity === 'high'     ? 'bg-orange-500 border-orange-400' :
                    inc.severity === 'medium'   ? 'bg-amber-500 border-amber-400' :
                                                  'bg-blue-500 border-blue-400'
                  }`} />
                  {/* Content */}
                  <div className="flex-1 bg-card/60 border border-border/50 rounded-xl p-3 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm">{inc.feature}</span>
                      <Badge variant="outline" className={`text-[10px] ${SEV_COLOR[inc.severity] ?? ''}`}>{inc.severity}</Badge>
                      <span className={`text-xs font-medium ${STATUS_COLOR[inc.status] ?? 'text-muted-foreground'}`}>{inc.status}</span>
                      <span className="ml-auto font-mono font-bold text-sm text-red-400">{fmt(inc.total_cost_usd)}</span>
                    </div>
                    <div className="grid md:grid-cols-4 gap-2 text-[10px]">
                      {[
                        { label: 'API Calls',   value: inc.api_calls },
                        { label: 'Vision Calls', value: inc.vision_calls },
                        { label: 'Images',       value: inc.images_processed },
                        { label: 'Model',        value: inc.model ?? '—' },
                      ].map(s => (
                        <div key={s.label}>
                          <span className="text-muted-foreground">{s.label}: </span>
                          <span className="font-mono">{s.value}</span>
                        </div>
                      ))}
                    </div>
                    {inc.root_cause && (
                      <div className="text-xs"><span className="text-muted-foreground">Root Cause: </span>{inc.root_cause.substring(0, 120)}{inc.root_cause.length > 120 ? '…' : ''}</div>
                    )}
                    {inc.resolution && (
                      <div className="text-xs text-green-400/80"><span className="text-muted-foreground">Resolution: </span>{inc.resolution.substring(0, 120)}{inc.resolution.length > 120 ? '…' : ''}</div>
                    )}
                    {inc.fixed_by && (
                      <div className="text-[10px] text-muted-foreground">Fixed by: {inc.fixed_by}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Cost Leak Detector
// ══════════════════════════════════════════════════════════════════════════════
function LeakDetectorTab() {
  const { data, isLoading, refetch } = useCosts<any>('leak-detector', '/api/costs/leak-detector', { refetchInterval: 120_000 });
  const leaks: any[] = data?.leaks ?? [];

  const SEV: Record<string, { bar: string; badge: string; icon: any }> = {
    critical: { bar: 'border-red-500/40 bg-red-500/5',    badge: 'text-red-400 border-red-400/40',    icon: CircleX },
    high:     { bar: 'border-orange-500/40 bg-orange-500/5', badge: 'text-orange-400 border-orange-400/40', icon: AlertTriangle },
    medium:   { bar: 'border-amber-500/40 bg-amber-500/5', badge: 'text-amber-400 border-amber-400/40', icon: TriangleAlert },
    low:      { bar: 'border-blue-500/30 bg-blue-500/5',  badge: 'text-blue-400 border-blue-400/30',  icon: Info },
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">Automatic Cost Leak Detection</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Scans existing DB logs for anomalies. No paid API calls made. Last checked: {data?.checked_at ? new Date(data.checked_at).toLocaleTimeString() : '—'}
          </p>
        </div>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => refetch()}>
          <RefreshCw className="h-3 w-3" /> Scan Now
        </Button>
      </div>

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground text-sm">Scanning…</div>
      ) : leaks.length === 0 ? (
        <div className="rounded-xl border-2 border-green-500/40 bg-green-500/5 p-6 text-center">
          <CircleCheck className="h-8 w-8 text-green-400 mx-auto mb-2" />
          <div className="font-semibold text-green-400">No Leaks Detected</div>
          <div className="text-xs text-muted-foreground mt-1">All cost patterns within expected bounds</div>
        </div>
      ) : (
        <div className="space-y-4">
          {leaks.map((leak: any, i: number) => {
            const sev = SEV[leak.severity] ?? SEV.low;
            const Icon = sev.icon;
            return (
              <div key={i} className={`rounded-xl border-2 p-4 space-y-3 ${sev.bar}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="font-semibold text-sm">{leak.title}</span>
                  <Badge variant="outline" className={`text-[10px] ml-1 ${sev.badge}`}>{leak.severity.toUpperCase()}</Badge>
                  {leak.estimated_loss_usd != null && (
                    <span className="ml-auto font-mono font-bold text-sm text-red-400">
                      ~{fmt(leak.estimated_loss_usd)} risk
                    </span>
                  )}
                </div>
                <div className="grid md:grid-cols-2 gap-4 text-xs">
                  <div>
                    <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1">Root Cause</div>
                    <div>{leak.root_cause}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1">Suggested Fix</div>
                    <div className="text-amber-400">{leak.suggested_fix}</div>
                  </div>
                </div>
                {leak.evidence && Object.keys(leak.evidence).length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(leak.evidence).map(([k, v]) => (
                      <span key={k} className="text-[10px] bg-muted/40 rounded px-2 py-0.5 font-mono">
                        {k}: {typeof v === 'number' && k.includes('usd') ? fmt(v as number) : String(v)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="text-[10px] text-muted-foreground border-t border-border/30 pt-3">
        Detection categories: Unexpected Vision Calls · Unexpected GPT-5.4 Usage · GPT-4o Spike · Duplicate Translation ·
        Repeated Caption Requests · Runaway API Calls · Expensive Vision Model.
        All derived from {data?.note ?? 'existing DB logs — no paid API calls made.'}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Root Cause Analytics
// ══════════════════════════════════════════════════════════════════════════════
function RootCauseTab() {
  const { data, isLoading } = useCosts<any>('root-cause', '/api/costs/root-cause', { refetchInterval: 120_000 });
  const features: any[] = data?.features ?? [];

  const PROT_BADGE: Record<string, string> = {
    PASS:    'text-green-400 border-green-400/40 bg-green-400/5',
    WARNING: 'text-amber-400 border-amber-400/40 bg-amber-400/5',
    FAIL:    'text-red-400 border-red-400/40 bg-red-400/5',
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-semibold text-sm">Root Cause Analytics — Per Feature</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Historical cost · current cost · highest job · average · biggest incident · most frequent cause · protection status.
          Total tracked: {data?.total_tracked_cost_usd != null ? fmt(data.total_tracked_cost_usd) : '—'}
        </p>
      </div>

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div>
      ) : (
        <div className="space-y-4">
          {features.map((feat: any, i: number) => {
            const prot = feat.protection_status ?? 'WARNING';
            return (
              <Card key={i} className={prot === 'FAIL' ? 'border-red-500/30' : prot === 'PASS' ? 'border-green-500/20' : ''}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2 flex-wrap">
                    <span>{feat.feature}</span>
                    <Badge variant="outline" className={`text-[10px] ${PROT_BADGE[prot] ?? PROT_BADGE.WARNING}`}>
                      {prot}
                    </Badge>
                    <span className="ml-auto font-mono font-bold text-amber-400 text-sm">
                      {fmt(feat.current_cost_usd)}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                    {[
                      { label: 'Historical Cost',     value: feat.historical_cost },
                      { label: 'Current Cost',        value: fmt(feat.current_cost_usd) },
                      { label: 'Highest Single Job',  value: fmt(feat.highest_single_job_usd) },
                      { label: 'Average Cost',        value: `${fmt(feat.average_cost_usd)} / call` },
                    ].map(s => (
                      <div key={s.label} className="bg-muted/20 rounded-lg p-2">
                        <div className="text-[10px] text-muted-foreground font-mono uppercase">{s.label}</div>
                        <div className="font-mono font-bold mt-0.5">{s.value}</div>
                      </div>
                    ))}
                  </div>
                  <div className="text-xs space-y-1">
                    <div>
                      <span className="text-muted-foreground">Most Frequent Cause: </span>
                      <span className="text-amber-400">{feat.most_frequent_cause}</span>
                    </div>
                    {feat.biggest_incident && (
                      <div>
                        <span className="text-muted-foreground">Biggest Incident: </span>
                        <span className="text-red-400">{feat.biggest_incident.feature}</span>
                        <span className="font-mono ml-2 text-red-400">{fmt(feat.biggest_incident.cost_usd)}</span>
                        <span className="text-muted-foreground ml-2 text-[10px]">
                          {feat.biggest_incident.date ? new Date(feat.biggest_incident.date).toLocaleDateString() : ''}
                          {' · '}{feat.biggest_incident.status}
                        </span>
                      </div>
                    )}
                    {feat.protection_checks?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {feat.protection_checks.map((c: string) => (
                          <span key={c} className="text-[10px] bg-muted/40 rounded px-1.5 py-0.5">{c}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB: Config Audit — Historical Protection Validation
// ══════════════════════════════════════════════════════════════════════════════
function ConfigAuditTab() {
  const { data, isLoading } = useCosts<any>('config-audit', '/api/costs/config-audit', { refetchInterval: 60_000 });
  const entries: any[] = data?.entries ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-semibold text-sm">Historical Protection Validation</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Every configuration change recorded with old value, new value, user, timestamp, and reason.
          Immutable audit trail — entries are never modified or deleted.
        </p>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div>
          ) : entries.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              No configuration changes recorded yet.
              <div className="text-xs mt-1">Toggle the vision kill switch to create the first entry.</div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/30">
                  <tr>
                    {['Timestamp', 'Config Key', 'Old Value', 'New Value', 'User', 'Source', 'Reason'].map(h => (
                      <th key={h} className="px-3 py-2.5 text-left text-[10px] font-mono uppercase text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e: any) => (
                    <tr key={e.id} className="border-t border-border/30 hover:bg-muted/10">
                      <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground whitespace-nowrap">
                        {e.changed_at ? new Date(e.changed_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-3 py-2 font-mono font-semibold text-blue-400">{e.config_key}</td>
                      <td className="px-3 py-2 font-mono text-red-400/80">{e.old_value ?? '(not set)'}</td>
                      <td className="px-3 py-2 font-mono text-green-400">{e.new_value ?? '(cleared)'}</td>
                      <td className="px-3 py-2 text-muted-foreground">{e.user_id ?? 'system'}</td>
                      <td className="px-3 py-2">
                        <Badge variant="outline" className="text-[10px]">{e.source}</Badge>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground max-w-[200px] truncate">{e.reason ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Info about what triggers a log entry */}
      <div className="text-[10px] text-muted-foreground space-y-1 border border-border/30 rounded-lg p-3">
        <div className="font-semibold text-foreground/70 mb-1">What generates an audit entry:</div>
        <div>· Vision kill switch triggered (<code>POST /api/vision/kill-switch</code>)</div>
        <div>· Vision re-enabled (<code>POST /api/vision/enable</code>)</div>
        <div>· Any future limit/model/config changes routed through the ProtectionConfigLog API</div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// COST CONTRIBUTION ANALYTICS  — 6 interactive charts
// ══════════════════════════════════════════════════════════════════════════════

// ── Risk colour from cost value ───────────────────────────────────────────────
function riskFill(usd: number, hasIncident = false): string {
  if (hasIncident || usd >= 50) return '#7f1d1d'; // dark red
  if (usd >= 25) return '#ef4444';                 // red
  if (usd >= 10) return '#f97316';                 // orange
  if (usd >= 1)  return '#eab308';                 // yellow
  return '#22c55e';                                 // green
}

// ── Palette for non-cost charts (token, model, document, vision breakdown) ───
const PIE_PALETTE = [
  '#3b82f6','#f59e0b','#10b981','#8b5cf6','#ef4444',
  '#06b6d4','#ec4899','#84cc16','#a855f7','#0ea5e9',
  '#f97316','#14b8a6','#6366f1','#fb923c',
];

// ── Custom tooltip ─────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, grandTotal, isTokenChart = false }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-card border border-border rounded-xl shadow-2xl p-3 text-xs max-w-[220px] space-y-1">
      <div className="font-bold text-sm truncate">{d.label}</div>
      {d.current != null && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Current Cost</span>
          <span className="font-mono font-bold text-amber-400">{fmt(d.current)}</span>
        </div>
      )}
      {d.historical != null && d.historical > 0 && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Historical Peak</span>
          <span className="font-mono text-orange-400">{fmt(d.historical)}</span>
        </div>
      )}
      {d.cost != null && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Cost</span>
          <span className="font-mono font-bold text-amber-400">{fmt(d.cost)}</span>
        </div>
      )}
      {d.value != null && isTokenChart && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Tokens</span>
          <span className="font-mono">{(d.value as number).toLocaleString()}</span>
        </div>
      )}
      {d.pct_current != null && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">% of Spend</span>
          <span className="font-mono">{d.pct_current}%</span>
        </div>
      )}
      {grandTotal != null && d.current != null && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">% of Total</span>
          <span className="font-mono">{grandTotal > 0 ? ((d.current / grandTotal) * 100).toFixed(1) : 0}%</span>
        </div>
      )}
      {d.calls != null && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">API Calls</span>
          <span className="font-mono">{(d.calls as number).toLocaleString()}</span>
        </div>
      )}
      {d.avg != null && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Avg Cost</span>
          <span className="font-mono">{fmt(d.avg)}</span>
        </div>
      )}
      {d.highest != null && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Highest Request</span>
          <span className="font-mono text-red-400">{fmt(d.highest)}</span>
        </div>
      )}
      {d.last_used && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Last Used</span>
          <span className="font-mono">{new Date(d.last_used).toLocaleDateString()}</span>
        </div>
      )}
      {d.saved != null && d.saved > 0 && (
        <div className="flex justify-between gap-3">
          <span className="text-muted-foreground">Saved</span>
          <span className="font-mono text-green-400">{fmt(d.saved)}</span>
        </div>
      )}
      {d.has_incident && (
        <div className="mt-1 pt-1 border-t border-border/50 text-[10px] text-red-300">
          🔥 Historical incident recorded
          {d.incident?.date && ` · ${new Date(d.incident.date).toLocaleDateString()}`}
          {d.incident?.cost != null && ` · ${fmt(d.incident.cost)}`}
        </div>
      )}
    </div>
  );
}

// ── Incident label renderer (renders "🔥 $X" on slice label line) ─────────────
function IncidentLabel({ cx, cy, midAngle, outerRadius, payload }: any) {
  if (!payload?.has_incident) return null;
  const RADIAN = Math.PI / 180;
  const r = outerRadius + 18;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="#fca5a5" fontSize={9} textAnchor="middle" dominantBaseline="central">
      🔥{payload.incident?.cost != null ? ` ${payload.incident.cost.toFixed(0)}` : ''}
    </text>
  );
}

// ── CSV export helper ─────────────────────────────────────────────────────────
function exportCsv(rows: any[], filename: string) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const csv  = [keys.join(','), ...rows.map(r => keys.map(k => JSON.stringify(r[k] ?? '')).join(','))].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = filename;
  a.click();
}

// ── SVG export helper ─────────────────────────────────────────────────────────
function exportSvg(containerRef: React.RefObject<HTMLDivElement | null>, filename: string) {
  const svg = containerRef.current?.querySelector('svg');
  if (!svg) return;
  const blob = new Blob([svg.outerHTML], { type: 'image/svg+xml' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

// ── PNG export helper ─────────────────────────────────────────────────────────
function exportPng(containerRef: React.RefObject<HTMLDivElement | null>, filename: string) {
  const svg = containerRef.current?.querySelector('svg');
  if (!svg) return;
  const svgData = new XMLSerializer().serializeToString(svg);
  const img = new Image();
  const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  img.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width  = img.width  || 600;
    canvas.height = img.height || 400;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = filename;
    a.click();
  };
  img.src = url;
}

// ── Single chart card ─────────────────────────────────────────────────────────
function ChartCard({
  title, subtitle, children, chartRef, csvData, csvName,
  svgName, pngName,
}: {
  title: string; subtitle?: string;
  children: React.ReactNode;
  chartRef: React.RefObject<HTMLDivElement | null>;
  csvData?: any[]; csvName?: string;
  svgName?: string; pngName?: string;
}) {
  const [showExport, setShowExport] = useState(false);
  return (
    <Card className="relative">
      <CardHeader className="pb-1">
        <CardTitle className="text-sm flex items-center gap-2">
          <PieChartIcon className="h-4 w-4 text-amber-400 shrink-0" />
          {title}
          <div className="ml-auto relative">
            <button
              onClick={() => setShowExport(s => !s)}
              className="text-[10px] text-muted-foreground hover:text-foreground border border-border/50 rounded px-2 py-0.5 transition-colors"
            >
              Export ▾
            </button>
            {showExport && (
              <div className="absolute right-0 top-6 z-20 bg-card border border-border rounded-lg shadow-xl text-xs divide-y divide-border/40 min-w-[100px]">
                {csvData && <button className="block w-full text-left px-3 py-1.5 hover:bg-muted/40" onClick={() => { exportCsv(csvData, csvName ?? 'chart.csv'); setShowExport(false); }}>CSV</button>}
                <button className="block w-full text-left px-3 py-1.5 hover:bg-muted/40" onClick={() => { exportSvg(chartRef, svgName ?? 'chart.svg'); setShowExport(false); }}>SVG</button>
                <button className="block w-full text-left px-3 py-1.5 hover:bg-muted/40" onClick={() => { exportPng(chartRef, pngName ?? 'chart.png'); setShowExport(false); }}>PNG</button>
                <button className="block w-full text-left px-3 py-1.5 hover:bg-muted/40" onClick={() => { window.print(); setShowExport(false); }}>PDF (Print)</button>
              </div>
            )}
          </div>
        </CardTitle>
        {subtitle && <p className="text-[10px] text-muted-foreground">{subtitle}</p>}
      </CardHeader>
      <CardContent className="pt-0" ref={chartRef as any}>
        {children}
      </CardContent>
    </Card>
  );
}

// ── Main analytics tab ────────────────────────────────────────────────────────
function CostAnalyticsTab() {
  const [drillDown, setDrillDown] = useState<{ id: string; label: string } | null>(null);

  const { data, isLoading } = useCosts<any>('analytics', '/api/costs/analytics', { refetchInterval: 120_000 });

  const chart1Data: any[] = data?.chart1_feature_current   ?? [];
  const chart2Data: any[] = data?.chart2_feature_historical ?? [];
  const chart3Data: any[] = data?.chart3_token_distribution ?? [];
  const chart4Data: any[] = data?.chart4_model_cost         ?? [];
  const chart5Data: any[] = data?.chart5_top_documents      ?? [];
  const chart6Data: any[] = data?.chart6_vision_breakdown   ?? [];
  const grandCurrent  = data?.grand_total_current_usd   ?? 0;
  const grandHist     = data?.grand_total_historical_usd ?? 0;

  // Feature ID mapping for drill-down
  const FEAT_ID: Record<string, string> = {
    'Image Captioning':       'image_captioning',
    'Translation Studio':     'translation',
    'Learning Hub':           'learning_hub',
    'AI Chat':                'ai_chat',
    'Innovation Engine':      'innovation_engine',
    'Training Generator':     'training_generator',
    'Gallery Reindex':        'gallery_reindex',
    'Image Translation':      'image_translation',
    'LinkedIn Generator':     'linkedin_generator',
    'X-Ray Analysis':         'xray_analysis',
    'RAG Vision (Knowledge Base)': 'rag_vision',
  };

  // Refs for per-chart export
  const refs = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null),
                useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)];

  if (isLoading) {
    return <div className="flex items-center justify-center h-60 text-muted-foreground text-sm">Loading analytics…</div>;
  }

  const CHART_H = 280;

  // ── Shared: custom label showing name + % ────────────────────────────────────
  const renderLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, payload, percent }: any) => {
    const RADIAN = Math.PI / 180;
    const r  = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x  = cx + r * Math.cos(-midAngle * RADIAN);
    const y  = cy + r * Math.sin(-midAngle * RADIAN);
    if (percent < 0.05) return null; // skip tiny slices
    return (
      <text x={x} y={y} fill="#fff" fontSize={9} textAnchor="middle" dominantBaseline="central" fontWeight="600">
        {`${(percent * 100).toFixed(0)}%`}
      </text>
    );
  };

  // ── Chart 1: Current Cost by Feature (Doughnut) ───────────────────────────
  const chart1 = chart1Data.map(d => ({
    ...d, value: d.current, fill: riskFill(Math.max(d.current, d.historical), d.has_incident),
  }));

  // ── Chart 2: Historical Cost (Doughnut) ───────────────────────────────────
  const chart2 = chart2Data.map(d => ({
    ...d, value: d.historical, fill: riskFill(d.historical, d.has_incident),
  }));

  // ── Chart 3: Token Distribution (Pie) ────────────────────────────────────
  const chart3 = chart3Data.map((d, i) => ({ ...d, fill: d.color ?? PIE_PALETTE[i % PIE_PALETTE.length] }));

  // ── Chart 4: Model Cost (Doughnut) ───────────────────────────────────────
  const chart4 = chart4Data.map((d, i) => ({
    ...d, value: d.cost, label: d.label, fill: d.color ?? PIE_PALETTE[i % PIE_PALETTE.length],
  }));

  // ── Chart 5: Top Documents (Doughnut) ────────────────────────────────────
  const chart5 = chart5Data.map((d, i) => ({
    ...d, value: d.cost, fill: riskFill(d.cost),
    label: d.label.length > 22 ? d.label.slice(0, 20) + '…' : d.label,
  }));

  // ── Chart 6: Vision Breakdown (Pie) ──────────────────────────────────────
  const chart6 = chart6Data.map((d, i) => ({
    ...d, value: Math.max(d.cost, d.saved, d.calls * 0.001),
    label: d.label, fill: d.color ?? PIE_PALETTE[i % PIE_PALETTE.length],
  }));

  const handleFeatureClick = (entry: any) => {
    const id = FEAT_ID[entry?.label ?? ''];
    if (id) setDrillDown({ id, label: entry.label });
  };

  // ── Legend component ──────────────────────────────────────────────────────
  const ChartLegend = ({ items }: { items: { label: string; fill: string; value?: number; pct?: number }[] }) => (
    <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center mt-2">
      {items.slice(0, 12).map((item, i) => (
        <div key={i} className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: item.fill }} />
          <span className="truncate max-w-[100px]">{item.label}</span>
        </div>
      ))}
    </div>
  );

  const isEmpty = (arr: any[]) => !arr.length || arr.every(d => (d.value ?? 0) === 0);

  const EmptyState = () => (
    <div className="flex items-center justify-center h-40 text-muted-foreground text-xs">
      No data recorded yet for this chart
    </div>
  );

  return (
    <>
      {drillDown && (
        <DrillDownModal featureId={drillDown.id} featureLabel={drillDown.label} onClose={() => setDrillDown(null)} />
      )}

      <div className="space-y-4">
        {/* Header */}
        <div>
          <h3 className="font-bold text-sm">Cost Contribution Analytics</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Current lifetime: <span className="font-mono text-amber-400">{fmt(grandCurrent)}</span>
            {' · '}Historical peak exposure: <span className="font-mono text-red-400">{fmt(grandHist)}</span>
            {' · '}Click any slice to drill down · 🔥 = historical incident
          </p>
        </div>

        {/* Risk legend */}
        <div className="flex flex-wrap gap-2 text-[10px]">
          {[
            { label: 'Very Low (<$1)',   color: '#22c55e' },
            { label: 'Medium ($1–$10)', color: '#eab308' },
            { label: 'High ($10–$25)',  color: '#f97316' },
            { label: 'Critical ($25–$50)', color: '#ef4444' },
            { label: 'Incident (>$50)', color: '#7f1d1d' },
          ].map(c => (
            <span key={c.label} className="flex items-center gap-1 border border-border/40 rounded-full px-2 py-0.5">
              <span className="w-2 h-2 rounded-full" style={{ background: c.color }} />
              {c.label}
            </span>
          ))}
        </div>

        {/* Charts grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

          {/* Chart 1 — Current Cost by Feature */}
          <ChartCard
            title="Cost by Feature (Current)"
            subtitle="Click any slice to see every API request for that feature"
            chartRef={refs[0]}
            csvData={chart1Data} csvName="feature_current.csv"
            svgName="feature_current.svg" pngName="feature_current.png"
          >
            {isEmpty(chart1) ? <EmptyState /> : (
              <>
                <ResponsiveContainer width="100%" height={CHART_H}>
                  <PieChart>
                    <Pie
                      data={chart1} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" innerRadius="40%" outerRadius="72%"
                      animationBegin={0} animationDuration={600}
                      labelLine={false} label={renderLabel}
                      onClick={(entry) => handleFeatureClick(entry)}
                      style={{ cursor: 'pointer' }}
                    >
                      {chart1.map((entry, i) => <Cell key={i} fill={entry.fill} stroke="transparent" />)}
                    </Pie>
                    <Pie
                      data={chart1} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" innerRadius="72%" outerRadius="76%"
                      fill="transparent" stroke="transparent"
                      label={<IncidentLabel />} labelLine={false}
                    >
                      {chart1.map((_e, i) => <Cell key={i} fill="transparent" stroke="transparent" />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip grandTotal={grandCurrent} />} />
                  </PieChart>
                </ResponsiveContainer>
                <ChartLegend items={chart1} />
              </>
            )}
          </ChartCard>

          {/* Chart 2 — Historical Cost */}
          <ChartCard
            title="Historical Cost Contribution"
            subtitle="Lifetime peak exposure — 🔥 = incident recorded above $25"
            chartRef={refs[1]}
            csvData={chart2Data} csvName="feature_historical.csv"
            svgName="feature_historical.svg" pngName="feature_historical.png"
          >
            {isEmpty(chart2) ? <EmptyState /> : (
              <>
                <ResponsiveContainer width="100%" height={CHART_H}>
                  <PieChart>
                    <Pie
                      data={chart2} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" innerRadius="40%" outerRadius="72%"
                      animationBegin={0} animationDuration={700}
                      labelLine={false} label={renderLabel}
                      onClick={(entry) => handleFeatureClick(entry)}
                      style={{ cursor: 'pointer' }}
                    >
                      {chart2.map((entry, i) => <Cell key={i} fill={entry.fill} stroke="transparent" />)}
                    </Pie>
                    <Pie
                      data={chart2} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" innerRadius="72%" outerRadius="76%"
                      fill="transparent" stroke="transparent"
                      label={<IncidentLabel />} labelLine={false}
                    >
                      {chart2.map((_e, i) => <Cell key={i} fill="transparent" stroke="transparent" />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip grandTotal={grandHist} />} />
                  </PieChart>
                </ResponsiveContainer>
                <ChartLegend items={chart2} />
              </>
            )}
          </ChartCard>

          {/* Chart 3 — Token Distribution */}
          <ChartCard
            title="Token Consumption Distribution"
            subtitle="Prompt · Completion · Cached · Vision · OCR"
            chartRef={refs[2]}
            csvData={chart3Data} csvName="token_distribution.csv"
            svgName="token_distribution.svg" pngName="token_distribution.png"
          >
            {isEmpty(chart3) ? <EmptyState /> : (
              <>
                <ResponsiveContainer width="100%" height={CHART_H}>
                  <PieChart>
                    <Pie
                      data={chart3} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" outerRadius="72%"
                      animationBegin={0} animationDuration={600}
                      labelLine={false} label={renderLabel}
                    >
                      {chart3.map((entry, i) => <Cell key={i} fill={entry.fill} stroke="transparent" />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip isTokenChart />} />
                  </PieChart>
                </ResponsiveContainer>
                <ChartLegend items={chart3} />
              </>
            )}
          </ChartCard>

          {/* Chart 4 — Model Cost */}
          <ChartCard
            title="Model Cost Contribution"
            subtitle="Spending by model — GPT-5.4 is 20× more expensive than GPT-4o"
            chartRef={refs[3]}
            csvData={chart4Data} csvName="model_cost.csv"
            svgName="model_cost.svg" pngName="model_cost.png"
          >
            {isEmpty(chart4) ? <EmptyState /> : (
              <>
                <ResponsiveContainer width="100%" height={CHART_H}>
                  <PieChart>
                    <Pie
                      data={chart4} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" innerRadius="35%" outerRadius="72%"
                      animationBegin={0} animationDuration={700}
                      labelLine={false} label={renderLabel}
                    >
                      {chart4.map((entry, i) => <Cell key={i} fill={entry.fill} stroke="transparent" />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <ChartLegend items={chart4} />
              </>
            )}
          </ChartCard>

          {/* Chart 5 — Top 10 Documents */}
          <ChartCard
            title="Document Cost Distribution"
            subtitle="Top 10 most expensive uploaded documents"
            chartRef={refs[4]}
            csvData={chart5Data} csvName="top_documents.csv"
            svgName="top_documents.svg" pngName="top_documents.png"
          >
            {isEmpty(chart5) ? <EmptyState /> : (
              <>
                <ResponsiveContainer width="100%" height={CHART_H}>
                  <PieChart>
                    <Pie
                      data={chart5} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" innerRadius="35%" outerRadius="72%"
                      animationBegin={0} animationDuration={600}
                      labelLine={false} label={renderLabel}
                    >
                      {chart5.map((entry, i) => <Cell key={i} fill={entry.fill} stroke="transparent" />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-2 space-y-1">
                  {chart5Data.slice(0, 5).map((d: any, i: number) => (
                    <div key={i} className="flex items-center justify-between text-[10px]">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: riskFill(d.cost) }} />
                        <span className="truncate max-w-[160px] text-muted-foreground">{d.label}</span>
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <span className="font-mono text-amber-400">{fmt(d.cost)}</span>
                        <span className="text-muted-foreground">{d.calls} calls</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </ChartCard>

          {/* Chart 6 — Vision Cost Breakdown */}
          <ChartCard
            title="Vision Cost Breakdown"
            subtitle="Image Captioning sub-categories: API calls, cache, dedup, blocked"
            chartRef={refs[5]}
            csvData={chart6Data} csvName="vision_breakdown.csv"
            svgName="vision_breakdown.svg" pngName="vision_breakdown.png"
          >
            {isEmpty(chart6) ? <EmptyState /> : (
              <>
                <ResponsiveContainer width="100%" height={CHART_H}>
                  <PieChart>
                    <Pie
                      data={chart6} dataKey="value" nameKey="label"
                      cx="50%" cy="50%" outerRadius="72%"
                      animationBegin={0} animationDuration={700}
                      labelLine={false} label={renderLabel}
                    >
                      {chart6.map((entry, i) => <Cell key={i} fill={entry.fill} stroke="transparent" />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-2 space-y-1">
                  {chart6Data.map((d: any, i: number) => (
                    <div key={i} className="flex items-center justify-between text-[10px]">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
                        <span className="text-muted-foreground">{d.label}</span>
                      </div>
                      <div className="flex gap-3 shrink-0">
                        {d.cost > 0 && <span className="font-mono text-red-400">{fmt(d.cost)}</span>}
                        {d.saved > 0 && <span className="font-mono text-green-400">+{fmt(d.saved)}</span>}
                        <span className="text-muted-foreground">{d.calls}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </ChartCard>

        </div>

        {/* Note */}
        <p className="text-[10px] text-muted-foreground">
          All data from database records only. No API calls made to generate these charts.
          Colors reflect current cost risk level. 🔥 markers appear on features with historical incidents ≥$25.
        </p>
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Main page
// ══════════════════════════════════════════════════════════════════════════════
const TABS = [
  { id: 'overview',          label: 'Overview',         icon: BarChart2 },
  { id: 'exec-summary',      label: 'Exec Summary',     icon: Building2 },
  { id: 'cost-analytics',    label: 'Cost Analytics',   icon: PieChartIcon },
  { id: 'incidents',         label: 'Incidents',        icon: History },
  { id: 'leak-detector',     label: 'Leak Detector',    icon: Bug },
  { id: 'root-cause',        label: 'Root Cause',       icon: Activity },
  { id: 'config-audit',      label: 'Config Audit',     icon: GitCommit },
  { id: 'by-feature',        label: 'By Feature',       icon: Layers },
  { id: 'documents',         label: 'Documents',        icon: FileText },
  { id: 'chat',              label: 'AI Chat',          icon: MessageSquare },
  { id: 'translation',       label: 'Translation',      icon: Languages },
  { id: 'learning',          label: 'Learning Hub',     icon: Brain },
  { id: 'analytics',         label: 'Token Analytics',  icon: Cpu },
  { id: 'savings',           label: 'Savings',          icon: TrendingDown },
  { id: 'alerts',            label: 'Alerts',           icon: AlertTriangle },
  { id: 'top-ops',           label: 'Top Ops',          icon: TrendingUp },
  { id: 'risk-controls',     label: 'Risk Controls',    icon: Shield },
  { id: 'vision-protection', label: 'Vision Protection',icon: ShieldAlert },
  { id: 'reconcile',         label: 'Reconcile',        icon: GitCompare },
  { id: 'inspector',         label: 'Inspector',        icon: Search },
  { id: 'export',            label: 'Export',           icon: Download },
  { id: 'settings',          label: 'Settings',         icon: Settings },
  { id: 'recommendations',   label: 'Auto Optimize',    icon: Lightbulb },
];

export default function CostDashboardPage() {
  const [tab, setTab] = useState('overview');
  const qc = useQueryClient();
  const { toast } = useToast();

  const handleRefresh = () => {
    qc.invalidateQueries({ queryKey: ['costs'] });
    toast({ title: 'Refreshing cost data…' });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 border-b border-border shrink-0">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-amber-400" />
              Cost Dashboard
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Real-time OpenAI usage, token consumption, and optimization insights
            </p>
          </div>
          <Button size="sm" variant="outline" className="text-xs gap-1.5 h-8 shrink-0" onClick={handleRefresh}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Financial Health Banner — always visible */}
      <div className="px-6 py-2 border-b border-border/50 shrink-0">
        <FinancialHealthBanner />
      </div>

      {/* Top Cost Consumers — always visible ranked section */}
      <TopCostConsumers />

      {/* Tab bar */}
      <div className="border-b border-border shrink-0 overflow-x-auto scrollbar-none">
        <div className="flex px-6 gap-0 min-w-max">
          {TABS.map(t => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-4 py-3 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
                  active
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                }`}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'overview'         && <OverviewTab />}
        {tab === 'exec-summary'     && <ExecutiveSummaryTab />}
        {tab === 'cost-analytics'   && <CostAnalyticsTab />}
        {tab === 'incidents'        && <IncidentHistoryTab />}
        {tab === 'leak-detector'    && <LeakDetectorTab />}
        {tab === 'root-cause'       && <RootCauseTab />}
        {tab === 'config-audit'     && <ConfigAuditTab />}
        {tab === 'by-feature'       && <ByFeatureTab />}
        {tab === 'documents'        && <DocumentsTab />}
        {tab === 'chat'             && <ChatCostTab />}
        {tab === 'translation'      && <TranslationCostTab />}
        {tab === 'learning'         && <LearningCostTab />}
        {tab === 'analytics'        && <TokenAnalyticsTab />}
        {tab === 'savings'          && <SavingsTab />}
        {tab === 'alerts'           && <AlertsTab />}
        {tab === 'top-ops'          && <TopOperationsTab />}
        {tab === 'risk-controls'     && <HighRiskControlsTab />}
        {tab === 'vision-protection' && <VisionProtectionTab />}
        {tab === 'reconcile'        && <ReconcileTab />}
        {tab === 'inspector'        && <RequestInspectorTab />}
        {tab === 'export'           && <ExportTab />}
        {tab === 'settings'         && <SettingsTab />}
        {tab === 'recommendations'  && <RecommendationsTab />}
      </div>
    </div>
  );
}
