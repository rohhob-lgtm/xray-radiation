import { useState, useEffect, useCallback, useRef } from 'react';
import { ChevronLeft, ChevronRight, GripVertical } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════════
// Resizable + collapsible column.
// Drag the handle to resize, click the chevron to collapse. Both the width and
// the collapsed state persist per storage key so the layout survives reloads.
// ═══════════════════════════════════════════════════════════════════════════════

interface Options { key: string; initial: number; min?: number; max?: number }

export function useResizableColumn({ key, initial, min = 160, max = 560 }: Options) {
  const [width, setWidth] = useState(initial);
  const [collapsed, setCollapsed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const startRef = useRef<{ x: number; w: number } | null>(null);

  // Restore persisted state
  useEffect(() => {
    try {
      const raw = localStorage.getItem(`col:${key}`);
      if (raw) {
        const v = JSON.parse(raw) as { w?: number; c?: boolean };
        if (typeof v.w === 'number') setWidth(Math.min(max, Math.max(min, v.w)));
        if (typeof v.c === 'boolean') setCollapsed(v.c);
      }
    } catch { /* storage unavailable */ }
  }, [key, min, max]);

  const persist = useCallback((w: number, c: boolean) => {
    try { localStorage.setItem(`col:${key}`, JSON.stringify({ w, c })); } catch { /* ignore */ }
  }, [key]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    startRef.current = { x: e.clientX, w: width };
    setDragging(true);
  }, [width]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!startRef.current) return;
    const next = Math.min(max, Math.max(min, startRef.current.w + (e.clientX - startRef.current.x)));
    setWidth(next);
  }, [min, max]);

  const endDrag = useCallback(() => {
    if (!startRef.current) return;
    startRef.current = null;
    setDragging(false);
    persist(width, collapsed);
  }, [width, collapsed, persist]);

  const toggle = useCallback(() => {
    setCollapsed(c => { persist(width, !c); return !c; });
  }, [width, persist]);

  const reset = useCallback(() => { setWidth(initial); persist(initial, collapsed); }, [initial, collapsed, persist]);

  return { width, collapsed, dragging, toggle, reset, onPointerDown, onPointerMove, endDrag };
}

/** The draggable divider itself. Place it as a sibling of the column. */
export function ColumnResizer({
  onPointerDown, onPointerMove, onPointerUp, dragging, side = 'right',
}: {
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerMove: (e: React.PointerEvent) => void;
  onPointerUp: () => void;
  dragging: boolean;
  side?: 'left' | 'right';
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      title="Drag to resize · double-click to reset"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      className={`group relative hidden md:flex w-1.5 shrink-0 cursor-col-resize items-center justify-center
        ${dragging ? 'bg-primary/40' : 'bg-transparent hover:bg-primary/20'} transition-colors`}
      style={{ touchAction: 'none' }}
    >
      <span className={`absolute inset-y-0 ${side === 'right' ? 'left-0' : 'right-0'} w-px bg-border`} />
      <GripVertical className={`h-4 w-4 pointer-events-none transition-opacity ${dragging ? 'opacity-100 text-primary' : 'opacity-0 group-hover:opacity-70 text-muted-foreground'}`} />
    </div>
  );
}

/** Small chevron button that collapses / expands a column. */
export function ColumnToggle({
  collapsed, onClick, label, side = 'left',
}: { collapsed: boolean; onClick: () => void; label: string; side?: 'left' | 'right' }) {
  const Icon = collapsed ? (side === 'left' ? ChevronRight : ChevronLeft) : (side === 'left' ? ChevronLeft : ChevronRight);
  return (
    <button
      onClick={onClick}
      title={collapsed ? `Show ${label}` : `Hide ${label}`}
      className="h-6 w-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors shrink-0"
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

/** Vertical strip shown in place of a collapsed column so it can be reopened. */
export function CollapsedStrip({ label, onExpand }: { label: string; onExpand: () => void }) {
  return (
    <div className="hidden md:flex flex-col items-center gap-2 w-9 shrink-0 border-r border-border bg-card/30 py-3">
      <button onClick={onExpand} title={`Show ${label}`}
        className="h-6 w-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/50">
        <ChevronRight className="h-4 w-4" />
      </button>
      <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/70"
        style={{ writingMode: 'vertical-rl' }}>
        {label}
      </span>
    </div>
  );
}
