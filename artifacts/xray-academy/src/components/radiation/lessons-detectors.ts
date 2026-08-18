import type { Lesson } from './anim-gallery';

// ═══════════════════════════════════════════════════════════════════════════════
// Mini-lessons — detector technology: how radiation is received and measured.
// ═══════════════════════════════════════════════════════════════════════════════

export const DETECTOR_LESSONS: Record<string, Lesson> = {

  'det-chain': {
    oneLiner: 'Every radiation detector ever built runs the same five stages — interact, convert, collect, amplify, digitise. Only the physics of the first two stages differs between technologies.',
    analogy: 'A microphone, a guitar pickup and a seismometer all do the same thing: turn a physical disturbance into a voltage, then into a number. Only the first step differs.',
    watchFor: 'The highlighted stage advancing along the chain while the pulse below grows toward a final digital value.',
    how: [
      '<b>Interact</b> — the photon or particle must actually deposit energy in the sensitive volume.',
      '<b>Convert</b> — that energy becomes visible light (scintillator) or free charge (gas or semiconductor).',
      '<b>Collect</b> — an electric field sweeps the charge to an electrode, or optics guide the light to a photodetector.',
      '<b>Amplify</b> — gas multiplication, a dynode chain, an avalanche, or a low-noise charge amplifier.',
      '<b>Digitise</b> — shaping, sampling and an ADC turn the pulse into a count or an intensity value.',
    ],
    physics: [
      'A photon that passes through without interacting is completely invisible — efficiency is stage one.',
      'How much signal you get per keV is set at stage two, and it determines the best energy resolution possible.',
      'Everything after stage two can only preserve or degrade what stages one and two produced.',
    ],
    engineering: [
      'Understanding which stage limits a given detector tells you what can and cannot be improved.',
      'A noisy amplifier can be replaced; a low interaction probability can only be fixed with more material.',
      'Integrating detectors (imaging) skip pulse counting and read accumulated charge per frame instead.',
    ],
    practice: [
      'When a detector under-performs, diagnose by stage: is it catching photons, converting them, or just reading them badly?',
      'Comparisons between detectors are only fair if you specify which stage you are comparing.',
    ],
    numbers: [['Stages', '5'], ['Stage 1', 'sets efficiency'], ['Stage 2', 'sets resolution']],
  },

  'det-interaction': {
    oneLiner: 'A detected photon must undergo photoelectric absorption, Compton scattering or pair production inside the sensitive volume — anything else and the photon is simply lost.',
    analogy: 'A fishing net: only fish that actually hit the net are caught. Mesh size and net area decide the catch, not how good your boat is.',
    watchFor: 'The three interaction types cycling. Notice that only photoelectric absorption deposits the full energy.',
    how: [
      'A photon enters the sensitive volume.',
      'Photoelectric absorption: the photon is completely absorbed and its full energy is deposited.',
      'Compton scattering: part of the energy is transferred to an electron and the photon continues, often escaping.',
      'Pair production: above 1.022 MeV the photon converts into an electron-positron pair.',
      'If none of these happens, the photon passes through unrecorded.',
    ],
    physics: [
      'Photoelectric absorption dominates at low energy and high Z — ideal for spectroscopy because it gives full-energy deposition.',
      'Compton scattering creates the Compton continuum and edge visible in every gamma spectrum.',
      'Pair production adds escape peaks at 511 keV intervals below the full-energy peak.',
    ],
    engineering: [
      'Detection efficiency = probability of interacting at all; energy resolution = how cleanly it is measured.',
      'This is why high-Z, high-density scintillators dominate gamma work and silicon dominates low-energy work.',
      'Detector thickness trades efficiency against cost, resolution and readout complexity.',
    ],
    practice: [
      'A "peak" in a spectrum is the full-energy peak; the continuum below it is real physics, not noise.',
      'Choosing a detector starts with the energy range you actually need to measure.',
    ],
    numbers: [['Photoelectric', 'full energy'], ['Compton', 'partial'], ['Pair production', '> 1.022 MeV']],
  },

  'det-ionchamber': {
    oneLiner: 'Radiation ionises the fill gas and a modest field collects the ion pairs before they recombine — no internal gain, so the current is directly proportional to dose rate.',
    analogy: 'Collecting rainwater in a bucket. You measure exactly what fell — no amplification, no exaggeration, and it never overflows in a downpour.',
    watchFor: 'Ion pairs separating and drifting to opposite electrodes. Note that no avalanche occurs — what is created is what is collected.',
    how: [
      'Radiation passing through the gas creates ion pairs (a free electron and a positive ion).',
      'A voltage across the chamber creates a field.',
      'Electrons drift to the anode, positive ions to the cathode.',
      'The field is strong enough to prevent recombination but too weak to cause multiplication.',
      'The resulting current is measured directly by an electrometer.',
    ],
    physics: [
      'It operates in the saturation region: enough field to collect everything, not enough to multiply anything.',
      'Roughly 30 eV of deposited energy produces one ion pair in air.',
      'Output current is small (picoamps) but it never saturates in an intense field — the key advantage.',
    ],
    engineering: [
      'Needs a good electrometer because the signal is genuinely tiny.',
      'Sealed, temperature- and pressure-compensated chambers are the reference for beam dosimetry.',
      'Transmission chambers in a LINAC head are ion chambers monitoring dose in real time.',
    ],
    practice: [
      'This is why ion chambers, not GM tubes, are trusted for high dose-rate radiography surveys.',
      'Slow response makes them poor for finding a hidden source but ideal for measuring a known field.',
      'Calibration is traceable and energy-dependent — check the chamber suits the energy in use.',
    ],
    numbers: [['Region', 'saturation'], ['Gain', 'none (×1)'], ['Air W-value', '≈ 34 eV / ion pair']],
  },

  'det-proportional': {
    oneLiner: 'Raise the field near a thin anode wire and each primary electron triggers an avalanche — thousands of times more charge, but still proportional to the energy deposited.',
    analogy: 'A snowball rolling downhill. It grows enormously, but a bigger starting snowball still ends up bigger — the proportion survives.',
    watchFor: 'A single primary electron reaching the wire and multiplying into a cloud, producing a clean measurable pulse.',
    how: [
      'Radiation creates primary ion pairs in the gas, exactly as in an ion chamber.',
      'The electrons drift toward a very thin anode wire.',
      'Near the wire the field becomes extremely intense because of the small radius.',
      'Each electron gains enough energy between collisions to ionise further atoms — an avalanche.',
      'The total charge is thousands of times the original, but still proportional to it.',
    ],
    physics: [
      'Gas gain of 10³–10⁵ makes single-photon counting practical while keeping energy information.',
      'The avalanche happens within a few wire radii, so the geometry does the amplification, not the electronics.',
      'Proportionality holds only while space charge from the avalanche stays small.',
    ],
    engineering: [
      'This is the working principle of the He-3 and B-10 neutron tubes used in portal monitors.',
      'Gas purity matters: electronegative contaminants capture electrons and destroy the proportionality.',
      'Wire diameter and tension are precision parameters — a sagging wire changes the gain along its length.',
    ],
    practice: [
      'Push the voltage further and proportionality is lost — that is the Geiger region.',
      'Gain depends steeply on high voltage, so supply stability directly becomes energy-resolution stability.',
    ],
    numbers: [['Gas gain', '10³–10⁵'], ['Region', 'proportional'], ['Use', 'neutron tubes, X-ray counting']],
  },

  'det-gm': {
    oneLiner: 'At high enough voltage one ionisation triggers a discharge along the whole anode wire — every event gives the same big pulse, which makes counting easy and spectroscopy impossible.',
    analogy: 'A doorbell. It tells you someone is there, but not who, and it needs a moment before it can ring again.',
    watchFor: 'The full-length discharge after a single interaction, then the dead period where further radiation produces nothing at all.',
    how: [
      'Radiation creates at least one ion pair in the gas.',
      'The very high field causes a full avalanche that propagates along the entire anode.',
      'The output pulse is large and always the same size, whatever caused it.',
      'A quench gas absorbs the UV photons that would restart the discharge.',
      'For 50–300 µs afterwards the tube cannot respond to anything.',
    ],
    physics: [
      'Output pulse is independent of photon energy — a GM tube counts, it does not measure spectra.',
      'Dead time means a GM tube reads <b>low</b> in an intense field, which is the dangerous failure mode.',
      'True count rate correction: <code>m = n/(1 + nτ)</code>, but at very high rates the tube can go silent entirely.',
    ],
    engineering: [
      'A quench gas (halogen or organic) stops the discharge so the tube can recover.',
      'Organic quench gases are consumed and give the tube a finite lifetime; halogen ones self-heal.',
      'Cheap, rugged and audible — still the right tool for contamination hunting and general area survey.',
    ],
    practice: [
      'For radiography surveys near a projector, use an ion chamber, not just a GM survey meter.',
      'If a GM meter suddenly reads low as you approach a source, back away immediately — that is saturation, not safety.',
      'The audible click rate is genuinely useful for locating contamination quickly.',
    ],
    numbers: [['Pulse', 'always the same size'], ['Dead time', '50–300 µs'], ['Risk', 'reads low when saturated']],
  },

  'det-pmt': {
    oneLiner: 'Scintillation light releases a single photoelectron, and a chain of dynodes multiplies it by a factor of a million — the closest thing to noise-free amplification in physics.',
    analogy: 'A rumour spreading: one person tells four, each of those tells four, and after ten rounds a million people know.',
    watchFor: 'The number of electrons multiplying at each dynode stage. Watch the running gain figure climb by roughly a factor of four each time.',
    how: [
      'A scintillator converts the radiation into a flash of visible light.',
      'That light strikes a photocathode, releasing a single photoelectron.',
      'An electric field accelerates it onto the first dynode.',
      'The impact releases three to five secondary electrons, which are accelerated to the next dynode.',
      'After 8–12 stages the original single electron has become millions, collected at the anode.',
    ],
    physics: [
      'Gain <code>G = δⁿ</code> where δ ≈ 4 is the secondary yield and n is the number of dynodes — 10⁶ or more.',
      'The first amplification stage is essentially noise-free, which is why a PMT can register a single photon.',
      'Gain depends steeply on high voltage, so supply stability directly becomes energy-resolution stability.',
    ],
    engineering: [
      'Bulky, fragile and useless in a magnetic field, which is why SiPMs are displacing it.',
      'Still the reference for NaI(Tl) spectroscopy and large-area plastic scintillator panels.',
      'The dynode chain is biased by a resistor divider; divider current must exceed the signal current.',
    ],
    practice: [
      'Gain drift with temperature and HV is corrected by periodic gain stabilisation against a known peak.',
      'Exposing a powered PMT to room light destroys it — light-tight discipline is absolute.',
      'A cracked light guide or aged optical coupling looks exactly like a failing PMT.',
    ],
    numbers: [['Gain', '10⁶–10⁷'], ['Dynodes', '8–12'], ['Secondary yield δ', '≈ 4']],
  },

  'det-nai': {
    oneLiner: 'Thallium-doped sodium iodide converts about 38 photons of visible light per keV deposited, so the pulse height is proportional to energy and the histogram is a gamma spectrum.',
    analogy: 'A bell that rings louder when hit harder. Recording how loud each ring was tells you how hard each strike was.',
    watchFor: 'The photopeak on the right and the broad Compton continuum below it — both are real physics, not noise.',
    how: [
      'A gamma ray interacts in the crystal and deposits energy.',
      'That energy excites the doped lattice, which relaxes by emitting visible light.',
      'The number of light photons is proportional to the energy deposited.',
      'A PMT converts that light burst into a charge pulse of proportional height.',
      'Histogramming pulse heights over many events produces the energy spectrum.',
    ],
    physics: [
      'About 38 000 photons per MeV — the highest light yield of the common inorganic scintillators.',
      'Energy resolution around 6–7 % at 662 keV — enough to identify common isotopes.',
      'The spectrum shows a photopeak plus a Compton continuum and edge, because not every interaction deposits everything.',
    ],
    engineering: [
      'High density and high Z give excellent gamma detection efficiency for the price.',
      'Hygroscopic: the crystal must be hermetically sealed or it fogs and dies.',
      'For high resolution, HPGe replaces it; for cost and ruggedness, NaI still wins.',
    ],
    practice: [
      'Peak position drifts with temperature — gain stabilisation against a reference peak is standard practice.',
      'A yellowed or cracked crystal (moisture ingress) shows as a broadened, shifted photopeak.',
      'Isotope identification software depends entirely on the calibration being current.',
    ],
    numbers: [['Light yield', '≈ 38 photons/keV'], ['Resolution @662 keV', '6–7 %'], ['Weakness', 'hygroscopic']],
  },

  'det-sipm': {
    oneLiner: 'Thousands of tiny avalanche cells run in Geiger mode in parallel; each fired cell contributes a fixed charge, so the total output counts how many light photons arrived.',
    analogy: 'A wall of mousetraps. Each one snaps identically, so counting the sprung traps tells you how many mice arrived.',
    watchFor: 'Individual cells lighting up one by one. The output is proportional to how many fired, not to how hard each was hit.',
    how: [
      'Scintillation light falls on an array of microscopic avalanche photodiodes.',
      'Each cell is biased above breakdown, so any photon triggers a full avalanche.',
      'Every fired cell delivers the same fixed charge, regardless of how many photons hit it.',
      'A quench resistor stops the avalanche and resets that cell.',
      'The summed output from all cells is proportional to the number of photons detected.',
    ],
    physics: [
      'Comparable gain to a PMT (10⁵–10⁶) at a few tens of volts instead of a kilovolt.',
      'Saturates when photon count approaches cell count — the response is inherently non-linear at the top.',
      'Dark count rate and temperature-dependent gain are the main design headaches.',
    ],
    engineering: [
      'Immune to magnetic fields, physically tiny, and mechanically rugged.',
      'Bias voltage must be temperature-compensated or the gain drifts noticeably.',
      'Cell count and cell size trade dynamic range against fill factor and efficiency.',
    ],
    practice: [
      'Now standard in PET, handheld spectrometers and new-generation portal monitors.',
      'Saturation correction is required if the light output can approach the cell count.',
      'Dark counts set the practical low-energy threshold, especially at room temperature.',
    ],
    numbers: [['Gain', '10⁵–10⁶'], ['Bias', 'tens of volts'], ['Limit', 'cell-count saturation']],
  },

  'det-photodiode': {
    oneLiner: 'A small scintillator crystal glued to a silicon photodiode, read as a current rather than counted as pulses — the workhorse element of every line-scan imaging array.',
    analogy: 'A light meter rather than a photon counter: it tells you how bright, not how many.',
    watchFor: 'Light produced in the scintillator being captured by the photodiode directly beneath, with the septa preventing it spreading sideways.',
    how: [
      'X-rays are absorbed in a small scintillator crystal.',
      'The crystal emits visible light in proportion to the energy absorbed.',
      'Reflective septa around each crystal keep that light within its own element.',
      'A silicon photodiode below converts the light into current.',
      'That current is integrated over the line period to give one pixel value.',
    ],
    physics: [
      'It integrates rather than counts, so it cannot separate photon energies — but it handles enormous flux.',
      'Scintillator choice sets the stopping power: CsI(Tl) for tube energies, CdWO₄ or ceramic GOS for MeV cargo.',
      'Linear over a huge dynamic range, which is why one exposure can cover thick and thin regions.',
    ],
    engineering: [
      'Optical isolation between elements is what stops cross-talk blurring the image.',
      'Dark current drifts with temperature, so an offset (dark) calibration runs regularly.',
      'Cheap and easy to tile into arrays of thousands of elements.',
    ],
    practice: [
      'Element-to-element gain variation is corrected by the gain calibration — skip it and you get vertical striping.',
      'A cracked crystal or delaminated coupling shows as a permanently low channel.',
    ],
    numbers: [['Mode', 'integrating'], ['Scintillators', 'CsI, CdWO₄, GOS'], ['Key detail', 'optical septa']],
  },

  'det-dab': {
    oneLiner: 'The Detector Array Board is the field-replaceable unit of a cargo array — a row of scintillator-photodiode channels with their own digitising electronics, power supply and single data port, on one card that a service engineer can swap in minutes.',
    analogy: 'A strip of camera sensor with its own brain and power supply. Two connectors and four captive screws, and that slice of the image is in your hand.',
    watchFor: 'The healthy board reads every channel; then a dead band appears where one section failed — a contiguous stripe, not scattered noise. That shape is the whole diagnosis.',
    how: [
      'X-rays strike the row of CdWO₄ crystals along the top edge of the board.',
      'A photodiode bonded beneath each crystal converts the scintillation light into charge.',
      'An analogue front end amplifies and integrates each channel over the line period.',
      'A multiplexer and ADC digitise all channels in sequence; the FPGA packs them into a serial frame.',
      'One RJ45 carries the LVDS data out, and one 7.5 VDC feed powers the whole board.',
    ],
    physics: [
      'It is an <b>integrating</b> detector: charge is accumulated per line, so it reports intensity, not a photon count or an energy spectrum.',
      'CdWO₄ is used because at MeV cargo energies a light scintillator would be nearly transparent to the beam.',
      'LVDS is differential, so noise picked up along a long array run appears on both conductors and cancels.',
      'Digitising on the card means only digital data travels the array — analogue signals never leave the board.',
      'Integration time is tied to the line rate, which is tied to the conveyor or vehicle speed.',
    ],
    engineering: [
      'Boards are daisy-chained to a concentrator; each carries its own per-channel gain and offset calibration in EEPROM.',
      'A single 7.5 VDC feed arrives from the concentrator and the board generates its own internal rails.',
      'The PCB mounts to a support framework with captive screws, locator pins and locator lugs.',
      'Locator pins and lugs fix the geometry mechanically, so channel alignment does not depend on fitting care.',
      'Captive screws are a safety requirement: no loose fastener can drop into the tunnel during a change.',
      'Several board variants exist with different crystal pitches and quieter versions; the concentrator detects the type at boot.',
    ],
    practice: [
      'One failed board shows as a contiguous band of dead columns — easy to localise and quick to fix.',
      'A single dead channel is a persistent horizontal line at that channel position.',
      'Always run the calibration after a board swap; skipping it leaves a visible seam in every image.',
      'Intermittent bands usually mean a connector or power problem rather than a failed board.',
      'Let the concentrator re-detect and re-initialise after a swap — do not assume a hot-swap took.',
    ],
    numbers: [['Power in', '7.5 VDC'], ['Data out', 'LVDS over RJ45'], ['Crystal', 'CdWO₄'], ['Fault signature', 'contiguous dead band']],
  },

  'det-plastic': {
    oneLiner: 'Cheap plastic panels of a square metre or more, viewed by PMTs at the edges — maximum sensitivity per dollar for answering the question "is something radioactive going past?"',
    analogy: 'A very large, very cheap microphone. It cannot tell you what the sound was, only that something was loud.',
    watchFor: 'The count-rate trace jumping when a source passes between the panels, and returning to background afterwards.',
    how: [
      'A large slab of polyvinyltoluene scintillator sits beside the traffic lane.',
      'A gamma ray interacting in the plastic produces a flash of light.',
      'PMTs at the edges collect that light and produce a pulse.',
      'The system counts pulses and compares the rate against a rolling background estimate.',
      'A statistically significant rise raises an alarm.',
    ],
    physics: [
      'Low effective atomic number means good sensitivity per unit cost but essentially no spectroscopic capability.',
      'Compton scattering dominates in plastic, so full-energy peaks barely exist.',
      'Alarm logic is purely statistical: count rate versus expected background.',
    ],
    engineering: [
      'Panel size is driven by solid angle: bigger panels intercept more of the emitted radiation.',
      'Plastic is cheap, machinable and available in large sheets — no other scintillator scales this way.',
      'Light collection over a metre of plastic is the main optical engineering challenge.',
    ],
    practice: [
      'A dense cargo load suppresses natural background and can itself trigger a nuisance alarm.',
      'Positive alarms go to secondary inspection with a handheld spectroscopic identifier.',
      'Naturally occurring radioactive material causes the large majority of real-world alarms.',
    ],
    numbers: [['Material', 'polyvinyltoluene'], ['Spectroscopy', 'essentially none'], ['Role', 'detect, then identify elsewhere']],
  },

  'det-cdte': {
    oneLiner: 'The photon creates electron-hole pairs directly in the semiconductor — no light stage at all, so both spatial and energy resolution are dramatically better.',
    analogy: 'Translating a language directly instead of going through a second language first. Nothing is lost or blurred in the intermediate step.',
    watchFor: 'Charge carriers appearing directly at the interaction point and drifting straight to the electrodes — no light spreading sideways.',
    how: [
      'A photon is absorbed in the semiconductor crystal.',
      'Its energy promotes electrons across the band gap, creating electron-hole pairs.',
      'A bias voltage across the crystal sweeps electrons one way and holes the other.',
      'The moving charge induces a current pulse on the electrodes.',
      'Pulse height is proportional to the energy deposited.',
    ],
    physics: [
      'About 4.4 eV per electron-hole pair in CdTe, versus roughly 100 eV per detected carrier through a scintillator plus photodetector.',
      'More carriers per keV means much better energy resolution — real spectroscopy at room temperature.',
      'High Z and density give good stopping power for hard X-rays, unlike silicon.',
    ],
    engineering: [
      'Charge follows field lines with almost no lateral spread, so pixel pitch alone limits resolution.',
      'Hole trapping causes polarisation and spectral tailing; periodic bias reset is a real operational requirement.',
      'Crystal growth quality directly determines detector-grade yield, and it is expensive.',
    ],
    practice: [
      'This is the sensor behind photon-counting CT and portable isotope identifiers.',
      'Polarisation under high flux is the main practical limitation in imaging applications.',
      'Temperature stability matters less than for silicon, but leakage still rises with heat.',
    ],
    numbers: [['Pair energy', '≈ 4.4 eV'], ['Mode', 'direct conversion'], ['Issue', 'hole trapping / polarisation']],
  },

  'det-hpge': {
    oneLiner: 'Germanium needs only 2.96 eV per electron-hole pair, so the statistical spread is tiny — this is the reference detector for gamma spectroscopy, at the price of cryogenic cooling.',
    analogy: 'Measuring with a micrometer instead of a ruler. Vastly more precise, but you have to look after the instrument.',
    watchFor: 'The two sharp HPGe peaks against the single broad dashed NaI bump. Same two gamma lines, completely different ability to separate them.',
    how: [
      'A gamma ray interacts in a large high-purity germanium crystal.',
      'It creates electron-hole pairs — many more than in any other common detector.',
      'A high bias voltage sweeps the carriers to the electrodes.',
      'A charge-sensitive preamplifier converts the collected charge into a voltage step.',
      'Pulse height gives the deposited energy with exceptional precision.',
    ],
    physics: [
      'Only 2.96 eV per pair means very large carrier numbers, and resolution improves as <code>1/√N</code>.',
      'Resolution of about 1.8 keV at 1332 keV versus roughly 45 keV for NaI(Tl).',
      'Must be cooled to about 90 K or thermal generation across the small band gap swamps the signal.',
    ],
    engineering: [
      'Liquid nitrogen or an electromechanical cooler is mandatory, and it is the main operational burden.',
      'Field-portable versions with mechanical coolers exist but remain heavy and power-hungry.',
      'Crystal size determines efficiency, and large detector-grade crystals are extremely expensive.',
    ],
    practice: [
      'Used for nuclear forensics, safeguards verification and environmental measurement — anywhere identification must be certain.',
      'Warming up a biased detector damages it; power-down sequence discipline matters.',
      'Efficiency calibration must match the actual counting geometry, not a generic curve.',
    ],
    numbers: [['Pair energy', '2.96 eV'], ['Resolution', '≈ 1.8 keV @1332'], ['Cooling', '≈ 90 K']],
  },

  'det-asi': {
    oneLiner: 'A caesium-iodide needle layer converts X-rays to light directly above an amorphous-silicon transistor array that stores and reads out the charge pixel by pixel.',
    analogy: 'A digital camera sensor with a fluorescent screen glued on top — the screen turns X-rays into light the sensor can actually see.',
    watchFor: 'The gate line sweeping down the array one row at a time, reading out stored charge row by row.',
    how: [
      'X-rays are absorbed in the CsI layer and produce visible light.',
      'CsI grows in needle-like columns that pipe the light downward instead of letting it spread.',
      'Each pixel has a photodiode that converts light into stored charge.',
      'A thin-film transistor holds that charge until its row is addressed.',
      'Gate lines read one row at a time; charge amplifiers digitise each column.',
    ],
    physics: [
      'The needle structure preserves resolution far better than a powder screen would.',
      'Dynamic range above 10⁴ means one exposure covers thick and thin sections together.',
      'It integrates charge, so it records intensity rather than counting individual photons.',
    ],
    engineering: [
      'Each pixel is a photodiode plus a switching TFT; gate and data lines run across the panel.',
      'Bad-pixel maps, offset and gain calibration are mandatory and periodic, not one-off.',
      'Panel size is limited by manufacturing yield and by the cost of large-area TFT arrays.',
    ],
    practice: [
      'This is the standard detector for digital radiography, both medical and industrial.',
      'Panels degrade under cumulative dose, so requalification is periodic.',
      'A row or column of dead pixels usually means a broken gate or data line — a panel-level fault.',
    ],
    numbers: [['Scintillator', 'CsI needles'], ['Dynamic range', '> 10⁴'], ['Readout', 'row by row']],
  },

  'det-ase': {
    oneLiner: 'Amorphous selenium converts X-rays straight to charge under a strong field, and that charge travels along field lines with almost no lateral spread — the sharpest flat panel available.',
    analogy: 'Rain falling in perfectly still air lands exactly below where it started. No wind, no spreading.',
    watchFor: 'Charge created in the selenium layer travelling straight down field lines onto a single pixel.',
    how: [
      'A high bias field is applied across a thick amorphous selenium layer.',
      'X-rays absorbed in the selenium create electron-hole pairs directly.',
      'The strong field sweeps them vertically with almost no sideways diffusion.',
      'The charge lands on the pixel electrode directly beneath the interaction point.',
      'A TFT array reads out the stored charge exactly as in an a-Si panel.',
    ],
    physics: [
      'No light stage at all means no optical blur — resolution is limited only by pixel pitch.',
      'Needs a high bias field, around 10 V per micrometre across the selenium layer.',
      'Low atomic number limits absorption at higher energies, so it favours mammography-range work.',
    ],
    engineering: [
      'Temperature sensitive: selenium crystallises if it gets too warm, permanently ruining the panel.',
      'Layer thickness trades absorption against required bias voltage.',
      'Chosen where resolution dominates the requirement and beam energy is modest.',
    ],
    practice: [
      'Transport and storage temperature limits are strict and are a real cause of panel loss.',
      'Ghosting after a very high exposure is a known behaviour of selenium panels.',
    ],
    numbers: [['Conversion', 'direct'], ['Bias field', '≈ 10 V/µm'], ['Risk', 'thermal crystallisation']],
  },

  'det-cr': {
    oneLiner: 'A photostimulable phosphor stores the image as trapped electrons; a scanning laser releases them as light, a PMT reads it, and a bright lamp erases the plate for reuse.',
    analogy: 'Writing in invisible ink, then reading it under a special lamp, then bleaching the paper to write again.',
    watchFor: 'The laser sweeping across the plate, releasing stored energy as blue light which the PMT collects. Behind the laser, the plate is blank.',
    how: [
      'X-rays strike the imaging plate and excite electrons into long-lived trap states.',
      'The plate now holds a latent image made of trapped charge.',
      'In the reader, a red laser scans across the plate point by point.',
      'The laser energy releases trapped electrons, which emit blue light as they relax.',
      'A PMT measures that blue light; a bright lamp then erases the plate for reuse.',
    ],
    physics: [
      'Europium-doped barium fluorobromide traps electrons in colour centres proportional to the dose.',
      'The stimulating laser is red and the emitted light is blue, so an optical filter separates them cleanly.',
      'The latent image fades over hours: read the plate promptly or lose signal.',
    ],
    engineering: [
      'Read-out is mechanical and takes tens of seconds — much slower than a flat panel.',
      'Plates are flexible and cheap, so CR survives where a rigid panel will not fit or would be damaged.',
      'Reader optics and laser spot size set the achievable resolution.',
    ],
    practice: [
      'Incomplete erasure leaves ghost images from the previous exposure — a real and confusing artefact.',
      'Plates wear: scratches and cracks are permanent and show on every subsequent image.',
      'CR sits between film and DDA on both cost and performance, which is exactly why it persists.',
    ],
    numbers: [['Phosphor', 'BaFBr:Eu'], ['Read-out', 'tens of seconds'], ['Risk', 'fading and ghosting']],
  },

  'det-film': {
    oneLiner: 'Photons reduce silver halide grains to a latent image, and development amplifies each struck grain by about a billion times into visible metallic silver.',
    analogy: 'A seed and a greenhouse. The exposure plants a tiny seed in each grain; development grows every seed into something you can actually see.',
    watchFor: 'Grains changing from faint latent specks to large developed silver deposits — that jump is chemical amplification.',
    how: [
      'X-rays (mostly via photoelectrons from the lead screens) strike silver halide grains.',
      'A few silver atoms are reduced in each struck grain, forming a latent image speck.',
      'Development chemically reduces the entire grain wherever a latent speck exists.',
      'Fixing removes the undeveloped halide so the image is stable.',
      'The resulting metallic silver density is read on a light box or densitometer.',
    ],
    physics: [
      'Development is the amplification stage — a handful of atoms becomes a whole grain of silver, a gain of about 10⁹.',
      'The characteristic (H&D) curve defines toe, straight-line latitude and shoulder.',
      'Film class (EN ISO 11699 C4–C7) trades speed against grain and therefore against detail.',
    ],
    engineering: [
      'Processing chemistry, temperature and time are as much part of image quality as the exposure.',
      'Density is measured, not judged: a densitometer reading is the acceptance criterion.',
      'Archival stability depends on complete fixing and washing.',
    ],
    practice: [
      'Still the archival reference in some codes because the record is physical and self-contained.',
      'Most "exposure" problems in film radiography turn out to be processing problems.',
      'Processor QA with a step wedge catches chemistry drift before it ruins production work.',
    ],
    numbers: [['Amplification', '≈ 10⁹ (development)'], ['Curve', 'H&D characteristic'], ['Classes', 'C4–C7']],
  },

  'det-tld': {
    oneLiner: 'Radiation traps electrons in a crystal; later, heat or light releases them and the emitted glow is proportional to the dose the wearer actually received.',
    analogy: 'A savings jar you cannot look into. At the end of the month you empty it and count what accumulated.',
    watchFor: 'Traps filling during exposure, then releasing as the chip is heated, producing the glow curve on the right.',
    how: [
      'Radiation creates electron-hole pairs in the crystal.',
      'Some carriers become trapped at defect sites and stay there.',
      'The badge is worn for a month or a quarter, accumulating trapped charge.',
      'In the reader, heating (TLD) or light (OSL) releases the trapped carriers.',
      'They recombine and emit light; the total light is proportional to the accumulated dose.',
    ],
    physics: [
      'LiF:Mg,Ti is nearly tissue-equivalent, which is why it dominates personal dosimetry.',
      'The glow curve peaks identify which traps emptied — deep traps hold dose stably for months.',
      'Shallow traps fade, so the reader analyses only the stable peaks.',
    ],
    engineering: [
      'OSL (Al₂O₃:C) can be re-read several times; TLD read-out is destructive.',
      'Filters over different elements of the badge let the reader estimate photon energy and radiation type.',
      'Reader calibration is traceable and the whole chain is accredited.',
    ],
    practice: [
      'The badge is the legal dose of record; an electronic dosimeter is the real-time warning. You need both.',
      'A badge left in a car or near a source gives a false record that must be investigated, not ignored.',
      'Neutron dose needs a different technique — CR-39 track etch or albedo TLD.',
    ],
    numbers: [['Material', 'LiF:Mg,Ti'], ['OSL', 'Al₂O₃:C, re-readable'], ['Role', 'legal dose of record']],
  },

  'det-preamp': {
    oneLiner: 'The collected charge is integrated by a charge-sensitive preamplifier, shaped into a well-behaved pulse, then sampled — and this electronics chain sets the noise floor of the whole detector.',
    analogy: 'A recording studio. However good the singer, a noisy microphone and bad mixing decide what actually reaches the listener.',
    watchFor: 'The step from the preamp, the shaped pulse from the shaper, and the final number from the ADC. Each stage transforms the same event.',
    how: [
      'Charge from the sensor is integrated onto the preamplifier feedback capacitor, producing a voltage step.',
      'The step height is proportional to the collected charge, and hence to the deposited energy.',
      'A shaping amplifier converts that step into a short, symmetric pulse with optimal signal-to-noise.',
      'Baseline restoration removes low-frequency drift between pulses.',
      'A peak-sensing or flash ADC digitises the pulse height into a number.',
    ],
    physics: [
      'Equivalent noise charge (ENC) is the figure of merit, usually quoted in electrons RMS.',
      'Shaping time trades energy resolution against count-rate capability — long shaping means pile-up.',
      'ENC rises with sensor capacitance, which is why the preamp must be as close to the sensor as possible.',
    ],
    engineering: [
      'Every millimetre of track between sensor and preamp adds capacitance and therefore noise.',
      'Pile-up rejection and baseline restoration keep the spectrum clean at high flux.',
      'In integrating detectors the same chain reads accumulated charge per line instead of per pulse.',
    ],
    practice: [
      'Poor grounding and pickup are far more common causes of bad resolution than a bad detector.',
      'Choosing shaping time is the single most influential setting in a spectroscopy chain.',
      'Resolution measured on a bench does not survive a noisy installation — measure in situ.',
    ],
    numbers: [['Figure of merit', 'ENC (e⁻ RMS)'], ['Trade', 'resolution vs rate'], ['Rule', 'preamp close to sensor']],
  },

  'det-dqe': {
    oneLiner: 'Three numbers describe any imaging detector: how many photons it catches, how well it preserves detail, and how much of the input signal-to-noise actually survives to the image.',
    analogy: 'A camera can be sharp but grainy, or smooth but soft. Only measuring both together tells you which one takes better photographs.',
    watchFor: 'Switching between a thick efficient detector and a thin sharp one — MTF and DQE move in opposite directions.',
    how: [
      'Measure quantum efficiency: what fraction of incident photons actually interact.',
      'Measure MTF: how much contrast survives at each spatial frequency.',
      'Measure noise power spectrum: how the noise is distributed across frequencies.',
      'Combine them into DQE — the fraction of input SNR² that reaches the output.',
      'Compare detectors on DQE, not on any single component measurement.',
    ],
    physics: [
      '<code>DQE(f) = SNR²_out / SNR²_in</code> as a function of spatial frequency.',
      'A detector can have great MTF and poor DQE if it throws away most photons — sharp but noisy.',
      'DQE can never exceed 1: you cannot recover information the photons never carried.',
    ],
    engineering: [
      'Quantum efficiency is driven by thickness and atomic number; MTF by light spread and pixel pitch.',
      'Thicker scintillator: more photons caught, more light spread, better DQE at low frequency, worse MTF.',
      'IEC 62220 defines how DQE is measured so manufacturers\' numbers can be compared.',
    ],
    practice: [
      'Dose reduction claims are only meaningful if quoted as DQE, not as efficiency or resolution alone.',
      'Always ask at which spatial frequency and which beam quality a quoted DQE was measured.',
      'A detector optimised for one application is rarely optimal for another — the trade is physical, not commercial.',
    ],
    numbers: [['DQE', 'SNR²out / SNR²in'], ['Max value', '1.0'], ['Standard', 'IEC 62220']],
  },
};
