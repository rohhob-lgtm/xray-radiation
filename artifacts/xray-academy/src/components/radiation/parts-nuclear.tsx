import type { MicroAnim } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Part-by-part micro animations — radioisotope sources, neutron sources,
// gamma irradiators, industrial radiography and security screening.
// ═══════════════════════════════════════════════════════════════════════════════

const saw = (t: number, hz = 1) => (t * hz) % 1;
const osc = (t: number, hz = 1) => Math.sin(t * Math.PI * 2 * hz);
const L = (x: number, y: number, s: string, c = '#94a3b8', size = 7, a: 'start' | 'middle' | 'end' = 'start') => (
  <text x={x} y={y} fontSize={size} fill={c} textAnchor={a}>{s}</text>
);

// ─── RADIOISOTOPE SOURCES ─────────────────────────────────────────────────────
export const ISOTOPE_PARTS: MicroAnim[] = [
  {
    id: 'is-capsule', group: 'radioisotopes', tag: 'Source', hex: '#f97316',
    part: 'Double-encapsulated sealed source',
    summary: 'Active material is sintered into pellets or wire, sealed in an inner capsule, and that capsule is welded inside a second one — two independent barriers.',
    bullets: [
      'ISO 2919 classification code records the temperature, pressure, impact, vibration and puncture ratings.',
      'Welds are laser or TIG and are helium leak-tested at manufacture.',
      'Wipe test every 6–12 months; more than 200 Bq removable activity condemns the source.',
      'Capsule material is usually 316L stainless or, for high temperature, Inconel.',
      'A source is never opened, cut or ground in the field — a breach is a contamination event.',
    ],
    draw: t => {
      const glow = 0.5 + 0.5 * Math.abs(osc(t, 0.4));
      return (
        <g>
          <rect x="40" y="52" width="180" height="52" rx="14" fill="#0f172a" stroke="#94a3b8" strokeWidth="1.8" />
          <rect x="56" y="62" width="148" height="32" rx="10" fill="#111c2e" stroke="#cbd5e1" strokeWidth="1.2" />
          <rect x="86" y="70" width="88" height="16" rx="5" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" opacity={glow} />
          {L(130, 82, 'active pellets', '#fdba74', 6.5, 'middle')}
          {L(40, 44, 'outer capsule', '#94a3b8')}
          {L(56, 118, 'inner capsule — seal weld', '#cbd5e1')}
          {L(10, 20, 'DOUBLE ENCAPSULATION', '#cbd5e1', 8)}
          {L(190, 140, 'ISO 2919', '#f97316')}
        </g>
      );
    },
  },
  {
    id: 'is-pigtail', group: 'radioisotopes', tag: 'Projector', hex: '#fbbf24',
    part: 'Source pigtail & connector',
    summary: 'The capsule is swaged to a short flexible cable — the pigtail — which the drive cable pushes out and, critically, pulls back.',
    bullets: [
      'The female connector on the drive cable must latch positively; a partial connection is the classic accident precursor.',
      'Wear at the connector is inspected before every job and logged.',
      'If the pigtail disconnects while exposed, the source stays in the guide tube — an emergency, not a fault.',
      'Recovery requires the licensee emergency procedure and long-handled tools, never bare hands.',
      'Cable and connector are consumables with defined replacement intervals.',
    ],
    draw: t => {
      const f = saw(t, 0.45);
      const latched = f > 0.55;
      const gap = latched ? 0 : (0.55 - f) * 60;
      return (
        <g>
          <rect x="30" y="68" width="80" height="14" rx="5" fill="#334155" stroke="#94a3b8" strokeWidth="1.2" />
          {L(30, 60, 'drive cable', '#cbd5e1')}
          <rect x={110} y="64" width="14" height="22" rx="3" fill="#1f2937" stroke={latched ? '#4ade80' : '#f87171'} strokeWidth="1.4" />
          <rect x={132 + gap} y="66" width="12" height="18" rx="3" fill="#1f2937" stroke={latched ? '#4ade80' : '#f87171'} strokeWidth="1.4" />
          <rect x={144 + gap} y="60" width="60" height="30" rx="10" fill="#7c2d12" stroke="#f97316" strokeWidth="1.4" />
          {L(174 + gap, 79, 'source', '#fdba74', 7, 'middle')}
          {L(120, 116, latched ? 'connector latched ✓' : 'NOT LATCHED — do not deploy', latched ? '#4ade80' : '#f87171')}
          {L(10, 20, 'PIGTAIL CONNECTION', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'is-projector', group: 'radioisotopes', tag: 'Projector', hex: '#94a3b8',
    part: 'Projector shield & S-tube',
    summary: 'The source sits at the centre of a depleted-uranium or tungsten shield, inside an S-shaped channel so no straight line runs from the source to the outside.',
    bullets: [
      'Depleted uranium gives the highest attenuation per kilogram — critical for a device carried up scaffolding.',
      'The S-tube geometry removes any direct radiation path; scattered photons lose energy at each bounce.',
      'Surface dose rate limits and transport index are defined by IAEA SSR-6.',
      'A lock and a source-position indicator are mandatory before transport.',
      'Devices are leak-tested and inspected on a fixed schedule regardless of use.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      return (
        <g>
          <rect x="60" y="44" width="140" height="76" rx="12" fill="#1f2937" stroke="#94a3b8" strokeWidth="2" />
          <path d="M 74 108 q 0 -26 30 -26 q 30 0 30 -24 h 60" fill="none" stroke="#475569" strokeWidth="7" />
          <circle cx={f < 0.5 ? 104 - f * 40 : 134 + (f - 0.5) * 200} cy={f < 0.5 ? 90 : 58} r="5" fill="#f97316" />
          {L(64, 38, 'DU / W shield', '#cbd5e1')}
          {L(64, 134, 'S-channel — no straight path', '#94a3b8')}
          {L(10, 20, 'PROJECTOR BODY', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'is-guide', group: 'radioisotopes', tag: 'Projector', hex: '#38bdf8',
    part: 'Guide tube & directional collimator',
    summary: 'A flexible guide tube takes the source to the weld; a tungsten collimator at the end restricts emission to the useful cone and shrinks the controlled area dramatically.',
    bullets: [
      'Minimum guide tube length (typically 7 m) keeps the operator away from the exposed source.',
      'A directional collimator can cut the boundary distance by a factor of five or more.',
      'The end fitting must be secured to the object — a whipping guide tube is a real hazard.',
      'Barriers and warning signs are placed using measured, not assumed, dose rates.',
      'Every exposure ends with a survey of the projector and the full guide tube run.',
    ],
    draw: t => {
      const on = saw(t, 0.3) > 0.35;
      return (
        <g>
          <path d="M 24 110 q 60 -40 110 -30" fill="none" stroke="#475569" strokeWidth="7" />
          <rect x="130" y="66" width="26" height="26" rx="4" fill="#334155" stroke="#94a3b8" strokeWidth="1.3" />
          <circle cx="143" cy="79" r="4.5" fill="#f97316" />
          {L(120, 108, 'collimator', '#cbd5e1')}
          {on && <polygon points="156,72 232,50 232,108 156,86" fill="#fbbf24" fillOpacity="0.22" stroke="#fbbf24" strokeOpacity="0.5" />}
          {L(190, 40, on ? 'useful cone' : '', '#fbbf24')}
          {L(10, 20, 'GUIDE TUBE + COLLIMATOR', '#cbd5e1', 8)}
          {L(10, 142, 'shielded arc → boundary distance ÷ 5', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'is-survey', group: 'radioisotopes', tag: 'Instrumentation', hex: '#4ade80',
    part: 'Survey meter & alarming dosimeter',
    summary: 'A calibrated survey meter is the only proof the source came back. An audible alarming dosimeter adds an independent second line of defence.',
    bullets: [
      'Check the battery, the source check and the calibration date before every job.',
      'Geiger tubes saturate and can read low in a very intense field — ion chambers do not.',
      'Survey the projector, the guide tube and the work area after every single exposure.',
      'The alarming dosimeter is personal and worn, not left in a toolbox.',
      'A passive TLD or OSL badge provides the legal dose of record.',
    ],
    draw: t => {
      const near = 0.5 + 0.5 * osc(t, 0.25);
      const rate = 0.5 + near * 120;
      const needle = -60 + Math.min(120, Math.log10(rate + 1) * 60);
      return (
        <g>
          <rect x="40" y="44" width="96" height="80" rx="8" fill="#0b1220" stroke="#4ade80" strokeWidth="1.6" />
          <path d="M 56 100 A 32 32 0 0 1 120 100" fill="none" stroke="#334155" strokeWidth="2" />
          <line x1="88" y1="100" x2={88 + Math.cos((needle - 90) * Math.PI / 180) * 28} y2={100 + Math.sin((needle - 90) * Math.PI / 180) * 28} stroke="#4ade80" strokeWidth="1.8" />
          {L(88, 118, `${rate.toFixed(0)} µSv/h`, rate > 25 ? '#f87171' : '#86efac', 8, 'middle')}
          <rect x="160" y="60" width="34" height="52" rx="5" fill="#111c2e" stroke={rate > 25 ? '#f87171' : '#64748b'} strokeWidth="1.4" />
          {L(177, 88, rate > 25 ? '♪♪' : '—', rate > 25 ? '#f87171' : '#64748b', 10, 'middle')}
          {L(154, 128, 'EPD alarm', '#94a3b8')}
          {L(10, 20, 'SURVEY & ALARM', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'is-transport', group: 'radioisotopes', tag: 'Regulatory', hex: '#fde047',
    part: 'Type B package & transport index',
    summary: 'High-activity sources travel in Type B packages certified to survive fire, impact, puncture and immersion, labelled with a transport index derived from the dose rate at one metre.',
    bullets: [
      'Type B(U) certification requires the package to survive a defined accident sequence intact.',
      'Transport index = dose rate in µSv/h at 1 m divided by 10, rounded up.',
      'Category labels: White-I, Yellow-II, Yellow-III, set by surface and 1 m dose rates.',
      'IAEA SSR-6 (and ADR/IMDG/IATA) govern documentation, marking and vehicle placarding.',
      'Security requirements (NSS 14) apply in parallel to safety requirements — they are not the same rules.',
    ],
    draw: t => {
      const d = 0.5 + 0.5 * osc(t, 0.2);
      const ti = (0.4 + d * 2.6).toFixed(1);
      return (
        <g>
          <rect x="46" y="50" width="90" height="76" rx="6" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.6" />
          <polygon points="91,66 100,84 82,84" fill="#fde047" />
          {L(91, 100, '☢', '#fde047', 12, 'middle')}
          {L(91, 118, 'TYPE B(U)', '#cbd5e1', 7, 'middle')}
          <rect x="152" y="56" width="84" height="30" rx="4" fill="#3f3f0b" stroke="#eab308" strokeWidth="1.3" />
          {L(194, 76, 'YELLOW-III', '#fde047', 8, 'middle')}
          <rect x="152" y="94" width="84" height="26" rx="4" fill="#0b1220" stroke="#64748b" strokeWidth="1.2" />
          {L(194, 111, `TI = ${ti}`, '#cbd5e1', 8, 'middle')}
          {L(10, 20, 'TRANSPORT PACKAGE', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'is-decay', group: 'radioisotopes', tag: 'Source', hex: '#fb7185',
    part: 'Decay clock & exposure recalculation',
    summary: 'Activity falls exponentially, so the exposure time for the same film density has to be recalculated continually — daily for iridium-192.',
    bullets: [
      'Ir-192 loses about 1 % of its activity per day (73.8-day half-life).',
      'Co-60 loses about 12.3 % per year — reload planning, not daily arithmetic.',
      'Decay charts or software give the current activity; guessing produces under-exposed radiographs.',
      'Source replacement is scheduled on activity, not on calendar age alone.',
      'The decayed source remains a licensed radioactive item until formally disposed of.',
    ],
    draw: t => {
      const f = saw(t, 0.18);
      const a = Math.pow(0.5, f * 4);
      return (
        <g>
          <line x1="34" y1="120" x2="230" y2="120" stroke="#334155" />
          <line x1="34" y1="120" x2="34" y2="34" stroke="#334155" />
          <polyline points={Array.from({ length: 60 }, (_, i) => `${34 + i * 3.3},${120 - 78 * Math.pow(0.5, (i / 60) * 4)}`).join(' ')}
            fill="none" stroke="#fb7185" strokeWidth="1.5" />
          <circle cx={34 + f * 198} cy={120 - 78 * a} r="3.2" fill="#fb7185" />
          <line x1={34 + f * 198} y1={120 - 78 * a} x2={34 + f * 198} y2="120" stroke="#fb7185" strokeWidth="0.8" strokeDasharray="2 2" />
          {L(150, 50, `A = ${(a * 100).toFixed(0)} % A₀`, '#fda4af')}
          {L(150, 64, `t = ${(f * 4).toFixed(1)} half-lives`, '#94a3b8')}
          {L(34, 134, '0', '#64748b')}
          {L(214, 134, '4 t½', '#64748b')}
          {L(10, 20, 'DECAY CLOCK', '#cbd5e1', 8)}
        </g>
      );
    },
  },
];

// ─── NEUTRON SOURCES ──────────────────────────────────────────────────────────
export const NEUTRON_PARTS: MicroAnim[] = [
  {
    id: 'nt-dt-tube', group: 'neutron', tag: 'Generator', hex: '#f87171',
    part: 'Sealed D-T tube internals',
    summary: 'An ion source ionises deuterium, an accelerating gap drives the ions to about 100 keV, and they fuse in a metal-hydride target loaded with tritium.',
    bullets: [
      'Yield is set by beam current and target loading; both decline slowly over tube life.',
      'The tube is a sealed consumable — typical life is a few thousand hours of beam-on time.',
      'Switching the high voltage off stops neutron emission instantly, unlike an isotope source.',
      'Tritium inventory is small but is still a regulated radioactive material.',
      'Pulsed operation enables time-gated measurements that separate prompt from delayed gammas.',
    ],
    draw: t => {
      const f = saw(t, 0.7);
      return (
        <g>
          <rect x="30" y="56" width="200" height="46" rx="10" fill="#0d1524" stroke="#475569" strokeWidth="1.6" />
          <rect x="42" y="64" width="34" height="30" rx="4" fill="#2a0b2e" stroke="#f472b6" strokeWidth="1.2" />
          {L(38, 116, 'ion source', '#f9a8d4')}
          <line x1="96" y1="60" x2="96" y2="98" stroke="#38bdf8" strokeWidth="1.6" />
          <line x1="122" y1="60" x2="122" y2="98" stroke="#38bdf8" strokeWidth="1.6" />
          {L(94, 48, '≈100 kV gap', '#7dd3fc')}
          <circle cx={76 + f * 116} cy="79" r="2.6" fill="#38bdf8" />
          <rect x="196" y="62" width="14" height="34" rx="3" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.3" />
          {L(184, 116, 'Ti-T target', '#fbbf24')}
          {f > 0.85 && Array.from({ length: 5 }, (_, i) => (
            <circle key={i} cx={214 + (f - 0.85) * 160} cy={79 + (i - 2) * 12} r="2.2" fill="#f87171" />
          ))}
          {L(10, 20, 'SEALED D-T TUBE', '#cbd5e1', 8)}
          {L(10, 142, '14.1 MeV neutrons · 10⁸–10¹¹ n/s', '#fca5a5')}
        </g>
      );
    },
  },
  {
    id: 'nt-ambe', group: 'neutron', tag: 'Isotopic source', hex: '#4ade80',
    part: 'Am-Be (α,n) source',
    summary: 'Alpha particles from americium-241 strike beryllium-9, producing carbon-12 and a neutron with a broad energy spectrum up to about 11 MeV.',
    bullets: [
      'Reaction: <code>⁹Be(α,n)¹²C</code>. Yield is roughly 10⁵–10⁶ neutrons per second per GBq of Am-241.',
      'Continuous spectrum averaging about 4.5 MeV, unlike the monoenergetic output of a generator.',
      'It cannot be switched off — the 432-year half-life makes it effectively permanent.',
      'Also emits a strong 59.5 keV gamma line, so shielding must handle both.',
      'Widely used for detector calibration and well logging where a generator is impractical.',
    ],
    draw: t => {
      const f = saw(t, 0.6);
      return (
        <g>
          <circle cx="100" cy="78" r="40" fill="#0d2018" stroke="#22c55e" strokeWidth="1.5" />
          {L(78, 40, 'Am-241 + Be powder', '#86efac')}
          <circle cx="88" cy="72" r="6" fill="#22c55e" />
          {L(88, 75, 'Be', '#0b1220', 6, 'middle')}
          <circle cx={88 + f * 18} cy={72 - f * 6} r="3" fill="#fde047" />
          {L(60, 100, 'α', '#fde047')}
          {f > 0.7 && Array.from({ length: 4 }, (_, i) => (
            <circle key={i} cx={140 + (f - 0.7) * 220} cy={78 + (i - 1.5) * 16} r="2.4" fill="#f87171" />
          ))}
          {L(150, 40, 'n  0.1–11 MeV', '#fca5a5')}
          {L(150, 118, 'γ 59.5 keV', '#fde047')}
          {L(10, 20, 'Am-Be (α,n)', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'nt-cf252', group: 'neutron', tag: 'Isotopic source', hex: '#a78bfa',
    part: 'Cf-252 spontaneous fission',
    summary: 'Californium-252 fissions spontaneously, releasing about four neutrons per event — an extremely compact neutron source with a fission-like spectrum.',
    bullets: [
      'About 2.3 × 10⁶ neutrons per second per microgram; a milligram is an intense source.',
      'Average neutron energy around 2.3 MeV, close to a reactor fission spectrum.',
      'Half-life 2.65 years, so the source needs replacing on a short cycle.',
      'Emits prompt gammas alongside neutrons — both must be shielded.',
      'Used for reactor start-up, neutron activation analysis, BNCT research and well logging.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      const split = f > 0.45;
      return (
        <g>
          {!split && <circle cx="110" cy="78" r={14 - f * 6} fill="#7c3aed" stroke="#a78bfa" strokeWidth="1.4" />}
          {!split && L(110, 82, 'Cf', '#e9d5ff', 8, 'middle')}
          {split && (<>
            <circle cx={110 - (f - 0.45) * 90} cy={78 + (f - 0.45) * 30} r="9" fill="#7c3aed" stroke="#a78bfa" strokeWidth="1.2" />
            <circle cx={110 + (f - 0.45) * 90} cy={78 - (f - 0.45) * 30} r="8" fill="#7c3aed" stroke="#a78bfa" strokeWidth="1.2" />
            {Array.from({ length: 4 }, (_, i) => (
              <circle key={i} cx={110 + Math.cos(i * 1.6) * (f - 0.45) * 200} cy={78 + Math.sin(i * 1.6) * (f - 0.45) * 130} r="2.4" fill="#f87171" />
            ))}
          </>)}
          {L(180, 46, '≈ 4 n / fission', '#fca5a5')}
          {L(180, 60, 'Ē ≈ 2.3 MeV', '#94a3b8')}
          {L(10, 20, 'SPONTANEOUS FISSION', '#cbd5e1', 8)}
          {L(10, 142, '2.3 × 10⁶ n/s per µg  ·  t½ 2.65 y', '#c4b5fd')}
        </g>
      );
    },
  },
  {
    id: 'nt-detector', group: 'neutron', tag: 'Detection', hex: '#38bdf8',
    part: 'He-3 / B-10 proportional counter',
    summary: 'Thermal neutrons are detected indirectly: a capture reaction releases charged particles that ionise the fill gas and produce a countable pulse.',
    bullets: [
      '³He(n,p)³H releases 764 keV; ¹⁰B(n,α)⁷Li releases 2.31 MeV — both easy to discriminate from gammas.',
      'The 2009 helium-3 shortage pushed portal monitors toward boron-lined tubes and lithium-6 scintillators.',
      'Pulse-height discrimination rejects gamma background, which matters at a border crossing.',
      'The tube only sees thermal neutrons, so a moderator jacket is part of the detector, not an accessory.',
      'ANSI N42.43 defines the performance a portal monitor must demonstrate.',
    ],
    draw: t => {
      const f = saw(t, 0.55);
      const captured = f > 0.5;
      return (
        <g>
          <rect x="50" y="52" width="160" height="52" rx="24" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.6" />
          <line x1="60" y1="78" x2="200" y2="78" stroke="#94a3b8" strokeWidth="1" />
          {L(52, 44, '³He / ¹⁰B fill gas', '#7dd3fc')}
          <circle cx={20 + f * 110} cy="78" r="2.6" fill="#f87171" opacity={captured ? 0 : 1} />
          {captured && Array.from({ length: 8 }, (_, i) => {
            const a = (i / 8) * Math.PI * 2;
            const r = (f - 0.5) * 90;
            return <circle key={i} cx={130 + Math.cos(a) * r} cy={78 + Math.sin(a) * r * 0.4} r="1.6" fill="#38bdf8" />;
          })}
          <polyline points={Array.from({ length: 40 }, (_, i) => {
            const x = 50 + i * 4;
            const spike = captured && i > 18 && i < 24 ? -22 * Math.exp(-Math.abs(i - 21) / 1.5) : 0;
            return `${x},${132 + spike}`;
          }).join(' ')} fill="none" stroke="#4ade80" strokeWidth="1.3" />
          {L(10, 20, 'NEUTRON COUNTER', '#cbd5e1', 8)}
          {L(214, 78, 'pulse', '#86efac')}
        </g>
      );
    },
  },
  {
    id: 'nt-shield', group: 'neutron', tag: 'Shielding', hex: '#22c55e',
    part: 'Layered shield — moderate, absorb, attenuate',
    summary: 'Neutron shielding is a sequence: hydrogen-rich material slows the neutrons, boron or cadmium captures them, and lead mops up the capture gammas.',
    bullets: [
      'Lead first would be almost useless — fast neutrons scatter weakly from heavy nuclei.',
      '10–20 cm of borated polyethylene handles most industrial fast-neutron fields.',
      'Capture in ordinary hydrogen emits a 2.2 MeV gamma, which is why the lead layer is needed.',
      'Boron-loaded material suppresses that capture gamma by absorbing in ¹⁰B instead.',
      'Concrete works because of its water content — dried-out concrete is a worse neutron shield.',
    ],
    draw: t => {
      const f = saw(t, 0.6);
      const stage = f < 0.4 ? 0 : f < 0.7 ? 1 : 2;
      return (
        <g>
          <rect x="70" y="40" width="52" height="90" rx="4" fill="#0d2018" stroke="#22c55e" strokeWidth="1.4" />
          <rect x="122" y="40" width="30" height="90" rx="3" fill="#1e1b4b" stroke="#818cf8" strokeWidth="1.4" />
          <rect x="152" y="40" width="26" height="90" rx="3" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.4" />
          {L(72, 34, 'PE', '#86efac')}
          {L(126, 34, 'B/Cd', '#a5b4fc')}
          {L(156, 34, 'Pb', '#cbd5e1')}
          <circle cx={20 + f * 170} cy="85" r={3.4 - f * 1.6} fill={stage === 0 ? '#f87171' : '#38bdf8'} />
          {stage >= 1 && L(120, 148, 'thermalised → captured', '#a5b4fc')}
          {stage === 2 && <polyline points="152,85 160,79 156,91 166,85" fill="none" stroke="#fde047" strokeWidth="1.3" />}
          {L(10, 20, 'SHIELD ORDER MATTERS', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'nt-remmeter', group: 'neutron', tag: 'Detection', hex: '#fde047',
    part: 'Bonner sphere / rem-meter',
    summary: 'A thermal detector inside a polyethylene sphere gives a response that roughly follows the neutron dose-equivalent curve across many decades of energy.',
    bullets: [
      'Sphere diameter tunes which energies are moderated efficiently — that is how the response is shaped.',
      'A Bonner sphere set (several diameters) can unfold an approximate neutron energy spectrum.',
      'Rem-meters are heavy and slow but remain the reference instrument for workplace neutron surveys.',
      'Personal neutron dosimetry usually uses CR-39 track etch or albedo TLDs instead.',
      'Neutron quality factors reach 20, so field measurement matters more than for photons.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      return (
        <g>
          <circle cx="110" cy="80" r="46" fill="#0d2018" stroke="#22c55e" strokeWidth="1.6" />
          <circle cx="110" cy="80" r="14" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.4" />
          {L(110, 83, '³He', '#7dd3fc', 7, 'middle')}
          {Array.from({ length: 6 }, (_, i) => {
            const a = (i / 6) * Math.PI * 2;
            const r = 60 - ((f + i / 6) % 1) * 46;
            return <circle key={i} cx={110 + Math.cos(a) * r} cy={80 + Math.sin(a) * r} r={1.4 + (r / 60) * 2} fill={r < 30 ? '#38bdf8' : '#f87171'} />;
          })}
          {L(166, 44, 'moderating', '#86efac')}
          {L(166, 56, 'sphere', '#86efac')}
          {L(10, 20, 'REM-METER', '#cbd5e1', 8)}
          {L(10, 142, 'response ≈ dose-equivalent curve', '#94a3b8')}
        </g>
      );
    },
  },
];

// ─── GAMMA IRRADIATOR ─────────────────────────────────────────────────────────
export const IRRADIATOR_PARTS: MicroAnim[] = [
  {
    id: 'ir-rack', group: 'gamma-irradiators', tag: 'Source', hex: '#f97316',
    part: 'Source pencils & rack geometry',
    summary: 'Cobalt-60 slugs are sealed in double-encapsulated pencils, loaded into modules, and arranged in a planar rack so the product sees a broad, even field.',
    bullets: [
      'Pencil loading is planned so activity is highest where the product dwell time is shortest.',
      'Racks are reloaded periodically because Co-60 decays about 12.3 % per year.',
      'Source movement and loading are done underwater with long-handled tools.',
      'Each pencil is tracked by serial number for the whole facility lifetime.',
      'Rack geometry is a commissioning input to the dose-mapping model.',
    ],
    draw: t => {
      const glow = 0.5 + 0.5 * Math.abs(osc(t, 0.4));
      return (
        <g>
          <rect x="70" y="34" width="120" height="96" rx="4" fill="#0b1220" stroke="#64748b" strokeWidth="1.4" />
          {Array.from({ length: 18 }, (_, i) => (
            <rect key={i} x={80 + (i % 6) * 18} y={44 + Math.floor(i / 6) * 30} width="10" height="24" rx="3"
              fill="#7c2d12" stroke="#f97316" strokeWidth="1" opacity={0.55 + 0.45 * glow * Math.abs(Math.sin(t + i))} />
          ))}
          {L(70, 28, 'source rack module', '#fdba74')}
          {L(10, 20, 'Co-60 PENCILS', '#cbd5e1', 8)}
          {L(10, 144, '1.17 + 1.33 MeV γ · 12.3 %/y decay', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ir-pool', group: 'gamma-irradiators', tag: 'Shielding', hex: '#38bdf8',
    part: 'Storage pool & water treatment',
    summary: 'Five to six metres of demineralised water shields the racks completely while staying clear enough for visual inspection from the pool edge.',
    bullets: [
      'Deionisation keeps conductivity low, which limits corrosion of the stainless capsules.',
      'Pool water is monitored for activity — any rise is a leaking-source indicator.',
      'Level and temperature alarms are part of the safety system, not just plant monitoring.',
      'Čerenkov glow is the visible signature of the beta emission from the decay chain.',
      'Ion exchange resin becomes radioactive waste and is managed as such.',
    ],
    draw: t => {
      const g = 0.4 + 0.4 * Math.abs(osc(t, 0.35));
      return (
        <g>
          <rect x="60" y="34" width="140" height="106" rx="5" fill="#0c2237" stroke="#334155" strokeWidth="2.4" />
          <rect x="66" y="40" width="128" height="96" fill="#0e3a5c" opacity="0.6" />
          <rect x="112" y="82" width="34" height="42" rx="4" fill="#3f2a12" stroke="#f97316" strokeWidth="1.3" />
          <circle cx="129" cy="103" r={26 * g} fill="#38bdf8" opacity={0.25} />
          {L(206, 60, 'demineralised', '#7dd3fc')}
          {L(206, 72, '5–6 m', '#7dd3fc')}
          {L(206, 100, 'Čerenkov', '#38bdf8')}
          {L(10, 20, 'STORAGE POOL', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ir-conveyor', group: 'gamma-irradiators', tag: 'Process', hex: '#4ade80',
    part: 'Carrier conveyor & pass pattern',
    summary: 'Totes travel past the rack on both sides and are often turned end-for-end, so the maximum and minimum dose within a pallet converge.',
    bullets: [
      'Dose is proportional to residence time — conveyor speed is the primary process control.',
      'Multiple passes and product rotation shrink the dose uniformity ratio.',
      'Product density is a commissioning parameter: a denser load self-shields more.',
      'A stalled conveyor triggers source lowering to avoid overdosing a stopped tote.',
      'Every batch is documented against a validated process per ISO 11137.',
    ],
    draw: t => {
      const f = saw(t, 0.25);
      return (
        <g>
          <rect x="118" y="40" width="22" height="70" rx="3" fill="#3f2a12" stroke="#f97316" strokeWidth="1.4" />
          {Array.from({ length: 8 }, (_, i) => {
            const a = (i / 8) * Math.PI * 2;
            return <line key={i} x1="129" y1="75" x2={129 + Math.cos(a) * 70} y2={75 + Math.sin(a) * 52} stroke="#fbbf24" strokeWidth="0.6" opacity="0.3" />;
          })}
          <rect x="20" y="122" width="220" height="6" rx="3" fill="#334155" />
          {Array.from({ length: 4 }, (_, i) => {
            const g = (f + i / 4) % 1;
            const x = 20 + g * 210;
            const dose = Math.max(0, 1 - Math.abs(x - 129) / 110);
            return (
              <g key={i}>
                <rect x={x} y="98" width="26" height="24" rx="2" fill="#111c2e" stroke="#64748b" strokeWidth="0.9" />
                <rect x={x + 2} y={120 - dose * 20} width="22" height={dose * 20} fill="#fbbf24" opacity="0.4" />
              </g>
            );
          })}
          {L(10, 20, 'PRODUCT CONVEYOR', '#cbd5e1', 8)}
          {L(10, 144, 'dose ∝ residence time near the rack', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ir-dosimetry', group: 'gamma-irradiators', tag: 'Process', hex: '#a78bfa',
    part: 'Alanine / Fricke dose mapping',
    summary: 'Dosimeters placed throughout a reference load establish where the minimum and maximum dose actually occur before routine processing is allowed.',
    bullets: [
      'Alanine dosimeters are read by electron paramagnetic resonance and cover 1 Gy to 100 kGy.',
      'Fricke chemical dosimetry is the classic reference for lower doses.',
      'Dose uniformity ratio = D_max / D_min; below about 1.5 is the industrial target.',
      'Routine monitoring dosimeters then verify each batch against the validated map.',
      'Traceability to a national standards laboratory is required for released product.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      return (
        <g>
          <rect x="60" y="42" width="140" height="90" rx="4" fill="#111c2e" stroke="#64748b" strokeWidth="1.3" />
          {Array.from({ length: 12 }, (_, i) => {
            const cx = 78 + (i % 4) * 40, cy = 60 + Math.floor(i / 4) * 30;
            const d = 0.35 + 0.65 * Math.abs(Math.sin(i * 1.3 + f * 6));
            return (
              <g key={i}>
                <circle cx={cx} cy={cy} r="9" fill="#a78bfa" opacity={0.2 + d * 0.6} stroke="#c4b5fd" strokeWidth="0.8" />
                <text x={cx} y={cy + 3} fontSize="6" fill="#e9d5ff" textAnchor="middle">{(20 + d * 12).toFixed(0)}</text>
              </g>
            );
          })}
          {L(60, 36, 'reference load — kGy per position', '#c4b5fd')}
          {L(10, 20, 'DOSE MAPPING', '#cbd5e1', 8)}
          {L(10, 146, 'DUR = D_max / D_min < 1.5', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ir-interlock', group: 'gamma-irradiators', tag: 'Safety', hex: '#f87171',
    part: 'Interlock chain & source position monitor',
    summary: 'Independent, redundant sensors confirm both that the cell is empty and that the source is where the control system believes it is.',
    bullets: [
      'Search-and-secure: a physical walk-through with sequenced buttons that must be pressed in order and in time.',
      'Two independent source-position signals — losing one alone is a fault, not a licence to continue.',
      'Area monitors at every exit are wired to the interlock, not just to a display.',
      'Loss of power lowers the rack by gravity; there is no powered-safe state to fail.',
      'Interlock testing is a documented periodic requirement (IAEA TECDOC-1313).',
    ],
    draw: t => {
      const f = saw(t, 0.25);
      const stage = Math.floor(f * 4);
      const names = ['door closed', 'cell searched', 'monitors clear', 'RAISE ENABLED'];
      return (
        <g>
          {names.map((n, i) => (
            <g key={i}>
              <rect x="50" y={38 + i * 26} width="140" height="20" rx="4" fill="#0b1220" stroke={i <= stage ? '#4ade80' : '#334155'} strokeWidth="1.2" />
              <text x="60" y={52 + i * 26} fontSize="7.5" fill={i <= stage ? '#86efac' : '#475569'}>{n}</text>
              <circle cx="180" cy={48 + i * 26} r="4" fill={i <= stage ? '#4ade80' : '#1f2937'} />
            </g>
          ))}
          {L(200, 80, stage === 3 ? '☢' : '●', stage === 3 ? '#f87171' : '#4ade80', 14)}
          {L(10, 20, 'INTERLOCK CHAIN', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ir-maze', group: 'gamma-irradiators', tag: 'Shielding', hex: '#94a3b8',
    part: 'Labyrinth entrance',
    summary: 'A maze replaces a heavy shielded door: radiation must scatter around several corners to reach the entrance, losing energy every time.',
    bullets: [
      'Each 90° scatter costs roughly an order of magnitude in dose rate.',
      'Product enters through the same maze on the conveyor, so no door has to open during operation.',
      'Maze length and leg count are set by shielding calculation, not by architecture.',
      'The end of the maze still needs a monitored barrier and access control.',
      'Skyshine — scatter off the air above the cell — is a separate calculation for large plants.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      const pts = [[40, 120], [40, 60], [110, 60], [110, 118], [186, 118], [186, 50]];
      const seg = Math.min(4, Math.floor(f * 5));
      const p0 = pts[seg], p1 = pts[seg + 1] || pts[seg];
      const lf = (f * 5) % 1;
      return (
        <g>
          <polyline points={pts.map(p => p.join(',')).join(' ')} fill="none" stroke="#334155" strokeWidth="16" />
          <polyline points={pts.map(p => p.join(',')).join(' ')} fill="none" stroke="#475569" strokeWidth="1" strokeDasharray="3 3" />
          <circle cx="196" cy="44" r="7" fill="#f97316" />
          {L(178, 32, 'source cell', '#fdba74')}
          <circle cx={p0[0] + (p1[0] - p0[0]) * lf} cy={p0[1] + (p1[1] - p0[1]) * lf} r={4 - seg * 0.7} fill="#fbbf24" opacity={1 - seg * 0.2} />
          {L(20, 138, 'entrance — background', '#4ade80')}
          {L(10, 20, 'LABYRINTH', '#cbd5e1', 8)}
        </g>
      );
    },
  },
];

// ─── INDUSTRIAL RADIOGRAPHY ───────────────────────────────────────────────────
export const INDUSTRIAL_PARTS: MicroAnim[] = [
  {
    id: 'ix-head', group: 'industrial-xray', tag: 'Source', hex: '#38bdf8',
    part: 'Directional vs panoramic tube head',
    summary: 'A directional head emits a cone through a window; a panoramic (360°) head exposes an entire circumferential weld from inside the pipe in one shot.',
    bullets: [
      'Panoramic exposure of a girth weld replaces many single-wall shots — a big productivity gain.',
      'Directional heads give better contrast per exposure because less scatter is generated.',
      'Rod-anode tubes reach inside small-bore pipe where a normal head will not fit.',
      'Output falls with the square of distance, so head placement dominates exposure time.',
      'Head cooling limits duty cycle: continuous panoramic work needs forced cooling.',
    ],
    draw: t => {
      const pan = saw(t, 0.15) > 0.5;
      return (
        <g>
          <circle cx="130" cy="80" r="52" fill="none" stroke="#475569" strokeWidth="9" />
          <circle cx="130" cy="80" r="52" fill="none" stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" />
          <rect x="120" y="70" width="20" height="20" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.2" />
          {pan
            ? Array.from({ length: 16 }, (_, i) => {
              const a = (i / 16) * Math.PI * 2;
              return <line key={i} x1="130" y1="80" x2={130 + Math.cos(a) * 52} y2={80 + Math.sin(a) * 52} stroke="#fde047" strokeWidth="1" opacity="0.5" />;
            })
            : <polygon points="130,80 182,54 182,106" fill="#fde047" fillOpacity="0.22" />}
          {L(10, 20, pan ? 'PANORAMIC 360°' : 'DIRECTIONAL CONE', '#cbd5e1', 8)}
          {L(10, 144, pan ? 'whole girth weld in one exposure' : 'single-wall single-image technique', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ix-crawler', group: 'industrial-xray', tag: 'Deployment', hex: '#a78bfa',
    part: 'Pipeline crawler',
    summary: 'A battery-powered crawler drives the tube head inside the pipeline and is positioned at each weld by an external isotope marker.',
    bullets: [
      'Positioning uses a low-activity gamma marker outside the pipe that the crawler detects and stops on.',
      'One crawler run can radiograph dozens of welds without breaking into the line.',
      'Battery capacity and exposure time per weld set the achievable production rate.',
      'A stalled crawler with a live tube is a controlled-area emergency and has a defined recovery procedure.',
      'Exposure control is by command link; interlocks prevent firing while the crawler is moving.',
    ],
    draw: t => {
      const f = saw(t, 0.2);
      const stop = f > 0.55 && f < 0.8;
      const x = stop ? 138 : 30 + f * 200;
      return (
        <g>
          <rect x="10" y="52" width="240" height="56" rx="6" fill="#0b1220" stroke="#475569" strokeWidth="1.4" />
          <line x1="10" y1="60" x2="250" y2="60" stroke="#334155" strokeWidth="3" />
          <line x1="10" y1="100" x2="250" y2="100" stroke="#334155" strokeWidth="3" />
          <line x1="150" y1="46" x2="150" y2="114" stroke="#f59e0b" strokeWidth="1.6" strokeDasharray="3 2" />
          {L(156, 44, 'weld', '#fbbf24')}
          <rect x={x} y="70" width="30" height="20" rx="4" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.3" />
          <circle cx={x + 6} cy="92" r="3.5" fill="#64748b" />
          <circle cx={x + 24} cy="92" r="3.5" fill="#64748b" />
          {stop && <polygon points={`${x + 30},80 ${x + 70},62 ${x + 70},98`} fill="#fde047" fillOpacity="0.25" />}
          {L(10, 20, 'PIPELINE CRAWLER', '#cbd5e1', 8)}
          {L(10, 136, stop ? 'positioned on marker — exposing' : 'travelling to next weld', stop ? '#fde047' : '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ix-iqi', group: 'industrial-xray', tag: 'Quality', hex: '#4ade80',
    part: 'Wire and hole-type IQIs',
    summary: 'The image quality indicator is the objective evidence that the technique could resolve a defect of a stated size — without it the radiograph is not acceptable.',
    bullets: [
      'Wire IQIs (EN 462-1, ASTM E747) present a graded series of wire diameters.',
      'Hole (plaque) IQIs used in ASME practice present 1T, 2T and 4T holes in a step of known thickness.',
      'The IQI goes on the source side of the object unless the code explicitly permits otherwise.',
      'Required sensitivity is set by the applicable code for the material thickness.',
      'IQI visibility is judged on the radiograph, not on the live monitor at full contrast stretch.',
    ],
    draw: t => {
      const f = saw(t, 0.25);
      const vis = Math.floor(f * 7);
      return (
        <g>
          <rect x="30" y="40" width="200" height="72" rx="4" fill="#0f172a" stroke="#334155" strokeWidth="1.3" />
          {Array.from({ length: 7 }, (_, i) => (
            <rect key={i} x={44 + i * 26} y="52" width={1.5 + i * 1.1} height="44" fill="#cbd5e1" opacity={i <= vis ? 0.95 : 0.1} />
          ))}
          {L(30, 126, `smallest visible: W${16 - vis}`, '#86efac')}
          {L(10, 20, 'IMAGE QUALITY INDICATOR', '#cbd5e1', 8)}
          {L(10, 142, 'no visible wire → invalid radiograph', '#f87171')}
        </g>
      );
    },
  },
  {
    id: 'ix-film', group: 'industrial-xray', tag: 'Detector', hex: '#94a3b8',
    part: 'Film cassette & lead intensifying screens',
    summary: 'Lead foil screens in direct contact with the film emit photoelectrons that expose the emulsion and simultaneously absorb soft scattered radiation.',
    bullets: [
      'Front screen typically 0.02–0.15 mm lead; the back screen also stops backscatter.',
      'Intensification shortens exposure while improving contrast by removing scatter.',
      'Poor screen-to-film contact produces a characteristic mottled unsharpness.',
      'Film class (EN ISO 11699 C4–C7) trades speed against graininess.',
      'A lead letter "B" on the cassette back checks that backscatter is adequately controlled.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      return (
        <g>
          <rect x="60" y="38" width="120" height="14" rx="2" fill="#334155" stroke="#94a3b8" strokeWidth="1" />
          {L(186, 48, 'Pb front', '#cbd5e1')}
          <rect x="60" y="54" width="120" height="42" rx="2" fill="#1f2937" stroke="#64748b" strokeWidth="1" />
          {L(186, 78, 'film', '#cbd5e1')}
          <rect x="60" y="98" width="120" height="14" rx="2" fill="#334155" stroke="#94a3b8" strokeWidth="1" />
          {L(186, 108, 'Pb back', '#cbd5e1')}
          {Array.from({ length: 4 }, (_, i) => {
            const g = (f + i / 4) % 1;
            return <circle key={i} cx={80 + i * 30} cy={10 + g * 34} r="2" fill="#fde047" opacity={g > 0.9 ? 0.2 : 1} />;
          })}
          {Array.from({ length: 4 }, (_, i) => (
            <line key={i} x1={80 + i * 30} y1="52" x2={80 + i * 30 + 5} y2="62" stroke="#60a5fa" strokeWidth="1.1" />
          ))}
          {L(10, 20, 'FILM + SCREENS', '#cbd5e1', 8)}
          {L(10, 132, 'photoelectrons intensify, screens absorb scatter', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ix-dda', group: 'industrial-xray', tag: 'Detector', hex: '#22c55e',
    part: 'Digital detector array (DDA)',
    summary: 'A scintillator converts X-rays to light and an amorphous-silicon TFT array reads the charge pixel by pixel — an image in seconds, with wide dynamic range.',
    bullets: [
      'CsI needles channel light and preserve resolution better than a GOS powder layer.',
      'Dynamic range of 10⁴ or more means one exposure can cover thick and thin sections.',
      'Bad-pixel maps and gain/offset calibration are part of routine detector qualification.',
      'Basic spatial resolution and SNR must be demonstrated per EN ISO 17636-2 before replacing film.',
      'Detectors degrade under cumulative dose — qualification is periodic, not one-off.',
    ],
    draw: t => {
      const f = saw(t, 0.35);
      return (
        <g>
          <rect x="40" y="36" width="180" height="16" rx="2" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.1" />
          {L(226, 48, 'CsI', '#fbbf24')}
          <rect x="40" y="54" width="180" height="62" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.3" />
          {Array.from({ length: 24 }, (_, i) => (
            <rect key={i} x={44 + (i % 8) * 22} y={58 + Math.floor(i / 8) * 19} width="19" height="16"
              fill="#22c55e" opacity={0.1 + 0.55 * Math.abs(Math.sin(f * 6 + i * 0.7))} />
          ))}
          {Array.from({ length: 5 }, (_, i) => (
            <circle key={i} cx={60 + i * 38} cy={10 + ((f + i / 5) % 1) * 24} r="2" fill="#fde047" />
          ))}
          {L(10, 20, 'a-Si TFT PANEL', '#cbd5e1', 8)}
          {L(10, 134, 'dynamic range > 10⁴  ·  ISO 17636-2 Class A/B', '#86efac')}
        </g>
      );
    },
  },
  {
    id: 'ix-ct', group: 'industrial-xray', tag: 'Detector', hex: '#a78bfa',
    part: 'Industrial CT — rotate, reconstruct, measure',
    summary: 'Rotating the part through hundreds of projections reconstructs a voxel volume that can be sectioned, measured and compared to the CAD model.',
    bullets: [
      'Cone-beam CT with a flat panel is standard for small to medium parts.',
      'Voxel size is set by magnification and focal spot — micro-focus tubes reach a few micrometres.',
      'Beam hardening artefacts are corrected in software or suppressed with pre-filtration.',
      'CT metrology can measure internal features no contact probe can reach.',
      'Reconstruction times and file sizes, not scanning, are usually the throughput bottleneck.',
    ],
    draw: t => {
      const a = t * 1.2;
      return (
        <g>
          <rect x="24" y="66" width="22" height="26" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.2" />
          <polygon points="46,79 210,40 210,118" fill="#fde047" fillOpacity="0.1" />
          <g transform={`rotate(${(a * 70) % 360} 128 79)`}>
            <rect x="112" y="62" width="32" height="34" rx="3" fill="#111c2e" stroke="#94a3b8" strokeWidth="1.2" />
            <circle cx="124" cy="76" r="5" fill="#0b1220" stroke="#f87171" strokeWidth="1" />
          </g>
          <rect x="210" y="40" width="12" height="78" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.3" />
          {L(112, 124, 'rotary stage', '#cbd5e1')}
          {L(10, 20, 'CONE-BEAM CT', '#cbd5e1', 8)}
          {L(10, 142, '360° projections → voxel volume', '#94a3b8')}
        </g>
      );
    },
  },
];

// ─── SECURITY SCREENING ───────────────────────────────────────────────────────
export const SECURITY_PARTS: MicroAnim[] = [
  {
    id: 'sc-array', group: 'security', tag: 'Imaging chain', hex: '#22c55e',
    part: 'L-shaped detector array & line scan',
    summary: 'A single fan beam crosses the tunnel onto an L-shaped diode array. The image is built one line at a time as the belt advances.',
    bullets: [
      'Line-scan geometry means the source and detector never move — mechanically simple and stable.',
      'Belt speed and line rate together fix the pixel size along the travel direction.',
      'Photodiode-plus-scintillator elements are typically 0.8–1.6 mm pitch.',
      'A dark/gain calibration runs at power-up and is repeated periodically.',
      'A dead detector element shows as a persistent line down the image — a daily-check item.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      return (
        <g>
          <rect x="34" y="34" width="190" height="80" rx="6" fill="#111c2e" stroke="#475569" strokeWidth="1.5" />
          <rect x="118" y="26" width="22" height="16" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.1" />
          <polygon points="129,42 44,114 214,114" fill="#fde047" fillOpacity="0.1" />
          <path d="M 44 114 L 129 42 L 214 114" fill="none" stroke="#22c55e" strokeWidth="1.4" strokeDasharray="3 2" />
          <rect x={34 + f * 170} y="86" width="34" height="24" rx="3" fill="#0b1220" stroke="#94a3b8" strokeWidth="1" />
          <rect x="30" y="122" width="200" height="5" rx="2" fill="#334155" />
          {L(10, 20, 'LINE-SCAN GEOMETRY', '#cbd5e1', 8)}
          {L(10, 142, 'one detector line per belt step', '#86efac')}
        </g>
      );
    },
  },
  {
    id: 'sc-curtain', group: 'security', tag: 'Safety', hex: '#94a3b8',
    part: 'Lead curtains & leakage control',
    summary: 'Overlapping lead-rubber strips at both tunnel ends let bags through while keeping the scattered radiation inside the enclosure.',
    bullets: [
      'Leakage limit at 5 cm from any accessible surface is typically 1 µSv/h (IEC 62463).',
      'Missing or torn curtain strips are the most common cause of a failed radiation survey.',
      'Curtains are consumables — inspect them at every routine service.',
      'Interlocks stop the beam if an access panel is opened, but curtains have no interlock: inspection is the control.',
      'Operators should never reach into the tunnel; retrieval procedures require the beam disabled.',
    ],
    draw: t => {
      const f = saw(t, 0.35);
      const pushing = f > 0.35 && f < 0.62;
      return (
        <g>
          <rect x="60" y="42" width="140" height="70" rx="6" fill="#111c2e" stroke="#475569" strokeWidth="1.5" />
          {Array.from({ length: 6 }, (_, i) => (
            <rect key={i} x={62 + i * 9} y="46" width="8" height={pushing ? 44 : 62} rx="2" fill="#1f2937" stroke="#94a3b8" strokeWidth="0.7" />
          ))}
          {Array.from({ length: 6 }, (_, i) => (
            <rect key={i} x={132 + i * 9} y="46" width="8" height="62" rx="2" fill="#1f2937" stroke="#94a3b8" strokeWidth="0.7" />
          ))}
          <rect x={20 + f * 120} y="80" width="34" height="24" rx="3" fill="#0b1220" stroke="#64748b" strokeWidth="1" />
          {L(10, 20, 'LEAD CURTAINS', '#cbd5e1', 8)}
          {L(10, 136, '< 1 µSv/h at 5 cm from the surface', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'sc-dual', group: 'security', tag: 'Imaging chain', hex: '#f97316',
    part: 'Sandwich detector — dual energy in one pass',
    summary: 'A front detector records the low-energy signal, a copper filter hardens what passes, and a rear detector records the high-energy signal — two spectra, one exposure.',
    bullets: [
      'The front layer absorbs preferentially at low energy; the filter removes what is left of the soft beam.',
      'The ratio of the two signals maps to effective atomic number.',
      'No dual-source or fast kV switching is needed — mechanically simple and inherently registered.',
      'Colour convention: orange for organic, green for light inorganic, blue for metal, black for opaque.',
      'Thick metal saturates the discrimination — the console flags it rather than guessing.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      const z = 6 + Math.floor(f * 4) * 8;
      const col = z < 10 ? '#f97316' : z < 20 ? '#4ade80' : '#38bdf8';
      return (
        <g>
          <polygon points="20,80 70,60 70,100" fill="#fde047" fillOpacity="0.25" />
          <rect x="76" y="52" width="16" height="56" rx="2" fill={col} fillOpacity="0.35" stroke={col} strokeWidth="1.2" />
          {L(70, 128, `object Z≈${z}`, col)}
          <rect x="128" y="46" width="8" height="68" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(120, 40, 'low-E', '#86efac')}
          <rect x="140" y="46" width="8" height="68" rx="2" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          {L(144, 128, 'Cu filter', '#fdba74')}
          <rect x="152" y="46" width="8" height="68" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(166, 40, 'high-E', '#86efac')}
          <rect x="180" y="60" width="56" height="10" rx="4" fill="#0b1220" stroke="#334155" />
          <rect x="181" y="61" width={54 * Math.max(0.1, 1 - z / 40)} height="8" rx="4" fill={col} />
          {L(180, 84, 'HE/LE ratio → Zeff', '#94a3b8')}
          {L(10, 20, 'SANDWICH DETECTOR', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'sc-ct', group: 'security', tag: 'Imaging chain', hex: '#4ade80',
    part: 'Slip-ring CT gantry',
    summary: 'Source and detector rotate continuously on a slip ring while the bag translates, producing a helical scan and a full 3-D reconstruction.',
    bullets: [
      'Slip rings remove cable wrap, allowing continuous rotation at 2–4 revolutions per second.',
      'Helical pitch and belt speed together determine slice quality and throughput.',
      'Reconstruction gives a CT number per voxel — a measured property, not a shadow.',
      'Explosive detection algorithms alarm on density and Zeff signatures, then present the alarm to the operator.',
      'ECAC Standard 3 and TSA certification define detection and false-alarm performance.',
    ],
    draw: t => {
      const a = t * 2;
      return (
        <g>
          <circle cx="130" cy="76" r="54" fill="none" stroke="#334155" strokeWidth="12" />
          <g transform={`rotate(${(a * 60) % 360} 130 76)`}>
            <rect x="122" y="14" width="16" height="12" rx="2" fill="#14301c" stroke="#22c55e" strokeWidth="1" />
            <path d="M 130 26 L 104 130 L 156 130 Z" fill="#fde047" fillOpacity="0.13" />
            <rect x="100" y="126" width="60" height="8" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1" />
          </g>
          <rect x="112" y="64" width="34" height="26" rx="3" fill="#0b1220" stroke="#94a3b8" strokeWidth="1" />
          <rect x="120" y="72" width="12" height="11" rx="2" fill="#f97316" fillOpacity="0.7" />
          {L(10, 20, 'SLIP-RING CT', '#cbd5e1', 8)}
          {L(10, 146, 'helical scan → volumetric EDS', '#86efac')}
        </g>
      );
    },
  },
  {
    id: 'sc-backscatter', group: 'security', tag: 'Modality', hex: '#a78bfa',
    part: 'Backscatter imaging',
    summary: 'A pencil beam sweeps across the target and large detectors on the same side collect Compton-scattered photons — organic material scatters strongly and appears bright.',
    bullets: [
      'Single-sided access: ideal for vehicles, walls and containers you cannot get behind.',
      'Organic materials (explosives, drugs, people) scatter much more than steel of the same mass.',
      'Effective dose per personnel scan is around 0.05–0.1 µSv — minutes of natural background.',
      'Depth information is poor compared with transmission imaging; it is a surface-layer technique.',
      'Privacy-preserving automated target recognition replaced raw body images in most jurisdictions.',
    ],
    draw: t => {
      const f = saw(t, 0.35);
      const y = 40 + f * 76;
      return (
        <g>
          <rect x="30" y="34" width="26" height="90" rx="4" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.3" />
          {L(26, 28, 'chopper', '#d8b4fe')}
          <line x1="56" y1={y} x2="170" y2={y} stroke="#fde047" strokeWidth="1.6" />
          <rect x="170" y="40" width="34" height="76" rx="6" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          {L(166, 132, 'organic target', '#fdba74')}
          {Array.from({ length: 5 }, (_, i) => (
            <line key={i} x1="170" y1={y} x2={170 - 100} y2={y + (i - 2) * 26} stroke="#a78bfa" strokeWidth="0.9" opacity="0.55" />
          ))}
          <rect x="60" y="34" width="8" height="90" rx="2" fill="#0b1220" stroke="#a855f7" strokeWidth="1.1" />
          {L(10, 20, 'BACKSCATTER', '#cbd5e1', 8)}
          {L(10, 144, 'same-side detection · surface sensitive', '#c4b5fd')}
        </g>
      );
    },
  },
  {
    id: 'sc-rpm', group: 'security', tag: 'Modality', hex: '#38bdf8',
    part: 'Radiation portal monitor (passive)',
    summary: 'Large plastic scintillator panels watch for gamma and neutron emission from a passing vehicle — a passive system that emits nothing itself.',
    bullets: [
      'Alarm is on count rate above a rolling background, so background suppression by a dense load matters.',
      'Neutron channel (He-3 or B-10) targets special nuclear material specifically.',
      'Plastic scintillator is cheap and large but has no spectroscopy — hence secondary inspection with a handheld identifier.',
      'Naturally occurring radioactive material (fertiliser, ceramics, bananas) causes most alarms.',
      'Performance requirements are defined in ANSI N42.35 and N42.38.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      const alarm = f > 0.45 && f < 0.65;
      return (
        <g>
          <rect x="40" y="34" width="26" height="94" rx="4" fill="#0b1220" stroke={alarm ? '#f87171' : '#38bdf8'} strokeWidth="1.5" />
          <rect x="194" y="34" width="26" height="94" rx="4" fill="#0b1220" stroke={alarm ? '#f87171' : '#38bdf8'} strokeWidth="1.5" />
          <rect x={70 + f * 90} y="76" width="60" height="34" rx="4" fill="#111c2e" stroke="#94a3b8" strokeWidth="1.1" />
          <circle cx={100 + f * 90} cy="93" r="5" fill={alarm ? '#f97316' : '#334155'} />
          <polyline points={Array.from({ length: 40 }, (_, i) => {
            const x = 40 + i * 4.6;
            const spike = alarm && i > 16 && i < 26 ? -20 * Math.exp(-Math.abs(i - 21) / 3) : -2 * Math.abs(Math.sin(i));
            return `${x},${150 + spike}`;
          }).join(' ')} fill="none" stroke={alarm ? '#f87171' : '#4ade80'} strokeWidth="1.3" />
          {L(10, 20, 'PORTAL MONITOR', '#cbd5e1', 8)}
          {L(84, 30, alarm ? 'ALARM — secondary inspection' : 'background', alarm ? '#f87171' : '#86efac')}
        </g>
      );
    },
  },
  {
    id: 'sc-operator', group: 'security', tag: 'Human factors', hex: '#fde047',
    part: 'Operator workstation & threat image projection',
    summary: 'Fictional threat images are injected into the real stream at a controlled rate, measuring and maintaining detection performance during live screening.',
    bullets: [
      'Detection performance drops measurably after roughly 20 minutes of continuous image review.',
      'Rotation intervals and break scheduling are regulated, not left to local discretion.',
      'TIP data feeds recurrent training: individual weak categories can be targeted.',
      'Image enhancement tools (organic strip, inorganic strip, edge enhance) are part of trained procedure.',
      'The console is a decision aid — the machine flags, the human decides and documents.',
    ],
    draw: t => {
      const f = saw(t, 0.25);
      const tip = f > 0.6 && f < 0.78;
      return (
        <g>
          <rect x="34" y="34" width="192" height="80" rx="5" fill="#0b1220" stroke="#475569" strokeWidth="1.4" />
          <rect x="42" y="42" width="176" height="64" rx="3" fill="#111c2e" />
          <rect x={60 + f * 60} y="56" width="46" height="34" rx="3" fill="#f97316" fillOpacity="0.35" stroke="#f97316" strokeWidth="1" />
          <rect x={130 + f * 30} y="62" width="26" height="22" rx="2" fill="#38bdf8" fillOpacity="0.4" stroke="#38bdf8" strokeWidth="1" />
          {tip && <rect x="150" y="52" width="34" height="24" rx="2" fill="#ef4444" fillOpacity="0.35" stroke="#f87171" strokeWidth="1.3" />}
          {tip && L(150, 48, 'TIP', '#f87171')}
          <rect x="34" y="120" width="192" height="14" rx="3" fill="#0b1220" stroke="#334155" />
          {L(42, 130, `shift time ${Math.round(f * 30)} min`, f > 0.66 ? '#f87171' : '#86efac')}
          {L(10, 20, 'OPERATOR CONSOLE', '#cbd5e1', 8)}
        </g>
      );
    },
  },
];

export const NUCLEAR_PART_ANIMS: MicroAnim[] = [
  ...ISOTOPE_PARTS, ...NEUTRON_PARTS, ...IRRADIATOR_PARTS, ...INDUSTRIAL_PARTS, ...SECURITY_PARTS,
];
