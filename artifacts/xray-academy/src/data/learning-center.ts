/**
 * Data for the Interactive Learning Center (Radiation Sources platform).
 * Quizzes, flashcards, and guided lesson tracks — all client-side, no backend dependency.
 */

export interface QuizQuestion {
  q: string;
  options: string[];
  answer: number;
  explanation: string;
}

// ─── Quizzes ────────────────────────────────────────────────────────────────
// Keyed by two namespaces that never collide:
//  - topic ids (xray-tube, linac, radioisotopes, neutron, security) used by the
//    per-page `SectionQuiz` widgets already embedded in individual source pages.
//  - learning-path ids (fundamentals, xray-engineering, ...) used by the
//    Learning Center's aggregated "Quizzes & Certificates" tab, one per LEARNING_PATHS entry.
export const TOPIC_QUIZZES: Record<string, QuizQuestion[]> = {
  // ── Existing per-topic quizzes (moved from radiation-sources.tsx) ──────────
  'xray-tube': [
    { q: 'What percentage of electron beam energy is typically converted to X-rays in a diagnostic tube?', options: ['~1%', '~10%', '~50%', '~99%'], answer: 0, explanation: 'Only ~1% of the beam energy becomes X-radiation; ~99% becomes heat at the anode — hence why cooling is critical.' },
    { q: 'Which material is used as the anode target in mammography tubes to produce optimal K-α characteristic radiation?', options: ['Tungsten (W)', 'Molybdenum (Mo)', 'Copper (Cu)', 'Gold (Au)'], answer: 1, explanation: 'Molybdenum has a K-edge at 20 keV, producing K-α characteristic radiation ideal for mammography tissue contrast.' },
    { q: 'What is the primary purpose of the focusing cup (Wehnelt electrode) in an X-ray tube?', options: ['Cool the anode', 'Filter soft X-rays', 'Focus the electron beam onto the focal spot', 'Rotate the anode disc'], answer: 2, explanation: 'The Wehnelt electrode creates an electrostatic lens effect that concentrates electrons onto the desired focal spot on the anode.' },
    { q: "Anode Heat Units (AHU) are calculated as:", options: ['kVp × mAs', 'kV × mA × time²', 'mAs / kVp', 'kVp² × mA'], answer: 0, explanation: "AHU = kVp × mAs. Exceeding the tube's rated AHU capacity risks anode cracking or bearing seizure." },
  ],
  linac: [
    { q: 'What is the primary function of the bending magnet in a medical LINAC?', options: ['Generate RF power', 'Accelerate electrons', 'Redirect the electron beam to the treatment head and select energy', 'Filter the photon beam'], answer: 2, explanation: 'The 270° achromatic bending magnet redirects the beam downward and acts as an energy selector (spread < 3%).' },
    { q: 'In cargo inspection LINACs, what technique is used to discriminate between organic and metallic materials?', options: ['Single-energy attenuation', 'Dual-energy imaging (Zeff mapping)', 'Neutron activation', 'Phase contrast'], answer: 1, explanation: 'Dual-energy imaging compares high/low energy attenuation ratios to compute effective atomic number (Zeff), separating organics (Zeff ~7) from metals (Zeff > 20).' },
    { q: 'What is the role of the magnetron (or klystron) in a LINAC?', options: ['Cool the waveguide', 'Generate high-power RF pulses to drive the accelerating structure', 'Produce the initial electron beam', 'Flatten the dose profile'], answer: 1, explanation: 'Magnetrons (compact, up to 5 MW) or klystrons (large, up to 50 MW) generate the RF power that creates the accelerating EM field in the waveguide.' },
    { q: 'Which energy range is typical for LINAC-based cargo container portal scanners?', options: ['160–450 kV', '1–3 MeV', '3–9 MeV', '15–25 MV'], answer: 2, explanation: '6–9 MeV is the standard range for container cargo scanners, providing penetration through 300–380 mm of steel-equivalent.' },
  ],
  radioisotopes: [
    { q: 'Co-60 produces gamma rays at two energies. Which pair is correct?', options: ['0.511 and 1.02 MeV', '0.662 and 1.33 MeV', '1.17 and 1.33 MeV', '0.186 and 0.60 MeV'], answer: 2, explanation: 'Co-60 decays via β⁻ to excited Ni-60, which de-excites emitting 1.173 MeV and 1.333 MeV gamma photons almost simultaneously.' },
    { q: 'A source has an activity of 100 GBq today. After two half-lives, the activity will be:', options: ['50 GBq', '25 GBq', '12.5 GBq', '6.25 GBq'], answer: 1, explanation: 'After one half-life: 50 GBq. After two half-lives: 25 GBq. Activity halves each half-life period.' },
    { q: 'Which isotope is most commonly used in HDR (High Dose Rate) brachytherapy due to its small source size and suitable energy?', options: ['Co-60', 'Ra-226', 'Ir-192', 'Cs-137'], answer: 2, explanation: 'Ir-192 (73.8 day T½, avg 0.37 MeV γ) is the standard HDR source — small enough (< 1 mm diameter) to fit through brachytherapy catheters.' },
    { q: 'According to the Inverse Square Law, moving from 1 m to 3 m from a point source reduces the dose rate by a factor of:', options: ['3', '6', '9', '27'], answer: 2, explanation: 'ISL: dose rate ∝ 1/d². At 3× the distance, dose rate is 1/9. This is why distance is the simplest and most effective radiation protection tool.' },
  ],
  neutron: [
    { q: 'What energy do neutrons produced by a D-T generator have?', options: ['0.025 eV (thermal)', '2.45 MeV', '14.1 MeV', '200 MeV'], answer: 2, explanation: 'D-T fusion (d + t → ⁴He + n) produces 14.1 MeV monoenergetic fast neutrons — the basis for pulsed fast neutron analysis (PFNA) in cargo scanning.' },
    { q: 'Which material is the most effective moderator for fast neutrons?', options: ['Lead', 'Borated steel', 'Polyethylene (hydrogen-rich)', 'Tungsten'], answer: 2, explanation: 'Hydrogen nuclei (same mass as neutrons) achieve maximum energy transfer per elastic collision. Polyethylene and water are the most efficient moderators.' },
    { q: 'He-3 proportional counters are preferred for thermal neutron detection. Why has He-3 become scarce since 2009?', options: ['New reactor designs no longer produce it', 'Tritium decay (the only He-3 source) outstrips supply', 'It is being stockpiled for fusion research', 'Export controls limit availability'], answer: 1, explanation: 'He-3 is produced by beta decay of tritium (T½ = 12.3 y) from nuclear weapons programs. Post-Cold-War tritium stockpile reductions drastically reduced He-3 supply.' },
  ],
  security: [
    { q: 'In dual-energy X-ray security screening, what property of a material is estimated from the high/low energy attenuation ratio?', options: ['Mass', 'Density', 'Effective atomic number (Zeff)', 'Volume'], answer: 2, explanation: 'The ratio of Compton-dominated high-energy to photoelectric-dominated low-energy attenuation is a strong function of Zeff, enabling material discrimination.' },
    { q: 'What is the typical effective dose received by a person from a single airport backscatter personnel scanner?', options: ['0.05–0.1 μSv', '1–5 μSv', '0.5 mSv', '5 mSv'], answer: 0, explanation: '~0.05–0.1 μSv per scan — equivalent to a few minutes of normal background radiation and far below any health-relevant threshold.' },
    { q: 'A Radiation Portal Monitor (RPM) at a border crossing uses passive detection. What gamma detector material is commonly used?', options: ['Germanium (HPGe)', 'Sodium iodide (NaI)', 'Silicon PIN diode', 'Xenon gas'], answer: 1, explanation: 'Large NaI(Tl) plastic or CsI panels are used in RPMs for their high detection efficiency. HPGe offers better resolution but requires cooling and is too expensive for portal-scale deployment.' },
  ],
  'linac-history': [],

  // ── Learning-path quizzes (new) — one per LEARNING_PATHS id ────────────────
  fundamentals: [
    { q: 'What distinguishes ionising radiation from non-ionising radiation?', options: ['Its wavelength is always visible', 'It carries enough energy to remove electrons from atoms', 'It only travels through air', 'It has no measurable energy'], answer: 1, explanation: 'Ionising radiation (X-rays, gamma rays, alpha, beta) has enough energy per photon/particle to strip electrons from atoms, unlike non-ionising radiation (radio waves, visible light).' },
    { q: 'Radioactive decay follows which mathematical law?', options: ['Linear decrease over time', 'Exponential decay, N(t) = N₀e^(−λt)', 'Step-function decrease at the half-life', 'Constant activity until sudden decay'], answer: 1, explanation: 'Activity decreases exponentially. The decay constant λ relates to half-life by λ = ln(2)/T½.' },
    { q: 'X-rays are produced in a tube by two main mechanisms. What are they?', options: ['Fission and fusion', 'Bremsstrahlung and characteristic radiation', 'Compton and photoelectric', 'Alpha and beta decay'], answer: 1, explanation: 'Bremsstrahlung (deceleration in the nuclear field, continuous spectrum) and characteristic radiation (inner-shell electron transitions, discrete lines) together form the tube output spectrum.' },
    { q: 'Which of the three basic radiation protection principles reduces dose the most efficiently for a point source, all else equal?', options: ['Shielding only', 'Time only', 'Distance — dose rate falls as 1/d²', 'None of these matter'], answer: 2, explanation: 'The inverse square law means dose rate drops with the square of distance — doubling distance cuts dose rate to a quarter, often more practical than adding shielding.' },
    { q: 'The SI unit of absorbed dose is the:', options: ['Sievert (Sv)', 'Becquerel (Bq)', 'Gray (Gy)', 'Curie (Ci)'], answer: 2, explanation: 'Gray (Gy = J/kg) measures absorbed dose. Sievert measures equivalent/effective dose (weighted for biological effect); Becquerel measures activity (decays/second).' },
  ],
  'xray-engineering': [
    { q: 'What is the main practical limit on X-ray tube output at a given kVp?', options: ['Filament voltage', 'Anode heat loading capacity', 'Detector sensitivity', 'Tube envelope colour'], answer: 1, explanation: 'Most of the beam energy converts to heat at the anode. Anode heat units (AHU) and cooling rate set the practical output ceiling before tube damage.' },
    { q: 'Which image quality metric describes a system\'s ability to preserve fine spatial detail (contrast at high spatial frequency)?', options: ['SNR (Signal-to-Noise Ratio)', 'MTF (Modulation Transfer Function)', 'CNR (Contrast-to-Noise Ratio)', 'DQE at zero frequency'], answer: 1, explanation: 'MTF quantifies how well spatial frequencies (fine detail) are preserved through the imaging chain — it falls off at higher frequencies as resolution degrades.' },
    { q: 'Dual-energy X-ray imaging for material discrimination relies primarily on the fact that:', options: ['All materials attenuate identically at every energy', 'Photoelectric and Compton cross-sections depend differently on atomic number and energy', 'Only metals attenuate X-rays', 'Detector gain is energy-independent'], answer: 1, explanation: 'Photoelectric attenuation scales strongly with Z (∝Z⁴⁻⁵) and falls fast with energy, while Compton attenuation is nearly Z-independent — comparing high/low energy attenuation isolates effective Z.' },
    { q: 'DQE (Detective Quantum Efficiency) of a detector describes:', options: ['Its physical weight', 'How efficiently it converts input signal-to-noise into output signal-to-noise', 'Its maximum operating kVp', 'Its frame rate only'], answer: 1, explanation: 'DQE = (SNR_out)² / (SNR_in)², a frequency-dependent measure of how much a detector degrades the available signal-to-noise ratio — the single most complete detector performance metric.' },
    { q: 'A flat-panel detector shows increasing gain non-uniformity over time. What is the standard corrective procedure?', options: ['Replace the entire system', 'Recalibrate with dark-field and flat-field acquisitions (gain + offset map)', 'Increase kVp permanently', 'Ignore it — it self-corrects'], answer: 1, explanation: 'Periodic gain/offset recalibration using dark frames (no X-rays) and flat-field frames (uniform exposure) is the standard maintenance procedure for detector drift.' },
  ],
  'linac-engineering': [
    { q: 'What is the key difference between a standing-wave and a travelling-wave accelerating structure?', options: ['Standing-wave structures cannot be used in medical LINACs', 'Standing-wave structures reflect RF power to build resonant field amplitude; travelling-wave structures absorb power along a single pass', 'Travelling-wave structures require no RF source', 'There is no practical difference'], answer: 1, explanation: 'Standing-wave structures use resonant reflection for higher efficiency in compact medical LINACs; travelling-wave structures are common in longer, higher-energy research accelerators.' },
    { q: 'IAEA TRS-398 is the international code of practice for:', options: ['Radioactive material transport', 'Absorbed dose determination (dosimetry) in external beam radiotherapy', 'Cargo inspection system procurement', 'Industrial radiography film processing'], answer: 1, explanation: 'TRS-398 establishes the calibration conditions, beam quality correction factors, and uncertainty analysis for calibrating photon and electron therapy beams.' },
    { q: 'What is the purpose of the flattening filter in a conventional LINAC treatment head?', options: ['Cool the target', 'Produce a spatially uniform (flat) dose profile across the field', 'Generate the RF power', 'Bend the electron beam'], answer: 1, explanation: 'The raw forward-peaked bremsstrahlung beam from the target is shaped by a conical flattening filter to produce a uniform dose profile across the treatment field (FFF beams skip this for higher dose rate).' },
    { q: 'A magnetron typically has an operating life on the order of:', options: ['3,000–5,000 hours', '50 hours', '500,000 hours', 'Indefinite — magnetrons do not wear out'], answer: 0, explanation: 'Magnetron cathode emitters degrade with use; 3,000–5,000 operating hours is a typical replacement interval, tracked via service logs and filament current trends.' },
    { q: 'In LINAC beam commissioning, what does AFC stand for and what does it do?', options: ['Automatic Filter Control — adjusts the flattening filter', 'Automatic Frequency Control — keeps the magnetron/waveguide system tuned to resonance', 'Automatic Focus Calibration — focuses the electron gun', 'Advanced Field Correction — corrects dose profile only'], answer: 1, explanation: 'AFC continuously adjusts frequency to keep the RF source matched to the accelerating structure\'s resonant frequency as it drifts with temperature; a large AFC drift indicates ageing components.' },
  ],
  'radiation-safety-officer': [
    { q: 'Deterministic (tissue reaction) radiation effects are characterised by:', options: ['No threshold — any dose carries some probability of harm', 'A dose threshold below which the effect does not occur, and severity increases with dose above it', 'Occurring only at the cellular level with no clinical significance', 'Being unrelated to absorbed dose'], answer: 1, explanation: 'Deterministic effects (e.g. skin erythema, cataracts) have a dose threshold; stochastic effects (e.g. cancer induction) are assumed to have no threshold, with probability — not severity — increasing with dose.' },
    { q: 'Per ICRP 103, what is the annual effective dose limit for occupationally exposed workers?', options: ['1 mSv/year', '20 mSv/year (averaged over 5 years, max 50 mSv in any single year)', '100 mSv/year', 'No limit applies to trained workers'], answer: 1, explanation: '20 mSv/year averaged over defined 5-year periods (with a 50 mSv/year single-year cap) is the ICRP 103 occupational limit; the public limit is 1 mSv/year.' },
    { q: 'ALARA stands for and means:', options: ['"As Low As Regulically Approved" — follow the exact legal limit', 'As Low As Reasonably Achievable — minimise dose below limits considering cost, benefit, and practicality', 'A Legal Administrative Radiation Assessment', 'A dose calculation formula'], answer: 1, explanation: 'ALARA is an optimisation principle: doses should be kept as low as reasonably achievable, not simply below the legal limit, weighing economic and societal factors.' },
    { q: 'When designing a primary radiation barrier for a facility, which factor is NOT typically part of the calculation?', options: ['Workload (W)', 'Use factor (U)', 'Occupancy factor (T)', 'The colour of the facility walls'], answer: 3, explanation: 'Barrier thickness is derived from workload, use factor, occupancy factor, distance, and required transmission — per NCRP 151 for megavoltage facilities. Wall colour is irrelevant to shielding physics.' },
    { q: 'What is the first action required when an area radiation monitor alarms unexpectedly during operation?', options: ['Increase beam output to test the alarm', 'Immediately disable the source/beam and notify the Radiation Protection Officer', 'Ignore it if no one is nearby', 'Wait until the end of the shift to investigate'], answer: 1, explanation: 'A monitor alarm must be treated as a real radiation safety event until proven otherwise — beam off immediately, evacuate if needed, and notify the RPO without delay.' },
  ],
  'cargo-inspection': [
    { q: 'Why do container cargo scanners typically use 6–9 MeV LINAC sources rather than lower-energy X-ray tubes?', options: ['LINACs are cheaper to install', 'MeV-range photons are needed to penetrate 300+ mm of steel-equivalent cargo', 'Regulations require LINACs specifically', 'X-ray tubes cannot be made mobile'], answer: 1, explanation: 'Steel containers and dense cargo require multi-MeV photon energies for sufficient penetration; kV-range tube sources cannot achieve the needed steel-equivalent penetration.' },
    { q: 'Dual-energy discrimination in cargo scanning is primarily used to:', options: ['Reduce scan time only', 'Distinguish organic materials (low Zeff) from metallic/dense materials (high Zeff) for threat and contraband screening', 'Increase radiation dose for better contrast', 'Replace the need for any operator review'], answer: 1, explanation: 'By comparing attenuation at two energies, the system estimates effective atomic number, colour-coding organics (e.g., drugs, explosives precursors) differently from metals.' },
    { q: 'What is a key operational safety requirement specific to cargo inspection LINAC systems?', options: ['No safety requirements beyond standard electrical safety', 'Positive confirmation that the scan zone is clear of personnel before beam-on, enforced by interlocks', 'Operators must stand inside the tunnel during scanning', 'The beam must remain on continuously between scans'], answer: 1, explanation: 'Interlocked access control and personnel-clear confirmation before beam activation is fundamental — cargo LINAC beams are lethal at close range and systems must fail safe.' },
    { q: 'Special Nuclear Material (SNM) detection in cargo screening is generally supplemented by which additional technology beyond transmission X-ray imaging?', options: ['Passive gamma/neutron radiation portal monitors', 'Higher visible-light cameras', 'Sound-based sonar', 'Infrared thermal imaging only'], answer: 0, explanation: 'Transmission X-ray imaging shows shape/density but not radioactivity; passive radiation portal monitors (gamma + neutron detectors) are used alongside imaging to flag SNM and other radioactive threats.' },
  ],
  'ndt-radiography': [
    { q: 'In industrial radiography, what does an Image Quality Indicator (IQI) verify?', options: ['The exposure time only', 'That the radiographic technique achieves adequate sensitivity to detect flaws of a specified size', 'The isotope\'s remaining half-life', 'The operator\'s certification level'], answer: 1, explanation: 'IQIs (wire-type or hole-type) placed on the test object confirm the technique\'s sensitivity — if the required IQI feature is visible, the technique meets the specified image quality class.' },
    { q: 'Per EN ISO 17636-1 / ASTM E94, what does "Class B" (or equivalent higher-sensitivity) technique generally require compared to Class A?', options: ['Lower image quality requirements', 'Tighter geometric and exposure parameters for higher sensitivity (e.g. lower permitted geometric unsharpness)', 'No IQI is needed', 'Only isotope sources may be used'], answer: 1, explanation: 'Higher-sensitivity technique classes impose stricter limits on geometric unsharpness, source-to-object distance, and other parameters to reveal smaller flaws.' },
    { q: 'Which industrial gamma source is most associated with portable pipeline and field weld radiography due to its compact size and moderate energy?', options: ['Co-60', 'Ra-226', 'Ir-192', 'Am-241'], answer: 2, explanation: 'Ir-192 combines a small physical source size, moderate gamma energy (avg. 0.37 MeV), and practical half-life (73.8 days) — the standard choice for portable field radiography projectors.' },
    { q: 'What is the main advantage of digital detector arrays (DDA) over traditional film in industrial radiography?', options: ['DDAs require no calibration ever', 'Immediate image availability and reusable detectors, though film often still offers higher intrinsic spatial resolution', 'DDAs eliminate the need for any radiation source', 'Film cannot be used for welds'], answer: 1, explanation: 'DDA/CR systems offer speed, reusability, and digital archiving; film retains advantages in very fine spatial resolution for some applications — technique selection depends on the standard and application.' },
    { q: 'A Level II radiographer\'s certification typically authorises them to:', options: ['Only load film into cassettes', 'Interpret radiographs, set up techniques, and evaluate results against acceptance criteria under a Level III\'s written procedures', 'Approve their own certification without oversight', 'Design new NDT standards'], answer: 1, explanation: 'Level II personnel perform and interpret NDT per established, Level III-approved written procedures — a core competency the NDT learning path builds toward.' },
  ],
};

// ─── Flashcards ─────────────────────────────────────────────────────────────
export interface Flashcard {
  id: string;
  front: string;
  back: string;
  category: string;
}

export const FLASHCARDS: Flashcard[] = [
  // Core physics & dosimetry terms
  { id: 'hvl', front: 'HVL (Half-Value Layer)', back: 'The thickness of a specified material that reduces radiation intensity to 50% of its original value. HVL = ln(2)/μ. Used to design shielding.', category: 'Physics & Dosimetry' },
  { id: 'tvl', front: 'TVL (Tenth-Value Layer)', back: 'The thickness of a specified material that reduces radiation intensity to 10% of its original value. TVL = ln(10)/μ ≈ 3.32 × HVL.', category: 'Physics & Dosimetry' },
  { id: 'alara', front: 'ALARA', back: 'As Low As Reasonably Achievable — the radiation protection optimisation principle: keep doses below limits and as low as practical given cost, benefit, and technology.', category: 'Radiation Protection' },
  { id: 'zeff', front: 'Zeff (Effective Atomic Number)', back: 'A weighted average atomic number representing how a compound/mixture attenuates radiation, used in dual-energy imaging to distinguish organic from metallic/dense materials.', category: 'Physics & Dosimetry' },
  { id: 'kvp', front: 'kVp (Peak Kilovoltage)', back: 'The peak voltage applied across an X-ray tube, setting the maximum photon energy (and strongly influencing beam penetration/contrast).', category: 'X-ray Tube Engineering' },
  { id: 'mas', front: 'mAs (Milliampere-seconds)', back: 'Tube current × exposure time — controls the quantity (not energy) of X-rays produced, and thus image noise/dose.', category: 'X-ray Tube Engineering' },
  { id: 'gray', front: 'Gray (Gy)', back: 'SI unit of absorbed dose: 1 Gy = 1 joule of energy absorbed per kilogram of matter. Replaces the older "rad" (1 rad = 0.01 Gy).', category: 'Units' },
  { id: 'sievert', front: 'Sievert (Sv)', back: 'SI unit of equivalent/effective dose: absorbed dose weighted for radiation type and tissue sensitivity, used for radiation protection risk assessment. Replaces "rem" (1 rem = 0.01 Sv).', category: 'Units' },
  { id: 'becquerel', front: 'Becquerel (Bq)', back: 'SI unit of radioactivity: 1 Bq = 1 nuclear decay per second. The older unit, Curie (Ci), equals exactly 3.7 × 10¹⁰ Bq.', category: 'Units' },
  { id: 'isl', front: 'Inverse Square Law (ISL)', back: 'For a point source, dose rate is proportional to 1/d². Doubling distance from the source reduces dose rate to one quarter — the most efficient protection tool after time.', category: 'Radiation Protection' },
  { id: 'bremsstrahlung', front: 'Bremsstrahlung', back: '"Braking radiation" — X-rays produced when a fast electron decelerates in the Coulomb field of a nucleus. Produces the continuous part of an X-ray tube spectrum.', category: 'Physics & Dosimetry' },
  { id: 'characteristic', front: 'Characteristic Radiation', back: 'Discrete-energy X-rays emitted when an incident electron ejects an inner-shell (K/L) electron from a target atom and an outer electron fills the vacancy, releasing energy equal to the shell energy difference.', category: 'Physics & Dosimetry' },
  { id: 'compton', front: 'Compton Scattering', back: 'A photon scatters off a loosely-bound outer electron, losing some energy and changing direction; the electron recoils. Dominant interaction at 0.1–10 MeV in low-Z materials (e.g. tissue).', category: 'Physics & Dosimetry' },
  { id: 'photoelectric', front: 'Photoelectric Effect', back: 'A photon is fully absorbed by an inner-shell electron, which is ejected with kinetic energy KE = hν − φ. Strongly favours high-Z materials and low photon energies (< ~100 keV).', category: 'Physics & Dosimetry' },
  { id: 'pair-production', front: 'Pair Production', back: 'A photon above 1.022 MeV (2 × electron rest mass) converts into an electron-positron pair in a nucleus\'s field. Dominant above ~5–10 MeV in high-Z materials.', category: 'Physics & Dosimetry' },
  { id: 'half-life', front: 'Half-Life (T½)', back: 'The time required for a radioactive source\'s activity to decrease by half. Related to the decay constant λ by T½ = ln(2)/λ.', category: 'Radioisotopes' },
  { id: 'collimation', front: 'Collimation', back: 'Restricting the X-ray/gamma beam to the area of clinical or inspection interest using shielded apertures — reduces scatter, improves image quality, and reduces unnecessary dose.', category: 'Radiation Protection' },
  { id: 'filtration', front: 'Beam Filtration (Al Equivalent)', back: 'Added material (commonly aluminium) that removes low-energy ("soft") photons from the beam that would otherwise be absorbed by the patient/object without contributing useful signal, reducing dose without materially reducing image quality.', category: 'X-ray Tube Engineering' },
  { id: 'buildup-factor', front: 'Buildup Factor B(μx)', back: 'A multiplier accounting for scattered radiation reaching a detector behind a shield in broad-beam geometry (as opposed to narrow-beam attenuation alone), always ≥ 1 — increasingly important for thick shields and higher energies.', category: 'Physics & Dosimetry' },
  { id: 'geometric-unsharpness', front: 'Geometric Unsharpness (Ug)', back: 'Image blur caused by the finite size of the radiation source (focal spot). Ug = f·b/a, where f = focal spot size, b = object-to-detector distance, a = source-to-object distance. Standards (ASTM E94, EN ISO 17636) set maximum allowed Ug.', category: 'NDT & Radiography' },

  // Standards & references (derived from STANDARDS_DB)
  { id: 'std-iaea-ssr6', front: 'IAEA SSR-6 Rev.1', back: 'Regulations for the Safe Transport of Radioactive Material (2018). Mandatory reference for shipping Co-60, Ir-192, Cs-137, and all other radioactive sources — defines package types, activity limits, and labelling.', category: 'Standards' },
  { id: 'std-iaea-ssg8', front: 'IAEA SSG-8', back: 'Radiation Protection in the Design of Radiation Sources (Irradiators). Key reference for Co-60/Cs-137 gamma irradiator shielding design, interlocks, and safety analysis.', category: 'Standards' },
  { id: 'std-iaea-trs398', front: 'IAEA TRS-398', back: 'Absorbed Dose Determination in External Beam Radiotherapy. The primary dosimetry reference for calibrating medical LINAC and cobalt-60 teletherapy beams.', category: 'Standards' },
  { id: 'std-icrp-103', front: 'ICRP Publication 103 (2007)', back: 'The internationally adopted basis for radiological protection legislation: defines dose limits (20 mSv/y occupational, 1 mSv/y public), dose concepts, and the ALARA optimisation principle.', category: 'Standards' },
  { id: 'std-ncrp-151', front: 'NCRP Report 151 (2005)', back: 'Structural Shielding Design for Megavoltage X- and Gamma-Ray Radiotherapy Facilities. The standard design reference for LINAC bunker/vault shielding in hospitals.', category: 'Standards' },
  { id: 'std-iec-60601-2-1', front: 'IEC 60601-2-1:2014', back: 'Particular requirements for the safety and performance of electron accelerators (1–50 MeV) used for radiotherapy. Mandatory product standard for CE marking of radiotherapy LINACs.', category: 'Standards' },
  { id: 'std-iec-62463', front: 'IEC 62463:2010', back: 'Radiation Protection Instrumentation — X-ray Systems for the Inspection of Persons. Key standard for backscatter/transmission person-screening equipment type approval.', category: 'Standards' },
  { id: 'std-iso-11137', front: 'ISO 11137-1:2006', back: 'Sterilization of health care products by radiation — requirements for development, validation, and routine control. Essential for Co-60/E-beam sterilisation facilities.', category: 'Standards' },
  { id: 'std-astm-e94', front: 'ASTM E94-17', back: 'Standard Guide for Radiographic Examination Using Industrial Radiographic Film. Foundational NDT film radiography standard covering technique, processing, and acceptance criteria.', category: 'Standards' },
  { id: 'std-en-iso-17636-1', front: 'EN ISO 17636-1:2013', back: 'Radiographic testing of welds using film and digital detectors (X- and gamma-ray techniques). The primary European/international film weld-radiography standard.', category: 'Standards' },
  { id: 'std-ansi-n42-45', front: 'ANSI N42.45-2011', back: 'Characterization of the Imaging Performance of Security X-ray Systems. Reference standard for image quality assessment of airport/security screening systems.', category: 'Standards' },
  { id: 'std-ansi-n42-35', front: 'ANSI N42.35-2016', back: 'Evaluation and Performance of Radiation Portal Monitors for homeland security. Key standard for RPM procurement and performance testing at border crossings.', category: 'Standards' },
  { id: 'std-icrp-116', front: 'ICRP Publication 116 (2010)', back: 'Conversion Coefficients for Radiological Protection Quantities. Used to convert measured operational quantities (Hp(10), H*(10)) to effective dose for risk assessment.', category: 'Standards' },
];

// ─── Guided step-by-step lesson tracks ─────────────────────────────────────
export interface LessonStep {
  title: string;
  explanation: string;
  /** id from ANIM_LIST (radiation-ext.tsx) to render for this step; omit for a text-only step */
  animationId?: string;
  checkQuestion?: QuizQuestion;
}

export interface LessonTrack {
  id: string;
  title: string;
  description: string;
  steps: LessonStep[];
}

export const LESSON_TRACKS: LessonTrack[] = [
  {
    id: 'photon-interactions',
    title: 'Photon Interactions with Matter',
    description: 'A guided walk through the four fundamental ways photons interact with matter, and which one dominates at a given energy and material.',
    steps: [
      {
        title: 'Why Photons Interact with Matter',
        explanation: 'When an X-ray or gamma photon travels through matter, it can be absorbed or scattered by the atoms it encounters. Which interaction happens depends mainly on two things: the photon\'s energy and the atomic number (Z) of the material. Over the next steps you\'ll see each mechanism animated, then see how they compete.',
      },
      {
        title: 'The Photoelectric Effect',
        explanation: 'At low photon energies (typically below ~100 keV) and in high-Z materials (like lead or tungsten), the photon is completely absorbed by a tightly-bound inner-shell electron, which is ejected with kinetic energy KE = hν − φ. This is why lead is such an effective shield at diagnostic X-ray energies.',
        animationId: 'photoelectric',
        checkQuestion: { q: 'The photoelectric effect is strongest in which combination of conditions?', options: ['High energy, low-Z material', 'Low energy, high-Z material', 'High energy, high-Z material only above 5 MeV', 'Energy and Z have no effect'], answer: 1, explanation: 'Photoelectric cross-section scales roughly as Z⁴⁻⁵/E³ — it is strongest for low-energy photons in high-Z absorbers.' },
      },
      {
        title: 'Compton Scattering',
        explanation: 'In the intermediate energy range (roughly 0.1–10 MeV), photons scatter off loosely-bound outer-shell electrons, losing part of their energy and changing direction while the electron recoils. This is the dominant interaction in soft tissue and water across most diagnostic and therapeutic energies.',
        animationId: 'compton',
        checkQuestion: { q: 'Compton scattering is the dominant interaction for photons in soft tissue mainly because:', options: ['Tissue is high-Z', 'Tissue is low-Z and the relevant energies fall in the Compton-dominant range', 'Tissue absorbs all photons completely', 'Compton scattering only happens in gases'], answer: 1, explanation: 'Tissue (low-Z, mostly H/C/O/N) has weak photoelectric interaction at typical diagnostic/therapeutic energies, leaving Compton scattering as the dominant process.' },
      },
      {
        title: 'Pair Production',
        explanation: 'Above the 1.022 MeV threshold (twice the electron rest-mass energy), a photon passing near a nucleus can convert directly into an electron-positron pair. This becomes significant only at high energies (LINAC therapy beams, high-energy cargo scanners) and in high-Z materials. The positron later annihilates, producing two 511 keV photons.',
        animationId: 'pair',
        checkQuestion: { q: 'What is the minimum photon energy required for pair production to occur?', options: ['100 keV', '511 keV', '1.022 MeV', '10 MeV'], answer: 2, explanation: '1.022 MeV = 2 × 0.511 MeV, the combined rest-mass energy of an electron and a positron — the physical minimum required by E = mc².' },
      },
      {
        title: 'Putting It Together: Which Interaction Dominates?',
        explanation: 'Below ~30 keV, the photoelectric effect dominates almost everywhere, especially in high-Z materials. From ~150 keV to 5 MeV, Compton scattering dominates in both low- and high-Z materials — this is the range most medical and industrial X-ray/gamma work happens in. Above ~5–10 MeV, pair production takes over in high-Z materials. This is exactly why lead is an excellent shield at diagnostic energies but a much less efficient (per unit weight) shield at very high LINAC energies, where Compton and pair production dominate instead.',
        checkQuestion: { q: 'For a 6 MV LINAC therapy beam interacting with a lead shield, which interaction is most significant?', options: ['Photoelectric effect only', 'Compton scattering (with growing pair production contribution)', 'No interaction occurs above 1 MeV', 'Only characteristic radiation'], answer: 1, explanation: 'At megavoltage energies, Compton scattering dominates across most materials, with pair production becoming increasingly significant in high-Z shields as energy rises further.' },
      },
    ],
  },
  {
    id: 'xray-tube-physics',
    title: 'How X-rays Are Born Inside a Tube',
    description: 'From the filament to the emitted beam — how an X-ray tube converts electrical energy into a usable X-ray spectrum.',
    steps: [
      {
        title: 'Anatomy of an X-ray Tube',
        explanation: 'An X-ray tube accelerates electrons, boiled off a heated filament (cathode), across a high-voltage gap toward a target (anode) — typically tungsten for its high melting point and high atomic number. Only when these fast electrons slam into the target does X-ray production actually happen, through two distinct mechanisms covered in the next two steps.',
      },
      {
        title: 'Bremsstrahlung: "Braking Radiation"',
        explanation: 'Most incident electrons don\'t hit a nucleus directly — instead, they pass close to one and are deflected and decelerated by its electric field. The kinetic energy lost in that deflection is emitted as an X-ray photon (ΔKE = hν). Because electrons can lose any amount of energy from near-zero up to their full kinetic energy, bremsstrahlung produces a continuous spectrum, up to a maximum photon energy set by kVp.',
        animationId: 'bremsstrahlung',
        checkQuestion: { q: 'Why does bremsstrahlung produce a continuous (not discrete) energy spectrum?', options: ['Because tungsten has no defined atomic structure', 'Because the amount of deflection — and therefore energy lost — varies continuously from one electron to the next', 'Because the tube filament vibrates randomly', 'It does not — bremsstrahlung is always monoenergetic'], answer: 1, explanation: 'Each electron\'s deflection angle and resulting energy loss is essentially random, so photon energies span a continuum from near zero up to the maximum set by the tube voltage (kVp).' },
      },
      {
        title: 'Characteristic Radiation',
        explanation: 'Occasionally, an incident electron directly knocks an inner-shell (K-shell) electron out of a target atom. When an outer-shell electron immediately falls in to fill that vacancy, it releases energy exactly equal to the difference between the two shell energies — as a photon of one very specific ("characteristic") energy. This is why mammography tubes use molybdenum (K-edge ~20 keV) rather than tungsten: the characteristic lines land exactly where they\'re most useful for imaging soft tissue.',
        checkQuestion: { q: 'Characteristic radiation photons have which property?', options: ['A continuous range of energies, like bremsstrahlung', 'One or a few very specific (discrete) energies determined by the target element\'s electron shell structure', 'Zero energy', 'Energies independent of the target material'], answer: 1, explanation: 'Characteristic X-rays appear as sharp spikes at energies fixed by the target element\'s atomic structure (e.g. tungsten K-α ≈ 59–67 keV) — unlike the smooth, continuous bremsstrahlung background.' },
      },
      {
        title: 'The Combined Spectrum',
        explanation: 'The beam that finally leaves the tube is the sum of both mechanisms: a broad, continuous bremsstrahlung background with sharp characteristic-radiation spikes superimposed at the target\'s specific energies. kVp sets the maximum photon energy and shifts the whole spectrum higher; mAs (tube current × time) scales the total number of photons without changing their energy distribution. Understanding this spectrum is the foundation for everything from image contrast to shielding design.',
        checkQuestion: { q: 'If kVp is increased while mAs stays constant, what happens to the emitted X-ray spectrum?', options: ['Photon quantity increases but energy stays the same', 'The maximum photon energy increases and the beam becomes more penetrating; photon quantity also tends to rise', 'Nothing changes', 'Only characteristic radiation is affected, not bremsstrahlung'], answer: 1, explanation: 'kVp directly sets the maximum possible photon energy (shifting and broadening the bremsstrahlung spectrum), which increases beam penetration — unlike mAs, which primarily controls photon quantity at a given energy distribution.' },
      },
    ],
  },
  {
    id: 'radiation-protection-basics',
    title: 'ALARA and the Fundamentals of Radiation Protection',
    description: 'The three core tools every radiation worker relies on — time, distance, and shielding — worked through with real numbers.',
    steps: [
      {
        title: 'The Three Pillars: Time, Distance, Shielding',
        explanation: 'Every radiation protection strategy comes down to three levers: minimise the TIME spent near a source, maximise the DISTANCE from it, and add SHIELDING between the source and the worker. Used together, these three tools can reduce almost any occupational exposure to a small fraction of the unshielded value.',
      },
      {
        title: 'Distance in Practice: The Inverse Square Law',
        explanation: 'For a point source, dose rate falls with the square of distance: dose rate ∝ 1/d². Worked example: if the dose rate at 1 m from a source is 100 μSv/h, then at 2 m it drops to 25 μSv/h (1/4), and at 5 m it drops to just 4 μSv/h (1/25). This is why radiographers step back during exposures and why remote handling tools exist for industrial gamma sources.',
        checkQuestion: { q: 'A dose rate of 80 μSv/h is measured at 1 m from a point source. What is the approximate dose rate at 4 m?', options: ['20 μSv/h', '5 μSv/h', '2.5 μSv/h', '80 μSv/h — distance does not matter'], answer: 1, explanation: 'At 4× the distance, dose rate falls to 1/4² = 1/16 of the original: 80 / 16 = 5 μSv/h.' },
      },
      {
        title: 'Shielding: Choosing the Right Material and Thickness',
        explanation: 'Shielding effectiveness is described by the Half-Value Layer (HVL) — the thickness that cuts intensity in half — and the Tenth-Value Layer (TVL ≈ 3.32 × HVL). High-Z, high-density materials like lead are efficient per unit thickness at lower photon energies (dominated by the photoelectric effect), while at very high LINAC energies, thick concrete becomes more practical despite needing much greater thickness, because bulk material and cost matter more than compactness in fixed installations like bunkers.',
        checkQuestion: { q: 'Why might a hospital LINAC vault use thick concrete walls rather than a thin lead shield, even though lead attenuates more per centimetre?', options: ['Concrete is a better conductor', 'At megavoltage energies the required thickness and cost trade-offs favour bulk, low-cost concrete over compact but expensive lead', 'Lead cannot be used near radiotherapy equipment', 'Concrete blocks neutrons but lead does not, and this is the only consideration'], answer: 1, explanation: 'At MV energies, the practical, economical choice for a large fixed structure is usually thick concrete, even though it requires far more thickness than lead would for the same attenuation — cost and structural factors dominate the decision alongside neutron shielding needs at higher energies.' },
      },
      {
        title: 'ALARA and Dose Limits',
        explanation: 'Regulatory dose limits (ICRP 103: 20 mSv/year occupational, 1 mSv/year public) are a legal ceiling — not a target. The ALARA principle requires pushing doses as far below that ceiling as reasonably achievable, balancing radiation risk against the cost and practicality of further reductions. In practice, this means combining time, distance, and shielding thoughtfully rather than relying on any single measure, and continuously reviewing procedures as technology and risk understanding improve.',
        checkQuestion: { q: 'A facility is operating well within its legal dose limits. Does ALARA require any further action?', options: ['No — being under the legal limit is always sufficient', 'Yes — ALARA requires continuing to reduce dose further where reasonably achievable, not just staying under the limit', 'ALARA only applies to members of the public', 'ALARA is optional guidance with no practical requirement'], answer: 1, explanation: 'ALARA is an optimisation duty, distinct from the legal dose limit — organisations are expected to keep pursuing reasonable further reductions even while compliant.' },
      },
    ],
  },
];
