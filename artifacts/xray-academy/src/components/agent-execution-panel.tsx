import { Check, Loader2, Circle, Wrench, AlertTriangle } from 'lucide-react';

export interface AgentEvent {
  type: 'stage' | 'tool_call' | 'tool_result';
  stage?: string;
  message?: string;
  tool?: string;
  ok?: boolean;
}

export interface AgentStageDef {
  key: string;
  label: string;
}

const DEFAULT_STAGES: AgentStageDef[] = [
  { key: 'understanding', label: 'Understanding request' },
  { key: 'inspecting', label: 'Inspecting workspace' },
  { key: 'planning', label: 'Planning task' },
  { key: 'processing', label: 'Processing files' },
  { key: 'validating', label: 'Validating output' },
  { key: 'completed', label: 'Completed' },
];

/** Concise execution status for an agent turn — stage checklist + short
 * tool-call labels. Never renders chain-of-thought, only the short
 * stage/tool strings the backend emits. `stages` defaults to the workspace
 * agent's own list so existing callers are unaffected; other agent flows
 * (e.g. the design+Drive orchestrator) pass their own stage list. */
export function AgentExecutionPanel({ events, stages = DEFAULT_STAGES }: { events: AgentEvent[]; stages?: AgentStageDef[] }) {
  const seenStages = events.filter((e) => e.type === 'stage').map((e) => e.stage!);
  const lastStage = seenStages[seenStages.length - 1];
  const toolEvents = events.filter((e) => e.type === 'tool_call' || e.type === 'tool_result');

  // Pair up tool_call/tool_result by order into {tool, status}
  const toolRows: { tool: string; status: 'running' | 'ok' | 'error' }[] = [];
  for (const e of toolEvents) {
    if (e.type === 'tool_call') {
      toolRows.push({ tool: e.tool || 'tool', status: 'running' });
    } else if (e.type === 'tool_result') {
      const row = [...toolRows].reverse().find((r) => r.tool === e.tool && r.status === 'running');
      if (row) row.status = e.ok ? 'ok' : 'error';
    }
  }

  return (
    <div className="w-full rounded-lg border border-primary/20 bg-card/60 px-3 py-2.5 space-y-1.5">
      {stages.map(({ key: stage, label }) => {
        const done = seenStages.includes(stage) && stage !== lastStage;
        const active = stage === lastStage;
        const pending = !seenStages.includes(stage);
        return (
          <div key={stage} className={`flex items-center gap-2 text-xs ${pending ? 'opacity-40' : ''}`}>
            {done || (active && stage === 'completed') ? (
              <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
            ) : active ? (
              <Loader2 className="h-3.5 w-3.5 text-primary animate-spin shrink-0" />
            ) : (
              <Circle className="h-3 w-3 text-muted-foreground/40 shrink-0" />
            )}
            <span className={active ? 'text-foreground font-medium' : 'text-muted-foreground'}>
              {label}
            </span>
          </div>
        );
      })}

      {toolRows.length > 0 && (
        <div className="pt-1.5 mt-1.5 border-t border-border/50 space-y-1">
          {toolRows.map((row, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px] font-mono text-muted-foreground">
              {row.status === 'running' ? (
                <Loader2 className="h-3 w-3 animate-spin shrink-0 text-primary" />
              ) : row.status === 'error' ? (
                <AlertTriangle className="h-3 w-3 shrink-0 text-amber-400" />
              ) : (
                <Wrench className="h-3 w-3 shrink-0 text-muted-foreground/70" />
              )}
              <span className="truncate">{row.tool}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
