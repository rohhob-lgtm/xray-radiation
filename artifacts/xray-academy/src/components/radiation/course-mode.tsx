import { useState, useMemo, useEffect } from 'react';
import {
  GraduationCap, PlayCircle, Boxes, Sigma, Clock3, HelpCircle, CheckCircle2,
  Circle, ChevronRight, ChevronLeft, RotateCcw, Award, BookOpen, Youtube,
  Maximize2, Minimize2, PanelLeftClose, PanelLeftOpen,
} from 'lucide-react';
import { PhysicsFilm, type Film } from './film-player';
import { LessonView, LangToggle, useLessonLang, type MicroAnim } from './anim-gallery';
import { COURSE_STRINGS, CATALOGUE_STRINGS, FILM_CHAPTERS_AR, COURSE_TITLES_AR, TAG_AR } from './lessons-ar-course';
import { useResizableColumn, ColumnResizer } from '@/components/ui/resizable-column';
import {
  ALL_FILMS, ALL_PART_ANIMS, KeyEquations, HistoryTimeline, VideoShelf, filmFor,
} from './media-shelf';
import { TOPIC_QUIZZES, type QuizQuestion } from '@/data/learning-center';

// ═══════════════════════════════════════════════════════════════════════════════
// Learn — course mode. Turns every film, component animation, equation set and
// timeline into an ordered curriculum with progress tracking.
// ═══════════════════════════════════════════════════════════════════════════════

const COURSE_TOPICS: { id: string; title: string; blurb: string }[] = [
  { id: 'xray-tube',         title: 'X-ray Tubes',            blurb: 'From hot filament to useful beam' },
  { id: 'linac',             title: 'Linear Accelerators',    blurb: 'RF power to megavolt photons' },
  { id: 'betatron',          title: 'Betatrons',              blurb: 'Acceleration by pure induction' },
  { id: 'cyclotron',         title: 'Cyclotrons',             blurb: 'Resonance, spirals and PET isotopes' },
  { id: 'synchrotron',       title: 'Synchrotron Light',      blurb: 'Storage rings and beamlines' },
  { id: 'van-de-graaff',     title: 'Van de Graaff',          blurb: 'Electrostatics at megavolt scale' },
  { id: 'radioisotopes',     title: 'Radioisotope Sources',   blurb: 'Decay, capsules, projectors, protection' },
  { id: 'neutron',           title: 'Neutron Sources',        blurb: 'Generation, moderation, detection' },
  { id: 'gamma-irradiators', title: 'Gamma Irradiators',      blurb: 'Pool storage to validated dose' },
  { id: 'industrial-xray',   title: 'Industrial Radiography', blurb: 'Geometry, energy, IQI, detector' },
  { id: 'security',          title: 'Security Screening',     blurb: 'Tunnel, dual energy, CT, operator' },
  { id: 'xray-technologies', title: 'Imaging Technologies',   blurb: 'Transmission, backscatter, scatter, spectral' },
  { id: 'detectors',         title: 'Detector Technology',    blurb: 'How radiation is received and measured' },
];

type UnitKind = 'film' | 'part' | 'equations' | 'timeline' | 'quiz' | 'watch';

interface Unit {
  key: string;
  kind: UnitKind;
  title: string;
  sub?: string;
  anim?: MicroAnim;
  film?: Film;
  chapter?: number;
}

interface Module { label: string; kind: 'film' | 'parts' | 'ref' | 'quiz'; tag?: string; n: number; icon: typeof PlayCircle; units: Unit[] }

function buildCourse(topic: string): Module[] {
  const film = filmFor(topic);
  const parts = ALL_PART_ANIMS.filter(a => a.group === topic);
  const quiz = TOPIC_QUIZZES[topic] as QuizQuestion[] | undefined;

  const modules: Module[] = [];

  if (film) {
    modules.push({
      label: 'Module 1 — Watch the film', kind: 'film', n: 1,
      icon: PlayCircle,
      units: film.chapters.map((c, i) => ({
        key: `${topic}:film:${i}`, kind: 'film', title: c.title, sub: `Chapter ${i + 1}`, film, chapter: i,
      })),
    });
  }

  if (parts.length > 0) {
    // group parts by their sub-assembly tag so the curriculum reads sensibly
    const tags = Array.from(new Set(parts.map(p => p.tag)));
    tags.forEach((tag, ti) => {
      modules.push({
        label: `Module ${modules.length + 1} — ${tag}`, kind: 'parts', tag, n: modules.length + 1,
        icon: Boxes,
        units: parts.filter(p => p.tag === tag).map(p => ({
          key: `${topic}:part:${p.id}`, kind: 'part', title: p.part, sub: tag, anim: p,
        })),
      });
      void ti;
    });
  }

  const refUnits: Unit[] = [
    { key: `${topic}:equations`, kind: 'equations', title: 'Equations that get used', sub: 'Reference' },
    { key: `${topic}:timeline`, kind: 'timeline', title: 'How the technology got here', sub: 'Reference' },
    { key: `${topic}:watch`, kind: 'watch', title: 'Go deeper — external video', sub: 'Reference' },
  ];
  modules.push({ label: `Module ${modules.length + 1} — Reference`, kind: 'ref', n: modules.length + 1, icon: Sigma, units: refUnits });

  if (quiz && quiz.length > 0) {
    modules.push({
      label: `Module ${modules.length + 1} — Knowledge check`, kind: 'quiz', n: modules.length + 1,
      icon: HelpCircle,
      units: [{ key: `${topic}:quiz`, kind: 'quiz', title: 'Final quiz', sub: `${quiz.length} questions` }],
    });
  }

  return modules;
}

// ─── Progress persistence ─────────────────────────────────────────────────────
const STORE_KEY = 'xr-course-progress';

function loadProgress(): Record<string, true> {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}
function saveProgress(p: Record<string, true>) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(p)); } catch { /* storage unavailable */ }
}

// ─── Compact quiz ─────────────────────────────────────────────────────────────
function CourseQuiz({ questions, onPass }: { questions: QuizQuestion[]; onPass: () => void }) {
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>(Array(questions.length).fill(null));
  const [done, setDone] = useState(false);
  const q = questions[current];
  const selected = answers[current];

  const pick = (i: number) => {
    if (selected !== null) return;
    const next = [...answers];
    next[current] = i;
    setAnswers(next);
  };

  const score = answers.filter((a, i) => a === questions[i].answer).length;

  if (done) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <div className="rounded-xl border border-border bg-card/40 p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${pct >= 75 ? 'bg-emerald-500/10 ring-1 ring-emerald-500/30' : 'bg-amber-500/10 ring-1 ring-amber-500/30'}`}>
            <Award className={`h-6 w-6 ${pct >= 75 ? 'text-emerald-400' : 'text-amber-400'}`} />
          </div>
          <div>
            <div className="font-bold text-foreground text-lg">{score} / {questions.length} — {pct}%</div>
            <div className="text-xs text-muted-foreground">
              {pct >= 75 ? 'Passed. You have solid command of this topic.' : 'Review the flagged questions and try again.'}
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {questions.map((qq, i) => (
            <div key={i} className={`rounded-lg border px-3 py-2 text-xs ${answers[i] === qq.answer ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
              <div className="font-medium text-foreground mb-0.5">{qq.q}</div>
              <div className="text-muted-foreground">{qq.explanation}</div>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setCurrent(0); setAnswers(Array(questions.length).fill(null)); setDone(false); }}
            className="h-8 px-3 rounded-md border border-border text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5">
            <RotateCcw className="h-3.5 w-3.5" /> Retake
          </button>
          {pct >= 75 && (
            <button onClick={onPass} className="h-8 px-3 rounded-md bg-emerald-500/15 border border-emerald-500/40 text-xs text-emerald-300 flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" /> Mark course complete
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card/40 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-foreground flex items-center gap-1.5"><HelpCircle className="h-4 w-4 text-primary" /> Knowledge check</span>
        <span className="text-[11px] font-mono text-muted-foreground">{current + 1} / {questions.length}</span>
      </div>
      <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${(current / questions.length) * 100}%` }} />
      </div>
      <p className="text-sm font-medium text-foreground leading-relaxed">{q.q}</p>
      <div className="space-y-2">
        {q.options.map((opt, i) => {
          let cls = 'border-border/50 text-muted-foreground hover:border-border hover:text-foreground';
          if (selected !== null) {
            if (i === q.answer) cls = 'border-emerald-500 bg-emerald-500/10 text-emerald-300';
            else if (i === selected) cls = 'border-red-500 bg-red-500/10 text-red-300';
            else cls = 'border-border/30 text-muted-foreground/50';
          }
          return (
            <button key={i} onClick={() => pick(i)} className={`w-full text-left text-xs px-3 py-2.5 rounded-lg border transition-all ${cls}`}>
              <span className="font-mono text-[10px] mr-2 opacity-60">{String.fromCharCode(65 + i)}.</span>{opt}
            </button>
          );
        })}
      </div>
      {selected !== null && (
        <>
          <div className={`rounded-lg px-3 py-2 text-xs ${selected === q.answer ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-200' : 'bg-red-500/10 border border-red-500/30 text-red-200'}`}>
            <span className="font-semibold">{selected === q.answer ? '✓ Correct. ' : '✗ Not quite. '}</span>{q.explanation}
          </div>
          <button onClick={() => (current < questions.length - 1 ? setCurrent(c => c + 1) : setDone(true))}
            className="h-8 px-3 rounded-md bg-primary text-primary-foreground text-xs font-semibold flex items-center gap-1.5">
            {current < questions.length - 1 ? 'Next question' : 'See results'} <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </>
      )}
    </div>
  );
}

/** Arabic text for the small chip beside the lesson counter. */
function unitSub(u: Unit): string {
  const S = COURSE_STRINGS.ar;
  if (!u.sub) return '';
  if (u.kind === 'film') return `${S.chapter} ${(u.chapter ?? 0) + 1}`;
  if (u.kind === 'quiz') return u.sub.replace(/(\d+)\s*questions/, `$1 ${S.questions}`);
  if (u.sub === 'Reference') return S.moduleRef;
  return TAG_AR[u.sub] ?? u.sub;
}

/** Arabic label for a curriculum module. */
function moduleLabel(m: Module, ar: boolean): string {
  if (!ar) return m.label;
  const S = COURSE_STRINGS.ar;
  const head = `${S.module} ${m.n} — `;
  if (m.kind === 'film') return head + S.moduleFilm;
  if (m.kind === 'ref') return head + S.moduleRef;
  if (m.kind === 'quiz') return head + S.moduleQuiz;
  return head + (TAG_AR[m.tag ?? ''] ?? m.tag ?? '');
}

/** Arabic title for a curriculum unit where one exists. */
function unitTitle(u: Unit, ar: boolean): string {
  if (!ar) return u.title;
  if (u.kind === 'part' && u.anim?.partAr) return u.anim.partAr;
  if (u.kind === 'film' && u.film) {
    const c = FILM_CHAPTERS_AR[u.film.id]?.[u.chapter ?? 0];
    if (c) return c.title;
  }
  if (u.kind === 'equations') return COURSE_STRINGS.ar.equationsUnit;
  if (u.kind === 'timeline') return COURSE_STRINGS.ar.timelineUnit;
  if (u.kind === 'watch') return COURSE_STRINGS.ar.watchUnit;
  if (u.kind === 'quiz') return COURSE_STRINGS.ar.quizUnit;
  return u.title;
}

// ─── Course view ──────────────────────────────────────────────────────────────
function CourseView({ topic, onExit }: { topic: string; onExit: () => void }) {
  const meta = COURSE_TOPICS.find(c => c.id === topic)!;
  const modules = useMemo(() => buildCourse(topic), [topic]);
  const flat = useMemo(() => modules.flatMap(m => m.units), [modules]);
  const [index, setIndex] = useState(0);
  const [progress, setProgress] = useState<Record<string, true>>({});
  const [theater, setTheater] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const [lang, setLang] = useLessonLang();
  const ar = lang === 'ar';
  const S = COURSE_STRINGS[lang];
  const rail = useResizableColumn({ key: 'course-rail', initial: 280, min: 190, max: 520 });

  useEffect(() => { setProgress(loadProgress()); }, []);
  useEffect(() => { setIndex(0); }, [topic]);

  // Escape leaves theatre mode before it leaves the course
  useEffect(() => {
    if (!theater) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setTheater(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [theater]);

  const unit = flat[index];
  const doneCount = flat.filter(u => progress[u.key]).length;
  const pct = Math.round((doneCount / flat.length) * 100);
  const film = filmFor(topic);

  const markDone = (key: string) => {
    setProgress(p => { const n = { ...p, [key]: true as const }; saveProgress(n); return n; });
  };
  const completeAndNext = () => {
    markDone(unit.key);
    if (index < flat.length - 1) setIndex(index + 1);
  };

  return (
    <div className={theater
      ? 'fixed inset-0 z-50 bg-background overflow-y-auto p-3 sm:p-5 space-y-4'
      : 'space-y-4'}>
      {/* Course header */}
      <div className="rounded-xl border border-border bg-card/40 px-4 py-3">
        {/* Controls first, on the left, so they are always reachable */}
        <div className="flex items-center gap-2 flex-wrap mb-2.5">
          <button onClick={() => setTheater(t => !t)}
            title={theater ? 'Exit theatre mode (Esc)' : 'Theatre mode — use the full window'}
            className={`h-8 px-3 rounded-md text-[11px] font-semibold flex items-center gap-1.5 shrink-0 border ${
              theater ? 'bg-primary text-primary-foreground border-primary' : 'border-primary/50 text-primary hover:bg-primary/10'
            }`}>
            {theater ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            {theater ? S.exitTheatre : S.theatre}
          </button>
          <span className="text-[11px] text-muted-foreground shrink-0">
            {theater ? S.pressEsc : S.pressFull}
          </span>
          <LangToggle lang={lang} setLang={setLang} size="lg" />
          <button onClick={() => setRailOpen(o => !o)}
            title={railOpen ? 'Hide the curriculum list' : 'Show the curriculum list'}
            className="h-8 px-2.5 rounded-md border border-border text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1.5 shrink-0">
            {railOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
            {railOpen ? S.hideList : S.showList}
          </button>
          <button onClick={onExit} className="h-8 px-2.5 rounded-md border border-border text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1.5 shrink-0">
            <ChevronLeft className="h-4 w-4" /> {S.allCourses}
          </button>
        </div>

        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex-1 min-w-0" dir={ar ? 'rtl' : 'ltr'}>
            <div className="text-sm font-bold text-foreground truncate">{ar ? (COURSE_TITLES_AR[topic]?.title ?? meta.title) : meta.title}</div>
            <div className="text-[11px] text-muted-foreground truncate">{ar ? (COURSE_TITLES_AR[topic]?.blurb ?? meta.blurb) : meta.blurb}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-[11px] font-mono text-foreground">{doneCount} / {flat.length} {S.lessons}</div>
            <div className="text-[10px] text-muted-foreground">{pct}% {S.complete}</div>
          </div>
        </div>
        <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden mt-2.5">
          <div className="h-full bg-emerald-500 rounded-full transition-all duration-300" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* Curriculum */}
        <div className={`shrink-0 ${railOpen ? 'lg:w-[var(--railw)]' : 'hidden'}`}
          style={{ ['--railw' as string]: `${rail.width}px` }}>
          <div className="rounded-xl border border-border bg-card/40 overflow-hidden lg:sticky lg:top-2 max-h-[70vh] overflow-y-auto">
            {modules.map(m => {
              const Icon = m.icon;
              return (
                <div key={m.label}>
                  <div className="px-3 py-2 bg-card/60 border-y border-border/60 flex items-center gap-1.5 sticky top-0">
                    <Icon className="h-3.5 w-3.5 text-primary shrink-0" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground truncate"
                      dir={ar ? 'rtl' : 'ltr'}>{moduleLabel(m, ar)}</span>
                  </div>
                  {m.units.map(u => {
                    const i = flat.findIndex(f => f.key === u.key);
                    const active = i === index;
                    const done = !!progress[u.key];
                    return (
                      <button key={u.key} onClick={() => setIndex(i)}
                        className={`w-full text-left px-3 py-2 flex items-start gap-2 border-b border-border/40 transition-colors ${
                          active ? 'bg-primary/10' : 'hover:bg-muted/30'
                        }`}>
                        {done
                          ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                          : <Circle className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0 mt-0.5" />}
                        <span className={`text-[11px] leading-snug ${active ? 'text-foreground font-medium' : 'text-muted-foreground'}`}
                          dir={ar ? 'rtl' : 'ltr'}>
                          {unitTitle(u, ar)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
        {railOpen && (
          <div className="hidden lg:flex">
            <ColumnResizer
              dragging={rail.dragging}
              onPointerDown={rail.onPointerDown}
              onPointerMove={rail.onPointerMove}
              onPointerUp={rail.endDrag}
            />
          </div>
        )}

        {/* Lesson pane */}
        <div className="flex-1 min-w-0 space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-border text-muted-foreground">
              {S.lessonOf(index + 1, flat.length)}
            </span>
            {unit.sub && <span className="text-[10px] text-muted-foreground" dir={ar ? 'rtl' : 'ltr'}>
              {ar ? unitSub(unit) : unit.sub}
            </span>}
            <div className="flex-1" />
            <button disabled={index === 0} onClick={() => setIndex(i => Math.max(0, i - 1))}
              className="h-7 px-2 rounded-md border border-border text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-30 flex items-center gap-1">
              <ChevronLeft className="h-3.5 w-3.5" /> {S.prev}
            </button>
            <button onClick={completeAndNext}
              className="h-7 px-3 rounded-md bg-emerald-500/15 border border-emerald-500/40 text-[11px] text-emerald-300 flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {index < flat.length - 1 ? S.completeNext : S.completeOnly}
            </button>
          </div>

          <h3 className="text-base font-bold text-foreground" dir={ar ? 'rtl' : 'ltr'}>{unitTitle(unit, ar)}</h3>

          {unit.kind === 'film' && film && (
            <div className="space-y-3">
              <PhysicsFilm
                film={film}
                startAt={film.chapters[unit.chapter ?? 0]?.t ?? 0}
                seekKey={unit.key}
                autoPlay
              />
              <div className="rounded-lg border border-border bg-card/40 p-4">
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">{S.lessonNotes}</div>
                {(() => {
                  const i = unit.chapter ?? 0;
                  const en = film.chapters[i];
                  const arCh = ar ? FILM_CHAPTERS_AR[film.id]?.[i] : undefined;
                  const cap = arCh?.caption ?? en.caption;
                  const det = arCh?.detail ?? en.detail;
                  const ttl = arCh?.title ?? en.title;
                  return (
                    <div dir={arCh ? 'rtl' : 'ltr'}>
                      <p className="text-[12px] text-foreground leading-relaxed">{cap}</p>
                      {det && <p className="text-[11px] text-muted-foreground leading-relaxed mt-2">{det}</p>}
                      <p className="text-[10px] text-muted-foreground mt-3">{S.chapterHint(ttl)}</p>
                    </div>
                  );
                })()}
              </div>
            </div>
          )}

          {unit.kind === 'part' && unit.anim && <LessonView anim={unit.anim} />}
          {unit.kind === 'equations' && <KeyEquations topic={topic} />}
          {unit.kind === 'timeline' && <HistoryTimeline topic={topic} />}
          {unit.kind === 'watch' && (
            <div className="space-y-3">
              <div className="rounded-lg border border-border bg-card/40 p-4 flex items-start gap-2.5">
                <Youtube className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                <p className="text-[12px] text-muted-foreground leading-relaxed" dir={ar ? 'rtl' : 'ltr'}>{S.watchIntro}</p>
              </div>
              <VideoShelf topic={topic} />
            </div>
          )}
          {unit.kind === 'quiz' && TOPIC_QUIZZES[topic] && (
            <CourseQuiz questions={TOPIC_QUIZZES[topic]} onPass={() => flat.forEach(u => markDone(u.key))} />
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Course catalogue ─────────────────────────────────────────────────────────
export function LearnSection() {
  const [topic, setTopic] = useState<string | null>(null);
  const [lang, setLang] = useLessonLang();
  const ar = lang === 'ar';
  const S = CATALOGUE_STRINGS[lang];
  const [progress, setProgress] = useState<Record<string, true>>({});
  useEffect(() => { setProgress(loadProgress()); }, [topic]);

  const stats = useMemo(() => {
    const totalLessons = COURSE_TOPICS.reduce((s, c) => s + buildCourse(c.id).flatMap(m => m.units).length, 0);
    const done = Object.keys(progress).length;
    return { totalLessons, done };
  }, [progress]);

  if (topic) return <CourseView topic={topic} onExit={() => setTopic(null)} />;

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border bg-card/40 p-4 flex items-start gap-3">
        <div className="h-10 w-10 rounded-lg bg-primary/10 ring-1 ring-primary/30 flex items-center justify-center shrink-0">
          <GraduationCap className="h-5 w-5 text-primary" />
        </div>
        <div className="flex-1 min-w-0" dir={ar ? 'rtl' : 'ltr'}>
          <h3 className="text-sm font-bold text-foreground">{S.heading}</h3>
          <p className="text-[12px] text-muted-foreground leading-relaxed mt-0.5">{S.intro}</p>
        </div>
        <LangToggle lang={lang} setLang={setLang} size="lg" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { v: String(COURSE_TOPICS.length), l: S.courses, c: 'text-rose-400' },
          { v: String(stats.totalLessons), l: S.totalLessons, c: 'text-violet-400' },
          { v: String(ALL_PART_ANIMS.length), l: S.liveSims, c: 'text-emerald-400' },
          { v: `${stats.done}`, l: S.doneLessons, c: 'text-amber-400' },
        ].map(s => (
          <div key={s.l} className="bg-card/60 border border-border rounded-lg p-3">
            <div className={`text-lg font-bold font-mono ${s.c}`}>{s.v}</div>
            <div className="text-[11px] text-muted-foreground">{s.l}</div>
          </div>
        ))}
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {COURSE_TOPICS.map(c => {
          const units = buildCourse(c.id).flatMap(m => m.units);
          const done = units.filter(u => progress[u.key]).length;
          const pct = Math.round((done / units.length) * 100);
          const film = ALL_FILMS.find(f => f.id === (filmFor(c.id)?.id));
          return (
            <button key={c.id} onClick={() => setTopic(c.id)}
              className="text-left rounded-xl border border-border bg-card/40 p-4 hover:border-primary/50 transition-colors group">
              <div className="flex items-start gap-2">
                <span className="h-2 w-2 rounded-full mt-1.5 shrink-0" style={{ background: film?.hex ?? '#64748b' }} />
                <div className="flex-1 min-w-0" dir={ar ? 'rtl' : 'ltr'}>
                  <div className="text-[13px] font-bold text-foreground">{ar ? (COURSE_TITLES_AR[c.id]?.title ?? c.title) : c.title}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{ar ? (COURSE_TITLES_AR[c.id]?.blurb ?? c.blurb) : c.blurb}</div>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </div>
              <div className="flex items-center gap-2 mt-3">
                <div className="h-1.5 flex-1 bg-muted rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: pct === 100 ? '#22c55e' : (film?.hex ?? '#64748b') }} />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground shrink-0">{done}/{units.length}</span>
              </div>
              <div className="flex items-center gap-3 mt-2.5 text-[10px] text-muted-foreground">
                <span className="flex items-center gap-1"><PlayCircle className="h-3 w-3" />{film ? `${film.chapters.length} ${S.chaptersWord}` : S.noFilm}</span>
                <span className="flex items-center gap-1"><Boxes className="h-3 w-3" />{ALL_PART_ANIMS.filter(a => a.group === c.id).length} {S.simsWord}</span>
                {TOPIC_QUIZZES[c.id] && <span className="flex items-center gap-1"><HelpCircle className="h-3 w-3" />{S.quizWord}</span>}
              </div>
            </button>
          );
        })}
      </div>

      <div className="rounded-xl border border-border bg-card/40 p-4 flex items-start gap-2.5">
        <BookOpen className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
        <p className="text-[11px] text-muted-foreground leading-relaxed" dir={ar ? 'rtl' : 'ltr'}>
          {S.footer} <Clock3 className="h-3 w-3 inline mx-0.5" />
        </p>
      </div>
    </div>
  );
}
