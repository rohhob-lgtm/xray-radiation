import { useState, useMemo } from 'react';
import { Film as FilmIcon, ExternalLink, Youtube, BookOpen, Search, Sigma, Clock3, Languages } from 'lucide-react';
import { PhysicsFilm, type Film } from './film-player';
import { AnimationGallery, LangToggle, useLessonLang, type MicroAnim, type Lesson } from './anim-gallery';
import { EQUATIONS_AR, TIMELINES_AR, REF_STRINGS } from './lessons-ar-reference';
import { TUBE_LINAC_LESSONS } from './lessons-tube-linac';
import { ACCEL2_LESSONS } from './lessons-accel2';
import { NUCLEAR_LESSONS } from './lessons-nuclear';
import { TECHNOLOGY_LESSONS } from './lessons-technologies';
import { DETECTOR_LESSONS } from './lessons-detectors';
import { DETECTOR_ARRAY_LESSONS } from './lessons-detector-array';
import { TUBE_LESSONS_AR, type ArabicEntry } from './lessons-ar-tube';
import { LINAC_LESSONS_AR } from './lessons-ar-linac';
import { ACCEL2_LESSONS_AR } from './lessons-ar-accel2';
import { NUCLEAR_LESSONS_AR } from './lessons-ar-nuclear';
import { TECHNOLOGY_LESSONS_AR } from './lessons-ar-tech';
import { DETECTOR_LESSONS_AR } from './lessons-ar-detectors';
import { DETECTOR_ARRAY_LESSONS_AR } from './lessons-ar-detector-array';
import { ACCELERATOR_FILMS } from './films-accelerators';
import { NUCLEAR_FILMS } from './films-nuclear';
import { TECHNOLOGY_FILMS } from './films-technologies';
import { ACCELERATOR_PART_ANIMS } from './parts-accelerators';
import { NUCLEAR_PART_ANIMS } from './parts-nuclear';
import { TECHNOLOGY_ANIMS } from './parts-technologies';
import { DETECTOR_ANIMS } from './parts-detectors';
import { DETECTOR_ARRAY_ANIMS } from './parts-detector-array';

// ═══════════════════════════════════════════════════════════════════════════════
// Media shelf — binds each section id to its film, its part animations, its
// curated external video searches, key equations and a history timeline.
// ═══════════════════════════════════════════════════════════════════════════════

export const ALL_FILMS: Film[] = [...ACCELERATOR_FILMS, ...NUCLEAR_FILMS, ...TECHNOLOGY_FILMS];

/** Mini-lessons are authored separately and attached here by anim id. */
const ALL_LESSONS: Record<string, Lesson> = {
  ...TUBE_LINAC_LESSONS, ...ACCEL2_LESSONS, ...NUCLEAR_LESSONS,
  ...TECHNOLOGY_LESSONS, ...DETECTOR_LESSONS, ...DETECTOR_ARRAY_LESSONS,
};

/** Arabic translations, attached the same way. */
const ALL_LESSONS_AR: Record<string, ArabicEntry> = {
  ...TUBE_LESSONS_AR, ...LINAC_LESSONS_AR, ...ACCEL2_LESSONS_AR,
  ...NUCLEAR_LESSONS_AR, ...TECHNOLOGY_LESSONS_AR, ...DETECTOR_LESSONS_AR,
  ...DETECTOR_ARRAY_LESSONS_AR,
};

export const ALL_PART_ANIMS: MicroAnim[] = [
  ...ACCELERATOR_PART_ANIMS, ...NUCLEAR_PART_ANIMS, ...TECHNOLOGY_ANIMS, ...DETECTOR_ANIMS, ...DETECTOR_ARRAY_ANIMS,
].map(a => {
  const en = ALL_LESSONS[a.id];
  const ar = ALL_LESSONS_AR[a.id];
  if (!en && !ar) return a;
  return {
    ...a,
    ...(en ? { lesson: en } : {}),
    ...(ar ? { lessonAr: ar.lesson, partAr: ar.part, summaryAr: ar.summary } : {}),
  };
});

/** How many components already have an Arabic lesson. */
export const ARABIC_COVERAGE = Object.keys(ALL_LESSONS_AR).length;

/** section id → film id */
const FILM_BY_TOPIC: Record<string, string> = {
  'xray-tube': 'film-xray-tube',
  'linac': 'film-linac',
  'betatron': 'film-betatron',
  'cyclotron': 'film-cyclotron',
  'synchrotron': 'film-synchrotron',
  'van-de-graaff': 'film-vdg',
  'radioisotopes': 'film-isotopes',
  'neutron': 'film-neutron',
  'gamma-irradiators': 'film-irradiator',
  'industrial-xray': 'film-industrial',
  'security': 'film-security',
  'xray-technologies': 'film-technologies',
  'detectors': 'film-detectors',
};

export const filmFor = (topic: string) => ALL_FILMS.find(f => f.id === FILM_BY_TOPIC[topic]) || null;
export const partsFor = (topic: string) => ALL_PART_ANIMS.filter(a => a.group === topic);

// ─── External video shelf ─────────────────────────────────────────────────────
// Each entry opens a pre-built search on a video platform or an official body's
// own site, so links never rot the way hard-coded video ids do.
interface VideoRef { title: string; channel: string; query: string; kind: 'video' | 'lecture' | 'official'; mins?: string }

const YT = (q: string) => `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`;

export const VIDEO_SHELF: Record<string, VideoRef[]> = {
  'xray-tube': [
    { title: 'How an X-ray tube actually works — cutaway', channel: 'Engineering channels', query: 'x-ray tube cutaway how it works rotating anode', kind: 'video', mins: '8–15 min' },
    { title: 'Rotating anode manufacture and failure modes', channel: 'Tube manufacturers', query: 'rotating anode x-ray tube manufacturing failure', kind: 'video', mins: '10–20 min' },
    { title: 'Bremsstrahlung and characteristic radiation lecture', channel: 'University physics', query: 'bremsstrahlung characteristic x-ray production lecture', kind: 'lecture', mins: '30–50 min' },
    { title: 'Beam filtration, HVL and half-value layer measurement', channel: 'Medical physics', query: 'half value layer HVL measurement x-ray beam quality', kind: 'lecture', mins: '20–40 min' },
    { title: 'IAEA diagnostic radiology physics handbook', channel: 'IAEA', query: 'IAEA diagnostic radiology physics handbook x-ray tube', kind: 'official' },
  ],
  'linac': [
    { title: 'Inside a medical linear accelerator', channel: 'Hospital / vendor tours', query: 'inside medical linear accelerator linac tour waveguide', kind: 'video', mins: '10–25 min' },
    { title: 'RF acceleration and travelling-wave structures', channel: 'Accelerator schools', query: 'RF linear accelerator travelling wave structure lecture CERN', kind: 'lecture', mins: '45–60 min' },
    { title: 'Magnetron vs klystron explained', channel: 'RF engineering', query: 'magnetron vs klystron explained microwave power tube', kind: 'video', mins: '10–20 min' },
    { title: 'Cargo inspection LINAC dual-energy imaging', channel: 'Security industry', query: 'cargo inspection linac dual energy container scanning', kind: 'video', mins: '5–15 min' },
    { title: 'CERN accelerator school lecture archive', channel: 'CERN', query: 'CERN accelerator school lectures linac', kind: 'official' },
  ],
  'betatron': [
    { title: 'Betatron principle — induction acceleration', channel: 'Physics education', query: 'betatron principle induction acceleration explained', kind: 'video', mins: '8–20 min' },
    { title: 'Kerst betatron history and the 2:1 condition', channel: 'History of physics', query: 'Kerst betatron history betatron condition', kind: 'lecture', mins: '20–40 min' },
    { title: 'Portable betatron for thick-section NDT', channel: 'NDT industry', query: 'betatron industrial radiography thick steel NDT', kind: 'video', mins: '5–15 min' },
  ],
  'cyclotron': [
    { title: 'Cyclotron working principle animation', channel: 'Physics education', query: 'cyclotron working principle animation dees magnetic field', kind: 'video', mins: '5–15 min' },
    { title: 'Medical cyclotron and PET isotope production tour', channel: 'Nuclear medicine', query: 'medical cyclotron PET isotope production F-18 FDG tour', kind: 'video', mins: '10–25 min' },
    { title: 'Isochronous cyclotrons and relativistic effects', channel: 'Accelerator physics', query: 'isochronous cyclotron relativistic mass increase lecture', kind: 'lecture', mins: '30–60 min' },
    { title: 'IAEA cyclotron produced radionuclides', channel: 'IAEA', query: 'IAEA cyclotron produced radionuclides publication', kind: 'official' },
  ],
  'synchrotron': [
    { title: 'How a synchrotron light source works', channel: 'Light source facilities', query: 'how synchrotron light source works storage ring beamline', kind: 'video', mins: '5–20 min' },
    { title: 'Undulators, wigglers and brightness', channel: 'Accelerator physics', query: 'undulator wiggler synchrotron radiation brightness lecture', kind: 'lecture', mins: '40–60 min' },
    { title: 'Beamline tour — from front end to detector', channel: 'ESRF / Diamond / ALS', query: 'synchrotron beamline tour monochromator detector', kind: 'video', mins: '10–30 min' },
    { title: 'Phase contrast and diffraction imaging applications', channel: 'Imaging science', query: 'synchrotron phase contrast imaging diffraction explosives detection', kind: 'lecture', mins: '20–45 min' },
  ],
  'van-de-graaff': [
    { title: 'Van de Graaff generator — how charge accumulates', channel: 'Physics education', query: 'Van de Graaff generator how it works charge belt terminal', kind: 'video', mins: '5–15 min' },
    { title: 'Tandem accelerator and stripping explained', channel: 'Nuclear physics labs', query: 'tandem Van de Graaff accelerator stripper foil explained', kind: 'lecture', mins: '15–40 min' },
    { title: 'Accelerator mass spectrometry for radiocarbon dating', channel: 'AMS laboratories', query: 'accelerator mass spectrometry radiocarbon dating AMS tandem', kind: 'video', mins: '10–25 min' },
  ],
  'radioisotopes': [
    { title: 'Industrial gamma radiography — projector operation', channel: 'NDT training', query: 'industrial gamma radiography projector Ir-192 operation safety', kind: 'video', mins: '10–25 min' },
    { title: 'Sealed source construction and leak testing', channel: 'Radiation safety', query: 'sealed radioactive source construction ISO 2919 leak test', kind: 'lecture', mins: '15–35 min' },
    { title: 'Radiography accident case studies', channel: 'IAEA / regulators', query: 'IAEA radiography source accident case study lessons learned', kind: 'official' },
    { title: 'Transport of radioactive material — SSR-6', channel: 'IAEA', query: 'IAEA SSR-6 transport of radioactive material regulations', kind: 'official' },
  ],
  'neutron': [
    { title: 'Neutron generator (D-T) principle and applications', channel: 'Nuclear instrumentation', query: 'deuterium tritium neutron generator principle applications', kind: 'video', mins: '8–20 min' },
    { title: 'Neutron moderation and thermalisation explained', channel: 'Reactor physics', query: 'neutron moderation thermalisation elastic scattering lecture', kind: 'lecture', mins: '30–50 min' },
    { title: 'Neutron detection after the He-3 shortage', channel: 'Detector research', query: 'helium-3 shortage neutron detection alternatives boron lithium', kind: 'lecture', mins: '20–45 min' },
    { title: 'Neutron interrogation of cargo containers', channel: 'Security research', query: 'pulsed fast neutron analysis cargo interrogation explosives', kind: 'video', mins: '5–20 min' },
  ],
  'gamma-irradiators': [
    { title: 'Inside a Co-60 gamma irradiation plant', channel: 'Sterilisation industry', query: 'cobalt-60 gamma irradiation facility tour sterilization', kind: 'video', mins: '5–20 min' },
    { title: 'Food irradiation — process and regulation', channel: 'Food science / IAEA', query: 'food irradiation process regulation gamma cobalt-60', kind: 'lecture', mins: '15–40 min' },
    { title: 'Dose mapping and ISO 11137 validation', channel: 'Sterilisation science', query: 'ISO 11137 dose mapping validation radiation sterilization', kind: 'lecture', mins: '20–45 min' },
    { title: 'IAEA irradiator safety publications', channel: 'IAEA', query: 'IAEA gamma irradiator safety TECDOC 1313', kind: 'official' },
  ],
  'industrial-xray': [
    { title: 'Radiographic testing of welds — full technique', channel: 'NDT training', query: 'radiographic testing welds technique RT level 2 training', kind: 'lecture', mins: '30–60 min' },
    { title: 'IQI selection and sensitivity demonstration', channel: 'NDT training', query: 'IQI penetrameter selection radiography sensitivity EN 462', kind: 'video', mins: '10–25 min' },
    { title: 'Digital radiography vs film — transition guidance', channel: 'NDT industry', query: 'digital radiography DDA vs film ISO 17636-2 comparison', kind: 'lecture', mins: '20–45 min' },
    { title: 'Industrial CT metrology of castings', channel: 'Metrology', query: 'industrial computed tomography metrology casting inspection', kind: 'video', mins: '10–30 min' },
  ],
  'security': [
    { title: 'How airport baggage screening works', channel: 'Security technology', query: 'how airport x-ray baggage screening works dual energy', kind: 'video', mins: '5–20 min' },
    { title: 'CT explosive detection systems for hold baggage', channel: 'Aviation security', query: 'hold baggage CT explosive detection system EDS airport', kind: 'video', mins: '8–25 min' },
    { title: 'Dual-energy material discrimination physics', channel: 'Imaging physics', query: 'dual energy x-ray material discrimination effective atomic number', kind: 'lecture', mins: '20–45 min' },
    { title: 'Radiation portal monitors at borders', channel: 'Nuclear security', query: 'radiation portal monitor border nuclear security detection', kind: 'video', mins: '5–20 min' },
    { title: 'IAEA nuclear security series', channel: 'IAEA', query: 'IAEA nuclear security series detection radioactive material', kind: 'official' },
  ],
  'xray-technologies': [
    { title: 'Backscatter X-ray imaging explained', channel: 'Security technology', query: 'x-ray backscatter imaging how it works flying spot', kind: 'video', mins: '5–20 min' },
    { title: 'Compton scattering and Klein–Nishina', channel: 'Physics lectures', query: 'Compton scattering Klein-Nishina angular distribution lecture', kind: 'lecture', mins: '30–60 min' },
    { title: 'X-ray diffraction imaging for substance ID', channel: 'Detection research', query: 'x-ray diffraction imaging explosives identification security', kind: 'lecture', mins: '20–45 min' },
    { title: 'Phase contrast and dark-field imaging', channel: 'Imaging science', query: 'grating interferometry phase contrast dark field x-ray imaging', kind: 'lecture', mins: '25–50 min' },
    { title: 'Dual-energy and spectral CT principles', channel: 'Medical physics', query: 'dual energy spectral CT photon counting principles lecture', kind: 'lecture', mins: '30–60 min' },
    { title: 'NIST XCOM attenuation database', channel: 'NIST', query: 'NIST XCOM photon cross sections database', kind: 'official' },
  ],
  'detectors': [
    { title: 'How a photomultiplier tube works', channel: 'Instrumentation', query: 'photomultiplier tube how it works dynode chain explained', kind: 'video', mins: '5–20 min' },
    { title: 'Radiation detection and measurement — full course', channel: 'University courses', query: 'radiation detection and measurement course Knoll lectures', kind: 'lecture', mins: '10+ hours' },
    { title: 'Scintillators, photodiodes and SiPMs compared', channel: 'Detector research', query: 'scintillator photodiode SiPM comparison radiation detector', kind: 'lecture', mins: '20–45 min' },
    { title: 'CdTe / CZT direct conversion detectors', channel: 'Detector research', query: 'CdTe CZT direct conversion x-ray detector photon counting', kind: 'lecture', mins: '20–45 min' },
    { title: 'Flat panel detectors — a-Si and a-Se', channel: 'Medical physics', query: 'flat panel detector amorphous silicon selenium digital radiography', kind: 'lecture', mins: '20–40 min' },
    { title: 'DQE, MTF and NPS explained', channel: 'Medical physics', query: 'DQE MTF NPS detector performance explained medical imaging', kind: 'lecture', mins: '25–50 min' },
    { title: 'Gamma spectroscopy with NaI and HPGe', channel: 'Nuclear instrumentation', query: 'gamma spectroscopy NaI HPGe pulse height spectrum tutorial', kind: 'video', mins: '15–40 min' },
  ],
};

const KIND_STYLE: Record<VideoRef['kind'], { label: string; cls: string }> = {
  video:    { label: 'Video',    cls: 'text-red-400 border-red-500/30 bg-red-500/10' },
  lecture:  { label: 'Lecture',  cls: 'text-violet-400 border-violet-500/30 bg-violet-500/10' },
  official: { label: 'Official', cls: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
};

export function VideoShelf({ topic }: { topic: string }) {
  const [lang] = useLessonLang();
  const ar = lang === 'ar';
  const S = REF_STRINGS[ar ? 'ar' : 'en'];
  const refs = VIDEO_SHELF[topic] || [];
  if (refs.length === 0) return null;
  return (
    <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/70 bg-card/60">
        <Youtube className="h-4 w-4 text-red-400" />
        <div className="flex-1">
          <div className="text-xs font-bold text-foreground" dir={ar ? 'rtl' : 'ltr'}>{S.watch}</div>
          <div className="text-[10px] text-muted-foreground" dir={ar ? 'rtl' : 'ltr'}>{S.watchSub}</div>
        </div>
        <span className="text-[10px] font-mono text-muted-foreground">{refs.length} {S.topics}</span>
      </div>
      <div className="grid sm:grid-cols-2 gap-2 p-3">
        {refs.map(r => (
          <a key={r.title} href={YT(r.query)} target="_blank" rel="noopener noreferrer"
            className="group rounded-lg border border-border/70 bg-background/40 px-3 py-2.5 hover:border-primary/50 transition-colors">
            <div className="flex items-start gap-2">
              <div className="h-8 w-8 rounded-md bg-card border border-border flex items-center justify-center shrink-0">
                {r.kind === 'official' ? <BookOpen className="h-3.5 w-3.5 text-emerald-400" /> : <FilmIcon className="h-3.5 w-3.5 text-red-400" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-semibold text-foreground leading-snug">{r.title}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">{r.channel}</div>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border font-mono ${KIND_STYLE[r.kind].cls}`}>
                  {ar ? (r.kind === 'video' ? S.video : r.kind === 'lecture' ? S.lecture : S.official) : KIND_STYLE[r.kind].label}
                </span>
                  {r.mins && <span className="text-[9px] font-mono text-muted-foreground flex items-center gap-0.5"><Clock3 className="h-2.5 w-2.5" />{r.mins}</span>}
                </div>
              </div>
              <ExternalLink className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

// ─── Key equations block ──────────────────────────────────────────────────────
export interface Equation { expr: string; meaning: string; note?: string }

export const EQUATIONS: Record<string, Equation[]> = {
  'xray-tube': [
    { expr: 'J = A · T² · e^(−φ/kT)', meaning: 'Richardson–Dushman thermionic emission current density', note: 'Why a small filament-temperature change swings mA hard' },
    { expr: 'E_max = e · kVp', meaning: 'Bremsstrahlung endpoint energy (Duane–Hunt limit)', note: 'λ_min = 1239.8 / kVp  (nm)' },
    { expr: 'Efficiency ≈ 1.1 × 10⁻⁹ · Z · V', meaning: 'Fraction of beam power converted to X-rays', note: '≈ 1 % at 100 kV on tungsten' },
    { expr: 'f_eff = f_actual · sin θ', meaning: 'Line-focus principle — effective focal spot', note: 'Smaller anode angle → sharper image, smaller field' },
    { expr: 'Ug = f · b / a', meaning: 'Geometric unsharpness', note: 'Set by geometry before any exposure is made' },
  ],
  'linac': [
    { expr: 'ΔE = q · E_z · L · cos φ_s', meaning: 'Energy gain in an RF structure at synchronous phase', note: '10–15 MeV per metre typical' },
    { expr: 'β = v/c, γ = 1/√(1−β²)', meaning: 'Relativistic factors — electrons are relativistic within centimetres', note: 'γ ≈ 1 + E[MeV]/0.511' },
    { expr: 'p = 0.2998 · B · ρ', meaning: 'Magnetic rigidity (GeV/c, T, m) for the bending magnet', note: 'Sets the bend radius for a given energy' },
    { expr: 'D ∝ pulse rate × pulse charge', meaning: 'Dose rate scales with duty cycle', note: 'Why FFF modes reach 2–4× the dose rate' },
  ],
  'betatron': [
    { expr: 'B̄(inside orbit) = 2 · B(r₀)', meaning: 'The betatron condition for a constant-radius orbit', note: 'Kerst & Serber, 1941' },
    { expr: '∮E·dl = −dΦ/dt', meaning: 'Faraday induction supplies the accelerating field', note: 'No electrodes are involved at all' },
    { expr: 'n = −(r/B)(∂B/∂r), 0 < n < 1', meaning: 'Field index for weak focusing in both planes', note: 'Outside this range the beam is lost' },
  ],
  'cyclotron': [
    { expr: 'f = q B / (2π m)', meaning: 'Cyclotron resonance frequency', note: 'Independent of radius — non-relativistically' },
    { expr: 'r = m v / (q B)', meaning: 'Orbit radius grows with momentum', note: 'The spiral you see in the film' },
    { expr: 'E = (q B R)² / (2 m)', meaning: 'Final energy from extraction radius and field', note: 'Energy scales with R² — magnets get heavy fast' },
    { expr: 'f_iso(r) = f₀ / γ(r)', meaning: 'Isochronism requires B to rise with radius', note: 'Achieved with hill-and-valley sectors' },
  ],
  'synchrotron': [
    { expr: 'θ ≈ 1/γ', meaning: 'Opening angle of the synchrotron radiation cone', note: '≈ 0.17 mrad at 3 GeV' },
    { expr: 'P ∝ E⁴ / (m⁴ ρ²)', meaning: 'Radiated power — why electrons radiate and protons barely do', note: 'Mass to the fourth power in the denominator' },
    { expr: 'E_c = 3ħcγ³ / (2ρ)', meaning: 'Critical photon energy of the emitted spectrum', note: 'Half the power lies above it' },
    { expr: 'λ = (λ_u / 2γ²)(1 + K²/2 + γ²θ²)', meaning: 'Undulator fundamental wavelength', note: 'Change the magnet gap to tune the photon energy' },
  ],
  'van-de-graaff': [
    { expr: 'V = Q / C', meaning: 'Terminal voltage from accumulated charge', note: 'Rises until leakage equals charging current' },
    { expr: 'E_final = (1 + q) · V', meaning: 'Tandem energy gain with charge state q after stripping', note: 'The whole reason tandems exist' },
    { expr: 'E_breakdown(air) ≈ 3 MV/m', meaning: 'Why the column lives in pressurised SF₆', note: 'SF₆ at 5–10 bar raises the ceiling to ≈ 25 MV' },
  ],
  'radioisotopes': [
    { expr: 'A(t) = A₀ · e^(−λt),  λ = ln2 / t½', meaning: 'Exponential decay law', note: 'Nothing an operator does changes λ' },
    { expr: 'İ₂ = İ₁ · (d₁/d₂)²', meaning: 'Inverse square law', note: 'Double the distance, quarter the dose rate' },
    { expr: 'İ = Γ · A / d²', meaning: 'Dose rate from a point source (Γ = specific gamma constant)', note: 'Co-60 Γ ≈ 0.351 mSv·m²/(h·GBq)' },
    { expr: 'I = I₀ · e^(−µx),  HVL = ln2/µ', meaning: 'Attenuation through shielding', note: 'Ir-192 HVL ≈ 2.5 mm Pb' },
    { expr: 'TI = İ(1 m) [µSv/h] / 10', meaning: 'Transport index for package labelling', note: 'Rounded up to one decimal place' },
  ],
  'neutron': [
    { expr: 'd + t → ⁴He (3.5 MeV) + n (14.1 MeV)', meaning: 'The D-T fusion reaction in a sealed generator', note: 'Monoenergetic and switchable' },
    { expr: 'ξ = 1 + (A−1)²/(2A) · ln((A−1)/(A+1))', meaning: 'Average logarithmic energy decrement per collision', note: 'Hydrogen ξ = 1 — the best moderator per collision' },
    { expr: 'n_collisions ≈ ln(E₀/E) / ξ', meaning: 'Collisions needed to thermalise', note: '≈ 18 in water from 2 MeV' },
    { expr: 'H = Σ w_R · D_R', meaning: 'Equivalent dose with neutron radiation weighting up to 20', note: 'Same absorbed dose, far greater biological effect' },
  ],
  'gamma-irradiators': [
    { expr: 'D = İ · t', meaning: 'Absorbed dose is dose rate times residence time', note: 'Conveyor speed is the process control' },
    { expr: 'DUR = D_max / D_min', meaning: 'Dose uniformity ratio across the load', note: 'Industrial target below 1.5' },
    { expr: 'A(t) = A₀ · e^(−λt) → −12.3 %/y', meaning: 'Co-60 decay drives the reload cycle', note: 'Process times must be recalculated as the source ages' },
  ],
  'industrial-xray': [
    { expr: 'Ug = f · b / a', meaning: 'Geometric unsharpness', note: 'Object against the detector, source far away' },
    { expr: 'I = I₀ · e^(−µx)', meaning: 'Beer–Lambert attenuation through the section', note: 'Contrast comes from differences in µx' },
    { expr: 'BUR = (1 + b/a)', meaning: 'Projection magnification', note: 'Used deliberately in micro-focus CT' },
    { expr: 'Sensitivity % = (smallest visible IQI / thickness) × 100', meaning: 'Demonstrated radiographic sensitivity', note: 'The code sets the required value' },
  ],
  'security': [
    { expr: 'R = ln(I₀/I)_HE / ln(I₀/I)_LE', meaning: 'Dual-energy ratio → effective atomic number', note: 'Basis of the orange / green / blue convention' },
    { expr: 'µ_photoelectric ∝ Z³·⁵ / E³', meaning: 'Low-energy channel is Z-sensitive', note: 'Why the low-energy frame carries the material information' },
    { expr: 'µ_Compton ∝ ρ · Z/A', meaning: 'High-energy channel tracks density', note: 'Nearly Z-independent above a few hundred keV' },
    { expr: 'CT number = 1000 · (µ − µ_w)/µ_w', meaning: 'Hounsfield-style scaling used by EDS algorithms', note: 'A measured property per voxel, not a shadow' },
  ],
  'xray-technologies': [
    { expr: 'E′ = E / (1 + (E/m₀c²)(1 − cos θ))', meaning: 'Compton scattered photon energy versus angle', note: 'Energy encodes angle — the basis of Compton tomography' },
    { expr: 'dσ/dΩ (Klein–Nishina)', meaning: 'Angular distribution of Compton scattering', note: 'Decides whether backscatter imaging is even possible at a given energy' },
    { expr: 'nλ = 2 d sin θ', meaning: 'Bragg condition — coherent scatter from a crystal lattice', note: 'The molecular fingerprint used in XRD imaging' },
    { expr: 'λ [nm] = 1.2398 / E [keV]', meaning: 'Photon wavelength from energy', note: 'Needed to turn a diffraction angle into a d-spacing' },
    { expr: 'µ/ρ = photoelectric + Compton + pair', meaning: 'Total mass attenuation as a sum of channels', note: 'Which term dominates picks the imaging technology' },
    { expr: 'SPR = scatter / primary', meaning: 'Scatter-to-primary ratio', note: 'Above ~1 the image is mostly noise — grid or air gap needed' },
  ],
  'detectors': [
    { expr: 'N = E_dep / w', meaning: 'Carriers created per interaction (w = pair-creation energy)', note: 'CdTe w ≈ 4.4 eV, Ge 2.96 eV, Si 3.6 eV, gas ≈ 30 eV' },
    { expr: 'ΔE/E ∝ 1/√N', meaning: 'Energy resolution improves with more carriers', note: 'Exactly why HPGe beats NaI by more than an order of magnitude' },
    { expr: 'G = δⁿ', meaning: 'PMT gain from n dynodes with secondary yield δ', note: 'δ ≈ 4, n ≈ 10 → gain ≈ 10⁶' },
    { expr: 'm = n_true / (1 + n_true·τ)', meaning: 'Count-rate loss from dead time τ', note: 'Why a GM tube reads LOW in an intense field' },
    { expr: 'DQE(f) = SNR²_out / SNR²_in', meaning: 'Detective quantum efficiency versus spatial frequency', note: 'The only honest way to compare two imaging detectors' },
    { expr: 'ENC (electrons RMS)', meaning: 'Equivalent noise charge of the front-end chain', note: 'Rises with sensor capacitance and falls with longer shaping' },
  ],
};

export function KeyEquations({ topic }: { topic: string }) {
  const [lang] = useLessonLang();
  const eqs = EQUATIONS[topic] || [];
  const arList = EQUATIONS_AR[topic];
  const ar = lang === 'ar' && !!arList;
  const S = REF_STRINGS[ar ? 'ar' : 'en'];
  if (eqs.length === 0) return null;
  return (
    <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/70 bg-card/60">
        <Sigma className="h-4 w-4 text-amber-400" />
        <div className="text-xs font-bold text-foreground">{S.equations}</div>
      </div>
      <div className="divide-y divide-border/50">
        {eqs.map((e, i) => {
          const t = ar ? arList[i] : undefined;
          return (
            <div key={e.expr} className="px-4 py-2.5">
              <div className="font-mono text-[12px] text-amber-300" dir="ltr">{e.expr}</div>
              <div className="text-[11px] text-foreground mt-0.5" dir={ar ? 'rtl' : 'ltr'}>{t?.meaning ?? e.meaning}</div>
              {(t?.note ?? e.note) && (
                <div className="text-[10px] text-muted-foreground mt-0.5" dir={ar ? 'rtl' : 'ltr'}>{t?.note ?? e.note}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── History timelines ────────────────────────────────────────────────────────
export const TIMELINES: Record<string, { year: string; event: string }[]> = {
  'xray-tube': [
    { year: '1895', event: 'Röntgen observes X-rays from a Crookes gas discharge tube' },
    { year: '1913', event: 'Coolidge introduces the hot-cathode high-vacuum tube — the modern architecture' },
    { year: '1929', event: 'Rotating anode patented, multiplying tolerable power' },
    { year: '1970s', event: 'Metal-ceramic envelopes and grid-controlled switching enter service' },
    { year: '1990s', event: 'High-frequency inverter generators replace three-phase units' },
    { year: '2000s', event: 'Liquid-metal spiral-groove bearings enable continuous high-speed CT operation' },
  ],
  'linac': [
    { year: '1928', event: 'Wideröe proposes the drift-tube RF linear accelerator' },
    { year: '1945', event: 'Alvarez builds the first practical RF LINAC at Berkeley' },
    { year: '1952', event: 'First clinical electron LINAC treats a patient (Hammersmith, London)' },
    { year: '1960s', event: 'SLAC two-mile machine proves large-scale RF acceleration' },
    { year: '1990s', event: 'Multileaf collimators make conformal and intensity-modulated therapy routine' },
    { year: '2000s', event: 'Dual-energy cargo LINACs become the backbone of container security' },
  ],
  'betatron': [
    { year: '1922', event: 'Slepian patents an induction acceleration concept' },
    { year: '1940', event: 'Kerst builds the first working betatron at Illinois (2.3 MeV)' },
    { year: '1941', event: 'Kerst and Serber publish the orbit-stability theory' },
    { year: '1950s', event: 'Betatrons used clinically for radiotherapy and for heavy-section NDT' },
    { year: '1970s+', event: 'LINACs displace betatrons in nearly all applications' },
  ],
  'cyclotron': [
    { year: '1930', event: 'Lawrence and Livingston demonstrate the first cyclotron' },
    { year: '1939', event: 'Lawrence receives the Nobel Prize for the cyclotron' },
    { year: '1945', event: 'Synchrocyclotron concept resolves the relativistic limit' },
    { year: '1950s', event: 'Isochronous (AVF) cyclotrons deliver continuous relativistic beams' },
    { year: '1970s', event: 'Compact medical cyclotrons begin on-site PET isotope production' },
    { year: '2000s', event: 'Self-shielded hospital cyclotrons make FDG routine worldwide' },
  ],
  'synchrotron': [
    { year: '1947', event: 'Synchrotron radiation observed directly at General Electric' },
    { year: '1960s', event: 'First-generation "parasitic" use of radiation from particle-physics rings' },
    { year: '1980s', event: 'Second generation — rings built specifically as light sources' },
    { year: '1990s', event: 'Third generation — long straight sections built for insertion devices' },
    { year: '2009+', event: 'X-ray free-electron lasers deliver femtosecond coherent pulses' },
    { year: '2016+', event: 'Fourth-generation multi-bend achromat rings push emittance down further' },
  ],
  'van-de-graaff': [
    { year: '1929', event: 'Van de Graaff builds his first electrostatic generator' },
    { year: '1933', event: 'Round Hill twin-sphere machine reaches the megavolt range' },
    { year: '1950s', event: 'Tandem principle doubles energy from the same terminal voltage' },
    { year: '1960s', event: 'Pelletron chains replace rubber belts for reliability' },
    { year: '1977', event: 'Accelerator mass spectrometry transforms radiocarbon dating' },
  ],
  'radioisotopes': [
    { year: '1896', event: 'Becquerel discovers radioactivity in uranium salts' },
    { year: '1898', event: 'The Curies isolate polonium and radium' },
    { year: '1950s', event: 'Reactor-produced Co-60 and Ir-192 replace radium in industry' },
    { year: '1980s', event: 'Goiânia and other orphan-source accidents drive modern source security' },
    { year: '2003+', event: 'IAEA Code of Conduct on the Safety and Security of Radioactive Sources' },
  ],
  'neutron': [
    { year: '1932', event: 'Chadwick identifies the neutron' },
    { year: '1942', event: 'First self-sustaining chain reaction — Chicago Pile-1' },
    { year: '1950s', event: 'Sealed D-T generators developed for well logging' },
    { year: '1970s', event: 'Cf-252 becomes available as a compact spontaneous-fission source' },
    { year: '2009', event: 'Helium-3 shortage forces a redesign of portal-monitor detection' },
  ],
  'gamma-irradiators': [
    { year: '1950s', event: 'First industrial Co-60 irradiation plants enter service' },
    { year: '1960s', event: 'Medical device sterilisation by gamma becomes an industry' },
    { year: '1980s', event: 'Food irradiation approvals expand under WHO/FAO/IAEA review' },
    { year: '1990s', event: 'ISO 11137 formalises dose validation for sterilisation' },
    { year: '2010s', event: 'E-beam and X-ray plants begin displacing Co-60 for some products' },
  ],
  'industrial-xray': [
    { year: '1896', event: 'First industrial radiographs of metal castings' },
    { year: '1920s', event: 'Radiography adopted for pressure-vessel and weld inspection' },
    { year: '1950s', event: 'Codes (ASME, API) formalise radiographic acceptance criteria' },
    { year: '1980s', event: 'Computed radiography imaging plates arrive' },
    { year: '2000s', event: 'Digital detector arrays and industrial CT become mainstream' },
  ],
  'security': [
    { year: '1970s', event: 'X-ray screening of cabin baggage introduced after hijackings' },
    { year: '1990s', event: 'Dual-energy discrimination brings material colour coding to consoles' },
    { year: '2000s', event: 'CT-based explosive detection deployed for hold baggage' },
    { year: '2001+', event: 'Cargo and vehicle LINAC scanning expands rapidly worldwide' },
    { year: '2010s', event: 'Backscatter body scanners replaced by privacy-preserving MMW with ATR' },
    { year: '2018+', event: 'Computed tomography reaches the cabin-baggage checkpoint' },
  ],
  'xray-technologies': [
    { year: '1923', event: 'Compton demonstrates the wavelength shift of scattered X-rays' },
    { year: '1929', event: 'Klein and Nishina derive the relativistic scattering cross-section' },
    { year: '1970s', event: 'First backscatter imaging systems built for single-sided inspection' },
    { year: '1980s', event: 'Dual-energy transmission brings material discrimination to screening' },
    { year: '1990s', event: 'Coherent-scatter (XRD) imaging demonstrated for explosive identification' },
    { year: '2000s', event: 'Grating interferometry brings phase contrast to ordinary X-ray tubes' },
    { year: '2010s+', event: 'Photon-counting spectral detectors move from research to product' },
  ],
  'detectors': [
    { year: '1908', event: 'Geiger and Rutherford build the first electrical particle counter' },
    { year: '1928', event: 'Geiger–Müller tube reaches its familiar form' },
    { year: '1936', event: 'First practical photomultiplier tubes' },
    { year: '1948', event: 'Hofstadter shows NaI(Tl) is an excellent gamma scintillator' },
    { year: '1960s', event: 'Lithium-drifted and then high-purity germanium transform spectroscopy' },
    { year: '1980s', event: 'Photostimulable phosphor plates introduce computed radiography' },
    { year: '1990s', event: 'a-Si flat panels make direct digital radiography practical' },
    { year: '2000s', event: 'CdTe/CZT and silicon photomultipliers enter mainstream instruments' },
    { year: '2021', event: 'First photon-counting CT scanner receives clinical approval' },
  ],
};

export function HistoryTimeline({ topic }: { topic: string }) {
  const [lang] = useLessonLang();
  const items = TIMELINES[topic] || [];
  const arList = TIMELINES_AR[topic];
  const ar = lang === 'ar' && !!arList;
  const S = REF_STRINGS[ar ? 'ar' : 'en'];
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/70 bg-card/60">
        <Clock3 className="h-4 w-4 text-sky-400" />
        <div className="text-xs font-bold text-foreground">{S.timeline}</div>
      </div>
      <div className="p-4">
        <div className="relative pl-5">
          <div className="absolute left-1.5 top-1 bottom-1 w-px bg-border" />
          {items.map((i, k) => (
            <div key={i.year + i.event} className="relative pb-3 last:pb-0">
              <span className="absolute -left-[15px] top-1 h-2 w-2 rounded-full bg-sky-400 ring-2 ring-background" />
              <div className="text-[11px] font-mono font-bold text-sky-400" dir="ltr">{i.year}</div>
              <div className="text-[11px] text-muted-foreground leading-relaxed" dir={ar ? 'rtl' : 'ltr'}>
                {(ar ? arList[k] : undefined) ?? i.event}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Combined per-topic media block ───────────────────────────────────────────
export function TopicMedia({ topic }: { topic: string }) {
  const [lang, setLang] = useLessonLang();
  const ar = lang === 'ar';
  const film = filmFor(topic);
  const parts = partsFor(topic);
  if (!film && parts.length === 0) return null;
  return (
    <div className="space-y-4">
      {/* Language switch for this whole section */}
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card/40 px-4 py-2.5">
        <Languages className="h-4 w-4 text-primary shrink-0" />
        <span className="text-[11px] text-muted-foreground flex-1" dir={ar ? 'rtl' : 'ltr'}>
          {ar
            ? 'كل الشروح في هذا القسم متاحة بالعربية والإنجليزية — بدّل من هنا.'
            : 'Every explanation in this section is available in Arabic and English — switch here.'}
        </span>
        <LangToggle lang={lang} setLang={setLang} size="lg" />
      </div>
      {film && <PhysicsFilm film={film} />}
      {parts.length > 0 && (
        <AnimationGallery
          items={parts}
          title="Component anatomy — every part, animated"
          subtitle="Click any card for the full-size animation and engineering notes"
          titleAr="تشريح المكوّنات — كل جزء بأنيميشن خاص"
          subtitleAr="اضغط أي بطاقة لفتح الأنيميشن بالحجم الكامل مع الشرح الهندسي"
        />
      )}
      <div className="grid lg:grid-cols-2 gap-4">
        <KeyEquations topic={topic} />
        <HistoryTimeline topic={topic} />
      </div>
      <VideoShelf topic={topic} />
    </div>
  );
}

// ─── Whole-section theatre ────────────────────────────────────────────────────
export function MediaTheatreSection() {
  const [active, setActive] = useState(ALL_FILMS[0].id);
  const [query, setQuery] = useState('');
  const film = ALL_FILMS.find(f => f.id === active)!;
  const topic = useMemo(
    () => Object.keys(FILM_BY_TOPIC).find(k => FILM_BY_TOPIC[k] === active) || '',
    [active],
  );
  const allParts = useMemo(
    () => (query ? ALL_PART_ANIMS : ALL_PART_ANIMS.filter(a => a.group === topic)),
    [query, topic],
  );

  const totalChapters = ALL_FILMS.reduce((s, f) => s + f.chapters.length, 0);
  const totalMinutes = Math.round(ALL_FILMS.reduce((s, f) => s + f.duration, 0) / 60);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { v: String(ALL_FILMS.length), l: 'Physics films', c: 'text-pink-400' },
          { v: String(totalChapters), l: 'Narrated chapters', c: 'text-violet-400' },
          { v: String(ALL_PART_ANIMS.length), l: 'Component animations', c: 'text-emerald-400' },
          { v: `≈ ${totalMinutes} min`, l: 'Total run time', c: 'text-amber-400' },
        ].map(s => (
          <div key={s.l} className="bg-card/60 border border-border rounded-lg p-3">
            <div className={`text-lg font-bold font-mono ${s.c}`}>{s.v}</div>
            <div className="text-[11px] text-muted-foreground">{s.l}</div>
          </div>
        ))}
      </div>

      {/* Film picker */}
      <div className="flex flex-wrap gap-1.5">
        {ALL_FILMS.map(f => (
          <button key={f.id} onClick={() => setActive(f.id)}
            className={`text-[11px] px-2.5 py-1.5 rounded-lg border transition-colors ${
              f.id === active ? 'bg-primary/10 text-foreground' : 'border-border/50 text-muted-foreground hover:text-foreground hover:border-border'
            }`}
            style={f.id === active ? { borderColor: f.hex } : undefined}>
            <span className="h-1.5 w-1.5 rounded-full inline-block mr-1.5 align-middle" style={{ background: f.hex }} />
            {f.title.split('—')[0].trim()}
          </button>
        ))}
      </div>

      <PhysicsFilm film={film} />

      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-xs">
          <Search className="h-3 w-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search every component animation…"
            className="h-8 w-full pl-7 pr-2 rounded-md bg-background border border-border text-[11px] outline-none focus:border-primary/60" />
        </div>
        <span className="text-[10px] text-muted-foreground">
          {query ? 'searching all sources' : `showing parts for “${film.title.split('—')[0].trim()}”`}
        </span>
      </div>

      <AnimationGallery
        items={query ? allParts.filter(a => (a.part + a.summary + a.tag + a.group).toLowerCase().includes(query.toLowerCase())) : allParts}
        title="Component anatomy library"
        subtitle="Every physical part of every source, animated and annotated"
      />

      {topic && (
        <div className="grid lg:grid-cols-2 gap-4">
          <KeyEquations topic={topic} />
          <HistoryTimeline topic={topic} />
        </div>
      )}
      {topic && <VideoShelf topic={topic} />}
    </div>
  );
}
