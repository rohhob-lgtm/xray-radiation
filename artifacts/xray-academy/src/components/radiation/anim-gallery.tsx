import { useState, useEffect, useRef, useMemo } from 'react';
import type { ReactNode } from 'react';
import {
  Play, Pause, Gauge, Search, X, ChevronRight, Layers3,
  BookOpen, Lightbulb, ListOrdered, Atom, Wrench, HardHat, Eye, GraduationCap,
  Languages,
} from 'lucide-react';
import { SceneDefs } from './film-player';
import { TAG_AR } from './lessons-ar-course';

// ═══════════════════════════════════════════════════════════════════════════════
// Component-anatomy animation gallery.
// Dozens of small looping SVG animations — one per physical part — driven by a
// single shared clock so a page with 60 cards still costs one rAF loop.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * A short structured lesson attached to a component — the point is that clicking
 * a part teaches you how it works, not just what it is called.
 */
export interface Lesson {
  /** The whole idea in one plain sentence */
  oneLiner: string;
  /** A everyday mental model — "think of it as…" */
  analogy?: string;
  /** What to look at while the animation runs */
  watchFor?: string;
  /** Mechanism, step by step, in plain language */
  how: string[];
  /** The physics underneath, with the equations that matter */
  physics: string[];
  /** Materials, tolerances, design trade-offs */
  engineering: string[];
  /** Operation, failure modes, maintenance, safety */
  practice?: string[];
  /** Key figures worth memorising */
  numbers?: [string, string][];
}

/** Language of the lesson text. The simulation itself is language-neutral. */
export type LessonLang = 'en' | 'ar';

const LANG_KEY = 'xr-lesson-lang';

// Module-level store so every toggle on the page switches together — a language
// switch buried in one panel that leaves the rest in English is worse than none.
let currentLang: LessonLang = (() => {
  try {
    const v = localStorage.getItem(LANG_KEY);
    return v === 'ar' || v === 'en' ? v : 'en';
  } catch { return 'en'; }
})();
const langSubscribers = new Set<(l: LessonLang) => void>();

export function setLessonLang(l: LessonLang) {
  currentLang = l;
  try { localStorage.setItem(LANG_KEY, l); } catch { /* storage unavailable */ }
  langSubscribers.forEach(fn => fn(l));
}

export function useLessonLang(): [LessonLang, (l: LessonLang) => void] {
  const [lang, setLang] = useState<LessonLang>(currentLang);
  useEffect(() => {
    langSubscribers.add(setLang);
    setLang(currentLang);
    return () => { langSubscribers.delete(setLang); };
  }, []);
  return [lang, setLessonLang];
}

/** Tab labels and headings in both languages. */
export const UI_STRINGS = {
  en: {
    all: 'Full lesson', overview: 'Overview', how: 'How it works', physics: 'Physics', engineering: 'Engineering', practice: 'In practice',
    hintAll: 'Everything on one page — scroll to read it all', hintOverview: 'The idea in one minute', hintHow: 'Mechanism, step by step', hintPhysics: 'Why it works at all',
    hintEngineering: 'Materials and trade-offs', hintPractice: 'Operation, faults, safety',
    oneSentence: 'In one sentence', thinkOf: 'Think of it as', watchFor: 'Watch for', whatItDoes: 'What it does',
    followSteps: 'Follow these steps against the animation.', miniLesson: 'mini-lesson', next: 'Next', escClose: 'Esc to close',
    noArabic: 'Arabic text for this component is not written yet — showing English.',
  },
  ar: {
    all: 'الدرس كاملًا', overview: 'نظرة عامة', how: 'آلية العمل', physics: 'الفيزياء', engineering: 'الهندسة', practice: 'في الميدان',
    hintAll: 'كل شيء في صفحة واحدة — مرّر لقراءته كاملًا', hintOverview: 'الفكرة في دقيقة واحدة', hintHow: 'الآلية خطوة بخطوة', hintPhysics: 'لماذا يعمل أصلًا',
    hintEngineering: 'المواد والمقايضات', hintPractice: 'التشغيل والأعطال والسلامة',
    oneSentence: 'في جملة واحدة', thinkOf: 'تخيّلها هكذا', watchFor: 'راقب في المحاكاة', whatItDoes: 'ماذا يفعل',
    followSteps: 'تابع هذه الخطوات مع المحاكاة على الجانب.', miniLesson: 'درس مصغّر', next: 'التالي', escClose: 'Esc للإغلاق',
    noArabic: 'النص العربي لهذا المكوّن لم يُكتب بعد — يُعرض الإنجليزي.',
  },
} as const;

export interface MicroAnim {
  id: string;
  /** Which source this part belongs to (section id) */
  group: string;
  /** Part name, e.g. "Rotating anode disc" */
  part: string;
  /** Sub-assembly chip, e.g. "Anode assembly" */
  tag: string;
  /** One or two sentences on what the part does */
  summary: string;
  /** Detailed engineering notes shown when the card is expanded */
  bullets: string[];
  hex: string;
  /** Draws inside a 260 × 150 viewBox. `t` is seconds since mount. */
  draw: (t: number) => ReactNode;
  /** Full mini-lesson shown next to the animation */
  lesson?: Lesson;
  /** Arabic translation of the same lesson, shown when the AR toggle is on */
  lessonAr?: Lesson;
  /** Arabic part name and one-line summary for the header */
  partAr?: string;
  summaryAr?: string;
}

/** Shared clock — one requestAnimationFrame for the whole gallery */
function useSharedClock(running: boolean, speed: number) {
  const [t, setT] = useState(0);
  const tRef = useRef(0);
  const lastRef = useRef<number | null>(null);
  const rafRef = useRef<number>(0);
  useEffect(() => {
    if (!running) { lastRef.current = null; return; }
    const loop = (ts: number) => {
      if (lastRef.current === null) lastRef.current = ts;
      tRef.current += ((ts - lastRef.current) / 1000) * speed;
      lastRef.current = ts;
      setT(tRef.current);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [running, speed]);
  return t;
}

function Stage({ anim, t, height = 150 }: { anim: MicroAnim; t: number; height?: number }) {
  return (
    <svg viewBox="0 0 260 150" style={{ fontFamily: 'ui-monospace, monospace', display: 'block', width: '100%', height }}>
      <SceneDefs />
      <rect x="0" y="0" width="260" height="150" fill="#060a12" />
      <g opacity="0.14">
        {Array.from({ length: 7 }, (_, i) => <line key={`v${i}`} x1={i * 40} y1={0} x2={i * 40} y2={150} stroke="#1e293b" strokeWidth="0.5" />)}
        {Array.from({ length: 4 }, (_, i) => <line key={`h${i}`} x1={0} y1={i * 40} x2={260} y2={i * 40} stroke="#1e293b" strokeWidth="0.5" />)}
      </g>
      {anim.draw(t)}
    </svg>
  );
}

export function AnimationGallery({
  items, title = 'Component Anatomy', subtitle, columns = 3,
  titleAr = 'تشريح المكوّنات', subtitleAr = 'اضغط أي بطاقة لفتح الأنيميشن بالحجم الكامل مع الشرح الهندسي',
}: {
  items: MicroAnim[]; title?: string; subtitle?: string; columns?: 2 | 3;
  titleAr?: string; subtitleAr?: string;
}) {
  const [lang, setLang] = useLessonLang();
  const ar = lang === 'ar';
  const running0 = true; void running0;
  const [running, setRunning] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const t = useSharedClock(running, speed);

  const tags = useMemo(() => ['All', ...Array.from(new Set(items.map(i => i.tag)))], [items]);
  const [tag, setTag] = useState('All');

  const filtered = useMemo(() => items.filter(i =>
    (tag === 'All' || i.tag === tag) &&
    (query === '' || (i.part + i.summary + i.tag + (i.partAr ?? '') + (i.summaryAr ?? ''))
      .toLowerCase().includes(query.toLowerCase()))
  ), [items, tag, query]);

  const open = items.find(i => i.id === openId) || null;

  return (
    <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/70 bg-card/60 flex-wrap">
        <Layers3 className="h-4 w-4 text-primary shrink-0" />
        <div className="min-w-0" dir={ar ? 'rtl' : 'ltr'}>
          <div className="text-xs font-bold text-foreground">{ar ? titleAr : title}</div>
          {(ar ? subtitleAr : subtitle) && (
            <div className="text-[10px] text-muted-foreground">{ar ? subtitleAr : subtitle}</div>
          )}
        </div>
        <LangToggle lang={lang} setLang={setLang} />
        <span className="text-[10px] font-mono text-muted-foreground ml-1">{filtered.length} / {items.length}</span>
        <div className="flex-1" />
        <div className="relative">
          <Search className="h-3 w-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query} onChange={e => setQuery(e.target.value)} placeholder={ar ? 'ابحث عن مكوّن…' : 'Find a part…'}
            className="h-7 w-36 pl-7 pr-2 rounded-md bg-background border border-border text-[11px] outline-none focus:border-primary/60"
          />
        </div>
        <button onClick={() => setSpeed(s => (s === 1 ? 0.5 : s === 0.5 ? 2 : 1))}
          className="h-7 px-2 rounded-md flex items-center gap-1 text-[10px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted/40 border border-border">
          <Gauge className="h-3 w-3" />{speed}×
        </button>
        <button onClick={() => setRunning(r => !r)}
          className="h-7 px-2.5 rounded-md flex items-center gap-1.5 text-[10px] font-semibold bg-primary text-primary-foreground">
          {running ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
          {running ? (ar ? 'إيقاف الكل' : 'Pause all') : (ar ? 'تشغيل الكل' : 'Play all')}
        </button>
      </div>

      {/* Tag filter */}
      {tags.length > 2 && (
        <div className="flex gap-1 flex-wrap px-4 py-2 border-b border-border/50 bg-background/30">
          {tags.map(tg => (
            <button key={tg} onClick={() => setTag(tg)}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                tag === tg ? 'border-primary bg-primary/15 text-foreground' : 'border-border/50 text-muted-foreground hover:text-foreground hover:border-border'
              }`}>
              {ar ? (tg === 'All' ? 'الكل' : (TAG_AR[tg] ?? tg)) : tg}
            </button>
          ))}
        </div>
      )}

      {/* Grid */}
      <div className={`grid gap-3 p-3 ${columns === 2 ? 'sm:grid-cols-2' : 'sm:grid-cols-2 lg:grid-cols-3'}`}>
        {filtered.map(a => (
          <button key={a.id} onClick={() => setOpenId(a.id)}
            className="text-left rounded-lg border border-border/70 bg-background/40 overflow-hidden hover:border-primary/50 transition-colors group">
            <Stage anim={a} t={t} />
            <div className="px-3 py-2 border-t border-border/60">
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: a.hex }} />
                <span className="text-[11px] font-semibold text-foreground truncate flex-1"
                  dir={ar ? 'rtl' : 'ltr'}>{ar ? (a.partAr ?? a.part) : a.part}</span>
                <ChevronRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed"
                dir={ar ? 'rtl' : 'ltr'}>{ar ? (a.summaryAr ?? a.summary) : a.summary}</div>
              <span className="inline-block mt-1.5 text-[9px] font-mono px-1.5 py-0.5 rounded border border-border/60 text-muted-foreground">
                {ar ? (TAG_AR[a.tag] ?? a.tag) : a.tag}
              </span>
            </div>
          </button>
        ))}
        {filtered.length === 0 && (
          <div className="col-span-full text-center text-xs text-muted-foreground py-8">
            {ar ? `‏لا يوجد مكوّن يطابق «${query}».` : `No part matches “${query}”.`}
          </div>
        )}
      </div>

      {/* Mini-lesson overlay */}
      {open && (
        <LessonPanel
          anim={open} t={t} running={running} speed={speed}
          onClose={() => setOpenId(null)}
          onToggle={() => setRunning(r => !r)}
          onSpeed={() => setSpeed(s => (s === 1 ? 0.5 : s === 0.5 ? 2 : 1))}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Lesson panel — the animation stays live on the left, the lesson reads on the
// right. Tabs keep each part of the explanation short enough to actually read.
// ═══════════════════════════════════════════════════════════════════════════════
type TabId = 'all' | 'overview' | 'how' | 'physics' | 'engineering' | 'practice';

const tabMeta = (lang: LessonLang): { id: TabId; label: string; icon: typeof BookOpen; hint: string }[] => {
  const S = UI_STRINGS[lang];
  return [
    { id: 'all', label: S.all, icon: BookOpen, hint: S.hintAll },
    { id: 'overview',    label: S.overview,    icon: Lightbulb,   hint: S.hintOverview },
    { id: 'how',         label: S.how,         icon: ListOrdered, hint: S.hintHow },
    { id: 'physics',     label: S.physics,     icon: Atom,        hint: S.hintPhysics },
    { id: 'engineering', label: S.engineering, icon: Wrench,      hint: S.hintEngineering },
    { id: 'practice',    label: S.practice,    icon: HardHat,     hint: S.hintPractice },
  ];
};

/**
 * AR / EN switch. Exported so the course header can show the same control at the
 * top of the page, where it is actually noticeable.
 */
export function LangToggle({
  lang, setLang, hasAr = true, size = 'sm',
}: { lang: LessonLang; setLang: (l: LessonLang) => void; hasAr?: boolean; size?: 'sm' | 'lg' }) {
  const big = size === 'lg';
  return (
    <div
      className={`flex items-center rounded-md border overflow-hidden shrink-0 ${big ? 'border-primary/50' : 'border-border'}`}
      title={hasAr ? 'Switch lesson language — تبديل لغة الدرس' : 'Arabic not available for this component yet'}
    >
      <Languages className={`${big ? 'h-4 w-4 mx-1.5' : 'h-3 w-3 mx-1'} text-muted-foreground shrink-0`} />
      {(['en', 'ar'] as const).map(l => (
        <button key={l} onClick={() => setLang(l)}
          className={`${big ? 'h-8 px-3 text-[12px]' : 'h-6 px-2 text-[10px]'} font-bold transition-colors ${
            lang === l ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
          } ${l === 'ar' && !hasAr ? 'opacity-50' : ''}`}>
          {l === 'en' ? 'EN' : 'العربية'}
        </button>
      ))}
    </div>
  );
}

/** One titled block inside the stacked full-lesson view. */
function Section({
  icon: Icon, title, hint, hex, children,
}: { icon: typeof BookOpen; title: string; hint?: string; hex: string; children: ReactNode }) {
  return (
    <section className="scroll-mt-4">
      <div className="flex items-center gap-2 mb-2 pb-1.5 border-b border-border/70">
        <Icon className="h-4 w-4 shrink-0" style={{ color: hex }} />
        <h4 className="text-[13px] font-bold text-foreground">{title}</h4>
        {hint && <span className="text-[10px] text-muted-foreground truncate">— {hint}</span>}
      </div>
      {children}
    </section>
  );
}

/**
 * The whole lesson as one readable page. Tabs still work as filters, but the
 * default view shows everything so a lesson never looks thinner than it is.
 */
function LessonBody({
  lesson, anim, ar, S, tab,
}: {
  lesson: Lesson | undefined;
  anim: MicroAnim;
  ar: boolean;
  S: typeof UI_STRINGS['en'] | typeof UI_STRINGS['ar'];
  tab: TabId;
}) {
  const dir = ar ? 'rtl' : 'ltr';
  const summary = ar ? (anim.summaryAr ?? anim.summary) : anim.summary;

  if (!lesson) {
    return (
      <div dir={dir} className="space-y-4">
        <p className="text-[12px] text-muted-foreground leading-relaxed">{summary}</p>
        <Bullets items={anim.bullets} hex={anim.hex} />
      </div>
    );
  }

  const showAll = tab === 'all';
  const show = (id: TabId) => showAll || tab === id;

  return (
    <div dir={dir} className="space-y-6">
      {show('overview') && (
        <div className="space-y-4">
          <div className="rounded-lg border px-3.5 py-3" style={{ borderColor: `${anim.hex}44`, background: `${anim.hex}0d` }}>
            <div className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: anim.hex }}>{S.oneSentence}</div>
            <p className="text-[13px] text-foreground leading-relaxed">{lesson.oneLiner}</p>
          </div>
          {lesson.analogy && (
            <div className="rounded-lg border border-border bg-background/40 px-3.5 py-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Lightbulb className="h-3.5 w-3.5 text-amber-400" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">{S.thinkOf}</span>
              </div>
              <p className="text-[12px] text-muted-foreground leading-relaxed">{lesson.analogy}</p>
            </div>
          )}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">{S.whatItDoes}</div>
            <p className="text-[12px] text-muted-foreground leading-relaxed mb-3">{summary}</p>
            {/* The English bullet list duplicates the translated sections below, so
                it is hidden in Arabic rather than shown untranslated. */}
            {!ar && <Bullets items={anim.bullets} hex={anim.hex} />}
          </div>
        </div>
      )}

      {show('how') && (
        <Section icon={ListOrdered} title={S.how} hint={showAll ? S.hintHow : undefined} hex={anim.hex}>
          {!showAll && <p className="text-[11px] text-muted-foreground mb-2">{S.followSteps}</p>}
          <Bullets items={lesson.how} hex={anim.hex} ordered />
        </Section>
      )}

      {show('physics') && (
        <Section icon={Atom} title={S.physics} hint={showAll ? S.hintPhysics : undefined} hex={anim.hex}>
          <Bullets items={lesson.physics} hex={anim.hex} />
        </Section>
      )}

      {show('engineering') && (
        <Section icon={Wrench} title={S.engineering} hint={showAll ? S.hintEngineering : undefined} hex={anim.hex}>
          <Bullets items={lesson.engineering} hex={anim.hex} />
        </Section>
      )}

      {show('practice') && lesson.practice && lesson.practice.length > 0 && (
        <Section icon={HardHat} title={S.practice} hint={showAll ? S.hintPractice : undefined} hex={anim.hex}>
          <Bullets items={lesson.practice} hex={anim.hex} />
        </Section>
      )}
    </div>
  );
}

function Bullets({ items, hex, ordered = false }: { items: string[]; hex: string; ordered?: boolean }) {
  return (
    <ol className="space-y-2">
      {items.map((b, i) => (
        <li key={i} className="text-[12px] text-muted-foreground flex gap-2.5 leading-relaxed">
          {ordered ? (
            <span className="shrink-0 h-4 w-4 mt-0.5 rounded-full text-[9px] font-bold flex items-center justify-center"
              style={{ background: `${hex}22`, color: hex }}>{i + 1}</span>
          ) : (
            <span className="shrink-0 mt-[7px] h-1 w-1 rounded-full" style={{ background: hex }} />
          )}
          <span className="[&_code]:font-mono [&_code]:text-[11px] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:bg-muted/60 [&_code]:text-foreground [&_b]:text-foreground [&_b]:font-semibold"
            dangerouslySetInnerHTML={{ __html: b }} />
        </li>
      ))}
    </ol>
  );
}

/**
 * Inline version of the lesson — same content, no modal chrome. Used by the
 * course mode, where the lesson is the page rather than a popup.
 */
export function LessonView({ anim, stageHeight = 250 }: { anim: MicroAnim; stageHeight?: number }) {
  const [running, setRunning] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [tab, setTab] = useState<TabId>('all');
  const [lang, setLang] = useLessonLang();
  const t = useSharedClock(running, speed);
  const hasAr = !!anim.lessonAr;
  const ar = lang === 'ar' && hasAr;
  const lesson = ar ? anim.lessonAr : anim.lesson;
  const S = UI_STRINGS[ar ? 'ar' : 'en'];
  const title = ar ? (anim.partAr ?? anim.part) : anim.part;
  const summary = ar ? (anim.summaryAr ?? anim.summary) : anim.summary;

  const tabs = tabMeta(ar ? 'ar' : 'en').filter(tb => {
    if (!lesson) return tb.id === 'all';
    if (tb.id === 'practice') return (lesson.practice?.length ?? 0) > 0;
    return true;
  });

  return (
    <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
      {/* Header — title and the language switch, where they are actually seen */}
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-border bg-card/60">
        <span className="h-7 w-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: `${anim.hex}1a`, border: `1px solid ${anim.hex}55` }}>
          <GraduationCap className="h-4 w-4" style={{ color: anim.hex }} />
        </span>
        <div className="flex-1 min-w-0" dir={ar ? 'rtl' : 'ltr'}>
          <div className="text-[13px] font-bold text-foreground truncate">{title}</div>
          <div className="text-[10px] text-muted-foreground truncate">{anim.tag} · {S.miniLesson}</div>
        </div>
        <LangToggle lang={lang} setLang={setLang} hasAr={hasAr} />
      </div>
      <div className="flex flex-col lg:flex-row">
        <div className="lg:w-[44%] shrink-0 border-b lg:border-b-0 lg:border-r border-border bg-[#060a12] flex flex-col">
          <Stage anim={anim} t={t} height={stageHeight} />
          {lesson?.watchFor && (
            <div className="px-3.5 py-2.5 border-t border-border/60 bg-card/30 flex items-start gap-2">
              <Eye className="h-3.5 w-3.5 shrink-0 mt-0.5" style={{ color: anim.hex }} />
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: anim.hex }}>{S.watchFor}</div>
                <div className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">{lesson.watchFor}</div>
              </div>
            </div>
          )}
          {lesson?.numbers && lesson.numbers.length > 0 && (
            <div className="grid grid-cols-2 gap-px bg-border/50 border-t border-border/60">
              {lesson.numbers.map(([k, v]) => (
                <div key={k} className="bg-card/40 px-3 py-2">
                  <div className="text-[11px] font-mono font-bold" style={{ color: anim.hex }}>{v}</div>
                  <div className="text-[9px] text-muted-foreground leading-tight">{k}</div>
                </div>
              ))}
            </div>
          )}
          <div className="px-3 py-2 border-t border-border/60 bg-card/30 flex items-center gap-1.5 mt-auto">
            <button onClick={() => setRunning(r => !r)}
              className="h-7 px-2.5 rounded-md flex items-center gap-1.5 text-[10px] font-semibold text-background" style={{ background: anim.hex }}>
              {running ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}{running ? 'Pause' : 'Play'}
            </button>
            <button onClick={() => setSpeed(s => (s === 1 ? 0.5 : s === 0.5 ? 2 : 1))}
              className="h-7 px-2 rounded-md flex items-center gap-1 text-[10px] font-mono text-muted-foreground hover:text-foreground border border-border">
              <Gauge className="h-3 w-3" />{speed}×
            </button>
            <span className="ml-auto text-[10px] text-muted-foreground font-mono">{anim.tag}</span>
          </div>
        </div>

        <div className="flex-1 min-w-0 flex flex-col">
          <div className="flex gap-0.5 px-2 pt-2 border-b border-border overflow-x-auto">
            {tabs.map(tb => {
              const Icon = tb.icon;
              const active = tab === tb.id;
              return (
                <button key={tb.id} onClick={() => setTab(tb.id)}
                  className={`px-2.5 py-1.5 rounded-t-md text-[11px] font-medium flex items-center gap-1.5 whitespace-nowrap border-b-2 transition-colors ${
                    active ? 'text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                  style={active ? { borderColor: anim.hex } : undefined}>
                  <Icon className="h-3.5 w-3.5" style={active ? { color: anim.hex } : undefined} />
                  {tb.label}
                </button>
              );
            })}
          </div>
          <div className="p-4 space-y-4" dir={ar ? 'rtl' : 'ltr'}>
            {lang === 'ar' && !hasAr && (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300" dir="rtl">
                {UI_STRINGS.ar.noArabic}
              </div>
            )}
            <LessonBody lesson={lesson} anim={anim} ar={ar} S={S} tab={tab} />
          </div>
        </div>
      </div>
    </div>
  );
}

function LessonPanel({
  anim, t, running, speed, onClose, onToggle, onSpeed,
}: {
  anim: MicroAnim; t: number; running: boolean; speed: number;
  onClose: () => void; onToggle: () => void; onSpeed: () => void;
}) {
  const [tab, setTab] = useState<TabId>('all');
  const [lang, setLang] = useLessonLang();
  const hasAr = !!anim.lessonAr;
  const ar = lang === 'ar' && hasAr;
  const lesson = ar ? anim.lessonAr : anim.lesson;
  const S = UI_STRINGS[ar ? 'ar' : 'en'];
  const title = ar ? (anim.partAr ?? anim.part) : anim.part;
  const summary = ar ? (anim.summaryAr ?? anim.summary) : anim.summary;

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const tabs = tabMeta(ar ? 'ar' : 'en').filter(tb => {
    if (!lesson) return tb.id === 'all';
    if (tb.id === 'practice') return (lesson.practice?.length ?? 0) > 0;
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-3 sm:p-6" onClick={onClose}>
      <div className="w-full max-w-5xl max-h-[92vh] rounded-xl border border-border bg-card shadow-2xl overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-border shrink-0">
          <span className="h-8 w-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: `${anim.hex}1a`, border: `1px solid ${anim.hex}55` }}>
            <GraduationCap className="h-4 w-4" style={{ color: anim.hex }} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-foreground truncate" dir={ar ? 'rtl' : 'ltr'}>{title}</div>
            <div className="text-[10px] font-mono text-muted-foreground">{anim.tag} · {S.miniLesson}</div>
          </div>
          <LangToggle lang={lang} setLang={setLang} hasAr={hasAr} />
          <button onClick={onClose} className="h-7 w-7 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40 shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
          {/* Simulation — stays live while you read */}
          <div className="lg:w-[46%] shrink-0 border-b lg:border-b-0 lg:border-r border-border flex flex-col bg-[#060a12]">
            <Stage anim={anim} t={t} height={230} />
            {lesson?.watchFor && (
              <div className="px-3.5 py-2.5 border-t border-border/60 bg-card/30">
                <div className="flex items-start gap-2">
                  <Eye className="h-3.5 w-3.5 shrink-0 mt-0.5" style={{ color: anim.hex }} />
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: anim.hex }}>Watch for</div>
                    <div className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">{lesson.watchFor}</div>
                  </div>
                </div>
              </div>
            )}
            {lesson?.numbers && lesson.numbers.length > 0 && (
              <div className="grid grid-cols-2 gap-px bg-border/50 border-t border-border/60">
                {lesson.numbers.map(([k, v]) => (
                  <div key={k} className="bg-card/40 px-3 py-2">
                    <div className="text-[11px] font-mono font-bold" style={{ color: anim.hex }}>{v}</div>
                    <div className="text-[9px] text-muted-foreground leading-tight">{k}</div>
                  </div>
                ))}
              </div>
            )}
            <div className="px-3 py-2 border-t border-border/60 bg-card/30 flex items-center gap-1.5 mt-auto">
              <button onClick={onToggle}
                className="h-7 px-2.5 rounded-md flex items-center gap-1.5 text-[10px] font-semibold text-background" style={{ background: anim.hex }}>
                {running ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}{running ? 'Pause' : 'Play'}
              </button>
              <button onClick={onSpeed}
                className="h-7 px-2 rounded-md flex items-center gap-1 text-[10px] font-mono text-muted-foreground hover:text-foreground border border-border">
                <Gauge className="h-3 w-3" />{speed}×
              </button>
              <span className="text-[10px] text-muted-foreground ml-auto">Esc to close</span>
            </div>
          </div>

          {/* Lesson */}
          <div className="flex-1 min-w-0 flex flex-col">
            <div className="flex gap-0.5 px-2 pt-2 border-b border-border overflow-x-auto shrink-0">
              {tabs.map(tb => {
                const Icon = tb.icon;
                const active = tab === tb.id;
                return (
                  <button key={tb.id} onClick={() => setTab(tb.id)}
                    className={`px-2.5 py-1.5 rounded-t-md text-[11px] font-medium flex items-center gap-1.5 whitespace-nowrap border-b-2 transition-colors ${
                      active ? 'text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                    style={active ? { borderColor: anim.hex } : undefined}>
                    <Icon className="h-3.5 w-3.5" style={active ? { color: anim.hex } : undefined} />
                    {tb.label}
                  </button>
                );
              })}
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4" dir={ar ? 'rtl' : 'ltr'}>
              {lang === 'ar' && !hasAr && (
                <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300" dir="rtl">
                  {UI_STRINGS.ar.noArabic}
                </div>
              )}
              <LessonBody lesson={lesson} anim={anim} ar={ar} S={S} tab={tab} />
            </div>

            <div className="px-4 py-2 border-t border-border shrink-0 flex items-center gap-2">
              <BookOpen className="h-3 w-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground">
                {tabs.find(x => x.id === tab)?.hint}
              </span>
              <div className="flex-1" />
              {tabs.length > 1 && (
                <button
                  onClick={() => setTab(tabs[(tabs.findIndex(x => x.id === tab) + 1) % tabs.length].id)}
                  className="h-6 px-2 rounded flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground border border-border">
                  {S.next} <ChevronRight className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
