// AI Chat Workspace API — plain fetch/XHR against /api/workspaces/*, matching
// the convention already used by translation.tsx and upload.tsx (this backend
// route is additive and not part of the generated @workspace/api-client-react
// OpenAPI client).

import { ANON_SESSION_HEADER, getAnonSessionId } from './session';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');
const base = (path: string) => `${API}${path}`;
/** Anonymous-session isolation header — ignored server-side once authenticated. */
const anonHeaders = (): Record<string, string> => ({ [ANON_SESSION_HEADER]: getAnonSessionId() });

export interface WorkspaceFileDict {
  id: string;
  workspace_id: string;
  relative_path: string;
  original_filename: string;
  mime_type: string;
  extension: string;
  size_bytes: number;
  checksum: string;
  parse_status: 'pending' | 'processing' | 'ready' | 'error' | 'unsupported' | 'skipped';
  errors: string[];
  warnings: string[];
  created_at: string;
}

export interface WorkspaceDict {
  id: string;
  user_id: string;
  conversation_id: string | null;
  name: string;
  status: string;
  total_files: number;
  total_size_bytes: number;
  created_at: string;
  updated_at: string;
  files?: WorkspaceFileDict[];
}

export interface GeneratedFileDict {
  id: string;
  workspace_id: string;
  task_id: string | null;
  filename: string;
  format: string;
  size_bytes: number;
  source_file_ids: string[];
  created_at: string;
}

export interface WorkspaceTreeNode {
  __type__: 'dir' | 'file';
  id?: string;
  size_bytes?: number;
  parse_status?: string;
  extension?: string;
  children?: Record<string, WorkspaceTreeNode>;
}

async function asJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(text || `Request failed (HTTP ${resp.status})`);
  }
  return resp.json();
}

export async function createWorkspace(name: string, conversationId?: string | null): Promise<WorkspaceDict> {
  const resp = await fetch(base('/api/workspaces'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...anonHeaders() },
    credentials: 'include',
    body: JSON.stringify({ name, conversation_id: conversationId || null }),
  });
  return asJson(resp);
}

export async function listWorkspaces(): Promise<WorkspaceDict[]> {
  const resp = await fetch(base('/api/workspaces'), { credentials: 'include', headers: anonHeaders() });
  return asJson(resp);
}

export async function getWorkspace(workspaceId: string): Promise<WorkspaceDict> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}`), { credentials: 'include', headers: anonHeaders() });
  return asJson(resp);
}

export async function getWorkspaceTree(workspaceId: string): Promise<{ workspace_id: string; tree: Record<string, WorkspaceTreeNode> }> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}/tree`), { credentials: 'include', headers: anonHeaders() });
  return asJson(resp);
}

export async function listGeneratedFiles(workspaceId: string): Promise<GeneratedFileDict[]> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}/generated`), { credentials: 'include', headers: anonHeaders() });
  return asJson(resp);
}

export async function deleteWorkspaceFile(workspaceId: string, fileId: string): Promise<void> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}/files/${fileId}`), {
    method: 'DELETE',
    credentials: 'include',
    headers: anonHeaders(),
  });
  if (!resp.ok && resp.status !== 204) throw new Error(`Failed to delete file (HTTP ${resp.status})`);
}

export async function reindexWorkspace(workspaceId: string): Promise<{ workspace: WorkspaceDict; processing: { processed: number; failed: number; total: number } }> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}/index`), { method: 'POST', credentials: 'include', headers: anonHeaders() });
  return asJson(resp);
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}`), { method: 'DELETE', credentials: 'include', headers: anonHeaders() });
  if (!resp.ok && resp.status !== 204) throw new Error(`Failed to delete workspace (HTTP ${resp.status})`);
}

/** Hybrid Workspace Awareness trigger #14 (user opening a different project) —
 * called by useWorkspace on workspace switch to check freshness. */
export async function getIndexStatus(workspaceId: string): Promise<{ workspace_id: string; dirty_count: number; fresh: boolean }> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}/index-status`), { credentials: 'include', headers: anonHeaders() });
  return asJson(resp);
}

/** Hybrid Workspace Awareness trigger #13 (explicit refresh request). */
export async function refreshWorkspaceIndex(workspaceId: string, force = false): Promise<Record<string, number>> {
  const resp = await fetch(base(`/api/workspaces/${workspaceId}/refresh-index?force=${force}`), {
    method: 'POST', credentials: 'include', headers: anonHeaders(),
  });
  return asJson(resp);
}

export function downloadGeneratedFileUrl(workspaceId: string, fileId: string): string {
  return base(`/api/workspaces/${workspaceId}/generated/${fileId}/download`);
}

export interface UploadEntry {
  file: File;
  relativePath: string;
}

export interface UploadResult {
  workspace: WorkspaceDict;
  uploaded: WorkspaceFileDict[];
  upload_errors: string[];
  processing: { processed: number; failed: number; total: number };
}

/** XHR-based multipart upload with real progress, mirroring translation.tsx's upload pattern. */
export function uploadToWorkspace(
  workspaceId: string,
  entries: UploadEntry[],
  onProgress?: (pct: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    for (const { file, relativePath } of entries) {
      form.append('files', file, file.name);
      form.append('relative_paths', relativePath);
    }

    const xhr = new XMLHttpRequest();
    xhr.withCredentials = true;
    xhr.timeout = 10 * 60 * 1000;

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error('Upload succeeded but the response could not be parsed.'));
        }
      } else {
        reject(new Error(xhr.responseText || `Upload failed (HTTP ${xhr.status})`));
      }
    });
    xhr.addEventListener('error', () => reject(new Error('Network error during upload.')));
    xhr.addEventListener('timeout', () => reject(new Error('Upload timed out.')));

    xhr.open('POST', base(`/api/workspaces/${workspaceId}/upload`));
    xhr.setRequestHeader(ANON_SESSION_HEADER, getAnonSessionId());
    xhr.send(form);
  });
}

/** Recursively read a dropped/selected folder's files with webkitRelativePath preserved. */
export function fileListToEntries(files: FileList | File[], folderName?: string): UploadEntry[] {
  const list = Array.from(files);
  return list.map((file) => {
    const rel = (file as any).webkitRelativePath as string | undefined;
    return { file, relativePath: rel && rel.length > 0 ? rel : (folderName ? `${folderName}/${file.name}` : file.name) };
  });
}

export function topLevelFolderName(files: FileList | File[]): string {
  const list = Array.from(files);
  for (const file of list) {
    const rel = (file as any).webkitRelativePath as string | undefined;
    if (rel && rel.includes('/')) return rel.split('/')[0];
  }
  return 'Workspace';
}
