import { useEffect, useRef, useState } from 'react';
import {
  Loader2, Plus, Trash2, Sparkles, RefreshCw, Save, FileDown,
  Download, Upload, Image as ImageIcon, X,
  FolderOpen, AlertTriangle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

interface DocRef { reference_number: string; title: string }
interface Attendee {
  name: string;
  exam_percentage: number | null;
  certificate_awarded: boolean;
  certificate_serial: string;
  comments: string;
}

interface FormData {
  report_title: string;
  training_level: string;
  course_name: string;
  start_date: string;
  end_date: string;
  instructor: string;
  project_code: string;
  system_type: string;
  system_serial_no: string;
  site_of_operation: string;
  customer: string;
  contract_reference: string;
  delivery_language: string;
  documentation_language: string;
  classroom_location: string;
  practical_location: string;
  total_training_days: number | null;
  classroom_days: number | null;
  practical_days: number | null;
  instructor_travel_days: number | null;
  output_language: 'en' | 'ar';

  attendees_total: number | null;
  attendees_pass: number | null;
  attendees_fail: number | null;
  attendees_certified: number | null;
  previous_experience: string;
  computer_skills: string;
  language_ability: string;
  trainee_background: string;
  attendees: Attendee[];

  doc_refs: DocRef[];

  training_purpose: string;
  course_objectives: string;
  training_scope: string;
  schedule_summary: string;
  subjects_covered: string;
  practical_activities: string;
  assessment_method: string;
  written_exam_completed: boolean;
  practical_exam_completed: boolean;
  pass_percentage: number | null;
  certification_requirements: string;
  instructor_evaluation: string;
  instructor_bio: string;
  additional_notes: string;
  qa_issues: string;
  technical_issues: string;
  action_taken: string;
  responsible_party: string;
  follow_up_plan: string;

  site_image_id: string | null;
}

const emptyForm = (): FormData => ({
  report_title: '', training_level: '', course_name: '', start_date: '', end_date: '',
  instructor: '', project_code: '', system_type: '', system_serial_no: '', site_of_operation: '',
  customer: '', contract_reference: '', delivery_language: '', documentation_language: '',
  classroom_location: '', practical_location: '', total_training_days: null, classroom_days: null,
  practical_days: null, instructor_travel_days: null, output_language: 'en',
  attendees_total: null, attendees_pass: null, attendees_fail: null, attendees_certified: null,
  previous_experience: '', computer_skills: '', language_ability: '', trainee_background: '',
  attendees: [{ name: '', exam_percentage: null, certificate_awarded: false, certificate_serial: '', comments: '' }],
  doc_refs: [{ reference_number: '', title: '' }],
  training_purpose: '', course_objectives: '', training_scope: '', schedule_summary: '',
  subjects_covered: '', practical_activities: '', assessment_method: '',
  written_exam_completed: false, practical_exam_completed: false, pass_percentage: null,
  certification_requirements: '', instructor_evaluation: '', instructor_bio: '',
  additional_notes: '', qa_issues: '', technical_issues: '', action_taken: '', responsible_party: '',
  follow_up_plan: '', site_image_id: null,
});

const SECTION_LABELS: Record<string, string> = {
  reference_documents: 'Reference Documents',
  background: 'Background',
  instructor: 'Instructor',
  delivery_language: 'Training Delivery Language',
  training_location: 'Training Location',
  students: 'Students',
  schedule: 'Schedule of Training',
  completion_certification: 'Course Completion and Certification',
  additional_notes: 'Additional Notes and QA Issues',
  follow_up_plan: 'After Training Follow-up Plan',
};
const SECTION_KEYS = Object.keys(SECTION_LABELS);

interface ReportSummary {
  id: string; template: string; title: string; customer: string; system_type: string;
  instructor: string; start_date: string; end_date: string; status: string;
  output_language: string; has_docx: boolean; has_pdf: boolean;
  created_at: string | null; updated_at: string | null;
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground mb-2 block">
        {label} {required && <span className="text-emerald-500">*</span>}
      </label>
      {children}
    </div>
  );
}

export default function TrainingCourseReportPanel() {
  const [form, setForm] = useState<FormData>(emptyForm());
  const [narrative, setNarrative] = useState<Record<string, string>>({});
  const [reportId, setReportId] = useState<string | null>(null);
  const [status, setStatus] = useState<'draft' | 'final'>('draft');

  const [generatingNarrative, setGeneratingNarrative] = useState(false);
  const [regeneratingSection, setRegeneratingSection] = useState<string | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);
  const [generatingFinal, setGeneratingFinal] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [importingAttendees, setImportingAttendees] = useState(false);

  const [errors, setErrors] = useState<string[]>([]);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [history, setHistory] = useState<ReportSummary[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<ReportSummary | null>(null);

  const csvInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const loadHistory = async () => {
    try {
      const resp = await fetch(`${API}/api/training-reports`, { credentials: 'include' });
      if (resp.ok) setHistory(await resp.json());
    } catch (e) { console.error(e); }
  };

  useEffect(() => { loadHistory(); }, []);

  const update = <K extends keyof FormData>(key: K, value: FormData[K]) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const updateAttendee = (i: number, field: keyof Attendee, value: any) => {
    setForm(prev => ({
      ...prev,
      attendees: prev.attendees.map((a, idx) => idx === i ? { ...a, [field]: value } : a),
    }));
  };
  const addAttendee = () => setForm(prev => ({
    ...prev,
    attendees: [...prev.attendees, { name: '', exam_percentage: null, certificate_awarded: false, certificate_serial: '', comments: '' }],
  }));
  const removeAttendee = (i: number) => setForm(prev => ({ ...prev, attendees: prev.attendees.filter((_, idx) => idx !== i) }));

  const updateDocRef = (i: number, field: keyof DocRef, value: string) => {
    setForm(prev => ({ ...prev, doc_refs: prev.doc_refs.map((r, idx) => idx === i ? { ...r, [field]: value } : r) }));
  };
  const addDocRef = () => setForm(prev => ({ ...prev, doc_refs: [...prev.doc_refs, { reference_number: '', title: '' }] }));
  const removeDocRef = (i: number) => setForm(prev => ({ ...prev, doc_refs: prev.doc_refs.filter((_, idx) => idx !== i) }));

  // Attendance totals auto-calculated from the attendee table, but the
  // operator's explicit override (if typed) always wins.
  const namedAttendees = form.attendees.filter(a => a.name.trim());
  const computedTotal = form.attendees_total ?? namedAttendees.length;
  const computedCertified = form.attendees_certified ?? namedAttendees.filter(a => a.certificate_awarded).length;

  const handleImportAttendees = async (file: File) => {
    setImportingAttendees(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const resp = await fetch(`${API}/api/training-reports/import-attendees`, { method: 'POST', body: fd, credentials: 'include' });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      const imported: Attendee[] = (data.attendees || []).map((a: any) => ({
        name: a.name || '', exam_percentage: a.exam_percentage ?? null,
        certificate_awarded: !!a.certificate_awarded, certificate_serial: a.certificate_serial || '',
        comments: a.comments || '',
      }));
      if (imported.length) setForm(prev => ({ ...prev, attendees: imported }));
      setNotice({ type: 'success', text: `Imported ${imported.length} attendee(s).` });
    } catch (e) {
      console.error(e);
      setNotice({ type: 'error', text: 'Could not import attendees from that file.' });
    } finally {
      setImportingAttendees(false);
    }
  };

  const handleUploadImage = async (file: File) => {
    setUploadingImage(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const resp = await fetch(`${API}/api/training-reports/upload-image`, { method: 'POST', body: fd, credentials: 'include' });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      update('site_image_id', data.image_id);
      setNotice({ type: 'success', text: 'Site image uploaded.' });
    } catch (e) {
      console.error(e);
      setNotice({ type: 'error', text: 'Could not upload that image.' });
    } finally {
      setUploadingImage(false);
    }
  };

  const generateNarrative = async (sections?: string[]) => {
    if (sections) setRegeneratingSection(sections[0]); else setGeneratingNarrative(true);
    setNotice(null);
    try {
      const resp = await fetch(`${API}/api/training-reports/narrative/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ form_data: form, sections: sections || null }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setNarrative(prev => ({ ...prev, ...data.sections }));
    } catch (e) {
      console.error(e);
      setNotice({ type: 'error', text: 'Narrative generation failed. Check required fields and try again.' });
    } finally {
      setGeneratingNarrative(false);
      setRegeneratingSection(null);
    }
  };

  const save = async (targetStatus: 'draft' | 'final') => {
    const setBusy = targetStatus === 'final' ? setGeneratingFinal : setSavingDraft;
    setBusy(true);
    setErrors([]);
    setNotice(null);
    try {
      const method = reportId ? 'PUT' : 'POST';
      const url = reportId ? `${API}/api/training-reports/${reportId}` : `${API}/api/training-reports`;
      const resp = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ template: 'standard_completion', status: targetStatus, form_data: form, narrative }),
      });
      if (resp.status === 422) {
        const data = await resp.json();
        setErrors(data.detail?.errors || ['Please complete the required fields.']);
        return;
      }
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setReportId(data.id);
      setStatus(data.status);
      setNotice({
        type: 'success',
        text: targetStatus === 'final'
          ? (data.has_pdf ? 'Final report generated — DOCX and PDF are ready.' : 'Final report generated (DOCX ready; PDF export was unavailable).')
          : 'Draft saved.',
      });
      loadHistory();
    } catch (e) {
      console.error(e);
      setNotice({ type: 'error', text: 'Could not save the report. Please try again.' });
    } finally {
      setBusy(false);
    }
  };

  const openReport = async (id: string) => {
    const resp = await fetch(`${API}/api/training-reports/${id}`, { credentials: 'include' });
    if (!resp.ok) return;
    const data = await resp.json();
    setForm({ ...emptyForm(), ...data.form_data });
    setNarrative(data.narrative || {});
    setReportId(data.id);
    setStatus(data.status);
    setNotice({ type: 'success', text: `Loaded "${data.title}" for editing.` });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const duplicateReport = async (id: string) => {
    const resp = await fetch(`${API}/api/training-reports/${id}/duplicate`, { method: 'POST', credentials: 'include' });
    if (resp.ok) loadHistory();
  };

  const deleteReport = async (id: string) => {
    const resp = await fetch(`${API}/api/training-reports/${id}`, { method: 'DELETE', credentials: 'include' });
    if (resp.ok) {
      if (reportId === id) { setReportId(null); setStatus('draft'); }
      loadHistory();
    }
    setDeleteTarget(null);
  };

  const downloadFile = async (id: string, kind: 'docx' | 'pdf') => {
    const resp = await fetch(`${API}/api/training-reports/${id}/download/${kind}`, { credentials: 'include' });
    if (!resp.ok) {
      setNotice({ type: 'error', text: `${kind.toUpperCase()} is not available for this report.` });
      return;
    }
    const blob = await resp.blob();
    const disposition = resp.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
    const filename = match ? decodeURIComponent(match[1]) : `Training_Report.${kind}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const newReport = () => {
    setForm(emptyForm());
    setNarrative({});
    setReportId(null);
    setStatus('draft');
    setErrors([]);
    setNotice(null);
  };

  return (
    <div className="space-y-6">
      {reportId && (
        <div className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-2 text-xs font-mono">
          <span className="text-muted-foreground">
            Editing report <span className="text-foreground">{form.report_title || reportId}</span> — status: {' '}
            <Badge variant="outline" className={status === 'final' ? 'border-emerald-500/40 text-emerald-400' : 'border-border text-muted-foreground'}>
              {status}
            </Badge>
          </span>
          <Button type="button" variant="outline" size="sm" className="h-7" onClick={newReport}>New report</Button>
        </div>
      )}

      <Accordion type="multiple" defaultValue={['basic', 'attendance']} className="w-full">
        {/* A. Basic report information */}
        <AccordionItem value="basic">
          <AccordionTrigger>A. Basic Report Information</AccordionTrigger>
          <AccordionContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Report Title" required><Input className="bg-background" value={form.report_title} onChange={e => update('report_title', e.target.value)} /></Field>
              <Field label="Training Level / Course Name" required><Input className="bg-background" placeholder="e.g. P60 ZBX OP Course" value={form.training_level} onChange={e => update('training_level', e.target.value)} /></Field>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Field label="Start Date" required><Input type="date" className="bg-background" value={form.start_date} onChange={e => update('start_date', e.target.value)} /></Field>
              <Field label="End Date" required><Input type="date" className="bg-background" value={form.end_date} onChange={e => update('end_date', e.target.value)} /></Field>
              <Field label="Instructor(s)" required><Input className="bg-background" value={form.instructor} onChange={e => update('instructor', e.target.value)} /></Field>
              <Field label="Project Code"><Input className="bg-background" value={form.project_code} onChange={e => update('project_code', e.target.value)} /></Field>
              <Field label="System Type / Model" required><Input className="bg-background" value={form.system_type} onChange={e => update('system_type', e.target.value)} /></Field>
              <Field label="System Serial No."><Input className="bg-background" value={form.system_serial_no} onChange={e => update('system_serial_no', e.target.value)} /></Field>
              <Field label="Site of Operation" required><Input className="bg-background" value={form.site_of_operation} onChange={e => update('site_of_operation', e.target.value)} /></Field>
              <Field label="Customer" required><Input className="bg-background" value={form.customer} onChange={e => update('customer', e.target.value)} /></Field>
              <Field label="Contract Reference"><Input className="bg-background" value={form.contract_reference} onChange={e => update('contract_reference', e.target.value)} /></Field>
              <Field label="Training Delivery Language"><Input className="bg-background" value={form.delivery_language} onChange={e => update('delivery_language', e.target.value)} /></Field>
              <Field label="Documentation Language"><Input className="bg-background" value={form.documentation_language} onChange={e => update('documentation_language', e.target.value)} /></Field>
              <Field label="Output Language">
                <select className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm" value={form.output_language} onChange={e => update('output_language', e.target.value as 'en' | 'ar')}>
                  <option value="en">English</option>
                  <option value="ar">Arabic</option>
                </select>
              </Field>
              <Field label="Classroom Training Location"><Input className="bg-background" value={form.classroom_location} onChange={e => update('classroom_location', e.target.value)} /></Field>
              <Field label="Practical Training Location"><Input className="bg-background" value={form.practical_location} onChange={e => update('practical_location', e.target.value)} /></Field>
              <Field label="Total Training Days"><Input type="number" min={0} className="bg-background" value={form.total_training_days ?? ''} onChange={e => update('total_training_days', e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Classroom Days"><Input type="number" min={0} className="bg-background" value={form.classroom_days ?? ''} onChange={e => update('classroom_days', e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Practical Days"><Input type="number" min={0} className="bg-background" value={form.practical_days ?? ''} onChange={e => update('practical_days', e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Instructor Travel/Assignment Days"><Input type="number" min={0} className="bg-background" value={form.instructor_travel_days ?? ''} onChange={e => update('instructor_travel_days', e.target.value ? Number(e.target.value) : null)} /></Field>
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* B. Course attendance */}
        <AccordionItem value="attendance">
          <AccordionTrigger>B. Course Attendance</AccordionTrigger>
          <AccordionContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Field label="Total Attendees"><Input type="number" min={0} className="bg-background" placeholder={String(namedAttendees.length)} value={form.attendees_total ?? ''} onChange={e => update('attendees_total', e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Total Passed"><Input type="number" min={0} className="bg-background" value={form.attendees_pass ?? ''} onChange={e => update('attendees_pass', e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Total Failed"><Input type="number" min={0} className="bg-background" value={form.attendees_fail ?? ''} onChange={e => update('attendees_fail', e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Total Certified"><Input type="number" min={0} className="bg-background" placeholder={String(computedCertified)} value={form.attendees_certified ?? ''} onChange={e => update('attendees_certified', e.target.value ? Number(e.target.value) : null)} /></Field>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Field label="Previous Experience"><Input className="bg-background" placeholder="Yes / No / details" value={form.previous_experience} onChange={e => update('previous_experience', e.target.value)} /></Field>
              <Field label="Computer Skills Level"><Input className="bg-background" value={form.computer_skills} onChange={e => update('computer_skills', e.target.value)} /></Field>
              <Field label="English/Language Ability"><Input className="bg-background" value={form.language_ability} onChange={e => update('language_ability', e.target.value)} /></Field>
            </div>
            <Field label="General Trainee Background">
              <Textarea className="min-h-[70px] bg-background" value={form.trainee_background} onChange={e => update('trainee_background', e.target.value)} />
            </Field>

            <div className="flex items-center justify-between pt-2">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">
                Attendees ({namedAttendees.length}) — computed total {computedTotal}, certified {computedCertified}
              </span>
              <div className="flex gap-2">
                <input ref={csvInputRef} type="file" accept=".csv,.xlsx" className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleImportAttendees(f); e.target.value = ''; }} />
                <Button type="button" variant="outline" size="sm" className="h-7" disabled={importingAttendees} onClick={() => csvInputRef.current?.click()}>
                  {importingAttendees ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Upload className="h-3.5 w-3.5 mr-1" />} Import CSV/XLSX
                </Button>
                <Button type="button" variant="outline" size="sm" className="h-7" onClick={addAttendee}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add Attendee
                </Button>
              </div>
            </div>
            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
              {form.attendees.map((a, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 rounded-md border border-border/50 p-2">
                  <span className="w-6 text-xs text-muted-foreground text-center">{i + 1}</span>
                  <Input placeholder="Name" className="bg-background flex-1 min-w-[140px]" value={a.name} onChange={e => updateAttendee(i, 'name', e.target.value)} />
                  <Input type="number" min={0} max={100} placeholder="Exam %" className="bg-background w-24" value={a.exam_percentage ?? ''} onChange={e => updateAttendee(i, 'exam_percentage', e.target.value ? Number(e.target.value) : null)} />
                  <label className="flex items-center gap-1.5 text-xs shrink-0">
                    <Checkbox checked={a.certificate_awarded} onCheckedChange={v => updateAttendee(i, 'certificate_awarded', !!v)} /> Certified
                  </label>
                  <Input placeholder="Certificate Serial No." className="bg-background w-40" value={a.certificate_serial} onChange={e => updateAttendee(i, 'certificate_serial', e.target.value)} />
                  <Input placeholder="Comments" className="bg-background flex-1 min-w-[120px]" value={a.comments} onChange={e => updateAttendee(i, 'comments', e.target.value)} />
                  <Button type="button" variant="outline" size="icon" className="h-9 w-9 shrink-0" onClick={() => removeAttendee(i)} disabled={form.attendees.length <= 1}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* C. Reference documents */}
        <AccordionItem value="refs">
          <AccordionTrigger>C. Reference Documents</AccordionTrigger>
          <AccordionContent className="space-y-2">
            <div className="flex justify-end">
              <Button type="button" variant="outline" size="sm" className="h-7" onClick={addDocRef}><Plus className="h-3.5 w-3.5 mr-1" /> Add Row</Button>
            </div>
            {form.doc_refs.map((r, i) => (
              <div key={i} className="flex gap-2">
                <Input placeholder="Document Reference Number" className="bg-background" value={r.reference_number} onChange={e => updateDocRef(i, 'reference_number', e.target.value)} />
                <Input placeholder="Title" className="bg-background" value={r.title} onChange={e => updateDocRef(i, 'title', e.target.value)} />
                <Button type="button" variant="outline" size="icon" className="h-10 w-10 shrink-0" onClick={() => removeDocRef(i)} disabled={form.doc_refs.length <= 1}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </AccordionContent>
        </AccordionItem>

        {/* D. Training details */}
        <AccordionItem value="details">
          <AccordionTrigger>D. Training Details</AccordionTrigger>
          <AccordionContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Contract / Training Purpose"><Textarea className="min-h-[70px] bg-background" value={form.training_purpose} onChange={e => update('training_purpose', e.target.value)} /></Field>
              <Field label="Course Objectives"><Textarea className="min-h-[70px] bg-background" value={form.course_objectives} onChange={e => update('course_objectives', e.target.value)} /></Field>
              <Field label="Training Scope"><Textarea className="min-h-[70px] bg-background" value={form.training_scope} onChange={e => update('training_scope', e.target.value)} /></Field>
              <Field label="Training Schedule Summary"><Textarea className="min-h-[70px] bg-background" value={form.schedule_summary} onChange={e => update('schedule_summary', e.target.value)} /></Field>
              <Field label="Subjects / Modules Covered"><Textarea className="min-h-[70px] bg-background" value={form.subjects_covered} onChange={e => update('subjects_covered', e.target.value)} /></Field>
              <Field label="Practical Activities Performed"><Textarea className="min-h-[70px] bg-background" value={form.practical_activities} onChange={e => update('practical_activities', e.target.value)} /></Field>
              <Field label="Assessment Method"><Textarea className="min-h-[70px] bg-background" value={form.assessment_method} onChange={e => update('assessment_method', e.target.value)} /></Field>
              <Field label="Instructor Bio"><Textarea className="min-h-[70px] bg-background" value={form.instructor_bio} onChange={e => update('instructor_bio', e.target.value)} /></Field>
            </div>
            <div className="flex flex-wrap gap-6">
              <label className="flex items-center gap-2 text-sm"><Checkbox checked={form.written_exam_completed} onCheckedChange={v => update('written_exam_completed', !!v)} /> Written examination completed</label>
              <label className="flex items-center gap-2 text-sm"><Checkbox checked={form.practical_exam_completed} onCheckedChange={v => update('practical_exam_completed', !!v)} /> Practical examination completed</label>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Field label="Pass Percentage"><Input type="number" min={0} max={100} className="bg-background" value={form.pass_percentage ?? ''} onChange={e => update('pass_percentage', e.target.value ? Number(e.target.value) : null)} /></Field>
              <Field label="Certification Requirements"><Input className="bg-background" value={form.certification_requirements} onChange={e => update('certification_requirements', e.target.value)} /></Field>
              <Field label="Instructor Evaluation of Trainees"><Input className="bg-background" value={form.instructor_evaluation} onChange={e => update('instructor_evaluation', e.target.value)} /></Field>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Additional Notes"><Textarea className="min-h-[70px] bg-background" value={form.additional_notes} onChange={e => update('additional_notes', e.target.value)} /></Field>
              <Field label="QA Issues"><Textarea className="min-h-[70px] bg-background" value={form.qa_issues} onChange={e => update('qa_issues', e.target.value)} /></Field>
              <Field label="Technical Issues Discovered"><Textarea className="min-h-[70px] bg-background" value={form.technical_issues} onChange={e => update('technical_issues', e.target.value)} /></Field>
              <Field label="Action Taken"><Textarea className="min-h-[70px] bg-background" value={form.action_taken} onChange={e => update('action_taken', e.target.value)} /></Field>
              <Field label="Responsible Department / Person"><Input className="bg-background" value={form.responsible_party} onChange={e => update('responsible_party', e.target.value)} /></Field>
              <Field label="After-Training Follow-up Plan"><Textarea className="min-h-[70px] bg-background" value={form.follow_up_plan} onChange={e => update('follow_up_plan', e.target.value)} /></Field>
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* E. Media */}
        <AccordionItem value="media">
          <AccordionTrigger>E. Media</AccordionTrigger>
          <AccordionContent className="space-y-3">
            <input ref={imageInputRef} type="file" accept="image/*" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) handleUploadImage(f); e.target.value = ''; }} />
            <div className="flex items-center gap-3">
              <Button type="button" variant="outline" size="sm" disabled={uploadingImage} onClick={() => imageInputRef.current?.click()}>
                {uploadingImage ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <ImageIcon className="h-4 w-4 mr-2" />}
                Upload Site Image
              </Button>
              {form.site_image_id && (
                <Badge variant="secondary" className="gap-1">
                  Image attached
                  <div role="button" onClick={() => update('site_image_id', null)} className="hover:bg-destructive/20 rounded-full p-0.5"><X className="h-3 w-3" /></div>
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">Replaces the "Figure 1 site image" placeholder in the final document. Classroom/system images and a custom logo can be added in a later revision of this form.</p>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {errors.length > 0 && (
        <Card className="border-destructive/40 bg-destructive/5 p-4">
          <div className="flex items-center gap-2 text-destructive font-semibold text-sm mb-2">
            <AlertTriangle className="h-4 w-4" /> Please fix the following before generating the final report:
          </div>
          <ul className="list-disc list-inside text-sm text-destructive/90 space-y-0.5">
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </Card>
      )}

      {notice && (
        <div className={`text-sm rounded-md px-3 py-2 ${notice.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-destructive/10 text-destructive border border-destructive/30'}`}>
          {notice.text}
        </div>
      )}

      {/* Narrative */}
      <Card className="bg-card border-border p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-muted-foreground">AI-Generated Narrative</h3>
          <Button type="button" size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" disabled={generatingNarrative} onClick={() => generateNarrative()}>
            {generatingNarrative ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Sparkles className="h-4 w-4 mr-2" />}
            Generate Narrative
          </Button>
        </div>
        <div className="space-y-4">
          {SECTION_KEYS.map(key => (
            <div key={key}>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">{SECTION_LABELS[key]}</label>
                <Button type="button" variant="outline" size="sm" className="h-6 text-xs" disabled={regeneratingSection === key} onClick={() => generateNarrative([key])}>
                  {regeneratingSection === key ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <RefreshCw className="h-3 w-3 mr-1" />} Regenerate
                </Button>
              </div>
              <Textarea
                className="min-h-[70px] bg-background text-sm"
                value={narrative[key] || ''}
                onChange={e => setNarrative(prev => ({ ...prev, [key]: e.target.value }))}
                placeholder="Not generated yet — click Generate Narrative or Regenerate."
              />
            </div>
          ))}
        </div>
      </Card>

      {/* Actions */}
      <div className="flex flex-wrap gap-3 pt-2 border-t border-border/50">
        <Button type="button" variant="outline" disabled={savingDraft} onClick={() => save('draft')}>
          {savingDraft ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />} Save Draft
        </Button>
        <Button type="button" className="bg-emerald-600 hover:bg-emerald-700 text-white" disabled={generatingFinal} onClick={() => save('final')}>
          {generatingFinal ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FileDown className="h-4 w-4 mr-2" />} Generate Final Report
        </Button>
        {reportId && status === 'final' && (
          <>
            <Button type="button" variant="outline" onClick={() => downloadFile(reportId, 'docx')}><Download className="h-4 w-4 mr-2" /> Download DOCX</Button>
            <Button type="button" variant="outline" onClick={() => downloadFile(reportId, 'pdf')}><Download className="h-4 w-4 mr-2" /> Download PDF</Button>
          </>
        )}
      </div>

      {/* History */}
      <Card className="bg-card border-border p-5">
        <h3 className="font-semibold text-sm uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
          <FolderOpen className="h-4 w-4" /> Report History
        </h3>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">No training course reports saved yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b border-border/50">
                  <th className="py-2 pr-3">Title</th>
                  <th className="py-2 pr-3">Customer</th>
                  <th className="py-2 pr-3">System</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Updated</th>
                  <th className="py-2 pr-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {history.map(rec => (
                  <tr key={rec.id} className="border-b border-border/30">
                    <td className="py-2 pr-3">{rec.title || '(untitled)'}</td>
                    <td className="py-2 pr-3">{rec.customer}</td>
                    <td className="py-2 pr-3">{rec.system_type}</td>
                    <td className="py-2 pr-3">
                      <Badge variant="outline" className={rec.status === 'final' ? 'border-emerald-500/40 text-emerald-400' : 'border-border text-muted-foreground'}>{rec.status}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">{rec.updated_at ? new Date(rec.updated_at).toLocaleString() : ''}</td>
                    <td className="py-2 pr-3">
                      <div className="flex justify-end gap-1 flex-wrap">
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => openReport(rec.id)}>Open</Button>
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => duplicateReport(rec.id)}>Duplicate</Button>
                        {rec.has_docx && <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => downloadFile(rec.id, 'docx')}>DOCX</Button>}
                        {rec.has_pdf && <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => downloadFile(rec.id, 'pdf')}>PDF</Button>}
                        <Button variant="outline" size="sm" className="h-7 text-xs text-destructive hover:text-destructive" onClick={() => setDeleteTarget(rec)}>Delete</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <AlertDialog open={!!deleteTarget} onOpenChange={open => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this report?</AlertDialogTitle>
            <AlertDialogDescription>
              "{deleteTarget?.title}" and its generated DOCX/PDF files will be permanently deleted. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => deleteTarget && deleteReport(deleteTarget.id)}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
