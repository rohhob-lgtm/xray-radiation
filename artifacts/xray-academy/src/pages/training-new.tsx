import { useState, useRef, useCallback, useEffect } from 'react';
import { useLocation, Link } from 'wouter';
import { useListProviders } from '@workspace/api-client-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Upload, FileText, ChevronRight, ChevronLeft, Loader2,
  Check, AlertCircle, BookMarked, Users, Layers, Sparkles,
  Download, FolderOpen
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── Types ─────────────────────────────────────────────────────────────────────

interface PagePreview { page_num: number; text: string }
interface UploadResult {
  project_id: string;
  filename: string;
  page_count: number;
  content_pages?: number;
  total_chars?: number;
  preview_pages: PagePreview[];
}

interface SlidePreview {
  slide_index: number;
  type: string;
  title: string;
  bullets: string[];
  source_pages: number[];
}

interface StepProgress {
  step: number;
  name: string;
  status: 'pending' | 'running' | 'done' | 'warning' | 'error';
  data?: Record<string, any>;
}

interface ExportVerificationResult {
  ready: boolean;
  project_id: string;
  artifacts?: Record<string, {
    ok: boolean;
    filename: string;
    path: string;
    size: number;
    download_url: string;
  }>;
  errors?: string[];
}

interface ExpertPptSource {
  doc_id: string;
  filename: string;
  course_title?: string;
  manufacturer?: string;
  equipment_model?: string;
  language?: string;
  slide_count?: number;
  trusted?: boolean;
  manufacturer_approved?: boolean;
  internal_training_reference?: boolean;
  cached?: boolean;
  speaker_notes_count?: number;
  laboratories_count?: number;
  quizzes_count?: number;
  troubleshooting_modules_count?: number;
}

interface ExpertCoursesUploadResponse {
  uploaded?: Array<{ doc_id: string; filename: string }>;
  failed?: Array<{ filename: string; error: string }>;
  uploaded_count?: number;
}

interface TeachingDnaSummary {
  source_file?: string;
  expert_courses_count?: number;
  total_slides_analyzed?: number;
  total_instructor_notes_analyzed?: number;
  modules_detected?: number;
  role_types?: number;
  module_sequence_template?: string[];
  lab_patterns?: number;
  troubleshooting_patterns?: number;
  assessment_patterns?: number;
  visual_patterns?: number;
  transition_patterns?: number;
  selection_warnings?: string[];
  recommended_dataset?: {
    min_courses?: number;
    recommended_total_slides?: number;
    warning_below_total_slides?: number;
  };
  pattern_confidence?: {
    lab_patterns?: number;
    troubleshooting_patterns?: number;
    assessment_patterns?: number;
    visual_patterns?: number;
    transition_patterns?: number;
  };
}

interface CourseSettings {
  course_title: string;
  manufacturer: string;
  equipment_model: string;
  audience: string;
  training_type: string;
  course_type: string;
  audience_level: string;
  language: string;
  difficulty: string;
  duration: string;
  output_format: string;
  visual_density: string;
  assessment_level: string;
  slide_depth: string;
  target_slides: number;
  country: string;
  customer_org: string;
  instructor_name: string;
  include_notes: boolean;
  include_instructor_notes: boolean;
  include_quizzes: boolean;
  include_practical: boolean;
  include_exam: boolean;
  include_student_workbook: boolean;
  include_answer_key: boolean;
  use_powerpoint_knowledge_base: boolean;
  use_powerpoint_references: boolean;
  use_manufacturer_approved_only: boolean;
  use_powerpoint_technical_support: boolean;
  use_powerpoint_layout_inspiration: boolean;
  use_powerpoint_terminology: boolean;
  use_powerpoint_exercises_assessments: boolean;
  use_arabic_formatting_examples: boolean;
  powerpoint_reference_strictness: string;
  powerpoint_options?: Record<string, boolean>;
  enhance_training_material: boolean;
  learn_from_expert_powerpoint: boolean;
  expert_powerpoint_doc_id: string;
  expert_powerpoint_doc_ids: string[];
  reanalyze_expert_powerpoint: boolean;
  enhancement_options: Record<string, boolean>;
}

// ── Options ────────────────────────────────────────────────────────────────────

const AUDIENCES = [
  { value: 'X-Ray Operators',        icon: '👨‍✈️', desc: 'Operation, controls, alarms, daily checks' },
  { value: 'Maintenance Engineers',   icon: '🔧', desc: 'Components, diagnostics, calibration, repair' },
  { value: 'Field Service Engineers', icon: '⚙️', desc: 'Installation, commissioning, service procedures' },
  { value: 'Supervisors',             icon: '📋', desc: 'Compliance, reporting, team management' },
  { value: 'System Administrators',   icon: '💻', desc: 'Software, networking, configuration' },
  { value: 'Train-the-Trainer',       icon: '🎓', desc: 'Teaching methodology + full technical content' },
];

const COURSE_TYPES = [
  'Operator Training',
  'Maintenance Training',
  'Installation Training',
  'Troubleshooting Training',
  'Radiation Safety Training',
  'Train-the-Trainer Course',
  'Complete Technical Course',
];

const AUDIENCE_LEVELS = [
  { value: 'beginner', label: 'Beginner' },
  { value: 'intermediate', label: 'Intermediate' },
  { value: 'advanced', label: 'Advanced' },
  { value: 'mixed', label: 'Mixed' },
];

const OUTPUT_FORMATS = [
  { value: 'pptx', label: 'PowerPoint (PPTX)' },
  { value: 'docx', label: 'Word (DOCX)' },
  { value: 'pdf', label: 'PDF' },
  { value: 'zip', label: 'Complete ZIP Package' },
];

const VISUAL_DENSITY_OPTIONS = [
  { value: 'text-focused', label: 'Text focused' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'visual-rich', label: 'Visual rich' },
];

const ASSESSMENT_LEVELS = [
  { value: 'basic', label: 'Basic' },
  { value: 'standard', label: 'Standard' },
  { value: 'advanced', label: 'Advanced' },
];

const PPT_REFERENCE_STRICTNESS = [
  { value: 'strict', label: 'Strict: same manufacturer and exact model only' },
  { value: 'balanced', label: 'Balanced: same manufacturer/product family/related topic' },
  { value: 'broad', label: 'Broad: any relevant training presentation' },
];

const ENHANCEMENT_OPTIONS: Array<{ key: string; label: string }> = [
  { key: 'improve_scientific_explanation', label: 'Improve scientific explanation' },
  { key: 'simplify_complex_technical_language', label: 'Simplify complex technical language' },
  { key: 'add_instructor_notes', label: 'Add instructor notes' },
  { key: 'add_practical_examples', label: 'Add practical examples' },
  { key: 'add_safety_emphasis', label: 'Add safety emphasis' },
  { key: 'add_diagrams_visual_explanations', label: 'Add diagrams and visual explanations' },
  { key: 'add_knowledge_checks', label: 'Add knowledge checks' },
  { key: 'add_practical_exercises', label: 'Add practical exercises' },
  { key: 'add_troubleshooting_scenarios', label: 'Add troubleshooting scenarios' },
  { key: 'add_course_summary_glossary', label: 'Add course summary and glossary' },
];

const SLIDE_DEPTHS = [
  {
    value: 'concise',
    label: 'Concise',
    range: '40–80 slides',
    desc: 'Core content only. Half-day to 1-day courses.',
    icon: '📄',
  },
  {
    value: 'standard',
    label: 'Standard',
    range: '80–150 slides',
    desc: 'Full topic coverage with exercises. 2–3 day courses.',
    icon: '📋',
  },
  {
    value: 'detailed',
    label: 'Detailed',
    range: '150–220 slides',
    desc: 'Deep engineering content + practical labs. 3–5 day courses.',
    icon: '📚',
  },
  {
    value: 'full_cert',
    label: 'Full Certification',
    range: '200–300 slides',
    desc: 'Complete certification course with exams. Full service curriculum.',
    icon: '🎓',
  },
];

const SLIDE_TYPE_COLORS: Record<string, string> = {
  title:      'bg-sky-500/10 border-sky-500/20 text-sky-300',
  agenda:     'bg-indigo-500/10 border-indigo-500/20 text-indigo-300',
  section:    'bg-violet-500/10 border-violet-500/20 text-violet-300',
  objectives: 'bg-blue-500/10 border-blue-500/20 text-blue-300',
  content:    'bg-slate-500/10 border-slate-500/20 text-slate-300',
  quiz:       'bg-amber-500/10 border-amber-500/20 text-amber-300',
  practical:  'bg-orange-500/10 border-orange-500/20 text-orange-300',
  summary:    'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
  references: 'bg-pink-500/10 border-pink-500/20 text-pink-300',
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function TrainingNewPage() {
  const [, navigate] = useLocation();
  const { toast } = useToast();

  // Step: upload | configure | generate | done
  const [step, setStep] = useState<'upload' | 'configure' | 'generate' | 'done'>('upload');

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [providerId, setProviderId] = useState('auto');
  const { data: aiProviders } = useListProviders();

  // Configure state
  const [settings, setSettings] = useState<CourseSettings>({
    course_title: '',
    manufacturer: '',
    equipment_model: '',
    audience: 'Maintenance Engineers',
    training_type: 'Complete Technical Course',
    course_type: 'Complete Technical Course',
    audience_level: 'mixed',
    language: 'english',
    difficulty: 'advanced',
    duration: '3 days',
    output_format: 'pptx',
    visual_density: 'balanced',
    assessment_level: 'standard',
    slide_depth: 'detailed',
    target_slides: 150,
    country: 'International',
    customer_org: '',
    instructor_name: '',
    include_notes: true,
    include_instructor_notes: true,
    include_quizzes: true,
    include_practical: true,
    include_exam: true,
    include_student_workbook: true,
    include_answer_key: true,
    use_powerpoint_knowledge_base: true,
    use_powerpoint_references: true,
    use_manufacturer_approved_only: false,
    use_powerpoint_technical_support: true,
    use_powerpoint_layout_inspiration: true,
    use_powerpoint_terminology: true,
    use_powerpoint_exercises_assessments: true,
    use_arabic_formatting_examples: true,
    powerpoint_reference_strictness: 'balanced',
    enhance_training_material: true,
    learn_from_expert_powerpoint: false,
    expert_powerpoint_doc_id: '',
    expert_powerpoint_doc_ids: [],
    reanalyze_expert_powerpoint: false,
    enhancement_options: {
      improve_scientific_explanation: true,
      simplify_complex_technical_language: true,
      add_instructor_notes: true,
      add_practical_examples: true,
      add_safety_emphasis: true,
      add_diagrams_visual_explanations: true,
      add_knowledge_checks: true,
      add_practical_exercises: true,
      add_troubleshooting_scenarios: true,
      add_course_summary_glossary: true,
    },
  });
  const [qualityWarnings, setQualityWarnings] = useState<{errors: string[], warnings: string[], safety_pct: number} | null>(null);
  const [pipelineWarnings, setPipelineWarnings] = useState<string[]>([]);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [genStatus, setGenStatus] = useState('');
  const [slides, setSlides] = useState<SlidePreview[]>([]);
  const [genError, setGenError] = useState<string | null>(null);
  const [finalProjectId, setFinalProjectId] = useState<string | null>(null);
  const [stepProgress, setStepProgress] = useState<StepProgress[]>([]);
  const [showDebug, setShowDebug] = useState(false);
  const [exportVerified, setExportVerified] = useState(false);
  const [exportInfo, setExportInfo] = useState<ExportVerificationResult | null>(null);
  const [exportFailure, setExportFailure] = useState<string | null>(null);
  const [draftStatus, setDraftStatus] = useState<string>('Draft — Instructor Review Recommended');
  const [finalQualityScore, setFinalQualityScore] = useState<number>(0);
  const [expertSources, setExpertSources] = useState<ExpertPptSource[]>([]);
  const [loadingExpertSources, setLoadingExpertSources] = useState(false);
  const [analyzingTeachingDna, setAnalyzingTeachingDna] = useState(false);
  const [teachingDnaSummary, setTeachingDnaSummary] = useState<TeachingDnaSummary | null>(null);
  const [uploadingExpertCourses, setUploadingExpertCourses] = useState(false);
  const expertCoursesFileRef = useRef<HTMLInputElement | null>(null);

  const selectedExpertDocIds = Array.from(new Set([
    ...(settings.expert_powerpoint_doc_ids || []),
    ...(settings.expert_powerpoint_doc_id ? [settings.expert_powerpoint_doc_id] : []),
  ].filter(Boolean)));
  const selectedExpertSources = expertSources.filter(src => selectedExpertDocIds.includes(src.doc_id));
  const selectedExpertCoursesCount = selectedExpertSources.length;
  const selectedExpertSlides = selectedExpertSources.reduce((sum, src) => sum + Number(src.slide_count || 0), 0);
  const selectedExpertSpeakerNotes = selectedExpertSources.reduce((sum, src) => sum + Number(src.speaker_notes_count || 0), 0);
  const selectedExpertLabs = selectedExpertSources.reduce((sum, src) => sum + Number(src.laboratories_count || 0), 0);
  const selectedExpertQuizzes = selectedExpertSources.reduce((sum, src) => sum + Number(src.quizzes_count || 0), 0);
  const selectedExpertTroubleshooting = selectedExpertSources.reduce((sum, src) => sum + Number(src.troubleshooting_modules_count || 0), 0);
  const canBuildMasterBlueprint = selectedExpertCoursesCount >= 1;
  const hasRecommendedExpertDataset = selectedExpertCoursesCount >= 5 && selectedExpertSlides >= 200;

  const loadExpertSources = useCallback(async () => {
    setLoadingExpertSources(true);
    try {
      const r = await fetch(`${API}/api/training/teaching-dna/sources`, { credentials: 'include' });
      if (!r.ok) throw new Error(await r.text());
      const rows: ExpertPptSource[] = await r.json();
      setExpertSources(Array.isArray(rows) ? rows : []);
    } catch (e: any) {
      toast({ title: 'Expert sources load failed', description: e?.message || 'Could not load trusted PowerPoint sources.', variant: 'destructive' });
    } finally {
      setLoadingExpertSources(false);
    }
  }, [toast]);

  const toggleExpertCourseSelection = useCallback((docId: string) => {
    setSettings(prev => {
      const current = Array.from(new Set([...(prev.expert_powerpoint_doc_ids || []), ...(prev.expert_powerpoint_doc_id ? [prev.expert_powerpoint_doc_id] : [])]));
      const next = current.includes(docId)
        ? current.filter(id => id !== docId)
        : [...current, docId];
      return {
        ...prev,
        expert_powerpoint_doc_ids: next,
        expert_powerpoint_doc_id: next[0] || '',
      };
    });
  }, []);

  const uploadExpertCourses = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setUploadingExpertCourses(true);
    try {
      const form = new FormData();
      Array.from(files).forEach((f) => form.append('files', f));

      const r = await fetch(`${API}/api/training/teaching-dna/upload-courses`, {
        method: 'POST',
        body: form,
        credentials: 'include',
      });
      if (!r.ok) throw new Error(await r.text());

      const data: ExpertCoursesUploadResponse = await r.json();
      const uploadedDocIds = (data.uploaded || []).map(x => x.doc_id).filter(Boolean);

      await loadExpertSources();

      if (uploadedDocIds.length > 0) {
        setSettings(prev => {
          const current = Array.from(new Set([...(prev.expert_powerpoint_doc_ids || []), ...(prev.expert_powerpoint_doc_id ? [prev.expert_powerpoint_doc_id] : [])]));
          const next = Array.from(new Set([...current, ...uploadedDocIds]));
          return {
            ...prev,
            expert_powerpoint_doc_ids: next,
            expert_powerpoint_doc_id: next[0] || '',
          };
        });
      }

      const failedCount = (data.failed || []).length;
      if (failedCount > 0) {
        toast({
          title: 'Some courses uploaded',
          description: `${data.uploaded_count || uploadedDocIds.length} added, ${failedCount} failed.`,
          variant: 'destructive',
        });
      } else {
        toast({
          title: 'Expert courses added',
          description: `${data.uploaded_count || uploadedDocIds.length} PowerPoint course(s) indexed and ready.`,
        });
      }
    } catch (e: any) {
      toast({ title: 'Expert upload failed', description: e?.message || 'Could not upload expert PowerPoint files.', variant: 'destructive' });
    } finally {
      if (expertCoursesFileRef.current) expertCoursesFileRef.current.value = '';
      setUploadingExpertCourses(false);
    }
  }, [loadExpertSources, toast]);

  const analyzeTeachingDna = useCallback(async (forceReanalyze: boolean) => {
    if (selectedExpertDocIds.length === 0) {
      toast({ title: 'Select source first', description: 'Choose one or more trusted expert courses before analysis.', variant: 'destructive' });
      return;
    }
    setAnalyzingTeachingDna(true);
    try {
      const r = await fetch(`${API}/api/training/teaching-dna/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          doc_ids: selectedExpertDocIds,
          doc_id: selectedExpertDocIds[0] || '',
          force_reanalyze: forceReanalyze,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setTeachingDnaSummary((data?.summary || null) as TeachingDnaSummary | null);
      toast({
        title: data?.cached ? 'Master blueprint loaded from cache' : 'Master blueprint created',
        description: data?.summary?.source_file || 'Consolidated expert teaching blueprint is ready.',
      });
    } catch (e: any) {
      toast({ title: 'Blueprint analysis failed', description: e?.message || 'Could not analyze expert courses.', variant: 'destructive' });
    } finally {
      setAnalyzingTeachingDna(false);
    }
  }, [selectedExpertDocIds, toast]);

  useEffect(() => {
    if (settings.learn_from_expert_powerpoint && expertSources.length === 0 && !loadingExpertSources) {
      loadExpertSources();
    }
  }, [settings.learn_from_expert_powerpoint, expertSources.length, loadingExpertSources, loadExpertSources]);

  // ── Upload ──────────────────────────────────────────────────────────────────

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Only PDF files are accepted.');
      return;
    }
    setUploadError(null);
    setUploading(true);
    const form = new FormData();
    form.append('file', file);
    try {
      const r = await fetch(`${API}/api/training/upload-manual`, {
        method: 'POST', body: form, credentials: 'include',
      });
      if (!r.ok) throw new Error(await r.text());
      const data: UploadResult = await r.json();
      setUploadResult(data);
      setSettings(s => ({
        ...s,
        course_title: data.filename.replace(/\.pdf$/i, '').replace(/[_-]/g, ' '),
      }));
    } catch (e: any) {
      setUploadError(e.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  }, []);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  // ── Generate ────────────────────────────────────────────────────────────────

  const startGeneration = async () => {
    if (!uploadResult) return;
    setStep('generate');
    setGenerating(true);
    setSlides([]);
    setGenError(null);
    setExportVerified(false);
    setExportInfo(null);
    setExportFailure(null);
    setDraftStatus('Draft — Instructor Review Recommended');
    setFinalQualityScore(0);
    setStepProgress([]);
    setPipelineWarnings([]);
    setGenStatus('Connecting to generation pipeline…');

    const body = {
      project_id: uploadResult.project_id,
      provider_id: providerId,
      settings: {
        ...settings,
        powerpoint_options: {
          use_powerpoint_references: settings.use_powerpoint_references,
          use_manufacturer_approved_only: settings.use_manufacturer_approved_only,
          use_powerpoint_technical_support: settings.use_powerpoint_technical_support,
          use_powerpoint_layout_inspiration: settings.use_powerpoint_layout_inspiration,
          use_powerpoint_terminology: settings.use_powerpoint_terminology,
          use_powerpoint_exercises_assessments: settings.use_powerpoint_exercises_assessments,
          use_arabic_formatting_examples: settings.use_arabic_formatting_examples,
        },
      },
    };

    const updateStep = (upd: Partial<StepProgress> & { step: number; name: string }) => {
      setStepProgress(prev => {
        const next = [...prev];
        const idx = next.findIndex(s => s.step === upd.step);
        if (idx >= 0) {
          next[idx] = { ...next[idx], ...upd };
        } else {
          next.push({ status: 'pending', data: {}, ...upd } as StepProgress);
        }
        return next.sort((a, b) => a.step - b.step);
      });
    };

    try {
      const r = await fetch(`${API}/api/training/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        credentials: 'include',
      });
      if (!r.ok) {
        const errText = await r.text();
        throw new Error(`Server error ${r.status}: ${errText}`);
      }
      if (!r.body) throw new Error('No response stream from server');

      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let d: any;
          try {
            d = JSON.parse(line.slice(6));
          } catch {
            continue; // skip malformed SSE line
          }

          if (d.type === 'step') {
            updateStep({ step: d.step, name: d.name, status: d.status, data: d.data });
            const total = PIPELINE_STEPS.length;
            if (d.status === 'running') setGenStatus(`Step ${d.step}/${total}: ${d.name}…`);
            if (d.status === 'done')    setGenStatus(`Step ${d.step}/${total}: ${d.name} ✓`);
            if (d.status === 'warning') setGenStatus(`Step ${d.step}/${total}: ${d.name} ⚠`);

          } else if (d.type === 'slide') {
            setSlides(prev => {
              const next = [...prev];
              next[d.index] = d.slide;
              return next;
            });
            setGenStatus(`Saving slide ${d.index + 1}…`);

          } else if (d.type === 'done') {
            setFinalProjectId(d.project_id);
            setDraftStatus(d.draft_status || 'Draft — Instructor Review Recommended');
            setFinalQualityScore(Number(d?.generation_summary?.overall_quality_score || 0));
            setGenStatus('Generation complete — verifying export artifacts…');

            try {
              const vr = await fetch(`${API}/api/training/export/verify/${d.project_id}`, {
                method: 'GET',
                credentials: 'include',
              });
              if (!vr.ok) {
                const txt = await vr.text();
                throw new Error(`Export verification failed (${vr.status}): ${txt}`);
              }
              const verification: ExportVerificationResult = await vr.json();
              setExportInfo(verification);
              if (!verification.ready) {
                const message = (verification.errors && verification.errors.length > 0)
                  ? verification.errors.join(' | ')
                  : 'Export verification failed. Generated files are not ready for download.';
                setExportFailure(message);
                setGenError(message);
                setGenStatus('Export verification failed');
                setStep('generate');
                setGenerating(false);
                return;
              }

              setExportVerified(true);
              setGenStatus(`Complete — ${d.slide_count} slides generated and export verified`);
              setStep('done');
            } catch (verifyErr: any) {
              const message = verifyErr?.message || 'Export verification request failed';
              setExportFailure(message);
              setGenError(message);
              setGenStatus('Export verification failed');
              setStep('generate');
              setGenerating(false);
              return;
            }

          } else if (d.type === 'quality_warning') {
            setQualityWarnings({
              errors:     d.errors   || [],
              warnings:   d.warnings || [],
              safety_pct: d.safety_pct || 0,
            });

          } else if (d.type === 'warning') {
            const msg = d.message || 'Optional enhancement stage reported a warning.';
            setPipelineWarnings(prev => [...prev, msg]);

          } else if (d.type === 'error') {
            // Mark the failed step as error
            if (d.step) {
              updateStep({ step: d.step, name: `Step ${d.step}`, status: 'error', data: { error: d.error, debug: d.debug } });
            }
            setGenError(d.error || 'Generation failed');
            setExportVerified(false);
            setGenerating(false);
            return;
          }
        }
      }
    } catch (e: any) {
      setGenError(e.message || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  // ── Render helpers ──────────────────────────────────────────────────────────

  const StepIndicator = () => (
    <div className="flex items-center gap-2 text-xs font-mono">
      {(['upload', 'configure', 'generate', 'done'] as const).map((s, i) => {
        const isActive = step === s;
        const isDone = ['upload', 'configure', 'generate', 'done'].indexOf(step) >
                       ['upload', 'configure', 'generate', 'done'].indexOf(s);
        return (
          <div key={s} className="flex items-center gap-2">
            {i > 0 && <div className={`w-8 h-px ${isDone || isActive ? 'bg-primary' : 'bg-border'}`} />}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-semibold uppercase tracking-wider
              ${isActive ? 'bg-primary text-primary-foreground border-primary' :
                isDone   ? 'bg-primary/10 text-primary border-primary/30' :
                           'bg-transparent text-muted-foreground border-border'}`}>
              {isDone ? <Check className="h-2.5 w-2.5" /> : <span>{i + 1}</span>}
              <span className="hidden sm:inline">
                {s === 'upload' ? 'Upload' : s === 'configure' ? 'Configure' :
                 s === 'generate' ? 'Generate' : 'Done'}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );

  // ── Step: Upload ──────────────────────────────────────────────────────────

  const UploadStep = () => (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-foreground mb-1">Upload Equipment Manual</h2>
        <p className="text-sm text-muted-foreground">Upload the PDF manual your training course will be based on.</p>
      </div>

      {!uploadResult ? (
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center gap-4 cursor-pointer transition-all
            ${dragOver ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50 hover:bg-primary/3'}`}>
          <input ref={fileRef} type="file" accept=".pdf" className="hidden"
            onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
          {uploading ? (
            <>
              <Loader2 className="h-12 w-12 animate-spin text-primary" />
              <p className="text-sm font-medium text-foreground">Extracting manual content…</p>
              <p className="text-xs text-muted-foreground">This may take 30–60 seconds for large manuals</p>
            </>
          ) : (
            <>
              <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center ring-1 ring-primary/20">
                <Upload className="h-8 w-8 text-primary" />
              </div>
              <div className="text-center">
                <p className="text-base font-semibold text-foreground">Drop PDF here or click to browse</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Operator manual · Service manual · Installation guide · Troubleshooting guide
                </p>
              </div>
              <Badge variant="outline" className="text-xs">PDF only · Any size</Badge>
            </>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5 space-y-4">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0">
              <Check className="h-5 w-5 text-emerald-400" />
            </div>
            <div className="flex-1">
              <p className="font-semibold text-foreground">{uploadResult.filename}</p>
              <p className="text-sm text-muted-foreground">{uploadResult.page_count} pages extracted</p>
            </div>
            <Button size="sm" variant="ghost" className="text-xs text-muted-foreground"
              onClick={() => { setUploadResult(null); setUploadError(null); }}>
              Change
            </Button>
          </div>

          {uploadResult.preview_pages.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider">Content Preview</p>
              {uploadResult.preview_pages.slice(0, 3).map(pg => (
                <div key={pg.page_num}
                  className="rounded-lg bg-background/50 border border-border/50 px-3 py-2">
                  <p className="text-[10px] font-mono text-primary mb-1">Page {pg.page_num}</p>
                  <p className="text-xs text-muted-foreground line-clamp-2">{pg.text || '(no text on this page)'}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {uploadError && (
        <Alert className="border-destructive/30 bg-destructive/5">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-xs">{uploadError}</AlertDescription>
        </Alert>
      )}

      <div className="flex justify-end">
        <Button onClick={() => setStep('configure')} disabled={!uploadResult} className="gap-2 font-semibold">
          Configure Course <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );

  // ── Step: Configure ────────────────────────────────────────────────────────

  const ConfigureStep = () => {
    const set = (k: keyof CourseSettings, v: any) => setSettings(s => ({ ...s, [k]: v }));
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-foreground mb-1">Configure Your Course</h2>
            <p className="text-sm text-muted-foreground">Customise the training content for your audience.</p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setStep('upload')} className="gap-1 text-xs">
            <ChevronLeft className="h-3.5 w-3.5" /> Back
          </Button>
        </div>

        {/* Course identity */}
        <div className="space-y-4">
          <h3 className="text-xs font-mono font-bold text-muted-foreground/70 uppercase tracking-widest">Course Details</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Course Title *</Label>
              <Input value={settings.course_title} onChange={e => set('course_title', e.target.value)}
                placeholder="e.g. RTT 110 Operator Training" className="h-9 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Manufacturer</Label>
              <Input value={settings.manufacturer} onChange={e => set('manufacturer', e.target.value)}
                placeholder="e.g. Rapiscan Systems" className="h-9 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Equipment Model</Label>
              <Input value={settings.equipment_model} onChange={e => set('equipment_model', e.target.value)}
                placeholder="e.g. RTT 110" className="h-9 text-sm" />
            </div>
          </div>
        </div>

        {/* Audience */}
        <div className="space-y-3">
          <h3 className="text-xs font-mono font-bold text-muted-foreground/70 uppercase tracking-widest">Training Audience</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {AUDIENCES.map(a => (
              <button key={a.value} type="button"
                onClick={() => set('audience', a.value)}
                className={`rounded-lg border p-3 text-left transition-all hover:border-primary/50 space-y-1
                  ${settings.audience === a.value
                    ? 'border-primary bg-primary/10 ring-1 ring-primary/30'
                    : 'border-border bg-card/40 hover:bg-card'}`}>
                <div className="flex items-center gap-2">
                  <span className="text-base">{a.icon}</span>
                  <span className="text-xs font-semibold text-foreground">{a.value}</span>
                  {settings.audience === a.value && (
                    <Check className="h-3 w-3 text-primary ml-auto shrink-0" />
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground leading-relaxed">{a.desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Course type */}
        <div className="space-y-3">
          <h3 className="text-xs font-mono font-bold text-muted-foreground/70 uppercase tracking-widest">Course Type</h3>
          <div className="flex flex-wrap gap-2">
            {COURSE_TYPES.map(t => (
              <button key={t} type="button" onClick={() => setSettings(prev => ({ ...prev, training_type: t, course_type: t }))}
                className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all
                  ${settings.training_type === t
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'}`}>
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Course depth */}
        <div className="space-y-3">
          <h3 className="text-xs font-mono font-bold text-muted-foreground/70 uppercase tracking-widest">Course Depth</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {SLIDE_DEPTHS.map(d => (
              <button key={d.value} type="button"
                onClick={() => set('slide_depth', d.value)}
                className={`rounded-lg border p-3 text-left transition-all hover:border-primary/50 space-y-1
                  ${settings.slide_depth === d.value
                    ? 'border-primary bg-primary/10 ring-1 ring-primary/30'
                    : 'border-border bg-card/40 hover:bg-card'}`}>
                <div className="flex items-center gap-2">
                  <span className="text-base">{d.icon}</span>
                  <span className="text-xs font-semibold text-foreground">{d.label}</span>
                  {settings.slide_depth === d.value && (
                    <Check className="h-3 w-3 text-primary ml-auto shrink-0" />
                  )}
                </div>
                <p className="text-[10px] text-primary/80 font-mono font-semibold">{d.range}</p>
                <p className="text-[10px] text-muted-foreground leading-relaxed">{d.desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Course settings grid */}
        <div className="space-y-4">
          <h3 className="text-xs font-mono font-bold text-muted-foreground/70 uppercase tracking-widest">Course Settings</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Language</Label>
              <Select value={settings.language} onValueChange={v => set('language', v)}>
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="english">English</SelectItem>
                  <SelectItem value="arabic">Arabic</SelectItem>
                  <SelectItem value="bilingual">Bilingual (EN + AR)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Difficulty</Label>
              <Select value={settings.difficulty} onValueChange={v => set('difficulty', v)}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="basic">Basic</SelectItem>
                  <SelectItem value="intermediate">Intermediate</SelectItem>
                  <SelectItem value="advanced">Advanced</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Duration</Label>
              <Select value={settings.duration} onValueChange={v => set('duration', v)}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="half day">Half Day (4h)</SelectItem>
                  <SelectItem value="1 day">1 Day (8h)</SelectItem>
                  <SelectItem value="2 days">2 Days</SelectItem>
                  <SelectItem value="3 days">3 Days</SelectItem>
                  <SelectItem value="5 days">5 Days</SelectItem>
                  <SelectItem value="1 week">1 Week (Full Service)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Audience Level</Label>
              <Select value={settings.audience_level} onValueChange={v => set('audience_level', v)}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {AUDIENCE_LEVELS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Output Format</Label>
              <Select value={settings.output_format} onValueChange={v => set('output_format', v)}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {OUTPUT_FORMATS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Visual Density</Label>
              <Select value={settings.visual_density} onValueChange={v => set('visual_density', v)}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {VISUAL_DENSITY_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Assessment Level</Label>
              <Select value={settings.assessment_level} onValueChange={v => set('assessment_level', v)}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ASSESSMENT_LEVELS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Country / Regulatory</Label>
              <Input value={settings.country} onChange={e => set('country', e.target.value)}
                placeholder="International" className="h-9 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Customer / Organisation</Label>
              <Input value={settings.customer_org} onChange={e => set('customer_org', e.target.value)}
                placeholder="Optional" className="h-9 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Instructor Name</Label>
              <Input value={settings.instructor_name} onChange={e => set('instructor_name', e.target.value)}
                placeholder="Optional" className="h-9 text-sm" />
            </div>
          </div>
        </div>

        <div className="space-y-3 rounded-xl border border-primary/30 bg-primary/5 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Enhance Training Material</h3>
              <p className="text-xs text-muted-foreground">
                Improve the source manual content using professional instructional design, clearer explanations,
                scientific background, visuals, exercises, and assessments.
              </p>
            </div>
            <Switch
              checked={settings.enhance_training_material}
              onCheckedChange={v => set('enhance_training_material', v)}
            />
          </div>

          {settings.enhance_training_material && (
            <div className="space-y-3 pt-1">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {ENHANCEMENT_OPTIONS.map(opt => (
                  <div key={opt.key} className="flex items-center justify-between rounded-lg border border-border bg-card/40 px-3 py-2">
                    <Label className="text-xs cursor-pointer" htmlFor={`enh-${opt.key}`}>{opt.label}</Label>
                    <Switch
                      id={`enh-${opt.key}`}
                      checked={Boolean(settings.enhancement_options?.[opt.key])}
                      onCheckedChange={(v) => setSettings(prev => ({
                        ...prev,
                        enhancement_options: {
                          ...prev.enhancement_options,
                          [opt.key]: v,
                        },
                      }))}
                    />
                  </div>
                ))}
              </div>

              <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h4 className="text-xs font-semibold text-foreground">Learn From Expert PowerPoint</h4>
                    <p className="text-[11px] text-muted-foreground">
                      Use an Expert Course Library to build one consolidated Master Teaching Blueprint from
                      multiple trusted human-created courses.
                    </p>
                  </div>
                  <Switch
                    checked={settings.learn_from_expert_powerpoint}
                    onCheckedChange={(v) => setSettings(prev => ({
                      ...prev,
                      learn_from_expert_powerpoint: v,
                    }))}
                  />
                </div>

                {settings.learn_from_expert_powerpoint && (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <Label className="text-xs text-muted-foreground">Expert Course Library</Label>
                          <div className="flex items-center gap-2">
                            <input
                              ref={expertCoursesFileRef}
                              type="file"
                              accept=".pptx"
                              multiple
                              className="hidden"
                              onChange={(e) => uploadExpertCourses(e.target.files)}
                            />
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-8 text-[11px]"
                              onClick={() => expertCoursesFileRef.current?.click()}
                              disabled={uploadingExpertCourses}
                            >
                              {uploadingExpertCourses ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Upload className="h-3.5 w-3.5 mr-1" />}
                              Add Expert Courses
                            </Button>
                          </div>
                        </div>
                        <div className="max-h-44 overflow-auto rounded-md border border-border bg-background/40 p-2 space-y-1.5">
                          {loadingExpertSources ? (
                            <p className="text-xs text-muted-foreground">Loading sources...</p>
                          ) : expertSources.length === 0 ? (
                            <p className="text-xs text-muted-foreground">No trusted expert courses found.</p>
                          ) : (
                            expertSources.map(src => {
                              const selected = selectedExpertDocIds.includes(src.doc_id);
                              return (
                                <label
                                  key={src.doc_id}
                                  className={`w-full rounded border px-2.5 py-2 text-left text-xs transition-colors cursor-pointer flex items-start gap-2 ${selected ? 'border-primary/40 bg-primary/10' : 'border-border bg-card/30 hover:bg-card/60'}`}
                                >
                                  <Checkbox
                                    checked={selected}
                                    onCheckedChange={() => toggleExpertCourseSelection(src.doc_id)}
                                    className="mt-0.5"
                                  />
                                  <div className="min-w-0">
                                    <p className="font-medium text-foreground truncate">{src.filename}</p>
                                    <p className="text-[11px] text-muted-foreground">
                                      {src.slide_count || 0} slides
                                      {' | '}{src.speaker_notes_count || 0} speaker notes
                                      {' | '}{src.cached ? 'cached' : 'not cached'}
                                    </p>
                                  </div>
                                </label>
                              );
                            })
                          )}
                        </div>
                        <div className="text-[11px] text-muted-foreground space-y-1">
                          <p>Selected courses: {selectedExpertCoursesCount}</p>
                          <p>Total slides: {selectedExpertSlides}</p>
                          <p>Total speaker notes: {selectedExpertSpeakerNotes}</p>
                          <p>Total laboratories: {selectedExpertLabs}</p>
                          <p>Total quizzes: {selectedExpertQuizzes}</p>
                          <p>Total troubleshooting modules: {selectedExpertTroubleshooting}</p>
                          <p>Build is enabled once at least 1 course is selected.</p>
                          {!hasRecommendedExpertDataset && selectedExpertCoursesCount > 0 && (
                            <p className="text-amber-300">Warning: recommended baseline is 5 courses and 200 total slides for stronger pattern reliability.</p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-9"
                          onClick={() => analyzeTeachingDna(false)}
                          disabled={!canBuildMasterBlueprint || analyzingTeachingDna}
                        >
                          {analyzingTeachingDna ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                          Build Master Teaching Blueprint
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-9"
                          onClick={() => analyzeTeachingDna(true)}
                          disabled={!canBuildMasterBlueprint || analyzingTeachingDna}
                        >
                          Re-analyze Blueprint
                        </Button>
                      </div>
                    </div>

                    {teachingDnaSummary && (
                      <div className="rounded-md border border-border bg-card/50 px-3 py-2 text-[11px] text-muted-foreground space-y-1">
                        <p className="text-foreground font-medium">Master Teaching Blueprint Summary</p>
                        <p>Source: {teachingDnaSummary.source_file || 'N/A'}</p>
                        <p>
                          Expert courses: {teachingDnaSummary.expert_courses_count || selectedExpertCoursesCount}
                          {' | '}Slides analyzed: {teachingDnaSummary.total_slides_analyzed || 0}
                          {' | '}Instructor notes analyzed: {teachingDnaSummary.total_instructor_notes_analyzed || 0}
                        </p>
                        <p>Modules detected: {teachingDnaSummary.modules_detected || 0} | Role types: {teachingDnaSummary.role_types || 0}</p>
                        <p>Lab patterns: {teachingDnaSummary.lab_patterns || 0} | Troubleshooting patterns: {teachingDnaSummary.troubleshooting_patterns || 0}</p>
                        <p>Assessment patterns: {teachingDnaSummary.assessment_patterns || 0} | Visual patterns: {teachingDnaSummary.visual_patterns || 0}</p>
                        <p>Transitions: {teachingDnaSummary.transition_patterns || 0}</p>
                        <p>
                          Pattern confidence - Lab: {teachingDnaSummary.pattern_confidence?.lab_patterns ?? 0}
                          {' | '}Troubleshooting: {teachingDnaSummary.pattern_confidence?.troubleshooting_patterns ?? 0}
                          {' | '}Assessment: {teachingDnaSummary.pattern_confidence?.assessment_patterns ?? 0}
                        </p>
                        <p>
                          Pattern confidence - Visual: {teachingDnaSummary.pattern_confidence?.visual_patterns ?? 0}
                          {' | '}Transitions: {teachingDnaSummary.pattern_confidence?.transition_patterns ?? 0}
                        </p>
                        {(teachingDnaSummary.selection_warnings || []).map((w, idx) => (
                          <p key={`${w}-${idx}`} className="text-amber-300">{w}</p>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-3 rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Use PowerPoint Knowledge Base</h3>
              <p className="text-xs text-muted-foreground">
                Search previously uploaded training presentations and use relevant slides as technical,
                instructional, and visual references.
              </p>
            </div>
            <Switch
              checked={settings.use_powerpoint_knowledge_base}
              onCheckedChange={(v) => setSettings(prev => ({
                ...prev,
                use_powerpoint_knowledge_base: v,
                use_powerpoint_references: v,
              }))}
            />
          </div>

          {settings.use_powerpoint_knowledge_base && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
                {([
                  ['use_powerpoint_references', 'Use relevant PowerPoint references'],
                  ['use_manufacturer_approved_only', 'Use manufacturer-approved files only'],
                  ['use_powerpoint_technical_support', 'Use PowerPoint content for technical support'],
                  ['use_powerpoint_layout_inspiration', 'Use PowerPoint files for visual and layout inspiration'],
                  ['use_powerpoint_terminology', 'Use PowerPoint terminology'],
                  ['use_powerpoint_exercises_assessments', 'Use PowerPoint exercises and assessments'],
                  ['use_arabic_formatting_examples', 'Use Arabic PowerPoint formatting examples'],
                ] as const).map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between rounded-lg border border-border bg-card/40 px-3 py-2">
                    <Label className="text-xs cursor-pointer" htmlFor={key}>{label}</Label>
                    <Switch
                      id={key}
                      checked={Boolean(settings[key])}
                      onCheckedChange={v => set(key, v)}
                    />
                  </div>
                ))}
              </div>

              <div className="space-y-1 pt-2">
                <Label className="text-xs text-muted-foreground">Reference Strictness</Label>
                <Select value={settings.powerpoint_reference_strictness} onValueChange={v => set('powerpoint_reference_strictness', v)}>
                  <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PPT_REFERENCE_STRICTNESS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </>
          )}
        </div>

        {/* Toggles */}
        <div className="space-y-3">
          <h3 className="text-xs font-mono font-bold text-muted-foreground/70 uppercase tracking-widest">Include</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {([
              ['include_notes',    'Speaker Notes'],
              ['include_quizzes',  'Knowledge Checks'],
              ['include_practical','Practical Exercises'],
              ['include_exam',     'Final Examination'],
              ['include_student_workbook', 'Student Workbook'],
              ['include_answer_key', 'Answer Key'],
            ] as const).map(([key, label]) => (
              <div key={key}
                className="flex items-center justify-between rounded-lg border border-border bg-card/40 px-3 py-2.5">
                <Label className="text-xs cursor-pointer" htmlFor={key}>{label}</Label>
                <Switch id={key}
                  checked={settings[key] as boolean}
                  onCheckedChange={v => set(key, v)} />
              </div>
            ))}
            <div className="flex items-center justify-between rounded-lg border border-border bg-card/40 px-3 py-2.5">
              <Label className="text-xs cursor-pointer" htmlFor="include_instructor_notes">Include Instructor Notes</Label>
              <Switch id="include_instructor_notes"
                checked={settings.include_instructor_notes}
                onCheckedChange={v => setSettings(prev => ({ ...prev, include_instructor_notes: v, include_notes: v }))} />
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Generate Course Using</Label>
          <Select value={providerId} onValueChange={setProviderId}>
            <SelectTrigger className="h-9 text-sm" data-testid="select-training-provider"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Auto</SelectItem>
              {(aiProviders || []).filter(p => p.id !== 'mock' && p.is_configured).map(p => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex justify-between items-center pt-2">
          <Button variant="ghost" onClick={() => setStep('upload')} className="gap-1 text-sm">
            <ChevronLeft className="h-4 w-4" /> Back
          </Button>
          <Button onClick={startGeneration}
            disabled={!settings.course_title.trim()}
            className="gap-2 font-semibold px-6">
            <Sparkles className="h-4 w-4" />
            Generate Course
          </Button>
        </div>
      </div>
    );
  };

  // ── Step: Generate ────────────────────────────────────────────────────────

  // 12-stage pipeline definitions
  const PIPELINE_STEPS = [
    { step: 1, name: 'Read Manual',                        desc: 'Validate manual pages and input readiness' },
    { step: 2, name: 'Extract Knowledge',                  desc: 'Extract searchable technical content from the manual' },
    { step: 3, name: 'Search Knowledge Base',              desc: 'Build indexed knowledge chunks and references' },
    { step: 4, name: 'Search PowerPoint Library',          desc: 'Retrieve relevant PowerPoint reference slides' },
    { step: 5, name: 'Build Course Blueprint',             desc: 'Create the technical knowledge map and blueprint' },
    { step: 6, name: 'Build Technical Modules',            desc: 'Generate course module structure and sequencing' },
    { step: 7, name: 'Enhance Training Materials',         desc: 'Apply selected instructional enhancement options' },
    { step: 8, name: 'Generate Diagrams',                  desc: 'Plan diagrams and visual placeholders with traceability' },
    { step: 9, name: 'Generate Assessments',               desc: 'Build assessments and answer keys' },
    { step: 10, name: 'Assemble Course',                   desc: 'Assemble slides, references, and source mapping' },
    { step: 11, name: 'AI Training Director',              desc: 'Supervise engines, assign missing work, and run iterative review cycles' },
    { step: 12, name: 'Export',                            desc: 'Finalize export-ready course package' },
  ];

  const StepIcon = ({ sp }: { sp: StepProgress | undefined; step: number }) => {
    if (!sp) return <div className="h-5 w-5 rounded-full border border-border bg-background shrink-0" />;
    if (sp.status === 'running') return <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />;
    if (sp.status === 'done')    return <Check className="h-5 w-5 text-emerald-400 shrink-0" />;
    if (sp.status === 'warning') return <AlertCircle className="h-5 w-5 text-amber-400 shrink-0" />;
    if (sp.status === 'error')   return <AlertCircle className="h-5 w-5 text-destructive shrink-0" />;
    return <div className="h-5 w-5 rounded-full border border-border bg-background shrink-0" />;
  };

  const GenerateStep = () => {
    const qualityStepData: any = stepProgress.find(s => s.step === 11)?.data;
    const qualityDashboard = qualityStepData?.quality_dashboard;
    const trainingDirector = qualityStepData?.ai_training_director;
    const directorDashboard = trainingDirector?.dashboard || qualityWarnings?.training_director_dashboard;
    const qualityScores: Array<[string, number]> = qualityDashboard?.scores
      ? Object.entries(qualityDashboard.scores as Record<string, number>)
      : [];

    return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-foreground mb-1">
            {step === 'done' ? 'Course Generated ✓' : 'Generating Course…'}
          </h2>
          <p className="text-sm text-muted-foreground font-mono">{genStatus}</p>
        </div>
        <div className="flex items-center gap-2">
          {stepProgress.length > 0 && (
            <Button variant="ghost" size="sm" className="text-[10px] h-7 px-2 font-mono"
              onClick={() => setShowDebug(v => !v)}>
              {showDebug ? 'Hide' : 'Debug'}
            </Button>
          )}
          {generating && <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />}
          {step === 'done' && <Check className="h-5 w-5 text-emerald-400 shrink-0" />}
        </div>
      </div>

      {/* Error */}
      {genError && (
        <Alert className="border-destructive/30 bg-destructive/5">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <AlertDescription className="text-xs space-y-1">
            <div className="font-semibold text-destructive">Generation failed</div>
            <div className="text-muted-foreground break-words whitespace-pre-wrap font-mono">{genError}</div>
            {(() => {
              const failedStep = stepProgress.find(s => s.status === 'error' && s.step === 11);
              const debug = failedStep?.data?.debug;
              const plan: string[] = debug?.suggested_action_plan || [];
              if (!plan.length) return null;
              return (
                <div className="pt-2 border-t border-destructive/20 space-y-1">
                  <div className="text-[11px] font-semibold text-destructive/90">Suggested improvement plan</div>
                  {plan.map((p, i) => (
                    <div key={i} className="text-[10px] text-muted-foreground">- {p}</div>
                  ))}
                </div>
              );
            })()}
            <div className="pt-1 flex gap-2">
              <Button variant="outline" size="sm" className="text-xs h-7"
                onClick={() => { setStep('configure'); setGenError(null); setStepProgress([]); }}>
                ← Back to Settings
              </Button>
              <Button variant="outline" size="sm" className="text-xs h-7"
                onClick={() => { setGenError(null); startGeneration(); }}>
                Retry
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}

      {exportFailure && (
        <Alert className="border-destructive/30 bg-destructive/5">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <AlertDescription className="text-xs space-y-1">
            <div className="font-semibold text-destructive">Export verification failed</div>
            <div className="text-muted-foreground break-words whitespace-pre-wrap font-mono">{exportFailure}</div>
          </AlertDescription>
        </Alert>
      )}

      {/* Quality gate warnings */}
      {pipelineWarnings.length > 0 && (
        <Alert className="border-amber-500/30 bg-amber-500/5">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" />
          <AlertDescription className="text-xs space-y-1">
            <div className="font-semibold text-amber-400">Optional Enhancement Warnings</div>
            {pipelineWarnings.map((w, i) => (
              <div key={i} className="text-muted-foreground">{w}</div>
            ))}
            <div className="text-[10px] text-muted-foreground/70">
              Core manual-based generation continued successfully. Re-running generation with the same configuration reuses cache and retries failed optional stages.
            </div>
          </AlertDescription>
        </Alert>
      )}

      {qualityWarnings && qualityWarnings.errors.length > 0 && (
        <Alert className="border-amber-500/30 bg-amber-500/5">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" />
          <AlertDescription className="text-xs space-y-2">
            <div className="font-semibold text-amber-400">⚠ AI Training Director — Quality Advisory</div>
            {qualityWarnings.errors.map((e, i) => (
              <div key={i} className="text-amber-300/80 font-mono">{e}</div>
            ))}
            {qualityWarnings.warnings.length > 0 && (
              <div className="space-y-1 pt-1 border-t border-amber-500/20">
                {qualityWarnings.warnings.map((w, i) => (
                  <div key={i} className="text-muted-foreground font-mono text-[10px]">⚠ {w}</div>
                ))}
              </div>
            )}
            <div className="text-[10px] text-muted-foreground pt-1">
              Safety/radiation content: <span className="text-amber-400 font-semibold">{qualityWarnings.safety_pct}%</span> of slides.
              The AI Training Director performed supervised review cycles and assigned corrective work automatically.
              If quality remains below threshold, regenerate with richer depth or stricter reference settings.
            </div>
          </AlertDescription>
        </Alert>
      )}

      {directorDashboard && (
        <div className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-mono text-sky-300 uppercase tracking-wider">AI Training Director Dashboard</p>
              <p className="text-sm text-foreground font-semibold">
                Overall Completion: {directorDashboard.overall_completion}%
              </p>
            </div>
            <Badge variant="outline" className="border-sky-500/40 text-sky-300">
              Supervised Engines: {(directorDashboard.supervised_engines || []).length}
            </Badge>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {[
              ['Educational Completeness', directorDashboard.educational_completeness],
              ['Technical Completeness', directorDashboard.technical_completeness],
              ['Visual Completeness', directorDashboard.visual_completeness],
              ['Laboratory Coverage', directorDashboard.laboratory_coverage],
              ['Assessment Coverage', directorDashboard.assessment_coverage],
              ['Knowledge-base Utilization', directorDashboard.knowledge_base_utilization],
              ['PowerPoint Utilization', directorDashboard.powerpoint_utilization],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-lg border border-border bg-card/50 px-3 py-2 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{String(k)}</span>
                <span className="text-xs font-mono font-semibold text-sky-300">{Number(v || 0)}</span>
              </div>
            ))}
          </div>

          {(directorDashboard.remaining_tasks || []).length > 0 && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-1">
              <p className="text-[11px] font-semibold text-amber-300">Remaining Tasks</p>
              {(directorDashboard.remaining_tasks || []).slice(0, 8).map((task: string, i: number) => (
                <div key={i} className="text-[10px] text-muted-foreground font-mono">- {task}</div>
              ))}
            </div>
          )}

          {directorDashboard.human_benchmark && (
            <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-3 space-y-1">
              <p className="text-[11px] font-semibold text-sky-300">
                Human Benchmark: {directorDashboard.human_benchmark.passes ? 'Matched/Exceeded' : 'Below Benchmark'}
              </p>
              {(directorDashboard.human_benchmark.designer_principles || []).slice(0, 4).map((principle: string, i: number) => (
                <div key={`p-${i}`} className="text-[10px] text-sky-200/90 font-mono">- {principle}</div>
              ))}
              {!directorDashboard.human_benchmark.passes &&
                (directorDashboard.human_benchmark.missing_areas || []).slice(0, 6).map((area: string, i: number) => (
                  <div key={i} className="text-[10px] text-muted-foreground font-mono">- {area}</div>
                ))}
            </div>
          )}
        </div>
      )}

      {qualityDashboard && (
        <div id="quality-report" className="rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-mono text-primary/80 uppercase tracking-wider">AI Instructor Review Dashboard</p>
              <p className="text-sm text-foreground font-semibold">
                Overall Score: {qualityDashboard.overall_score}/100 · Grade: {qualityDashboard.grade}
              </p>
            </div>
            <Badge variant="outline" className={qualityDashboard.passes_threshold ? 'border-emerald-500/40 text-emerald-400' : 'border-amber-500/40 text-amber-400'}>
              {qualityDashboard.passes_threshold ? 'Quality Pass' : 'Quality Advisory'}
            </Badge>
          </div>

          {qualityScores.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {qualityScores.map(([k, v]) => (
                <div key={k} className="rounded-lg border border-border bg-card/50 px-3 py-2 flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{k.replace(/_/g, ' ')}</span>
                  <span className={`text-xs font-mono font-semibold ${v >= (qualityDashboard.min_threshold || 72) ? 'text-emerald-400' : 'text-amber-400'}`}>{v}</span>
                </div>
              ))}
            </div>
          )}

          {(qualityDashboard.weak_categories?.length || 0) > 0 && (
            <div className="text-xs text-amber-300/80 font-mono">
              Weak Categories: {qualityDashboard.weak_categories.join(', ')}
            </div>
          )}
        </div>
      )}

      {/* 12-stage pipeline tracker */}
      <div className="rounded-xl border border-border bg-card/40 divide-y divide-border overflow-hidden">
        {PIPELINE_STEPS.map(({ step: stepNum, name, desc }) => {
          const sp = stepProgress.find(p => p.step === stepNum);
          const isActive  = sp?.status === 'running';
          const isDone    = sp?.status === 'done';
          const isError   = sp?.status === 'error';
          const isWarning = sp?.status === 'warning';
          const isPending = !sp;
          return (
            <div key={stepNum}
              className={`px-4 py-3 flex items-start gap-3 transition-colors
                ${isActive  ? 'bg-primary/5' :
                  isDone    ? 'bg-emerald-500/3' :
                  isError   ? 'bg-destructive/5' :
                  isWarning ? 'bg-amber-500/5' : ''}`}>
              <div className="flex flex-col items-center gap-1 pt-0.5 w-5 shrink-0">
                <StepIcon sp={sp} step={stepNum} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold
                    ${isActive  ? 'text-primary' :
                      isDone    ? 'text-emerald-400' :
                      isError   ? 'text-destructive' :
                      isWarning ? 'text-amber-400' :
                                  'text-muted-foreground'}`}>
                    Step {stepNum}: {name}
                  </span>
                  {isDone && sp?.data && (
                    <span className="text-[10px] font-mono text-muted-foreground/60">
                      {stepNum === 1 && `${sp.data.pages || 0} pages`}
                      {stepNum === 2 && `${sp.data.content_pages || 0} content pages · ${Math.round((sp.data.total_chars || 0) / 1000)}K chars`}
                      {stepNum === 3 && `${sp.data.sections_detected || 0} sections · ${sp.data.chunks || 0} chunks`}
                      {stepNum === 4 && `${sp.data.figures_detected || 0} figures · ${sp.data.tables_detected || 0} tables`}
                      {stepNum === 5 && `${sp.data.topics || 0} knowledge topics`}
                      {stepNum === 6 && `${sp.data.sections || 0} modules · ${sp.data.source || 'ai'}`}
                      {stepNum === 7 && `${sp.data.selected_options?.length || 0} enhancement options`}
                      {stepNum === 8 && `${sp.data.visuals_generated || 0} visuals · ${sp.data.placeholders || 0} placeholders`}
                      {stepNum === 9 && `${sp.data.questions || 0} questions`}
                      {stepNum === 10 && `${sp.data.slides_saved || 0} slides · ${sp.data.citation_summary?.pages_cited_count || 0} cited pages`}
                      {stepNum === 11 && `${sp.data.quality_dashboard?.overall_score || 0}/100 instructor score`}
                      {stepNum === 12 && `${sp.data.slides_saved || 0} slides · ${sp.data.pptx_size_kb || 0}KB PPTX`}
                    </span>
                  )}
                </div>
                {isActive && (
                  <p className="text-[11px] text-muted-foreground mt-0.5 animate-pulse">{desc}</p>
                )}
                {isPending && (
                  <p className="text-[11px] text-muted-foreground/40 mt-0.5">{desc}</p>
                )}
                {/* Debug data panel */}
                {showDebug && isDone && sp?.data && (
                  <pre className="mt-2 text-[10px] font-mono text-muted-foreground/70 bg-background/60 rounded p-2 overflow-x-auto max-h-40">
                    {JSON.stringify(sp.data, null, 2)}
                  </pre>
                )}
                {isError && sp?.data?.error && (
                  <p className="text-[11px] text-destructive mt-1 font-mono break-words">{sp.data.error}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Live slide list (appears once slides start arriving from Step 7) */}
      {slides.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-mono text-muted-foreground/60 uppercase tracking-wider">
              Slides — {slides.length} saved
            </p>
          </div>
          <div className="space-y-1 max-h-[320px] overflow-y-auto rounded-lg border border-border p-2">
            {slides.map((s, i) => (
              <div key={i}
                className="rounded-lg border bg-card/60 p-2.5 flex items-center gap-3 animate-in fade-in slide-in-from-bottom-1">
                <span className="text-[10px] font-mono text-muted-foreground w-5 shrink-0 text-right">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <Badge variant="outline"
                  className={`text-[9px] px-1.5 py-0 border shrink-0 ${SLIDE_TYPE_COLORS[s.type] || SLIDE_TYPE_COLORS.content}`}>
                  {s.type}
                </Badge>
                <p className="text-xs text-foreground truncate flex-1">{s.title}</p>
                {s.source_pages?.length > 0 && (
                  <span className="text-[10px] text-primary/50 shrink-0 font-mono">p.{s.source_pages[0]}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Success actions */}
      {step === 'done' && finalProjectId && exportVerified && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Check className="h-4 w-4 text-emerald-400" />
            <p className="text-sm font-semibold text-emerald-400">
              Course Generated Successfully
            </p>
          </div>
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs space-y-1">
            <div><span className="text-muted-foreground">Status:</span> <span className="font-semibold text-emerald-300">{draftStatus}</span></div>
            <div><span className="text-muted-foreground">Quality Score:</span> <span className="font-semibold text-amber-300">{finalQualityScore}/100</span></div>
          </div>
          <div className="flex gap-3">
            <Link href={`/training/project/${finalProjectId}`} className="flex-1">
              <Button className="w-full gap-2 font-semibold">
                <FolderOpen className="h-4 w-4" />
                Open Project
              </Button>
            </Link>
            <a href={exportInfo?.artifacts?.pptx?.download_url ? `${API}${exportInfo.artifacts.pptx.download_url}` : `${API}/api/training/export/pptx/${finalProjectId}?version=instructor`} download>
              <Button variant="outline" className="gap-2">
                <Download className="h-4 w-4" />
                Download Draft
              </Button>
            </a>
            <a href={exportInfo?.artifacts?.zip?.download_url ? `${API}${exportInfo.artifacts.zip.download_url}` : `${API}/api/training/export/zip/${finalProjectId}`} download>
              <Button variant="outline" className="gap-2">
                <Download className="h-4 w-4" />
                ZIP
              </Button>
            </a>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            <Button
              variant="secondary"
              className="text-xs"
              onClick={() => {
                const el = document.getElementById('quality-report');
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }}
            >
              View Quality Report
            </Button>
            <Button
              variant="secondary"
              className="text-xs"
              onClick={() => navigate(`/training/project/${finalProjectId}`)}
            >
              Improve Course
            </Button>
            <Button
              variant="secondary"
              className="text-xs"
              onClick={() => navigate(`/training/project/${finalProjectId}`)}
            >
              Improve Selected Modules
            </Button>
            <Button
              variant="secondary"
              className="text-xs"
              onClick={() => {
                toast({
                  title: 'Regenerate Selected Slide',
                  description: 'Open the project and use per-slide controls to regenerate the selected slide.',
                });
              }}
            >
              Regenerate Selected Slide
            </Button>
            <Button
              variant="secondary"
              className="text-xs"
              onClick={() => {
                const qualityStepData: any = stepProgress.find(s => s.step === 11)?.data || {};
                const payload = {
                  draft_status: draftStatus,
                  quality_dashboard: qualityStepData?.quality_dashboard || null,
                  ai_training_director: qualityStepData?.ai_training_director || null,
                  quality_warning: qualityWarnings || null,
                };
                const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `quality-report-${finalProjectId}.json`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              Export Quality Report
            </Button>
          </div>
        </div>
      )}
    </div>
  );
  };

  // ── Main render ────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-auto bg-background">
      <div className="border-b border-border bg-card/40 px-6 py-4 shrink-0">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/20">
              <BookMarked className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-base font-bold text-foreground tracking-tight">New Training Course</h1>
              <p className="text-xs text-muted-foreground">
                {uploadResult ? uploadResult.filename : 'Upload a manual to begin'}
              </p>
            </div>
          </div>
          <StepIndicator />
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto px-6 py-8">
          {step === 'upload'    && <UploadStep />}
          {step === 'configure' && <ConfigureStep />}
          {(step === 'generate' || step === 'done') && <GenerateStep />}
        </div>
      </div>
    </div>
  );
}
