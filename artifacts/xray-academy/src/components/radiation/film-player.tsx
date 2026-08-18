import { useState, useEffect, useRef, useCallback } from 'react';
import type { ReactNode } from 'react';
import { Play, Pause, RotateCcw, SkipBack, SkipForward, Repeat, Gauge, Subtitles, Maximize2, Minimize2 } from 'lucide-react';
import { useLessonLang } from './anim-gallery';
import { FILM_CHAPTERS_AR, FILM_META_AR, PLAYER_STRINGS } from './lessons-ar-course';

// ═══════════════════════════════════════════════════════════════════════════════
// Physics "film" engine — a time-line driven, chaptered SVG animation player.
// Scenes are pure functions of a clock, so they can be scrubbed, paused and
// replayed exactly like a video without shipping any media files.
// ═══════════════════════════════════════════════════════════════════════════════

export interface FilmChapter {
  /** Chapter start time in seconds */
  t: number;
  title: string;
  /** Narration line shown in the caption bar while this chapter plays */
  caption: string;
  /** Optional technical footnote shown under the caption */
  detail?: string;
}

export interface SceneCtx {
  /** Absolute film time, seconds */
  t: number;
  /** Active chapter index */
  ch: number;
  /** Progress inside the active chapter, 0 → 1 */
  p: number;
  /** Whether the clock is currently running */
  playing: boolean;
}

export interface Film {
  id: string;
  title: string;
  tagline: string;
  /** Total run time in seconds */
  duration: number;
  /** Tailwind text colour class used for accents */
  accent: string;
  /** Raw hex used inside the SVG */
  hex: string;
  chapters: FilmChapter[];
  scene: (ctx: SceneCtx) => ReactNode;
  /** Key numbers shown under the player */
  facts?: { label: string; value: string }[];
}

// ─── Maths helpers shared by every scene ──────────────────────────────────────
export const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
export const lerp = (a: number, b: number, p: number) => a + (b - a) * clamp(p);
/** Smooth-step easing, 0 → 1 */
export const ease = (p: number) => { const x = clamp(p); return x * x * (3 - 2 * x); };
/** Loops a value in [0,1) at `hz` cycles per second */
export const cycle = (t: number, hz = 1) => (t * hz) % 1;
/** Fade-in / hold / fade-out envelope for a chapter-local progress value */
export const fade = (p: number, inAt = 0.08, outAt = 0.92) =>
  p < inAt ? clamp(p / inAt) : p > outAt ? clamp((1 - p) / (1 - outAt)) : 1;

export const fmtTime = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
};

// ─── Small SVG building blocks ────────────────────────────────────────────────
export function SceneDefs() {
  return (
    <defs>
      <marker id="fp-arrow" viewBox="0 0 8 8" refX="4" refY="4" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M 0 0 L 8 4 L 0 8 z" fill="currentColor" />
      </marker>
      <radialGradient id="fp-glow">
        <stop offset="0%" stopColor="#fde047" stopOpacity="0.85" />
        <stop offset="100%" stopColor="#fde047" stopOpacity="0" />
      </radialGradient>
      <radialGradient id="fp-hot">
        <stop offset="0%" stopColor="#f87171" stopOpacity="0.9" />
        <stop offset="100%" stopColor="#7f1d1d" stopOpacity="0" />
      </radialGradient>
      <linearGradient id="fp-beam" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stopColor="#60a5fa" stopOpacity="0.05" />
        <stop offset="100%" stopColor="#60a5fa" stopOpacity="0.55" />
      </linearGradient>
    </defs>
  );
}

/** Labelled rounded box used for machine subassemblies */
export function Box({
  x, y, w, h, label, sub, stroke = '#475569', fill = '#111c2e', dim = false, r = 6,
}: { x: number; y: number; w: number; h: number; label?: string; sub?: string; stroke?: string; fill?: string; dim?: boolean; r?: number }) {
  return (
    <g opacity={dim ? 0.28 : 1}>
      <rect x={x} y={y} width={w} height={h} rx={r} fill={fill} stroke={stroke} strokeWidth="1.5" />
      {label && <text x={x + w / 2} y={y + h / 2 + (sub ? -2 : 3)} textAnchor="middle" fontSize="9" fill={stroke === '#475569' ? '#cbd5e1' : stroke}>{label}</text>}
      {sub && <text x={x + w / 2} y={y + h / 2 + 10} textAnchor="middle" fontSize="7" fill="#94a3b8">{sub}</text>}
    </g>
  );
}

/** Annotation text with an optional leader line */
export function Note({ x, y, text, color = '#94a3b8', size = 8, anchor = 'start' }:
{ x: number; y: number; text: string; color?: string; size?: number; anchor?: 'start' | 'middle' | 'end' }) {
  return <text x={x} y={y} fontSize={size} fill={color} textAnchor={anchor}>{text}</text>;
}

/** A moving particle with a soft halo */
export function Dot({ x, y, r = 3.5, color = '#60a5fa', opacity = 1, halo = true }:
{ x: number; y: number; r?: number; color?: string; opacity?: number; halo?: boolean }) {
  return (
    <g opacity={opacity}>
      {halo && <circle cx={x} cy={y} r={r * 2.6} fill={color} opacity={0.16} />}
      <circle cx={x} cy={y} r={r} fill={color} />
    </g>
  );
}

/** Wavy photon glyph travelling along a direction */
export function Wave({ x, y, angle, len = 34, color = '#fde047', amp = 3.5, phase = 0, width = 1.4 }:
{ x: number; y: number; angle: number; len?: number; color?: string; amp?: number; phase?: number; width?: number }) {
  const pts: string[] = [];
  const steps = 16;
  for (let i = 0; i <= steps; i++) {
    const d = (i / steps) * len;
    const off = Math.sin((i / steps) * Math.PI * 4 + phase) * amp;
    pts.push(`${d.toFixed(1)},${off.toFixed(1)}`);
  }
  return (
    <g transform={`translate(${x} ${y}) rotate(${(angle * 180) / Math.PI})`}>
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" />
      <polygon points={`${len},0 ${len - 5},-3 ${len - 5},3`} fill={color} />
    </g>
  );
}

/** Chapter caption plate drawn inside the stage */
export function Plate({ x, y, w, lines, color = '#38bdf8' }: { x: number; y: number; w: number; lines: string[]; color?: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={14 + lines.length * 11} rx="4" fill="#0b1220" stroke={color} strokeOpacity="0.35" strokeWidth="1" />
      {lines.map((l, i) => (
        <text key={i} x={x + 8} y={y + 15 + i * 11} fontSize="8" fill={i === 0 ? color : '#94a3b8'}>{l}</text>
      ))}
    </g>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// The player
// ═══════════════════════════════════════════════════════════════════════════════
const SPEEDS = [0.5, 1, 1.5, 2];

export function PhysicsFilm({
  film, autoPlay = false, startAt, seekKey,
}: {
  film: Film;
  autoPlay?: boolean;
  /** Seconds to jump to when the player mounts or `seekKey` changes */
  startAt?: number;
  /** Change this to force a re-seek — e.g. the course lesson key */
  seekKey?: string | number;
}) {
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);
  const [speed, setSpeed] = useState(1);
  const [loop, setLoop] = useState(true);
  const [captions, setCaptions] = useState(true);
  const [big, setBig] = useState(false);

  const timeRef = useRef(0);
  const rafRef = useRef<number>(0);
  const lastRef = useRef<number | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  // Arabic layer — chapter titles, narration and the player chrome
  const [lang] = useLessonLang();
  const arCh = FILM_CHAPTERS_AR[film.id];
  const ar = lang === 'ar' && !!arCh;
  const P = PLAYER_STRINGS[ar ? 'ar' : 'en'];
  const meta = ar ? FILM_META_AR[film.id] : undefined;
  const chTitle = (i: number) => (ar ? arCh[i]?.title : undefined) ?? film.chapters[i].title;

  // rAF clock — decoupled from React state so seeking stays exact
  useEffect(() => {
    if (!playing) { lastRef.current = null; return; }
    const loopFn = (ts: number) => {
      if (lastRef.current === null) lastRef.current = ts;
      const dt = ((ts - lastRef.current) / 1000) * speed;
      lastRef.current = ts;
      let next = timeRef.current + dt;
      if (next >= film.duration) {
        if (loop) next = next % film.duration;
        else { next = film.duration; setPlaying(false); }
      }
      timeRef.current = next;
      setTime(next);
      rafRef.current = requestAnimationFrame(loopFn);
    };
    rafRef.current = requestAnimationFrame(loopFn);
    return () => cancelAnimationFrame(rafRef.current);
  }, [playing, speed, loop, film.duration]);

  // Reset when the film changes, then honour any requested start position.
  // Without this, every chapter lesson in a course would show the film from 0:00.
  useEffect(() => {
    const at = startAt ?? 0;
    timeRef.current = at;
    setTime(at);
    lastRef.current = null;
  }, [film.id, startAt, seekKey]);

  const seek = useCallback((s: number) => {
    const v = clamp(s, 0, film.duration);
    timeRef.current = v;
    setTime(v);
  }, [film.duration]);

  const chIndex = (() => {
    let idx = 0;
    for (let i = 0; i < film.chapters.length; i++) if (time >= film.chapters[i].t) idx = i;
    return idx;
  })();
  const ch = film.chapters[chIndex];
  const chEnd = chIndex + 1 < film.chapters.length ? film.chapters[chIndex + 1].t : film.duration;
  const chProgress = clamp((time - ch.t) / Math.max(0.001, chEnd - ch.t));

  const onTrack = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = trackRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    seek(((e.clientX - rect.left) / rect.width) * film.duration);
  };

  const jump = (dir: -1 | 1) => {
    if (dir === -1) {
      // restart current chapter unless we just entered it
      if (time - ch.t > 1.2 || chIndex === 0) seek(ch.t);
      else seek(film.chapters[chIndex - 1].t);
    } else {
      seek(chIndex + 1 < film.chapters.length ? film.chapters[chIndex + 1].t : 0);
    }
  };

  return (
    <div className={`rounded-xl border border-border bg-[#080d17] overflow-hidden ${big ? 'fixed inset-4 z-50 shadow-2xl flex flex-col' : ''}`}>
      {/* Title bar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/70 bg-card/40 shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-red-400">{P.film}</span>
        </div>
        <div className="min-w-0 flex-1" dir={ar ? 'rtl' : 'ltr'}>
          <div className={`text-xs font-bold truncate ${film.accent}`}>{meta?.title ?? film.title}</div>
          <div className="text-[10px] text-muted-foreground truncate">{meta?.tagline ?? film.tagline}</div>
        </div>
        <span className="text-[10px] font-mono text-muted-foreground shrink-0 hidden sm:block">
          {film.chapters.length} {P.chapters} · {fmtTime(film.duration)}
        </span>
        <button onClick={() => setBig(b => !b)} title={big ? P.exitTheatre : P.theatre}
          className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors shrink-0">
          {big ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Stage */}
      <div className={`relative bg-[#060a12] ${big ? 'flex-1 min-h-0 flex items-center justify-center' : ''}`}>
        <svg viewBox="0 0 640 300" className={`w-full ${big ? 'h-full' : ''}`} style={{ fontFamily: 'ui-monospace, monospace', display: 'block' }}>
          <SceneDefs />
          {/* Faint engineering grid */}
          <g opacity="0.16">
            {Array.from({ length: 16 }, (_, i) => <line key={`v${i}`} x1={i * 40} y1={0} x2={i * 40} y2={300} stroke="#1e293b" strokeWidth="0.5" />)}
            {Array.from({ length: 8 }, (_, i) => <line key={`h${i}`} x1={0} y1={i * 40} x2={640} y2={i * 40} stroke="#1e293b" strokeWidth="0.5" />)}
          </g>

          {film.scene({ t: time, ch: chIndex, p: chProgress, playing })}

          {/* Chapter chip */}
          <g opacity="0.95">
            <rect x="10" y="8" width={Math.min(430, 22 + ch.title.length * 5.6)} height="18" rx="4" fill="#0b1220" stroke={film.hex} strokeOpacity="0.4" />
            <text x="18" y="21" fontSize="9" fill={film.hex} fontWeight="bold">
              {String(chIndex + 1).padStart(2, '0')} · {ch.title.toUpperCase()}
            </text>
          </g>
          <text x="630" y="21" fontSize="9" fill="#475569" textAnchor="end">{fmtTime(time)} / {fmtTime(film.duration)}</text>
        </svg>

        {/* Caption bar */}
        {captions && (
          <div className="absolute inset-x-0 bottom-0 px-4 py-2 bg-gradient-to-t from-[#060a12] via-[#060a12]/95 to-transparent">
            <p className="text-[11px] leading-relaxed text-slate-200 max-w-3xl" dir={ar ? 'rtl' : 'ltr'}>
              {(ar ? arCh[chIndex]?.caption : undefined) ?? ch.caption}
            </p>
            {((ar ? arCh[chIndex]?.detail : undefined) ?? ch.detail) && (
              <p className="text-[10px] leading-relaxed text-muted-foreground mt-0.5 max-w-3xl" dir={ar ? 'rtl' : 'ltr'}>
                {(ar ? arCh[chIndex]?.detail : undefined) ?? ch.detail}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Transport */}
      <div className="px-3 pt-2 pb-3 bg-card/40 border-t border-border/70 shrink-0">
        {/* Seek track with chapter ticks */}
        <div
          ref={trackRef}
          onPointerDown={e => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); onTrack(e); }}
          onPointerMove={e => { if (e.buttons === 1) onTrack(e); }}
          className="relative h-4 flex items-center cursor-pointer group"
        >
          <div className="h-1 w-full rounded-full bg-muted/60 overflow-hidden">
            <div className="h-full rounded-full transition-[width] duration-75" style={{ width: `${(time / film.duration) * 100}%`, background: film.hex }} />
          </div>
          {film.chapters.map((c, i) => (
            <span key={i} title={chTitle(i)}
              className="absolute h-2.5 w-[2px] rounded-full bg-background/80 pointer-events-none"
              style={{ left: `${(c.t / film.duration) * 100}%` }} />
          ))}
          <span className="absolute h-3 w-3 rounded-full border-2 border-background pointer-events-none shadow"
            style={{ left: `calc(${(time / film.duration) * 100}% - 6px)`, background: film.hex }} />
        </div>

        <div className="flex items-center gap-1 mt-1.5 flex-wrap">
          <button onClick={() => setPlaying(p => !p)}
            className="h-7 w-7 rounded-md flex items-center justify-center text-background shrink-0" style={{ background: film.hex }}>
            {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </button>
          <button onClick={() => jump(-1)} className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40">
            <SkipBack className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => jump(1)} className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40">
            <SkipForward className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => { seek(0); setPlaying(true); }} className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40">
            <RotateCcw className="h-3.5 w-3.5" />
          </button>

          <span className="text-[10px] font-mono text-muted-foreground px-2 shrink-0">{fmtTime(time)} / {fmtTime(film.duration)}</span>

          <div className="flex-1" />

          <button onClick={() => setSpeed(s => SPEEDS[(SPEEDS.indexOf(s) + 1) % SPEEDS.length])}
            title={P.speed}
            className="h-7 px-2 rounded-md flex items-center gap-1 text-[10px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted/40">
            <Gauge className="h-3 w-3" />{speed}×
          </button>
          <button onClick={() => setLoop(l => !l)} title={P.loop}
            className={`h-7 w-7 rounded-md flex items-center justify-center hover:bg-muted/40 ${loop ? 'text-emerald-400' : 'text-muted-foreground'}`}>
            <Repeat className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => setCaptions(c => !c)} title={P.captions}
            className={`h-7 w-7 rounded-md flex items-center justify-center hover:bg-muted/40 ${captions ? 'text-sky-400' : 'text-muted-foreground'}`}>
            <Subtitles className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Chapter list */}
        <div className="flex flex-wrap gap-1 mt-2">
          {film.chapters.map((c, i) => (
            <button key={i} onClick={() => { seek(c.t); setPlaying(true); }}
              className={`text-[10px] px-2 py-1 rounded border transition-colors text-left ${
                i === chIndex
                  ? 'border-current bg-current/10 text-foreground'
                  : 'border-border/50 text-muted-foreground hover:border-border hover:text-foreground'
              }`}
              style={i === chIndex ? { borderColor: film.hex, color: film.hex } : undefined}>
              <span className="font-mono opacity-70 mr-1">{fmtTime(c.t)}</span>{chTitle(i)}
            </button>
          ))}
        </div>
      </div>

      {/* Key numbers */}
      {film.facts && film.facts.length > 0 && !big && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border/60 border-t border-border/70">
          {film.facts.map(f => (
            <div key={f.label} className="bg-card/40 px-3 py-2">
              <div className={`text-[11px] font-mono font-bold ${film.accent}`}>{f.value}</div>
              <div className="text-[9px] text-muted-foreground leading-tight">{f.label}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
