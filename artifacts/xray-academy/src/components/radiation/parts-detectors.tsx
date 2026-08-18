import type { MicroAnim } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// DETECTOR TECHNOLOGY animations — how radiation is actually received, converted
// and turned into a number. Every draw() renders inside a 260 × 150 viewBox.
// ═══════════════════════════════════════════════════════════════════════════════

const saw = (t: number, hz = 1) => (t * hz) % 1;
const osc = (t: number, hz = 1) => Math.sin(t * Math.PI * 2 * hz);
const L = (x: number, y: number, s: string, c = '#94a3b8', size = 7, a: 'start' | 'middle' | 'end' = 'start') => (
  <text x={x} y={y} fontSize={size} fill={c} textAnchor={a}>{s}</text>
);
/** incoming photon glyph */
const Photon = ({ x, y, c = '#fde047', r = 2.4 }: { x: number; y: number; c?: string; r?: number }) => (
  <g><circle cx={x} cy={y} r={r * 2.4} fill={c} opacity="0.15" /><circle cx={x} cy={y} r={r} fill={c} /></g>
);

export const DETECTOR_ANIMS: MicroAnim[] = [
  // ─── THE RECEPTION CHAIN ────────────────────────────────────────────────────
  {
    id: 'det-chain', group: 'detectors', tag: 'Signal chain', hex: '#4ade80',
    part: 'The reception chain — photon to number',
    summary: 'Every detector, whatever the technology, runs the same five stages: interact, convert, collect, amplify, digitise. Only the physics of the first two stages differs.',
    bullets: [
      '<b>Interact</b> — the photon must actually deposit energy; if it passes through, it is invisible.',
      '<b>Convert</b> — energy becomes light (scintillator) or charge (semiconductor / gas).',
      '<b>Collect</b> — an electric field sweeps the charge, or an optical path guides the light.',
      '<b>Amplify</b> — gas multiplication, dynode chain, avalanche, or a low-noise charge amplifier.',
      '<b>Digitise</b> — shaping, sampling and an ADC turn the pulse into a count or an intensity value.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      const stage = Math.floor(f * 5);
      const names = ['INTERACT', 'CONVERT', 'COLLECT', 'AMPLIFY', 'DIGITISE'];
      const cols = ['#fde047', '#38bdf8', '#a78bfa', '#f472b6', '#4ade80'];
      return (
        <g>
          {names.map((n, i) => (
            <g key={n} opacity={i === stage ? 1 : 0.35}>
              <rect x={12 + i * 48} y="56" width="42" height="34" rx="5" fill="#0b1220" stroke={cols[i]} strokeWidth={i === stage ? 1.6 : 1} />
              <text x={33 + i * 48} y="76" fontSize="5.6" fill={cols[i]} textAnchor="middle">{n}</text>
              {i < 4 && <line x1={54 + i * 48} y1="73" x2={60 + i * 48} y2="73" stroke="#334155" strokeWidth="1" />}
            </g>
          ))}
          <Photon x={12 + f * 232} y={36} />
          <polyline points={Array.from({ length: 50 }, (_, i) => {
            const x = 12 + i * 4.7;
            const pulse = Math.exp(-Math.pow((i - 10 - stage * 8) / 3, 2));
            return `${x},${126 - pulse * 22}`;
          }).join(' ')} fill="none" stroke={cols[stage]} strokeWidth="1.3" />
          {L(10, 20, 'HOW RADIATION IS RECEIVED', '#cbd5e1', 8)}
          {L(10, 144, 'same five stages in every detector ever built', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'det-interaction', group: 'detectors', tag: 'Signal chain', hex: '#fde047',
    part: 'Interaction — what the photon does on arrival',
    summary: 'A detected photon must undergo photoelectric absorption, Compton scattering or pair production inside the sensitive volume. Anything else and the photon is simply lost.',
    bullets: [
      'Photoelectric absorption deposits the full energy — ideal for spectroscopy, dominant at low keV and high Z.',
      'Compton scattering deposits only part of the energy and creates the Compton continuum in a spectrum.',
      'Pair production only starts above 1.022 MeV and adds escape peaks at 511 keV intervals.',
      'Detection efficiency = probability of interacting at all; energy resolution = how cleanly it is measured.',
      'This is why high-Z, high-density scintillators dominate gamma work and silicon dominates low-energy work.',
    ],
    draw: t => {
      const mode = Math.floor(saw(t, 0.2) * 3);
      const f = saw(t, 0.6);
      return (
        <g>
          <rect x="90" y="34" width="120" height="92" rx="6" fill="#111c2e" stroke="#475569" strokeWidth="1.3" />
          {L(90, 28, 'sensitive volume', '#94a3b8')}
          <Photon x={20 + Math.min(f, 0.5) * 130} y={79} />
          {f > 0.5 && mode === 0 && (<>
            <circle cx="150" cy="79" r={(f - 0.5) * 60} fill="#fde047" opacity={0.5 - (f - 0.5)} />
            {L(150, 112, 'PHOTOELECTRIC — full energy', '#fde047', 6.5, 'middle')}
          </>)}
          {f > 0.5 && mode === 1 && (<>
            <line x1="150" y1="79" x2={150 + (f - 0.5) * 110} y2={79 - (f - 0.5) * 70} stroke="#fde047" strokeWidth="1.2" />
            <circle cx="150" cy="79" r="4" fill="#38bdf8" />
            {L(150, 112, 'COMPTON — partial deposit', '#38bdf8', 6.5, 'middle')}
          </>)}
          {f > 0.5 && mode === 2 && (<>
            <line x1="150" y1="79" x2={150 + (f - 0.5) * 90} y2={79 - (f - 0.5) * 46} stroke="#4ade80" strokeWidth="1.2" />
            <line x1="150" y1="79" x2={150 + (f - 0.5) * 90} y2={79 + (f - 0.5) * 46} stroke="#f472b6" strokeWidth="1.2" />
            {L(150, 112, 'PAIR PRODUCTION > 1.022 MeV', '#f472b6', 6.5, 'middle')}
          </>)}
          {L(10, 20, 'INTERACTION MECHANISMS', '#cbd5e1', 8)}
        </g>
      );
    },
  },

  // ─── GAS DETECTORS ──────────────────────────────────────────────────────────
  {
    id: 'det-ionchamber', group: 'detectors', tag: 'Gas-filled', hex: '#38bdf8',
    part: 'Ionisation chamber',
    summary: 'Radiation ionises the fill gas and a modest field collects the ion pairs before they recombine. No internal gain — the current is directly proportional to dose rate.',
    bullets: [
      'Operates in the saturation region: enough field to collect everything, not enough to multiply.',
      'Output current is small (picoamps), so it needs a good electrometer — but it never saturates in an intense field.',
      'This is why ion chambers, not GM tubes, are trusted for high dose-rate radiography surveys.',
      'Sealed, temperature- and pressure-compensated chambers are the reference for beam dosimetry.',
      'Transmission chambers in a LINAC head are ion chambers monitoring dose in real time.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      return (
        <g>
          <rect x="46" y="42" width="168" height="66" rx="10" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.5" />
          <line x1="60" y1="52" x2="200" y2="52" stroke="#f87171" strokeWidth="2" />
          <line x1="60" y1="98" x2="200" y2="98" stroke="#4ade80" strokeWidth="2" />
          {L(206, 54, '+HV', '#fca5a5')}
          {L(206, 102, 'GND', '#86efac')}
          <Photon x={24 + f * 100} y={75} />
          {f > 0.45 && Array.from({ length: 5 }, (_, i) => {
            const g = (f - 0.45) * 2;
            return (
              <g key={i}>
                <circle cx={124 + i * 12} cy={75 - g * 20} r="1.8" fill="#60a5fa" />
                <circle cx={124 + i * 12} cy={75 + g * 20} r="1.8" fill="#f87171" />
              </g>
            );
          })}
          {L(96, 128, 'ion pairs collected — no multiplication', '#7dd3fc')}
          {L(10, 20, 'IONISATION CHAMBER', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-proportional', group: 'detectors', tag: 'Gas-filled', hex: '#a78bfa',
    part: 'Proportional counter & gas avalanche',
    summary: 'Raise the field near a thin anode wire and each primary electron triggers an avalanche — thousands of times more charge, still proportional to the energy deposited.',
    bullets: [
      'Gas gain of 10³–10⁵ makes single-photon counting practical while keeping energy information.',
      'The avalanche happens within a few wire radii, so the geometry does the amplification, not electronics.',
      'This is the working principle of the He-3 and B-10 neutron tubes used in portal monitors.',
      'Gas purity matters: electronegative contaminants capture electrons and kill the proportionality.',
      'Push the voltage further and proportionality is lost — that is the Geiger region.',
    ],
    draw: t => {
      const f = saw(t, 0.55);
      const av = f > 0.55;
      return (
        <g>
          <rect x="40" y="40" width="180" height="70" rx="34" fill="#0b1220" stroke="#a78bfa" strokeWidth="1.5" />
          <line x1="52" y1="75" x2="208" y2="75" stroke="#c4b5fd" strokeWidth="1.4" />
          {L(96, 34, 'anode wire (thin → high field)', '#c4b5fd')}
          <Photon x={22 + Math.min(f, 0.5) * 120} y={58} />
          {f > 0.5 && !av && <circle cx="140" cy="62" r="2" fill="#60a5fa" />}
          {av && Array.from({ length: 14 }, (_, i) => {
            const a = (i / 14) * Math.PI * 2;
            const r = (f - 0.55) * 40;
            return <circle key={i} cx={140 + Math.cos(a) * r} cy={75 + Math.sin(a) * r * 0.5} r="1.5" fill="#a78bfa" />;
          })}
          <polyline points={Array.from({ length: 46 }, (_, i) => {
            const x = 40 + i * 4;
            const p = av ? Math.exp(-Math.pow((i - 22) / 3, 2)) : 0;
            return `${x},${132 - p * 24}`;
          }).join(' ')} fill="none" stroke="#a78bfa" strokeWidth="1.3" />
          {L(10, 20, 'PROPORTIONAL COUNTER', '#cbd5e1', 8)}
          {L(176, 128, 'gain 10³–10⁵', '#c4b5fd')}
        </g>
      );
    },
  },
  {
    id: 'det-gm', group: 'detectors', tag: 'Gas-filled', hex: '#f87171',
    part: 'Geiger–Müller tube & dead time',
    summary: 'At high enough voltage one ionisation triggers a full discharge along the whole anode. Every event gives the same big pulse — easy to count, but all energy information is gone.',
    bullets: [
      'Output pulse is independent of the photon energy — a GM tube counts, it does not measure spectra.',
      'A quench gas (halogen or organic) stops the discharge so the tube can recover.',
      'Dead time of 50–300 µs means a GM tube reads LOW in an intense field — the dangerous failure mode.',
      'For that reason radiography surveys near a projector use an ion chamber, not just a GM survey meter.',
      'Cheap, rugged and audible — still the right tool for contamination hunting and general area survey.',
    ],
    draw: t => {
      const f = saw(t, 0.7);
      const dead = f > 0.45 && f < 0.72;
      return (
        <g>
          <rect x="40" y="46" width="176" height="60" rx="28" fill="#0b1220" stroke={dead ? '#7f1d1d' : '#f87171'} strokeWidth="1.5" />
          <line x1="52" y1="76" x2="204" y2="76" stroke="#fca5a5" strokeWidth="1.4" />
          {f < 0.45 && <Photon x={22 + f * 240} y={62} />}
          {dead && Array.from({ length: 24 }, (_, i) => (
            <circle key={i} cx={56 + i * 6.4} cy={76 + Math.sin(i) * 8} r="1.6" fill="#f87171" opacity="0.8" />
          ))}
          {dead && L(128, 128, `DEAD TIME — blind`, '#f87171', 7, 'middle')}
          <polyline points={Array.from({ length: 60 }, (_, i) => {
            const x = 22 + i * 3.9;
            const hit = ((i / 60 * 3 + t * 0.7) % 1);
            return `${x},${hit < 0.06 ? 116 : 138}`;
          }).join(' ')} fill="none" stroke="#f87171" strokeWidth="1.2" />
          {L(10, 20, 'GEIGER–MÜLLER', '#cbd5e1', 8)}
          {L(10, 40, 'all pulses identical — no spectroscopy', '#fca5a5', 6.5)}
        </g>
      );
    },
  },

  // ─── SCINTILLATION ──────────────────────────────────────────────────────────
  {
    id: 'det-pmt', group: 'detectors', tag: 'Scintillation', hex: '#22d3ee',
    part: 'Photomultiplier tube (PMT) — dynode chain',
    summary: 'Scintillation light releases a photoelectron from a photocathode; a chain of dynodes multiplies it by a factor of a million, producing a large clean pulse.',
    bullets: [
      'Gain of 10⁶–10⁷ from 8–12 dynode stages, each biased a hundred or so volts above the last.',
      'Extremely low noise: the first amplification stage is essentially noise-free.',
      'Gain depends steeply on HV — supply stability directly becomes energy-resolution stability.',
      'Bulky, fragile, and useless in a magnetic field, which is why SiPMs are displacing it.',
      'Still the reference for NaI(Tl) spectroscopy and large-area plastic scintillator panels.',
    ],
    draw: t => {
      const f = saw(t, 0.55);
      const stage = Math.floor(f * 7);
      return (
        <g>
          <rect x="14" y="52" width="26" height="46" rx="3" fill="#0d2018" stroke="#22c55e" strokeWidth="1.2" />
          {L(10, 46, 'scint.', '#86efac')}
          {f < 0.18 && <Photon x={4 + f * 120} y={75} />}
          <line x1="40" y1="52" x2="40" y2="98" stroke="#22d3ee" strokeWidth="2.4" />
          {L(34, 116, 'photocathode', '#67e8f9', 6)}
          {Array.from({ length: 6 }, (_, i) => (
            <line key={i} x1={62 + i * 26} y1={i % 2 ? 52 : 98} x2={78 + i * 26} y2={i % 2 ? 74 : 76}
              stroke={stage > i ? '#67e8f9' : '#334155'} strokeWidth="2.2" />
          ))}
          {Array.from({ length: Math.min(28, Math.pow(2, stage)) }, (_, i) => {
            const px = 44 + stage * 26 + (i % 6) * 3;
            const py = 62 + (i % 9) * 3;
            return <circle key={i} cx={px} cy={py} r="1.3" fill="#60a5fa" opacity="0.85" />;
          })}
          <rect x="222" y="58" width="18" height="34" rx="3" fill="#0b1220" stroke="#a78bfa" strokeWidth="1.2" />
          {L(214, 106, 'anode', '#c4b5fd', 6)}
          {L(10, 20, 'PMT DYNODE CHAIN', '#cbd5e1', 8)}
          {L(150, 34, `gain ≈ 10^${Math.min(7, stage + 1)}`, '#67e8f9')}
        </g>
      );
    },
  },
  {
    id: 'det-nai', group: 'detectors', tag: 'Scintillation', hex: '#fbbf24',
    part: 'NaI(Tl) scintillator & pulse-height spectrum',
    summary: 'Thallium-doped sodium iodide converts about 38 photons of visible light per keV deposited. The pulse height is proportional to energy, so the histogram is a gamma spectrum.',
    bullets: [
      'High density and high Z give excellent gamma detection efficiency for the price.',
      'Energy resolution around 6–7 % at 662 keV — enough to identify common isotopes.',
      'Hygroscopic: the crystal must be hermetically sealed or it fogs and dies.',
      'The spectrum shows a photopeak plus a Compton continuum and edge — both are physics, not noise.',
      'For high resolution, HPGe replaces it; for cost and ruggedness, NaI still wins.',
    ],
    draw: t => {
      const ph = t * 2;
      const spec = Array.from({ length: 60 }, (_, i) => {
        const e = i / 59;
        const compton = e < 0.66 ? 0.35 * Math.exp(-Math.pow((e - 0.3) / 0.35, 2)) : 0;
        const peak = 0.95 * Math.exp(-Math.pow((e - 0.82) / 0.045, 2));
        const v = (compton + peak) * (0.92 + 0.08 * Math.sin(ph + i));
        return `${34 + i * 3.5},${(126 - v * 76).toFixed(1)}`;
      }).join(' ');
      return (
        <g>
          <rect x="14" y="42" width="16" height="40" rx="3" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.2" />
          {L(8, 36, 'NaI(Tl)', '#fbbf24')}
          {Array.from({ length: 4 }, (_, i) => (
            <circle key={i} cx={22 + Math.cos(t * 3 + i) * 6} cy={62 + Math.sin(t * 3 + i) * 12} r="1.4" fill="#67e8f9" />
          ))}
          <line x1="34" y1="126" x2="244" y2="126" stroke="#334155" />
          <polyline points={spec} fill="none" stroke="#fbbf24" strokeWidth="1.4" />
          {L(196, 48, 'photopeak', '#fbbf24', 6.5)}
          {L(80, 96, 'Compton continuum', '#94a3b8', 6.5)}
          {L(34, 138, '0', '#64748b')}
          {L(238, 138, 'E', '#64748b')}
          {L(10, 20, 'PULSE-HEIGHT SPECTRUM', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-sipm', group: 'detectors', tag: 'Scintillation', hex: '#4ade80',
    part: 'Silicon photomultiplier (SiPM)',
    summary: 'Thousands of tiny avalanche cells run in Geiger mode in parallel. Each fired cell contributes a fixed charge, so the summed output counts how many photons arrived.',
    bullets: [
      'Comparable gain to a PMT (10⁵–10⁶) at a few tens of volts instead of a kilovolt.',
      'Immune to magnetic fields, physically tiny, and mechanically rugged.',
      'Dark count rate and temperature-dependent gain are the main design headaches.',
      'Saturates when photon count approaches cell count — the response is inherently non-linear at the top.',
      'Now standard in PET, handheld spectrometers and new-generation portal monitors.',
    ],
    draw: t => {
      const f = saw(t, 0.7);
      const fired = Math.floor(f * 24);
      return (
        <g>
          <rect x="20" y="40" width="30" height="60" rx="3" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.2" />
          {L(14, 34, 'scintillator', '#fbbf24')}
          {Array.from({ length: 6 }, (_, i) => (
            <circle key={i} cx={52 + ((f * 3 + i / 6) % 1) * 46} cy={52 + i * 9} r="1.5" fill="#67e8f9" />
          ))}
          {Array.from({ length: 36 }, (_, i) => {
            const cx = 108 + (i % 6) * 17, cy = 44 + Math.floor(i / 6) * 15;
            const on = i < fired;
            return <rect key={i} x={cx} y={cy} width="14" height="12" rx="2" fill={on ? '#4ade80' : '#0b1220'} stroke={on ? '#86efac' : '#334155'} strokeWidth="0.8" opacity={on ? 0.9 : 1} />;
          })}
          {L(106, 146, `${fired} cells fired — charge ∝ photon count`, '#86efac')}
          {L(10, 20, 'SiPM ARRAY', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-photodiode', group: 'detectors', tag: 'Scintillation', hex: '#38bdf8',
    part: 'Scintillator + photodiode element',
    summary: 'The workhorse of security and CT line-scan detectors: a small scintillator crystal glued to a silicon photodiode, read as a current rather than counted as pulses.',
    bullets: [
      'Scintillators: CsI(Tl) for tubes, CdWO₄ or ceramic GOS for high-energy cargo systems.',
      'The photodiode integrates charge over the line period — an intensity value, not a photon count.',
      'Optical isolation between elements (reflective septa) is what stops cross-talk blurring the image.',
      'Dark current drifts with temperature, so an offset (dark) calibration runs regularly.',
      'Cheap, linear over a huge dynamic range, and easy to tile into arrays of thousands.',
    ],
    draw: t => {
      const f = saw(t, 0.6);
      return (
        <g>
          {Array.from({ length: 5 }, (_, i) => (
            <g key={i}>
              <rect x={40 + i * 40} y="34" width="30" height="34" rx="3" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.1" />
              <rect x={40 + i * 40} y="70" width="30" height="20" rx="2" fill="#0b1b34" stroke="#38bdf8" strokeWidth="1.1" />
              <line x1={38 + i * 40} y1="34" x2={38 + i * 40} y2="90" stroke="#94a3b8" strokeWidth="1.2" />
            </g>
          ))}
          <Photon x={95} y={10 + f * 24} />
          {f > 0.55 && Array.from({ length: 4 }, (_, i) => (
            <circle key={i} cx={88 + i * 5} cy={44 + (f - 0.55) * 50} r="1.3" fill="#67e8f9" />
          ))}
          {L(34, 28, 'scintillator', '#fbbf24', 6.5)}
          {L(34, 104, 'photodiode', '#7dd3fc', 6.5)}
          {L(34, 118, 'septa stop optical cross-talk', '#94a3b8', 6.5)}
          {L(10, 20, 'INDIRECT ELEMENT', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-dab', group: 'detectors', tag: 'Arrays', hex: '#22c55e',
    part: 'Detector Array Board (DAB)',
    summary: 'The field-replaceable module in a screening tunnel: a row of scintillator-photodiode elements plus the analogue front end, multiplexer and ADC on one board.',
    bullets: [
      'Boards are daisy-chained along the L-shaped array; each carries its own calibration data.',
      'One failed board shows as a contiguous band of dead columns in the image — easy to localise.',
      'Gain and offset are stored per channel; replacing a board requires a recalibration run.',
      'Serial digital output means only a few wires leave the array, cutting noise pickup.',
      'DAB alignment relative to the fan beam is a service adjustment, not a factory-only setting.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      const bad = f > 0.55;
      return (
        <g>
          <rect x="18" y="40" width="176" height="52" rx="4" fill="#08150f" stroke="#22c55e" strokeWidth="1.4" />
          {Array.from({ length: 16 }, (_, i) => (
            <rect key={i} x={24 + i * 10.6} y="46" width="8" height="16" rx="1.5" fill="#3f2a12" stroke="#f59e0b" strokeWidth="0.6" />
          ))}
          {Array.from({ length: 16 }, (_, i) => (
            <rect key={i} x={24 + i * 10.6} y="64" width="8" height="10" rx="1.5"
              fill={bad && i > 5 && i < 10 ? '#3f0b0b' : '#0b1b34'} stroke={bad && i > 5 && i < 10 ? '#f87171' : '#38bdf8'} strokeWidth="0.6" />
          ))}
          <rect x="24" y="78" width="60" height="9" rx="2" fill="#0b1220" stroke="#64748b" strokeWidth="0.7" />
          {L(26, 85, 'MUX + ADC', '#94a3b8', 5.5)}
          <rect x="94" y="78" width="42" height="9" rx="2" fill="#0b1220" stroke="#64748b" strokeWidth="0.7" />
          {L(96, 85, 'CAL EEPROM', '#94a3b8', 5.5)}
          <line x1="194" y1="66" x2="240" y2="66" stroke="#22c55e" strokeWidth="1.4" />
          {L(200, 60, 'serial out', '#86efac', 6)}
          <rect x="18" y="100" width="176" height="34" rx="3" fill="#0b1220" stroke="#334155" strokeWidth="1" />
          {Array.from({ length: 16 }, (_, i) => (
            <rect key={i} x={24 + i * 10.6} y="104" width="8" height="26"
              fill={bad && i > 5 && i < 10 ? '#1f2937' : '#e2e8f0'} opacity={bad && i > 5 && i < 10 ? 1 : 0.35 + 0.35 * Math.abs(Math.sin(t + i))} />
          ))}
          {L(10, 20, 'DETECTOR ARRAY BOARD', '#cbd5e1', 8)}
          {L(200, 122, bad ? 'dead band → replace DAB' : 'all channels live', bad ? '#f87171' : '#86efac', 6)}
        </g>
      );
    },
  },
  {
    id: 'det-plastic', group: 'detectors', tag: 'Scintillation', hex: '#a78bfa',
    part: 'Large plastic scintillator panel',
    summary: 'Cheap polyvinyltoluene panels of a square metre or more, viewed by PMTs at the edges — maximum sensitivity per dollar for detecting that something radioactive went past.',
    bullets: [
      'Low effective atomic number means good sensitivity but essentially no spectroscopic capability.',
      'Used in radiation portal monitors where the question is "is there a source?", not "which isotope?".',
      'Alarm logic compares count rate against a continuously updated background estimate.',
      'A dense cargo load suppresses background and can itself trigger a nuisance alarm.',
      'Positive alarms go to secondary inspection with a handheld spectroscopic identifier.',
    ],
    draw: t => {
      const hot = saw(t, 0.35) > 0.55;
      return (
        <g>
          <rect x="40" y="34" width="60" height="94" rx="4" fill="#1e1b4b" stroke="#a78bfa" strokeWidth="1.4" opacity="0.75" />
          <rect x="164" y="34" width="60" height="94" rx="4" fill="#1e1b4b" stroke="#a78bfa" strokeWidth="1.4" opacity="0.75" />
          <ellipse cx="70" cy="30" rx="10" ry="6" fill="#0b1220" stroke="#22d3ee" strokeWidth="1" />
          <ellipse cx="194" cy="30" rx="10" ry="6" fill="#0b1220" stroke="#22d3ee" strokeWidth="1" />
          {L(56, 22, 'PMT', '#67e8f9', 6)}
          <rect x="108" y="66" width="48" height="30" rx="3" fill="#111c2e" stroke="#94a3b8" strokeWidth="1" />
          {hot && <circle cx="132" cy="81" r={5 + 3 * Math.abs(osc(t, 2))} fill="#f97316" />}
          {hot && Array.from({ length: 8 }, (_, i) => {
            const a = (i / 8) * Math.PI * 2;
            return <line key={i} x1="132" y1="81" x2={132 + Math.cos(a) * 44} y2={81 + Math.sin(a) * 34} stroke="#fbbf24" strokeWidth="0.7" opacity="0.5" />;
          })}
          {L(10, 20, 'PORTAL PANEL', '#cbd5e1', 8)}
          {L(96, 142, hot ? 'ALARM — count rate over background' : 'monitoring background', hot ? '#f87171' : '#86efac', 6.5)}
        </g>
      );
    },
  },

  // ─── SEMICONDUCTOR ──────────────────────────────────────────────────────────
  {
    id: 'det-cdte', group: 'detectors', tag: 'Semiconductor', hex: '#f472b6',
    part: 'Direct conversion — CdTe / CZT',
    summary: 'The photon creates electron-hole pairs directly in the semiconductor. No light stage means no optical spread, so spatial and energy resolution are both excellent.',
    bullets: [
      'About 4.4 eV per electron-hole pair in CdTe versus roughly 100 eV per detected photoelectron via a scintillator.',
      'More charge carriers per keV means much better energy resolution — real spectroscopy at room temperature.',
      'High Z and density give good stopping power for hard X-rays, unlike silicon.',
      'Hole trapping causes polarisation and tailing; periodic bias reset is a real operational requirement.',
      'This is the sensor behind photon-counting CT and portable isotope identifiers.',
    ],
    draw: t => {
      const f = saw(t, 0.6);
      return (
        <g>
          <rect x="60" y="40" width="140" height="66" rx="4" fill="#2a0b2e" stroke="#f472b6" strokeWidth="1.4" />
          <line x1="60" y1="40" x2="200" y2="40" stroke="#f87171" strokeWidth="2.4" />
          <line x1="60" y1="106" x2="200" y2="106" stroke="#4ade80" strokeWidth="2.4" />
          {L(206, 44, '+HV', '#fca5a5')}
          {L(10, 34, 'CdTe / CZT', '#f9a8d4')}
          <Photon x={30 + Math.min(f, 0.4) * 100} y={73} />
          {f > 0.4 && Array.from({ length: 7 }, (_, i) => {
            const g = (f - 0.4) * 1.7;
            return (
              <g key={i}>
                <circle cx={118 + i * 8} cy={73 - g * 30} r="1.6" fill="#60a5fa" />
                <circle cx={118 + i * 8} cy={73 + g * 30} r="1.6" fill="#f87171" />
              </g>
            );
          })}
          <polyline points={Array.from({ length: 40 }, (_, i) => {
            const x = 60 + i * 3.5;
            const p = f > 0.55 ? Math.exp(-Math.pow((i - 18) / 2.4, 2)) : 0;
            return `${x},${134 - p * 22}`;
          }).join(' ')} fill="none" stroke="#f472b6" strokeWidth="1.3" />
          {L(10, 20, 'DIRECT CONVERSION', '#cbd5e1', 8)}
          {L(150, 128, '≈ 4.4 eV / e-h pair', '#f9a8d4', 6.5)}
        </g>
      );
    },
  },
  {
    id: 'det-hpge', group: 'detectors', tag: 'Semiconductor', hex: '#22d3ee',
    part: 'HPGe — high-purity germanium spectroscopy',
    summary: 'The reference for gamma spectroscopy: resolution around 0.2 % separates lines that NaI merges into one bump — at the price of liquid-nitrogen or electromechanical cooling.',
    bullets: [
      'Only 2.96 eV per electron-hole pair, so the statistical spread on the charge is tiny.',
      'Resolution of about 1.8 keV at 1332 keV versus roughly 45 keV for NaI(Tl).',
      'Must be cooled to about 90 K or thermal generation swamps the signal.',
      'Used for nuclear forensics, safeguards verification and environmental measurement.',
      'Field-portable versions with mechanical coolers now exist but remain heavy and power-hungry.',
    ],
    draw: t => {
      const ph = t * 2;
      const line = (c: number, w: number, col: string) => Array.from({ length: 70 }, (_, i) => {
        const v = Math.exp(-Math.pow((i - c) / w, 2));
        return `${34 + i * 3},${(122 - v * 70 * (0.92 + 0.08 * Math.sin(ph + i))).toFixed(1)}`;
      }).join(' ');
      return (
        <g>
          <rect x="14" y="46" width="20" height="46" rx="4" fill="#0b1b34" stroke="#22d3ee" strokeWidth="1.2" />
          {L(8, 40, 'HPGe @ 90 K', '#67e8f9', 6.5)}
          {Array.from({ length: 3 }, (_, i) => (
            <line key={i} x1="18" y1={100 + i * 6} x2="30" y2={100 + i * 6} stroke="#38bdf8" strokeWidth="1" opacity="0.5" />
          ))}
          <line x1="34" y1="122" x2="244" y2="122" stroke="#334155" />
          <polyline points={line(28, 1.6, '#22d3ee')} fill="none" stroke="#22d3ee" strokeWidth="1.3" />
          <polyline points={line(34, 1.6, '#22d3ee')} fill="none" stroke="#22d3ee" strokeWidth="1.3" />
          <polyline points={line(31, 9, '#64748b')} fill="none" stroke="#64748b" strokeWidth="1.1" strokeDasharray="3 2" />
          {L(150, 48, 'HPGe resolves both lines', '#67e8f9', 6.5)}
          {L(150, 62, 'NaI merges them (dashed)', '#64748b', 6.5)}
          {L(10, 20, 'HIGH-RESOLUTION SPECTROSCOPY', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-asi', group: 'detectors', tag: 'Arrays', hex: '#4ade80',
    part: 'a-Si TFT flat panel (indirect)',
    summary: 'A caesium-iodide needle layer converts X-rays to light directly above an amorphous-silicon thin-film-transistor array that stores and reads the charge pixel by pixel.',
    bullets: [
      'CsI grows in needles that pipe light down to the pixel, keeping resolution far better than a powder screen.',
      'Each pixel is a photodiode plus a switching TFT; gate lines read one row at a time.',
      'Dynamic range above 10⁴ means one exposure covers thick and thin sections together.',
      'Bad-pixel maps, offset and gain calibration are mandatory and periodic, not one-off.',
      'This is the standard detector for digital radiography, both medical and industrial.',
    ],
    draw: t => {
      const row = Math.floor(saw(t, 0.7) * 5);
      return (
        <g>
          <rect x="30" y="30" width="200" height="16" rx="2" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.1" />
          {Array.from({ length: 20 }, (_, i) => <line key={i} x1={34 + i * 10} y1="30" x2={34 + i * 10} y2="46" stroke="#fbbf24" strokeWidth="0.5" opacity="0.5" />)}
          {L(30, 24, 'CsI needle layer', '#fbbf24', 6.5)}
          {Array.from({ length: 25 }, (_, i) => {
            const r = Math.floor(i / 5), c = i % 5;
            const reading = r === row;
            return (
              <g key={i}>
                <rect x={44 + c * 36} y={54 + r * 15} width="30" height="12" rx="2"
                  fill={reading ? '#14301c' : '#0b1220'} stroke={reading ? '#4ade80' : '#334155'} strokeWidth="0.8" />
              </g>
            );
          })}
          <line x1="34" y1={60 + row * 15} x2="228" y2={60 + row * 15} stroke="#4ade80" strokeWidth="1" opacity="0.6" />
          {L(228, 60 + row * 15, '◄ gate', '#86efac', 6)}
          {L(10, 20, 'a-Si TFT PANEL', '#cbd5e1', 8)}
          {L(10, 144, 'row-by-row readout · DR > 10⁴', '#86efac')}
        </g>
      );
    },
  },
  {
    id: 'det-ase', group: 'detectors', tag: 'Arrays', hex: '#a855f7',
    part: 'a-Se flat panel (direct)',
    summary: 'Amorphous selenium converts X-rays straight to charge under a strong field. The charge travels along field lines with almost no lateral spread, so resolution is limited only by pixel pitch.',
    bullets: [
      'No light stage at all — no optical blur, the sharpest of the flat-panel technologies.',
      'Needs a high bias field (around 10 V/µm) across the selenium layer.',
      'Low atomic number limits absorption at higher energies, so it favours mammography-range work.',
      'Temperature sensitive: selenium crystallises if it gets too warm, permanently ruining the panel.',
      'Chosen where resolution dominates the requirement and beam energy is modest.',
    ],
    draw: t => {
      const f = saw(t, 0.55);
      return (
        <g>
          <rect x="34" y="34" width="192" height="46" rx="3" fill="#2a0b2e" stroke="#a855f7" strokeWidth="1.3" />
          <line x1="34" y1="34" x2="226" y2="34" stroke="#f87171" strokeWidth="2" />
          {L(34, 28, 'a-Se + bias electrode', '#d8b4fe', 6.5)}
          <Photon x={130} y={4 + f * 30} />
          {f > 0.35 && Array.from({ length: 5 }, (_, i) => (
            <circle key={i} cx={128 + (i - 2) * 1.2} cy={40 + (f - 0.35) * 70} r="1.5" fill="#c084fc" />
          ))}
          {[0, 1].map(k => (
            <line key={k} x1={118 + k * 24} y1="36" x2={118 + k * 24} y2="80" stroke="#64748b" strokeWidth="0.6" strokeDasharray="2 2" />
          ))}
          {Array.from({ length: 8 }, (_, i) => (
            <rect key={i} x={38 + i * 24} y="82" width="20" height="14" rx="2"
              fill={i === 3 && f > 0.85 ? '#3b0764' : '#0b1220'} stroke="#a855f7" strokeWidth="0.8" />
          ))}
          {L(34, 112, 'charge lands on one pixel — no light spread', '#d8b4fe', 6.5)}
          {L(10, 20, 'DIRECT FLAT PANEL', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-cr', group: 'detectors', tag: 'Storage', hex: '#38bdf8',
    part: 'Computed radiography imaging plate',
    summary: 'A photostimulable phosphor stores the latent image as trapped electrons; a scanning laser releases them as blue light which a PMT reads, then a bright lamp erases the plate for reuse.',
    bullets: [
      'Europium-doped barium fluorobromide traps electrons in colour centres proportional to the dose.',
      'Read-out is mechanical and takes tens of seconds — much slower than a flat panel.',
      'Plates are flexible and cheap, so CR survives where a rigid panel will not fit or would be damaged.',
      'The latent image fades over hours: read the plate promptly or lose signal.',
      'Incomplete erasure leaves ghost images from the previous exposure.',
    ],
    draw: t => {
      const f = saw(t, 0.35);
      const scanX = 40 + f * 160;
      return (
        <g>
          <rect x="34" y="52" width="176" height="46" rx="3" fill="#0b1b34" stroke="#38bdf8" strokeWidth="1.3" />
          {Array.from({ length: 24 }, (_, i) => {
            const x = 40 + i * 7;
            const read = x < scanX;
            return <circle key={i} cx={x} cy={62 + (i % 3) * 12} r="1.8" fill={read ? '#1f2937' : '#fbbf24'} />;
          })}
          <line x1={scanX} y1="46" x2={scanX} y2="104" stroke="#f87171" strokeWidth="1.4" />
          {L(scanX - 16, 42, 'laser', '#fca5a5', 6.5)}
          {Array.from({ length: 3 }, (_, i) => (
            <line key={i} x1={scanX} y1={62 + i * 12} x2="226" y2={34 + i * 6} stroke="#67e8f9" strokeWidth="0.8" opacity="0.6" />
          ))}
          <rect x="222" y="26" width="16" height="26" rx="3" fill="#0b1220" stroke="#22d3ee" strokeWidth="1.1" />
          {L(212, 20, 'PMT', '#67e8f9', 6)}
          {L(34, 122, 'trapped electrons → stimulated blue light → erase → reuse', '#7dd3fc', 6.5)}
          {L(10, 20, 'PHOTOSTIMULABLE PLATE', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-film', group: 'detectors', tag: 'Storage', hex: '#94a3b8',
    part: 'Silver-halide film',
    summary: 'Photons and photoelectrons reduce silver halide grains to a latent image; development amplifies each struck grain by a factor of about a billion into visible metallic silver.',
    bullets: [
      'Development is the amplification stage — a handful of atoms becomes a whole grain of silver.',
      'The characteristic (H&D) curve defines toe, straight-line latitude and shoulder.',
      'Film class (EN ISO 11699 C4–C7) trades speed against grain and therefore against detail.',
      'Processing chemistry, temperature and time are as much part of image quality as the exposure.',
      'Still the archival reference in some codes because the record is physical and self-contained.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      const dev = f > 0.5;
      return (
        <g>
          <rect x="30" y="36" width="110" height="80" rx="3" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.2" />
          {Array.from({ length: 30 }, (_, i) => {
            const x = 36 + (i % 6) * 18, y = 44 + Math.floor(i / 6) * 14;
            const hit = (i * 37) % 5 < 2;
            return <circle key={i} cx={x} cy={y} r={dev && hit ? 4.5 : 2} fill={dev && hit ? '#e2e8f0' : hit ? '#64748b' : '#334155'} />;
          })}
          {L(30, 30, dev ? 'developed silver' : 'latent image', dev ? '#e2e8f0' : '#94a3b8', 6.5)}
          <line x1="156" y1="116" x2="244" y2="116" stroke="#334155" />
          <line x1="156" y1="116" x2="156" y2="36" stroke="#334155" />
          <polyline points={Array.from({ length: 40 }, (_, i) => {
            const x = i / 39;
            const d = 1 / (1 + Math.exp(-(x - 0.5) * 9));
            return `${156 + x * 88},${116 - d * 72}`;
          }).join(' ')} fill="none" stroke="#cbd5e1" strokeWidth="1.3" />
          {L(160, 34, 'H&D curve', '#cbd5e1', 6.5)}
          {L(158, 128, 'log exposure', '#64748b', 6)}
          {L(10, 20, 'FILM', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-tld', group: 'detectors', tag: 'Dosimetry', hex: '#fbbf24',
    part: 'TLD / OSL personal dosimeter',
    summary: 'Radiation traps electrons in a crystal; later, heat (TLD) or light (OSL) releases them and the emitted glow is proportional to the dose the wearer received.',
    bullets: [
      'LiF:Mg,Ti is nearly tissue-equivalent, which is why it dominates personal dosimetry.',
      'The glow curve peaks identify which traps emptied — deep traps hold dose stably for months.',
      'OSL (Al₂O₃:C) can be re-read several times; TLD read-out is destructive.',
      'Filters over different elements of the badge let the reader estimate photon energy and radiation type.',
      'The badge is the legal dose of record; an electronic dosimeter is the real-time warning.',
    ],
    draw: t => {
      const f = saw(t, 0.35);
      const heating = f > 0.4;
      const T = 50 + f * 300;
      return (
        <g>
          <rect x="26" y="52" width="46" height="46" rx="5" fill="#0b1220" stroke="#fbbf24" strokeWidth="1.3" />
          {Array.from({ length: 8 }, (_, i) => (
            <circle key={i} cx={36 + (i % 4) * 10} cy={64 + Math.floor(i / 4) * 14} r="2" fill={heating ? '#1f2937' : '#fbbf24'} />
          ))}
          {L(24, 46, 'LiF chip', '#fbbf24', 6.5)}
          {heating && <circle cx="49" cy="75" r={16 * (f - 0.4)} fill="url(#fp-hot)" opacity="0.7" />}
          <line x1="86" y1="122" x2="246" y2="122" stroke="#334155" />
          <polyline points={Array.from({ length: 60 }, (_, i) => {
            const x = i / 59;
            const g1 = 0.4 * Math.exp(-Math.pow((x - 0.35) / 0.08, 2));
            const g2 = 0.95 * Math.exp(-Math.pow((x - 0.62) / 0.09, 2));
            return `${86 + x * 156},${122 - (g1 + g2) * 66}`;
          }).join(' ')} fill="none" stroke="#fbbf24" strokeWidth="1.3" />
          <line x1={86 + f * 156} y1="46" x2={86 + f * 156} y2="122" stroke="#f87171" strokeWidth="0.8" strokeDasharray="2 2" />
          {L(86, 42, `glow curve — ${T.toFixed(0)} °C`, '#fca5a5', 6.5)}
          {L(10, 20, 'THERMOLUMINESCENCE', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'det-preamp', group: 'detectors', tag: 'Signal chain', hex: '#a78bfa',
    part: 'Charge preamp, shaper & ADC',
    summary: 'The collected charge is integrated by a charge-sensitive preamplifier, shaped into a well-behaved pulse, then sampled — this electronics chain sets the noise floor of the whole detector.',
    bullets: [
      'The preamp sits as close to the sensor as physically possible; every millimetre of track adds capacitance and noise.',
      'Shaping time trades energy resolution against count-rate capability — long shaping means pile-up.',
      'Pile-up rejection and baseline restoration keep the spectrum clean at high flux.',
      'Equivalent noise charge (ENC) is the figure of merit, usually quoted in electrons RMS.',
      'In integrating detectors the same chain reads accumulated charge per line instead of per pulse.',
    ],
    draw: t => {
      const f = saw(t, 0.6);
      const fired = f > 0.25;
      return (
        <g>
          <rect x="16" y="60" width="30" height="34" rx="3" fill="#2a0b2e" stroke="#f472b6" strokeWidth="1.2" />
          {L(12, 54, 'sensor', '#f9a8d4', 6.5)}
          <polygon points="60,60 60,94 92,77" fill="#0b1220" stroke="#a78bfa" strokeWidth="1.2" />
          {L(56, 108, 'preamp', '#c4b5fd', 6.5)}
          <polygon points="106,60 106,94 138,77" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.2" />
          {L(104, 108, 'shaper', '#7dd3fc', 6.5)}
          <rect x="152" y="60" width="34" height="34" rx="4" fill="#0b1220" stroke="#4ade80" strokeWidth="1.2" />
          {L(158, 80, 'ADC', '#86efac', 7)}
          <rect x="200" y="60" width="44" height="34" rx="4" fill="#0b1220" stroke="#64748b" strokeWidth="1" />
          {L(206, 80, fired ? String(Math.round(600 + f * 300)) : '0000', '#e2e8f0', 8)}
          {/* step waveform */}
          <polyline points={Array.from({ length: 30 }, (_, i) => `${60 + i * 1.1},${44 - (fired && i > 6 ? 12 : 0) + (fired && i > 6 ? (i - 6) * 0.25 : 0)}`).join(' ')} fill="none" stroke="#a78bfa" strokeWidth="1.1" />
          <polyline points={Array.from({ length: 30 }, (_, i) => {
            const p = fired ? Math.exp(-Math.pow((i - 12) / 4, 2)) : 0;
            return `${106 + i * 1.1},${44 - p * 14}`;
          }).join(' ')} fill="none" stroke="#38bdf8" strokeWidth="1.1" />
          {L(10, 20, 'FRONT-END ELECTRONICS', '#cbd5e1', 8)}
          {L(10, 134, 'ENC (electrons RMS) sets the true noise floor', '#c4b5fd', 6.5)}
        </g>
      );
    },
  },
  {
    id: 'det-dqe', group: 'detectors', tag: 'Performance', hex: '#4ade80',
    part: 'Efficiency, MTF and DQE',
    summary: 'Three numbers describe any imaging detector: how many photons it catches, how well it preserves detail, and how much of the input signal-to-noise survives to the image.',
    bullets: [
      'Quantum efficiency: fraction of incident photons that actually interact — thickness and Z drive it.',
      'MTF: contrast transfer versus spatial frequency — pixel pitch, light spread and focal spot all degrade it.',
      'DQE combines both: it is the fraction of the input SNR² that reaches the output.',
      'A detector can have great MTF and poor DQE if it throws away most photons — sharp but noisy.',
      'Dose reduction claims are only meaningful if quoted as DQE, not as efficiency or resolution alone.',
    ],
    draw: t => {
      const sel = Math.floor(saw(t, 0.2) * 2);
      const mtf = (k: number) => Array.from({ length: 40 }, (_, i) => {
        const fr = i / 39;
        return `${34 + fr * 96},${118 - Math.exp(-Math.pow(fr * k, 1.7)) * 74}`;
      }).join(' ');
      const dqe = (k: number, q: number) => Array.from({ length: 40 }, (_, i) => {
        const fr = i / 39;
        return `${146 + fr * 96},${118 - q * Math.exp(-Math.pow(fr * k, 1.7)) * 74}`;
      }).join(' ');
      return (
        <g>
          <line x1="34" y1="118" x2="130" y2="118" stroke="#334155" />
          <line x1="146" y1="118" x2="242" y2="118" stroke="#334155" />
          <polyline points={mtf(sel === 0 ? 2.2 : 3.4)} fill="none" stroke={sel === 0 ? '#38bdf8' : '#f472b6'} strokeWidth="1.4" />
          <polyline points={dqe(sel === 0 ? 2.2 : 3.4, sel === 0 ? 0.75 : 0.4)} fill="none" stroke={sel === 0 ? '#38bdf8' : '#f472b6'} strokeWidth="1.4" />
          {L(34, 36, 'MTF', '#cbd5e1', 7)}
          {L(146, 36, 'DQE', '#cbd5e1', 7)}
          {L(34, 132, 'spatial frequency →', '#64748b', 6)}
          {L(146, 132, 'spatial frequency →', '#64748b', 6)}
          {L(10, 20, sel === 0 ? 'THICK SCINTILLATOR — efficient, softer' : 'THIN / DIRECT — sharp, fewer photons', '#cbd5e1', 7.5)}
        </g>
      );
    },
  },
];
