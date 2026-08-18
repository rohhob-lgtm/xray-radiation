import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'wouter';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import {
  DollarSign, TrendingDown, TrendingUp, Zap, Clock, FileText, ChevronDown, ChevronUp,
  ArrowUpDown, ArrowUp, ArrowDown, AlertTriangle, Lightbulb, RefreshCw, Download,
  Cpu, Database, Layers, CheckCircle, BarChart2, Target, Activity, Award,
  PieChart, Settings, ChevronRight, Users,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

// ─── Types ─────────────────────────────────────────────────────────────────────

interface BudgetStatus {
  budget_usd: number;
  spent_this_month: number;
  remaining: number | null;
  pct_consumed: number | null;
  warning_level: 'none' | 'warn70' | 'warn90' | 'critical';
  is_admin: boolean;
  default_markup_pct: number;
}

interface ForecastData {
  avg_daily_usd: number;
  projected_eom_usd: number;
  remaining_budget_usd: number | null;
  avg_cost_per_translation: number;
  days_elapsed: number;
  days_remaining: number;
  days_in_month: number;
  month_cost: number;
  month_jobs: number;
}

interface LiveMetrics {
  today_usd: number;
  week_usd: number;
  month_usd: number;
  avg_cost_per_file: number;
  avg_cost_per_page: number;
  avg_cost_per_1k_words: number;
  avg_cost_per_token: number;
  total_files: number;
  total_tokens: number;
}

interface ProfitRow {
  job_id: string;
  project_name: string;
  created_at: string;
  file_type: string;
  status: string;
  segments_total: number;
  actual_cost_usd: number;
  markup_pct: number;
  selling_price_usd: number;
  gross_profit_usd: number;
  margin_pct: number;
}

interface ProfitData {
  jobs: ProfitRow[];
  total: number;
  page: number;
  pages: number;
  markup_pct: number;
  summary: {
    total_cost_usd: number;
    total_revenue_usd: number;
    total_profit_usd: number;
    avg_margin_pct: number;
  };
}

interface Top20Job {
  id: string;
  project_name: string;
  created_at: string;
  est_cost_usd: number;
  translate_in_tokens: number;
  translate_out_tokens: number;
  review_in_tokens: number;
  review_out_tokens: number;
  file_type: string;
  model: string;
  segments_total: number;
  source_pages: number;
}

interface UsageJob {
  id: string;
  created_at: string;
  project_name: string;
  file_type: string;
  model: string;
  provider: string;
  status: string;
  duration_secs: number;
  segments_total: number;
  segments_translated: number;
  segments_reviewed: number;
  memory_hits: number;
  source_pages: number;
  chars_translated: number;
  retries: number;
  input_tokens: number;
  output_tokens: number;
  translate_in_tokens: number;
  translate_out_tokens: number;
  translate_cached_tokens: number;
  review_in_tokens: number;
  review_out_tokens: number;
  review_cached_tokens: number;
  api_calls_translate: number;
  api_calls_review: number;
  stage_extract_s: number;
  stage_translate_s: number;
  stage_review_s: number;
  stage_rebuild_s: number;
  stage_validate_s: number;
  translate_cost_usd: number;
  review_cost_usd: number;
  total_cost_usd: number;
  memory_savings_usd: number;
  cached_savings_usd: number;
  review_savings_usd: number;
}

interface ChartPoint { label: string; cost: number; jobs: number; tokens: number; }
interface ChartData {
  daily: ChartPoint[];
  weekly: ChartPoint[];
  monthly: ChartPoint[];
  avg_cost_per_file: number;
  avg_cost_per_page: number;
  avg_cost_per_1k_words: number;
  total_memory_savings: number;
  total_cached_savings: number;
  total_review_savings: number;
  summary: {
    today_cost: number; today_jobs: number;
    week_cost: number;  week_jobs: number;
    month_cost: number; month_jobs: number;
    all_cost: number;   all_jobs: number;
  };
}
interface HistoryData { jobs: UsageJob[]; total: number; page: number; pages: number; }

type SortKey = 'created_at' | 'total_cost_usd' | 'project_name' | 'duration_secs' | 'input_tokens';

// ─── Helpers ───────────────────────────────────────────────────────────────────

const fmtUsd  = (v: number) => `$${(v ?? 0).toFixed(6)}`;
const fmtUsd4 = (v: number) => `$${(v ?? 0).toFixed(4)}`;
const fmtUsd2 = (v: number) => `$${(v ?? 0).toFixed(2)}`;
const fmtTok  = (v: number) => `$${(v ?? 0).toFixed(8)}`;
const fmtSec  = (v: number) => v >= 60 ? `${(v / 60).toFixed(1)}m` : `${(v ?? 0).toFixed(1)}s`;
const fmtNum  = (v: number) => (v ?? 0).toLocaleString();
const fmtDate = (s: string) =>
  new Date(s).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });

const MODEL_PRICES: Record<string, [number, number]> = {
  'gpt-4o-mini':  [0.15, 0.60],
  'gpt-4o':       [2.50, 10.00],
  'gpt-4.1':      [2.00, 8.00],
  'gpt-4.1-mini': [0.40, 1.60],
};
function modelCost(inTok: number, outTok: number, model: string): number {
  const key = Object.keys(MODEL_PRICES).find(k => model.startsWith(k)) ?? 'gpt-4o';
  const [pin, pout] = MODEL_PRICES[key];
  return (inTok * pin + outTok * pout) / 1_000_000;
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ─── Budget Bar ────────────────────────────────────────────────────────────────

function BudgetBar({
  budget, isAdmin, onSaveBudget,
}: {
  budget: BudgetStatus | null;
  isAdmin: boolean;
  onSaveBudget: (v: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState('');

  if (!budget) return null;

  const pct = budget.pct_consumed ?? 0;
  const hasLimit = budget.budget_usd > 0;

  const barColor =
    budget.warning_level === 'critical' ? 'bg-red-500' :
    budget.warning_level === 'warn90'   ? 'bg-orange-500' :
    budget.warning_level === 'warn70'   ? 'bg-amber-400' :
    'bg-emerald-500';

  const warnBg =
    budget.warning_level === 'critical' ? 'bg-red-50 dark:bg-red-950/30 border-red-300 dark:border-red-700 text-red-700 dark:text-red-400' :
    budget.warning_level === 'warn90'   ? 'bg-orange-50 dark:bg-orange-950/30 border-orange-300 dark:border-orange-700 text-orange-700 dark:text-orange-400' :
    budget.warning_level === 'warn70'   ? 'bg-amber-50 dark:bg-amber-950/30 border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400' :
    null;

  const warnMsg =
    budget.warning_level === 'critical' ? '🚨 Monthly budget exhausted — all API calls continue to incur costs' :
    budget.warning_level === 'warn90'   ? '⚠️ 90% of monthly budget consumed' :
    budget.warning_level === 'warn70'   ? '⚠️ 70% of monthly budget consumed' : null;

  return (
    <div className="border-b bg-card/80 backdrop-blur">
      <div className="max-w-6xl mx-auto px-4 py-2.5 space-y-1.5">
        {/* Warning banner */}
        {warnBg && warnMsg && (
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded border text-xs font-medium ${warnBg}`}>
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            {warnMsg}
          </div>
        )}

        {/* Budget row */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground font-medium shrink-0">Monthly Budget</span>

          {hasLimit ? (
            <div className="flex-1 flex items-center gap-2 min-w-0">
              <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className={`h-2 rounded-full transition-all duration-500 ${barColor}`}
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
              <span className="text-xs font-mono font-bold shrink-0" style={{
                color: budget.warning_level === 'critical' ? '#ef4444' :
                       budget.warning_level === 'warn90'   ? '#f97316' :
                       budget.warning_level === 'warn70'   ? '#d97706' : '#16a34a',
              }}>{pct.toFixed(1)}%</span>
              <span className="text-xs text-muted-foreground shrink-0">
                {fmtUsd2(budget.spent_this_month)} / {fmtUsd2(budget.budget_usd)}
              </span>
              {budget.remaining !== null && (
                <span className="text-xs font-medium shrink-0 text-emerald-600">
                  {fmtUsd2(budget.remaining)} remaining
                </span>
              )}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">No budget limit set</span>
          )}

          {isAdmin && (
            editing ? (
              <div className="flex items-center gap-1.5 ml-auto shrink-0">
                <span className="text-xs text-muted-foreground">$</span>
                <Input
                  className="h-6 w-24 text-xs"
                  placeholder="0 = unlimited"
                  value={inputVal}
                  onChange={e => setInputVal(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { onSaveBudget(parseFloat(inputVal) || 0); setEditing(false); }
                    if (e.key === 'Escape') setEditing(false);
                  }}
                  autoFocus
                />
                <Button size="sm" className="h-6 text-xs px-2" onClick={() => { onSaveBudget(parseFloat(inputVal) || 0); setEditing(false); }}>Save</Button>
                <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => setEditing(false)}>Cancel</Button>
              </div>
            ) : (
              <Button
                variant="ghost" size="sm"
                className="h-6 text-xs ml-auto shrink-0 gap-1"
                onClick={() => { setInputVal(String(budget.budget_usd || '')); setEditing(true); }}
              >
                <Settings className="h-3 w-3" /> Set budget
              </Button>
            )
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Forecast Panel ────────────────────────────────────────────────────────────

function ForecastPanel({ data }: { data: ForecastData | null }) {
  if (!data) return null;

  const items = [
    {
      label: 'Avg Daily Spend',
      value: fmtUsd4(data.avg_daily_usd),
      sub: `${data.days_elapsed}d elapsed`,
      icon: Activity,
      color: 'text-blue-600',
      bg: 'bg-blue-50 dark:bg-blue-950/30',
    },
    {
      label: 'Projected Month-End',
      value: fmtUsd4(data.projected_eom_usd),
      sub: `${data.days_remaining}d remaining`,
      icon: TrendingUp,
      color: 'text-violet-600',
      bg: 'bg-violet-50 dark:bg-violet-950/30',
    },
    {
      label: 'Avg Cost / Translation',
      value: fmtUsd4(data.avg_cost_per_translation),
      sub: `${data.month_jobs} jobs this month`,
      icon: FileText,
      color: 'text-amber-600',
      bg: 'bg-amber-50 dark:bg-amber-950/30',
    },
    ...(data.remaining_budget_usd !== null ? [{
      label: 'Budget Headroom (EOM)',
      value: fmtUsd2(data.remaining_budget_usd),
      sub: 'projected surplus',
      icon: Target,
      color: data.remaining_budget_usd > 0 ? 'text-emerald-600' : 'text-red-600',
      bg: data.remaining_budget_usd > 0 ? 'bg-emerald-50 dark:bg-emerald-950/30' : 'bg-red-50 dark:bg-red-950/30',
    }] : []),
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {items.map(item => (
        <Card key={item.label} className="border-0 shadow-sm">
          <CardContent className="pt-3 pb-3">
            <div className="flex items-start gap-2">
              <div className={`p-1.5 rounded-md ${item.bg} shrink-0`}>
                <item.icon className={`h-3.5 w-3.5 ${item.color}`} />
              </div>
              <div className="min-w-0">
                <p className="text-[10px] text-muted-foreground leading-tight">{item.label}</p>
                <p className={`font-bold font-mono text-sm mt-0.5 ${item.color}`}>{item.value}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{item.sub}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ─── Live Metrics Strip ────────────────────────────────────────────────────────

function LiveMetricsStrip({ data, lastRefresh }: { data: LiveMetrics | null; lastRefresh: Date | null }) {
  const metrics = data ? [
    { label: 'Today',         value: fmtUsd4(data.today_usd),            accent: 'text-blue-600' },
    { label: 'This Week',     value: fmtUsd4(data.week_usd),             accent: 'text-violet-600' },
    { label: 'This Month',    value: fmtUsd4(data.month_usd),            accent: 'text-amber-600' },
    { label: 'Avg / File',    value: fmtUsd4(data.avg_cost_per_file),    accent: 'text-slate-700 dark:text-slate-300' },
    { label: 'Avg / Page',    value: fmtUsd4(data.avg_cost_per_page),    accent: 'text-slate-700 dark:text-slate-300' },
    { label: 'Avg / 1K Words',value: fmtUsd4(data.avg_cost_per_1k_words),accent: 'text-slate-700 dark:text-slate-300' },
    { label: 'Avg / Token',   value: fmtTok(data.avg_cost_per_token),    accent: 'text-slate-700 dark:text-slate-300' },
  ] : [];

  return (
    <Card className="border-0 shadow-sm bg-gradient-to-r from-slate-900 to-slate-800 text-white">
      <CardContent className="py-3 px-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-mono text-slate-300 uppercase tracking-wider">Live Metrics</span>
          </div>
          {lastRefresh && (
            <span className="text-[10px] text-slate-400 font-mono">
              Updated {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              {' · '}refreshes every 30s
            </span>
          )}
        </div>
        {data ? (
          <div className="grid grid-cols-4 md:grid-cols-7 gap-x-4 gap-y-1">
            {metrics.map((m, i) => (
              <div key={m.label} className={`${i === 2 ? 'border-r border-slate-600 pr-4 md:border-r' : ''}`}>
                <p className="text-[9px] text-slate-400 uppercase tracking-widest leading-tight">{m.label}</p>
                <p className={`font-bold font-mono text-sm leading-tight mt-0.5 ${m.accent}`}>{m.value}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-slate-400 text-xs">
            <RefreshCw className="h-3 w-3 animate-spin" />
            Loading live metrics…
          </div>
        )}
        {data && (
          <div className="mt-2 pt-2 border-t border-slate-700 flex gap-4 text-[10px] text-slate-400">
            <span>{fmtNum(data.total_files)} total files</span>
            <span>{fmtNum(data.total_tokens)} total tokens billed</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Top 20 Table ─────────────────────────────────────────────────────────────

function Top20Table({ jobs }: { jobs: Top20Job[] }) {
  const [open, setOpen] = useState(true);

  if (!jobs.length) return (
    <Card>
      <CardContent className="py-8 text-center text-sm text-muted-foreground">No translation jobs found</CardContent>
    </Card>
  );

  return (
    <Card>
      <button
        className="w-full flex items-center justify-between p-4 hover:bg-muted/30 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <CardTitle className="text-base flex items-center gap-2">
          <Award className="h-4 w-4 text-amber-500" />
          Top 20 Most Expensive Translations
        </CardTitle>
        {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>
      {open && (
        <div className="overflow-x-auto border-t">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-muted/50 text-muted-foreground">
                <th className="text-left px-3 py-2 font-medium">#</th>
                <th className="text-left px-3 py-2 font-medium">Project</th>
                <th className="text-left px-3 py-2 font-medium">Date</th>
                <th className="text-left px-3 py-2 font-medium">Type</th>
                <th className="text-left px-3 py-2 font-medium">Model</th>
                <th className="text-right px-3 py-2 font-medium">Segments</th>
                <th className="text-right px-3 py-2 font-medium">Pages</th>
                <th className="text-right px-3 py-2 font-medium">Total Tokens</th>
                <th className="text-right px-3 py-2 font-medium">Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j, i) => {
                const totalTok = j.translate_in_tokens + j.translate_out_tokens + j.review_in_tokens + j.review_out_tokens;
                const isTop3 = i < 3;
                return (
                  <tr
                    key={j.id}
                    className={`border-t border-border/40 ${isTop3 ? 'bg-amber-50/50 dark:bg-amber-950/10' : i % 2 === 0 ? '' : 'bg-muted/20'}`}
                  >
                    <td className="px-3 py-2 font-bold">
                      {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`}
                    </td>
                    <td className="px-3 py-2 font-medium max-w-[200px] truncate">{j.project_name}</td>
                    <td className="px-3 py-2 text-muted-foreground">{j.created_at ? fmtDate(j.created_at) : '—'}</td>
                    <td className="px-3 py-2"><Badge variant="outline" className="text-[9px] py-0 px-1 uppercase">{j.file_type}</Badge></td>
                    <td className="px-3 py-2 text-muted-foreground font-mono">{j.model}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtNum(j.segments_total)}</td>
                    <td className="px-3 py-2 text-right font-mono">{j.source_pages || '—'}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtNum(totalTok)}</td>
                    <td className="px-3 py-2 text-right font-bold font-mono text-primary">{fmtUsd4(j.est_cost_usd)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ─── Stage breakdown ───────────────────────────────────────────────────────────

function StageCostBreakdown({ job }: { job: UsageJob }) {
  const translateCost = modelCost(job.translate_in_tokens, job.translate_out_tokens, job.model || 'gpt-4o-mini');
  const reviewCost    = modelCost(job.review_in_tokens, job.review_out_tokens, 'gpt-4o');
  const totalApiCost  = translateCost + reviewCost;

  const stages = [
    { name: 'Document Extraction',              icon: FileText,    dur: job.stage_extract_s,   calls: 0, inTok: 0, outTok: 0, cached: 0, cost: 0,          isLocal: true,  color: '#64748b' },
    { name: `Translation API (${job.model || 'gpt-4o-mini'})`, icon: Cpu, dur: job.stage_translate_s, calls: job.api_calls_translate, inTok: job.translate_in_tokens, outTok: job.translate_out_tokens, cached: job.translate_cached_tokens, cost: translateCost, isLocal: false, color: '#3b82f6' },
    { name: 'AI Engineering Review (gpt-4o)',   icon: Zap,         dur: job.stage_review_s,    calls: job.api_calls_review, inTok: job.review_in_tokens, outTok: job.review_out_tokens, cached: job.review_cached_tokens, cost: reviewCost, isLocal: false, color: '#8b5cf6' },
    { name: 'Layout Reconstruction',            icon: Layers,      dur: job.stage_rebuild_s,   calls: 0, inTok: 0, outTok: 0, cached: 0, cost: 0,          isLocal: true,  color: '#64748b' },
    { name: 'Validation',                       icon: CheckCircle, dur: job.stage_validate_s,  calls: 0, inTok: 0, outTok: 0, cached: 0, cost: 0,          isLocal: true,  color: '#64748b' },
  ];

  const mostExpensive = stages.reduce((a, b) => a.cost > b.cost ? a : b);
  const highCostStages = stages.filter(s => totalApiCost > 0 && s.cost / totalApiCost > 0.30);

  return (
    <div className="p-4 space-y-4 bg-muted/30 rounded-b-lg border-t">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground border-b">
              {['Stage','Duration','API Calls','Tokens In','Tokens Out','Cached','Cost (USD)','% of total'].map(h => (
                <th key={h} className={`py-1 pr-3 font-medium ${h === 'Stage' ? 'text-left' : 'text-right'}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stages.map(s => {
              const pct = totalApiCost > 0 ? Math.round((s.cost / totalApiCost) * 100) : 0;
              const isMostExp = s.name === mostExpensive.name && s.cost > 0;
              return (
                <tr key={s.name} className={`border-b border-border/40 ${isMostExp ? 'bg-amber-50 dark:bg-amber-950/20' : ''}`}>
                  <td className="py-1.5 pr-3 flex items-center gap-1.5">
                    <s.icon className="h-3 w-3 shrink-0" style={{ color: s.color }} />
                    <span className={isMostExp ? 'font-semibold' : ''}>{s.name}</span>
                    {isMostExp && <Badge variant="outline" className="ml-1 text-[9px] py-0 px-1 text-amber-600 border-amber-300">Most expensive</Badge>}
                  </td>
                  <td className="text-right py-1.5 pr-3 font-mono">{s.dur > 0 ? fmtSec(s.dur) : '—'}</td>
                  <td className="text-right py-1.5 pr-3 font-mono">
                    {s.isLocal ? <span className="text-muted-foreground text-[10px]">local</span> : s.calls}
                  </td>
                  <td className="text-right py-1.5 pr-3 font-mono">{s.inTok ? fmtNum(s.inTok) : '—'}</td>
                  <td className="text-right py-1.5 pr-3 font-mono">{s.outTok ? fmtNum(s.outTok) : '—'}</td>
                  <td className="text-right py-1.5 pr-3 font-mono">{s.cached ? fmtNum(s.cached) : '—'}</td>
                  <td className="text-right py-1.5 pr-3 font-mono font-medium">{fmtUsd(s.cost)}</td>
                  <td className="text-right py-1.5">
                    {pct > 0 ? (
                      <div className="flex items-center justify-end gap-1">
                        <div className="w-12 bg-muted rounded-full h-1.5">
                          <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, backgroundColor: s.color }} />
                        </div>
                        <span className="font-mono w-8">{pct}%</span>
                      </div>
                    ) : <span className="text-muted-foreground">—</span>}
                  </td>
                </tr>
              );
            })}
            <tr className="font-semibold border-t-2">
              <td className="py-1.5 pr-3">Total API Cost</td>
              <td className="text-right py-1.5 pr-3 font-mono">{fmtSec(job.duration_secs)}</td>
              <td className="text-right py-1.5 pr-3 font-mono">{job.api_calls_translate + job.api_calls_review}</td>
              <td className="text-right py-1.5 pr-3 font-mono">{fmtNum(job.input_tokens)}</td>
              <td className="text-right py-1.5 pr-3 font-mono">{fmtNum(job.output_tokens)}</td>
              <td className="text-right py-1.5 pr-3 font-mono">{fmtNum((job.translate_cached_tokens || 0) + (job.review_cached_tokens || 0))}</td>
              <td className="text-right py-1.5 pr-3 font-mono text-primary">{fmtUsd(totalApiCost)}</td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>

      {/* Savings */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        {(() => {
          const memHits = job.memory_hits || 0;
          const nonCached = Math.max(job.segments_total - memHits, 0);
          const avgSeg = nonCached > 0 ? translateCost / nonCached : 0;
          const memSav = memHits * avgSeg;
          const pin = MODEL_PRICES['gpt-4o-mini'][0] / 1_000_000;
          const cacheSav = ((job.translate_cached_tokens || 0) + (job.review_cached_tokens || 0)) * 0.5 * pin;
          const skipped = Math.max((job.segments_total || 0) - (job.segments_reviewed || 0), 0);
          const avgRevSeg = job.segments_reviewed > 0 ? reviewCost / job.segments_reviewed : 0;
          const revSav = skipped * avgRevSeg;
          return [
            { label: 'Translation Memory saved', val: memSav, sub: `${memHits} segments from cache` },
            { label: 'Prompt cache saved', val: cacheSav, sub: `${fmtNum((job.translate_cached_tokens || 0) + (job.review_cached_tokens || 0))} cached tokens` },
            { label: 'Review skipping saved', val: revSav, sub: `${skipped} segments skipped` },
          ].map(s => (
            <div key={s.label} className="bg-green-50 dark:bg-green-950/20 rounded p-2 border border-green-200 dark:border-green-800">
              <div className="text-muted-foreground mb-0.5">{s.label}</div>
              <div className="font-bold text-green-700 dark:text-green-400">{fmtUsd(s.val)}</div>
              <div className="text-muted-foreground">{s.sub}</div>
            </div>
          ));
        })()}
      </div>

      {/* Optimization hints */}
      {highCostStages.map(s => {
        const pct = Math.round((s.cost / totalApiCost) * 100);
        const tips = s.name.includes('Engineering Review')
          ? ['Reduce review batch size or increase the technical-classifier threshold', 'Build translation memory to increase cache hit rate (reviewed segs are cheaper on repeat)']
          : ['Build translation memory — repeated documents cost near $0 after the first run', 'Glossary entries resolve common segments without an API call'];
        return (
          <div key={s.name} className="flex gap-2 p-2 bg-amber-50 dark:bg-amber-950/20 rounded border border-amber-200 dark:border-amber-800 text-xs">
            <Lightbulb className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-amber-700 dark:text-amber-400 mb-1">
                Optimization: {s.name} used {pct}% of total cost
              </div>
              <ul className="space-y-0.5 text-muted-foreground list-disc ml-3">
                {tips.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Job row ───────────────────────────────────────────────────────────────────

function JobRow({ job }: { job: UsageJob }) {
  const [open, setOpen] = useState(false);
  const translateCost = modelCost(job.translate_in_tokens, job.translate_out_tokens, job.model || 'gpt-4o-mini');
  const reviewCost    = modelCost(job.review_in_tokens, job.review_out_tokens, 'gpt-4o');
  const totalCost     = translateCost + reviewCost;
  const memPct = job.segments_total > 0 ? Math.round((job.memory_hits / job.segments_total) * 100) : 0;

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center gap-3 p-3 hover:bg-muted/40 text-left transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm truncate">{job.project_name || 'Untitled'}</span>
            <Badge variant="outline" className="text-[10px] py-0 px-1.5 uppercase">{job.file_type}</Badge>
            <Badge variant={job.status === 'complete' ? 'default' : 'destructive'} className="text-[10px] py-0 px-1.5">
              {job.status}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-3 flex-wrap">
            <span>{fmtDate(job.created_at)}</span>
            <span>{job.segments_total} segs</span>
            {memPct > 0 && <span className="text-green-600">{memPct}% from memory</span>}
            <span className="font-mono text-[10px]">{job.model || '—'}</span>
          </div>
        </div>
        <div className="flex items-center gap-4 shrink-0 text-right">
          <div>
            <div className="font-mono font-bold text-sm">{fmtUsd4(totalCost)}</div>
            <div className="text-xs text-muted-foreground">{fmtSec(job.duration_secs)}</div>
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>
      {open && <StageCostBreakdown job={job} />}
    </div>
  );
}

// ─── Spending chart ────────────────────────────────────────────────────────────

function SpendingChart({ data }: { data: ChartPoint[] }) {
  if (!data.length) return <p className="text-sm text-muted-foreground text-center py-8">No data for this period</p>;
  const maxCost = Math.max(...data.map(d => d.cost), 0.0001);
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} />
        <YAxis tickFormatter={v => `$${v.toFixed(3)}`} tick={{ fontSize: 10 }} width={62} />
        <Tooltip formatter={(v: number) => [fmtUsd4(v), 'Cost']} labelClassName="font-medium" />
        <Bar dataKey="cost" radius={[3, 3, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.cost === maxCost ? '#6366f1' : '#94a3b8'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ─── Sort button ───────────────────────────────────────────────────────────────

function SortBtn({ label, sortKey, current, order, onSort }: {
  label: string; sortKey: SortKey; current: SortKey; order: 'asc' | 'desc';
  onSort: (k: SortKey) => void;
}) {
  const active = current === sortKey;
  return (
    <button
      onClick={() => onSort(sortKey)}
      className={`flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors
        ${active ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-muted'}`}
    >
      {label}
      {active
        ? (order === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)
        : <ArrowUpDown className="h-3 w-3 opacity-40" />}
    </button>
  );
}

// ─── Profitability tab ─────────────────────────────────────────────────────────

function ProfitabilityTab({
  data, markupPct, onMarkupChange, isAdmin, onSaveMarkup, profitPage, onPageChange,
}: {
  data: ProfitData | null;
  markupPct: number;
  onMarkupChange: (v: number) => void;
  isAdmin: boolean;
  onSaveMarkup: (v: number) => void;
  profitPage: number;
  onPageChange: (p: number) => void;
}) {
  const [markupInput, setMarkupInput] = useState(String(markupPct));
  const [savingMarkup, setSavingMarkup] = useState(false);

  useEffect(() => { setMarkupInput(String(markupPct)); }, [markupPct]);

  const applyMarkup = () => {
    const v = parseFloat(markupInput);
    if (!isNaN(v) && v >= 0) onMarkupChange(v);
  };

  const saveDefault = async () => {
    const v = parseFloat(markupInput);
    if (isNaN(v) || v < 0) return;
    setSavingMarkup(true);
    try { await onSaveMarkup(v); } finally { setSavingMarkup(false); }
  };

  const sum = data?.summary;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground">Markup %</label>
          <Input
            className="h-7 w-20 text-xs"
            type="number"
            min="0"
            value={markupInput}
            onChange={e => setMarkupInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyMarkup()}
          />
          <Button size="sm" className="h-7 text-xs" onClick={applyMarkup}>Apply</Button>
        </div>
        {isAdmin && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs gap-1"
            onClick={saveDefault}
            disabled={savingMarkup}
          >
            <Settings className="h-3 w-3" />
            {savingMarkup ? 'Saving…' : 'Save as default'}
          </Button>
        )}
        {sum && (
          <div className="ml-auto flex items-center gap-4 text-xs text-muted-foreground">
            <span>Cost: <span className="font-mono text-foreground">{fmtUsd2(sum.total_cost_usd)}</span></span>
            <span>Revenue: <span className="font-mono text-emerald-600">{fmtUsd2(sum.total_revenue_usd)}</span></span>
            <span>Gross profit: <span className="font-mono text-emerald-600 font-bold">{fmtUsd2(sum.total_profit_usd)}</span></span>
            <span>Avg margin: <span className="font-mono text-primary font-bold">{sum.avg_margin_pct.toFixed(1)}%</span></span>
          </div>
        )}
      </div>

      {/* Summary cards */}
      {sum && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Total API Cost', val: fmtUsd2(sum.total_cost_usd),      color: 'text-slate-700 dark:text-slate-300' },
            { label: 'Total Revenue',  val: fmtUsd2(sum.total_revenue_usd),   color: 'text-blue-600' },
            { label: 'Gross Profit',   val: fmtUsd2(sum.total_profit_usd),    color: 'text-emerald-600' },
            { label: 'Avg Margin',     val: `${sum.avg_margin_pct.toFixed(1)}%`, color: 'text-violet-600' },
          ].map(c => (
            <Card key={c.label}>
              <CardContent className="pt-3 pb-3 text-center">
                <p className="text-xs text-muted-foreground">{c.label}</p>
                <p className={`text-xl font-bold font-mono mt-0.5 ${c.color}`}>{c.val}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Table */}
      {!data ? (
        <div className="text-center py-8 text-muted-foreground text-sm">Loading…</div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-muted/50 text-muted-foreground">
                  {['Project','Date','Type','Segments','Actual Cost','Markup %','Sell Price','Gross Profit','Margin'].map(h => (
                    <th key={h} className={`px-3 py-2 font-medium ${h === 'Project' ? 'text-left' : 'text-right'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.jobs.map((j, i) => (
                  <tr key={j.job_id} className={`border-t border-border/40 ${i % 2 === 0 ? '' : 'bg-muted/20'}`}>
                    <td className="px-3 py-2 font-medium max-w-[180px] truncate">{j.project_name}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{j.created_at ? fmtDate(j.created_at) : '—'}</td>
                    <td className="px-3 py-2 text-right"><Badge variant="outline" className="text-[9px] py-0 px-1 uppercase">{j.file_type}</Badge></td>
                    <td className="px-3 py-2 text-right font-mono">{fmtNum(j.segments_total)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmtUsd(j.actual_cost_usd)}</td>
                    <td className="px-3 py-2 text-right font-mono">{j.markup_pct.toFixed(1)}%</td>
                    <td className="px-3 py-2 text-right font-mono text-blue-600">{fmtUsd4(j.selling_price_usd)}</td>
                    <td className="px-3 py-2 text-right font-mono font-bold text-emerald-600">{fmtUsd4(j.gross_profit_usd)}</td>
                    <td className="px-3 py-2 text-right">
                      <span className={`font-mono font-bold ${j.margin_pct >= 30 ? 'text-emerald-600' : 'text-amber-600'}`}>
                        {j.margin_pct.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.pages > 1 && (
            <div className="flex items-center justify-between px-3 py-2 border-t text-xs text-muted-foreground">
              <span>Page {data.page} of {data.pages} ({fmtNum(data.total)} jobs)</span>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" className="h-6 px-2 text-xs" disabled={profitPage <= 1} onClick={() => onPageChange(profitPage - 1)}>←</Button>
                <Button size="sm" variant="outline" className="h-6 px-2 text-xs" disabled={profitPage >= data.pages} onClick={() => onPageChange(profitPage + 1)}>→</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Export dropdown ───────────────────────────────────────────────────────────

function ExportDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const download = (fmt: string) => {
    window.location.href = `${BASE}/api/translation/cost/export?format=${fmt}`;
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setOpen(o => !o)}>
        <Download className="h-3.5 w-3.5" />
        Export
        <ChevronDown className="h-3 w-3 opacity-60" />
      </Button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-40 rounded-md border bg-popover shadow-lg z-50">
          {[
            { fmt: 'xlsx', label: 'Excel (.xlsx)', icon: '📊' },
            { fmt: 'pdf',  label: 'PDF Report',   icon: '📄' },
            { fmt: 'csv',  label: 'CSV Data',      icon: '📋' },
          ].map(opt => (
            <button
              key={opt.fmt}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left"
              onClick={() => download(opt.fmt)}
            >
              <span>{opt.icon}</span>
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

export default function TranslationCostPage() {
  const [, navigate] = useLocation();

  // Data state
  const [budget, setBudget]         = useState<BudgetStatus | null>(null);
  const [forecast, setForecast]     = useState<ForecastData | null>(null);
  const [live, setLive]             = useState<LiveMetrics | null>(null);
  const [charts, setCharts]         = useState<ChartData | null>(null);
  const [history, setHistory]       = useState<HistoryData | null>(null);
  const [top20, setTop20]           = useState<Top20Job[]>([]);
  const [profitData, setProfitData] = useState<ProfitData | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  // UI state
  const [loading, setLoading]       = useState(true);
  const [liveLoading, setLiveLoading] = useState(false);
  const [error, setError]           = useState('');
  const [sort, setSort]             = useState<SortKey>('created_at');
  const [order, setOrder]           = useState<'asc' | 'desc'>('desc');
  const [histPage, setHistPage]     = useState(1);
  const [profitPage, setProfitPage] = useState(1);
  const [markupPct, setMarkupPct]   = useState(40);
  const debouncedMarkup = useDebounce(markupPct, 500);

  // ── Fetchers ────────────────────────────────────────────────────────────────

  const fetchStatic = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [budRes, fcastRes, chartsRes, histRes, top20Res] = await Promise.all([
        fetch(`${BASE}/api/translation/cost/budget`, { credentials: 'include' }),
        fetch(`${BASE}/api/translation/cost/forecast`, { credentials: 'include' }),
        fetch(`${BASE}/api/translation/cost/charts`, { credentials: 'include' }),
        fetch(`${BASE}/api/translation/cost/history?page=${histPage}&sort=${sort}&order=${order}&limit=50`, { credentials: 'include' }),
        fetch(`${BASE}/api/translation/cost/top20`, { credentials: 'include' }),
      ]);

      if (!chartsRes.ok) { setError(`Failed to load data (${chartsRes.status})`); return; }

      const [bud, fcast, ch, hist, t20] = await Promise.all([
        budRes.ok   ? budRes.json()   : null,
        fcastRes.ok ? fcastRes.json() : null,
        chartsRes.json(),
        histRes.ok  ? histRes.json()  : null,
        top20Res.ok ? top20Res.json() : null,
      ]);

      if (bud)   setBudget(bud);
      if (fcast) setForecast(fcast);
      setCharts(ch);
      if (hist)  setHistory(hist);
      if (t20)   setTop20(t20.jobs || []);
      if (bud?.default_markup_pct) setMarkupPct(bud.default_markup_pct);
    } catch {
      setError('Failed to fetch dashboard data');
    } finally {
      setLoading(false);
    }
  }, [histPage, sort, order]);

  const fetchLive = useCallback(async () => {
    setLiveLoading(true);
    try {
      const res = await fetch(`${BASE}/api/translation/cost/live`, { credentials: 'include' });
      if (res.ok) { setLive(await res.json()); setLastRefresh(new Date()); }
    } finally { setLiveLoading(false); }
  }, []);

  const fetchProfitability = useCallback(async () => {
    try {
      const res = await fetch(
        `${BASE}/api/translation/cost/profitability?markup_pct=${debouncedMarkup}&page=${profitPage}&limit=50`,
        { credentials: 'include' },
      );
      if (res.ok) setProfitData(await res.json());
    } catch {}
  }, [debouncedMarkup, profitPage]);

  useEffect(() => { fetchStatic(); }, [fetchStatic]);
  useEffect(() => { fetchLive(); }, [fetchLive]);
  useEffect(() => { fetchProfitability(); }, [fetchProfitability]);

  // 30-second live metrics refresh
  useEffect(() => {
    const interval = setInterval(fetchLive, 30_000);
    return () => clearInterval(interval);
  }, [fetchLive]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleSort = (k: SortKey) => {
    if (k === sort) setOrder(o => o === 'desc' ? 'asc' : 'desc');
    else { setSort(k); setOrder('desc'); }
    setHistPage(1);
  };

  const handleSaveBudget = async (val: number) => {
    await fetch(`${BASE}/api/translation/cost/budget`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget_usd: val }),
    });
    fetchStatic();
  };

  const handleSaveMarkup = async (val: number) => {
    await fetch(`${BASE}/api/translation/cost/markup`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markup_pct: val }),
    });
    setMarkupPct(val);
  };

  const isAdmin = budget?.is_admin ?? false;
  const sum = charts?.summary;

  return (
    <div className="min-h-screen bg-background">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="border-b bg-card/50 sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate('/translation')} className="text-muted-foreground hover:text-foreground text-sm">
              ← Translation Studio
            </button>
            <span className="text-muted-foreground">/</span>
            <div className="flex items-center gap-2">
              <BarChart2 className="h-5 w-5 text-primary" />
              <h1 className="font-semibold text-lg">Financial Analytics</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ExportDropdown />
            <Button variant="outline" size="sm" onClick={() => { fetchStatic(); fetchLive(); }} disabled={loading}>
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      {/* ── Budget Bar (sticky below header) ─────────────────────────────── */}
      <div className="sticky top-[57px] z-10">
        <BudgetBar budget={budget} isAdmin={isAdmin} onSaveBudget={handleSaveBudget} />
      </div>

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
        {error && (
          <div className="flex gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded text-sm text-destructive">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" /> {error}
          </div>
        )}

        {/* ── Live Metrics Strip ─────────────────────────────────────────── */}
        <LiveMetricsStrip data={live} lastRefresh={lastRefresh} />

        {/* ── Forecast cards ─────────────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">Cost Prediction (This Month)</h2>
          </div>
          <ForecastPanel data={forecast} />
        </div>

        {/* ── Period summary cards ───────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Today',     cost: sum?.today_cost ?? 0, jobs: sum?.today_jobs ?? 0, icon: DollarSign, accent: 'bg-blue-100 text-blue-600 dark:bg-blue-900/40' },
            { label: 'This Week', cost: sum?.week_cost  ?? 0, jobs: sum?.week_jobs  ?? 0, icon: Clock,       accent: 'bg-violet-100 text-violet-600 dark:bg-violet-900/40' },
            { label: 'This Month',cost: sum?.month_cost ?? 0, jobs: sum?.month_jobs ?? 0, icon: PieChart,    accent: 'bg-amber-100 text-amber-600 dark:bg-amber-900/40' },
            { label: 'All Time',  cost: sum?.all_cost   ?? 0, jobs: sum?.all_jobs   ?? 0, icon: BarChart2,   accent: 'bg-slate-100 text-slate-600 dark:bg-slate-800' },
          ].map(c => (
            <Card key={c.label}>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground font-medium">{c.label}</p>
                    <p className="text-2xl font-bold font-mono mt-0.5">{fmtUsd2(c.cost)}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{c.jobs} job{c.jobs !== 1 ? 's' : ''}</p>
                  </div>
                  <div className={`p-2 rounded-full ${c.accent}`}>
                    <c.icon className="h-4 w-4" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* ── Main tabs ─────────────────────────────────────────────────── */}
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview & Charts</TabsTrigger>
            <TabsTrigger value="history">Job History ({history?.total ?? '…'})</TabsTrigger>
            <TabsTrigger value="profitability">
              <Users className="h-3.5 w-3.5 mr-1" />
              Profitability
            </TabsTrigger>
            <TabsTrigger value="top20">Top 20</TabsTrigger>
          </TabsList>

          {/* ── Overview tab ──────────────────────────────────────────────── */}
          <TabsContent value="overview" className="space-y-5 mt-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">API Spending Over Time</CardTitle>
              </CardHeader>
              <CardContent>
                <Tabs defaultValue="daily">
                  <TabsList className="mb-3 h-7">
                    <TabsTrigger value="daily"   className="text-xs h-6 px-2">Daily (30d)</TabsTrigger>
                    <TabsTrigger value="weekly"  className="text-xs h-6 px-2">Weekly (12w)</TabsTrigger>
                    <TabsTrigger value="monthly" className="text-xs h-6 px-2">Monthly (12m)</TabsTrigger>
                  </TabsList>
                  <TabsContent value="daily"><SpendingChart data={charts?.daily ?? []} /></TabsContent>
                  <TabsContent value="weekly"><SpendingChart data={charts?.weekly ?? []} /></TabsContent>
                  <TabsContent value="monthly"><SpendingChart data={charts?.monthly ?? []} /></TabsContent>
                </Tabs>
              </CardContent>
            </Card>

            {/* Average cost metrics */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Avg cost / file',      value: fmtUsd4(charts?.avg_cost_per_file ?? 0) },
                { label: 'Avg cost / page',      value: fmtUsd4(charts?.avg_cost_per_page ?? 0) },
                { label: 'Avg cost / 1000 words',value: fmtUsd4(charts?.avg_cost_per_1k_words ?? 0) },
              ].map(m => (
                <Card key={m.label}>
                  <CardContent className="pt-4 pb-3 text-center">
                    <p className="text-xs text-muted-foreground">{m.label}</p>
                    <p className="text-xl font-bold font-mono mt-1">{m.value}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Savings summary */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingDown className="h-4 w-4 text-green-500" />
                  Total Savings (All Time)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  {[
                    { label: 'Translation Memory', val: charts?.total_memory_savings ?? 0, sub: 'saved by cached segments' },
                    { label: 'OpenAI Prompt Cache', val: charts?.total_cached_savings ?? 0, sub: '50% discount on cached tokens' },
                    { label: 'Review Skipping', val: charts?.total_review_savings ?? 0, sub: 'general segments skipped' },
                  ].map(s => (
                    <div key={s.label}>
                      <p className="text-muted-foreground text-xs">{s.label}</p>
                      <p className="font-bold font-mono text-green-600 text-lg">{fmtUsd2(s.val)}</p>
                      <p className="text-xs text-muted-foreground">{s.sub}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── History tab ───────────────────────────────────────────────── */}
          <TabsContent value="history" className="mt-4 space-y-4">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-muted-foreground mr-1">Sort by:</span>
              <SortBtn label="Date"     sortKey="created_at"    current={sort} order={order} onSort={handleSort} />
              <SortBtn label="Cost"     sortKey="total_cost_usd" current={sort} order={order} onSort={handleSort} />
              <SortBtn label="File"     sortKey="project_name"  current={sort} order={order} onSort={handleSort} />
              <SortBtn label="Duration" sortKey="duration_secs" current={sort} order={order} onSort={handleSort} />
              <SortBtn label="Tokens"   sortKey="input_tokens"  current={sort} order={order} onSort={handleSort} />
            </div>

            {loading ? (
              <div className="space-y-2">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
                ))}
              </div>
            ) : !history?.jobs.length ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <BarChart2 className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground">No translation jobs found</p>
                </CardContent>
              </Card>
            ) : (
              <>
                <div className="space-y-2">
                  {history.jobs.map(j => <JobRow key={j.id} job={j} />)}
                </div>

                {history.pages > 1 && (
                  <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
                    <span>Page {history.page} of {history.pages} ({fmtNum(history.total)} jobs)</span>
                    <div className="flex gap-1">
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                        disabled={histPage <= 1} onClick={() => setHistPage(p => p - 1)}>← Prev</Button>
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                        disabled={histPage >= history.pages} onClick={() => setHistPage(p => p + 1)}>Next →</Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </TabsContent>

          {/* ── Profitability tab ─────────────────────────────────────────── */}
          <TabsContent value="profitability" className="mt-4">
            <ProfitabilityTab
              data={profitData}
              markupPct={markupPct}
              onMarkupChange={v => { setMarkupPct(v); setProfitPage(1); }}
              isAdmin={isAdmin}
              onSaveMarkup={handleSaveMarkup}
              profitPage={profitPage}
              onPageChange={setProfitPage}
            />
          </TabsContent>

          {/* ── Top 20 tab ────────────────────────────────────────────────── */}
          <TabsContent value="top20" className="mt-4">
            <Top20Table jobs={top20} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
