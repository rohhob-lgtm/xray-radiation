import { useQuery } from '@tanstack/react-query';
import {
  ListOrdered, LinkIcon, FileText, ScrollText, AlertTriangle,
  ShieldCheck, ShieldAlert, HardDrive, CalendarClock, SlidersHorizontal,
  Network,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

async function apiFetch(path: string) {
  const res = await fetch(`${API}${path}`, { credentials: 'include' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const QUALITY_COLORS: Record<string, string> = {
  authoritative: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  high_quality: 'text-cyan-400 border-cyan-500/30 bg-cyan-500/10',
  useful: 'text-blue-400 border-blue-500/30 bg-blue-500/10',
  low_confidence: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  rejected: 'text-red-400 border-red-500/30 bg-red-500/10',
};

function Empty({ label }: { label: string }) {
  return <p className="text-xs text-muted-foreground py-6 text-center">{label}</p>;
}

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</div>
      <div className="text-sm font-semibold mt-0.5">{value}</div>
    </div>
  );
}

export function AutonomousResearchDashboard({ missionId, mission }: { missionId: string; mission: any }) {
  const queueQuery = useQuery({
    queryKey: ['research-agent-queue', missionId],
    queryFn: () => apiFetch(`/api/research-agent/missions/${missionId}/queue`),
    refetchInterval: 5_000,
  });
  const sourcesQuery = useQuery({
    queryKey: ['research-agent-sources', missionId],
    queryFn: () => apiFetch(`/api/research-agent/missions/${missionId}/sources`),
    refetchInterval: 5_000,
  });
  const filesQuery = useQuery({
    queryKey: ['research-agent-files', missionId],
    queryFn: () => apiFetch(`/api/research-agent/missions/${missionId}/files`),
    refetchInterval: 5_000,
  });
  const activityQuery = useQuery({
    queryKey: ['research-agent-activity', missionId],
    queryFn: () => apiFetch(`/api/research-agent/missions/${missionId}/activity`),
    refetchInterval: 5_000,
  });
  const planQuery = useQuery({
    queryKey: ['research-brain-plan', missionId],
    queryFn: () => apiFetch(`/api/research-brain/missions/${missionId}/plan`),
    refetchInterval: 8_000,
  });
  const coverageQuery = useQuery({
    queryKey: ['research-brain-coverage', missionId],
    queryFn: () => apiFetch(`/api/research-brain/missions/${missionId}/coverage`),
    refetchInterval: 8_000,
  });

  const queue = queueQuery.data?.queue ?? [];
  const sources = sourcesQuery.data?.sources ?? [];
  const files = filesQuery.data?.files ?? [];
  const activity = activityQuery.data?.activity ?? [];
  const errors = activity.filter((a: any) => a.level === 'error');
  const acceptedSources = sources.filter((s: any) => s.accepted_into_kb);
  const rejectedSources = sources.filter((s: any) => !s.accepted_into_kb);

  const storageMb = ((mission?.storage_used_bytes ?? 0) / (1024 * 1024)).toFixed(2);
  const maxStorageMb = mission?.limits?.max_storage_mb ?? '—';

  const topics = planQuery.data?.topics ?? [];
  const plan = planQuery.data?.plan ?? null;
  const coverageByTopic: Record<string, any> = {};
  for (const c of coverageQuery.data?.coverage ?? []) coverageByTopic[c.topic_id] = c;
  const suggestions = coverageQuery.data?.suggestions ?? [];

  const coverageColor = (pct: number) =>
    pct >= 80 ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
    : pct < 40 ? 'text-red-400 border-red-500/30 bg-red-500/10'
    : 'text-amber-400 border-amber-500/30 bg-amber-500/10';

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-4">
      {/* Live status strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatChip label="Phase" value={mission?.current_phase ?? '—'} />
        <StatChip label="Pages Processed" value={mission?.pages_processed ?? 0} />
        <StatChip label="Files Ingested" value={mission?.files_ingested ?? 0} />
        <StatChip label="Files Rejected" value={mission?.files_rejected ?? 0} />
        <StatChip label="Duplicates Skipped" value={mission?.duplicates_skipped ?? 0} />
        <StatChip label="Trusted Sources" value={acceptedSources.length} />
        <StatChip label="Storage Used" value={`${storageMb} MB`} />
        <StatChip label="Estimated Cost" value={`$${(mission?.estimated_cost_usd ?? 0).toFixed(2)}`} />
      </div>
      {mission?.last_error && (
        <div className="flex items-start gap-2 text-xs text-red-400 border border-red-500/20 bg-red-500/10 rounded-lg px-3 py-2">
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          {mission.last_error}
        </div>
      )}

      <Tabs defaultValue="plan">
        <TabsList className="flex flex-wrap h-auto gap-1 bg-transparent p-0">
          <TabsTrigger value="plan" className="text-[11px] gap-1"><Network className="h-3 w-3" /> Research Plan ({topics.length})</TabsTrigger>
          <TabsTrigger value="queue" className="text-[11px] gap-1"><ListOrdered className="h-3 w-3" /> Queue ({queue.length})</TabsTrigger>
          <TabsTrigger value="sources" className="text-[11px] gap-1"><LinkIcon className="h-3 w-3" /> Sources ({sources.length})</TabsTrigger>
          <TabsTrigger value="files" className="text-[11px] gap-1"><FileText className="h-3 w-3" /> Files ({files.length})</TabsTrigger>
          <TabsTrigger value="rejected" className="text-[11px] gap-1"><ShieldAlert className="h-3 w-3" /> Rejected ({rejectedSources.length})</TabsTrigger>
          <TabsTrigger value="activity" className="text-[11px] gap-1"><ScrollText className="h-3 w-3" /> Activity Log</TabsTrigger>
          <TabsTrigger value="errors" className="text-[11px] gap-1"><AlertTriangle className="h-3 w-3" /> Errors ({errors.length})</TabsTrigger>
          <TabsTrigger value="schedule" className="text-[11px] gap-1"><CalendarClock className="h-3 w-3" /> Schedule</TabsTrigger>
          <TabsTrigger value="settings" className="text-[11px] gap-1"><SlidersHorizontal className="h-3 w-3" /> Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="plan">
          {plan?.normalized_understanding && (
            <div className="text-xs text-muted-foreground mb-2">
              Template: <span className="font-medium text-foreground">{plan.normalized_understanding.template}</span>
              {plan.normalized_understanding.matched_manufacturer && (
                <> · Manufacturer: <span className="font-medium text-foreground">{plan.normalized_understanding.matched_manufacturer}</span></>
              )}
            </div>
          )}
          <ScrollArea className="h-64">
            {topics.length === 0 ? <Empty label="Building the research plan…" /> : (
              <div className="space-y-1.5 pr-2">
                {topics.map((t: any) => {
                  const coverage = coverageByTopic[t.id]?.coverage_pct ?? t.coverage_pct ?? 0;
                  return (
                    <div key={t.id} className="text-xs border border-border/60 rounded-lg px-2.5 py-1.5 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{t.label}</span>
                        <Badge variant="outline" className={`text-[10px] shrink-0 ${coverageColor(coverage)}`}>
                          {coverage}% coverage
                        </Badge>
                      </div>
                      <div className="text-muted-foreground">
                        rank {t.rank} · status {t.status} · ~{t.estimates?.expected_sources ?? '—'} expected sources
                      </div>
                      {(t.research_questions || []).length > 0 && (
                        <ul className="text-muted-foreground list-disc list-inside">
                          {t.research_questions.map((q: string, i: number) => <li key={i}>{q}</li>)}
                        </ul>
                      )}
                    </div>
                  );
                })}
                {suggestions.length > 0 && (
                  <div className="border border-amber-500/20 bg-amber-500/10 rounded-lg px-2.5 py-1.5 text-amber-400 space-y-1">
                    {suggestions.map((s: any) => <div key={s.topic_id}>{s.suggestion}</div>)}
                  </div>
                )}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="queue">
          <ScrollArea className="h-64">
            {queue.length === 0 ? <Empty label="No URLs queued yet." /> : (
              <div className="space-y-1.5 pr-2">
                {queue.map((q: any) => (
                  <div key={q.id} className="flex items-center justify-between gap-2 text-xs border border-border/60 rounded-lg px-2.5 py-1.5">
                    <span className="truncate flex-1" title={q.url}>{q.url}</span>
                    <Badge variant="outline" className="text-[10px] shrink-0">{q.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="sources">
          <ScrollArea className="h-64">
            {sources.length === 0 ? <Empty label="No sources discovered yet." /> : (
              <div className="space-y-1.5 pr-2">
                {sources.map((s: any) => (
                  <div key={s.id} className="text-xs border border-border/60 rounded-lg px-2.5 py-1.5 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate flex-1 font-medium" title={s.title}>{s.title || s.url}</span>
                      <Badge variant="outline" className={`text-[10px] shrink-0 ${QUALITY_COLORS[s.quality_label] ?? ''}`}>
                        {s.quality_label} · {s.quality_score}
                      </Badge>
                    </div>
                    <div className="text-muted-foreground truncate">{s.domain}</div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="files">
          <ScrollArea className="h-64">
            {files.length === 0 ? <Empty label="No files ingested yet." /> : (
              <div className="space-y-1.5 pr-2">
                {files.map((f: any) => (
                  <div key={f.id} className="flex items-center justify-between gap-2 text-xs border border-border/60 rounded-lg px-2.5 py-1.5">
                    <span className="truncate flex-1" title={f.filename}>{f.filename}</span>
                    <span className="text-muted-foreground shrink-0">{(f.size_bytes / 1024).toFixed(1)} KB</span>
                    <Badge variant="outline" className="text-[10px] shrink-0">{f.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="rejected">
          <ScrollArea className="h-64">
            {rejectedSources.length === 0 ? <Empty label="Nothing held for review." /> : (
              <div className="space-y-1.5 pr-2">
                {rejectedSources.map((s: any) => (
                  <div key={s.id} className="text-xs border border-border/60 rounded-lg px-2.5 py-1.5 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate flex-1 font-medium" title={s.title}>{s.title || s.url}</span>
                      <Badge variant="outline" className={`text-[10px] shrink-0 ${QUALITY_COLORS[s.quality_label] ?? ''}`}>
                        {s.quality_label} · {s.quality_score}
                      </Badge>
                    </div>
                    <div className="text-muted-foreground">{(s.quality_reasons || []).join(' · ')}</div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="activity">
          <ScrollArea className="h-64">
            {activity.length === 0 ? <Empty label="No activity yet." /> : (
              <div className="space-y-1 pr-2">
                {activity.map((a: any) => (
                  <div key={a.id} className="flex items-start gap-2 text-xs">
                    <span className={`shrink-0 mt-0.5 h-1.5 w-1.5 rounded-full ${
                      a.level === 'error' ? 'bg-red-400' : a.level === 'warning' ? 'bg-amber-400' : 'bg-emerald-400'
                    }`} />
                    <span className="text-muted-foreground">{new Date(a.created_at).toLocaleTimeString()}</span>
                    <span className="flex-1">{a.message}</span>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="errors">
          <ScrollArea className="h-64">
            {errors.length === 0 ? <Empty label="No errors." /> : (
              <div className="space-y-1.5 pr-2">
                {errors.map((a: any) => (
                  <div key={a.id} className="text-xs text-red-400 border border-red-500/20 bg-red-500/10 rounded-lg px-2.5 py-1.5">
                    {a.message}
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="schedule">
          <div className="text-xs space-y-2 pt-2">
            {mission?.schedule ? (
              <>
                <div>Frequency: <span className="font-medium">{mission.schedule.frequency}</span></div>
                <div>Next run: <span className="font-medium">{mission.schedule.next_run_at ?? 'Not scheduled yet'}</span></div>
                <div>Last run: <span className="font-medium">{mission.last_run_at ?? 'Never'}</span></div>
              </>
            ) : (
              <Empty label="This mission does not run on a recurring schedule (Continuous Learning mode only)." />
            )}
          </div>
        </TabsContent>

        <TabsContent value="settings">
          <div className="grid grid-cols-2 gap-2 pt-2 text-xs">
            <StatChip label="Max Pages" value={mission?.limits?.max_pages ?? '—'} />
            <StatChip label="Max Files" value={mission?.limits?.max_files ?? '—'} />
            <StatChip label="Max Storage" value={`${maxStorageMb} MB`} />
            <StatChip label="Max Depth" value={mission?.limits?.max_depth ?? '—'} />
            <StatChip label="Min Relevance" value={mission?.limits?.min_relevance_score ?? '—'} />
            <StatChip label="Min Quality" value={mission?.limits?.min_quality_score ?? '—'} />
            <StatChip label="Free Mode" value={mission?.free_mode ? 'ON' : 'OFF'} />
            <StatChip label="Languages" value={(mission?.languages || []).join(', ') || '—'} />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
