import { useState, useCallback, useEffect } from 'react';
import {
  WorkspaceDict, GeneratedFileDict, WorkspaceTreeNode, UploadEntry,
  createWorkspace, getWorkspace, getWorkspaceTree, listGeneratedFiles,
  uploadToWorkspace, deleteWorkspaceFile, reindexWorkspace,
  deleteWorkspace as apiDeleteWorkspace, fileListToEntries, topLevelFolderName,
  getIndexStatus, refreshWorkspaceIndex,
} from '@/lib/workspace-api';

export interface UploadStatus {
  phase: 'idle' | 'uploading' | 'processing' | 'done' | 'error';
  pct: number;
  message?: string;
  summary?: { uploaded: number; errors: string[]; processed: number; failed: number };
}

/** Manages the active AI Chat Workspace: attach/create, upload, and its
 * folder tree + generated files, so follow-up chat turns can reuse it
 * without re-uploading. */
export function useWorkspace(initialWorkspaceId?: string | null) {
  const [workspaceId, setWorkspaceId] = useState<string | null>(initialWorkspaceId || null);
  const [workspace, setWorkspace] = useState<WorkspaceDict | null>(null);
  const [tree, setTree] = useState<Record<string, WorkspaceTreeNode> | null>(null);
  const [generatedFiles, setGeneratedFiles] = useState<GeneratedFileDict[]>([]);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>({ phase: 'idle', pct: 0 });
  const [panelOpen, setPanelOpen] = useState(false);

  const refresh = useCallback(async (id?: string) => {
    const wid = id || workspaceId;
    if (!wid) return;
    try {
      const [ws, treeResp, gen] = await Promise.all([
        getWorkspace(wid), getWorkspaceTree(wid), listGeneratedFiles(wid),
      ]);
      setWorkspace(ws);
      setTree(treeResp.tree);
      setGeneratedFiles(gen);
    } catch {
      // Transient — the panel just won't refresh this cycle.
    }
  }, [workspaceId]);

  // Sync to a conversation's linked workspace (e.g. after loading a saved conversation).
  useEffect(() => {
    if (initialWorkspaceId && initialWorkspaceId !== workspaceId) {
      setWorkspaceId(initialWorkspaceId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialWorkspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    refresh(workspaceId);
    // Hybrid Workspace Awareness trigger #14 (user opening a different
    // project) — best-effort, non-blocking: check freshness and kick off a
    // background refresh if stale so the index is warm before the next chat turn.
    getIndexStatus(workspaceId)
      .then((status) => {
        if (!status.fresh) return refreshWorkspaceIndex(workspaceId);
      })
      .catch(() => {
        // Non-critical — the backend also checks freshness before every chat response.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const attachExisting = useCallback((id: string) => {
    setWorkspaceId(id);
  }, []);

  const clearWorkspace = useCallback(() => {
    setWorkspaceId(null);
    setWorkspace(null);
    setTree(null);
    setGeneratedFiles([]);
    setPanelOpen(false);
    setUploadStatus({ phase: 'idle', pct: 0 });
  }, []);

  const uploadFiles = useCallback(async (
    files: FileList | File[],
    opts?: { isFolder?: boolean; conversationId?: string | null },
  ) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setUploadStatus({ phase: 'uploading', pct: 0 });
    try {
      let wid = workspaceId;
      if (!wid) {
        const name = opts?.isFolder ? topLevelFolderName(list) : 'Workspace';
        const ws = await createWorkspace(name, opts?.conversationId ?? null);
        wid = ws.id;
        setWorkspaceId(wid);
      }
      const folderName = opts?.isFolder ? topLevelFolderName(list) : undefined;
      const entries: UploadEntry[] = fileListToEntries(list, folderName);
      const result = await uploadToWorkspace(wid, entries, (pct) => setUploadStatus({ phase: 'uploading', pct }));
      setUploadStatus({
        phase: 'done', pct: 100,
        summary: {
          uploaded: result.uploaded.length,
          errors: result.upload_errors,
          processed: result.processing.processed,
          failed: result.processing.failed,
        },
      });
      await refresh(wid);
      setPanelOpen(true);
      return result;
    } catch (err: any) {
      setUploadStatus({ phase: 'error', pct: 0, message: err?.message || 'Upload failed' });
      throw err;
    }
  }, [workspaceId, refresh]);

  const removeFile = useCallback(async (fileId: string) => {
    if (!workspaceId) return;
    await deleteWorkspaceFile(workspaceId, fileId);
    await refresh(workspaceId);
  }, [workspaceId, refresh]);

  const reindex = useCallback(async () => {
    if (!workspaceId) return;
    await reindexWorkspace(workspaceId);
    await refresh(workspaceId);
  }, [workspaceId, refresh]);

  const removeWorkspace = useCallback(async () => {
    if (!workspaceId) return;
    await apiDeleteWorkspace(workspaceId);
    clearWorkspace();
  }, [workspaceId, clearWorkspace]);

  return {
    workspaceId, workspace, tree, generatedFiles, uploadStatus, panelOpen,
    setPanelOpen, attachExisting, clearWorkspace, uploadFiles, removeFile,
    reindex, removeWorkspace, refreshWorkspace: refresh,
  };
}
