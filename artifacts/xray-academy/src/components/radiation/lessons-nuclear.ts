import type { Lesson } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Mini-lessons — radioisotope sources, neutron sources, gamma irradiators,
// industrial radiography and security screening components.
// ═══════════════════════════════════════════════════════════════════════════════

export const NUCLEAR_LESSONS: Record<string, Lesson> = {

  // ─── RADIOISOTOPE SOURCES ───────────────────────────────────────────────────
  'is-capsule': {
    oneLiner: 'A sealed source is radioactive material locked inside two independently welded metal capsules, so that no single failure can release it.',
    analogy: 'A vacuum flask inside a second vacuum flask. If the inner one cracks, the outer one still holds everything in.',
    watchFor: 'The two nested capsule walls around the glowing active pellets — two barriers, not one.',
    how: [
      'Active material is sintered into solid pellets, discs or wire — never a powder or liquid.',
      'It is sealed inside an inner capsule, which is welded shut.',
      'That whole capsule is placed inside a second one, which is also welded shut.',
      'Every weld is helium leak-tested at manufacture.',
      'The finished source carries a classification code recording the abuse tests it survived.',
    ],
    physics: [
      'Containment does not stop the gamma radiation — that passes straight through the steel and is the point of the source.',
      'What containment stops is <b>contamination</b>: loose radioactive material escaping and being inhaled or spread.',
      'Alpha and beta emitters are far more dangerous if released, which is why encapsulation is absolute.',
    ],
    engineering: [
      'Capsule material is usually 316L stainless steel, or Inconel for high-temperature service.',
      'ISO 2919 classification code (e.g. C 66646) records temperature, pressure, impact, vibration and puncture ratings.',
      'Capsule dimensions are standardised so sources fit existing projectors and shields.',
    ],
    practice: [
      'Wipe test every 6–12 months; more than 200 Bq of removable activity condemns the source.',
      'A source is never opened, cut or ground in the field — a breach is a contamination event, not a repair job.',
      'Damaged or suspect sources are handled only under the licensee emergency procedure.',
    ],
    numbers: [['Barriers', '2 welded capsules'], ['Leak limit', '200 Bq removable'], ['Standard', 'ISO 2919'], ['Material', '316L / Inconel']],
  },

  'is-pigtail': {
    oneLiner: 'The source capsule is swaged onto a short flexible cable — the pigtail — and the drive cable must latch onto it positively, because that latch is what brings the source home.',
    analogy: 'A tow hitch. Getting the car moving is easy; the coupling only matters when you need to pull it back.',
    watchFor: 'The connector either latching green or sitting open in red. A partial connection looks almost identical to a good one.',
    how: [
      'The source is permanently attached to a short flexible cable assembly (the pigtail).',
      'The drive cable from the crank carries a female connector.',
      'Connecting them locks the two together mechanically.',
      'Cranking out pushes the assembly through the guide tube to the exposure position.',
      'Cranking back pulls it into the shield — but only if the connection held.',
    ],
    physics: [
      'Nothing about the radiation changes when the source is exposed — only its distance from the shield.',
      'An exposed source in a guide tube can give lethal dose rates within a metre.',
      'There is no way to "switch it off": the only controls are shielding, distance and time.',
    ],
    engineering: [
      'The connector must latch positively; wear at the coupling is inspected before every job and logged.',
      'Cable and connector are consumables with defined replacement intervals.',
      'Drive cable stiffness limits how tight a bend the guide tube can have.',
    ],
    practice: [
      'A partial connection is the classic accident precursor: the source goes out but does not come back.',
      'If the pigtail disconnects while exposed, the source stays in the guide tube — that is an emergency, not a fault.',
      'Recovery requires the licensee emergency procedure and long-handled tools, never bare hands.',
    ],
    numbers: [['Critical action', 'positive latch'], ['Inspection', 'before every job'], ['Failure', 'source stays out']],
  },

  'is-projector': {
    oneLiner: 'The projector holds the source at the centre of a heavy shield, in an S-shaped channel so there is no straight line from the source to the outside world.',
    analogy: 'A letterbox with a bent chute — light cannot shine straight through, and neither can radiation.',
    watchFor: 'The source travelling around the S-bend. At no point is there a straight path from the source to the outer surface.',
    how: [
      'The source rests at the centre of the shield when stored.',
      'The channel that holds it curves in an S shape.',
      'Radiation heading outward must strike shield material at least once.',
      'Scattered photons lose energy at each bounce and are then easily absorbed.',
      'Cranking out drives the source through that channel and along the guide tube.',
    ],
    physics: [
      'Attenuation follows <code>I = I₀ e^(−µx)</code>, so the effective thickness in every direction is what matters.',
      'Compton scattering reduces photon energy at each interaction, making subsequent absorption easier.',
      'Depleted uranium gives the highest attenuation per kilogram — critical for a device carried up scaffolding.',
    ],
    engineering: [
      'Shield material is depleted uranium or tungsten alloy, encased in a rugged housing.',
      'A lock and a source-position indicator are mandatory before transport.',
      'Surface dose rate limits and transport index are defined by IAEA SSR-6.',
    ],
    practice: [
      'Devices are leak-tested and inspected on a fixed schedule regardless of how much they are used.',
      'Damage to the housing can shift the shield internally — any impact means the device is out of service pending inspection.',
      'The projector is also a security item: it is a Category 2 source in a portable box.',
    ],
    numbers: [['Shield', 'depleted U or W'], ['Geometry', 'S-channel'], ['Standard', 'IAEA SSR-6']],
  },

  'is-guide': {
    oneLiner: 'A flexible guide tube carries the source to the weld, and a tungsten collimator at the end restricts the emission to the useful cone — shrinking the controlled area dramatically.',
    analogy: 'Swapping a bare light bulb for a spotlight: same lamp, but now you only light what you are looking at.',
    watchFor: 'With the collimator fitted, the emission is a narrow cone instead of a full sphere. That difference is what sets the barrier distance.',
    how: [
      'The guide tube is connected between the projector and the exposure position.',
      'The source is cranked through it to the weld being inspected.',
      'Without a collimator, radiation goes out in all directions equally.',
      'A tungsten collimator absorbs everything except the cone aimed at the film.',
      'The barrier distance is then set by measurement, not by assumption.',
    ],
    physics: [
      'Inverse square law: doubling the distance quarters the dose rate — distance is the cheapest control available.',
      'A directional collimator can cut the boundary distance by a factor of five or more.',
      'Scattered radiation from surrounding steel still needs surveying — the collimator does not eliminate it.',
    ],
    engineering: [
      'Minimum guide tube length (typically 7 m) keeps the operator away from the exposed source.',
      'The end fitting must be secured to the object — a whipping guide tube is a genuine hazard.',
      'Guide tubes have a minimum bend radius; exceeding it can jam the source.',
    ],
    practice: [
      'Barriers and warning signs are placed using measured dose rates, never assumed ones.',
      'Every exposure ends with a survey of the projector <b>and</b> the full guide tube run.',
      'A jammed source in a kinked guide tube is one of the most common radiography emergencies.',
    ],
    numbers: [['Guide tube', '≥ 7 m typical'], ['Collimator gain', '≈ 5× smaller area'], ['Law', 'İ ∝ 1/d²']],
  },

  'is-survey': {
    oneLiner: 'The survey meter is the only proof that the source actually came back into the shield — the crank handle position is not proof of anything.',
    analogy: 'Checking the gas is really off at the meter, not just assuming because you turned the knob.',
    watchFor: 'The needle and the alarm responding as the reading crosses the threshold. Note that the reading, not the crank, tells the truth.',
    how: [
      'Before the job: check battery, response to a check source, and the calibration date.',
      'During the job: the meter defines where the barriers go.',
      'After every exposure: survey the projector, the guide tube and the work area.',
      'The alarming personal dosimeter provides an independent second warning.',
      'A passive TLD or OSL badge records the legal dose after the fact.',
    ],
    physics: [
      'Geiger tubes saturate in very intense fields and can read <b>low</b> — the most dangerous possible failure mode.',
      'Ion chambers have no internal gain and stay linear at high dose rates, which is why they are the right instrument here.',
      'Dose rate falls with the square of distance, so meter readings change fast as you approach.',
    ],
    engineering: [
      'Calibration is traceable and time-limited; an out-of-calibration meter is not a meter.',
      'Alarming dosimeters have both dose and dose-rate thresholds.',
      'Energy response varies with photon energy — the meter must be appropriate for the isotope in use.',
    ],
    practice: [
      'The single most repeated lesson from radiography accidents: the survey was not done, or was done with a dead meter.',
      'The alarming dosimeter is personal and worn — not left in a toolbox with the paperwork.',
      'If the meter reading disagrees with expectation, believe the meter and withdraw.',
    ],
    numbers: [['Pre-job checks', 'battery, source, calibration'], ['GM risk', 'reads low when saturated'], ['Survey', 'after every exposure']],
  },

  'is-transport': {
    oneLiner: 'High-activity sources travel in Type B packages certified to survive fire, impact, puncture and immersion, labelled with an index derived from the dose rate one metre away.',
    analogy: 'A black box flight recorder: the container is designed around the worst accident you can credibly imagine, not around normal handling.',
    watchFor: 'The package label and the transport index. The index is a measured number, not a category chosen by the shipper.',
    how: [
      'The source is placed in its shielded container inside a certified overpack.',
      'Dose rate is measured at the surface and at one metre.',
      'The transport index is calculated from the one-metre reading.',
      'Category labels (White-I, Yellow-II, Yellow-III) follow from the surface and one-metre rates.',
      'Documentation, marking and vehicle placarding follow IAEA SSR-6 as adopted into ADR, IMDG or IATA.',
    ],
    physics: [
      'Transport index = dose rate in µSv/h at 1 m divided by 10, rounded up to one decimal place.',
      'The index exists so that packages can be separated by distance during transport and storage.',
      'Type B certification means the package survives a defined accident sequence — fire, drop, puncture, immersion — intact.',
    ],
    engineering: [
      'Type B(U) approval is a design certification issued by a competent authority, not a manufacturer claim.',
      'Package integrity depends on the closure being correctly fitted — torque and seals are specified.',
      'Security requirements (IAEA NSS 14) apply in parallel to safety requirements — they are not the same rules.',
    ],
    practice: [
      'Shipping paperwork errors are the most common regulatory finding in source transport.',
      'Vehicle placarding and driver training are legal requirements, not company policy.',
      'A damaged package on arrival is an incident to be reported, not unpacked.',
    ],
    numbers: [['Transport index', 'İ(1 m)/10'], ['Categories', 'White-I → Yellow-III'], ['Standard', 'IAEA SSR-6']],
  },

  'is-decay': {
    oneLiner: 'Activity falls exponentially and nothing can stop it, so the exposure time for the same film density has to be recalculated as the source ages — daily for iridium-192.',
    analogy: 'A battery that self-discharges on a fixed schedule you cannot change. You can plan around it, but you cannot recharge it.',
    watchFor: 'The curve falling and the percentage dropping. Note the shape: each half-life removes half of what is left, not a fixed amount.',
    how: [
      'Each nucleus decays at random, but a large population follows a clean exponential law.',
      'After one half-life, half the original activity remains.',
      'After two half-lives, a quarter. After three, an eighth.',
      'The dose rate at a given distance scales directly with activity.',
      'So exposure time must be increased to keep the same film density.',
    ],
    physics: [
      '<code>A(t) = A₀ · e^(−λt)</code> with <code>λ = ln2 / t½</code>.',
      'Ir-192 (73.8 d half-life) loses about 1 % of its activity per day.',
      'Co-60 (5.27 y) loses about 12.3 % per year — a reload planning matter, not daily arithmetic.',
      'Nothing an operator can do — heating, cooling, chemistry, pressure — changes the decay constant.',
    ],
    engineering: [
      'Decay charts or software give the current activity from the reference date.',
      'Source replacement is scheduled on activity, not on calendar age alone.',
      'Projector rating is specified in maximum activity, so a fresh source may exceed the device limit.',
    ],
    practice: [
      'Guessing the activity produces under-exposed radiographs and wasted site time.',
      'The decayed source remains a licensed radioactive item until formally disposed of — it never becomes scrap.',
      'Disposal or return to supplier must be arranged well before the source becomes useless.',
    ],
    numbers: [['Law', 'A = A₀e^(−λt)'], ['Ir-192', '≈ 1 % per day'], ['Co-60', '≈ 12.3 % per year']],
  },

  // ─── NEUTRON SOURCES ────────────────────────────────────────────────────────
  'nt-dt-tube': {
    oneLiner: 'A sealed tube accelerates deuterium ions into a tritium-loaded target; the fusion reaction makes 14 MeV neutrons — and stops the instant you cut the high voltage.',
    analogy: 'A neutron light switch. Unlike an isotope source, this one genuinely turns off.',
    watchFor: 'Ions crossing the acceleration gap and striking the target, with neutrons only appearing at the moment of impact.',
    how: [
      'A small ion source ionises deuterium gas inside the sealed tube.',
      'A gap of about 100 kV accelerates the deuterium ions toward the target.',
      'The target is a metal hydride loaded with tritium.',
      'Deuterium and tritium nuclei fuse: <code>d + t → ⁴He + n</code>.',
      'The neutron carries 14.1 MeV and leaves in essentially any direction.',
    ],
    physics: [
      'The reaction releases 17.6 MeV total, split as 3.5 MeV to the helium and 14.1 MeV to the neutron.',
      'The neutron energy is monoenergetic, unlike the broad spectrum from Am-Be or Cf-252.',
      'Yield is set by beam current and target loading, both of which decline slowly over tube life.',
    ],
    engineering: [
      'The tube is a sealed consumable — typical life is a few thousand hours of beam-on time.',
      'Tritium inventory is small but is still a regulated radioactive material.',
      'Pulsed operation enables time-gated measurements that separate prompt from delayed gammas.',
    ],
    practice: [
      'Switchability is a major regulatory advantage: no source to secure when the system is off.',
      'Declining yield is gradual and predictable — tube replacement is planned, not emergency work.',
      'Neutron shielding is still required during operation; the tube is off, not harmless.',
    ],
    numbers: [['Neutron energy', '14.1 MeV'], ['Accel voltage', '≈ 100 kV'], ['Yield', '10⁸–10¹¹ n/s']],
  },

  'nt-ambe': {
    oneLiner: 'Alpha particles from americium-241 strike beryllium, knocking out neutrons — a permanently-on neutron source in a sealed capsule.',
    analogy: 'A struck match that never goes out. With a 432-year half-life, this source outlives everyone who handles it.',
    watchFor: 'The alpha travelling only a short distance before hitting a beryllium nucleus and releasing a neutron.',
    how: [
      'Am-241 emits alpha particles at 5.49 MeV.',
      'The alpha travels only microns, so the americium is intimately mixed with beryllium powder.',
      'An alpha striking a beryllium-9 nucleus produces carbon-12 plus a free neutron.',
      'The neutron emerges with anything from 0.1 to about 11 MeV.',
      'The whole mixture is sealed in a double capsule like any other sealed source.',
    ],
    physics: [
      'Reaction: <code>⁹Be(α,n)¹²C</code>. Yield is roughly 10⁵–10⁶ neutrons per second per GBq of Am-241.',
      'The spectrum is continuous, averaging about 4.5 MeV — quite different from a generator\'s single line.',
      'Am-241 also emits a strong 59.5 keV gamma line, so shielding must handle both radiation types.',
    ],
    engineering: [
      'The 432-year half-life means the source is effectively constant over any working lifetime.',
      'Widely used for detector calibration and well logging where a generator is impractical.',
      'Capsule integrity is critical: americium is an alpha emitter and highly hazardous if inhaled.',
    ],
    practice: [
      'It cannot be switched off — storage shielding is the only control when not in use.',
      'Combined neutron plus gamma field means two different dosimetry techniques are needed.',
      'Disposal is expensive and must be planned from the moment of purchase.',
    ],
    numbers: [['Reaction', '⁹Be(α,n)¹²C'], ['Mean energy', '≈ 4.5 MeV'], ['Am-241 half-life', '432 y']],
  },

  'nt-cf252': {
    oneLiner: 'Californium-252 fissions all by itself, throwing out about four neutrons per event — the most compact intense neutron source available.',
    analogy: 'A firework that keeps going off by itself, scattering sparks in every direction, from a speck of material.',
    watchFor: 'The nucleus splitting into two fragments with several neutrons flying off at once.',
    how: [
      'Cf-252 nuclei undergo spontaneous fission without any external trigger.',
      'Each fission splits the nucleus into two lighter fragments.',
      'On average about four neutrons are released per fission.',
      'The neutron spectrum resembles a reactor fission spectrum, averaging about 2.3 MeV.',
      'Prompt gamma rays accompany every fission.',
    ],
    physics: [
      'About 2.3 × 10⁶ neutrons per second per microgram — a milligram is an intense source.',
      'Half-life is 2.65 years, so the source needs replacing on a short cycle.',
      'Both neutrons and prompt gammas must be shielded — this is not a pure neutron emitter.',
    ],
    engineering: [
      'Extremely high output from a physically tiny source makes it valuable where space is limited.',
      'Used for reactor start-up, neutron activation analysis, BNCT research and downhole well logging.',
      'Criticality control is required in transport for larger quantities.',
    ],
    practice: [
      'The short half-life means routine replacement and continuous recalculation of yield.',
      'It cannot be switched off; when not in use it lives in a shielded store.',
      'A very high dose rate in a small package makes handling procedures unforgiving.',
    ],
    numbers: [['Yield', '2.3×10⁶ n/s per µg'], ['Mean energy', '≈ 2.3 MeV'], ['Half-life', '2.65 y']],
  },

  'nt-detector': {
    oneLiner: 'Neutrons carry no charge, so they cannot ionise directly — detection works by capturing them in a nucleus that then releases charged particles you can actually measure.',
    analogy: 'You cannot see the wind, so you watch what it moves. Here you watch the charged fragments the neutron capture releases.',
    watchFor: 'The neutron entering and vanishing at the moment of capture, replaced by a burst of ionisation and a clean pulse.',
    how: [
      'A neutron enters the tube filled with helium-3 or lined with boron-10.',
      'It is captured by a nucleus in the fill gas or the wall coating.',
      'The capture reaction releases energetic charged particles.',
      'Those particles ionise the gas along their tracks.',
      'Gas multiplication turns that ionisation into a countable pulse.',
    ],
    physics: [
      '<code>³He(n,p)³H</code> releases 764 keV; <code>¹⁰B(n,α)⁷Li</code> releases 2.31 MeV.',
      'Both energies are far above what a gamma-ray background produces, so pulse-height discrimination rejects gammas cleanly.',
      'The capture cross-section is huge for thermal neutrons and small for fast ones — so a moderator is part of the detector, not an accessory.',
    ],
    engineering: [
      'The 2009 helium-3 shortage pushed portal monitors toward boron-lined tubes and lithium-6 scintillators.',
      'Tube pressure and diameter set the detection efficiency.',
      'ANSI N42.43 defines the performance a portal monitor must demonstrate.',
    ],
    practice: [
      'Gamma rejection matters enormously at a border crossing where the gamma background is variable.',
      'A detector without its moderator jacket is effectively blind to fast neutrons.',
      'Detector response must be verified with a traceable source, not assumed from the datasheet.',
    ],
    numbers: [['³He reaction', '764 keV'], ['¹⁰B reaction', '2.31 MeV'], ['Standard', 'ANSI N42.43']],
  },

  'nt-shield': {
    oneLiner: 'Neutron shielding is a sequence, not a material: slow them down with hydrogen, capture them with boron, then absorb the capture gammas with lead. Doing it in any other order barely works.',
    analogy: 'Stopping a bouncing ball: first slow it with something soft, then catch it, then deal with the noise it made. A brick wall alone just bounces it back.',
    watchFor: 'The neutron shrinking as it crosses the polyethylene, being captured in the boron layer, and a gamma ray appearing that the lead must then stop.',
    how: [
      'Fast neutrons enter the hydrogen-rich layer (polyethylene, water or paraffin).',
      'Elastic collisions with hydrogen nuclei rapidly remove energy.',
      'Once thermalised, the neutron is captured in a boron or cadmium layer.',
      'That capture releases a gamma ray.',
      'A final lead layer attenuates those capture gammas before they leave the shield.',
    ],
    physics: [
      'Hydrogen has almost the same mass as a neutron, so a single head-on collision can take nearly all its energy.',
      'Capture in ordinary hydrogen emits a 2.2 MeV gamma — which is why the lead layer is needed at all.',
      'Boron-loaded material suppresses that gamma by absorbing in ¹⁰B, which emits a much softer 478 keV line.',
    ],
    engineering: [
      '10–20 cm of borated polyethylene handles most industrial fast-neutron fields.',
      'Concrete works because of its water content — dried-out concrete is a measurably worse neutron shield.',
      'Lead placed first would be almost useless: fast neutrons scatter weakly from heavy nuclei.',
    ],
    practice: [
      'Getting the layer order wrong is a common and expensive design mistake.',
      'Shield performance must be verified by measurement — neutron calculations carry large uncertainties.',
      'Neutron quality factor reaches 20, so the same absorbed dose carries far more biological weight.',
    ],
    numbers: [['Order', 'moderate → absorb → attenuate'], ['Borated PE', '10–20 cm'], ['H capture gamma', '2.2 MeV']],
  },

  'nt-remmeter': {
    oneLiner: 'A thermal neutron detector buried inside a polyethylene sphere responds in a way that roughly matches the neutron dose-equivalent curve across many decades of energy.',
    analogy: 'A microphone with a filter that makes it hear the way a human ear does — not flat, but weighted to what actually matters.',
    watchFor: 'Fast neutrons entering the sphere and slowing down as they approach the small central detector.',
    how: [
      'A small thermal-neutron detector sits at the centre of a polyethylene sphere.',
      'Fast neutrons entering the sphere are moderated by the hydrogen.',
      'How well they are moderated depends on both their energy and the sphere size.',
      'Only neutrons thermalised near the centre are detected.',
      'The sphere diameter is chosen so the overall response mimics the dose-equivalent curve.',
    ],
    physics: [
      'Sphere diameter tunes which energies are moderated efficiently — that is how the response shape is engineered.',
      'A Bonner sphere set (several diameters) can unfold an approximate neutron energy spectrum.',
      'Neutron quality factors reach 20, so field measurement matters far more than it does for photons.',
    ],
    engineering: [
      'Rem-meters are heavy and slow, but they remain the reference instrument for workplace neutron surveys.',
      'Response is direction-dependent, so orientation during measurement matters.',
      'Calibration is done against traceable neutron sources at defined energies.',
    ],
    practice: [
      'Personal neutron dosimetry usually uses CR-39 track etch or albedo TLDs rather than a rem-meter.',
      'Mixed neutron-gamma fields need both instruments — one meter cannot report both correctly.',
      'A rem-meter reading in a strongly thermal field can be misleading if the spectrum is unusual.',
    ],
    numbers: [['Principle', 'moderating sphere'], ['Spectrum tool', 'Bonner sphere set'], ['Quality factor', 'up to 20']],
  },

  // ─── GAMMA IRRADIATOR ───────────────────────────────────────────────────────
  'ir-rack': {
    oneLiner: 'Cobalt-60 slugs are sealed into double-encapsulated pencils and arranged in a planar rack, so product moving past sees a broad, reasonably even radiation field.',
    analogy: 'A wall of heat lamps rather than a single bulb — a wide even field is what gives uniform cooking.',
    watchFor: 'The regular grid of source pencils. Their arrangement, not just their total activity, determines the dose pattern.',
    how: [
      'Cobalt-59 is irradiated in a reactor to become cobalt-60.',
      'The active metal is sealed into slugs, then into double-walled pencils.',
      'Pencils are loaded into modules, and modules into a planar rack.',
      'Loading is planned so activity is highest where product dwell time is shortest.',
      'The rack is raised into the cell to irradiate and lowered into the pool to store.',
    ],
    physics: [
      'Co-60 emits two gammas per decay at 1.17 and 1.33 MeV — an average of 1.25 MeV.',
      'These energies penetrate deeply, which is exactly what bulk product irradiation needs.',
      'Activity decays 12.3 % per year, so processing times must be adjusted continuously.',
    ],
    engineering: [
      'Racks are reloaded periodically to restore capacity as the cobalt decays.',
      'Source movement and loading are done underwater with long-handled tools.',
      'Each pencil is tracked by serial number for the whole facility lifetime.',
    ],
    practice: [
      'Rack geometry is a commissioning input to the dose-mapping model — changing it invalidates the map.',
      'Source inventory records are a regulatory and security requirement, not just housekeeping.',
      'Spent pencils are returned to the supplier, never disposed of locally.',
    ],
    numbers: [['Photon energies', '1.17 + 1.33 MeV'], ['Average', '1.25 MeV'], ['Decay', '12.3 % / year']],
  },

  'ir-pool': {
    oneLiner: 'Five to six metres of demineralised water shields the sources completely while staying clear enough to inspect them visually from the pool edge.',
    analogy: 'A swimming pool that is also a lead wall. You can stand at the edge and look straight down at something that would be lethal in air.',
    watchFor: 'The blue Čerenkov glow around the submerged source — visible proof that the source is where it should be.',
    how: [
      'The source rack is lowered into a deep concrete-lined pool when not irradiating.',
      'Water attenuates the gammas over the depth of the pool.',
      'At the surface the dose rate is at background level.',
      'The water also removes decay heat from the sources.',
      'Because water is transparent, the racks remain visible for inspection.',
    ],
    physics: [
      'Water\'s half-value layer for 1.25 MeV gammas is about 11 cm — five metres is many HVLs.',
      'The Čerenkov glow comes from beta particles travelling faster than light in water.',
      'Deionisation keeps conductivity low, which limits corrosion of the stainless capsules.',
    ],
    engineering: [
      'Pool water is monitored for activity — any rise is a leaking-source indicator.',
      'Level and temperature alarms are part of the safety system, not just plant monitoring.',
      'Ion exchange resin used for purification becomes radioactive waste and is managed as such.',
    ],
    practice: [
      'Water purity is monitored continuously; rising conductivity signals corrosion risk to the capsules.',
      'A dropping pool level is an immediate emergency — the shielding is the water.',
      'Visual inspection from the pool edge is a routine, and completely safe, operation.',
    ],
    numbers: [['Pool depth', '5–6 m'], ['Water HVL', '≈ 11 cm @1.25 MeV'], ['Glow', 'Čerenkov']],
  },

  'ir-conveyor': {
    oneLiner: 'Absorbed dose is simply the time the product spends near the source, so conveyor speed and pass pattern are the actual process controls.',
    analogy: 'Sunbathing. How brown you get depends on how long you lie there and how close you are — not on any switch.',
    watchFor: 'The dose bar filling as each tote passes the rack, and filling faster when the tote is closest.',
    how: [
      'Totes or pallets are loaded onto the conveyor outside the cell.',
      'They travel through the maze into the irradiation zone.',
      'They pass the source rack on one side, then the other.',
      'Product is often turned end-for-end so top and bottom average out.',
      'They exit through the maze and are unloaded.',
    ],
    physics: [
      'Dose = dose rate × time, so conveyor speed sets the delivered dose directly.',
      'Product density matters: a denser load self-shields more and gets a lower interior dose.',
      'Multiple passes and rotation shrink the ratio between the maximum and minimum dose in a load.',
    ],
    engineering: [
      'Product density is a commissioning parameter — a new product density means a new dose map.',
      'A stalled conveyor triggers source lowering to avoid overdosing a stopped tote.',
      'Carrier design (how the product is held) is part of the validated process.',
    ],
    practice: [
      'Every batch is documented against a validated process per ISO 11137.',
      'Changing product packaging can change the dose map even if the product itself is identical.',
      'Typical doses: 0.15–1 kGy phytosanitary, 6–10 kGy spices, 25 kGy medical device sterilisation.',
    ],
    numbers: [['Relation', 'D = İ × t'], ['Sterilisation dose', '25 kGy'], ['Control', 'conveyor speed']],
  },

  'ir-dosimetry': {
    oneLiner: 'Dosimeters placed throughout a reference load reveal exactly where the highest and lowest doses occur, before any real product is ever processed.',
    analogy: 'Putting thermometers all through a roast to find the cold spot — you validate once, then trust the recipe.',
    watchFor: 'The grid of dose readings across the load. Note that they are not all the same — that spread is the whole point.',
    how: [
      'A reference load of known density is filled with dosimeters at many positions.',
      'It is processed through the normal cycle.',
      'Every dosimeter is read and mapped to its position.',
      'The maximum and minimum dose positions are identified.',
      'Routine monitoring dosimeters are then placed at those known positions for every production batch.',
    ],
    physics: [
      'Alanine dosimeters are read by electron paramagnetic resonance and cover 1 Gy to 100 kGy.',
      'Fricke chemical dosimetry is the classic reference for lower doses.',
      'Dose uniformity ratio = D_max / D_min; below about 1.5 is the industrial target.',
    ],
    engineering: [
      'Traceability to a national standards laboratory is required for released product.',
      'Dosimeter response depends on temperature and humidity, so storage conditions are controlled.',
      'The dose map is specific to product, density and packaging — all three.',
    ],
    practice: [
      'Routine monitoring verifies each batch against the validated map; it does not re-map it.',
      'Any process change requires re-validation, not just a note in the log.',
      'Sterility assurance is a statistical argument built on that dose evidence.',
    ],
    numbers: [['DUR target', '< 1.5'], ['Alanine range', '1 Gy – 100 kGy'], ['Standard', 'ISO 11137']],
  },

  'ir-interlock': {
    oneLiner: 'The source only rises when every independent check confirms the cell is empty — and if any one of them drops out, gravity puts the source back in the pool.',
    analogy: 'A bank vault that needs several keys turned in the right order, and slams shut by itself if any one is removed.',
    watchFor: 'The chain of conditions turning green in sequence. Only when all four are satisfied does the source-up indicator appear.',
    how: [
      'An operator performs a physical search-and-secure walk-through of the cell.',
      'Sequenced buttons must be pressed in order and within a time limit, proving a real walk-through.',
      'The door is closed and locked, and the interlock confirms it.',
      'Area radiation monitors confirm background levels.',
      'Only then does the key switch enable the source raise.',
    ],
    physics: [
      'There is no powered-safe state: loss of power lowers the rack by gravity.',
      'Two independent source-position signals are required — losing one alone is a fault, not a licence to continue.',
      'Area monitors at every exit are wired into the interlock, not just to a display.',
    ],
    engineering: [
      'IAEA TECDOC-1313 requires that no single failure can leave the source exposed with the room accessible.',
      'Interlock logic is hard-wired for the primary safety path, not software-only.',
      'Interlock testing is a documented periodic requirement.',
    ],
    practice: [
      'Defeating an interlock to "just finish a batch" is the precursor to every serious irradiator accident.',
      'Operator licensing and documented emergency drills are part of the licence, not optional extras.',
      'Any interlock fault stops production until it is properly diagnosed.',
    ],
    numbers: [['Failure mode', 'gravity return'], ['Position signals', '2 independent'], ['Standard', 'IAEA TECDOC-1313']],
  },

  'ir-maze': {
    oneLiner: 'A labyrinth replaces a heavy shielded door: radiation has to scatter around several corners to reach the entrance, losing about an order of magnitude at each one.',
    analogy: 'Shouting down a corridor with several right-angle bends. By the third bend nobody can hear you.',
    watchFor: 'The photon dimming at every corner of the maze until it is at background level by the exit.',
    how: [
      'The entrance passage turns through several right angles between the cell and the outside.',
      'Radiation from the source cannot reach the entrance in a straight line.',
      'It must scatter off the maze walls to make each turn.',
      'Each scatter both reduces intensity and lowers the photon energy.',
      'By the entrance the dose rate is at background.',
    ],
    physics: [
      'Each 90° scatter costs roughly an order of magnitude in dose rate.',
      'Compton scattering reduces photon energy at each bounce, making later absorption easier.',
      'Skyshine — scatter off the air above the cell — is a separate calculation for large plants.',
    ],
    engineering: [
      'Maze length and leg count are set by shielding calculation, not by architecture.',
      'Product enters through the same maze on the conveyor, so no door has to open during operation.',
      'The end of the maze still needs a monitored barrier and access control.',
    ],
    practice: [
      'A maze avoids the maintenance and reliability problems of a multi-tonne shielded door.',
      'Shielding surveys are done at the maze entrance and at every accessible surface, not just at the design points.',
      'Modifications to maze geometry require re-calculation and re-survey.',
    ],
    numbers: [['Per 90° bend', '≈ 10× reduction'], ['Legs', 'set by calculation'], ['Extra term', 'skyshine']],
  },

  // ─── INDUSTRIAL RADIOGRAPHY ─────────────────────────────────────────────────
  'ix-head': {
    oneLiner: 'A directional head fires a cone through a window; a panoramic head fires in all directions at once, exposing an entire circumferential weld from inside the pipe in a single shot.',
    analogy: 'A torch versus a bare candle in the middle of a room. One lights a spot, the other lights the whole ring of wall at once.',
    watchFor: 'Switch between the narrow cone and the full 360° emission, and notice how much weld each one covers per exposure.',
    how: [
      'A directional head has shielding everywhere except a window, producing a cone.',
      'A panoramic head has a rod anode or a 360° window, emitting all around.',
      'For a girth weld, the panoramic head is placed inside the pipe at the weld plane.',
      'Film is wrapped around the outside of the pipe.',
      'One exposure covers the entire circumference — a single-wall single-image technique.',
    ],
    physics: [
      'Output falls with the square of distance, so head placement dominates exposure time.',
      'Directional heads produce better contrast per exposure because less scatter is generated overall.',
      'A panoramic exposure of a girth weld replaces many single-wall shots — a large productivity gain.',
    ],
    engineering: [
      'Rod-anode tubes reach inside small-bore pipe where a normal head will not fit.',
      'Head cooling limits duty cycle: continuous panoramic work needs forced cooling.',
      'Panoramic heads make shielding the surroundings harder — the beam goes everywhere.',
    ],
    practice: [
      'Choose panoramic for production pipeline work, directional for local repairs and confined shots.',
      'Controlled area size is much larger for panoramic exposures — plan the site accordingly.',
    ],
    numbers: [['Directional', 'cone through window'], ['Panoramic', '360° single shot'], ['Placement', 'dominates time']],
  },

  'ix-crawler': {
    oneLiner: 'A battery-powered crawler drives the X-ray head inside the pipeline and stops at each weld by detecting a small gamma marker placed outside the pipe.',
    analogy: 'A robot vacuum that stops at markers on the floor — except it is inside a steel pipe and carries an X-ray tube.',
    watchFor: 'The crawler travelling, stopping exactly at the weld marker, then firing its exposure cone.',
    how: [
      'The crawler is inserted into the pipeline and driven along it.',
      'A low-activity gamma marker is placed on the outside at each weld.',
      'The crawler detects the marker through the pipe wall and stops.',
      'A command link triggers the exposure.',
      'After the exposure it moves on to the next weld.',
    ],
    physics: [
      'The marker source is far too weak to expose film — it is a position signal, nothing more.',
      'Battery capacity and exposure time per weld set the achievable production rate.',
      'Interlocks prevent firing while the crawler is moving.',
    ],
    engineering: [
      'One crawler run can radiograph dozens of welds without breaking into the line.',
      'Wheel design and pipe diameter range determine where a given crawler can be used.',
      'Retrieval cable or magnetic recovery methods are part of the equipment package.',
    ],
    practice: [
      'A stalled crawler with a live tube is a controlled-area emergency with a defined recovery procedure.',
      'Battery management is the practical limit on how many welds a shift can cover.',
      'Marker placement accuracy directly determines whether the weld lands in the exposed field.',
    ],
    numbers: [['Positioning', 'external gamma marker'], ['Coverage', 'dozens of welds per run'], ['Interlock', 'no firing while moving']],
  },

  'ix-iqi': {
    oneLiner: 'The image quality indicator is the objective proof that the technique could have found a flaw of a stated size — without a visible IQI element, the radiograph is not acceptable.',
    analogy: 'An eye chart. It does not tell you what you are looking at, it tells you how small a thing you could have seen.',
    watchFor: 'Progressively thinner wires becoming visible. The smallest visible one is the number that gets recorded.',
    how: [
      'A set of graded wires (or a plaque with graded holes) is placed on the object.',
      'It is placed on the <b>source side</b> unless the code explicitly permits otherwise.',
      'The radiograph is taken with the technique being qualified.',
      'The smallest visible wire or hole is identified on the developed image.',
      'That value is compared against the sensitivity the applicable code requires.',
    ],
    physics: [
      'Sensitivity % = (smallest visible IQI element / material thickness) × 100.',
      'The IQI tests the whole chain at once: energy, geometry, film or detector, and processing.',
      'Placing it on the detector side would flatter the result by removing geometric unsharpness.',
    ],
    engineering: [
      'Wire IQIs follow EN 462-1 or ASTM E747; hole (plaque) IQIs are used in ASME practice with 1T, 2T and 4T holes.',
      'IQI material must match the object material group.',
      'Required sensitivity is set by the code for the material thickness — it is not negotiable.',
    ],
    practice: [
      'IQI visibility is judged on the radiograph under viewing conditions, not on a live monitor at maximum contrast stretch.',
      'No visible IQI element means an invalid radiograph, whatever the image looks like subjectively.',
      'The IQI does not measure the weld — it certifies the technique.',
    ],
    numbers: [['Placement', 'source side'], ['Standards', 'EN 462-1 / ASTM E747'], ['Rule', 'no IQI → invalid']],
  },

  'ix-film': {
    oneLiner: 'Lead foil screens pressed against the film emit photoelectrons that expose the emulsion, and at the same time absorb the soft scattered radiation that would fog it.',
    analogy: 'A screen door that lets the breeze through but keeps the insects out — the screens help the signal and block the nuisance.',
    watchFor: 'Photons striking the lead foil and producing short-range electrons that expose the film right where they land.',
    how: [
      'Lead foils are placed in direct contact with both faces of the film.',
      'A high-energy photon interacting in the lead ejects a photoelectron.',
      'That electron has a very short range and exposes the emulsion immediately adjacent.',
      'This intensifies the image, shortening the required exposure.',
      'At the same time, soft scattered radiation is absorbed in the lead before it reaches the film.',
    ],
    physics: [
      'Intensification works because lead\'s high Z gives far more interactions per incident photon than the film alone.',
      'Because the ejected electrons travel only microns, resolution is preserved.',
      'Poor screen-to-film contact lets electrons spread, producing characteristic mottled unsharpness.',
    ],
    engineering: [
      'Front screen typically 0.02–0.15 mm lead; the back screen also stops backscatter from behind.',
      'Film class (EN ISO 11699 C4–C7) trades speed against graininess and therefore against detail.',
      'Cassettes must be checked for contact and cleanliness — dirt shows on every radiograph taken with them.',
    ],
    practice: [
      'A lead letter "B" on the cassette back checks that backscatter is adequately controlled — if it shows, it is not.',
      'Processing chemistry, temperature and time are as much part of image quality as the exposure itself.',
      'Screens are consumables: creased or oxidised foils show as recurring artefacts.',
    ],
    numbers: [['Front screen', '0.02–0.15 mm Pb'], ['Film classes', 'C4–C7'], ['Backscatter check', 'lead "B"']],
  },

  'ix-dda': {
    oneLiner: 'A caesium-iodide layer converts X-rays into light directly above an amorphous-silicon pixel array, giving an image in seconds with a dynamic range no film can match.',
    analogy: 'Going from wet-chemistry photography to a digital camera. Same optics, completely different workflow.',
    watchFor: 'X-rays hitting the scintillator layer and the pixel grid below lighting up in response, row by row.',
    how: [
      'X-rays enter the CsI scintillator layer and produce visible light.',
      'CsI grows as fine needles that pipe the light straight down instead of letting it spread.',
      'Each pixel has a photodiode that converts that light into charge.',
      'A thin-film transistor holds the charge until its row is read.',
      'Row-by-row readout produces a digital image within seconds.',
    ],
    physics: [
      'The needle structure preserves resolution far better than a powder (GOS) screen would.',
      'Dynamic range of 10⁴ or more means one exposure can cover thick and thin sections together.',
      'DQE — how much of the input signal-to-noise survives — is the honest comparison metric against film.',
    ],
    engineering: [
      'Bad-pixel maps and gain/offset calibration are part of routine detector qualification, not optional setup.',
      'Detectors degrade under cumulative dose, so qualification is periodic rather than one-off.',
      'Basic spatial resolution and SNR must be demonstrated per EN ISO 17636-2 before replacing film.',
    ],
    practice: [
      'No consumables, immediate review, software measurement and easy archive — the operational case is strong.',
      'The regulatory case still requires formal qualification: Class A or Class B techniques are defined.',
      'Computed radiography with imaging plates sits between film and DDA on cost and performance.',
    ],
    numbers: [['Scintillator', 'CsI needles'], ['Dynamic range', '> 10⁴'], ['Standard', 'EN ISO 17636-2']],
  },

  'ix-ct': {
    oneLiner: 'Rotating the part through hundreds of projections reconstructs a full voxel volume that can be sectioned, measured and compared directly against the CAD model.',
    analogy: 'Photographing a loaf from every angle to work out where each raisin sits — without slicing it.',
    watchFor: 'The part rotating on the stage while the detector collects a new projection at every angle.',
    how: [
      'The part is mounted on a rotary stage between source and detector.',
      'A projection image is captured.',
      'The part rotates a fraction of a degree and another projection is taken.',
      'Hundreds or thousands of projections are collected over a full rotation.',
      'Reconstruction converts that stack into a 3-D voxel volume.',
    ],
    physics: [
      'Cone-beam CT with a flat panel is standard for small to medium parts.',
      'Voxel size is set by magnification and focal spot — micro-focus tubes reach a few micrometres.',
      'Beam hardening artefacts are corrected in software or suppressed with pre-filtration.',
    ],
    engineering: [
      'Rotary stage accuracy (sphere of confusion) directly limits achievable resolution.',
      'Reconstruction times and file sizes, not scanning, are usually the throughput bottleneck.',
      'Magnification is set by moving the part between source and detector — a geometric, not optical, zoom.',
    ],
    practice: [
      'CT metrology measures internal features no contact probe can reach — porosity, wall thickness, assembly fit.',
      'Comparison to CAD produces a colour deviation map that is immediately actionable for production.',
      'Dense or highly attenuating parts may simply be beyond the energy available.',
    ],
    numbers: [['Geometry', 'cone beam'], ['Voxel size', 'down to µm'], ['Bottleneck', 'reconstruction']],
  },

  // ─── SECURITY SCREENING ─────────────────────────────────────────────────────
  'sc-array': {
    oneLiner: 'A fixed fan beam crosses the tunnel onto an L-shaped detector array, and the image is assembled one line at a time as the belt moves the bag through.',
    analogy: 'A flatbed scanner where the paper moves instead of the sensor. The optics never change, which is why the calibration holds.',
    watchFor: 'The single fan of radiation and the L-shaped detector. Nothing moves except the belt — the image is built by that motion.',
    how: [
      'A tube fires a thin fan of radiation across the tunnel.',
      'An L-shaped array of detector elements receives what passes through.',
      'Each read of the array produces one line of the image.',
      'The belt advances the bag slightly and another line is read.',
      'Thousands of lines assemble into the picture the operator sees.',
    ],
    physics: [
      'Belt speed and line rate together fix the pixel size along the travel direction.',
      'Line-scan geometry means source and detector never move, so geometric calibration is inherently stable.',
      'The L shape wraps the beam so the bag is covered corner to corner.',
    ],
    engineering: [
      'Photodiode-plus-scintillator elements are typically 0.8–1.6 mm pitch.',
      'A dark and gain calibration runs at power-up and is repeated periodically.',
      'Belt speed is typically 0.2–0.5 m/s at a checkpoint.',
    ],
    practice: [
      'A dead detector element shows as a persistent line down the image — a daily-check item.',
      'Image stretch or compression usually means a belt speed or encoder problem, not a detector fault.',
      'Never judge image quality from a single bag — use the daily test piece.',
    ],
    numbers: [['Element pitch', '0.8–1.6 mm'], ['Belt speed', '0.2–0.5 m/s'], ['Geometry', 'fixed line scan']],
  },

  'sc-curtain': {
    oneLiner: 'Overlapping lead-rubber strips at both tunnel ends let bags pass while keeping scattered radiation inside the enclosure — and they have no interlock, so inspection is the only control.',
    analogy: 'The strip curtains on a cold store doorway. They work only if none of the strips are missing.',
    watchFor: 'The strips parting for the bag and falling back closed. Any gap left open is a direct radiation path.',
    how: [
      'Lead-loaded rubber strips hang across both tunnel openings.',
      'They overlap so there is no straight-through gap when at rest.',
      'A bag pushes them aside as it enters and they close behind it.',
      'Scattered radiation inside the tunnel is absorbed by the strips.',
      'The result keeps external dose rates at or near background.',
    ],
    physics: [
      'The primary beam is contained by the tunnel shielding; the curtains deal mainly with scatter.',
      'Leakage limit at 5 cm from any accessible surface is typically 1 µSv/h (IEC 62463).',
      'Even a small missing section creates a measurable local increase.',
    ],
    engineering: [
      'Curtains are consumables — inspect them at every routine service.',
      'Interlocks stop the beam if an access panel is opened, but curtains have no interlock at all.',
      'Strip length and overlap are specified by the manufacturer, not adjustable in the field.',
    ],
    practice: [
      'Missing or torn curtain strips are the most common cause of a failed radiation survey on a screening machine.',
      'Operators must never reach into the tunnel; retrieval procedures require the beam disabled.',
      'A visual curtain check is a legitimate daily task, not excessive caution.',
    ],
    numbers: [['Leakage limit', '< 1 µSv/h at 5 cm'], ['Interlock', 'none — visual check'], ['Standard', 'IEC 62463']],
  },

  'sc-dual': {
    oneLiner: 'A front detector reads the low-energy signal, a copper filter hardens what passes, and a rear detector reads the high-energy signal — two spectra from one exposure, inherently aligned.',
    analogy: 'Two photographs through different coloured filters taken through the same lens at the same instant. Perfectly registered by construction.',
    watchFor: 'The same object producing different relative signals in the front and rear detectors, and the ratio bar reflecting its atomic number.',
    how: [
      'Radiation passes through the object and reaches the front detector layer.',
      'That layer absorbs preferentially at low energy, recording the low-energy signal.',
      'A copper filter between the layers removes what remains of the soft beam.',
      'The rear layer records the surviving hard radiation.',
      'The ratio of the two signals maps to the effective atomic number of the material.',
    ],
    physics: [
      'Low energy is photoelectric-dominated (∝ Z³·⁵), high energy is Compton-dominated (∝ density).',
      'The ratio therefore separates <b>what</b> the material is from <b>how much</b> of it there is.',
      'Colour convention: orange for organic, green for light inorganic, blue for metal, black for opaque.',
    ],
    engineering: [
      'No dual source or fast kV switching is needed — mechanically simple and inherently registered.',
      'Filter thickness sets the energy separation between the two channels.',
      'Both layers must be calibrated together; replacing one alone invalidates the discrimination.',
    ],
    practice: [
      'Thick metal saturates the discrimination — the console flags it rather than guessing.',
      'Colour is a physics measurement, not a threat decision: interpretation remains the operator\'s job.',
      'Loss of colour discrimination with normal grayscale usually means a rear-layer or filter problem.',
    ],
    numbers: [['Low-E', '∝ Z³·⁵'], ['High-E', '∝ density'], ['Output', 'Zeff colour map']],
  },

  'sc-ct': {
    oneLiner: 'Source and detector rotate continuously on a slip ring while the bag translates through, producing a helical scan and a full three-dimensional reconstruction.',
    analogy: 'A medical CT scanner adapted for luggage: the same physics, tuned for throughput instead of patient dose.',
    watchFor: 'The rotating gantry and translating bag. Every voxel gets a measured value instead of a superimposed shadow.',
    how: [
      'The bag moves through the gantry at constant speed.',
      'Source and detector rotate around it at 2–4 revolutions per second.',
      'The combination traces a helical path around the bag.',
      'Reconstruction converts the projections into a voxel volume.',
      'Automatic detection algorithms search that volume for threat signatures.',
    ],
    physics: [
      'Reconstruction gives a CT number per voxel — a measured property, not an impression.',
      'Density and effective atomic number per voxel are what explosive-detection algorithms actually use.',
      'Helical pitch and belt speed together determine slice quality and throughput.',
    ],
    engineering: [
      'Slip rings remove cable wrap, allowing continuous rotation instead of back-and-forth motion.',
      'Rotating a heavy source and detector at several revolutions per second is a serious mechanical problem.',
      'ECAC Standard 3 and TSA certification define detection and false-alarm performance.',
    ],
    practice: [
      'CT at the checkpoint is why laptops and liquids can stay in the bag — the volume is resolved.',
      'Alarm resolution is still a human task: the machine flags, the operator decides and documents.',
      'Reconstruction and algorithm software are certified items; they cannot be updated casually.',
    ],
    numbers: [['Rotation', '2–4 rev/s'], ['Output', 'CT number per voxel'], ['Certification', 'ECAC Std 3 / TSA']],
  },

  'sc-backscatter': {
    oneLiner: 'A pencil beam sweeps across the target and large detectors on the same side collect Compton-scattered photons — organic material scatters strongly and appears bright.',
    analogy: 'Sweeping a torch across a dark wall and watching what reflects back. You never need to get behind the wall.',
    watchFor: 'The scattered rays returning to detectors on the same side as the source. Nothing is measured on the far side at all.',
    how: [
      'A chopper wheel converts a fan beam into a fast-moving pencil beam.',
      'The pencil sweeps across the target line by line.',
      'Photons scatter in all directions from whatever they hit.',
      'Large-area detectors beside the source collect the ones scattered backwards.',
      'Because the beam direction is known at every instant, each detected photon maps to a pixel.',
    ],
    physics: [
      'Compton scattering from low-Z material is strong; high-Z material absorbs instead of scattering back.',
      'That inverts the contrast compared with transmission: organics bright, steel dark.',
      'Effective dose per personnel scan is around 0.05–0.1 µSv — minutes of natural background.',
    ],
    engineering: [
      'The image is built from where the beam was pointing, not from where the photons landed — detector position hardly matters.',
      'Detectors are large plastic scintillators; more area simply means more signal.',
      'Penetration is shallow: a surface and near-surface technique, a few centimetres in steel.',
    ],
    practice: [
      'Single-sided access is the defining advantage: vehicles, walls, containers and personnel.',
      'Depth information is poor compared with transmission — it complements, not replaces, it.',
      'Privacy-preserving automated target recognition replaced raw body images in most jurisdictions.',
    ],
    numbers: [['Contrast', 'organic bright'], ['Body scan dose', '0.05–0.1 µSv'], ['Depth', 'shallow']],
  },

  'sc-rpm': {
    oneLiner: 'Large plastic scintillator panels watch passing vehicles for gamma and neutron emission — a completely passive system that emits nothing at all.',
    analogy: 'A metal detector arch that listens instead of transmitting. It only notices what the vehicle itself is giving off.',
    watchFor: 'The count-rate trace staying flat until a source passes, then spiking above the rolling background.',
    how: [
      'Panels on both sides of the lane continuously count gamma events.',
      'A rolling estimate of the natural background is maintained.',
      'A vehicle passes between the panels.',
      'If the count rate rises significantly above background, an alarm is raised.',
      'A separate neutron channel targets special nuclear material specifically.',
    ],
    physics: [
      'Plastic scintillator is cheap and large but has essentially no spectroscopic capability.',
      'Alarm is on count rate above a rolling background — so a dense load that suppresses background matters.',
      'Neutron detection uses He-3 or B-10 because it targets material that gammas alone may not reveal.',
    ],
    engineering: [
      'Performance requirements are defined in ANSI N42.35 and N42.38.',
      'Panel size is driven by solid angle: bigger panels catch more of the emitted radiation.',
      'Occupancy sensors define when a vehicle is in the measurement zone.',
    ],
    practice: [
      'Naturally occurring radioactive material — fertiliser, ceramics, bananas, medical patients — causes most alarms.',
      'Positive alarms go to secondary inspection with a handheld spectroscopic identifier.',
      'Because it is passive, the portal poses no radiation hazard whatever to drivers or staff.',
    ],
    numbers: [['Detector', 'plastic scintillator'], ['Mode', 'fully passive'], ['Standards', 'ANSI N42.35/38']],
  },

  'sc-operator': {
    oneLiner: 'Fictional threat images are injected into the live image stream at a controlled rate, measuring and maintaining detection performance while real screening continues.',
    analogy: 'A driving instructor occasionally saying "emergency stop" during a normal drive. It keeps the skill sharp and measures it honestly.',
    watchFor: 'The injected TIP image appearing in the stream, and the shift-time indicator changing colour as the rotation limit approaches.',
    how: [
      'The system holds a library of realistic threat images.',
      'At random intervals it superimposes one onto a real bag image.',
      'The operator responds exactly as they would to a real threat.',
      'The system records whether it was detected, then reveals that it was a test.',
      'Detection statistics accumulate per operator and per threat category.',
    ],
    physics: [
      'Detection performance drops measurably after roughly 20 minutes of continuous image review.',
      'Vigilance decrement is a well-documented human factor, not a training deficiency.',
      'That is why rotation intervals and break scheduling are regulated rather than left to local discretion.',
    ],
    engineering: [
      'Image enhancement tools (organic strip, inorganic strip, edge enhance) are part of trained procedure, not personal preference.',
      'TIP data feeds recurrent training: individual weak categories can be targeted specifically.',
      'The console is a decision aid — the machine flags, the human decides and documents.',
    ],
    practice: [
      'The real limiting factor at a checkpoint is human vigilance, not the machine\'s physics.',
      'Recurrent competency testing is a regulatory requirement in aviation security.',
      'TIP rates must be high enough to be meaningful but low enough not to erode trust in real alarms.',
    ],
    numbers: [['Vigilance limit', '≈ 20 min'], ['Method', 'threat image projection'], ['Decision', 'human, documented']],
  },
};
