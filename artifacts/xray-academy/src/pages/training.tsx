import { useState, useEffect } from 'react';
import { Link } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  BookMarked, Plus, Trash2, Download, Loader2, FileText,
  Calendar, Users, Layers, AlertCircle, FolderOpen
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

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
}

const STATUS_COLORS: Record<string, string> = {
  complete:   'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  generating: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
  ready:      'bg-sky-500/10 text-sky-400 border-sky-500/20',
  error:      'bg-red-500/10 text-red-400 border-red-500/20',
};

const AUDIENCE_ICONS: Record<string, string> = {
  'X-Ray Operators': '👨‍✈️',
  'Maintenance Engineers': '🔧',
  'Field Service Engineers': '⚙️',
  'Supervisors': '📋',
  'System Administrators': '💻',
  'Train-the-Trainer': '🎓',
};

export default function TrainingPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const r = await fetch(`${API}/api/training/projects`, { credentials: 'include' });
      if (!r.ok) throw new Error(await r.text());
      setProjects(await r.json());
    } catch (e: any) {
      setError(e.message || 'Failed to load projects');
    } finally {
      setLoading(false);
    }
  };

  const deleteProject = async (id: string, title: string) => {
    if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
    setDeletingId(id);
    try {
      const r = await fetch(`${API}/api/training/project/${id}`, {
        method: 'DELETE', credentials: 'include',
      });
      if (!r.ok) throw new Error(await r.text());
      setProjects(p => p.filter(x => x.id !== id));
      toast({ title: 'Project deleted', description: title });
    } catch (e: any) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

  return (
    <div className="flex flex-col h-full overflow-auto bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/40 px-6 py-4 shrink-0">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/20">
              <BookMarked className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground tracking-tight">Training Material Generator</h1>
              <p className="text-xs text-muted-foreground">Generate professional training courses from equipment manuals</p>
            </div>
          </div>
          <Link href="/training/new">
            <Button size="sm" className="gap-2 font-semibold">
              <Plus className="h-4 w-4" />
              New Course
            </Button>
          </Link>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-6">

          {/* Stats row */}
          {!loading && projects.length > 0 && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              {[
                { label: 'Total Courses', value: projects.length, icon: Layers, color: 'text-sky-400' },
                { label: 'Complete', value: projects.filter(p => p.status === 'complete').length, icon: FileText, color: 'text-emerald-400' },
                { label: 'Total Slides', value: projects.reduce((a, p) => a + (p.slide_count || 0), 0), icon: BookMarked, color: 'text-violet-400' },
              ].map(stat => (
                <div key={stat.label} className="rounded-xl border border-border bg-card/60 p-4 flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-background flex items-center justify-center shrink-0">
                    <stat.icon className={`h-5 w-5 ${stat.color}`} />
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-foreground">{stat.value}</div>
                    <div className="text-xs text-muted-foreground">{stat.label}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && (
            <Alert className="mb-6 border-destructive/30 bg-destructive/5">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-24">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : projects.length === 0 ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center py-24 gap-6 text-center">
              <div className="h-20 w-20 rounded-2xl bg-primary/10 flex items-center justify-center ring-1 ring-primary/20">
                <BookMarked className="h-10 w-10 text-primary/60" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-foreground mb-2">No Training Courses Yet</h2>
                <p className="text-muted-foreground text-sm max-w-md">
                  Upload an equipment manual and generate a complete professional training course
                  with slides, exercises, and examinations — automatically.
                </p>
              </div>
              <Link href="/training/new">
                <Button size="lg" className="gap-2 font-semibold px-8">
                  <Plus className="h-5 w-5" />
                  Create Your First Course
                </Button>
              </Link>
            </div>
          ) : (
            /* Project grid */
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {projects.map(p => (
                <div key={p.id}
                  className="group rounded-xl border border-border bg-card/60 hover:border-primary/30 hover:bg-card/80 transition-all overflow-hidden">
                  {/* Card header */}
                  <div className="p-4 border-b border-border/50 bg-gradient-to-r from-primary/5 to-transparent">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-lg" title={p.audience}>
                            {AUDIENCE_ICONS[p.audience] || '📚'}
                          </span>
                          <Badge variant="outline"
                            className={`text-[10px] border ${STATUS_COLORS[p.status] || STATUS_COLORS.ready}`}>
                            {p.status.toUpperCase()}
                          </Badge>
                        </div>
                        <h3 className="font-semibold text-sm text-foreground truncate" title={p.course_title}>
                          {p.course_title}
                        </h3>
                        {(p.manufacturer || p.equipment_model) && (
                          <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                            {[p.manufacturer, p.equipment_model].filter(Boolean).join(' · ')}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Card body */}
                  <div className="p-4 space-y-2">
                    <div className="grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <Users className="h-3 w-3 text-primary/50" />
                        <span className="truncate">{p.audience}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Layers className="h-3 w-3 text-primary/50" />
                        <span>{p.slide_count || 0} slides</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <FileText className="h-3 w-3 text-primary/50" />
                        <span className="truncate">{p.manual_filename || 'No manual'}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Calendar className="h-3 w-3 text-primary/50" />
                        <span>{formatDate(p.updated_at)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Card actions */}
                  <div className="px-4 pb-4 flex items-center gap-2">
                    <Link href={`/training/project/${p.id}`} className="flex-1">
                      <Button size="sm" variant="default" className="w-full gap-2 h-8 text-xs font-semibold">
                        <FolderOpen className="h-3.5 w-3.5" />
                        Open Project
                      </Button>
                    </Link>
                    {p.status === 'complete' && (
                      <a href={`${API}/api/training/export/pptx/${p.id}?version=instructor`}
                        download className="shrink-0">
                        <Button size="sm" variant="outline" className="h-8 w-8 p-0">
                          <Download className="h-3.5 w-3.5" />
                        </Button>
                      </a>
                    )}
                    <Button size="sm" variant="ghost"
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive shrink-0"
                      disabled={deletingId === p.id}
                      onClick={() => deleteProject(p.id, p.course_title)}>
                      {deletingId === p.id
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <Trash2 className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                </div>
              ))}

              {/* New course card */}
              <Link href="/training/new">
                <div className="rounded-xl border-2 border-dashed border-border hover:border-primary/40 bg-transparent hover:bg-primary/5 transition-all cursor-pointer flex flex-col items-center justify-center p-8 gap-3 min-h-[220px]">
                  <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center">
                    <Plus className="h-6 w-6 text-primary" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-semibold text-foreground">New Course</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Upload a manual to start</p>
                  </div>
                </div>
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
