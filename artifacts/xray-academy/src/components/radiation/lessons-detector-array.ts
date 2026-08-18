import type { Lesson } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Mini-lessons — cargo detector array service chain.
// Sourced from field service training material for cargo scanner arrays.
// ═══════════════════════════════════════════════════════════════════════════════

export const DETECTOR_ARRAY_LESSONS: Record<string, Lesson> = {

  'da-dab-anatomy': {
    oneLiner: 'A Diode Array Board is one self-contained slice of the detector: a row of scintillator crystals, their photodiodes, the digitising electronics, a power supply and a single data port — all on one replaceable card.',
    analogy: 'A strip of camera sensor with its own brain and its own power supply. Unplug two connectors, undo the captive screws, and that slice of the image comes out in your hand.',
    watchFor: 'Follow the highlight along the chain: crystal → photodiode → ADC → FPGA → RJ45. Only two cables cross the board boundary — 7.5 V in and data out.',
    how: [
      'X-rays strike the row of CdWO₄ crystals along the top edge of the board.',
      'Each crystal converts the absorbed energy into a flash of visible light.',
      'A photodiode bonded directly beneath each crystal turns that light into charge.',
      'A charge amplifier and ADC digitise every channel; the FPGA packs the results into a serial frame.',
      'The frame leaves over a single RJ45 connector as LVDS, and the whole board runs from one 7.5 VDC feed.',
    ],
    physics: [
      'The board is an <b>integrating</b> detector: it accumulates charge over the line period rather than counting individual photons.',
      'CdWO₄ is chosen for density and stopping power at MeV cargo energies, where a light scintillator would be transparent to the beam.',
      'LVDS is used because it is differential: noise picked up along a long array run appears on both wires and cancels.',
      'Digitising on the board itself means only digital data travels the length of the array — analogue signals never leave the card.',
    ],
    engineering: [
      'A single 7.5 VDC feed comes from the concentrator; the board generates its own internal rails from it.',
      'The PCB bolts to a support framework using captive screws, locator pins and locator lugs.',
      'Locator pins and lugs set the board position mechanically, so channel alignment does not depend on how carefully it was fitted.',
      'Captive screws are a deliberate safety choice: no loose fastener can drop into the tunnel during a board change.',
      'Boards exist in several variants (different crystal pitches and quiet versions) — the concentrator detects the type at boot.',
    ],
    practice: [
      'One dead channel shows as a persistent horizontal line in the image at that channel’s position.',
      'A whole dead board shows as a contiguous band — much easier to localise than scattered noise.',
      'Always let the concentrator re-detect and re-initialise after a board swap; do not hot-swap and assume.',
      'Check the RJ45 and the power connector before condemning a board — an intermittent band is usually a connector.',
    ],
    numbers: [['Power in', '7.5 VDC'], ['Data out', 'LVDS over RJ45'], ['Crystal', 'CdWO₄'], ['Mounting', 'captive screws + pins']],
  },

  'da-cdwo4': {
    oneLiner: 'Cadmium tungstate is the workhorse cargo scintillator: dense enough to stop MeV photons, transparent enough to let its own light out, and chemically inert enough to sit in a tunnel for years.',
    analogy: 'A block of glass that glows faintly every time something invisible passes through it — and stops glowing the instant that thing stops.',
    watchFor: 'The X-ray disappears inside the crystal and a burst of blue light spreads out. The metal walls each side are the optical isolation that keeps that light in its own channel.',
    how: [
      'An X-ray photon enters the crystal and deposits energy through photoelectric absorption or Compton scattering.',
      'That energy excites the crystal lattice, which relaxes by emitting visible light.',
      'The number of light photons is proportional to the energy deposited.',
      'Because the crystal is transparent to its own emission, light created deep inside still escapes to the bottom face.',
      'The photodiode bonded underneath converts that light burst into a charge pulse.',
    ],
    physics: [
      'CdWO₄ is the cadmium salt of tungstic acid — a dense, chemically inert solid.',
      'High density and high effective atomic number give it real stopping power at the MeV energies cargo scanning uses.',
      'Afterglow is the key spec on a moving conveyor: residual light from one line would contaminate the next.',
      'It is an integrating detector — the diode reads accumulated charge, so there is no energy spectrum, only intensity.',
    ],
    engineering: [
      'Crystals are cut and polished to a fixed pitch that defines the array’s channel spacing.',
      'Reflective or opaque septa between crystals stop light leaking sideways into the neighbouring channel.',
      'Optical coupling between crystal and diode must be void-free; a bubble becomes a permanently low channel.',
      'The crystal is fragile relative to the board it sits on — mechanical shock during handling is a real failure mode.',
    ],
    practice: [
      'A cracked or delaminated crystal shows as one channel reading persistently low, not noisy.',
      'That is different from a dead electronic channel, which usually reads zero or rails.',
      'Gain calibration compensates for small crystal-to-crystal differences; skip it after a change and you get visible striping.',
    ],
    numbers: [['Material', 'CdWO₄'], ['Role', 'X-ray → visible light'], ['Key spec', 'low afterglow'], ['Mode', 'integrating']],
  },

  'da-concentrator': {
    oneLiner: 'The concentrator is the hub of the array: it powers sixteen DABs, collects everything they measure, and sends one Ethernet stream onward — and board one also keeps the whole array in time.',
    analogy: 'A stage manager for sixteen musicians. It feeds them, collects what they play, sends one mix to the desk — and if it is the first one, it also beats the time.',
    watchFor: 'Sixteen DAB ports across the top, the two AVRs and the FPGA in the middle, and the six system connectors along the bottom. Watch which port lights up as it polls each board.',
    how: [
      'Each of the sixteen ports feeds one DAB with 7.5 V and receives its LVDS data.',
      'The FPGA handles the fast data path, gathering frames from all sixteen boards.',
      'The AVR microcontrollers handle housekeeping: configuration, LED display, buttons and setpoints.',
      'Collected data goes out through the Ethernet PHY to the network switch and on to the array PC.',
      'If the rotary switch is set to position one, this board also generates the sync signal and the trigger pulse.',
    ],
    physics: [
      'Concentrating sixteen boards into one Ethernet stream is what keeps the cabling in a long array manageable.',
      'The FPGA is needed because the aggregate data rate from sixteen boards is far beyond what a microcontroller could move.',
      'Splitting duties — FPGA for data, AVR for housekeeping — keeps the fast path free of slow tasks.',
    ],
    engineering: [
      'Two ATMEGA128 AVR microcontrollers and a Xilinx Spartan-3 FPGA sit on the board with their own flash.',
      'Connectors: sixteen DAB ports, Ethernet, sync in, sync out, trigger, RS232, and a 24 V supply input.',
      'A four-segment LED display and push buttons give local status and self-test without a laptop.',
      'The RESET button is hard-wired to the AVR reset; the other buttons are firmware dependent.',
      'Two firmware families exist: VGather (more data types, tolerant of cable length) and Netgather (lower noise, simple packet counting).',
    ],
    practice: [
      'Self-test behaviour differs by firmware: one style blindly tests slot 1, another tests only slots it believes are populated.',
      'Blindly testing empty slots will report a failure that is not real — know which firmware you are on before believing it.',
      'One concentrator with no packets is nearly always its own Ethernet cable, not the board.',
      'The board supplies power to its DABs, so a concentrator power fault takes sixteen boards dark at once.',
    ],
    numbers: [['DABs per board', '16'], ['DAB supply', '7.5 V'], ['Board supply', '24 V'], ['FPGA', 'Xilinx Spartan-3']],
  },

  'da-addressing': {
    oneLiner: 'A rotary switch decides where a concentrator sits in the array, what IP address it answers on, and whether it is the master that generates sync and trigger.',
    analogy: 'Numbered seats in an orchestra. Seat one is the conductor; everyone else plays to the beat. Two people in seat one and the performance falls apart in a very specific way.',
    watchFor: 'As the switch steps round, the IP address changes with it — and only position one turns the board green as MASTER.',
    how: [
      'Set the rotary switch to the board’s intended position in the array.',
      'The firmware derives the IP address directly from that position: position 1 is .193, position 2 is .194, and so on.',
      'Position 1 additionally elects the board as master, which generates sync and trigger for the whole array.',
      'The array PC and the network switch sit on the same subnet, so everything is reachable from one console.',
      'Power-cycle after changing the switch — the address is read at boot.',
    ],
    physics: [
      'Deriving the address from a physical switch means the array topology is visible on the hardware, not buried in a config file.',
      'Exactly one master is required: two sync sources would fight and the line numbering would be ambiguous.',
    ],
    engineering: [
      'Position 1 → 192.168.66.193, then .194, .195, .196, .197, .198 as you go up the array.',
      'The managed switch typically sits at 192.168.66.2 and the array PC at 192.168.66.100.',
      'Concentrator 1 serves DABs 1–16, concentrator 2 serves 17–32, and so on up to 80 boards across five concentrators.',
      'Because the mapping is fixed, a channel number in the image translates directly to a physical board and port.',
    ],
    practice: [
      'Two concentrators on the same position is the classic field mistake after a board swap.',
      'Its signature is unmistakable: one concentrator reports no packets while another reports double packets.',
      'Always confirm the switch position on the replacement board before fitting it, not after.',
      'Write the position on the service record — the next engineer will not be able to see it once the covers are on.',
    ],
    numbers: [['Position 1', '192.168.66.193'], ['Switch', '192.168.66.2'], ['Array PC', '192.168.66.100'], ['Master', 'position 1 only']],
  },

  'da-sync-trigger': {
    oneLiner: 'Sync and trigger are what turn eighty independent boards into one image: the trigger says when the X-ray pulse happens, and sync makes every board count the same line.',
    analogy: 'A rowing crew. The trigger is the stroke; sync is the cox making sure everyone counts the same stroke number. Lose either and the boat still moves, but nothing lines up.',
    watchFor: 'Pulses travel from the master along the chain. When the sync breaks, notice that the failure is not just one board — it is that board and everything after it.',
    how: [
      'The LINAC signals each X-ray pulse to the master concentrator over RS422.',
      'The master converts that into a sync signal and sends it out on its SYNC-OUT port.',
      'Concentrator 2 receives it on SYNC-IN and passes it on from its own SYNC-OUT, and so on down the chain.',
      'Every board integrates its channels over the same window and tags the result with the same line number.',
      'The array PC reassembles all the streams into one image line, board by board.',
    ],
    physics: [
      'Integration windows must align, or the same physical position appears at different times in different parts of the image.',
      'The trigger has to arrive before the pulse, not with it — the boards need setup time to start integrating.',
      'Daisy-chained sync accumulates a small delay per hop, which the firmware accounts for.',
    ],
    engineering: [
      'Sync runs over LVDS between concentrators; the LINAC trigger arrives on RS422.',
      'The chain is deliberately serial rather than a star, which keeps cabling simple but makes it fail in a chain.',
      'That chain failure mode is a diagnostic gift: the first dark board in the chain is next to the bad cable.',
    ],
    practice: [
      'A concentrator and everything downstream of it showing no packets points straight at the sync cable into that board.',
      'A bad trigger cable gives a poor image and an unstable scanner graph while X-rays are on — the boards are alive but out of step.',
      'Check the trigger before chasing image quality problems; it looks like a detector fault but it is a timing fault.',
    ],
    numbers: [['Trigger', 'RS422 from LINAC'], ['Sync', 'LVDS, daisy chain'], ['Source', 'master (position 1)'], ['Failure', 'board + downstream']],
  },

  'da-startup': {
    oneLiner: 'The start-of-day sequence is a free diagnostic: in six steps the concentrator tells you it booted, what boards it found, and which firmware everything is running.',
    analogy: 'An aircraft pre-flight check that runs itself and reads the results out loud — but only for thirty seconds, so you have to be watching.',
    watchFor: 'The six steps light up in order, and the LED display shows revision numbers at step five before going dark at step six.',
    how: [
      'The AVR processor boots first.',
      'The FPGA configuration is then loaded from flash.',
      'The concentrator probes each port to detect what type of DAB is connected, and boots each type appropriately.',
      'Every detected DAB is initialised with its operating parameters.',
      'Revision numbers are shown on the four-segment LED display.',
      'After thirty seconds the display goes dark so it does not distract the operator during normal running.',
    ],
    physics: [
      'Type detection matters because different DAB variants need different boot images and different initialisation.',
      'Initialising every board with matched setpoints is what makes the channels comparable across the whole array.',
    ],
    engineering: [
      'Setpoints live in the AVR EEPROM: LED behaviour, DAB pinging, DDC range, and the maximum and minimum PPS limits.',
      'Reading setpoints reports the lowest selected board; writing them updates all selected boards at once.',
      'Firmware comes in three separate files — FPGA config, AVR config and DAB config — pushed from the engineering console.',
    ],
    practice: [
      'Watch the display at power-up before you start pulling cables — a missing board shows up in step three.',
      'The thirty-second blackout is normal behaviour, not a fault; use the console to turn the LEDs back on if you need them.',
      'After any firmware push, power-cycle and watch the full sequence to confirm all boards came back.',
    ],
    numbers: [['Steps', '6'], ['Display timeout', '30 s'], ['Setpoints stored in', 'AVR EEPROM'], ['Firmware files', 'FPGA + AVR + DAB']],
  },

  'da-faults': {
    oneLiner: 'The array fails in a handful of very distinctive patterns — read the pattern first and it tells you which single cable or board to touch.',
    analogy: 'A doctor reading a rash. The shape and spread say more than any single spot does; treat the pattern, not the pixel.',
    watchFor: 'Each symptom on the left maps to exactly one likely cause on the right. The mapping is one-to-one, which is what makes it useful.',
    how: [
      'Start at the array PC and look at packet counts per concentrator — that is the cheapest measurement available.',
      'If exactly one concentrator is silent, suspect its own Ethernet path first.',
      'If a concentrator and everything after it is silent, walk the sync chain to the first dark board.',
      'If packets are healthy but the image is not, suspect timing — the trigger — before suspecting detectors.',
      'If one board is silent and another is doubled, two boards are answering on the same address.',
    ],
    physics: [
      'Ethernet is per-board, so an Ethernet fault is local; sync is chained, so a sync fault propagates downstream.',
      'That difference in topology is exactly what lets you separate the two from the symptom alone.',
      'A single bad channel affects one image row; a bad board affects a contiguous band.',
    ],
    engineering: [
      'One concentrator, no packets → that concentrator’s Ethernet cable.',
      'One concentrator plus everything downstream dark → the sync cable into that board.',
      'Bad image with an unstable scanner graph during X-rays → the trigger cable.',
      'No packets on one board and double packets on another → duplicate rotary switch positions.',
      'Horizontal black line in the image → a bad channel, a bad DAB, or the concentrator serving it.',
    ],
    practice: [
      'Change one thing at a time and re-check the packet counts before moving on.',
      'Swap cables before swapping boards — cables fail far more often and cost far less.',
      'Record the symptom pattern in the service log; it is what makes the next visit faster.',
    ],
    numbers: [['First measurement', 'packets per concentrator'], ['Local fault', 'Ethernet'], ['Chained fault', 'sync'], ['Timing fault', 'trigger']],
  },

  'da-concloader': {
    oneLiner: 'conc_loader is the engineering console for the array — a small Tcl/Tk tool that lets you interrogate every concentrator and every DAB from the array PC without opening a single panel.',
    analogy: 'A diagnostic scanner plugged into a car. You ask each module what it is, how it feels and what software it is running, before you reach for a spanner.',
    watchFor: 'Each command is prefixed by its target — 10 for concentrator 1, 20 for concentrator 2. The prefix is how you aim.',
    how: [
      'Install and set the array PC to a static IP on the array subnet, then run the supplied Ethernet setup script.',
      'Open the console and address a concentrator by prefix: <code>10</code> for the first, <code>20</code> for the second, and so on.',
      '<code>10 ping</code> confirms comms and returns the application state and the board serial number.',
      '<code>10 dab_summary</code> lists the Board_Id of every DAB that concentrator can see.',
      '<code>10 diag</code> returns full diagnostics plus firmware versions for the concentrator and all its DABs.',
    ],
    physics: [
      'The tool talks over UDP on the array subnet, which is why the firewall exception matters more than anything else in setup.',
      'Reading a board’s serial number over the wire is what lets you match a logical channel to a physical card.',
    ],
    engineering: [
      'Written in Tcl/Tk, installed on every array PC, and able to connect over Ethernet or RS232.',
      'Setup: static IP on the array subnet, run the Ethernet setup script, allow the application through the firewall, and open UDP port 1024 both directions.',
      'On a managed switch, the vendor discovery protocol has to be turned off or it interferes with the array traffic.',
      'The GUI adds setpoints and firmware pages: get and set setpoints, and push FPGA, AVR and DAB firmware images.',
    ],
    practice: [
      '<code>10 leds on</code> and <code>10 disp HIYA</code> light the concentrator and its DABs so you can physically identify the right board in a long array.',
      '<code>10 dab_summary</code> is the fastest way to prove a board is missing rather than merely quiet.',
      'Take a <code>diag</code> capture before and after any firmware change — it is the only record of what was running.',
      'Get setpoints reports the lowest selected board, so check what you are actually reading before you trust it.',
    ],
    numbers: [['Language', 'Tcl/Tk'], ['Links', 'Ethernet or RS232'], ['UDP port', '1024 both ways'], ['Target prefix', '10, 20, 30 …']],
  },
};
