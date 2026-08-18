import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { Progress } from '@/components/ui/progress';
import {
  Zap, Cpu, Atom, Shield, Radio, Eye, Dna, Bot, FileText,
  Play, Pause, RotateCcw, Send, Download, Loader2, CheckCircle,
  ChevronRight, Info, AlertTriangle, Thermometer, BarChart2,
  Activity, Target, BookOpen, Layers, FlaskConical,
} from 'lucide-react';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid,
} from 'recharts';

// ─── Constants ───────────────────────────────────────────────────────────────
const API = import.meta.env.BASE_URL?.replace(/\/$/, '');

// ─── Shared helpers ───────────────────────────────────────────────────────────
function InfoCard({ label, value, sub, color = 'text-primary' }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="bg-card/60 border border-border rounded-lg p-3">
      <div className={`text-base font-bold font-mono ${color}`}>{value}</div>
      <div className="text-xs font-medium text-foreground">{label}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
function AlertBox({ type, children }: { type: 'info' | 'warning' | 'danger'; children: React.ReactNode }) {
  const s = { info: 'bg-blue-500/10 border-blue-500/30 text-blue-200', warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-200', danger: 'bg-red-500/10 border-red-500/30 text-red-200' };
  const i = { info: 'ℹ', warning: '⚠', danger: '☢' };
  return <div className={`border rounded-lg px-3 py-2 text-xs flex gap-2 items-start ${s[type]}`}><span className="shrink-0 mt-0.5">{i[type]}</span><span>{children}</span></div>;
}

// ─── Physics functions ────────────────────────────────────────────────────────
function xraySpectrum(kVp: number, mA: number, Z: number, kEdge: number, filterMu: number) {
  const pts: { E: number; I: number }[] = [];
  for (let E = 5; E <= kVp; E += 2) {
    let I = Z * (kVp - E) / (E * E);
    if (kEdge > 0 && kVp > kEdge) {
      I += 8 * Math.exp(-((E - kEdge * 0.84) ** 2) / 4) * mA / 300;
      I += 4 * Math.exp(-((E - kEdge * 0.87) ** 2) / 4) * mA / 300;
    }
    I *= Math.exp(-filterMu * E / kVp) * mA / 200;
    pts.push({ E, I: Math.max(0, I) });
  }
  return pts;
}

function depthDoseCurve(energyMeV: number, medium: 'water' | 'steel') {
  const muMap: Record<string, Record<number, number>> = {
    water: { 3: 0.041, 6: 0.031, 9: 0.026, 15: 0.021 },
    steel: { 3: 0.32,  6: 0.22,  9: 0.17,  15: 0.13 },
  };
  const mu = muMap[medium][energyMeV] ?? 0.03;
  const buildup = 1.2 + 0.15 * energyMeV;
  return Array.from({ length: 40 }, (_, i) => {
    const d = i * (medium === 'water' ? 0.5 : 5); // cm water, mm steel
    const dose = 100 * buildup * Math.exp(-mu * d) / buildup;
    return { d: parseFloat(d.toFixed(1)), D: parseFloat(dose.toFixed(1)) };
  });
}

function decayCurve(halfLifeYears: number, initialActivity: number) {
  const t05 = halfLifeYears;
  return Array.from({ length: 50 }, (_, i) => {
    const t = i * t05 * 0.12;
    const A = initialActivity * Math.pow(0.5, t / t05);
    return { t: parseFloat(t.toFixed(2)), A: parseFloat(A.toFixed(2)) };
  });
}

function shieldingTransmission(energy: number, material: string, thickness: number) {
  // μρ cm⁻¹ approximate values keyed by material and energy bin
  const MU: Record<string, [number, number][]> = {
    Lead:       [[0.1, 59.7], [0.5, 1.67], [1.0, 0.775], [1.5, 0.555]],
    Steel:      [[0.1, 1.97], [0.5, 0.87], [1.0, 0.597], [1.5, 0.452]],
    Concrete:   [[0.1, 0.74], [0.5, 0.22], [1.0, 0.167], [1.5, 0.134]],
    Water:      [[0.1, 0.167],[0.5, 0.097],[1.0, 0.071], [1.5, 0.060]],
    Polyethylene:[[0.1,0.17], [0.5, 0.096],[1.0, 0.071], [1.5, 0.059]],
    'Borated PE':[[0.1,0.18], [0.5, 0.10], [1.0, 0.074], [1.5, 0.062]],
  };
  const curve = MU[material] ?? MU.Lead;
  const energyBins = curve.map(c => c[0]);
  const eBin = energyBins.reduce((prev, curr) => Math.abs(curr - energy) < Math.abs(prev - energy) ? curr : prev);
  const mu = curve.find(c => c[0] === eBin)?.[1] ?? 1;
  return Array.from({ length: 60 }, (_, i) => {
    const x = i * 0.5;
    const T = Math.exp(-mu * x) * 100;
    return { x: parseFloat(x.toFixed(1)), T: parseFloat(T.toFixed(3)) };
  }).filter(p => p.T > 0.001);
}

function cellSurvival(alpha: number, beta: number) {
  return Array.from({ length: 30 }, (_, i) => {
    const D = i * 0.5;
    const S = Math.exp(-(alpha * D + beta * D * D));
    return { D: parseFloat(D.toFixed(1)), S: parseFloat((S * 100).toFixed(3)) };
  });
}

// ─── MATERIAL / ISOTOPE DATA ─────────────────────────────────────────────────
const TARGETS: Record<string, { Z: number; kEdge: number; label: string }> = {
  W:  { Z: 74, kEdge: 69.5, label: 'Tungsten (W)' },
  Mo: { Z: 42, kEdge: 20.0, label: 'Molybdenum (Mo)' },
  Rh: { Z: 45, kEdge: 23.2, label: 'Rhodium (Rh)' },
  Cu: { Z: 29, kEdge: 8.98, label: 'Copper (Cu)' },
};
const FILTERS = [
  { id: 'none', label: 'None', mu: 0 },
  { id: 'al1',  label: 'Al 1 mm', mu: 0.06 },
  { id: 'al3',  label: 'Al 3 mm', mu: 0.15 },
  { id: 'cu05', label: 'Cu 0.5 mm', mu: 0.45 },
];
const ISOTOPES_LAB = [
  { id: 'Co-60',  hl: 5.27,   E: 1.25,  color: '#f97316', activity: 1000 },
  { id: 'Cs-137', hl: 30.17,  E: 0.662, color: '#eab308', activity: 500  },
  { id: 'Ir-192', hl: 0.202,  E: 0.37,  color: '#3b82f6', activity: 3700 },
  { id: 'Am-241', hl: 432.2,  E: 0.0595,color: '#22c55e', activity: 10   },
  { id: 'Cf-252', hl: 2.645,  E: 2.35,  color: '#a855f7', activity: 0.5  },
];
const SHIELD_MATS = ['Lead','Steel','Concrete','Water','Polyethylene','Borated PE'];
const DETECTORS = [
  { id: 'GM',    label: 'GM Tube',          res: null, effPeak: 0.01, notes: 'Count rate only; no energy discrimination. Typical eff ~1–2% at 1 MeV.' },
  { id: 'NaI',   label: 'NaI(Tl) 2×2"',    res: 7.5,  effPeak: 0.35, notes: '7.5% energy resolution at 662 keV. High eff for γ up to 3 MeV.' },
  { id: 'CsI',   label: 'CsI(Tl)',          res: 6.0,  effPeak: 0.40, notes: 'Slightly better eff than NaI; rugged for field use; 6% res at 662 keV.' },
  { id: 'Plastic',label:'Plastic Scint.',   res: 50,   effPeak: 0.60, notes: '~50% FWHM res; very fast; large volumes possible; neutron detection possible.' },
  { id: 'HPGe',  label: 'HPGe',             res: 0.18, effPeak: 0.25, notes: '0.18% res at 1.33 MeV — gold standard for γ spectrometry. Requires LN₂.' },
  { id: 'CdZnTe',label: 'CdZnTe',          res: 2.0,  effPeak: 0.22, notes: '2% res at 662 keV; room-temp semiconductor; compact field instruments.' },
  { id: 'Neutron',label:'He-3 / Li-6',      res: null, effPeak: 0.90, notes: 'High thermal neutron detection efficiency (>90%). Poor energy resolution.' },
];

// ─── LAB 1: X-RAY TUBE ───────────────────────────────────────────────────────
function XrayTubeLab({ onSave }: { onSave: (data: any) => void }) {
  const [kVp, setKVp]           = useState(120);
  const [mA, setMA]             = useState(300);
  const [target, setTarget]     = useState('W');
  const [filterIdx, setFilter]  = useState(0);
  const [focalSpot, setFocal]   = useState(1.0);
  const [animated, setAnim]     = useState(false);
  const [t, setT]               = useState(0);
  const rafRef                  = useRef<number>(0);
  const startRef                = useRef<number|null>(null);

  useEffect(() => {
    if (!animated) return;
    const loop = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      setT(((ts - startRef.current) % 2000) / 2000);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animated]);

  const mat = TARGETS[target];
  const spectrum = useMemo(() => xraySpectrum(kVp, mA, mat.Z, mat.kEdge, FILTERS[filterIdx].mu), [kVp, mA, mat, filterIdx]);
  const heatW = (kVp * mA * 0.001 * 0.99).toFixed(0);
  const outputMGy = (0.0054 * kVp ** 2 * mA / 1000).toFixed(1);
  const hvlMmPb   = (0.693 / (0.0585 * (kVp / 100) ** 1.7)).toFixed(1);
  const iqScore   = Math.min(100, Math.round(70 + (150 - kVp) * 0.2 + (1.5 - focalSpot) * 10 - filterIdx * 5));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Controls */}
        <div className="bg-card/60 border border-border rounded-xl p-5 space-y-5">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Tube Parameters</h3>

          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Tube Voltage (kVp)</span><span className="font-mono text-yellow-400">{kVp} kV</span></div>
            <Slider min={40} max={150} step={1} value={[kVp]} onValueChange={([v]) => setKVp(v)} />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Tube Current (mA)</span><span className="font-mono text-blue-400">{mA} mA</span></div>
            <Slider min={50} max={1200} step={50} value={[mA]} onValueChange={([v]) => setMA(v)} />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Focal Spot (mm)</span><span className="font-mono text-green-400">{focalSpot} mm</span></div>
            <Slider min={0.1} max={2.5} step={0.1} value={[focalSpot]} onValueChange={([v]) => setFocal(v)} />
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-2">Target Material</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(TARGETS).map(([k, v]) => (
                <button key={k} onClick={() => setTarget(k)}
                  className={`text-xs px-2 py-1.5 rounded-lg border text-left transition-all ${target === k ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                  {v.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-2">Filtration</p>
            <div className="flex flex-wrap gap-2">
              {FILTERS.map((f, i) => (
                <button key={f.id} onClick={() => setFilter(i)}
                  className={`text-xs px-2 py-1 rounded border transition-all ${filterIdx === i ? 'border-emerald-500 bg-emerald-500/10 text-emerald-400' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setAnim(a => !a)} className="gap-1 h-8">
              {animated ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
              {animated ? 'Pause' : 'Animate Beam'}
            </Button>
            <Button size="sm" variant="outline" className="gap-1 h-8" onClick={() => onSave({ lab: 'X-ray Tube', kVp, mA, target, filter: FILTERS[filterIdx].label, focalSpot, output: outputMGy, hvl: hvlMmPb })}>
              <Download className="h-3 w-3" /> Save Experiment
            </Button>
          </div>
        </div>

        {/* Metrics */}
        <div className="space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Live Readings</h3>
          <div className="grid grid-cols-2 gap-3">
            <InfoCard label="Max photon energy" value={`${kVp} keV`} color="text-yellow-400" />
            <InfoCard label="Output (1 m)" value={`${outputMGy} mGy/min`} color="text-orange-400" sub="air kerma, approx." />
            <InfoCard label="Anode heat load" value={`${heatW} W`} color="text-red-400" sub="99% of beam power" />
            <InfoCard label="HVL (Pb)" value={`${hvlMmPb} mm`} color="text-blue-400" />
          </div>

          {/* Heat gauge */}
          <div className="bg-card/60 border border-border rounded-lg p-3">
            <div className="flex justify-between text-xs mb-2">
              <span className="text-muted-foreground">Anode Heat Units</span>
              <span className="font-mono text-orange-400">{(kVp * mA).toLocaleString()} HU</span>
            </div>
            <Progress value={Math.min(100, (kVp * mA) / 2000)} className="h-2 [&>div]:bg-orange-400" />
            <div className="text-[10px] text-muted-foreground mt-1">Max rating: 200,000 HU (typical rotating anode)</div>
          </div>

          {/* Image quality */}
          <div className="bg-card/60 border border-border rounded-lg p-3">
            <div className="flex justify-between text-xs mb-2">
              <span className="text-muted-foreground">Image Quality Score</span>
              <span className={`font-mono font-bold ${iqScore > 75 ? 'text-green-400' : iqScore > 50 ? 'text-yellow-400' : 'text-red-400'}`}>{iqScore}/100</span>
            </div>
            <Progress value={iqScore} className={`h-2 ${iqScore > 75 ? '[&>div]:bg-green-400' : iqScore > 50 ? '[&>div]:bg-yellow-400' : '[&>div]:bg-red-400'}`} />
            <div className="text-[10px] text-muted-foreground mt-1">Lower kVp, smaller focal spot, minimal filtration → better contrast</div>
          </div>

          <AlertBox type="info">
            <strong>Beam animation:</strong> Blue dots = electrons (cathode→anode). Yellow rays = bremsstrahlung photons. Spectrum updates live as you change parameters.
          </AlertBox>
        </div>
      </div>

      {/* Spectrum chart */}
      <div className="bg-card/60 border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
            X-ray Spectrum — {TARGETS[target].label}, {kVp} kVp, {mA} mA, {FILTERS[filterIdx].label}
          </h3>
          <Badge variant="outline" className="font-mono text-xs">{mat.kEdge} keV K-edge</Badge>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={spectrum} margin={{ top: 5, right: 20, bottom: 20, left: 10 }}>
            <defs>
              <linearGradient id="xg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.5} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <XAxis dataKey="E" label={{ value: 'Energy (keV)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
            <YAxis tick={{ fill: '#64748b', fontSize: 9 }} label={{ value: 'Relative I', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} labelFormatter={e => `${e} keV`} />
            {mat.kEdge < kVp && <ReferenceLine x={Math.round(mat.kEdge * 0.85)} stroke="#a78bfa" strokeDasharray="3 3" label={{ value: 'Kα', fill: '#a78bfa', fontSize: 10 }} />}
            <Area type="monotone" dataKey="I" stroke="#3b82f6" fill="url(#xg)" strokeWidth={1.5} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── LAB 2: LINAC ────────────────────────────────────────────────────────────
const LINAC_ENERGIES = [3, 6, 9, 15] as const;
function LinacLab({ onSave }: { onSave: (data: any) => void }) {
  const [energy, setEnergy]   = useState<number>(6);
  const [medium, setMedium]   = useState<'water'|'steel'>('water');
  const penDepthMap: Record<number, Record<string, string>> = {
    3:  { water: '~25 cm', steel: '~200 mm' },
    6:  { water: '~30 cm', steel: '~270 mm' },
    9:  { water: '~33 cm', steel: '~330 mm' },
    15: { water: '~38 cm', steel: '~420 mm' },
  };
  const ddCurve = useMemo(() => depthDoseCurve(energy, medium), [energy, medium]);
  const xLabel  = medium === 'water' ? 'Depth (cm water)' : 'Depth (mm steel)';
  const dmax    = medium === 'water' ? (energy > 8 ? 3.5 : 1.5 + energy * 0.3).toFixed(1) : (energy * 20).toFixed(0);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-card/60 border border-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">LINAC Configuration</h3>
          <div>
            <p className="text-xs text-muted-foreground mb-2">Beam Energy</p>
            <div className="grid grid-cols-4 gap-2">
              {LINAC_ENERGIES.map(e => (
                <button key={e} onClick={() => setEnergy(e)}
                  className={`py-2 rounded-lg border text-sm font-bold font-mono transition-all ${energy === e ? 'border-violet-500 bg-violet-500/10 text-violet-300' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                  {e} MeV
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-2">Phantom Medium</p>
            <div className="grid grid-cols-2 gap-2">
              {(['water','steel'] as const).map(m => (
                <button key={m} onClick={() => setMedium(m)}
                  className={`py-2 rounded-lg border text-sm font-medium capitalize transition-all ${medium === m ? 'border-cyan-500 bg-cyan-500/10 text-cyan-300' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                  {m === 'water' ? '💧 Water phantom' : '🔩 Steel plate'}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <InfoCard label="Practical penetration" value={penDepthMap[energy][medium]} color="text-violet-400" />
            <InfoCard label="Dmax depth" value={`${dmax} ${medium === 'water' ? 'cm' : 'mm'}`} color="text-cyan-400" sub="dose build-up" />
            <InfoCard label="Beam type" value="Bremsstrahlung" color="text-blue-400" />
            <InfoCard label="Pulse rate" value="300 Hz" color="text-green-400" sub="typical" />
          </div>
          <Button size="sm" variant="outline" className="gap-1 h-8" onClick={() => onSave({ lab: 'LINAC', energy: `${energy} MeV`, medium, penetration: penDepthMap[energy][medium] })}>
            <Download className="h-3 w-3" /> Save Experiment
          </Button>
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Component Status</h3>
          {[
            ['Electron Gun',     '100%', 'text-green-400'],
            ['RF Magnetron',     energy <= 9 ? '100%' : 'n/a (klystron)', 'text-green-400'],
            ['Klystron',         energy >= 15 ? '100%' : 'standby', 'text-yellow-400'],
            ['Waveguide',        '100%', 'text-green-400'],
            ['Bending Magnet',   '270° achromatic', 'text-blue-400'],
            ['Target (W)',       'active', 'text-orange-400'],
            ['Collimator',       `${energy * 0.5 + 2} cm field`, 'text-cyan-400'],
            ['Cooling System',   `${(energy * 2.5).toFixed(0)} L/min`, 'text-teal-400'],
            ['Safety Interlocks','ALL CLEAR', 'text-green-400'],
          ].map(([c, v, cls]) => (
            <div key={c as string} className="flex justify-between items-center py-1.5 border-b border-border/30">
              <span className="text-xs text-muted-foreground">{c}</span>
              <span className={`text-xs font-mono font-semibold ${cls}`}>{v}</span>
            </div>
          ))}
          <AlertBox type="warning">LINAC requires primary barrier ≥ {energy >= 9 ? '4' : '3'} m concrete at {energy} MeV. Interlocks tested per IEC 60601-2-1.</AlertBox>
        </div>
      </div>

      <div className="bg-card/60 border border-border rounded-xl p-5">
        <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">
          Depth–Dose Profile — {energy} MeV in {medium} ({xLabel})
        </h3>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={ddCurve} margin={{ top: 5, right: 20, bottom: 22, left: 10 }}>
            <defs>
              <linearGradient id="ddg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.5} />
                <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <XAxis dataKey="d" label={{ value: xLabel, position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
            <YAxis tickFormatter={v => `${v}%`} tick={{ fill: '#64748b', fontSize: 9 }} />
            <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} formatter={(v: any) => [`${v}%`, 'Relative dose']} />
            <ReferenceLine y={50} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: 'D₅₀', fill: '#f59e0b', fontSize: 10 }} />
            <Area type="monotone" dataKey="D" stroke="#8b5cf6" fill="url(#ddg)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── LAB 3: RADIOACTIVE SOURCE ────────────────────────────────────────────────
function RadioactiveLab({ onSave }: { onSave: (data: any) => void }) {
  const [isoIdx, setIsoIdx]     = useState(0);
  const [actMult, setActMult]   = useState(1.0);
  const [distance, setDistance] = useState(1.0);
  const iso = ISOTOPES_LAB[isoIdx];
  const A0  = iso.activity * actMult;
  const doseRate = (A0 * iso.E * 0.000096 / (distance * distance)).toFixed(4);
  const doseRateClose = (A0 * iso.E * 0.000096 / (0.3 * 0.3)).toFixed(2);
  const curve = useMemo(() => decayCurve(iso.hl, A0), [iso, A0]);

  // Inverse square law
  const islCurve = Array.from({ length: 30 }, (_, i) => {
    const r = 0.1 + i * 0.3;
    const D = A0 * iso.E * 0.000096 / (r * r);
    return { r: parseFloat(r.toFixed(1)), D: parseFloat(D.toFixed(4)) };
  });

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-card/60 border border-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Source Configuration</h3>
          <div className="flex flex-wrap gap-2">
            {ISOTOPES_LAB.map((iso, i) => (
              <button key={iso.id} onClick={() => setIsoIdx(i)}
                className={`px-3 py-1.5 rounded-lg border text-sm font-mono font-semibold transition-all ${isoIdx === i ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                {iso.id}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Activity multiplier</span><span className="font-mono" style={{ color: iso.color }}>{actMult.toFixed(1)}× ({A0.toFixed(1)} GBq)</span></div>
            <Slider min={0.1} max={5} step={0.1} value={[actMult]} onValueChange={([v]) => setActMult(v)} />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Distance from source</span><span className="font-mono text-cyan-400">{distance.toFixed(1)} m</span></div>
            <Slider min={0.1} max={8} step={0.1} value={[distance]} onValueChange={([v]) => setDistance(v)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <InfoCard label="Dose rate at distance" value={`${doseRate} mSv/h`} color={parseFloat(doseRate) > 1 ? 'text-red-400' : 'text-green-400'} />
            <InfoCard label="Dose rate at 30 cm" value={`${doseRateClose} mSv/h`} color="text-orange-400" />
            <InfoCard label="Energy (avg γ)" value={`${iso.E} MeV`} color="text-yellow-400" />
            <InfoCard label="Half-life" value={iso.hl > 1 ? `${iso.hl} y` : `${(iso.hl * 365.25).toFixed(0)} d`} />
          </div>
          <AlertBox type={parseFloat(doseRate) > 20 ? 'danger' : parseFloat(doseRate) > 0.5 ? 'warning' : 'info'}>
            {parseFloat(doseRate) > 20 ? '☢ DANGER — Controlled area. Remote handling required. Dose rate exceeds occupational limit.' : parseFloat(doseRate) > 0.5 ? 'Supervised area. TLD dosimetry required. Max 8 h/week.' : 'Unsupervised area (&lt;1 mSv/h). Normal precautions apply.'}
          </AlertBox>
          <Button size="sm" variant="outline" className="gap-1 h-8" onClick={() => onSave({ lab: 'Radioactive Source', isotope: iso.id, activity: A0, distance, doseRate })}>
            <Download className="h-3 w-3" /> Save Experiment
          </Button>
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Inverse Square Law</h3>
          <ResponsiveContainer width="100%" height={170}>
            <LineChart data={islCurve} margin={{ top: 5, right: 20, bottom: 22, left: 10 }}>
              <XAxis dataKey="r" label={{ value: 'Distance (m)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 9 }} label={{ value: 'mSv/h', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} formatter={(v: any) => [`${v} mSv/h`, 'Dose rate']} />
              <ReferenceLine x={distance} stroke="#60a5fa" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="D" stroke={iso.color} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>

          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Radioactive Decay Curve</h3>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={curve} margin={{ top: 5, right: 20, bottom: 22, left: 10 }}>
              <defs>
                <linearGradient id="dcg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={iso.color} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={iso.color} stopOpacity={0.03} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" label={{ value: 'Time (years)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} formatter={(v: any) => [`${v} GBq`, 'Activity']} />
              <ReferenceLine y={A0 / 2} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: 'A₀/2', fill: '#f59e0b', fontSize: 10 }} />
              <Area type="monotone" dataKey="A" stroke={iso.color} fill="url(#dcg)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

// ─── LAB 4: SHIELDING ────────────────────────────────────────────────────────
const SHIELD_COSTS: Record<string, number> = { Lead: 28, Steel: 8, Concrete: 0.5, Water: 0.1, Polyethylene: 3.5, 'Borated PE': 6 };
const SHIELD_DENSITIES: Record<string, number> = { Lead: 11340, Steel: 7850, Concrete: 2300, Water: 1000, Polyethylene: 950, 'Borated PE': 1000 };
function ShieldingLab({ onSave }: { onSave: (data: any) => void }) {
  const [mat, setMat]       = useState('Lead');
  const [thickness, setTh]  = useState(10);
  const [energy, setEnergy] = useState(1.0);
  const curve = useMemo(() => shieldingTransmission(energy, mat, thickness), [energy, mat, thickness]);

  // Find HVL and TVL
  const muEff  = curve.length > 1 ? -Math.log(curve[1].T / 100) / (curve[1].x - curve[0].x) : 0.5;
  const hvl    = muEff > 0 ? (0.693 / muEff).toFixed(1) : '—';
  const tvl    = muEff > 0 ? (2.303 / muEff).toFixed(1) : '—';
  const atPoint= (curve.find(p => Math.abs(p.x - thickness) < 0.6)?.T ?? 0).toFixed(4);
  const doseRed= (100 - parseFloat(atPoint)).toFixed(1);
  const vol1m2 = thickness * 0.01;
  const cost   = (vol1m2 * SHIELD_DENSITIES[mat] / 1000 * SHIELD_COSTS[mat]).toFixed(0);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-card/60 border border-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Shield Design</h3>
          <div>
            <p className="text-xs text-muted-foreground mb-2">Shielding Material</p>
            <div className="grid grid-cols-2 gap-2">
              {SHIELD_MATS.map(m => (
                <button key={m} onClick={() => setMat(m)}
                  className={`text-xs px-2 py-1.5 rounded-lg border transition-all text-left ${mat === m ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                  {m}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Thickness</span><span className="font-mono text-blue-400">{thickness} cm</span></div>
            <Slider min={1} max={60} step={1} value={[thickness]} onValueChange={([v]) => setTh(v)} />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Source energy</span><span className="font-mono text-yellow-400">{energy} MeV</span></div>
            <Slider min={0.1} max={1.5} step={0.1} value={[energy]} onValueChange={([v]) => setEnergy(parseFloat(v.toFixed(1)))} />
            <div className="flex justify-between text-[10px] text-muted-foreground"><span>0.1 MeV</span><span>1.5 MeV</span></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <InfoCard label="Transmission" value={`${atPoint}%`} color={parseFloat(atPoint) < 1 ? 'text-green-400' : 'text-orange-400'} />
            <InfoCard label="Dose reduction" value={`${doseRed}%`} color="text-teal-400" />
            <InfoCard label="HVL" value={`${hvl} cm`} color="text-blue-400" sub={mat} />
            <InfoCard label="TVL" value={`${tvl} cm`} color="text-violet-400" sub={mat} />
          </div>
          <div className="bg-card border border-border rounded-lg p-3 text-xs space-y-1">
            <div className="flex justify-between"><span className="text-muted-foreground">Material density</span><span className="font-mono">{(SHIELD_DENSITIES[mat] / 1000).toFixed(2)} g/cm³</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Mass per m² (1 cm thick)</span><span className="font-mono">{(SHIELD_DENSITIES[mat] / 100).toFixed(0)} kg/m²</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Est. cost / m² at {thickness} cm</span><span className="font-mono text-yellow-400">${cost}</span></div>
          </div>
          <Button size="sm" variant="outline" className="gap-1 h-8" onClick={() => onSave({ lab: 'Shielding', material: mat, thickness, energy, transmission: atPoint, hvl, tvl })}>
            <Download className="h-3 w-3" /> Save Experiment
          </Button>
        </div>

        <div className="bg-card/60 border border-border rounded-xl p-5">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">
            Transmission Curve — {mat}, {energy} MeV γ
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={curve} margin={{ top: 5, right: 20, bottom: 22, left: 10 }}>
              <defs>
                <linearGradient id="shg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0.03} />
                </linearGradient>
              </defs>
              <XAxis dataKey="x" label={{ value: 'Thickness (cm)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
              <YAxis tickFormatter={v => `${v}%`} tick={{ fill: '#64748b', fontSize: 9 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} formatter={(v: any) => [`${v}%`, 'Transmission']} />
              <ReferenceLine x={thickness} stroke="#60a5fa" strokeDasharray="3 3" />
              <ReferenceLine y={50} stroke="#f59e0b" strokeDasharray="2 2" label={{ value: 'HVL', fill: '#f59e0b', fontSize: 10 }} />
              <ReferenceLine y={10} stroke="#f97316" strokeDasharray="2 2" label={{ value: 'TVL', fill: '#f97316', fontSize: 10 }} />
              <Area type="monotone" dataKey="T" stroke="#22c55e" fill="url(#shg)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

// ─── LAB 5: DETECTOR ─────────────────────────────────────────────────────────
function DetectorLab({ onSave }: { onSave: (data: any) => void }) {
  const [detIdx, setDetIdx] = useState(1);
  const [sourceEnergy, setSrcE] = useState(0.662);
  const det = DETECTORS[detIdx];

  // Efficiency vs energy curve (simplified)
  const effCurve = Array.from({ length: 30 }, (_, i) => {
    const E = 0.05 + i * 0.1;
    let eff = det.effPeak * Math.exp(-0.3 * Math.abs(E - 0.8)) * 100;
    if (det.id === 'GM') eff = 1.5;
    if (det.id === 'Neutron') eff = E < 0.1 ? 90 : 20;
    return { E: parseFloat(E.toFixed(2)), eff: parseFloat(eff.toFixed(1)) };
  });

  // Simulated energy spectrum for NaI / HPGe
  const specCurve = (() => {
    if (!det.res) return [];
    const fwhm = det.res / 100 * sourceEnergy;
    const sigma = fwhm / 2.355;
    return Array.from({ length: 60 }, (_, i) => {
      const E = sourceEnergy * 0.5 + i * (sourceEnergy * 1.2 - sourceEnergy * 0.5) / 60;
      const peak = Math.exp(-0.5 * ((E - sourceEnergy) / sigma) ** 2) * 100;
      const compton = E < sourceEnergy * 0.8 ? 30 * (1 - E / sourceEnergy) : 0;
      return { E: parseFloat(E.toFixed(3)), C: parseFloat((peak + compton + Math.random() * 2).toFixed(1)) };
    });
  })();

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-card/60 border border-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Detector Selection</h3>
          <div className="space-y-2">
            {DETECTORS.map((d, i) => (
              <button key={d.id} onClick={() => setDetIdx(i)}
                className={`w-full text-left px-3 py-2.5 rounded-lg border text-sm transition-all ${detIdx === i ? 'border-primary bg-primary/10' : 'border-border/50 hover:border-border'}`}>
                <div className="flex justify-between items-center">
                  <span className={`font-semibold ${detIdx === i ? 'text-foreground' : 'text-muted-foreground'}`}>{d.label}</span>
                  {d.res && <Badge variant="outline" className="text-[10px]">{d.res}% FWHM</Badge>}
                </div>
                {detIdx === i && <p className="text-[11px] text-muted-foreground mt-1">{d.notes}</p>}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Source energy (MeV)</span><span className="font-mono text-yellow-400">{sourceEnergy.toFixed(3)} MeV</span></div>
            <Slider min={0.05} max={3.0} step={0.005} value={[sourceEnergy]} onValueChange={([v]) => setSrcE(parseFloat(v.toFixed(3)))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <InfoCard label="Peak efficiency" value={`${(det.effPeak * 100).toFixed(0)}%`} color="text-blue-400" />
            <InfoCard label="Energy resolution" value={det.res ? `${det.res}% FWHM` : 'None'} color="text-violet-400" />
          </div>
          <Button size="sm" variant="outline" className="gap-1 h-8" onClick={() => onSave({ lab: 'Detector', detector: det.label, sourceEnergy, resolution: det.res, efficiency: det.effPeak })}>
            <Download className="h-3 w-3" /> Save Experiment
          </Button>
        </div>

        <div className="space-y-4">
          <div className="bg-card/60 border border-border rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">Efficiency vs Energy</h4>
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={effCurve} margin={{ top: 5, right: 10, bottom: 22, left: 10 }}>
                <XAxis dataKey="E" label={{ value: 'Energy (MeV)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
                <YAxis tickFormatter={v => `${v}%`} tick={{ fill: '#64748b', fontSize: 9 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} />
                <Line type="monotone" dataKey="eff" stroke="#06b6d4" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {specCurve.length > 0 && (
            <div className="bg-card/60 border border-border rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">
                Simulated Spectrum — {det.label} at {sourceEnergy.toFixed(3)} MeV
              </h4>
              <ResponsiveContainer width="100%" height={150}>
                <AreaChart data={specCurve} margin={{ top: 5, right: 10, bottom: 22, left: 10 }}>
                  <defs>
                    <linearGradient id="detg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.5} />
                      <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.03} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="E" label={{ value: 'Energy (MeV)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 9 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} />
                  <Area type="monotone" dataKey="C" stroke="#a78bfa" fill="url(#detg)" strokeWidth={1.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── LAB 6: SECURITY SCREENING ───────────────────────────────────────────────
const SCAN_ITEMS = [
  { id: 'laptop',   label: 'Laptop',      Z: 13, density: 2.0, color: '#475569', active: true  },
  { id: 'phone',    label: 'Mobile phone',Z: 14, density: 2.3, color: '#334155', active: true  },
  { id: 'bottle',   label: 'Water bottle',Z: 8,  density: 1.0, color: '#0ea5e9', active: true  },
  { id: 'shoes',    label: 'Shoes',       Z: 7,  density: 0.9, color: '#6b7280', active: true  },
  { id: 'knife',    label: 'Metal blade', Z: 26, density: 7.8, color: '#1d4ed8', active: false },
  { id: 'cable',    label: 'Wiring bundle',Z:29, density: 8.9, color: '#2563eb', active: false },
  { id: 'powder',   label: 'Powder pack', Z: 9,  density: 1.2, color: '#f97316', active: false },
  { id: 'explosive',label: 'IED sim.',    Z: 7.5,density: 1.7, color: '#ef4444', active: false },
];

function SecurityLab({ onSave }: { onSave: (data: any) => void }) {
  const [items, setItems] = useState(SCAN_ITEMS);
  const [energy, setEnergy] = useState(120);
  const [dualE, setDualE]   = useState(true);
  const [scanned, setScanned] = useState(false);

  const toggleItem = (id: string) => setItems(prev => prev.map(it => it.id === id ? { ...it, active: !it.active } : it));
  const activeItems = items.filter(i => i.active);

  const getColor = (item: typeof SCAN_ITEMS[0]) => {
    if (!dualE) return item.Z > 18 ? '#1d4ed8' : '#4b5563';
    if (item.Z < 10) return '#f97316';   // organic → orange
    if (item.Z < 20) return '#22c55e';   // medium-Z → green
    return '#3b82f6';                     // metal → blue
  };

  const threats = activeItems.filter(i => ['knife','explosive'].includes(i.id));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-card/60 border border-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Baggage Configuration</h3>
          <div className="grid grid-cols-2 gap-2">
            {items.map(item => (
              <button key={item.id} onClick={() => { toggleItem(item.id); setScanned(false); }}
                className={`text-xs px-2 py-2 rounded-lg border text-left transition-all ${item.active ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                <span className="font-medium">{item.label}</span>
                <span className="block text-[10px] opacity-60">Zeff={item.Z}, ρ={item.density} g/cm³</span>
              </button>
            ))}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>X-ray energy</span><span className="font-mono text-yellow-400">{energy} kVp</span></div>
            <Slider min={80} max={160} step={5} value={[energy]} onValueChange={([v]) => { setEnergy(v); setScanned(false); }} />
          </div>
          <div className="flex items-center justify-between py-2 border-b border-border/30">
            <span className="text-sm">Dual-energy mode</span>
            <button onClick={() => setDualE(d => !d)} className={`relative w-10 h-5 rounded-full transition-colors ${dualE ? 'bg-primary' : 'bg-border'}`}>
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${dualE ? 'translate-x-5' : ''}`} />
            </button>
          </div>
          <Button className="w-full gap-2" onClick={() => setScanned(true)}>
            <Zap className="h-4 w-4" /> Generate X-ray Image
          </Button>
          {scanned && threats.length > 0 && (
            <AlertBox type="danger">⚠ ALERT — {threats.length} threat item(s) detected: {threats.map(t => t.label).join(', ')}. Resolve bag for manual inspection.</AlertBox>
          )}
          {scanned && threats.length === 0 && (
            <AlertBox type="info">✓ No threats detected. Bag cleared for screening.</AlertBox>
          )}
          <Button size="sm" variant="outline" className="gap-1 h-8 w-full" onClick={() => onSave({ lab: 'Security Screening', items: activeItems.map(i => i.label), energy, dualEnergy: dualE, threats: threats.length })}>
            <Download className="h-3 w-3" /> Save Experiment
          </Button>
        </div>

        {/* Simulated X-ray view */}
        <div className="bg-card/60 border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">X-ray View</h3>
            <div className="flex gap-2 text-[10px]">
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full bg-orange-400" />Organic</span>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full bg-green-400" />Med-Z</span>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full bg-blue-400" />Metal</span>
            </div>
          </div>
          <div className="bg-black rounded-lg p-3 min-h-[260px] relative overflow-hidden" style={{ background: '#0a0a0a' }}>
            {!scanned && (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-sm">Click "Generate X-ray Image" to scan</div>
            )}
            {scanned && (
              <svg viewBox="0 0 300 200" className="w-full h-full">
                {/* Bag outline */}
                <rect x="20" y="20" width="260" height="160" rx="12" fill="#111" stroke="#333" strokeWidth="1.5" />
                {/* Items scattered in bag */}
                {activeItems.map((item, i) => {
                  const col = getColor(item);
                  const x = 40 + (i % 4) * 62 + (i % 2) * 8;
                  const y = 40 + Math.floor(i / 4) * 70;
                  const opacity = Math.min(0.95, 0.3 + item.density * 0.08);
                  return (
                    <g key={item.id}>
                      <rect x={x} y={y} width={52} height={34} rx={4} fill={col} opacity={opacity} />
                      {threats.includes(item) && scanned && (
                        <rect x={x - 1} y={y - 1} width={54} height={36} rx={5} fill="none" stroke="#ef4444" strokeWidth="2">
                          <animate attributeName="opacity" values="1;0.3;1" dur="0.8s" repeatCount="indefinite" />
                        </rect>
                      )}
                      <text x={x + 26} y={y + 22} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.6)" fontFamily="monospace">{item.label.slice(0, 8)}</text>
                    </g>
                  );
                })}
                {!dualE && <text x="150" y="192" textAnchor="middle" fontSize="8" fill="#475569">Standard transmission</text>}
                {dualE && <text x="150" y="192" textAnchor="middle" fontSize="8" fill="#22c55e">DUAL ENERGY — material discrimination active</text>}
              </svg>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── LAB 7: RADIATION BIOLOGY ─────────────────────────────────────────────────
const TISSUES = [
  { label: 'Early-responding tissue',  alpha: 0.35, beta: 0.035, color: '#ef4444' },
  { label: 'Late-responding tissue',   alpha: 0.15, beta: 0.05,  color: '#3b82f6' },
  { label: 'Tumour (typical)',         alpha: 0.30, beta: 0.030, color: '#f97316' },
  { label: 'Spinal cord',             alpha: 0.05, beta: 0.006, color: '#a855f7' },
];
const CANCER_RISK: Record<string, number> = { 'Thyroid (neck CT)': 0.3, 'Lung (chest CT)': 0.4, 'Breast (mammography)': 0.1, 'Colon (abdominal CT)': 0.6, 'Bone marrow (whole body)': 0.5 };

function BiologyLab({ onSave }: { onSave: (data: any) => void }) {
  const [tissueIdx, setTissueIdx] = useState(0);
  const [dose, setDose]           = useState(2.0);
  const tissue = TISSUES[tissueIdx];
  const survivalCurve = useMemo(() => cellSurvival(tissue.alpha, tissue.beta), [tissue]);
  const survAtDose = (Math.exp(-(tissue.alpha * dose + tissue.beta * dose * dose)) * 100).toFixed(2);
  const lethalDose  = tissue.alpha > 0 ? ((-tissue.alpha + Math.sqrt(tissue.alpha ** 2 + 4 * tissue.beta * Math.log(100))) / (2 * tissue.beta)).toFixed(1) : '—';
  const alphaBeta   = (tissue.alpha / tissue.beta).toFixed(1);

  // ARS dose response
  const arsData = [
    { label: 'No effect', dose: 0.1, pct: 0 },
    { label: 'N+V', dose: 1.0, pct: 10 },
    { label: 'ARS H-S', dose: 2.0, pct: 30 },
    { label: 'LD10', dose: 2.5, pct: 10 },
    { label: 'LD50', dose: 4.5, pct: 50 },
    { label: 'LD90', dose: 6.0, pct: 90 },
    { label: '100% lethal', dose: 10.0, pct: 100 },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-card/60 border border-border rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Cell Survival (LQ Model)</h3>
          <div className="space-y-2">
            {TISSUES.map((t, i) => (
              <button key={t.label} onClick={() => setTissueIdx(i)}
                className={`w-full text-left px-3 py-2 rounded-lg border text-xs transition-all ${tissueIdx === i ? 'border-primary bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:border-border'}`}>
                <span className="font-semibold">{t.label}</span>
                <span className="block text-[10px] opacity-70 mt-0.5">α={t.alpha} Gy⁻¹, β={t.beta} Gy⁻², α/β={+(t.alpha/t.beta).toFixed(1)} Gy</span>
              </button>
            ))}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm"><span>Dose</span><span className="font-mono text-orange-400">{dose} Gy</span></div>
            <Slider min={0.1} max={15} step={0.1} value={[dose]} onValueChange={([v]) => setDose(parseFloat(v.toFixed(1)))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <InfoCard label="Cell survival" value={`${survAtDose}%`} color={parseFloat(survAtDose) > 50 ? 'text-green-400' : 'text-red-400'} />
            <InfoCard label="α/β ratio" value={`${alphaBeta} Gy`} color="text-violet-400" />
          </div>
          <AlertBox type="info">
            LQ model: S = exp(−αD − βD²). Widely used in radiotherapy fractionation. α/β high ({'>'}10 Gy) = acutely responding; low (&lt;5 Gy) = late-responding tissues.
          </AlertBox>
          <Button size="sm" variant="outline" className="gap-1 h-8" onClick={() => onSave({ lab: 'Radiation Biology', tissue: tissue.label, dose, survival: survAtDose, alphaBeta })}>
            <Download className="h-3 w-3" /> Save Experiment
          </Button>
        </div>

        <div className="space-y-4">
          <div className="bg-card/60 border border-border rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">Cell Survival Curve</h4>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={survivalCurve} margin={{ top: 5, right: 15, bottom: 22, left: 10 }}>
                <XAxis dataKey="D" label={{ value: 'Dose (Gy)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 10 }} tick={{ fill: '#64748b', fontSize: 9 }} />
                <YAxis tickFormatter={v => `${v}%`} tick={{ fill: '#64748b', fontSize: 9 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} formatter={(v: any) => [`${v}%`, 'Survival']} />
                <ReferenceLine x={dose} stroke="#60a5fa" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="S" stroke={tissue.color} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-card/60 border border-border rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">Acute Radiation Syndrome (ARS) — Dose–Effect</h4>
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={arsData} margin={{ top: 5, right: 10, bottom: 22, left: 10 }}>
                <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 8 }} />
                <YAxis tickFormatter={v => `${v}%`} tick={{ fill: '#64748b', fontSize: 9 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }} />
                <Bar dataKey="pct" fill="#ef4444" opacity={0.8} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── LAB 8: AI ASSISTANT ─────────────────────────────────────────────────────
const AI_PROMPTS = [
  'Explain how bremsstrahlung X-rays are produced in a tungsten anode.',
  'What is the difference between HVL and TVL in shielding?',
  'Why is the linear-quadratic model used in radiotherapy?',
  'How does dual-energy X-ray discriminate between organic and metallic threats?',
  'What are the ICRP dose limits for occupationally exposed workers?',
  'Create a quiz on inverse square law calculations.',
];
function AIAssistantLab({ experiments }: { experiments: any[] }) {
  const [messages, setMessages] = useState<{ role: 'user'|'assistant'; text: string }[]>([
    { role: 'assistant', text: "Hello! I'm your Virtual Radiation Laboratory AI assistant. Ask me anything about radiation physics, safety, detectors, accelerators, shielding, or the experiments you've run in this lab. I can also generate quiz questions or draft experiment reports." }
  ]);
  const [input, setInput]       = useState('');
  const [loading, setLoading]   = useState(false);
  const scrollRef               = useRef<HTMLDivElement>(null);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg = { role: 'user' as const, text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const history = [...messages, userMsg].map(m => ({ role: m.role, content: m.text }));
    let assistantText = '';

    try {
      const resp = await fetch(`${API}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          message: text,
          conversation_id: null,
          system_override: `You are the AI assistant for a Virtual Radiation Laboratory. You are an expert in radiation physics, radiological safety (ICRP, IAEA, NCRP standards), X-ray technology, accelerators (LINAC, cyclotron, betatron), radioactive sources, shielding design, radiation detectors, security screening, and radiation biology. 
          
The user is working in a virtual lab with the following experiment history: ${JSON.stringify(experiments.slice(-3))}.

When answering:
- Be technically precise with numbers, units, and equations.
- Reference IAEA, ICRP, IEC, ISO, NCRP, ASTM standards where relevant.
- For quiz requests, create 5 multiple-choice questions with answers.
- For report requests, produce a structured engineering report with Introduction, Method, Results, Discussion, and References.
- Keep responses clear and educational.`,
        }),
      });

      if (!resp.ok) throw new Error(`API error ${resp.status}`);
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      setMessages(prev => [...prev, { role: 'assistant', text: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const d = JSON.parse(line.slice(6));
            if (d.type === 'chunk') {
              assistantText += d.chunk;
              setMessages(prev => {
                const copy = [...prev];
                copy[copy.length - 1] = { role: 'assistant', text: assistantText };
                return copy;
              });
            }
          } catch {}
        }
      }
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', text: `Error: ${e?.message || 'Failed to connect to AI assistant.'}` }]);
    } finally {
      setLoading(false);
      setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }), 50);
    }
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col h-full min-h-[500px] gap-4">
      <div className="flex flex-wrap gap-2">
        {AI_PROMPTS.map(p => (
          <button key={p} onClick={() => sendMessage(p)}
            className="text-[11px] px-2 py-1 rounded border border-border/50 text-muted-foreground hover:border-primary hover:text-foreground transition-colors truncate max-w-[200px]">
            {p}
          </button>
        ))}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-4 max-h-[480px] pr-1">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs ${m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-card border border-border'}`}>
              {m.role === 'user' ? 'U' : <Bot className="h-3.5 w-3.5 text-muted-foreground" />}
            </div>
            <div className={`rounded-xl px-4 py-2.5 text-sm leading-relaxed max-w-[80%] ${m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-card/80 border border-border text-foreground'}`}>
              <pre className="whitespace-pre-wrap font-sans">{m.text || (loading && i === messages.length - 1 ? '…' : '')}</pre>
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <Textarea
          value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
          placeholder="Ask about radiation physics, safety, calculations, or request a quiz / report…"
          className="flex-1 min-h-[56px] max-h-[120px] resize-none text-sm bg-card/60"
          disabled={loading}
        />
        <Button onClick={() => sendMessage(input)} disabled={loading || !input.trim()} className="h-14 px-4 shrink-0">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}

// ─── LAB 9: EXPERIMENT REPORTS ────────────────────────────────────────────────
function ReportsLab({ experiments }: { experiments: any[] }) {
  const [generating, setGenerating] = useState(false);
  const [report, setReport]         = useState('');
  const [selectedExp, setSelectedExp] = useState<number | null>(null);

  const generateReport = async () => {
    const exp = selectedExp !== null ? experiments[selectedExp] : experiments[experiments.length - 1];
    if (!exp) return;
    setGenerating(true);
    setReport('');

    try {
      const resp = await fetch(`${API}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          message: `Generate a professional engineering experiment report for the following virtual radiation laboratory experiment: ${JSON.stringify(exp, null, 2)}. 
          
Include:
1. Experiment Title
2. Objective
3. Equipment Used (virtual)
4. Theory (relevant physics)
5. Procedure
6. Results (with the recorded values)
7. Discussion (interpret the results, compare to literature)
8. Safety Considerations
9. Conclusions
10. References (IAEA, ICRP, IEC, relevant standards)

Format as a professional technical report. Use SI units throughout.`,
          conversation_id: null,
        }),
      });

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let text = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const d = JSON.parse(line.slice(6));
            if (d.type === 'chunk') { text += d.chunk; setReport(text); }
          } catch {}
        }
      }
    } catch {}
    finally { setGenerating(false); }
  };

  const downloadReport = () => {
    const blob = new Blob([report], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'lab-report.txt'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      {experiments.length === 0 ? (
        <AlertBox type="info">No saved experiments yet. Complete any laboratory and click "Save Experiment" to record your results here.</AlertBox>
      ) : (
        <>
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-3">Saved Experiments ({experiments.length})</h3>
            <div className="space-y-2">
              {experiments.map((exp, i) => (
                <button key={i} onClick={() => setSelectedExp(i === selectedExp ? null : i)}
                  className={`w-full text-left px-4 py-3 rounded-lg border text-sm transition-all ${selectedExp === i ? 'border-primary bg-primary/10' : 'border-border/50 hover:border-border bg-card/60'}`}>
                  <div className="flex justify-between items-center">
                    <span className="font-semibold">{exp.lab}</span>
                    <CheckCircle className={`h-4 w-4 ${selectedExp === i ? 'text-primary' : 'text-muted-foreground/30'}`} />
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5 font-mono">
                    {Object.entries(exp).filter(([k]) => k !== 'lab').map(([k, v]) => `${k}=${v}`).join(' · ')}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-2 flex-wrap">
            <Button onClick={generateReport} disabled={generating || experiments.length === 0} className="gap-2">
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
              {generating ? 'Generating…' : `Generate Report${selectedExp !== null ? ` — ${experiments[selectedExp]?.lab}` : ' — Latest'}`}
            </Button>
            {report && (
              <Button variant="outline" onClick={downloadReport} className="gap-2">
                <Download className="h-4 w-4" /> Download .txt
              </Button>
            )}
          </div>

          {report && (
            <div className="bg-card/60 border border-border rounded-xl p-5">
              <pre className="text-xs text-foreground font-mono leading-relaxed whitespace-pre-wrap max-h-[500px] overflow-y-auto">{report}</pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── LAB DEFINITIONS ─────────────────────────────────────────────────────────
interface Lab { id: string; label: string; icon: any; color: string; desc: string; badge: string }
const LABS: Lab[] = [
  { id: 'xray-tube',   label: 'X-ray Tube Lab',      icon: Zap,      color: 'text-yellow-400', desc: 'kVp, mA, target, filtration — live spectrum & heat', badge: 'Physics' },
  { id: 'linac',       label: 'LINAC Lab',            icon: Cpu,      color: 'text-violet-400', desc: '3–15 MeV beam energy, depth-dose, penetration',         badge: 'Accelerator' },
  { id: 'radioisotope',label: 'Radioactive Source Lab',icon: Atom,    color: 'text-orange-400', desc: 'Co-60, Cs-137, Ir-192, decay, inverse square law',     badge: 'Nuclear' },
  { id: 'shielding',   label: 'Shielding Lab',        icon: Shield,   color: 'text-green-400',  desc: 'Lead, steel, concrete, PE — HVL, TVL, cost estimate',   badge: 'Protection' },
  { id: 'detector',    label: 'Detector Lab',         icon: Radio,    color: 'text-cyan-400',   desc: 'GM, NaI, HPGe, CdZnTe — efficiency, resolution, spectra',badge: 'Detection' },
  { id: 'security',    label: 'Security Screening Lab',icon: Eye,     color: 'text-teal-400',   desc: 'Virtual baggage scanner, dual-energy, threat detection', badge: 'Security' },
  { id: 'biology',     label: 'Radiation Biology Lab', icon: Dna,     color: 'text-red-400',    desc: 'Cell survival (LQ model), ARS, dose-response',          badge: 'Biology' },
  { id: 'ai',          label: 'AI Lab Assistant',     icon: Bot,      color: 'text-blue-400',   desc: 'Ask questions, get quizzes, generate explanations',     badge: 'AI' },
  { id: 'reports',     label: 'Experiment Reports',   icon: FileText, color: 'text-lime-400',   desc: 'AI-generated professional lab reports from saved data',  badge: 'Reports' },
];

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────
const STORAGE_KEY = 'vlab-experiments';

export default function VirtualLabPage() {
  const [activeLab, setActiveLab]       = useState<string | null>(null);
  const [experiments, setExperiments]   = useState<any[]>(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; }
  });

  const saveExperiment = useCallback((data: any) => {
    const updated = [...experiments, { ...data, savedAt: new Date().toISOString() }].slice(-50);
    setExperiments(updated);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  }, [experiments]);

  const lab = LABS.find(l => l.id === activeLab);

  return (
    <div className="flex bg-background flex-col md:flex-row md:h-full md:overflow-hidden overflow-y-auto">
      {/* Sidebar */}
      <div className="w-full md:w-[248px] md:shrink-0 border-r border-border bg-card/30 flex flex-col md:h-full">
        <div className="p-4 border-b border-border bg-card shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-emerald-500/10 flex items-center justify-center ring-1 ring-emerald-500/30 shrink-0">
              <FlaskConical className="h-5 w-5 text-emerald-400" />
            </div>
            <div>
              <h2 className="font-bold text-sm leading-tight">Virtual Radiation</h2>
              <h2 className="font-bold text-sm leading-tight text-emerald-400">Laboratory</h2>
            </div>
          </div>
          <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mt-2">AI-Powered · 9 Labs</p>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2">
            <button
              onClick={() => setActiveLab(null)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors mb-1 ${!activeLab ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'}`}>
              <Layers className="h-4 w-4 shrink-0" />
              <span className="text-xs font-medium">Lab Dashboard</span>
            </button>
            {LABS.map(l => {
              const Icon = l.icon;
              const isActive = activeLab === l.id;
              return (
                <button key={l.id} onClick={() => setActiveLab(l.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'}`}>
                  <Icon className={`h-4 w-4 shrink-0 ${isActive ? '' : l.color}`} />
                  <span className="text-xs font-medium flex-1 truncate text-left">{l.label}</span>
                </button>
              );
            })}
          </div>
        </ScrollArea>

        <div className="p-3 border-t border-border bg-card/50 shrink-0 space-y-1">
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>Saved experiments</span>
            <span className="font-mono text-foreground">{experiments.length}</span>
          </div>
          {experiments.length > 0 && (
            <button onClick={() => { setExperiments([]); localStorage.removeItem(STORAGE_KEY); }}
              className="text-[10px] text-red-400/60 hover:text-red-400 transition-colors">
              Clear history
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col min-w-0 min-h-[60vh] md:min-h-0">
        {!activeLab ? (
          /* Dashboard */
          <ScrollArea className="flex-1">
            <div className="p-6 max-w-5xl mx-auto">
              <div className="mb-8">
                <h1 className="text-2xl font-bold mb-2">Virtual Radiation Laboratory</h1>
                <p className="text-muted-foreground">The world's first AI-powered virtual radiation lab — experiment safely with X-ray tubes, LINACs, radioactive sources, shielding, detectors, security screening, and radiation biology.</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {LABS.map(l => {
                  const Icon = l.icon;
                  return (
                    <button key={l.id} onClick={() => setActiveLab(l.id)}
                      className="group text-left bg-card/60 border border-border rounded-xl p-5 hover:border-primary/50 hover:bg-card/80 transition-all">
                      <div className="flex items-start gap-4">
                        <div className={`h-10 w-10 rounded-lg bg-background flex items-center justify-center ring-1 ring-border group-hover:ring-primary/40 transition-all shrink-0`}>
                          <Icon className={`h-5 w-5 ${l.color}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="font-semibold text-sm text-foreground">{l.label}</span>
                            <Badge variant="outline" className={`text-[10px] px-1.5 h-4 ${l.color} border-current`}>{l.badge}</Badge>
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">{l.desc}</p>
                        </div>
                      </div>
                      <div className="mt-3 flex items-center gap-1 text-xs text-muted-foreground group-hover:text-primary transition-colors">
                        <span>Open laboratory</span>
                        <ChevronRight className="h-3 w-3" />
                      </div>
                    </button>
                  );
                })}
              </div>

              {experiments.length > 0 && (
                <div className="mt-8">
                  <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-3">Recent Experiments</h2>
                  <div className="space-y-2">
                    {experiments.slice(-5).reverse().map((exp, i) => (
                      <div key={i} className="flex items-center gap-3 px-4 py-2.5 bg-card/60 border border-border rounded-lg text-xs">
                        <CheckCircle className="h-3.5 w-3.5 text-green-400 shrink-0" />
                        <span className="font-semibold text-foreground">{exp.lab}</span>
                        <span className="text-muted-foreground font-mono truncate">
                          {Object.entries(exp).filter(([k]) => !['lab','savedAt'].includes(k)).slice(0,3).map(([k,v]) => `${k}=${v}`).join(' · ')}
                        </span>
                        <span className="ml-auto text-muted-foreground/50 shrink-0">{new Date(exp.savedAt).toLocaleTimeString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-card/40 border border-border rounded-xl p-4">
                  <BookOpen className="h-5 w-5 text-blue-400 mb-2" />
                  <h3 className="font-semibold text-sm mb-1">Standards-Based</h3>
                  <p className="text-xs text-muted-foreground">All physics models reference IAEA, ICRP, IEC, NCRP, and ISO standards.</p>
                </div>
                <div className="bg-card/40 border border-border rounded-xl p-4">
                  <Activity className="h-5 w-5 text-green-400 mb-2" />
                  <h3 className="font-semibold text-sm mb-1">Real Physics</h3>
                  <p className="text-xs text-muted-foreground">Kramers rule, LQ model, inverse square law, and depth-dose calculations.</p>
                </div>
                <div className="bg-card/40 border border-border rounded-xl p-4">
                  <Bot className="h-5 w-5 text-violet-400 mb-2" />
                  <h3 className="font-semibold text-sm mb-1">AI-Powered</h3>
                  <p className="text-xs text-muted-foreground">Ask questions, generate quizzes, and produce professional experiment reports.</p>
                </div>
              </div>
            </div>
          </ScrollArea>
        ) : (
          /* Active lab */
          <>
            <div className="border-b border-border bg-card/50 px-6 py-4 shrink-0">
              <div className="flex items-center gap-3">
                <button onClick={() => setActiveLab(null)} className="text-muted-foreground hover:text-foreground text-xs">← Dashboard</button>
                <span className="text-muted-foreground">/</span>
                {lab && (
                  <>
                    <lab.icon className={`h-4 w-4 ${lab.color}`} />
                    <h1 className="font-bold text-base">{lab.label}</h1>
                    <Badge variant="outline" className={`text-xs ${lab.color} border-current`}>{lab.badge}</Badge>
                  </>
                )}
              </div>
            </div>

            <ScrollArea className="flex-1">
              <div className="p-6 max-w-5xl mx-auto">
                {activeLab === 'xray-tube'    && <XrayTubeLab   onSave={saveExperiment} />}
                {activeLab === 'linac'         && <LinacLab       onSave={saveExperiment} />}
                {activeLab === 'radioisotope'  && <RadioactiveLab onSave={saveExperiment} />}
                {activeLab === 'shielding'     && <ShieldingLab   onSave={saveExperiment} />}
                {activeLab === 'detector'      && <DetectorLab    onSave={saveExperiment} />}
                {activeLab === 'security'      && <SecurityLab    onSave={saveExperiment} />}
                {activeLab === 'biology'       && <BiologyLab     onSave={saveExperiment} />}
                {activeLab === 'ai'            && <AIAssistantLab experiments={experiments} />}
                {activeLab === 'reports'       && <ReportsLab     experiments={experiments} />}
              </div>
            </ScrollArea>
          </>
        )}
      </div>
    </div>
  );
}
