import { useState } from 'react';
import {
  X, Folder, FolderOpen, File as FileIcon, FileText, FileSpreadsheet,
  FileCode, Image as ImageIcon, FileArchive, Download, Trash2, RefreshCw,
  CheckCircle2, XCircle, Clock, HelpCircle, Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { WorkspaceDict, GeneratedFileDict, WorkspaceTreeNode, downloadGeneratedFileUrl } from '@/lib/workspace-api';

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function fileIconFor(extension?: string) {
  const ext = (extension || '').toLowerCase();
  if (['pdf', 'txt', 'md', 'rtf', 'log'].includes(ext)) return FileText;
  if (['xlsx', 'xls', 'csv'].includes(ext)) return FileSpreadsheet;
  if (['pptx'].includes(ext)) return FileText;
  if (['png', 'jpg', 'jpeg', 'webp', 'tiff', 'tif'].includes(ext)) return ImageIcon;
  if (['zip'].includes(ext)) return FileArchive;
  if (['py', 'js', 'jsx', 'ts', 'tsx', 'html', 'css', 'sql', 'json', 'xml', 'yaml', 'yml'].includes(ext)) return FileCode;
  return FileIcon;
}

function StatusBadge({ status }: { status?: string }) {
  const map: Record<string, { icon: any; cls: string; label: string }> = {
    ready: { icon: CheckCircle2, cls: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10', label: 'Ready' },
    processing: { icon: Loader2, cls: 'text-amber-400 border-amber-500/30 bg-amber-500/10', label: 'Processing' },
    pending: { icon: Clock, cls: 'text-muted-foreground border-border bg-secondary', label: 'Pending' },
    error: { icon: XCircle, cls: 'text-destructive border-destructive/30 bg-destructive/10', label: 'Error' },
    unsupported: { icon: HelpCircle, cls: 'text-muted-foreground border-border bg-secondary', label: 'Unsupported' },
    skipped: { icon: HelpCircle, cls: 'text-muted-foreground border-border bg-secondary', label: 'Skipped' },
  };
  const entry = map[status || ''] || map.pending;
  const Icon = entry.icon;
  return (
    <Badge variant="outline" className={`h-4 px-1 text-[9px] gap-0.5 font-mono ${entry.cls}`}>
      <Icon className={`h-2.5 w-2.5 ${status === 'processing' ? 'animate-spin' : ''}`} />
      {entry.label}
    </Badge>
  );
}

function TreeNode({ name, node, depth, onDeleteFile }: {
  name: string; node: WorkspaceTreeNode; depth: number; onDeleteFile: (fileId: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const isDir = node.__type__ === 'dir';
  const pad = { paddingInlineStart: `${depth * 14}px` };

  if (isDir) {
    const DirIcon = open ? FolderOpen : Folder;
    const children = node.children || {};
    return (
      <div>
        <button
          className="w-full flex items-center gap-1.5 py-1 text-xs text-foreground hover:bg-secondary/60 rounded-sm"
          style={pad}
          onClick={() => setOpen((o) => !o)}
        >
          <DirIcon className="h-3.5 w-3.5 text-amber-400 shrink-0" />
          <span className="truncate">{name}</span>
        </button>
        {open && (
          <div>
            {Object.entries(children)
              .sort(([, a], [, b]) => (a.__type__ === b.__type__ ? 0 : a.__type__ === 'dir' ? -1 : 1))
              .map(([childName, child]) => (
                <TreeNode key={childName} name={childName} node={child} depth={depth + 1} onDeleteFile={onDeleteFile} />
              ))}
          </div>
        )}
      </div>
    );
  }

  const Icon = fileIconFor(node.extension);
  return (
    <div className="group flex items-center gap-1.5 py-1 text-xs" style={pad}>
      <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <span className="truncate flex-1 text-foreground/90">{name}</span>
      <span className="text-[9px] font-mono text-muted-foreground/60 shrink-0">{formatBytes(node.size_bytes || 0)}</span>
      <StatusBadge status={node.parse_status} />
      {node.id && (
        <button
          className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive shrink-0 transition-opacity"
          onClick={() => onDeleteFile(node.id!)}
          title="Remove file"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

export interface WorkspacePanelProps {
  workspace: WorkspaceDict | null;
  tree: Record<string, WorkspaceTreeNode> | null;
  generatedFiles: GeneratedFileDict[];
  onClose: () => void;
  onDeleteFile: (fileId: string) => void;
  onReindex: () => void;
  onDeleteWorkspace: () => void;
}

export function WorkspacePanel({
  workspace, tree, generatedFiles, onClose, onDeleteFile, onReindex, onDeleteWorkspace,
}: WorkspacePanelProps) {
  const [busy, setBusy] = useState(false);

  if (!workspace) return null;

  const run = async (fn: () => Promise<void> | void) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  return (
    <div className="absolute inset-y-0 end-0 z-30 w-[320px] max-w-[85%] bg-card border-s border-border shadow-2xl shadow-black/30 flex flex-col animate-in slide-in-from-right duration-200">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{workspace.name}</p>
          <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
            {workspace.total_files} files · {formatBytes(workspace.total_size_bytes)}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button variant="ghost" size="icon" className="h-7 w-7" disabled={busy} onClick={() => run(onReindex)} title="Re-index workspace">
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 hover:text-destructive" disabled={busy} onClick={() => run(onDeleteWorkspace)} title="Delete workspace">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose} data-testid="button-close-workspace-panel">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="px-3 py-2">
          <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/70 px-1 py-1">Files</p>
          {tree && Object.keys(tree).length > 0 ? (
            Object.entries(tree)
              .sort(([, a], [, b]) => (a.__type__ === b.__type__ ? 0 : a.__type__ === 'dir' ? -1 : 1))
              .map(([name, node]) => (
                <TreeNode key={name} name={name} node={node} depth={0} onDeleteFile={(id) => run(() => onDeleteFile(id))} />
              ))
          ) : (
            <p className="text-xs text-muted-foreground px-1 py-2">No files yet.</p>
          )}
        </div>

        <Separator />

        <div className="px-3 py-2">
          <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/70 px-1 py-1">
            Generated Files ({generatedFiles.length})
          </p>
          {generatedFiles.length === 0 ? (
            <p className="text-xs text-muted-foreground px-1 py-2">Nothing generated yet — ask the assistant to create a report, spreadsheet, or translation.</p>
          ) : (
            <div className="space-y-1">
              {generatedFiles.map((gf) => (
                <a
                  key={gf.id}
                  href={downloadGeneratedFileUrl(gf.workspace_id, gf.id)}
                  className="flex items-center gap-2 px-1.5 py-1.5 rounded-md hover:bg-secondary/60 text-xs group"
                  download
                >
                  <FileIcon className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span className="truncate flex-1 text-foreground/90">{gf.filename}</span>
                  <span className="text-[9px] font-mono text-muted-foreground/60 shrink-0">{formatBytes(gf.size_bytes)}</span>
                  <Download className="h-3 w-3 text-muted-foreground group-hover:text-primary shrink-0" />
                </a>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
