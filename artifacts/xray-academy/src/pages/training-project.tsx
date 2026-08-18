import { useState, useEffect, useCallback } from 'react';
import { useParams, useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Download, Trash2, ChevronLeft, Loader2, Edit2, Check, X,
  AlertCircle, BookMarked, Users, FileText, Calendar,
  Package, Eye, EyeOff, ZipIcon, FileDown, Presentation
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
  manual_filename: string;
  manual_page_count: number;
  audience: string;
  training_type: string;
  language: string;
  difficulty: string;
  status: string;
  version_num: number;
  slide_count: number;
  created_at: string;
  updated_at: string;
  settings: Record<string, any>;
  slides: Slide[];
}

// ── Colours ────────────────────────────────────────────────────────────────────

const SLIDE_TYPE_STYLES: Record<string, { badge: string; card: string; label: string }> = {
  title:      { badge: 'bg-sky-500/10 text-sky-300 border-sky-500/20',     card: 'border-l-sky-500',   label: 'Title'       },
  agenda:     { badge: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20', card: 'border-l-indigo-500', label: 'Agenda' },
  section:    { badge: 'bg-violet-500/10 text-violet-300 border-violet-500/20', card: 'border-l-violet-500', label: 'Section' },
  objectives: { badge: 'bg-blue-500/10 text-blue-300 border-blue-500/20',   card: 'border-l-blue-500',  label: 'Objectives' },
  content:    { badge: 'bg-slate-500/10 text-slate-300 border-slate-500/20', card: 'border-l-slate-400', label: 'Content'   },
  quiz:       { badge: 'bg-amber-500/10 text-amber-300 border-amber-500/20', card: 'border-l-amber-500', label: 'Quiz'      },
  practical:  { badge: 'bg-orange-500/10 text-orange-300 border-orange-500/20', card: 'border-l-orange-500', label: 'Practical' },
  summary:    { badge: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', card: 'border-l-emerald-500', label: 'Summary' },
  references: { badge: 'bg-pink-500/10 text-pink-300 border-pink-500/20',   card: 'border-l-pink-500',  label: 'References' },
};

const fallbackStyle = { badge: 'bg-muted text-muted-foreground border-border', card: 'border-l-border', label: 'Slide' };

// ── Slide card renderer ───────────────────────────────────────────────────────

function SlideCard({ slide }: { slide: Slide }) {
  const style = SLIDE_TYPE_STYLES[slide.type] || fallbackStyle;
  const bg: Record<string, string> = {
    title: 'bg-[#0A1628]', section: 'bg-[#1B263B]', agenda: 'bg-[#0A1628]',
    objectives: 'bg-[#0A1628]', content: 'bg-[#0A1628]', quiz: 'bg-[#0A1628]',
    practical: 'bg-[#0A1628]', summary: 'bg-[#0A1628]', references: 'bg-[#0A1628]',
  };
  const bgClass = bg[slide.type] || 'bg-[#0A1628]';

  return (
    <div className={`w-full aspect-video rounded-lg overflow-hidden ${bgClass} relative border border-border/30 shadow-lg`}>
      {/* Top accent bar */}
      <div className="absolute top-0 left-0 right-0 h-[14%] bg-[#1B263B] flex items-center px-4">
        <p className="text-white text-[10px] font-bold truncate"
          style={{ fontSize: 'clamp(7px, 1.2vw, 12px)' }}>
          {slide.type === 'title' ? '' : slide.title}
        </p>
      </div>
      {/* Cyan accent line */}
      <div className="absolute top-[14%] left-0 right-0 h-[1.5px] bg-[#008BD8]" />

      {/* Content area */}
      <div className="absolute top-[16%] left-0 right-0 bottom-[7%] px-4 py-2 overflow-hidden">
        {slide.type === 'title' ? (
          <div className="h-full flex flex-col justify-center gap-1">
            <div className="w-8 h-0.5 bg-[#008BD8] mb-1" />
            <p className="text-white font-bold leading-tight"
              style={{ fontSize: 'clamp(8px, 1.8vw, 18px)' }}>
              {slide.title}
            </p>
            {slide.bullets?.[0] && (
              <p className="text-[#008BD8]" style={{ fontSize: 'clamp(6px, 1.1vw, 11px)' }}>
                {slide.bullets[0]}
              </p>
            )}
          </div>
        ) : slide.type === 'section' ? (
          <div className="h-full flex flex-col justify-center">
            <p className="text-white font-bold" style={{ fontSize: 'clamp(8px, 1.6vw, 16px)' }}>
              {slide.title}
            </p>
          </div>
        ) : (
          <div className="space-y-0.5 pt-1">
            {(slide.bullets || []).slice(0, 5).map((b, i) => (
              <div key={i} className="flex items-start gap-1">
                <span className="text-[#008BD8] shrink-0" style={{ fontSize: 'clamp(5px, 0.9vw, 9px)' }}>▸</span>
                <p className="text-[#E0E1DD] leading-tight line-clamp-1"
                  style={{ fontSize: 'clamp(5px, 0.9vw, 9px)' }}>
                  {b}
                </p>
              </div>
            ))}
            {(slide.bullets?.length || 0) > 5 && (
              <p className="text-[#8D99AE]" style={{ fontSize: 'clamp(4px, 0.8vw, 8px)' }}>
                +{slide.bullets.length - 5} more…
              </p>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="absolute bottom-0 left-0 right-0 h-[7%] bg-[#1B263B] flex items-center px-3 gap-2">
        {slide.source_pages?.length > 0 && (
          <span className="text-[#8D99AE]" style={{ fontSize: 'clamp(4px, 0.8vw, 8px)' }}>
            p.{slide.source_pages.join(', ')}
          </span>
        )}
      </div>

      {/* Type badge overlay */}
      <div className="absolute top-1 right-1">
        <Badge variant="outline" className={`text-[8px] px-1 py-0 border ${style.badge} backdrop-blur-sm`}>
          {style.label}
        </Badge>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function TrainingProjectPage() {
  const params = useParams<{ id: string }>();
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSlide, setSelectedSlide] = useState<number>(0);
  const [editingSlide, setEditingSlide] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [savingSlide, setSavingSlide] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (projectId) fetchProject();
  }, [projectId]);

  const fetchProject = async () => {
    try {
      setLoading(true);
      const r = await fetch(`${API}/api/training/project/${projectId}`, { credentials: 'include' });
      if (!r.ok) throw new Error(await r.text());
      const data: Project = await r.json();
      setProject(data);
      setSelectedSlide(0);
    } catch (e: any) {
      setError(e.message || 'Failed to load project');
    } finally {
      setLoading(false);
    }
  };

  const visibleSlides = project?.slides?.filter(s => s.is_visible) ?? [];
  const currentSlide = visibleSlides[selectedSlide] ?? null;

  const startEdit = (slide: Slide) => {
    setEditingSlide(slide.slide_index);
    setEditTitle(slide.title);
    setEditNotes(slide.speaker_notes);
  };

  const saveEdit = async () => {
    if (editingSlide === null || !project) return;
    setSavingSlide(true);
    try {
      const r = await fetch(
        `${API}/api/training/project/${project.id}/slide/${editingSlide}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: editTitle, speaker_notes: editNotes }),
          credentials: 'include',
        }
      );
      if (!r.ok) throw new Error(await r.text());
      const updated = await r.json();
      setProject(p => p ? {
        ...p, slides: p.slides.map(s => s.slide_index === editingSlide ? { ...s, ...updated } : s)
      } : p);
      setEditingSlide(null);
      toast({ title: 'Slide updated' });
    } catch (e: any) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setSavingSlide(false);
    }
  };

  const toggleVisibility = async (slide: Slide) => {
    if (!project) return;
    try {
      await fetch(
        `${API}/api/training/project/${project.id}/slide/${slide.slide_index}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_visible: !slide.is_visible }),
          credentials: 'include',
        }
      );
      setProject(p => p ? {
        ...p, slides: p.slides.map(s =>
          s.slide_index === slide.slide_index ? { ...s, is_visible: !s.is_visible } : s)
      } : p);
    } catch {}
  };

  const deleteProject = async () => {
    if (!project) return;
    if (!confirm(`Delete "${project.course_title}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await fetch(`${API}/api/training/project/${project.id}`, {
        method: 'DELETE', credentials: 'include',
      });
      navigate('/training');
    } catch (e: any) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
      setDeleting(false);
    }
  };

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Alert className="max-w-md border-destructive/30 bg-destructive/5">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error || 'Project not found'}</AlertDescription>
        </Alert>
      </div>
    );
  }

  const hasSuficientSlides = visibleSlides.length > 0;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/40 px-4 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0"
            onClick={() => navigate('/training')}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/20 shrink-0">
            <BookMarked className="h-4 w-4 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-bold text-foreground truncate">{project.course_title}</h1>
            <p className="text-xs text-muted-foreground truncate">
              {[project.manufacturer, project.equipment_model].filter(Boolean).join(' · ')}
              {project.manual_filename && ` · ${project.manual_filename}`}
            </p>
          </div>

          {/* Export buttons */}
          <div className="flex items-center gap-2 shrink-0">
            <Badge variant="outline" className="text-[10px] hidden sm:flex">
              {visibleSlides.length} slides
            </Badge>

            {hasSuficientSlides && (
              <>
                <div className="hidden md:flex items-center gap-1.5">
                  {[
                    { label: 'Instructor PPTX', version: 'instructor', icon: Presentation },
                    { label: 'Student PPTX',    version: 'student',    icon: Presentation },
                    { label: 'Instructor Guide', version: null, doctype: 'instructor_guide', icon: FileText },
                    { label: 'Student Handbook', version: null, doctype: 'student_handbook',  icon: FileText },
                  ].map(btn => {
                    const href = btn.version
                      ? `${API}/api/training/export/pptx/${project.id}?version=${btn.version}`
                      : `${API}/api/training/export/docx/${project.id}?doc_type=${btn.doctype}`;
                    return (
                      <a key={btn.label} href={href} download>
                        <Button size="sm" variant="outline"
                          className="gap-1.5 h-7 text-[11px] font-medium px-2.5">
                          <btn.icon className="h-3 w-3" />
                          {btn.label}
                        </Button>
                      </a>
                    );
                  })}
                </div>
                <a href={`${API}/api/training/export/zip/${project.id}`} download>
                  <Button size="sm" className="gap-1.5 h-8 text-xs font-semibold">
                    <Download className="h-3.5 w-3.5" />
                    ZIP Package
                  </Button>
                </a>
              </>
            )}

            <Button size="sm" variant="ghost"
              className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
              disabled={deleting} onClick={deleteProject}>
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        {/* Metadata strip */}
        <div className="flex items-center gap-4 mt-2 ml-11 flex-wrap">
          {[
            { icon: Users, text: project.audience },
            { icon: FileText, text: project.training_type },
            { icon: Calendar, text: formatDate(project.created_at) },
          ].map(m => (
            <div key={m.text} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <m.icon className="h-3 w-3" />
              <span>{m.text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Mobile export strip */}
      {hasSuficientSlides && (
        <div className="md:hidden border-b border-border bg-card/20 px-4 py-2 flex gap-2 overflow-x-auto shrink-0">
          {[
            { label: 'Instructor PPTX', href: `${API}/api/training/export/pptx/${project.id}?version=instructor` },
            { label: 'Student PPTX',    href: `${API}/api/training/export/pptx/${project.id}?version=student` },
            { label: 'Instructor DOCX', href: `${API}/api/training/export/docx/${project.id}?doc_type=instructor_guide` },
            { label: 'Student DOCX',    href: `${API}/api/training/export/docx/${project.id}?doc_type=student_handbook` },
          ].map(b => (
            <a key={b.label} href={b.href} download>
              <Button size="sm" variant="outline"
                className="h-7 text-[11px] font-medium whitespace-nowrap gap-1.5">
                <FileDown className="h-3 w-3" />{b.label}
              </Button>
            </a>
          ))}
        </div>
      )}

      {!hasSuficientSlides ? (
        <div className="flex-1 flex items-center justify-center p-6 flex-col gap-4 text-center">
          <BookMarked className="h-12 w-12 text-muted-foreground/30" />
          <div>
            <p className="text-sm font-semibold text-foreground">No slides generated yet</p>
            <p className="text-xs text-muted-foreground mt-1">
              Go back and run the generation step to produce slides.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/training/new')}>
            Create New Course
          </Button>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Slide list sidebar */}
          <div className="w-56 shrink-0 border-r border-border bg-card/20 overflow-y-auto">
            <div className="p-2 space-y-1">
              {project.slides.map((slide, listIdx) => {
                const visIdx = visibleSlides.indexOf(slide);
                const style = SLIDE_TYPE_STYLES[slide.type] || fallbackStyle;
                const isSelected = visIdx === selectedSlide && slide.is_visible;
                return (
                  <button key={slide.id} type="button"
                    onClick={() => {
                      if (visIdx >= 0) setSelectedSlide(visIdx);
                    }}
                    className={`w-full text-left rounded-lg p-2 border-l-2 transition-all group
                      ${isSelected
                        ? `${style.card} bg-primary/10 border-l-primary`
                        : 'border-l-transparent hover:bg-card'}
                      ${!slide.is_visible ? 'opacity-40' : ''}`}>
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] font-mono text-muted-foreground w-5 text-right shrink-0">
                        {visIdx >= 0 ? String(visIdx + 1).padStart(2, '0') : '--'}
                      </span>
                      <div className="flex-1 min-w-0">
                        <Badge variant="outline"
                          className={`text-[8px] px-1 py-0 mb-0.5 border ${style.badge}`}>
                          {style.label}
                        </Badge>
                        <p className="text-[11px] text-foreground leading-tight line-clamp-2">
                          {slide.title || '(untitled)'}
                        </p>
                      </div>
                      <button type="button"
                        className="opacity-0 group-hover:opacity-100 shrink-0 text-muted-foreground hover:text-foreground"
                        onClick={e => { e.stopPropagation(); toggleVisibility(slide); }}
                        title={slide.is_visible ? 'Hide slide' : 'Show slide'}>
                        {slide.is_visible
                          ? <EyeOff className="h-3 w-3" />
                          : <Eye className="h-3 w-3" />}
                      </button>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Main slide view */}
          <div className="flex-1 overflow-auto bg-background p-6 space-y-4">
            {currentSlide ? (
              <>
                {/* Slide navigation */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="icon" className="h-7 w-7"
                      disabled={selectedSlide === 0}
                      onClick={() => setSelectedSlide(i => i - 1)}>
                      <ChevronLeft className="h-3.5 w-3.5" />
                    </Button>
                    <span className="text-xs text-muted-foreground font-mono">
                      {selectedSlide + 1} / {visibleSlides.length}
                    </span>
                    <Button variant="outline" size="icon" className="h-7 w-7"
                      disabled={selectedSlide >= visibleSlides.length - 1}
                      onClick={() => setSelectedSlide(i => i + 1)}>
                      <ChevronLeft className="h-3.5 w-3.5 rotate-180" />
                    </Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline"
                      className={`text-[10px] border ${(SLIDE_TYPE_STYLES[currentSlide.type] || fallbackStyle).badge}`}>
                      {(SLIDE_TYPE_STYLES[currentSlide.type] || fallbackStyle).label}
                    </Badge>
                    {editingSlide !== currentSlide.slide_index && (
                      <Button size="sm" variant="outline"
                        className="h-7 gap-1.5 text-xs"
                        onClick={() => startEdit(currentSlide)}>
                        <Edit2 className="h-3 w-3" /> Edit
                      </Button>
                    )}
                  </div>
                </div>

                {/* Slide preview */}
                <div className="w-full max-w-3xl mx-auto">
                  <SlideCard slide={currentSlide} />
                </div>

                {/* Slide detail / edit */}
                <div className="max-w-3xl mx-auto space-y-4">
                  {editingSlide === currentSlide.slide_index ? (
                    <div className="rounded-xl border border-primary/30 bg-card/60 p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold text-foreground">Edit Slide</p>
                        <div className="flex gap-2">
                          <Button size="sm" variant="ghost"
                            className="h-7 text-xs gap-1.5"
                            onClick={() => setEditingSlide(null)}>
                            <X className="h-3 w-3" /> Cancel
                          </Button>
                          <Button size="sm" className="h-7 text-xs gap-1.5"
                            disabled={savingSlide} onClick={saveEdit}>
                            {savingSlide
                              ? <Loader2 className="h-3 w-3 animate-spin" />
                              : <Check className="h-3 w-3" />}
                            Save
                          </Button>
                        </div>
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Slide Title</label>
                        <Input value={editTitle} onChange={e => setEditTitle(e.target.value)}
                          className="h-8 text-sm" />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Speaker Notes</label>
                        <Textarea value={editNotes} onChange={e => setEditNotes(e.target.value)}
                          rows={3} className="text-sm resize-none" />
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-border bg-card/40 p-4 space-y-3">
                      <p className="text-sm font-semibold text-foreground">{currentSlide.title}</p>

                      {currentSlide.bullets?.length > 0 && (
                        <div className="space-y-1">
                          {currentSlide.bullets.map((b, i) => (
                            <p key={i} className="text-xs text-muted-foreground flex items-start gap-2">
                              <span className="text-primary shrink-0 mt-0.5">▸</span>{b}
                            </p>
                          ))}
                        </div>
                      )}

                      {currentSlide.speaker_notes && (
                        <div className="rounded-lg bg-amber-500/5 border border-amber-500/20 p-3">
                          <p className="text-[10px] font-mono text-amber-400 uppercase tracking-wider mb-1">
                            Instructor Notes
                          </p>
                          <p className="text-xs text-muted-foreground">{currentSlide.speaker_notes}</p>
                        </div>
                      )}

                      {currentSlide.source_pages?.length > 0 && (
                        <div className="flex items-center gap-1.5">
                          <FileText className="h-3 w-3 text-primary/50" />
                          <p className="text-[11px] text-muted-foreground">
                            Source: Manual page{currentSlide.source_pages.length > 1 ? 's' : ''}{' '}
                            {currentSlide.source_pages.join(', ')}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                Select a slide from the list
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
