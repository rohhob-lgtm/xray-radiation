import type { MicroAnim } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// X-ray source & imaging TECHNOLOGY animations — transmission, backscatter,
// forward/coherent scatter, tomography and spectral methods.
// Every draw() renders inside a 260 × 150 viewBox.
// ═══════════════════════════════════════════════════════════════════════════════

const saw = (t: number, hz = 1) => (t * hz) % 1;
const osc = (t: number, hz = 1) => Math.sin(t * Math.PI * 2 * hz);
const L = (x: number, y: number, s: string, c = '#94a3b8', size = 7, a: 'start' | 'middle' | 'end' = 'start') => (
  <text x={x} y={y} fontSize={size} fill={c} textAnchor={a}>{s}</text>
);

/** Small source block used by most technology scenes */
const Src = ({ x, y, label = 'source' }: { x: number; y: number; label?: string }) => (
  <g>
    <rect x={x} y={y} width="20" height="18" rx="3" fill="#14301c" stroke="#22c55e" strokeWidth="1.2" />
    <text x={x + 10} y={y - 4} fontSize="6.5" fill="#86efac" textAnchor="middle">{label}</text>
  </g>
);

export const TECHNOLOGY_ANIMS: MicroAnim[] = [
  // ─── TRANSMISSION FAMILY ────────────────────────────────────────────────────
  {
    id: 'tech-transmission', group: 'xray-technologies', tag: 'Transmission', hex: '#fde047',
    part: 'Transmission imaging — the baseline',
    summary: 'Photons that pass straight through are counted on the far side. What you see is a shadow map of the line-integral of attenuation along each ray.',
    bullets: [
      'Beer–Lambert: <code>I = I₀ · e^(−∫µ dx)</code> — every pixel is one integral along one ray.',
      'Needs access to both sides of the object, which rules it out for walls, vehicles in place, and ship hulls.',
      'Contrast comes from differences in µ·x, so a thin dense object can mimic a thick light one.',
      'Superposition is the fundamental weakness: everything along the ray collapses into one number.',
      'It remains the highest-efficiency modality — most photons that matter are actually used.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      return (
        <g>
          <Src x={22} y={70} />
          <rect x="108" y="46" width="46" height="70" rx="4" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          <rect x="120" y="66" width="20" height="30" rx="2" fill="#0b1220" stroke="#94a3b8" strokeWidth="1" />
          <rect x="214" y="34" width="10" height="94" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.3" />
          {L(206, 142, 'detector', '#86efac')}
          {Array.from({ length: 6 }, (_, i) => {
            const y = 48 + i * 16;
            const g = (f + i / 6) % 1;
            const blocked = y > 62 && y < 100;
            const x = 42 + g * 176;
            return <circle key={i} cx={x} cy={y} r="2.2" fill="#fde047" opacity={blocked && x > 122 ? 0.15 : 1} />;
          })}
          {Array.from({ length: 6 }, (_, i) => {
            const y = 48 + i * 16;
            const blocked = y > 62 && y < 100;
            return <rect key={i} x="226" y={y - 5} width={blocked ? 8 : 22} height="10" rx="2" fill="#fde047" opacity={blocked ? 0.3 : 0.8} />;
          })}
          {L(10, 20, 'TRANSMISSION', '#cbd5e1', 8)}
          {L(10, 144, 'I = I₀ e^(−∫µdx)  ·  needs two-sided access', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'tech-dualview', group: 'xray-technologies', tag: 'Transmission', hex: '#38bdf8',
    part: 'Dual-view / multi-view transmission',
    summary: 'Two or more source-detector pairs at different angles break the superposition problem: a thin plate edge-on in one view is broadside in the other.',
    bullets: [
      'The classic defeat for single-view screening is a blade presented edge-on to the beam.',
      'Views are typically at 90° or at a shallower offset chosen to fit the tunnel envelope.',
      'Multi-view does not reconstruct a volume — it just samples a few projections.',
      'Four-view systems approach CT-like confidence for a fraction of the cost and dose.',
      'Each view needs its own generator, detector array and calibration.',
    ],
    draw: t => {
      const flip = saw(t, 0.25) > 0.5;
      return (
        <g>
          <Src x={16} y={70} label="view 1" />
          <Src x={118} y={16} label="view 2" />
          <g transform={`rotate(${flip ? 0 : 82} 130 82)`}>
            <rect x="120" y="58" width="50" height="8" rx="2" fill="#94a3b8" stroke="#e2e8f0" strokeWidth="1" />
          </g>
          {L(112, 130, 'blade target', '#cbd5e1')}
          <line x1="36" y1="79" x2="216" y2="79" stroke="#fde047" strokeWidth="1" opacity="0.5" />
          <line x1="128" y1="34" x2="128" y2="128" stroke="#38bdf8" strokeWidth="1" opacity="0.5" />
          <rect x="216" y="44" width="9" height="70" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          <rect x="88" y="128" width="90" height="9" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(10, 20, 'DUAL VIEW', '#cbd5e1', 8)}
          {L(184, 24, flip ? 'edge-on to view 1' : 'broadside to view 1', flip ? '#f87171' : '#4ade80', 6.5)}
        </g>
      );
    },
  },
  {
    id: 'tech-dualenergy', group: 'xray-technologies', tag: 'Transmission', hex: '#f97316',
    part: 'Dual-energy material discrimination',
    summary: 'Two spectra through the same path give two independent measurements, which separates effective atomic number from areal density.',
    bullets: [
      'Low energy is photoelectric-weighted (∝ Z³·⁵), high energy is Compton-weighted (∝ density).',
      'Implementation options: sandwich detector with a copper interlayer, fast kV switching, or dual sources.',
      'Output is the familiar orange (organic) / green (light inorganic) / blue (metal) colour map.',
      'Very thick steel saturates the measurement — the console flags it rather than guessing.',
      'MeV cargo systems use 6/9 MeV interleaving for the same purpose at much greater thickness.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      const zs = [6, 13, 26, 82];
      return (
        <g>
          {zs.map((z, i) => {
            const col = z < 10 ? '#f97316' : z < 20 ? '#4ade80' : z < 40 ? '#38bdf8' : '#1f2937';
            const le = 1 - Math.exp(-z / 12);
            const he = 1 - Math.exp(-z / 40);
            const active = Math.floor(f * 4) === i;
            return (
              <g key={z} opacity={active ? 1 : 0.45}>
                <rect x={26 + i * 58} y="34" width="44" height="30" rx="4" fill={col} fillOpacity="0.4" stroke={col} strokeWidth="1.2" />
                {L(48 + i * 58, 54, `Z${z}`, '#e2e8f0', 8, 'middle')}
                <rect x={26 + i * 58} y="74" width="44" height="7" rx="3" fill="#0b1220" stroke="#334155" />
                <rect x={27 + i * 58} y="75" width={42 * le} height="5" rx="2" fill="#a78bfa" />
                <rect x={26 + i * 58} y="86" width="44" height="7" rx="3" fill="#0b1220" stroke="#334155" />
                <rect x={27 + i * 58} y="87" width={42 * he} height="5" rx="2" fill="#38bdf8" />
                {L(48 + i * 58, 110, (le / Math.max(0.05, he)).toFixed(1), col === '#1f2937' ? '#94a3b8' : col, 7, 'middle')}
              </g>
            );
          })}
          {L(10, 80, 'LE', '#c4b5fd', 6.5)}
          {L(10, 92, 'HE', '#7dd3fc', 6.5)}
          {L(10, 20, 'DUAL ENERGY → Zeff', '#cbd5e1', 8)}
          {L(10, 128, 'ratio LE/HE identifies the material class', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'tech-highenergy', group: 'xray-technologies', tag: 'Transmission', hex: '#a855f7',
    part: 'High-energy (MeV) cargo transmission',
    summary: 'At MeV energies attenuation is Compton-dominated and nearly Z-independent, so the image is essentially a density map that can see through 300+ mm of steel.',
    bullets: [
      'A 6 MeV LINAC penetrates roughly 300 mm of steel; 9 MeV reaches about 380 mm.',
      'Because Compton dominates, single-energy MeV imaging cannot identify materials — only mass.',
      'Interleaved 6/9 MeV frames restore some discrimination for organic versus metallic loads.',
      'Dose per scan is far higher than a baggage tunnel, so occupancy exclusion zones are large.',
      'Detector arrays use dense scintillators (CdWO₄) with photodiodes to cope with the energy.',
    ],
    draw: t => {
      const f = saw(t, 0.2);
      return (
        <g>
          <rect x="14" y="60" width="30" height="34" rx="4" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.3" />
          {L(14, 54, 'LINAC 6–9 MeV', '#d8b4fe')}
          <polygon points="44,77 216,30 216,124" fill="#fde047" fillOpacity="0.08" />
          <rect x={60 + f * 90} y="46" width="110" height="60" rx="3" fill="#111c2e" stroke="#475569" strokeWidth="1.2" />
          <rect x={80 + f * 90} y="60" width="26" height="32" rx="2" fill="#94a3b8" opacity="0.6" />
          <rect x={120 + f * 90} y="66" width="34" height="24" rx="2" fill="#f97316" opacity="0.45" />
          <rect x="216" y="30" width="10" height="94" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.3" />
          {L(200, 140, 'CdWO₄ array', '#86efac')}
          {L(10, 20, 'MeV TRANSMISSION', '#cbd5e1', 8)}
          {L(10, 140, '≈300 mm steel @6 MeV · Compton-dominated', '#c4b5fd')}
        </g>
      );
    },
  },

  // ─── SCATTER FAMILY ─────────────────────────────────────────────────────────
  {
    id: 'tech-angular', group: 'xray-technologies', tag: 'Scatter physics', hex: '#a78bfa',
    part: 'Where photons go — angular distribution',
    summary: 'The Klein–Nishina distribution decides every scatter technology: at low energy scattering is nearly symmetric front-to-back; at high energy it collapses forward.',
    bullets: [
      'Below about 100 keV a useful fraction scatters backwards — that is what makes backscatter imaging possible.',
      'Above a few hundred keV almost everything goes forward, so MeV systems cannot image by backscatter.',
      'Coherent (Rayleigh) scatter is confined to very small forward angles and carries structural information.',
      'Scatter that is not used for imaging is noise — it is the reason grids and collimators exist.',
      'Scatter-to-primary ratio drives shielding design as much as the primary beam does.',
    ],
    draw: t => {
      const E = 40 + 120 * (0.5 + 0.5 * osc(t, 0.15));
      const fwd = Math.min(0.92, E / 260);
      const lobe = (ang: number) => {
        const forwardBias = 1 + fwd * 3;
        return 24 + 30 * Math.pow((1 + Math.cos(ang)) / 2, forwardBias);
      };
      const pts = Array.from({ length: 48 }, (_, i) => {
        const a = (i / 47) * Math.PI * 2;
        const r = lobe(a);
        return `${(130 + Math.cos(a) * r).toFixed(1)},${(78 + Math.sin(a) * r * 0.85).toFixed(1)}`;
      }).join(' ');
      return (
        <g>
          <line x1="20" y1="78" x2="126" y2="78" stroke="#fde047" strokeWidth="1.6" />
          <circle cx="130" cy="78" r="4" fill="#94a3b8" />
          <polygon points={pts} fill="#a78bfa" fillOpacity="0.22" stroke="#a78bfa" strokeWidth="1.2" />
          {L(196, 44, `${E.toFixed(0)} keV`, '#c4b5fd', 8)}
          {L(196, 58, E < 90 ? 'back-scatter usable' : 'forward-peaked', E < 90 ? '#4ade80' : '#f87171', 6.5)}
          {L(10, 20, 'KLEIN–NISHINA LOBE', '#cbd5e1', 8)}
          {L(10, 144, 'the lobe shape decides which technology works', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'tech-backscatter', group: 'xray-technologies', tag: 'Backscatter', hex: '#22d3ee',
    part: 'Backscatter imaging — flying spot',
    summary: 'A pencil beam sweeps the scene and large unfocused detectors on the same side collect Compton-scattered photons. Low-Z material scatters strongly and appears bright.',
    bullets: [
      'Single-sided access — the defining advantage for vehicles, walls, containers and personnel.',
      'The image is built by knowing where the pencil beam was pointing, not by where photons land.',
      'Organic material (drugs, explosives, people) is bright; steel is dark, the inverse of transmission.',
      'Penetration is shallow — a surface and near-surface technique, typically a few centimetres in steel.',
      'Detectors are large-area plastic scintillators; more area simply means more signal.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      const y = 34 + f * 84;
      return (
        <g>
          <rect x="18" y="30" width="18" height="92" rx="4" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.2" />
          {L(14, 24, 'chopper wheel', '#d8b4fe')}
          <rect x="42" y="30" width="10" height="92" rx="2" fill="#0b1220" stroke="#22d3ee" strokeWidth="1.2" />
          {L(40, 138, 'detector', '#67e8f9')}
          <line x1="52" y1={y} x2="176" y2={y} stroke="#fde047" strokeWidth="1.6" />
          <rect x="176" y="38" width="40" height="80" rx="5" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          {L(170, 132, 'organic target', '#fdba74')}
          {Array.from({ length: 5 }, (_, i) => (
            <line key={i} x1="178" y1={y} x2="52" y2={y + (i - 2) * 30} stroke="#22d3ee" strokeWidth="0.9" opacity="0.5" />
          ))}
          <rect x="228" y="30" width="24" height="92" rx="3" fill="#0b1220" stroke="#334155" />
          <rect x="230" y={y - 3} width="20" height="6" fill="#22d3ee" opacity="0.8" />
          {L(10, 20, 'BACKSCATTER (Compton)', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'tech-zbv', group: 'xray-technologies', tag: 'Backscatter', hex: '#4ade80',
    part: 'Mobile backscatter van (drive-by)',
    summary: 'The whole flying-spot system is built into a vehicle so it can image parked cars, trucks and containers from the roadside without any set-up on the far side.',
    bullets: [
      'Scan is produced by driving past the target — the vehicle motion is the slow axis.',
      'Exclusion zones are defined around the vehicle because the primary beam exits the shell.',
      'Operators work from a shielded cab with an interlocked beam-on control.',
      'It sees organic contraband hidden behind steel skin that transmission would render as a blur.',
      'Regulatory acceptance depends on demonstrating dose to bystanders and to any person inside the target.',
    ],
    draw: t => {
      const f = saw(t, 0.18);
      const vx = 10 + f * 90;
      return (
        <g>
          <rect x={vx} y="60" width="84" height="40" rx="6" fill="#111c2e" stroke="#4ade80" strokeWidth="1.4" />
          <rect x={vx + 6} y="66" width="24" height="16" rx="2" fill="#0b1220" stroke="#64748b" strokeWidth="0.8" />
          <circle cx={vx + 18} cy="104" r="6" fill="#1f2937" stroke="#94a3b8" strokeWidth="1" />
          <circle cx={vx + 66} cy="104" r="6" fill="#1f2937" stroke="#94a3b8" strokeWidth="1" />
          {L(vx, 54, 'scanning van', '#86efac')}
          <polygon points={`${vx + 84},80 ${186},52 ${186},108`} fill="#fde047" fillOpacity="0.16" />
          <rect x="186" y="44" width="56" height="66" rx="5" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.3" />
          <rect x="198" y="62" width="30" height="28" rx="3" fill="#f97316" fillOpacity={0.25 + 0.5 * Math.abs(osc(t, 0.6))} stroke="#f97316" strokeWidth="1" />
          {L(190, 126, 'target vehicle', '#cbd5e1')}
          {L(10, 20, 'DRIVE-BY BACKSCATTER', '#cbd5e1', 8)}
          {L(10, 144, 'single-sided · organic contrast · shallow depth', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'tech-forward', group: 'xray-technologies', tag: 'Forward scatter', hex: '#f472b6',
    part: 'Forward / small-angle scatter imaging',
    summary: 'Photons deflected by only a few degrees still carry information about sub-millimetre structure — collect them just off the primary axis instead of throwing them away.',
    bullets: [
      'Small-angle scatter intensity depends on particle size and packing, not just on bulk density.',
      'Powders, fibres and emulsions produce characteristic small-angle signatures.',
      'A beam stop blocks the intense primary so the weak scattered signal is not swamped.',
      'Combined with transmission it adds a channel that pure attenuation cannot supply.',
      'It is the physical basis for dark-field imaging in grating interferometry.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      return (
        <g>
          <Src x={16} y={70} />
          <line x1="36" y1="79" x2="118" y2="79" stroke="#fde047" strokeWidth="1.6" />
          <rect x="118" y="52" width="24" height="54" rx="3" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          {L(110, 122, 'sample', '#fdba74')}
          <circle cx="212" cy="79" r="7" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.2" />
          {L(206, 100, 'beam stop', '#cbd5e1')}
          {[-3, -1.6, 1.6, 3].map((k, i) => (
            <line key={i} x1="142" y1="79" x2="238" y2={79 + k * 12} stroke="#f472b6" strokeWidth="1" opacity={0.4 + 0.5 * Math.abs(Math.sin(f * 6 + i))} />
          ))}
          <rect x="238" y="30" width="10" height="98" rx="2" fill="#0b1220" stroke="#f472b6" strokeWidth="1.2" />
          {L(10, 20, 'SMALL-ANGLE SCATTER', '#cbd5e1', 8)}
          {L(10, 144, 'structure information, not just density', '#f9a8d4')}
        </g>
      );
    },
  },
  {
    id: 'tech-coherent', group: 'xray-technologies', tag: 'Forward scatter', hex: '#a855f7',
    part: 'Coherent scatter / X-ray diffraction imaging',
    summary: 'Crystalline materials scatter coherently at angles set by their lattice spacing, giving a diffraction fingerprint that separates substances with identical attenuation.',
    bullets: [
      'Bragg: <code>nλ = 2d·sin θ</code> — the peak positions are a molecular signature.',
      'Distinguishes crystalline explosives from inert powders that transmit identically.',
      'Angles are small (a few degrees) at the energies used, so long collimation paths are needed.',
      'Energy-dispersive geometry uses a fixed angle and a spectroscopic detector instead of scanning.',
      'Slow compared with transmission — used as a secondary confirmation stage, not a primary scanner.',
    ],
    draw: t => {
      const cryst = saw(t, 0.25) > 0.5;
      const ph = t * 3;
      return (
        <g>
          <Src x={14} y={70} />
          <line x1="34" y1="79" x2="112" y2="79" stroke="#fde047" strokeWidth="1.5" />
          <rect x="112" y="58" width="24" height="42" rx="3" fill={cryst ? '#312e81' : '#3f2a12'} stroke={cryst ? '#818cf8' : '#f59e0b'} strokeWidth="1.2" />
          {L(104, 118, cryst ? 'crystalline' : 'amorphous', cryst ? '#a5b4fc' : '#fbbf24')}
          {cryst
            ? [-2.2, -1.1, 1.1, 2.2].map((k, i) => (
              <line key={i} x1="136" y1="79" x2="230" y2={79 + k * 16} stroke="#a855f7" strokeWidth="1.2" opacity="0.85" />
            ))
            : Array.from({ length: 9 }, (_, i) => (
              <line key={i} x1="136" y1="79" x2="230" y2={30 + i * 12} stroke="#64748b" strokeWidth="0.7" opacity="0.4" />
            ))}
          <rect x="230" y="26" width="10" height="106" rx="2" fill="#0b1220" stroke="#a855f7" strokeWidth="1.2" />
          {Array.from({ length: 3 }, (_, i) => cryst && (
            <rect key={i} x="244" y={54 + i * 22 + Math.sin(ph + i) * 1.5} width="10" height="4" fill="#a855f7" />
          ))}
          {L(10, 20, 'XRD IMAGING', '#cbd5e1', 8)}
          {L(10, 144, cryst ? 'sharp Bragg peaks → identified' : 'diffuse halo → unidentified', cryst ? '#c4b5fd' : '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'tech-comptontomo', group: 'xray-technologies', tag: 'Backscatter', hex: '#38bdf8',
    part: 'Compton scatter tomography',
    summary: 'Because scattered energy encodes the scattering angle, a collimated detector can locate the scattering voxel — giving depth information from one side only.',
    bullets: [
      'Scattered energy: <code>E′ = E / (1 + (E/m₀c²)(1 − cos θ))</code> — energy tells you the angle.',
      'A spectroscopic detector plus a known beam direction fixes the voxel in three dimensions.',
      'Enables single-sided tomography of walls, aircraft skins and thick composite panels.',
      'Count rates are low, so acquisition is slow compared with transmission CT.',
      'Multiple scattering blurs the reconstruction and must be modelled or suppressed.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      const depth = 120 + f * 60;
      const Escat = (100 / (1 + (100 / 511) * (1 - Math.cos(2.4)))).toFixed(0);
      return (
        <g>
          <Src x={14} y={70} label="pencil" />
          <line x1="34" y1="79" x2="220" y2="79" stroke="#fde047" strokeWidth="1.4" opacity="0.55" />
          <rect x="110" y="34" width="120" height="92" rx="4" fill="#111c2e" stroke="#475569" strokeWidth="1.2" />
          <circle cx={depth} cy="79" r="4" fill="#fde047" />
          <line x1={depth} y1="79" x2="52" y2="40" stroke="#38bdf8" strokeWidth="1.1" />
          <rect x="34" y="26" width="26" height="16" rx="3" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.2" />
          {L(28, 20, 'spectroscopic detector', '#7dd3fc')}
          {L(120, 142, `voxel depth ${(f * 100).toFixed(0)} mm  ·  E′ ≈ ${Escat} keV`, '#7dd3fc')}
          {L(10, 20, 'COMPTON TOMOGRAPHY', '#cbd5e1', 8)}
        </g>
      );
    },
  },

  // ─── TOMOGRAPHIC & GEOMETRIC ────────────────────────────────────────────────
  {
    id: 'tech-geometry', group: 'xray-technologies', tag: 'Geometry', hex: '#94a3b8',
    part: 'Pencil, fan and cone beam',
    summary: 'The beam shape sets the trade between scatter rejection, dose efficiency and acquisition speed — from one ray at a time to a whole volume in one shot.',
    bullets: [
      'Pencil beam: the best scatter rejection of all, but the slowest — used in backscatter and XRD.',
      'Fan beam: one line per read, near-ideal for conveyor line-scan and for medical CT slices.',
      'Cone beam: a whole area at once, fastest, but scatter-to-primary ratio rises sharply.',
      'Anti-scatter grids and air gaps are the standard countermeasures for cone-beam scatter.',
      'Beam shape and detector geometry must be designed together, never chosen independently.',
    ],
    draw: t => {
      const mode = Math.floor(saw(t, 0.18) * 3);
      const names = ['PENCIL', 'FAN', 'CONE'];
      return (
        <g>
          <Src x={26} y={70} />
          {mode === 0 && <line x1="46" y1="79" x2="212" y2="79" stroke="#fde047" strokeWidth="2" />}
          {mode === 1 && <polygon points="46,79 212,36 212,122" fill="#fde047" fillOpacity="0.2" />}
          {mode === 2 && (<>
            <polygon points="46,79 212,26 212,132" fill="#fde047" fillOpacity="0.15" />
            <ellipse cx="212" cy="79" rx="8" ry="53" fill="#fde047" fillOpacity="0.12" />
          </>)}
          <rect x="212" y={mode === 0 ? 72 : 26} width="10" height={mode === 0 ? 14 : 106} rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(10, 20, `${names[mode]} BEAM`, '#cbd5e1', 8)}
          {L(10, 144, mode === 0 ? 'best scatter rejection · slowest' : mode === 1 ? 'line-scan workhorse' : 'fastest · highest scatter', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'tech-ct', group: 'xray-technologies', tag: 'Tomography', hex: '#4ade80',
    part: 'Computed tomography reconstruction',
    summary: 'Hundreds of projections around the object are back-projected into a voxel grid, replacing a superimposed shadow with a measured attenuation per voxel.',
    bullets: [
      'Filtered back-projection is fast; iterative and model-based reconstruction cut dose and artefacts.',
      'Each voxel gets a CT number, so density becomes a measurement rather than an impression.',
      'Beam hardening, metal streaks and cone-beam artefacts are the main image-quality enemies.',
      'In security this is what enables automatic explosive detection on hold and now cabin baggage.',
      'In industry it enables internal metrology against a CAD model with no destructive sectioning.',
    ],
    draw: t => {
      const f = saw(t, 0.25);
      const nProj = Math.max(1, Math.floor(f * 12));
      return (
        <g>
          <circle cx="88" cy="79" r="46" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />
          {Array.from({ length: nProj }, (_, i) => {
            const a = (i / 12) * Math.PI;
            return <line key={i} x1={88 - Math.cos(a) * 46} y1={79 - Math.sin(a) * 46} x2={88 + Math.cos(a) * 46} y2={79 + Math.sin(a) * 46}
              stroke="#fde047" strokeWidth="0.8" opacity="0.4" />;
          })}
          <rect x="70" y="64" width="30" height="26" rx="3" fill="#f97316" fillOpacity="0.35" stroke="#f97316" strokeWidth="1" />
          {L(56, 138, `${nProj} projections`, '#94a3b8')}
          <rect x="152" y="40" width="90" height="78" rx="4" fill="#0b1220" stroke="#4ade80" strokeWidth="1.2" />
          {Array.from({ length: 36 }, (_, i) => {
            const cx = 156 + (i % 6) * 14, cy = 44 + Math.floor(i / 6) * 12;
            const inside = Math.abs((i % 6) - 2.5) < 2 && Math.abs(Math.floor(i / 6) - 2.5) < 2;
            return <rect key={i} x={cx} y={cy} width="13" height="11" fill={inside ? '#f97316' : '#22c55e'}
              opacity={Math.min(1, (nProj / 12) * (inside ? 0.75 : 0.25))} />;
          })}
          {L(150, 132, 'reconstructed voxels', '#86efac')}
          {L(10, 20, 'CT RECONSTRUCTION', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'tech-tomo', group: 'xray-technologies', tag: 'Tomography', hex: '#38bdf8',
    part: 'Tomosynthesis / limited-angle imaging',
    summary: 'Sweeping the source over a limited arc gives depth separation without a full rotation — cheaper and faster than CT, at the price of blurred depth resolution.',
    bullets: [
      'Typical sweep is 15°–50°, far short of the 180° plus fan angle that full reconstruction needs.',
      'In-plane resolution is excellent; through-plane resolution is poor and direction-dependent.',
      'It removes the superposition problem for layered objects such as circuit boards and welds.',
      'Used where geometry forbids a full rotation — in-line inspection, large panels, breast imaging.',
      'Reconstruction artefacts from out-of-plane structures are inherent, not a tuning failure.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      const ang = (f - 0.5) * 0.9;
      const sx = 130 + Math.sin(ang) * 90;
      return (
        <g>
          <Src x={sx - 10} y={22} />
          <path d="M 40 40 Q 130 12 220 40" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />
          <polygon points={`${sx},42 82,116 178,116`} fill="#fde047" fillOpacity="0.13" />
          <rect x="104" y="64" width="52" height="8" rx="2" fill="#38bdf8" fillOpacity="0.5" stroke="#38bdf8" strokeWidth="0.9" />
          <rect x="112" y="82" width="36" height="8" rx="2" fill="#f97316" fillOpacity="0.5" stroke="#f97316" strokeWidth="0.9" />
          <rect x="72" y="116" width="116" height="10" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(10, 20, 'TOMOSYNTHESIS', '#cbd5e1', 8)}
          {L(10, 144, `sweep ${(ang * 57).toFixed(0)}°  ·  layers separate, depth blurs`, '#7dd3fc')}
        </g>
      );
    },
  },
  {
    id: 'tech-multisource', group: 'xray-technologies', tag: 'Geometry', hex: '#f472b6',
    part: 'Stationary multi-source arrays',
    summary: 'Instead of rotating one source, fire many fixed emitters in sequence — no moving mass, so scan speed is limited only by electronics.',
    bullets: [
      'Carbon-nanotube and distributed field-emission arrays make dozens of addressable emitters practical.',
      'No rotating gantry means far lower maintenance and much faster effective frame rates.',
      'Angular coverage is set by array geometry and is usually sparse, so reconstruction is model-based.',
      'Sparse-view artefacts are handled by iterative reconstruction rather than by more projections.',
      'Well suited to conveyor lines where the object is already moving through the field.',
    ],
    draw: t => {
      const active = Math.floor(saw(t, 1.2) * 6);
      return (
        <g>
          {Array.from({ length: 6 }, (_, i) => (
            <g key={i}>
              <rect x={24 + i * 36} y="26" width="18" height="14" rx="3"
                fill={i === active ? '#14301c' : '#0b1220'} stroke={i === active ? '#22c55e' : '#334155'} strokeWidth="1.1" />
              {i === active && <polygon points={`${33 + i * 36},40 ${60},116 ${200},116`} fill="#fde047" fillOpacity="0.13" />}
            </g>
          ))}
          <rect x="104" y="64" width="46" height="34" rx="3" fill="#f97316" fillOpacity="0.3" stroke="#f97316" strokeWidth="1" />
          <rect x="50" y="118" width="164" height="10" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(10, 20, 'DISTRIBUTED SOURCE ARRAY', '#cbd5e1', 8)}
          {L(10, 146, 'no moving gantry · electronic scanning', '#f9a8d4')}
        </g>
      );
    },
  },

  // ─── SPECTRAL & ADVANCED ────────────────────────────────────────────────────
  {
    id: 'tech-photoncount', group: 'xray-technologies', tag: 'Spectral', hex: '#22d3ee',
    part: 'Photon-counting spectral detector',
    summary: 'Instead of integrating charge, each photon is counted and sorted into energy bins — giving several spectral channels from a single exposure with no electronic noise floor.',
    bullets: [
      'Direct-conversion sensors (CdTe, CZT) generate charge without a scintillator light stage.',
      'Energy binning gives multi-material decomposition far beyond two-channel dual energy.',
      'No dark noise means low-dose imaging improves rather than degrading proportionally.',
      'Charge sharing and pulse pile-up at high flux are the practical engineering limits.',
      'The same technology moves K-edge imaging from research into deployable systems.',
    ],
    draw: t => {
      const f = saw(t, 0.8);
      const bins = [0.35, 0.62, 0.85, 0.5];
      return (
        <g>
          {Array.from({ length: 4 }, (_, i) => {
            const g = (f + i / 4) % 1;
            return <circle key={i} cx={20 + g * 90} cy={40 + i * 22} r="2.2" fill="#fde047" />;
          })}
          <rect x="110" y="30" width="26" height="96" rx="3" fill="#0b1220" stroke="#22d3ee" strokeWidth="1.3" />
          {L(104, 24, 'CdTe sensor', '#67e8f9')}
          {bins.map((b, i) => (
            <g key={i}>
              <rect x="152" y={34 + i * 24} width="90" height="14" rx="3" fill="#0b1220" stroke="#334155" />
              <rect x="153" y={35 + i * 24} width={88 * b * (0.75 + 0.25 * Math.abs(osc(t + i, 0.6)))} height="12" rx="3" fill="#22d3ee" opacity="0.75" />
              <text x="246" y={45 + i * 24} fontSize="6" fill="#94a3b8">bin {i + 1}</text>
            </g>
          ))}
          {L(10, 20, 'PHOTON COUNTING', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'tech-kedge', group: 'xray-technologies', tag: 'Spectral', hex: '#f97316',
    part: 'K-edge subtraction imaging',
    summary: 'Every element has a sharp jump in absorption at its K-edge. Imaging just below and just above that energy isolates that element from everything else in the scene.',
    bullets: [
      'Iodine 33.2 keV, gadolinium 50.2 keV, tungsten 69.5 keV, lead 88.0 keV.',
      'Subtracting the two frames cancels the background and leaves only the target element.',
      'Requires narrow energy bands — synchrotron beams, filtered spectra or photon-counting bins.',
      'In security it can flag specific high-Z materials rather than merely "something dense".',
      'In medicine it is the basis of contrast-agent-specific and dual-contrast imaging.',
    ],
    draw: t => {
      const f = saw(t, 0.3);
      const above = f > 0.5;
      const curve = Array.from({ length: 60 }, (_, i) => {
        const e = 10 + (i / 59) * 90;
        const jump = e > 33.2 ? 2.6 : 1;
        const v = (jump * 900) / Math.pow(e, 2.1);
        return `${34 + (i / 59) * 150},${(122 - Math.min(80, v * 26)).toFixed(1)}`;
      }).join(' ');
      return (
        <g>
          <line x1="34" y1="122" x2="192" y2="122" stroke="#334155" />
          <line x1="34" y1="122" x2="34" y2="34" stroke="#334155" />
          <polyline points={curve} fill="none" stroke="#f97316" strokeWidth="1.5" />
          <line x1={34 + ((33.2 - 10) / 90) * 150} y1="34" x2={34 + ((33.2 - 10) / 90) * 150} y2="122" stroke="#94a3b8" strokeWidth="0.8" strokeDasharray="2 2" />
          {L(74, 44, 'K-edge 33.2 keV (I)', '#cbd5e1', 6.5)}
          <circle cx={34 + ((above ? 38 : 28) - 10) / 90 * 150} cy="70" r="3.4" fill={above ? '#4ade80' : '#38bdf8'} />
          {L(200, 60, above ? 'above edge' : 'below edge', above ? '#4ade80' : '#7dd3fc')}
          <rect x="200" y="74" width="48" height="34" rx="4" fill={above ? '#14301c' : '#0b1b34'} stroke={above ? '#22c55e' : '#38bdf8'} strokeWidth="1.2" />
          {L(224, 96, above ? 'I visible' : 'I hidden', '#e2e8f0', 6.5, 'middle')}
          {L(10, 20, 'K-EDGE SUBTRACTION', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'tech-xrf', group: 'xray-technologies', tag: 'Spectral', hex: '#a78bfa',
    part: 'X-ray fluorescence (XRF) elemental analysis',
    summary: 'Excite the sample with X-rays, then read the characteristic lines it emits back. Each element has its own line energies, so the spectrum names the elements present.',
    bullets: [
      'The same inner-shell physics as characteristic emission in a tube — here used as an analytical probe.',
      'Handheld XRF identifies alloys, coatings and contaminants in seconds without any sampling.',
      'Detection depth is shallow: it is a surface-and-near-surface technique.',
      'Light elements (below sodium) are hard because their fluorescence energies are absorbed in air.',
      'Used for alloy verification, RoHS screening, art authentication and soil contamination survey.',
    ],
    draw: t => {
      const ph = t * 2;
      const lines = [{ x: 168, h: 44, c: '#a78bfa', n: 'Fe' }, { x: 190, h: 28, c: '#38bdf8', n: 'Cu' }, { x: 214, h: 36, c: '#4ade80', n: 'Zn' }];
      return (
        <g>
          <Src x={16} y={44} label="excite" />
          <line x1="36" y1="53" x2="92" y2="76" stroke="#fde047" strokeWidth="1.5" />
          <rect x="92" y="66" width="44" height="40" rx="4" fill="#1f2937" stroke="#94a3b8" strokeWidth="1.2" />
          {L(90, 122, 'sample', '#cbd5e1')}
          {Array.from({ length: 3 }, (_, i) => (
            <line key={i} x1="114" y1="76" x2="42" y2={96 + i * 12} stroke={lines[i].c} strokeWidth="1" opacity={0.5 + 0.4 * Math.abs(Math.sin(ph + i))} />
          ))}
          <rect x="18" y="96" width="22" height="30" rx="3" fill="#0b1220" stroke="#a78bfa" strokeWidth="1.2" />
          {L(14, 140, 'SDD detector', '#c4b5fd')}
          <line x1="150" y1="122" x2="248" y2="122" stroke="#334155" />
          {lines.map(l => (
            <g key={l.n}>
              <line x1={l.x} y1="122" x2={l.x} y2={122 - l.h * (0.8 + 0.2 * Math.abs(Math.sin(ph)))} stroke={l.c} strokeWidth="2" />
              <text x={l.x} y="134" fontSize="6" fill={l.c} textAnchor="middle">{l.n}</text>
            </g>
          ))}
          {L(150, 44, 'characteristic lines', '#c4b5fd')}
          {L(10, 20, 'XRF ANALYSIS', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'tech-phase', group: 'xray-technologies', tag: 'Forward scatter', hex: '#22d3ee',
    part: 'Phase contrast & dark-field imaging',
    summary: 'X-rays refract very slightly when passing through a material. Grating interferometry reads that phase shift and the loss of coherence, adding two channels to plain attenuation.',
    bullets: [
      'Phase shift can be orders of magnitude larger than absorption for light materials.',
      'A Talbot–Lau interferometer (three gratings) makes it work with an ordinary tube, not just a synchrotron.',
      'The dark-field channel maps sub-pixel micro-structure — cracks, fibres, powders.',
      'Excellent for soft materials, composites and explosives that attenuate almost identically.',
      'Cost is acquisition time and mechanical stability at micrometre scale.',
    ],
    draw: t => {
      const ph = t * 2.4;
      return (
        <g>
          <Src x={12} y={70} />
          {[52, 96, 214].map((x, i) => (
            <g key={i}>
              {Array.from({ length: 9 }, (_, k) => (
                <rect key={k} x={x} y={36 + k * 10} width="6" height="5" fill="#64748b" />
              ))}
              {L(x - 4, 30, `G${i}`, '#cbd5e1', 6.5)}
            </g>
          ))}
          <rect x="130" y="58" width="34" height="42" rx="4" fill="#0b1b34" stroke="#38bdf8" strokeWidth="1.1" />
          {L(126, 116, 'sample', '#7dd3fc')}
          <polyline points={Array.from({ length: 60 }, (_, i) => `${58 + i * 2.6},${79 - Math.sin(i * 0.5 - ph) * 8}`).join(' ')}
            fill="none" stroke="#22d3ee" strokeWidth="1.1" opacity="0.85" />
          <polyline points={Array.from({ length: 60 }, (_, i) => `${58 + i * 2.6},${79 - Math.sin(i * 0.5 - ph + (i > 28 ? 1.1 : 0)) * (i > 28 ? 5 : 8)}`).join(' ')}
            fill="none" stroke="#f472b6" strokeWidth="1.1" opacity="0.7" />
          {L(150, 136, 'phase shift + visibility loss = dark field', '#67e8f9')}
          {L(10, 20, 'PHASE CONTRAST', '#cbd5e1', 8)}
        </g>
      );
    },
  },
  {
    id: 'tech-grid', group: 'xray-technologies', tag: 'Scatter physics', hex: '#94a3b8',
    part: 'Anti-scatter grid & air gap',
    summary: 'Scattered photons arrive off-axis carrying no positional truth. A grid of lead strips absorbs them; simply moving the detector back does much the same for free.',
    bullets: [
      'Grid ratio = strip height / interspace width; higher ratio rejects more scatter and needs more dose.',
      'Scatter-to-primary ratio can exceed 3:1 in thick sections — most of the signal is noise.',
      'Grid cut-off from misalignment causes a characteristic density loss across the image.',
      'An air gap is the zero-cost alternative, at the price of magnification and geometric unsharpness.',
      'Digital scatter-correction algorithms increasingly supplement, but do not replace, physical rejection.',
    ],
    draw: t => {
      const f = saw(t, 0.4);
      return (
        <g>
          <rect x="30" y="46" width="34" height="66" rx="4" fill="#7c2d12" stroke="#f97316" strokeWidth="1.2" />
          {L(24, 128, 'object', '#fdba74')}
          {Array.from({ length: 9 }, (_, i) => (
            <rect key={i} x={150} y={34 + i * 11} width="9" height="8" fill="#334155" stroke="#94a3b8" strokeWidth="0.5" />
          ))}
          {L(140, 28, 'Pb grid', '#cbd5e1')}
          <line x1="64" y1="79" x2="230" y2="79" stroke="#fde047" strokeWidth="1.8" />
          {[-2.4, -1.2, 1.2, 2.4].map((k, i) => {
            const yEnd = 79 + k * 26;
            const stopped = Math.abs(k) > 0.9;
            return <line key={i} x1="64" y1="79" x2={stopped ? 150 : 230} y2={stopped ? 79 + k * 17 : yEnd}
              stroke="#f472b6" strokeWidth="0.9" opacity={0.35 + 0.4 * Math.abs(Math.sin(f * 6 + i))} />;
          })}
          <rect x="230" y="30" width="10" height="98" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(10, 20, 'SCATTER REJECTION', '#cbd5e1', 8)}
          {L(10, 146, 'primary passes · scatter absorbed', '#94a3b8')}
        </g>
      );
    },
  },
  {
    id: 'tech-fluoro', group: 'xray-technologies', tag: 'Geometry', hex: '#fbbf24',
    part: 'Radiography vs real-time fluoroscopy',
    summary: 'One long exposure gives the best signal-to-noise per image; a pulsed low-dose stream gives motion at a dose penalty per unit of information.',
    bullets: [
      'Pulsed fluoroscopy dose scales almost linearly with frame rate — halving the rate halves the dose.',
      'Grid-controlled tubes make clean microsecond pulses possible without switching the high voltage.',
      'Last-image-hold and frame averaging cut dose without losing clinical or inspection information.',
      'In NDT, real-time radioscopy is used for in-line inspection where throughput beats ultimate sensitivity.',
      'Cumulative fluoroscopy time is a regulated, logged quantity in both medicine and industry.',
    ],
    draw: t => {
      const pulse = saw(t, 2) < 0.4;
      const single = saw(t, 0.16) > 0.5;
      return (
        <g>
          <Src x={26} y={70} />
          {(single || pulse) && <polygon points="46,79 200,44 200,114" fill="#fde047" fillOpacity={single ? 0.24 : 0.14} />}
          <rect x="200" y="36" width="10" height="86" rx="2" fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          <polyline points={Array.from({ length: 60 }, (_, i) => {
            const x = 26 + i * 3.6;
            const hi = single ? (i > 10 && i < 46) : (((i / 60) * 8 + t * 2) % 1) < 0.4;
            return `${x},${hi ? 132 : 144}`;
          }).join(' ')} fill="none" stroke="#fbbf24" strokeWidth="1.3" />
          {L(10, 20, single ? 'RADIOGRAPHY — single exposure' : 'FLUOROSCOPY — pulsed stream', '#cbd5e1', 8)}
          {L(120, 30, single ? 'best SNR per image' : 'motion at low dose per frame', single ? '#4ade80' : '#fbbf24', 6.5)}
        </g>
      );
    },
  },
  {
    id: 'tech-mmw', group: 'xray-technologies', tag: 'Complementary', hex: '#a855f7',
    part: 'Millimetre wave — the non-ionising alternative',
    summary: 'Active millimetre-wave imaging reflects off skin and reveals concealed objects without any ionising radiation, which is why it replaced backscatter for personnel screening.',
    bullets: [
      'Frequencies around 24–30 GHz; the wave reflects at the skin and at dielectric discontinuities.',
      'Zero ionising dose removes the whole justification argument for scanning members of the public.',
      'Automatic target recognition displays a generic avatar instead of any body image.',
      'It cannot see inside the body or through metal — complementary to, not a replacement for, X-ray.',
      'Throughput and resolution are the main engineering trade-offs at a busy checkpoint.',
    ],
    draw: t => {
      const a = t * 1.6;
      return (
        <g>
          <ellipse cx="130" cy="79" rx="60" ry="52" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />
          <g transform={`rotate(${(a * 50) % 360} 130 79)`}>
            <rect x="66" y="70" width="12" height="18" rx="3" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.2" />
          </g>
          <circle cx="130" cy="56" r="9" fill="#64748b" />
          <rect x="122" y="66" width="16" height="42" rx="6" fill="#64748b" />
          <rect x="136" y="74" width="12" height="14" rx="2" fill="#f97316" fillOpacity={0.4 + 0.4 * Math.abs(osc(t, 0.8))} stroke="#f97316" strokeWidth="1" />
          {Array.from({ length: 3 }, (_, i) => (
            <circle key={i} cx="130" cy="79" r={20 + i * 12 + ((t * 20) % 12)} fill="none" stroke="#a855f7" strokeWidth="0.8" opacity={0.4 - i * 0.1} />
          ))}
          {L(10, 20, 'ACTIVE mmWAVE', '#cbd5e1', 8)}
          {L(10, 146, 'non-ionising · surface reflection · ATR avatar', '#d8b4fe')}
        </g>
      );
    },
  },
  {
    id: 'tech-matrix', group: 'xray-technologies', tag: 'Scatter physics', hex: '#4ade80',
    part: 'Choosing a technology — the decision map',
    summary: 'Access, thickness, what you need to know and how fast you need to know it — those four constraints pick the modality before any physics argument starts.',
    bullets: [
      'Two-sided access + material question → dual-energy transmission.',
      'One-sided access + organic contraband → backscatter.',
      'Superposition is the problem → CT, or multi-view if CT is too slow or costly.',
      'Substance identity is the question → XRD or spectral/K-edge methods as a second stage.',
      'Element composition matters → neutron interrogation or XRF, depending on depth.',
    ],
    draw: t => {
      const sel = Math.floor(saw(t, 0.22) * 4);
      const rows = [
        ['two-sided, material?', 'dual-energy transmission', '#f97316'],
        ['one-sided, organic?', 'backscatter', '#22d3ee'],
        ['superposition?', 'CT / multi-view', '#4ade80'],
        ['what substance?', 'XRD / K-edge', '#a78bfa'],
      ];
      return (
        <g>
          {rows.map((r, i) => (
            <g key={i} opacity={i === sel ? 1 : 0.4}>
              <rect x="20" y={32 + i * 27} width="104" height="21" rx="4" fill="#0b1220" stroke={i === sel ? (r[2] as string) : '#334155'} strokeWidth="1.1" />
              <text x="28" y={46 + i * 27} fontSize="6.5" fill="#cbd5e1">{r[0]}</text>
              <line x1="124" y1={42 + i * 27} x2="142" y2={42 + i * 27} stroke={i === sel ? (r[2] as string) : '#334155'} strokeWidth="1.1" />
              <rect x="142" y={32 + i * 27} width="102" height="21" rx="4" fill="#0b1220" stroke={i === sel ? (r[2] as string) : '#334155'} strokeWidth="1.1" />
              <text x="150" y={46 + i * 27} fontSize="6.5" fill={i === sel ? (r[2] as string) : '#64748b'}>{r[1]}</text>
            </g>
          ))}
          {L(10, 20, 'TECHNOLOGY DECISION MAP', '#cbd5e1', 8)}
        </g>
      );
    },
  },
];
