import type { Lesson } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Mini-lessons — imaging technologies: transmission, scatter, tomography, spectral.
// ═══════════════════════════════════════════════════════════════════════════════

export const TECHNOLOGY_LESSONS: Record<string, Lesson> = {

  'tech-transmission': {
    oneLiner: 'Count the photons that make it straight through, and every pixel becomes a measure of how much material was in the way along that one ray.',
    analogy: 'Holding a leaf up to a window. Thick veins block more light and appear dark — but you cannot tell whether a dark line is one thick vein or two thin ones stacked.',
    watchFor: 'Photons passing freely except where the dense insert blocks them, and the detector bars on the right shortening exactly there.',
    how: [
      'A source on one side emits photons toward the object.',
      'Some are absorbed or scattered away inside the object.',
      'The survivors reach a detector on the far side.',
      'Each detector element records how many arrived along its own ray.',
      'Mapping that count to grey level produces the familiar shadow image.',
    ],
    physics: [
      'Beer–Lambert law: <code>I = I₀ · e^(−∫µ dx)</code> — every pixel is one line integral.',
      'Contrast comes from differences in µ·x, so a thin dense object can look identical to a thick light one.',
      'Superposition is the fundamental weakness: everything along the ray collapses into a single number.',
    ],
    engineering: [
      'It is the highest-efficiency modality — most useful photons are actually used.',
      'It needs access to both sides, which rules it out for walls, vehicles in place and ship hulls.',
      'Geometry is fixed, so calibration is stable over long periods.',
    ],
    practice: [
      'Every other technology in this section exists to fix one of transmission\'s limitations.',
      'Adding a second view or a second energy is almost always cheaper than switching modality entirely.',
    ],
    numbers: [['Law', 'I = I₀e^(−∫µdx)'], ['Access', 'two-sided required'], ['Weakness', 'superposition']],
  },

  'tech-dualview': {
    oneLiner: 'Two source-detector pairs at different angles break the superposition problem: a thin plate invisible edge-on in one view is fully visible in the other.',
    analogy: 'Looking at a playing card edge-on you see a line; from the front you see the whole card. Two views and nothing can hide.',
    watchFor: 'The blade rotating between edge-on and broadside. One view loses it completely while the other sees it clearly.',
    how: [
      'A second source and detector are installed at a different angle in the same tunnel.',
      'Both fire as the bag passes, producing two independent images.',
      'An object presenting minimum area to one beam presents more to the other.',
      'The operator (or the algorithm) sees both images together.',
      'Objects that hide in one projection are exposed in the other.',
    ],
    physics: [
      'The classic defeat for single-view screening is a blade presented edge-on to the beam.',
      'Multi-view does not reconstruct a volume — it just samples a few projections.',
      'Four-view systems approach CT-like confidence for a fraction of the cost and dose.',
    ],
    engineering: [
      'Views are typically at 90°, or at a shallower offset chosen to fit the tunnel envelope.',
      'Each view needs its own generator, detector array and calibration.',
      'More views mean more shielding, more heat and a longer machine.',
    ],
    practice: [
      'Dual view is the standard mitigation for edge-on threats at cabin-baggage checkpoints.',
      'Correlating the two images is a trained skill, not automatic.',
    ],
    numbers: [['Typical angle', '90°'], ['Solves', 'edge-on threats'], ['Not', 'a volume reconstruction']],
  },

  'tech-dualenergy': {
    oneLiner: 'Two energies through the same path give two independent measurements, which is exactly what you need to separate what a material is from how much of it there is.',
    analogy: 'Weighing a parcel and also measuring its size. Either alone is ambiguous; together they tell you what is inside.',
    watchFor: 'Each material showing a different ratio between the purple low-energy bar and the blue high-energy bar. That ratio is the material signature.',
    how: [
      'The object is imaged at a low effective energy and at a high one.',
      'At low energy, attenuation depends strongly on atomic number.',
      'At high energy, it depends mainly on density and thickness.',
      'The ratio of the two measurements cancels most of the thickness dependence.',
      'What remains is a value that tracks the effective atomic number.',
    ],
    physics: [
      'Photoelectric absorption ∝ <code>Z³·⁵/E³</code>; Compton scattering ∝ density and is nearly Z-independent.',
      'Organic materials have Zeff ≈ 6–8; light metals and salts around 11–20; steel and above, over 20.',
      'MeV cargo systems use 6/9 MeV interleaving for the same purpose at far greater thickness.',
    ],
    engineering: [
      'Implementation options: sandwich detector with a copper interlayer, fast kV switching, or dual sources.',
      'The sandwich approach is inherently registered — both measurements share the same ray exactly.',
      'Output is the familiar orange / green / blue colour map on every screening console.',
    ],
    practice: [
      'Very thick steel saturates the measurement — the console flags it rather than guessing.',
      'Colour is a physics result, not a threat decision. Interpretation is still the operator\'s job.',
    ],
    numbers: [['Organic Zeff', '6–8'], ['Metal Zeff', '> 20'], ['Cargo', '6/9 MeV interleaved']],
  },

  'tech-highenergy': {
    oneLiner: 'At MeV energies attenuation is almost purely Compton, so the image is essentially a density map — but one that can see through more than 300 mm of steel.',
    analogy: 'Turning up the power on a torch until it shines through a wall. You can now see shapes, but all the colour information is gone.',
    watchFor: 'The beam penetrating the whole container, with contrast coming from mass rather than material type.',
    how: [
      'A LINAC produces bremsstrahlung with an endpoint of 6–9 MeV.',
      'The beam passes through the entire container and its contents.',
      'Dense scintillator detectors on the far side record what survives.',
      'The container moves through the beam to build a full image.',
      'Interleaved energies restore some material discrimination.',
    ],
    physics: [
      'A 6 MeV LINAC penetrates roughly 300 mm of steel; 9 MeV reaches about 380 mm.',
      'Because Compton dominates, single-energy MeV imaging cannot identify materials — only mass.',
      'Pair production begins to contribute above 1.022 MeV and re-introduces a weak Z dependence at very high energy.',
    ],
    engineering: [
      'Detector arrays use dense scintillators (CdWO₄) with photodiodes to cope with the energy.',
      'Dose per scan is far higher than a baggage tunnel, so occupancy exclusion zones are large.',
      'Neutron production above about 8 MeV becomes a shielding consideration in its own right.',
    ],
    practice: [
      'People are never in the beam: drive-through systems either move the vehicle empty or scan with the cab excluded.',
      'Exclusion zone management is the dominant operational constraint at a cargo site.',
    ],
    numbers: [['6 MeV', '≈ 300 mm steel'], ['9 MeV', '≈ 380 mm steel'], ['Detector', 'CdWO₄']],
  },

  'tech-angular': {
    oneLiner: 'The angle a photon scatters into is not random — it follows the Klein–Nishina distribution, and that distribution decides which imaging technologies are even possible at a given energy.',
    analogy: 'Throwing a tennis ball at a wall: a slow ball can bounce straight back, a very fast one mostly deflects forward. Photons behave the same way.',
    watchFor: 'The purple lobe changing shape as the energy sweeps. At low energy it is nearly symmetric; at high energy it collapses forward.',
    how: [
      'A photon strikes an electron and scatters.',
      'At low energy it can go in almost any direction, including straight back.',
      'As energy rises, forward angles become increasingly favoured.',
      'By a few hundred keV, backward scattering has become rare.',
      'That is why backscatter imaging works at 100 keV but not at 6 MeV.',
    ],
    physics: [
      'The Klein–Nishina cross-section gives the probability per unit solid angle as a function of angle and energy.',
      'Below about 100 keV a useful fraction scatters backwards — the basis of backscatter imaging.',
      'Coherent (Rayleigh) scatter is confined to very small forward angles and carries structural information.',
    ],
    engineering: [
      'Scatter that is not used for imaging is noise — the reason grids, collimators and air gaps exist.',
      'Scatter-to-primary ratio drives shielding design as much as the primary beam does.',
      'Detector placement in any scatter system is dictated entirely by this lobe shape.',
    ],
    practice: [
      'If you know the energy, you already know roughly which modality can work — before any hardware discussion.',
      'This single graph explains why personnel backscatter scanners run at low energy and cargo systems do not use backscatter at all.',
    ],
    numbers: [['Backscatter viable', '≲ 120 keV'], ['High energy', 'forward-peaked'], ['Coherent', 'very small angles']],
  },

  'tech-backscatter': {
    oneLiner: 'Sweep a pencil beam across the scene and collect the photons that come back — you get an image from one side only, with organic material shining bright.',
    analogy: 'Painting a dark room with a laser pointer while a camera watches the whole wall. You know where the dot is at every instant, so you can build the picture.',
    watchFor: 'Scattered rays returning to the detector on the same side as the source. The image line brightens when the beam hits organic material.',
    how: [
      'A chopper wheel turns a fan beam into a fast-sweeping pencil beam.',
      'The pencil scans across the target, line by line.',
      'Photons scatter from whatever the pencil is currently illuminating.',
      'Large unfocused detectors beside the source collect a fraction of them.',
      'Because the beam direction is known at every instant, each detected photon maps to the correct pixel.',
    ],
    physics: [
      'Organic material (drugs, explosives, people) scatters strongly; steel absorbs and appears dark.',
      'That inverts the contrast compared with transmission — a genuinely complementary image.',
      'Penetration is shallow, typically a few centimetres in steel: this is a surface technique.',
    ],
    engineering: [
      'The image comes from beam position, not detector position — so detectors can be crude and enormous.',
      'Detectors are large-area plastic scintillators; more area simply means more signal.',
      'Chopper wheel speed and beam current together set the scan rate.',
    ],
    practice: [
      'Single-sided access is the defining advantage: vehicles, walls, aircraft skins, containers in place.',
      'It does not replace transmission — it answers a different question about a different depth.',
    ],
    numbers: [['Access', 'single-sided'], ['Contrast', 'organic bright'], ['Depth', 'a few cm in steel']],
  },

  'tech-zbv': {
    oneLiner: 'Build the whole flying-spot system into a van and you can image parked cars, trucks and containers from the roadside with no set-up on the far side at all.',
    analogy: 'A mobile speed camera for contraband — it drives past and takes the picture, and the target never has to be prepared.',
    watchFor: 'The van moving past the target and the concealed object gradually brightening in the reconstructed image.',
    how: [
      'The source, chopper and detectors are mounted inside a vehicle.',
      'The van drives slowly past the target.',
      'The pencil beam sweeps vertically while the vehicle motion provides the horizontal axis.',
      'Backscattered photons are collected by detectors in the van.',
      'The image builds up column by column as the van travels.',
    ],
    physics: [
      'Vehicle motion is the slow scan axis — image quality depends directly on speed stability.',
      'It sees organic contraband hidden behind steel skin that transmission would render as a blur.',
      'Because the primary beam exits the vehicle shell, exclusion zones must be defined and enforced.',
    ],
    engineering: [
      'Operators work from a shielded cab with an interlocked beam-on control.',
      'Ruggedisation for road use is a significant part of the engineering.',
      'GPS or wheel encoders correct the image for speed variation.',
    ],
    practice: [
      'Regulatory acceptance depends on demonstrating dose to bystanders and to any person inside the target.',
      'Operational procedures must guarantee the exclusion zone is clear before every scan.',
      'Occupant-in-vehicle scanning is heavily restricted in most jurisdictions.',
    ],
    numbers: [['Slow axis', 'vehicle motion'], ['Access', 'roadside, single-sided'], ['Key control', 'exclusion zone']],
  },

  'tech-forward': {
    oneLiner: 'Photons deflected by only a few degrees still carry information about sub-millimetre structure — so collect them just off the primary axis instead of throwing them away.',
    analogy: 'Looking at a beam of sunlight in a dusty room. The dust is invisible head-on but obvious in the light scattered slightly off-axis.',
    watchFor: 'The beam stop blocking the intense primary while the weak small-angle rays continue past it to the detector.',
    how: [
      'The primary beam passes through the sample.',
      'A small fraction is deflected by a few degrees by internal structure.',
      'A beam stop blocks the intense unscattered beam.',
      'A detector ring around the stop records the small-angle signal.',
      'Intensity versus angle reveals characteristic sizes inside the material.',
    ],
    physics: [
      'Small-angle scatter intensity depends on particle size and packing, not just bulk density.',
      'Powders, fibres and emulsions produce characteristic small-angle signatures.',
      'It is the physical basis for the dark-field channel in grating interferometry.',
    ],
    engineering: [
      'A beam stop is essential — the primary would otherwise swamp the weak scattered signal completely.',
      'Long collimation distances are needed to resolve small angles.',
      'Combined with transmission it adds a channel that pure attenuation cannot supply.',
    ],
    practice: [
      'Two materials with identical density can have completely different small-angle signatures.',
      'It is slower than transmission, so it fits a secondary-inspection role.',
    ],
    numbers: [['Angles', 'a few degrees'], ['Sensitive to', 'particle size'], ['Requires', 'beam stop']],
  },

  'tech-coherent': {
    oneLiner: 'Crystalline materials scatter coherently at angles set by their lattice spacing, giving a diffraction fingerprint that identifies the substance rather than just its density.',
    analogy: 'A barcode for molecules. Two white powders look identical until you scan their pattern.',
    watchFor: 'The crystalline sample producing sharp discrete rays while the amorphous one produces only a diffuse spread.',
    how: [
      'The beam passes through the sample.',
      'In a crystal, atoms sit on regular planes.',
      'Waves scattered from successive planes interfere.',
      'At specific angles they add constructively, producing sharp peaks.',
      'The peak positions are determined by the crystal spacing, which is unique to the substance.',
    ],
    physics: [
      'Bragg condition: <code>nλ = 2 d sin θ</code>. Measuring θ gives d, and d identifies the material.',
      'Amorphous materials have no long-range order, so they produce only a diffuse halo.',
      'Angles are small (a few degrees) at the energies used, so long collimation paths are needed.',
    ],
    engineering: [
      'Energy-dispersive geometry uses a fixed angle and a spectroscopic detector instead of scanning angle.',
      'Multi-focus and coded-aperture designs speed acquisition for security use.',
      'It distinguishes crystalline explosives from inert powders that attenuate identically.',
    ],
    practice: [
      'Slow compared with transmission — used as a secondary confirmation stage, not a primary scanner.',
      'Very effective exactly where dual-energy fails: substances of the same effective Z but different structure.',
    ],
    numbers: [['Bragg law', 'nλ = 2d sinθ'], ['Angles', 'few degrees'], ['Role', 'confirmation stage']],
  },

  'tech-comptontomo': {
    oneLiner: 'Because a scattered photon\'s energy tells you the angle it turned through, a spectroscopic detector can work out exactly which point in space scattered it — giving depth from one side only.',
    analogy: 'Echo-location with colour: the pitch of the echo tells you the angle it came from, so you can locate the object without going around it.',
    watchFor: 'The scattering point moving deeper into the object and the reported scattered energy changing with it.',
    how: [
      'A pencil beam of known direction enters the object.',
      'A photon scatters at some point along that line.',
      'It reaches a collimated spectroscopic detector at a known position.',
      'Its measured energy reveals the scattering angle.',
      'Beam direction plus scattering angle plus detector position fixes the scattering point in three dimensions.',
    ],
    physics: [
      'Scattered energy: <code>E′ = E / (1 + (E/m₀c²)(1 − cos θ))</code> — energy is a direct measure of angle.',
      'Enables single-sided tomography of walls, aircraft skins and thick composite panels.',
      'Multiple scattering blurs the reconstruction and must be modelled or suppressed.',
    ],
    engineering: [
      'Requires a detector with real energy resolution — CdTe or HPGe, not a plastic scintillator.',
      'Count rates are low, so acquisition is slow compared with transmission CT.',
      'Collimation geometry directly determines the achievable spatial resolution.',
    ],
    practice: [
      'A research and specialist technique rather than a checkpoint workhorse.',
      'Valuable exactly where you cannot get behind the object and still need depth information.',
    ],
    numbers: [['Key relation', "E′ from cos θ"], ['Access', 'single-sided'], ['Limit', 'low count rate']],
  },

  'tech-geometry': {
    oneLiner: 'Beam shape sets the trade between scatter rejection, dose efficiency and speed — from one ray at a time to a whole volume in a single shot.',
    analogy: 'Painting with a fine brush, a roller, or a spray gun. Same paint, completely different speed and overspray.',
    watchFor: 'The three beam shapes cycling. Notice how the detector shape must change with each one.',
    how: [
      'A pencil beam illuminates one ray at a time — scatter has almost nowhere to go but away.',
      'A fan beam illuminates one line, matched to a linear detector array.',
      'A cone beam illuminates a whole area, matched to a flat panel.',
      'Wider beams collect more data per exposure but also generate and collect far more scatter.',
      'The detector geometry must be designed together with the beam shape.',
    ],
    physics: [
      'Scatter-to-primary ratio rises sharply with irradiated volume.',
      'Pencil beam gives the best scatter rejection of all, but is the slowest.',
      'Cone beam is fastest but needs anti-scatter grids, air gaps or software correction.',
    ],
    engineering: [
      'Fan beam is the line-scan workhorse: near-ideal for conveyors and for medical CT slices.',
      'Cone-beam artefacts grow toward the edges of the field — a geometric limitation, not a tuning problem.',
      'Collimator design is what actually creates the beam shape.',
    ],
    practice: [
      'Beam shape and detector geometry must be designed together, never chosen independently.',
      'Choosing a wider beam for speed always costs image quality somewhere — decide where you can afford it.',
    ],
    numbers: [['Pencil', 'best scatter rejection'], ['Fan', 'line-scan standard'], ['Cone', 'fastest, most scatter']],
  },

  'tech-ct': {
    oneLiner: 'Take hundreds of projections around the object and mathematically back-project them into a grid — the superimposed shadow becomes a measured value for every voxel.',
    analogy: 'Working out the layout of a building from its shadows at every hour of the day. One shadow is ambiguous; hundreds are not.',
    watchFor: 'Projection lines accumulating around the object while the voxel grid on the right sharpens from noise into a clear shape.',
    how: [
      'A projection is captured at one angle.',
      'The object (or the gantry) rotates a fraction of a degree.',
      'Another projection is captured, and so on through at least 180° plus the fan angle.',
      'Each projection is filtered and smeared back across the reconstruction grid.',
      'Where all projections agree, structure emerges; elsewhere the contributions cancel.',
    ],
    physics: [
      'Each voxel receives a CT number — a measured attenuation, not an impression.',
      'Filtered back-projection is fast; iterative and model-based methods cut dose and artefacts.',
      'Beam hardening, metal streaks and cone-beam artefacts are the main image-quality enemies.',
    ],
    engineering: [
      'In security this is what enables automatic explosive detection on hold and now cabin baggage.',
      'In industry it enables internal metrology against a CAD model with no destructive sectioning.',
      'Reconstruction compute and data storage are often the practical bottleneck, not the scanning.',
    ],
    practice: [
      'A CT number is comparable between scans only if calibration is maintained — that is what makes automatic detection possible.',
      'Sparse-view reconstruction trades image quality for speed when full sampling is not affordable.',
    ],
    numbers: [['Angular range', '≥ 180° + fan'], ['Output', 'CT number per voxel'], ['Enemy', 'beam hardening']],
  },

  'tech-tomo': {
    oneLiner: 'Sweep the source over a limited arc instead of a full circle: you get depth separation between layers, cheaply and quickly, at the cost of blurred depth resolution.',
    analogy: 'Tilting your head side to side to see behind an object. It helps a lot, but it is not the same as walking all the way around it.',
    watchFor: 'The source sweeping over a limited arc, and the two layers separating in the reconstruction even though the sweep never completes a circle.',
    how: [
      'The source moves over an arc of typically 15°–50° while the detector stays fixed (or moves slightly).',
      'Projections are captured throughout the sweep.',
      'Reconstruction shifts and adds the projections for a chosen depth plane.',
      'Structures at that depth reinforce; structures at other depths blur out.',
      'Repeating for different shifts produces a stack of in-focus planes.',
    ],
    physics: [
      'In-plane resolution is excellent; through-plane resolution is poor and direction-dependent.',
      'The limited angular range means the reconstruction problem is fundamentally under-determined.',
      'Artefacts from out-of-plane structures are inherent, not a tuning failure.',
    ],
    engineering: [
      'Used where geometry forbids a full rotation — in-line inspection, large panels, breast imaging.',
      'Far cheaper and faster than CT because there is no gantry and far fewer projections.',
      'It removes the superposition problem for layered objects such as circuit boards and welds.',
    ],
    practice: [
      'Do not expect CT-quality depth information; expect layer separation and read it as such.',
      'Sweep angle is the single parameter that most affects depth resolution.',
    ],
    numbers: [['Sweep', '15°–50°'], ['In-plane', 'excellent'], ['Depth', 'blurred']],
  },

  'tech-multisource': {
    oneLiner: 'Instead of rotating one source, fire many fixed emitters in sequence — with no moving mass, scan speed is limited only by the electronics.',
    analogy: 'A camera flash ring instead of one flash you have to carry around the subject. Same coverage, no movement.',
    watchFor: 'Each emitter firing in turn, illuminating the object from a different angle without anything moving.',
    how: [
      'An array of individually addressable emitters is arranged around the object.',
      'Each one is switched on briefly in sequence.',
      'A detector array records a projection for each emitter position.',
      'The set of projections covers a range of angles.',
      'Reconstruction proceeds as for CT, but from a sparse set of fixed viewpoints.',
    ],
    physics: [
      'Angular coverage is set by array geometry and is usually sparse, so reconstruction is model-based.',
      'Sparse-view artefacts are handled by iterative reconstruction rather than by more projections.',
      'No rotating mass means no centrifugal limit on speed.',
    ],
    engineering: [
      'Carbon-nanotube and distributed field-emission arrays make dozens of addressable emitters practical.',
      'No rotating gantry means far lower maintenance and much faster effective frame rates.',
      'Each emitter needs its own focusing and gating electronics.',
    ],
    practice: [
      'Well suited to conveyor lines where the object is already moving through the field.',
      'Emitter uniformity and lifetime are the key reliability questions for this technology.',
    ],
    numbers: [['Moving parts', 'none'], ['Coverage', 'sparse, fixed angles'], ['Reconstruction', 'iterative']],
  },

  'tech-photoncount': {
    oneLiner: 'Count each photon individually and sort it into an energy bin, instead of just integrating total charge — several spectral channels from a single exposure, with no electronic noise floor.',
    analogy: 'Counting coins one by one and sorting them by denomination, instead of just weighing the whole pile.',
    watchFor: 'Individual photons arriving and being placed into different energy bins, rather than adding to one running total.',
    how: [
      'A photon interacts in a direct-conversion sensor and creates a charge pulse.',
      'A fast amplifier shapes that pulse.',
      'Comparators check the pulse height against several thresholds.',
      'The photon is counted in the bin matching its energy.',
      'Reading out several bins gives several spectral images from one exposure.',
    ],
    physics: [
      'Energy binning gives multi-material decomposition far beyond two-channel dual energy.',
      'No dark noise means low-dose imaging improves rather than degrading proportionally.',
      'The same technology moves K-edge imaging from research into deployable systems.',
    ],
    engineering: [
      'Direct-conversion sensors (CdTe, CZT) generate charge without a scintillator light stage.',
      'Charge sharing between pixels and pulse pile-up at high flux are the practical engineering limits.',
      'Each pixel needs its own counting ASIC channel — density and power are real constraints.',
    ],
    practice: [
      'The first clinical photon-counting CT was approved in 2021 — this is now product, not research.',
      'Pile-up correction is essential at the flux levels real systems actually run.',
    ],
    numbers: [['Sensors', 'CdTe / CZT'], ['Noise floor', 'essentially none'], ['Limits', 'charge sharing, pile-up']],
  },

  'tech-kedge': {
    oneLiner: 'Every element has a sharp jump in absorption at its K-edge, so imaging just below and just above that energy isolates that one element from everything else in the scene.',
    analogy: 'A pair of glasses that make one specific colour vanish. Take a photo with and without, subtract, and only that colour remains.',
    watchFor: 'The absorption curve jumping at the K-edge, and the sample switching between visible and hidden as the energy crosses it.',
    how: [
      'Choose two narrow energy bands, one just below and one just above the element\'s K-edge.',
      'Acquire an image in each band.',
      'Below the edge, the element is relatively transparent.',
      'Above the edge, it absorbs strongly.',
      'Subtracting the two images cancels the background and leaves only that element.',
    ],
    physics: [
      'K-edge energies: iodine 33.2 keV, gadolinium 50.2 keV, tungsten 69.5 keV, lead 88.0 keV.',
      'The jump happens because above the edge a photon can eject a K-shell electron; below it, it cannot.',
      'Everything else in the scene changes only smoothly across that small energy step, so it subtracts away.',
    ],
    engineering: [
      'Requires narrow energy bands — synchrotron beams, filtered spectra or photon-counting bins.',
      'Band width directly determines how much of the background actually cancels.',
      'Photon-counting detectors make this practical outside a synchrotron for the first time.',
    ],
    practice: [
      'In security it can flag specific high-Z materials rather than merely "something dense".',
      'In medicine it is the basis of contrast-agent-specific and dual-contrast imaging.',
    ],
    numbers: [['Iodine K-edge', '33.2 keV'], ['Tungsten K-edge', '69.5 keV'], ['Method', 'subtract two bands']],
  },

  'tech-xrf': {
    oneLiner: 'Illuminate a sample with X-rays and read the characteristic lines it emits back — each element has its own line energies, so the spectrum names what is there.',
    analogy: 'Shining light on a mineral and identifying it by the exact colour it glows. Every element has its own fingerprint colour.',
    watchFor: 'The excitation beam striking the sample and distinct labelled lines appearing in the spectrum on the right.',
    how: [
      'An X-ray source illuminates the sample surface.',
      'Photons eject inner-shell electrons from atoms in the sample.',
      'Outer-shell electrons drop into the vacancies.',
      'Each drop emits a photon of energy equal to the difference between the two shells.',
      'A spectroscopic detector records those energies, identifying the elements present.',
    ],
    physics: [
      'This is the same inner-shell physics as characteristic emission in an X-ray tube — used here as an analytical probe.',
      'Line energies depend only on the element (Moseley\'s law), so identification is unambiguous.',
      'Light elements below sodium are hard because their fluorescence energies are absorbed in air.',
    ],
    engineering: [
      'Silicon drift detectors give the energy resolution needed to separate neighbouring elements.',
      'Handheld XRF identifies alloys, coatings and contaminants in seconds without any sampling.',
      'Detection depth is shallow — it is a surface and near-surface technique.',
    ],
    practice: [
      'Used for alloy verification, RoHS screening, art authentication and soil contamination survey.',
      'Surface contamination or coating will dominate the result — sample preparation matters.',
      'Handheld units emit a real primary beam: the safety interlock and trigger discipline are not decorative.',
    ],
    numbers: [['Detector', 'silicon drift'], ['Depth', 'surface / near-surface'], ['Limit', 'light elements < Na']],
  },

  'tech-phase': {
    oneLiner: 'X-rays refract very slightly passing through matter; grating interferometry reads that phase shift and the loss of fringe visibility, adding two channels to plain attenuation.',
    analogy: 'Seeing a clear glass rod in water. It absorbs almost nothing, but it bends light — and that bending is what makes it visible.',
    watchFor: 'The reference wave and the shifted wave. Where the sample sits, the fringe both shifts and loses contrast — those are the two extra channels.',
    how: [
      'A source grating creates an array of mutually coherent line sources.',
      'A phase grating downstream produces an interference (Talbot) pattern.',
      'The sample slightly refracts the beam, shifting that pattern sideways.',
      'Micro-structure inside the sample scatters at small angles, blurring the pattern.',
      'An analyser grating converts both effects into measurable intensity changes.',
    ],
    physics: [
      'Phase shift can be orders of magnitude larger than absorption for light materials.',
      'Three signals result: attenuation, differential phase (refraction) and dark field (small-angle scatter).',
      'The dark-field channel maps sub-pixel micro-structure — cracks, fibres, powders.',
    ],
    engineering: [
      'A Talbot–Lau interferometer (three gratings) makes it work with an ordinary tube, not just a synchrotron.',
      'Grating periods are micrometres, so mechanical stability at that scale is the core engineering problem.',
      'Cost is acquisition time and stability, not exotic sources.',
    ],
    practice: [
      'Excellent for soft materials, composites and explosives that attenuate almost identically.',
      'Still largely a research and specialist-inspection technique rather than a checkpoint product.',
    ],
    numbers: [['Channels', 'attenuation + phase + dark field'], ['Setup', 'Talbot–Lau, 3 gratings'], ['Grating period', 'micrometres']],
  },

  'tech-grid': {
    oneLiner: 'Scattered photons arrive off-axis carrying no positional truth, so a grid of lead strips absorbs them — or simply move the detector back and let geometry do the same job for free.',
    analogy: 'Venetian blinds angled at the sun: light from the right direction gets through, light from anywhere else does not.',
    watchFor: 'Primary rays passing straight through the grid while the off-angle scattered rays are stopped by the lead strips.',
    how: [
      'The primary beam travels in a known direction from the focal spot.',
      'Scattered photons leave the object in random directions.',
      'A grid of thin lead strips is aligned with the primary direction.',
      'Primary photons pass between the strips.',
      'Off-angle scattered photons strike a strip and are absorbed.',
    ],
    physics: [
      'Scatter-to-primary ratio can exceed 3:1 in thick sections — most of the arriving signal is noise.',
      'Grid ratio = strip height / interspace width; higher ratio rejects more scatter and needs more dose.',
      'An air gap achieves a similar effect geometrically, since scatter diverges faster than primary.',
    ],
    engineering: [
      'Grid cut-off from misalignment causes a characteristic density loss across the image.',
      'Focused grids must be used at their design distance; parallel grids are more forgiving but less efficient.',
      'Digital scatter-correction algorithms increasingly supplement, but do not replace, physical rejection.',
    ],
    practice: [
      'Using a grid always costs dose — it is a deliberate trade for contrast.',
      'An air gap is the zero-cost alternative, at the price of magnification and geometric unsharpness.',
      'A grid installed upside down or off-centre is a common and immediately visible error.',
    ],
    numbers: [['SPR', 'can exceed 3:1'], ['Grid ratio', 'height / gap'], ['Alternative', 'air gap']],
  },

  'tech-fluoro': {
    oneLiner: 'One long exposure gives the best signal-to-noise per image; a pulsed low-dose stream gives you motion instead, at a dose penalty per unit of information.',
    analogy: 'A long-exposure photograph versus a video. The photo is sharper and cleaner; the video shows you what moved.',
    watchFor: 'The single sustained exposure versus the repeating pulse train, and the different beam-on patterns each produces.',
    how: [
      'Radiography fires one exposure with enough photons to produce a low-noise image.',
      'Fluoroscopy instead fires many short low-dose pulses per second.',
      'Each pulse produces a noisy frame.',
      'Displaying them in sequence shows motion.',
      'Frame averaging and last-image-hold recover some quality without more dose.',
    ],
    physics: [
      'Image noise scales as the inverse square root of the photon count, so low-dose frames are inherently noisier.',
      'Pulsed fluoroscopy dose scales almost linearly with frame rate — halving the rate halves the dose.',
      'Total information per unit dose is worse for fluoroscopy; you are buying time resolution with it.',
    ],
    engineering: [
      'Grid-controlled tubes make clean microsecond pulses possible without switching the high voltage.',
      'Last-image-hold and frame averaging cut dose without losing the information that matters.',
      'In NDT, real-time radioscopy is used for in-line inspection where throughput beats ultimate sensitivity.',
    ],
    practice: [
      'Cumulative fluoroscopy time is a regulated, logged quantity in both medicine and industry.',
      'Dropping the pulse rate is usually the single largest dose saving available to an operator.',
    ],
    numbers: [['Dose scaling', '∝ pulse rate'], ['Noise', '∝ 1/√N'], ['Tool', 'last-image-hold']],
  },

  'tech-mmw': {
    oneLiner: 'Active millimetre-wave imaging reflects off skin and reveals concealed objects without any ionising radiation — which is why it replaced backscatter for personnel screening.',
    analogy: 'Radar for people. It bounces off the surface and never enters the body at all.',
    watchFor: 'The antenna orbiting the subject and the concealed object showing as a reflection difference — the waves never penetrate the body.',
    how: [
      'Antennas transmit millimetre waves at the subject.',
      'The waves reflect at the skin surface and at dielectric discontinuities such as concealed objects.',
      'Antennas around the booth receive the reflections.',
      'The system reconstructs a surface map from amplitude and phase.',
      'Automatic target recognition flags anomalies on a generic avatar.',
    ],
    physics: [
      'Frequencies around 24–30 GHz — non-ionising, with photon energies billions of times below X-ray.',
      'Millimetre waves do not penetrate the body, so there is no internal imaging and no dose whatsoever.',
      'They also cannot see through metal, so it complements rather than replaces X-ray inspection.',
    ],
    engineering: [
      'Zero ionising dose removes the whole justification argument for scanning members of the public.',
      'Automatic target recognition displays a generic avatar instead of any body image.',
      'Throughput and resolution are the main engineering trade-offs at a busy checkpoint.',
    ],
    practice: [
      'It answers "is something concealed on this person?", not "what is inside this bag?".',
      'Privacy concerns drove the ATR requirement, and that requirement is now near-universal.',
    ],
    numbers: [['Frequency', '24–30 GHz'], ['Dose', 'zero (non-ionising)'], ['Sees', 'surface only']],
  },

  'tech-matrix': {
    oneLiner: 'Access, thickness, the question you actually need answered, and throughput — those four constraints pick the modality before any physics argument starts.',
    analogy: 'Choosing a vehicle. You do not start with engine specifications; you start with what you need to carry, how far, and how fast.',
    watchFor: 'Each constraint on the left mapping to a specific technology on the right. The constraint drives the choice, not the other way round.',
    how: [
      'Ask first: can I get to both sides of the object? If not, transmission is out.',
      'Ask second: how thick and how dense? That sets the minimum energy.',
      'Ask third: do I need to know <b>what</b> it is, or only <b>where</b> it is?',
      'Ask fourth: how many objects per hour must pass?',
      'Only then compare the technologies that survive all four filters.',
    ],
    physics: [
      'Two-sided access plus a material question → dual-energy transmission.',
      'One-sided access plus organic contraband → backscatter.',
      'Superposition is the problem → CT, or multi-view if CT is too slow or costly.',
      'Substance identity is the question → XRD or spectral/K-edge methods as a second stage.',
    ],
    engineering: [
      'Most real systems combine two modalities: transmission for speed, a second one for the hard cases.',
      'Element composition at depth calls for neutron interrogation; at the surface, XRF.',
      'Throughput almost always eliminates more options than physics does.',
    ],
    practice: [
      'Specify the question before the equipment — a scanner that answers the wrong question well is still useless.',
      'Every technology in this library exists because it solves a specific limitation of another one.',
    ],
    numbers: [['Filter 1', 'access'], ['Filter 2', 'thickness'], ['Filter 3', 'the question'], ['Filter 4', 'throughput']],
  },
};
