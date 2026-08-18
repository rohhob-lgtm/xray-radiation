import { useState, useEffect, useRef } from 'react';
import { Link } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sparkles, Loader2, Wand2, ArrowLeft, Send, FileText,
  Bot, User, AlertCircle, CheckCircle2, Layers,
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── Types ─────────────────────────────────────────────────────────────────────

interface Slide {
  id: string;
  slide_index: number;
  type: string;
  title: string;
  bullets: string[];
  speaker_notes: string;
  source_pages: number[];
  is_visible: boolean;
}

interface Project {
  id: string;
  course_title: string;
  manufacturer: string;
  equipment_model: string;
  slide_count: number;
  status: string;
  updated_at: string;
  slides?: Slide[];
}

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  slideIdx?: number;
}

const SLIDE_TYPE_LABEL: Record<string, string> = {
  title: 'Title', agenda: 'Agenda', section: 'Section', objectives: 'Objectives',
  content: 'Content', quiz: 'Quiz', practical: 'Practical', summary: 'Summary',
  references: 'References', image_content: 'Diagram',
};

// ── AI Presentation Studio ──────────────────────────────────────────────────────
//
// New, additive module inspired by Gamma.app's "chat with your deck" agent.
// Reuses the existing Training Generator's data (projects/slides) — does not
// modify the Training Generator page or its endpoints. This is Phase 1 of a
// larger planned Studio: the AI Assistant chat panel, wired to the new
// /training/projects/{id}/slides/{idx}/refine backend endpoint.

export default function PresentationStudioPage() {
  const { toast } = useToast();

  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loadingProject, setLoadingProject] = useState(false);

  const [selectedSlideIdx, setSelectedSlideIdx] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [instruction, setInstruction] = useState('');
  const [refining, setRefining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchProjects();
  }, []);

  useEffect(() => {
    if (selectedProjectId) fetchProject(selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const fetchProjects = async () => {
    try {
      setLoadingProjects(true);
      const r = await fetch(`${API}/api/training/projects`, { credentials: 'include' });
      if (!r.ok) throw new Error(await r.text());
      const data: Project[] = await r.json();
      setProjects(data.filter((p) => (p.slide_count || 0) > 0));
    } catch (e: any) {
      setError(e.message || 'Failed to load projects');
    } finally {
      setLoadingProjects(false);
    }
  };

  const fetchProject = async (id: string) => {
    try {
      setLoadingProject(true);
      setError(null);
      const r = await fetch(`${API}/api/training/project/${id}`, { credentials: 'include' });
      if (!r.ok) throw new Error(await r.text());
      const data: Project = await r.json();
      setProject(data);
      setSelectedSlideIdx(data.slides && data.slides.length > 0 ? data.slides[0].slide_index : null);
      setMessages([]);
    } catch (e: any) {
      setError(e.message || 'Failed to load project');
    } finally {
      setLoadingProject(false);
    }
  };

  const currentSlide = project?.slides?.find((s) => s.slide_index === selectedSlideIdx) ?? null;

  const sendInstruction = async () => {
    const text = instruction.trim();
    if (!text || !project || selectedSlideIdx === null || refining) return;

    setMessages((m) => [...m, { role: 'user', text, slideIdx: selectedSlideIdx }]);
    setInstruction('');
    setRefining(true);

    try {
      const r = await fetch(
        `${API}/api/training/projects/${project.id}/slides/${selectedSlideIdx}/refine`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ instruction: text }),
          credentials: 'include',
        }
      );
      if (!r.ok) {
        const detail = await r.text();
        throw new Error(detail || 'Refinement failed');
      }
      const data = await r.json();
      setProject((p) => {
        if (!p || !p.slides) return p;
        return {
          ...p,
          slides: p.slides.map((s) =>
            s.slide_index === selectedSlideIdx
              ? { ...s, title: data.slide.title, bullets: data.slide.bullets, speaker_notes: data.slide.speaker_notes }
              : s
          ),
        };
      });
      setMessages((m) => [...m, { role: 'assistant', text: `Updated slide ${selectedSlideIdx + 1}: "${data.slide.title}"`, slideIdx: selectedSlideIdx }]);
      toast({ title: 'Slide updated', description: `Slide ${selectedSlideIdx + 1} refined successfully.` });
    } catch (e: any) {
      const msg = e.message || 'Something went wrong';
      setMessages((m) => [...m, { role: 'assistant', text: `⚠ ${msg}` }]);
      toast({ title: 'Refinement failed', description: msg, variant: 'destructive' });
    } finally {
      setRefining(false);
    }
  };

  // ── Project picker ──────────────────────────────────────────────────────────

  if (!selectedProjectId) {
    return (
      <div className="p-6 max-w-5xl mx-auto space-y-6" data-testid="page-presentation-studio">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-violet-500 to-sky-500 flex items-center justify-center">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">AI Presentation Studio</h1>
            <p className="text-sm text-muted-foreground">Chat with your generated courses to refine them, Gamma-style.</p>
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {loadingProjects ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <Layers className="h-10 w-10 mx-auto mb-3 opacity-40" />
            <p>No generated courses yet. Create one in Training Generator first.</p>
            <Link href="/training/new">
              <Button className="mt-4" data-testid="button-go-to-training">Go to Training Generator</Button>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedProjectId(p.id)}
                data-testid={`card-studio-project-${p.id}`}
                className="text-left rounded-xl border border-border bg-card p-4 hover:border-violet-500/50 hover:shadow-md transition-all"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold line-clamp-2">{p.course_title}</h3>
                  <Badge variant="outline" className="shrink-0">{p.slide_count} slides</Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {p.manufacturer} {p.equipment_model}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Studio workspace ─────────────────────────────────────────────────────────

  return (
    <div className="h-[calc(100vh-2rem)] flex flex-col p-4 gap-3" data-testid="page-presentation-studio-workspace">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => { setSelectedProjectId(null); setProject(null); }} data-testid="button-back-to-picker">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-violet-500 to-sky-500 flex items-center justify-center">
          <Sparkles className="h-4 w-4 text-white" />
        </div>
        <div>
          <h1 className="font-semibold leading-tight">{project?.course_title || 'Loading…'}</h1>
          <p className="text-xs text-muted-foreground">AI Presentation Studio</p>
        </div>
      </div>

      {loadingProject ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[280px_1fr_360px] gap-3 min-h-0">
          {/* Slide list */}
          <div className="rounded-xl border border-border bg-card overflow-hidden flex flex-col min-h-0">
            <div className="px-3 py-2 border-b border-border text-xs font-medium text-muted-foreground">
              Slides ({project?.slides?.length || 0})
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2 space-y-1">
                {project?.slides?.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedSlideIdx(s.slide_index)}
                    data-testid={`button-studio-slide-${s.slide_index}`}
                    className={`w-full text-left rounded-lg px-2 py-1.5 text-xs transition-colors ${
                      s.slide_index === selectedSlideIdx
                        ? 'bg-violet-500/10 border border-violet-500/30'
                        : 'hover:bg-muted border border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-muted-foreground shrink-0">{s.slide_index + 1}.</span>
                      <span className="truncate">{s.title || '(untitled)'}</span>
                    </div>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Slide preview */}
          <div className="rounded-xl border border-border bg-card p-6 overflow-y-auto min-h-0">
            {currentSlide ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{SLIDE_TYPE_LABEL[currentSlide.type] || currentSlide.type}</Badge>
                  <span className="text-xs text-muted-foreground">Slide {currentSlide.slide_index + 1}</span>
                  {currentSlide.source_pages?.length > 0 && (
                    <span className="text-xs text-muted-foreground">
                      · Manual p.{currentSlide.source_pages.join(', ')}
                    </span>
                  )}
                </div>
                <h2 className="text-xl font-bold">{currentSlide.title}</h2>
                <ul className="space-y-2">
                  {(currentSlide.bullets || []).map((b, i) => (
                    <li key={i} className="text-sm flex gap-2">
                      <span className="text-violet-400 shrink-0">▸</span>
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
                {currentSlide.speaker_notes && (
                  <div className="mt-6 pt-4 border-t border-border">
                    <p className="text-xs font-medium text-muted-foreground mb-1">Speaker Notes</p>
                    <p className="text-sm text-muted-foreground italic">{currentSlide.speaker_notes}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
                <FileText className="h-5 w-5 mr-2" /> Select a slide
              </div>
            )}
          </div>

          {/* AI Assistant chat */}
          <div className="rounded-xl border border-border bg-card flex flex-col min-h-0">
            <div className="px-3 py-2 border-b border-border flex items-center gap-2">
              <Bot className="h-4 w-4 text-violet-400" />
              <span className="text-xs font-medium">AI Assistant</span>
              {selectedSlideIdx !== null && (
                <Badge variant="outline" className="ml-auto text-[10px]">Slide {selectedSlideIdx + 1}</Badge>
              )}
            </div>
            <ScrollArea className="flex-1 px-3 py-2" ref={scrollRef as any}>
              <div className="space-y-3">
                {messages.length === 0 && (
                  <p className="text-xs text-muted-foreground py-4 text-center">
                    Try: "make this shorter", "simplify the wording", "add a worked example"
                  </p>
                )}
                {messages.map((m, i) => (
                  <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : ''}`}>
                    {m.role === 'assistant' && <Bot className="h-4 w-4 mt-1 text-violet-400 shrink-0" />}
                    <div
                      className={`rounded-lg px-3 py-2 text-xs max-w-[85%] ${
                        m.role === 'user' ? 'bg-violet-500/10 text-foreground' : 'bg-muted'
                      }`}
                    >
                      {m.text}
                    </div>
                    {m.role === 'user' && <User className="h-4 w-4 mt-1 text-muted-foreground shrink-0" />}
                  </div>
                ))}
                {refining && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" /> Refining slide…
                  </div>
                )}
              </div>
            </ScrollArea>
            <div className="p-3 border-t border-border flex gap-2">
              <Textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendInstruction();
                  }
                }}
                placeholder="Ask the assistant to change this slide…"
                className="min-h-[40px] max-h-[100px] text-xs resize-none"
                disabled={!currentSlide || refining}
                data-testid="input-studio-instruction"
              />
              <Button
                size="icon"
                onClick={sendInstruction}
                disabled={!instruction.trim() || !currentSlide || refining}
                data-testid="button-studio-send"
              >
                {refining ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
