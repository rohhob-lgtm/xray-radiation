import type { Lesson } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Mini-lessons — X-ray tube, LINAC and betatron components.
// Keyed by MicroAnim id. Plain language first, then physics, then engineering.
// ═══════════════════════════════════════════════════════════════════════════════

export const TUBE_LINAC_LESSONS: Record<string, Lesson> = {

  // ─── X-RAY TUBE ─────────────────────────────────────────────────────────────
  'xt-filament': {
    oneLiner: 'Heat a tungsten wire hot enough and electrons literally boil off its surface — that cloud of free electrons is the raw material for every X-ray the tube will ever make.',
    analogy: 'Like steam rising off a boiling kettle: raise the temperature a little and far more steam appears. Here the "steam" is electrons, and the kettle temperature is the filament current.',
    watchFor: 'The orange glow intensity and the size of the electron cloud rise and fall together. Note that the cloud sits around the filament — it has not gone anywhere yet.',
    how: [
      'A small transformer supplies roughly 8–12 V at 3–5 A to the coiled tungsten filament.',
      'Resistive heating drives the filament to about 2 400 K — bright orange-white.',
      'Some electrons in the metal gain more thermal energy than the surface barrier (the work function) and escape.',
      'They hover in a cloud just outside the wire, held back by their own negative charge. This is the <b>space charge</b>.',
      'When high voltage is later applied, this cloud is what gets pulled to the anode. No cloud, no beam.',
    ],
    physics: [
      'Richardson–Dushman: <code>J = A·T²·e^(−φ/kT)</code>. The exponential term is why a tiny temperature change produces a large current change.',
      'Tungsten\'s work function φ ≈ 4.5 eV — the energy an electron needs to break free of the surface.',
      'The space-charge cloud is self-limiting: escaped electrons repel the next ones, so emission settles at equilibrium.',
      'At low kV the tube runs <b>space-charge limited</b> (current set by the cloud); at high kV it becomes <b>emission limited</b> (current set by filament temperature).',
    ],
    engineering: [
      'Tungsten is chosen for its 3 422 °C melting point and low vapour pressure — almost nothing else survives 2 400 K continuously.',
      'The filament is coiled to pack a long emitting length into a small focal area.',
      'The filament supply floats at cathode potential (tens of kV below ground), so it needs a high-isolation transformer.',
      'Dual-filament cathodes give a fine focus (≈0.3 mm) and a broad focus (≈1.2 mm) selectable from the console.',
    ],
    practice: [
      'Filament current is the mA control. kVp does not set tube current — a common conceptual mistake.',
      'The life-limiting mechanism is tungsten evaporation: the wire thins until it opens. Typical life 500–2 000 exposure hours.',
      'Standby preheat keeps the filament warm below emission temperature so exposures start instantly without wasting filament life.',
      'An open filament gives no exposure and zero tube current — usually a tube-insert replacement.',
    ],
    numbers: [['Filament supply', '8–12 V / 3–5 A'], ['Operating temperature', '≈ 2 400 K'], ['Work function (W)', '4.5 eV'], ['Typical life', '500–2 000 h']],
  },

  'xt-focus-cup': {
    oneLiner: 'A negatively charged metal cup around the filament acts as an electrostatic lens, squeezing the spreading electron cloud into a small rectangle on the anode.',
    analogy: 'Like cupping your hands around a jet of water to keep it from spraying everywhere — except the "hands" are made of electric field, not metal touching the beam.',
    watchFor: 'Electrons leave the cup spread apart and converge as they travel. The dashed field lines show the lens shape doing the work.',
    how: [
      'The cup surrounds the filament and is held negative relative to it.',
      'Because electrons are negative, the cup repels them inward from the sides.',
      'The result is an electric field shaped like a converging lens: electrons entering wide leave narrow.',
      'They cross over and land on the anode in a small rectangle — the <b>focal spot</b>.',
      'Push the cup bias far enough negative and the field pinches the beam off completely: the tube is switched off electrically.',
    ],
    physics: [
      'The cup is an electrostatic lens; its shape sets the focal length exactly as glass curvature does for light.',
      'Mutual repulsion (space-charge blow-up) would spread the beam over the whole anode face without it.',
      'Bias of −100 to −4 000 V relative to the filament; cut-off occurs around −2 000 to −4 000 V.',
      'Focal spot size directly limits image sharpness through geometric unsharpness <code>Ug = f·b/a</code>.',
    ],
    engineering: [
      'Cup geometry, filament position and bias are designed together — moving one changes the focal spot.',
      'Grid-controlled tubes bring the bias out to a fast switch, allowing microsecond exposures.',
      'The two filaments in a dual-focus cathode sit in separate slots in the same cup.',
      'Focal spot size is verified against IEC 60336 using a star or slit pattern.',
    ],
    practice: [
      'A focal spot that has grown (from filament sag or ageing) shows up as loss of fine detail before anything else fails.',
      'Grid switching is the basis of pulsed fluoroscopy — halving the pulse rate roughly halves the dose.',
      'Never assume the nominal focal spot: it blooms with mA, so measure at the mA you actually use.',
    ],
    numbers: [['Bias range', '−100 to −4 000 V'], ['Fine focus', '≈ 0.3 mm'], ['Broad focus', '≈ 1.2 mm'], ['Standard', 'IEC 60336']],
  },

  'xt-anode-disc': {
    oneLiner: 'Only about one percent of the electron beam power becomes X-rays; the rest is heat, so the target is spun to spread that heat around a circular track instead of burning one spot.',
    analogy: 'Like turning a kebab over a fire: keep it still and one side chars, keep it turning and the whole surface shares the heat.',
    watchFor: 'The bright red patch is the instantaneous focal spot. It stays fixed in space while the metal underneath it keeps moving — that is the whole trick.',
    how: [
      'The electron beam is aimed at one fixed point in space, a few millimetres from the disc edge.',
      'The disc spins at 3 000–10 800 RPM, so fresh cold metal continuously arrives at that point.',
      'Each piece of the focal track is heated for microseconds, then has a whole revolution to radiate that heat away.',
      'Effective heat capacity rises by the ratio of track circumference to focal spot length — often several hundred times.',
      'Between exposures, heat radiates from the disc to the housing, where oil carries it away.',
    ],
    physics: [
      'X-ray production efficiency ≈ <code>1.1 × 10⁻⁹ · Z · V</code> — roughly 1 % at 100 kV on tungsten. The other 99 % is heat.',
      'In vacuum there is no conduction or convection path from the disc: it can only radiate (Stefan–Boltzmann, T⁴).',
      'The focal track surface reaches about 2 600 °C during an exposure while the bulk disc stays far cooler.',
      'Anode heat units accumulate as <code>kVp × mA × s</code> (times a waveform factor); the rating curve is a thermal limit, not an electrical one.',
    ],
    engineering: [
      'Disc is rhenium-alloyed tungsten (resists thermal cracking) brazed onto a molybdenum or graphite-backed substrate for heat storage.',
      'Graphite backing raises heat capacity dramatically at low mass — important for the bearings.',
      'The disc is balanced to fine tolerance; imbalance destroys bearings in a rotating vacuum assembly.',
      'Larger diameter and higher speed both raise the rating, but both stress the bearings harder.',
    ],
    practice: [
      'Thermal overload pits and roughens the track: output falls, the beam softens and image mottle appears.',
      'Rapid-sequence protocols must respect the cooling curve — the interlock wait state is protecting a very expensive part.',
      'A cracked anode usually announces itself as sudden output loss plus vacuum failure.',
    ],
    numbers: [['Rotation speed', '3 000–10 800 RPM'], ['Track temperature', '≈ 2 600 °C'], ['X-ray efficiency', '≈ 1 %'], ['Disc material', 'W-Re on Mo/graphite']],
  },

  'xt-heel': {
    oneLiner: 'Tilting the target face lets a big heated area project as a small sharp spot — but photons leaving toward the anode side pass through more target metal and come out weaker.',
    analogy: 'Look at a tilted coin edge-on and it appears as a thin line. The heat spreads over the whole coin, but the beam only "sees" the thin projection.',
    watchFor: 'The yellow intensity bars on the right: short at the anode side (top), long at the cathode side (bottom). Watch the angle θ sweep and the field change with it.',
    how: [
      'Electrons strike a target face tilted 7°–20° from vertical.',
      'The heated area (actual focal spot) is long along the tilt direction.',
      'Viewed from the patient or detector, that long area projects as a much shorter one — the effective focal spot.',
      'Photons produced slightly below the surface must escape through target material.',
      'Those heading toward the anode side traverse more metal, so that side of the field is dimmer. That is the heel effect.',
    ],
    physics: [
      'Line-focus principle: <code>effective spot = actual spot × sin θ</code>.',
      'A 7° anode gives a sharper image but covers a smaller field at a given distance.',
      'Heel-effect intensity variation can reach 20–45 % across a large field.',
      'The effect worsens with smaller anode angle, larger field size and shorter source-to-image distance.',
    ],
    engineering: [
      'Anode angle is a permanent design choice trading sharpness against field coverage — it cannot be changed in service.',
      'Steep angles (7°–9°) suit small-field, high-resolution work; shallower angles (16°–20°) suit large fields.',
      'Target roughening from age deepens the heel effect because photons cross more disturbed surface.',
    ],
    practice: [
      'Use the heel deliberately: place the thicker part of the object on the cathode side where intensity is highest.',
      'A sudden increase in heel effect on QA films is an early indicator of anode surface damage.',
      'For flat-field digital detectors, heel-effect correction is part of the calibration, not a physics fix.',
    ],
    numbers: [['Anode angle', '7°–20°'], ['Intensity variation', '20–45 %'], ['Effective spot', 'actual × sin θ']],
  },

  'xt-stator': {
    oneLiner: 'The anode is spun by an induction motor whose windings sit outside the glass — the rotating magnetic field passes straight through the vacuum envelope so no wires ever cross it.',
    analogy: 'Exactly how an induction cooktop heats a pan through the glass: the field crosses the barrier, not the current.',
    watchFor: 'The dashed field rings rotate around the copper rotor, dragging it along. Nothing physically connects the outside to the inside.',
    how: [
      'Stator windings outside the envelope are driven with phase-shifted AC, producing a rotating magnetic field.',
      'That field induces currents in the copper rotor attached to the anode stem inside the vacuum.',
      'Induced currents create their own field, which is dragged around by the stator field — the rotor turns.',
      'The anode reaches full speed in 1–2 seconds; the exposure interlock waits for it.',
      'After the series, dynamic braking slows the disc to limit bearing wear.',
    ],
    physics: [
      'Standard induction-motor action: the rotor always turns slightly slower than the field (slip) — that slip is what generates torque.',
      'Magnetic fields pass through glass and ceramic unaffected, which is why no vacuum feed-through is needed.',
      'In vacuum there is no air drag, so once at speed very little power is required to maintain rotation.',
    ],
    engineering: [
      'Bearings run dry with a silver or lead lamellar solid-film lubricant — any oil would evaporate and destroy the vacuum.',
      'Spiral-groove liquid-metal (gallium alloy) bearings allow continuous high-speed rotation and conduct heat out of the anode stem.',
      'Bearing life, not the target, is often what ends a modern CT tube\'s service life.',
      'The rotor must be balanced; imbalance at 10 000 RPM in vacuum is unforgiving.',
    ],
    practice: [
      'Rising noise, longer run-up time or a rotation fault interlock are the classic end-of-life symptoms.',
      'Never defeat a rotation interlock: firing at a stationary anode destroys the target in a single exposure.',
      'A stator fault (open winding) looks like a tube fault — check the drive before condemning the insert.',
    ],
    numbers: [['Run-up time', '1–2 s'], ['Speeds', '3 000 / 10 000 RPM'], ['Lubricant', 'solid film or Ga alloy']],
  },

  'xt-window': {
    oneLiner: 'Photons have to escape the tube, and whatever they pass through on the way out absorbs the softest ones — so the window material decides the low-energy end of your spectrum.',
    analogy: 'A window pane you have to look through: ordinary glass blocks ultraviolet, quartz lets it through. Same idea, different part of the spectrum.',
    watchFor: 'Red dots are soft photons — they stop at the window. Yellow photons pass. The lower the window absorption, the more red gets through.',
    how: [
      'X-rays are produced inside the target and radiate in all directions.',
      'The useful fraction heads toward the port and must cross the tube envelope, the insulating oil and the housing window.',
      'Each layer absorbs preferentially at low energy, where the photoelectric cross-section is huge.',
      'What survives is the beam you actually work with — the sum of these layers is the <b>inherent filtration</b>.',
      'A beryllium window (Z = 4) is nearly transparent below 10 keV; borosilicate glass cuts off around 15–20 keV.',
    ],
    physics: [
      'Photoelectric absorption scales roughly as <code>Z³·⁵ / E³</code> — so low-Z material and higher energy both mean better transmission.',
      'Inherent filtration is expressed in mm of aluminium equivalent so different materials can be compared.',
      'Removing soft photons raises the mean beam energy — the half-value layer goes up.',
    ],
    engineering: [
      'Beryllium 0.5–1 mm is used where soft photons matter: mammography, XRF, crystallography.',
      'General radiography tubes use glass or metal ports because soft photons would only add skin dose.',
      'IEC 60522 defines how inherent filtration is measured and declared by the manufacturer.',
    ],
    practice: [
      'Tungsten evaporated from the target slowly plates the window, hardening the beam and cutting output — a gradual, easily-missed drift.',
      'Rising HVL on routine QA with no protocol change points straight at window contamination.',
      'Beryllium dust is toxic: a cracked Be window is a health-physics event, not just a vacuum failure.',
    ],
    numbers: [['Be window', '0.5–1 mm'], ['Be atomic number', 'Z = 4'], ['Glass cut-off', '≈ 15–20 keV'], ['Standard', 'IEC 60522']],
  },

  'xt-filter': {
    oneLiner: 'Low-energy photons cannot reach the detector but are absorbed in the object, so a metal filter removes them before they ever enter — less dose, same image.',
    analogy: 'Sunscreen blocks UV that only burns you, while letting through the visible light you actually see by.',
    watchFor: 'The dashed curve is the raw spectrum; the solid one is what remains after filtration. Watch the low-energy side collapse while the peak shifts right.',
    how: [
      'The raw spectrum from the target contains photons from almost zero up to the tube potential.',
      'Photons below roughly 20–30 keV are absorbed within the first centimetres of tissue or material.',
      'They contribute dose and heat but no signal at the detector.',
      'A metal sheet in the beam absorbs them preferentially before they ever reach the object.',
      'The surviving beam is "harder": higher mean energy, higher half-value layer, lower entrance dose.',
    ],
    physics: [
      'Filtration exploits the same <code>Z³·⁵/E³</code> photoelectric dependence — attenuation is far stronger at low energy.',
      'The mean energy rises but the peak (kVp) does not change: filtration cannot exceed the endpoint.',
      'HVL is the practical measurement of filtration — it is what an inspector actually measures.',
      'K-edge filters (erbium, rhodium) shape a narrow band rather than simply cutting the bottom off.',
    ],
    engineering: [
      'Aluminium is standard; copper (0.1–0.3 mm) is used for paediatric and fluoroscopy protocols.',
      'Total filtration above 70 kV must be at least 2.5 mm Al equivalent for diagnostic units.',
      'Motorised filter wheels let the system change filtration per protocol automatically.',
      'Industrial NDT uses copper or lead pre-filters mainly to suppress scatter and improve latitude.',
    ],
    practice: [
      'Over-filtration is a real cost: tube output drops, exposure times lengthen and subject contrast falls.',
      'Missing or wrong filtration is a regulatory finding, and it is checked by HVL measurement at acceptance.',
      'If output drops after service, verify the filter wheel position before investigating the tube.',
    ],
    numbers: [['Minimum > 70 kV', '2.5 mm Al eq.'], ['Typical Cu filter', '0.1–0.3 mm'], ['Effect', 'HVL ↑, entrance dose ↓']],
  },

  'xt-collimator': {
    oneLiner: 'Everything outside the region you actually need to see is pure dose and scatter, so lead blades trim the beam to exactly that region and no more.',
    analogy: 'A torch with an adjustable beam: narrow it to the page you are reading instead of lighting the whole room.',
    watchFor: 'As the blades open and close, watch the field on the detector scale with them. The source never changes — only how much of its output escapes.',
    how: [
      'Two orthogonal pairs of lead blades sit just below the tube port.',
      'Moving them changes the size and shape of the rectangular field.',
      'A mirror at 45° projects a light field that shows exactly where the X-ray field will land.',
      'Anything outside the blades is absorbed — that radiation never reaches the object at all.',
      'Smaller field means less irradiated volume, which means dramatically less scatter reaching the detector.',
    ],
    physics: [
      'Scatter production is roughly proportional to irradiated volume, so field size is the dominant scatter control.',
      'Lead thickness is set so leakage through the blades is negligible compared with the primary beam.',
      'Reducing field size improves contrast without changing kV, mA or filtration at all.',
    ],
    engineering: [
      'Light/radiation field congruence must stay within 2 % of the source-to-image distance (IEC 60601-1-3).',
      'Positive beam limitation automatically restricts the field to the loaded cassette size.',
      'Industrial systems often use fixed cones or slit collimators matched to a specific detector geometry.',
    ],
    practice: [
      'Collimation is the single most effective operator-controlled dose and image-quality measure.',
      'Light-field/radiation-field misalignment is a routine QA test and a common failure after a lamp change.',
      '"Coning down" is not just dose ethics — it visibly improves the image you are trying to interpret.',
    ],
    numbers: [['Congruence limit', '2 % of SID'], ['Blades', 'two orthogonal pairs'], ['Standard', 'IEC 60601-1-3']],
  },

  'xt-cooling': {
    oneLiner: 'The oil around the tube insert does two jobs at once: it insulates tens of kilovolts and it carries the anode heat out to a radiator.',
    analogy: 'Engine oil in a car — it lubricates and it cools. Here it insulates and it cools, and it must never be substituted with the wrong grade.',
    watchFor: 'Red dots leaving the housing hot, blue dots returning cold. The heat glow inside pulses with the exposure cycle.',
    how: [
      'Heat radiates from the anode disc across the vacuum to the insert envelope.',
      'The envelope transfers it into the surrounding dielectric oil by conduction.',
      'Oil circulates — by convection in small units, by pump in high-duty systems.',
      'A heat exchanger (air or water) dumps the heat outside the housing.',
      'As the oil warms it expands; a bellows or diaphragm absorbs the volume change and trips a thermal switch at the limit.',
    ],
    physics: [
      'Vacuum blocks conduction and convection from the disc — radiation (∝ T⁴) is the only path out of the anode.',
      'The oil is chosen for dielectric strength first and thermal properties second; both matter.',
      'Housing cooling curves define the duty cycle: exceeding them triggers a wait state, not damage.',
    ],
    engineering: [
      'Air-cooled exchangers suffice for radiography; CT and cargo systems use pumped water-to-air or chilled loops.',
      'The expansion bellows is a safety device — if it bottoms out, pressure rises and seals fail.',
      'Flow switches and thermal interlocks are wired into the exposure chain, not just to a display.',
    ],
    practice: [
      'Oil degradation and moisture ingress cause arcing — one of the most common causes of intermittent kV faults.',
      'Never top up with the wrong oil: dielectric strength, not viscosity, is the specification that matters.',
      'A hot housing that will not cool between series usually means a failed fan or blocked radiator, not a failing tube.',
    ],
    numbers: [['Oil roles', 'insulate + cool'], ['Heat path', 'radiation → oil → HX'], ['Interlocks', 'thermal + flow']],
  },

  'xt-hv': {
    oneLiner: 'The generator turns mains power into a steady high voltage across the tube — and how steady it is directly determines how much of your dose becomes useful image.',
    analogy: 'A water pump: a smooth continuous pump gives even flow, a hand pump gives pulses. Same average, very different behaviour.',
    watchFor: 'Two waveforms: the ragged single-phase trace at the top versus the almost flat high-frequency trace below. Same peak, very different area under the useful part.',
    how: [
      'Mains AC is rectified to DC.',
      'An inverter chops that DC at above 40 kHz.',
      'A compact high-frequency transformer steps the voltage up to tens or hundreds of kilovolts.',
      'The output is rectified again and smoothed by capacitance.',
      'The result is near-constant potential — ripple under one percent — applied across the tube.',
    ],
    physics: [
      'During the low-kV part of a ripple cycle, photons produced are too soft to reach the detector: dose without signal.',
      'Higher frequency means the transformer core can be far smaller for the same power — that is why modern generators are compact.',
      'Older twelve-pulse three-phase units ripple 3–4 %; single-phase self-rectified units ripple 100 %.',
    ],
    engineering: [
      'HV cables use graded insulation and a shielded ground braid; connector wells need fresh dielectric grease at every mating.',
      'Closed-loop kV and mA feedback correct within microseconds, making very short reproducible exposures possible.',
      'Cable capacitance stores real energy — HV must be discharged and grounded before any service work.',
    ],
    practice: [
      'Corona in a dirty or dry cable well shows as intermittent kV faults long before outright flashover.',
      'kV accuracy and reproducibility are core acceptance tests — measure, do not trust the display.',
      'HV service is a two-person job with proven discharge: treat every capacitor as charged until grounded.',
    ],
    numbers: [['Inverter frequency', '> 40 kHz'], ['HF ripple', '< 1 %'], ['Single-phase ripple', '100 %']],
  },

  'xt-vacuum': {
    oneLiner: 'Electrons must cross from cathode to anode without hitting anything, so the tube is evacuated to below a ten-millionth of atmospheric pressure and kept that way for its whole life.',
    analogy: 'Firing an arrow across an empty hall versus a crowded one. Any gas molecule in the way ruins the shot — and starts a chain reaction.',
    watchFor: 'The blue electron crosses cleanly. The faint red dots are residual gas molecules — every one is a potential collision and a potential arc.',
    how: [
      'The insert is pumped down and sealed during manufacture, below 10⁻⁷ mbar.',
      'Electrons then travel the gap ballistically, losing no energy on the way.',
      'The hot anode continuously releases trapped gas over the tube\'s life.',
      'A getter material chemically traps that released gas so pressure stays low.',
      'If pressure rises, electrons ionise the gas, positive ions bombard the cathode, and the process runs away into an arc.',
    ],
    physics: [
      'Mean free path at 10⁻⁷ mbar is hundreds of metres — far longer than the few centimetres an electron must cross.',
      'Gas ionisation produces positive ions that accelerate back toward the cathode, damaging the filament.',
      'Arcing is a sudden collapse of the insulating gap — the generator sees a short circuit.',
    ],
    engineering: [
      'Metal-ceramic envelopes tolerate higher power and shield off-focus radiation far better than glass.',
      'Getters are barium or zirconium alloys activated during manufacture.',
      'Every internal component must be vacuum-compatible: no organics, no plated finishes that outgas.',
    ],
    practice: [
      'Gassy tubes are conditioned by slow kV ramping ("seasoning") after long storage — this is a real procedure, not folklore.',
      'Repeated arcing with rising frequency means the vacuum is failing; the insert is replaced, never repaired in the field.',
      'Off-focus radiation from a poor envelope degrades contrast and adds dose outside the intended field.',
    ],
    numbers: [['Vacuum level', '< 10⁻⁷ mbar'], ['Getter material', 'Ba or Zr alloy'], ['Failure mode', 'arcing → insert replacement']],
  },

  'xt-grid': {
    oneLiner: 'Instead of switching hundreds of kilovolts on and off, bias the focusing cup hard negative and the beam is pinched off at source — switching in microseconds with no HV transients.',
    analogy: 'A tap on the hose right at the nozzle instead of at the water main. Far faster, and nothing upstream has to change.',
    watchFor: 'The pulse train at the bottom. When the grid is open, electrons flow and the anode glows; when it is cut off, nothing crosses at all — while the kV stays applied the whole time.',
    how: [
      'The high voltage between cathode and anode stays applied continuously.',
      'A control voltage on the focusing cup (grid) is driven strongly negative.',
      'That field cancels the accelerating field near the filament, so no electron can leave.',
      'Release the bias and the beam restarts within microseconds.',
      'The result is a clean pulse train of X-ray output, gated entirely at low voltage.',
    ],
    physics: [
      'Cut-off requires roughly −2 000 to −4 000 V relative to the filament, depending on cup geometry.',
      'Switching at the grid avoids the ringing, overshoot and cable reflections of switching the HV supply itself.',
      'Dose per second scales directly with duty cycle: pulse width × pulse rate.',
    ],
    engineering: [
      'The grid driver must swing kilovolts in microseconds while floating at cathode potential — a non-trivial circuit.',
      'Duty cycle is limited by anode heating, not by the grid switch.',
      'Cargo and cine systems use the same trick to freeze motion at high frame rates.',
    ],
    practice: [
      'Pulsed fluoroscopy dose scales with pulse rate — dropping from 30 to 15 pulses per second roughly halves patient dose.',
      'A failed grid driver typically leaves the tube permanently on or permanently off — both are immediately obvious.',
      'Grid-controlled tubes cost more and are worth it only where fast, repeatable gating is genuinely needed.',
    ],
    numbers: [['Cut-off bias', '−2 to −4 kV'], ['Switching time', 'microseconds'], ['Dose scaling', '∝ duty cycle']],
  },

  // ─── LINAC ──────────────────────────────────────────────────────────────────
  'ln-gun': {
    oneLiner: 'The gun is the LINAC\'s starting pistol: it injects a modest stream of electrons at a few tens of keV, timed so the RF wave can pick them up.',
    analogy: 'Getting on a moving escalator — you have to step on at a sensible speed and at the right moment, or you never make it up.',
    watchFor: 'Electrons leave the hot cathode continuously, but only the ones entering the first cell at the right moment survive downstream.',
    how: [
      'A heated cathode emits electrons exactly as in an X-ray tube.',
      'A DC field of 10–50 kV accelerates them into the accelerator entrance.',
      'They arrive still non-relativistic, which is what allows the buncher to sort them.',
      'A triode gun adds a grid so the beam current — and hence dose rate — can be controlled quickly.',
      'Timing of the gun pulse relative to the RF pulse sets how many electrons are actually captured.',
    ],
    physics: [
      'Injection energy is kept low deliberately: at 10–50 keV the electrons travel at a fraction of c, so velocity differences can be exploited for bunching.',
      'Gun current sets beam current, which sets dose rate — the machine\'s servo adjusts it continuously.',
      'Space charge at the gun exit limits how much current can be extracted from a given cathode.',
    ],
    engineering: [
      'The gun shares the accelerator vacuum system; its ion pump current is a useful health indicator.',
      'Cathodes are dispenser type for long life at high emission.',
      'Gun HV, filament and grid all float and need isolated supplies.',
    ],
    practice: [
      'A failing gun shows as gradually falling dose rate that the servo compensates for — until it runs out of range and the machine faults.',
      'Gun replacement usually means breaking vacuum, so it is planned work, not a quick fix.',
      'Beam current instability at the gun propagates to dose-rate instability at the patient or object.',
    ],
    numbers: [['Injection energy', '10–50 keV'], ['Pulse width', '1–5 µs'], ['Pulse rate', '100–400 Hz']],
  },

  'ln-buncher': {
    oneLiner: 'A continuous stream of electrons cannot all ride the accelerating phase of an RF wave, so the first cells squeeze them into tight packets that can.',
    analogy: 'Surfers paddling for a wave: only those who match its speed at the right moment get carried. The buncher nudges everyone into the same take-off window.',
    watchFor: 'Electrons start evenly spread along the line and progressively clump into discrete groups as they move right.',
    how: [
      'Electrons enter continuously, spread across all RF phases.',
      'An electron arriving early sees a weaker field and gets a smaller kick.',
      'One arriving late sees a stronger field and gets a bigger kick.',
      'The late ones catch up with the early ones — the stream compresses itself into bunches.',
      'Electrons too far out of phase are simply lost on the copper in the first few centimetres.',
    ],
    physics: [
      'This is velocity modulation converting into density modulation — the same principle a klystron uses.',
      'Capture efficiency is typically 50–70 %; the rest becomes heat and stray radiation at the input end.',
      'Final bunch length is a few degrees of RF phase, which is why the output energy spectrum is narrow.',
    ],
    engineering: [
      'Buncher cells have a shorter period than the main structure because the electrons are still sub-relativistic.',
      'Once electrons reach ~0.98 c the cell length becomes constant — velocity barely changes after that.',
      'Buncher design is where most of the machine\'s beam-loading behaviour is decided.',
    ],
    practice: [
      'Phase errors here appear downstream as an energy spread that the bending magnet then discards — dose rate drops with no obvious cause at the head.',
      'Losses in the buncher region are a known activation and shielding consideration in high-current machines.',
    ],
    numbers: [['Capture efficiency', '50–70 %'], ['Bunch length', 'a few ° of RF'], ['Cell period', 'shorter than main']],
  },

  'ln-cavity': {
    oneLiner: 'Precisely machined copper cells resonate at 2 856 MHz; the electric field in the gaps between them adds energy to each bunch every time it passes.',
    analogy: 'Pushing a child on a swing — small pushes at exactly the right moment, repeated, build up a large amplitude.',
    watchFor: 'Field colour flips between adjacent cells while the bunch travels. It always arrives at a cell when the field is pointing the right way.',
    how: [
      'RF power is fed into the copper structure, exciting a resonant mode.',
      'In a standing-wave design, adjacent cells oscillate in opposite phase.',
      'Side-coupling cavities carry power between accelerating cells without the beam ever passing through them.',
      'The bunch crosses each gap exactly when the field points forward, so every gap adds energy.',
      'After 1–2 metres the electrons carry 6–25 MeV.',
    ],
    physics: [
      'Accelerating gradient is typically 10–15 MeV per metre for medical machines.',
      'Standing-wave structures are roughly half the length of travelling-wave structures for the same energy.',
      'Travelling-wave designs need a matched RF load at the far end to absorb leftover power.',
      'The copper surface itself is the resonator — surface currents, not bulk material, define the frequency.',
    ],
    engineering: [
      'Cells are machined to micrometre tolerance and brazed in a hydrogen furnace; a scratch changes the frequency.',
      'Thermal expansion shifts the resonance, so automatic frequency control chases it continuously.',
      'Cooling water temperature is regulated to a fraction of a degree for exactly this reason.',
    ],
    practice: [
      'AFC loop errors show as energy drift and failed daily output constancy checks.',
      'Vacuum leaks in the structure destroy the surface Q and cause RF breakdown (arcing).',
      'A structure is not field-serviceable — this is factory-exchange hardware.',
    ],
    numbers: [['Frequency (S-band)', '2 856 MHz'], ['Gradient', '10–15 MeV/m'], ['Length', '1–2 m']],
  },

  'ln-magnetron': {
    oneLiner: 'A magnetron generates megawatts of microwave power by making electrons spiral past resonant cavities — the same device as in a microwave oven, scaled up enormously.',
    analogy: 'Blowing across the tops of bottles: the airflow is smooth, but the cavities turn it into a strong tone at their own frequency.',
    watchFor: 'Electrons leave the central cathode and curve into rotating spokes rather than travelling straight out — that rotation is what pumps the cavities.',
    how: [
      'A hot central cathode emits electrons toward a surrounding anode block.',
      'An axial magnetic field bends their paths into curves instead of straight radial lines.',
      'The electrons form rotating "spokes" of space charge.',
      'As each spoke sweeps past a cavity opening it deposits energy, sustaining oscillation.',
      'A coupling loop extracts that power into the waveguide feeding the accelerator.',
    ],
    physics: [
      'The magnetron is an oscillator: it defines its own frequency rather than amplifying an input.',
      'Peak power 2–5 MW pulsed, sufficient for machines up to about 10 MeV.',
      'Frequency drifts with temperature and load, which is why AFC exists in every magnetron machine.',
    ],
    engineering: [
      'Compact and comparatively inexpensive — the reason most 6 MeV machines use one.',
      'A circulator protects it from power reflected by a mismatched accelerating structure.',
      'Cathode life is the usual replacement driver: output falls slowly, then collapses.',
    ],
    practice: [
      'Rising reflected power or increasing AFC correction range are early warnings of magnetron ageing.',
      'Magnetrons are consumables with a known lifetime — plan replacement, do not wait for failure.',
      'Arc detectors in the waveguide inhibit the next pulse within microseconds of a breakdown.',
    ],
    numbers: [['Peak power', '2–5 MW'], ['Energy ceiling', '≈ 10 MeV'], ['Type', 'oscillator']],
  },

  'ln-klystron': {
    oneLiner: 'A klystron amplifies a small, very stable RF signal into tens of megawatts by bunching a DC electron beam and letting those bunches drive an output cavity.',
    analogy: 'A megaphone for radio waves: you supply the precise signal, it supplies the power. The tone comes from you, the loudness from the tube.',
    watchFor: 'The electron stream enters evenly spaced and progressively clumps as it drifts, then gives up its energy at the catcher cavity on the right.',
    how: [
      'A DC electron beam is launched down the tube by a high-voltage modulator pulse.',
      'A low-power RF drive at the buncher cavity speeds some electrons up and slows others down.',
      'Over the drift tube, faster electrons catch slower ones — the beam bunches.',
      'The dense bunches induce a large RF current in the output (catcher) cavity.',
      'That amplified RF is extracted to the accelerator; the spent beam is dumped in a water-cooled collector.',
    ],
    physics: [
      'Velocity modulation converts into density modulation over the drift length — exactly the buncher principle, used for amplification.',
      'Because it amplifies, frequency and phase are set by a stable external driver, not by the tube.',
      'Peak power 5–50 MW makes it the choice above roughly 15 MeV.',
    ],
    engineering: [
      'Needs a modulator producing 100–300 kV pulses and usually a solenoid focusing coil.',
      'Larger, heavier and more costly than a magnetron, but far more stable.',
      'The spent-beam collector dominates the cooling load of the whole RF system.',
    ],
    practice: [
      'Klystron stability is what dose-rate-critical applications actually buy — the extra cost is bought stability, not extra power alone.',
      'Solenoid current is a tuning parameter; a drifting solenoid supply looks like a failing klystron.',
      'Collector cooling failure is an immediate shutdown condition.',
    ],
    numbers: [['Peak power', '5–50 MW'], ['Modulator pulse', '100–300 kV'], ['Type', 'amplifier']],
  },

  'ln-bend': {
    oneLiner: 'The 270° magnet does two jobs: it folds the beam back down toward the target so the head stays compact, and it throws away any electron with the wrong energy.',
    analogy: 'A coin sorter: coins of the wrong size follow a different curve and fall out, only the right ones reach the slot.',
    watchFor: 'The beam enters horizontally and exits downward onto the target. Energy slits sit where off-energy particles would land.',
    how: [
      'Electrons leave the accelerating structure travelling horizontally.',
      'A magnetic field bends them onto a curved path — radius depends on momentum.',
      'A higher-energy electron curves less and drifts outward; a lower-energy one curves more.',
      'Slits at the dispersion point physically absorb anything outside the accepted band.',
      'The achromatic design brings the accepted band back to the same exit point regardless of small energy differences.',
    ],
    physics: [
      'Magnetic rigidity <code>p = 0.2998 · B · ρ</code> (GeV/c, tesla, metre) sets the bend radius for a given energy.',
      'Achromatic means exit position does not depend on energy — the focal spot stays put even as the spectrum breathes.',
      'The energy slits define the beam quality index that dosimetry protocols assume.',
    ],
    engineering: [
      'A 270° geometry keeps the treatment head short enough to rotate on a gantry.',
      'Steering coils trim the beam onto the target centre; a mis-steered beam shows as field asymmetry.',
      'Industrial in-line machines often skip the bend entirely and fire straight through the target.',
    ],
    practice: [
      'Daily beam symmetry checks are effectively a test of steering and bend stability.',
      'A drifting bend current shows as gradual output loss as more beam lands on the slits instead of the target.',
      'The slits are activated components — they are a radiation-protection consideration during service.',
    ],
    numbers: [['Bend angle', '270°'], ['Rigidity', 'p = 0.2998·B·ρ'], ['Function', 'fold + energy filter']],
  },

  'ln-target': {
    oneLiner: 'The electron beam stops in a thin high-Z target and becomes X-rays — but at MeV energies that beam is sharply forward-peaked, so a cone-shaped filter is needed to even it out.',
    analogy: 'A spotlight that is far too bright in the middle: put a shaped piece of glass in front to even out the illumination across the wall.',
    watchFor: 'The dashed profile is the raw forward-peaked beam; the solid one is after the flattening filter. The filter is thickest where the beam is most intense.',
    how: [
      'Electrons strike a tungsten or gold transmission target a few millimetres thick.',
      'They decelerate in the nuclear field and radiate bremsstrahlung photons.',
      'At MeV energies almost all of that radiation goes forward, giving a very peaked profile.',
      'A conical flattening filter — thick on axis, thin at the edges — attenuates the centre more than the edges.',
      'Primary collimators and then the multileaf collimator shape the flattened field to the target outline.',
    ],
    physics: [
      'Forward peaking scales with energy: the higher the electron energy, the narrower the emission cone.',
      'The flattening filter also hardens the beam, which is why flattening-filter-free modes have a measurably softer spectrum.',
      'FFF beams give 2–4× the dose rate and are standard for stereotactic treatments.',
    ],
    engineering: [
      'The target is backed by copper for heat removal and runs red hot during treatment.',
      'Filter shape is machine-specific and is part of the commissioned beam model — it is not interchangeable.',
      'Target and filter alignment is set at commissioning and verified in periodic QA.',
    ],
    practice: [
      'Damage or mis-positioning shows immediately as beam-profile asymmetry in daily QA.',
      'Any change to target or filter invalidates the beam model and requires re-commissioning.',
      'Never interpret an FFF profile with flattened-beam expectations — they are different beams.',
    ],
    numbers: [['Target', 'W or Au, thin'], ['FFF dose rate', '2–4× flattened'], ['Filter shape', 'conical']],
  },

  'ln-mlc': {
    oneLiner: 'Dozens of independently driven tungsten leaves shape the radiation field to the outline of the target, and can move during delivery to vary the intensity across it.',
    analogy: 'A row of sliding book-ends: push each one in by a different amount and you can trace any outline you like.',
    watchFor: 'Each leaf pair opens by a different amount, and together they trace a curved outline no rectangular collimator could produce.',
    how: [
      'Each leaf is an individually motorised tungsten block that slides across the field.',
      'Opposing leaf pairs define the open aperture for that row.',
      'Setting every pair independently traces an arbitrary outline.',
      'In dynamic delivery, leaves sweep while the beam is on, so different parts of the field receive different exposure times.',
      'Combined with gantry rotation and variable dose rate, this produces highly conformal dose distributions.',
    ],
    physics: [
      'Leaf transmission must stay below about 2 % of the open-field dose — that sets the required tungsten thickness.',
      'Rounded leaf ends keep penumbra roughly constant across the travel range.',
      'Tongue-and-groove leaf sides control inter-leaf leakage but introduce their own small underdose effect.',
    ],
    engineering: [
      'Modern heads carry 80–160 leaves with 2.5–5 mm projected width at isocentre.',
      'Each leaf has independent position feedback — usually optical or capacitive.',
      'Leaf speed limits how fast a dynamic plan can be delivered.',
    ],
    practice: [
      'Picket-fence tests verify leaf position accuracy and are part of routine QA.',
      'A single sticking leaf can invalidate a whole treatment plan — the interlock catches it, but it stops the machine.',
      'Leaf calibration drift is gradual: trend the QA data rather than judging each test in isolation.',
    ],
    numbers: [['Leaf count', '80–160'], ['Projected width', '2.5–5 mm'], ['Leakage limit', '≈ 2 %']],
  },

  'ln-chamber': {
    oneLiner: 'Two independent sealed ion chambers sit in the beam and continuously measure dose, dose rate, symmetry and flatness — either one alone can stop the machine.',
    analogy: 'Two independent smoke alarms wired to the same shut-off. Neither trusts the other, and either can act alone.',
    watchFor: 'The accumulating dose bar and the red 110 % line. When the bar crosses it, the beam terminates and the field disappears.',
    how: [
      'The chambers are thin transmission chambers — the beam passes through them on its way out.',
      'Radiation ionises the sealed gas; the collected charge is proportional to dose delivered.',
      'Segmented electrodes let the system compare left/right and front/back signals — that gives symmetry and flatness.',
      'Charge is integrated against the prescribed monitor units.',
      'At 110 % of the set dose, or on any symmetry excursion, the beam is terminated automatically.',
    ],
    physics: [
      'Ion chambers have no internal gain, so they cannot saturate even in an intense pulsed beam — exactly the right choice here.',
      'Sealed and temperature/pressure compensated so calibration does not drift with the weather.',
      'The chamber reading is a relative measure; absolute dose comes from periodic calibration against a reference.',
    ],
    engineering: [
      'The two chambers are read by physically separate electronics chains — a genuine redundancy, not a duplicated display.',
      'Chamber thickness is minimised so it perturbs the beam as little as possible.',
      'Interlock logic is hard-wired, not software-only, for the primary termination path.',
    ],
    practice: [
      'Daily output constancy checks compare chamber response against an external reference — this is the machine\'s daily health test.',
      'Other interlocks in the same chain: door switches, emergency stops, arc detectors, water flow, SF₆ pressure.',
      'Never bypass a chamber fault to finish a treatment or a scan — that interlock is the last line of defence.',
    ],
    numbers: [['Chambers', '2 independent'], ['Termination', '110 % of set MU'], ['Standard', 'IEC 60601-2-1']],
  },

  'ln-modulator': {
    oneLiner: 'The modulator stores energy between pulses and dumps it into the RF source in a few microseconds — that pulse is what makes megawatt-level microwave power possible.',
    analogy: 'Filling a bucket slowly and then tipping it all at once. Average flow is small; the instantaneous flood is enormous.',
    watchFor: 'The charge level rising steadily, then collapsing the instant the thyratron fires. The pulse train at the bottom is what the accelerator actually sees.',
    how: [
      'A power supply charges a pulse-forming network (PFN) between pulses.',
      'A thyratron (or solid-state switch) is triggered and conducts almost instantly.',
      'The PFN discharges through a pulse transformer into the magnetron or klystron.',
      'The result is a flat-topped 1–5 µs pulse of 100–300 kV.',
      'The cycle repeats 100–400 times a second, setting the machine\'s duty cycle.',
    ],
    physics: [
      'Peak power is enormous but average power is modest — that is the whole point of pulsed operation.',
      'Pulse-to-pulse amplitude stability directly determines beam energy stability.',
      'Pulse flatness matters: a drooping top produces an energy spread within the pulse.',
    ],
    engineering: [
      'Thyratrons are consumables; reservoir voltage drift is the classic early warning of end of life.',
      'Solid-state modulators are replacing thyratrons in new installations — fewer consumables, faster fault detection.',
      'Arc detectors watch the waveguide and inhibit the next pulse within microseconds of a breakdown.',
    ],
    practice: [
      'Dose rate is set by pulse rate; changing it changes nothing about beam energy.',
      'Modulator faults are usually the first thing to check when the machine loses output without an obvious RF fault.',
      'Stored energy in the PFN is lethal — proven discharge before any panel comes off.',
    ],
    numbers: [['Pulse width', '1–5 µs'], ['Pulse rate', '100–400 Hz'], ['Pulse voltage', '100–300 kV']],
  },

  // ─── BETATRON ───────────────────────────────────────────────────────────────
  'bt-core': {
    oneLiner: 'A betatron has no electrodes at all — the accelerating force is the electric field induced by a magnetic flux that keeps growing.',
    analogy: 'A transformer where the secondary winding is a single loop of electrons instead of a coil of wire.',
    watchFor: 'The blue field rings expanding and contracting with the mains cycle. Only the rising part of the cycle can accelerate anything.',
    how: [
      'A large laminated iron core is driven at mains frequency.',
      'The magnetic flux through the electron orbit rises during a quarter of each cycle.',
      'A changing flux induces a circular electric field around the orbit.',
      'Electrons circulating in that field are accelerated continuously, turn after turn.',
      'When the flux stops rising, acceleration stops. The rest of the cycle is dead time.',
    ],
    physics: [
      'Faraday\'s law: <code>∮E·dl = −dΦ/dt</code>. The induced EMF is the accelerating voltage.',
      'Because acceleration is distributed around the whole orbit, no single point sees a high voltage.',
      'Core saturation sets the practical energy ceiling for a given geometry.',
    ],
    engineering: [
      'Laminations suppress eddy currents that would otherwise waste drive power as heat.',
      'The drive current is often resonated with a capacitor bank to reduce the supply rating.',
      'The magnet is the heaviest and costliest part of the machine, and energy scales poorly with its size.',
    ],
    practice: [
      'Only about a quarter of each mains cycle is useful, which caps the achievable dose rate.',
      'The absence of an RF system is the betatron\'s main maintenance advantage over a LINAC.',
    ],
    numbers: [['Drive frequency', '50/60 Hz'], ['Useful fraction', '≈ ¼ cycle'], ['Law', '∮E·dl = −dΦ/dt']],
  },

  'bt-donut': {
    oneLiner: 'The vacuum chamber has to be an electrical insulator, because a metal one would carry an induced current that cancels the very field doing the accelerating.',
    analogy: 'A shorted turn on a transformer: put a closed metal loop in a changing field and it fights the field instead of letting it work.',
    watchFor: 'The electron circulating inside the toroidal chamber. The chamber wall is a barrier to gas, not to the electric field.',
    how: [
      'A doughnut-shaped chamber of glass or ceramic holds the circulating beam.',
      'It is evacuated below 10⁻⁶ mbar so gas scattering does not destroy the beam.',
      'Because the wall is insulating, the induced electric field passes through it unimpeded.',
      'A thin conductive coating inside drains static charge without forming a closed conducting loop.',
      'The chamber walls also define the physical aperture the beam must stay inside.',
    ],
    physics: [
      'A conducting torus would act as a shorted secondary turn, cancelling the accelerating EMF.',
      'The beam travels hundreds of kilometres of path length over a few milliseconds, so even trace gas matters.',
      'Wall aperture sets the tolerance for betatron oscillations before the beam is scraped away.',
    ],
    engineering: [
      'Glass or ceramic construction makes the chamber fragile and expensive to replace.',
      'The internal coating must be resistive enough not to short, conductive enough to drain charge.',
      'Chamber cracks are catastrophic and usually terminal for the machine.',
    ],
    practice: [
      'Vacuum quality directly sets how much of the injected beam survives to full energy.',
      'Handling a spare chamber is a specialist job — thermal and mechanical shock both kill it.',
    ],
    numbers: [['Vacuum', '< 10⁻⁶ mbar'], ['Wall', 'insulating glass/ceramic'], ['Path length', 'hundreds of km']],
  },

  'bt-condition': {
    oneLiner: 'For the orbit radius to stay constant while the energy rises, the average magnetic field inside the orbit must be exactly twice the field at the orbit itself.',
    analogy: 'A car going faster around a fixed bend needs proportionally more grip. Here "grip" is magnetic field, and the 2:1 rule is the exact recipe.',
    watchFor: 'When the ratio is right the orbit stays locked on the dashed circle. When it is wrong, watch the orbit drift outward toward the wall.',
    how: [
      'Momentum grows as the electron is accelerated each turn.',
      'A higher momentum needs a stronger field to keep the same radius.',
      'The flux inside the orbit (which does the accelerating) and the field at the orbit (which does the bending) come from the same magnet.',
      'Shaping the pole faces and adding a central flux bar makes the average interior field grow at exactly twice the rate of the orbit field.',
      'Get that ratio wrong and the radius drifts, and the beam hits the chamber wall within a few hundred turns.',
    ],
    physics: [
      'The betatron condition: <code>B̄(inside orbit) = 2 · B(r₀)</code> — Kerst and Serber, 1941.',
      'Field index <code>n = −(r/B)(∂B/∂r)</code> must lie between 0 and 1 for weak focusing in both planes.',
      'Outside that range, either radial or vertical oscillations grow instead of damping.',
    ],
    engineering: [
      'The ratio is enforced by iron geometry, not by a control loop — it is designed in, not tuned.',
      'A central flux bar supplies the extra interior flux the ratio demands.',
      'The same stability analysis underpins every later circular accelerator.',
    ],
    practice: [
      'This condition is why a betatron cannot simply be "turned up" beyond its design energy.',
      'Pole-face shims are the physical adjustment mechanism, and adjusting them is specialist work.',
    ],
    numbers: [['Condition', 'B̄ = 2·B(r₀)'], ['Field index', '0 < n < 1'], ['Published', 'Kerst & Serber 1941']],
  },

  'bt-injector': {
    oneLiner: 'Electrons are injected in a burst at the very start of the cycle, and the orbit is immediately pulled inward so the beam does not keep hitting the injector structure.',
    analogy: 'Boarding a roundabout, then stepping inward away from the gate so you do not collide with it every lap.',
    watchFor: 'A brief injection at the start, then the orbit contracting inward away from the gun before acceleration proceeds.',
    how: [
      'A pulsed electron gun fires into the chamber for a few microseconds at the start of the rising flux.',
      'The injected electrons begin circulating immediately.',
      'A contraction pulse shifts the orbit inward, clearing the injector structure.',
      'Acceleration then proceeds for hundreds of thousands of turns.',
      'At peak energy an expansion pulse drives the beam outward onto the target.',
    ],
    physics: [
      'Capture efficiency is low — most injected electrons are lost within the first few turns.',
      'The injector sits inside the aperture, so orbit contraction is not optional.',
      'Injection timing relative to the flux ramp is one of the two main tuning parameters on an operating betatron.',
    ],
    engineering: [
      'Injection and extraction pulses are supplied by auxiliary windings, not the main magnet.',
      'Gun structure geometry is a compromise between emission and aperture obstruction.',
    ],
    practice: [
      'Output tuning on a betatron largely means adjusting injection and extraction timing.',
      'Poor injection timing shows as low output with otherwise normal magnet behaviour.',
    ],
    numbers: [['Injection window', 'a few µs'], ['Turns per pulse', '10⁵–10⁶'], ['Tuning knobs', 'inject / extract timing']],
  },

  'bt-target': {
    oneLiner: 'At peak energy the orbit is deliberately expanded until the beam strikes an internal tungsten target, converting the electrons into a very hard X-ray burst.',
    analogy: 'Widening a spiral until it hits the wall — except the "wall" is placed exactly where you want the X-rays made.',
    watchFor: 'The orbit expanding outward each cycle until it reaches the target, followed by a burst of photon rays.',
    how: [
      'Acceleration continues until the flux ramp reaches its useful end.',
      'An expansion winding pushes the orbit outward.',
      'The beam strikes a tungsten target mounted at the chamber edge.',
      'Electrons decelerate in the target and produce bremsstrahlung with an endpoint equal to their full energy.',
      'The whole burst lasts microseconds and repeats once per mains cycle.',
    ],
    physics: [
      'Photon endpoint equals the final electron energy — 15 MeV to a few hundred MeV.',
      'Very hard spectra penetrate 100–300 mm of steel, the reason betatrons survived in heavy NDT.',
      'Average dose rate is modest because only one short burst occurs per mains cycle.',
    ],
    engineering: [
      'Beam dump and X-ray production happen at the same place — there is no external beam line.',
      'Target cooling is simple: average power is low even though peak energy is high.',
      'Target position is fixed by the extraction radius, not adjustable in operation.',
    ],
    practice: [
      'Low dose rate means long exposures — betatron radiography is slow compared with a LINAC.',
      'Exposure calculations use burst count rather than continuous time.',
    ],
    numbers: [['Photon endpoint', '15–300 MeV'], ['Steel penetration', '100–300 mm'], ['Burst rate', '≈ mains frequency']],
  },
};
