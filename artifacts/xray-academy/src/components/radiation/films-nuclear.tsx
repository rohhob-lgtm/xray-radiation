import type { Film, SceneCtx } from './film-player';
import { Box, Dot, Wave, Plate, ease, clamp } from './film-player';

// ═══════════════════════════════════════════════════════════════════════════════
// Film scenes — radioisotope sources, neutron sources, gamma irradiators,
// industrial radiography and security screening.
// ═══════════════════════════════════════════════════════════════════════════════

const saw = (t: number, hz = 1) => (t * hz) % 1;
const osc = (t: number, hz = 1) => Math.sin(t * Math.PI * 2 * hz);

// ═══════════════════════════════════════════════════════════════════════════════
// 1 — RADIOISOTOPE SOURCES
// ═══════════════════════════════════════════════════════════════════════════════
function isotopeScene({ ch, p, t }: SceneCtx) {
  switch (ch) {
    case 0: { // decay physics
      const decayed = ease(p);
      const nuclei = Array.from({ length: 40 }, (_, i) => ({
        x: 60 + (i % 8) * 26, y: 96 + Math.floor(i / 8) * 24,
        gone: (i * 2654435761 % 100) / 100 < decayed,
      }));
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">RADIOACTIVE DECAY — A STATISTICAL PROCESS</text>
          {nuclei.map((n, i) => (
            <circle key={i} cx={n.x} cy={n.y} r="6" fill={n.gone ? '#1f2937' : '#f97316'} stroke={n.gone ? '#334155' : '#fdba74'} strokeWidth="1" />
          ))}
          <text x="60" y="86" fontSize="7" fill="#94a3b8">parent nuclei ({Math.round((1 - decayed) * 100)} % remaining)</text>
          <Plate x={330} y={92} w={290} color="#f97316" lines={[
            'A(t) = A₀ · e^(−λt)      λ = ln2 / t½',
            'Decay is spontaneous: no temperature,',
            'pressure or chemistry can change it.',
            'Activity in becquerel = decays per second.',
            '1 Ci = 3.7 × 10¹⁰ Bq',
          ]} />
          <rect x="330" y="196" width="290" height="70" rx="4" fill="#0b1220" stroke="#334155" />
          <polyline points={Array.from({ length: 50 }, (_, i) => `${336 + i * 5.6},${258 - 54 * Math.pow(0.5, (i / 50) * 4)}`).join(' ')}
            fill="none" stroke="#f97316" strokeWidth="1.4" />
          <text x="336" y="206" fontSize="7" fill="#94a3b8">activity vs half-lives</text>
        </g>
      );
    }
    case 1: { // sealed source construction
      const k = ease(p);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">SEALED SOURCE — DOUBLE ENCAPSULATION</text>
          <g transform="translate(180 150)">
            <rect x="-90" y="-46" width="180" height="92" rx="12" fill="#0f172a" stroke="#94a3b8" strokeWidth="2" />
            <rect x={-70 + k * 4} y="-32" width="140" height="64" rx="10" fill="#111c2e" stroke="#cbd5e1" strokeWidth="1.5" />
            <rect x="-44" y="-18" width="88" height="36" rx="6" fill="#7c2d12" stroke="#f97316" strokeWidth="1.5" />
            <text x="0" y="4" textAnchor="middle" fontSize="9" fill="#fdba74">Ir-192 pellets</text>
            <text x="0" y="-52" textAnchor="middle" fontSize="7" fill="#94a3b8">outer capsule (316L stainless)</text>
            <text x="0" y="62" textAnchor="middle" fontSize="7" fill="#94a3b8">inner capsule — laser seal-welded</text>
          </g>
          <Plate x={370} y={92} w={250} color="#38bdf8" lines={[
            'ISO 2919 classification code',
            'e.g. C 66646 — temperature, pressure,',
            'impact, vibration, puncture ratings.',
            'Leak test every 6–12 months by wipe;',
            'limit 200 Bq removable contamination.',
          ]} />
          <Plate x={370} y={210} w={250} color="#f87171" lines={[
            'Never open, cut or grind a capsule.',
            'A breached source is a contamination',
            'event, not a maintenance task.',
          ]} />
        </g>
      );
    }
    case 2: { // projector / crank out
      const out = ease(clamp(p * 1.5));
      const sx = 180 + out * 300;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">GAMMA PROJECTOR — CRANK-OUT RADIOGRAPHY</text>
          <rect x="90" y="120" width="120" height="70" rx="10" fill="#1f2937" stroke="#94a3b8" strokeWidth="2" />
          <text x="150" y="112" textAnchor="middle" fontSize="7" fill="#cbd5e1">depleted-U / W shield</text>
          <path d="M 150 155 q 0 -26 40 -26 h 30" fill="none" stroke="#475569" strokeWidth="6" />
          <line x1="220" y1="129" x2="520" y2="129" stroke="#475569" strokeWidth="6" />
          <Dot x={sx} y={out > 0.12 ? 129 : 155} r={5} color="#f97316" />
          {out > 0.2 && Array.from({ length: 8 }, (_, i) => {
            const a = (i / 8) * Math.PI * 2 + t;
            return <Wave key={i} x={sx} y={129} angle={a} len={40 * out} color="#fbbf24" amp={2.5} phase={t * 8} width={1} />;
          })}
          <rect x="60" y="200" width="70" height="30" rx="4" fill="#0b1220" stroke="#64748b" />
          <text x="95" y="219" textAnchor="middle" fontSize="7" fill="#cbd5e1">crank drive</text>
          <text x="95" y="246" textAnchor="middle" fontSize="7" fill="#94a3b8">min. 7 m guide tube</text>
          <rect x="470" y="96" width="10" height="66" rx="2" fill="#111c2e" stroke="#22c55e" strokeWidth="1.5" />
          <text x="486" y="130" fontSize="7" fill="#86efac">weld + film</text>
          <Plate x={330} y={210} w={290} color="#f87171" lines={[
            'The three worst-case failures: source not fully retracted,',
            'disconnected pigtail, and survey meter not used on return.',
            'Always survey the projector AND the guide tube after every exposure.',
          ]} />
        </g>
      );
    }
    default: { // TDS protection
      const d = 1 + ease(p) * 5;
      const rate = 350 / (d * d);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">TIME · DISTANCE · SHIELDING</text>
          <circle cx="120" cy="160" r="10" fill="#f97316" stroke="#fdba74" strokeWidth="1.5" />
          {[1, 2, 3, 4, 5, 6].map(i => (
            <circle key={i} cx="120" cy="160" r={i * 40} fill="none" stroke="#f97316" strokeWidth="1" opacity={0.35 / i} />
          ))}
          <g transform={`translate(${120 + d * 46} 160)`}>
            <circle cx="0" cy="-18" r="7" fill="#94a3b8" />
            <rect x="-6" y="-10" width="12" height="24" rx="4" fill="#64748b" />
          </g>
          <line x1="120" y1="212" x2={120 + d * 46} y2="212" stroke="#64748b" strokeWidth="1" strokeDasharray="3 2" />
          <text x={120 + d * 23} y="226" textAnchor="middle" fontSize="8" fill="#cbd5e1">{d.toFixed(1)} m</text>
          <Plate x={380} y={86} w={240} color="#fde047" lines={[
            'INVERSE SQUARE LAW',
            'İ₂ = İ₁ · (d₁ / d₂)²',
            `at ${d.toFixed(1)} m → ${rate.toFixed(1)} µSv/h`,
            '(1 TBq Ir-192 reference)',
          ]} />
          <Plate x={380} y={182} w={240} color="#38bdf8" lines={[
            'Doubling distance quarters the rate —',
            'the cheapest protection there is.',
            'Then: minimise time, then add shielding.',
            'HVL Ir-192 ≈ 2.5 mm Pb.',
          ]} />
        </g>
      );
    }
  }
}

export const ISOTOPE_FILM: Film = {
  id: 'film-isotopes',
  title: 'Sealed radioisotope sources — decay, capsule, projector, protection',
  tagline: 'Why decay cannot be switched off, how a source is built, and how radiographers stay safe',
  duration: 28,
  accent: 'text-orange-400',
  hex: '#f97316',
  chapters: [
    { t: 0,  title: 'Decay statistics', caption: 'Each nucleus decays at random, but a large population follows a clean exponential law. Nothing an operator can do — heating, cooling, chemistry — changes the decay constant.', detail: 'A(t) = A₀·e^(−λt) with λ = ln2 / half-life. This is why an isotope source cannot be switched off, only shielded.' },
    { t: 8,  title: 'Sealed source construction', caption: 'The active material is sintered into pellets, sealed inside an inner capsule, and that capsule is welded inside a second one. The classification code records the mechanical and thermal tests it survived.', detail: 'ISO 2919 sets the ratings; a wipe test every 6–12 months confirms the encapsulation still holds.' },
    { t: 15, title: 'The projector', caption: 'For industrial radiography the source is cranked out of a depleted-uranium shield, through a guide tube, to the weld being inspected — then wound all the way back.', detail: 'Most serious radiography accidents come from a source that did not fully retract and a survey meter that was not used.' },
    { t: 22, title: 'Time, distance, shielding', caption: 'Dose rate falls with the square of distance. Doubling your distance quarters your exposure, which makes distance the cheapest and most reliable control on any site.', detail: 'Then minimise the time you spend in the field, and only then add lead. Ir-192 half-value layer is about 2.5 mm of lead.' },
  ],
  facts: [
    { label: 'Co-60 half-life', value: '5.27 y' },
    { label: 'Ir-192 half-life', value: '73.8 d' },
    { label: 'Ir-192 HVL', value: '2.5 mm Pb' },
    { label: 'Leak-test limit', value: '200 Bq' },
  ],
  scene: isotopeScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 2 — NEUTRON SOURCES
// ═══════════════════════════════════════════════════════════════════════════════
function neutronScene({ ch, p, t }: SceneCtx) {
  switch (ch) {
    case 0: { // D-T fusion
      const k = saw(t, 0.6);
      const approach = Math.min(k, 0.5) * 2;
      const fused = k > 0.5;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">D-T GENERATOR — FUSION ON A BENCHTOP</text>
          <Dot x={200 + approach * 100} y={150} r={7} color="#38bdf8" />
          <text x={200 + approach * 100} y={132} textAnchor="middle" fontSize="7" fill="#7dd3fc">D⁺</text>
          {!fused && <><Dot x={420 - approach * 100} y={150} r={8} color="#f472b6" />
            <text x={420 - approach * 100} y={132} textAnchor="middle" fontSize="7" fill="#f9a8d4">T</text></>}
          {fused && (<>
            <Dot x={330 - (k - 0.5) * 120} y={150 + (k - 0.5) * 40} r={8} color="#4ade80" />
            <text x={330 - (k - 0.5) * 120} y={188} textAnchor="middle" fontSize="7" fill="#86efac">⁴He 3.5 MeV</text>
            <Dot x={330 + (k - 0.5) * 260} y={150 - (k - 0.5) * 60} r={4} color="#f87171" halo />
            <text x={330 + (k - 0.5) * 260} y={110} textAnchor="middle" fontSize="7" fill="#fca5a5">n 14.1 MeV</text>
          </>)}
          <Plate x={40} y={210} w={280} color="#f87171" lines={[
            'd + t → ⁴He (3.5 MeV) + n (14.1 MeV)',
            'Sealed tube: ion source + 100 kV accel',
            '+ hydride target. Yield 10⁸–10¹¹ n/s.',
            'Switch it off and the emission stops.',
          ]} />
          <Plate x={350} y={210} w={270} color="#38bdf8" lines={[
            'D-D alternative: 2.45 MeV neutrons,',
            'lower yield, no tritium inventory —',
            'often simpler from a licensing view.',
          ]} />
        </g>
      );
    }
    case 1: { // moderation
      const bounces = 8;
      const k = saw(t, 0.35);
      const idx = Math.min(bounces - 1, Math.floor(k * bounces));
      const energyLabels = ['14 MeV', '4.7 MeV', '1.6 MeV', '520 keV', '175 keV', '58 keV', '19 keV', '0.025 eV'];
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">MODERATION — SLOWING DOWN IN HYDROGEN</text>
          <rect x="120" y="90" width="400" height="130" rx="8" fill="#0d2018" stroke="#22c55e" strokeWidth="1.5" />
          <text x="130" y="84" fontSize="7" fill="#86efac">polyethylene (CH₂)ₙ</text>
          {Array.from({ length: 24 }, (_, i) => (
            <circle key={i} cx={140 + (i % 8) * 50} cy={110 + Math.floor(i / 8) * 42} r="7" fill="#134e4a" stroke="#2dd4bf" strokeWidth="1" />
          ))}
          <polyline points={Array.from({ length: idx + 1 }, (_, i) => `${140 + i * 46},${120 + (i % 2) * 70}`).join(' ')}
            fill="none" stroke="#f87171" strokeWidth="1.4" strokeDasharray="3 2" />
          <Dot x={140 + idx * 46} y={120 + (idx % 2) * 70} r={4 - idx * 0.3} color={idx > 5 ? '#38bdf8' : '#f87171'} />
          <text x="540" y="150" fontSize="9" fill={idx > 5 ? '#7dd3fc' : '#fca5a5'}>{energyLabels[idx]}</text>
          <text x="540" y="166" fontSize="7" fill="#94a3b8">after {idx} collisions</text>
          <Plate x={120} y={232} w={430} color="#4ade80" lines={[
            'Hydrogen has almost the same mass as a neutron, so one head-on collision can take',
            'nearly all the energy. About 18 collisions in water take 2 MeV down to thermal.',
            'Then boron-10 or lithium-6 captures the thermal neutron — moderate first, absorb second.',
          ]} />
        </g>
      );
    }
    case 2: { // PFNA cargo interrogation
      const k = saw(t, 0.5);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">NEUTRON INTERROGATION OF CARGO</text>
          <Box x={40} y={132} w={70} h={40} label="D-T tube" sub="pulsed" stroke="#f87171" />
          <rect x="150" y="100" width="300" height="104" rx="6" fill="#111c2e" stroke="#475569" strokeWidth="1.5" />
          <text x="300" y="94" textAnchor="middle" fontSize="7" fill="#94a3b8">container under interrogation</text>
          <rect x="250" y="130" width="60" height="46" rx="4" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          <text x="280" y="157" textAnchor="middle" fontSize="7" fill="#fdba74">suspect load</text>
          {Array.from({ length: 6 }, (_, i) => {
            const f = (k + i / 6) % 1;
            return <Dot key={i} x={112 + f * 150} y={152 + (i - 2.5) * 9} r={2.6} color="#f87171" halo={false} />;
          })}
          {k > 0.4 && Array.from({ length: 5 }, (_, i) => (
            <Wave key={i} x={310} y={140 + i * 9} angle={-0.4 + i * 0.2} len={90 * (k - 0.4)} color="#a78bfa" amp={2.5} phase={t * 9} width={1} />
          ))}
          <rect x="470" y="106" width="12" height="92" rx="3" fill="#0b1220" stroke="#a855f7" strokeWidth="1.5" />
          <text x="490" y="152" fontSize="7" fill="#d8b4fe">γ spectrometer</text>
          <Plate x={40} y={216} w={560} color="#a78bfa" lines={[
            'Fast neutrons excite nuclei; the prompt and delayed gamma lines identify the elements present:',
            'N-14 at 10.8 MeV, C-12 at 4.4 MeV, O-16 at 6.1 MeV. Explosives are nitrogen- and oxygen-rich,',
            'narcotics are carbon- and hydrogen-rich — element ratios classify the load in under a minute.',
          ]} />
        </g>
      );
    }
    default: { // detection & shielding
      const k = saw(t, 0.7);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">DETECTION &amp; SHIELDING STRATEGY</text>
          <rect x="60" y="96" width="70" height="130" rx="6" fill="#0d2018" stroke="#22c55e" strokeWidth="1.5" />
          <text x="95" y="90" textAnchor="middle" fontSize="7" fill="#86efac">moderator</text>
          <rect x="130" y="96" width="34" height="130" rx="4" fill="#1e1b4b" stroke="#818cf8" strokeWidth="1.5" />
          <text x="147" y="240" textAnchor="middle" fontSize="7" fill="#a5b4fc">B / Cd</text>
          <rect x="164" y="96" width="30" height="130" rx="4" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.5" />
          <text x="179" y="240" textAnchor="middle" fontSize="7" fill="#cbd5e1">Pb</text>
          <Dot x={20 + k * 150} y={150} r={3.4 - k * 1.4} color={k > 0.5 ? '#38bdf8' : '#f87171'} />
          {k > 0.72 && <Wave x={196} y={150} angle={0} len={60} color="#fde047" amp={2.5} phase={t * 8} width={1} />}
          <text x="200" y="176" fontSize="7" fill="#fde047">capture γ (2.2 MeV in H)</text>
          <Plate x={280} y={92} w={340} color="#38bdf8" lines={[
            'ORDER MATTERS: moderate → absorb → attenuate capture gammas.',
            'Lead first would do almost nothing: fast neutrons barely notice it.',
            'Detectors: ³He proportional counters (scarce since 2009),',
            'now ¹⁰B-lined tubes and ⁶Li glass or plastic scintillators.',
            'Personal dosimetry uses CR-39 track etch or rem-meters.',
          ]} />
          <Plate x={280} y={204} w={340} color="#f87171" lines={[
            'Neutron quality factor is up to 20 — the same absorbed dose',
            'carries far more biological weight than a gamma photon.',
          ]} />
        </g>
      );
    }
  }
}

export const NEUTRON_FILM: Film = {
  id: 'film-neutron',
  title: 'Neutron sources — generation, moderation, interrogation, shielding',
  tagline: 'D-T fusion tubes, thermalisation in hydrogen, cargo element analysis and why lead is the wrong first layer',
  duration: 30,
  accent: 'text-red-400',
  hex: '#f87171',
  chapters: [
    { t: 0,  title: 'D-T generation', caption: 'A sealed tube accelerates deuterium ions into a tritiated target at about 100 kV. The fusion reaction releases a helium nucleus and a 14.1 MeV neutron — and stops the instant the high voltage is removed.', detail: 'Yields run 10⁸–10¹¹ neutrons per second. The switchable nature is a major regulatory advantage over Am-Be or Cf-252.' },
    { t: 8,  title: 'Moderation', caption: 'Fast neutrons lose energy through elastic collisions. Hydrogen works best because it has nearly the same mass, so a single head-on collision can absorb almost the whole energy.', detail: 'About eighteen collisions in water take a 2 MeV neutron to thermal energy, where boron or lithium can capture it.' },
    { t: 16, title: 'Cargo interrogation', caption: 'Pulsed fast neutrons excite the nuclei inside a container. The prompt gamma lines that come back identify elements — nitrogen, carbon, oxygen, chlorine — rather than just density.', detail: 'Explosives are nitrogen- and oxygen-rich, narcotics carbon- and hydrogen-rich. Element ratios classify a load in under a minute.' },
    { t: 23, title: 'Detection and shielding', caption: 'Shield in the right order: moderate with hydrogen, absorb with boron or cadmium, then attenuate the capture gammas with lead. Starting with lead achieves almost nothing.', detail: 'Since the 2009 helium-3 shortage, boron-10 lined tubes and lithium-6 scintillators dominate portal monitors (ANSI N42.43).' },
  ],
  facts: [
    { label: 'D-T neutron energy', value: '14.1 MeV' },
    { label: 'D-D neutron energy', value: '2.45 MeV' },
    { label: 'Thermal energy', value: '0.025 eV' },
    { label: 'Quality factor', value: 'up to 20' },
  ],
  scene: neutronScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 3 — GAMMA IRRADIATOR
// ═══════════════════════════════════════════════════════════════════════════════
function irradiatorScene({ ch, p, t }: SceneCtx) {
  const pool = (srcY: number) => (
    <g>
      <rect x="180" y="120" width="150" height="150" rx="6" fill="#0c2237" stroke="#334155" strokeWidth="3" />
      <rect x="188" y="128" width="134" height="136" fill="#0e3a5c" opacity="0.6" />
      <text x="255" y="284" textAnchor="middle" fontSize="7" fill="#7dd3fc">5–6 m demineralised water</text>
      <rect x="238" y={srcY} width="34" height="46" rx="4" fill="#3f2a12" stroke="#f97316" strokeWidth="1.5" />
      <text x="255" y={srcY + 28} textAnchor="middle" fontSize="7" fill="#fdba74">Co-60</text>
    </g>
  );
  switch (ch) {
    case 0: {
      const glow = 0.4 + 0.35 * Math.abs(osc(t, 0.5));
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">SOURCE AT REST — STORED UNDER WATER</text>
          {pool(196)}
          <circle cx="255" cy="219" r={30 * glow} fill="#38bdf8" opacity={0.25 * glow} />
          <text x="300" y="196" fontSize="7" fill="#7dd3fc">Čerenkov glow</text>
          <Plate x={360} y={96} w={260} color="#38bdf8" lines={[
            'Water is shield, coolant and window:',
            'operators can see the racks from the',
            'pool edge at background dose rate.',
            'Purity is monitored continuously —',
            'conductivity rise means corrosion risk.',
          ]} />
          <Plate x={360} y={202} w={260} color="#f97316" lines={[
            'Category I/II activity up to ~10 PBq',
            'Average photon energy 1.25 MeV',
            'Decay 12.3 % per year → reload cycle',
          ]} />
        </g>
      );
    }
    case 1: {
      const rise = ease(p);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">SOURCE RAISE — INTERLOCK CHAIN MUST BE SATISFIED</text>
          {pool(196 - rise * 96)}
          {rise > 0.4 && Array.from({ length: 10 }, (_, i) => {
            const a = (i / 10) * Math.PI * 2;
            return <Wave key={i} x={255} y={128} angle={a} len={50 * rise} color="#fbbf24" amp={2.5} phase={t * 8} width={1} />;
          })}
          <Plate x={360} y={92} w={260} color="#4ade80" lines={[
            'INTERLOCKS CHECKED BEFORE RAISE:',
            '· door closed and locked',
            '· occupancy / motion sensor clear',
            '· area monitor reading background',
            '· key switch and search-and-secure done',
          ]} />
          <Plate x={360} y={200} w={260} color="#f87171" lines={[
            'Any interlock loss drops the rack back',
            'into the pool by gravity — the failure',
            'mode is designed to be safe.',
          ]} />
          <text x="60" y="150" fontSize="8" fill={rise > 0.4 ? '#f87171' : '#4ade80'}>{rise > 0.4 ? '☢ SOURCE UP' : '● SOURCE DOWN'}</text>
        </g>
      );
    }
    case 2: {
      const conv = saw(t, 0.25);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">PRODUCT CONVEYOR — DOSE FROM RESIDENCE TIME</text>
          <rect x="255" y="118" width="26" height="70" rx="3" fill="#3f2a12" stroke="#f97316" strokeWidth="1.5" />
          {Array.from({ length: 12 }, (_, i) => {
            const a = (i / 12) * Math.PI * 2;
            return <line key={i} x1="268" y1="153" x2={268 + Math.cos(a) * 110} y2={153 + Math.sin(a) * 90} stroke="#fbbf24" strokeWidth="0.7" opacity="0.35" />;
          })}
          <rect x="60" y="200" width="500" height="8" rx="4" fill="#334155" />
          {Array.from({ length: 6 }, (_, i) => {
            const f = (conv + i / 6) % 1;
            const x = 60 + f * 480;
            const dist = Math.abs(x - 268);
            const dose = Math.max(0, 1 - dist / 260);
            return (
              <g key={i}>
                <rect x={x} y="168" width="36" height="32" rx="3" fill="#111c2e" stroke="#64748b" strokeWidth="1" />
                <rect x={x + 2} y={198 - dose * 28} width="32" height={dose * 28} fill="#fbbf24" opacity="0.35" />
              </g>
            );
          })}
          <text x="60" y="226" fontSize="7" fill="#94a3b8">totes pass the rack on multiple passes to even out the dose</text>
          <Plate x={360} y={236} w={260} color="#4ade80" lines={[
            'Dose uniformity ratio DUR < 1.5',
            'Verified by alanine / Fricke dosimeters',
            'ISO 11137 for medical device sterilisation',
          ]} />
          <Plate x={60} y={92} w={270} color="#38bdf8" lines={[
            'Typical doses:',
            '· food phytosanitary 0.15–1 kGy',
            '· spice decontamination 6–10 kGy',
            '· medical device sterilisation 25 kGy',
            '· polymer cross-linking 50–200 kGy',
          ]} />
        </g>
      );
    }
    default: {
      const alarm = saw(t, 0.4) > 0.6;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">SAFETY ARCHITECTURE — DEFENCE IN DEPTH</text>
          {[
            ['Access control', 'key, search-and-secure, door interlock'],
            ['Source position', 'redundant independent monitoring'],
            ['Area monitoring', 'independent detector at every exit'],
            ['Emergency lower', 'gravity return, no power required'],
            ['Personal dosimetry', 'TLD/EPD plus pocket alarm'],
          ].map(([a, b], i) => (
            <g key={i}>
              <rect x="60" y={86 + i * 34} width="330" height="28" rx="4" fill="#0b1220" stroke={i === 3 && alarm ? '#f87171' : '#334155'} strokeWidth="1.2" />
              <text x="72" y={104 + i * 34} fontSize="8" fill="#cbd5e1">{a}</text>
              <text x="200" y={104 + i * 34} fontSize="7" fill="#94a3b8">{b}</text>
              <circle cx="374" cy={100 + i * 34} r="4" fill={i === 3 && alarm ? '#f87171' : '#4ade80'} />
            </g>
          ))}
          <Plate x={410} y={92} w={210} color="#f87171" lines={[
            'IAEA TECDOC-1313 requires that',
            'no single failure can leave the',
            'source exposed with the room',
            'accessible. Operator licensing and',
            'documented emergency drills are',
            'part of the licence, not optional.',
          ]} />
        </g>
      );
    }
  }
}

export const IRRADIATOR_FILM: Film = {
  id: 'film-irradiator',
  title: 'Gamma irradiator — pool storage, source raise, dose delivery',
  tagline: 'How a multi-petabecquerel Co-60 plant sterilises product without ever exposing a person',
  duration: 28,
  accent: 'text-rose-400',
  hex: '#fb7185',
  chapters: [
    { t: 0,  title: 'Source at rest', caption: 'Between runs the cobalt-60 racks sit under five to six metres of demineralised water. The water shields, cools and stays transparent, so the racks can be inspected visually from the pool edge.', detail: 'Water purity is monitored continuously — rising conductivity signals corrosion risk to the source capsules.' },
    { t: 7,  title: 'Raising the source', caption: 'The rack only rises when every interlock is satisfied: door locked, occupancy sensor clear, area monitor at background and the search-and-secure procedure completed.', detail: 'If any interlock drops out, the rack falls back into the pool under gravity — the failure mode is inherently safe.' },
    { t: 14, title: 'Dose delivery', caption: 'Product moves past the rack on a conveyor. Absorbed dose is simply the time spent near the source, so speed and pass pattern are the process controls.', detail: 'Typical doses: 0.15–1 kGy phytosanitary, 6–10 kGy for spices, 25 kGy for medical device sterilisation per ISO 11137.' },
    { t: 21, title: 'Safety architecture', caption: 'Every layer is redundant and independent: access control, source-position monitoring, area radiation monitors, gravity emergency return, and personal dosimetry.', detail: 'IAEA TECDOC-1313: no single failure may leave the source exposed while the cell is accessible.' },
  ],
  facts: [
    { label: 'Source activity', value: 'up to ~10 PBq' },
    { label: 'Pool depth', value: '5–6 m water' },
    { label: 'Sterilisation dose', value: '25 kGy' },
    { label: 'Uniformity', value: 'DUR < 1.5' },
  ],
  scene: irradiatorScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 4 — INDUSTRIAL RADIOGRAPHY
// ═══════════════════════════════════════════════════════════════════════════════
function industrialScene({ ch, p, t }: SceneCtx) {
  switch (ch) {
    case 0: {
      const a = 0.2 + ease(p) * 0.5;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">GEOMETRY — UNSHARPNESS IS DECIDED BEFORE THE EXPOSURE</text>
          <circle cx="120" cy="150" r={4 + a * 8} fill="#fde047" />
          <text x="120" y="128" textAnchor="middle" fontSize="7" fill="#fde047">focal spot f</text>
          <rect x="330" y="110" width="24" height="80" rx="3" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.2" />
          <text x="342" y="102" textAnchor="middle" fontSize="7" fill="#cbd5e1">object</text>
          <rect x="470" y="90" width="10" height="120" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.5" />
          <text x="496" y="150" fontSize="7" fill="#86efac">film / DDA</text>
          <line x1="120" y1={150 - (4 + a * 8)} x2="470" y2={150 - 40 - a * 30} stroke="#fde047" strokeWidth="0.8" opacity="0.6" />
          <line x1="120" y1={150 + (4 + a * 8)} x2="470" y2={150 + 40 + a * 30} stroke="#fde047" strokeWidth="0.8" opacity="0.6" />
          <line x1="120" y1="150" x2="330" y2="150" stroke="#64748b" strokeWidth="0.8" strokeDasharray="3 2" />
          <text x="220" y="200" fontSize="7" fill="#94a3b8">a (source → object)</text>
          <text x="392" y="200" fontSize="7" fill="#94a3b8">b</text>
          <Plate x={90} y={224} w={470} color="#fde047" lines={[
            'Ug = f · b / a  — geometric unsharpness',
            'Small focal spot, object hard against the detector, long SOD → sharp image.',
            `Live: f = ${(0.4 + a * 3).toFixed(1)} mm  →  Ug = ${((0.4 + a * 3) * 0.25).toFixed(2)} mm`,
          ]} />
        </g>
      );
    }
    case 1: {
      const kv = 160 + ease(p) * 290;
      const pen = Math.round((kv - 100) * 0.2);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">ENERGY SELECTION — USE THE LOWEST kV THAT PENETRATES</text>
          <rect x="150" y="96" width="320" height="112" rx="4" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.5" />
          <rect x="150" y="96" width={Math.min(320, pen * 3.4)} height="112" fill="#38bdf8" fillOpacity="0.18" />
          <text x="160" y="90" fontSize="7" fill="#cbd5e1">steel section</text>
          <text x="160" y="230" fontSize="9" fill="#38bdf8">{Math.round(kv)} kV → ≈ {pen} mm penetration</text>
          <Plate x={150} y={244} w={430} color="#f87171" lines={[
            'Too much energy is not "safer imaging": contrast collapses as Compton scatter takes over,',
            'and the controlled area grows for no benefit. Match the energy to the thickness.',
          ]} />
          <Plate x={40} y={92} w={100} color="#38bdf8" lines={[
            '160 kV 25 mm',
            '225 kV 40 mm',
            '320 kV 60 mm',
            '450 kV 90 mm',
            '1 MeV 150 mm',
            '9 MeV 350 mm',
          ]} />
        </g>
      );
    }
    case 2: {
      const k = saw(t, 0.3);
      const visible = Math.floor(k * 7);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">IMAGE QUALITY INDICATOR — PROVING THE TECHNIQUE</text>
          <rect x="120" y="96" width="380" height="120" rx="4" fill="#0f172a" stroke="#334155" strokeWidth="1.5" />
          {Array.from({ length: 7 }, (_, i) => (
            <g key={i}>
              <rect x={150 + i * 48} y="120" width={2 + i * 1.4} height="60" fill="#94a3b8" opacity={i <= visible ? 0.95 : 0.12} />
              <text x={150 + i * 48} y="196" fontSize="6.5" fill={i <= visible ? '#cbd5e1' : '#475569'}>W{16 - i}</text>
            </g>
          ))}
          <text x="120" y="90" fontSize="7" fill="#94a3b8">wire-type IQI (EN 462-1 / ASTM E747)</text>
          <text x="120" y="234" fontSize="8" fill="#4ade80">smallest visible wire = W{16 - visible} → sensitivity demonstrated</text>
          <Plate x={120} y={246} w={470} color="#38bdf8" lines={[
            'The IQI does not measure the weld — it certifies that the technique could have seen a flaw',
            'of a given size. No visible IQI wire, no valid radiograph, whatever the image looks like.',
          ]} />
        </g>
      );
    }
    default: {
      const k = saw(t, 0.3);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">FILM vs DIGITAL DETECTOR ARRAYS</text>
          <rect x="70" y="96" width="220" height="120" rx="4" fill="#0b1220" stroke="#64748b" strokeWidth="1.5" />
          <text x="80" y="90" fontSize="7" fill="#94a3b8">film — chemistry, latitude, archive</text>
          <rect x="90" y="120" width="180" height="72" fill="#1f2937" />
          <path d="M 110 156 q 40 -20 70 4 q 30 20 70 -6" fill="none" stroke="#cbd5e1" strokeWidth="2" opacity="0.55" />
          <rect x="350" y="96" width="220" height="120" rx="4" fill="#0b1220" stroke="#22c55e" strokeWidth="1.5" />
          <text x="360" y="90" fontSize="7" fill="#86efac">DDA — instant, wide dynamic range</text>
          {Array.from({ length: 12 }, (_, i) => (
            <rect key={i} x={362 + (i % 6) * 34} y={120 + Math.floor(i / 6) * 36} width="30" height="32"
              fill="#22c55e" opacity={0.12 + 0.5 * Math.abs(Math.sin(k * 6 + i))} />
          ))}
          <Plate x={70} y={232} w={500} color="#38bdf8" lines={[
            'Digital: no consumables, immediate review, software measurement, easy archive — but SNR and',
            'basic spatial resolution must be qualified per EN ISO 17636-2 Class A or B before it replaces film.',
            'Computed radiography with imaging plates sits between the two on cost and performance.',
          ]} />
        </g>
      );
    }
  }
}

export const INDUSTRIAL_FILM: Film = {
  id: 'film-industrial',
  title: 'Industrial radiography — geometry, energy, IQI, detector',
  tagline: 'The four decisions that determine whether a radiograph is admissible evidence',
  duration: 28,
  accent: 'text-sky-400',
  hex: '#38bdf8',
  chapters: [
    { t: 0,  title: 'Geometry', caption: 'Geometric unsharpness is fixed by the setup, not by the exposure. It equals the focal spot size times the object-to-detector distance divided by the source-to-object distance.', detail: 'Push the object against the detector, back the source off, and use the smallest focal spot the output allows.' },
    { t: 7,  title: 'Energy selection', caption: 'Use the lowest kilovoltage that still penetrates the section. Excess energy destroys contrast through Compton scatter and enlarges the controlled area for nothing.', detail: '160 kV covers about 25 mm of steel; 450 kV reaches 90 mm; MeV-class sources are needed beyond that.' },
    { t: 14, title: 'Image quality indicator', caption: 'The IQI is the proof of technique. The smallest visible wire or hole establishes the flaw size the radiograph could have detected.', detail: 'If no IQI element is visible, the radiograph is not valid — regardless of how good the image looks subjectively.' },
    { t: 21, title: 'Film or digital', caption: 'Digital detector arrays give immediate results, wide dynamic range and no chemistry, but they have to be qualified for signal-to-noise and basic spatial resolution before replacing film.', detail: 'EN ISO 17636-2 defines Class A and Class B digital techniques; ASME V and API 1104 govern acceptance in their sectors.' },
  ],
  facts: [
    { label: 'Unsharpness', value: 'Ug = f·b/a' },
    { label: '450 kV reach', value: '≈ 90 mm steel' },
    { label: 'IQI standards', value: 'EN 462-1 / E747' },
    { label: 'Digital classes', value: 'ISO 17636-2 A/B' },
  ],
  scene: industrialScene,
};

// ═══════════════════════════════════════════════════════════════════════════════
// 5 — SECURITY SCREENING
// ═══════════════════════════════════════════════════════════════════════════════
function securityScene({ ch, p, t }: SceneCtx) {
  switch (ch) {
    case 0: {
      const belt = saw(t, 0.22);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">TUNNEL GEOMETRY — LINE-SCAN IMAGING</text>
          <rect x="150" y="96" width="330" height="120" rx="8" fill="#111c2e" stroke="#475569" strokeWidth="2" />
          <rect x="130" y="196" width="380" height="8" rx="4" fill="#334155" />
          <rect x="196" y="86" width="34" height="24" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.2" />
          <text x="213" y="80" textAnchor="middle" fontSize="7" fill="#86efac">tube 140–160 kV</text>
          <polygon points="213,110 150,196 300,196" fill="#fde047" fillOpacity="0.12" />
          <path d="M 150 196 L 213 110 L 300 196" fill="none" stroke="#22c55e" strokeWidth="1.5" strokeDasharray="3 2" />
          <text x="322" y="140" fontSize="7" fill="#86efac">L-shaped detector array</text>
          {Array.from({ length: 3 }, (_, i) => {
            const f = (belt + i / 3) % 1;
            return <rect key={i} x={130 + f * 360} y="170" width="40" height="26" rx="3" fill="#0b1220" stroke="#94a3b8" strokeWidth="1" />;
          })}
          <text x="130" y="228" fontSize="7" fill="#94a3b8">bag speed 0.2–0.5 m/s — one detector line per step</text>
          <Plate x={150} y={240} w={430} color="#38bdf8" lines={[
            'Lead curtains at both ends keep the leakage dose below 1 µSv/h at 5 cm.',
            'The image is built line by line as the belt moves — geometry is fixed, so calibration holds.',
          ]} />
        </g>
      );
    }
    case 1: {
      const k = saw(t, 0.35);
      const mats = [
        { z: 7, label: 'organic (Zeff 6–8)', col: '#f97316' },
        { z: 14, label: 'light metal / salts', col: '#4ade80' },
        { z: 26, label: 'steel', col: '#38bdf8' },
        { z: 82, label: 'lead — opaque', col: '#1f2937' },
      ];
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">DUAL ENERGY — TURNING TWO IMAGES INTO A MATERIAL</text>
          {mats.map((m, i) => (
            <g key={i}>
              <rect x={70 + i * 130} y="96" width="90" height="60" rx="4" fill={m.col} fillOpacity="0.35" stroke={m.col} strokeWidth="1.4" />
              <text x={115 + i * 130} y="130" textAnchor="middle" fontSize="8" fill="#e2e8f0">Z ≈ {m.z}</text>
              <text x={115 + i * 130} y="172" textAnchor="middle" fontSize="6.5" fill="#94a3b8">{m.label}</text>
              <rect x={70 + i * 130} y="184" width="90" height="8" rx="3" fill="#0b1220" stroke="#334155" />
              <rect x={71 + i * 130} y="185" width={88 * (0.25 + 0.7 * (1 - Math.exp(-m.z / 30)))} height="6" rx="3" fill={m.col} opacity={0.55 + 0.4 * Math.abs(Math.sin(k * 6 + i))} />
            </g>
          ))}
          <text x="70" y="206" fontSize="7" fill="#94a3b8">high-energy / low-energy attenuation ratio →</text>
          <Plate x={70} y={220} w={500} color="#f97316" lines={[
            'Low energy is photoelectric-dominated (∝ Z³ᐟ⁵), high energy is Compton-dominated (∝ density).',
            'The ratio of the two frames therefore separates effective atomic number from mass — which is',
            'exactly what the orange / green / blue colour convention on every screening console encodes.',
          ]} />
        </g>
      );
    }
    case 2: {
      const a = t * 1.4;
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">HOLD-BAGGAGE CT — VOLUMETRIC, AUTOMATIC DETECTION</text>
          <circle cx="250" cy="160" r="86" fill="none" stroke="#334155" strokeWidth="14" />
          <circle cx="250" cy="160" r="86" fill="none" stroke="#475569" strokeWidth="1" strokeDasharray="4 4" />
          <g transform={`rotate(${(a * 60) % 360} 250 160)`}>
            <rect x="238" y="60" width="24" height="18" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.2" />
            <path d="M 250 78 L 210 244 L 290 244 Z" fill="#fde047" fillOpacity="0.14" />
            <rect x="206" y="240" width="88" height="10" rx="3" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          </g>
          <rect x="228" y="142" width="44" height="36" rx="4" fill="#0b1220" stroke="#94a3b8" strokeWidth="1.2" />
          <rect x="238" y="152" width="18" height="16" rx="2" fill="#f97316" fillOpacity="0.7" />
          <Plate x={370} y={92} w={250} color="#4ade80" lines={[
            'Reconstruction gives CT number and',
            'density for every voxel — no longer a',
            'shadow, but a measured material map.',
            'EDS algorithms alarm on the density /',
            'Zeff signature of known explosives.',
            'Operator resolves the alarm on-screen.',
          ]} />
          <Plate x={370} y={216} w={250} color="#38bdf8" lines={[
            'ECAC Standard 3 / TSA certification',
            'define detection and false-alarm rates.',
          ]} />
        </g>
      );
    }
    default: {
      const k = saw(t, 0.4);
      return (
        <g>
          <text x="320" y="52" textAnchor="middle" fontSize="10" fill="#cbd5e1">DOSE PERSPECTIVE &amp; OPERATOR FACTORS</text>
          {[
            { l: 'Backscatter body scan', v: 0.1, u: '0.05–0.1 µSv' },
            { l: 'Baggage X-ray leakage (1 h)', v: 1, u: '< 1 µSv' },
            { l: 'Chest radiograph', v: 20, u: '≈ 20 µSv' },
            { l: 'Transatlantic flight', v: 40, u: '≈ 40 µSv' },
            { l: 'Natural background (1 day)', v: 8, u: '≈ 8 µSv' },
          ].map((r, i) => (
            <g key={i}>
              <text x="60" y={100 + i * 26} fontSize="8" fill="#cbd5e1">{r.l}</text>
              <rect x="300" y={90 + i * 26} width="220" height="12" rx="4" fill="#0b1220" stroke="#334155" />
              <rect x="301" y={91 + i * 26} width={Math.min(218, (r.v / 40) * 218)} height="10" rx="4" fill="#38bdf8" opacity="0.75" />
              <text x="530" y={100 + i * 26} fontSize="7" fill="#94a3b8">{r.u}</text>
            </g>
          ))}
          <Plate x={60} y={224} w={520} color="#a78bfa" lines={[
            'The limiting factor at a checkpoint is not dose — it is human vigilance. Image interpretation',
            `performance falls measurably after 20 minutes of continuous screening (currently ${Math.round(20 - k * 8)} min into a shift),`,
            'which is why rotation intervals, TIP threat projection and recurrent testing are regulated.',
          ]} />
        </g>
      );
    }
  }
}

export const SECURITY_FILM: Film = {
  id: 'film-security',
  title: 'Security screening — tunnel, dual energy, CT and the operator',
  tagline: 'How a checkpoint turns attenuation into a material decision, and where the real limit sits',
  duration: 28,
  accent: 'text-teal-400',
  hex: '#2dd4bf',
  chapters: [
    { t: 0,  title: 'Tunnel geometry', caption: 'A fixed tube fires through the bag onto an L-shaped detector array while the belt moves. The image is assembled one detector line at a time, so geometry and calibration stay constant.', detail: 'Lead curtains at both ends hold the leakage dose below 1 µSv/h at 5 cm from the tunnel.' },
    { t: 7,  title: 'Dual-energy discrimination', caption: 'At low energy the photoelectric effect dominates and depends strongly on atomic number; at high energy Compton scattering dominates and tracks density. The ratio of the two frames separates the two.', detail: 'That ratio is what the familiar orange-organic, green-inorganic, blue-metal colour convention actually encodes.' },
    { t: 14, title: 'Hold-baggage CT', caption: 'Rotating the source and detector around the bag reconstructs a full volume. Every voxel now carries a measured density and CT number rather than a superimposed shadow.', detail: 'Automatic explosive-detection algorithms alarm on density and effective-Z signatures; certification follows ECAC Standard 3 or TSA protocols.' },
    { t: 21, title: 'Dose and the operator', caption: 'Screening doses are tiny compared with natural background. The real performance limit is human: detection accuracy falls measurably after about twenty minutes of continuous image review.', detail: 'Hence regulated rotation intervals, threat image projection and recurrent competency testing.' },
  ],
  facts: [
    { label: 'Cabin baggage', value: '140–160 kV' },
    { label: 'Body scan dose', value: '0.05–0.1 µSv' },
    { label: 'Organic Zeff', value: '6–8' },
    { label: 'Cargo LINAC', value: '6–9 MeV' },
  ],
  scene: securityScene,
};

export const NUCLEAR_FILMS: Film[] = [
  ISOTOPE_FILM, NEUTRON_FILM, IRRADIATOR_FILM, INDUSTRIAL_FILM, SECURITY_FILM,
];

export { saw, osc };
