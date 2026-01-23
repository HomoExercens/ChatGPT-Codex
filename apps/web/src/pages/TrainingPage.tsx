import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, BrainCircuit, Pause, Play, Settings2, Square, Wand2 } from 'lucide-react';
import { Line, LineChart, ResponsiveContainer, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts';

import { Button, Card, CardContent, CardHeader, CardTitle, Slider } from '../components/ui';
import { apiFetch } from '../lib/api';
import { useLabsEnabled } from '../lib/labs';
import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';
import type { Mode } from '../api/types';

type TrainingRun = {
  id: string;
  mode: '1v1' | 'team';
  plan: string;
  budget_tokens: number;
  status: string;
  progress: number;
  metrics: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type CheckpointList = {
  checkpoints: Array<{
    id: string;
    step: number;
    metrics: Record<string, unknown>;
    artifact_path: string | null;
    created_at: string;
  }>;
};

type ToBlueprintResponse = { blueprint_id: string; spec_hash: string };

type BenchmarkResponse = {
  summary: { wins: number; losses: number; draws: number };
  results: Array<{
    bot_id: string;
    bot_name: string;
    winner: 'A' | 'B' | 'draw';
  }>;
  candidate_spec_hash: string;
};

function formatStatus(status: string): { label: string; tone: 'neutral' | 'info' | 'warning' | 'error' | 'success' } {
  if (status === 'queued') return { label: 'Queued', tone: 'neutral' };
  if (status === 'running') return { label: 'Running', tone: 'info' };
  if (status === 'paused') return { label: 'Paused', tone: 'warning' };
  if (status === 'stopped') return { label: 'Stopped', tone: 'warning' };
  if (status === 'failed') return { label: 'Failed', tone: 'error' };
  if (status === 'done') return { label: 'Done', tone: 'success' };
  return { label: status || 'Idle', tone: 'neutral' };
}

function timeAgo(iso: string | undefined): string {
  if (!iso) return '—';
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return '—';
  const diffSec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export const TrainingPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const lang = useSettingsStore((s) => s.language);
  const t = TRANSLATIONS[lang].common;
  const labsEnabled = useLabsEnabled();

  if (!labsEnabled) {
    return (
      <div className="max-w-xl mx-auto">
        <Card>
          <CardHeader>
            <CardTitle>{lang === 'ko' ? 'Labs: 훈련 기능 비활성' : 'Labs: Training disabled'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-sm text-slate-600">
              {lang === 'ko'
                ? '프리뷰 기본 루프(Play → Beat This → Reply)에 필요한 기능이 아니므로 기본 UI에서 숨겨져 있습니다.'
                : 'Training is hidden by default in preview. It’s not required for the core loop (Play → Beat This → Reply).'}
            </div>
            <div className="text-xs text-slate-500 font-mono">
              {lang === 'ko'
                ? 'Labs를 켜려면: URL에 ?labs=1 추가 또는 VITE_ENABLE_LABS=1'
                : 'Enable labs: add ?labs=1 to the URL or set VITE_ENABLE_LABS=1'}
            </div>
            <div className="flex gap-2 pt-2">
              <Button onClick={() => navigate('/play')}>{lang === 'ko' ? '플레이로' : 'Go to Play'}</Button>
              <Button variant="secondary" onClick={() => navigate('/me')}>
                {lang === 'ko' ? '프로필' : 'Profile'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const [activeTab, setActiveTab] = useState<'overview' | 'runs'>('overview');
  const [mode, setMode] = useState<Mode>('1v1');
  const [budget, setBudget] = useState(500);
  const [selectedPlan, setSelectedPlan] = useState<string>('Stable');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [compareA, setCompareA] = useState<string | null>(null);
  const [compareB, setCompareB] = useState<string | null>(null);
  const [benchmarkFor, setBenchmarkFor] = useState<string | null>(null);
  const [benchmarks, setBenchmarks] = useState<Record<string, BenchmarkResponse>>({});

  const { data: runs = [] } = useQuery({
    queryKey: ['trainingRuns'],
    queryFn: () => apiFetch<TrainingRun[]>('/api/training/runs'),
    refetchInterval: 2000,
  });

  const runId = activeRunId ?? runs[0]?.id ?? null;

  const { data: run } = useQuery({
    queryKey: ['trainingRun', runId],
    queryFn: () => apiFetch<TrainingRun>(`/api/training/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 1000 : 4000),
  });

  const { data: checkpoints } = useQuery({
    queryKey: ['trainingRun', runId, 'checkpoints'],
    queryFn: () => apiFetch<CheckpointList>(`/api/training/runs/${runId}/checkpoints`),
    enabled: Boolean(runId),
    refetchInterval: 2000,
  });

  const startMutation = useMutation({
    mutationFn: () =>
      apiFetch<TrainingRun>('/api/training/runs', {
        method: 'POST',
        body: JSON.stringify({ mode, plan: selectedPlan, budget_tokens: budget }),
      }),
    onSuccess: async (created) => {
      setActiveRunId(created.id);
      await queryClient.invalidateQueries({ queryKey: ['trainingRuns'] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => apiFetch(`/api/training/runs/${runId}/pause`, { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['trainingRun', runId] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: () => apiFetch(`/api/training/runs/${runId}/resume`, { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['trainingRun', runId] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: () => apiFetch(`/api/training/runs/${runId}/stop`, { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['trainingRun', runId] });
    },
  });

  const toBlueprintMutation = useMutation({
    mutationFn: async (checkpointId: string) => {
      if (!runId) throw new Error('No training run selected');
      return apiFetch<ToBlueprintResponse>(`/api/training/runs/${runId}/to-blueprint`, {
        method: 'POST',
        body: JSON.stringify({ name: `Trained ${selectedPlan} @ ${checkpointId}`, checkpoint_id: checkpointId }),
      });
    },
    onSuccess: async (res) => {
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] });
      navigate(`/forge/${encodeURIComponent(res.blueprint_id)}`);
    },
  });

  const benchmarkMutation = useMutation({
    mutationFn: async (checkpointId: string) => {
      if (!runId) throw new Error('No training run selected');
      return apiFetch<BenchmarkResponse>(`/api/training/runs/${runId}/benchmark`, {
        method: 'POST',
        body: JSON.stringify({ checkpoint_id: checkpointId }),
      });
    },
    onMutate: (checkpointId) => {
      setBenchmarkFor(checkpointId);
    },
    onSuccess: (data, checkpointId) => {
      setBenchmarks((prev) => ({ ...prev, [checkpointId]: data }));
      setBenchmarkFor(checkpointId);
    },
  });

  const chartData = useMemo(() => {
    const list = checkpoints?.checkpoints ?? [];
    const rows = [...list].reverse();
    return rows.map((c) => {
      const mean = Number((c.metrics as any).episode_return_mean ?? (c.metrics as any).episode_reward_mean ?? 0);
      return {
        step: c.step,
        winRate: mean * 100,
        loss: Number((c.metrics as any).loss ?? 0),
      };
    });
  }, [checkpoints?.checkpoints]);

  const trainingState = run?.status ?? 'idle';
  const progress = run?.progress ?? 0;
  const estWin = chartData.length > 0 ? chartData[chartData.length - 1].winRate : undefined;
  const loss = chartData.length > 0 ? chartData[chartData.length - 1].loss : undefined;
  const prevWin = chartData.length > 1 ? chartData[chartData.length - 2].winRate : undefined;
  const winDelta = estWin !== undefined && prevWin !== undefined ? estWin - prevWin : undefined;
  const stability = useMemo(() => {
    const recent = chartData.slice(-3).map((d) => d.winRate);
    if (recent.length < 2) return undefined;
    const mean = recent.reduce((acc, v) => acc + v, 0) / recent.length;
    const variance = recent.reduce((acc, v) => acc + (v - mean) ** 2, 0) / recent.length;
    return Math.sqrt(variance);
  }, [chartData]);
  const episodes = Number((run?.metrics as any)?.num_episodes ?? 0);
  const sampledSteps = Number((run?.metrics as any)?.num_env_steps_sampled_lifetime ?? 0);
  const statusChip = formatStatus(trainingState);
  const errorMsg = (run?.metrics as any)?.error ? String((run?.metrics as any)?.error) : null;
  const canStartNew =
    trainingState === 'idle' ||
    trainingState === 'done' ||
    trainingState === 'failed' ||
    trainingState === 'stopped' ||
    !runId;
  const progressTone =
    trainingState === 'done'
      ? 'bg-green-500'
      : trainingState === 'failed'
        ? 'bg-red-500'
        : trainingState === 'stopped'
          ? 'bg-slate-400'
          : 'bg-brand-500';

  const plans = [
    { id: 'Stable', label: t.planStable, icon: '🛡️', desc: t.descStable },
    { id: 'Aggressive', label: t.planAggro, icon: '⚔️', desc: t.descAggro },
    { id: 'Counter', label: t.planCounter, icon: '🎯', desc: t.descCounter },
    { id: 'Exploratory', label: t.planExplore, icon: '🧪', desc: t.descExplore },
  ];

  const compareData = useMemo(() => {
    if (!compareA || !compareB || compareA === compareB) return null;
    const a = benchmarks[compareA];
    const b = benchmarks[compareB];

    const mapA = new Map((a?.results ?? []).map((r) => [r.bot_id, r] as const));
    const mapB = new Map((b?.results ?? []).map((r) => [r.bot_id, r] as const));

    const rows: Array<{ bot_id: string; bot_name: string; a?: 'A' | 'B' | 'draw'; b?: 'A' | 'B' | 'draw' }> = [];
    const ids = new Set<string>([...Array.from(mapA.keys()), ...Array.from(mapB.keys())]);
    for (const bot_id of ids) {
      const ra = mapA.get(bot_id);
      const rb = mapB.get(bot_id);
      rows.push({
        bot_id,
        bot_name: ra?.bot_name ?? rb?.bot_name ?? bot_id,
        a: ra?.winner,
        b: rb?.winner,
      });
    }
    rows.sort((x, y) => x.bot_name.localeCompare(y.bot_name));

    return { a, b, rows };
  }, [benchmarks, compareA, compareB]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-140px)]">
      <div className="lg:col-span-4 flex flex-col gap-6 overflow-y-auto pr-2">
        <Card className="flex-1 flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BrainCircuit size={20} className="text-brand-600" />
              {t.trainingConfig}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6 flex-1">
            {runs.length > 0 ? (
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 block">Run</label>
                <select
                  className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none"
                  value={runId ?? ''}
                  onChange={(e) => setActiveRunId(e.target.value || null)}
                >
                  {runs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.id.slice(0, 10)}… ({r.mode}, {r.status}, {r.progress}%)
                    </option>
                  ))}
                </select>
                <div className="mt-2 text-[10px] text-slate-400 flex justify-between">
                  <span>Retries: 0</span>
                  <span>Updated: {timeAgo(run?.updated_at)}</span>
                </div>
              </div>
            ) : null}

            <div>
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 block">Mode</label>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant={mode === '1v1' ? 'primary' : 'secondary'}
                  onClick={() => setMode('1v1')}
                  aria-pressed={mode === '1v1'}
                  type="button"
                >
                  1v1
                </Button>
                <Button
                  size="sm"
                  variant={mode === 'team' ? 'primary' : 'secondary'}
                  onClick={() => setMode('team')}
                  aria-pressed={mode === 'team'}
                  type="button"
                >
                  Team (3v3)
                </Button>
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 block">{t.trainingPlan}</label>
              <div className="grid grid-cols-2 gap-3">
                {plans.map((plan) => (
                  <button
                    key={plan.id}
                    onClick={() => setSelectedPlan(plan.id)}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      selectedPlan === plan.id ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-slate-200 hover:bg-slate-50'
                    }`}
                    type="button"
                  >
                    <div className="text-xl mb-1">{plan.icon}</div>
                    <div className="font-bold text-sm text-slate-800">{plan.label}</div>
                    <div className="text-[10px] text-slate-500 leading-tight mt-1">{plan.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
              <div className="flex justify-between items-center mb-2">
                <label className="text-xs font-bold text-slate-700">{t.computeBudget}</label>
                <span className="text-xs font-mono bg-white px-2 py-0.5 rounded border border-slate-200 text-brand-600">
                  {budget} {t.tokens}
                </span>
              </div>
              <Slider min={100} max={2000} step={50} value={budget} onChange={(e) => setBudget(parseInt(e.target.value))} />
              <div className="mt-2 text-[10px] text-slate-400 flex justify-between">
                <span>{t.quickCheck}</span>
                <span>{t.deepLearning}</span>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 flex gap-3">
              {canStartNew ? (
                <Button className="w-full h-12 text-lg shadow-brand-500/20" onClick={() => startMutation.mutate()} isLoading={startMutation.isPending}>
                  <Play size={20} className="mr-2 fill-current" /> {t.startExperiment}
                </Button>
              ) : (
                <>
                  <Button variant="secondary" className="w-full" onClick={() => (trainingState === 'paused' ? resumeMutation.mutate() : pauseMutation.mutate())}>
                    {trainingState === 'paused' ? (
                      <>
                        <Play size={20} className="mr-1" /> {t.resume}
                      </>
                    ) : (
                      <>
                        <Pause size={20} className="mr-1" /> {t.pause}
                      </>
                    )}
                  </Button>
                  <Button variant="destructive" className="w-full" onClick={() => stopMutation.mutate()}>
                    <Square size={20} className="fill-current mr-1" /> {t.stop}
                  </Button>
                </>
              )}
            </div>

            {startMutation.error ? <div className="text-xs text-red-600 break-words">{String(startMutation.error)}</div> : null}
            {trainingState === 'failed' && errorMsg ? (
              <div className="text-xs text-red-700 bg-red-50 border border-red-100 rounded-xl p-3">
                <div className="font-bold mb-1">Training failed</div>
                <div className="break-words">{errorMsg}</div>
                <div className="mt-2 text-[10px] text-red-700/70">Retries are disabled (0). Try lowering budget or switching plan.</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setBudget((b) => Math.max(100, Math.floor((b * 0.6) / 50) * 50))}
                  >
                    Lower budget
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setSelectedPlan('Stable')}>
                    Switch to Stable
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setActiveTab('overview')}>
                    View logs
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="lg:col-span-8 flex flex-col gap-6">
        <div className="flex items-center gap-4 bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
          <div className="flex-1">
            <div className="flex justify-between text-sm mb-2">
              <span className="font-medium text-slate-700">
                {trainingState === 'idle'
                  ? t.readyToTrain
                  : trainingState === 'done'
                    ? t.trainingComplete
                    : trainingState === 'failed'
                      ? 'Training failed'
                      : trainingState === 'stopped'
                        ? 'Training stopped'
                        : t.trainingModel}
              </span>
              <span className="flex items-center gap-2">
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full border ${
                    statusChip.tone === 'success'
                      ? 'bg-green-50 text-green-700 border-green-200'
                      : statusChip.tone === 'error'
                        ? 'bg-red-50 text-red-700 border-red-200'
                        : statusChip.tone === 'warning'
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : statusChip.tone === 'info'
                            ? 'bg-blue-50 text-blue-700 border-blue-200'
                            : 'bg-slate-50 text-slate-600 border-slate-200'
                  }`}
                >
                  {statusChip.label}
                </span>
                <span className="font-mono text-slate-500">{progress}%</span>
              </span>
            </div>
            <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden">
              <div className={`h-full transition-all duration-300 ${progressTone}`} style={{ width: `${progress}%` }}></div>
            </div>
            <div className="mt-2 flex justify-between text-xs text-slate-500">
              <span>
                {t.trend}:{' '}
                {winDelta === undefined ? (
                  '—'
                ) : (
                  <span className={winDelta > 0 ? 'text-green-700' : winDelta < 0 ? 'text-red-700' : ''}>
                    {winDelta > 0 ? '+' : ''}
                    {winDelta.toFixed(1)}%
                  </span>
                )}
              </span>
              <span className="font-mono">
                {t.episodes}: {episodes || '—'} · steps: {Number.isFinite(sampledSteps) ? sampledSteps.toLocaleString() : '—'}
              </span>
            </div>
          </div>
          <div className="hidden md:flex gap-4 border-l border-slate-100 pl-4">
            <div>
              <div className="text-[10px] uppercase text-slate-400 font-bold">{t.estWinrate}</div>
              <div className="text-lg font-bold text-slate-800">{estWin === undefined ? '--' : `${estWin.toFixed(1)}%`}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-slate-400 font-bold">{t.loss}</div>
              <div className="text-lg font-bold text-slate-800">{loss === undefined ? '--' : loss.toFixed(3)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-slate-400 font-bold">{t.trend}</div>
              <div
                className={`text-lg font-bold ${
                  winDelta === undefined ? 'text-slate-800' : winDelta > 0 ? 'text-green-700' : winDelta < 0 ? 'text-red-700' : 'text-slate-800'
                }`}
              >
                {winDelta === undefined ? '--' : `${winDelta > 0 ? '+' : ''}${winDelta.toFixed(1)}%`}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-slate-400 font-bold">{t.stability}</div>
              <div className="text-lg font-bold text-slate-800">{stability === undefined ? '--' : `±${stability.toFixed(1)}`}</div>
            </div>
          </div>
        </div>

        <Card className="flex-1 flex flex-col min-h-[400px]">
          <CardHeader className="flex justify-between">
            <div className="flex gap-4">
              <button
                onClick={() => setActiveTab('overview')}
                className={`text-sm font-medium pb-4 border-b-2 -mb-4 transition-colors ${
                  activeTab === 'overview' ? 'border-brand-500 text-brand-600' : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
                type="button"
              >
                {t.learningCurve}
              </button>
              <button
                onClick={() => setActiveTab('runs')}
                className={`text-sm font-medium pb-4 border-b-2 -mb-4 transition-colors ${
                  activeTab === 'runs' ? 'border-brand-500 text-brand-600' : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
                type="button"
              >
                {t.checkpoints}
              </button>
            </div>
            <Button variant="ghost" size="sm" aria-label="Training settings">
              <Settings2 size={16} />
            </Button>
          </CardHeader>
          <CardContent className="flex-1 relative">
            {activeTab === 'overview' ? (
              <>
                {chartData.length === 0 ? (
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
                    <Activity size={48} className="mb-4 opacity-50" />
                    <p>Start a training run to see real-time metrics</p>
                  </div>
                ) : (
                  <div className="w-full h-full min-h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData}>
                        <XAxis dataKey="step" hide />
                        <YAxis domain={[0, 100]} hide />
                        <RechartsTooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
                        <Line type="monotone" dataKey="winRate" stroke="#2563eb" strokeWidth={3} dot={false} animationDuration={200} />
                        <Line type="monotone" dataKey="loss" stroke="#ef4444" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                <div className="absolute bottom-4 left-4 right-4 h-32 bg-slate-900 rounded-xl p-3 font-mono text-xs text-green-400 overflow-hidden shadow-lg opacity-90">
                  <div className="opacity-50 mb-1"> {t.systemLogs}_</div>
                  <div className="space-y-1">
                    <p>
                      {'>'} run: <span className="text-white">{runId ?? '—'}</span>
                    </p>
                    <p>
                      {'>'} status: <span className="text-white">{trainingState}</span>
                    </p>
                    <p className="opacity-70">
                      {'>'} episodes: {Number.isFinite(episodes) && episodes > 0 ? episodes : '—'}
                    </p>
                    <p className="opacity-70">
                      {'>'} sampled_steps: {Number.isFinite(sampledSteps) && sampledSteps > 0 ? sampledSteps.toLocaleString() : '—'}
                    </p>
                    <p className="opacity-70">{'>'} checkpoints: {(checkpoints?.checkpoints ?? []).length}</p>
                  </div>
                </div>
              </>
            ) : (
              <div className="space-y-3">
                {(checkpoints?.checkpoints ?? []).length === 0 ? (
                  <div className="p-6 rounded-2xl border border-slate-200 bg-slate-50 flex flex-col items-start gap-3">
                    <div className="text-sm font-bold text-slate-800">No checkpoints yet</div>
                    <div className="text-sm text-slate-600">Start a run and the first checkpoint should appear within a few seconds.</div>
                    <Button onClick={() => startMutation.mutate()} disabled={startMutation.isPending}>
                      <Play size={16} className="mr-2" /> {t.startExperiment}
                    </Button>
                  </div>
                ) : (
                  <>
                    <div className="text-xs text-slate-500 flex justify-between">
                      <span>Select a checkpoint to convert into a Blueprint.</span>
                      <span className="font-mono">Retries: 0</span>
                    </div>

                    <div className="divide-y divide-slate-100 border border-slate-200 rounded-2xl overflow-hidden bg-white">
                      {(checkpoints?.checkpoints ?? []).map((c) => {
                        const mean = Number((c.metrics as any).episode_return_mean ?? (c.metrics as any).episode_reward_mean ?? 0);
                        const winRate = mean * 100;
                        const isA = compareA === c.id;
                        const isB = compareB === c.id;
                        const bench = benchmarks[c.id];
                        return (
                          <div key={c.id} className="p-4 flex flex-col gap-2">
                            <div className="flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <div className="font-bold text-slate-800">Checkpoint {c.step}</div>
                                <div className="text-xs text-slate-500 font-mono truncate">
                                  {c.id} · {timeAgo(c.created_at)}
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="text-[10px] uppercase text-slate-400 font-bold">{t.estWinrate}</div>
                                <div className="text-lg font-bold text-slate-800">{winRate.toFixed(1)}%</div>
                              </div>
                            </div>

                            <div className="flex flex-wrap items-center gap-2">
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => toBlueprintMutation.mutate(c.id)}
                                isLoading={toBlueprintMutation.isPending}
                              >
                                <Wand2 size={16} className="mr-2" /> To Blueprint
                              </Button>
                              <Button
                                size="sm"
                                variant={bench ? 'secondary' : 'ghost'}
                                onClick={() => benchmarkMutation.mutate(c.id)}
                                isLoading={benchmarkMutation.isPending && benchmarkFor === c.id}
                              >
                                Benchmark
                              </Button>
                              <button
                                type="button"
                                className={`text-xs px-2 py-1 rounded-lg border ${
                                  isA ? 'bg-brand-50 border-brand-200 text-brand-700' : 'bg-white border-slate-200 text-slate-600'
                                }`}
                                onClick={() => setCompareA(isA ? null : c.id)}
                              >
                                Compare A
                              </button>
                              <button
                                type="button"
                                className={`text-xs px-2 py-1 rounded-lg border ${
                                  isB ? 'bg-accent-200/30 border-accent-200 text-accent-700' : 'bg-white border-slate-200 text-slate-600'
                                }`}
                                onClick={() => setCompareB(isB ? null : c.id)}
                              >
                                Compare B
                              </button>
                            </div>

                            {bench ? (
                              <div className="mt-2 p-3 rounded-xl border border-slate-200 bg-slate-50 text-sm">
                                <div className="flex items-center justify-between gap-3">
                                  <div className="font-bold text-slate-800">
                                    Benchmark vs fixed bots: {bench.summary.wins}-{bench.summary.losses}-{bench.summary.draws}
                                  </div>
                                  <div className="text-[10px] font-mono text-slate-500">
                                    {bench.candidate_spec_hash.slice(0, 12)}…
                                  </div>
                                </div>

                                <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                                  {bench.results.map((r) => {
                                    const outcome = r.winner === 'A' ? 'W' : r.winner === 'B' ? 'L' : 'D';
                                    const tone =
                                      outcome === 'W'
                                        ? 'bg-green-50 text-green-700 border-green-200'
                                        : outcome === 'L'
                                          ? 'bg-red-50 text-red-700 border-red-200'
                                          : 'bg-slate-50 text-slate-700 border-slate-200';
                                    return (
                                      <div key={`${c.id}-${r.bot_id}`} className="flex items-center justify-between gap-2">
                                        <span className="text-slate-700 truncate">{r.bot_name}</span>
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${tone}`}>{outcome}</span>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>

                    {compareA && compareB && compareA !== compareB ? (
                      <div className="p-4 rounded-2xl border border-slate-200 bg-white">
                        <div className="text-sm font-bold text-slate-800 mb-2">A/B quick compare</div>
                        <div className="text-xs text-slate-600 font-mono">
                          A: {compareA.slice(0, 10)}… · B: {compareB.slice(0, 10)}…
                        </div>

                        {!compareData?.a || !compareData?.b ? (
                          <div className="mt-3 text-sm text-slate-600">
                            Run benchmarks for both checkpoints to compare matchups.
                            <div className="mt-2 flex flex-wrap gap-2">
                              {!compareData?.a ? (
                                <Button size="sm" variant="secondary" onClick={() => benchmarkMutation.mutate(compareA)}>
                                  Benchmark A
                                </Button>
                              ) : null}
                              {!compareData?.b ? (
                                <Button size="sm" variant="secondary" onClick={() => benchmarkMutation.mutate(compareB)}>
                                  Benchmark B
                                </Button>
                              ) : null}
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                              <div className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                                <div className="text-[10px] uppercase font-bold text-slate-400 mb-1">A Summary</div>
                                <div className="font-bold text-slate-800">
                                  {compareData.a.summary.wins}-{compareData.a.summary.losses}-{compareData.a.summary.draws}
                                </div>
                              </div>
                              <div className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                                <div className="text-[10px] uppercase font-bold text-slate-400 mb-1">B Summary</div>
                                <div className="font-bold text-slate-800">
                                  {compareData.b.summary.wins}-{compareData.b.summary.losses}-{compareData.b.summary.draws}
                                </div>
                              </div>
                            </div>

                            <div className="mt-3 text-xs text-slate-600">
                              <div className="font-bold text-slate-700 mb-2">Matchup diff (W/L/D)</div>
                              <div className="space-y-2">
                                {compareData.rows.map((r) => {
                                  const aOut = r.a === 'A' ? 'W' : r.a === 'B' ? 'L' : r.a === 'draw' ? 'D' : '—';
                                  const bOut = r.b === 'A' ? 'W' : r.b === 'B' ? 'L' : r.b === 'draw' ? 'D' : '—';
                                  return (
                                    <div key={`diff-${r.bot_id}`} className="flex items-center justify-between gap-3">
                                      <span className="truncate text-slate-700">{r.bot_name}</span>
                                      <span className="font-mono text-slate-500">
                                        A:{aOut} · B:{bOut}
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          </>
                        )}

                        <div className="mt-3 text-xs text-slate-500">
                          Convert each checkpoint to a blueprint and validate/submit in Forge for ranked.
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-slate-500">Select two different checkpoints to compare (A/B).</div>
                    )}
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
