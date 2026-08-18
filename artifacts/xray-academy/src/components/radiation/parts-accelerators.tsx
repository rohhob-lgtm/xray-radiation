import type { MicroAnim } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Part-by-part micro animations — X-ray tube, LINAC, betatron, cyclotron,
// synchrotron and Van de Graaff. Each draws inside a 260 × 150 viewBox.
// ═══════════════════════════════════════════════════════════════════════════════

const saw = (t: number, hz = 1) => (t * hz) % 1;
const osc = (t: number, hz = 1) => Math.sin(t * Math.PI * 2 * hz);
const L = (x: number, y: number, s: string, c = '#94a3b8', size = 7, a: 'start' | 'middle' | 'end' = 'start') => (
  <text x={x} y={y} fontSize={size} fill={c} textAnchor={a}>{s}</text>
);

// ─── X-RAY TUBE ───────────────────────────────────────────────────────────────
export const XRAY_TUBE_PARTS: MicroAnim[] = [
  {
    id: 'xt-filament', group: 'xray-tube', tag: 'Cathode assembly', hex: '#f59e0b',
    part: 'Tungsten filament — thermionic emission',
    summary: 'A coiled tungsten wire heated to roughly 2 400 K boils electrons off its surface. Filament current sets tube current; it is the mA knob, not the kV knob.',
    bullets: [
      'Richardson–Dushman: <code>J = A·T²·e^(−φ/kT)</code>, tungsten work function φ ≈ 4.5 eV.',
      'Heater supply is typically 8–12 V at 3–5 A through an isolation transformer at cathode potential.',
      'Small changes in filament temperature produce large mA changes — hence closed-loop mA feedback.',
      'Life-limiting mechanism is tungsten evaporation; typical filament life is 500–2 000 exposure hours.',
      'Standby preheat below emission temperature shortens exposure delay without consuming filament life.',
    ],
    draw: t => {
      const heat = 0.55 + 0.45 * Math.abs(osc(t, 0.3));
      const cloud = Array.from({ length: 12 }, (_, i) => {
        const a = (i / 12) * Math.PI * 2 + t * 1.4;
        return { x: 130 + Math.cos(a) * (26 + 8 * osc(t + i, 0.7)), y: 78 + Math.sin(a) * (16 + 4 * osc(t + i, 0.5)) };
      });
      return (
        <g>
          <circle cx="86" cy="78" r={34 * heat} fill="url(#fp-hot)" opacity={0.55} />
          {[0, 1, 2, 3, 4, 5].map(i => (
            <ellipse key={i} cx="86" cy={54 + i * 10} rx="15" ry="4" fill="none"
              stroke={`rgb(${Math.round(200 + 55 * heat)},${Math.round(110 + 80 * heat)},40)`} strokeWidth={1.4 + heat} />
          ))}
          {cloud.map((c, i) => <circle key={i} cx={c.x} cy={c.y} r="1.8" fill="#60a5fa" opacity="0.85" />)}
          <line x1="52" y1="54" x2="30" y2="54" stroke="#ef4444" strokeWidth="1.5" />
          <line x1="52" y1="104" x2="30" y2="104" stroke="#ef4444" strokeWidth="1.5" />
          {L(10, 122, '8–12 V / 3–5 A', '#fbbf24')}
          {L(150, 40, `T ≈ ${Math.round(2100 + 400 * heat)} K`, '#f87171')}
          {L(150, 54, 'e⁻ cloud (space charge)', '#60a5fa')}
          {L(10, 20, 'THERMIONIC EMISSION', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-focus-cup', group: 'xray-tube', tag: 'Cathode assembly', hex: '#60a5fa',
    part: 'Focusing cup (Wehnelt electrode)',
    summary: 'A negatively biased metal cup surrounding the filament forms an electrostatic lens that compresses the diverging electron cloud into a small rectangular focal spot.',
    bullets: [
      'Without the cup, mutual repulsion would spread the beam over the whole anode face.',
      'Bias of −100 to −4 000 V relative to the filament; deep bias can cut the beam off entirely.',
      'Grid-controlled (grid-switched) tubes use this to switch exposures in microseconds — the basis of pulsed fluoroscopy.',
      'Dual-filament cathodes give a fine focus (≈0.3 mm) and a broad focus (≈1.2 mm) in one insert.',
      'Focal spot size is verified with a star or slit pattern per IEC 60336.',
    ],
    draw: t => {
      const k = saw(t, 0.5);
      return (
        <g>
          <path d="M 26 40 L 70 56 L 70 100 L 26 116 Z" fill="#0b1b34" stroke="#3b82f6" strokeWidth="1.5" />
          {[0, 1, 2, 3].map(i => <ellipse key={i} cx="44" cy={62 + i * 10} rx="9" ry="3" fill="none" stroke="#f59e0b" strokeWidth="1.2" />)}
          {L(20, 34, '−bias', '#93c5fd')}
          {Array.from({ length: 7 }, (_, i) => {
            const ph = (k + i / 7) % 1;
            const spread = (1 - ph) * 22;
            const y0 = 78 + (i - 3) * 7;
            const y = 78 + (y0 - 78) * (1 - ph * 0.86);
            return <circle key={i} cx={70 + ph * 130} cy={y} r="2" fill="#60a5fa" opacity={0.9} />;
          })}
          <path d="M 70 56 Q 140 70 200 74" fill="none" stroke="#1d4ed8" strokeWidth="0.8" strokeDasharray="3 2" />
          <path d="M 70 100 Q 140 86 200 82" fill="none" stroke="#1d4ed8" strokeWidth="0.8" strokeDasharray="3 2" />
          <rect x="200" y="52" width="26" height="52" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.5" />
          <rect x="198" y="72" width="5" height="12" fill="#fca5a5" />
          {L(196, 122, 'focal spot 0.3–1.2 mm', '#86efac')}
          {L(10, 20, 'ELECTROSTATIC FOCUSING', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-anode-disc', group: 'xray-tube', tag: 'Anode assembly', hex: '#22c55e',
    part: 'Rotating anode disc & focal track',
    summary: 'Spinning the target turns a single burning spot into a long circular track, spreading the thermal load over hundreds of times more material.',
    bullets: [
      'Disc is typically rhenium-alloyed tungsten brazed to a molybdenum (or graphite-backed) substrate.',
      'Speeds: 3 000 RPM for routine work, 9 000–10 800 RPM for high-power CT and angiography.',
      'Focal track temperature reaches ~2 600 °C during exposure while the bulk disc stays far cooler.',
      'Heat leaves the disc almost entirely by radiation to the oil-cooled housing — vacuum blocks conduction.',
      'Track pitting from thermal overload shows up as progressive output loss and image mottle.',
    ],
    draw: t => {
      const a = t * 6;
      return (
        <g>
          <ellipse cx="120" cy="80" rx="86" ry="34" fill="#1f2937" stroke="#6b7280" strokeWidth="1.5" />
          <ellipse cx="120" cy="80" rx="62" ry="24" fill="none" stroke="#9ca3af" strokeWidth="1" strokeDasharray="4 3" />
          {Array.from({ length: 14 }, (_, i) => {
            const ang = a + (i / 14) * Math.PI * 2;
            return <circle key={i} cx={120 + Math.cos(ang) * 74} cy={80 + Math.sin(ang) * 29} r="1.6" fill="#4b5563" />;
          })}
          <ellipse cx={120 + Math.cos(a) * 74} cy={80 + Math.sin(a) * 29} rx="11" ry="5.5" fill="#fca5a5" opacity="0.9" />
          <ellipse cx={120 + Math.cos(a) * 74} cy={80 + Math.sin(a) * 29} rx="20" ry="10" fill="#f87171" opacity="0.18" />
          <ellipse cx="120" cy="80" rx="10" ry="5" fill="#374151" stroke="#9ca3af" />
          {L(10, 20, 'ROTATING ANODE', '#cbd5e1', 8)}
          {L(10, 132, `${Math.round(3000 + 0 * a)}–10 800 RPM · focal track`, '#9ca3af')}
          {L(206, 44, '~2 600 °C', '#f87171')}
        </g>
      );
    },
  },
  {
    id: 'xt-heel', group: 'xray-tube', tag: 'Anode assembly', hex: '#a78bfa',
    part: 'Anode bevel, line focus & heel effect',
    summary: 'Tilting the target face makes the projected (effective) focal spot much smaller than the heated area — at the cost of intensity falling off toward the anode side.',
    bullets: [
      'Line-focus principle: <code>effective spot = actual spot × sin θ</code>, with θ typically 7°–20°.',
      'A 7° anode gives a sharper image but a smaller usable field at a given distance.',
      'Heel effect: photons emitted toward the anode side traverse more target material and are attenuated.',
      'Intensity can drop 20–45 % across the field — place the thicker part of the object on the cathode side.',
      'The effect grows with smaller anode angle, larger field size and shorter source-to-image distance.',
    ],
    draw: t => {
      const sweep = 0.5 + 0.5 * osc(t, 0.25);
      return (
        <g>
          <polygon points="60,40 110,58 110,102 60,120" fill="#4b5563" stroke="#9ca3af" strokeWidth="1" />
          {L(48, 34, 'target', '#cbd5e1')}
          <rect x="56" y="70" width="6" height="16" fill="#fca5a5" />
          {L(6, 84, 'actual', '#fca5a5')}
          <line x1="62" y1="78" x2="230" y2="40" stroke="#fde047" strokeWidth="1" opacity="0.35" />
          <line x1="62" y1="78" x2="230" y2="126" stroke="#fde047" strokeWidth="1" opacity="0.9" />
          <polygon points="62,78 230,40 230,126" fill="#fde047" fillOpacity="0.1" />
          {Array.from({ length: 9 }, (_, i) => {
            const f = i / 8;
            const h = 6 + 22 * f;   // anode side weaker (top)
            return <rect key={i} x={232} y={40 + f * 78} width={h} height="6" fill="#fde047" opacity="0.65" />;
          })}
          {L(196, 32, 'anode side', '#f87171')}
          {L(196, 140, 'cathode side', '#4ade80')}
          {L(10, 20, 'LINE FOCUS + HEEL EFFECT', '#cbd5e1', 8)}
          {L(120, 96, `θ = ${(7 + 13 * sweep).toFixed(0)}°`, '#a78bfa')}
        </g>
      );
    },
  },
  {
    id: 'xt-stator', group: 'xray-tube', tag: 'Anode assembly', hex: '#38bdf8',
    part: 'Stator, rotor and anode bearings',
    summary: 'The anode is spun by an induction motor whose stator sits outside the vacuum envelope, coupling magnetically to a copper rotor on the anode stem.',
    bullets: [
      'No electrical feed-through crosses the vacuum — the rotating field passes straight through the glass or ceramic.',
      'Ball bearings run dry with a silver or lead lamellar film; conventional lubricants would evaporate.',
      'Spiral-groove liquid-metal (gallium alloy) bearings allow continuous high-speed rotation and better heat conduction.',
      'A rotor brake or dynamic braking stops the disc between series to limit bearing wear.',
      'Rising bearing noise, longer run-up time or a rotation fault interlock are classic end-of-life symptoms.',
    ],
    draw: t => {
      const a = t * 8;
      return (
        <g>
          <rect x="30" y="46" width="24" height="68" rx="4" fill="#1e293b" stroke="#38bdf8" strokeWidth="1.5" />
          <rect x="206" y="46" width="24" height="68" rx="4" fill="#1e293b" stroke="#38bdf8" strokeWidth="1.5" />
          {L(24, 40, 'STATOR', '#7dd3fc')}
          {Array.from({ length: 4 }, (_, i) => (
            <ellipse key={i} cx="130" cy="80" rx={56 + i * 8} ry={34 + i * 5} fill="none" stroke="#38bdf8"
              strokeWidth="0.8" opacity={0.5 - i * 0.1} strokeDasharray="4 4"
              transform={`rotate(${(a * 12) % 360} 130 80)`} />
          ))}
          <g transform={`rotate(${(a * 40) % 360} 130 80)`}>
            <rect x="106" y="62" width="48" height="36" rx="5" fill="#7c2d12" stroke="#f97316" strokeWidth="1.5" />
            <line x1="112" y1="62" x2="112" y2="98" stroke="#fdba74" strokeWidth="1" />
            <line x1="148" y1="62" x2="148" y2="98" stroke="#fdba74" strokeWidth="1" />
          </g>
          {L(104, 122, 'Cu rotor + bearings', '#fdba74')}
          {L(10, 20, 'INDUCTION DRIVE', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-window', group: 'xray-tube', tag: 'Beam exit', hex: '#fbbf24',
    part: 'Beryllium window & inherent filtration',
    summary: 'Photons leave through a thin low-Z window. Beryllium (Z = 4) passes soft X-rays that glass would absorb, which matters for mammography and XRF.',
    bullets: [
      'Inherent filtration = window + tube oil + housing port, expressed in mm of aluminium equivalent.',
      'Beryllium windows of 0.5–1 mm transmit below 10 keV; borosilicate glass ports cut off around 15–20 keV.',
      'Tungsten evaporated from the target slowly plates the window, hardening the beam and dropping output.',
      'IEC 60522 defines how inherent filtration is measured and declared.',
      'Be dust is toxic — a cracked window is a health-physics event, not just a vacuum failure.',
    ],
    draw: t => {
      const k = saw(t, 0.6);
      return (
        <g>
          <rect x="30" y="40" width="52" height="76" rx="4" fill="#14301c" stroke="#22c55e" strokeWidth="1.5" />
          {L(30, 34, 'anode / envelope', '#86efac')}
          <rect x="84" y="58" width="9" height="40" rx="2" fill="#0f172a" stroke="#f59e0b" strokeWidth="1.5" />
          {L(76, 128, 'Be 0.5–1 mm', '#fbbf24')}
          {Array.from({ length: 5 }, (_, i) => {
            const ph = (k + i / 5) % 1;
            const soft = i < 2;
            const x = 93 + ph * 130;
            return <circle key={i} cx={soft ? Math.min(x, 100) : x} cy={62 + i * 8} r="2.2"
              fill={soft ? '#f87171' : '#fde047'} opacity={soft ? 0.5 : 0.95} />;
          })}
          {L(150, 46, 'hard photons pass', '#fde047')}
          {L(150, 118, 'softest absorbed', '#f87171')}
          {L(10, 20, 'EXIT WINDOW', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-filter', group: 'xray-tube', tag: 'Beam exit', hex: '#fde047',
    part: 'Added filtration & beam hardening',
    summary: 'Aluminium, copper or rare-earth filters remove low-energy photons that could never reach the detector, raising the mean beam energy and cutting entrance dose.',
    bullets: [
      'Total filtration above 70 kV must be at least 2.5 mm Al equivalent for diagnostic units.',
      'Copper (0.1–0.3 mm) is common in paediatric and fluoroscopy protocols; erbium and rhodium are used in mammography.',
      'Hardening raises the half-value layer, so HVL is the practical acceptance test for filtration.',
      'Over-filtration wastes tube output and lowers subject contrast — it is a trade, not a free win.',
      'Industrial NDT uses copper or lead pre-filters mainly to suppress scatter and improve latitude.',
    ],
    draw: t => {
      const mm = 1.5 + 1.5 * (0.5 + 0.5 * osc(t, 0.2));
      const curve = (f: number, x0: number) => {
        const pts: string[] = [];
        for (let i = 0; i <= 40; i++) {
          const e = (i / 40) * 100;
          const v = Math.max(0, 100 - e) * (e < 2 ? 0 : Math.exp(-f * 55 / Math.pow(e, 2.3)));
          pts.push(`${x0 + (i / 40) * 150},${118 - v * 0.78}`);
        }
        return `M ${x0},118 L ${pts.join(' L ')} L ${x0 + 150},118 Z`;
      };
      return (
        <g>
          <rect x="34" y="52" width={7 + mm * 3} height="56" rx="2" fill="#334155" stroke="#94a3b8" strokeWidth="1" />
          {L(24, 44, `${mm.toFixed(1)} mm Al`, '#fbbf24')}
          <path d={curve(0, 84)} fill="#64748b" fillOpacity="0.15" stroke="#64748b" strokeWidth="1" strokeDasharray="3 2" />
          <path d={curve(mm, 84)} fill="#fde047" fillOpacity="0.22" stroke="#fde047" strokeWidth="1.3" />
          <line x1="84" y1="118" x2="240" y2="118" stroke="#334155" />
          {L(84, 130, '0', '#64748b')}
          {L(232, 130, 'kVp', '#64748b')}
          {L(120, 40, 'dashed = unfiltered', '#64748b')}
          {L(10, 20, 'BEAM HARDENING', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-collimator', group: 'xray-tube', tag: 'Beam exit', hex: '#94a3b8',
    part: 'Collimator, light field & shutters',
    summary: 'Lead shutters trim the useful beam to the region of interest. Everything outside that field is pure dose and scatter with no image value.',
    bullets: [
      'Two orthogonal pairs of lead blades give a rectangular field; a mirror projects a matching light field.',
      'Light/radiation field congruence must stay within 2 % of the source-to-image distance (IEC 60601-1-3).',
      'Positive beam limitation automatically restricts the field to the loaded cassette size.',
      'Reducing field size is the single most effective scatter-reduction measure available to the operator.',
      'Industrial systems use fixed cones or slit collimators matched to the detector geometry.',
    ],
    draw: t => {
      const open = 14 + 16 * (0.5 + 0.5 * osc(t, 0.22));
      return (
        <g>
          <rect x="118" y="26" width="24" height="18" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.2" />
          {L(148, 38, 'source', '#86efac')}
          <rect x={130 - open - 22} y="56" width="22" height="14" fill="#1c1917" stroke="#6b7280" strokeWidth="1" />
          <rect x={130 + open} y="56" width="22" height="14" fill="#1c1917" stroke="#6b7280" strokeWidth="1" />
          <rect x={130 - open - 22} y="76" width="22" height="14" fill="#1c1917" stroke="#6b7280" strokeWidth="1" />
          <rect x={130 + open} y="76" width="22" height="14" fill="#1c1917" stroke="#6b7280" strokeWidth="1" />
          <polygon points={`130,44 ${130 - open},56 ${130 - open * 2.1},134 ${130 + open * 2.1},134 ${130 + open},56`} fill="#fde047" fillOpacity="0.18" stroke="#fde047" strokeOpacity="0.4" />
          <line x1={130 - open * 2.1} y1="134" x2={130 + open * 2.1} y2="134" stroke="#fde047" strokeWidth="2" />
          {L(10, 20, 'COLLIMATION', '#cbd5e1', 8)}
          {L(10, 100, 'Pb blades', '#94a3b8')}
          {L(186, 128, `field ${(open * 4.2).toFixed(0)} mm`, '#fde047')}
        </g>
      );
    },
  },
  {
    id: 'xt-cooling', group: 'xray-tube', tag: 'Thermal management', hex: '#38bdf8',
    part: 'Oil bath, expansion bellows & heat exchanger',
    summary: 'Dielectric oil surrounds the insert, doing double duty as high-voltage insulation and as the path that carries anode heat out to a radiator or chiller.',
    bullets: [
      'Oil expands as it heats; a bellows or diaphragm takes up the volume and trips a thermal interlock at the limit.',
      'Air-cooled exchangers suffice for radiography; CT and cargo systems use pumped water-to-air or chilled loops.',
      'Housing cooling curves define the duty cycle — exceeding them triggers a wait state, not a failure.',
      'Oil degradation and moisture ingress cause arcing, one of the most common intermittent-fault causes.',
      'Never top up with the wrong oil grade: dielectric strength, not just viscosity, is the specification.',
    ],
    draw: t => {
      const flow = saw(t, 0.35);
      const heat = 0.5 + 0.5 * osc(t, 0.15);
      return (
        <g>
          <rect x="26" y="46" width="96" height="66" rx="10" fill="#0d1524" stroke="#475569" strokeWidth="1.5" />
          <rect x="42" y="62" width="64" height="34" rx="6" fill="#111c2e" stroke="#22c55e" strokeWidth="1" />
          {L(46, 40, 'housing + oil', '#94a3b8')}
          <ellipse cx="74" cy="79" rx={26 * heat} ry={14 * heat} fill="url(#fp-hot)" opacity="0.6" />
          <path d="M 122 62 L 176 62" stroke="#f87171" strokeWidth="2" />
          <path d="M 122 96 L 176 96" stroke="#38bdf8" strokeWidth="2" />
          <rect x="176" y="50" width="52" height="58" rx="4" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.5" />
          {Array.from({ length: 5 }, (_, i) => <line key={i} x1="180" y1={58 + i * 11} x2="224" y2={58 + i * 11} stroke="#38bdf8" strokeWidth="1" opacity="0.6" />)}
          {L(172, 124, 'heat exchanger', '#7dd3fc')}
          {[0, 1, 2].map(i => {
            const f = (flow + i / 3) % 1;
            return <circle key={i} cx={122 + f * 54} cy="62" r="2.2" fill="#f87171" />;
          })}
          {[0, 1, 2].map(i => {
            const f = (flow + i / 3) % 1;
            return <circle key={i} cx={176 - f * 54} cy="96" r="2.2" fill="#38bdf8" />;
          })}
          {L(10, 20, 'COOLING LOOP', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-hv', group: 'xray-tube', tag: 'Power', hex: '#ef4444',
    part: 'High-frequency generator & HV cables',
    summary: 'A modern generator rectifies mains, chops it above 40 kHz, steps it up and re-rectifies — producing near-constant potential with under one percent ripple.',
    bullets: [
      'High-frequency operation shrinks the transformer and makes very short, reproducible exposures possible.',
      'Older three-phase twelve-pulse units ripple around 3–4 %; single-phase self-rectified units ripple 100 %.',
      'Ripple matters because the low-kV part of each cycle contributes dose but little useful image signal.',
      'HV cables use graded insulation and a shielded ground braid; the connector wells need fresh dielectric grease.',
      'Corona in a dirty cable well shows up as intermittent kV faults long before an outright flashover.',
    ],
    draw: t => {
      const ph = t * 3;
      const pts = (ripple: number, y0: number, col: string) =>
        Array.from({ length: 70 }, (_, i) => {
          const x = 30 + (i / 69) * 200;
          const y = y0 - 16 + Math.abs(Math.sin(i * 0.35 + ph)) * ripple;
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');
      return (
        <g>
          <polyline points={pts(14, 62, '#f87171')} fill="none" stroke="#f87171" strokeWidth="1.2" />
          {L(30, 40, 'single-phase — 100 % ripple', '#f87171')}
          <polyline points={pts(2.2, 116, '#4ade80')} fill="none" stroke="#4ade80" strokeWidth="1.5" />
          {L(30, 94, 'high-frequency inverter — < 1 %', '#4ade80')}
          <line x1="30" y1="126" x2="230" y2="126" stroke="#334155" />
          {L(10, 20, 'GENERATOR RIPPLE', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-vacuum', group: 'xray-tube', tag: 'Envelope', hex: '#3b82f6',
    part: 'Vacuum envelope & getter',
    summary: 'Electrons must fly from cathode to anode without hitting gas molecules, so the insert is evacuated below 10⁻⁷ mbar and kept there by a getter material.',
    bullets: [
      'Residual gas causes ionisation, erratic tube current and eventually destructive arcing.',
      'Metal-ceramic envelopes tolerate higher power and shield better against off-focus radiation than glass.',
      'A getter (barium or zirconium alloy) chemically traps gas released by the hot anode over the tube life.',
      'Gassy tubes are conditioned by slow kV ramping — "seasoning" — after long storage.',
      'Loss of vacuum is terminal: the insert is replaced, never repaired in the field.',
    ],
    draw: t => {
      const k = saw(t, 0.35);
      return (
        <g>
          <rect x="26" y="42" width="204" height="72" rx="18" fill="#0d1524" stroke="#334155" strokeWidth="2" />
          <rect x="38" y="52" width="180" height="52" rx="12" fill="#080e1a" stroke="#1d4ed8" strokeWidth="1" strokeDasharray="5 4" />
          {L(44, 36, '< 10⁻⁷ mbar', '#3b82f6')}
          <circle cx={54 + k * 140} cy="78" r="2.6" fill="#60a5fa" />
          {Array.from({ length: 3 }, (_, i) => {
            const gx = 90 + i * 50 + osc(t + i, 0.4) * 8;
            const gy = 64 + i * 12 + osc(t + i, 0.3) * 6;
            return <circle key={i} cx={gx} cy={gy} r="2" fill="#f87171" opacity="0.55" />;
          })}
          {L(150, 120, 'residual gas → arcing', '#f87171')}
          <rect x="196" y="96" width="18" height="8" rx="2" fill="#334155" stroke="#94a3b8" />
          {L(184, 132, 'getter', '#94a3b8')}
          {L(10, 20, 'VACUUM ENVELOPE', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'xt-grid', group: 'xray-tube', tag: 'Control', hex: '#a78bfa',
    part: 'Grid switching & pulsed exposure',
    summary: 'Biasing the focusing cup strongly negative pinches the beam off completely, letting the tube be switched on and off in microseconds without touching the kV.',
    bullets: [
      'Grid-controlled tubes make pulsed fluoroscopy possible — dose scales directly with pulse rate.',
      'Switching at the grid avoids the ringing and overshoot of switching megavolt-class HV supplies.',
      'Typical cut-off bias is −2 000 to −4 000 V relative to the filament.',
      'Pulse widths from a few microseconds up; duty cycle is limited by anode heating, not by the grid.',
      'Cargo and cine systems use the same trick to freeze motion at high frame rates.',
    ],
    draw: t => {
      const on = saw(t, 1.2) < 0.45;
      return (
        <g>
          <rect x="26" y="44" width="46" height="62" rx="4" fill="#0b1b34" stroke={on ? '#3b82f6' : '#7f1d1d'} strokeWidth="1.5" />
          {L(22, 38, on ? 'grid open' : 'grid cut-off', on ? '#93c5fd' : '#f87171')}
          {on && Array.from({ length: 5 }, (_, i) => {
            const f = (saw(t, 2) + i / 5) % 1;
            return <circle key={i} cx={72 + f * 116} cy={75 + (i - 2) * 3} r="2.2" fill="#60a5fa" />;
          })}
          <rect x="188" y="52" width="24" height="46" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.5" />
          {on && <circle cx="200" cy="75" r="12" fill="url(#fp-glow)" />}
          {/* pulse train */}
          <polyline points={Array.from({ length: 60 }, (_, i) => {
            const x = 26 + i * 3.4;
            const hi = ((i / 60 * 4 + t * 1.2) % 1) < 0.45;
            return `${x},${hi ? 122 : 136}`;
          }).join(' ')} fill="none" stroke="#a78bfa" strokeWidth="1.3" />
          {L(10, 20, 'GRID SWITCHING', '#cbd5e1', 8)}
        </g>
      );
    },
  },
];

// ─── LINAC ────────────────────────────────────────────────────────────────────
export const LINAC_PARTS: MicroAnim[] = [
  {
    id: 'ln-gun', group: 'linac', tag: 'Injector', hex: '#a855f7',
    part: 'Electron gun (diode / triode)',
    summary: 'A heated cathode injects electrons at a few tens of keV into the first accelerating cell, timed to the RF pulse.',
    bullets: [
      'Diode guns run continuously during the pulse; triode guns add a grid for fast beam-current control.',
      'Injection energy is typically 10–50 keV — deliberately low so the buncher can capture the electrons.',
      'Gun current sets dose rate; gun timing relative to the RF pulse sets capture efficiency.',
      'The gun sits at the vacuum boundary and shares the accelerator ion-pump system.',
      'A failing gun shows as falling dose rate that the servo compensates for until it runs out of range.',
    ],
    draw: t => {
      const k = saw(t, 0.9);
      return (
        <g>
          <path d="M 34 50 L 72 66 L 72 94 L 34 110 Z" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.5" />
          {[0, 1, 2].map(i => <ellipse key={i} cx="48" cy={68 + i * 12} rx="8" ry="3" fill="none" stroke="#f59e0b" strokeWidth="1.2" />)}
          <circle cx="48" cy="80" r="18" fill="url(#fp-hot)" opacity="0.5" />
          {L(26, 40, 'cathode', '#d8b4fe')}
          {Array.from({ length: 6 }, (_, i) => {
            const f = (k + i / 6) % 1;
            return <circle key={i} cx={72 + f * 120} cy="80" r="2.4" fill="#818cf8" opacity={f > 0.94 ? 0 : 1} />;
          })}
          <rect x="192" y="62" width="38" height="36" rx="3" fill="#0b1b34" stroke="#3b82f6" strokeWidth="1.5" />
          {L(186, 118, 'first cell', '#93c5fd')}
          {L(10, 20, 'ELECTRON GUN', '#cbd5e1', 8)}
          {L(100, 118, '10–50 keV injection', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ln-buncher', group: 'linac', tag: 'Injector', hex: '#22d3ee',
    part: 'Buncher cavity — phase capture',
    summary: 'The first cells vary the electron velocity so that a continuous stream is compressed into discrete bunches sitting on the accelerating phase.',
    bullets: [
      'Slow electrons arriving early get a smaller kick, fast ones arriving late get a bigger one — the bunch self-compresses.',
      'Capture efficiency is typically 50–70 %; the rest is lost on the first few centimetres of copper.',
      'Bunch length ends up a few degrees of RF phase, which is what makes the output energy spectrum narrow.',
      'The buncher cells have a shorter period than the main structure because the beam is still sub-relativistic.',
      'Phase errors here propagate as an energy spread that the bending magnet then throws away.',
    ],
    draw: t => {
      const ph = t * 3;
      return (
        <g>
          <polyline points={Array.from({ length: 70 }, (_, i) => `${26 + i * 3},${58 - Math.sin(i * 0.28 - ph) * 16}`).join(' ')}
            fill="none" stroke="#22d3ee" strokeWidth="1.2" opacity="0.8" />
          {Array.from({ length: 14 }, (_, i) => {
            const f = (saw(t, 0.5) + i / 14) % 1;
            const squeeze = Math.pow(f, 0.6);
            const grouped = Math.round(f * 3) / 3;
            const x = 26 + (f * 0.35 + grouped * 0.6) * 200;
            return <circle key={i} cx={x} cy={100} r="2.2" fill="#818cf8" opacity={0.5 + squeeze * 0.5} />;
          })}
          {L(26, 128, 'continuous stream → RF bunches', '#94a3b8')}
          {L(10, 20, 'BUNCHER', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ln-cavity', group: 'linac', tag: 'Accelerating structure', hex: '#3b82f6',
    part: 'Standing-wave cavity & side coupling',
    summary: 'Copper cells resonate at 2 856 MHz. In a standing-wave design, side-coupled cavities carry power between accelerating cells so the beam sees a field everywhere it matters.',
    bullets: [
      'Standing-wave structures are roughly half the length of travelling-wave structures for the same energy.',
      'Travelling-wave designs need a matched RF load at the far end to absorb leftover power.',
      'Cells are machined to micrometre tolerance and brazed in a hydrogen furnace — the copper surface is the resonator.',
      'Accelerating gradient is typically 10–15 MeV per metre for medical machines.',
      'Automatic frequency control chases the cavity resonance as the copper thermally expands.',
    ],
    draw: t => {
      const ph = t * 5;
      return (
        <g>
          {Array.from({ length: 6 }, (_, i) => {
            const amp = Math.sin(ph + i * Math.PI);
            return (
              <g key={i}>
                <rect x={30 + i * 34} y="58" width="30" height="34" rx="4" fill="#0b1b34" stroke="#3b82f6" strokeWidth="1.2" />
                <rect x={32 + i * 34} y={75 - Math.abs(amp) * 15} width="26" height={Math.abs(amp) * 15} fill={amp > 0 ? '#38bdf8' : '#f472b6'} opacity="0.45" />
                {i < 5 && <rect x={54 + i * 34} y="98" width="16" height="14" rx="3" fill="#111c2e" stroke="#64748b" strokeWidth="1" />}
              </g>
            );
          })}
          {L(52, 126, 'side-coupling cells', '#64748b')}
          <circle cx={30 + saw(t, 0.5) * 204} cy="75" r="2.8" fill="#818cf8" />
          {L(10, 20, 'STANDING-WAVE STRUCTURE', '#cbd5e1', 8)}
          {L(10, 46, '2 856 MHz · 10–15 MeV/m', '#93c5fd')}
        </g>
      );
    },
  },
  {
    id: 'ln-magnetron', group: 'linac', tag: 'RF power', hex: '#a855f7',
    part: 'Magnetron — resonant cavity oscillator',
    summary: 'Electrons spiral from a central cathode toward an anode block of resonant cavities, forming rotating spokes that pump microwave power out of a coupling loop.',
    bullets: [
      'Peak power 2–5 MW pulsed, enough for machines up to about 10 MeV.',
      'Compact and inexpensive, but frequency drifts with temperature and load — hence automatic frequency control.',
      'The magnetron is an oscillator: it defines its own frequency rather than amplifying an input.',
      'Cathode life is the usual replacement driver; output falls slowly, then collapses.',
      'A circulator protects it from power reflected by a mismatched accelerating structure.',
    ],
    draw: t => {
      const a = t * 2.5;
      return (
        <g>
          <circle cx="98" cy="80" r="52" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.5" />
          {Array.from({ length: 8 }, (_, i) => {
            const ang = (i / 8) * Math.PI * 2;
            return <circle key={i} cx={98 + Math.cos(ang) * 38} cy={80 + Math.sin(ang) * 38} r="9" fill="#0b0416" stroke="#c084fc" strokeWidth="1" />;
          })}
          <circle cx="98" cy="80" r="9" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          {Array.from({ length: 4 }, (_, i) => {
            const ang = a + (i / 4) * Math.PI * 2;
            return <path key={i} d={`M ${98 + Math.cos(ang) * 12} ${80 + Math.sin(ang) * 12} Q ${98 + Math.cos(ang + 0.5) * 24} ${80 + Math.sin(ang + 0.5) * 24} ${98 + Math.cos(ang + 1) * 33} ${80 + Math.sin(ang + 1) * 33}`}
              fill="none" stroke="#60a5fa" strokeWidth="1.6" opacity="0.85" />;
          })}
          <rect x="150" y="70" width="80" height="20" rx="3" fill="#111c2e" stroke="#64748b" strokeWidth="1" />
          {Array.from({ length: 3 }, (_, i) => {
            const f = (saw(t, 0.8) + i / 3) % 1;
            return <circle key={i} cx={152 + f * 76} cy="80" r="2.4" fill="#22d3ee" />;
          })}
          {L(154, 106, 'to waveguide', '#67e8f9')}
          {L(10, 20, 'MAGNETRON', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ln-klystron', group: 'linac', tag: 'RF power', hex: '#22d3ee',
    part: 'Klystron — velocity-modulated amplifier',
    summary: 'A low-power RF drive velocity-modulates a DC electron beam; the beam bunches as it drifts and gives up megawatts to the output cavity.',
    bullets: [
      'Peak power 5–50 MW — the choice above roughly 15 MeV and for research machines.',
      'Unlike a magnetron it is an amplifier, so frequency and phase are set by a stable external driver.',
      'Needs a high-voltage modulator (100–300 kV pulses) and usually a solenoid focusing coil.',
      'Larger, heavier and costlier, but far more stable — important for dose-rate-critical applications.',
      'The spent beam is dumped into a water-cooled collector that dominates the cooling load.',
    ],
    draw: t => {
      const ph = t * 4;
      return (
        <g>
          <rect x="26" y="62" width="208" height="36" rx="6" fill="#0b1b34" stroke="#22d3ee" strokeWidth="1.2" />
          <rect x="52" y="56" width="12" height="48" rx="2" fill="#111c2e" stroke="#67e8f9" strokeWidth="1.2" />
          <rect x="176" y="56" width="12" height="48" rx="2" fill="#111c2e" stroke="#67e8f9" strokeWidth="1.2" />
          {L(36, 48, 'buncher', '#67e8f9')}
          {L(166, 48, 'catcher', '#67e8f9')}
          {L(96, 48, 'drift tube — bunching', '#94a3b8')}
          {Array.from({ length: 16 }, (_, i) => {
            const f = (saw(t, 0.35) + i / 16) % 1;
            const bunch = Math.sin(f * Math.PI * 3 + ph) * (f > 0.25 ? (f - 0.25) * 12 : 0);
            return <circle key={i} cx={30 + f * 196 + bunch} cy="80" r="2" fill="#818cf8" />;
          })}
          <rect x="198" y="70" width="34" height="20" rx="3" fill="#111c2e" stroke="#a855f7" strokeWidth="1" />
          {L(196, 116, 'RF out 5–50 MW', '#d8b4fe')}
          {L(10, 20, 'KLYSTRON', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ln-bend', group: 'linac', tag: 'Beam transport', hex: '#22c55e',
    part: '270° achromatic bending magnet',
    summary: 'The bend folds the beam back toward the target and acts as a spectrometer: energy slits reject any electron outside the accepted momentum band.',
    bullets: [
      'Achromatic means the exit position does not depend on energy — the spot stays put as the spectrum breathes.',
      'Energy slits define the beam quality index that dosimetry protocols assume.',
      'A 270° geometry keeps the treatment head short enough to rotate on a gantry.',
      'Steering coils trim the beam onto the target centre; a mis-steered beam shows up as field asymmetry.',
      'Industrial in-line machines often skip the bend entirely and fire straight through the target.',
    ],
    draw: t => {
      const f = saw(t, 0.35);
      const ang = -Math.PI / 2 + f * Math.PI * 1.5;
      return (
        <g>
          <circle cx="150" cy="70" r="34" fill="none" stroke="#22c55e" strokeWidth="10" strokeOpacity="0.15" />
          <circle cx="150" cy="70" r="34" fill="none" stroke="#22c55e" strokeWidth="1.2" strokeDasharray="4 3" />
          <line x1="40" y1="70" x2="150" y2="70" stroke="#818cf8" strokeWidth="1.4" strokeDasharray="3 2" />
          <circle cx={150 + Math.cos(ang) * 34} cy={70 + Math.sin(ang) * 34} r="3" fill="#818cf8" />
          <rect x="138" y="116" width="26" height="9" rx="2" fill="#292524" stroke="#f59e0b" strokeWidth="1.2" />
          {L(170, 124, 'target', '#fbbf24')}
          <rect x="122" y="100" width="8" height="12" fill="#1c1917" stroke="#6b7280" />
          <rect x="172" y="100" width="8" height="12" fill="#1c1917" stroke="#6b7280" />
          {L(186, 108, 'energy slits', '#94a3b8')}
          {L(10, 20, 'ACHROMATIC BEND', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ln-target', group: 'linac', tag: 'Head', hex: '#fde047',
    part: 'Transmission target & flattening filter',
    summary: 'Electrons stop in a thin high-Z target; at MeV energy the bremsstrahlung is sharply forward-peaked, so a conical filter flattens the profile across the field.',
    bullets: [
      'Target is tungsten or gold backed by copper for heat removal — it runs red hot during treatment.',
      'The flattening filter also hardens the beam, which is why flattening-filter-free modes have a softer spectrum.',
      'FFF beams give 2–4× the dose rate and are standard for stereotactic treatments.',
      'Filter shape is machine-specific and is part of the commissioned beam model.',
      'Damage or mis-positioning shows immediately as beam-profile asymmetry in daily QA.',
    ],
    draw: t => {
      const k = saw(t, 0.7);
      const prof = (flat: boolean) => Array.from({ length: 40 }, (_, i) => {
        const x = 150 + (i / 39) * 90;
        const u = (i / 39 - 0.5) * 2;
        const v = flat ? 26 * (1 - 0.06 * u * u * u * u) : 30 * Math.exp(-u * u * 4);
        return `${x},${126 - v}`;
      }).join(' ');
      return (
        <g>
          <circle cx={70} cy={26 + k * 18} r="2.6" fill="#818cf8" />
          <rect x="52" y="46" width="36" height="8" rx="2" fill="#292524" stroke="#f59e0b" strokeWidth="1.2" />
          {L(92, 52, 'W target', '#fbbf24')}
          <polygon points="70,54 40,120 100,120" fill="#fde047" fillOpacity="0.14" />
          <polygon points="58,66 82,66 70,82" fill="#94a3b8" stroke="#cbd5e1" strokeWidth="1" />
          {L(90, 76, 'flattening filter', '#cbd5e1')}
          <line x1="150" y1="126" x2="240" y2="126" stroke="#334155" />
          <polyline points={prof(false)} fill="none" stroke="#64748b" strokeWidth="1" strokeDasharray="3 2" />
          <polyline points={prof(true)} fill="none" stroke="#fde047" strokeWidth="1.4" />
          {L(150, 44, 'raw (dashed) vs flattened', '#94a3b8')}
          {L(10, 20, 'TARGET + FILTER', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ln-mlc', group: 'linac', tag: 'Head', hex: '#94a3b8',
    part: 'Multileaf collimator (MLC)',
    summary: 'Dozens of independently driven tungsten leaves shape the field to the target outline and can move during delivery to modulate intensity.',
    bullets: [
      'Modern heads carry 80–160 leaves with 2.5–5 mm projected width at isocentre.',
      'Leaf ends are rounded and sides tongue-and-grooved to control transmission and inter-leaf leakage.',
      'Leakage must stay below about 2 % of the open-field dose (IEC 60601-2-1).',
      'Dynamic delivery (IMRT/VMAT) sweeps the leaves while the gantry rotates and the dose rate varies.',
      'Leaf position accuracy is verified with picket-fence tests as part of routine QA.',
    ],
    draw: t => {
      const k = 0.5 + 0.5 * osc(t, 0.2);
      return (
        <g>
          {Array.from({ length: 10 }, (_, i) => {
            const shape = Math.sin((i / 9) * Math.PI);
            const gap = 12 + shape * 34 * k;
            return (
              <g key={i}>
                <rect x={130 - gap - 66} y={30 + i * 10} width="66" height="8" rx="1.5" fill="#334155" stroke="#94a3b8" strokeWidth="0.6" />
                <rect x={130 + gap} y={30 + i * 10} width="66" height="8" rx="1.5" fill="#334155" stroke="#94a3b8" strokeWidth="0.6" />
              </g>
            );
          })}
          {Array.from({ length: 10 }, (_, i) => {
            const shape = Math.sin((i / 9) * Math.PI);
            const gap = 12 + shape * 34 * k;
            return <rect key={i} x={130 - gap} y={30 + i * 10} width={gap * 2} height="8" fill="#fde047" fillOpacity="0.18" />;
          })}
          {L(10, 20, 'MULTILEAF COLLIMATOR', '#cbd5e1', 8)}
          {L(10, 142, 'tungsten leaves conform to target outline', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'ln-chamber', group: 'linac', tag: 'Safety', hex: '#4ade80',
    part: 'Dual ion chambers & beam interrupts',
    summary: 'Two independent sealed transmission chambers sit in the beam, continuously measuring dose, dose rate, symmetry and flatness.',
    bullets: [
      'Either chamber alone can terminate the beam; they are read by separate electronics chains.',
      'Beam stops automatically at 110 % of the set monitor units, and on any symmetry or flatness excursion.',
      'Chambers are sealed and temperature/pressure compensated so the calibration does not drift with weather.',
      'Daily output constancy checks compare chamber response against an external reference.',
      'Other interlocks in the chain: door switches, emergency stops, arc detectors, water flow and SF₆ pressure.',
    ],
    draw: t => {
      const fault = saw(t, 0.22) > 0.72;
      const lvl = fault ? 1.12 : 0.6 + 0.35 * Math.abs(osc(t, 0.5));
      return (
        <g>
          <rect x="96" y="34" width="68" height="10" rx="2" fill="#0b1b34" stroke="#4ade80" strokeWidth="1.2" />
          <rect x="96" y="50" width="68" height="10" rx="2" fill="#0b1b34" stroke="#4ade80" strokeWidth="1.2" />
          {L(170, 42, 'chamber 1', '#86efac')}
          {L(170, 58, 'chamber 2', '#86efac')}
          <polygon points="130,20 96,132 164,132" fill="#fde047" fillOpacity={fault ? 0.05 : 0.16} />
          <rect x="26" y="86" width="56" height="40" rx="4" fill="#0b1220" stroke={fault ? '#ef4444' : '#334155'} strokeWidth="1.5" />
          <rect x="30" y={122 - lvl * 30} width="48" height={lvl * 30} fill={fault ? '#ef4444' : '#4ade80'} opacity="0.7" />
          <line x1="26" y1="93" x2="82" y2="93" stroke="#f87171" strokeWidth="1" strokeDasharray="2 2" />
          {L(26, 140, fault ? 'BEAM OFF — 110 % limit' : 'dose accumulating', fault ? '#f87171' : '#86efac')}
          {L(10, 20, 'DOSE MONITORING', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'ln-modulator', group: 'linac', tag: 'RF power', hex: '#f472b6',
    part: 'Modulator & thyratron pulse forming',
    summary: 'A pulse-forming network charges between pulses and dumps its energy through a thyratron into the RF source, producing microsecond pulses of hundreds of kilovolts.',
    bullets: [
      'Pulse width 1–5 µs at 100–400 Hz sets the machine duty cycle and therefore the dose rate.',
      'Thyratrons are consumables; reservoir voltage drift is the classic early warning of end of life.',
      'Solid-state modulators are replacing thyratrons in new installations — fewer consumables, faster fault detection.',
      'Pulse-to-pulse amplitude stability directly determines beam energy stability.',
      'Arc detectors watch the waveguide and inhibit the next pulse within microseconds of a breakdown.',
    ],
    draw: t => {
      const f = saw(t, 0.8);
      const firing = f > 0.7;
      return (
        <g>
          <rect x="26" y="56" width="52" height="44" rx="4" fill="#0b1220" stroke="#64748b" strokeWidth="1.2" />
          {L(24, 50, 'PFN charge', '#94a3b8')}
          <rect x="30" y={96 - (firing ? 4 : f * 36)} width="44" height={firing ? 4 : f * 36} fill="#f472b6" opacity="0.6" />
          <polygon points="96,66 96,90 118,78" fill={firing ? '#f472b6' : '#1f2937'} stroke="#f472b6" strokeWidth="1.2" />
          {L(90, 108, 'thyratron', '#f9a8d4')}
          <rect x="134" y="58" width="46" height="40" rx="4" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.2" />
          {L(132, 112, 'magnetron', '#d8b4fe')}
          <polyline points={Array.from({ length: 60 }, (_, i) => {
            const x = 26 + i * 3.4;
            const hi = ((i / 60 * 3 + t * 0.8) % 1) > 0.7;
            return `${x},${hi ? 124 : 136}`;
          }).join(' ')} fill="none" stroke="#f472b6" strokeWidth="1.3" />
          {L(10, 20, 'PULSE MODULATOR', '#cbd5e1', 8)}
        </g>
      );
    },
  },
];

// ─── BETATRON ─────────────────────────────────────────────────────────────────
export const BETATRON_PARTS: MicroAnim[] = [
  {
    id: 'bt-core', group: 'betatron', tag: 'Magnet', hex: '#f472b6',
    part: 'Laminated core & flux ramp',
    summary: 'A large laminated iron core driven at mains frequency produces the changing flux whose induced electric field is the accelerating force.',
    bullets: [
      'Laminations suppress eddy currents that would otherwise waste the drive power as heat.',
      'Only the rising quarter of each cycle accelerates; the rest of the cycle is dead time.',
      'The magnet is the heaviest and costliest part of the machine — energy scales poorly with size.',
      'Drive current is often resonated with a capacitor bank to reduce the supply rating.',
      'Core saturation sets the practical energy ceiling for a given geometry.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      const B = Math.sin(f * Math.PI * 2);
      return (
        <g>
          <rect x="96" y="34" width="68" height="82" rx="6" fill="#1f2937" stroke="#6b7280" strokeWidth="1.5" />
          {Array.from({ length: 7 }, (_, i) => <line key={i} x1={100 + i * 9} y1="34" x2={100 + i * 9} y2="116" stroke="#374151" strokeWidth="1" />)}
          {Array.from({ length: 5 }, (_, i) => (
            <ellipse key={i} cx="130" cy="75" rx={36 + i * 12} ry={26 + i * 8} fill="none" stroke="#38bdf8" strokeWidth="1" opacity={Math.abs(B) * (1 - i / 6)} />
          ))}
          <line x1="26" y1="130" x2="234" y2="130" stroke="#334155" />
          <polyline points={Array.from({ length: 60 }, (_, i) => `${26 + i * 3.5},${130 - Math.sin((i / 60) * Math.PI * 4) * 14}`).join(' ')} fill="none" stroke="#64748b" strokeWidth="1" />
          <circle cx={26 + f * 208} cy={130 - Math.sin(f * Math.PI * 4) * 14} r="2.6" fill="#f472b6" />
          {L(10, 20, 'FLUX RAMP  dΦ/dt', '#cbd5e1', 8)}
          {L(178, 60, B > 0 ? 'accelerating' : 'dead phase', B > 0 ? '#4ade80' : '#f87171')}
        </g>
      );
    },
  },
  {
    id: 'bt-donut', group: 'betatron', tag: 'Vacuum', hex: '#38bdf8',
    part: 'Doughnut vacuum chamber',
    summary: 'A toroidal glass or ceramic chamber holds the circulating beam. It must be insulating so the induced electric field is not shorted out.',
    bullets: [
      'A metal chamber would carry an induced current and cancel the accelerating field — hence glass or ceramic.',
      'An internal conductive coating drains static charge without forming a closed loop.',
      'Vacuum below 10⁻⁶ mbar keeps gas scattering from destroying the beam over the long path length.',
      'The chamber walls also define the physical aperture that beam oscillations must stay inside.',
      'Chamber cracks are catastrophic and usually terminal for the machine.',
    ],
    draw: t => {
      const a = t * 4;
      return (
        <g>
          <ellipse cx="130" cy="76" rx="88" ry="46" fill="none" stroke="#64748b" strokeWidth="12" strokeOpacity="0.3" />
          <ellipse cx="130" cy="76" rx="88" ry="46" fill="none" stroke="#38bdf8" strokeWidth="1" strokeDasharray="4 3" />
          <ellipse cx="130" cy="76" rx="66" ry="32" fill="none" stroke="#334155" strokeWidth="1" />
          <circle cx={130 + Math.cos(a) * 77} cy={76 + Math.sin(a) * 39} r="3" fill="#f472b6" />
          {L(10, 20, 'DOUGHNUT CHAMBER', '#cbd5e1', 8)}
          {L(10, 138, 'insulating wall · < 10⁻⁶ mbar', '#7dd3fc')}
        </g>
      );
    },
  },
  {
    id: 'bt-condition', group: 'betatron', tag: 'Beam dynamics', hex: '#fde047',
    part: 'The 2:1 betatron condition',
    summary: 'The average field enclosed by the orbit must be exactly twice the field at the orbit radius, otherwise the radius drifts inward or outward as energy rises.',
    bullets: [
      'Formally: <code>B̄(inside) = 2 · B(r₀)</code> — Kerst and Serber, 1941.',
      'Pole-face shaping and a central flux bar are what enforce the ratio in hardware.',
      'A field index between 0 and 1 gives weak focusing in both the radial and vertical planes.',
      'Get it wrong and the beam spirals into the chamber wall within a few hundred turns.',
      'The same stability analysis underpins every later circular machine.',
    ],
    draw: t => {
      const bad = saw(t, 0.25) > 0.55;
      const drift = bad ? (saw(t, 0.25) - 0.55) * 60 : 0;
      return (
        <g>
          <ellipse cx="120" cy="78" rx="70" ry="38" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />
          <ellipse cx="120" cy="78" rx={70 + drift} ry={38 + drift * 0.55} fill="none" stroke={bad ? '#f87171' : '#4ade80'} strokeWidth="1.4" />
          <circle cx={120 + Math.cos(t * 6) * (70 + drift)} cy={78 + Math.sin(t * 6) * (38 + drift * 0.55)} r="3" fill={bad ? '#f87171' : '#4ade80'} />
          <ellipse cx="120" cy="78" rx="22" ry="14" fill="#1f2937" stroke="#6b7280" />
          {L(102, 82, 'flux bar', '#cbd5e1')}
          {L(10, 20, 'ORBIT STABILITY', '#cbd5e1', 8)}
          {L(196, 60, bad ? 'ratio ≠ 2 →' : 'ratio = 2', bad ? '#f87171' : '#4ade80')}
          {L(196, 72, bad ? 'orbit drifts' : 'orbit locked', bad ? '#f87171' : '#4ade80')}
        </g>
      );
    },
  },
  {
    id: 'bt-injector', group: 'betatron', tag: 'Injector', hex: '#a78bfa',
    part: 'Injection gun & orbit contraction',
    summary: 'A pulsed electron gun fires into the chamber at the start of each cycle; a contraction pulse then moves the beam off the injector so it is not scraped away.',
    bullets: [
      'Injection lasts only a few microseconds at the very beginning of the rising flux.',
      'Capture efficiency is low — most injected electrons are lost in the first turns.',
      'The injector structure sits inside the aperture, so the orbit has to be moved away from it immediately.',
      'At the end of the cycle an expansion pulse does the reverse, driving the beam onto the target.',
      'Injection and extraction timing are the main tuning parameters on an operating betatron.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      const r = 30 + ease01(f) * 46;
      return (
        <g>
          <ellipse cx="130" cy="78" rx="86" ry="44" fill="none" stroke="#334155" strokeWidth="8" strokeOpacity="0.4" />
          <rect x="200" y="70" width="18" height="16" rx="3" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.2" />
          {L(190, 106, 'gun', '#d8b4fe')}
          <ellipse cx="130" cy="78" rx={r} ry={r * 0.52} fill="none" stroke="#f472b6" strokeWidth="1.2" strokeDasharray="2 3" />
          <circle cx={130 + Math.cos(t * 8) * r} cy={78 + Math.sin(t * 8) * r * 0.52} r="2.8" fill="#f472b6" />
          {L(10, 20, 'INJECT → CONTRACT', '#cbd5e1', 8)}
          {L(10, 138, f < 0.15 ? 'injecting…' : 'orbit contracted, accelerating', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'bt-target', group: 'betatron', tag: 'Output', hex: '#fbbf24',
    part: 'Expansion pulse & tungsten target',
    summary: 'At peak energy an expansion winding pushes the orbit outward until the beam strikes an internal tungsten target, converting electrons into hard bremsstrahlung.',
    bullets: [
      'Beam dump and X-ray production happen at the same place — there is no external beam line.',
      'The photon endpoint equals the final electron energy, from 15 MeV up to a few hundred MeV.',
      'Very hard spectra penetrate 100–300 mm of steel, the reason betatrons survived in heavy NDT.',
      'Dose rate is modest compared with a LINAC because only one short burst occurs per mains cycle.',
      'Target cooling is simple: average power is low even though peak energy is high.',
    ],
    draw: t => {
      const f = saw(t, 0.6);
      const hit = f > 0.75;
      return (
        <g>
          <ellipse cx="120" cy="78" rx="72" ry="38" fill="none" stroke="#334155" strokeWidth="8" strokeOpacity="0.4" />
          <ellipse cx="120" cy="78" rx={60 + f * 16} ry={(60 + f * 16) * 0.52} fill="none" stroke="#f472b6" strokeWidth="1.2" />
          <rect x="192" y="70" width="9" height="18" rx="2" fill="#292524" stroke="#f59e0b" strokeWidth="1.2" />
          {L(186, 104, 'W target', '#fbbf24')}
          {hit && Array.from({ length: 4 }, (_, i) => (
            <line key={i} x1="201" y1="79" x2={201 + 40 * (f - 0.75) * 4} y2={79 + (i - 1.5) * 12 * (f - 0.75) * 4} stroke="#fde047" strokeWidth="1.4" />
          ))}
          {L(10, 20, 'EXTRACTION BURST', '#cbd5e1', 8)}
          {L(10, 138, hit ? 'photon burst → 15–300 MeV endpoint' : 'orbit expanding…', hit ? '#fde047' : '#94a3b8')}
        </g>
      );
    },
  },
];

const ease01 = (p: number) => { const x = Math.min(1, Math.max(0, p)); return x * x * (3 - 2 * x); };

// ─── CYCLOTRON ────────────────────────────────────────────────────────────────
export const CYCLOTRON_PARTS: MicroAnim[] = [
  {
    id: 'cy-source', group: 'cyclotron', tag: 'Injector', hex: '#fde047',
    part: 'Ion source (PIG / external)',
    summary: 'A gas discharge at the machine centre creates the ions. Medical machines almost always make negative hydrogen ions because extraction is then trivial.',
    bullets: [
      'Internal Penning (PIG) sources sit in the median plane; external sources inject axially through a spiral inflector.',
      'H⁻ is fragile — it is stripped by residual gas, so source gas load and vacuum quality fight each other.',
      'Source current sets beam current, which sets isotope yield per irradiation.',
      'Cathode erosion makes the source the most frequently serviced component in a hospital cyclotron.',
      'Deuterium sources are used where neutron-producing reactions are needed.',
    ],
    draw: t => {
      const n = 10;
      return (
        <g>
          <circle cx="130" cy="76" r="46" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />
          <rect x="122" y="60" width="16" height="32" rx="3" fill="#0b1220" stroke="#fde047" strokeWidth="1.4" />
          <circle cx="130" cy="76" r={10 + 4 * Math.abs(osc(t, 1.2))} fill="url(#fp-glow)" />
          {Array.from({ length: n }, (_, i) => {
            const a = (i / n) * Math.PI * 2 + t * 2;
            const r = 16 + 10 * ((t * 0.5 + i / n) % 1);
            return <circle key={i} cx={130 + Math.cos(a) * r} cy={76 + Math.sin(a) * r} r="1.8" fill="#4ade80" />;
          })}
          {L(10, 20, 'ION SOURCE', '#cbd5e1', 8)}
          {L(184, 60, 'H⁻ plasma', '#4ade80')}
          {L(184, 74, 'arc 300–800 V', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'cy-dees', group: 'cyclotron', tag: 'RF', hex: '#22d3ee',
    part: 'Dees & RF resonator',
    summary: 'Two hollow D-shaped electrodes form the RF resonator. Inside a dee there is no field; all the acceleration happens in the gap between them.',
    bullets: [
      'Resonant frequency must equal qB/2πm — typically 20–100 MHz for medical machines.',
      'Dee voltage of 30–100 kV means each turn adds twice that in energy.',
      'The dee stems and liner form a quarter-wave resonator; tuning is done with a movable panel or trimmer.',
      'RF power is fed through a coupling loop with a matching network that follows beam loading.',
      'Sparking in the dee gap is the classic conditioning problem after a vacuum vent.',
    ],
    draw: t => {
      const pos = osc(t, 1.5) > 0;
      const a = t * 6;
      return (
        <g>
          <path d="M 124 30 A 46 46 0 0 0 124 122 Z" fill="#0b2540" stroke={pos ? '#22d3ee' : '#334155'} strokeWidth="1.6" />
          <path d="M 136 30 A 46 46 0 0 1 136 122 Z" fill="#2a0b2e" stroke={pos ? '#334155' : '#f472b6'} strokeWidth="1.6" />
          <rect x="124" y="30" width="12" height="92" fill={pos ? '#22d3ee' : '#f472b6'} fillOpacity="0.14" />
          {L(80, 78, pos ? '−' : '+', '#67e8f9', 12, 'middle')}
          {L(180, 78, pos ? '+' : '−', '#f9a8d4', 12, 'middle')}
          <circle cx={130 + Math.cos(a) * 30} cy={76 + Math.sin(a) * 30} r="2.8" fill="#4ade80" />
          <circle cx="130" cy="76" r="30" fill="none" stroke="#4ade80" strokeWidth="0.8" strokeDasharray="2 3" />
          {L(10, 20, 'DEE GAP KICK', '#cbd5e1', 8)}
          {L(10, 140, 'f = qB / 2πm  ·  V_dee 30–100 kV', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'cy-sectors', group: 'cyclotron', tag: 'Magnet', hex: '#4ade80',
    part: 'Hill-and-valley sectors (isochronism)',
    summary: 'Azimuthally varying field sectors let the average field rise with radius — compensating relativistic mass gain — while still focusing the beam vertically.',
    bullets: [
      'A field that simply rises with radius would defocus vertically; sector shaping restores focusing via edge effects.',
      'Spiral sectors add extra focusing at higher energies (Thomas focusing).',
      'This is what makes a continuous-beam isochronous cyclotron possible instead of a pulsed synchrocyclotron.',
      'Trim coils fine-tune the isochronism field profile after magnetic mapping.',
      'A mis-set trim coil shows up as beam loss at a specific radius — effectively an energy ceiling.',
    ],
    draw: t => {
      const a = t * 3;
      return (
        <g>
          <circle cx="130" cy="76" r="54" fill="none" stroke="#334155" strokeWidth="1" />
          {Array.from({ length: 4 }, (_, i) => {
            const a0 = (i / 4) * Math.PI * 2;
            const a1 = a0 + Math.PI / 4;
            const p = (r: number, ang: number) => `${130 + Math.cos(ang) * r},${76 + Math.sin(ang) * r}`;
            return <path key={i} d={`M ${p(12, a0)} L ${p(54, a0)} A 54 54 0 0 1 ${p(54, a1)} L ${p(12, a1)} Z`}
              fill="#14301c" stroke="#4ade80" strokeWidth="1" />;
          })}
          <circle cx={130 + Math.cos(a) * 40} cy={76 + Math.sin(a) * 40} r="2.6" fill="#fde047" />
          {L(10, 20, 'AVF SECTORS', '#cbd5e1', 8)}
          {L(196, 44, 'hill', '#4ade80')}
          {L(196, 58, 'valley', '#64748b')}
          {L(10, 140, 'B̄(r) ∝ γ(r) keeps f_rev constant', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'cy-stripper', group: 'cyclotron', tag: 'Extraction', hex: '#f472b6',
    part: 'Stripper foil extraction',
    summary: 'A thin carbon foil tears both electrons off the H⁻ ion. The charge flips sign, the magnetic force reverses, and the beam curves straight out of the machine.',
    bullets: [
      'Extraction efficiency approaches 100 % — no septum losses, so activation of the machine stays low.',
      'Foil radial position selects the extracted energy; moving it is how variable-energy machines work.',
      'Two foils on a carousel allow simultaneous dual-target irradiation.',
      'Foils are consumables: they thin, curl and eventually break under beam heating.',
      'Positive-ion machines instead need an electrostatic deflector and accept a few percent beam loss.',
    ],
    draw: t => {
      const f = saw(t, 0.55);
      const inside = f < 0.55;
      const a = f * 12;
      const x = inside ? 130 + Math.cos(a) * (26 + f * 50) : 176 + (f - 0.55) * 130;
      const y = inside ? 76 + Math.sin(a) * (26 + f * 50) : 76 - (f - 0.55) * 40;
      return (
        <g>
          <circle cx="130" cy="76" r="56" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />
          <line x1="176" y1="60" x2="176" y2="92" stroke="#f472b6" strokeWidth="2" />
          {L(160, 108, 'C foil', '#f9a8d4')}
          <circle cx={x} cy={y} r="2.8" fill={inside ? '#38bdf8' : '#f472b6'} />
          {L(30, 40, inside ? 'H⁻ circulating' : 'p⁺ extracted', inside ? '#7dd3fc' : '#f9a8d4')}
          <rect x="216" y="26" width="26" height="26" rx="3" fill="#0b2540" stroke="#38bdf8" strokeWidth="1.2" />
          {L(206, 20, 'target', '#7dd3fc')}
          {L(10, 20, 'STRIPPING EXTRACTION', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'cy-target', group: 'cyclotron', tag: 'Targetry', hex: '#38bdf8',
    part: 'Water target & hot cell chemistry',
    summary: 'The extracted protons hit enriched oxygen-18 water inside a small pressurised chamber; the fluorine-18 produced is swept to a shielded synthesis module.',
    bullets: [
      'Reaction ¹⁸O(p,n)¹⁸F; target foils are usually Havar or niobium and take the full beam power.',
      'Targets run at 20–40 bar because the water boils under beam heating.',
      'Product is transferred by helium push through shielded tubing to a hot cell.',
      'FDG synthesis, purification and QC take about 30 minutes against a 110-minute half-life.',
      'Target windows are routine consumables; a window failure contaminates the target chamber.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      return (
        <g>
          <rect x="26" y="62" width="46" height="34" rx="4" fill="#0b2540" stroke="#38bdf8" strokeWidth="1.4" />
          {L(22, 56, '[¹⁸O]H₂O', '#7dd3fc')}
          {Array.from({ length: 4 }, (_, i) => {
            const g = (f + i / 4) % 1;
            return <circle key={i} cx={0 + g * 30} cy="79" r="2" fill="#f472b6" opacity={g > 0.85 ? 0 : 1} />;
          })}
          <line x1="72" y1="79" x2="112" y2="79" stroke="#22c55e" strokeWidth="1.6" markerEnd="url(#fp-arrow)" />
          <rect x="112" y="52" width="52" height="54" rx="5" fill="#111c2e" stroke="#22c55e" strokeWidth="1.4" />
          {L(112, 46, 'hot cell', '#86efac')}
          {L(120, 76, '¹⁸F⁻', '#4ade80', 9)}
          {L(118, 92, 'FDG synth', '#94a3b8', 6.5)}
          <line x1="164" y1="79" x2="200" y2="79" stroke="#22c55e" strokeWidth="1.6" markerEnd="url(#fp-arrow)" />
          <rect x="200" y="62" width="34" height="34" rx="4" fill="#0b1220" stroke="#94a3b8" strokeWidth="1.2" />
          {L(198, 118, 'QC → dose', '#cbd5e1')}
          {L(10, 20, 'TARGET → RADIOPHARMACY', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'cy-vacuum', group: 'cyclotron', tag: 'Vacuum', hex: '#94a3b8',
    part: 'Vacuum & self-shielding',
    summary: 'Cryopumps hold the chamber below 10⁻⁶ mbar so H⁻ survives the trip, while a local shield of concrete and borated polyethylene absorbs the neutrons produced.',
    bullets: [
      'Residual gas strips H⁻ prematurely, causing beam loss and localised activation.',
      'Neutrons from (p,n) reactions activate the machine and the vault — access control is time-based.',
      'Self-shielded cyclotrons let a hospital install one without building a thick concrete bunker.',
      'Short-lived activation products dictate a cool-down wait before maintenance.',
      'Air activation (¹³N, ⁴¹Ar) requires vault ventilation with a controlled delay before release.',
    ],
    draw: t => {
      const p = 0.4 + 0.6 * Math.abs(osc(t, 0.25));
      return (
        <g>
          <rect x="34" y="34" width="192" height="86" rx="10" fill="#0b1220" stroke="#94a3b8" strokeWidth="1.4" />
          <rect x="50" y="46" width="160" height="62" rx="8" fill="#111c2e" stroke="#64748b" strokeWidth="1" strokeDasharray="4 3" />
          <circle cx="130" cy="77" r="26" fill="none" stroke="#4ade80" strokeWidth="1.2" />
          {Array.from({ length: 10 }, (_, i) => {
            const a = (i / 10) * Math.PI * 2 + t;
            const r = 34 + 26 * ((t * 0.4 + i / 10) % 1);
            return <circle key={i} cx={130 + Math.cos(a) * r} cy={77 + Math.sin(a) * r * 0.6} r="1.6" fill="#f87171" opacity={0.8 - r / 90} />;
          })}
          {L(46, 132, 'borated PE + concrete self-shield', '#94a3b8')}
          {L(10, 20, 'VACUUM & SHIELDING', '#cbd5e1', 8)}
          {L(196, 30, `${(1e-6 / p).toExponential(0)} mbar`, '#7dd3fc')}
        </g>
      );
    },
  },
];

// ─── SYNCHROTRON ──────────────────────────────────────────────────────────────
export const SYNCHROTRON_PARTS: MicroAnim[] = [
  {
    id: 'sy-dipole', group: 'synchrotron', tag: 'Lattice', hex: '#22d3ee',
    part: 'Dipole (bending) magnet',
    summary: 'Dipoles steer the beam around the ring and, as a by-product, radiate a broad continuous spectrum tangentially into the bending-magnet beamlines.',
    bullets: [
      'Bending radius and beam energy set the critical photon energy of the emitted spectrum.',
      'Radiated power scales as the fourth power of energy divided by the radius squared.',
      'The radiation fan is wide horizontally and narrow vertically — about 1/γ.',
      'Dipole field stability directly determines beam orbit stability at the experiments.',
      'Superbends use superconducting dipoles to push the critical energy higher in an existing ring.',
    ],
    draw: t => {
      const a = t * 1.2;
      const px = 90 + Math.cos(a) * 0, py = 0;
      const x = 40 + saw(t, 0.35) * 150;
      return (
        <g>
          <path d="M 30 110 Q 130 110 220 46" fill="none" stroke="#22d3ee" strokeWidth="1.4" strokeDasharray="3 3" />
          <rect x="96" y="72" width="66" height="42" rx="5" fill="#0b1b34" stroke="#22d3ee" strokeWidth="1.4" />
          {L(100, 66, 'dipole B', '#67e8f9')}
          <circle cx={x} cy={110 - Math.max(0, (x - 130) * 0.45)} r="2.8" fill="#818cf8" />
          <polygon points="150,96 240,54 244,74" fill="#fde047" fillOpacity="0.2" />
          {L(196, 96, 'radiation fan', '#fde047')}
          {L(10, 20, 'BENDING MAGNET', '#cbd5e1', 8)}
          {L(10, 140, 'P ∝ E⁴ / ρ²   ·   cone ≈ 1/γ', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'sy-quad', group: 'synchrotron', tag: 'Lattice', hex: '#4ade80',
    part: 'Quadrupole focusing (FODO)',
    summary: 'A quadrupole focuses in one plane and defocuses in the other. Alternating them along the ring gives net focusing in both planes — strong focusing.',
    bullets: [
      'Strong focusing (Courant–Snyder, 1952) is what made small-aperture, high-energy rings possible.',
      'The repeating focus–drift–defocus–drift pattern is the FODO cell.',
      'Beta functions describe the envelope; low beta at the insertion device means a small, bright source.',
      'Emittance — the phase-space area — is what ultimately sets brightness; modern rings chase ultra-low emittance.',
      'Multi-bend achromat lattices trade many weaker dipoles for far lower emittance.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      const env = (x: number) => 16 + 12 * Math.sin(x / 26 + f * Math.PI * 2);
      return (
        <g>
          {Array.from({ length: 4 }, (_, i) => (
            <rect key={i} x={40 + i * 52} y="52" width="18" height="52" rx="3"
              fill={i % 2 ? '#14301c' : '#2a0b2e'} stroke={i % 2 ? '#4ade80' : '#f472b6'} strokeWidth="1.2" />
          ))}
          {[0, 1, 2, 3].map(i => L(40 + i * 52, 46, i % 2 ? 'F' : 'D', i % 2 ? '#4ade80' : '#f472b6', 8))}
          <polyline points={Array.from({ length: 60 }, (_, i) => `${30 + i * 3.4},${78 - env(i * 3.4)}`).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="1.2" />
          <polyline points={Array.from({ length: 60 }, (_, i) => `${30 + i * 3.4},${78 + env(i * 3.4)}`).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="1.2" />
          <line x1="30" y1="78" x2="234" y2="78" stroke="#334155" strokeDasharray="2 3" />
          {L(10, 20, 'STRONG FOCUSING', '#cbd5e1', 8)}
          {L(10, 140, 'FODO cell — β function envelope', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'sy-rf', group: 'synchrotron', tag: 'Lattice', hex: '#a78bfa',
    part: 'RF cavity & bunch structure',
    summary: 'Superconducting or copper cavities replace the energy radiated each turn and bunch the beam, which is why synchrotron light arrives as a pulse train.',
    bullets: [
      'Typical cavity frequency is around 500 MHz, giving nanosecond-spaced bunches.',
      'Filling patterns (uniform, hybrid, single-bunch) are chosen for the timing experiments that need them.',
      'Phase stability — synchrotron oscillation — keeps particles bunched around the synchronous phase.',
      'Higher-harmonic cavities lengthen the bunch to fight Touschek scattering and extend beam lifetime.',
      'Pulse structure enables time-resolved and pump–probe experiments.',
    ],
    draw: t => {
      const ph = t * 4;
      return (
        <g>
          <ellipse cx="70" cy="76" rx="26" ry="34" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.4" />
          {L(48, 34, 'RF cavity 500 MHz', '#d8b4fe')}
          <polyline points={Array.from({ length: 40 }, (_, i) => `${48 + i * 1.1},${76 - Math.sin(i * 0.5 + ph) * 14}`).join(' ')} fill="none" stroke="#c084fc" strokeWidth="1" />
          <line x1="96" y1="76" x2="240" y2="76" stroke="#334155" strokeWidth="6" />
          {Array.from({ length: 6 }, (_, i) => {
            const x = 100 + ((saw(t, 0.35) * 6 + i) % 6) * 24;
            return <circle key={i} cx={x} cy="76" r="3.4" fill="#22d3ee" />;
          })}
          {L(100, 108, 'bunch train — ns spacing', '#67e8f9')}
          {L(10, 20, 'RF & BUNCHES', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'sy-undulator', group: 'synchrotron', tag: 'Insertion device', hex: '#f59e0b',
    part: 'Undulator vs wiggler',
    summary: 'Both wiggle the beam with periodic magnets. A wiggler adds incoherent flux; an undulator makes the wiggles small enough that emissions interfere and form sharp harmonics.',
    bullets: [
      'Deflection parameter K separates them: K ≲ 1 is an undulator, K ≫ 1 a wiggler.',
      'Undulator wavelength: <code>λ = (λ_u/2γ²)(1 + K²/2 + γ²θ²)</code> — closing the gap tunes the energy.',
      'Brightness gain is about 10⁴ over a bending magnet; a wiggler gains about 10².',
      'In-vacuum and cryogenic undulators shrink the gap further for harder photons.',
      'Gap motion is a routine user-controlled parameter during an experiment.',
    ],
    draw: t => {
      const wig = saw(t, 0.12) > 0.5;
      const amp = wig ? 22 : 7;
      const ph = t * 3;
      return (
        <g>
          {Array.from({ length: 8 }, (_, i) => (
            <g key={i}>
              <rect x={30 + i * 26} y="36" width="20" height="14" rx="2" fill={i % 2 ? '#1e293b' : '#3f2a12'} stroke={i % 2 ? '#64748b' : '#f59e0b'} strokeWidth="0.8" />
              <rect x={30 + i * 26} y="104" width="20" height="14" rx="2" fill={i % 2 ? '#3f2a12' : '#1e293b'} stroke={i % 2 ? '#f59e0b' : '#64748b'} strokeWidth="0.8" />
            </g>
          ))}
          <polyline points={Array.from({ length: 70 }, (_, i) => `${30 + i * 3},${77 - Math.sin(i * 0.42 - ph) * amp}`).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="1.4" />
          {L(10, 20, wig ? 'WIGGLER  (K ≫ 1)' : 'UNDULATOR  (K ≲ 1)', '#cbd5e1', 8)}
          {L(10, 140, wig ? 'broad spectrum, high flux' : 'narrow harmonics, high brightness', wig ? '#f59e0b' : '#22d3ee')}
        </g>
      );
    },
  },
  {
    id: 'sy-mono', group: 'synchrotron', tag: 'Beamline', hex: '#a78bfa',
    part: 'Double-crystal monochromator',
    summary: 'Two parallel silicon crystals select one wavelength by Bragg diffraction and return the beam parallel to the incoming direction, so the sample never has to move.',
    bullets: [
      'Bragg condition <code>nλ = 2d·sin θ</code>; rotating the crystals scans photon energy.',
      'Si(111) gives about 10⁻⁴ energy resolution; Si(311) is finer but passes less flux.',
      'The first crystal absorbs kilowatts of white beam — cryogenic cooling is standard.',
      'A fixed-exit geometry keeps beam height constant while the energy is scanned.',
      'Energy scanning across an absorption edge is exactly what XAFS spectroscopy needs.',
    ],
    draw: t => {
      const th = 0.35 + 0.18 * (0.5 + 0.5 * osc(t, 0.15));
      const dx = Math.cos(th) * 46, dy = Math.sin(th) * 46;
      return (
        <g>
          <line x1="20" y1="60" x2="96" y2="60" stroke="#fde047" strokeWidth="2" opacity="0.75" />
          {L(20, 50, 'white beam', '#fde047')}
          <g transform={`rotate(${(th * 180) / Math.PI - 20} 100 60)`}>
            <rect x="86" y="54" width="34" height="8" rx="1.5" fill="#334155" stroke="#a78bfa" strokeWidth="1.2" />
          </g>
          <line x1="100" y1="60" x2={100 + dx} y2={60 + dy} stroke="#a78bfa" strokeWidth="1.6" />
          <g transform={`rotate(${(th * 180) / Math.PI - 20} ${100 + dx} ${60 + dy})`}>
            <rect x={86 + dx} y={54 + dy} width="34" height="8" rx="1.5" fill="#334155" stroke="#a78bfa" strokeWidth="1.2" />
          </g>
          <line x1={100 + dx} y1={60 + dy} x2="238" y2={60 + dy} stroke="#a78bfa" strokeWidth="1.8" />
          {L(150, 54 + dy, `E = ${(12.4 / (2 * 3.135 * Math.sin(th))).toFixed(1)} keV`, '#c4b5fd')}
          {L(10, 20, 'Si(111) DCM', '#cbd5e1', 8)}
          {L(10, 140, 'nλ = 2d sin θ  ·  fixed exit height', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'sy-detector', group: 'synchrotron', tag: 'Beamline', hex: '#22c55e',
    part: 'Sample stage & area detector',
    summary: 'Transmission, diffraction and fluorescence signals are recorded simultaneously; rotating the sample builds a tomographic or diffraction data set.',
    bullets: [
      'Photon-counting pixel detectors run at kilohertz frame rates with essentially no read noise.',
      'Phase-contrast imaging exploits refraction, revealing soft-tissue and composite detail attenuation misses.',
      'Diffraction imaging separates crystalline explosives from inert powders with identical attenuation.',
      'XAFS at an absorption edge gives oxidation state and local coordination of a specific element.',
      'Micro-CT of heritage objects reaches sub-micrometre voxels without sampling the artefact.',
    ],
    draw: t => {
      const a = t * 1.2;
      return (
        <g>
          <line x1="20" y1="76" x2="98" y2="76" stroke="#a78bfa" strokeWidth="2" />
          <g transform={`rotate(${(a * 60) % 360} 116 76)`}>
            <rect x="102" y="56" width="28" height="40" rx="3" fill="#111c2e" stroke="#f59e0b" strokeWidth="1.3" />
          </g>
          {L(98, 116, 'rotating sample', '#fbbf24')}
          {Array.from({ length: 5 }, (_, i) => {
            const ang = (i - 2) * 0.2;
            return <line key={i} x1="132" y1="76" x2={132 + Math.cos(ang) * 70} y2={76 + Math.sin(ang) * 70} stroke="#38bdf8" strokeWidth="1" opacity="0.6" />;
          })}
          <rect x="206" y="34" width="16" height="84" rx="3" fill="#0b1220" stroke="#22c55e" strokeWidth="1.4" />
          {Array.from({ length: 8 }, (_, i) => (
            <rect key={i} x="208" y={38 + i * 10} width="12" height="7" fill="#22c55e" opacity={0.2 + 0.6 * Math.abs(Math.sin(a + i))} />
          ))}
          {L(196, 132, 'pixel detector', '#86efac')}
          {L(10, 20, 'SAMPLE → DETECTOR', '#cbd5e1', 8)}
        </g>
      );
    },
  },
];

// ─── VAN DE GRAAFF ────────────────────────────────────────────────────────────
export const VDG_PARTS: MicroAnim[] = [
  {
    id: 'vd-corona', group: 'van-de-graaff', tag: 'Charging', hex: '#f87171',
    part: 'Corona spray points',
    summary: 'A sharp electrode held at 20–30 kV ionises the surrounding gas and sprays charge onto the moving belt at the grounded end of the column.',
    bullets: [
      'Field concentration at the tip is what starts the discharge — geometry, not voltage alone.',
      'Spray current sets the charging current and therefore how fast the terminal recovers under beam load.',
      'A second corona assembly at the terminal can be used to regulate the voltage downward.',
      'Corona is also the main parasitic loss mechanism, which is why the tank is pressurised.',
      'Ozone and gas breakdown products are why SF₆ handling procedures exist.',
    ],
    draw: t => {
      const n = 8;
      return (
        <g>
          <polygon points="40,68 70,76 40,84" fill="#1f2937" stroke="#f87171" strokeWidth="1.3" />
          {L(20, 60, '20–30 kV', '#f87171')}
          {Array.from({ length: n }, (_, i) => {
            const f = (saw(t, 0.7) + i / n) % 1;
            return <text key={i} x={70 + f * 46} y={76 + Math.sin(i * 2 + t * 3) * 10} fontSize="9" fill="#fde047" opacity={1 - f * 0.3}>+</text>;
          })}
          <rect x="122" y="26" width="20" height="100" fill="#0b1220" stroke="#475569" strokeWidth="1" />
          <line x1="126" y1="26" x2="126" y2="126" stroke="#64748b" strokeWidth="2" />
          <line x1="138" y1="26" x2="138" y2="126" stroke="#64748b" strokeWidth="2" />
          {Array.from({ length: 5 }, (_, i) => {
            const y = 126 - ((saw(t, 0.45) + i / 5) % 1) * 100;
            return <text key={i} x="127" y={y} fontSize="8" fill="#fde047">+</text>;
          })}
          {L(150, 44, 'belt carries charge up', '#94a3b8')}
          {L(10, 20, 'CORONA CHARGING', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'vd-terminal', group: 'van-de-graaff', tag: 'Terminal', hex: '#facc15',
    part: 'Terminal sphere & charge collection',
    summary: 'Charge transferred inside a hollow conductor migrates to its outer surface, so the terminal voltage keeps rising even though the incoming charge is delivered inside.',
    bullets: [
      'This is the electrostatic shielding property of conductors — the reason the machine works at all.',
      'Terminal voltage rises until leakage plus beam load equals the charging current.',
      'A generating voltmeter measures the terminal potential without touching it.',
      'The terminal houses the ion source (single-ended) or the stripper (tandem) and is serviced by opening the tank.',
      'Sphere surface finish matters: a scratch is a field concentration and a flashover site.',
    ],
    draw: t => {
      const v = 0.4 + 0.6 * ease01(saw(t, 0.25));
      return (
        <g>
          <ellipse cx="130" cy="70" rx="60" ry="42" fill="#111c2e" stroke="#facc15" strokeWidth="2" />
          {Array.from({ length: 14 }, (_, i) => {
            const a = (i / 14) * Math.PI * 2;
            return <text key={i} x={130 + Math.cos(a) * 60} y={70 + Math.sin(a) * 42} fontSize="8" fill="#fde047" opacity={v}>+</text>;
          })}
          <line x1="130" y1="112" x2="130" y2="136" stroke="#64748b" strokeWidth="8" />
          {L(88, 74, `${(v * 5).toFixed(1)} MV`, '#fde047', 12)}
          {L(10, 20, 'TERMINAL POTENTIAL', '#cbd5e1', 8)}
          {L(10, 140, 'charge resides on the outer surface', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'vd-column', group: 'van-de-graaff', tag: 'Column', hex: '#38bdf8',
    part: 'Grading rings & resistor chain',
    summary: 'The accelerating column is a stack of insulator sections with metal rings held at evenly spaced potentials by a resistor chain, so the field never concentrates.',
    bullets: [
      'Uniform gradient prevents local breakdown along the column surface.',
      'The chain also defines the equipotentials that shape the beam-focusing action of each gap.',
      'A single failed resistor distorts the gradient and usually triggers repeated sparking at that section.',
      'Corona rings at the ends manage the highest-stress region near the terminal.',
      'Sparking damage is cumulative: each flashover roughens the surface and lowers the next breakdown voltage.',
    ],
    draw: t => {
      const spark = saw(t, 0.3) > 0.86;
      return (
        <g>
          {Array.from({ length: 7 }, (_, i) => (
            <g key={i}>
              <rect x="86" y={26 + i * 15} width="88" height="9" rx="2" fill="#1f2937" stroke="#38bdf8" strokeWidth="1" />
              <rect x="178" y={28 + i * 15} width="16" height="6" rx="1" fill="#0b1220" stroke="#64748b" strokeWidth="0.8" />
            </g>
          ))}
          {L(198, 70, 'resistor', '#94a3b8')}
          {L(198, 80, 'chain', '#94a3b8')}
          <line x1="130" y1="26" x2="130" y2="132" stroke="#818cf8" strokeWidth="1.6" strokeDasharray="3 2" />
          {spark && <polyline points="86,60 74,66 82,74 70,82" fill="none" stroke="#f87171" strokeWidth="1.4" />}
          {L(10, 20, 'ACCELERATING COLUMN', '#cbd5e1', 8)}
          {L(10, 144, spark ? 'flashover — gradient upset' : 'uniform gradient, stable', spark ? '#f87171' : '#4ade80')}
        </g>
      );
    },
  },
  {
    id: 'vd-stripper', group: 'van-de-graaff', tag: 'Tandem', hex: '#f472b6',
    part: 'Stripper foil / gas canal',
    summary: 'At the terminal, the negative ion loses electrons in a thin carbon foil or a gas canal, becoming positive so the same voltage accelerates it a second time.',
    bullets: [
      'Final energy is <code>(1 + q) × V</code>, where q is the charge state after stripping.',
      'Gas strippers give lower charge states but far longer life; foils give higher q and higher final energy.',
      'Charge-state distribution is statistical — an analysing magnet downstream selects the wanted one.',
      'Foil thickness is a compromise between stripping efficiency and energy straggling.',
      'Foil breakage is a routine maintenance event on a busy AMS machine.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      const stripped = f > 0.5;
      return (
        <g>
          <line x1="20" y1="76" x2="240" y2="76" stroke="#334155" strokeWidth="8" />
          <ellipse cx="130" cy="76" rx="30" ry="22" fill="#111c2e" stroke="#facc15" strokeWidth="1.6" />
          <line x1="130" y1="58" x2="130" y2="94" stroke="#f472b6" strokeWidth="2" />
          {L(112, 44, 'stripper', '#f9a8d4')}
          <circle cx={20 + f * 220} cy="76" r="3" fill={stripped ? '#f472b6' : '#38bdf8'} />
          {L(20 + f * 220, 62, stripped ? 'A^q+' : 'A⁻', stripped ? '#f9a8d4' : '#7dd3fc', 7, 'middle')}
          {L(30, 116, '1st: attracted', '#38bdf8')}
          {L(160, 116, '2nd: repelled', '#f472b6')}
          {L(10, 20, 'TANDEM STRIPPING', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'vd-tank', group: 'van-de-graaff', tag: 'Insulation', hex: '#94a3b8',
    part: 'SF₆ pressure tank',
    summary: 'The whole column lives inside a vessel of sulphur hexafluoride at 5–10 bar, whose dielectric strength is several times that of air.',
    bullets: [
      'Air breaks down near 3 MV/m; pressurised SF₆ pushes terminals to roughly 25 MV.',
      'SF₆ is a potent greenhouse gas — recovery and recycling during tank opening is mandatory.',
      'Breakdown products after a spark are corrosive and toxic; the gas is filtered before reuse.',
      'Tank opening for terminal service is a half-day job dominated by gas handling.',
      'Moisture control matters as much as pressure: wet gas breaks down far sooner.',
    ],
    draw: t => {
      const p = 5 + 5 * (0.5 + 0.5 * osc(t, 0.15));
      return (
        <g>
          <rect x="30" y="34" width="200" height="86" rx="24" fill="#0b1220" stroke="#94a3b8" strokeWidth="1.8" />
          <ellipse cx="112" cy="76" rx="34" ry="24" fill="#111c2e" stroke="#facc15" strokeWidth="1.4" />
          {Array.from({ length: 16 }, (_, i) => {
            const a = (i / 16) * Math.PI * 2 + t * 0.6;
            return <circle key={i} cx={130 + Math.cos(a) * (72 + 10 * osc(t + i, 0.4))} cy={76 + Math.sin(a) * (34 + 5 * osc(t + i, 0.3))} r="1.6" fill="#38bdf8" opacity="0.55" />;
          })}
          {L(160, 66, 'SF₆', '#7dd3fc', 11)}
          {L(160, 82, `${p.toFixed(1)} bar`, '#94a3b8')}
          {L(10, 20, 'PRESSURE VESSEL', '#cbd5e1', 8)}
          {L(10, 140, 'dielectric strength ≈ 3× air at 1 bar', '#94a3b8')}
        </g>
      );
    },
  },
];

export const ACCELERATOR_PART_ANIMS: MicroAnim[] = [
  ...XRAY_TUBE_PARTS, ...LINAC_PARTS, ...BETATRON_PARTS,
  ...CYCLOTRON_PARTS, ...SYNCHROTRON_PARTS, ...VDG_PARTS,
];
