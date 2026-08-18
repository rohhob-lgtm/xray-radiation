import type { Film, SceneCtx } from './film-player';
import { Box, Dot, Wave, Plate, ease } from './film-player';

// ═══════════════════════════════════════════════════════════════════════════════
// Films: (1) imaging technologies — transmission, backscatter, forward scatter
//        (2) detectors — how radiation is actually received, photon to pixel
// ═══════════════════════════════════════════════════════════════════════════════

const saw = (t: number, hz = 1) => (t * hz) % 1;
const osc = (t: number, hz = 1) => Math.sin(t * Math.PI * 2 * hz);

// ─── 1. IMAGING TECHNOLOGIES ──────────────────────────────────────────────────
function techScene({ ch, p, t }: SceneCtx) {
  switch (ch) {
    case 0: { // the fork in the road
      const E = 30 + ease(p) * 260;
      const back = Math.max(0.04, 0.55 - E / 420);
      const lobe = (a: number) => 26 + 40 * Math.pow((1 + Math.cos(a)) / 2, 1 + (E / 90));
      const pts = Array.from({ length: 64 }, (_, i) => {
        const a = (i / 63) * Math.PI * 2;
        const r = lobe(a);
        return `${(330 + Math.cos(a) * r).toFixed(1)},${(160 + Math.sin(a) * r * 0.9).toFixed(1)}`;
      }).join(' ');
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">EVERY TECHNOLOGY STARTS HERE — WHERE DO THE PHOTONS GO?</text>
          <line x1="120" y1="160" x2="324" y2="160" stroke="#fde047" strokeWidth="2" />
          <circle cx="330" cy="160" r="5" fill="#94a3b8" />
          <polygon points={pts} fill="#a78bfa" fillOpacity="0.2" stroke="#a78bfa" strokeWidth="1.3" />
          <text x="120" y="150" fontSize="8" fill="#fde047">primary beam</text>
          <Plate x={430} y={92} w={190} color="#a78bfa" lines={[
            `E = ${E.toFixed(0)} keV`,
            `back-scatter share ≈ ${(back * 100).toFixed(0)} %`,
            E < 120 ? 'backscatter imaging viable' : 'forward-peaked — transmission only',
          ]} />
          <Plate x={40} y={216} w={560} color="#38bdf8" lines={[
            'Transmitted photons  → attenuation image (needs two-sided access)',
            'Back-scattered       → single-sided imaging, organic contrast, shallow depth',
            'Small-angle forward  → structure and phase information, dark-field, XRD',
            'Absorbed             → dose. Not an image. Everything else is a design choice.',
          ]} />
        </g>
      );
    }
    case 1: { // transmission
      const f = saw(t, 0.5);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">TRANSMISSION — THE LINE INTEGRAL</text>
          <Box x={60} y={140} w={44} h={36} label="source" stroke="#22c55e" />
          <rect x="220" y="96" width="70" height="120" rx="6" fill="#7c2d12" stroke="#f97316" strokeWidth="1.4" />
          <rect x="240" y="130" width="30" height="52" rx="3" fill="#0b1220" stroke="#94a3b8" strokeWidth="1.2" />
          <text x="255" y="234" textAnchor="middle" fontSize="7" fill="#fdba74">object with dense insert</text>
          {Array.from({ length: 9 }, (_, i) => {
            const y = 104 + i * 14;
            const blocked = y > 128 && y < 184;
            const x = 108 + ((f + i / 9) % 1) * 340;
            return <Dot key={i} x={x} y={y} r={2.4} color="#fde047" opacity={blocked && x > 250 ? 0.18 : 1} halo={false} />;
          })}
          <rect x="454" y="92" width="12" height="130" rx="3" fill="#0b1220" stroke="#22c55e" strokeWidth="1.5" />
          {Array.from({ length: 9 }, (_, i) => {
            const y = 104 + i * 14;
            const blocked = y > 128 && y < 184;
            return <rect key={i} x="470" y={y - 5} width={blocked ? 14 : 44} height="10" rx="2" fill="#fde047" opacity={blocked ? 0.3 : 0.8} />;
          })}
          <text x="470" y="240" fontSize="7" fill="#94a3b8">signal per ray</text>
          <Plate x={60} y={216} w={330} color="#fde047" lines={[
            'I = I₀ · exp( − ∫ µ(x) dx )',
            'One number per ray — everything along the path is superimposed.',
            'Highest photon efficiency of any modality, but needs both sides.',
          ]} />
        </g>
      );
    }
    case 2: { // backscatter
      const f = saw(t, 0.35);
      const y = 100 + f * 120;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">BACKSCATTER — IMAGING FROM ONE SIDE ONLY</text>
          <rect x="70" y="88" width="26" height="150" rx="5" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.4" />
          <text x="60" y="82" fontSize="7" fill="#d8b4fe">chopper wheel — pencil beam</text>
          <rect x="104" y="88" width="16" height="150" rx="4" fill="#0b1220" stroke="#22d3ee" strokeWidth="1.4" />
          <text x="100" y="252" fontSize="7" fill="#67e8f9">large-area detector</text>
          <line x1="120" y1={y} x2="400" y2={y} stroke="#fde047" strokeWidth="2" />
          <rect x="400" y="96" width="80" height="140" rx="6" fill="#7c2d12" stroke="#f97316" strokeWidth="1.4" />
          <rect x="418" y="132" width="44" height="40" rx="4" fill="#292524" stroke="#94a3b8" strokeWidth="1.2" />
          <text x="440" y="252" textAnchor="middle" fontSize="7" fill="#fdba74">organic body / steel insert</text>
          {Array.from({ length: 7 }, (_, i) => {
            const bright = !(y > 132 && y < 172);
            return <line key={i} x1="402" y1={y} x2="122" y2={y + (i - 3) * 40} stroke="#22d3ee"
              strokeWidth="1" opacity={bright ? 0.55 : 0.12} />;
          })}
          <rect x="520" y="90" width="60" height="150" rx="4" fill="#0b1220" stroke="#334155" />
          <rect x="524" y={y - 4} width="52" height="8" fill={(y > 132 && y < 172) ? '#1f2937' : '#22d3ee'} opacity="0.85" />
          <text x="520" y="256" fontSize="7" fill="#67e8f9">image line by line</text>
          <Plate x={140} y={252} w={360} color="#22d3ee" lines={[
            'Bright = low-Z (scatters back). Dark = steel. Exactly inverted from transmission.',
          ]} />
        </g>
      );
    }
    case 3: { // forward / coherent
      const cryst = p > 0.5;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">FORWARD &amp; COHERENT SCATTER — IDENTIFYING THE SUBSTANCE</text>
          <Box x={50} y={144} w={46} h={32} label="source" stroke="#22c55e" />
          <line x1="96" y1="160" x2="250" y2="160" stroke="#fde047" strokeWidth="1.8" />
          <rect x="250" y="128" width="44" height="64" rx="5" fill={cryst ? '#312e81' : '#3f2a12'} stroke={cryst ? '#818cf8' : '#f59e0b'} strokeWidth="1.4" />
          <text x="272" y="210" textAnchor="middle" fontSize="7" fill={cryst ? '#a5b4fc' : '#fbbf24'}>{cryst ? 'crystalline (RDX)' : 'amorphous powder'}</text>
          <circle cx="470" cy="160" r="10" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.2" />
          <text x="470" y="188" textAnchor="middle" fontSize="7" fill="#cbd5e1">beam stop</text>
          {cryst
            ? [-2.6, -1.3, 1.3, 2.6].map((k, i) => (
              <line key={i} x1="294" y1="160" x2="520" y2={160 + k * 26} stroke="#a855f7" strokeWidth="1.3" />
            ))
            : Array.from({ length: 11 }, (_, i) => (
              <line key={i} x1="294" y1="160" x2="520" y2={90 + i * 14} stroke="#64748b" strokeWidth="0.7" opacity="0.4" />
            ))}
          <rect x="520" y="86" width="12" height="150" rx="3" fill="#0b1220" stroke="#a855f7" strokeWidth="1.4" />
          {cryst && [0, 1, 2].map(i => <rect key={i} x="540" y={116 + i * 30} width="16" height="6" fill="#a855f7" />)}
          <Plate x={50} y={228} w={440} color="#a855f7" lines={[
            'nλ = 2 d sin θ — sharp Bragg peaks are a molecular fingerprint.',
            'Two powders that attenuate identically diffract completely differently.',
            'Slow, so it runs as a confirmation stage behind a fast transmission scanner.',
          ]} />
        </g>
      );
    }
    default: { // technology map
      const sel = Math.floor(saw(t, 0.25) * 5);
      const rows = [
        ['Two-sided access, "what is it?"', 'Dual-energy transmission', '#f97316'],
        ['One-sided access, organic threat', 'Backscatter (Compton)', '#22d3ee'],
        ['Overlapping clutter, need depth', 'CT / tomosynthesis', '#4ade80'],
        ['Which exact substance?', 'XRD / K-edge / spectral', '#a855f7'],
        ['Elemental composition, deep load', 'Neutron interrogation', '#f87171'],
      ];
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">CHOOSING THE TECHNOLOGY — CONSTRAINTS FIRST, PHYSICS SECOND</text>
          {rows.map((r, i) => (
            <g key={i} opacity={i === sel ? 1 : 0.4}>
              <rect x="60" y={84 + i * 34} width="250" height="26" rx="5" fill="#0b1220" stroke={i === sel ? (r[2] as string) : '#334155'} strokeWidth="1.2" />
              <text x="72" y={101 + i * 34} fontSize="8" fill="#cbd5e1">{r[0]}</text>
              <line x1="310" y1={97 + i * 34} x2="336" y2={97 + i * 34} stroke={i === sel ? (r[2] as string) : '#334155'} strokeWidth="1.3" />
              <rect x="336" y={84 + i * 34} width="240" height="26" rx="5" fill="#0b1220" stroke={i === sel ? (r[2] as string) : '#334155'} strokeWidth="1.2" />
              <text x="348" y={101 + i * 34} fontSize="8" fill={i === sel ? (r[2] as string) : '#64748b'}>{r[1]}</text>
            </g>
          ))}
          <Plate x={60} y={258} w={516} color="#38bdf8" lines={[
            'Access · thickness · question · throughput. Those four decide the modality before physics does.',
          ]} />
        </g>
      );
    }
  }
}

export const TECHNOLOGY_FILM: Film = {
  id: 'film-technologies',
  title: 'Imaging technologies — transmission, backscatter, forward scatter',
  tagline: 'One beam, four possible fates, and the technology family each one creates',
  duration: 32,
  accent: 'text-amber-400',
  hex: '#fbbf24',
  chapters: [
    { t: 0,  title: 'Where photons go', caption: 'Every photon that leaves the source ends up transmitted, back-scattered, forward-scattered or absorbed. Each of those fates is the physical basis of a whole technology family.', detail: 'The Klein–Nishina angular distribution decides how much of each you get — and it depends strongly on energy.' },
    { t: 7,  title: 'Transmission', caption: 'Count what passes straight through. Every pixel is one line integral of attenuation, which is why a thin dense object can look exactly like a thick light one.', detail: 'Highest photon efficiency of any modality, but it requires access to both sides of the object.' },
    { t: 14, title: 'Backscatter', caption: 'A pencil beam sweeps the scene and large detectors on the same side collect Compton-scattered photons. Organic material is bright, steel is dark — the inverse of a transmission image.', detail: 'Single-sided access is the whole point: vehicles, walls, aircraft skins and containers in place.' },
    { t: 21, title: 'Forward and coherent scatter', caption: 'Photons deflected by only a few degrees carry structural information. Crystalline materials diffract at angles set by their lattice, producing a molecular fingerprint.', detail: 'This is how two powders with identical attenuation are told apart — slow, so it runs as a confirmation stage.' },
    { t: 27, title: 'Choosing a technology', caption: 'Access, thickness, the question you actually need answered, and throughput. Those four constraints pick the modality long before any physics argument begins.', detail: 'Most real systems combine two — transmission for speed, a second modality for the hard cases.' },
  ],
  facts: [
    { label: 'Backscatter useful below', value: '≈ 120 keV' },
    { label: 'Cargo transmission', value: '6–9 MeV' },
    { label: 'XRD angles', value: 'a few degrees' },
    { label: 'Modality drivers', value: 'access · thickness' },
  ],
  scene: techScene,
};

// ─── 2. DETECTORS ─────────────────────────────────────────────────────────────
function detectorScene({ ch, p, t }: SceneCtx) {
  switch (ch) {
    case 0: { // interaction
      const f = saw(t, 0.5);
      const mode = Math.floor(p * 3) % 3;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">STAGE 1 — THE PHOTON HAS TO INTERACT AT ALL</text>
          <rect x="230" y="90" width="240" height="140" rx="8" fill="#111c2e" stroke="#475569" strokeWidth="1.5" />
          <text x="230" y="84" fontSize="7" fill="#94a3b8">sensitive volume</text>
          <Dot x={80 + Math.min(f, 0.5) * 260} y={160} r={3} color="#fde047" />
          {f > 0.5 && mode === 0 && (<>
            <circle cx="350" cy="160" r={(f - 0.5) * 90} fill="#fde047" opacity={0.45 - (f - 0.5) * 0.6} />
            <text x="350" y="252" textAnchor="middle" fontSize="8" fill="#fde047">PHOTOELECTRIC — full energy deposited</text>
          </>)}
          {f > 0.5 && mode === 1 && (<>
            <Wave x={350} y={160} angle={-0.6} len={140 * (f - 0.5) * 2} color="#38bdf8" phase={t * 8} />
            <Dot x={350} y={160} r={4} color="#60a5fa" />
            <text x="350" y="252" textAnchor="middle" fontSize="8" fill="#38bdf8">COMPTON — partial deposit, photon escapes</text>
          </>)}
          {f > 0.5 && mode === 2 && (<>
            <Dot x={350 + (f - 0.5) * 160} y={160 - (f - 0.5) * 90} r={3.5} color="#4ade80" />
            <Dot x={350 + (f - 0.5) * 160} y={160 + (f - 0.5) * 90} r={3.5} color="#f472b6" />
            <text x="350" y="252" textAnchor="middle" fontSize="8" fill="#f472b6">PAIR PRODUCTION — above 1.022 MeV</text>
          </>)}
          <Plate x={40} y={96} w={170} color="#38bdf8" lines={[
            'Efficiency = P(interact)',
            'Driven by Z, density and',
            'thickness of the sensor.',
            'A photon that passes',
            'through is simply invisible.',
          ]} />
        </g>
      );
    }
    case 1: { // conversion — light vs charge
      const f = saw(t, 0.6);
      const light = p < 0.5;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">
            STAGE 2 — CONVERSION: {light ? 'INDIRECT (LIGHT)' : 'DIRECT (CHARGE)'}
          </text>
          {light ? (<>
            <rect x="200" y="96" width="90" height="120" rx="5" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.6" />
            <text x="245" y="90" textAnchor="middle" fontSize="7" fill="#fbbf24">CsI / NaI / CdWO₄</text>
            <Dot x={100 + Math.min(f, 0.45) * 220} y={156} r={3} color="#fde047" />
            {f > 0.45 && Array.from({ length: 16 }, (_, i) => {
              const a = (i / 16) * Math.PI * 2;
              const r = (f - 0.45) * 130;
              return <circle key={i} cx={245 + Math.cos(a) * r * 0.6} cy={156 + Math.sin(a) * r * 0.5} r="2" fill="#67e8f9" opacity="0.85" />;
            })}
            <rect x="300" y="120" width="20" height="72" rx="3" fill="#0b1220" stroke="#22d3ee" strokeWidth="1.4" />
            <text x="330" y="160" fontSize="7" fill="#67e8f9">photodetector</text>
            <Plate x={380} y={96} w={230} color="#fbbf24" lines={[
              '≈ 38 photons of light per keV in NaI',
              'Light spreads sideways → resolution loss',
              'Needs a second device to read the light:',
              'PMT, photodiode or SiPM.',
            ]} />
          </>) : (<>
            <rect x="200" y="96" width="180" height="120" rx="5" fill="#2a0b2e" stroke="#f472b6" strokeWidth="1.6" />
            <line x1="200" y1="96" x2="380" y2="96" stroke="#f87171" strokeWidth="3" />
            <line x1="200" y1="216" x2="380" y2="216" stroke="#4ade80" strokeWidth="3" />
            <text x="392" y="100" fontSize="7" fill="#fca5a5">+ bias</text>
            <Dot x={100 + Math.min(f, 0.45) * 190} y={156} r={3} color="#fde047" />
            {f > 0.45 && Array.from({ length: 8 }, (_, i) => {
              const g = (f - 0.45) * 1.9;
              return (
                <g key={i}>
                  <circle cx={276 + i * 9} cy={156 - g * 58} r="2" fill="#60a5fa" />
                  <circle cx={276 + i * 9} cy={156 + g * 58} r="2" fill="#f87171" />
                </g>
              );
            })}
            <Plate x={400} y={96} w={220} color="#f472b6" lines={[
              'CdTe ≈ 4.4 eV per electron-hole pair',
              'Charge follows field lines — almost',
              'no lateral spread, so both spatial and',
              'energy resolution are far better.',
            ]} />
          </>)}
        </g>
      );
    }
    case 2: { // amplification
      const stage = Math.floor(saw(t, 0.5) * 8);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">STAGE 3 — AMPLIFICATION: THE DYNODE CHAIN</text>
          <rect x="40" y="130" width="30" height="60" rx="4" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.3" />
          <text x="36" y="124" fontSize="7" fill="#fbbf24">scintillator</text>
          <line x1="76" y1="126" x2="76" y2="194" stroke="#22d3ee" strokeWidth="3" />
          <text x="60" y="212" fontSize="7" fill="#67e8f9">photocathode</text>
          {Array.from({ length: 7 }, (_, i) => (
            <line key={i} x1={110 + i * 56} y1={i % 2 ? 122 : 198} x2={146 + i * 56} y2={i % 2 ? 158 : 162}
              stroke={stage > i ? '#67e8f9' : '#334155'} strokeWidth="4" strokeLinecap="round" />
          ))}
          {Array.from({ length: Math.min(60, Math.pow(2, stage)) }, (_, i) => (
            <circle key={i} cx={86 + stage * 56 + (i % 8) * 4} cy={138 + (i % 11) * 4} r="1.8" fill="#60a5fa" opacity="0.85" />
          ))}
          <rect x="546" y="136" width="30" height="48" rx="4" fill="#0b1220" stroke="#a78bfa" strokeWidth="1.4" />
          <text x="540" y="200" fontSize="7" fill="#c4b5fd">anode</text>
          <Plate x={60} y={228} w={520} color="#22d3ee" lines={[
            `Stage ${Math.min(7, stage)} of 7 — running gain ≈ 10^${Math.min(7, stage)}. Each dynode is ~100 V above the last, and`,
            'every impact releases 3–5 secondary electrons. The first stage is essentially noise-free, which is',
            'why a PMT can register a single photon. Gain depends steeply on HV — supply stability is resolution.',
          ]} />
        </g>
      );
    }
    case 3: { // digitisation
      const f = saw(t, 0.7);
      const fired = f > 0.3;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">STAGE 4 — PREAMP, SHAPER, ADC</text>
          <Box x={40} y={140} w={60} h={44} label="sensor" stroke="#f472b6" />
          <polygon points="126,140 126,184 176,162" fill="#0b1220" stroke="#a78bfa" strokeWidth="1.4" />
          <text x="124" y="202" fontSize="7" fill="#c4b5fd">charge preamp</text>
          <polygon points="216,140 216,184 266,162" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.4" />
          <text x="216" y="202" fontSize="7" fill="#7dd3fc">shaper</text>
          <Box x={306} y={140} w={56} h={44} label="ADC" stroke="#4ade80" />
          <rect x="400" y="140" width="90" height="44" rx="5" fill="#0b1220" stroke="#64748b" strokeWidth="1.2" />
          <text x="412" y="168" fontSize="13" fill="#e2e8f0" fontFamily="monospace">{fired ? String(1200 + Math.round(f * 600)) : '0000'}</text>
          <polyline points={Array.from({ length: 40 }, (_, i) => `${126 + i * 1.3},${110 - (fired && i > 8 ? 18 : 0)}`).join(' ')} fill="none" stroke="#a78bfa" strokeWidth="1.3" />
          <polyline points={Array.from({ length: 40 }, (_, i) => {
            const pk = fired ? Math.exp(-Math.pow((i - 16) / 5, 2)) : 0;
            return `${216 + i * 1.3},${110 - pk * 22}`;
          }).join(' ')} fill="none" stroke="#38bdf8" strokeWidth="1.3" />
          <Plate x={40} y={224} w={550} color="#4ade80" lines={[
            'Shaping time is the central trade: long shaping gives the best energy resolution but pile-up at high',
            'count rate; short shaping handles flux but adds noise. Equivalent noise charge (electrons RMS) is the',
            'figure of merit. In integrating detectors the same chain reads accumulated charge once per line instead.',
          ]} />
        </g>
      );
    }
    default: { // the family map
      const sel = Math.floor(saw(t, 0.22) * 6);
      const rows = [
        ['Ion chamber', 'no gain, never saturates', 'dosimetry, beam monitors', '#38bdf8'],
        ['Proportional / GM', 'gas gain 10³–10⁵ / discharge', 'neutron tubes, survey meters', '#a78bfa'],
        ['Scintillator + PMT', 'light → 10⁶ electron gain', 'spectroscopy, portal panels', '#22d3ee'],
        ['Scintillator + diode (DAB)', 'light → integrated charge', 'security & CT line-scan arrays', '#22c55e'],
        ['CdTe / CZT direct', 'charge, 4.4 eV per pair', 'photon counting, identifiers', '#f472b6'],
        ['a-Si / a-Se flat panel', 'pixel array readout', 'digital radiography, CT', '#4ade80'],
      ];
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">THE DETECTOR FAMILY — SAME CHAIN, DIFFERENT PHYSICS</text>
          {rows.map((r, i) => (
            <g key={i} opacity={i === sel ? 1 : 0.4}>
              <rect x="40" y={78 + i * 30} width="560" height="24" rx="5" fill="#0b1220" stroke={i === sel ? (r[3] as string) : '#334155'} strokeWidth="1.1" />
              <text x="54" y={94 + i * 30} fontSize="8" fill={i === sel ? (r[3] as string) : '#cbd5e1'}>{r[0]}</text>
              <text x="230" y={94 + i * 30} fontSize="7.5" fill="#94a3b8">{r[1]}</text>
              <text x="410" y={94 + i * 30} fontSize="7.5" fill="#94a3b8">{r[2]}</text>
            </g>
          ))}
          <Plate x={40} y={262} w={560} color="#38bdf8" lines={[
            'Efficiency says how many photons you catch · MTF says how well you keep detail · DQE says how much',
            'of the input signal-to-noise actually survives. Only DQE lets you compare two detectors honestly.',
          ]} />
        </g>
      );
    }
  }
}

export const DETECTOR_FILM: Film = {
  id: 'film-detectors',
  title: 'From photon to pixel — how a detector receives radiation',
  tagline: 'Interaction, conversion, amplification, digitisation — and the detector family that results',
  duration: 32,
  accent: 'text-emerald-400',
  hex: '#34d399',
  chapters: [
    { t: 0,  title: 'Interaction', caption: 'Nothing happens until the photon actually deposits energy inside the sensitive volume. Photoelectric absorption gives the full energy, Compton gives part of it, pair production only starts above 1.022 MeV.', detail: 'Detection efficiency is simply the probability of interacting at all — driven by atomic number, density and thickness.' },
    { t: 7,  title: 'Conversion', caption: 'Indirect detectors turn the energy into visible light in a scintillator; direct detectors create electron-hole pairs straight away in a semiconductor.', detail: 'CdTe needs about 4.4 eV per pair; a scintillator plus photodetector effectively costs around 100 eV per detected carrier. That gap is why direct conversion resolves energy far better.' },
    { t: 14, title: 'Amplification', caption: 'A photomultiplier releases one photoelectron and multiplies it through a chain of dynodes, gaining a factor of three to five at each stage — a million-fold overall, with almost no added noise.', detail: 'SiPMs achieve comparable gain with Geiger-mode silicon cells at tens of volts instead of a kilovolt, and work in magnetic fields.' },
    { t: 21, title: 'Digitisation', caption: 'A charge-sensitive preamplifier integrates the collected charge, a shaper turns it into a clean pulse, and an ADC converts it into a number. This chain sets the true noise floor of the whole detector.', detail: 'Shaping time trades energy resolution against count-rate capability — the central design decision in any spectroscopy system.' },
    { t: 27, title: 'The detector family', caption: 'Gas, scintillator and semiconductor detectors all run the same five stages; they differ only in how the first two are done. That is what determines where each one belongs.', detail: 'Compare detectors by DQE, not by efficiency or resolution alone — a sharp detector that discards photons is simply a noisy one.' },
  ],
  facts: [
    { label: 'PMT gain', value: '10⁶–10⁷' },
    { label: 'CdTe pair energy', value: '4.4 eV' },
    { label: 'HPGe resolution', value: '≈ 1.8 keV @1332' },
    { label: 'GM dead time', value: '50–300 µs' },
  ],
  scene: detectorScene,
};

export const TECHNOLOGY_FILMS: Film[] = [TECHNOLOGY_FILM, DETECTOR_FILM];
export { saw, osc };
