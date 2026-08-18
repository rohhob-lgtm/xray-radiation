import type { Film, SceneCtx } from './film-player';
import { Box, Dot, Wave, Plate, ease, clamp, fade } from './film-player';

// ═══════════════════════════════════════════════════════════════════════════════
// Film scenes — X-ray tube, LINAC, betatron, cyclotron, synchrotron, Van de Graaff
// Every scene is a pure function of the film clock so it scrubs like real video.
// ═══════════════════════════════════════════════════════════════════════════════

// ─── Shared scenery ───────────────────────────────────────────────────────────
function TubeEnvelope({ dim = false }: { dim?: boolean }) {
  return (
    <g opacity={dim ? 0.35 : 1}>
      <rect x="120" y="90" width="400" height="130" rx="24" fill="#0d1524" stroke="#334155" strokeWidth="2" />
      <rect x="136" y="104" width="368" height="102" rx="14" fill="#080e1a" stroke="#1d4ed8" strokeWidth="1" strokeDasharray="5 4" />
      <text x="150" y="120" fontSize="7" fill="#3b82f6">VACUUM &lt; 10⁻⁷ mbar</text>
      {/* cathode block */}
      <rect x="146" y="126" width="34" height="56" rx="4" fill="#152a52" stroke="#3b82f6" strokeWidth="1.5" />
      <text x="163" y="121" textAnchor="middle" fontSize="7" fill="#93c5fd">CATHODE</text>
      {/* anode block */}
      <rect x="440" y="118" width="52" height="74" rx="6" fill="#14301c" stroke="#22c55e" strokeWidth="1.5" />
      <text x="466" y="113" textAnchor="middle" fontSize="7" fill="#86efac">ANODE</text>
      <polygon points="440,132 492,144 492,158 440,170" fill="#4b5563" stroke="#9ca3af" strokeWidth="1" />
      <text x="466" y="185" textAnchor="middle" fontSize="6" fill="#9ca3af">W / Re track</text>
    </g>
  );
}

/** Bremsstrahlung spectrum path, optionally filtered (hardened) */
function spectrumPath(kvp: number, filterMm: number, x0: number, y0: number, w: number, h: number) {
  const pts: string[] = [];
  const n = 48;
  for (let i = 0; i <= n; i++) {
    const e = (i / n) * kvp;
    // Kramers rule + crude exponential filtration term
    const kramers = Math.max(0, kvp - e);
    const atten = e < 1 ? 0 : Math.exp(-filterMm * 60 / Math.pow(e, 2.4));
    const v = kramers * atten;
    pts.push(`${(x0 + (i / n) * w).toFixed(1)},${(y0 + h - (v / kvp) * h * 1.9).toFixed(1)}`);
  }
  return `M ${x0},${y0 + h} L ${pts.join(' L ')} L ${x0 + w},${y0 + h} Z`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1 — X-RAY TUBE
// ═══════════════════════════════════════════════════════════════════════════════
function xrayTubeScene({ ch, p, t }: SceneCtx) {
  switch (ch) {
    // ── Thermionic emission ──
    case 0: {
      const heat = ease(p * 1.6);
      const cloud = Array.from({ length: 14 }, (_, i) => {
        const a = (i / 14) * Math.PI * 2 + t * 1.2;
        const rr = 8 + 6 * Math.sin(t * 2 + i);
        return { x: 190 + Math.cos(a) * rr * 1.6, y: 154 + Math.sin(a) * rr };
      });
      return (
        <g>
          <TubeEnvelope />
          {[0, 1, 2, 3, 4].map(i => (
            <ellipse key={i} cx={163} cy={134 + i * 11} rx="9" ry="3"
              fill="none" stroke={`rgb(${Math.round(180 + 75 * heat)},${Math.round(120 + 60 * heat)},60)`} strokeWidth={1.2 + heat} />
          ))}
          <circle cx="163" cy="156" r={26 * heat} fill="url(#fp-hot)" opacity={0.7 * heat} />
          {heat > 0.4 && cloud.map((c, i) => <Dot key={i} x={c.x} y={c.y} r={2.2} color="#60a5fa" opacity={(heat - 0.4) * 1.6} halo={false} />)}
          <Plate x={190} y={228} w={280} color="#f59e0b" lines={[
            'FILAMENT CIRCUIT — 8-12 V @ 3-5 A',
            `T ≈ ${Math.round(300 + 2100 * heat)} K   ·  W work function 4.5 eV`,
            'Richardson–Dushman:  J = A T² e^(−φ/kT)',
          ]} />
          <text x="80" y="160" fontSize="8" fill="#fbbf24">heater</text>
          <line x1="100" y1="164" x2="144" y2="156" stroke="#f59e0b" strokeWidth="1" strokeDasharray="3 2" />
          <text x="230" y="146" fontSize="7" fill="#60a5fa">space-charge cloud</text>
        </g>
      );
    }
    // ── Acceleration ──
    case 1: {
      const kv = Math.round(lerpN(0, 150, ease(p * 2)));
      const beam = Array.from({ length: 6 }, (_, i) => {
        const ph = ((t * 0.9 + i / 6) % 1);
        return { x: 180 + ph * 258, y: 156 + Math.sin(ph * Math.PI) * (1 - ph) * 8, o: ph > 0.96 ? 0 : 1 };
      });
      return (
        <g>
          <TubeEnvelope />
          <path d="M 146 128 L 186 140 L 186 172 L 146 184 Z" fill="none" stroke="#60a5fa" strokeWidth="1" strokeDasharray="3 2" />
          <text x="150" y="200" fontSize="6.5" fill="#60a5fa">focusing cup</text>
          {beam.map((b, i) => <Dot key={i} x={b.x} y={b.y} r={3} color="#60a5fa" opacity={b.o} />)}
          <line x1="163" y1="220" x2="163" y2="248" stroke="#ef4444" strokeWidth="1.5" />
          <line x1="466" y1="220" x2="466" y2="248" stroke="#22c55e" strokeWidth="1.5" />
          <rect x="250" y="240" width="130" height="22" rx="4" fill="#0f172a" stroke="#475569" />
          <text x="315" y="255" textAnchor="middle" fontSize="8" fill="#cbd5e1">HF GENERATOR &gt; 40 kHz</text>
          <line x1="163" y1="248" x2="250" y2="251" stroke="#ef4444" strokeWidth="1" />
          <line x1="466" y1="248" x2="380" y2="251" stroke="#22c55e" strokeWidth="1" />
          <text x="315" y="234" textAnchor="middle" fontSize="13" fill="#fde047" fontWeight="bold">{kv} kVp</text>
          <Plate x={430} y={228} w={200} color="#38bdf8" lines={[
            'E_kin = e · kVp',
            `v ≈ ${(Math.sqrt(1 - 1 / Math.pow(1 + kv / 511, 2)) * 100).toFixed(0)} % c`,
            'ripple < 1 % → stable spectrum',
          ]} />
        </g>
      );
    }
    // ── Bremsstrahlung ──
    case 2: {
      const k = (t * 0.55) % 1;
      const ex = 200 + k * 180;
      const dy = k > 0.45 ? Math.pow((k - 0.45) * 2.6, 2) * 46 : 0;
      const emitted = k > 0.45;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">MICROSCOPIC VIEW — NUCLEAR DECELERATION FIELD</text>
          <circle cx="380" cy="150" r="52" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 4" />
          <circle cx="380" cy="150" r="30" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 4" />
          <circle cx="380" cy="150" r="11" fill="#7f1d1d" stroke="#ef4444" strokeWidth="1.5" />
          <text x="380" y="153" textAnchor="middle" fontSize="8" fill="#fecaca">W</text>
          <text x="380" y="176" textAnchor="middle" fontSize="7" fill="#94a3b8">Z = 74 nucleus</text>
          <Dot x={ex} y={150 - dy} r={3.5} color="#60a5fa" />
          <path d={`M 200 150 Q ${330} 150 ${ex} ${150 - dy}`} fill="none" stroke="#3b82f6" strokeWidth="1" strokeDasharray="3 3" opacity="0.7" />
          {emitted && <Wave x={ex} y={150 - dy} angle={-0.5} len={90 * (k - 0.45) * 2} color="#fde047" phase={t * 8} />}
          <Plate x={40} y={200} w={300} color="#fde047" lines={[
            'BREMSSTRAHLUNG  ("braking radiation")',
            'Continuous spectrum, endpoint E_max = e·kVp',
            'Yield ∝ Z · kVp²  →  high-Z target, high kV',
          ]} />
          <path d={spectrumPath(150, 0, 430, 210, 170, 56)} fill="#fde047" fillOpacity="0.18" stroke="#fde047" strokeWidth="1.2" />
          <text x="430" y="278" fontSize="7" fill="#94a3b8">0</text>
          <text x="596" y="278" fontSize="7" fill="#94a3b8">kVp</text>
          <text x="515" y="204" textAnchor="middle" fontSize="7" fill="#fde047">continuous spectrum</text>
        </g>
      );
    }
    // ── Characteristic ──
    case 3: {
      const stage = p * 3;
      const showHole = stage > 0.6;
      const showDrop = stage > 1.2;
      const showPhoton = stage > 1.9;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">CHARACTERISTIC EMISSION — INNER-SHELL VACANCY</text>
          <circle cx="250" cy="150" r="9" fill="#7f1d1d" stroke="#ef4444" strokeWidth="1.5" />
          {[26, 46, 66].map((r, i) => <circle key={i} cx="250" cy="150" r={r} fill="none" stroke="#334155" strokeWidth="1" />)}
          <text x="250" y="118" textAnchor="middle" fontSize="7" fill="#64748b">K</text>
          <text x="250" y="98" textAnchor="middle" fontSize="7" fill="#64748b">L</text>
          <text x="250" y="78" textAnchor="middle" fontSize="7" fill="#64748b">M</text>
          {!showHole && <Dot x={250 + 26 * Math.cos(t * 2)} y={150 + 26 * Math.sin(t * 2)} r={3} color="#60a5fa" />}
          {showHole && <circle cx={250 + 26 * Math.cos(1.2)} cy={150 + 26 * Math.sin(1.2)} r="4" fill="none" stroke="#f87171" strokeWidth="1.5" strokeDasharray="2 2" />}
          {!showHole && <Dot x={110 + ease(stage / 0.6) * 110} y={150} r={3} color="#818cf8" />}
          {showDrop && !showPhoton && <Dot x={250 + lerpN(46, 26, ease((stage - 1.2) / 0.7)) * Math.cos(1.2)} y={150 + lerpN(46, 26, ease((stage - 1.2) / 0.7)) * Math.sin(1.2)} r={3} color="#60a5fa" />}
          {showPhoton && <Wave x={260} y={140} angle={-0.35} len={110 * clamp((stage - 1.9) / 1)} color="#a78bfa" phase={t * 9} />}
          <Plate x={410} y={90} w={210} color="#a78bfa" lines={[
            'TUNGSTEN LINES',
            'Kα₁ 59.3 keV   Kα₂ 58.0 keV',
            'Kβ₁ 67.2 keV   K-edge 69.5 keV',
            'Discrete → material fingerprint',
          ]} />
          <path d={spectrumPath(150, 0.1, 410, 190, 200, 62)} fill="#fde047" fillOpacity="0.14" stroke="#fde047" strokeWidth="1.1" />
          {showPhoton && (<>
            <line x1="489" y1="252" x2="489" y2={252 - 46 * clamp((stage - 1.9) / 0.8)} stroke="#a78bfa" strokeWidth="2" />
            <line x1="500" y1="252" x2="500" y2={252 - 30 * clamp((stage - 1.9) / 0.8)} stroke="#a78bfa" strokeWidth="2" />
            <text x="512" y="212" fontSize="7" fill="#a78bfa">Kα / Kβ</text>
          </>)}
          <text x="450" y="268" fontSize="7" fill="#94a3b8">photon energy →</text>
        </g>
      );
    }
    // ── Heat / rotating anode ──
    case 4: {
      const spin = t * 7;
      const heat = 0.35 + 0.65 * Math.abs(Math.sin(p * Math.PI));
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">THERMAL LOAD — ROTATING ANODE, FOCAL TRACK</text>
          <g transform="translate(230 160)">
            <ellipse cx="0" cy="0" rx="92" ry="34" fill="#1f2937" stroke="#6b7280" strokeWidth="1.5" />
            <ellipse cx="0" cy="0" rx="66" ry="24" fill="none" stroke="#9ca3af" strokeWidth="1" strokeDasharray="4 3" />
            {Array.from({ length: 12 }, (_, i) => {
              const a = spin + (i / 12) * Math.PI * 2;
              return <circle key={i} cx={Math.cos(a) * 78} cy={Math.sin(a) * 29} r="2" fill="#4b5563" />;
            })}
            <ellipse cx={Math.cos(spin) * 78} cy={Math.sin(spin) * 29} rx="12" ry="6" fill="#fca5a5" opacity={heat} />
            <ellipse cx="0" cy="0" rx="10" ry="5" fill="#374151" stroke="#9ca3af" />
          </g>
          <text x="230" y="212" textAnchor="middle" fontSize="7" fill="#9ca3af">3 000 – 10 800 RPM · focal track spreads the load</text>
          {/* heat bar */}
          <rect x="410" y="96" width="190" height="12" rx="6" fill="#0f172a" stroke="#334155" />
          <rect x="411" y="97" width={188 * 0.99} height="10" rx="5" fill="#ef4444" opacity="0.85" />
          <rect x="411" y="97" width={188 * 0.01} height="10" rx="5" fill="#fde047" />
          <text x="410" y="92" fontSize="7" fill="#94a3b8">energy budget</text>
          <text x="410" y="124" fontSize="8" fill="#f87171">99 % heat</text>
          <text x="560" y="124" fontSize="8" fill="#fde047" textAnchor="end">1 % X-ray</text>
          <Plate x={410} y={140} w={210} color="#f87171" lines={[
            'AHU = kVp × mA × s × factor',
            'Focal-track T up to ~2 600 °C',
            'Cooling: oil bath → HX → chiller',
            'Overload → pitting, cracks, seizure',
          ]} />
          <Plate x={60} y={232} w={300} color="#38bdf8" lines={[
            'ANODE ANGLE 7–20°  →  line-focus principle',
            'Effective focal spot = actual × sin θ  (heel effect)',
          ]} />
        </g>
      );
    }
    // ── Filtration & output ──
    default: {
      const fmm = ease(p * 1.5) * 3;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">FILTRATION, COLLIMATION &amp; USEFUL BEAM</text>
          <rect x="60" y="120" width="26" height="70" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.5" />
          <text x="73" y="204" textAnchor="middle" fontSize="7" fill="#86efac">target</text>
          <polygon points="86,150 200,110 200,196 86,158" fill="url(#fp-beam)" />
          <rect x="150" y="104" width="10" height="100" rx="2" fill="#334155" stroke="#94a3b8" strokeWidth="1" />
          <text x="155" y="98" textAnchor="middle" fontSize="7" fill="#cbd5e1">Al/Cu</text>
          <text x="155" y="218" textAnchor="middle" fontSize="7" fill="#fbbf24">{fmm.toFixed(1)} mm Al eq.</text>
          <rect x="205" y="100" width="12" height="42" fill="#1c1917" stroke="#6b7280" />
          <rect x="205" y="168" width="12" height="42" fill="#1c1917" stroke="#6b7280" />
          <text x="211" y="94" textAnchor="middle" fontSize="7" fill="#cbd5e1">collimator</text>
          <polygon points="217,142 300,128 300,182 217,168" fill="#fde047" fillOpacity={0.22} />
          <text x="256" y="232" textAnchor="middle" fontSize="7" fill="#fde047">useful beam → patient / object</text>
          {/* live spectrum comparison */}
          <path d={spectrumPath(150, 0, 350, 100, 250, 120)} fill="#64748b" fillOpacity="0.12" stroke="#64748b" strokeWidth="1" strokeDasharray="3 3" />
          <path d={spectrumPath(150, fmm, 350, 100, 250, 120)} fill="#fde047" fillOpacity="0.2" stroke="#fde047" strokeWidth="1.4" />
          <text x="350" y="94" fontSize="7" fill="#94a3b8">unfiltered (dashed) vs filtered</text>
          <text x="350" y="234" fontSize="7" fill="#94a3b8">0</text>
          <text x="600" y="234" fontSize="7" fill="#94a3b8" textAnchor="end">150 keV</text>
          <Plate x={350} y={244} w={260} color="#38bdf8" lines={[
            'Soft photons removed → skin dose ↓, HVL ↑',
            'IEC 60522: ≥ 2.5 mm Al total above 70 kV',
          ]} />
        </g>
      );
    }
  }
}

const lerpN = (a: number, b: number, p: number) => a + (b - a) * clamp(p);

export const XRAY_TUBE_FILM: Film = {
  id: 'film-xray-tube',
  title: 'Inside the X-ray Tube — from hot filament to useful beam',
  tagline: 'Six-chapter animated walkthrough of thermionic emission, acceleration, photon production, heat and filtration',
  duration: 36,
  accent: 'text-blue-400',
  hex: '#60a5fa',
  chapters: [
    { t: 0,  title: 'Thermionic emission', caption: 'The tungsten filament is heated to about 2 400 K by a low-voltage circuit. Electrons gain enough thermal energy to escape the metal surface and form a space-charge cloud around the filament.', detail: 'Richardson–Dushman: J = A·T²·e^(−φ/kT). Filament current controls tube current (mA) — kVp does not.' },
    { t: 6,  title: 'Acceleration across the gap', caption: 'The high-voltage generator places the anode tens to hundreds of kilovolts above the cathode. The focusing cup shapes an electrostatic lens that drives the cloud into a narrow beam aimed at the focal spot.', detail: 'At 150 kVp electrons arrive at roughly 0.63 c. Generator ripple below 1 % keeps the spectrum stable shot-to-shot.' },
    { t: 12, title: 'Bremsstrahlung production', caption: 'Inside the target, electrons are deflected by the Coulomb field of tungsten nuclei. Each deflection radiates a photon whose energy is whatever kinetic energy the electron lost — producing a continuous spectrum up to the tube potential.', detail: 'Yield rises with atomic number and with the square of the tube potential, which is why high-Z targets and high kV are efficient.' },
    { t: 18, title: 'Characteristic X-rays', caption: 'Some electrons eject a K-shell electron instead. An outer-shell electron drops into the vacancy and the energy difference leaves as a sharp characteristic line, unique to the target element.', detail: 'Tungsten: Kα₁ 59.3 keV, Kβ₁ 67.2 keV. These lines only appear once the tube potential exceeds the 69.5 keV K-edge.' },
    { t: 24, title: 'Heat and the rotating anode', caption: 'Only about one percent of the beam power becomes X-rays; the rest is heat. Spinning the anode spreads the load around a focal track instead of one spot, multiplying the tolerable instantaneous power.', detail: 'Anode heat units accumulate as kVp × mA × s. Exceeding the rating causes track pitting, envelope cracking or bearing seizure.' },
    { t: 30, title: 'Filtration and collimation', caption: 'Inherent and added filtration strip the low-energy photons that would only deposit dose without reaching the detector. Collimators then trim the field to the region of interest.', detail: 'Drag the timeline: the dashed curve is the raw spectrum, the solid one is the hardened beam after filtration.' },
  ],
  facts: [
    { label: 'Tube potential', value: '40–450 kV' },
    { label: 'Filament temperature', value: '≈ 2 400 K' },
    { label: 'Anode speed', value: '3 000–10 800 RPM' },
    { label: 'Conversion efficiency', value: '≈ 1 % X-ray' },
  ],
  scene: xrayTubeScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 2 — LINAC
// ═══════════════════════════════════════════════════════════════════════════════
function linacScene({ ch, p, t }: SceneCtx) {
  const rail = (dim = false) => (
    <g opacity={dim ? 0.3 : 1}>
      <Box x={40} y={126} w={58} h={48} label="e⁻ GUN" sub="thermionic" stroke="#a855f7" />
      <rect x="104" y="134" width="250" height="32" rx="4" fill="#0b1b34" stroke="#3b82f6" strokeWidth="1.5" />
      {Array.from({ length: 7 }, (_, i) => <line key={i} x1={122 + i * 33} y1="134" x2={122 + i * 33} y2="166" stroke="#1d4ed8" strokeWidth="1" />)}
      <text x="229" y="128" textAnchor="middle" fontSize="7" fill="#93c5fd">ACCELERATING STRUCTURE</text>
      <Box x={166} y={186} w={92} h={26} label="MAGNETRON" stroke="#a855f7" />
      <line x1="212" y1="186" x2="212" y2="166" stroke="#a855f7" strokeWidth="1.5" />
    </g>
  );

  switch (ch) {
    case 0: { // injection
      const g = ease(p * 1.4);
      return (
        <g>
          {rail()}
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">INJECTION — ELECTRON GUN &amp; BUNCHER</text>
          <circle cx="69" cy="150" r={16 * g} fill="url(#fp-hot)" opacity={0.8 * g} />
          {g > 0.3 && Array.from({ length: 5 }, (_, i) => {
            const ph = ((t * 1.1 + i / 5) % 1);
            return <Dot key={i} x={98 + ph * 40} y={150} r={2.8} color="#818cf8" opacity={g} />;
          })}
          <Plate x={380} y={100} w={230} color="#a78bfa" lines={[
            'Gun: 10–50 keV DC injection',
            'Buncher cavity groups electrons',
            'into RF-phase packets (bunches)',
            'Duty cycle: 1–5 µs @ 100–400 Hz',
          ]} />
          <Plate x={380} y={186} w={230} color="#38bdf8" lines={[
            'Only electrons riding the correct RF',
            'phase are captured — the rest are lost',
            'in the first few centimetres.',
          ]} />
        </g>
      );
    }
    case 1: { // RF wave
      const phase = t * 4;
      const wavePts = Array.from({ length: 60 }, (_, i) => {
        const x = 104 + (i / 59) * 250;
        const y = 150 - Math.sin((i / 59) * Math.PI * 6 - phase) * 22;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ');
      const bx = 104 + (((t * 0.35) % 1)) * 250;
      return (
        <g>
          {rail()}
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">RF ACCELERATION — SURFING THE TRAVELLING WAVE</text>
          <polyline points={wavePts} fill="none" stroke="#22d3ee" strokeWidth="1.4" opacity="0.85" />
          <Dot x={bx} y={150 - Math.sin(((bx - 104) / 250) * Math.PI * 6 - phase) * 22} r={4} color="#818cf8" />
          <text x="360" y="150" fontSize="7" fill="#22d3ee">2 856 MHz (S-band)</text>
          <Plate x={380} y={96} w={230} color="#22d3ee" lines={[
            'MAGNETRON vs KLYSTRON',
            'Magnetron  2–5 MW  ≤ 10 MeV  compact',
            'Klystron   5–50 MW  15 MeV+  stable',
            'Energy gain ≈ 10–15 MeV per metre',
          ]} />
          <Plate x={380} y={196} w={230} color="#38bdf8" lines={[
            'Standing-wave structures are shorter;',
            'travelling-wave structures need a load.',
            'SF₆ or vacuum waveguide feeds RF in.',
          ]} />
        </g>
      );
    }
    case 2: { // bending magnet
      const a = ease(p * 1.3);
      const ang = -Math.PI / 2 + a * (Math.PI * 1.5);
      const cx = 400, cy = 150, r = 34;
      return (
        <g>
          {rail(true)}
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">270° ACHROMATIC BENDING MAGNET</text>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="#22c55e" strokeWidth="10" strokeOpacity="0.18" />
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="#22c55e" strokeWidth="1.5" strokeDasharray="4 3" />
          <text x={cx} y={cy + 3} textAnchor="middle" fontSize="7" fill="#86efac">B field</text>
          <line x1="354" y1="150" x2={cx} y2="150" stroke="#818cf8" strokeWidth="1.5" strokeDasharray="3 2" />
          <Dot x={cx + Math.cos(ang) * r} y={cy + Math.sin(ang) * r} r={3.5} color="#818cf8" />
          <Box x={376} y={216} w={48} h={14} label="TARGET" stroke="#f59e0b" />
          <Box x={368} y={234} w={64} h={14} label="FLATTENING" stroke="#94a3b8" />
          <Box x={372} y={252} w={56} h={14} label="COLLIMATOR" stroke="#6b7280" />
          <Plate x={40} y={210} w={300} color="#4ade80" lines={[
            'The 270° bend selects one energy window',
            '(momentum dispersion) and folds the beam',
            'downwards so the gantry stays compact.',
            'Energy slits reject off-energy electrons.',
          ]} />
        </g>
      );
    }
    case 3: { // target and beam
      const k = (t * 0.8) % 1;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">TARGET → BREMSSTRAHLUNG → SHAPED PHOTON BEAM</text>
          <Box x={286} y={78} w={68} h={16} label="e⁻ 6 MeV" stroke="#818cf8" />
          <Dot x={320} y={100 + k * 18} r={3} color="#818cf8" />
          <rect x="292" y="120" width="56" height="12" rx="2" fill="#292524" stroke="#f59e0b" strokeWidth="1.5" />
          <text x="360" y="130" fontSize="7" fill="#fbbf24">W transmission target</text>
          <polygon points="320,132 240,270 400,270" fill="#fde047" fillOpacity="0.13" stroke="#fde047" strokeOpacity="0.4" />
          <path d="M 288 152 L 352 152" stroke="#94a3b8" strokeWidth="6" />
          <text x="368" y="156" fontSize="7" fill="#cbd5e1">flattening filter</text>
          <rect x="276" y="172" width="16" height="26" fill="#1c1917" stroke="#6b7280" />
          <rect x="348" y="172" width="16" height="26" fill="#1c1917" stroke="#6b7280" />
          <text x="380" y="190" fontSize="7" fill="#cbd5e1">primary collimator</text>
          <rect x="262" y="206" width="14" height="22" fill="#0f172a" stroke="#94a3b8" />
          <rect x="364" y="206" width="14" height="22" fill="#0f172a" stroke="#94a3b8" />
          <text x="392" y="222" fontSize="7" fill="#cbd5e1">MLC leaves</text>
          <Plate x={30} y={96} w={196} color="#fde047" lines={[
            'Forward-peaked at MeV energies:',
            'photon emission collapses into a',
            'narrow cone along the beam axis.',
          ]} />
          <Plate x={30} y={190} w={196} color="#38bdf8" lines={[
            'Dual ion chambers monitor dose and',
            'symmetry; 110 % of set dose triggers',
            'automatic termination (IEC 60601-2-1).',
          ]} />
        </g>
      );
    }
    default: { // cargo dual energy
      const scan = (t * 0.25) % 1;
      const hi = Math.floor(t * 3) % 2 === 0;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">CARGO INSPECTION — INTERLEAVED DUAL ENERGY</text>
          <Box x={30} y={130} w={70} h={44} label="LINAC" sub={hi ? '6 MeV' : '9 MeV'} stroke={hi ? '#38bdf8' : '#f472b6'} />
          <polygon points="100,152 260,96 260,214" fill={hi ? '#38bdf8' : '#f472b6'} fillOpacity="0.12" />
          <rect x="180" y="118" width="240" height="76" rx="4" fill="#111c2e" stroke="#475569" strokeWidth="1.5" />
          <text x="300" y="112" textAnchor="middle" fontSize="7" fill="#94a3b8">ISO container</text>
          <rect x={200 + scan * 180} y="140" width="26" height="30" rx="2" fill="#f97316" fillOpacity="0.5" stroke="#f97316" />
          <rect x={240 + scan * 120} y="150" width="18" height="22" rx="2" fill="#38bdf8" fillOpacity="0.5" stroke="#38bdf8" />
          <rect x="430" y="106" width="10" height="100" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.5" />
          <text x="446" y="156" fontSize="7" fill="#86efac">detector array</text>
          <Plate x={430} y={214} w={190} color="#f97316" lines={[
            'Z_eff from HE/LE ratio',
            'orange = organic (Z 6–8)',
            'blue = inorganic / metal',
          ]} />
          <Plate x={30} y={214} w={370} color="#38bdf8" lines={[
            'Pulse-to-pulse energy switching interleaves 6 and 9 MeV frames,',
            'so both images share the same geometry and container speed.',
            'Penetration: ~300 mm steel @6 MeV, ~380 mm @9 MeV.',
          ]} />
        </g>
      );
    }
  }
}

export const LINAC_FILM: Film = {
  id: 'film-linac',
  title: 'Linear Accelerator — RF power to megavolt photons',
  tagline: 'Gun, buncher, travelling-wave structure, 270° bend, target and dual-energy cargo imaging',
  duration: 34,
  accent: 'text-violet-400',
  hex: '#a78bfa',
  chapters: [
    { t: 0,  title: 'Injection', caption: 'A thermionic gun injects electrons at a few tens of keV. A buncher cavity gathers them into packets that sit on the accelerating phase of the radio-frequency wave.', detail: 'Electrons that arrive at the wrong RF phase are simply lost in the first centimetres of the structure.' },
    { t: 7,  title: 'RF acceleration', caption: 'A magnetron or klystron feeds megawatts of microwave power into the copper structure. Each bunch rides the wave crest and gains roughly 10–15 MeV per metre of structure.', detail: 'Medical machines run S-band at 2 856 MHz. Magnetrons are compact up to ~10 MeV; klystrons dominate above 15 MeV.' },
    { t: 14, title: 'Beam transport', caption: 'A 270° achromatic bending magnet folds the beam downwards and acts as an energy filter: only electrons within a narrow momentum window survive the slit.', detail: 'This keeps the gantry compact and guarantees a reproducible energy spectrum at the target.' },
    { t: 21, title: 'Target and beam shaping', caption: 'The electron beam strikes a high-Z transmission target. At MeV energies bremsstrahlung is forward-peaked, so a flattening filter, primary collimator and multileaf collimator shape the useful field.', detail: 'Two independent ion chambers monitor dose, symmetry and flatness, terminating the beam at 110 % of the set dose.' },
    { t: 28, title: 'Cargo dual energy', caption: 'Security LINACs switch energy pulse-to-pulse. Comparing high- and low-energy frames yields the effective atomic number, separating organic loads from metals inside a sealed container.', detail: 'Typical penetration: about 300 mm of steel at 6 MeV, 380 mm at 9 MeV.' },
  ],
  facts: [
    { label: 'Medical energy', value: '4–25 MV' },
    { label: 'RF frequency', value: '2 856 MHz' },
    { label: 'Pulse width / rate', value: '1–5 µs · 100–400 Hz' },
    { label: 'Gradient', value: '10–15 MeV / m' },
  ],
  scene: linacScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 3 — BETATRON
// ═══════════════════════════════════════════════════════════════════════════════
function betatronScene({ ch, p, t }: SceneCtx) {
  const cx = 250, cy = 156, R = 76;
  const core = (
    <g>
      <ellipse cx={cx} cy={cy} rx={R + 34} ry={R + 22} fill="none" stroke="#334155" strokeWidth="12" strokeOpacity="0.5" />
      <ellipse cx={cx} cy={cy} rx={R} ry={R * 0.62} fill="none" stroke="#64748b" strokeWidth="9" strokeOpacity="0.35" />
      <ellipse cx={cx} cy={cy} rx={R} ry={R * 0.62} fill="none" stroke="#94a3b8" strokeWidth="1" strokeDasharray="4 3" />
      <ellipse cx={cx} cy={cy} rx="26" ry="18" fill="#1f2937" stroke="#6b7280" strokeWidth="1.5" />
      <text x={cx} y={cy + 3} textAnchor="middle" fontSize="7" fill="#cbd5e1">CORE</text>
      <text x={cx} y={cy - R * 0.62 - 16} textAnchor="middle" fontSize="7" fill="#94a3b8">doughnut vacuum chamber</text>
    </g>
  );
  switch (ch) {
    case 0: {
      const B = Math.abs(Math.sin(p * Math.PI * 2));
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">AC MAGNET — RISING FLUX INDUCES THE ACCELERATING FIELD</text>
          {core}
          {Array.from({ length: 7 }, (_, i) => (
            <circle key={i} cx={cx} cy={cy} r={8 + i * 5} fill="none" stroke="#38bdf8" strokeWidth="1" opacity={B * (1 - i / 9)} />
          ))}
          <Plate x={420} y={92} w={200} color="#38bdf8" lines={[
            'Faraday:  ∮E·dl = −dΦ/dt',
            'The changing flux through the orbit',
            'is the accelerating "voltage".',
            'Only the rising quarter-cycle is used.',
          ]} />
          <rect x="420" y="196" width="200" height="60" rx="4" fill="#0b1220" stroke="#334155" />
          <polyline points={Array.from({ length: 50 }, (_, i) => `${420 + i * 4},${226 - Math.sin((i / 49) * Math.PI * 4) * 22}`).join(' ')}
            fill="none" stroke="#64748b" strokeWidth="1" />
          <circle cx={420 + p * 196} cy={226 - Math.sin(p * Math.PI * 4) * 22} r="3" fill="#38bdf8" />
          <text x="426" y="252" fontSize="7" fill="#94a3b8">50/60 Hz magnet cycle</text>
        </g>
      );
    }
    case 1: {
      const turns = p * 26;
      const a = turns * Math.PI * 2;
      const r = R * (0.35 + 0.6 * ease(p));
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">ORBIT GROWTH — ELECTRONS GAIN ENERGY EVERY TURN</text>
          {core}
          <ellipse cx={cx} cy={cy} rx={r} ry={r * 0.62} fill="none" stroke="#f472b6" strokeWidth="1.2" strokeDasharray="2 3" />
          <Dot x={cx + Math.cos(a) * r} y={cy + Math.sin(a) * r * 0.62} r={3.5} color="#f472b6" />
          <text x="420" y="106" fontSize="8" fill="#f472b6">turns: {Math.floor(turns * 10000).toLocaleString()}</text>
          <text x="420" y="122" fontSize="8" fill="#fde047">E ≈ {(p * 25).toFixed(1)} MeV</text>
          <Plate x={420} y={136} w={200} color="#f472b6" lines={[
            'A betatron pass is ~10⁵–10⁶ turns',
            'in a few milliseconds; each turn adds',
            'only a few hundred electron-volts.',
            'Path length ≈ hundreds of kilometres.',
          ]} />
        </g>
      );
    }
    case 2: {
      const wob = Math.sin(t * 3) * 6 * (1 - ease(p));
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">THE BETATRON CONDITION — KEEPING THE ORBIT STABLE</text>
          {core}
          <ellipse cx={cx} cy={cy} rx={R * 0.8 + wob} ry={(R * 0.8 + wob) * 0.62} fill="none" stroke="#f472b6" strokeWidth="1.4" />
          <Dot x={cx + Math.cos(t * 6) * (R * 0.8 + wob)} y={cy + Math.sin(t * 6) * (R * 0.8 + wob) * 0.62} r={3.5} color="#f472b6" />
          <Plate x={392} y={96} w={230} color="#fde047" lines={[
            'B̄(inside orbit) = 2 · B(at orbit)',
            'Flux must grow twice as fast as the',
            'guide field, or the radius drifts.',
            'Kerst & Serber, 1941 — the "2:1 rule".',
          ]} />
          <Plate x={392} y={196} w={230} color="#38bdf8" lines={[
            'Weak focusing (field index 0 < n < 1)',
            'damps radial and vertical wobble —',
            'watch the orbit settle as the film runs.',
          ]} />
        </g>
      );
    }
    default: {
      const k = ease(p * 1.6);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">EXTRACTION — BEAM DUMPED ONTO THE TUNGSTEN TARGET</text>
          {core}
          <ellipse cx={cx} cy={cy} rx={R * (0.95 + k * 0.28)} ry={R * (0.95 + k * 0.28) * 0.62} fill="none" stroke="#f472b6" strokeWidth="1.2" opacity={1 - k * 0.5} />
          <rect x={cx + R + 20} y={cy - 12} width="12" height="24" rx="2" fill="#292524" stroke="#f59e0b" strokeWidth="1.5" />
          <text x={cx + R + 26} y={cy - 20} textAnchor="middle" fontSize="7" fill="#fbbf24">W target</text>
          {k > 0.5 && Array.from({ length: 5 }, (_, i) => (
            <Wave key={i} x={cx + R + 34} y={cy - 8 + i * 4} angle={-0.35 + i * 0.18} len={70 * (k - 0.5) * 2} color="#fde047" phase={t * 8 + i} width={1.1} />
          ))}
          <Plate x={430} y={200} w={190} color="#fde047" lines={[
            '15–300 MeV photon endpoint',
            'Penetrates 100–300 mm steel',
            'No RF system → simple upkeep',
            'Superseded by LINACs in most NDT',
          ]} />
        </g>
      );
    }
  }
}

export const BETATRON_FILM: Film = {
  id: 'film-betatron',
  title: 'Betatron — accelerating electrons with pure induction',
  tagline: 'Flux ramp, orbit growth, the 2:1 betatron condition and target extraction',
  duration: 26,
  accent: 'text-pink-400',
  hex: '#f472b6',
  chapters: [
    { t: 0,  title: 'Rising magnetic flux', caption: 'A large laminated electromagnet is driven at mains frequency. The changing flux threading the electron orbit induces a circular electric field — that induced field, not an electrode, is what accelerates the beam.', detail: 'Only the rising quarter of each magnet cycle is usable, which is why betatrons pulse at line frequency.' },
    { t: 7,  title: 'Orbit growth', caption: 'Electrons make hundreds of thousands of turns inside the doughnut chamber in a few milliseconds. Each turn adds only a few hundred electron-volts, but the total path length runs to hundreds of kilometres.', detail: 'The energy climbs smoothly to tens or hundreds of MeV before extraction.' },
    { t: 14, title: 'The betatron condition', caption: 'For the radius to stay constant, the average field inside the orbit must be exactly twice the field at the orbit itself. Weak focusing then damps residual radial and vertical oscillations.', detail: 'Kerst and Serber formalised this in 1941; violating the 2:1 rule makes the beam spiral into the chamber wall.' },
    { t: 20, title: 'Extraction to target', caption: 'A perturbing field expands the orbit onto a tungsten target at the chamber edge, converting the electron beam into a hard bremsstrahlung spectrum for radiography of very thick steel.', detail: 'No RF system means simple maintenance — the reason a few betatrons still serve specialist NDT workshops.' },
  ],
  facts: [
    { label: 'Energy range', value: '15–300 MeV' },
    { label: 'Turns per pulse', value: '10⁵–10⁶' },
    { label: 'Pulse rate', value: '≈ 50/60 Hz' },
    { label: 'Steel penetration', value: '100–300 mm' },
  ],
  scene: betatronScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 4 — CYCLOTRON
// ═══════════════════════════════════════════════════════════════════════════════
function cyclotronScene({ ch, p, t }: SceneCtx) {
  const cx = 250, cy = 158;
  const dees = (
    <g>
      <path d={`M ${cx - 6} ${cy - 96} A 96 96 0 0 0 ${cx - 6} ${cy + 96} Z`} fill="#0b2540" stroke="#22d3ee" strokeWidth="1.5" />
      <path d={`M ${cx + 6} ${cy - 96} A 96 96 0 0 1 ${cx + 6} ${cy + 96} Z`} fill="#2a0b2e" stroke="#f472b6" strokeWidth="1.5" />
      <text x={cx - 52} y={cy} fontSize="9" fill="#67e8f9">DEE 1</text>
      <text x={cx + 22} y={cy} fontSize="9" fill="#f9a8d4">DEE 2</text>
      <circle cx={cx} cy={cy} r="100" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" />
    </g>
  );
  const spiral = (turns: number, k: number) => {
    const pts: string[] = [];
    const N = Math.max(2, Math.floor(turns * 40));
    for (let i = 0; i <= N; i++) {
      const f = i / N;
      const ang = f * turns * Math.PI * 2;
      const r = 8 + f * 84 * k;
      pts.push(`${(cx + Math.cos(ang) * r).toFixed(1)},${(cy + Math.sin(ang) * r).toFixed(1)}`);
    }
    return pts.join(' ');
  };
  switch (ch) {
    case 0: {
      const g = ease(p * 1.5);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">ION SOURCE AT THE CENTRE OF THE MAGNET GAP</text>
          {dees}
          <circle cx={cx} cy={cy} r={5 + 10 * g} fill="url(#fp-glow)" />
          <circle cx={cx} cy={cy} r="4" fill="#fde047" />
          <text x={cx} y={cy + 122} textAnchor="middle" fontSize="7" fill="#94a3b8">PIG / external source → H⁻ or protons</text>
          <Plate x={400} y={92} w={220} color="#fde047" lines={[
            'Static field B (1–2 T) fills the gap',
            'Ions born at the centre are bent into',
            'circles by the Lorentz force qv × B.',
            'Radius r = m v / (q B)',
          ]} />
          <Plate x={400} y={190} w={220} color="#38bdf8" lines={[
            'Modern medical machines accelerate',
            'H⁻ and strip it at extraction — a',
            'much cleaner way to get the beam out.',
          ]} />
        </g>
      );
    }
    case 1: {
      const gapFlip = Math.floor(t * 4) % 2 === 0;
      const ang = t * 5;
      const r = 26;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">THE GAP KICK — RF POLARITY FLIPS EVERY HALF TURN</text>
          {dees}
          <rect x={cx - 6} y={cy - 96} width="12" height="192" fill={gapFlip ? '#22d3ee' : '#f472b6'} fillOpacity="0.18" />
          <text x={cx} y={cy - 104} textAnchor="middle" fontSize="7" fill={gapFlip ? '#67e8f9' : '#f9a8d4'}>
            {gapFlip ? '← accelerating' : 'accelerating →'}
          </text>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="#4ade80" strokeWidth="1" strokeDasharray="2 3" />
          <Dot x={cx + Math.cos(ang) * r} y={cy + Math.sin(ang) * r} r={3.5} color="#4ade80" />
          <Plate x={400} y={96} w={220} color="#4ade80" lines={[
            'f_rf = q B / (2π m)',
            'The revolution time is independent',
            'of radius — so one fixed frequency',
            'keeps kicking every single turn.',
          ]} />
          <Plate x={400} y={196} w={220} color="#38bdf8" lines={[
            'Energy gain per gap = q · V_dee',
            'Typical dee voltage 30–100 kV',
          ]} />
        </g>
      );
    }
    case 2: {
      const k = ease(p);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">SPIRAL — RADIUS GROWS WITH MOMENTUM</text>
          {dees}
          <polyline points={spiral(9, k)} fill="none" stroke="#4ade80" strokeWidth="1.2" opacity="0.9" />
          <Dot x={cx + Math.cos(9 * Math.PI * 2 * 0.999) * (8 + 84 * k)} y={cy + Math.sin(9 * Math.PI * 2 * 0.999) * (8 + 84 * k)} r={3.5} color="#4ade80" />
          <text x="400" y="106" fontSize="8" fill="#4ade80">E ≈ {(k * 18).toFixed(1)} MeV</text>
          <Plate x={400} y={118} w={220} color="#4ade80" lines={[
            'E ∝ (q B r)² / 2m  — energy scales',
            'with the square of the pole radius,',
            'so higher energy means a bigger,',
            'heavier and far costlier magnet.',
          ]} />
        </g>
      );
    }
    case 3: {
      const drift = ease(p);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">RELATIVISTIC DETUNING &amp; THE ISOCHRONOUS FIX</text>
          {dees}
          <polyline points={spiral(7, 0.95)} fill="none" stroke="#64748b" strokeWidth="1" strokeDasharray="3 3" />
          {/* phase slip meter */}
          <rect x="400" y="96" width="220" height="46" rx="4" fill="#0b1220" stroke="#334155" />
          <text x="408" y="110" fontSize="7" fill="#94a3b8">RF phase vs particle</text>
          <line x1="408" y1="128" x2="612" y2="128" stroke="#334155" />
          <polyline points={Array.from({ length: 40 }, (_, i) => `${408 + i * 5.2},${128 - Math.sin(i * 0.5) * 10}`).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="1" />
          <polyline points={Array.from({ length: 40 }, (_, i) => `${408 + i * 5.2},${128 - Math.sin(i * 0.5 - drift * 2.2) * 10}`).join(' ')} fill="none" stroke="#f87171" strokeWidth="1.2" />
          <text x="408" y="140" fontSize="6.5" fill="#f87171">slip = {(drift * 90).toFixed(0)}°</text>
          <Plate x={400} y={152} w={220} color="#f87171" lines={[
            'γ grows → m grows → f_rev falls',
            'The bunch slips out of phase and',
            'acceleration stops.',
          ]} />
          <Plate x={400} y={214} w={220} color="#4ade80" lines={[
            'ISOCHRONOUS CYCLOTRON: raise B with',
            'radius (hill-valley sectors) so f_rev',
            'stays constant. Synchrocyclotrons',
            'instead sweep the RF frequency.',
          ]} />
        </g>
      );
    }
    default: {
      const k = ease(p * 1.3);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">EXTRACTION → TARGET → PET RADIOPHARMACEUTICAL</text>
          {dees}
          <polyline points={spiral(6, 0.96)} fill="none" stroke="#4ade80" strokeWidth="1" opacity="0.4" />
          <line x1={cx + 92} y1={cy} x2={cx + 92 + 60 * k} y2={cy} stroke="#4ade80" strokeWidth="2" markerEnd="url(#fp-arrow)" color="#4ade80" />
          <text x={cx + 96} y={cy - 8} fontSize="7" fill="#4ade80">stripper foil</text>
          <rect x={cx + 152} y={cy - 18} width="34" height="36" rx="4" fill="#0b2540" stroke="#38bdf8" strokeWidth="1.5" opacity={k} />
          <text x={cx + 169} y={cy + 3} textAnchor="middle" fontSize="7" fill="#7dd3fc" opacity={k}>[¹⁸O]</text>
          <text x={cx + 169} y={cy + 30} textAnchor="middle" fontSize="6.5" fill="#94a3b8" opacity={k}>water target</text>
          <Plate x={392} y={198} w={230} color="#38bdf8" lines={[
            '¹⁸O(p,n)¹⁸F   t½ = 109.8 min',
            '¹⁴N(p,α)¹¹C   t½ = 20.4 min',
            'Hot cell → FDG synthesis → QC → dose',
            'Short half-life forces on-site production',
          ]} />
        </g>
      );
    }
  }
}

export const CYCLOTRON_FILM: Film = {
  id: 'film-cyclotron',
  title: 'Cyclotron — resonance, spiral orbits and PET isotopes',
  tagline: 'Ion source, dee gap kicks, relativistic detuning, isochronous design and target chemistry',
  duration: 32,
  accent: 'text-emerald-400',
  hex: '#4ade80',
  chapters: [
    { t: 0,  title: 'Ion source', caption: 'Ions are created at the centre of a strong static magnetic field filling the gap between two D-shaped electrodes. The Lorentz force immediately bends them into a circular path.', detail: 'Most medical cyclotrons accelerate negative hydrogen ions, which makes extraction far simpler.' },
    { t: 6,  title: 'The gap kick', caption: 'A radio-frequency voltage across the dees reverses polarity every half revolution, so the ion is accelerated each time it crosses the gap. Non-relativistically the revolution period does not depend on radius, so one fixed frequency works for every turn.', detail: 'Cyclotron frequency: f = qB / 2πm. Dee voltages are typically 30–100 kV per gap.' },
    { t: 12, title: 'Spiral growth', caption: 'Every kick raises the momentum and therefore the orbit radius, tracing the familiar spiral outward from the centre toward the pole edge.', detail: 'Final energy scales with the square of the extraction radius and of the magnetic field — bigger magnet, higher energy.' },
    { t: 20, title: 'Relativistic limit', caption: 'As the ions approach relativistic speeds their mass grows, the revolution frequency falls, and the bunch slips out of phase with the RF. Acceleration stalls.', detail: 'Isochronous cyclotrons raise the field with radius using hill-and-valley sectors; synchrocyclotrons instead sweep the RF frequency downward.' },
    { t: 26, title: 'Extraction and isotopes', caption: 'A thin stripper foil removes the electrons from the negative ions, flipping the charge sign and bending the beam straight out to the target where the nuclear reaction happens.', detail: 'Oxygen-18 water bombarded with protons yields fluorine-18 for FDG — 110 minutes of half-life means the chemistry has to happen on-site.' },
  ],
  facts: [
    { label: 'Magnetic field', value: '1–2 T' },
    { label: 'Medical energy', value: '10–30 MeV' },
    { label: 'Dee voltage', value: '30–100 kV' },
    { label: 'F-18 half-life', value: '109.8 min' },
  ],
  scene: cyclotronScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 5 — SYNCHROTRON
// ═══════════════════════════════════════════════════════════════════════════════
function synchrotronScene({ ch, p, t }: SceneCtx) {
  const cx = 230, cy = 160, rx = 120, ry = 84;
  const ring = (dim = false) => (
    <g opacity={dim ? 0.35 : 1}>
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#1e293b" strokeWidth="14" />
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#22d3ee" strokeWidth="1" strokeDasharray="3 4" opacity="0.6" />
      {Array.from({ length: 12 }, (_, i) => {
        const a = (i / 12) * Math.PI * 2;
        return <rect key={i} x={cx + Math.cos(a) * rx - 5} y={cy + Math.sin(a) * ry - 5} width="10" height="10" rx="2"
          fill={i % 3 === 0 ? '#1e3a5f' : '#1f2937'} stroke={i % 3 === 0 ? '#38bdf8' : '#64748b'} strokeWidth="1" />;
      })}
      <text x={cx} y={cy} textAnchor="middle" fontSize="8" fill="#64748b">STORAGE RING</text>
    </g>
  );
  switch (ch) {
    case 0: {
      const k = ease(p);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">INJECTION CHAIN — LINAC → BOOSTER → STORAGE RING</text>
          {ring()}
          <Box x={430} y={78} w={80} h={26} label="LINAC" sub="100 MeV" stroke="#a855f7" />
          <Box x={430} y={116} w={80} h={26} label="BOOSTER" sub="→ 3 GeV" stroke="#38bdf8" />
          <line x1="470" y1="104" x2="470" y2="116" stroke="#64748b" strokeWidth="1" markerEnd="url(#fp-arrow)" color="#64748b" />
          <path d={`M 430 142 Q 380 180 ${cx + rx} ${cy}`} fill="none" stroke="#22d3ee" strokeWidth="1" strokeDasharray="3 3" />
          {Array.from({ length: 8 }, (_, i) => {
            const a = -Math.PI / 2 + ((t * 1.4 + i / 8) % 1) * Math.PI * 2;
            return <Dot key={i} x={cx + Math.cos(a) * rx} y={cy + Math.sin(a) * ry} r={2.6} color="#22d3ee" opacity={k} halo={false} />;
          })}
          <Plate x={392} y={168} w={230} color="#22d3ee" lines={[
            'Electrons circulate for hours in an',
            'ultra-high vacuum (10⁻⁹ mbar).',
            'RF cavities replace the energy lost',
            'to radiation on every single turn.',
            'Top-up injection holds current steady.',
          ]} />
        </g>
      );
    }
    case 1: {
      const a = t * 1.6;
      const px = cx + Math.cos(a) * rx, py = cy + Math.sin(a) * ry;
      const tang = Math.atan2(Math.cos(a) * ry, -Math.sin(a) * rx);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">BENDING MAGNET RADIATION — A SEARCHLIGHT CONE</text>
          {ring()}
          <Dot x={px} y={py} r={3.5} color="#22d3ee" />
          <polygon points={`${px},${py} ${px + Math.cos(tang - 0.08) * 150},${py + Math.sin(tang - 0.08) * 150} ${px + Math.cos(tang + 0.08) * 150},${py + Math.sin(tang + 0.08) * 150}`}
            fill="#fde047" fillOpacity="0.16" />
          <Plate x={392} y={92} w={230} color="#fde047" lines={[
            'Opening angle ≈ 1/γ',
            'At 3 GeV, γ ≈ 5 870 → 0.17 mrad',
            'Emission is tangential, polarised',
            'and pulsed at the bunch rate.',
          ]} />
          <Plate x={392} y={190} w={230} color="#38bdf8" lines={[
            'Critical energy E_c ∝ E³ / ρ',
            'sets where the spectrum rolls off —',
            'infrared through hard X-ray in one',
            'continuous white beam.',
          ]} />
        </g>
      );
    }
    case 2: {
      const N = 10;
      const phase = t * 3;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">UNDULATOR — INTERFERENCE BUILDS BRIGHTNESS</text>
          {Array.from({ length: N }, (_, i) => (
            <g key={i}>
              <rect x={70 + i * 44} y={104} width="34" height="20" rx="3" fill={i % 2 ? '#1e293b' : '#3f2a12'} stroke={i % 2 ? '#64748b' : '#f59e0b'} strokeWidth="1" />
              <rect x={70 + i * 44} y={186} width="34" height="20" rx="3" fill={i % 2 ? '#3f2a12' : '#1e293b'} stroke={i % 2 ? '#f59e0b' : '#64748b'} strokeWidth="1" />
            </g>
          ))}
          <polyline points={Array.from({ length: 80 }, (_, i) => {
            const x = 70 + (i / 79) * 440;
            return `${x.toFixed(1)},${(155 + Math.sin((i / 79) * Math.PI * 10 - phase) * 11).toFixed(1)}`;
          }).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="1.6" />
          <Dot x={70 + (((t * 0.4) % 1)) * 440} y={155 + Math.sin((((t * 0.4) % 1)) * Math.PI * 10 - phase) * 11} r={3} color="#22d3ee" />
          <text x="70" y="96" fontSize="7" fill="#f59e0b">alternating permanent magnets · period λ_u ≈ 20 mm</text>
          <Plate x={70} y={220} w={480} color="#22d3ee" lines={[
            'Each wiggle radiates; when the wiggles are small (K ≲ 1) the emissions from all',
            'periods interfere constructively → narrow harmonics, ~10 000× a bending magnet.',
            'λ = (λ_u / 2γ²)(1 + K²/2 + γ²θ²)   — tune the gap, tune the photon energy.',
          ]} />
        </g>
      );
    }
    default: {
      const k = (t * 0.6) % 1;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">BEAMLINE — MONOCHROMATOR, SAMPLE, DETECTOR</text>
          <rect x="30" y="148" width="60" height="20" rx="3" fill="#0b1b34" stroke="#22d3ee" strokeWidth="1.5" />
          <text x="60" y="162" textAnchor="middle" fontSize="7" fill="#67e8f9">FRONT END</text>
          <line x1="90" y1="158" x2="180" y2="158" stroke="#fde047" strokeWidth="2" opacity="0.7" />
          <polygon points="180,148 210,138 214,146 186,158" fill="#94a3b8" stroke="#cbd5e1" />
          <polygon points="188,168 218,158 222,166 194,178" fill="#94a3b8" stroke="#cbd5e1" />
          <text x="196" y="196" fontSize="7" fill="#cbd5e1">Si(111) DCM</text>
          <line x1="222" y1="164" x2="330" y2="164" stroke="#a78bfa" strokeWidth="2" />
          <text x="256" y="156" fontSize="7" fill="#a78bfa">monochromatic</text>
          <rect x="330" y="140" width="34" height="48" rx="3" fill="#111c2e" stroke="#f59e0b" strokeWidth="1.5" />
          <text x="347" y="200" textAnchor="middle" fontSize="7" fill="#fbbf24">sample</text>
          {Array.from({ length: 6 }, (_, i) => {
            const ang = (i - 2.5) * 0.16;
            const L = 120 * k;
            return <line key={i} x1="364" y1="164" x2={364 + Math.cos(ang) * L} y2={164 + Math.sin(ang) * L} stroke="#38bdf8" strokeWidth="1" opacity={0.8 - k * 0.4} />;
          })}
          <rect x="500" y="112" width="14" height="104" rx="3" fill="#0b1220" stroke="#22c55e" strokeWidth="1.5" />
          <text x="530" y="164" fontSize="7" fill="#86efac">2D detector</text>
          <Plate x={30} y={222} w={520} color="#38bdf8" lines={[
            'Techniques: phase-contrast imaging · µCT of heritage objects · XAFS speciation of nuclear',
            'material · coherent diffraction · X-ray diffraction imaging that separates explosives from',
            'inert powders with the same attenuation but a different crystal structure.',
          ]} />
        </g>
      );
    }
  }
}

export const SYNCHROTRON_FILM: Film = {
  id: 'film-synchrotron',
  title: 'Synchrotron light source — from booster to beamline',
  tagline: 'Injection chain, bending-magnet cone, undulator interference and what beamlines actually measure',
  duration: 30,
  accent: 'text-cyan-400',
  hex: '#22d3ee',
  chapters: [
    { t: 0,  title: 'Injection chain', caption: 'A LINAC feeds a booster ring that ramps electrons to a few GeV, then transfers them into the storage ring where they circulate for hours in ultra-high vacuum.', detail: 'RF cavities replace the energy radiated away on every turn; top-up injection keeps the stored current essentially constant.' },
    { t: 8,  title: 'Bending-magnet radiation', caption: 'Every time a dipole bends the relativistic beam, the electrons radiate tangentially in a narrow forward cone with an opening angle of roughly one over gamma.', detail: 'At 3 GeV that cone is about 0.17 mrad wide. The spectrum is continuous from infrared to hard X-rays, linearly polarised and pulsed.' },
    { t: 16, title: 'Undulators', caption: 'A periodic array of permanent magnets makes the beam wiggle gently. Radiation from every period interferes constructively, concentrating the output into narrow harmonics.', detail: 'Brightness gain over a bending magnet is around four orders of magnitude. Changing the magnet gap tunes the photon energy.' },
    { t: 23, title: 'The beamline', caption: 'A double-crystal monochromator selects one wavelength, the sample sits in the focus, and area detectors record transmission, diffraction or fluorescence.', detail: 'Security-relevant use: diffraction imaging separates crystalline explosives from inert powders that attenuate identically.' },
  ],
  facts: [
    { label: 'Ring energy', value: '1–8 GeV' },
    { label: 'Cone angle', value: '≈ 1/γ' },
    { label: 'Undulator gain', value: '≈ 10⁴ × dipole' },
    { label: 'Vacuum', value: '10⁻⁹ mbar' },
  ],
  scene: synchrotronScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 6 — VAN DE GRAAFF
// ═══════════════════════════════════════════════════════════════════════════════
function vdgScene({ ch, p, t }: SceneCtx) {
  const belt = (charged: number) => (
    <g>
      <ellipse cx="200" cy="98" rx="58" ry="42" fill="#111c2e" stroke="#eab308" strokeWidth="2" />
      <text x="200" y="82" textAnchor="middle" fontSize="8" fill="#fde047">TERMINAL</text>
      <text x="200" y="96" textAnchor="middle" fontSize="11" fill="#fde047" fontWeight="bold">+{(charged * 5).toFixed(1)} MV</text>
      <rect x="186" y="140" width="28" height="110" fill="#0b1220" stroke="#475569" strokeWidth="1" />
      <line x1="192" y1="140" x2="192" y2="250" stroke="#64748b" strokeWidth="2" />
      <line x1="208" y1="140" x2="208" y2="250" stroke="#64748b" strokeWidth="2" />
      <circle cx="200" cy="252" r="10" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.5" />
      <text x="200" y="272" textAnchor="middle" fontSize="7" fill="#94a3b8">drive pulley</text>
      <line x1="120" y1="255" x2="280" y2="255" stroke="#64748b" strokeWidth="2" />
      <text x="120" y="270" fontSize="7" fill="#64748b">ground</text>
    </g>
  );
  switch (ch) {
    case 0: {
      const k = ease(p * 1.3);
      const charges = Array.from({ length: 8 }, (_, i) => 250 - (((t * 0.5 + i / 8) % 1)) * 110);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">CORONA SPRAY — CHARGE RIDES THE BELT UPWARD</text>
          {belt(k)}
          {Array.from({ length: 5 }, (_, i) => <line key={i} x1="168" y1={236 + i * 3} x2="184" y2={238 + i * 3} stroke="#f87171" strokeWidth="1" />)}
          <text x="112" y="234" fontSize="7" fill="#f87171">corona points</text>
          {charges.map((y, i) => <text key={i} x="192" y={y} fontSize="8" fill="#fde047">+</text>)}
          <Plate x={330} y={92} w={280} color="#fde047" lines={[
            'A sharp electrode at 20–30 kV sprays ions',
            'onto an insulating belt (or a Pelletron',
            'chain of metal pellets). At the top, a',
            'collector transfers the charge to the',
            'terminal — charge accumulates on the',
            'outside of the conductor.',
          ]} />
        </g>
      );
    }
    case 1: {
      const k = ease(p);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">POTENTIAL BUILD-UP &amp; INSULATION LIMIT</text>
          {belt(k)}
          {k > 0.75 && Array.from({ length: 3 }, (_, i) => (
            <polyline key={i} points={`258,${92 + i * 12} 274,${86 + i * 12} 268,${98 + i * 12} 286,${90 + i * 12}`}
              fill="none" stroke="#f87171" strokeWidth="1.2" opacity={(k - 0.75) * 4} />
          ))}
          <Plate x={330} y={92} w={280} color="#38bdf8" lines={[
            'V = Q / C — the terminal rises until',
            'leakage equals the charging current.',
            'Air breaks down at ~3 MV/m, so tanks',
            'are pressurised with SF₆ at 5–10 bar,',
            'pushing the limit to ~25 MV.',
          ]} />
          <Plate x={330} y={196} w={280} color="#f87171" lines={[
            'Resistor chain grades the field along',
            'the column; a single flashover can',
            'destroy the gradient rings.',
          ]} />
        </g>
      );
    }
    default: {
      const k = (t * 0.55) % 1;
      const x = 90 + k * 420;
      const stripped = x > 300;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">TANDEM — ACCELERATE TWICE FROM ONE TERMINAL</text>
          <line x1="60" y1="160" x2="560" y2="160" stroke="#334155" strokeWidth="10" />
          <ellipse cx="300" cy="160" rx="40" ry="26" fill="#111c2e" stroke="#eab308" strokeWidth="2" />
          <text x="300" y="163" textAnchor="middle" fontSize="8" fill="#fde047">+V terminal</text>
          <text x="300" y="132" textAnchor="middle" fontSize="7" fill="#fbbf24">stripper foil / gas</text>
          <Box x={40} y={144} w={44} h={32} label="A⁻" sub="source" stroke="#38bdf8" />
          <Box x={556} y={144} w={44} h={32} label="target" stroke="#22c55e" />
          <Dot x={x} y={160} r={3.5} color={stripped ? '#f472b6' : '#38bdf8'} />
          <text x={x} y={144} textAnchor="middle" fontSize="7" fill={stripped ? '#f9a8d4' : '#7dd3fc'}>{stripped ? 'A^q+' : 'A⁻'}</text>
          <text x="160" y="196" fontSize="7" fill="#38bdf8">1st gain: qV (attracted)</text>
          <text x="380" y="196" fontSize="7" fill="#f472b6">2nd gain: qV × charge state (repelled)</text>
          <Plate x={70} y={216} w={480} color="#fde047" lines={[
            'E_final = (1 + q) · V — a 10 MV terminal can deliver 50+ MeV heavy ions.',
            'Uses: accelerator mass spectrometry (¹⁴C dating), ion implantation, nuclear',
            'cross-section metrology, and nuclear resonance fluorescence for fissile-material assay.',
          ]} />
        </g>
      );
    }
  }
}

export const VDG_FILM: Film = {
  id: 'film-vdg',
  title: 'Van de Graaff — electrostatics done at megavolt scale',
  tagline: 'Corona spray, belt transport, insulation limits and the tandem double-acceleration trick',
  duration: 24,
  accent: 'text-yellow-400',
  hex: '#facc15',
  chapters: [
    { t: 0,  title: 'Charging the belt', caption: 'A sharp corona electrode sprays ions onto an insulating belt. The belt carries the charge mechanically to the terminal, where a collector comb transfers it to the outer surface of the sphere.', detail: 'Pelletron machines replace the rubber belt with a chain of metal pellets separated by insulators — quieter, cleaner, longer lived.' },
    { t: 8,  title: 'Terminal voltage', caption: 'The terminal potential rises until leakage current equals the charging current. Air alone breaks down near 3 MV/m, so the whole column sits in a tank of pressurised sulphur hexafluoride.', detail: 'Modern insulated tanks reach roughly 25 MV. A resistor chain grades the field evenly along the accelerating column.' },
    { t: 16, title: 'The tandem trick', caption: 'Negative ions are attracted to the positive terminal, stripped of electrons by a thin foil or gas, then repelled away as positive ions — gaining energy twice from the same voltage.', detail: 'Final energy is (1 + charge state) × terminal voltage, which is why tandems dominate accelerator mass spectrometry and ion-beam analysis.' },
  ],
  facts: [
    { label: 'Terminal voltage', value: '0.5–25 MV' },
    { label: 'Insulating gas', value: 'SF₆ 5–10 bar' },
    { label: 'Energy (tandem)', value: '(1+q) × V' },
    { label: 'Signature use', value: 'AMS / ¹⁴C dating' },
  ],
  scene: vdgScene,
};

export const ACCELERATOR_FILMS: Film[] = [
  XRAY_TUBE_FILM, LINAC_FILM, BETATRON_FILM, CYCLOTRON_FILM, SYNCHROTRON_FILM, VDG_FILM,
];

// Re-exported so sibling film modules can share the spectrum helper
export { spectrumPath, fade };
