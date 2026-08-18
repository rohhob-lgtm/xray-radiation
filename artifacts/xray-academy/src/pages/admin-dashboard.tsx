import { useEffect, useState, useCallback } from 'react';
import { Users, FileText, DollarSign, ShieldCheck, RefreshCw, Loader2 } from 'lucide-react';

// Simple one-glance admin dashboard: visitors, translations, and cost vs the
// daily/monthly caps. Reads GET /api/translation/admin/dashboard (admin-only).

interface Dash {
  visitors: { today: number; total: number };
  translations: { today: number; month: number; total: number };
  cost: {
    today_usd: number; month_usd: number;
    daily_cap_usd: number; monthly_cap_usd: number;
    daily_pct: number; monthly_pct: number;
    daily_cap_active: boolean; monthly_cap_active: boolean;
    translation_enabled: boolean;
  };
  active_jobs: number;
}

function Bar({ pct }: { pct: number }) {
  const p = Math.max(0, Math.min(100, pct));
  const color = p < 60 ? 'bg-emerald-500' : p < 85 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
      <div className={`h-full ${color} transition-all`} style={{ width: `${p}%` }} />
    </div>
  );
}

export default function AdminDashboardPage() {
  const [data, setData] = useState<Dash | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetch('/api/translation/admin/dashboard', { credentials: 'include' })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 403 ? 'غير مصرّح — سجّلي الدخول كأدمن أولاً' : `خطأ ${r.status}`);
        return r.json();
      })
      .then((d) => { setData(d); setErr(null); })
      .catch((e) => setErr(e.message || 'تعذّر التحميل'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const money = (v: number) => `$${Number(v ?? 0).toFixed(2)}`;

  return (
    <div dir="rtl" className="mx-auto max-w-4xl p-4 md:p-8 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">لوحة المعلومات</h1>
          <p className="text-sm text-muted-foreground">نظرة سريعة على الزوّار والترجمات والتكلفة</p>
        </div>
        <button
          onClick={load}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium hover:bg-muted"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          تحديث
        </button>
      </div>

      {err && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">{err}</div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Visitors */}
            <div className="rounded-2xl border border-border bg-card p-5 space-y-2">
              <div className="flex items-center gap-2 text-primary">
                <Users className="h-5 w-5" />
                <span className="text-sm font-semibold text-foreground">الزوّار</span>
              </div>
              <p className="text-4xl font-bold text-foreground">{data.visitors.today.toLocaleString()}</p>
              <p className="text-xs text-muted-foreground">اليوم · الإجمالي {data.visitors.total.toLocaleString()}</p>
            </div>

            {/* Translations */}
            <div className="rounded-2xl border border-border bg-card p-5 space-y-2">
              <div className="flex items-center gap-2 text-primary">
                <FileText className="h-5 w-5" />
                <span className="text-sm font-semibold text-foreground">الترجمات</span>
              </div>
              <p className="text-4xl font-bold text-foreground">{data.translations.today.toLocaleString()}</p>
              <p className="text-xs text-muted-foreground">
                اليوم · الشهر {data.translations.month.toLocaleString()} · الإجمالي {data.translations.total.toLocaleString()}
              </p>
            </div>

            {/* Cost today */}
            <div className="rounded-2xl border border-border bg-card p-5 space-y-2">
              <div className="flex items-center gap-2 text-primary">
                <DollarSign className="h-5 w-5" />
                <span className="text-sm font-semibold text-foreground">تكلفة اليوم</span>
              </div>
              <p className="text-4xl font-bold text-foreground">{money(data.cost.today_usd)}</p>
              <p className="text-xs text-muted-foreground">من سقف {money(data.cost.daily_cap_usd)} ({data.cost.daily_pct}%)</p>
              <Bar pct={data.cost.daily_pct} />
            </div>
          </div>

          {/* Monthly cost */}
          <div className="rounded-2xl border border-border bg-card p-5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-foreground">تكلفة الشهر</span>
              <span className="text-sm font-mono text-muted-foreground">
                {money(data.cost.month_usd)} / {money(data.cost.monthly_cap_usd)} ({data.cost.monthly_pct}%)
              </span>
            </div>
            <Bar pct={data.cost.monthly_pct} />
          </div>

          {/* Protection status */}
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5">
            <div className="flex items-start gap-3">
              <ShieldCheck className="h-6 w-6 text-emerald-400 shrink-0" />
              <div className="text-sm space-y-1">
                <p className="font-semibold text-foreground">الحماية المالية مفعّلة</p>
                <p className="text-muted-foreground">
                  تتوقّف الترجمة تلقائياً عند بلوغ السقف اليومي (<span className="font-mono">{money(data.cost.daily_cap_usd)}</span>){' '}
                  {data.cost.daily_cap_active ? '✅' : '⚠️ (غير مفعّل)'} أو الشهري (
                  <span className="font-mono">{money(data.cost.monthly_cap_usd)}</span>){' '}
                  {data.cost.monthly_cap_active ? '✅' : '⚠️ (غير مفعّل)'} — فلا تتجاوز التكلفة هذه الحدود.
                </p>
                <p className="text-xs text-muted-foreground/70">
                  الترجمة {data.cost.translation_enabled ? 'مُفعّلة' : 'متوقّفة'} · العمليات النشطة الآن: {data.active_jobs}
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
