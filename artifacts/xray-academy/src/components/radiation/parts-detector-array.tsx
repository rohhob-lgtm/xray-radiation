import type { MicroAnim } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Cargo detector array — the real service-level chain used in cargo scanners:
// CdWO₄ crystal → photodiode → DAB → concentrator → array PC.
// Every draw() renders inside a 260 × 150 viewBox.
// ═══════════════════════════════════════════════════════════════════════════════

const saw = (t: number, hz = 1) => (t * hz) % 1;
const osc = (t: number, hz = 1) => Math.sin(t * Math.PI * 2 * hz);
const L = (x: number, y: number, s: string, c = '#94a3b8', size = 7, a: 'start' | 'middle' | 'end' = 'start') => (
  <text x={x} y={y} fontSize={size} fill={c} textAnchor={a}>{s}</text>
);

export const DETECTOR_ARRAY_ANIMS: MicroAnim[] = [
  {
    id: 'da-dab-anatomy', group: 'detectors', tag: 'Cargo array', hex: '#22c55e',
    part: 'DAB anatomy — crystals, diodes, ADC, FPGA',
    summary: 'A Diode Array Board carries a row of CdWO₄ crystals bonded to photodiodes, its own ADCs, an FPGA, a power supply and a single data port — a complete block of detector channels on one card.',
    bullets: [
      'Signal path on the card: crystal → photodiode → charge amplifier → ADC → FPGA → serial data out.',
      'Power in is a single 7.5 VDC feed from the concentrator; the board generates its own internal rails.',
      'Data leaves over one RJ45 connector using LVDS, so a long array run picks up very little noise.',
      'The PCB is bolted to a support framework with captive screws, locator pins and locator lugs.',
      'Captive screws matter in service: nothing can drop into the tunnel while a board is being changed.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      const stage = f < 0.25 ? 0 : f < 0.45 ? 1 : f < 0.65 ? 2 : f < 0.85 ? 3 : 4;
      const box = (x: number, w: number, lbl: string, on: boolean, col: string) => (
        <g>
          <rect x={x} y={62} width={w} height={26} rx={3}
            fill={on ? col + '33' : '#0b1220'} stroke={on ? col : '#334155'} strokeWidth={on ? 1.4 : 0.9} />
          <text x={x + w / 2} y={78} fontSize="6" fill={on ? col : '#64748b'} textAnchor="middle">{lbl}</text>
        </g>
      );
      return (
        <g>
          {Array.from({ length: 6 }, (_, i) => (
            <g key={i}>
              <rect x={16 + i * 9} y={30} width={7} height={16} rx={1}
                fill={stage === 0 ? '#f59e0b' : '#3f2a12'} stroke="#f59e0b" strokeWidth="0.6" />
              <rect x={16 + i * 9} y={47} width={7} height={7} rx={1}
                fill={stage >= 1 ? '#0b1b34' : '#0b1220'} stroke={stage >= 1 ? '#38bdf8' : '#334155'} strokeWidth="0.6" />
            </g>
          ))}
          {L(12, 26, 'CdWO₄ crystals', '#fbbf24', 6)}
          {L(12, 62, 'photodiodes', '#7dd3fc', 6)}
          {box(78, 32, 'ADC', stage >= 2, '#a78bfa')}
          {box(116, 34, 'FPGA', stage >= 3, '#4ade80')}
          {box(158, 30, 'PSU', true, '#f87171')}
          <rect x={196} y={62} width={30} height={26} rx={3} fill="#0b1220" stroke="#22c55e" strokeWidth="1.2" />
          {L(211, 78, 'RJ45', '#86efac', 6, 'middle')}
          {stage >= 4 && Array.from({ length: 3 }, (_, i) => (
            <circle key={i} cx={228 + ((f * 3 + i / 3) % 1) * 26} cy={75} r="1.8" fill="#22c55e" />
          ))}
          <line x1="156" y1="100" x2="176" y2="100" stroke="#f87171" strokeWidth="1.4" />
          {L(118, 105, '7.5 VDC in', '#fca5a5', 6)}
          {L(10, 20, 'DIODE ARRAY BOARD', '#cbd5e1', 8)}
          {L(10, 126, 'crystal → diode → ADC → FPGA → LVDS out', '#94a3b8', 6.5)}
          {L(10, 140, 'captive screws · locator pins · locator lugs', '#64748b', 6)}
        </g>
      );
    },
  },

  {
    id: 'da-cdwo4', group: 'detectors', tag: 'Cargo array', hex: '#fbbf24',
    part: 'Cadmium tungstate (CdWO₄) crystal',
    summary: 'The cargo-array scintillator of choice: dense, chemically inert, transparent, and it emits visible light whenever an X-ray or gamma ray deposits energy in it.',
    bullets: [
      'CdWO₄ is the cadmium salt of tungstic acid — a dense, chemically inert solid.',
      'High density and high effective atomic number give strong stopping power at MeV cargo energies.',
      'The crystal is transparent to its own emission, so light produced deep inside still reaches the diode.',
      'Low afterglow matters on a moving conveyor: a lingering glow would smear into the next image line.',
      'Each crystal is optically isolated from its neighbours so light cannot leak sideways into the wrong channel.',
    ],
    draw: t => {
      const f = saw(t, 0.6);
      const hit = f > 0.35;
      return (
        <g>
          <rect x="86" y="34" width="52" height="66" rx="4" fill="#3f2a12" stroke="#f59e0b" strokeWidth="1.5" />
          {L(76, 28, 'CdWO₄', '#fbbf24', 8)}
          <circle cx={112} cy={4 + Math.min(f, 0.35) * 100} r="2.6" fill="#fde047" opacity={hit ? 0 : 1} />
          {hit && Array.from({ length: 12 }, (_, i) => {
            const a = (i / 12) * Math.PI * 2;
            const r = (f - 0.35) * 90;
            return <circle key={i} cx={112 + Math.cos(a) * r * 0.5} cy={52 + Math.sin(a) * r * 0.55} r="1.5" fill="#67e8f9" />;
          })}
          <rect x="86" y="102" width="52" height="16" rx="2" fill="#0b1b34" stroke="#38bdf8" strokeWidth="1.2" />
          {L(112, 113, 'photodiode', '#7dd3fc', 6, 'middle')}
          <rect x="74" y="34" width="8" height="66" fill="#1f2937" />
          <rect x="142" y="34" width="8" height="66" fill="#1f2937" />
          {L(152, 46, 'optical', '#94a3b8', 6)}
          {L(152, 56, 'isolation', '#94a3b8', 6)}
          {L(152, 78, 'dense · inert', '#fbbf24', 6)}
          {L(152, 90, 'low afterglow', '#fbbf24', 6)}
          {L(10, 20, 'SCINTILLATOR CRYSTAL', '#cbd5e1', 8)}
          {L(10, 140, 'X-ray in ⇒ visible light out ⇒ diode current', '#94a3b8', 6.5)}
        </g>
      );
    },
  },

  {
    id: 'da-concentrator', group: 'detectors', tag: 'Cargo array', hex: '#38bdf8',
    part: 'Concentrator board — sixteen DABs on one card',
    summary: 'The concentrator powers sixteen DABs, gathers all their data and forwards a single Ethernet stream to the array PC. Board number one also generates the sync and the trigger for the whole array.',
    bullets: [
      'Sixteen DAB ports, each carrying LVDS data in and 7.5 V power out.',
      'Two ATMEGA128 AVR microcontrollers handle housekeeping; a Xilinx Spartan-3 FPGA handles the data path.',
      'Other connectors: Ethernet PHY, sync in, sync out, trigger, RS232 and 24 V supply in.',
      'A four-segment LED display and push buttons give local status without needing a laptop.',
      'Only board number one generates the sync signal and the trigger pulse — every other board follows it.',
    ],
    draw: t => {
      const active = Math.floor(saw(t, 0.8) * 16);
      return (
        <g>
          <rect x="20" y="26" width="220" height="98" rx="4" fill="#08151f" stroke="#38bdf8" strokeWidth="1.4" />
          {Array.from({ length: 16 }, (_, i) => (
            <rect key={i} x={26 + (i % 8) * 13} y={32 + Math.floor(i / 8) * 12} width="10" height="9" rx="1.5"
              fill={i === active ? '#38bdf8' : '#0b1220'} stroke={i === active ? '#7dd3fc' : '#334155'} strokeWidth="0.7" />
          ))}
          {L(26, 66, '16 × DAB ports (LVDS + 7.5 V)', '#7dd3fc', 6)}
          <rect x="26" y="72" width="34" height="16" rx="2" fill="#0b1220" stroke="#a78bfa" strokeWidth="0.9" />
          {L(43, 82, 'AVR', '#c4b5fd', 5.5, 'middle')}
          <rect x="64" y="72" width="34" height="16" rx="2" fill="#0b1220" stroke="#a78bfa" strokeWidth="0.9" />
          {L(81, 82, 'AVR', '#c4b5fd', 5.5, 'middle')}
          <rect x="102" y="72" width="52" height="16" rx="2" fill="#0b1220" stroke="#4ade80" strokeWidth="1.1" />
          {L(128, 82, 'Spartan-3', '#86efac', 5.5, 'middle')}
          <rect x="158" y="72" width="30" height="16" rx="2" fill="#0b1220" stroke="#64748b" strokeWidth="0.9" />
          {L(173, 82, 'flash', '#94a3b8', 5.5, 'middle')}
          <rect x="192" y="72" width="42" height="16" rx="2" fill="#111c2e" stroke="#f59e0b" strokeWidth="1.1" />
          {L(213, 84, String(1000 + active).slice(0, 4), '#fbbf24', 9, 'middle')}
          {['ETH', 'SYNC-I', 'SYNC-O', 'TRIG', 'RS232', '24V'].map((p, i) => (
            <g key={p}>
              <rect x={26 + i * 36} y={96} width={32} height={12} rx="2" fill="#0b1220" stroke="#475569" strokeWidth="0.8" />
              <text x={42 + i * 36} y={104} fontSize="5" fill="#94a3b8" textAnchor="middle">{p}</text>
            </g>
          ))}
          {L(10, 20, 'CONCENTRATOR BOARD', '#cbd5e1', 8)}
          {L(10, 140, 'powers, collects, forwards — one Ethernet stream out', '#94a3b8', 6.5)}
        </g>
      );
    },
  },

  {
    id: 'da-addressing', group: 'detectors', tag: 'Cargo array', hex: '#a78bfa',
    part: 'Rotary switch, addressing and the master board',
    summary: 'A rotary switch on each concentrator sets its place in the array, and that position maps directly onto its IP address. Position one is the master that generates sync and trigger.',
    bullets: [
      'Position 1 → 192.168.66.193, position 2 → .194, position 3 → .195, and so on up the array.',
      'Position 1 is the master: it alone generates the sync signal and the trigger pulse.',
      'The array PC sits on the same subnet, typically at .100; the managed switch at 192.168.66.2.',
      'Setting two concentrators to the same position is a classic field mistake with a very clear signature.',
      'That signature is one concentrator reporting no packets while another reports double packets.',
    ],
    draw: t => {
      const pos = 1 + Math.floor(saw(t, 0.3) * 6);
      const ang = (pos - 1) * 60 - 90;
      return (
        <g>
          <circle cx="66" cy="76" r="32" fill="#0b1220" stroke="#a78bfa" strokeWidth="1.4" />
          {Array.from({ length: 6 }, (_, i) => {
            const a = (i * 60 - 90) * Math.PI / 180;
            return (
              <g key={i}>
                <circle cx={66 + Math.cos(a) * 24} cy={76 + Math.sin(a) * 24} r="2"
                  fill={i + 1 === pos ? '#c4b5fd' : '#334155'} />
                <text x={66 + Math.cos(a) * 24} y={76 + Math.sin(a) * 24 - 5} fontSize="5"
                  fill={i + 1 === pos ? '#c4b5fd' : '#475569'} textAnchor="middle">{i + 1}</text>
              </g>
            );
          })}
          <line x1="66" y1="76" x2={66 + Math.cos(ang * Math.PI / 180) * 20} y2={76 + Math.sin(ang * Math.PI / 180) * 20}
            stroke="#c4b5fd" strokeWidth="2" />
          {L(66, 120, 'rotary switch', '#c4b5fd', 6.5, 'middle')}
          <rect x="114" y="48" width="126" height="24" rx="4" fill="#0b1220" stroke="#38bdf8" strokeWidth="1.2" />
          {L(177, 64, '192.168.66.' + (192 + pos), '#7dd3fc', 9, 'middle')}
          <rect x="114" y="80" width="126" height="20" rx="4"
            fill={pos === 1 ? '#14301c' : '#0b1220'} stroke={pos === 1 ? '#22c55e' : '#334155'} strokeWidth="1.1" />
          {L(177, 93, pos === 1 ? 'MASTER — sync + trigger' : 'slave — follows master', pos === 1 ? '#86efac' : '#64748b', 6.5, 'middle')}
          {L(114, 116, 'switch .2 · array PC .100', '#94a3b8', 6)}
          {L(10, 20, 'ARRAY ADDRESSING', '#cbd5e1', 8)}
        </g>
      );
    },
  },

  {
    id: 'da-sync-trigger', group: 'detectors', tag: 'Cargo array', hex: '#f472b6',
    part: 'Sync chain and LINAC trigger',
    summary: 'The master concentrator daisy-chains a sync signal down the array and takes a trigger from the LINAC, so every board integrates the same X-ray pulse into the same image line.',
    bullets: [
      'Sync runs concentrator to concentrator over LVDS: master → 2 → 3 → 4 → 5.',
      'The LINAC trigger arrives on RS422 and tells the array exactly when an X-ray pulse is coming.',
      'Every board must integrate over the same window, or the image line will not line up across the array.',
      'A broken sync cable kills that concentrator and everything downstream of it — the pattern points at the fault.',
      'A bad trigger cable shows as a poor image and an unstable scanner graph while X-rays are on.',
    ],
    draw: t => {
      const f = saw(t, 0.5);
      const broken = saw(t, 0.16) > 0.6;
      const reach = broken ? 2 : 5;
      return (
        <g>
          <rect x="14" y="60" width="26" height="30" rx="3" fill="#2a0b2e" stroke="#f472b6" strokeWidth="1.3" />
          {L(27, 79, 'M', '#f9a8d4', 9, 'middle')}
          {L(10, 54, 'master', '#f9a8d4', 6)}
          {Array.from({ length: 4 }, (_, i) => {
            const x = 62 + i * 46;
            const alive = i + 2 <= reach;
            return (
              <g key={i}>
                <rect x={x} y="60" width="26" height="30" rx="3"
                  fill={alive ? '#0b1b34' : '#2a0f0f'} stroke={alive ? '#38bdf8' : '#f87171'} strokeWidth="1.2" />
                <text x={x + 13} y="79" fontSize="8" fill={alive ? '#7dd3fc' : '#f87171'} textAnchor="middle">{i + 2}</text>
              </g>
            );
          })}
          {Array.from({ length: 4 }, (_, i) => {
            const x0 = 40 + i * 46, x1 = 62 + i * 46;
            const alive = i + 2 <= reach;
            return <line key={i} x1={x0} y1="75" x2={x1} y2="75"
              stroke={alive ? '#f472b6' : '#7f1d1d'} strokeWidth="1.4" strokeDasharray={alive ? '0' : '3 2'} />;
          })}
          {!broken && Array.from({ length: 3 }, (_, i) => (
            <circle key={i} cx={40 + ((f + i / 3) % 1) * 180} cy="75" r="2" fill="#f472b6" />
          ))}
          {broken && L(60, 108, 'sync open ⇒ this board and all downstream go dark', '#f87171', 6)}
          <rect x="14" y="26" width="52" height="18" rx="3" fill="#1e0b34" stroke="#a855f7" strokeWidth="1.1" />
          {L(40, 38, 'LINAC', '#d8b4fe', 6.5, 'middle')}
          <line x1="66" y1="35" x2="27" y2="58" stroke="#a855f7" strokeWidth="1.1" strokeDasharray="2 2" />
          {L(72, 38, 'trigger (RS422)', '#d8b4fe', 6)}
          {L(10, 20, 'SYNC + TRIGGER CHAIN', '#cbd5e1', 8)}
          {L(10, 140, 'one pulse, one line, every board in step', '#94a3b8', 6.5)}
        </g>
      );
    },
  },

  {
    id: 'da-startup', group: 'detectors', tag: 'Cargo array', hex: '#4ade80',
    part: 'Concentrator start-of-day sequence',
    summary: 'At power-up the concentrator boots its processor, boots its FPGA, discovers what type of DAB sits on each port, initialises them all, shows the firmware revisions, then goes dark after thirty seconds.',
    bullets: [
      'Step 1 — boot the AVR processor. Step 2 — load the FPGA configuration.',
      'Step 3 — detect the type of DAB connected on each port and boot each type appropriately.',
      'Step 4 — initialise every DAB. Step 5 — show revision numbers on the LED display.',
      'Step 6 — wait thirty seconds, then the display goes dark so it does not distract the operator.',
      'A missing or wrong-type board shows up here — watch the display at power-up before assuming a cable fault.',
    ],
    draw: t => {
      const step = Math.floor(saw(t, 0.22) * 6);
      const names = ['boot processor', 'boot FPGA', 'detect DAB types', 'initialise DABs', 'show revisions', 'display goes dark'];
      return (
        <g>
          {names.map((n, i) => (
            <g key={n} opacity={i <= step ? 1 : 0.3}>
              <circle cx="26" cy={30 + i * 19} r="6"
                fill={i < step ? '#14301c' : i === step ? '#4ade80' : '#0b1220'}
                stroke={i <= step ? '#4ade80' : '#334155'} strokeWidth="1" />
              <text x="26" y={33 + i * 19} fontSize="6" fill={i === step ? '#08150f' : '#86efac'} textAnchor="middle">{i + 1}</text>
              <text x="40" y={33 + i * 19} fontSize="7" fill={i === step ? '#e2e8f0' : '#94a3b8'}>{n}</text>
              {i < 5 && <line x1="26" y1={36 + i * 19} x2="26" y2={43 + i * 19} stroke={i < step ? '#4ade80' : '#334155'} strokeWidth="1" />}
            </g>
          ))}
          <rect x="176" y="52" width="66" height="34" rx="4" fill="#111c2e" stroke="#f59e0b" strokeWidth="1.2" />
          {L(209, 75, step === 4 ? 'r2.7' : step >= 5 ? '' : '····', '#fbbf24', 12, 'middle')}
          {L(174, 98, step >= 5 ? 'dark after 30 s' : 'LED display', '#94a3b8', 6)}
          {L(10, 20, 'START-OF-DAY SEQUENCE', '#cbd5e1', 8)}
        </g>
      );
    },
  },

  {
    id: 'da-faults', group: 'detectors', tag: 'Cargo array', hex: '#f87171',
    part: 'Array fault finding — symptom to cause',
    summary: 'The array fails in a small number of very recognisable patterns. Reading the pattern tells you which cable or board to touch before you open anything.',
    bullets: [
      'One concentrator showing no packets → that concentrator’s Ethernet cable.',
      'One concentrator and everything downstream of it dark → the sync cable.',
      'Bad image and an unstable scanner graph while X-rays are on → the trigger cable.',
      'One concentrator with no packets and another with double packets → two boards set to the same address.',
      'A horizontal black line across the image → a bad channel, a bad DAB, or the concentrator behind it.',
    ],
    draw: t => {
      const sel = Math.floor(saw(t, 0.22) * 5);
      const rows: [string, string, string][] = [
        ['one conc, no packets', 'Ethernet cable', '#38bdf8'],
        ['conc + all downstream dark', 'sync cable', '#f472b6'],
        ['unstable graph, bad image', 'trigger cable', '#a855f7'],
        ['no packets + double packets', 'duplicate address', '#fbbf24'],
        ['horizontal black line', 'channel / DAB / conc', '#f87171'],
      ];
      return (
        <g>
          {rows.map((r, i) => (
            <g key={i} opacity={i === sel ? 1 : 0.35}>
              <rect x="12" y={28 + i * 22} width="120" height="18" rx="3"
                fill="#0b1220" stroke={i === sel ? r[2] : '#334155'} strokeWidth="1" />
              <text x="18" y={40 + i * 22} fontSize="6" fill="#cbd5e1">{r[0]}</text>
              <line x1="132" y1={37 + i * 22} x2="146" y2={37 + i * 22} stroke={i === sel ? r[2] : '#334155'} strokeWidth="1" />
              <rect x="146" y={28 + i * 22} width="102" height="18" rx="3"
                fill="#0b1220" stroke={i === sel ? r[2] : '#334155'} strokeWidth="1" />
              <text x="152" y={40 + i * 22} fontSize="6" fill={i === sel ? r[2] : '#64748b'}>{r[1]}</text>
            </g>
          ))}
          {L(10, 20, 'SYMPTOM ⇒ LIKELY CAUSE', '#cbd5e1', 8)}
        </g>
      );
    },
  },

  {
    id: 'da-concloader', group: 'detectors', tag: 'Cargo array', hex: '#c4b5fd',
    part: 'conc_loader — the engineering console',
    summary: 'A Tcl/Tk tool installed on every array PC that talks to the concentrators over Ethernet or RS232: ping them, list their DABs, read diagnostics, drive the LEDs and push firmware.',
    bullets: [
      'Commands are prefixed by target: <code>10</code> is concentrator 1, <code>20</code> is concentrator 2, and so on.',
      '<code>10 ping</code> returns the application state, the board serial number and a pong that proves comms are good.',
      '<code>10 dab_summary</code> lists the Board_Id of every DAB the concentrator can see — the fastest way to find a missing board.',
      '<code>10 diag</code> returns concentrator diagnostics plus every firmware version, concentrator and DABs.',
      '<code>10 leds on</code> and <code>10 disp HIYA</code> drive the LEDs and the display so you can identify a board physically.',
    ],
    draw: t => {
      const line = Math.floor(saw(t, 0.3) * 5);
      const cmds: [string, string][] = [
        ['10 ping', 'state + serial + pong'],
        ['10 dab_summary', 'Board_Id of all DABs'],
        ['10 diag', 'diagnostics + firmware'],
        ['10 status 0', 'configuration settings'],
        ['10 leds on', 'light conc + its DABs'],
      ];
      return (
        <g>
          <rect x="12" y="24" width="236" height="102" rx="4" fill="#05080f" stroke="#c4b5fd" strokeWidth="1.1" />
          {L(18, 36, 'conc_loader ›', '#c4b5fd', 7)}
          {cmds.map((c, i) => (
            <g key={i} opacity={i <= line ? 1 : 0.18}>
              <text x="18" y={50 + i * 15} fontSize="6.5" fill="#86efac">{'> ' + c[0]}</text>
              <text x="122" y={50 + i * 15} fontSize="6" fill="#94a3b8">{c[1]}</text>
            </g>
          ))}
          <rect x="18" y={44 + line * 15} width={4 + 3 * Math.abs(osc(t, 2))} height="8" fill="#4ade80" opacity="0.5" />
          {L(10, 20, 'ENGINEERING SOFTWARE', '#cbd5e1', 8)}
          {L(12, 140, 'static IP .100 · UDP 1024 open · Hi-Discovery off', '#64748b', 6)}
        </g>
      );
    },
  },
];
