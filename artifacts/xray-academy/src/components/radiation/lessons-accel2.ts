import type { Lesson } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Mini-lessons — cyclotron, synchrotron and Van de Graaff components.
// ═══════════════════════════════════════════════════════════════════════════════

export const ACCEL2_LESSONS: Record<string, Lesson> = {

  // ─── CYCLOTRON ──────────────────────────────────────────────────────────────
  'cy-source': {
    oneLiner: 'Ions are created right at the centre of the magnet gap, so they start circling immediately and every later turn adds energy without any injection line.',
    analogy: 'Dropping a marble into the very centre of a spinning bowl — it starts orbiting straight away rather than being fired in from outside.',
    watchFor: 'The glowing plasma at the centre and green ions peeling off it into small circles.',
    how: [
      'Hydrogen (or deuterium) gas is fed into a small chamber at the machine centre.',
      'An arc discharge of a few hundred volts ionises the gas into a plasma.',
      'Medical machines pull out <b>negative</b> hydrogen ions (H⁻) — a proton with two electrons.',
      'The static magnetic field immediately bends them into a small circle.',
      'Each pass across the dee gap then adds energy and grows the radius.',
    ],
    physics: [
      'The Lorentz force <code>F = qv × B</code> is always perpendicular to the velocity, so it curves the path without changing the speed.',
      'Radius <code>r = mv / (qB)</code> — momentum and radius rise together.',
      'H⁻ is fragile: its second electron is bound by only 0.75 eV, so residual gas can strip it prematurely.',
    ],
    engineering: [
      'Internal Penning (PIG) sources sit in the median plane; external sources inject axially through a spiral inflector.',
      'Source gas load and vacuum quality fight each other — more gas means more beam but more stripping losses.',
      'Cathode erosion makes the source the most frequently serviced component in a hospital cyclotron.',
    ],
    practice: [
      'Source current sets beam current, which sets isotope yield per irradiation.',
      'Falling yield with normal RF and magnet readings usually points at the source, not the accelerator.',
      'Deuterium sources are used where neutron-producing reactions are wanted.',
    ],
    numbers: [['Arc voltage', '300–800 V'], ['Ion species', 'H⁻ (medical)'], ['H⁻ binding', '0.75 eV']],
  },

  'cy-dees': {
    oneLiner: 'Two hollow D-shaped electrodes form a resonator; there is no field inside them, so all the acceleration happens in the gap between the two.',
    analogy: 'Pushing a swing: you only push at the bottom of each pass. Inside the dee the ion simply coasts, waiting for the next push.',
    watchFor: 'The gap highlight flipping colour every half turn, and the ion always crossing when the polarity favours it.',
    how: [
      'RF voltage is applied between the two dees.',
      'Inside a hollow conductor there is no electric field, so the ion coasts along a semicircle.',
      'When it emerges into the gap, the field accelerates it.',
      'By the time it comes round again, the RF has reversed — so it is accelerated again, in the other direction.',
      'Each full turn therefore gives two kicks of <code>q · V_dee</code>.',
    ],
    physics: [
      'Cyclotron frequency <code>f = qB / 2πm</code> is independent of radius and speed — the reason one fixed RF frequency works.',
      'Energy gain per gap crossing is <code>q · V_dee</code>, typically 30–100 keV per crossing.',
      'The dee stems and liner form a quarter-wave resonator; tuning is done with a movable panel or trimmer.',
    ],
    engineering: [
      'Resonant frequency for medical machines is typically 20–100 MHz.',
      'RF power is fed through a coupling loop with a matching network that tracks beam loading.',
      'Dee gap surfaces must be clean and smooth: field concentration at any burr starts sparking.',
    ],
    practice: [
      'Sparking in the dee gap is the classic conditioning problem after a vacuum vent — the machine is run up slowly to recondition.',
      'RF instability shows immediately as beam loss at a specific radius.',
    ],
    numbers: [['Dee voltage', '30–100 kV'], ['RF frequency', '20–100 MHz'], ['Kicks per turn', '2']],
  },

  'cy-sectors': {
    oneLiner: 'Shaping the magnet into alternating strong "hills" and weak "valleys" lets the average field rise with radius — cancelling relativistic slowdown while still holding the beam together vertically.',
    analogy: 'A bobsleigh track with banked corners: the banking is what keeps you on course when you go faster, instead of throwing you off.',
    watchFor: 'The four green wedges are the hills. The ion crosses hill and valley alternately as it circles, and the edge crossings are what focus it.',
    how: [
      'As the ion approaches relativistic speed, its mass increases and its revolution frequency falls.',
      'To keep it in step with a fixed RF, the magnetic field must rise with radius.',
      'But a field that simply rises with radius defocuses the beam vertically — it would spread out and be lost.',
      'Cutting the pole into azimuthal sectors makes the ion cross field edges at an angle on every turn.',
      'Each edge crossing gives a vertical focusing kick that restores stability.',
    ],
    physics: [
      'Isochronism requires <code>B̄(r) ∝ γ(r)</code> so that revolution time stays constant at all radii.',
      'Edge focusing at sector boundaries (Thomas focusing) supplies the vertical restoring force.',
      'Spiralling the sectors adds extra focusing at higher energies where it is needed most.',
    ],
    engineering: [
      'This design is what makes a continuous-beam isochronous cyclotron possible instead of a pulsed synchrocyclotron.',
      'Trim coils fine-tune the field profile after magnetic mapping of the actual iron.',
      'The magnetic map is a per-machine dataset — no two magnets are identical.',
    ],
    practice: [
      'A mis-set trim coil shows up as beam loss at a specific radius — effectively an energy ceiling.',
      'Magnetic mapping is repeated after any major magnet work.',
    ],
    numbers: [['Isochronism', 'B̄(r) ∝ γ(r)'], ['Sectors', 'typically 3–4'], ['Focusing', 'Thomas edge focusing']],
  },

  'cy-stripper': {
    oneLiner: 'Push a negative hydrogen ion through a thin carbon foil, it loses both electrons and becomes a proton — the magnetic force reverses instantly and the beam curves straight out of the machine.',
    analogy: 'A car that suddenly changes from left-hand drive to right-hand drive: the same road bends it the other way, and it exits the roundabout immediately.',
    watchFor: 'The dot changes colour at the foil and its path flips from curving inward to curving outward, straight to the target.',
    how: [
      'H⁻ circulates until it reaches the desired energy radius.',
      'A thin carbon foil is inserted into its path.',
      'The foil strips both electrons; the ion becomes a bare proton (charge +1 instead of −1).',
      'With the charge sign reversed, the Lorentz force now bends it the opposite way.',
      'It leaves the magnetic field along a fixed extraction path to the target.',
    ],
    physics: [
      'Extraction efficiency approaches 100 % — no septum losses, so machine activation stays low.',
      'Foil radial position selects the extracted energy: this is how variable-energy machines work.',
      'Positive-ion machines instead need an electrostatic deflector and accept a few percent beam loss.',
    ],
    engineering: [
      'Foils are a few micrograms per square centimetre of carbon — barely visible.',
      'Two foils on a carousel allow simultaneous dual-target irradiation.',
      'Foil holders are motorised so energy and target can be changed from the console.',
    ],
    practice: [
      'Foils are consumables: they thin, curl and eventually break under beam heating.',
      'A broken foil means no extracted beam even though the internal beam is perfectly healthy.',
      'Low machine activation from clean extraction is a genuine operational advantage during maintenance.',
    ],
    numbers: [['Extraction efficiency', '≈ 100 %'], ['Foil', 'thin carbon'], ['Energy selection', 'by foil radius']],
  },

  'cy-target': {
    oneLiner: 'The extracted protons slam into enriched water inside a small pressurised chamber, transmuting oxygen-18 into fluorine-18 for PET imaging.',
    analogy: 'A tiny alchemy chamber: put one element in, take a different element out — except the change is nuclear, not chemical.',
    watchFor: 'The beam enters the target on the left, then the product travels right through the hot cell to the QC stage.',
    how: [
      'Protons pass through a thin metal window into the target chamber.',
      'The chamber holds enriched [¹⁸O]water under 20–40 bar pressure.',
      'The nuclear reaction <code>¹⁸O(p,n)¹⁸F</code> converts some oxygen into fluorine-18.',
      'A helium push transfers the activated water through shielded tubing to a hot cell.',
      'Automated chemistry makes FDG, which is then purified and quality-controlled before release.',
    ],
    physics: [
      'F-18 has a 109.8 minute half-life — long enough to synthesise and inject, far too short to ship far.',
      'Other routes: <code>¹⁴N(p,α)¹¹C</code> (20.4 min), <code>¹⁶O(p,α)¹³N</code> (10 min), <code>¹⁵N(p,n)¹⁵O</code> (2 min).',
      'Beam current directly sets yield, but target heating limits how much current the window can take.',
    ],
    engineering: [
      'Target windows are Havar or niobium foils that absorb the full beam power.',
      'Pressurisation stops the water boiling under beam heating.',
      'The hot cell is heavily shielded and fully remote — nobody handles the activity directly.',
    ],
    practice: [
      'FDG synthesis, purification and QC take about 30 minutes against a 110-minute half-life — the schedule is tight by design.',
      'Target windows are routine consumables; a window failure contaminates the target chamber.',
      'Short half-life is why hospitals install their own cyclotron rather than buying the tracer.',
    ],
    numbers: [['Reaction', '¹⁸O(p,n)¹⁸F'], ['F-18 half-life', '109.8 min'], ['Target pressure', '20–40 bar']],
  },

  'cy-vacuum': {
    oneLiner: 'Cryopumps keep the chamber below a millionth of atmospheric pressure so the fragile H⁻ survives its journey, while a local shield absorbs the neutrons the reactions produce.',
    analogy: 'A cleanroom with thick walls: keep the inside empty so nothing collides, and keep the outside safe from what escapes.',
    watchFor: 'Red neutron dots streaming outward from the beam region and being absorbed by the surrounding shield layers.',
    how: [
      'Cryopumps freeze residual gas onto cold surfaces, holding pressure below 10⁻⁶ mbar.',
      'Good vacuum stops H⁻ being stripped before it reaches full energy.',
      'Nuclear reactions in the target produce neutrons as a by-product.',
      'Borated polyethylene moderates and absorbs those neutrons close to the source.',
      'Concrete or steel then attenuates the resulting capture gammas.',
    ],
    physics: [
      'Residual gas strips H⁻ prematurely, causing beam loss and localised activation exactly where the loss happens.',
      'Neutrons activate the machine and the vault — access control after shutdown is time-based, not just interlock-based.',
      'Air activation produces ¹³N and ⁴¹Ar, which is why vault ventilation has a controlled delay before release.',
    ],
    engineering: [
      'Self-shielded cyclotrons let a hospital install one without building a thick concrete bunker.',
      'Cryopump regeneration is scheduled maintenance — it takes the machine out of service.',
      'Shield design is a neutron problem first and a gamma problem second.',
    ],
    practice: [
      'A cool-down wait before maintenance is dictated by short-lived activation products, and it is not negotiable.',
      'Rising vacuum pressure predicts falling beam current before the beam itself is obviously bad.',
      'Activation surveys are part of routine service planning, not an afterthought.',
    ],
    numbers: [['Vacuum', '< 10⁻⁶ mbar'], ['Shield', 'borated PE + concrete'], ['Air activation', '¹³N, ⁴¹Ar']],
  },

  // ─── SYNCHROTRON ────────────────────────────────────────────────────────────
  'sy-dipole': {
    oneLiner: 'Dipole magnets steer the beam around the ring, and because a bent relativistic electron must radiate, every bend is also a free X-ray source.',
    analogy: 'A car on a banked curve throwing water off its tyres tangentially — the water leaves along the direction of travel, not sideways.',
    watchFor: 'The radiation fan leaves tangentially at the bend, not radially. That tangent direction is where the beamline is built.',
    how: [
      'A uniform vertical magnetic field bends the electron beam horizontally.',
      'Acceleration (change of direction) forces the electron to radiate energy.',
      'Because the electron is highly relativistic, that radiation is squeezed into a narrow forward cone.',
      'The cone sweeps as the electron traverses the magnet, painting a wide horizontal fan.',
      'A beamline port placed on that tangent collects the fan as a white X-ray beam.',
    ],
    physics: [
      'Cone opening angle is approximately <code>1/γ</code> — about 0.17 mrad at 3 GeV.',
      'Radiated power scales as <code>E⁴ / ρ²</code>, which is why electrons radiate strongly and protons barely do.',
      'Critical energy <code>E_c ∝ E³/ρ</code> sets where the continuous spectrum rolls off.',
    ],
    engineering: [
      'Bending radius and beam energy together fix the critical photon energy available to users.',
      'Superbends use superconducting dipoles to push critical energy higher in an existing ring.',
      'Dipole field stability translates directly into orbit stability at the experiment.',
    ],
    practice: [
      'The lost energy must be replaced every turn by the RF cavities — the dipoles are why the RF exists.',
      'Orbit feedback systems correct micron-level drifts caused by thermal and ground motion.',
    ],
    numbers: [['Cone angle', '≈ 1/γ'], ['Power', '∝ E⁴/ρ²'], ['γ at 3 GeV', '≈ 5 870']],
  },

  'sy-quad': {
    oneLiner: 'A quadrupole focuses the beam in one plane and defocuses it in the other, so they are alternated around the ring to produce net focusing in both.',
    analogy: 'A series of alternating lenses in a long tube: individually each one is wrong in one direction, but the sequence keeps the light collimated.',
    watchFor: 'The beam envelope pinching at the F magnets and bulging at the D magnets, staying bounded overall.',
    how: [
      'A quadrupole field is zero on axis and grows linearly outward.',
      'A particle off-axis horizontally is pushed back toward the axis; one off-axis vertically is pushed away.',
      'The next quadrupole is rotated 90°, reversing the roles.',
      'A particle that was defocused arrives further from the axis, so the next magnet\'s stronger kick focuses it more.',
      'The net effect over a repeating focus–drift–defocus–drift (FODO) cell is focusing in both planes.',
    ],
    physics: [
      'Strong focusing (Courant–Snyder, 1952) is what made small-aperture, high-energy rings possible at all.',
      'Beta functions describe the envelope; low beta at an insertion device means a small, bright source point.',
      'Emittance — the phase-space area — ultimately sets brightness, and modern rings chase ultra-low emittance.',
    ],
    engineering: [
      'Multi-bend achromat lattices trade many weaker dipoles for far lower emittance in fourth-generation rings.',
      'Sextupoles are added to correct chromaticity — the energy dependence of the focusing strength.',
      'Magnet alignment tolerances are tens of micrometres over hundreds of metres.',
    ],
    practice: [
      'A single mis-set quadrupole distorts the whole ring optics, not just the local region.',
      'Beam-based alignment uses the beam itself to find each magnet\'s true magnetic centre.',
    ],
    numbers: [['Principle', 'strong focusing'], ['Cell', 'FODO'], ['Published', 'Courant & Snyder 1952']],
  },

  'sy-rf': {
    oneLiner: 'RF cavities replace the energy the beam radiates away on every turn, and in doing so they also force the beam into discrete bunches — which is why synchrotron light arrives as a pulse train.',
    analogy: 'A metronome that both keeps the orchestra in time and tops up its energy each beat.',
    watchFor: 'Evenly spaced bunches travelling around the ring — not a continuous stream. That spacing is the pulse structure users exploit.',
    how: [
      'A cavity oscillating at around 500 MHz presents an accelerating field only during part of each cycle.',
      'Only particles arriving in that window gain energy; others lose or gain less.',
      'A particle arriving early gets less energy, circulates slightly differently and arrives later next time.',
      'This self-correction (phase stability) gathers particles into stable bunches.',
      'The bunch spacing is set by the RF period — nanoseconds.',
    ],
    physics: [
      'Synchrotron oscillation is the longitudinal restoring motion around the synchronous phase.',
      'Higher-harmonic cavities lengthen the bunch to fight Touschek scattering and extend beam lifetime.',
      'Filling patterns (uniform, hybrid, single-bunch) are chosen for the timing experiments that need them.',
    ],
    engineering: [
      'Superconducting cavities reduce wall losses and allow higher accelerating voltage.',
      'Cavity higher-order modes must be damped or they drive beam instabilities.',
      'RF amplitude and phase stability directly limit beam stability at the experiments.',
    ],
    practice: [
      'The pulse structure enables time-resolved and pump–probe experiments — it is a feature, not a side effect.',
      'Top-up injection keeps stored current essentially constant so the thermal load on optics never changes.',
    ],
    numbers: [['Cavity frequency', '≈ 500 MHz'], ['Bunch spacing', 'nanoseconds'], ['Function', 'replace radiated energy']],
  },

  'sy-undulator': {
    oneLiner: 'A row of alternating magnets makes the beam wiggle; if the wiggles are gentle enough, light from every period interferes constructively and the output collapses into narrow, extremely bright harmonics.',
    analogy: 'A single hand clap versus a stadium clapping in unison. Same total effort, vastly more concentrated result.',
    watchFor: 'Switch between the large-amplitude wiggler path and the gentle undulator path. Small wiggles, coherent addition; large wiggles, incoherent flux.',
    how: [
      'Permanent magnets alternate polarity every few centimetres along the beam path.',
      'The electron beam weaves gently through this array.',
      'Each weave radiates a small burst of light in the forward direction.',
      'If the wiggle amplitude is small, all the bursts arrive in phase with each other.',
      'Constructive interference concentrates the output into narrow harmonics instead of a broad continuum.',
    ],
    physics: [
      'The deflection parameter K separates the regimes: <code>K ≲ 1</code> is an undulator, <code>K ≫ 1</code> a wiggler.',
      'Undulator wavelength: <code>λ = (λ_u/2γ²)(1 + K²/2 + γ²θ²)</code>.',
      'Brightness gain is around 10⁴ over a bending magnet; a wiggler gains about 10².',
    ],
    engineering: [
      'Closing the magnet gap raises K and shifts the harmonics — that is how users tune photon energy.',
      'In-vacuum and cryogenic undulators shrink the gap further for harder photons.',
      'Gap motion is a routine user-controlled parameter during an experiment.',
    ],
    practice: [
      'Wigglers are preferred when raw flux over a broad band matters more than brightness.',
      'Undulator harmonics must be filtered or the higher orders contaminate the measurement.',
    ],
    numbers: [['Undulator', 'K ≲ 1'], ['Wiggler', 'K ≫ 1'], ['Brightness gain', '≈ 10⁴ ×']],
  },

  'sy-mono': {
    oneLiner: 'Two parallel silicon crystals pick one wavelength out of the white beam by Bragg diffraction, and return the beam parallel to where it came from so the sample never has to move.',
    analogy: 'A pair of mirrors angled to pick one colour out of a rainbow and send it on in the original direction.',
    watchFor: 'As the crystal angle changes, the selected energy changes — but the outgoing beam stays horizontal and at the same height.',
    how: [
      'The white beam strikes the first crystal at angle θ.',
      'Only the wavelength satisfying the Bragg condition reflects; everything else passes through or is absorbed.',
      'The second crystal, parallel to the first, reflects that beam back to the original direction.',
      'Rotating both crystals together scans the photon energy.',
      'Translating the second crystal keeps the exit height fixed while the angle changes.',
    ],
    physics: [
      'Bragg condition: <code>nλ = 2 d sin θ</code>, with d the crystal plane spacing.',
      'Si(111) gives about 10⁻⁴ energy resolution; Si(311) is finer but passes less flux.',
      'Energy scanning across an absorption edge is exactly what XAFS spectroscopy requires.',
    ],
    engineering: [
      'The first crystal absorbs kilowatts of white beam — cryogenic cooling with liquid nitrogen is standard.',
      'Fixed-exit geometry keeps the beam height constant while the energy is scanned.',
      'Angular stability at the microradian level is required for stable flux.',
    ],
    practice: [
      'Thermal deformation of the first crystal ("thermal bump") degrades flux and beam shape at high power.',
      'Higher harmonics are rejected by detuning the second crystal slightly or by a mirror.',
    ],
    numbers: [['Bragg law', 'nλ = 2d sin θ'], ['Si(111) resolution', '≈ 10⁻⁴'], ['Cooling', 'cryogenic LN₂']],
  },

  'sy-detector': {
    oneLiner: 'The sample sits in the focus and is rotated while area detectors record transmission, diffraction and fluorescence — building a full data set rather than a single picture.',
    analogy: 'Photographing a sculpture from every angle to build a 3-D model instead of settling for one photo.',
    watchFor: 'The sample rotating and the pixel detector lighting up in changing patterns — each rotation angle is one data frame.',
    how: [
      'Monochromatic (or white) beam illuminates a small volume of the sample.',
      'Photons are transmitted, diffracted or absorbed and re-emitted as fluorescence.',
      'A pixel array detector records a full 2-D frame in milliseconds.',
      'The sample is rotated and the process repeated hundreds or thousands of times.',
      'Reconstruction turns that stack into a tomogram, a diffraction map or an elemental map.',
    ],
    physics: [
      'Phase-contrast imaging exploits refraction, revealing soft-tissue and composite detail that attenuation misses.',
      'Diffraction imaging separates crystalline explosives from inert powders with identical attenuation.',
      'XAFS at an absorption edge gives oxidation state and local coordination of a specific element.',
    ],
    engineering: [
      'Photon-counting pixel detectors run at kilohertz frame rates with essentially no read noise.',
      'Sample stages need sub-micrometre sphere of confusion so the rotation axis stays put.',
      'Data rates reach terabytes per experiment — storage and reconstruction are real constraints.',
    ],
    practice: [
      'Micro-CT of heritage objects reaches sub-micrometre voxels without sampling the artefact.',
      'Radiation damage to the sample is a real limit for biological and polymer specimens.',
    ],
    numbers: [['Frame rate', 'kHz'], ['Read noise', '≈ zero'], ['Voxel size', 'sub-micrometre']],
  },

  // ─── VAN DE GRAAFF ──────────────────────────────────────────────────────────
  'vd-corona': {
    oneLiner: 'A sharp electrode ionises the gas around its tip and sprays charge onto a moving belt, which then carries that charge mechanically up to the terminal.',
    analogy: 'A conveyor belt in a warehouse: it does not push the boxes electrically, it just physically carries them uphill.',
    watchFor: 'Plus signs being sprayed onto the belt at the bottom and riding upward — the transport is mechanical, not electrical.',
    how: [
      'A needle electrode is held at 20–30 kV near the bottom pulley.',
      'The intense field at the sharp tip ionises the surrounding gas.',
      'Ions land on the insulating belt surface and stick there.',
      'The belt carries them upward into the terminal.',
      'A collector comb inside the terminal removes the charge and passes it to the sphere.',
    ],
    physics: [
      'Field concentration at a sharp tip is what starts the discharge — geometry, not voltage alone.',
      'Spray current sets the charging current and therefore how fast the terminal recovers under beam load.',
      'Corona is also the main parasitic loss mechanism, which is why the tank is pressurised.',
    ],
    engineering: [
      'Pelletron machines replace the rubber belt with a chain of metal pellets separated by insulators.',
      'Pellet chains are quieter, cleaner and last far longer than a rubber belt.',
      'A second corona assembly at the terminal can regulate the voltage downward on demand.',
    ],
    practice: [
      'Belt dust and wear products contaminate the tank and degrade insulation over time.',
      'Ozone and gas breakdown products are why SF₆ handling procedures exist.',
      'Charging current is measured and trended — it is the first indicator of belt or corona problems.',
    ],
    numbers: [['Corona voltage', '20–30 kV'], ['Transport', 'mechanical'], ['Alternative', 'Pelletron chain']],
  },

  'vd-terminal': {
    oneLiner: 'Charge delivered inside a hollow conductor migrates to its outside surface, so you can keep adding charge indefinitely without ever fighting the voltage already there.',
    analogy: 'Filling a bucket from a pipe that ends inside it — you never have to lift the water over the rim.',
    watchFor: 'Plus signs accumulating on the outside of the sphere while the voltage figure climbs.',
    how: [
      'The belt delivers charge to a comb inside the hollow terminal.',
      'Because the interior of a conductor has no field, the charge immediately moves to the outer surface.',
      'The delivering comb therefore never has to work against the terminal potential.',
      'The terminal voltage rises steadily as charge accumulates.',
      'It stabilises when leakage plus beam load equals the charging current.',
    ],
    physics: [
      '<code>V = Q / C</code> — voltage rises with accumulated charge on a fixed capacitance.',
      'Electrostatic shielding (no field inside a conductor) is the property that makes the whole machine work.',
      'A generating voltmeter measures the terminal potential without touching it.',
    ],
    engineering: [
      'The terminal houses the ion source (single-ended) or the stripper (tandem) and is serviced by opening the tank.',
      'Sphere surface finish matters: a scratch is a field concentration and a flashover site.',
      'Terminal voltage is the machine\'s primary control parameter, regulated by corona feedback.',
    ],
    practice: [
      'Terminal work means venting and re-filling the SF₆ tank — half a day of gas handling.',
      'A drifting terminal voltage under constant load usually means changing leakage, not changing charging.',
    ],
    numbers: [['Relation', 'V = Q / C'], ['Typical range', '0.5–25 MV'], ['Measurement', 'generating voltmeter']],
  },

  'vd-column': {
    oneLiner: 'The accelerating column is a stack of insulator rings with metal electrodes between them, held at evenly spaced voltages so the electric stress never concentrates anywhere.',
    analogy: 'A ladder with evenly spaced rungs. Remove one rung and the gap becomes twice as hard to cross — that is where it breaks.',
    watchFor: 'The evenly spaced grading rings. When a flashover occurs, watch how it starts at the point where the gradient is disturbed.',
    how: [
      'The column spans from the terminal down to ground potential.',
      'It is built as alternating insulator sections and metal grading rings.',
      'A resistor chain connects the rings, forcing each to sit at a defined fraction of the terminal voltage.',
      'The result is a uniform voltage gradient along the whole column.',
      'The ion travels down that gradient, gaining energy continuously rather than in discrete kicks.',
    ],
    physics: [
      'A uniform gradient prevents local breakdown along the column surface.',
      'The equipotential rings also shape the field into weak lenses that focus the beam at each gap.',
      'Total energy gain equals the charge times the total terminal voltage, regardless of how many sections.',
    ],
    engineering: [
      'Corona rings at the ends manage the highest-stress region near the terminal.',
      'Resistor values are matched to keep the chain current well above the beam current.',
      'Column insulators are ceramic or epoxy-glass, bonded to metal rings in a vacuum-tight stack.',
    ],
    practice: [
      'A single failed resistor distorts the gradient and usually triggers repeated sparking at that section.',
      'Sparking damage is cumulative: each flashover roughens the surface and lowers the next breakdown voltage.',
      'Trending the maximum stable terminal voltage over months is the standard column health check.',
    ],
    numbers: [['Function', 'uniform gradient'], ['Elements', 'insulator + grading rings'], ['Failure sign', 'repeated sparking']],
  },

  'vd-stripper': {
    oneLiner: 'At the terminal the negative ion is stripped of electrons, becoming positive — so the same voltage that attracted it now repels it, and the machine gets a second acceleration for free.',
    analogy: 'Riding a magnet down a slope, flipping it over at the bottom, and having the same magnet push you up the other side.',
    watchFor: 'The particle changing colour and label at the terminal, and continuing to gain energy on the second half instead of losing it.',
    how: [
      'Negative ions are produced at ground potential and attracted up to the positive terminal.',
      'They gain energy <code>q·V</code> on the way up.',
      'At the terminal they pass through a thin carbon foil or a gas canal.',
      'Collisions strip off electrons, leaving a positive ion of charge state q.',
      'Now repelled by the positive terminal, they accelerate again all the way back to ground potential.',
    ],
    physics: [
      'Final energy is <code>(1 + q) × V</code>, where q is the charge state after stripping.',
      'Charge-state distribution is statistical — an analysing magnet downstream selects the wanted one.',
      'A 10 MV terminal can therefore deliver 50+ MeV heavy ions.',
    ],
    engineering: [
      'Gas strippers give lower charge states but far longer life; foils give higher q and higher final energy.',
      'Foil thickness is a compromise between stripping efficiency and energy straggling.',
      'Foil carousels allow remote replacement without opening the tank.',
    ],
    practice: [
      'Foil breakage is a routine maintenance event on a busy AMS machine.',
      'The tandem trick is the whole reason these machines dominate accelerator mass spectrometry.',
      'Beam energy calibration depends on knowing exactly which charge state was selected.',
    ],
    numbers: [['Final energy', '(1 + q) × V'], ['Stripper', 'C foil or gas'], ['Example', '10 MV → 50+ MeV']],
  },

  'vd-tank': {
    oneLiner: 'Air breaks down at about 3 MV per metre, so the whole column is sealed inside a vessel of sulphur hexafluoride at 5–10 bar, which withstands several times more.',
    analogy: 'Diving equipment for electricity: the machine cannot survive in ordinary air, so you give it a pressurised atmosphere it can work in.',
    watchFor: 'The SF₆ molecules filling the space around the terminal — that gas is doing the insulating work, not empty space.',
    how: [
      'The terminal and column are enclosed in a steel pressure vessel.',
      'The vessel is evacuated and then filled with SF₆ to 5–10 bar.',
      'SF₆ molecules capture free electrons very efficiently, stopping avalanches before they start.',
      'This raises the breakdown field several-fold compared with air.',
      'Terminal voltages up to about 25 MV become possible in a practical-sized tank.',
    ],
    physics: [
      'Air breaks down near 3 MV/m; SF₆ at 5–10 bar pushes the limit to roughly 25 MV terminals.',
      'SF₆ is electronegative — it captures electrons, which is exactly what suppresses avalanche breakdown.',
      'Moisture control matters as much as pressure: wet gas breaks down far sooner.',
    ],
    engineering: [
      'Tank opening for terminal service is a half-day job dominated by gas handling.',
      'SF₆ is recovered, filtered and reused — it is never simply vented.',
      'Breakdown products after a spark are corrosive and toxic, and are removed by filtration.',
    ],
    practice: [
      'SF₆ is a potent greenhouse gas — recovery and recycling during tank opening is mandatory.',
      'Gas moisture content is monitored; a rising dew point predicts sparking before it happens.',
      'Personnel entry into a vented tank requires oxygen monitoring: SF₆ is heavier than air and pools.',
    ],
    numbers: [['Air breakdown', '≈ 3 MV/m'], ['SF₆ pressure', '5–10 bar'], ['Terminal ceiling', '≈ 25 MV']],
  },
};
