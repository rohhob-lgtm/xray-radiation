import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Pause, StopCircle, RotateCcw, Loader2, MinusCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/hooks/use-toast';
import { AutonomousResearchDashboard } from './autonomous-research-dashboard';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${API}${path}`, { credentials: 'include', ...opts });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const DEPTH_MODES = [
  { id: 'quick_scan', label: 'Quick Scan', desc: 'A fast pass over the strongest sources' },
  { id: 'deep_research', label: 'Deep Research', desc: 'Broader query set, more sources' },
  { id: 'continuous_learning', label: 'Continuous Learning', desc: 'Repeats on a schedule' },
] as const;

const LANGUAGES = [
  { id: 'en', label: 'English' },
  { id: 'ar', label: 'Arabic' },
] as const;

const CONTENT_TYPES = [
  { id: 'web_pages', label: 'Web Pages' },
  { id: 'pdf', label: 'PDF' },
] as const;

const SCHEDULES = [
  { id: 'manual', label: 'Manual' },
  { id: '6h', label: 'Every 6 hours' },
  { id: 'daily', label: 'Daily' },
  { id: 'weekly', label: 'Weekly' },
] as const;

export function AutonomousResearchPanel({ onLearnDone }: { onLearnDone: () => void }) {
  const { toast } = useToast();
  const qc = useQueryClient();

  const [missionText, setMissionText] = useState('');
  const [mode, setMode] = useState<typeof DEPTH_MODES[number]['id']>('quick_scan');
  const [languages, setLanguages] = useState<string[]>(['en']);
  const [contentTypes, setContentTypes] = useState<string[]>(['web_pages']);
  const [freeMode, setFreeMode] = useState(true);
  const [scheduleFrequency, setScheduleFrequency] = useState<typeof SCHEDULES[number]['id']>('manual');
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');

  const missionQuery = useQuery({
    queryKey: ['research-agent-mission', activeMissionId],
    queryFn: () => apiFetch(`/api/research-agent/missions/${activeMissionId}`),
    enabled: !!activeMissionId,
    refetchInterval: (query) => {
      const status = (query.state.data as any)?.mission?.status;
      return status === 'running' || status === 'queued' ? 4_000 : 15_000;
    },
  });
  const mission = missionQuery.data?.mission;
  const isRunning = mission?.status === 'running' || mission?.status === 'queued';
  const isPaused = mission?.status === 'paused';
  const isTerminal = mission?.status === 'completed' || mission?.status === 'stopped' || mission?.status === 'failed';

  const toggleIn = (list: string[], id: string) =>
    list.includes(id) ? list.filter(v => v !== id) : [...list, id];

  const startMission = async () => {
    if (!missionText.trim()) return;
    setStarting(true);
    setError('');
    try {
      const data = await apiFetch('/api/research-agent/missions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mission_text: missionText.trim(),
          mode,
          languages,
          content_types: contentTypes,
          free_mode: freeMode,
          schedule_frequency: mode === 'continuous_learning' ? scheduleFrequency : 'manual',
        }),
      });
      setActiveMissionId(data.mission.id);
      toast({ title: 'Research mission started', description: data.message });
      qc.invalidateQueries({ queryKey: ['learning-stats'] });
      onLearnDone();
    } catch (e: any) {
      setError(e.message || 'Failed to start mission');
    } finally {
      setStarting(false);
    }
  };

  const runAction = async (action: 'pause' | 'resume' | 'stop') => {
    if (!activeMissionId) return;
    try {
      await apiFetch(`/api/research-agent/missions/${activeMissionId}/${action}`, { method: 'POST' });
      qc.invalidateQueries({ queryKey: ['research-agent-mission', activeMissionId] });
    } catch (e: any) {
      toast({ title: `Failed to ${action} mission`, description: e.message, variant: 'destructive' });
    }
  };

  const runInBackground = () => {
    toast({
      title: 'Running in background',
      description: 'The mission keeps running on the server — check back here anytime for status.',
    });
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider block">
          Research Mission
        </label>
        <Textarea
          placeholder='e.g. "Research and learn everything about X-ray security systems, radiation sources, and radiation safety"'
          value={missionText}
          onChange={e => setMissionText(e.target.value)}
          className="bg-muted border-border text-xs resize-y min-h-[70px]"
          disabled={!!activeMissionId && isRunning}
        />
      </div>

      <div>
        <label className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider mb-1.5 block">
          Research Level
        </label>
        <div className="grid grid-cols-3 gap-2">
          {DEPTH_MODES.map(m => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              disabled={!!activeMissionId && isRunning}
              className={`text-left rounded-lg border p-2.5 transition-all ${
                mode === m.id ? 'border-indigo-500 bg-indigo-500/10' : 'border-border hover:border-muted-foreground/40'
              }`}
            >
              <div className="text-xs font-semibold">{m.label}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {mode === 'continuous_learning' && (
        <div>
          <label className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider mb-1.5 block">
            Schedule Frequency
          </label>
          <div className="flex flex-wrap gap-1.5">
            {SCHEDULES.map(s => (
              <button
                key={s.id}
                onClick={() => setScheduleFrequency(s.id)}
                className={`px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                  scheduleFrequency === s.id
                    ? 'text-indigo-400 border-indigo-500'
                    : 'text-muted-foreground border-border hover:border-muted-foreground/40'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider mb-1.5 block">Languages</label>
          <div className="space-y-1.5">
            {LANGUAGES.map(l => (
              <label key={l.id} className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={languages.includes(l.id)}
                  onCheckedChange={() => setLanguages(prev => toggleIn(prev, l.id))}
                />
                {l.label}
              </label>
            ))}
          </div>
        </div>
        <div>
          <label className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider mb-1.5 block">Content Types</label>
          <div className="space-y-1.5">
            {CONTENT_TYPES.map(c => (
              <label key={c.id} className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={contentTypes.includes(c.id)}
                  onCheckedChange={() => setContentTypes(prev => toggleIn(prev, c.id))}
                />
                {c.label}
              </label>
            ))}
          </div>
        </div>
      </div>

      <label className="flex items-center gap-2 text-xs border border-border rounded-lg px-3 py-2">
        <Checkbox checked={freeMode} onCheckedChange={(v) => setFreeMode(!!v)} />
        <span className="font-medium">Free Mode</span>
        <span className="text-muted-foreground">— no paid APIs are ever called; Estimated Cost = $0.00</span>
      </label>

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="flex flex-wrap items-center gap-2">
        {!activeMissionId ? (
          <Button size="sm" onClick={startMission} disabled={!missionText.trim() || starting}>
            {starting ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Play className="h-3.5 w-3.5 mr-1.5" />}
            Start Research
          </Button>
        ) : (
          <>
            {isRunning && (
              <Button size="sm" variant="outline" onClick={() => runAction('pause')}>
                <Pause className="h-3.5 w-3.5 mr-1.5" /> Pause
              </Button>
            )}
            {isPaused && (
              <Button size="sm" variant="outline" onClick={() => runAction('resume')}>
                <Play className="h-3.5 w-3.5 mr-1.5" /> Resume
              </Button>
            )}
            {!isTerminal && (
              <Button size="sm" variant="outline" onClick={() => runAction('stop')}>
                <StopCircle className="h-3.5 w-3.5 mr-1.5" /> Stop
              </Button>
            )}
            {isRunning && (
              <Button size="sm" variant="ghost" onClick={runInBackground}>
                <MinusCircle className="h-3.5 w-3.5 mr-1.5" /> Run in Background
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => { setActiveMissionId(null); setMissionText(''); setError(''); }}
            >
              <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> New Mission
            </Button>
          </>
        )}
      </div>

      {activeMissionId && mission && (
        <AutonomousResearchDashboard missionId={activeMissionId} mission={mission} />
      )}
    </div>
  );
}
