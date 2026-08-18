/**
 * Interactive Learning Center — standalone section for the Radiation Sources platform.
 * Quizzes & certificates, an AI tutor, step-by-step guided lessons, and flashcards.
 * Entirely client-side (localStorage for progress) except the AI Tutor tab, which
 * streams from the existing /api/chat/stream endpoint.
 */
import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { detectDirection } from '@/lib/rtl';
import {
  GraduationCap, Bot, Layers, Sparkles, CheckCircle2, XCircle, RotateCcw,
  Send, Square, Award, Clock, BookOpen, ChevronLeft, ChevronRight, Shuffle,
  Printer, User as UserIcon, HelpCircle,
} from 'lucide-react';
import {
  TOPIC_QUIZZES, FLASHCARDS, LESSON_TRACKS,
  type QuizQuestion, type Flashcard, type LessonTrack,
} from '@/data/learning-center';
import { LEARNING_PATHS, type LearningPath } from '@/data/radiation-ext';
import { ANIM_LIST } from './radiation-ext';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ─── localStorage helpers ─────────────────────────────────────────────────
function readLS<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}
function writeLS<T>(key: string, value: T) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

interface QuizProgress { bestScore: number; attempts: number; passedAt?: string; certificate?: { name: string; code: string; date: string } }
type QuizProgressMap = Record<string, QuizProgress>;
type LessonProgressMap = Record<string, { completedSteps: number; done: boolean }>;
type FlashcardStateMap = Record<string, 'known' | 'review'>;

const LS_QUIZ = 'lc_quiz_progress_v1';
const LS_LESSON = 'lc_lesson_progress_v1';
const LS_FLASHCARD = 'lc_flashcard_state_v1';

// ─── Shared local UI helpers (mirrors radiation-ext.tsx visual language) ──
function LCPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card/40 p-5 space-y-3">
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
      <div className="text-sm text-muted-foreground leading-relaxed space-y-2">{children}</div>
    </div>
  );
}

function LCNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3.5 text-sm">
      <HelpCircle className="h-4 w-4 mt-0.5 shrink-0 text-blue-400" />
      <span className="text-foreground/80 leading-relaxed">{children}</span>
    </div>
  );
}

function genCode(pathId: string): string {
  const rand = (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
  return `LC-${pathId.slice(0, 4).toUpperCase()}-${rand.toUpperCase()}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// ─── Tab 1: Quizzes & Certificates ─────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════
function PathQuizRunner({ path, questions, onComplete }: { path: LearningPath; questions: QuizQuestion[]; onComplete: (pct: number) => void }) {
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [answers, setAnswers] = useState<(number | null)[]>(Array(questions.length).fill(null));
  const [done, setDone] = useState(false);
  const reportedRef = useRef(false);

  const q = questions[current];
  const score = answers.filter((a, i) => a === questions[i]?.answer).length;

  useEffect(() => {
    if (done && !reportedRef.current) {
      reportedRef.current = true;
      onComplete(Math.round((score / questions.length) * 100));
    }
  }, [done, score, questions.length, onComplete]);

  const handleSelect = (idx: number) => {
    if (selected !== null) return;
    setSelected(idx);
    const next = [...answers];
    next[current] = idx;
    setAnswers(next);
  };

  const handleNext = () => {
    if (current < questions.length - 1) {
      setCurrent(c => c + 1);
      setSelected(answers[current + 1]);
    } else {
      setDone(true);
    }
  };

  const handleRetry = () => {
    reportedRef.current = false;
    setCurrent(0); setSelected(null); setDone(false);
    setAnswers(Array(questions.length).fill(null));
  };

  if (done) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <div className="rounded-xl border border-border bg-card/60 p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${pct >= 75 ? 'bg-emerald-500/10 ring-1 ring-emerald-500/30' : 'bg-yellow-500/10 ring-1 ring-yellow-500/30'}`}>
            {pct >= 75 ? <CheckCircle2 className="h-6 w-6 text-emerald-400" /> : <HelpCircle className="h-6 w-6 text-yellow-400" />}
          </div>
          <div>
            <div className="font-bold text-lg">{score}/{questions.length} correct — {pct}%</div>
            <div className="text-sm text-muted-foreground">
              {pct >= 75 ? 'Passed — certificate unlocked below.' : 'Below the 75% pass threshold — review the explanations and try again.'}
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {questions.map((qq, i) => (
            <div key={i} className={`rounded-lg border px-3 py-2 text-xs ${answers[i] === qq.answer ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
              <div className="flex items-start gap-2">
                {answers[i] === qq.answer ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" /> : <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />}
                <div>
                  <div className="font-medium text-foreground mb-0.5">{qq.q}</div>
                  <div className="text-muted-foreground">{qq.explanation}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={handleRetry} className="gap-2">
          <RotateCcw className="h-3.5 w-3.5" /> Retry quiz
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card/60 p-5 space-y-4">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Question {current + 1} of {questions.length} — {path.title}</span>
        <span>{score} correct so far</span>
      </div>
      <Progress value={((current + (selected !== null ? 1 : 0)) / questions.length) * 100} />
      <p className="font-medium text-sm text-foreground">{q.q}</p>
      <div className="space-y-2">
        {q.options.map((opt, idx) => {
          const isCorrect = idx === q.answer;
          const isPicked = idx === selected;
          const revealed = selected !== null;
          return (
            <button
              key={idx}
              onClick={() => handleSelect(idx)}
              disabled={revealed}
              className={`w-full text-left text-xs rounded-lg border px-3 py-2 transition-colors ${
                revealed
                  ? isCorrect ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                  : isPicked ? 'border-red-500/40 bg-red-500/10 text-red-200'
                  : 'border-border/50 text-muted-foreground'
                  : 'border-border hover:border-primary/40 text-foreground'
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>
      {selected !== null && (
        <div className="rounded-lg border border-border bg-background/40 p-3 text-xs text-muted-foreground">{q.explanation}</div>
      )}
      <Button size="sm" onClick={handleNext} disabled={selected === null} className="gap-1.5">
        {current < questions.length - 1 ? 'Next question' : 'Finish quiz'} <ChevronRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

function CertificateCard({ path, score, cert }: { path: LearningPath; score: number; cert: { name: string; code: string; date: string } }) {
  return (
    <div className="rounded-xl border-2 border-primary/30 bg-gradient-to-br from-primary/10 to-card/60 p-8 text-center space-y-3 print:border print:bg-white" id="lc-certificate">
      <Award className="h-10 w-10 text-primary mx-auto" />
      <div className="text-xs uppercase tracking-widest text-muted-foreground">Certificate of Completion</div>
      <div className="text-2xl font-bold text-foreground">{cert.name}</div>
      <div className="text-sm text-muted-foreground">has completed the learning path</div>
      <div className="text-lg font-semibold text-primary">{path.title}</div>
      <div className="text-xs text-muted-foreground">with a score of {score}% on {cert.date}</div>
      <div className="text-[10px] font-mono text-muted-foreground/70 pt-2">Verification code: {cert.code}</div>
      <div className="flex justify-center pt-2 print:hidden">
        <Button size="sm" variant="outline" onClick={() => window.print()} className="gap-1.5">
          <Printer className="h-3.5 w-3.5" /> Print / Save as PDF
        </Button>
      </div>
      <p className="text-[10px] text-muted-foreground/70 pt-2 print:hidden">
        This is a platform completion record, not an accredited professional certification. Consult your professional regulatory body for formal qualification requirements.
      </p>
    </div>
  );
}

function QuizzesTab() {
  const [progress, setProgress] = useState<QuizProgressMap>(() => readLS(LS_QUIZ, {}));
  const [activeId, setActiveId] = useState<string | null>(null);
  const [certName, setCertName] = useState('');

  const activePath = LEARNING_PATHS.find(p => p.id === activeId);
  const questions = activeId ? (TOPIC_QUIZZES[activeId] ?? []) : [];

  const handleComplete = (pathId: string, pct: number) => {
    setProgress(prev => {
      const existing = prev[pathId];
      const next: QuizProgressMap = {
        ...prev,
        [pathId]: {
          bestScore: Math.max(existing?.bestScore ?? 0, pct),
          attempts: (existing?.attempts ?? 0) + 1,
          passedAt: pct >= 75 ? (existing?.passedAt ?? new Date().toISOString().slice(0, 10)) : existing?.passedAt,
          certificate: existing?.certificate,
        },
      };
      writeLS(LS_QUIZ, next);
      return next;
    });
  };

  const generateCertificate = (pathId: string, name: string) => {
    setProgress(prev => {
      const existing = prev[pathId];
      if (!existing) return prev;
      const next: QuizProgressMap = {
        ...prev,
        [pathId]: { ...existing, certificate: { name, code: genCode(pathId), date: new Date().toISOString().slice(0, 10) } },
      };
      writeLS(LS_QUIZ, next);
      return next;
    });
  };

  if (activeId && activePath) {
    const pathProgress = progress[activeId];
    const passed = (pathProgress?.bestScore ?? 0) >= 75;
    return (
      <div className="space-y-4">
        <button onClick={() => setActiveId(null)} className="flex items-center gap-1.5 text-xs text-primary hover:underline">
          <ChevronLeft className="h-3.5 w-3.5" /> Back to all paths
        </button>
        {questions.length === 0 ? (
          <LCNote>No quiz is available yet for this path.</LCNote>
        ) : (
          <PathQuizRunner key={activeId} path={activePath} questions={questions} onComplete={pct => handleComplete(activeId, pct)} />
        )}
        {passed && !pathProgress?.certificate && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-2">
            <p className="text-sm font-medium text-emerald-300">You passed! Enter your name to generate a certificate.</p>
            <div className="flex gap-2">
              <Input value={certName} onChange={e => setCertName(e.target.value)} placeholder="Full name" className="bg-card/60 border-border text-sm" />
              <Button size="sm" disabled={!certName.trim()} onClick={() => generateCertificate(activeId, certName.trim())}>Generate</Button>
            </div>
          </div>
        )}
        {pathProgress?.certificate && (
          <CertificateCard path={activePath} score={pathProgress.bestScore} cert={pathProgress.certificate} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <LCPanel title="Quizzes & Certificates">
        <p>Take the quiz for any learning path. Score 75% or higher to unlock a printable completion certificate. Your best score and certificate are saved on this device.</p>
      </LCPanel>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {LEARNING_PATHS.map(p => {
          const pr = progress[p.id];
          const qCount = TOPIC_QUIZZES[p.id]?.length ?? 0;
          return (
            <button key={p.id} onClick={() => setActiveId(p.id)}
              className="p-4 rounded-xl border border-border bg-card/40 text-left hover:border-primary/40 transition-colors space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Badge variant="outline" className={`text-[9px] ${p.color} border-current`}>{p.level}</Badge>
                <span className="text-[10px] text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" />{p.duration}</span>
              </div>
              <h3 className="font-semibold text-sm">{p.title}</h3>
              <p className="text-[11px] text-muted-foreground">{qCount} questions</p>
              {pr && (
                <div className="flex items-center gap-2 pt-1">
                  <Badge variant="outline" className={`text-[9px] ${pr.bestScore >= 75 ? 'text-emerald-400 border-emerald-500/40' : 'text-yellow-400 border-yellow-500/40'}`}>
                    Best: {pr.bestScore}%
                  </Badge>
                  {pr.certificate && <span className="text-[9px] text-primary flex items-center gap-1"><Award className="h-3 w-3" />Certified</span>}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ─── Tab 2: AI Tutor ────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════
const TUTOR_SYSTEM_PREFIX = 'You are the AI tutor embedded in the Radiation Sources & Accelerator Engineering learning platform (X-ray tubes, LINACs, radioisotopes, security/industrial imaging, radiation protection). Answer clearly and concisely for a learner. Question: ';
const STARTER_QUESTIONS = [
  "What's the difference between Co-60 and Cs-137 shielding requirements?",
  'Why does mammography use a molybdenum target instead of tungsten?',
  'Explain ALARA in one paragraph.',
  'When does Compton scattering dominate over the photoelectric effect?',
];

interface TutorMessage { role: 'user' | 'assistant'; content: string }

async function streamTutorReply(question: string, onChunk: (c: string) => void, signal: AbortSignal): Promise<void> {
  const resp = await fetch(`${API}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: TUTOR_SYSTEM_PREFIX + question, conversation_id: null, agent_mode: 'general' }),
    credentials: 'include',
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`Tutor request failed (HTTP ${resp.status})`);

  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let d: any;
        try { d = JSON.parse(line.slice(6)); } catch { continue; }
        if (d.type === 'chunk') onChunk(d.chunk);
        else if (d.type === 'done') return;
        else if (d.type === 'error') throw new Error(d.error || 'The AI tutor returned an error.');
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* already released */ }
  }
}

function TutorMessageBubble({ msg }: { msg: TutorMessage }) {
  const dir = detectDirection(msg.content);
  const isUser = msg.role === 'user';
  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`h-7 w-7 rounded-lg flex items-center justify-center shrink-0 ${isUser ? 'bg-primary/20' : 'bg-fuchsia-500/10 ring-1 ring-fuchsia-500/30'}`}>
        {isUser ? <UserIcon className="h-3.5 w-3.5 text-primary" /> : <Bot className="h-3.5 w-3.5 text-fuchsia-400" />}
      </div>
      <div dir={dir} className={`rounded-xl px-3.5 py-2.5 text-sm max-w-[85%] ${isUser ? 'bg-primary/10 text-foreground' : 'bg-card/60 border border-border text-foreground'} ${dir === 'rtl' ? 'text-right' : 'text-left'}`}>
        {isUser ? msg.content : (
          <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-1.5">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || '…'}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function AiTutorTab() {
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const send = async (question: string) => {
    const text = question.trim();
    if (!text || streaming) return;
    setInput('');
    setMessages(m => [...m, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamTutorReply(text, chunk => {
        setMessages(m => {
          const next = [...m];
          next[next.length - 1] = { role: 'assistant', content: next[next.length - 1].content + chunk };
          return next;
        });
      }, controller.signal);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setMessages(m => {
          const next = [...m];
          next[next.length - 1] = { role: 'assistant', content: `⚠ ${err?.message || 'The tutor is unavailable right now.'}` };
          return next;
        });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  };

  return (
    <div className="space-y-4">
      <LCPanel title="AI Tutor">
        <p>Ask a free-form question about anything on this platform — radiation sources, equipment, physics, or standards. Answers are generated live and are not saved between visits.</p>
      </LCPanel>

      <div className="rounded-xl border border-border bg-card/40 flex flex-col h-[480px]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center gap-4 text-center px-6">
              <Sparkles className="h-8 w-8 text-fuchsia-400/60" />
              <p className="text-xs text-muted-foreground">Try one of these, or ask your own question below.</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full">
                {STARTER_QUESTIONS.map(q => (
                  <button key={q} onClick={() => void send(q)}
                    className="text-left text-[11px] rounded-lg border border-border bg-background/40 hover:border-primary/40 px-3 py-2 text-muted-foreground">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m, i) => <TutorMessageBubble key={i} msg={m} />)
          )}
        </div>
        <div className="border-t border-border p-3 flex items-end gap-2">
          <Textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the AI tutor…"
            rows={1}
            className="resize-none bg-card/60 border-border text-sm min-h-9"
          />
          {streaming ? (
            <Button size="icon" variant="outline" onClick={() => abortRef.current?.abort()} className="shrink-0">
              <Square className="h-3.5 w-3.5" />
            </Button>
          ) : (
            <Button size="icon" disabled={!input.trim()} onClick={() => void send(input)} className="shrink-0">
              <Send className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ─── Tab 3: Step-by-Step Lessons ───────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════
function LessonWizard({ track, onFinish }: { track: LessonTrack; onFinish: (completedSteps: number) => void }) {
  const [stepIdx, setStepIdx] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const step = track.steps[stepIdx];
  const anim = step.animationId ? ANIM_LIST.find(a => a.id === step.animationId) : undefined;
  const AnimComp = anim?.component;
  const isLast = stepIdx === track.steps.length - 1;
  const canAdvance = !step.checkQuestion || selected !== null;

  const advance = () => {
    if (isLast) { onFinish(track.steps.length); return; }
    setStepIdx(i => i + 1);
    setSelected(null);
  };

  return (
    <div className="space-y-4">
      <Progress value={((stepIdx + 1) / track.steps.length) * 100} />
      <div className="rounded-xl border border-border bg-card/40 p-5 space-y-4">
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>Step {stepIdx + 1} of {track.steps.length}</span>
          <span>{track.title}</span>
        </div>
        <h3 className="font-semibold text-base">{step.title}</h3>
        {AnimComp && (
          <div className="rounded-lg bg-[#0a1628] p-3">
            <AnimComp animated />
          </div>
        )}
        <p className="text-sm text-muted-foreground leading-relaxed">{step.explanation}</p>

        {step.checkQuestion && (
          <div className="rounded-lg border border-border bg-background/40 p-3 space-y-2">
            <p className="text-xs font-medium text-foreground flex items-center gap-1.5"><HelpCircle className="h-3.5 w-3.5 text-primary" />{step.checkQuestion.q}</p>
            <div className="space-y-1.5">
              {step.checkQuestion.options.map((opt, idx) => {
                const revealed = selected !== null;
                const isCorrect = idx === step.checkQuestion!.answer;
                return (
                  <button key={idx} disabled={revealed} onClick={() => setSelected(idx)}
                    className={`w-full text-left text-[11px] rounded-md border px-2.5 py-1.5 transition-colors ${
                      revealed
                        ? isCorrect ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                        : idx === selected ? 'border-red-500/40 bg-red-500/10 text-red-200' : 'border-border/40 text-muted-foreground'
                        : 'border-border hover:border-primary/40 text-foreground'
                    }`}>
                    {opt}
                  </button>
                );
              })}
            </div>
            {selected !== null && <p className="text-[11px] text-muted-foreground">{step.checkQuestion.explanation}</p>}
          </div>
        )}

        <div className="flex items-center justify-between pt-1">
          <Button size="sm" variant="ghost" disabled={stepIdx === 0} onClick={() => { setStepIdx(i => i - 1); setSelected(null); }} className="gap-1.5">
            <ChevronLeft className="h-3.5 w-3.5" /> Back
          </Button>
          <Button size="sm" onClick={advance} disabled={!canAdvance} className="gap-1.5">
            {isLast ? 'Finish lesson' : 'Continue'} <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function LessonsTab() {
  const [progress, setProgress] = useState<LessonProgressMap>(() => readLS(LS_LESSON, {}));
  const [activeId, setActiveId] = useState<string | null>(null);
  const [justFinished, setJustFinished] = useState(false);

  const track = LESSON_TRACKS.find(t => t.id === activeId);

  const finishTrack = (completedSteps: number) => {
    if (!activeId) return;
    const next = { ...progress, [activeId]: { completedSteps, done: true } };
    setProgress(next);
    writeLS(LS_LESSON, next);
    setJustFinished(true);
  };

  if (track) {
    return (
      <div className="space-y-4">
        <button onClick={() => { setActiveId(null); setJustFinished(false); }} className="flex items-center gap-1.5 text-xs text-primary hover:underline">
          <ChevronLeft className="h-3.5 w-3.5" /> Back to all lessons
        </button>
        {justFinished ? (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-6 text-center space-y-2">
            <CheckCircle2 className="h-8 w-8 text-emerald-400 mx-auto" />
            <p className="font-semibold">Lesson complete: {track.title}</p>
            <p className="text-xs text-muted-foreground">You worked through all {track.steps.length} steps.</p>
            <Button size="sm" variant="outline" onClick={() => { setActiveId(null); setJustFinished(false); }}>Choose another lesson</Button>
          </div>
        ) : (
          <LessonWizard key={track.id} track={track} onFinish={finishTrack} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <LCPanel title="Step-by-Step Interactive Lessons">
        <p>Guided walkthroughs that combine short explanations, the platform's physics animations, and quick knowledge checks at each step.</p>
      </LCPanel>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {LESSON_TRACKS.map(t => {
          const p = progress[t.id];
          return (
            <button key={t.id} onClick={() => setActiveId(t.id)}
              className="p-4 rounded-xl border border-border bg-card/40 text-left hover:border-primary/40 transition-colors space-y-2">
              <div className="flex items-center justify-between">
                <Layers className="h-4 w-4 text-pink-400" />
                {p?.done && <Badge variant="outline" className="text-[9px] text-emerald-400 border-emerald-500/40">Completed</Badge>}
              </div>
              <h3 className="font-semibold text-sm">{t.title}</h3>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{t.description}</p>
              <p className="text-[10px] text-muted-foreground">{t.steps.length} steps</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ─── Tab 4: Flashcards ──────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════
function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function FlashcardsTab() {
  const categories = ['All', ...Array.from(new Set(FLASHCARDS.map(c => c.category)))];
  const [category, setCategory] = useState('All');
  const [order, setOrder] = useState<Flashcard[]>(FLASHCARDS);
  const [idx, setIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [state, setState] = useState<FlashcardStateMap>(() => readLS(LS_FLASHCARD, {}));

  const filtered = category === 'All' ? order : order.filter(c => c.category === category);
  const card = filtered[idx % Math.max(filtered.length, 1)];

  const goNext = () => { setFlipped(false); setIdx(i => (i + 1) % Math.max(filtered.length, 1)); };

  const mark = (verdict: 'known' | 'review') => {
    if (!card) return;
    const next = { ...state, [card.id]: verdict };
    setState(next);
    writeLS(LS_FLASHCARD, next);
    goNext();
  };

  const knownCount = filtered.filter(c => state[c.id] === 'known').length;
  const reviewCount = filtered.filter(c => state[c.id] === 'review').length;

  return (
    <div className="space-y-5">
      <LCPanel title="Flashcards">
        <p>Quick-review cards drawn from core physics terms and the standards library. Flip a card, then mark it "Got it" or "Review again".</p>
      </LCPanel>

      <div className="flex flex-wrap gap-1.5">
        {categories.map(c => (
          <button key={c} onClick={() => { setCategory(c); setIdx(0); setFlipped(false); }}
            className={`text-[11px] px-2 py-0.5 rounded-md border transition-colors ${category === c ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground hover:border-primary/40'}`}>
            {c}
          </button>
        ))}
      </div>

      {filtered.length === 0 || !card ? (
        <div className="text-center py-12 text-muted-foreground text-sm">No flashcards in this category.</div>
      ) : (
        <>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Card {(idx % filtered.length) + 1} of {filtered.length}</span>
            <span className="flex items-center gap-3">
              <span className="text-emerald-400">{knownCount} known</span>
              <span className="text-yellow-400">{reviewCount} to review</span>
            </span>
          </div>

          <button onClick={() => setFlipped(f => !f)}
            className="w-full min-h-[180px] rounded-xl border border-border bg-card/60 hover:border-primary/40 transition-colors flex flex-col items-center justify-center text-center p-6 gap-2">
            <Badge variant="outline" className="text-[9px] mb-1">{card.category}</Badge>
            <p className="text-sm font-medium text-foreground">{flipped ? card.back : card.front}</p>
            <p className="text-[10px] text-muted-foreground/60 mt-2">{flipped ? 'Click to see the term' : 'Click to reveal the answer'}</p>
          </button>

          <div className="flex items-center justify-between gap-2">
            <Button size="sm" variant="outline" onClick={() => setOrder(shuffle(FLASHCARDS))} className="gap-1.5">
              <Shuffle className="h-3.5 w-3.5" /> Shuffle
            </Button>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => mark('review')} className="gap-1.5 border-yellow-500/40 text-yellow-300">
                Review again
              </Button>
              <Button size="sm" onClick={() => mark('known')} className="gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" /> Got it
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ─── Main export ────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════
export function LearningCenterSection() {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-fuchsia-500/20 bg-fuchsia-500/5 p-6">
        <div className="flex items-start gap-4">
          <div className="h-12 w-12 rounded-xl bg-fuchsia-500/10 flex items-center justify-center ring-1 ring-fuchsia-500/30 shrink-0">
            <GraduationCap className="h-6 w-6 text-fuchsia-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold">Interactive Learning Center</h2>
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
              Test your knowledge with certified quizzes, ask the AI tutor, work through guided step-by-step lessons, and review flashcards — all in one place.
            </p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="quizzes">
        <TabsList className="grid grid-cols-2 sm:grid-cols-4 h-auto p-1 gap-1">
          <TabsTrigger value="quizzes" className="gap-1.5 py-1.5 text-xs"><Award className="h-3.5 w-3.5" />Quizzes & Certificates</TabsTrigger>
          <TabsTrigger value="tutor" className="gap-1.5 py-1.5 text-xs"><Bot className="h-3.5 w-3.5" />AI Tutor</TabsTrigger>
          <TabsTrigger value="lessons" className="gap-1.5 py-1.5 text-xs"><Layers className="h-3.5 w-3.5" />Step-by-Step Lessons</TabsTrigger>
          <TabsTrigger value="flashcards" className="gap-1.5 py-1.5 text-xs"><BookOpen className="h-3.5 w-3.5" />Flashcards</TabsTrigger>
        </TabsList>
        <TabsContent value="quizzes"><QuizzesTab /></TabsContent>
        <TabsContent value="tutor"><AiTutorTab /></TabsContent>
        <TabsContent value="lessons"><LessonsTab /></TabsContent>
        <TabsContent value="flashcards"><FlashcardsTab /></TabsContent>
      </Tabs>
    </div>
  );
}
