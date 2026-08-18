import { useState, useEffect, useRef } from 'react';
import { Link } from 'wouter';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Database, Plus, Trash2, Edit3, Check, X, Download, Upload,
  Search, Languages, ChevronLeft, Loader2, BookOpen, AlertCircle,
  Brain, Share2, Users,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { TARGET_LANGUAGES as TARGET_LANG_OPTIONS } from '@/lib/languages';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── Types ─────────────────────────────────────────────────────────────────────

interface DictEntry {
  id: string;
  source_term: string;
  target_term: string;
  source_lang: string;
  target_lang: string;
  domain: string | null;
  notes: string | null;
  is_shared: boolean;
  created_at: string;
}

interface MemoryEntry {
  id: string;
  source_text: string;
  target_text: string;
  use_count: number;
  is_shared: boolean;
  updated_at: string;
}

// ── Language pair options ─────────────────────────────────────────────────────
// Derived from the shared language registry (src/lib/languages.ts) — every
// supported target gets an English↔{target} pair, both directions, so
// adding a language there is enough to add it here too.

const LANG_PAIRS = TARGET_LANG_OPTIONS.flatMap(l => [
  { source: 'en', target: l.code, label: `English → ${l.label}` },
  { source: l.code, target: 'en', label: `${l.label} → English` },
]);

const DOMAINS = [
  'X-Ray Systems', 'Security Screening', 'Radiation Physics',
  'Detector Electronics', 'Mechanical Engineering', 'Electrical Engineering',
  'AI / Machine Learning', 'Aviation Security', 'Nuclear Security',
  'Cargo Inspection', 'Medical Imaging', 'General',
];

// ── Default seed terminology (X-ray domain) ───────────────────────────────────

const SEED_TERMS: Omit<DictEntry, 'id' | 'created_at'>[] = [
  { source_term: 'Threat Image Projection', target_term: 'إسقاط صور التهديد', source_lang: 'en', target_lang: 'ar', domain: 'X-Ray Systems', notes: null },
  { source_term: 'Backscatter', target_term: 'الأشعة المرتدة', source_lang: 'en', target_lang: 'ar', domain: 'X-Ray Systems', notes: null },
  { source_term: 'Dual Energy', target_term: 'الطاقة المزدوجة', source_lang: 'en', target_lang: 'ar', domain: 'X-Ray Systems', notes: null },
  { source_term: 'Detector', target_term: 'الكاشف', source_lang: 'en', target_lang: 'ar', domain: 'Detector Electronics', notes: null },
  { source_term: 'HVPS', target_term: 'مزود الجهد العالي', source_lang: 'en', target_lang: 'ar', domain: 'Detector Electronics', notes: 'High Voltage Power Supply' },
  { source_term: 'Conveyor belt', target_term: 'حزام الناقل', source_lang: 'en', target_lang: 'ar', domain: 'X-Ray Systems', notes: null },
  { source_term: 'X-ray tube', target_term: 'أنبوب الأشعة السينية', source_lang: 'en', target_lang: 'ar', domain: 'X-Ray Systems', notes: null },
  { source_term: 'Collimator', target_term: 'المُضيِّق', source_lang: 'en', target_lang: 'ar', domain: 'X-Ray Systems', notes: null },
  { source_term: 'Alarm', target_term: 'إنذار', source_lang: 'en', target_lang: 'ar', domain: 'Security Screening', notes: null },
  { source_term: 'False alarm', target_term: 'إنذار كاذب', source_lang: 'en', target_lang: 'ar', domain: 'Security Screening', notes: null },
];

// ── Main component ─────────────────────────────────────────────────────────────

type ActiveTab = 'dictionary' | 'memory';

export default function TranslationDictionaryPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('dictionary');
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('ar');

  // Dictionary state
  const [entries, setEntries] = useState<DictEntry[]>([]);
  const [loadingDict, setLoadingDict] = useState(true);
  const [searchDict, setSearchDict] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editSource, setEditSource] = useState('');
  const [editTarget, setEditTarget] = useState('');
  const [editDomain, setEditDomain] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSource, setNewSource] = useState('');
  const [newTarget, setNewTarget] = useState('');
  const [newDomain, setNewDomain] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [savingNew, setSavingNew] = useState(false);

  // Memory state
  const [memoryEntries, setMemoryEntries] = useState<MemoryEntry[]>([]);
  const [loadingMemory, setLoadingMemory] = useState(true);
  const [searchMemory, setSearchMemory] = useState('');
  const [editingMemId, setEditingMemId] = useState<string | null>(null);
  const [editMemTarget, setEditMemTarget] = useState('');

  const importRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  // Load on mount / lang change
  useEffect(() => {
    if (activeTab === 'dictionary') fetchDictionary();
    else fetchMemory();
  }, [activeTab, sourceLang, targetLang]);

  const fetchDictionary = async () => {
    setLoadingDict(true);
    try {
      const r = await fetch(`${API}/api/translation/dictionary?source_lang=${sourceLang}&target_lang=${targetLang}`, { credentials: 'include' });
      if (r.ok) setEntries(await r.json());
    } catch {}
    finally { setLoadingDict(false); }
  };

  const fetchMemory = async () => {
    setLoadingMemory(true);
    try {
      const q = searchMemory ? `&search=${encodeURIComponent(searchMemory)}` : '';
      const r = await fetch(`${API}/api/translation/memory?source_lang=${sourceLang}&target_lang=${targetLang}${q}&limit=200`, { credentials: 'include' });
      if (r.ok) setMemoryEntries(await r.json());
    } catch {}
    finally { setLoadingMemory(false); }
  };

  // ── Dictionary actions ─────────────────────────────────────────────────────

  const addEntry = async () => {
    if (!newSource.trim() || !newTarget.trim()) return;
    setSavingNew(true);
    try {
      const r = await fetch(`${API}/api/translation/dictionary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          source_term: newSource.trim(),
          target_term: newTarget.trim(),
          source_lang: sourceLang,
          target_lang: targetLang,
          domain: newDomain || null,
          notes: newNotes || null,
        }),
      });
      if (!r.ok) throw new Error('Failed to add entry');
      setNewSource(''); setNewTarget(''); setNewDomain(''); setNewNotes('');
      setShowAddForm(false);
      await fetchDictionary();
      toast({ title: 'Term added to dictionary' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setSavingNew(false);
    }
  };

  const startEditEntry = (e: DictEntry) => {
    setEditingId(e.id);
    setEditSource(e.source_term);
    setEditTarget(e.target_term);
    setEditDomain(e.domain || '');
    setEditNotes(e.notes || '');
  };

  const saveEditEntry = async (id: string) => {
    try {
      const r = await fetch(`${API}/api/translation/dictionary/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          source_term: editSource.trim(),
          target_term: editTarget.trim(),
          source_lang: sourceLang,
          target_lang: targetLang,
          domain: editDomain || null,
          notes: editNotes || null,
        }),
      });
      if (!r.ok) throw new Error('Failed to update entry');
      setEditingId(null);
      await fetchDictionary();
      toast({ title: 'Term updated' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const deleteEntry = async (id: string, term: string) => {
    if (!confirm(`Delete "${term}" from the dictionary?`)) return;
    await fetch(`${API}/api/translation/dictionary/${id}`, { method: 'DELETE', credentials: 'include' });
    setEntries(e => e.filter(x => x.id !== id));
    toast({ title: 'Term deleted' });
  };

  const shareEntry = async (id: string, term: string) => {
    try {
      const r = await fetch(`${API}/api/translation/dictionary/${id}/share`, {
        method: 'POST', credentials: 'include',
      });
      if (!r.ok) throw new Error('Share failed');
      setEntries(e => e.map(x => x.id === id ? { ...x, is_shared: true } : x));
      toast({ title: `"${term}" shared with team`, description: 'All team members will see this term.' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const shareAll = async () => {
    const personal = entries.filter(e => !e.is_shared);
    if (personal.length === 0) {
      toast({ title: 'No personal terms to share' });
      return;
    }
    if (!confirm(`Share all ${personal.length} personal term(s) with the team? They will be visible to every user.`)) return;
    try {
      const r = await fetch(`${API}/api/translation/dictionary/share-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ source_lang: sourceLang, target_lang: targetLang }),
      });
      if (!r.ok) throw new Error('Share failed');
      const data = await r.json();
      await fetchDictionary();
      toast({ title: `${data.shared_count} term(s) shared with team` });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const seedDictionary = async () => {
    if (!confirm(`Add ${SEED_TERMS.length} standard X-Ray domain terms to the dictionary?`)) return;
    let added = 0;
    for (const term of SEED_TERMS) {
      try {
        await fetch(`${API}/api/translation/dictionary`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(term),
        });
        added++;
      } catch {}
    }
    await fetchDictionary();
    toast({ title: `Added ${added} X-Ray domain terms` });
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    form.append('source_lang', sourceLang);
    form.append('target_lang', targetLang);
    try {
      const r = await fetch(`${API}/api/translation/dictionary/import`, {
        method: 'POST', body: form, credentials: 'include',
      });
      if (!r.ok) throw new Error('Import failed');
      const data = await r.json();
      await fetchDictionary();
      toast({ title: `Imported ${data.imported} terms` });
    } catch (e: any) {
      toast({ title: 'Import failed', description: e.message, variant: 'destructive' });
    }
    e.target.value = '';
  };

  // ── Memory actions ─────────────────────────────────────────────────────────

  const saveMemEntry = async (id: string) => {
    try {
      const r = await fetch(`${API}/api/translation/memory/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ target_text: editMemTarget }),
      });
      if (!r.ok) throw new Error('Save failed');
      setMemoryEntries(m => m.map(e => e.id === id ? { ...e, target_text: editMemTarget } : e));
      setEditingMemId(null);
      toast({ title: 'Memory entry updated' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const deleteMemEntry = async (id: string) => {
    await fetch(`${API}/api/translation/memory/${id}`, { method: 'DELETE', credentials: 'include' });
    setMemoryEntries(m => m.filter(e => e.id !== id));
    toast({ title: 'Memory entry deleted' });
  };

  const shareMemEntry = async (id: string) => {
    try {
      const r = await fetch(`${API}/api/translation/memory/${id}/share`, {
        method: 'POST', credentials: 'include',
      });
      if (!r.ok) throw new Error('Share failed');
      setMemoryEntries(m => m.map(e => e.id === id ? { ...e, is_shared: true } : e));
      toast({ title: 'Shared with team', description: 'This cached translation will be reused by all team members.' });
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  // ── Filtered data ──────────────────────────────────────────────────────────

  const filteredEntries = entries.filter(e =>
    !searchDict ||
    e.source_term.toLowerCase().includes(searchDict.toLowerCase()) ||
    e.target_term.toLowerCase().includes(searchDict.toLowerCase()) ||
    (e.domain || '').toLowerCase().includes(searchDict.toLowerCase())
  );

  const filteredMemory = memoryEntries.filter(e =>
    !searchMemory ||
    e.source_text.toLowerCase().includes(searchMemory.toLowerCase()) ||
    e.target_text.toLowerCase().includes(searchMemory.toLowerCase())
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-auto bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/40 px-6 py-4 shrink-0">
        <div className="max-w-7xl mx-auto flex items-center gap-3">
          <Link href="/translation">
            <Button variant="ghost" size="sm" className="gap-1 text-xs shrink-0">
              <ChevronLeft className="h-3.5 w-3.5" /> Translation Studio
            </Button>
          </Link>
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center ring-1 ring-primary/20">
              <Database className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground">Dictionary & Translation Memory</h1>
              <p className="text-xs text-muted-foreground">Manage custom terminology and reusable translations</p>
            </div>
          </div>

          {/* Language selector */}
          <div className="flex items-center gap-2 shrink-0">
            <Select value={`${sourceLang}-${targetLang}`}
              onValueChange={v => { const [s, t] = v.split('-'); setSourceLang(s); setTargetLang(t); }}>
              <SelectTrigger className="h-8 w-44 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANG_PAIRS.map(lp => (
                  <SelectItem key={`${lp.source}-${lp.target}`} value={`${lp.source}-${lp.target}`} className="text-xs">
                    {lp.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-7xl mx-auto mt-3 flex items-center gap-1">
          {[
            { id: 'dictionary', label: 'Custom Dictionary', icon: BookOpen, count: entries.length },
            { id: 'memory', label: 'Translation Memory', icon: Brain, count: memoryEntries.length },
          ].map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id as ActiveTab)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all
                ${activeTab === tab.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'}`}>
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
              <span className={`px-1.5 py-0.5 rounded text-[10px] ${activeTab === tab.id ? 'bg-white/20' : 'bg-muted'}`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Dictionary Tab ─────────────────────────────────────────────────── */}
      {activeTab === 'dictionary' && (
        <div className="flex-1 overflow-auto">
          {/* Toolbar */}
          <div className="sticky top-0 z-10 bg-background/95 backdrop-blur-sm border-b border-border px-6 py-2">
            <div className="max-w-7xl mx-auto flex items-center gap-3">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input value={searchDict} onChange={e => setSearchDict(e.target.value)}
                  placeholder="Search terms…" className="h-8 pl-8 text-xs" />
              </div>
              <div className="ml-auto flex items-center gap-2">
                <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={seedDictionary}>
                  <Languages className="h-3 w-3" /> Seed X-Ray Terms
                </Button>
                {entries.some(e => !e.is_shared) && (
                  <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5 text-sky-600 border-sky-300 hover:bg-sky-50" onClick={shareAll}>
                    <Users className="h-3 w-3" /> Share All
                  </Button>
                )}
                <input ref={importRef} type="file" accept=".tsv,.txt,.csv" className="hidden" onChange={handleImport} />
                <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => importRef.current?.click()}>
                  <Upload className="h-3 w-3" /> Import TSV
                </Button>
                <a href={`${API}/api/translation/dictionary/export?source_lang=${sourceLang}&target_lang=${targetLang}`} download>
                  <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5">
                    <Download className="h-3 w-3" /> Export TSV
                  </Button>
                </a>
                <Button size="sm" className="h-8 text-xs gap-1.5" onClick={() => setShowAddForm(true)}>
                  <Plus className="h-3 w-3" /> Add Term
                </Button>
              </div>
            </div>
          </div>

          <div className="max-w-7xl mx-auto px-6 py-4">
            {/* Add form */}
            {showAddForm && (
              <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 mb-4 space-y-3">
                <h3 className="text-sm font-semibold text-foreground">Add New Term</h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Source Term ({sourceLang.toUpperCase()})</Label>
                    <Input value={newSource} onChange={e => setNewSource(e.target.value)}
                      placeholder="e.g. Detector Array" className="h-8 text-sm" autoFocus />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Target Term ({targetLang.toUpperCase()})</Label>
                    <Input value={newTarget} onChange={e => setNewTarget(e.target.value)}
                      placeholder="e.g. translated term"
                      className={`h-8 text-sm ${targetLang === 'ar' ? 'text-right' : 'text-left'}`}
                      dir={targetLang === 'ar' ? 'rtl' : 'ltr'} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Domain (optional)</Label>
                    <Select value={newDomain} onValueChange={setNewDomain}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select domain…" /></SelectTrigger>
                      <SelectContent>
                        {DOMAINS.map(d => <SelectItem key={d} value={d} className="text-xs">{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Notes (optional)</Label>
                    <Input value={newNotes} onChange={e => setNewNotes(e.target.value)}
                      placeholder="e.g. abbreviation, context" className="h-8 text-sm" />
                  </div>
                </div>
                <div className="flex gap-2 justify-end">
                  <Button size="sm" variant="ghost" className="text-xs" onClick={() => setShowAddForm(false)}>Cancel</Button>
                  <Button size="sm" className="text-xs gap-1.5" onClick={addEntry} disabled={savingNew || !newSource.trim() || !newTarget.trim()}>
                    {savingNew ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                    Add Term
                  </Button>
                </div>
              </div>
            )}

            {loadingDict ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
            ) : filteredEntries.length === 0 ? (
              <div className="text-center py-16">
                <BookOpen className="h-10 w-10 mx-auto mb-3 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground mb-4">
                  {entries.length === 0
                    ? 'No custom terms yet. Add terms or seed with X-Ray domain terminology.'
                    : 'No terms match your search.'}
                </p>
                {entries.length === 0 && (
                  <Button size="sm" onClick={seedDictionary} className="gap-2">
                    <Languages className="h-4 w-4" /> Seed X-Ray Domain Terms
                  </Button>
                )}
              </div>
            ) : (
              <>
                <p className="text-xs text-muted-foreground mb-3">{filteredEntries.length} term{filteredEntries.length !== 1 ? 's' : ''}</p>

                {/* Table header */}
                <div className="grid grid-cols-[2fr_2fr_1fr_auto] gap-3 px-3 py-2 text-[10px] font-mono font-semibold text-muted-foreground/60 uppercase tracking-widest border-b border-border">
                  <span>Source ({sourceLang.toUpperCase()})</span>
                  <span>Target ({targetLang.toUpperCase()})</span>
                  <span>Domain / Scope</span>
                  <span></span>
                </div>

                <div className="space-y-1 mt-1">
                  {filteredEntries.map(entry => (
                    <div key={entry.id} className={`grid grid-cols-[2fr_2fr_1fr_auto] gap-3 items-center px-3 py-2.5 rounded-lg hover:bg-card/60 transition-all group border border-transparent hover:border-border/50 ${entry.is_shared ? 'bg-sky-50/30 dark:bg-sky-900/10' : ''}`}>
                      {editingId === entry.id ? (
                        <>
                          <Input value={editSource} onChange={e => setEditSource(e.target.value)} className="h-7 text-xs" />
                          <Input value={editTarget} onChange={e => setEditTarget(e.target.value)}
                            className={`h-7 text-xs ${entry.target_lang === 'ar' ? 'text-right' : 'text-left'}`}
                            dir={entry.target_lang === 'ar' ? 'rtl' : 'ltr'} />
                          <Select value={editDomain} onValueChange={setEditDomain}>
                            <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                            <SelectContent>{DOMAINS.map(d => <SelectItem key={d} value={d} className="text-xs">{d}</SelectItem>)}</SelectContent>
                          </Select>
                          <div className="flex gap-1">
                            <Button size="sm" className="h-7 w-7 p-0" onClick={() => saveEditEntry(entry.id)}><Check className="h-3 w-3" /></Button>
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setEditingId(null)}><X className="h-3 w-3" /></Button>
                          </div>
                        </>
                      ) : (
                        <>
                          <div>
                            <span className="text-sm font-medium text-foreground">{entry.source_term}</span>
                            {entry.notes && <p className="text-[10px] text-muted-foreground">{entry.notes}</p>}
                          </div>
                          <span className={`text-sm text-foreground/90 ${entry.target_lang === 'ar' ? 'text-right' : 'text-left'}`} dir={entry.target_lang === 'ar' ? 'rtl' : 'ltr'}>{entry.target_term}</span>
                          <span className="flex flex-wrap gap-1 items-center">
                            {entry.is_shared ? (
                              <Badge className="text-[10px] bg-sky-500/15 text-sky-600 border border-sky-400/30 gap-0.5">
                                <Users className="h-2.5 w-2.5" /> Shared
                              </Badge>
                            ) : null}
                            {entry.domain && (
                              <Badge variant="outline" className="text-[10px] border-primary/20 text-primary/70">{entry.domain}</Badge>
                            )}
                          </span>
                          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            {!entry.is_shared && (
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-sky-600"
                                title="Share with team"
                                onClick={() => shareEntry(entry.id, entry.source_term)}>
                                <Share2 className="h-3 w-3" />
                              </Button>
                            )}
                            {!entry.is_shared && (
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => startEditEntry(entry)}>
                                <Edit3 className="h-3 w-3" />
                              </Button>
                            )}
                            {!entry.is_shared && (
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                                onClick={() => deleteEntry(entry.id, entry.source_term)}>
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Memory Tab ─────────────────────────────────────────────────────── */}
      {activeTab === 'memory' && (
        <div className="flex-1 overflow-auto">
          {/* Toolbar */}
          <div className="sticky top-0 z-10 bg-background/95 backdrop-blur-sm border-b border-border px-6 py-2">
            <div className="max-w-7xl mx-auto flex items-center gap-3">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input value={searchMemory} onChange={e => setSearchMemory(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && fetchMemory()}
                  placeholder="Search memory…" className="h-8 pl-8 text-xs" />
              </div>
              <Button size="sm" variant="outline" className="h-8 text-xs" onClick={fetchMemory}>Search</Button>
              <p className="ml-auto text-xs text-muted-foreground">{filteredMemory.length} entries</p>
            </div>
          </div>

          <div className="max-w-7xl mx-auto px-6 py-4">
            {loadingMemory ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
            ) : filteredMemory.length === 0 ? (
              <div className="text-center py-16">
                <Brain className="h-10 w-10 mx-auto mb-3 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">No translation memory entries yet.</p>
                <p className="text-xs text-muted-foreground mt-1">Memory is built automatically as you translate documents.</p>
              </div>
            ) : (
              <>
                {/* Table header */}
                <div className="grid grid-cols-[2fr_2fr_auto_auto] gap-3 px-3 py-2 text-[10px] font-mono font-semibold text-muted-foreground/60 uppercase tracking-widest border-b border-border">
                  <span>Source ({sourceLang.toUpperCase()})</span>
                  <span>Translation ({targetLang.toUpperCase()})</span>
                  <span>Uses / Scope</span>
                  <span></span>
                </div>

                <div className="space-y-1 mt-1">
                  {filteredMemory.map(entry => (
                    <div key={entry.id} className={`grid grid-cols-[2fr_2fr_auto_auto] gap-3 items-start px-3 py-2.5 rounded-lg hover:bg-card/60 transition-all group border border-transparent hover:border-border/50 ${entry.is_shared ? 'bg-sky-50/30 dark:bg-sky-900/10' : ''}`}>
                      <p className="text-xs text-foreground/80 leading-relaxed line-clamp-3">{entry.source_text}</p>

                      {editingMemId === entry.id ? (
                        <div className="space-y-1.5">
                          <textarea
                            value={editMemTarget}
                            onChange={e => setEditMemTarget(e.target.value)}
                            className={`w-full text-xs bg-background border border-primary/30 rounded p-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-primary min-h-[60px] ${targetLang === 'ar' ? 'text-right' : 'text-left'}`}
                            dir={targetLang === 'ar' ? 'rtl' : 'ltr'}
                          />
                          <div className="flex gap-1">
                            <Button size="sm" className="h-6 text-[10px] px-2" onClick={() => saveMemEntry(entry.id)}>Save</Button>
                            <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2" onClick={() => setEditingMemId(null)}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <p className={`text-xs text-foreground/80 leading-relaxed line-clamp-3 ${targetLang === 'ar' ? 'text-right' : 'text-left'}`} dir={targetLang === 'ar' ? 'rtl' : 'ltr'}>
                          {entry.target_text}
                        </p>
                      )}

                      <div className="flex flex-col gap-1 items-end shrink-0 self-start">
                        <Badge variant="outline" className="text-[10px] border-sky-500/20 text-sky-400">
                          ×{entry.use_count}
                        </Badge>
                        {entry.is_shared ? (
                          <Badge className="text-[10px] bg-sky-500/15 text-sky-600 border border-sky-400/30 gap-0.5">
                            <Users className="h-2.5 w-2.5" /> Team
                          </Badge>
                        ) : null}
                      </div>

                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity self-start">
                        {!entry.is_shared && (
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-muted-foreground hover:text-sky-600"
                            title="Share with team"
                            onClick={() => shareMemEntry(entry.id)}>
                            <Share2 className="h-3 w-3" />
                          </Button>
                        )}
                        {!entry.is_shared && (
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0"
                            onClick={() => { setEditingMemId(entry.id); setEditMemTarget(entry.target_text); }}>
                            <Edit3 className="h-3 w-3" />
                          </Button>
                        )}
                        {!entry.is_shared && (
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                            onClick={() => deleteMemEntry(entry.id)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
