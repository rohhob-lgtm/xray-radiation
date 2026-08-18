import { useState, useEffect, useRef, useMemo } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useResizableColumn, ColumnResizer, ColumnToggle, CollapsedStrip } from '@/components/ui/resizable-column';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import {
  Zap, Atom, Shield, AlertTriangle, Wrench, BookOpen, ChevronRight,
  Activity, Layers, Target, Thermometer, Eye, FlaskConical, Radio,
  Cpu, Radiation, BarChart2, Info, Play, Pause, RotateCcw, CheckCircle2,
  XCircle, HelpCircle, ChevronDown, ChevronUp, TrendingDown, Gauge,
  Building2, Calculator, GraduationCap, LayoutDashboard, Search, Brain, Clapperboard, ScanLine, CircuitBoard,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip,
  LineChart, Line, ReferenceLine, BarChart, Bar, Cell, CartesianGrid,
} from 'recharts';
import {
  DashboardSection, ManufacturersSection, EquipmentSection,
  CalculatorsSection, MaintenanceSection, StandardsSection,
  AnimationsSection, LearningPathsSection,
} from './radiation-ext';
import { LearningCenterSection } from './learning-center';
import { TopicMedia, MediaTheatreSection } from '@/components/radiation/media-shelf';
import { LearnSection } from '@/components/radiation/course-mode';
import { useLessonLang } from '@/components/radiation/anim-gallery';
import { PAGE_STRINGS_AR, SECTION_DESC_AR, COURSE_TITLES_AR } from '@/components/radiation/lessons-ar-course';
import { TOPIC_QUIZZES, type QuizQuestion } from '@/data/learning-center';

// ─── Navigation ──────────────────────────────────────────────────────────────
interface SourceSection {
  id: string; label: string; icon: any; color: string;
  badge?: string; group?: string; isNew?: boolean;
}

// Navigation groups for collapsible sidebar
const NAV_GROUPS = [
  { id: 'learn-top',     label: 'Learn',              ids: ['learn'] },
  { id: 'overview',      label: 'Overview',           ids: ['dashboard'] },
  { id: 'sources',       label: 'Radiation Sources',  ids: ['xray-tube','linac','betatron','cyclotron','synchrotron','van-de-graaff','radioisotopes','neutron','gamma-irradiators'] },
  { id: 'techdet',       label: 'Technology & Detectors', ids: ['xray-technologies','detectors'] },
  { id: 'systems',       label: 'Systems',            ids: ['industrial-xray','security','equipment-db'] },
  { id: 'industry',      label: 'Industry & Reference', ids: ['manufacturers','standards'] },
  { id: 'tools',         label: 'Interactive Tools',  ids: ['media-theatre','calculators','virtual-lab','animations','comparison'] },
  { id: 'learn',         label: 'Learning & Training', ids: ['learning-paths','learning-center','maintenance'] },
];

const SECTIONS: SourceSection[] = [
  // Learn
  { id: 'learn',         label: 'Courses',                icon: GraduationCap,   color: 'text-rose-400',    badge: 'Learn',        group: 'learn-top', isNew: true },
  // Overview
  { id: 'dashboard',     label: 'Dashboard',              icon: LayoutDashboard, color: 'text-purple-400',  badge: 'Hub',          group: 'overview' },
  // Radiation Sources
  { id: 'xray-tube',     label: 'X-ray Tubes',            icon: Zap,             color: 'text-blue-400',    badge: 'Core',         group: 'sources' },
  { id: 'linac',         label: 'LINAC',                  icon: Cpu,             color: 'text-violet-400',  badge: 'Accelerator',  group: 'sources' },
  { id: 'betatron',      label: 'Betatron',               icon: Activity,        color: 'text-pink-400',    badge: 'Accelerator',  group: 'sources' },
  { id: 'cyclotron',     label: 'Cyclotron',              icon: RotateCcw,       color: 'text-emerald-400', badge: 'Accelerator',  group: 'sources' },
  { id: 'synchrotron',   label: 'Synchrotron',            icon: Radio,           color: 'text-cyan-400',    badge: 'Accelerator',  group: 'sources' },
  { id: 'van-de-graaff', label: 'Van de Graaff',          icon: Radiation,       color: 'text-yellow-400',  badge: 'Electrostatic',group: 'sources' },
  { id: 'radioisotopes', label: 'Radioisotope Sources',   icon: Atom,            color: 'text-orange-400',  badge: 'Nuclear',      group: 'sources' },
  { id: 'neutron',       label: 'Neutron Sources',        icon: Target,          color: 'text-red-400',     badge: 'Neutron',      group: 'sources' },
  { id: 'gamma-irradiators', label: 'Gamma Irradiators', icon: Shield,          color: 'text-rose-400',    badge: 'Industrial',   group: 'sources' },
  // Technology & Detectors
  { id: 'xray-technologies', label: 'Imaging Technologies', icon: ScanLine,       color: 'text-amber-400',   badge: 'Physics',      group: 'techdet', isNew: true },
  { id: 'detectors',     label: 'Detector Technology',   icon: CircuitBoard,    color: 'text-emerald-400', badge: 'Detectors',    group: 'techdet', isNew: true },
  // Systems
  { id: 'industrial-xray', label: 'Industrial X-ray',    icon: Layers,          color: 'text-sky-400',     badge: 'Systems',      group: 'systems' },
  { id: 'security',      label: 'Security Screening',    icon: Eye,             color: 'text-teal-400',    badge: 'Security',     group: 'systems' },
  { id: 'equipment-db',  label: 'Equipment Database',    icon: BarChart2,       color: 'text-lime-400',    badge: 'DB',           group: 'systems', isNew: true },
  // Industry & Reference
  { id: 'manufacturers', label: 'Manufacturers',          icon: Building2,       color: 'text-sky-400',     badge: 'Directory',    group: 'industry', isNew: true },
  { id: 'standards',     label: 'Standards & Research',  icon: BookOpen,        color: 'text-cyan-400',    badge: 'Library',      group: 'industry', isNew: true },
  // Interactive Tools
  { id: 'media-theatre', label: 'Video Theatre',         icon: Clapperboard,    color: 'text-pink-400',    badge: 'Films',        group: 'tools',   isNew: true },
  { id: 'calculators',   label: 'Calculators',           icon: Calculator,      color: 'text-emerald-400', badge: 'Tools',        group: 'tools',   isNew: true },
  { id: 'virtual-lab',   label: 'Virtual Laboratory',    icon: FlaskConical,    color: 'text-amber-400',   badge: 'Lab',          group: 'tools' },
  { id: 'animations',    label: 'Physics Animations',    icon: Activity,        color: 'text-pink-400',    badge: 'Animate',      group: 'tools',   isNew: true },
  { id: 'comparison',    label: 'Source Comparison',     icon: BarChart2,       color: 'text-lime-400',    badge: 'Charts',       group: 'tools' },
  // Learning & Training
  { id: 'learning-paths',label: 'Learning Paths',        icon: GraduationCap,   color: 'text-rose-400',    badge: 'Learn',        group: 'learn',   isNew: true },
  { id: 'learning-center',label: 'Learning Center',      icon: Brain,           color: 'text-fuchsia-400', badge: 'New',          group: 'learn',   isNew: true },
  { id: 'maintenance',   label: 'Maintenance Center',    icon: Wrench,          color: 'text-orange-400',  badge: 'Service',      group: 'learn',   isNew: true },
];

// ─── Isotope data ─────────────────────────────────────────────────────────────
const ISOTOPES = [
  { name: 'Co-60',  z: 27, a: 60,  halfLifeYears: 5.27,   halfLife: '5.27 y',   energy: '1.17, 1.33 MeV γ', hvl: '12.5 mm Pb', activity: 'TBq range', shielding: 'Lead ≥ 150 mm / depleted uranium', uses: 'Industrial γ-radiography, food irradiation, sterilisation, teletherapy', hazard: 'High — remote handling only', color: 'text-orange-400', transport: 'Type B(U) package — IAEA SSR-6', refDoseRate: 350 },
  { name: 'Cs-137', z: 55, a: 137, halfLifeYears: 30.17,  halfLife: '30.17 y',  energy: '0.662 MeV γ (via Ba-137m)', hvl: '6.5 mm Pb', activity: 'GBq–TBq', shielding: 'Lead ≥ 80 mm', uses: 'Industrial gauges, brachytherapy, calibration, RTG', hazard: 'High — dispersal risk, historical accidents', color: 'text-yellow-400', transport: 'Type B(U) package', refDoseRate: 77 },
  { name: 'Ir-192', z: 77, a: 192, halfLifeYears: 0.202,  halfLife: '73.83 d',  energy: '0.31–0.60 MeV γ (avg 0.37 MeV)', hvl: '2.5 mm Pb', activity: 'Up to ~12 TBq', shielding: 'Lead ≥ 60 mm', uses: 'HDR brachytherapy, pipeline radiography, weld inspection', hazard: 'High — common in radiography accidents', color: 'text-blue-400', transport: 'Type B(U) — must remain in projector', refDoseRate: 59 },
  { name: 'Am-241', z: 95, a: 241, halfLifeYears: 432.2,  halfLife: '432.2 y',  energy: '59.5 keV γ + α 5.49 MeV', hvl: '0.2 mm Pb', activity: 'kBq–GBq', shielding: 'Thin Pb (γ) + sealed source for α', uses: 'Smoke detectors, gauging, XRF, neutron source (Am-Be)', hazard: 'Moderate — inhalation risk if unsealed', color: 'text-green-400', transport: 'Type A or excepted package', refDoseRate: 3 },
  { name: 'Cf-252', z: 98, a: 252, halfLifeYears: 2.645,  halfLife: '2.645 y',  energy: 'Spontaneous fission neutrons ~2.3 MeV avg', hvl: '10 cm polyethylene', activity: 'μg–mg quantities', shielding: 'Polyethylene + lead + borated water', uses: 'Neutron startup sources, PFTNA, downhole logging, cancer therapy', hazard: 'Very high — neutron + γ; criticality possible in quantity', color: 'text-purple-400', transport: 'Type B(U) — criticality control required', refDoseRate: 180 },
  { name: 'Sr-90',  z: 38, a: 90,  halfLifeYears: 28.8,   halfLife: '28.8 y',   energy: 'β 0.546 MeV → Y-90 β 2.28 MeV', hvl: 'Bremsstrahlung; few mm Al', activity: 'MBq–GBq', shielding: 'Low-Z material (plastic/Al) for β; lead for bremsstrahlung', uses: 'Thickness gauges, ophthalmic applicators, calibration', hazard: 'Moderate — bone seeker; β burn hazard', color: 'text-pink-400', transport: 'Type A package', refDoseRate: 20 },
  { name: 'Ra-226', z: 88, a: 226, halfLifeYears: 1600,   halfLife: '1600 y',   energy: '0.186 MeV γ + α; radon gas daughter', hvl: '16 mm Pb', activity: 'Legacy sources only', shielding: 'Lead ≥ 100 mm; radon containment essential', uses: 'Historical brachytherapy; legacy gauges (mostly replaced)', hazard: 'Very high — radon emanation, chemotoxic', color: 'text-red-400', transport: 'Type B(U) — sealed source verification required', refDoseRate: 210 },
];

// ─── Industrial energy tiers ──────────────────────────────────────────────────
const INDUSTRIAL_ENERGIES = [
  { kv: '160 kV', source: 'X-ray tube',          pen: 'Up to 25 mm steel',  app: 'Light alloys, plastics, thin welds, electronics PCBs',        quality: 'Excellent — high contrast', keV: 160 },
  { kv: '225 kV', source: 'X-ray tube',          pen: 'Up to 40 mm steel',  app: 'General weld inspection, casting, aerospace',                  quality: 'Good — fine focal spot', keV: 225 },
  { kv: '320 kV', source: 'X-ray tube',          pen: 'Up to 60 mm steel',  app: 'Pressure vessels, heavy castings, shipbuilding',               quality: 'Good, scatter increasing', keV: 320 },
  { kv: '450 kV', source: 'X-ray tube (comet)',  pen: 'Up to 90 mm steel',  app: 'Thick-walled pressure vessels, nuclear components',            quality: 'Moderate scatter; IQI essential', keV: 450 },
  { kv: '750 kV', source: 'Resonant transformer',pen: 'Up to 120 mm steel', app: 'Heavy industry, bridge fabrication, storage tanks',            quality: 'Scatter critical; geometry essential', keV: 750 },
  { kv: '1 MeV',  source: 'Betatron / LINAC',   pen: 'Up to 150 mm steel', app: 'Large castings, rocket motor casings, ordnance',              quality: 'Flash radiography possible', keV: 1000 },
  { kv: '3 MeV',  source: 'LINAC',              pen: 'Up to 250 mm steel', app: 'Heavy concrete, spent fuel assemblies, armour',               quality: 'Compton dominant; digital required', keV: 3000 },
  { kv: '6–9 MeV',source: 'LINAC (cargo)',       pen: 'Up to 350+ mm steel',app: 'Cargo screening, vehicle scanning, container inspection',       quality: 'Dual-energy for discrimination', keV: 7500 },
];

// ─── Source comparison data ───────────────────────────────────────────────────
const SOURCE_COMPARISON = [
  { name: 'X-ray Tube', minKeV: 20, maxKeV: 450, type: 'Electronic', color: '#3b82f6', brightness: 7, portability: 9, cost: 6 },
  { name: 'LINAC',      minKeV: 1000, maxKeV: 25000, type: 'Accelerator', color: '#8b5cf6', brightness: 9, portability: 4, cost: 2 },
  { name: 'Betatron',   minKeV: 15000, maxKeV: 300000, type: 'Accelerator', color: '#ec4899', brightness: 5, portability: 2, cost: 4 },
  { name: 'Cyclotron',  minKeV: 10000, maxKeV: 500000, type: 'Accelerator', color: '#10b981', brightness: 8, portability: 3, cost: 2 },
  { name: 'Synchrotron',minKeV: 1, maxKeV: 300000, type: 'Accelerator', color: '#06b6d4', brightness: 10, portability: 1, cost: 1 },
  { name: 'Van de Graaff',minKeV: 500, maxKeV: 25000, type: 'Electrostatic', color: '#eab308', brightness: 3, portability: 4, cost: 5 },
  { name: 'Co-60',      minKeV: 1170, maxKeV: 1330, type: 'Isotope', color: '#f97316', brightness: 4, portability: 6, cost: 7 },
  { name: 'Cs-137',     minKeV: 662, maxKeV: 662, type: 'Isotope', color: '#f59e0b', brightness: 3, portability: 7, cost: 7 },
  { name: 'Ir-192',     minKeV: 310, maxKeV: 600, type: 'Isotope', color: '#60a5fa', brightness: 4, portability: 8, cost: 7 },
  { name: 'D-T Neutron',minKeV: 14100, maxKeV: 14100, type: 'Neutron', color: '#ef4444', brightness: 5, portability: 7, cost: 6 },
];

// ─── Quiz data ────────────────────────────────────────────────────────────────
// ─── Shielding materials ──────────────────────────────────────────────────────
const SHIELD_MATERIALS = [
  { id: 'pb',   label: 'Lead (Pb)',          density: 11.34, mu100: 5.4,  mu500: 1.7,  mu1000: 0.77, mu3000: 0.47, color: '#94a3b8', hvl100: 0.13, hvl500: 0.41, hvl1000: 0.90, hvl3000: 1.47 },
  { id: 'fe',   label: 'Steel (Fe)',          density: 7.87,  mu100: 1.96, mu500: 0.60, mu1000: 0.40, mu3000: 0.29, color: '#6b7280', hvl100: 0.35, hvl500: 1.16, hvl1000: 1.73, hvl3000: 2.39 },
  { id: 'conc', label: 'Concrete',            density: 2.35,  mu100: 0.59, mu500: 0.20, mu1000: 0.14, mu3000: 0.10, color: '#d4d4aa', hvl100: 1.17, hvl500: 3.47, hvl1000: 4.95, hvl3000: 6.93 },
  { id: 'water',label: 'Water',               density: 1.00,  mu100: 0.17, mu500: 0.10, mu1000: 0.07, mu3000: 0.05, color: '#3b82f6', hvl100: 4.08, hvl500: 6.93, hvl1000: 9.90, hvl3000:13.86 },
  { id: 'pe',   label: 'Polyethylene (HDPE)', density: 0.96,  mu100: 0.15, mu500: 0.09, mu1000: 0.07, mu3000: 0.05, color: '#10b981', hvl100: 4.62, hvl500: 7.70, hvl1000: 9.90, hvl3000:13.86 },
];

// ═══════════════════════════════════════════════════════════════════════════════
// ─── Helper UI components ─────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

function ContentBlock({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      {title && <h3 className="text-base font-bold text-foreground mb-3 border-b border-border pb-2">{title}</h3>}
      <div className="text-sm text-muted-foreground leading-relaxed space-y-3">{children}</div>
    </div>
  );
}

function SpecTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-card/80">
            {headers.map(h => <th key={h} className="text-left px-3 py-2 font-semibold text-foreground border-b border-border">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={i % 2 === 0 ? 'bg-background/40' : 'bg-card/30'}>
              {row.map((cell, j) => <td key={j} className="px-3 py-2 text-muted-foreground border-b border-border/50">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InfoCard({ label, value, color = 'text-primary', sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div className="bg-card/60 border border-border rounded-lg p-3">
      <div className={`text-sm font-bold font-mono ${color}`}>{value}</div>
      <div className="text-[11px] text-foreground font-medium">{label}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function AlertBox({ type, children }: { type: 'warning' | 'info' | 'danger'; children: React.ReactNode }) {
  const styles = { warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-200', info: 'bg-blue-500/10 border-blue-500/30 text-blue-200', danger: 'bg-red-500/10 border-red-500/30 text-red-200' };
  const icons = { warning: '⚠', info: 'ℹ', danger: '☢' };
  return (
    <div className={`border rounded-lg px-4 py-3 text-sm flex gap-3 items-start ${styles[type]}`}>
      <span className="text-base shrink-0 mt-0.5">{icons[type]}</span>
      <span>{children}</span>
    </div>
  );
}

// ─── Knowledge Quiz component ─────────────────────────────────────────────────
function SectionQuiz({ questions }: { questions: QuizQuestion[] }) {
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [score, setScore] = useState(0);
  const [done, setDone] = useState(false);
  const [answers, setAnswers] = useState<(number | null)[]>(Array(questions.length).fill(null));

  const q = questions[current];
  const isAnswered = selected !== null;

  const handleSelect = (idx: number) => {
    if (isAnswered) return;
    setSelected(idx);
    const newAnswers = [...answers];
    newAnswers[current] = idx;
    setAnswers(newAnswers);
    if (idx === q.answer) setScore(s => s + 1);
  };

  const handleNext = () => {
    if (current < questions.length - 1) {
      setCurrent(c => c + 1);
      setSelected(answers[current + 1]);
    } else {
      setDone(true);
    }
  };

  const handleReset = () => {
    setCurrent(0); setSelected(null); setScore(0); setDone(false);
    setAnswers(Array(questions.length).fill(null));
  };

  if (done) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <div className="bg-card/60 border border-border rounded-xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${pct >= 75 ? 'bg-emerald-500/10 ring-1 ring-emerald-500/30' : 'bg-yellow-500/10 ring-1 ring-yellow-500/30'}`}>
            {pct >= 75 ? <CheckCircle2 className="h-6 w-6 text-emerald-400" /> : <HelpCircle className="h-6 w-6 text-yellow-400" />}
          </div>
          <div>
            <div className="font-bold text-foreground text-lg">{score}/{questions.length} correct — {pct}%</div>
            <div className="text-sm text-muted-foreground">{pct >= 75 ? 'Excellent! You have strong mastery of this topic.' : pct >= 50 ? 'Good effort — review the explanations below.' : 'Review the section content and try again.'}</div>
          </div>
        </div>
        <div className="space-y-2">
          {questions.map((qq, i) => (
            <div key={i} className={`rounded-lg border px-3 py-2 text-xs ${answers[i] === qq.answer ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
              <div className="flex items-start gap-2">
                {answers[i] === qq.answer ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" /> : <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />}
                <div>
                  <div className="font-medium text-foreground mb-0.5">{qq.q}</div>
                  <div className="text-muted-foreground">{qq.explanation}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={handleReset} className="gap-2"><RotateCcw className="h-3.5 w-3.5" /> Retry quiz</Button>
      </div>
    );
  }

  return (
    <div className="bg-card/60 border border-border rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HelpCircle className="h-4 w-4 text-primary" />
          <span className="font-bold text-sm text-foreground">Knowledge Check</span>
        </div>
        <span className="text-xs font-mono text-muted-foreground">Question {current + 1} / {questions.length}</span>
      </div>
      <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full transition-all duration-300" style={{ width: `${((current) / questions.length) * 100}%` }} />
      </div>
      <p className="text-sm font-medium text-foreground leading-relaxed">{q.q}</p>
      <div className="space-y-2">
        {q.options.map((opt, i) => {
          let cls = 'border-border/50 text-muted-foreground hover:border-border hover:text-foreground';
          if (isAnswered) {
            if (i === q.answer) cls = 'border-emerald-500 bg-emerald-500/10 text-emerald-300';
            else if (i === selected) cls = 'border-red-500 bg-red-500/10 text-red-300';
            else cls = 'border-border/30 text-muted-foreground/50';
          }
          return (
            <button key={i} onClick={() => handleSelect(i)}
              className={`w-full text-left text-xs px-3 py-2.5 rounded-lg border transition-all ${cls} ${!isAnswered ? 'cursor-pointer' : 'cursor-default'}`}>
              <span className="font-mono text-[10px] mr-2 opacity-60">{String.fromCharCode(65 + i)}.</span>{opt}
            </button>
          );
        })}
      </div>
      {isAnswered && (
        <div className={`rounded-lg px-3 py-2 text-xs ${selected === q.answer ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-200' : 'bg-red-500/10 border border-red-500/30 text-red-200'}`}>
          <span className="font-semibold">{selected === q.answer ? '✓ Correct! ' : '✗ Incorrect. '}</span>
          {q.explanation}
        </div>
      )}
      {isAnswered && (
        <Button size="sm" onClick={handleNext} className="gap-1.5">
          {current < questions.length - 1 ? 'Next question' : 'See results'} <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ─── Animated SVG Diagrams ────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

// ─── X-ray Tube ──────────────────────────────────────────────────────────────
function XrayTubeDiagram({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 3000) / 3000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);
  const ex = 120 + t * 260;
  const photons = [0.1, 0.3, 0.55, 0.8].map(phase => {
    const p = (t + phase) % 1;
    return { x: 385 + p * 100 * Math.sin((t + phase) * Math.PI * 0.5), y: 90 + p * 80 };
  });
  return (
    <svg viewBox="0 0 600 220" className="w-full max-w-2xl" style={{ fontFamily: 'monospace' }}>
      <rect x="80" y="40" width="400" height="120" rx="18" fill="#1e293b" stroke="#334155" strokeWidth="2" />
      <rect x="100" y="55" width="360" height="90" rx="10" fill="#0f172a" stroke="#1d4ed8" strokeWidth="1.5" strokeDasharray="4 3" />
      <rect x="108" y="72" width="30" height="46" rx="4" fill="#1e3a8a" stroke="#3b82f6" strokeWidth="1.5" />
      <text x="123" y="68" textAnchor="middle" fontSize="9" fill="#93c5fd">CATHODE</text>
      {[0,4,8,12,16].map(i => <ellipse key={i} cx="123" cy={82 + i * 6} rx="6" ry="2.5" fill="none" stroke="#f59e0b" strokeWidth="1.5" />)}
      <text x="123" y="128" textAnchor="middle" fontSize="7" fill="#fbbf24">filament</text>
      <path d="M 108 75 L 140 85 L 140 105 L 108 115 Z" fill="none" stroke="#60a5fa" strokeWidth="1" strokeDasharray="3 2" />
      <text x="145" y="100" fontSize="7" fill="#60a5fa">focusing cup</text>
      {animated && <circle cx={ex > 380 ? 380 : ex} cy={90} r="3.5" fill="#60a5fa" opacity={ex > 380 ? 0 : 0.9} />}
      {!animated && <line x1="138" y1="90" x2="378" y2="90" stroke="#60a5fa" strokeWidth="1.5" strokeDasharray="5 3" markerEnd="url(#arrow)" />}
      <defs><marker id="arrow" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 6 3 L 0 6 z" fill="#60a5fa" /></marker></defs>
      <rect x="370" y="60" width="50" height="80" rx="6" fill="#1a3a1a" stroke="#22c55e" strokeWidth="1.5" />
      <text x="395" y="56" textAnchor="middle" fontSize="9" fill="#86efac">ANODE</text>
      <polygon points="370,75 420,85 420,95 370,105" fill="#4b5563" stroke="#9ca3af" strokeWidth="1" />
      <text x="395" y="118" textAnchor="middle" fontSize="7" fill="#9ca3af">W target</text>
      <rect x="420" y="78" width="20" height="24" rx="2" fill="#0f172a" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="3 2" />
      <text x="450" y="78" fontSize="7" fill="#fbbf24">Be window</text>
      {photons.map((ph, i) => <circle key={i} cx={ph.x} cy={ph.y} r="2" fill="#fde047" opacity={animated ? 0.8 : 0} />)}
      {!animated && (<><line x1="440" y1="80" x2="510" y2="60" stroke="#fde047" strokeWidth="1.2" strokeDasharray="4 3" /><line x1="440" y1="90" x2="520" y2="90" stroke="#fde047" strokeWidth="1.2" strokeDasharray="4 3" /><line x1="440" y1="100" x2="510" y2="120" stroke="#fde047" strokeWidth="1.2" strokeDasharray="4 3" /><text x="520" y="88" fontSize="9" fill="#fde047">X-rays</text></>)}
      <circle cx="395" cy="90" r="8" fill="none" stroke="#6b7280" strokeWidth="1" strokeDasharray="3 3">
        {animated && <animateTransform attributeName="transform" type="rotate" from="0 395 90" to="360 395 90" dur="0.5s" repeatCount="indefinite" />}
      </circle>
      <text x="395" y="145" textAnchor="middle" fontSize="7" fill="#6b7280">rotating anode</text>
      <line x1="123" y1="160" x2="123" y2="180" stroke="#ef4444" strokeWidth="1.5" />
      <line x1="395" y1="160" x2="395" y2="180" stroke="#22c55e" strokeWidth="1.5" />
      <rect x="200" y="172" width="120" height="22" rx="4" fill="#1e293b" stroke="#475569" strokeWidth="1" />
      <text x="260" y="188" textAnchor="middle" fontSize="9" fill="#94a3b8">HIGH VOLTAGE GENERATOR</text>
      <line x1="123" y1="180" x2="200" y2="183" stroke="#ef4444" strokeWidth="1" />
      <line x1="395" y1="180" x2="320" y2="183" stroke="#22c55e" strokeWidth="1" />
      <text x="300" y="35" textAnchor="middle" fontSize="11" fill="#cbd5e1" fontWeight="bold">X-RAY TUBE — CROSS SECTION</text>
      {animated && <text x="300" y="210" textAnchor="middle" fontSize="8" fill="#4ade80">● LIVE: electrons accelerating cathode → anode → X-ray emission</text>}
    </svg>
  );
}

// ─── LINAC ───────────────────────────────────────────────────────────────────
function LinacDiagram({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) return;
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 4000) / 4000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);
  const beamX = 60 + t * 460;
  return (
    <svg viewBox="0 0 600 200" className="w-full max-w-2xl" style={{ fontFamily: 'monospace' }}>
      <text x="300" y="16" textAnchor="middle" fontSize="11" fill="#cbd5e1" fontWeight="bold">LINEAR ACCELERATOR (LINAC) — SCHEMATIC</text>
      <rect x="30" y="70" width="55" height="50" rx="6" fill="#1e293b" stroke="#7c3aed" strokeWidth="2" />
      <text x="57" y="90" textAnchor="middle" fontSize="8" fill="#c4b5fd">ELECTRON</text>
      <text x="57" y="102" textAnchor="middle" fontSize="8" fill="#c4b5fd">GUN</text>
      <rect x="90" y="80" width="200" height="30" rx="3" fill="#172554" stroke="#3b82f6" strokeWidth="1.5" />
      <text x="190" y="98" textAnchor="middle" fontSize="9" fill="#93c5fd">ACCELERATING WAVEGUIDE</text>
      {[0,1,2,3,4].map(i => <line key={i} x1={100 + i * 38} y1={80} x2={100 + i * 38} y2={110} stroke="#1d4ed8" strokeWidth="1" />)}
      <rect x="130" y="120" width="80" height="28" rx="4" fill="#1e293b" stroke="#a855f7" strokeWidth="1.5" />
      <text x="170" y="137" textAnchor="middle" fontSize="8" fill="#d8b4fe">MAGNETRON</text>
      <line x1="170" y1="120" x2="170" y2="110" stroke="#a855f7" strokeWidth="1.5" />
      <ellipse cx="320" cy="95" rx="28" ry="20" fill="#1a2e1a" stroke="#22c55e" strokeWidth="2" />
      <text x="320" y="93" textAnchor="middle" fontSize="8" fill="#86efac">BENDING</text>
      <text x="320" y="104" textAnchor="middle" fontSize="8" fill="#86efac">MAGNET</text>
      <line x1="320" y1="115" x2="320" y2="155" stroke="#4ade80" strokeWidth="2" strokeDasharray="3 2" />
      <rect x="296" y="155" width="48" height="14" rx="3" fill="#292524" stroke="#f59e0b" strokeWidth="1.5" />
      <text x="320" y="166" textAnchor="middle" fontSize="7" fill="#fbbf24">TARGET</text>
      <rect x="288" y="170" width="64" height="14" rx="3" fill="#1c1917" stroke="#94a3b8" strokeWidth="1.5" />
      <text x="320" y="181" textAnchor="middle" fontSize="7" fill="#94a3b8">COLLIMATOR</text>
      <polygon points="305,186 320,196 335,186" fill="#374151" stroke="#6b7280" strokeWidth="1" />
      {[0,1,2].map(i => <ellipse key={i} cx={108 + i * 60} cy={95} rx={16} ry={8} fill="none" stroke="#0ea5e9" strokeWidth="1" strokeDasharray="2 2" />)}
      {animated && <circle cx={beamX < 290 ? beamX : 320} cy={beamX < 290 ? 95 : 95 + (beamX - 290) * 0.7} r="3.5" fill="#818cf8" opacity="0.9" />}
      <line x1="320" y1="197" x2="320" y2="208" stroke="#fde047" strokeWidth="2" markerEnd="url(#ya)" />
      <defs><marker id="ya" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 6 3 L 0 6 z" fill="#fde047" /></marker></defs>
      <text x="335" y="207" fontSize="8" fill="#fde047">X-ray beam</text>
      <text x="30" y="168" fontSize="7" fill="#94a3b8">medical: 4–25 MV</text>
      <text x="30" y="178" fontSize="7" fill="#94a3b8">cargo: 3–9 MeV</text>
      <text x="30" y="188" fontSize="7" fill="#94a3b8">industrial: 1–15 MeV</text>
    </svg>
  );
}

// ─── Cyclotron Animated SVG ───────────────────────────────────────────────────
function CyclotronDiagram({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 5000) / 5000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  const cx = 300, cy = 110;
  // Spiral path: radius grows from 10 to 100 over multiple turns
  const numTurns = 5;
  const angle = t * numTurns * 2 * Math.PI;
  const radius = 10 + (t * 90);
  const px = cx + radius * Math.cos(angle);
  const py = cy + radius * Math.sin(angle);

  // Generate spiral path for display
  const spiralPoints: string[] = [];
  for (let i = 0; i <= 200; i++) {
    const a = (i / 200) * numTurns * 2 * Math.PI;
    const r = 10 + (i / 200) * 90;
    spiralPoints.push(`${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`);
  }
  const spiralPath = `M ${spiralPoints.join(' L ')}`;

  // Magnetic field dots (into page)
  const fieldDots = [];
  for (let x = 220; x <= 380; x += 25) {
    for (let y = 25; y <= 195; y += 25) {
      fieldDots.push({ x, y });
    }
  }

  return (
    <svg viewBox="0 0 600 220" className="w-full max-w-2xl" style={{ fontFamily: 'monospace' }}>
      <text x="300" y="14" textAnchor="middle" fontSize="11" fill="#cbd5e1" fontWeight="bold">CYCLOTRON — PARTICLE ACCELERATION</text>

      {/* Magnetic pole pieces */}
      <ellipse cx={cx} cy={cy} rx="105" ry="105" fill="#0f172a" stroke="#334155" strokeWidth="1.5" />
      <ellipse cx={cx} cy={cy} rx="105" ry="105" fill="none" stroke="#10b981" strokeWidth="2" />

      {/* Magnetic field dots (B into page) */}
      {fieldDots.map((d, i) => {
        const dist = Math.sqrt((d.x - cx) ** 2 + (d.y - cy) ** 2);
        if (dist > 100) return null;
        return <circle key={i} cx={d.x} cy={d.y} r="1.5" fill="#10b981" opacity="0.25" />;
      })}
      <text x="215" y="30" fontSize="8" fill="#6ee7b7" opacity="0.6">B ⊗ (into page)</text>

      {/* D-shaped electrodes (dees) */}
      {/* Left dee */}
      <path d={`M ${cx} ${cy - 90} A 90 90 0 0 0 ${cx} ${cy + 90} Z`} fill="#1e3a5f" stroke="#3b82f6" strokeWidth="2" opacity="0.7" />
      {/* Right dee */}
      <path d={`M ${cx} ${cy - 90} A 90 90 0 0 1 ${cx} ${cy + 90} Z`} fill="#1a2e1a" stroke="#22c55e" strokeWidth="2" opacity="0.7" />

      {/* Dee labels */}
      <text x={cx - 35} y={cy + 4} textAnchor="middle" fontSize="16" fill="#3b82f6" fontWeight="bold">D₁</text>
      <text x={cx + 35} y={cy + 4} textAnchor="middle" fontSize="16" fill="#22c55e" fontWeight="bold">D₂</text>

      {/* Gap (acceleration region) */}
      <line x1={cx} y1={cy - 95} x2={cx} y2={cy + 95} stroke="#fde047" strokeWidth="2" strokeDasharray="4 3" opacity="0.6" />
      <text x={cx + 4} y={cy - 97} fontSize="8" fill="#fde047">gap (E field)</text>

      {/* Spiral path (faint) */}
      {!animated && <path d={spiralPath} fill="none" stroke="#60a5fa" strokeWidth="1" opacity="0.35" />}
      {animated && (
        <>
          <path d={spiralPath} fill="none" stroke="#60a5fa" strokeWidth="1" opacity="0.2" />
          <circle cx={px} cy={py} r="4" fill="#60a5fa" opacity="0.95">
            <animate attributeName="opacity" values="0.8;1;0.8" dur="0.5s" repeatCount="indefinite" />
          </circle>
          {/* Glow */}
          <circle cx={px} cy={py} r="8" fill="#60a5fa" opacity="0.15" />
        </>
      )}

      {/* Ion source at center */}
      <circle cx={cx} cy={cy} r="5" fill="#f59e0b" stroke="#fbbf24" strokeWidth="1" />
      <text x={cx} y={cy + 18} textAnchor="middle" fontSize="7" fill="#fbbf24">ion source</text>

      {/* Extraction channel */}
      <path d="M 390 95 Q 420 100 450 90" fill="none" stroke="#a78bfa" strokeWidth="2" strokeDasharray="4 3" />
      <text x="452" y="94" fontSize="8" fill="#a78bfa">beam exit</text>
      <polygon points="445,87 455,91 443,95" fill="#a78bfa" />

      {/* RF source */}
      <rect x="20" y="95" width="55" height="30" rx="5" fill="#1e293b" stroke="#f59e0b" strokeWidth="1.5" />
      <text x="47" y="108" textAnchor="middle" fontSize="7" fill="#fbbf24">RF source</text>
      <text x="47" y="119" textAnchor="middle" fontSize="7" fill="#fbbf24">(alternating)</text>
      <line x1="75" y1="110" x2="195" y2="110" stroke="#f59e0b" strokeWidth="1" strokeDasharray="3 3" />

      {/* Energy label */}
      <text x="300" y="210" textAnchor="middle" fontSize="8" fill="#6b7280">Cyclotron frequency: f = qB / 2πm   |   Particles gain energy at each gap crossing</text>
    </svg>
  );
}

// ─── Betatron Animated SVG ────────────────────────────────────────────────────
function BetatronDiagram({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 3500) / 3500);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  const cx = 300, cy = 110;
  const angle = t * 2 * Math.PI * 6; // 6 orbits per cycle
  const orbitR = 55 + t * 20;         // radius grows slightly as B ramps up
  const px = cx + orbitR * Math.cos(angle - Math.PI / 2);
  const py = cy + orbitR * Math.sin(angle - Math.PI / 2);

  return (
    <svg viewBox="0 0 600 220" className="w-full max-w-2xl" style={{ fontFamily: 'monospace' }}>
      <text x="300" y="14" textAnchor="middle" fontSize="11" fill="#cbd5e1" fontWeight="bold">BETATRON — ELECTROMAGNETIC INDUCTION ACCELERATOR</text>

      {/* Electromagnet top/bottom poles */}
      <ellipse cx={cx} cy={40} rx="130" ry="28" fill="#1e293b" stroke="#ec4899" strokeWidth="2" />
      <text x={cx} y={44} textAnchor="middle" fontSize="9" fill="#f9a8d4">N pole (above)</text>
      <ellipse cx={cx} cy={178} rx="130" ry="28" fill="#1e293b" stroke="#ec4899" strokeWidth="2" />
      <text x={cx} y={182} textAnchor="middle" fontSize="9" fill="#f9a8d4">S pole (below)</text>

      {/* Vacuum donut chamber */}
      <ellipse cx={cx} cy={cy} rx="85" ry="30" fill="none" stroke="#6366f1" strokeWidth="2.5" />
      <ellipse cx={cx} cy={cy} rx="85" ry="30" fill="#0f172a" stroke="#4f46e5" strokeWidth="1" />
      <ellipse cx={cx} cy={cy} rx="60" ry="18" fill="#1e293b" stroke="#334155" strokeWidth="1" />

      {/* Donut cross-section label */}
      <text x={cx + 90} y={cy + 4} fontSize="9" fill="#818cf8">vacuum</text>
      <text x={cx + 90} y={cy + 15} fontSize="9" fill="#818cf8">donut</text>

      {/* Equilibrium orbit circle */}
      <ellipse cx={cx} cy={cy} rx="72" ry="24" fill="none" stroke="#ec4899" strokeWidth="1" strokeDasharray="5 3" opacity="0.5" />
      <text x={cx} y={cy - 27} textAnchor="middle" fontSize="7" fill="#f9a8d4">equilibrium orbit</text>

      {/* Animated electron */}
      {animated && (
        <circle cx={px} cy={py} r="4" fill="#ec4899" opacity="0.95">
          <animate attributeName="r" values="3.5;5;3.5" dur="0.4s" repeatCount="indefinite" />
        </circle>
      )}
      {!animated && (
        <ellipse cx={cx} cy={cy} rx="72" ry="24" fill="none" stroke="#ec4899" strokeWidth="2" opacity="0.7" />
      )}

      {/* Increasing B field arrows */}
      {[245, 285, 325, 365].map(x => (
        <g key={x}>
          <line x1={x} y1={55} x2={x} y2={80} stroke="#f9a8d4" strokeWidth="1" markerEnd="url(#barrow)" opacity="0.5" />
          <line x1={x} y1={140} x2={x} y2={165} stroke="#f9a8d4" strokeWidth="1" opacity="0.3" />
        </g>
      ))}
      <defs><marker id="barrow" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 6 3 L 0 6 z" fill="#f9a8d4" /></marker></defs>
      <text x={cx} y={93} textAnchor="middle" fontSize="7" fill="#f9a8d4" opacity="0.6">↑ B increasing</text>

      {/* Electron gun */}
      <rect x={cx - 8} y={cy - 6} width="16" height="12" rx="3" fill="#f59e0b" stroke="#fbbf24" strokeWidth="1" />
      <text x={cx} y={cy + 21} textAnchor="middle" fontSize="7" fill="#fbbf24">e-gun</text>

      {/* Target */}
      <rect x={cx + 70} y={cy - 6} width="14" height="12" rx="2" fill="#374151" stroke="#9ca3af" strokeWidth="1" />
      <text x={cx + 77} y={cy + 21} textAnchor="middle" fontSize="7" fill="#9ca3af">target</text>

      {/* X-ray beam */}
      <line x1={cx + 84} y1={cy} x2={cx + 130} y2={cy - 10} stroke="#fde047" strokeWidth="1.5" strokeDasharray="4 3" />
      <text x={cx + 132} y={cy - 8} fontSize="8" fill="#fde047">X-rays</text>

      <text x={cx} y={210} textAnchor="middle" fontSize="8" fill="#6b7280">Betatron condition: B̄(r₀) = 2B(r₀)  |  Energy via induced EMF from rising flux</text>
    </svg>
  );
}

// ─── Synchrotron Ring SVG ─────────────────────────────────────────────────────
function SynchrotronDiagram({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 3000) / 3000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  const cx = 290, cy = 110, ringR = 85;
  const angle = t * 2 * Math.PI;
  const px = cx + ringR * Math.cos(angle);
  const py = cy + ringR * Math.sin(angle);

  // Synchrotron radiation beam — emitted tangentially at each bending magnet
  const beamAngles = [0, Math.PI / 2, Math.PI, 3 * Math.PI / 2];

  // Bending magnets placed around ring
  const magnets = beamAngles.map(a => ({
    x: cx + ringR * Math.cos(a),
    y: cy + ringR * Math.sin(a),
    angle: a,
  }));

  return (
    <svg viewBox="0 0 600 220" className="w-full max-w-2xl" style={{ fontFamily: 'monospace' }}>
      <text x="300" y="14" textAnchor="middle" fontSize="11" fill="#cbd5e1" fontWeight="bold">SYNCHROTRON STORAGE RING — SCHEMATIC</text>

      {/* Storage ring guide */}
      <circle cx={cx} cy={cy} r={ringR + 12} fill="none" stroke="#334155" strokeWidth="14" />
      <circle cx={cx} cy={cy} r={ringR} fill="none" stroke="#06b6d4" strokeWidth="2" strokeDasharray="6 3" opacity="0.4" />

      {/* Bending magnets */}
      {magnets.map((m, i) => {
        const w = 24, h = 36;
        return (
          <g key={i} transform={`rotate(${(m.angle * 180) / Math.PI + 90} ${m.x} ${m.y})`}>
            <rect x={m.x - w / 2} y={m.y - h / 2} width={w} height={h} rx="4" fill="#1e3a5f" stroke="#06b6d4" strokeWidth="1.5" />
            <text x={m.x} y={m.y + 2} textAnchor="middle" fontSize="6" fill="#67e8f9">BM</text>
          </g>
        );
      })}

      {/* Undulator section (top arc) */}
      <path d={`M ${cx - 50} ${cy - ringR + 12} Q ${cx} ${cy - ringR - 8} ${cx + 50} ${cy - ringR + 12}`} fill="none" stroke="#a78bfa" strokeWidth="3" />
      <text x={cx} y={cy - ringR - 14} textAnchor="middle" fontSize="7" fill="#a78bfa">UNDULATOR</text>

      {/* RF cavity */}
      <rect x={cx + ringR - 18} y={cy - 10} width="22" height="20" rx="4" fill="#1a2e1a" stroke="#22c55e" strokeWidth="1.5" />
      <text x={cx + ringR + 14} y={cy + 2} fontSize="7" fill="#86efac">RF</text>
      <text x={cx + ringR + 14} y={cy + 11} fontSize="7" fill="#86efac">cav.</text>

      {/* Animated particle bunch */}
      {animated && (
        <>
          <circle cx={px} cy={py} r="5" fill="#06b6d4" opacity="0.9">
            <animate attributeName="opacity" values="0.7;1;0.7" dur="0.4s" repeatCount="indefinite" />
          </circle>
          <circle cx={px} cy={py} r="10" fill="#06b6d4" opacity="0.15" />
          {/* Synchrotron light emitted tangentially */}
          {[0, 1, 2].map(j => {
            const angleOffset = (j - 1) * 0.15;
            const tangAngle = angle + Math.PI / 2 + angleOffset;
            return (
              <line key={j}
                x1={px} y1={py}
                x2={px + 30 * Math.cos(tangAngle)}
                y2={py + 30 * Math.sin(tangAngle)}
                stroke="#fde047" strokeWidth={j === 1 ? 1.5 : 0.8} opacity={j === 1 ? 0.8 : 0.4} strokeDasharray="3 2"
              />
            );
          })}
        </>
      )}
      {!animated && (
        <circle cx={cx} cy={cy} r={ringR} fill="none" stroke="#06b6d4" strokeWidth="2.5" opacity="0.5" />
      )}

      {/* Synchrotron radiation beamlines */}
      {beamAngles.map((a, i) => {
        const bx = cx + (ringR + 30) * Math.cos(a);
        const by = cy + (ringR + 30) * Math.sin(a);
        const ex = cx + (ringR + 85) * Math.cos(a);
        const ey = cy + (ringR + 85) * Math.sin(a);
        return (
          <g key={i}>
            <line x1={bx} y1={by} x2={ex} y2={ey} stroke="#fde047" strokeWidth="1.2" strokeDasharray="3 2" opacity="0.5" />
          </g>
        );
      })}

      {/* Injector */}
      <rect x="445" y="100" width="55" height="28" rx="5" fill="#1e293b" stroke="#a855f7" strokeWidth="1.5" />
      <text x="472" y="116" textAnchor="middle" fontSize="8" fill="#d8b4fe">BOOSTER</text>
      <line x1="445" y1="114" x2={cx + ringR + 12} y2={cy + 5} stroke="#a855f7" strokeWidth="1" strokeDasharray="3 3" />

      <text x="295" y="208" textAnchor="middle" fontSize="8" fill="#6b7280">Brightness 10¹⁰× laboratory sources | Tuneable from IR to 300 keV hard X-rays</text>
    </svg>
  );
}

// ─── Van de Graaff SVG ────────────────────────────────────────────────────────
function VanDeGraaffDiagram({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 4000) / 4000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  // Belt charges move upward, 4 of them
  const chargePositions = [0, 0.25, 0.5, 0.75].map(offset => {
    const p = (t + offset) % 1; // 0 = bottom, 1 = back to bottom
    const goingUp = p < 0.5;
    const frac = goingUp ? p * 2 : (1 - p) * 2;
    return { y: 170 - frac * 130, visible: goingUp, x: goingUp ? 285 : 315 };
  });

  return (
    <svg viewBox="0 0 600 230" className="w-full max-w-2xl" style={{ fontFamily: 'monospace' }}>
      <text x="300" y="14" textAnchor="middle" fontSize="11" fill="#cbd5e1" fontWeight="bold">VAN DE GRAAFF GENERATOR — ELECTROSTATIC ACCELERATION</text>

      {/* High voltage terminal (sphere) */}
      <ellipse cx="300" cy="48" rx="60" ry="38" fill="#1e3a1e" stroke="#eab308" strokeWidth="2.5" />
      <text x="300" y="42" textAnchor="middle" fontSize="10" fill="#fde047" fontWeight="bold">HIGH VOLTAGE</text>
      <text x="300" y="56" textAnchor="middle" fontSize="10" fill="#fde047" fontWeight="bold">TERMINAL</text>
      {/* Charge symbols on sphere */}
      {animated && [0, 60, 120, 180, 240, 300].map(a => {
        const sx = 300 + 62 * Math.cos((a * Math.PI) / 180);
        const sy = 48 + 40 * Math.sin((a * Math.PI) / 180);
        return <text key={a} x={sx} y={sy + 3} textAnchor="middle" fontSize="10" fill="#fde047" opacity="0.8">+</text>;
      })}

      {/* Column / insulating tube */}
      <rect x="281" y="86" width="38" height="100" rx="4" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
      <text x="250" y="132" fontSize="8" fill="#64748b" textAnchor="middle">insulating</text>
      <text x="250" y="143" fontSize="8" fill="#64748b" textAnchor="middle">column</text>

      {/* Belt */}
      <line x1="290" y1="170" x2="290" y2="88" stroke="#f59e0b" strokeWidth="3" />
      <line x1="310" y1="88" x2="310" y2="170" stroke="#f59e0b" strokeWidth="3" />

      {/* Rollers */}
      <ellipse cx="300" cy="86" rx="14" ry="6" fill="#1e293b" stroke="#94a3b8" strokeWidth="1.5" />
      <text x="330" y="90" fontSize="8" fill="#94a3b8">upper roller</text>
      <ellipse cx="300" cy="170" rx="14" ry="6" fill="#1e293b" stroke="#94a3b8" strokeWidth="1.5" />
      <text x="330" y="174" fontSize="8" fill="#94a3b8">lower roller</text>

      {/* Charge on belt */}
      {chargePositions.map((cp, i) => (
        cp.visible && (
          <text key={i} x={cp.x - 6} y={cp.y + 4} fontSize="11" fill="#fde047" opacity="0.9">+</text>
        )
      ))}

      {/* Charge comb / pickup */}
      {[0, 8, 16].map(i => <line key={i} x1={272} y1={85 + i * 3} x2={283} y2={85 + i * 3} stroke="#fde047" strokeWidth="1" />)}
      <text x="240" y="82" fontSize="7" fill="#fde047" textAnchor="middle">pickup</text>
      <text x="240" y="92" fontSize="7" fill="#fde047" textAnchor="middle">comb</text>

      {/* Spray comb at bottom */}
      {[0, 8, 16].map(i => <line key={i} x1={317} y1={163 + i * 3} x2={328} y2={163 + i * 3} stroke="#60a5fa" strokeWidth="1" />)}
      <text x="355" y="168" fontSize="7" fill="#60a5fa">spray comb</text>
      <text x="355" y="178" fontSize="7" fill="#60a5fa">(charging)</text>

      {/* Motor */}
      <rect x="268" y="182" width="64" height="24" rx="4" fill="#1e293b" stroke="#6b7280" strokeWidth="1.5" />
      <text x="300" y="199" textAnchor="middle" fontSize="9" fill="#94a3b8">MOTOR</text>

      {/* Ion beam (acceleration downward) */}
      <line x1="300" y1="48" x2="300" y2="82" stroke="#a78bfa" strokeWidth="1.5" strokeDasharray="3 2" />
      <text x="220" y="60" fontSize="8" fill="#a78bfa">accelerated</text>
      <text x="220" y="70" fontSize="8" fill="#a78bfa">ion beam</text>
      <line x1="248" y1="64" x2="278" y2="64" stroke="#a78bfa" strokeWidth="1" markerEnd="url(#vdarrow)" />
      <defs><marker id="vdarrow" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 6 3 L 0 6 z" fill="#a78bfa" /></marker></defs>

      {/* Terminal voltage label */}
      <text x="500" y="50" fontSize="8" fill="#fde047">0.5–25 MV</text>
      <text x="500" y="62" fontSize="8" fill="#fde047">terminal</text>

      <text x="300" y="218" textAnchor="middle" fontSize="8" fill="#6b7280">Tandem VdG: negative ions accelerate in, stripped mid-tube, positive ions accelerate out → 2× energy gain</text>
    </svg>
  );
}

// ─── Neutron Moderation Animation ─────────────────────────────────────────────
function NeutronModerationViz({ animated }: { animated: boolean }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animated) { setT(0); return; }
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 5000) / 5000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  // Neutron travels right, collides with H atoms, slows down
  const stages = [
    { x: 60, y: 100, v: 1.0, label: '14 MeV (fast)' },
    { x: 180, y: 100, v: 0.65, label: '~6 MeV' },
    { x: 300, y: 100, v: 0.4, label: '~1 MeV' },
    { x: 400, y: 100, v: 0.2, label: '~100 keV' },
    { x: 490, y: 100, v: 0.05, label: '0.025 eV (thermal)' },
  ];

  // Animated neutron position
  const nx = 60 + t * 450;
  const stageIdx = stages.findIndex(s => s.x > nx) - 1;
  const curStage = stages[Math.max(0, Math.min(stageIdx, stages.length - 1))];

  return (
    <svg viewBox="0 0 580 180" className="w-full max-w-2xl" style={{ fontFamily: 'monospace' }}>
      <text x="290" y="14" textAnchor="middle" fontSize="10" fill="#cbd5e1" fontWeight="bold">NEUTRON THERMALIZATION IN POLYETHYLENE MODERATOR</text>

      {/* Moderator block */}
      <rect x="45" y="60" width="490" height="80" rx="8" fill="#14532d" stroke="#166534" strokeWidth="2" opacity="0.4" />
      <text x="290" y="152" textAnchor="middle" fontSize="9" fill="#6ee7b7" opacity="0.8">Polyethylene moderator (hydrogen-rich)</text>

      {/* H nuclei */}
      {[110, 150, 200, 240, 280, 320, 360, 400, 440].map((x, i) => (
        <circle key={i} cx={x} cy={90 + (i % 3) * 12} r="5" fill="#0f172a" stroke="#10b981" strokeWidth="1.5" />
      ))}
      {[130, 170, 220, 260, 300, 340, 380, 420, 460].map((x, i) => (
        <circle key={i + 20} cx={x} cy={102 + (i % 2) * 12} r="5" fill="#0f172a" stroke="#10b981" strokeWidth="1.5" />
      ))}

      {/* Stage labels */}
      {stages.map((s, i) => (
        <g key={i}>
          <line x1={s.x} y1={55} x2={s.x} y2={65} stroke="#64748b" strokeWidth="1" />
          <text x={s.x} y={50} textAnchor="middle" fontSize="7" fill="#94a3b8">{s.label}</text>
        </g>
      ))}

      {/* Animated neutron */}
      {animated && (
        <circle cx={nx > 535 ? 535 : nx} cy={100} r={3 + curStage.v * 4} fill="#ef4444" opacity="0.9">
          <animate attributeName="opacity" values="0.8;1;0.8" dur="0.3s" repeatCount="indefinite" />
        </circle>
      )}
      {!animated && (
        <>
          {stages.map((s, i) => i < stages.length - 1 && (
            <line key={i} x1={s.x} y1={100} x2={stages[i + 1].x} y2={100} stroke="#ef4444" strokeWidth={1 + (1 - i * 0.2)} strokeDasharray="4 3" opacity="0.5" />
          ))}
          {stages.map((s, i) => (
            <circle key={i} cx={s.x} cy={100} r={3 + s.v * 4} fill="#ef4444" opacity="0.7" />
          ))}
        </>
      )}

      {/* Source */}
      <rect x="20" y="88" width="30" height="24" rx="5" fill="#1e293b" stroke="#ef4444" strokeWidth="1.5" />
      <text x="35" y="104" textAnchor="middle" fontSize="8" fill="#fca5a5">D-T</text>

      {/* Detector */}
      <rect x="535" y="88" width="35" height="24" rx="5" fill="#1e293b" stroke="#a78bfa" strokeWidth="1.5" />
      <text x="552" y="100" textAnchor="middle" fontSize="8" fill="#c4b5fd">He-3</text>
      <text x="552" y="110" textAnchor="middle" fontSize="8" fill="#c4b5fd">det.</text>
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ─── Interactive Calculators ──────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

// ─── Inverse Square Law Calculator ───────────────────────────────────────────
function InverseSquareLawCalc({ isoIndex }: { isoIndex: number }) {
  const [dist, setDist] = useState(1.0);
  const iso = ISOTOPES[isoIndex];

  const doseAtDist = (d: number) => iso.refDoseRate / (d * d);
  const safeDistFor = (limit: number) => Math.sqrt(iso.refDoseRate / limit);

  const chartData = useMemo(() => {
    const pts = [];
    for (let d = 0.1; d <= 10; d += 0.1) {
      pts.push({ d: parseFloat(d.toFixed(1)), dose: parseFloat((iso.refDoseRate / (d * d)).toFixed(2)) });
    }
    return pts;
  }, [iso.refDoseRate]);

  const currentDose = doseAtDist(dist);
  const controlled = safeDistFor(7.5);   // 7.5 μSv/h occupational
  const supervised = safeDistFor(2.5);
  const public_ = safeDistFor(0.5);      // 0.5 μSv/h public

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-foreground font-medium">Distance from source</span>
          <span className="font-mono text-cyan-400">{dist.toFixed(1)} m</span>
        </div>
        <Slider min={0.1} max={10} step={0.1} value={[dist]} onValueChange={([v]) => setDist(v)} className="[&>span]:bg-cyan-400" />
        <div className="flex justify-between text-[10px] text-muted-foreground font-mono"><span>0.1 m</span><span>10 m</span></div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Dose rate at distance" value={`${currentDose >= 100 ? currentDose.toFixed(0) : currentDose.toFixed(2)} μSv/h`} color="text-red-400" />
        <InfoCard label="Dose rate at 1 m (ref.)" value={`${iso.refDoseRate} μSv/h`} color="text-orange-400" sub="per GBq approx." />
        <InfoCard label="Controlled area limit (7.5)" value={`${controlled.toFixed(1)} m`} color="text-yellow-400" sub="≥ 7.5 μSv/h" />
        <InfoCard label="Public area limit (0.5)" value={`${public_.toFixed(1)} m`} color="text-green-400" sub="≥ 0.5 μSv/h" />
      </div>

      <div className="bg-card/60 border border-border rounded-xl p-4">
        <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">Dose rate vs distance — {iso.name}</h4>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 20, left: 15 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="d" label={{ value: 'Distance (m)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} />
            <YAxis label={{ value: 'μSv/h', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }} labelStyle={{ color: '#94a3b8' }} formatter={(v: any) => [`${v} μSv/h`, 'Dose rate']} labelFormatter={(d) => `${d} m`} />
            <ReferenceLine x={dist} stroke="#06b6d4" strokeDasharray="4 3" label={{ value: `${dist}m`, fill: '#06b6d4', fontSize: 9 }} />
            <ReferenceLine y={7.5} stroke="#eab308" strokeDasharray="3 3" label={{ value: 'Controlled', fill: '#eab308', fontSize: 8, position: 'insideTopRight' }} />
            <ReferenceLine y={0.5} stroke="#22c55e" strokeDasharray="3 3" label={{ value: 'Public', fill: '#22c55e', fontSize: 8, position: 'insideTopRight' }} />
            <Line type="monotone" dataKey="dose" stroke="#ef4444" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <TopicMedia topic="industrial-xray" />

      <AlertBox type="info">
        <strong>Inverse Square Law:</strong> Dose rate ∝ 1/d². Doubling distance reduces dose rate by 4×. This is the simplest and most effective radiation protection measure. Reference dose rates are approximate; always use calibrated instruments.
      </AlertBox>
    </div>
  );
}

// ─── Shielding Calculator ─────────────────────────────────────────────────────
function ShieldingCalc() {
  const [matIdx, setMatIdx] = useState(0);
  const [thickness, setThickness] = useState(5);
  const [energyIdx, setEnergyIdx] = useState(1); // 0=100keV, 1=500keV, 2=1MeV, 3=3MeV

  const energies = [
    { label: '100 keV', getMu: (m: typeof SHIELD_MATERIALS[0]) => m.mu100, getHvl: (m: typeof SHIELD_MATERIALS[0]) => m.hvl100 },
    { label: '500 keV', getMu: (m: typeof SHIELD_MATERIALS[0]) => m.mu500, getHvl: (m: typeof SHIELD_MATERIALS[0]) => m.hvl500 },
    { label: '1 MeV',  getMu: (m: typeof SHIELD_MATERIALS[0]) => m.mu1000, getHvl: (m: typeof SHIELD_MATERIALS[0]) => m.hvl1000 },
    { label: '3 MeV',  getMu: (m: typeof SHIELD_MATERIALS[0]) => m.mu3000, getHvl: (m: typeof SHIELD_MATERIALS[0]) => m.hvl3000 },
  ];

  const mat = SHIELD_MATERIALS[matIdx];
  const eng = energies[energyIdx];
  const mu = eng.getMu(mat);
  const hvl = eng.getHvl(mat);
  const transmission = Math.exp(-mu * thickness);
  const nHvl = thickness / hvl;
  const tvl = hvl * Math.log10(10) / Math.log(2);

  const chartData = useMemo(() => {
    const pts = [];
    for (let x = 0; x <= 60; x += 1) {
      pts.push({ x, T: Math.exp(-mu * x) * 100 });
    }
    return pts;
  }, [mu]);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="space-y-4 bg-card/60 border border-border rounded-xl p-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Shielding Parameters</h3>

          <div className="space-y-1.5">
            <span className="text-sm font-medium">Shield material</span>
            <div className="grid grid-cols-1 gap-1.5">
              {SHIELD_MATERIALS.map((m, i) => (
                <button key={m.id} onClick={() => setMatIdx(i)}
                  className={`text-xs px-3 py-2 rounded-lg border transition-all text-left flex items-center gap-2 ${matIdx === i ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ background: m.color }} />
                  <span className="font-medium">{m.label}</span>
                  <span className="ml-auto opacity-60 font-mono text-[10px]">ρ={m.density} g/cm³</span>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <span className="text-sm font-medium">Photon energy</span>
            <div className="grid grid-cols-2 gap-1.5">
              {energies.map((e, i) => (
                <button key={e.label} onClick={() => setEnergyIdx(i)}
                  className={`text-xs px-2 py-1.5 rounded-lg border transition-all ${energyIdx === i ? 'border-amber-500 bg-amber-500/10 text-amber-400' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                  {e.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-foreground font-medium">Thickness</span>
              <span className="font-mono text-emerald-400">{thickness} cm</span>
            </div>
            <Slider min={0} max={60} step={0.5} value={[thickness]} onValueChange={([v]) => setThickness(v)} className="[&>span]:bg-emerald-400" />
          </div>
        </div>

        <div className="space-y-3">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Results</h3>
          <div className="grid grid-cols-2 gap-3">
            <InfoCard label="Transmission" value={`${(transmission * 100).toFixed(2)}%`} color={transmission < 0.01 ? 'text-emerald-400' : transmission < 0.1 ? 'text-yellow-400' : 'text-red-400'} />
            <InfoCard label="Dose reduction" value={`${((1 - transmission) * 100).toFixed(2)}%`} color="text-blue-400" />
            <InfoCard label="HVL" value={`${hvl.toFixed(2)} cm`} color="text-cyan-400" sub="half-value layer" />
            <InfoCard label="TVL" value={`${tvl.toFixed(1)} cm`} color="text-violet-400" sub="tenth-value layer" />
            <InfoCard label="# of HVLs" value={`${nHvl.toFixed(1)} HVL`} color="text-orange-400" />
            <InfoCard label="Attenuation coeff." value={`${mu.toFixed(3)} cm⁻¹`} color="text-slate-400" sub="linear (narrow beam)" />
          </div>
        </div>
      </div>

      <div className="bg-card/60 border border-border rounded-xl p-4">
        <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">
          Transmission curve — {mat.label}, {energies[energyIdx].label}
        </h4>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={chartData} margin={{ top: 5, right: 20, bottom: 20, left: 15 }}>
            <defs>
              <linearGradient id="shieldGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#22c55e" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="x" label={{ value: 'Thickness (cm)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} />
            <YAxis label={{ value: 'Transmission %', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }} formatter={(v: any) => [`${v.toFixed(2)}%`, 'Transmission']} labelFormatter={(x) => `${x} cm`} />
            <ReferenceLine x={thickness} stroke="#06b6d4" strokeDasharray="4 3" label={{ value: `${thickness}cm`, fill: '#06b6d4', fontSize: 9 }} />
            <ReferenceLine y={50} stroke="#eab308" strokeDasharray="3 3" label={{ value: '50% (1 HVL)', fill: '#eab308', fontSize: 8, position: 'insideTopRight' }} />
            <ReferenceLine y={10} stroke="#a78bfa" strokeDasharray="3 3" label={{ value: '10% (1 TVL)', fill: '#a78bfa', fontSize: 8, position: 'insideTopRight' }} />
            <Area type="monotone" dataKey="T" stroke="#ef4444" fill="url(#shieldGrad)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── Radioactive Decay Curve ──────────────────────────────────────────────────
function DecayCurveViz({ isoIndex }: { isoIndex: number }) {
  const iso = ISOTOPES[isoIndex];
  const t12 = iso.halfLifeYears;
  const maxT = t12 * 5;

  const data = useMemo(() => {
    const pts = [];
    const steps = 60;
    for (let i = 0; i <= steps; i++) {
      const t = (i / steps) * maxT;
      pts.push({ t: parseFloat(t.toFixed(3)), A: parseFloat((100 * Math.pow(0.5, t / t12)).toFixed(3)) });
    }
    return pts;
  }, [t12, maxT]);

  const tUnit = t12 >= 1 ? 'years' : t12 >= (1 / 365) ? 'days' : 'hours';
  const tLabel = tUnit === 'years' ? 'Time (years)' : tUnit === 'days' ? 'Time (days)' : 'Time (hours)';

  return (
    <div className="bg-card/60 border border-border rounded-xl p-4">
      <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">
        Decay curve — {iso.name} (T½ = {iso.halfLife})
      </h4>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data} margin={{ top: 5, right: 20, bottom: 20, left: 15 }}>
          <defs>
            <linearGradient id="decayGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f97316" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#f97316" stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="t" label={{ value: tLabel, position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} />
          <YAxis label={{ value: 'Activity (%)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} domain={[0, 100]} />
          <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }} formatter={(v: any) => [`${v.toFixed(1)}%`, 'Activity']} />
          <ReferenceLine y={50} stroke="#eab308" strokeDasharray="4 3" label={{ value: '50% (1 T½)', fill: '#eab308', fontSize: 8, position: 'insideTopRight' }} />
          <ReferenceLine y={25} stroke="#94a3b8" strokeDasharray="3 3" label={{ value: '25% (2 T½)', fill: '#94a3b8', fontSize: 8, position: 'insideTopRight' }} />
          <ReferenceLine y={12.5} stroke="#64748b" strokeDasharray="3 3" label={{ value: '12.5% (3 T½)', fill: '#64748b', fontSize: 8, position: 'insideTopRight' }} />
          <Area type="monotone" dataKey="A" stroke="#f97316" fill="url(#decayGrad)" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Source Comparison Chart ──────────────────────────────────────────────────
function SourceComparisonChart() {
  const [metric, setMetric] = useState<'energy' | 'brightness' | 'portability'>('energy');

  const energyData = SOURCE_COMPARISON.map(s => ({
    name: s.name, min: s.minKeV, max: s.maxKeV, color: s.color, type: s.type,
  }));

  const qualityData = SOURCE_COMPARISON.map(s => ({
    name: s.name,
    brightness: s.brightness,
    portability: s.portability,
    cost: s.cost,
    color: s.color,
  }));

  return (
    <div className="space-y-6">
      <div className="flex gap-2 flex-wrap">
        {[['energy','Energy Range'], ['brightness','Brightness / Flux'], ['portability','Portability & Cost']].map(([k, label]) => (
          <button key={k} onClick={() => setMetric(k as any)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${metric === k ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
            {label}
          </button>
        ))}
      </div>

      {metric === 'energy' && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Photon/particle energy ranges for each source type (keV). Log scale shown.</p>
          <div className="space-y-2">
            {energyData.map(s => {
              const logMin = Math.log10(Math.max(s.min, 1));
              const logMax = Math.log10(s.max);
              const logRange = Math.log10(500000) - Math.log10(1);
              const leftPct = ((logMin - Math.log10(1)) / logRange) * 100;
              const widthPct = Math.max(1, ((logMax - logMin) / logRange) * 100);
              return (
                <div key={s.name} className="flex items-center gap-3">
                  <span className="text-xs w-32 text-right text-muted-foreground shrink-0">{s.name}</span>
                  <div className="flex-1 h-5 bg-muted/30 rounded relative overflow-hidden">
                    <div className="absolute h-full rounded"
                      style={{ left: `${leftPct}%`, width: `${widthPct}%`, background: s.color, opacity: 0.7 }} />
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground w-32 shrink-0">
                    {s.min >= 1000 ? `${(s.min/1000).toFixed(0)} MeV` : `${s.min} keV`} – {s.max >= 1000 ? `${(s.max/1000).toFixed(0)} MeV` : `${s.max} keV`}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-[10px] font-mono text-muted-foreground px-[128px]">
            <span>1 keV</span><span>10 keV</span><span>100 keV</span><span>1 MeV</span><span>10 MeV</span><span>100 MeV</span><span>500 MeV</span>
          </div>
        </div>
      )}

      {metric !== 'energy' && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {metric === 'brightness' ? 'Relative flux/brightness score (10 = best). Synchrotrons are 10¹⁰× laboratory sources.' : 'Portability (10 = fully portable) and relative cost-effectiveness (10 = lowest cost).'}
          </p>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={qualityData} margin={{ top: 5, right: 20, bottom: 60, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="name" angle={-35} textAnchor="end" tick={{ fill: '#64748b', fontSize: 9 }} interval={0} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} domain={[0, 10]} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }} />
              {metric === 'brightness' && (
                <Bar dataKey="brightness" name="Flux / Brightness" radius={[3,3,0,0]}>
                  {qualityData.map((d, i) => <Cell key={i} fill={d.color} fillOpacity={0.75} />)}
                </Bar>
              )}
              {metric === 'portability' && (
                <>
                  <Bar dataKey="portability" name="Portability" radius={[3,3,0,0]}>
                    {qualityData.map((d, i) => <Cell key={i} fill={d.color} fillOpacity={0.75} />)}
                  </Bar>
                  <Bar dataKey="cost" name="Cost-effectiveness" fill="#60a5fa" fillOpacity={0.4} radius={[3,3,0,0]} />
                </>
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Most portable', value: 'Ir-192 / X-ray tube', color: 'text-blue-400' },
          { label: 'Highest brightness', value: 'Synchrotron X-FEL', color: 'text-cyan-400' },
          { label: 'Widest energy range', value: 'Synchrotron', color: 'text-cyan-400' },
          { label: 'Most cost-effective', value: 'X-ray tube', color: 'text-blue-400' },
        ].map(c => <InfoCard key={c.label} label={c.label} value={c.value} color={c.color} />)}
      </div>
    </div>
  );
}

// ─── Virtual Lab (X-ray spectrum simulator) ───────────────────────────────────
const TARGET_MATERIALS: Record<string, { Z: number; label: string; kEdge: number; color: string }> = {
  W:  { Z: 74, label: 'Tungsten (W)',    kEdge: 69.5, color: '#94a3b8' },
  Mo: { Z: 42, label: 'Molybdenum (Mo)', kEdge: 20.0, color: '#c084fc' },
  Rh: { Z: 45, label: 'Rhodium (Rh)',    kEdge: 23.2, color: '#f87171' },
  Cu: { Z: 29, label: 'Copper (Cu)',     kEdge: 8.98, color: '#fb923c' },
};
const FILTER_OPTIONS = [
  { id: 'none', label: 'No filter', mu: 0 },
  { id: 'al1',  label: 'Al 1 mm',  mu: 0.06 },
  { id: 'al3',  label: 'Al 3 mm',  mu: 0.15 },
  { id: 'cu05', label: 'Cu 0.5mm', mu: 0.45 },
  { id: 'cu1',  label: 'Cu 1 mm',  mu: 0.75 },
];

function computeSpectrum(kVp: number, mA: number, targetMat: string, filterIdx: number) {
  const mat = TARGET_MATERIALS[targetMat];
  const filt = FILTER_OPTIONS[filterIdx];
  const points: { E: number; I: number }[] = [];
  for (let E = 5; E <= kVp; E += 2) {
    let I = mat.Z * (kVp - E) / (E * E);
    if (mat.kEdge > 0 && kVp > mat.kEdge) {
      const peak1 = mat.kEdge * 0.84;
      const peak2 = mat.kEdge * 0.87;
      I += 6 * Math.exp(-((E - peak1) ** 2) / 4) * mA / 500;
      I += 3 * Math.exp(-((E - peak2) ** 2) / 4) * mA / 500;
    }
    I *= Math.exp(-filt.mu * E / kVp);
    I *= mA / 200;
    points.push({ E, I: Math.max(0, I) });
  }
  return points;
}

function VirtualLab() {
  const [kVp, setKVp] = useState(120);
  const [mA, setMA] = useState(300);
  const [targetMat, setTargetMat] = useState('W');
  const [filterIdx, setFilterIdx] = useState(0);
  const [tab, setTab] = useState<'spectrum' | 'shielding'>('spectrum');

  const spectrum = useMemo(() => computeSpectrum(kVp, mA, targetMat, filterIdx), [kVp, mA, targetMat, filterIdx]);
  const hvlPb = (0.693 / (0.0585 * (kVp / 100) ** 1.7)).toFixed(1);
  const hvlAl = (0.693 / (0.0034 * (kVp / 100) ** (-2.1) + 0.001)).toFixed(1);
  const output = (0.0054 * kVp ** 2 * mA / 1000).toFixed(1);
  const penMmAl = (0.12 * kVp + 5).toFixed(0);
  const mat = TARGET_MATERIALS[targetMat];

  return (
    <div className="space-y-5">
      <div className="flex gap-2">
        {[['spectrum','X-ray Spectrum'], ['shielding','Shielding Calc']].map(([k, label]) => (
          <button key={k} onClick={() => setTab(k as any)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${tab === k ? 'border-amber-500 bg-amber-500/10 text-amber-400' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'spectrum' && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="space-y-4 bg-card/60 border border-border rounded-xl p-5">
              <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Beam Parameters</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm"><span className="font-medium">Tube Voltage (kVp)</span><span className="font-mono text-yellow-400">{kVp} kV</span></div>
                <Slider min={40} max={150} step={1} value={[kVp]} onValueChange={([v]) => setKVp(v)} className="[&>span]:bg-yellow-400" />
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm"><span className="font-medium">Tube Current (mA)</span><span className="font-mono text-blue-400">{mA} mA</span></div>
                <Slider min={50} max={1200} step={50} value={[mA]} onValueChange={([v]) => setMA(v)} className="[&>span]:bg-blue-400" />
              </div>
              <div className="space-y-2">
                <span className="text-sm font-medium">Target Material</span>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(TARGET_MATERIALS).map(([k, v]) => (
                    <button key={k} onClick={() => setTargetMat(k)}
                      className={`text-xs px-3 py-2 rounded-lg border transition-all text-left ${targetMat === k ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                      <span className="font-mono">{v.label}</span>
                      <span className="block text-[10px] opacity-60">Z={v.Z}, K={v.kEdge} keV</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <span className="text-sm font-medium">Filtration</span>
                <div className="flex flex-wrap gap-2">
                  {FILTER_OPTIONS.map((f, i) => (
                    <button key={f.id} onClick={() => setFilterIdx(i)}
                      className={`text-xs px-2 py-1 rounded border transition-all ${filterIdx === i ? 'border-emerald-500 bg-emerald-500/10 text-emerald-400' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Computed Beam Properties</h3>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Max energy',  value: `${kVp} keV`,       sub: 'bremsstrahlung endpoint', color: 'text-yellow-400' },
                  { label: 'Output (1 m)',value: `${output} mGy/min`, sub: 'approx air kerma',        color: 'text-orange-400' },
                  { label: 'HVL (Pb)',    value: `${hvlPb} mm`,       sub: 'half-value layer, lead',  color: 'text-blue-400' },
                  { label: 'HVL (Al)',    value: `${hvlAl} mm`,       sub: 'half-value layer, Al',    color: 'text-teal-400' },
                  { label: 'Penetration', value: `~${penMmAl} mm Al`, sub: 'practical range estimate', color: 'text-green-400' },
                  { label: 'K-edge',      value: `${mat.kEdge} keV`,  sub: mat.label,                color: 'text-violet-400' },
                ].map(m => <InfoCard key={m.label} label={m.label} value={m.value} sub={m.sub} color={m.color} />)}
              </div>
              <div className="bg-card/40 border border-border rounded-lg p-3 text-xs text-muted-foreground leading-relaxed">
                <span className="font-semibold text-foreground">Note: </span>Approximate values from Kramers' rule and empirical HVL models. Use calibrated ionisation chambers per IEC 61267 / IAEA TRS 398 for regulatory measurements.
              </div>
            </div>
          </div>

          <div className="bg-card/60 border border-border rounded-xl p-5">
            <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground mb-4">
              X-ray Spectrum — {TARGET_MATERIALS[targetMat].label} target, {kVp} kVp, {FILTER_OPTIONS[filterIdx].label}
            </h3>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={spectrum} margin={{ top: 5, right: 20, bottom: 20, left: 10 }}>
                <defs><linearGradient id="specGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} /><stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05} /></linearGradient></defs>
                <XAxis dataKey="E" label={{ value: 'Energy (keV)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 11 }} tick={{ fill: '#64748b', fontSize: 10 }} />
                <YAxis label={{ value: 'Relative intensity', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }} labelStyle={{ color: '#94a3b8' }} formatter={(v: any) => [v.toFixed(3), 'I(E)']} labelFormatter={(e) => `${e} keV`} />
                {mat.kEdge < kVp && <ReferenceLine x={Math.round(mat.kEdge * 0.85)} stroke="#a78bfa" strokeDasharray="4 3" label={{ value: 'Kα', fill: '#a78bfa', fontSize: 10 }} />}
                <Area type="monotone" dataKey="I" stroke="#3b82f6" fill="url(#specGrad)" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {tab === 'shielding' && <ShieldingCalc />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ─── Section content ──────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

function XrayTubeContent() {
  const [animated, setAnimated] = useState(false);
  return (
    <div className="space-y-6">
      <div className="bg-card/40 border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Cross-Section Diagram</h3>
          <Button size="sm" variant="outline" onClick={() => setAnimated(a => !a)} className="gap-2 h-7">
            {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {animated ? 'Pause' : 'Animate'}
          </Button>
        </div>
        <XrayTubeDiagram animated={animated} />
      </div>

      <TopicMedia topic="xray-tube" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Typical kVp range" value="40–450 kV" color="text-yellow-400" />
        <InfoCard label="Anode rotation" value="3,000–10,800 RPM" color="text-blue-400" />
        <InfoCard label="Focal spot size" value="0.1–2.5 mm" color="text-green-400" />
        <InfoCard label="X-ray efficiency" value="~1% X-ray, 99% heat" color="text-orange-400" />
      </div>

      <ContentBlock title="Tube Construction">
        <p>An X-ray tube is a vacuum-sealed glass or metal/ceramic envelope in which electrons are accelerated from a heated cathode to a high-Z anode (target). The sudden deceleration of electrons in the Coulomb field of the anode nuclei produces bremsstrahlung radiation, while inner-shell ionisations produce characteristic X-rays at discrete energies determined by the target material.</p>
        <p>Modern rotating-anode tubes distribute the heat load over a large target track, allowing much higher instantaneous power than stationary-anode tubes. The anode disc (typically rhenium-alloyed tungsten on a molybdenum substrate) rotates at 3,000–10,800 RPM on ball bearings or electromagnetic bearings.</p>
      </ContentBlock>

      <ContentBlock title="Cathode Assembly">
        <p>The cathode comprises a tungsten filament heated by a low-voltage AC supply (~10 V, 3–5 A). Thermionic emission releases electrons according to the Richardson–Dushman equation. A focusing cup (Wehnelt electrode) creates an electrostatic lens that collimates the electron beam onto the anode focal spot.</p>
        <AlertBox type="warning">Filament aging: gradual evaporation of tungsten causes filament thinning and eventual failure. Mean life: 500–2,000 hours. Preheating below exposure temperatures extends life.</AlertBox>
      </ContentBlock>

      <ContentBlock title="Anode Target Materials">
        <SpecTable
          headers={['Material', 'Z', 'K-edge', 'Melting pt', 'Application']}
          rows={[
            ['Tungsten (W)',    '74', '69.5 keV', '3422 °C', 'General radiography, fluoroscopy, CT'],
            ['Molybdenum (Mo)', '42', '20.0 keV', '2623 °C', 'Mammography — optimal K-α for breast tissue'],
            ['Rhodium (Rh)',    '45', '23.2 keV', '1964 °C', 'Mammography — harder beams for dense breasts'],
            ['Copper (Cu)',     '29', '8.98 keV', '1085 °C', 'Low-energy XRF, some industrial applications'],
            ['Gold (Au)',       '79', '80.7 keV', '1064 °C', 'Transmission-target LINAC beamline'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="High Voltage Generation">
        <p>Modern generators use high-frequency inverter technology (&gt;40 kHz) with ripple &lt;1%. Older constant-potential generators use 12-pulse three-phase rectification. Single-phase units are limited to low-power dental/portable applications due to 100% ripple.</p>
        <AlertBox type="warning">AHU = kVp × mAs. Exceeding the tube rating causes anode cracking, bearing seizure, or envelope fracture. Always observe minimum cooling intervals in rapid-sequence protocols.</AlertBox>
      </ContentBlock>

      <ContentBlock title="Failure Modes & Troubleshooting">
        <SpecTable
          headers={['Failure', 'Symptoms', 'Cause', 'Action']}
          rows={[
            ['Filament open circuit', 'No exposure, tube current zero', 'Tungsten evaporation / mechanical shock', 'Replace tube insert'],
            ['Anode pitting / cracking', 'Image artefacts, focal spot distortion', 'Thermal overload / rapid cycling', 'Replace tube; review protocol'],
            ['Bearing seizure', 'Loud vibration, slow rotation alarm', 'Lubrication failure, contamination', 'Replace tube (bearings integral)'],
            ['Window contamination', 'Low kV filtration increase, soft beam', 'Tungsten deposit on Be window', 'Replace tube'],
            ['Oil contamination / arcing', 'Intermittent shut-down, sparks', 'Moisture ingress, oil degradation', 'Replace housing; inspect HV cables'],
          ]}
        />
      </ContentBlock>

      <AlertBox type="info"><strong>Standards:</strong> IEC 60613 (tube assemblies), IEC 60522 (inherent filtration), NCRP 102 (diagnostic imaging), IAEA Safety Series 115.</AlertBox>

      <SectionQuiz questions={TOPIC_QUIZZES['xray-tube']} />
    </div>
  );
}

function LinacContent() {
  const [animated, setAnimated] = useState(false);
  return (
    <div className="space-y-6">
      <div className="bg-card/40 border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">LINAC Schematic</h3>
          <Button size="sm" variant="outline" onClick={() => setAnimated(a => !a)} className="gap-2 h-7">
            {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {animated ? 'Pause' : 'Animate'}
          </Button>
        </div>
        <LinacDiagram animated={animated} />
      </div>

      <TopicMedia topic="linac" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Medical energy range" value="4–25 MV" color="text-violet-400" />
        <InfoCard label="Cargo inspection" value="3–9 MeV" color="text-blue-400" />
        <InfoCard label="Pulse width" value="1–5 μs" color="text-green-400" />
        <InfoCard label="Repetition rate" value="100–400 Hz" color="text-orange-400" />
      </div>

      <ContentBlock title="History">
        <p>Rolf Wideröe proposed the RF linear accelerator concept in 1928. Luis Alvarez built the first practical RF LINAC at Berkeley in 1945 (200 MeV protons). Medical electron LINACs entered clinical use in 1952 (Hammersmith Hospital, London). Industrial cargo inspection LINACs trace to Stanford Linear Accelerator Centre work of the 1960s–70s.</p>
      </ContentBlock>

      <ContentBlock title="Working Principle">
        <p>Electrons from a thermionic gun are injected into a travelling-wave or standing-wave RF accelerating structure. The oscillating EM field in the waveguide cavities applies successive voltage kicks to electron bunches, accelerating them to relativistic energies over 1–2 m. The beam then strikes a high-Z (W, Au) transmission target to produce bremsstrahlung X-rays.</p>
      </ContentBlock>

      <ContentBlock title="RF Power: Magnetron vs Klystron">
        <SpecTable
          headers={['Parameter', 'Magnetron', 'Klystron']}
          rows={[
            ['Power output', '2–5 MW peak (pulsed)', '5–50 MW peak'],
            ['Energy range', 'Up to ~10 MeV', '&gt;15 MeV possible'],
            ['Size / cost',  'Compact, lower cost', 'Larger, higher cost'],
            ['Stability',    'Phase/frequency jitter', 'Excellent stability'],
            ['Application',  '4–10 MeV medical/cargo', 'High-energy research, 15+ MeV'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="LINAC Applications by Energy">
        <SpecTable
          headers={['Energy', 'Application', 'Target thickness', 'Beam type']}
          rows={[
            ['4–6 MV',  'Medical radiotherapy (superficial)', '—', 'Photon'],
            ['6–10 MV', 'Medical radiotherapy (deep tumours)', '—', 'Photon'],
            ['15–25 MV','Medical radiotherapy (very deep)',    '—', 'Photon'],
            ['3–4 MeV', 'Industrial NDT, weld inspection',    '~200 mm steel', 'Photon'],
            ['6 MeV',   'Cargo screening (standard)',         '~300 mm steel', 'Pulsed photon'],
            ['9 MeV',   'Cargo screening (high penetration)', '~380 mm steel', 'Dual-energy'],
            ['15 MeV',  'Industrial flash radiography',       '~500 mm steel', 'Single-pulse'],
          ]}
        />
      </ContentBlock>

      <AlertBox type="danger">LINACs require primary barriers rated to several cm of lead-equivalent concrete. Interlocks include: door switches, emergency stops, arc detectors, dose monitoring chambers, and automatic shutdown at 110% set dose. All interlocks tested per IEC 60601-2-1 (medical) or IEC 60951 (industrial).</AlertBox>

      <SectionQuiz questions={TOPIC_QUIZZES['linac']} />
    </div>
  );
}

function BetatronContent() {
  const [animated, setAnimated] = useState(false);
  return (
    <div className="space-y-6">
      <div className="bg-card/40 border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Betatron — Induction Accelerator Animation</h3>
          <Button size="sm" variant="outline" onClick={() => setAnimated(a => !a)} className="gap-2 h-7">
            {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {animated ? 'Pause' : 'Animate'}
          </Button>
        </div>
        <BetatronDiagram animated={animated} />
      </div>

      <TopicMedia topic="betatron" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Energy range" value="15–300 MeV" color="text-pink-400" />
        <InfoCard label="Beam type" value="Electrons / X-rays" color="text-blue-400" />
        <InfoCard label="Inventor" value="D.W. Kerst, 1940" color="text-green-400" />
        <InfoCard label="Status" value="Largely superseded by LINAC" color="text-muted-foreground" />
      </div>

      <ContentBlock title="Construction & Operating Principle">
        <p>The betatron accelerates electrons in a circular orbit within a time-varying magnetic field. Electrons are injected from a gun at low energy and spiral within a doughnut-shaped vacuum chamber. The <strong className="text-foreground">betatron condition</strong> requires that the average magnetic field within the orbit be exactly twice the field at the orbit radius: B̄(r₀) = 2B(r₀).</p>
        <p>When electrons reach maximum energy, they are deflected onto a tungsten target at the orbit edge, producing bremsstrahlung X-rays. Energy is ultimately limited by synchrotron radiation losses at ~300 MeV for electrons.</p>
      </ContentBlock>

      <ContentBlock title="Comparison with LINAC">
        <SpecTable
          headers={['Parameter', 'Betatron', 'LINAC']}
          rows={[
            ['Energy',       '15–300 MeV', '1–25 MeV (practical)'],
            ['Pulse rate',   '~60 Hz (line-locked)', '100–400 Hz'],
            ['Dose rate',    'Moderate',   'High (up to 10 Gy/min)'],
            ['Portability',  'Not portable', 'Compact models available'],
            ['Maintenance',  'Simple (no RF system)', 'RF system maintenance required'],
            ['Cost',         'Lower',       'Higher'],
            ['Current use',  'Specialist NDT, increasingly rare', 'Standard industry & medical'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="Applications">
        <p>Betatrons were historically used for medical radiotherapy and industrial NDT of very thick steel sections (100–300 mm). Today they are largely replaced by LINACs, though they remain in some specialist NDT facilities requiring 100+ MeV for extremely thick components such as armour plate and heavy pressure vessel forgings where the lack of an RF system simplifies maintenance.</p>
      </ContentBlock>
    </div>
  );
}

function CyclotronContent() {
  const [animated, setAnimated] = useState(false);
  return (
    <div className="space-y-6">
      <div className="bg-card/40 border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Cyclotron — Particle Acceleration Animation</h3>
          <Button size="sm" variant="outline" onClick={() => setAnimated(a => !a)} className="gap-2 h-7">
            {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {animated ? 'Pause' : 'Animate'}
          </Button>
        </div>
        <CyclotronDiagram animated={animated} />
      </div>

      <TopicMedia topic="cyclotron" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Energy range" value="Up to ~500 MeV/u" color="text-emerald-400" />
        <InfoCard label="Invented" value="E.O. Lawrence, 1930" color="text-blue-400" />
        <InfoCard label="Key medical product" value="PET isotopes (F-18, C-11)" color="text-green-400" />
        <InfoCard label="Cyclotron frequency" value="f = qB / 2πm" color="text-orange-400" sub="Resonance condition" />
      </div>

      <ContentBlock title="Operating Principle">
        <p>Ions from a central source are accelerated in two D-shaped electrodes ("dees") by an alternating RF electric field. A perpendicular static magnetic field bends the ion trajectory into semicircles of increasing radius. The resonance condition requires that the RF frequency matches the cyclotron frequency: <strong className="text-foreground font-mono">f = qB / 2πm</strong>.</p>
        <p>At relativistic energies, increasing mass breaks the resonance condition — overcome in modern <strong className="text-foreground">isochronous cyclotrons</strong> by varying the magnetic field with radius to maintain synchronism.</p>
      </ContentBlock>

      <ContentBlock title="Medical Applications — PET Isotope Production">
        <SpecTable
          headers={['Isotope', 'Target', 'Reaction', 'Half-life', 'Use']}
          rows={[
            ['F-18',  'O-18 water',  '¹⁸O(p,n)¹⁸F',   '109.8 min', 'FDG-PET — most common PET tracer worldwide'],
            ['C-11',  'N-14 gas',    '¹⁴N(p,α)¹¹C',    '20.4 min',  'PET neurotransmitter studies, psychiatry'],
            ['N-13',  'O-16 water',  '¹⁶O(p,α)¹³N',    '9.97 min',  'Cardiac perfusion PET'],
            ['O-15',  'N-15 gas',    '¹⁵N(p,n)¹⁵O',    '2.04 min',  'Cerebral blood flow PET'],
            ['Ga-68', 'Ge-68 target','Generator-based', '67.6 min',  'Neuro-endocrine tumor PET'],
            ['Zr-89', 'Y-89 target', '⁸⁹Y(p,n)⁸⁹Zr',   '78.4 h',    'Immuno-PET, antibody imaging'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="Security & Industrial Use">
        <p>High-energy cyclotrons (100–500 MeV protons) produce spallation neutron sources and medical radionuclides (Mo-99, Tc-99m, I-131). Compact hospital cyclotrons (10–30 MeV) are increasingly self-shielded units installed in clinical facilities for on-site short-lived isotope production, eliminating dependence on reactor-based supply chains disrupted by maintenance shutdowns.</p>
      </ContentBlock>
    </div>
  );
}

function SynchrotronContent() {
  const [animated, setAnimated] = useState(false);
  return (
    <div className="space-y-6">
      <div className="bg-card/40 border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Synchrotron Storage Ring Animation</h3>
          <Button size="sm" variant="outline" onClick={() => setAnimated(a => !a)} className="gap-2 h-7">
            {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {animated ? 'Pause' : 'Animate'}
          </Button>
        </div>
        <SynchrotronDiagram animated={animated} />
      </div>

      <TopicMedia topic="synchrotron" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Typical energy" value="1–8 GeV (electron)" color="text-cyan-400" />
        <InfoCard label="Brightness" value="10¹⁰× lab source" color="text-blue-400" />
        <InfoCard label="Beam emittance" value="pm·rad range" color="text-green-400" />
        <InfoCard label="World facilities" value="ESRF, ALS, NSLS-II, SPring-8" color="text-orange-400" />
      </div>

      <ContentBlock title="Synchrotron Radiation">
        <p>When relativistic electrons are bent by dipole magnets in a storage ring, they emit synchrotron radiation across a broad spectrum from infrared to hard X-rays (&gt;100 keV). The radiation is highly collimated, linearly polarised, pulsed in time, and several orders of magnitude brighter than any laboratory X-ray source.</p>
      </ContentBlock>

      <ContentBlock title="Insertion Devices">
        <SpecTable
          headers={['Device', 'Type', 'Brightness', 'Spectrum', 'Application']}
          rows={[
            ['Bending magnet', 'Dipole',     'Baseline',              'Broad, continuous', 'White beam, wide energy range'],
            ['Wiggler',        'Periodic',   '~100× BM',              'Broad, high flux',  'High flux, wide energy range'],
            ['Undulator',      'Periodic',   '~10,000× BM',           'Quasi-monochromatic','High brightness, narrow peaks'],
            ['X-ray FEL',      'Long undulator','~10⁹× undulator','Coherent, ultrashort','Femtosecond pulses, CDI'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="Applications in Security & Industry">
        <p>Synchrotron X-ray sources enable: phase-contrast imaging of explosive composites, high-resolution CT of cultural heritage artefacts, XAFS spectroscopy for nuclear material speciation, and coherent diffraction imaging. For cargo security, synchrotron-based coherent scatter imaging discriminates materials with similar attenuation but different crystalline structures (e.g. explosives vs inert powders).</p>
      </ContentBlock>
    </div>
  );
}

function VanDeGraaffContent() {
  const [animated, setAnimated] = useState(false);
  return (
    <div className="space-y-6">
      <div className="bg-card/40 border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Van de Graaff Generator Animation</h3>
          <Button size="sm" variant="outline" onClick={() => setAnimated(a => !a)} className="gap-2 h-7">
            {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {animated ? 'Pause' : 'Animate'}
          </Button>
        </div>
        <VanDeGraaffDiagram animated={animated} />
      </div>

      <TopicMedia topic="van-de-graaff" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Voltage range" value="0.5–25 MV" color="text-yellow-400" />
        <InfoCard label="Beam type" value="Any ion species" color="text-blue-400" />
        <InfoCard label="Invented" value="R.J. Van de Graaff, 1929" color="text-green-400" />
        <InfoCard label="Current use" value="AMS, nuclear research, ion implant" color="text-orange-400" />
      </div>

      <ContentBlock title="Construction & Electrostatic Acceleration">
        <p>A motor-driven insulating belt (or Pelletron chain) transfers electric charge from a grounded base to an insulated metal sphere (terminal). Continuous charge transfer builds up a high static potential. Ions are then accelerated through the resulting potential gradient.</p>
        <p>In <strong className="text-foreground">tandem Van de Graaff</strong> accelerators, negative ions accelerated toward the positive terminal are stripped of electrons mid-way and then repelled (as positive ions) back to ground, gaining energy twice from the same terminal voltage — achieving 2–50 MeV beams from 1–25 MV terminals.</p>
      </ContentBlock>

      <ContentBlock title="Applications">
        <SpecTable
          headers={['Application', 'Energy range', 'Notes']}
          rows={[
            ['Nuclear cross-section measurements', '1–20 MeV', 'Precise, ultra-stable beam energy'],
            ['Ion implantation (semiconductor)', '0.1–5 MeV', 'High-purity doping profiles'],
            ['Accelerator mass spectrometry (AMS)', '0.5–10 MV', 'Carbon dating, ¹⁴C / ¹⁰Be / ²⁶Al isotope ratios'],
            ['Neutron production (T(p,n) reaction)', '2–4 MeV protons', 'Small-scale monoenergetic neutron source'],
            ['Nuclear resonance fluorescence (NRF)', '2–10 MeV', 'Non-destructive fissile material detection'],
          ]}
        />
      </ContentBlock>
    </div>
  );
}

function RadioisotopeContent() {
  const [selected, setSelected] = useState(0);
  const iso = ISOTOPES[selected];
  const [showDecay, setShowDecay] = useState(false);
  const [showISL, setShowISL] = useState(false);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {ISOTOPES.map((iso, i) => (
          <button key={iso.name} onClick={() => { setSelected(i); setShowDecay(false); setShowISL(false); }}
            className={`px-3 py-1.5 rounded-lg border text-sm font-mono font-semibold transition-all ${selected === i ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
            {iso.name}
          </button>
        ))}
      </div>

      <div className="bg-card/60 border border-border rounded-xl p-5">
        <div className="flex items-start gap-4 mb-5">
          <div className="bg-background border border-border rounded-lg p-3 font-mono text-center min-w-[72px]">
            <div className={`text-2xl font-bold ${iso.color}`}>{iso.name}</div>
            <div className="text-xs text-muted-foreground">Z={iso.z}, A={iso.a}</div>
          </div>
          <div className="flex-1">
            <h3 className={`text-xl font-bold ${iso.color} mb-1`}>{iso.name}</h3>
            <div className="flex flex-wrap gap-3 text-sm">
              <span className="text-muted-foreground">Half-life: <strong className="text-foreground">{iso.halfLife}</strong></span>
              <span className="text-muted-foreground">Radiation: <strong className="text-foreground">{iso.energy}</strong></span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
          <InfoCard label="HVL (approximate)" value={iso.hvl} />
          <InfoCard label="Typical activity" value={iso.activity} />
          <InfoCard label="Hazard level" value={iso.hazard} color={iso.color} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ContentBlock title="Shielding & Storage">
            <p>{iso.shielding}</p>
            <p className="text-xs">IAEA Category 1–3 sealed source. Secure storage per IAEA SSG-14; physical protection per NSS 23-G.</p>
          </ContentBlock>
          <ContentBlock title="Transport">
            <p>{iso.transport}</p>
            <p className="text-xs">Yellow-II or Yellow-III labelling per IAEA SSR-6/ADR. Transport index from 1 m dose rate.</p>
          </ContentBlock>
          <ContentBlock title="Industrial Applications"><p>{iso.uses}</p></ContentBlock>
          <ContentBlock title="Safety Procedures">
            <p>Shielded container at all times. Survey meter before and after use. Time–Distance–Shielding (TDS) principle. TLD or EPD dosimetry mandatory. Annual source leak test per IAEA RS-G-1.9.</p>
          </ContentBlock>
        </div>
      </div>

      <TopicMedia topic="radioisotopes" />

      {/* Interactive tools */}
      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant={showDecay ? 'default' : 'outline'} onClick={() => { setShowDecay(v => !v); setShowISL(false); }} className="gap-2 text-xs h-7">
          <TrendingDown className="h-3 w-3" /> {showDecay ? 'Hide' : 'Show'} Decay Curve
        </Button>
        <Button size="sm" variant={showISL ? 'default' : 'outline'} onClick={() => { setShowISL(v => !v); setShowDecay(false); }} className="gap-2 text-xs h-7">
          <Gauge className="h-3 w-3" /> {showISL ? 'Hide' : 'Show'} Distance Calculator
        </Button>
      </div>

      {showDecay && <DecayCurveViz isoIndex={selected} />}
      {showISL && <InverseSquareLawCalc isoIndex={selected} />}

      <AlertBox type="danger">All sealed sources must be registered with the national regulatory authority. Lost, stolen, or orphan sources must be reported immediately. Never attempt to open or dismantle a sealed source container.</AlertBox>

      <SectionQuiz questions={TOPIC_QUIZZES['radioisotopes']} />
    </div>
  );
}

function NeutronContent() {
  const [animated, setAnimated] = useState(false);
  return (
    <div className="space-y-6">
      <div className="bg-card/40 border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground">Neutron Thermalization — Moderation Animation</h3>
          <Button size="sm" variant="outline" onClick={() => setAnimated(a => !a)} className="gap-2 h-7">
            {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {animated ? 'Pause' : 'Animate'}
          </Button>
        </div>
        <NeutronModerationViz animated={animated} />
      </div>

      <TopicMedia topic="neutron" />

      <ContentBlock title="Neutron Source Types">
        <SpecTable
          headers={['Source', 'Reaction', 'Neutron energy', 'Yield', 'Application']}
          rows={[
            ['D-T generator',  'd + t → ⁴He + n',     '14.1 MeV (mono)',  '10⁸–10¹¹ n/s',   'Well logging, PFTNA, cargo screening'],
            ['D-D generator',  'd + d → ³He + n',      '2.45 MeV (mono)',  '10⁶–10⁹ n/s',    'Research, calibration'],
            ['Am-Be source',   '⁹Be(α,n)¹²C + Am-241', '0.1–11 MeV (cont)','10⁵–10⁶ n/s·GBq','Industrial, calibration, Am-Be'],
            ['Cf-252',         'Spontaneous fission',  '~2.3 MeV avg',     '2.3×10⁶ n/s·μg', 'Reactor start-up, BNCT, TNT'],
            ['Research reactor','²³⁵U fission',         'Thermal+epithermal','10¹²–10¹⁵ n/cm²s','Activation analysis, imaging'],
            ['Spallation (SNS)','p + W/Hg → spallation','Wide spectrum',    '10¹⁶ n/pulse',   'Scattering, fundamental research'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="D-T Generators in Cargo Inspection">
        <p>Pulsed fast neutron analysis (PFNA) and pulsed neutron activation (PNA) systems use D-T generators sealed into cargo container portals. 14 MeV neutrons activate elements in cargo, producing characteristic γ-ray signatures (N-14, C-12, O-16, Cl). Systems can distinguish explosives, narcotics, and chemical weapons from innocent cargo in &lt;60 second interrogation.</p>
      </ContentBlock>

      <ContentBlock title="Shielding & Detection">
        <p>Fast neutrons are best moderated by hydrogen-rich materials (polyethylene, water, paraffin), then captured in boron or cadmium. Thermal neutrons require 10–20 cm borated polyethylene. Personnel dosimetry uses track-etch dosimeters (CR-39) or neutron rem-meters.</p>
        <AlertBox type="warning">He-3 shortage since 2009: Li-6 and B-10 based detectors now preferred in cargo portal monitors per ANSI N42.43 standard.</AlertBox>
      </ContentBlock>

      <SectionQuiz questions={TOPIC_QUIZZES['neutron']} />
    </div>
  );
}

function GammaIrradiatorContent() {
  return (
    <div className="space-y-6">
      <TopicMedia topic="gamma-irradiators" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <InfoCard label="Max source activity" value="~10 PBq (270 kCi)" color="text-rose-400" sub="Category I food irradiator" />
        <InfoCard label="Pool depth (shielding)" value="5–6 m water" color="text-blue-400" />
        <InfoCard label="Dose uniformity ratio" value="DUR &lt; 1.5" color="text-green-400" sub="Per ISO 11137" />
        <InfoCard label="Primary isotope" value="Co-60 (1.25 MeV avg)" color="text-orange-400" />
      </div>

      <ContentBlock title="Gamma Irradiator Types">
        <SpecTable
          headers={['Type', 'Source', 'Activity', 'Application']}
          rows={[
            ['Category I — panoramic', 'Co-60 / Cs-137', 'PBq range',    'Food irradiation, sterilisation, polymer processing'],
            ['Category II — panoramic', 'Co-60',          'TBq–PBq',      'Medical device sterilisation, phytosanitary'],
            ['Category III',            'Co-60 / Cs-137', 'GBq–TBq',      'Blood irradiation, seed treatment, research'],
            ['Category IV — dry-storage','Cs-137',         'GBq',          'Self-shielded cabinets for calibration/research'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="Pool-Type Irradiator Construction">
        <p>Source racks (pencil sources in stainless steel capsules) are stored under 5–6 m of demineralised water in a concrete-lined pool when not in use. Products move through the irradiation zone on conveyors at a controlled speed governing absorbed dose. Automated dose mapping with Fricke or alanine dosimeters verifies dose uniformity.</p>
      </ContentBlock>

      <ContentBlock title="Safety Systems">
        <AlertBox type="danger">Category I/II irradiators require: entry interlock blocking source raise while door is open; occupancy sensor; redundant source position monitoring; emergency source lower; radiation monitoring at all exits; personnel dosimetry. Operator licence required (IAEA TECDOC-1313).</AlertBox>
      </ContentBlock>
    </div>
  );
}

function IndustrialXrayContent() {
  const chartData = INDUSTRIAL_ENERGIES.map(e => ({ name: e.kv, steelMm: parseInt(e.pen.replace(/[^0-9]/g, '')), keV: e.keV }));
  return (
    <div className="space-y-6">
      <div className="bg-card/60 border border-border rounded-xl p-5">
        <h3 className="font-bold text-sm uppercase tracking-wider text-muted-foreground mb-4">Steel Penetration by Energy</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 30, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="name" angle={-30} textAnchor="end" tick={{ fill: '#64748b', fontSize: 9 }} interval={0} />
            <YAxis label={{ value: 'Max steel (mm)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }} formatter={(v: any) => [`${v} mm steel`, 'Max penetration']} />
            <Bar dataKey="steelMm" radius={[3, 3, 0, 0]}>
              {chartData.map((_, i) => <Cell key={i} fill={`hsl(${200 + i * 18},70%,55%)`} fillOpacity={0.8} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ContentBlock title="Industrial X-ray Energy Selection Guide">
        <p>Fundamental rule: use the minimum energy that achieves adequate penetration. Higher-than-necessary energy reduces contrast, increases scatter, and creates unnecessary regulatory burden.</p>
        <SpecTable
          headers={['Energy', 'Source type', 'Max penetration', 'Applications', 'Image quality']}
          rows={INDUSTRIAL_ENERGIES.map(e => [e.kv, e.source, e.pen, e.app, e.quality])}
        />
      </ContentBlock>

      <ContentBlock title="Image Quality & Standards">
        <p>Industrial radiographic quality is governed by image quality indicators (IQIs/penetrameters): wire-type (EN 462-1 / ASTM E747) or hole-type. Geometric unsharpness: Ug = f × b/a, where f = focal spot size, b = object-to-detector distance, a = source-to-object distance.</p>
        <AlertBox type="info">Relevant standards: EN ISO 17636 (radiographic testing of welds), ASME V Article 2, ASTM E94, EN 444, API 1104. Radiographic films: Class C4–C7 per EN ISO 11699. Digital detectors: EN ISO 17636-2 Class A or B.</AlertBox>
      </ContentBlock>
    </div>
  );
}

function SecurityContent() {
  return (
    <div className="space-y-6">
      <TopicMedia topic="security" />

      <ContentBlock title="Security Screening System Types">
        <SpecTable
          headers={['System', 'Source', 'Energy', 'Application', 'Detection capability']}
          rows={[
            ['Cabin baggage (airport)', 'X-ray tube', '140–160 kV', 'Passenger carry-on', 'Threats by Z-number colour coding'],
            ['Hold baggage (CT)', 'X-ray tube', '120–160 kV + rotation', 'Checked luggage', 'Explosive detection by density + CT number'],
            ['Personnel scanner', 'Low-power X-ray or MMW', 'Backscatter / active MMW', 'Body-borne threats', 'Concealed items, weapons'],
            ['Cargo X-ray', 'LINAC 3–6 MeV', '3–6 MeV', 'Air/sea cargo', 'Density maps, organic/inorganic discrimination'],
            ['Vehicle scanner', 'LINAC 6–9 MeV', '6–9 MeV', 'Trucks, cars, trains', 'Contraband, special nuclear material'],
            ['Container portal', 'Co-60 or LINAC', '1.25 MeV / 6+ MeV', 'ISO containers', 'Dense contraband, radiological material'],
            ['Radiation portal (RPM)', 'Passive NaI/He-3', 'Passive γ + neutron', 'Border crossing', 'SNM, dirty bomb material detection'],
          ]}
        />
      </ContentBlock>

      <ContentBlock title="Dual-Energy Material Discrimination">
        <p>By imaging at two X-ray energies (e.g., 3 MeV and 6 MeV with rapid LINAC energy switching, or 80 kV and 140 kV in a tunnel system), the ratio of high-to-low energy attenuation reveals the effective atomic number (Zeff) of the material. Organic materials (explosives, narcotics, food) have Zeff ~6–8; metals have Zeff &gt;20. Automatic colour coding: orange = organic, blue/green = inorganic, black/green = metal.</p>
      </ContentBlock>

      <ContentBlock title="Radiation Dose in Passenger Screening">
        <AlertBox type="info">Backscatter personnel scanners: ~0.05–0.1 μSv effective dose per scan (minutes of background radiation). Baggage X-ray: &lt;1 mGy. Cargo containers: up to ~1 mGy. Dose surveys required by IAEA SSG-23 and national TSA/ECAC regulations.</AlertBox>
      </ContentBlock>

      <SectionQuiz questions={TOPIC_QUIZZES['security']} />
    </div>
  );
}

// ─── Section router ───────────────────────────────────────────────────────────
function SectionContent({ id, onNavigate }: { id: string; onNavigate: (id: string) => void }) {
  switch (id) {
    case 'learn':              return <LearnSection />;
    case 'dashboard':          return <DashboardSection onNavigate={onNavigate} />;
    case 'xray-tube':          return <XrayTubeContent />;
    case 'linac':              return <LinacContent />;
    case 'betatron':           return <BetatronContent />;
    case 'cyclotron':          return <CyclotronContent />;
    case 'synchrotron':        return <SynchrotronContent />;
    case 'van-de-graaff':      return <VanDeGraaffContent />;
    case 'radioisotopes':      return <RadioisotopeContent />;
    case 'neutron':            return <NeutronContent />;
    case 'gamma-irradiators':  return <GammaIrradiatorContent />;
    case 'industrial-xray':    return <IndustrialXrayContent />;
    case 'security':           return <SecurityContent />;
    case 'xray-technologies':  return <TopicMedia topic="xray-technologies" />;
    case 'detectors':          return <TopicMedia topic="detectors" />;
    case 'equipment-db':       return <EquipmentSection />;
    case 'manufacturers':      return <ManufacturersSection />;
    case 'standards':          return <StandardsSection />;
    case 'calculators':        return <CalculatorsSection />;
    case 'media-theatre':      return <MediaTheatreSection />;
    case 'virtual-lab':        return <VirtualLab />;
    case 'animations':         return <AnimationsSection />;
    case 'comparison':         return <SourceComparisonChart />;
    case 'learning-paths':     return <LearningPathsSection />;
    case 'learning-center':    return <LearningCenterSection />;
    case 'maintenance':        return <MaintenanceSection />;
    default:                   return <div className="text-muted-foreground">Section coming soon.</div>;
  }
}

// ─── Section metadata ─────────────────────────────────────────────────────────
const SECTION_META: Record<string, { desc: string; refs: string[] }> = {
  'learn':           { desc: '13 structured courses covering every source, technology and detector. Each lesson pairs a live simulation with a plain-language explanation of the mechanism, the physics and the engineering — with progress tracking and a closing quiz.', refs: ['IAEA', 'ICRP', 'NCRP', 'IEC', 'ISO'] },
  'dashboard':       { desc: 'Platform overview: quick-access grid, stats, learning paths, and safety disclaimer for the Radiation Sources & Accelerator Engineering encyclopedia.', refs: [] },
  'xray-tube':       { desc: 'Tube construction, cathode/anode physics, HV generation, cooling, filtration, failure modes, maintenance — with animated diagram and knowledge quiz.', refs: ['IEC 60613', 'IEC 60522', 'NCRP 102', 'IAEA Safety Series 115'] },
  'linac':           { desc: 'History, RF acceleration, magnetron/klystron, beam transport, medical, industrial, and cargo inspection applications — with animated schematic and quiz.', refs: ['IEC 60601-2-1', 'IAEA TRS 398', 'NCRP 151'] },
  'betatron':        { desc: 'Induction acceleration, betatron condition, donut orbit animation, comparison with LINAC, industrial NDT applications.', refs: ['ASTM E1817', 'EN ISO 17636'] },
  'cyclotron':       { desc: 'Magnetic resonance acceleration, dee electrodes, spiraling particle animation, isochronous design, PET isotope production.', refs: ['IAEA TRS 468', 'USP 823'] },
  'synchrotron':     { desc: 'Storage ring animation, insertion devices, undulators, synchrotron radiation brightness, security and industrial applications.', refs: ['IAEA TECDOC-1459'] },
  'van-de-graaff':   { desc: 'Belt charging animation, tandem VdG design, electrostatic acceleration, AMS, nuclear research, ion implantation.', refs: ['IAEA TRS 398'] },
  'radioisotopes':   { desc: 'Decay schemes, shielding, transport — with interactive decay curve, inverse square law calculator, and knowledge quiz.', refs: ['IAEA SSG-14', 'IAEA SSR-6', 'ICRP 103', 'NCRP 33'] },
  'neutron':         { desc: 'D-T generator animation, Am-Be, Cf-252, thermalization visualizer, PFNA cargo interrogation, He-3 shortage, quiz.', refs: ['IAEA TECDOC-1153', 'ANSI N42.43'] },
  'gamma-irradiators': { desc: 'Pool-type and dry-storage irradiators, source rack design, dose mapping, safety interlocks.', refs: ['IAEA TECDOC-1313', 'ISO 11137', 'IAEA SSG-8'] },
  'industrial-xray': { desc: '160 kV through 9 MeV — penetration bar chart, applications, image quality, and standards for each energy tier.', refs: ['EN ISO 17636', 'ASTM E94', 'ASME V Article 2', 'API 1104'] },
  'security':        { desc: 'Airport, cargo, vehicle and personnel screening systems, dual-energy discrimination, portal monitors, dose considerations, quiz.', refs: ['IAEA SSG-23', 'ANSI N42.45', 'ECAC Doc 30', 'IEC 62463'] },
  'xray-technologies': { desc: 'Transmission, dual-energy, backscatter, forward and coherent scatter, tomography and spectral methods — one film plus 21 part-level animations covering how each technology forms its image.', refs: ['NIST XCOM', 'IEC 62463', 'ANSI N42.45', 'ASTM E2662'] },
  'detectors':       { desc: 'Every detector family — ion chamber, proportional, GM, PMT, SiPM, photodiode/DAB arrays, CdTe/CZT, HPGe, a-Si and a-Se panels, CR plates, film and TLD — with the full reception chain animated from photon to digital number.', refs: ['IEC 62220', 'ANSI N42.35', 'IEC 61267', 'ISO 17636-2'] },
  'equipment-db':    { desc: 'Searchable database of 15+ security and industrial radiation systems — specs, detector technology, energy range, and side-by-side comparisons.', refs: ['IEC 62463', 'ANSI N42.45', 'IEC 60601-2-1'] },
  'manufacturers':   { desc: 'Directory of 20 global manufacturers — Rapiscan, Smiths Detection, Nuctech, Varex, Varian, Siemens Healthineers, and more — filterable by product category.', refs: [] },
  'standards':       { desc: 'Library of 15 key international standards and IAEA publications — ICRP, NCRP, IEC, ISO, ASTM — with direct links to official sources.', refs: ['IAEA', 'IEC', 'ISO', 'ASTM', 'ICRP', 'NCRP'] },
  'media-theatre':   { desc: '13 chaptered physics films with a scrubbable timeline, narration and theatre mode, plus a searchable library of 118 component animations covering every part of every source, technology and detector.', refs: ['IAEA', 'IEC', 'ICRP', 'NCRP'] },
  'calculators':     { desc: 'Four engineering calculators: HVL/TVL shielding, unit conversion (Gy/Sv/Bq/Ci/R), photon energy (E↔λ), and geometric unsharpness.', refs: ['NIST XCOM', 'IEC 61267', 'IAEA TRS 398'] },
  'virtual-lab':     { desc: 'Interactive X-ray spectrum simulator (Kramers rule + characteristic peaks) and shielding calculator.', refs: ['NIST XCOM', 'Kramers 1923', 'IEC 61267'] },
  'animations':      { desc: 'Animated SVG physics diagrams: Compton scattering, photoelectric effect, bremsstrahlung production, and pair production — with formulas and interaction tables.', refs: ['NIST XCOM', 'ICRP 103'] },
  'comparison':      { desc: 'Interactive comparison of all radiation source types — energy range, brightness, portability, and cost-effectiveness.', refs: ['NIST XCOM', 'IAEA-TECDOC-1439'] },
  'learning-paths':  { desc: '6 structured learning curricula: Fundamentals, X-ray Engineering, LINAC Engineering, RSO Prep, Cargo Inspection, and Industrial NDT.', refs: ['IAEA', 'ICRP', 'NCRP'] },
  'maintenance':     { desc: 'Fault database with 11 common faults — symptoms, root causes, diagnostic steps, corrective actions, safety notes, and escalation criteria.', refs: ['IEC 60601-2-1', 'IEC 62463', 'ISO 11137'] },
};

/** Sections that need the full window width rather than a reading column. */
const WIDE_SECTIONS = new Set(['learn', 'media-theatre', 'xray-technologies', 'detectors']);

// ─── Collapsible sidebar group ────────────────────────────────────────────────
function SidebarGroup({
  group, sections, activeSection, onSelect,
}: {
  group: typeof NAV_GROUPS[0];
  sections: SourceSection[];
  activeSection: string;
  onSelect: (id: string) => void;
}) {
  const hasActive = sections.some(s => s.id === activeSection);
  const [open, setOpen] = useState(hasActive || group.id === 'overview' || group.id === 'learn-top');

  return (
    <div className="mb-0.5">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left group"
      >
        <span className="flex-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 group-hover:text-muted-foreground transition-colors">
          {group.label}
        </span>
        {open
          ? <ChevronUp className="h-3 w-3 text-muted-foreground/40 shrink-0" />
          : <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />}
      </button>
      {open && (
        <div className="space-y-0.5">
          {sections.map(s => {
            const Icon = s.icon;
            const isActive = activeSection === s.id;
            return (
              <button
                key={s.id}
                onClick={() => onSelect(s.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors text-left ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'
                }`}
              >
                <Icon className={`h-4 w-4 shrink-0 ${isActive ? '' : s.color}`} />
                <span className="flex-1 text-xs font-medium truncate">{s.label}</span>
                {s.isNew && !isActive && (
                  <span className="text-[8px] font-bold px-1 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shrink-0">NEW</span>
                )}
                {!s.isNew && s.badge && !isActive && (
                  <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 font-mono shrink-0 border-border/50">
                    {s.badge}
                  </Badge>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function RadiationSourcesPage({ initialSection }: { initialSection?: string } = {}) {
  const [activeSection, setActiveSection] = useState(initialSection ?? 'dashboard');
  const nav = useResizableColumn({ key: 'radiation-nav', initial: 240, min: 170, max: 460 });
  const [lang] = useLessonLang();
  const ar = lang === 'ar';
  const section = SECTIONS.find(s => s.id === activeSection)!;
  const meta = SECTION_META[activeSection] || { desc: '', refs: [] };

  // Build a map from group id → sections in that group
  const groupedSections = useMemo(() =>
    NAV_GROUPS.map(g => ({
      group: g,
      sections: g.ids.map(id => SECTIONS.find(s => s.id === id)!).filter(Boolean),
    })),
  []);

  return (
    <div className="flex bg-background flex-col md:flex-row md:h-full md:overflow-hidden overflow-y-auto">
      {/* Section sidebar — drag the divider to resize, chevron to collapse */}
      {nav.collapsed && <CollapsedStrip label="Sections" onExpand={nav.toggle} />}
      <div
        className={`w-full md:w-[var(--navw)] md:shrink-0 border-r border-border bg-card/30 flex flex-col md:h-full z-10 ${nav.collapsed ? 'hidden' : ''}`}
        style={{ ['--navw' as string]: `${nav.width}px` }}
      >
        <div className="p-4 border-b border-border bg-card shrink-0">
          <div className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-lg bg-purple-500/10 flex items-center justify-center ring-1 ring-purple-500/30 shrink-0">
              <Atom className="h-5 w-5 text-purple-400" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="font-bold text-sm leading-tight truncate">{ar ? PAGE_STRINGS_AR.title1 : 'Radiation Sources &'}</h2>
              <h2 className="font-bold text-sm leading-tight text-purple-400 truncate">{ar ? PAGE_STRINGS_AR.title2 : 'Accelerator Engineering'}</h2>
            </div>
            <ColumnToggle collapsed={false} onClick={nav.toggle} label="sections" />
          </div>
          <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mt-2 truncate">{ar ? PAGE_STRINGS_AR.encyclopedia : 'Engineering Encyclopedia'}</p>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2 pt-3">
            {groupedSections.map(({ group, sections }) => (
              <SidebarGroup
                key={group.id}
                group={group}
                sections={sections}
                activeSection={activeSection}
                onSelect={setActiveSection}
              />
            ))}
          </div>
        </ScrollArea>

        <div className="p-3 border-t border-border bg-card/50 shrink-0">
          <p className="text-[10px] text-muted-foreground leading-relaxed" dir={ar ? 'rtl' : 'ltr'}>
            {ar ? PAGE_STRINGS_AR.refs : 'References: IAEA, ICRP, NCRP, IEC, ISO, ASTM peer-reviewed literature.'}
          </p>
        </div>
      </div>
      {!nav.collapsed && (
        <ColumnResizer
          dragging={nav.dragging}
          onPointerDown={nav.onPointerDown}
          onPointerMove={nav.onPointerMove}
          onPointerUp={nav.endDrag}
        />
      )}

      {/* Content area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-[60vh] md:min-h-0">
        {/* Header */}
        <div className="border-b border-border bg-card/50 px-6 py-4 shrink-0">
          <div className="flex items-start gap-4">
            <div className="h-10 w-10 rounded-lg bg-background flex items-center justify-center ring-1 ring-border shrink-0">
              <section.icon className={`h-5 w-5 ${section.color}`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-lg font-bold" dir={ar ? 'rtl' : 'ltr'}>
                  {ar ? (COURSE_TITLES_AR[activeSection]?.title ?? section.label) : section.label}
                </h1>
                <Badge variant="outline" className={`text-xs ${section.color} border-current`}>{section.badge}</Badge>
              </div>
              {meta.desc && (
                <p className="text-sm text-muted-foreground mt-0.5 leading-relaxed" dir={ar ? 'rtl' : 'ltr'}>
                  {ar ? (SECTION_DESC_AR[activeSection] ?? meta.desc) : meta.desc}
                </p>
              )}
              {meta.refs.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {meta.refs.map(r => (
                    <span key={r} className="text-[10px] font-mono px-1.5 py-0.5 bg-card border border-border rounded text-muted-foreground">{r}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Scrollable content.
            NOTE: deliberately a native scroll container rather than <ScrollArea>.
            Radix wraps viewport children in a display:table element, which
            shrink-wraps to content and pushes wide sections off the right edge
            instead of letting them wrap. */}
        <div className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden">
          <div className={`mx-auto p-6 min-w-0 ${WIDE_SECTIONS.has(activeSection) ? 'max-w-[1600px]' : 'max-w-5xl'}`}>
            <SectionContent id={activeSection} onNavigate={setActiveSection} />
          </div>
        </div>
      </div>
    </div>
  );
}
