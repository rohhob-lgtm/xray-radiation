import { useState, useRef, useCallback, useEffect } from 'react';
import { Database, Trash2, FileText, Upload, Plus, FileQuestion, HardDrive, FolderOpen, AlertCircle, Loader2, Pencil, Search, X, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { useListRagDocuments, useUploadRagDocument, useDeleteRagDocument, useUpdateRagDocument, getListRagDocumentsQueryKey } from '@workspace/api-client-react';
import type { RagDocument } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── RAG Search Component ─────────────────────────────────────────────────

function RagSearchBar() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); setHasSearched(false); return; }
    setIsSearching(true);
    try {
      const resp = await fetch(`${API}/api/rag/search?q=${encodeURIComponent(q)}&top_k=6`, { credentials: 'include' });
      const data = await resp.json();
      setResults(data.results || []);
      setHasSearched(true);
    } catch {
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(e.target.value), 600);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      doSearch(query);
    }
    if (e.key === 'Escape') { setQuery(''); setResults([]); setHasSearched(false); }
  };

  const clear = () => { setQuery(''); setResults([]); setHasSearched(false); };

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Search the knowledge base… (e.g. 'dual-energy detection', 'ZBV shielding')"
          className="pl-9 pr-9 bg-card border-border h-10 text-sm"
        />
        {(query || isSearching) && (
          <button onClick={clear} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            {isSearching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>

      {hasSearched && (
        <div className="space-y-2">
          {results.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6 font-mono uppercase tracking-widest">No matching chunks found</p>
          ) : (
            results.map((r, i) => (
              <div key={i} className="p-3.5 rounded-lg border border-border bg-card/50 hover:border-primary/30 transition-colors">
                <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="text-xs font-medium text-foreground truncate max-w-[220px]" title={r.source}>{r.source}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {r.page_num && <Badge variant="outline" className="font-mono text-[10px] h-4 px-1.5">p.{r.page_num}</Badge>}
                    <Badge variant="outline" className="font-mono text-[10px] h-4 px-1.5 text-emerald-400 border-emerald-500/20 bg-emerald-500/5">
                      ↑{(r.score * 100).toFixed(1)}%
                    </Badge>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed line-clamp-4">{r.text}</p>
              </div>
            ))
          )}
          <p className="text-[10px] text-muted-foreground font-mono text-center">{results.length} results for "{query}"</p>
        </div>
      )}
    </div>
  );
}

// Accepted MIME types & extensions
const ACCEPTED_EXTENSIONS = '.pdf,.pptx,.ppt,.docx,.doc,.txt,.md,.csv,.json,.xml,.yaml,.yml';
const TEXT_EXTS = new Set(['txt','md','csv','json','xml','yaml','yml','log','py','js','ts','html','tex','rst']);

async function uploadFileToKB(file: File, documentType: string): Promise<Response> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type', documentType);
  return fetch(`${API}/api/rag/documents/upload`, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });
}

export default function RagPage() {
  const queryClient = useQueryClient();
  const { data: documents, isLoading } = useListRagDocuments();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Auto-refresh while any document is processing ───────────────────────
  const hasProcessing = documents?.some(d => (d as any).status === 'processing');
  useEffect(() => {
    if (!hasProcessing) return;
    const id = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: getListRagDocumentsQueryKey() });
    }, 3000);
    return () => clearInterval(id);
  }, [hasProcessing, queryClient]);

  const [isOpen, setIsOpen] = useState(false);
  const [tab, setTab] = useState<'file' | 'paste'>('file');

  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileType, setFileType] = useState('other');
  const [isUploading, setIsUploading] = useState(false);
  const [fileError, setFileError] = useState('');

  // Paste state
  const [filename, setFilename] = useState('');
  const [pasteType, setPasteType] = useState('manual');
  const [content, setContent] = useState('');

  const { mutate: uploadJSON, isPending: isPastePending } = useUploadRagDocument({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListRagDocumentsQueryKey() });
        resetAndClose();
      },
      onError: () => setFileError('Upload failed. Please try again.'),
    }
  });

  const { mutate: deleteDoc } = useDeleteRagDocument({
    mutation: {
      onSuccess: () => queryClient.invalidateQueries({ queryKey: getListRagDocumentsQueryKey() }),
    }
  });

  // ── Edit state ──────────────────────────────────────────
  const [editingDoc, setEditingDoc] = useState<RagDocument | null>(null);
  const [editFilename, setEditFilename] = useState('');
  const [editType, setEditType] = useState('other');
  const [editContent, setEditContent] = useState('');
  const [editError, setEditError] = useState('');

  const { mutate: updateDoc, isPending: isSaving } = useUpdateRagDocument({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListRagDocumentsQueryKey() });
        setEditingDoc(null);
        setEditError('');
      },
      onError: () => setEditError('Save failed. Please try again.'),
    }
  });

  const openEdit = (doc: RagDocument) => {
    setEditingDoc(doc);
    setEditFilename(doc.filename);
    setEditType(doc.document_type);
    // content_preview is truncated — we need the full content from the list
    // The API returns content_preview only; full content is fetched via preview text
    setEditContent('');
    setEditError('');
  };

  const handleSave = () => {
    if (!editingDoc || !editFilename.trim()) return;
    const patch: Record<string, string> = {
      filename: editFilename,
      document_type: editType,
    };
    if (editContent.trim()) patch.content = editContent;
    updateDoc({ documentId: editingDoc.id, data: patch });
  };

  const resetAndClose = () => {
    setIsOpen(false);
    setSelectedFile(null);
    setFilename('');
    setContent('');
    setFileError('');
    setFileType('other');
    setPasteType('manual');
    setTab('file');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setFileError('');
    if (file.size > 1 * 1024 * 1024 * 1024) {
      setFileError('File too large — maximum 1 GB.');
      return;
    }
    setSelectedFile(file);
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    setFileError('');
    if (file.size > 1 * 1024 * 1024 * 1024) { setFileError('File too large — maximum 1 GB.'); return; }
    setSelectedFile(file);
  };

  const handleFileUpload = async () => {
    if (!selectedFile) return;
    setFileError('');
    setIsUploading(true);
    try {
      const resp = await uploadFileToKB(selectedFile, fileType);
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: 'Upload failed.' }));
        throw new Error(body.detail || 'Upload failed.');
      }
      // Server returns immediately with status='processing' for large files —
      // close the dialog right away and let auto-refresh handle the status update.
      queryClient.invalidateQueries({ queryKey: getListRagDocumentsQueryKey() });
      resetAndClose();
    } catch (err: any) {
      setFileError(err.message || 'Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const handlePasteUpload = () => {
    if (!filename.trim() || !content.trim()) return;
    uploadJSON({ data: { filename, document_type: pasteType as any, content } });
  };

  const totalWords = documents?.reduce((acc, doc) => acc + (doc.word_count || 0), 0) || 0;

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-background">
      <div className="p-6 md:p-8 max-w-6xl mx-auto w-full space-y-8">

        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-border pb-6">
          <div className="flex flex-col gap-2">
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
              <Database className="h-8 w-8 text-primary" />
              Knowledge Base
            </h1>
            <p className="text-muted-foreground uppercase font-mono tracking-wider text-sm">Semantic Retrieval Engine</p>
          </div>
          <div className="flex gap-4">
            <div className="flex flex-col items-end px-4 py-2 bg-card border border-border rounded-lg shadow-sm">
              <span className="text-2xl font-bold text-primary leading-none">{documents?.length || 0}</span>
              <span className="text-[10px] font-mono uppercase text-muted-foreground tracking-widest">Indexed Docs</span>
            </div>
            <div className="flex flex-col items-end px-4 py-2 bg-card border border-border rounded-lg shadow-sm">
              <span className="text-2xl font-bold text-foreground leading-none">{(totalWords / 1000).toFixed(1)}k</span>
              <span className="text-[10px] font-mono uppercase text-muted-foreground tracking-widest">Words Indexed</span>
            </div>
          </div>
        </div>

        {/* Info callout */}
        <div className="bg-primary/10 border border-primary/20 rounded-lg p-4 flex gap-4 items-start">
          <HardDrive className="h-5 w-5 text-primary shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="font-semibold text-sm text-primary-foreground">Automated Context Retrieval</h4>
            <p className="text-sm text-primary-foreground/80">
              Documents are automatically chunked, vectorized, and retrieved when relevant to your queries in the AI Chat.
              Supported formats: <span className="font-mono font-semibold">PDF, PPTX, DOCX, TXT, MD, CSV, JSON</span> and more.
            </p>
          </div>
        </div>

        {/* Semantic Search */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 mb-1">
            <Search className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground font-mono">Semantic Knowledge Search</h3>
          </div>
          <RagSearchBar />
        </div>

        {/* Header & Add action */}
        <div className="flex items-center justify-between pt-2">
          <h2 className="text-xl font-bold tracking-tight">Indexed Source Material</h2>
          <Dialog open={isOpen} onOpenChange={(v) => { if (!v) resetAndClose(); else setIsOpen(true); }}>
            <DialogTrigger asChild>
              <Button className="gap-2">
                <Plus className="h-4 w-4" />
                Add Document
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[580px] border-border bg-card">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Upload className="h-5 w-5 text-primary" />
                  Ingest Source Material
                </DialogTitle>
              </DialogHeader>

              {/* Tabs */}
              <div className="flex gap-1 p-1 bg-background rounded-lg border border-border mt-1">
                {(['file', 'paste'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => { setTab(t); setFileError(''); }}
                    className={`flex-1 text-xs uppercase font-mono tracking-wider py-2 px-3 rounded-md transition-colors ${
                      tab === t ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'text-muted-foreground hover:bg-secondary'
                    }`}
                  >
                    {t === 'file' ? 'Upload File' : 'Paste Text'}
                  </button>
                ))}
              </div>

              {tab === 'file' ? (
                <div className="grid gap-5 py-2">
                  {/* Drop zone */}
                  <div
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleFileDrop}
                    onClick={() => !selectedFile && fileInputRef.current?.click()}
                    className={`flex flex-col items-center justify-center gap-3 w-full border-2 border-dashed rounded-xl py-10 px-4 transition-colors cursor-pointer ${
                      selectedFile
                        ? 'border-primary/60 bg-primary/5 cursor-default'
                        : 'border-border hover:border-primary/50 hover:bg-primary/5'
                    }`}
                  >
                    {selectedFile ? (
                      <>
                        <FileText className="h-9 w-9 text-primary" />
                        <div className="text-center">
                          <p className="font-semibold text-sm text-foreground">{selectedFile.name}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {(selectedFile.size / 1024).toFixed(0)} KB
                          </p>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="mt-1"
                          onClick={(e) => { e.stopPropagation(); setSelectedFile(null); setFileError(''); }}
                        >
                          Remove
                        </Button>
                      </>
                    ) : (
                      <>
                        <FolderOpen className="h-9 w-9 text-muted-foreground" />
                        <div className="text-center">
                          <p className="text-sm font-medium text-foreground">Click to browse or drag & drop</p>
                          <p className="text-[11px] font-mono text-muted-foreground mt-1">
                            PDF · PPTX · DOCX · TXT · MD · CSV · JSON · XML · YAML
                          </p>
                          <p className="text-[10px] text-muted-foreground/60 mt-0.5">Max 1 GB</p>
                        </div>
                      </>
                    )}
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={ACCEPTED_EXTENSIONS}
                    onChange={handleFileChange}
                    className="hidden"
                  />

                  {/* Document type */}
                  <div className="grid gap-2">
                    <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Document Classification</label>
                    <div className="flex p-1 bg-background rounded-lg border border-border w-full flex-wrap gap-1">
                      {['manual', 'procedure', 'regulation', 'training', 'other'].map((t) => (
                        <button
                          key={t}
                          onClick={() => setFileType(t)}
                          className={`flex-1 min-w-[70px] text-xs uppercase font-mono tracking-wider py-2 px-1 rounded-md transition-colors ${
                            fileType === t ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'text-muted-foreground hover:bg-secondary'
                          }`}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>

                  {fileError && (
                    <div className="flex items-start gap-2 text-destructive text-xs bg-destructive/10 border border-destructive/20 rounded-lg p-3">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                      {fileError}
                    </div>
                  )}

                  <Button
                    onClick={handleFileUpload}
                    disabled={!selectedFile || isUploading}
                    className="w-full h-10"
                  >
                    {isUploading ? (
                      <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Extracting &amp; indexing…</span>
                    ) : 'Upload & Index Document'}
                  </Button>
                </div>
              ) : (
                <div className="grid gap-5 py-2">
                  <div className="grid gap-2">
                    <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Filename *</label>
                    <Input
                      placeholder="e.g., SOP-2023-Cargo.txt"
                      value={filename}
                      onChange={e => setFilename(e.target.value)}
                      className="bg-background"
                    />
                  </div>
                  <div className="grid gap-2">
                    <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Classification</label>
                    <div className="flex p-1 bg-background rounded-lg border border-border w-full flex-wrap gap-1">
                      {['manual', 'procedure', 'regulation', 'training', 'other'].map((t) => (
                        <button
                          key={t}
                          onClick={() => setPasteType(t)}
                          className={`flex-1 min-w-[70px] text-xs uppercase font-mono tracking-wider py-2 px-1 rounded-md transition-colors ${
                            pasteType === t ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'text-muted-foreground hover:bg-secondary'
                          }`}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="grid gap-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Text Content *</label>
                      {content && (
                        <span className="text-[10px] font-mono text-muted-foreground">
                          {content.split(/\s+/).filter(Boolean).length.toLocaleString()} words
                        </span>
                      )}
                    </div>
                    <Textarea
                      placeholder="Paste document content here…"
                      value={content}
                      onChange={e => setContent(e.target.value)}
                      className="min-h-[180px] bg-background font-mono text-sm leading-relaxed"
                    />
                  </div>
                  {fileError && (
                    <div className="flex items-start gap-2 text-destructive text-xs bg-destructive/10 border border-destructive/20 rounded-lg p-3">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                      {fileError}
                    </div>
                  )}
                  <Button
                    onClick={handlePasteUpload}
                    disabled={!filename.trim() || !content.trim() || isPastePending}
                    className="w-full h-10"
                  >
                    {isPastePending ? (
                      <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Indexing…</span>
                    ) : 'Add to Knowledge Base'}
                  </Button>
                </div>
              )}
            </DialogContent>
          </Dialog>
        </div>

        {/* Document list */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {isLoading ? (
            <div className="col-span-full py-12 text-center text-muted-foreground animate-pulse font-mono text-xs uppercase tracking-widest">
              Querying index…
            </div>
          ) : documents?.length === 0 ? (
            <div className="col-span-full py-16 flex flex-col items-center justify-center border-2 border-dashed border-border rounded-xl opacity-60">
              <FileQuestion className="h-12 w-12 mb-4 text-muted-foreground" />
              <p className="text-sm font-mono uppercase tracking-widest text-muted-foreground text-center">
                Index Empty.<br />Upload PDFs, presentations, or Word documents to enhance AI responses.
              </p>
            </div>
          ) : (
            documents?.map(doc => (
              <div key={doc.id} className="flex flex-col bg-card border border-border rounded-xl p-5 shadow-sm hover:border-primary/40 hover:shadow-md transition-all group">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-3 bg-secondary/50 p-2 rounded-lg border border-border/50 flex-1 min-w-0 mr-2">
                    <FileText className="h-5 w-5 text-primary shrink-0" />
                    <div className="flex flex-col min-w-0">
                      <span className="font-bold text-sm tracking-tight leading-tight truncate" title={doc.filename}>{doc.filename}</span>
                      {(doc as any).status === 'processing' ? (
                        <span className="text-[10px] text-amber-400 font-mono uppercase animate-pulse">Extracting &amp; indexing…</span>
                      ) : (doc as any).status === 'error' ? (
                        <span className="text-[10px] text-destructive font-mono uppercase">Extraction failed</span>
                      ) : (
                        <span className="text-[10px] text-muted-foreground font-mono uppercase">{doc.word_count?.toLocaleString()} words</span>
                      )}
                    </div>
                  </div>
                  <Badge variant="outline" className="font-mono text-[9px] uppercase tracking-wider bg-background shrink-0">{doc.document_type}</Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-4 mb-4 flex-1 font-mono leading-relaxed bg-background p-3 rounded border border-border/50">
                  {(doc as any).status === 'processing'
                    ? 'Extracting text and indexing pages in the background. This may take a minute for large documents.'
                    : (doc as any).status === 'error'
                    ? (doc.content_preview || 'Processing failed. Delete this entry and try again.')
                    : doc.content_preview}
                </p>
                <div className="flex items-center justify-between pt-3 border-t border-border">
                  <span className="text-[10px] text-muted-foreground font-mono">{new Date(doc.created_at).toLocaleDateString()}</span>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10"
                      onClick={() => openEdit(doc)}
                      title="Edit document"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                      onClick={() => deleteDoc({ documentId: doc.id })}
                      title="Delete document"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Edit dialog ─────────────────────────────────────── */}
      <Dialog open={!!editingDoc} onOpenChange={(v) => { if (!v) { setEditingDoc(null); setEditError(''); } }}>
        <DialogContent className="sm:max-w-[620px] border-border bg-card max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pencil className="h-5 w-5 text-primary" />
              Edit Document
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-5 py-2">
            {/* Filename / title */}
            <div className="grid gap-2">
              <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">
                Title / Filename *
              </label>
              <Input
                value={editFilename}
                onChange={e => setEditFilename(e.target.value)}
                placeholder="e.g., SOP-2023-Cargo.pdf"
                className="bg-background"
              />
            </div>

            {/* Document type */}
            <div className="grid gap-2">
              <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">
                Classification
              </label>
              <div className="flex p-1 bg-background rounded-lg border border-border w-full flex-wrap gap-1">
                {['manual', 'procedure', 'regulation', 'training', 'other'].map((t) => (
                  <button
                    key={t}
                    onClick={() => setEditType(t)}
                    className={`flex-1 min-w-[70px] text-xs uppercase font-mono tracking-wider py-2 px-1 rounded-md transition-colors ${
                      editType === t ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'text-muted-foreground hover:bg-secondary'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {/* Content */}
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">
                  Content
                </label>
                <span className="text-[10px] font-mono text-muted-foreground">
                  {editContent
                    ? `${editContent.split(/\s+/).filter(Boolean).length.toLocaleString()} words (new)`
                    : 'Leave blank to keep existing content'}
                </span>
              </div>
              <Textarea
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                placeholder={`Current content (preview):\n${editingDoc?.content_preview ?? ''}\n\nPaste replacement text here to update, or leave blank to keep existing.`}
                className="min-h-[220px] bg-background font-mono text-sm leading-relaxed"
              />
              <p className="text-[11px] text-muted-foreground">
                If you replace the content, the document will be re-indexed automatically.
              </p>
            </div>

            {editError && (
              <div className="flex items-start gap-2 text-destructive text-xs bg-destructive/10 border border-destructive/20 rounded-lg p-3">
                <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                {editError}
              </div>
            )}

            <div className="flex gap-3 pt-1">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => { setEditingDoc(null); setEditError(''); }}
              >
                Cancel
              </Button>
              <Button
                className="flex-1"
                onClick={handleSave}
                disabled={!editFilename.trim() || isSaving}
              >
                {isSaving
                  ? <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Saving…</span>
                  : 'Save Changes'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
