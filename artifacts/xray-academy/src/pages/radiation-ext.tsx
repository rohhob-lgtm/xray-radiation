/**
 * Extended section components for Radiation Sources & Accelerator Engineering platform.
 * These are imported by radiation-sources.tsx and rendered via SectionContent().
 */
import { useState, useEffect, useRef, useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Search, ExternalLink, Building2, ChevronDown, ChevronUp,
  BookOpen, FlaskConical, Calculator, Wrench, Globe,
  AlertTriangle, CheckCircle2, XCircle, Info, Play, Pause,
  GraduationCap, BarChart2, Zap, Atom, Shield, Cpu, Activity,
  ArrowRight, Clock, Users, Star, Filter, RotateCcw,
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid, LineChart, Line, ReferenceLine } from 'recharts';
import {
  MANUFACTURERS, EQUIPMENT_DB, FAULT_DB, STANDARDS_DB, LEARNING_PATHS,
  type Manufacturer, type Equipment, type FaultRecord, type StandardRecord,
} from '@/data/radiation-ext';

// ─── Shared UI helpers (mirrors radiation-sources.tsx) ───────────────────────
function ContentBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card/40 p-5 space-y-3">
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
      <div className="text-sm text-muted-foreground leading-relaxed space-y-2">{children}</div>
    </div>
  );
}

function AlertBox({ type, children }: { type: 'warning' | 'info' | 'danger'; children: React.ReactNode }) {
  const cfg = {
    warning: { bg: 'bg-amber-500/10 border-amber-500/30', icon: AlertTriangle, color: 'text-amber-400' },
    info:    { bg: 'bg-blue-500/10 border-blue-500/30',   icon: Info,           color: 'text-blue-400' },
    danger:  { bg: 'bg-red-500/10 border-red-500/30',     icon: AlertTriangle,  color: 'text-red-400' },
  }[type];
  const Icon = cfg.icon;
  return (
    <div className={`flex gap-2.5 rounded-lg border p-3.5 text-sm ${cfg.bg}`}>
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${cfg.color}`} />
      <span className="text-foreground/80 leading-relaxed">{children}</span>
    </div>
  );
}

const SEVERITY_CFG: Record<string, { color: string; bg: string }> = {
  Critical: { color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/30' },
  High:     { color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30' },
  Medium:   { color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/30' },
  Low:      { color: 'text-green-400',  bg: 'bg-green-500/10 border-green-500/30' },
};

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
export function DashboardSection({ onNavigate }: { onNavigate?: (id: string) => void }) {
  const stats = [
    { label: 'Source Types', value: '13', icon: Atom, color: 'text-purple-400', bg: 'bg-purple-500/10' },
    { label: 'Manufacturers', value: '20+', icon: Building2, color: 'text-blue-400', bg: 'bg-blue-500/10' },
    { label: 'Equipment Items', value: '15+', icon: Cpu, color: 'text-violet-400', bg: 'bg-violet-500/10' },
    { label: 'Calculators', value: '10+', icon: Calculator, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    { label: 'Fault Records', value: '11', icon: Wrench, color: 'text-orange-400', bg: 'bg-orange-500/10' },
    { label: 'Standards / Refs', value: '15+', icon: BookOpen, color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
  ];

  const quickLinks = [
    { id: 'xray-tube',    label: 'X-ray Tubes',          icon: Zap,          color: 'text-blue-400',   desc: 'Tube physics, construction, maintenance' },
    { id: 'linac',        label: 'LINAC',                 icon: Cpu,          color: 'text-violet-400', desc: 'RF acceleration, medical & cargo systems' },
    { id: 'radioisotopes',label: 'Radioisotopes',         icon: Atom,         color: 'text-orange-400', desc: 'Co-60, Cs-137, Ir-192, Cf-252 and more' },
    { id: 'security',     label: 'Security Screening',    icon: Shield,       color: 'text-teal-400',   desc: 'Airport, cargo, vehicle, border inspection' },
    { id: 'manufacturers',label: 'Manufacturers',         icon: Building2,    color: 'text-sky-400',    desc: '20+ verified companies and their products' },
    { id: 'equipment-db', label: 'Equipment Database',    icon: BarChart2,    color: 'text-lime-400',   desc: 'Searchable equipment specs with comparison' },
    { id: 'calculators',  label: 'Calculators',           icon: Calculator,   color: 'text-emerald-400',desc: 'ISL, HVL, shielding, decay, unit conversion' },
    { id: 'maintenance',  label: 'Maintenance Center',    icon: Wrench,       color: 'text-amber-400',  desc: '11 detailed fault records with diagnostics' },
    { id: 'standards',    label: 'Standards Library',     icon: BookOpen,     color: 'text-cyan-400',   desc: 'IAEA, ICRP, IEC, ISO, ASTM, ANSI, NCRP' },
    { id: 'animations',   label: 'Physics Animations',    icon: Activity,     color: 'text-pink-400',   desc: 'Compton, photoelectric, bremsstrahlung' },
    { id: 'learning-paths',label: 'Learning Paths',       icon: GraduationCap,color: 'text-rose-400',  desc: 'Structured curricula for every level' },
    { id: 'virtual-lab',  label: 'Virtual Laboratory',    icon: FlaskConical, color: 'text-yellow-400', desc: 'X-ray spectrum simulator + shielding calc' },
  ];

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-6">
        <div className="flex items-start gap-4">
          <div className="h-12 w-12 rounded-xl bg-purple-500/10 flex items-center justify-center ring-1 ring-purple-500/30 shrink-0">
            <Atom className="h-6 w-6 text-purple-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold">Radiation Sources & Accelerator Engineering</h2>
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
              A comprehensive interactive platform for students, engineers, operators, trainers, and researchers.
              Covering radiation physics, accelerator technology, security screening, industrial NDT, and radiation protection.
            </p>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {['IAEA', 'ICRP', 'IEC', 'ISO', 'ASTM', 'NCRP', 'NIST', 'CERN'].map(ref => (
                <span key={ref} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-card border border-border text-muted-foreground">{ref}</span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {stats.map(s => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="rounded-xl border border-border bg-card/40 p-4 flex items-center gap-3">
              <div className={`h-9 w-9 rounded-lg ${s.bg} flex items-center justify-center shrink-0`}>
                <Icon className={`h-4.5 w-4.5 ${s.color}`} />
              </div>
              <div>
                <div className="text-xl font-bold">{s.value}</div>
                <div className="text-[11px] text-muted-foreground">{s.label}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Quick access */}
      <ContentBlock title="Quick Access — All Sections">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
          {quickLinks.map(link => {
            const Icon = link.icon;
            return (
              <button key={link.id}
                onClick={() => onNavigate?.(link.id)}
                className="flex items-center gap-3 p-3 rounded-lg border border-border bg-background/40 hover:bg-card hover:border-primary/30 transition-colors text-left group"
              >
                <div className="h-8 w-8 rounded-lg bg-card flex items-center justify-center shrink-0">
                  <Icon className={`h-4 w-4 ${link.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">{link.label}</div>
                  <div className="text-[10px] text-muted-foreground truncate">{link.desc}</div>
                </div>
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground/50 group-hover:text-primary/50 shrink-0" />
              </button>
            );
          })}
        </div>
      </ContentBlock>

      {/* Learning Paths teaser */}
      <ContentBlock title="Learning Paths">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
          {LEARNING_PATHS.map(p => (
            <div key={p.id} className="p-3 rounded-lg border border-border bg-background/30 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold">{p.title}</span>
                <Badge variant="outline" className={`text-[9px] ${p.color} border-current shrink-0`}>{p.level}</Badge>
              </div>
              <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{p.duration}</span>
                <span className="flex items-center gap-1"><Users className="h-3 w-3" />{p.targetAudience[0]}</span>
              </div>
              <p className="text-[10px] text-muted-foreground leading-relaxed">{p.description}</p>
            </div>
          ))}
        </div>
        <button
          onClick={() => onNavigate?.('learning-paths')}
          className="mt-2 text-xs text-primary hover:underline flex items-center gap-1"
        >View full Learning Paths <ArrowRight className="h-3 w-3" /></button>
      </ContentBlock>

      {/* Safety disclaimer */}
      <AlertBox type="info">
        All content on this platform is for educational and reference purposes only. Simulations are not substitutes for calibrated clinical measurements, certified dosimetry equipment, or professional radiation protection advice. Always consult the Radiation Protection Officer and applicable regulations before any work involving radiation sources.
      </AlertBox>
    </div>
  );
}

// ─── MANUFACTURERS ────────────────────────────────────────────────────────────
function ManufacturerCard({ m, expanded, onToggle }: { m: Manufacturer; expanded: boolean; onToggle: () => void }) {
  return (
    <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
      <button className="w-full flex items-start gap-3 p-4 text-left hover:bg-card/60 transition-colors" onClick={onToggle}>
        <div className="h-9 w-9 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0 ring-1 ring-blue-500/20">
          <Building2 className="h-4 w-4 text-blue-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{m.name}</span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-card border border-border text-muted-foreground">{m.country}</span>
            {m.founded && <span className="text-[10px] text-muted-foreground">est. {m.founded}</span>}
          </div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {m.categories.slice(0, 3).map(c => (
              <Badge key={c} variant="outline" className="text-[9px] px-1 py-0 h-4">{c}</Badge>
            ))}
          </div>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground mt-1 shrink-0" /> : <ChevronDown className="h-4 w-4 text-muted-foreground mt-1 shrink-0" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border/50">
          <p className="text-xs text-muted-foreground leading-relaxed pt-3">{m.summary}</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="space-y-1">
              <p className="font-semibold text-foreground/80">Key Products</p>
              <ul className="space-y-0.5">
                {m.keyProducts.map(p => <li key={p} className="text-muted-foreground flex gap-1.5"><span className="text-primary/60 shrink-0">•</span>{p}</li>)}
              </ul>
            </div>
            <div className="space-y-3">
              <div>
                <p className="font-semibold text-foreground/80 mb-1">Detector Technologies</p>
                {m.detectorTech.map(d => <div key={d} className="text-muted-foreground text-[11px]">• {d}</div>)}
              </div>
              <div>
                <p className="font-semibold text-foreground/80 mb-1">Source Technologies</p>
                {m.sourceTech.map(s => <div key={s} className="text-muted-foreground text-[11px]">• {s}</div>)}
              </div>
            </div>
          </div>

          <a href={m.website} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline">
            <Globe className="h-3.5 w-3.5" />{m.website.replace('https://', '')}
            <ExternalLink className="h-3 w-3 opacity-50" />
          </a>
        </div>
      )}
    </div>
  );
}

const MANUFACTURER_CATEGORIES = ['All', 'Security Screening', 'Cargo Inspection', 'Medical Imaging', 'Radiation Therapy', 'Industrial X-ray', 'Detector Technology', 'Radiation Monitoring', 'X-ray Tubes', 'High-Voltage Generators', 'Analytical X-ray'];

export function ManufacturersSection() {
  const [query, setQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return MANUFACTURERS.filter(m => {
      const matchCat = activeCategory === 'All' || m.categories.some(c => c.includes(activeCategory));
      const matchQ = !q || m.name.toLowerCase().includes(q) || m.country.toLowerCase().includes(q) ||
        m.categories.some(c => c.toLowerCase().includes(q)) ||
        m.keyProducts.some(p => p.toLowerCase().includes(q));
      return matchCat && matchQ;
    });
  }, [query, activeCategory]);

  return (
    <div className="space-y-5">
      <ContentBlock title="Manufacturing Companies Directory">
        <p>Verified public information for leading manufacturers of radiation sources, detection systems, X-ray equipment, accelerators, and radiation monitoring instruments. Only publicly available information is included.</p>
        <AlertBox type="info">All company information is sourced from official public websites, press releases, and product brochures. No proprietary or confidential information is included.</AlertBox>
      </ContentBlock>

      {/* Search & filter */}
      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search companies, products, technologies…"
            className="pl-9 bg-card/60 border-border text-sm" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {MANUFACTURER_CATEGORIES.map(c => (
            <button key={c} onClick={() => setActiveCategory(c)}
              className={`text-[11px] px-2 py-0.5 rounded-md border transition-colors ${activeCategory === c ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground hover:border-primary/40'}`}>
              {c}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">{filtered.length} of {MANUFACTURERS.length} companies</p>
      </div>

      {/* Company cards */}
      <div className="space-y-2">
        {filtered.map(m => (
          <ManufacturerCard key={m.id} m={m}
            expanded={expandedId === m.id}
            onToggle={() => setExpandedId(expandedId === m.id ? null : m.id)} />
        ))}
        {filtered.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">No companies match your search.</div>
        )}
      </div>
    </div>
  );
}

// ─── EQUIPMENT DATABASE ───────────────────────────────────────────────────────
const EQUIP_CATEGORIES = ['All', 'Baggage X-ray', 'Cabin Baggage CT', 'Cargo Inspection', 'Mobile Cargo Inspection', 'Industrial CT System', 'Portable Industrial X-ray', 'Security LINAC', 'Medical Radiation Therapy LINAC', 'Medical CT Scanner', 'Flat-Panel X-ray Detector', 'Radiation Portal Monitor', 'X-ray Generator / High-Voltage Power Supply'];

function EquipmentRow({ eq, selected, onSelect }: { eq: Equipment; selected: boolean; onSelect: () => void }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`rounded-xl border bg-card/40 overflow-hidden transition-colors ${selected ? 'border-primary/60' : 'border-border'}`}>
      <div className="flex items-start gap-3 p-4">
        <input type="checkbox" checked={selected} onChange={onSelect}
          className="mt-1 h-4 w-4 rounded border-border accent-primary cursor-pointer shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{eq.manufacturer}</span>
            <span className="font-bold text-sm text-primary">{eq.model}</span>
            <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">{eq.category}</Badge>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-0.5 mt-2 text-[11px] text-muted-foreground">
            <span><b className="text-foreground/70">Energy:</b> {eq.energy}</span>
            <span><b className="text-foreground/70">Source:</b> {eq.sourceType}</span>
            {eq.tunnelSize && <span><b className="text-foreground/70">Tunnel:</b> {eq.tunnelSize}</span>}
            {eq.penetration && <span><b className="text-foreground/70">Penetration:</b> {eq.penetration}</span>}
            {eq.weight && <span><b className="text-foreground/70">Weight:</b> {eq.weight}</span>}
            <span><b className="text-foreground/70">Detector:</b> {eq.detectorType.split('(')[0].trim()}</span>
          </div>
        </div>
        <button onClick={() => setExpanded(e => !e)} className="text-muted-foreground hover:text-foreground p-1 shrink-0">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border/50 pt-3 space-y-2">
          <p className="text-xs text-muted-foreground"><b className="text-foreground/80">Application:</b> {eq.application}</p>
          <div>
            <p className="text-xs font-semibold text-foreground/80 mb-1">Key Features</p>
            <ul className="space-y-0.5">
              {eq.highlights.map(h => <li key={h} className="text-[11px] text-muted-foreground flex gap-1.5"><CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0 mt-0.5" />{h}</li>)}
            </ul>
          </div>
          <a href={eq.officialLink} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <Globe className="h-3.5 w-3.5" />Official website <ExternalLink className="h-3 w-3 opacity-50" />
          </a>
        </div>
      )}
    </div>
  );
}

function ComparisonPanel({ ids }: { ids: string[] }) {
  const items = ids.map(id => EQUIPMENT_DB.find(e => e.id === id)).filter(Boolean) as Equipment[];
  if (items.length < 2) return null;

  const fields: { key: keyof Equipment; label: string }[] = [
    { key: 'manufacturer', label: 'Manufacturer' },
    { key: 'category', label: 'Category' },
    { key: 'energy', label: 'Energy' },
    { key: 'sourceType', label: 'Source' },
    { key: 'detectorType', label: 'Detector' },
    { key: 'tunnelSize', label: 'Tunnel / Opening' },
    { key: 'penetration', label: 'Penetration' },
    { key: 'weight', label: 'Weight' },
    { key: 'application', label: 'Application' },
  ];

  return (
    <div className="rounded-xl border border-primary/30 bg-primary/5 overflow-hidden">
      <div className="px-4 py-3 border-b border-primary/20 flex items-center gap-2">
        <BarChart2 className="h-4 w-4 text-primary" />
        <span className="font-semibold text-sm">Side-by-Side Comparison ({items.length} systems)</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50">
              <th className="text-left px-4 py-2 text-muted-foreground font-medium w-32 shrink-0">Specification</th>
              {items.map(e => (
                <th key={e.id} className="text-left px-4 py-2 font-semibold text-foreground min-w-[180px]">
                  {e.manufacturer}<br /><span className="text-primary">{e.model}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fields.map(f => {
              const vals = items.map(e => e[f.key] as string | undefined);
              const allSame = new Set(vals.filter(Boolean)).size <= 1;
              return (
                <tr key={f.key} className="border-b border-border/30 hover:bg-card/30">
                  <td className="px-4 py-2 text-muted-foreground font-medium">{f.label}</td>
                  {items.map(e => (
                    <td key={e.id} className={`px-4 py-2 ${!allSame && 'text-yellow-300'}`}>
                      {(e[f.key] as string) || <span className="text-muted-foreground/40">—</span>}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function EquipmentSection() {
  const [query, setQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return EQUIPMENT_DB.filter(e => {
      const matchCat = activeCategory === 'All' || e.category === activeCategory;
      const matchQ = !q || e.manufacturer.toLowerCase().includes(q) || e.model.toLowerCase().includes(q) ||
        e.category.toLowerCase().includes(q) || e.energy.toLowerCase().includes(q) ||
        e.application.toLowerCase().includes(q) || e.sourceType.toLowerCase().includes(q);
      return matchCat && matchQ;
    });
  }, [query, activeCategory]);

  const toggleSelect = (id: string) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : prev.length < 4 ? [...prev, id] : prev
    );
  };

  return (
    <div className="space-y-5">
      <ContentBlock title="Equipment & Systems Database">
        <p>Searchable database of radiation inspection and imaging systems. Select up to 4 items for side-by-side comparison. All specifications are from public product documentation.</p>
        <AlertBox type="info">Do not infer medical device approvals, regulatory certifications, or operational suitability from this database alone. Always consult current official manufacturer documentation.</AlertBox>
      </ContentBlock>

      {selectedIds.length >= 2 && <ComparisonPanel ids={selectedIds} />}

      {/* Search & filter */}
      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search manufacturer, model, technology, application…"
            className="pl-9 bg-card/60 border-border text-sm" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {['All', 'Baggage X-ray', 'Cargo Inspection', 'Industrial CT System', 'Medical Radiation Therapy LINAC', 'Medical CT Scanner', 'Radiation Portal Monitor'].map(c => (
            <button key={c} onClick={() => setActiveCategory(c)}
              className={`text-[11px] px-2 py-0.5 rounded-md border transition-colors ${activeCategory === c ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground hover:border-primary/40'}`}>
              {c}
            </button>
          ))}
        </div>
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{filtered.length} of {EQUIPMENT_DB.length} systems</span>
          {selectedIds.length > 0 && (
            <span className="flex items-center gap-2">
              <span className="text-primary">{selectedIds.length} selected for comparison</span>
              {selectedIds.length > 0 && <button onClick={() => setSelectedIds([])} className="text-muted-foreground hover:text-foreground"><XCircle className="h-3.5 w-3.5" /></button>}
            </span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {filtered.map(eq => (
          <EquipmentRow key={eq.id} eq={eq}
            selected={selectedIds.includes(eq.id)}
            onSelect={() => toggleSelect(eq.id)} />
        ))}
        {filtered.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">No equipment matches your search.</div>
        )}
      </div>
      {selectedIds.length === 4 && (
        <AlertBox type="info">Maximum 4 systems selected for comparison. Deselect one to add another.</AlertBox>
      )}
    </div>
  );
}

// ─── CALCULATORS HUB ─────────────────────────────────────────────────────────
function HvlCalc() {
  const materials = [
    { id: 'pb',   label: 'Lead (Pb)',    mu50: 8.04, mu100: 5.4, mu500: 1.7,  mu1000: 0.77, mu3000: 0.47 },
    { id: 'fe',   label: 'Steel (Fe)',   mu50: 2.82, mu100: 1.96,mu500: 0.60, mu1000: 0.40, mu3000: 0.29 },
    { id: 'conc', label: 'Concrete',     mu50: 0.83, mu100: 0.59,mu500: 0.20, mu1000: 0.14, mu3000: 0.10 },
    { id: 'water',label: 'Water',        mu50: 0.22, mu100: 0.17,mu500: 0.10, mu1000: 0.07, mu3000: 0.05 },
    { id: 'al',   label: 'Aluminium',    mu50: 0.39, mu100: 0.16,mu500: 0.08, mu1000: 0.06, mu3000: 0.05 },
  ];
  const energies = [
    { label: '50 keV',  key: 'mu50' },
    { label: '100 keV', key: 'mu100' },
    { label: '500 keV', key: 'mu500' },
    { label: '1 MeV',   key: 'mu1000' },
    { label: '3 MeV',   key: 'mu3000' },
  ];
  const [matId, setMatId] = useState('pb');
  const [energyKey, setEnergyKey] = useState('mu100');

  const mat = materials.find(m => m.id === matId)!;
  const mu = (mat as any)[energyKey] as number;
  const hvl = Math.log(2) / mu;    // cm
  const tvl = Math.log(10) / mu;   // cm

  const chartData = Array.from({ length: 20 }, (_, i) => {
    const x = (i / 19) * tvl * 2.5;
    return { x: +x.toFixed(2), transmission: +(Math.exp(-mu * x) * 100).toFixed(2) };
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Shielding Material</label>
          <select value={matId} onChange={e => setMatId(e.target.value)}
            className="w-full text-xs bg-card border border-border rounded-md px-2 py-1.5 text-foreground">
            {materials.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Photon Energy</label>
          <select value={energyKey} onChange={e => setEnergyKey(e.target.value)}
            className="w-full text-xs bg-card border border-border rounded-md px-2 py-1.5 text-foreground">
            {energies.map(e => <option key={e.key} value={e.key}>{e.label}</option>)}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        {[
          { label: 'μ (cm⁻¹)', value: mu.toFixed(3), color: 'text-blue-400' },
          { label: 'HVL (cm)', value: hvl.toFixed(2), color: 'text-emerald-400' },
          { label: 'TVL (cm)', value: tvl.toFixed(2), color: 'text-orange-400' },
        ].map(r => (
          <div key={r.label} className="rounded-lg border border-border bg-card/60 p-3">
            <div className={`text-lg font-bold font-mono ${r.color}`}>{r.value}</div>
            <div className="text-[10px] text-muted-foreground">{r.label}</div>
          </div>
        ))}
      </div>

      <div className="h-32">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
            <XAxis dataKey="x" tick={{ fontSize: 9, fill: '#94a3b8' }} label={{ value: 'Thickness (cm)', position: 'insideBottom', offset: -2, fontSize: 9, fill: '#94a3b8' }} />
            <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} unit="%" domain={[0, 100]} />
            <Tooltip formatter={(v: any) => [`${v}%`, 'Transmission']} contentStyle={{ background: '#1e293b', border: '1px solid #334155', fontSize: 11 }} />
            <Area dataKey="transmission" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.15} strokeWidth={1.5} dot={false} />
            <ReferenceLine y={50}  stroke="#10b981" strokeDasharray="4 2" label={{ value: 'HVL', fontSize: 8, fill: '#10b981', position: 'right' }} />
            <ReferenceLine y={10}  stroke="#f97316" strokeDasharray="4 2" label={{ value: 'TVL', fontSize: 8, fill: '#f97316', position: 'right' }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] text-muted-foreground">μ values from NIST XCOM. Narrow-beam geometry (no scatter build-up). For broad-beam design, apply build-up factor B(μx). Ref: NIST XCOM; NCRP Report 151.</p>
    </div>
  );
}

function UnitConversionCalc() {
  const [value, setValue] = useState('1');
  const [fromUnit, setFromUnit] = useState('Gy');
  const groups = [
    { label: 'Absorbed Dose', units: ['Gy', 'mGy', 'μGy', 'rad', 'mrad'] },
    { label: 'Equivalent / Effective Dose', units: ['Sv', 'mSv', 'μSv', 'rem', 'mrem'] },
    { label: 'Activity', units: ['Bq', 'kBq', 'MBq', 'GBq', 'TBq', 'Ci', 'mCi', 'μCi', 'dps', 'dpm'] },
    { label: 'Exposure', units: ['C/kg', 'mC/kg', 'R', 'mR'] },
  ];
  // Conversion to SI base (Gy, Sv, Bq, C/kg)
  const factors: Record<string, number> = {
    Gy: 1, mGy: 1e-3, μGy: 1e-6, rad: 0.01, mrad: 1e-4,
    Sv: 1, mSv: 1e-3, μSv: 1e-6, rem: 0.01, mrem: 1e-4,
    Bq: 1, kBq: 1e3, MBq: 1e6, GBq: 1e9, TBq: 1e12, Ci: 3.7e10, mCi: 3.7e7, μCi: 3.7e4, dps: 1, dpm: 1 / 60,
    'C/kg': 1, 'mC/kg': 1e-3, R: 2.58e-4, mR: 2.58e-7,
  };
  const groupOf = (u: string) => groups.findIndex(g => g.units.includes(u));
  const currentGroup = groupOf(fromUnit);
  const val = parseFloat(value) || 0;
  const inSI = val * (factors[fromUnit] ?? 1);

  const convertibleUnits = currentGroup >= 0 ? groups[currentGroup].units : [];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-[11px] text-muted-foreground">Value</label>
          <input type="number" value={value} onChange={e => setValue(e.target.value)}
            className="w-full text-sm bg-card border border-border rounded-md px-3 py-1.5 text-foreground font-mono" />
        </div>
        <div className="space-y-1">
          <label className="text-[11px] text-muted-foreground">From Unit</label>
          <select value={fromUnit} onChange={e => setFromUnit(e.target.value)}
            className="w-full text-xs bg-card border border-border rounded-md px-2 py-1.5 text-foreground">
            {groups.map(g => (
              <optgroup key={g.label} label={g.label}>
                {g.units.map(u => <option key={u} value={u}>{u}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
      </div>

      {convertibleUnits.length > 0 ? (
        <div className="rounded-lg border border-border bg-card/40 overflow-hidden">
          <div className="px-3 py-1.5 bg-card/60 border-b border-border/50 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            {groups[currentGroup].label}
          </div>
          <div className="divide-y divide-border/30">
            {convertibleUnits.map(u => {
              const result = inSI / (factors[u] ?? 1);
              const formatted = result === 0 ? '0' : Math.abs(result) < 0.001 || Math.abs(result) > 1e9
                ? result.toExponential(4) : result.toPrecision(5);
              return (
                <div key={u} className={`flex items-center justify-between px-3 py-2 text-xs ${u === fromUnit ? 'bg-primary/5' : ''}`}>
                  <span className={u === fromUnit ? 'font-bold text-primary' : 'text-muted-foreground'}>{u}</span>
                  <span className="font-mono text-foreground">{formatted}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="text-center text-muted-foreground text-xs py-4">Select a unit to see conversions.</div>
      )}
      <p className="text-[10px] text-muted-foreground">1 Ci = 3.7 × 10¹⁰ Bq (exact). 1 R = 2.58 × 10⁻⁴ C/kg (exact). 1 rad = 0.01 Gy. 1 rem = 0.01 Sv. Ref: NCRP; ICRP 103.</p>
    </div>
  );
}

function PhotonEnergyCalc() {
  const h = 6.626e-34, c = 2.998e8, eV = 1.602e-19;
  const [mode, setMode] = useState<'energy' | 'wavelength'>('energy');
  const [inputVal, setInputVal] = useState('100');
  const [inputUnit, setInputUnit] = useState('keV');

  const energyUnits = { keV: 1e3, MeV: 1e6, eV: 1 };
  const lambdaUnits = { nm: 1e-9, pm: 1e-12, Å: 1e-10 };

  let energyJ = 0, lambdaM = 0;
  const v = parseFloat(inputVal) || 0;

  if (mode === 'energy') {
    energyJ = v * eV * (energyUnits[inputUnit as keyof typeof energyUnits] ?? 1e3);
    lambdaM = energyJ > 0 ? (h * c) / energyJ : 0;
  } else {
    lambdaM = v * (lambdaUnits[inputUnit as keyof typeof lambdaUnits] ?? 1e-12);
    energyJ = lambdaM > 0 ? (h * c) / lambdaM : 0;
  }

  const energyEV = energyJ / eV;
  const energyKeV = energyEV / 1e3;
  const energyMeV = energyEV / 1e6;
  const lambdaNM = lambdaM * 1e9;
  const lambdaPM = lambdaM * 1e12;
  const lambdaAng = lambdaM * 1e10;

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {(['energy', 'wavelength'] as const).map(m => (
          <button key={m} onClick={() => { setMode(m); setInputUnit(m === 'energy' ? 'keV' : 'pm'); }}
            className={`flex-1 text-xs py-1.5 rounded-md border transition-colors ${mode === m ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground'}`}>
            Input: {m === 'energy' ? 'Photon Energy' : 'Wavelength'}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input type="number" value={inputVal} onChange={e => setInputVal(e.target.value)}
          className="text-sm bg-card border border-border rounded-md px-3 py-1.5 text-foreground font-mono" />
        <select value={inputUnit} onChange={e => setInputUnit(e.target.value)}
          className="text-xs bg-card border border-border rounded-md px-2 py-1.5 text-foreground">
          {mode === 'energy'
            ? Object.keys(energyUnits).map(u => <option key={u}>{u}</option>)
            : Object.keys(lambdaUnits).map(u => <option key={u}>{u}</option>)}
        </select>
      </div>
      <div className="rounded-lg border border-border bg-card/40 divide-y divide-border/30">
        {[
          ['Energy (eV)',  energyEV.toExponential(4)],
          ['Energy (keV)', energyKeV.toPrecision(5)],
          ['Energy (MeV)', energyMeV.toPrecision(5)],
          ['λ (nm)',       lambdaNM.toExponential(4)],
          ['λ (pm)',       lambdaPM.toFixed(3)],
          ['λ (Å)',        lambdaAng.toFixed(4)],
        ].map(([label, val]) => (
          <div key={label} className="flex justify-between px-3 py-2 text-xs">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-mono text-foreground">{val}</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground">E = hf = hc/λ. h = 6.626 × 10⁻³⁴ J·s; c = 2.998 × 10⁸ m/s. Ref: NIST CODATA.</p>
    </div>
  );
}

function GeometricUnsharpnessCalc() {
  const [f, setF] = useState(1.0);    // focal spot mm
  const [b, setB] = useState(100);   // object-detector distance mm
  const [a, setA] = useState(900);   // source-object distance mm
  const Ug = (f * b) / a;
  const M = (a + b) / a;

  return (
    <div className="space-y-3">
      <div className="space-y-3">
        {[
          { label: 'Focal spot size f (mm)', val: f, set: setF, min: 0.01, max: 5, step: 0.01 },
          { label: 'Source-to-Object distance a (mm)', val: a, set: setA, min: 50, max: 5000, step: 10 },
          { label: 'Object-to-Detector distance b (mm)', val: b, set: setB, min: 0, max: 500, step: 5 },
        ].map(({ label, val, set, min, max, step }) => (
          <div key={label} className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-muted-foreground">{label}</span>
              <span className="font-mono text-foreground">{val}</span>
            </div>
            <input type="range" min={min} max={max} step={step} value={val}
              onChange={e => set(Number(e.target.value))}
              className="w-full accent-primary" />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-lg border border-border bg-card/60 p-3">
          <div className="text-xl font-bold font-mono text-orange-400">{Ug.toFixed(3)}</div>
          <div className="text-[10px] text-muted-foreground">Ug — Geometric Unsharpness (mm)</div>
        </div>
        <div className="rounded-lg border border-border bg-card/60 p-3">
          <div className="text-xl font-bold font-mono text-blue-400">{M.toFixed(3)}</div>
          <div className="text-[10px] text-muted-foreground">M — Geometric Magnification</div>
        </div>
      </div>
      <AlertBox type={Ug > 0.51 ? 'warning' : 'info'}>
        {Ug > 0.51
          ? `Ug = ${Ug.toFixed(3)} mm exceeds the ASTM E94 / EN ISO 17636 limit of 0.51 mm for Class B technique. Increase source-to-object distance or reduce object-to-detector distance.`
          : `Ug = ${Ug.toFixed(3)} mm — within EN ISO 17636 Class B limit (≤ 0.51 mm).`}
      </AlertBox>
      <p className="text-[10px] text-muted-foreground">Ug = f × b / a. M = (a + b) / a. Ref: EN ISO 17636-1; ASTM E94; ASME V Art. 2.</p>
    </div>
  );
}

const CALC_LIST = [
  { id: 'hvl',   label: 'HVL / TVL Calculator',              icon: Shield,     color: 'text-emerald-400', component: HvlCalc, formula: 'HVL = ln2/μ', ref: 'NIST XCOM' },
  { id: 'units', label: 'Radiation Unit Converter',           icon: RotateCcw,  color: 'text-blue-400',   component: UnitConversionCalc, formula: 'Gy, Sv, Bq, Ci, R, rem', ref: 'ICRP 103' },
  { id: 'photon',label: 'Photon Energy ↔ Wavelength',         icon: Zap,        color: 'text-yellow-400', component: PhotonEnergyCalc,  formula: 'E = hc/λ', ref: 'NIST CODATA' },
  { id: 'ug',    label: 'Geometric Unsharpness & Magnification', icon: Activity, color: 'text-orange-400', component: GeometricUnsharpnessCalc, formula: 'Ug = f·b/a', ref: 'EN ISO 17636' },
];

export function CalculatorsSection() {
  const [activeCalc, setActiveCalc] = useState('hvl');
  const calc = CALC_LIST.find(c => c.id === activeCalc)!;
  const CalcComp = calc.component;

  return (
    <div className="space-y-5">
      <ContentBlock title="Radiation Calculators">
        <p>Interactive calculators for radiation physics and shielding engineering. All formulae reference internationally published standards. Results are for educational and planning purposes — always verify with calibrated instruments and qualified personnel.</p>
      </ContentBlock>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {CALC_LIST.map(c => {
          const Icon = c.icon;
          return (
            <button key={c.id} onClick={() => setActiveCalc(c.id)}
              className={`p-3 rounded-xl border text-left transition-colors ${activeCalc === c.id ? 'bg-primary/10 border-primary/50' : 'bg-card/40 border-border hover:border-primary/30'}`}>
              <Icon className={`h-5 w-5 mb-2 ${c.color}`} />
              <div className="text-xs font-medium leading-tight">{c.label}</div>
              <div className="text-[9px] font-mono text-muted-foreground mt-1">{c.formula}</div>
            </button>
          );
        })}
      </div>

      <div className="rounded-xl border border-border bg-card/40 p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-7 w-7 rounded-lg bg-card flex items-center justify-center">
            <calc.icon className={`h-4 w-4 ${calc.color}`} />
          </div>
          <div>
            <div className="text-sm font-semibold">{calc.label}</div>
            <div className="text-[10px] font-mono text-muted-foreground">{calc.formula} · Ref: {calc.ref}</div>
          </div>
        </div>
        <CalcComp />
      </div>

      <AlertBox type="warning">
        These calculators are educational tools. Do not use results as substitutes for certified dosimetry measurements, ALARA shielding assessments, or professional radiation protection advice. Always consult your Radiation Protection Officer and applicable national regulations.
      </AlertBox>
    </div>
  );
}

// ─── MAINTENANCE CENTER ───────────────────────────────────────────────────────
const FAULT_CATEGORIES = ['All', 'High Voltage', 'X-ray Tube', 'LINAC', 'RF System', 'Cooling', 'Vacuum', 'Detector', 'Interlock', 'Conveyor', 'Image Processing', 'Radiation Monitoring'];

function FaultCard({ fault }: { fault: FaultRecord }) {
  const [expanded, setExpanded] = useState(false);
  const sev = SEVERITY_CFG[fault.severity];

  return (
    <div className={`rounded-xl border overflow-hidden ${sev.bg}`}>
      <button className="w-full flex items-start gap-3 p-4 text-left hover:bg-white/5 transition-colors" onClick={() => setExpanded(e => !e)}>
        <div className={`h-2 w-2 rounded-full mt-2 shrink-0 ${sev.color.replace('text-', 'bg-')}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{fault.title}</span>
            <Badge variant="outline" className={`text-[9px] px-1 py-0 h-4 ${sev.color} border-current`}>{fault.severity}</Badge>
            <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 border-border text-muted-foreground">{fault.category}</Badge>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">{fault.symptoms[0]}</p>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground mt-1 shrink-0" /> : <ChevronDown className="h-4 w-4 text-muted-foreground mt-1 shrink-0" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-white/10 pt-3">
          {/* Safety note first */}
          <AlertBox type={fault.severity === 'Critical' ? 'danger' : fault.severity === 'High' ? 'warning' : 'info'}>
            <b>⚠ Safety:</b> {fault.safetyNote}
          </AlertBox>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="space-y-1">
              <p className="font-semibold text-foreground/80">Symptoms</p>
              {fault.symptoms.map((s, i) => <div key={i} className="text-muted-foreground flex gap-1.5"><span className="text-yellow-400 shrink-0">•</span>{s}</div>)}
            </div>
            <div className="space-y-1">
              <p className="font-semibold text-foreground/80">Possible Causes</p>
              {fault.possibleCauses.map((s, i) => <div key={i} className="text-muted-foreground flex gap-1.5"><span className="text-orange-400 shrink-0">•</span>{s}</div>)}
            </div>
          </div>

          <div className="space-y-1 text-xs">
            <p className="font-semibold text-foreground/80">Diagnostic Steps</p>
            {fault.diagnosticSteps.map((s, i) => (
              <div key={i} className="flex gap-2 text-muted-foreground">
                <span className="font-mono text-blue-400 shrink-0 w-5">{i + 1}.</span>{s}
              </div>
            ))}
          </div>

          <div className="space-y-1 text-xs">
            <p className="font-semibold text-foreground/80">Corrective Actions</p>
            {fault.correctiveActions.map((s, i) => (
              <div key={i} className="flex gap-2 text-muted-foreground">
                <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0 mt-0.5" />{s}
              </div>
            ))}
          </div>

          <div className="text-xs space-y-1">
            <p className="font-semibold text-foreground/80">Related Components</p>
            <div className="flex flex-wrap gap-1.5">
              {fault.relatedComponents.map(c => (
                <span key={c} className="px-1.5 py-0.5 rounded bg-card border border-border text-muted-foreground text-[10px]">{c}</span>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-orange-500/30 bg-orange-500/10 px-3 py-2 text-[11px]">
            <span className="font-semibold text-orange-400">Escalation Criteria: </span>
            <span className="text-muted-foreground">{fault.escalate}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function MaintenanceSection() {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [severity, setSeverity] = useState('All');

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return FAULT_DB.filter(f => {
      const matchCat = category === 'All' || f.category === category;
      const matchSev = severity === 'All' || f.severity === severity;
      const matchQ = !q || f.title.toLowerCase().includes(q) ||
        f.symptoms.some(s => s.toLowerCase().includes(q)) ||
        f.category.toLowerCase().includes(q);
      return matchCat && matchSev && matchQ;
    });
  }, [query, category, severity]);

  return (
    <div className="space-y-5">
      <ContentBlock title="Maintenance & Troubleshooting Center">
        <p>Structured fault database for X-ray, LINAC, and radiation detection systems. Each record includes symptoms, possible causes, step-by-step diagnostics, corrective actions, and escalation criteria.</p>
        <AlertBox type="danger">
          All maintenance work must be performed by qualified personnel following manufacturer procedures, applicable safety regulations, and lockout/tagout (LOTO) protocols. Never bypass safety interlocks, radiation barriers, or emergency stop circuits. Work involving high voltage, radiation sources, or LINAC systems requires specialised training and authorisation.
        </AlertBox>
      </ContentBlock>

      {/* Quick severity summary */}
      <div className="grid grid-cols-4 gap-2">
        {['Critical', 'High', 'Medium', 'Low'].map(s => {
          const count = FAULT_DB.filter(f => f.severity === s).length;
          const cfg = SEVERITY_CFG[s];
          return (
            <button key={s} onClick={() => setSeverity(severity === s ? 'All' : s)}
              className={`p-2 rounded-lg border text-center transition-colors ${severity === s ? cfg.bg + ' border-current/50' : 'bg-card/40 border-border'}`}>
              <div className={`text-lg font-bold ${cfg.color}`}>{count}</div>
              <div className="text-[10px] text-muted-foreground">{s}</div>
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search faults, symptoms, categories…"
            className="pl-9 bg-card/60 border-border text-sm" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FAULT_CATEGORIES.map(c => (
            <button key={c} onClick={() => setCategory(c)}
              className={`text-[11px] px-2 py-0.5 rounded-md border transition-colors ${category === c ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground hover:border-primary/40'}`}>
              {c}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">{filtered.length} of {FAULT_DB.length} records</p>
      </div>

      <div className="space-y-2">
        {filtered.map(f => <FaultCard key={f.id} fault={f} />)}
        {filtered.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">No fault records match your search.</div>
        )}
      </div>
    </div>
  );
}

// ─── STANDARDS LIBRARY ────────────────────────────────────────────────────────
const STD_ORGS = ['All', 'IAEA', 'ICRP', 'NCRP', 'IEC', 'ISO', 'ASTM', 'ANSI / IEEE'];

function StandardCard({ s }: { s: StandardRecord }) {
  const [expanded, setExpanded] = useState(false);
  const orgColor: Record<string, string> = {
    IAEA: 'text-blue-400', ICRP: 'text-purple-400', NCRP: 'text-orange-400',
    IEC: 'text-emerald-400', ISO: 'text-cyan-400', ASTM: 'text-yellow-400', 'ANSI / IEEE': 'text-pink-400', 'ISO / CEN': 'text-teal-400',
  };
  const color = orgColor[s.organization] ?? 'text-muted-foreground';

  return (
    <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
      <button className="w-full flex items-start gap-3 p-4 text-left hover:bg-card/60 transition-colors" onClick={() => setExpanded(e => !e)}>
        <div className={`w-12 text-center shrink-0 mt-0.5 text-[10px] font-bold font-mono ${color} leading-tight`}>{s.organization}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-muted-foreground">{s.number}</span>
            <span className="font-semibold text-sm">{s.title}</span>
          </div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {s.categories.map(c => <Badge key={c} variant="outline" className="text-[9px] px-1 py-0 h-4">{c}</Badge>)}
            <span className="text-[10px] text-muted-foreground">{s.year}</span>
          </div>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground mt-1 shrink-0" /> : <ChevronDown className="h-4 w-4 text-muted-foreground mt-1 shrink-0" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border/50 pt-3">
          <div>
            <p className="text-xs font-semibold text-foreground/80 mb-1">Scope</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{s.scope}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-foreground/80 mb-1">Relevance to This Platform</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{s.relevance}</p>
          </div>
          <a href={s.url} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <Globe className="h-3.5 w-3.5" />Official source <ExternalLink className="h-3 w-3 opacity-50" />
          </a>
        </div>
      )}
    </div>
  );
}

export function StandardsSection() {
  const [query, setQuery] = useState('');
  const [org, setOrg] = useState('All');

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return STANDARDS_DB.filter(s => {
      const matchOrg = org === 'All' || s.organization.startsWith(org.split(' / ')[0]);
      const matchQ = !q || s.title.toLowerCase().includes(q) || s.number.toLowerCase().includes(q) ||
        s.categories.some(c => c.toLowerCase().includes(q)) || s.scope.toLowerCase().includes(q);
      return matchOrg && matchQ;
    });
  }, [query, org]);

  return (
    <div className="space-y-5">
      <ContentBlock title="Research, Standards & Regulatory Library">
        <p>Curated reference library of international standards, IAEA safety guides, ICRP recommendations, and regulatory documents relevant to radiation sources, accelerators, security screening, NDT, and radiation protection.</p>
        <AlertBox type="info">Only publicly accessible documents or their metadata are linked. Full text of paid standards requires purchase through the official issuing body. Do not rely on third-party reproductions.</AlertBox>
      </ContentBlock>

      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search title, number, organisation, topic…"
            className="pl-9 bg-card/60 border-border text-sm" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {STD_ORGS.map(o => (
            <button key={o} onClick={() => setOrg(o)}
              className={`text-[11px] px-2 py-0.5 rounded-md border transition-colors ${org === o ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground hover:border-primary/40'}`}>
              {o}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">{filtered.length} of {STANDARDS_DB.length} documents</p>
      </div>

      <div className="space-y-2">
        {filtered.map(s => <StandardCard key={s.id} s={s} />)}
        {filtered.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">No documents match your search.</div>
        )}
      </div>
    </div>
  );
}

// ─── PHYSICS ANIMATIONS HUB ───────────────────────────────────────────────────
function ComptonAnimation({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); cancelAnimationFrame(rafRef.current); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 2800) / 2800);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  // Incident photon: travels right along y=90 until electron at (250, 90)
  const px = Math.min(250, 20 + t * 290); // Photon progress
  const impacted = t > 0.80 || px >= 249;
  // Scattered photon: goes up-right after collision
  const scatT = impacted ? Math.min(1, (t - 0.80) / 0.20) : 0;
  const spx = 250 + scatT * 100;
  const spy = 90 - scatT * 70;
  // Recoil electron: goes down-right
  const epx = 250 + scatT * 80;
  const epy = 90 + scatT * 65;

  return (
    <svg viewBox="0 0 420 180" className="w-full max-w-xl" style={{ fontFamily: 'monospace' }}>
      <text x="210" y="14" textAnchor="middle" fontSize="10" fill="#cbd5e1" fontWeight="bold">COMPTON SCATTERING</text>

      {/* Electron cloud at origin */}
      <circle cx="250" cy="90" r="14" fill="#1e3a5f" stroke="#3b82f6" strokeWidth="1.5" />
      <text x="250" y="94" textAnchor="middle" fontSize="8" fill="#93c5fd">e⁻</text>

      {/* Incident photon ray */}
      {!impacted && (
        <>
          <line x1="20" y1="90" x2={px} y2="90" stroke="#fbbf24" strokeWidth="2" strokeDasharray="6 3" />
          <circle cx={px} cy="90" r="5" fill="#fbbf24" opacity="0.9" />
          <text x="20" y="82" fontSize="8" fill="#fbbf24">γ (incident)</text>
        </>
      )}
      {/* Arrow showing direction for static */}
      {!animated && (
        <line x1="20" y1="90" x2="234" y2="90" stroke="#fbbf24" strokeWidth="1.5" strokeDasharray="5 3" opacity="0.4" />
      )}

      {/* Scattered photon */}
      {impacted && (
        <>
          <line x1="250" y1="90" x2={spx} y2={spy} stroke="#f59e0b" strokeWidth="2" strokeDasharray="5 3" />
          <circle cx={spx} cy={spy} r="5" fill="#f59e0b" opacity="0.9" />
          <text x={spx + 6} y={spy - 4} fontSize="8" fill="#f59e0b">γ' (scattered)</text>
          <text x={spx - 4} y={spy + 14} fontSize="7" fill="#94a3b8">lower energy</text>
        </>
      )}
      {!animated && (
        <>
          <line x1="250" y1="90" x2="350" y2="20" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="5 3" opacity="0.5" />
          <text x="355" y="16" fontSize="8" fill="#f59e0b">γ' scattered</text>
        </>
      )}

      {/* Recoil electron */}
      {impacted && (
        <>
          <line x1="250" y1="90" x2={epx} y2={epy} stroke="#60a5fa" strokeWidth="2" />
          <circle cx={epx} cy={epy} r="5" fill="#60a5fa" opacity="0.9" />
          <text x={epx + 6} y={epy + 4} fontSize="8" fill="#60a5fa">e⁻ (recoil)</text>
        </>
      )}
      {!animated && (
        <>
          <line x1="250" y1="90" x2="330" y2="155" stroke="#60a5fa" strokeWidth="1.5" opacity="0.5" />
          <text x="335" y="155" fontSize="8" fill="#60a5fa">e⁻ recoil</text>
        </>
      )}

      {/* Angle labels */}
      {!animated && (
        <>
          <text x="270" y="62" fontSize="8" fill="#94a3b8">θ (scatter angle)</text>
          <text x="270" y="132" fontSize="8" fill="#94a3b8">φ (recoil angle)</text>
        </>
      )}

      {/* Labels */}
      <text x="210" y="170" textAnchor="middle" fontSize="8" fill="#64748b">E′ = E₀ / [1 + (E₀/m₀c²)(1 − cosθ)] · Compton (1923)</text>
    </svg>
  );
}

function PhotoelectricAnimation({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); cancelAnimationFrame(rafRef.current); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 2400) / 2400);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  const phx = Math.min(190, 20 + t * 220);
  const absorbed = phx >= 189;
  const ejectT = absorbed ? Math.min(1, (t - 0.85) / 0.15) : 0;
  const ejX = 210 + ejectT * 130;
  const ejY = 90 - ejectT * 50;

  return (
    <svg viewBox="0 0 420 180" className="w-full max-w-xl" style={{ fontFamily: 'monospace' }}>
      <text x="210" y="14" textAnchor="middle" fontSize="10" fill="#cbd5e1" fontWeight="bold">PHOTOELECTRIC EFFECT</text>

      {/* Atom with shells */}
      <circle cx="200" cy="90" r="50" fill="none" stroke="#1e3a5f" strokeWidth="1.5" strokeDasharray="4 3" />
      <circle cx="200" cy="90" r="30" fill="none" stroke="#1e3a5f" strokeWidth="1.5" strokeDasharray="3 2" />
      <circle cx="200" cy="90" r="12" fill="#1e2a3f" stroke="#3b82f6" strokeWidth="2" />
      <text x="200" y="94" textAnchor="middle" fontSize="8" fill="#93c5fd">Pb</text>
      {/* K-shell electron */}
      <circle cx="188" cy="90" r="4" fill="#60a5fa" />
      <text x="190" y="145" textAnchor="middle" fontSize="7" fill="#475569">K-shell</text>
      <text x="200" y="158" textAnchor="middle" fontSize="7" fill="#475569">L-shell</text>

      {/* Incident photon */}
      {!absorbed && (
        <>
          <line x1="20" y1="90" x2={phx} y2="90" stroke="#fbbf24" strokeWidth="2" strokeDasharray="6 3" />
          <circle cx={phx} cy="90" r="5" fill="#fbbf24" />
          <text x="20" y="82" fontSize="8" fill="#fbbf24">γ (hν)</text>
        </>
      )}
      {!animated && (
        <line x1="20" y1="90" x2="148" y2="90" stroke="#fbbf24" strokeWidth="1.5" strokeDasharray="5 3" opacity="0.4" />
      )}

      {/* Ejected photoelectron */}
      {(absorbed || !animated) && (
        <>
          <line x1="210" y1="90" x2={animated ? ejX : 340} y2={animated ? ejY : 40}
            stroke="#a78bfa" strokeWidth={animated ? 2 : 1.5} strokeDasharray={animated ? '0' : '5 3'} opacity={animated ? 1 : 0.6} />
          <circle cx={animated ? ejX : 340} cy={animated ? ejY : 40} r="5" fill="#a78bfa" opacity={animated && !absorbed ? 0 : 0.9} />
          <text x={animated ? ejX + 6 : 345} y={animated ? ejY - 4 : 36} fontSize="8" fill="#a78bfa">e⁻ (KE = hν − φ)</text>
        </>
      )}

      {/* Characteristic X-ray emitted during K-shell vacancy fill */}
      {absorbed && ejectT > 0.4 && (
        <>
          <line x1="200" y1="62" x2="200" y2="28" stroke="#06b6d4" strokeWidth="1.5" strokeDasharray="4 2" />
          <circle cx="200" cy="25" r="4" fill="#06b6d4" />
          <text x="206" y="24" fontSize="8" fill="#06b6d4">Kα X-ray</text>
        </>
      )}
      {!animated && (
        <>
          <line x1="200" y1="62" x2="200" y2="30" stroke="#06b6d4" strokeWidth="1.2" strokeDasharray="4 2" opacity="0.5" />
          <text x="206" y="28" fontSize="7" fill="#06b6d4">Kα fluorescent X-ray</text>
        </>
      )}

      <text x="210" y="172" textAnchor="middle" fontSize="8" fill="#64748b">KE = hν − φ (φ = binding energy). Dominant below ~100 keV in high-Z materials.</text>
    </svg>
  );
}

function BremsstrahlungAnimation({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); cancelAnimationFrame(rafRef.current); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 3000) / 3000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  const ex = Math.min(195, 30 + t * 220);
  const deflected = ex >= 194;
  const postT = deflected ? Math.min(1, (t - 0.64) / 0.36) : 0;
  const dex = 210 + postT * 80;
  const dey = 90 + postT * 60;
  const phX = 210 + postT * 120;
  const phY = 90 - postT * 80;

  return (
    <svg viewBox="0 0 420 190" className="w-full max-w-xl" style={{ fontFamily: 'monospace' }}>
      <text x="210" y="14" textAnchor="middle" fontSize="10" fill="#cbd5e1" fontWeight="bold">BREMSSTRAHLUNG PRODUCTION</text>

      {/* Nucleus */}
      <circle cx="200" cy="90" r="18" fill="#1e3a1e" stroke="#22c55e" strokeWidth="2" />
      <text x="200" y="86" textAnchor="middle" fontSize="8" fill="#86efac">W</text>
      <text x="200" y="97" textAnchor="middle" fontSize="8" fill="#86efac">(Z=74)</text>

      {/* Incident electron */}
      {!deflected && (
        <>
          <line x1="30" y1="90" x2={ex} y2="90" stroke="#60a5fa" strokeWidth="2" />
          <circle cx={ex} cy="90" r="5" fill="#60a5fa" />
          <text x="30" y="82" fontSize="8" fill="#60a5fa">e⁻ (v ≈ 0.9c)</text>
        </>
      )}
      {!animated && (
        <line x1="30" y1="90" x2="180" y2="90" stroke="#60a5fa" strokeWidth="1.5" opacity="0.4" />
      )}

      {/* Curved electron path around nucleus */}
      {!animated && (
        <path d="M 180 90 Q 200 60 220 90" fill="none" stroke="#60a5fa" strokeWidth="1.5" strokeDasharray="4 2" opacity="0.5" />
      )}

      {/* Deflected electron (slower) */}
      {(deflected || !animated) && (
        <>
          <line x1="210" y1="90" x2={animated ? dex : 290} y2={animated ? dey : 150}
            stroke="#3b82f6" strokeWidth={animated ? 2 : 1.5} opacity={animated && !deflected ? 0 : 0.9} strokeDasharray={animated ? '0' : '5 3'} />
          <circle cx={animated ? dex : 290} cy={animated ? dey : 150} r="5" fill="#3b82f6" opacity={animated && !deflected ? 0 : 0.9} />
          <text x={animated ? dex + 4 : 295} y={animated ? dey + 4 : 158} fontSize="8" fill="#93c5fd">e⁻ (slower)</text>
        </>
      )}

      {/* Bremsstrahlung photon */}
      {(deflected || !animated) && (
        <>
          <line x1="210" y1="90" x2={animated ? phX : 360} y2={animated ? phY : 20}
            stroke="#fbbf24" strokeWidth={animated ? 2 : 1.5} strokeDasharray="6 3" opacity={animated && !deflected ? 0 : 0.9} />
          <circle cx={animated ? phX : 360} cy={animated ? phY : 20} r="5" fill="#fbbf24" opacity={animated && !deflected ? 0 : 0.9} />
          <text x={animated ? phX - 20 : 340} y={animated ? phY - 6 : 14} fontSize="8" fill="#fbbf24">X-ray photon</text>
          <text x={animated ? phX - 14 : 340} y={animated ? phY + 6 : 24} fontSize="7" fill="#94a3b8">ΔKE = hν</text>
        </>
      )}

      <text x="210" y="182" textAnchor="middle" fontSize="8" fill="#64748b">Efficiency ≈ 9×10⁻¹⁰ ZV (kV). W target maximises Bremsstrahlung. Kramers (1923).</text>
    </svg>
  );
}

function PairProductionAnimation({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); cancelAnimationFrame(rafRef.current); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 2800) / 2800);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  const phX = Math.min(185, 20 + t * 220);
  const created = phX >= 184;
  const postT = created ? Math.min(1, (t - 0.65) / 0.35) : 0;

  // e⁻ goes up-left, e⁺ goes up-right
  const emX = 200 - postT * 90;
  const emY = 90 - postT * 65;
  const epX = 200 + postT * 90;
  const epY = 90 - postT * 60;

  // Annihilation photons from e⁺
  const annihilT = postT > 0.8 ? Math.min(1, (postT - 0.8) / 0.2) : 0;
  const ann1X = epX + annihilT * 60;
  const ann2X = epX - annihilT * 50;
  const ann1Y = epY - annihilT * 20;
  const ann2Y = epY + annihilT * 40;

  return (
    <svg viewBox="0 0 420 200" className="w-full max-w-xl" style={{ fontFamily: 'monospace' }}>
      <text x="210" y="14" textAnchor="middle" fontSize="10" fill="#cbd5e1" fontWeight="bold">PAIR PRODUCTION (E &gt; 1.022 MeV)</text>

      {/* Nucleus field region */}
      <circle cx="200" cy="90" r="22" fill="#1e1e3a" stroke="#8b5cf6" strokeWidth="1.5" strokeDasharray="4 2" opacity="0.7" />
      <text x="200" y="88" textAnchor="middle" fontSize="7" fill="#a78bfa">Nuclear</text>
      <text x="200" y="98" textAnchor="middle" fontSize="7" fill="#a78bfa">field</text>

      {/* Incoming high-energy photon */}
      {!created && (
        <>
          <line x1="20" y1="90" x2={phX} y2="90" stroke="#fbbf24" strokeWidth="2.5" strokeDasharray="6 3" />
          <circle cx={phX} cy="90" r="6" fill="#fbbf24" />
          <text x="22" y="82" fontSize="8" fill="#fbbf24">γ (hν &gt; 1.022 MeV)</text>
        </>
      )}
      {!animated && (
        <line x1="20" y1="90" x2="176" y2="90" stroke="#fbbf24" strokeWidth="2" strokeDasharray="5 3" opacity="0.4" />
      )}

      {/* Electron */}
      {(created || !animated) && (
        <>
          <line x1="200" y1="90" x2={animated ? emX : 110} y2={animated ? emY : 25}
            stroke="#60a5fa" strokeWidth={animated ? 2 : 1.5} opacity={animated && !created ? 0 : 0.9} strokeDasharray={animated ? '0' : '4 2'} />
          <circle cx={animated ? emX : 110} cy={animated ? emY : 25} r="5" fill="#60a5fa" opacity={animated && !created ? 0 : 1} />
          <text x={animated ? emX - 22 : 92} y={animated ? emY - 6 : 18} fontSize="8" fill="#60a5fa">e⁻</text>
        </>
      )}

      {/* Positron */}
      {(created || !animated) && (
        <>
          <line x1="200" y1="90" x2={animated ? epX : 300} y2={animated ? epY : 25}
            stroke="#f87171" strokeWidth={animated ? 2 : 1.5} opacity={animated && !created ? 0 : 0.9} strokeDasharray={animated ? '0' : '4 2'} />
          <circle cx={animated ? epX : 300} cy={animated ? epY : 25} r="5" fill="#f87171" opacity={animated && !created ? 0 : 1} />
          <text x={animated ? epX + 4 : 306} y={animated ? epY - 6 : 18} fontSize="8" fill="#f87171">e⁺</text>
        </>
      )}

      {/* Annihilation photons from positron */}
      {postT > 0.8 && animated && (
        <>
          <circle cx={epX} cy={epY} r="8" fill="none" stroke="#fbbf24" strokeWidth="1.5" opacity={annihilT} />
          <line x1={epX} y1={epY} x2={ann1X} y2={ann1Y} stroke="#fbbf24" strokeWidth="1.5" strokeDasharray="4 2" opacity={annihilT} />
          <line x1={epX} y1={epY} x2={ann2X} y2={ann2Y} stroke="#fbbf24" strokeWidth="1.5" strokeDasharray="4 2" opacity={annihilT} />
          <text x={ann1X + 3} y={ann1Y} fontSize="7" fill="#fbbf24" opacity={annihilT}>511 keV γ</text>
        </>
      )}
      {!animated && (
        <>
          <text x="305" y="40" fontSize="7" fill="#fbbf24">→ annihilation</text>
          <text x="305" y="50" fontSize="7" fill="#fbbf24">2 × 511 keV γ</text>
        </>
      )}

      <text x="210" y="188" textAnchor="middle" fontSize="8" fill="#64748b">Threshold: 1.022 MeV (2m₀c²). Dominant above 5–10 MeV in high-Z materials. ICRP 103.</text>
    </svg>
  );
}

export const ANIM_LIST = [
  {
    id: 'compton',         label: 'Compton Scattering',          desc: 'Photon-electron interaction. Scattered photon has lower energy; electron recoils. Dominant interaction at 0.1–10 MeV in low-Z materials.',
    energy: '0.1 – 10 MeV', material: 'Low-to-medium Z', component: ComptonAnimation,
    formula: "E' = E₀ / [1 + (E₀/m₀c²)(1−cosθ)]", ref: 'Compton (1923)',
  },
  {
    id: 'photoelectric',   label: 'Photoelectric Effect',        desc: 'Photon absorbed by inner-shell electron. Electron ejected with kinetic energy KE = hν − φ. Fluorescent X-ray or Auger electron emitted.',
    energy: '< 100 keV', material: 'High-Z (Pb, W, I)', component: PhotoelectricAnimation,
    formula: 'KE = hν − φ', ref: 'Einstein (1905)',
  },
  {
    id: 'bremsstrahlung',  label: 'Bremsstrahlung Production',   desc: 'Electron decelerated in nuclear Coulomb field. Energy difference emitted as X-ray photon. Basis of all medical and industrial X-ray tube output.',
    energy: 'Continuous 0–eV_max', material: 'Tungsten (Z=74)', component: BremsstrahlungAnimation,
    formula: 'ΔKE = hν', ref: 'Kramers (1923)',
  },
  {
    id: 'pair',            label: 'Pair Production',             desc: 'High-energy photon (> 1.022 MeV) creates electron–positron pair in nuclear field. Positron later annihilates producing two 511 keV photons.',
    energy: '> 1.022 MeV', material: 'High-Z', component: PairProductionAnimation,
    formula: 'E_threshold = 2m₀c² = 1.022 MeV', ref: 'Dirac (1930)',
  },
];

export function AnimationsSection() {
  const [activeId, setActiveId] = useState('compton');
  const [animated, setAnimated] = useState(false);
  const anim = ANIM_LIST.find(a => a.id === activeId)!;
  const AnimComp = anim.component;

  return (
    <div className="space-y-5">
      <ContentBlock title="Interactive Physics Animations">
        <p>Animated diagrams of fundamental radiation–matter interaction processes. Press Play to start the animation. Use the tabs to switch between processes.</p>
        <AlertBox type="info">These diagrams are schematic representations for educational purposes. They are not to scale and do not represent real quantum mechanical trajectories.</AlertBox>
      </ContentBlock>

      {/* Animation tabs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {ANIM_LIST.map(a => (
          <button key={a.id}
            onClick={() => { setActiveId(a.id); setAnimated(false); }}
            className={`p-3 rounded-xl border text-left transition-colors ${activeId === a.id ? 'bg-primary/10 border-primary/50' : 'bg-card/40 border-border hover:border-primary/30'}`}>
            <div className="text-xs font-semibold">{a.label}</div>
            <div className="text-[9px] font-mono text-muted-foreground mt-1">{a.energy}</div>
            <div className="text-[9px] text-muted-foreground">{a.material}</div>
          </button>
        ))}
      </div>

      {/* Main animation panel */}
      <div className="rounded-xl border border-border bg-card/40 p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">{anim.label}</h3>
            <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{anim.desc}</p>
          </div>
          <Button size="sm" variant={animated ? 'outline' : 'default'}
            onClick={() => setAnimated(a => !a)}
            className="shrink-0 gap-1.5 text-xs h-7">
            {animated ? <><Pause className="h-3 w-3" />Pause</> : <><Play className="h-3 w-3" />Play</>}
          </Button>
        </div>

        <div className="rounded-lg bg-[#0a1628] p-3">
          <AnimComp animated={animated} />
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="rounded-lg border border-border bg-card/40 p-3">
            <p className="font-mono text-muted-foreground text-[10px] mb-1">Formula</p>
            <p className="font-mono text-foreground">{anim.formula}</p>
          </div>
          <div className="rounded-lg border border-border bg-card/40 p-3">
            <p className="font-mono text-muted-foreground text-[10px] mb-1">Reference</p>
            <p className="text-foreground">{anim.ref}</p>
          </div>
        </div>
      </div>

      {/* Interaction dominance summary */}
      <ContentBlock title="Interaction Dominance by Energy & Material">
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 pr-4 text-muted-foreground font-medium">Energy Range</th>
                <th className="text-left py-2 pr-4 text-muted-foreground font-medium">Low-Z (water, tissue)</th>
                <th className="text-left py-2 text-muted-foreground font-medium">High-Z (lead, tungsten)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {[
                ['< 30 keV',    'Photoelectric dominant', 'Photoelectric (very strong, ∝ Z⁴)'],
                ['30–150 keV',  'Compton increasing',     'Photoelectric + Compton'],
                ['150 keV–5 MeV','Compton dominant',      'Compton dominant'],
                ['> 5 MeV',    'Pair production rising',  'Pair production dominant'],
                ['> 15 MeV',   'Pair production dominant','Pair production + photonuclear'],
              ].map(([e, lo, hi]) => (
                <tr key={e} className="hover:bg-card/30">
                  <td className="py-2 pr-4 font-mono text-muted-foreground">{e}</td>
                  <td className="py-2 pr-4 text-foreground/80">{lo}</td>
                  <td className="py-2 text-foreground/80">{hi}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-muted-foreground">Ref: NIST XCOM Photon Cross-Sections; ICRP 103; Attix "Introduction to Radiological Physics" (2004).</p>
      </ContentBlock>
    </div>
  );
}

// ─── LEARNING PATHS ───────────────────────────────────────────────────────────
export function LearningPathsSection() {
  const [selected, setSelected] = useState<string | null>(null);
  const path = LEARNING_PATHS.find(p => p.id === selected);

  const levelConfig = {
    Beginner:     { color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30' },
    Intermediate: { color: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/30' },
    Advanced:     { color: 'text-violet-400',  bg: 'bg-violet-500/10 border-violet-500/30' },
    Expert:       { color: 'text-orange-400',  bg: 'bg-orange-500/10 border-orange-500/30' },
  };

  return (
    <div className="space-y-5">
      <ContentBlock title="Structured Learning Paths">
        <p>Curated curricula designed for specific roles and experience levels. Each path outlines the sequence of topics, estimated duration, target audience, and learning prerequisites.</p>
        <AlertBox type="info">Completion of a learning path on this platform does not constitute official accreditation or professional certification unless issued by a recognised awarding body. Consult your professional regulatory body for formal qualification requirements.</AlertBox>
      </ContentBlock>

      {selected && path ? (
        <div className="space-y-4">
          <button onClick={() => setSelected(null)}
            className="flex items-center gap-1.5 text-xs text-primary hover:underline">
            ← Back to all paths
          </button>
          <div className={`rounded-xl border p-5 ${levelConfig[path.level].bg}`}>
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-lg font-bold">{path.title}</h2>
                  <Badge variant="outline" className={`${path.color} border-current`}>{path.level}</Badge>
                </div>
                <div className="flex gap-3 mt-1 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{path.duration}</span>
                  <span className="flex items-center gap-1"><Star className="h-3 w-3" />{path.level}</span>
                </div>
              </div>
            </div>
            <p className="text-sm text-muted-foreground mt-3 leading-relaxed">{path.description}</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <ContentBlock title="Topics Covered">
              <div className="space-y-1.5">
                {path.topics.map((t, i) => (
                  <div key={t} className="flex items-start gap-2 text-xs">
                    <span className="font-mono text-primary/60 shrink-0 w-5">{i + 1}.</span>
                    <span className="text-muted-foreground">{t}</span>
                  </div>
                ))}
              </div>
            </ContentBlock>
            <ContentBlock title="Target Audience">
              <div className="space-y-1.5">
                {path.targetAudience.map(a => (
                  <div key={a} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Users className="h-3 w-3 shrink-0 text-primary/50" />{a}
                  </div>
                ))}
              </div>
            </ContentBlock>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {LEARNING_PATHS.map(p => {
            const cfg = levelConfig[p.level];
            return (
              <button key={p.id} onClick={() => setSelected(p.id)}
                className={`p-4 rounded-xl border text-left hover:border-primary/40 transition-colors ${cfg.bg}`}>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <Badge variant="outline" className={`text-[9px] ${p.color} border-current`}>{p.level}</Badge>
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" />{p.duration}</span>
                </div>
                <h3 className="font-semibold text-sm leading-tight">{p.title}</h3>
                <p className="text-[11px] text-muted-foreground mt-2 leading-relaxed line-clamp-3">{p.description}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {p.targetAudience.slice(0, 2).map(a => (
                    <span key={a} className="text-[9px] px-1.5 py-0.5 rounded bg-card/40 border border-border/50 text-muted-foreground">{a}</span>
                  ))}
                </div>
                <div className="flex items-center gap-1 mt-2 text-[10px] text-primary">
                  View curriculum <ArrowRight className="h-3 w-3" />
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
