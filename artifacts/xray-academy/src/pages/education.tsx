import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpen, ChevronRight, ChevronLeft, Loader2, Plus, Trash2,
  Upload, FileText, CheckCircle2, AlertTriangle, Download, RefreshCw,
  Pencil, Check, X, Star, Zap, BookMarked, Settings, LayoutGrid,
  FilePlus2, Archive, Copy, ListChecks, Brain, ClipboardList, Presentation,
  Wrench, FlaskConical, FileQuestion, Award, FileSpreadsheet, ChevronDown,
  ChevronUp, HelpCircle, Eye, GraduationCap, Target, Filter, BarChart2,
  ShieldCheck,
} from "lucide-react";
const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, '') + '/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface EduProject {
  id: string;
  title: string;
  course_title: string;
  lesson_title: string;
  equipment_manufacturer: string;
  equipment_model: string;
  system_type: string;
  technical_domain: string;
  audience: string;
  level: string;
  depth_mode: string;
  language: string;
  delivery_mode: string;
  course_duration: string;
  lesson_duration: string;
  num_sessions: number;
  instructor_name: string;
  customer: string;
  country_regulatory: string;
  prerequisites: string;
  learning_outcomes: string;
  pass_mark: number;
  num_questions: number;
  include_practical: boolean;
  include_instructor_notes: boolean;
  include_student_notes: boolean;
  include_references: boolean;
  include_citations: boolean;
  include_images: boolean;
  include_tables: boolean;
  include_final_assessment: boolean;
  include_answer_key: boolean;
  selected_output_types: string[];
  status: string;
  quality_score: number | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  references?: EduRef[];
  outputs?: EduOutput[];
}

interface EduRef {
  id: string;
  filename: string;
  file_type: string;
  page_count: number;
  word_count: number;
  image_count: number;
  table_count: number;
  procedure_count: number;
  warning_count: number;
  section_count: number;
  figure_count: number;
  troubleshooting_count: number;
  doc_language: string;
  ocr_required: boolean;
  role: string;
  source_type: string;
  status: string;
  error_msg: string | null;
  created_at: string;
}

interface EduOutput {
  id: string;
  output_type: string;
  title: string;
  content: string;
  citations: Citation[];
  quality_issues: QualityIssue[];
  quality_score: number | null;
  technical_accuracy_score: number | null;
  source_coverage_score: number | null;
  citation_score: number | null;
  lo_alignment_score: number | null;
  approved: boolean;
  has_docx: boolean;
  has_pptx: boolean;
  created_at: string;
  updated_at: string;
}

interface Citation {
  source_filename: string;
  page: string;
  section: string;
  confidence: number;
}

interface VerificationFlag {
  paragraph_index: number;
  concern: string;
  severity: "error" | "warning";
  paragraph_preview: string;
}

interface VerificationResult {
  flagged: VerificationFlag[];
  verified_citation_score: number | null;
  verified_technical_accuracy_score: number | null;
  quality_score: number | null;
  summary: string;
  paragraph_count: number;
}

interface QualityIssue {
  type: string;
  severity: string;
  message: string;
  // Populated for verify_flag issues persisted from the backend verifier
  paragraph_index?: number;
  paragraph_preview?: string;
}

interface RefSummary {
  total_files: number;
  total_pages: number;
  total_words: number;
  total_sections: number;
  total_figures: number;
  total_tables: number;
  total_procedures: number;
  total_warnings: number;
  total_troubleshooting: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CONTENT_TYPE_CATEGORIES = [
  {
    label: "Planning & Structure",
    icon: LayoutGrid,
    color: "text-blue-400",
    types: [
      { id: "course_outline",  label: "Course Outline",  icon: BookOpen },
      { id: "curriculum_map",  label: "Curriculum Map",  icon: Target },
      { id: "lesson_plan",     label: "Lesson Plan",     icon: ListChecks },
      { id: "session_plan",    label: "Session Plan",    icon: ClipboardList },
    ],
  },
  {
    label: "Delivery Materials",
    icon: Presentation,
    color: "text-purple-400",
    types: [
      { id: "instructor_guide",  label: "Instructor Guide",  icon: BookMarked },
      { id: "student_handbook",  label: "Student Handbook",  icon: BookOpen },
      { id: "student_notes",     label: "Student Notes",     icon: FileText },
      { id: "pptx_presentation", label: "PowerPoint Slides", icon: Presentation },
    ],
  },
  {
    label: "Activities & Exercises",
    icon: FlaskConical,
    color: "text-emerald-400",
    types: [
      { id: "practical_exercise",    label: "Practical Exercise",    icon: Wrench },
      { id: "workshop_activity",     label: "Workshop Activity",     icon: Brain },
      { id: "demonstration_guide",   label: "Demonstration Guide",   icon: Eye },
      { id: "lab_activity",          label: "Lab Activity",          icon: FlaskConical },
      { id: "scenario_exercise",     label: "Scenario Exercise",     icon: Zap },
      { id: "case_study",            label: "Case Study",            icon: FileText },
    ],
  },
  {
    label: "Assessment",
    icon: FileQuestion,
    color: "text-amber-400",
    types: [
      { id: "knowledge_check",       label: "Knowledge Check",       icon: CheckCircle2 },
      { id: "quiz",                  label: "Quiz",                  icon: FileQuestion },
      { id: "formal_exam",           label: "Formal Examination",    icon: GraduationCap },
      { id: "practical_assessment",  label: "Practical Assessment",  icon: ListChecks },
      { id: "observation_checklist", label: "Observation Checklist", icon: ClipboardList },
      { id: "answer_key",            label: "Answer Key",            icon: Check },
      { id: "marking_scheme",        label: "Marking Scheme",        icon: Star },
      { id: "troubleshooting_exercise", label: "Troubleshooting Exercise", icon: Wrench },
    ],
  },
  {
    label: "Reference Materials",
    icon: FileText,
    color: "text-cyan-400",
    types: [
      { id: "pm_checklist",    label: "PM Checklist",        icon: ClipboardList },
      { id: "daily_inspection",label: "Daily Inspection",    icon: ListChecks },
      { id: "weekly_inspection",label: "Weekly Inspection",  icon: ListChecks },
      { id: "job_aid",         label: "Job Aid",             icon: FileText },
      { id: "quick_ref_guide", label: "Quick Reference",     icon: BookOpen },
      { id: "glossary",        label: "Glossary",            icon: BookMarked },
      { id: "faq",             label: "FAQ",                 icon: HelpCircle },
    ],
  },
  {
    label: "Administration",
    icon: FileSpreadsheet,
    color: "text-rose-400",
    types: [
      { id: "evaluation_form",  label: "Evaluation Form",   icon: Star },
      { id: "attendance_sheet", label: "Attendance Sheet",  icon: ClipboardList },
      { id: "certificate",      label: "Certificate",       icon: Award },
      { id: "complete_package", label: "Complete Package",  icon: Archive },
    ],
  },
];

const ALL_OUTPUT_TYPES = CONTENT_TYPE_CATEGORIES.flatMap(c => c.types);

const AUDIENCE_OPTIONS = [
  "operator", "maintenance technician", "field service engineer",
  "quality inspector", "safety officer", "supervisor/team leader",
  "trainer/instructor", "management", "mixed audience", "apprentice",
];
const LEVEL_OPTIONS = ["awareness", "basic", "intermediate", "advanced", "expert", "competency"];
const DELIVERY_OPTIONS = ["classroom", "online / e-learning", "blended", "on-the-job", "workshop", "self-paced"];
const LANGUAGE_OPTIONS = ["english", "arabic", "french", "spanish", "german", "portuguese", "other"];

const DEPTH_MODE_OPTIONS: { value: string; label: string; description: string; slides: string }[] = [
  { value: "overview",          label: "Overview",                    description: "Broad strokes — key topics only",                     slides: "30–40 slides" },
  { value: "basic",             label: "Basic",                       description: "Component intro, no labs or schematics",              slides: "50–70 slides" },
  { value: "standard",          label: "Standard",                    description: "Full subsystems, block diagrams, labs",               slides: "70–100 slides" },
  { value: "advanced",          label: "Advanced",                    description: "Engineering depth, fault analysis, all diagrams",     slides: "100–130 slides" },
  { value: "master_instructor", label: "Master Instructor",           description: "Every failure mode, test point, instructor guide",    slides: "130–180 slides" },
  { value: "certification",     label: "Field Service Certification", description: "Maximum depth — every procedure, lab and assessment", slides: "150–200+ slides" },
];

// ── Utility ───────────────────────────────────────────────────────────────────

function scoreColor(s: number | null) {
  if (s === null) return "text-muted-foreground";
  if (s >= 80) return "text-emerald-400";
  if (s >= 60) return "text-amber-400";
  return "text-rose-400";
}

function fmtType(t: string) {
  return ALL_OUTPUT_TYPES.find(x => x.id === t)?.label ?? t.replace(/_/g, " ");
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ScorePill({ score }: { score: number | null }) {
  if (score === null) return null;
  const c = score >= 80 ? "bg-emerald-900/50 text-emerald-300" :
            score >= 60 ? "bg-amber-900/50 text-amber-300" :
                          "bg-rose-900/50 text-rose-300";
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${c}`}>{score}/100</span>
  );
}

function ProgressBar({ value, className = "" }: { value: number; className?: string }) {
  const c = value >= 80 ? "bg-emerald-500" : value >= 60 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className={`h-1.5 w-full bg-white/10 rounded-full overflow-hidden ${className}`}>
      <div className={`h-full ${c} transition-all duration-500`} style={{ width: `${Math.min(100, value)}%` }} />
    </div>
  );
}

function RefBadge({ role }: { role: string }) {
  const map: Record<string, string> = {
    primary: "bg-blue-900/50 text-blue-300",
    supporting: "bg-purple-900/50 text-purple-300",
    style: "bg-pink-900/50 text-pink-300",
    terminology: "bg-teal-900/50 text-teal-300",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[role] ?? "bg-white/10 text-white/60"}`}>
      {role}
    </span>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function EducationPage() {
  const [projects, setProjects]     = useState<EduProject[]>([]);
  const [activeProject, setActiveProject] = useState<EduProject | null>(null);
  const [refs, setRefs]             = useState<EduRef[]>([]);
  const [refSummary, setRefSummary] = useState<RefSummary | null>(null);
  const [outputs, setOutputs]       = useState<EduOutput[]>([]);
  const [step, setStep]             = useState(1);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [creatingProject, setCreatingProject] = useState(false);

  // Step 1 – refs
  const [uploadingRef, setUploadingRef] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step 3 – output types
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());

  // Step 4 – parameters (pulled from project, editable locally)
  const [params, setParams] = useState<Partial<EduProject>>({});

  // Step 5 – generation
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState<
    { label: string; type: string; done: boolean; quality?: number; error?: string }[]
  >([]);
  const [genLog, setGenLog] = useState<string[]>([]);
  const streamRef = useRef<AbortController | null>(null);

  // Step 6 – review
  const [activeOutput, setActiveOutput] = useState<EduOutput | null>(null);
  const [editingOutput, setEditingOutput] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [regenOutputId, setRegenOutputId] = useState<string | null>(null);

  // Step 6 – verify
  const [verifyingOutputId, setVerifyingOutputId] = useState<string | null>(null);
  const [verificationResults, setVerificationResults] = useState<
    Record<string, VerificationResult>
  >({});

  // Step 7 – export
  const [exporting, setExporting] = useState<string | null>(null);

  // ── API helpers ─────────────────────────────────────────────────────────────

  const apiGet  = (path: string) => fetch(`${API_BASE}${path}`, { credentials: "include" });
  const apiPost = (path: string, body: unknown) =>
    fetch(`${API_BASE}${path}`, { method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const apiPatch = (path: string, body: unknown) =>
    fetch(`${API_BASE}${path}`, { method: "PATCH", credentials: "include",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const apiDel  = (path: string) =>
    fetch(`${API_BASE}${path}`, { method: "DELETE", credentials: "include" });

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true);
    try {
      const r = await apiGet("/edu/projects");
      if (r.ok) setProjects((await r.json()).projects ?? []);
    } finally { setLoadingProjects(false); }
  }, []);

  const loadProject = useCallback(async (id: string) => {
    const r = await apiGet(`/edu/projects/${id}`);
    if (!r.ok) return;
    const p: EduProject = await r.json();
    setActiveProject(p);
    setRefs(p.references ?? []);
    setOutputs(p.outputs ?? []);
    setSelectedTypes(new Set(p.selected_output_types ?? []));
    setParams(p);
    if (p.outputs?.length) setStep(6);
    else if (p.references?.length) setStep(2);
    else setStep(1);
  }, []);

  const loadRefs = useCallback(async (id: string) => {
    const r = await apiGet(`/edu/projects/${id}/references`);
    if (r.ok) {
      const data = await r.json();
      setRefs(data.references ?? []);
      setRefSummary(data.summary ?? null);
    }
  }, []);

  const loadOutputs = useCallback(async (id: string) => {
    const r = await apiGet(`/edu/projects/${id}/outputs`);
    if (!r.ok) return;
    const data = await r.json();
    const outs: EduOutput[] = data.outputs ?? [];
    setOutputs(outs);

    // Rehydrate verification results from quality_issues persisted in the DB.
    // This ensures paragraph highlights survive page refresh and re-entry.
    setVerificationResults(prev => {
      const rehydrated: Record<string, VerificationResult> = {};
      for (const out of outs) {
        const flags = (out.quality_issues || []).filter(
          (i: QualityIssue) => i.type === "verify_flag"
        );
        if (flags.length > 0) {
          rehydrated[out.id] = {
            flagged: flags.map((f: QualityIssue) => ({
              paragraph_index:   f.paragraph_index ?? 0,
              concern:           f.message,
              severity:          (f.severity as "error" | "warning"),
              paragraph_preview: f.paragraph_preview ?? "",
            })),
            verified_citation_score:           null,
            verified_technical_accuracy_score: null,
            quality_score:                     null,
            summary:                           "",
            paragraph_count:                   flags.length,
          };
        }
      }
      // Manual re-verify results take precedence over rehydrated ones
      return { ...rehydrated, ...prev };
    });
  }, []);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  // ── Project actions ─────────────────────────────────────────────────────────

  const createProject = async () => {
    setCreatingProject(true);
    try {
      const r = await apiPost("/edu/projects", { title: "New Project" });
      if (r.ok) {
        const p = await r.json();
        await loadProjects();
        await loadProject(p.id);
        setStep(1);
      }
    } finally { setCreatingProject(false); }
  };

  const deleteProject = async (id: string) => {
    if (!confirm("Delete this project and all its content?")) return;
    await apiDel(`/edu/projects/${id}`);
    if (activeProject?.id === id) { setActiveProject(null); setStep(1); }
    loadProjects();
  };

  const duplicateProject = async (id: string) => {
    const r = await fetch(`${API_BASE}/edu/projects/${id}/duplicate`, {
      method: "POST", credentials: "include"
    });
    if (r.ok) loadProjects();
  };

  const saveParams = async () => {
    if (!activeProject) return;
    const update = { ...params, selected_output_types: Array.from(selectedTypes) };
    const r = await apiPatch(`/edu/projects/${activeProject.id}`, update);
    if (r.ok) { const p = await r.json(); setActiveProject(p); }
  };

  // ── Reference upload ────────────────────────────────────────────────────────

  const uploadRef = async (file: File, role = "primary") => {
    if (!activeProject) return;
    setUploadingRef(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("role", role);
      const r = await fetch(`${API_BASE}/edu/projects/${activeProject.id}/references`, {
        method: "POST", credentials: "include", body: fd,
      });
      // Server returns immediately with status="processing"; polling takes over
      if (r.ok) loadRefs(activeProject.id);
    } finally { setUploadingRef(false); }
  };

  const deleteRef = async (refId: string) => {
    if (!activeProject) return;
    await apiDel(`/edu/projects/${activeProject.id}/references/${refId}`);
    loadRefs(activeProject.id);
  };

  const updateRefRole = async (refId: string, role: string) => {
    if (!activeProject) return;
    await apiPatch(`/edu/projects/${activeProject.id}/references/${refId}`, { role });
    loadRefs(activeProject.id);
  };

  const retryRef = async (refId: string) => {
    if (!activeProject) return;
    await fetch(`${API_BASE}/edu/projects/${activeProject.id}/references/${refId}/retry`, {
      method: "POST", credentials: "include",
    });
    loadRefs(activeProject.id);
  };

  // ── Poll while any reference is still processing ─────────────────────────

  useEffect(() => {
    if (!activeProject) return;
    const hasProcessing = refs.some(r => r.status === "processing");
    if (!hasProcessing) return;
    const id = setInterval(() => loadRefs(activeProject.id), 2000);
    return () => clearInterval(id);
  }, [activeProject, refs, loadRefs]);

  // ── Generation ──────────────────────────────────────────────────────────────

  const runGeneration = async (regen = false) => {
    if (!activeProject) return;
    // Save params first
    await saveParams();
    setGenerating(true);
    setGenProgress([]);
    setGenLog([]);

    const types = Array.from(selectedTypes);
    const initProgress = types.map(t => ({
      type: t, label: fmtType(t), done: false, quality: undefined, error: undefined,
    }));
    setGenProgress(initProgress);

    const ctrl = new AbortController();
    streamRef.current = ctrl;

    try {
      const r = await fetch(`${API_BASE}/edu/projects/${activeProject.id}/generate`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_types: types, regenerate: regen }),
        signal: ctrl.signal,
      });
      if (!r.ok) throw new Error("Generation failed");

      const reader = r.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "output_start") {
              setGenLog(prev => [...prev, `⚙ Generating: ${evt.label}...`]);
            } else if (evt.type === "output_done") {
              setGenProgress(prev => prev.map(p =>
                p.type === evt.output_type
                  ? { ...p, done: true, quality: evt.quality_score }
                  : p
              ));
              setGenLog(prev => [...prev, `✓ ${fmtType(evt.output_type)} — quality: ${evt.quality_score}/100`]);
            } else if (evt.type === "output_verifying") {
              setGenLog(prev => [...prev, `🔍 Verifying: ${fmtType(evt.output_type)}...`]);
            } else if (evt.type === "output_verified") {
              if (evt.output_id && Array.isArray(evt.flagged) && evt.flag_count >= 0) {
                setVerificationResults(prev => ({
                  ...prev,
                  [evt.output_id]: {
                    flagged:                           evt.flagged,
                    verified_citation_score:           null,
                    verified_technical_accuracy_score: null,
                    quality_score:                     evt.quality_score ?? null,
                    summary:                           evt.summary ?? "",
                    paragraph_count:                   evt.flagged.length,
                  },
                }));
                const fc = evt.flag_count as number;
                setGenLog(prev => [
                  ...prev,
                  fc === 0
                    ? `✓ ${fmtType(evt.output_type)} — verification passed`
                    : `⚠ ${fmtType(evt.output_type)} — ${fc} paragraph${fc !== 1 ? "s" : ""} flagged`,
                ]);
              } else if (evt.error) {
                setGenLog(prev => [...prev, `ℹ ${fmtType(evt.output_type)} — verification unavailable`]);
              }
            } else if (evt.type === "output_error") {
              setGenProgress(prev => prev.map(p =>
                p.type === evt.output_type ? { ...p, done: true, error: evt.error } : p
              ));
            } else if (evt.type === "done") {
              setGenLog(prev => [...prev, "✓ All outputs generated and verified."]);
              await loadOutputs(activeProject.id);
              setStep(6);
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        setGenLog(prev => [...prev, `✗ Error: ${(err as Error).message}`]);
      }
    } finally {
      setGenerating(false);
      streamRef.current = null;
      await loadProjects();
    }
  };

  // ── Output editing ──────────────────────────────────────────────────────────

  const startEdit = (out: EduOutput) => {
    setEditingOutput(true);
    setEditContent(out.content);
    setActiveOutput(out);
  };

  const saveEdit = async () => {
    if (!activeProject || !activeOutput) return;
    const r = await apiPatch(
      `/edu/projects/${activeProject.id}/outputs/${activeOutput.id}`,
      { content: editContent }
    );
    if (r.ok) {
      const updated = await r.json();
      setOutputs(prev => prev.map(o => o.id === updated.id ? updated : o));
      setActiveOutput(updated);
    }
    setEditingOutput(false);
  };

  const approveOutput = async (out: EduOutput) => {
    if (!activeProject) return;
    const r = await apiPatch(
      `/edu/projects/${activeProject.id}/outputs/${out.id}`,
      { approved: !out.approved }
    );
    if (r.ok) {
      const updated = await r.json();
      setOutputs(prev => prev.map(o => o.id === updated.id ? updated : o));
      if (activeOutput?.id === out.id) setActiveOutput(updated);
    }
  };

  const verifyOutput = async (out: EduOutput) => {
    if (!activeProject) return;
    setVerifyingOutputId(out.id);
    try {
      const r = await apiPost(
        `/edu/projects/${activeProject.id}/outputs/${out.id}/verify`,
        {}
      );
      if (!r.ok) return;
      const result: VerificationResult = await r.json();
      setVerificationResults(prev => ({ ...prev, [out.id]: result }));
      // Refresh outputs so quality scores update in the list
      await loadOutputs(activeProject.id);
      // Update activeOutput with refreshed data
      const refreshed = (await (await apiGet(`/edu/projects/${activeProject.id}/outputs/${out.id}`)).json()) as EduOutput;
      setActiveOutput(refreshed);
    } finally {
      setVerifyingOutputId(null);
    }
  };

  const regenerateOutput = async (out: EduOutput) => {
    if (!activeProject) return;
    setRegenOutputId(out.id);
    try {
      const r = await fetch(
        `${API_BASE}/edu/projects/${activeProject.id}/outputs/${out.id}/regenerate`,
        { method: "POST", credentials: "include" }
      );
      if (!r.ok) return;
      const reader = r.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "chunk") {
              fullContent += evt.chunk;
            } else if (evt.type === "done") {
              await loadOutputs(activeProject.id);
              const refreshed = outputs.find(o => o.id === out.id);
              if (refreshed) setActiveOutput(refreshed);
            } else if (evt.type === "output_verified") {
              // Clear stale verification flags from a previous run of this output
              if (evt.output_id && Array.isArray(evt.flagged) && evt.flag_count >= 0) {
                setVerificationResults(prev => ({
                  ...prev,
                  [evt.output_id]: {
                    flagged:                           evt.flagged,
                    verified_citation_score:           null,
                    verified_technical_accuracy_score: null,
                    quality_score:                     evt.quality_score ?? null,
                    summary:                           evt.summary ?? "",
                    paragraph_count:                   evt.flagged.length,
                  },
                }));
              } else if (evt.output_id && evt.error) {
                // Verification failed — remove stale flags so UI doesn't show wrong data
                setVerificationResults(prev => {
                  const next = { ...prev };
                  delete next[evt.output_id];
                  return next;
                });
              }
            }
          } catch { /* skip */ }
        }
      }
    } finally { setRegenOutputId(null); }
  };

  // ── Export ──────────────────────────────────────────────────────────────────

  const exportProject = async (fmt: string) => {
    if (!activeProject) return;
    setExporting(fmt);
    try {
      const r = await fetch(`${API_BASE}/edu/projects/${activeProject.id}/export/${fmt}`, {
        credentials: "include"
      });
      if (!r.ok) return;
      const blob = await r.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `${activeProject.title}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } finally { setExporting(null); }
  };

  // ── Steps ───────────────────────────────────────────────────────────────────

  const STEPS = [
    { n: 1, label: "References" },
    { n: 2, label: "Analysis" },
    { n: 3, label: "Content" },
    { n: 4, label: "Parameters" },
    { n: 5, label: "Generate" },
    { n: 6, label: "Review" },
    { n: 7, label: "Export" },
  ];

  const canProceed = (s: number) => {
    if (!activeProject) return false;
    if (s === 1) return refs.some(r => r.status === "done");
    if (s === 3) return selectedTypes.size > 0;
    if (s === 4) return !!params.course_title;
    if (s === 5) return outputs.length > 0;
    if (s === 6) return outputs.length > 0;
    return true;
  };

  const gotoStep = async (n: number) => {
    if (n === 4 || n === 5) await saveParams();
    setStep(n);
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? "w-72" : "w-0"} transition-all duration-200 border-r border-white/10
          flex flex-col bg-background overflow-hidden flex-shrink-0`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <span className="font-semibold text-sm">Projects</span>
          <button
            onClick={createProject}
            disabled={creatingProject}
            className="flex items-center gap-1 text-xs bg-primary text-primary-foreground
              px-2 py-1 rounded hover:bg-primary/90 disabled:opacity-50"
          >
            {creatingProject ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
            New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingProjects ? (
            <div className="flex items-center justify-center h-20">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : projects.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p>No projects yet</p>
              <button onClick={createProject} className="mt-2 text-primary text-xs hover:underline">
                Create your first project →
              </button>
            </div>
          ) : (
            projects.map(p => (
              <button
                key={p.id}
                onClick={() => loadProject(p.id)}
                className={`w-full text-left px-4 py-3 hover:bg-white/5 transition-colors border-b border-white/5
                  ${activeProject?.id === p.id ? "bg-white/10 border-l-2 border-l-primary" : ""}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{p.title}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {p.course_title || p.equipment_model || "Draft"}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium
                        ${p.status === "complete" ? "bg-emerald-900/50 text-emerald-300" :
                          p.status === "generating" ? "bg-amber-900/50 text-amber-300" :
                          "bg-white/10 text-white/50"}`}>
                        {p.status}
                      </span>
                      {p.quality_score !== null && (
                        <ScorePill score={p.quality_score} />
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 flex-shrink-0"
                    onClick={e => e.stopPropagation()}>
                    <button onClick={() => duplicateProject(p.id)}
                      className="p-1 hover:bg-white/10 rounded text-muted-foreground hover:text-foreground"
                      title="Duplicate">
                      <Copy className="w-3 h-3" />
                    </button>
                    <button onClick={() => deleteProject(p.id)}
                      className="p-1 hover:bg-white/10 rounded text-muted-foreground hover:text-rose-400"
                      title="Delete">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="flex items-center gap-3 px-4 py-3 border-b border-white/10 flex-shrink-0">
          <button onClick={() => setSidebarOpen(o => !o)}
            className="p-1.5 hover:bg-white/10 rounded text-muted-foreground">
            <LayoutGrid className="w-4 h-4" />
          </button>
          <div className="min-w-0">
            {activeProject ? (
              <>
                <h1 className="text-sm font-semibold truncate">{activeProject.title}</h1>
                {activeProject.course_title && (
                  <p className="text-xs text-muted-foreground truncate">{activeProject.course_title}</p>
                )}
              </>
            ) : (
              <h1 className="text-sm font-semibold">Reference-Based Education Studio</h1>
            )}
          </div>
          {activeProject && (
            <div className="ml-auto flex items-center gap-2">
              {activeProject.quality_score !== null && (
                <ScorePill score={activeProject.quality_score} />
              )}
              <button
                onClick={() => { setActiveProject(null); setStep(1); }}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                ← Projects
              </button>
            </div>
          )}
        </header>

        {!activeProject ? (
          /* Landing */
          <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
            <div className="text-center max-w-lg">
              <GraduationCap className="w-16 h-16 mx-auto mb-4 text-primary/60" />
              <h2 className="text-2xl font-bold mb-2">Reference-Based Education Studio</h2>
              <p className="text-muted-foreground text-sm leading-relaxed">
                Upload your technical manuals, service documents, and specifications.
                The AI generates training materials grounded exclusively in your references —
                no invented facts, every claim cited.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-4 text-center text-sm">
              {[
                { icon: Upload, label: "Upload References", desc: "PDF, DOCX, PPTX, TXT" },
                { icon: Brain, label: "AI Generation", desc: "33 content types" },
                { icon: CheckCircle2, label: "Quality Assured", desc: "Citation scoring" },
              ].map(({ icon: Icon, label, desc }) => (
                <div key={label} className="p-4 rounded-lg bg-white/5 border border-white/10">
                  <Icon className="w-6 h-6 mx-auto mb-2 text-primary/70" />
                  <div className="font-medium">{label}</div>
                  <div className="text-xs text-muted-foreground">{desc}</div>
                </div>
              ))}
            </div>
            <button
              onClick={createProject}
              disabled={creatingProject}
              className="flex items-center gap-2 bg-primary text-primary-foreground
                px-6 py-3 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {creatingProject ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Create New Project
            </button>
          </div>
        ) : (
          <>
            {/* Step bar */}
            <div className="flex items-center gap-0 px-4 py-2 border-b border-white/10 bg-background/50 flex-shrink-0 overflow-x-auto">
              {STEPS.map((s, i) => (
                <React.Fragment key={s.n}>
                  <button
                    onClick={() => activeProject && gotoStep(s.n)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors flex-shrink-0
                      ${step === s.n
                        ? "bg-primary/20 text-primary"
                        : step > s.n
                          ? "text-emerald-400 hover:bg-white/5"
                          : "text-muted-foreground hover:bg-white/5"}`}
                  >
                    <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0
                      ${step === s.n ? "bg-primary text-primary-foreground" :
                        step > s.n ? "bg-emerald-600 text-white" : "bg-white/10 text-white/40"}`}>
                      {step > s.n ? <Check className="w-3 h-3" /> : s.n}
                    </span>
                    {s.label}
                  </button>
                  {i < STEPS.length - 1 && <ChevronRight className="w-3 h-3 text-white/20 flex-shrink-0" />}
                </React.Fragment>
              ))}
            </div>

            {/* Step content */}
            <div className="flex-1 overflow-y-auto">
              {step === 1 && (
                <StepReferences
                  projectId={activeProject.id}
                  refs={refs}
                  summary={refSummary}
                  uploading={uploadingRef}
                  fileInputRef={fileInputRef}
                  onUpload={uploadFile => uploadRef(uploadFile)}
                  onDelete={deleteRef}
                  onRoleChange={updateRefRole}
                  onRetry={retryRef}
                />
              )}
              {step === 2 && (
                <StepAnalysis refs={refs} summary={refSummary} />
              )}
              {step === 3 && (
                <StepContentTypes
                  selected={selectedTypes}
                  onToggle={id => {
                    setSelectedTypes(prev => {
                      const s = new Set(prev);
                      if (s.has(id)) s.delete(id); else s.add(id);
                      return s;
                    });
                  }}
                  onSelectAll={category => {
                    const ids = category.types.map(t => t.id);
                    setSelectedTypes(prev => {
                      const s = new Set(prev);
                      const allSelected = ids.every(id => s.has(id));
                      if (allSelected) ids.forEach(id => s.delete(id));
                      else ids.forEach(id => s.add(id));
                      return s;
                    });
                  }}
                />
              )}
              {step === 4 && (
                <StepParameters params={params} onChange={setParams} />
              )}
              {step === 5 && (
                <StepGenerate
                  generating={generating}
                  progress={genProgress}
                  log={genLog}
                  selectedCount={selectedTypes.size}
                  onGenerate={() => runGeneration(false)}
                  onRegenerate={() => runGeneration(true)}
                  onCancel={() => { streamRef.current?.abort(); setGenerating(false); }}
                  hasOutputs={outputs.length > 0}
                />
              )}
              {step === 6 && (
                <StepReview
                  outputs={outputs}
                  activeOutput={activeOutput}
                  setActiveOutput={setActiveOutput}
                  editingOutput={editingOutput}
                  editContent={editContent}
                  setEditContent={setEditContent}
                  regenOutputId={regenOutputId}
                  verifyingOutputId={verifyingOutputId}
                  verificationResults={verificationResults}
                  onStartEdit={startEdit}
                  onSaveEdit={saveEdit}
                  onCancelEdit={() => setEditingOutput(false)}
                  onApprove={approveOutput}
                  onRegenerate={regenerateOutput}
                  onVerify={verifyOutput}
                />
              )}
              {step === 7 && (
                <StepExport
                  project={activeProject}
                  outputs={outputs}
                  exporting={exporting}
                  onExport={exportProject}
                />
              )}
            </div>

            {/* Navigation footer */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-white/10 flex-shrink-0 bg-background/50">
              <button
                onClick={() => gotoStep(Math.max(1, step - 1))}
                disabled={step === 1}
                className="flex items-center gap-1 text-sm px-3 py-1.5 rounded border border-white/10
                  hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" /> Back
              </button>
              <span className="text-xs text-muted-foreground">Step {step} of {STEPS.length}</span>
              <button
                onClick={() => gotoStep(Math.min(7, step + 1))}
                disabled={step === 7 || !canProceed(step)}
                className="flex items-center gap-1 text-sm px-3 py-1.5 rounded bg-primary text-primary-foreground
                  hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {step === 5 ? "Review" : "Next"} <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Step 1: References ────────────────────────────────────────────────────────

function StepReferences({
  projectId, refs, summary, uploading, fileInputRef, onUpload, onDelete, onRoleChange, onRetry,
}: {
  projectId: string;
  refs: EduRef[];
  summary: RefSummary | null;
  uploading: boolean;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onUpload: (file: File, role?: string) => void;
  onDelete: (id: string) => void;
  onRoleChange: (id: string, role: string) => void;
  onRetry: (id: string) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [expandedRef, setExpandedRef] = useState<string | null>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    files.forEach(f => onUpload(f));
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-1">Upload Reference Documents</h2>
        <p className="text-sm text-muted-foreground">
          Upload your technical manuals, service guides, and specifications. All generated
          content will be grounded exclusively in these documents.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer
          ${dragOver ? "border-primary/60 bg-primary/5" : "border-white/20 hover:border-white/40"}`}
        onClick={() => fileInputRef.current?.click()}
      >
        {uploading ? (
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="w-8 h-8 animate-spin text-primary/60" />
            <p className="text-sm text-muted-foreground">Processing document…</p>
          </div>
        ) : (
          <>
            <Upload className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
            <p className="text-sm font-medium">Drop files here or click to browse</p>
            <p className="text-xs text-muted-foreground mt-1">PDF, DOCX, PPTX, TXT — up to 100 MB each</p>
          </>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.pptx,.ppt,.txt,.md"
          className="hidden"
          onChange={e => {
            Array.from(e.target.files ?? []).forEach(f => onUpload(f));
            e.target.value = "";
          }}
        />
      </div>

      {/* Summary row */}
      {summary && summary.total_files > 0 && (
        <div className="grid grid-cols-4 sm:grid-cols-8 gap-3">
          {[
            { label: "Files", v: summary.total_files },
            { label: "Pages", v: summary.total_pages },
            { label: "Words", v: summary.total_words.toLocaleString() },
            { label: "Sections", v: summary.total_sections },
            { label: "Procedures", v: summary.total_procedures },
            { label: "Warnings", v: summary.total_warnings },
            { label: "Figures", v: summary.total_figures },
            { label: "Tables", v: summary.total_tables },
          ].map(({ label, v }) => (
            <div key={label} className="bg-white/5 rounded-lg p-2 text-center">
              <div className="text-base font-bold text-primary">{v}</div>
              <div className="text-xs text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Ref list */}
      {refs.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Uploaded References ({refs.length})
          </h3>
          {refs.map(ref => (
            <div key={ref.id} className="bg-white/5 border border-white/10 rounded-lg overflow-hidden">
              <div className="flex items-center gap-3 p-3">
                <div className="flex-shrink-0">
                  {ref.status === "processing" ? (
                    <Loader2 className="w-5 h-5 animate-spin text-amber-400" />
                  ) : ref.status === "error" ? (
                    <AlertTriangle className="w-5 h-5 text-rose-400" />
                  ) : (
                    <FileText className="w-5 h-5 text-primary/70" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium truncate">{ref.filename}</span>
                    <RefBadge role={ref.role} />
                    {ref.ocr_required && (
                      <span className="text-xs text-amber-400">⚠ OCR required</span>
                    )}
                  </div>
                  {ref.status === "done" && (
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                      <span>{ref.page_count} pages</span>
                      <span>{ref.word_count.toLocaleString()} words</span>
                      <span>{ref.section_count} sections</span>
                      {ref.procedure_count > 0 && <span>{ref.procedure_count} procedures</span>}
                      {ref.warning_count > 0 && <span className="text-amber-400">{ref.warning_count} warnings</span>}
                    </div>
                  )}
                  {ref.status === "error" && (
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-rose-400">{ref.error_msg || "Processing failed"}</span>
                      <button
                        onClick={e => { e.stopPropagation(); onRetry(ref.id); }}
                        className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300
                          border border-amber-400/40 rounded px-1.5 py-0.5"
                      >
                        <RefreshCw className="w-3 h-3" /> Retry
                      </button>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <select
                    value={ref.role}
                    onChange={e => onRoleChange(ref.id, e.target.value)}
                    className="text-xs bg-transparent border border-white/20 rounded px-1 py-0.5
                      text-muted-foreground hover:border-white/40"
                  >
                    <option value="primary">Primary</option>
                    <option value="supporting">Supporting</option>
                    <option value="style">Style only</option>
                    <option value="terminology">Terminology</option>
                  </select>
                  <button
                    onClick={() => setExpandedRef(expandedRef === ref.id ? null : ref.id)}
                    className="p-1 hover:bg-white/10 rounded text-muted-foreground"
                  >
                    {expandedRef === ref.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                  <button onClick={() => onDelete(ref.id)}
                    className="p-1 hover:bg-white/10 rounded text-muted-foreground hover:text-rose-400">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {expandedRef === ref.id && ref.status === "done" && (
                <div className="border-t border-white/10 p-3 grid grid-cols-4 gap-2 text-xs">
                  {[
                    { label: "Images", v: ref.image_count },
                    { label: "Tables", v: ref.table_count },
                    { label: "Figures", v: ref.figure_count },
                    { label: "Troubleshooting", v: ref.troubleshooting_count },
                  ].map(({ label, v }) => (
                    <div key={label} className="text-center">
                      <div className="font-bold text-foreground">{v}</div>
                      <div className="text-muted-foreground">{label}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {refs.length === 0 && !uploading && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          Upload at least one reference document to proceed.
        </div>
      )}
    </div>
  );
}

// ── Step 2: Analysis ──────────────────────────────────────────────────────────

function StepAnalysis({ refs, summary }: { refs: EduRef[]; summary: RefSummary | null }) {
  const doneRefs = refs.filter(r => r.status === "done");

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-1">Reference Analysis</h2>
        <p className="text-sm text-muted-foreground">
          Review what was extracted from your reference documents.
        </p>
      </div>

      {doneRefs.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No processed references yet. Go back to upload files.</p>
        </div>
      ) : (
        <>
          {summary && (
            <div className="bg-primary/10 border border-primary/30 rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3 text-primary">Combined Reference Coverage</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                {[
                  { label: "Total Pages", v: summary.total_pages, icon: FileText },
                  { label: "Total Words", v: summary.total_words.toLocaleString(), icon: BookOpen },
                  { label: "Procedures Found", v: summary.total_procedures, icon: ListChecks },
                  { label: "Safety Warnings", v: summary.total_warnings, icon: AlertTriangle },
                ].map(({ label, v, icon: Icon }) => (
                  <div key={label}>
                    <Icon className="w-5 h-5 mx-auto mb-1 text-primary/60" />
                    <div className="text-lg font-bold">{v}</div>
                    <div className="text-xs text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {doneRefs.map(ref => (
            <div key={ref.id} className="bg-white/5 border border-white/10 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="font-medium text-sm">{ref.filename}</h4>
                  <div className="flex items-center gap-2 mt-0.5">
                    <RefBadge role={ref.role} />
                    <span className="text-xs text-muted-foreground">{ref.file_type.toUpperCase()}</span>
                  </div>
                </div>
                <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              </div>
              <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 text-center text-xs">
                {[
                  { label: "Pages",       v: ref.page_count },
                  { label: "Words",       v: ref.word_count.toLocaleString() },
                  { label: "Sections",    v: ref.section_count },
                  { label: "Procedures",  v: ref.procedure_count },
                  { label: "Warnings",    v: ref.warning_count, highlight: ref.warning_count > 0 },
                  { label: "Figures",     v: ref.figure_count },
                  { label: "Tables",      v: ref.table_count },
                  { label: "Troubleshoot",v: ref.troubleshooting_count },
                ].map(({ label, v, highlight }) => (
                  <div key={label} className={`rounded p-1 ${highlight ? "bg-amber-900/30" : "bg-white/5"}`}>
                    <div className={`font-bold ${highlight ? "text-amber-300" : "text-foreground"}`}>{v}</div>
                    <div className="text-muted-foreground leading-tight">{label}</div>
                  </div>
                ))}
              </div>
              {ref.ocr_required && (
                <div className="mt-3 flex items-center gap-2 text-xs text-amber-400 bg-amber-900/20 rounded px-3 py-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  This document may be a scanned image. Text extraction may be incomplete.
                  Consider uploading a searchable PDF version.
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── Step 3: Content types ─────────────────────────────────────────────────────

function StepContentTypes({
  selected, onToggle, onSelectAll,
}: {
  selected: Set<string>;
  onToggle: (id: string) => void;
  onSelectAll: (category: (typeof CONTENT_TYPE_CATEGORIES)[0]) => void;
}) {
  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold mb-1">Select Content to Generate</h2>
          <p className="text-sm text-muted-foreground">
            Choose from 33 content types. Each will be generated from your reference documents.
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm flex-shrink-0">
          <span className="text-muted-foreground">Selected:</span>
          <span className="font-bold text-primary">{selected.size}</span>
        </div>
      </div>

      {CONTENT_TYPE_CATEGORIES.map(cat => {
        const allSelected = cat.types.every(t => selected.has(t.id));
        const someSelected = cat.types.some(t => selected.has(t.id));
        return (
          <div key={cat.label} className="bg-white/3 border border-white/10 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 bg-white/5">
              <div className="flex items-center gap-2">
                <cat.icon className={`w-4 h-4 ${cat.color}`} />
                <span className="text-sm font-medium">{cat.label}</span>
                <span className="text-xs text-muted-foreground">
                  ({cat.types.filter(t => selected.has(t.id)).length}/{cat.types.length})
                </span>
              </div>
              <button
                onClick={() => onSelectAll(cat)}
                className={`text-xs px-2 py-1 rounded transition-colors
                  ${allSelected ? "bg-primary/20 text-primary" :
                    someSelected ? "bg-primary/10 text-primary/70" :
                    "bg-white/10 text-muted-foreground hover:bg-white/15"}`}
              >
                {allSelected ? "Deselect all" : "Select all"}
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-3">
              {cat.types.map(type => {
                const active = selected.has(type.id);
                return (
                  <button
                    key={type.id}
                    onClick={() => onToggle(type.id)}
                    className={`flex items-center gap-2 p-2.5 rounded-lg text-left text-xs transition-all border
                      ${active
                        ? "bg-primary/15 border-primary/40 text-foreground"
                        : "bg-white/3 border-white/10 text-muted-foreground hover:bg-white/8 hover:border-white/20"}`}
                  >
                    <type.icon className={`w-3.5 h-3.5 flex-shrink-0 ${active ? cat.color : ""}`} />
                    <span className="leading-tight">{type.label}</span>
                    {active && <Check className="w-3 h-3 flex-shrink-0 ml-auto text-primary" />}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Step 4: Parameters ────────────────────────────────────────────────────────

function StepParameters({
  params, onChange,
}: {
  params: Partial<EduProject>;
  onChange: (p: Partial<EduProject>) => void;
}) {
  const set = (k: keyof EduProject, v: unknown) => onChange({ ...params, [k]: v });

  const field = (label: string, key: keyof EduProject, placeholder?: string) => (
    <div>
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide block mb-1">
        {label}
      </label>
      <input
        value={(params[key] as string) ?? ""}
        onChange={e => set(key, e.target.value)}
        placeholder={placeholder}
        className="w-full bg-white/5 border border-white/20 rounded-md px-3 py-2 text-sm
          focus:border-primary/60 focus:outline-none focus:bg-white/8 transition-colors"
      />
    </div>
  );

  const selectField = (label: string, key: keyof EduProject, options: string[]) => (
    <div>
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide block mb-1">
        {label}
      </label>
      <select
        value={(params[key] as string) ?? ""}
        onChange={e => set(key, e.target.value)}
        className="w-full bg-white/5 border border-white/20 rounded-md px-3 py-2 text-sm
          focus:border-primary/60 focus:outline-none text-foreground"
      >
        <option value="">Select…</option>
        {options.map(o => <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
      </select>
    </div>
  );

  const numField = (label: string, key: keyof EduProject, min = 0, max = 999) => (
    <div>
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide block mb-1">
        {label}
      </label>
      <input
        type="number"
        min={min}
        max={max}
        value={(params[key] as number) ?? 0}
        onChange={e => set(key, parseInt(e.target.value, 10))}
        className="w-full bg-white/5 border border-white/20 rounded-md px-3 py-2 text-sm
          focus:border-primary/60 focus:outline-none"
      />
    </div>
  );

  const toggle = (label: string, key: keyof EduProject) => (
    <label className="flex items-center justify-between gap-3 py-2 cursor-pointer group">
      <span className="text-sm group-hover:text-foreground transition-colors">{label}</span>
      <button
        role="switch"
        aria-checked={!!(params[key])}
        onClick={() => set(key, !params[key])}
        className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0
          ${params[key] ? "bg-primary" : "bg-white/20"}`}
      >
        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform
          ${params[key] ? "translate-x-5" : "translate-x-0.5"}`} />
      </button>
    </label>
  );

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-1">Course Parameters</h2>
        <p className="text-sm text-muted-foreground">
          Configure the course details that guide content generation.
        </p>
      </div>

      {/* Project identity */}
      <Section title="Project Identity" icon={BookOpen}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {field("Project Title", "title", "My Training Project")}
          {field("Course Title", "course_title", "Technical Operations Course")}
          {field("Lesson/Module Title", "lesson_title", "Module 1: System Overview")}
        </div>
      </Section>

      {/* Equipment */}
      <Section title="Equipment / System" icon={Wrench}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {field("Manufacturer", "equipment_manufacturer", "e.g. Smiths Detection")}
          {field("Model / Product", "equipment_model", "e.g. HI-SCAN 10080 XCT")}
          {field("System Type", "system_type", "e.g. X-ray Baggage Scanner")}
          {field("Technical Domain", "technical_domain", "e.g. Security Screening")}
        </div>
      </Section>

      {/* Course Depth Mode */}
      <Section title="Course Depth Mode" icon={Zap}>
        <p className="text-xs text-muted-foreground px-4 pb-3">
          Controls how many slides the AI generates per subsystem module and how deeply it teaches each topic.
          Higher modes produce longer, more detailed courses suitable for senior engineers and certification programmes.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 px-4 pb-4">
          {DEPTH_MODE_OPTIONS.map(opt => {
            const active = (params.depth_mode as string) === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => set("depth_mode", opt.value)}
                className={`text-left rounded-lg border p-3 transition-all ${
                  active
                    ? "border-primary bg-primary/10 shadow-sm shadow-primary/20"
                    : "border-white/10 bg-white/3 hover:border-white/25 hover:bg-white/6"
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className={`text-sm font-semibold ${active ? "text-primary" : "text-foreground"}`}>
                    {opt.label}
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground whitespace-nowrap">
                    {opt.slides}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-snug">{opt.description}</p>
              </button>
            );
          })}
        </div>
      </Section>

      {/* Delivery */}
      <Section title="Audience & Delivery" icon={GraduationCap}>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {selectField("Target Audience", "audience", AUDIENCE_OPTIONS)}
          {selectField("Competency Level", "level", LEVEL_OPTIONS)}
          {selectField("Delivery Mode", "delivery_mode", DELIVERY_OPTIONS)}
          {selectField("Language", "language", LANGUAGE_OPTIONS)}
          {field("Course Duration", "course_duration", "e.g. 5 days")}
          {field("Lesson Duration", "lesson_duration", "e.g. 90 minutes")}
          {numField("Number of Sessions", "num_sessions", 1, 20)}
        </div>
      </Section>

      {/* Administration */}
      <Section title="Administration" icon={ClipboardList}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {field("Instructor Name", "instructor_name")}
          {field("Customer / Client", "customer")}
          {field("Country / Regulatory Context", "country_regulatory", "e.g. UAE, ECAC, TSA")}
        </div>
      </Section>

      {/* Learning outcomes */}
      <Section title="Learning Outcomes & Prerequisites" icon={Target}>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide block mb-1">
              Prerequisites
            </label>
            <textarea
              rows={2}
              value={(params.prerequisites as string) ?? ""}
              onChange={e => set("prerequisites", e.target.value)}
              placeholder="List any knowledge or experience required before attending this course"
              className="w-full bg-white/5 border border-white/20 rounded-md px-3 py-2 text-sm
                focus:border-primary/60 focus:outline-none resize-y"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide block mb-1">
              Learning Outcomes (one per line)
            </label>
            <textarea
              rows={5}
              value={(params.learning_outcomes as string) ?? ""}
              onChange={e => set("learning_outcomes", e.target.value)}
              placeholder={"By the end of this course, participants will be able to:\n- Describe the operating principles of the system\n- Perform daily inspections per the maintenance manual\n- Respond to fault codes correctly"}
              className="w-full bg-white/5 border border-white/20 rounded-md px-3 py-2 text-sm
                focus:border-primary/60 focus:outline-none resize-y"
            />
          </div>
        </div>
      </Section>

      {/* Assessment */}
      <Section title="Assessment Settings" icon={FileQuestion}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {numField("Pass Mark (%)", "pass_mark", 50, 100)}
          {numField("Number of Questions", "num_questions", 5, 100)}
        </div>
      </Section>

      {/* Content toggles */}
      <Section title="Content Inclusions" icon={Filter}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 divide-y divide-white/5">
          {[
            { label: "Include practical exercises",          key: "include_practical" },
            { label: "Include instructor notes",             key: "include_instructor_notes" },
            { label: "Include student notes",                key: "include_student_notes" },
            { label: "Include source references",            key: "include_references" },
            { label: "Include inline citations",             key: "include_citations" },
            { label: "Include image descriptions",           key: "include_images" },
            { label: "Include tables from references",       key: "include_tables" },
            { label: "Include final assessment",             key: "include_final_assessment" },
            { label: "Include answer key",                   key: "include_answer_key" },
          ].map(({ label, key }) => toggle(label, key as keyof EduProject))}
        </div>
      </Section>
    </div>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="bg-white/3 border border-white/10 rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-white/5 border-b border-white/10">
        <Icon className="w-4 h-4 text-primary/70" />
        <h3 className="text-sm font-medium">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

// ── Step 5: Generate ──────────────────────────────────────────────────────────

function StepGenerate({
  generating, progress, log, selectedCount,
  onGenerate, onRegenerate, onCancel, hasOutputs,
}: {
  generating: boolean;
  progress: { label: string; type: string; done: boolean; quality?: number; error?: string }[];
  log: string[];
  selectedCount: number;
  onGenerate: () => void;
  onRegenerate: () => void;
  onCancel: () => void;
  hasOutputs: boolean;
}) {
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  const done  = progress.filter(p => p.done && !p.error).length;
  const error = progress.filter(p => p.error).length;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-1">Generate Training Content</h2>
        <p className="text-sm text-muted-foreground">
          {selectedCount} content type{selectedCount !== 1 ? "s" : ""} selected.
          All content will be grounded in your reference documents.
        </p>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        {!generating ? (
          <>
            <button
              onClick={hasOutputs ? onRegenerate : onGenerate}
              className="flex items-center gap-2 bg-primary text-primary-foreground
                px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-primary/90"
            >
              <Zap className="w-4 h-4" />
              {hasOutputs ? "Regenerate All" : "Generate Content"}
            </button>
            {hasOutputs && (
              <button
                onClick={onGenerate}
                className="flex items-center gap-2 border border-white/20 px-4 py-2.5
                  rounded-lg text-sm hover:bg-white/5"
              >
                <FilePlus2 className="w-4 h-4" />
                Add Missing Outputs
              </button>
            )}
          </>
        ) : (
          <button
            onClick={onCancel}
            className="flex items-center gap-2 border border-rose-500/50 text-rose-400
              px-4 py-2.5 rounded-lg text-sm hover:bg-rose-500/10"
          >
            <X className="w-4 h-4" /> Cancel
          </button>
        )}
        {generating && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            Generating {done + 1} of {progress.length}…
          </div>
        )}
      </div>

      {/* Progress grid */}
      {progress.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {progress.map(p => (
            <div
              key={p.type}
              className={`flex items-center gap-3 p-3 rounded-lg border transition-colors
                ${p.error ? "bg-rose-900/20 border-rose-800/40" :
                  p.done ? "bg-emerald-900/15 border-emerald-800/30" :
                  "bg-white/3 border-white/10"}`}
            >
              <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center">
                {p.error ? <X className="w-4 h-4 text-rose-400" /> :
                 p.done ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> :
                 generating && !p.done ? <Loader2 className="w-4 h-4 animate-spin text-primary/60" /> :
                 <div className="w-3 h-3 rounded-full bg-white/20" />}
              </div>
              <span className={`text-sm flex-1 ${p.done ? "text-foreground" : "text-muted-foreground"}`}>
                {p.label}
              </span>
              {p.done && p.quality !== undefined && <ScorePill score={p.quality} />}
              {p.error && <span className="text-xs text-rose-400">Error</span>}
            </div>
          ))}
        </div>
      )}

      {/* Log */}
      {log.length > 0 && (
        <div
          ref={logRef}
          className="bg-black/40 border border-white/10 rounded-lg p-3 h-40 overflow-y-auto
            font-mono text-xs text-muted-foreground"
        >
          {log.map((line, i) => (
            <div key={i} className={line.startsWith("✓") ? "text-emerald-400" :
              line.startsWith("✗") ? "text-rose-400" : ""}>
              {line}
            </div>
          ))}
        </div>
      )}

      {!generating && done > 0 && (
        <div className="flex items-center gap-3 bg-emerald-900/20 border border-emerald-800/40
          rounded-lg px-4 py-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <div className="text-sm">
            <span className="font-medium text-emerald-300">Generation complete!</span>
            <span className="text-muted-foreground ml-2">{done} outputs ready.</span>
            {error > 0 && <span className="text-rose-400 ml-2">{error} failed.</span>}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Step 6: Review ────────────────────────────────────────────────────────────

function StepReview({
  outputs, activeOutput, setActiveOutput,
  editingOutput, editContent, setEditContent,
  regenOutputId, verifyingOutputId, verificationResults,
  onStartEdit, onSaveEdit, onCancelEdit,
  onApprove, onRegenerate, onVerify,
}: {
  outputs: EduOutput[];
  activeOutput: EduOutput | null;
  setActiveOutput: (o: EduOutput) => void;
  editingOutput: boolean;
  editContent: string;
  setEditContent: (c: string) => void;
  regenOutputId: string | null;
  verifyingOutputId: string | null;
  verificationResults: Record<string, VerificationResult>;
  onStartEdit: (o: EduOutput) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onApprove: (o: EduOutput) => void;
  onRegenerate: (o: EduOutput) => void;
  onVerify: (o: EduOutput) => void;
}) {
  const approved = outputs.filter(o => o.approved).length;

  // Build a map of paragraph_index → flag for the active output
  const activeFlags: Record<number, VerificationFlag> = {};
  if (activeOutput) {
    const vr = verificationResults[activeOutput.id];
    if (vr) {
      for (const f of vr.flagged) {
        activeFlags[f.paragraph_index] = f;
      }
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Output list */}
      <div className="w-72 flex-shrink-0 border-r border-white/10 flex flex-col overflow-hidden">
        <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {approved}/{outputs.length} approved
          </span>
          <BarChart2 className="w-3.5 h-3.5 text-muted-foreground" />
        </div>
        <div className="flex-1 overflow-y-auto">
          {outputs.map(out => {
            const vr = verificationResults[out.id];
            const verifyFlags = vr ? vr.flagged.length : null;
            const isVerifying = verifyingOutputId === out.id;
            return (
              <button
                key={out.id}
                onClick={() => setActiveOutput(out)}
                className={`w-full text-left px-3 py-2.5 hover:bg-white/5 transition-colors border-b border-white/5
                  ${activeOutput?.id === out.id ? "bg-white/10 border-l-2 border-l-primary" : ""}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate">{out.title}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      {out.approved && <CheckCircle2 className="w-3 h-3 text-emerald-400 flex-shrink-0" />}
                      {(regenOutputId === out.id || isVerifying) && (
                        <Loader2 className="w-3 h-3 animate-spin text-primary/60 flex-shrink-0" />
                      )}
                      {out.quality_score !== null && (
                        <ProgressBar value={out.quality_score} className="w-16" />
                      )}
                      {out.quality_score !== null && (
                        <span className={`text-xs font-mono ${scoreColor(out.quality_score)}`}>
                          {out.quality_score}
                        </span>
                      )}
                    </div>
                  </div>
                  {/* Verification badge */}
                  {verifyFlags !== null && (
                    <span className={`flex-shrink-0 text-xs px-1.5 py-0.5 rounded font-medium
                      ${verifyFlags === 0
                        ? "bg-emerald-900/40 text-emerald-400"
                        : "bg-amber-900/40 text-amber-400"}`}
                      title={verifyFlags === 0 ? "Verified — no issues" : `${verifyFlags} flag${verifyFlags !== 1 ? "s" : ""}`}>
                      {verifyFlags === 0 ? "✓" : `⚠${verifyFlags}`}
                    </span>
                  )}
                </div>
                {(out.quality_issues?.length ?? 0) > 0 && (() => {
                  const nonFlagIssues = out.quality_issues.filter(i => i.type !== "verify_flag");
                  return nonFlagIssues.length > 0 ? (
                    <div className="flex items-center gap-1 mt-1">
                      <AlertTriangle className="w-3 h-3 text-amber-400" />
                      <span className="text-xs text-amber-400">
                        {nonFlagIssues.length} issue{nonFlagIssues.length !== 1 ? "s" : ""}
                      </span>
                    </div>
                  ) : null;
                })()}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content panel */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!activeOutput ? (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Eye className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">Select an output to review</p>
            </div>
          </div>
        ) : (
          <>
            {/* Output header */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-white/10 flex-shrink-0">
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold truncate">{activeOutput.title}</h3>
                <div className="flex items-center gap-3 mt-0.5">
                  {activeOutput.quality_score !== null && (
                    <>
                      <ScorePill score={activeOutput.quality_score} />
                      <span className="text-xs text-muted-foreground">
                        {activeOutput.citations?.length ?? 0} citations
                      </span>
                    </>
                  )}
                  {activeOutput.approved && (
                    <span className="text-xs text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Approved
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {editingOutput ? (
                  <>
                    <button onClick={onSaveEdit}
                      className="flex items-center gap-1 text-xs bg-primary/20 text-primary px-2 py-1.5 rounded hover:bg-primary/30">
                      <Check className="w-3 h-3" /> Save
                    </button>
                    <button onClick={onCancelEdit}
                      className="flex items-center gap-1 text-xs border border-white/20 px-2 py-1.5 rounded hover:bg-white/5">
                      <X className="w-3 h-3" /> Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button onClick={() => onStartEdit(activeOutput)}
                      className="flex items-center gap-1 text-xs border border-white/20 px-2 py-1.5 rounded hover:bg-white/5">
                      <Pencil className="w-3 h-3" /> Edit
                    </button>
                    <button
                      onClick={() => onRegenerate(activeOutput)}
                      disabled={regenOutputId === activeOutput.id || verifyingOutputId === activeOutput.id}
                      className="flex items-center gap-1 text-xs border border-white/20 px-2 py-1.5 rounded hover:bg-white/5 disabled:opacity-50">
                      {regenOutputId === activeOutput.id
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : <RefreshCw className="w-3 h-3" />}
                      Regen
                    </button>
                    <button
                      onClick={() => onVerify(activeOutput)}
                      disabled={verifyingOutputId === activeOutput.id || regenOutputId === activeOutput.id}
                      title="Cross-check content against reference documents"
                      className={`flex items-center gap-1 text-xs px-2 py-1.5 rounded disabled:opacity-50
                        ${verificationResults[activeOutput.id]
                          ? "border border-violet-700/50 bg-violet-900/30 text-violet-300 hover:bg-violet-900/50"
                          : "border border-white/20 hover:bg-white/5"}`}>
                      {verifyingOutputId === activeOutput.id
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : <ShieldCheck className="w-3 h-3" />}
                      {verifyingOutputId === activeOutput.id ? "Verifying…" :
                        verificationResults[activeOutput.id] ? "Re-verify" : "Verify"}
                    </button>
                    <button
                      onClick={() => onApprove(activeOutput)}
                      className={`flex items-center gap-1 text-xs px-2 py-1.5 rounded
                        ${activeOutput.approved
                          ? "bg-emerald-900/40 text-emerald-300 border border-emerald-700/40"
                          : "border border-white/20 hover:bg-white/5"}`}>
                      <CheckCircle2 className="w-3 h-3" />
                      {activeOutput.approved ? "Approved" : "Approve"}
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Quality scores */}
            {activeOutput.quality_score !== null && (
              <div className="flex items-center gap-4 px-4 py-2 bg-white/3 border-b border-white/10 flex-shrink-0">
                {[
                  { label: "Technical", v: activeOutput.technical_accuracy_score },
                  { label: "Coverage",  v: activeOutput.source_coverage_score },
                  { label: "Citations", v: activeOutput.citation_score },
                  { label: "LO Align", v: activeOutput.lo_alignment_score },
                ].map(({ label, v }) => (
                  <div key={label} className="flex items-center gap-1.5">
                    <span className="text-xs text-muted-foreground">{label}:</span>
                    <span className={`text-xs font-mono font-medium ${scoreColor(v)}`}>{v ?? "—"}</span>
                  </div>
                ))}
                {activeOutput.quality_issues?.length > 0 && (
                  <div className="ml-auto flex items-center gap-1 text-amber-400 text-xs">
                    <AlertTriangle className="w-3 h-3" />
                    {activeOutput.quality_issues.map(i => i.message).join(" • ")}
                  </div>
                )}
              </div>
            )}

            {/* Verification summary banner */}
            {verificationResults[activeOutput.id] && !editingOutput && (() => {
              const vr = verificationResults[activeOutput.id];
              const flagCount = vr.flagged.length;
              const errCount = vr.flagged.filter(f => f.severity === "error").length;
              const warnCount = flagCount - errCount;
              return (
                <div className={`flex items-start gap-3 px-4 py-2.5 border-b flex-shrink-0 text-xs
                  ${errCount > 0
                    ? "bg-rose-900/20 border-rose-800/30 text-rose-300"
                    : flagCount > 0
                      ? "bg-amber-900/20 border-amber-800/30 text-amber-300"
                      : "bg-emerald-900/20 border-emerald-800/30 text-emerald-300"}`}>
                  <ShieldCheck className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <span className="font-medium">Reference Verification: </span>
                    {flagCount === 0
                      ? "No issues found — all checked paragraphs match the reference material."
                      : `${flagCount} paragraph${flagCount !== 1 ? "s" : ""} flagged`
                        + (errCount > 0 ? ` (${errCount} error${errCount !== 1 ? "s" : ""})` : "")
                        + (warnCount > 0 ? ` (${warnCount} warning${warnCount !== 1 ? "s" : ""})` : "")
                        + " — scroll to highlighted paragraphs below."}
                    {vr.summary && <span className="ml-1 opacity-70">{vr.summary}</span>}
                  </div>
                </div>
              );
            })()}

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {editingOutput ? (
                <textarea
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  className="w-full h-full min-h-[400px] bg-white/5 border border-white/20 rounded-lg
                    p-4 text-sm font-mono focus:border-primary/40 focus:outline-none resize-none"
                />
              ) : Object.keys(activeFlags).length > 0 ? (
                // Flagged paragraph view.
                // IMPORTANT: filter empty paragraphs first so that the index
                // used here matches the index used by the backend verifier
                // (which also filters with `if p.strip()`).
                <div className="space-y-1 text-sm leading-relaxed font-sans text-foreground/90">
                  {activeOutput.content
                    .split("\n\n")
                    .filter(p => p.trim() !== "")
                    .map((para, idx) => {
                      const flag = activeFlags[idx];
                      if (!flag) {
                        return (
                          <p key={idx} className="whitespace-pre-wrap py-1">
                            {para}
                          </p>
                        );
                      }
                      return (
                        <div key={idx}
                          className={`rounded-lg border px-3 py-2 my-1
                            ${flag.severity === "error"
                              ? "bg-rose-900/25 border-rose-700/50"
                              : "bg-amber-900/20 border-amber-700/40"}`}>
                          <p className="whitespace-pre-wrap">{para}</p>
                          <div className={`flex items-start gap-1.5 mt-2 text-xs
                            ${flag.severity === "error" ? "text-rose-300" : "text-amber-300"}`}>
                            <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                            <span>{flag.concern}</span>
                          </div>
                        </div>
                      );
                    })}
                </div>
              ) : (
                <div className="prose prose-invert prose-sm max-w-none">
                  <pre className="whitespace-pre-wrap text-sm leading-relaxed font-sans text-foreground/90">
                    {activeOutput.content}
                  </pre>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Step 7: Export ────────────────────────────────────────────────────────────

function StepExport({
  project, outputs, exporting, onExport,
}: {
  project: EduProject;
  outputs: EduOutput[];
  exporting: string | null;
  onExport: (fmt: string) => void;
}) {
  const approved = outputs.filter(o => o.approved).length;
  const avgScore = outputs.length
    ? Math.round(outputs.reduce((s, o) => s + (o.quality_score ?? 0), 0) / outputs.length)
    : null;

  const formats = [
    {
      id: "zip",
      label: "Complete Package (ZIP)",
      desc: "All outputs + quality report + reference summary",
      icon: Archive,
      color: "text-primary",
      bg: "bg-primary/10 border-primary/30",
      recommended: true,
    },
    {
      id: "docx",
      label: "Word Document (DOCX)",
      desc: "All outputs combined in a single Word document",
      icon: FileText,
      color: "text-blue-400",
      bg: "bg-blue-900/15 border-blue-800/30",
    },
    {
      id: "pptx",
      label: "PowerPoint (PPTX)",
      desc: "Slide deck from the presentation output",
      icon: Presentation,
      color: "text-amber-400",
      bg: "bg-amber-900/15 border-amber-800/30",
    },
    {
      id: "txt",
      label: "Plain Text (TXT)",
      desc: "All outputs as plain text",
      icon: FileText,
      color: "text-white/60",
      bg: "bg-white/5 border-white/10",
    },
    {
      id: "csv",
      label: "Question Bank (CSV)",
      desc: "Quiz and exam questions in spreadsheet format",
      icon: FileSpreadsheet,
      color: "text-emerald-400",
      bg: "bg-emerald-900/15 border-emerald-800/30",
    },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-1">Export Training Package</h2>
        <p className="text-sm text-muted-foreground">
          Download your generated training materials in your preferred format.
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Outputs Generated", v: outputs.length, icon: FileText, color: "text-primary" },
          { label: "Approved", v: `${approved}/${outputs.length}`, icon: CheckCircle2, color: "text-emerald-400" },
          { label: "Overall Quality", v: avgScore !== null ? `${avgScore}/100` : "—", icon: BarChart2, color: scoreColor(avgScore) },
        ].map(({ label, v, icon: Icon, color }) => (
          <div key={label} className="bg-white/5 border border-white/10 rounded-lg p-4 text-center">
            <Icon className={`w-5 h-5 mx-auto mb-1 ${color}`} />
            <div className={`text-xl font-bold ${color}`}>{v}</div>
            <div className="text-xs text-muted-foreground">{label}</div>
          </div>
        ))}
      </div>

      {/* Format cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {formats.map(fmt => (
          <button
            key={fmt.id}
            onClick={() => onExport(fmt.id)}
            disabled={exporting !== null}
            className={`relative text-left p-4 rounded-lg border transition-all
              ${fmt.bg} hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {fmt.recommended && (
              <span className="absolute top-2 right-2 text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded font-medium">
                Recommended
              </span>
            )}
            <div className="flex items-center gap-3 mb-1">
              {exporting === fmt.id
                ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                : <Download className={`w-5 h-5 ${fmt.color}`} />}
              <span className="text-sm font-medium">{fmt.label}</span>
            </div>
            <p className="text-xs text-muted-foreground">{fmt.desc}</p>
          </button>
        ))}
      </div>

      {/* Output list */}
      {outputs.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-3">Package Contents</h3>
          <div className="space-y-1">
            {outputs.map(o => (
              <div key={o.id}
                className="flex items-center gap-3 px-3 py-2 rounded bg-white/3 border border-white/8">
                {o.approved
                  ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                  : <div className="w-3.5 h-3.5 rounded-full border border-white/20 flex-shrink-0" />}
                <span className="text-sm flex-1">{o.title}</span>
                {o.quality_score !== null && <ScorePill score={o.quality_score} />}
                {o.citations?.length > 0 && (
                  <span className="text-xs text-muted-foreground">{o.citations.length} citations</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
