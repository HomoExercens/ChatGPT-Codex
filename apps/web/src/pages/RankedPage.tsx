import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trophy } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { readShareVariants } from '../lib/shareVariants';
import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';
import type { BlueprintOut, MatchDetail, MatchRow, Mode, ModifiersMeta, QueueResponse } from '../api/types';

export const RankedPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const lang = useSettingsStore((s) => s.language);
  const t = useMemo(() => TRANSLATIONS[lang].common, [lang]);

  const initialMode = (searchParams.get('mode') as Mode | null) ?? '1v1';
  const [mode, setMode] = useState<Mode>(initialMode === 'team' ? 'team' : '1v1');

  const { data: blueprints = [] } = useQuery({
    queryKey: ['blueprints'],
    queryFn: () => apiFetch<BlueprintOut[]>('/api/blueprints'),
  });

  const submitted = useMemo(
    () => blueprints.filter((b) => b.status === 'submitted' && b.mode === mode),
    [blueprints, mode]
  );
  const [selectedBlueprintId, setSelectedBlueprintId] = useState<string>('');

  useEffect(() => {
    if (submitted.some((b) => b.id === selectedBlueprintId)) return;
    setSelectedBlueprintId(submitted[0]?.id ?? '');
  }, [selectedBlueprintId, submitted]);

  const { data: matches = [] } = useQuery({
    queryKey: ['matches', mode],
    queryFn: () => apiFetch<MatchRow[]>(`/api/matches?mode=${encodeURIComponent(mode)}`),
  });

  const { data: modifiersMeta } = useQuery({
    queryKey: ['metaModifiers'],
    queryFn: () => apiFetch<ModifiersMeta>('/api/meta/modifiers'),
    staleTime: 60 * 60 * 1000,
  });

  const portalName = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of modifiersMeta?.portals ?? []) map.set(p.id, p.name);
    return (id?: string | null) => (id ? map.get(id) ?? id : null);
  }, [modifiersMeta?.portals]);

  const augmentName = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of modifiersMeta?.augments ?? []) map.set(a.id, a.name);
    return (id?: string | null) => (id ? map.get(id) ?? id : null);
  }, [modifiersMeta?.augments]);

  const [activeMatchId, setActiveMatchId] = useState<string | null>(null);
  const autoOpen = searchParams.get('auto') === '1';

  useEffect(() => {
    const mParam = (searchParams.get('mode') as Mode | null) ?? null;
    if (mParam === 'team' || mParam === '1v1') setMode(mParam);
    const matchParam = searchParams.get('match_id');
    if (matchParam) setActiveMatchId(matchParam);
  }, [searchParams]);

  const queueMutation = useMutation({
    mutationFn: () =>
      apiFetch<QueueResponse>('/api/ranked/queue', {
        method: 'POST',
        body: JSON.stringify({ blueprint_id: selectedBlueprintId, seed_set_count: 3, ...readShareVariants() }),
      }),
    onSuccess: async (data) => {
      setActiveMatchId(data.match_id);
      await queryClient.invalidateQueries({ queryKey: ['matches', mode] });
      await queryClient.invalidateQueries({ queryKey: ['homeSummary'] });
    },
  });

  const queued = queueMutation.data;

  const { data: activeMatch } = useQuery({
    queryKey: ['match', activeMatchId],
    queryFn: () => apiFetch<MatchDetail>(`/api/matches/${activeMatchId}`),
    enabled: Boolean(activeMatchId),
    refetchInterval: (query) => {
      const data = query.state.data as MatchDetail | undefined;
      if (!data) return 800;
      if (data.status === 'done' || data.status === 'failed') return false;
      return 800;
    },
  });

  useEffect(() => {
    if (!activeMatch) return;
    if (activeMatch.status === 'done' || activeMatch.status === 'failed') {
      queryClient.invalidateQueries({ queryKey: ['matches', mode] });
      queryClient.invalidateQueries({ queryKey: ['homeSummary'] });
    }
    if (autoOpen && activeMatch.status === 'done' && activeMatchId) {
      const next = new URLSearchParams(searchParams);
      next.delete('auto');
      setSearchParams(next, { replace: true });
      navigate(`/replay/${encodeURIComponent(activeMatchId)}`);
    }
  }, [activeMatch, activeMatchId, autoOpen, mode, navigate, queryClient, searchParams, setSearchParams]);

  const statusBadgeVariant = (status: string): 'info' | 'warning' | 'success' | 'error' | 'neutral' => {
    if (status === 'done') return 'success';
    if (status === 'running') return 'warning';
    if (status === 'failed') return 'error';
    if (status === 'queued') return 'info';
    return 'neutral';
  };

  const opponentBadgeVariant = (t: 'human' | 'bot'): 'info' | 'neutral' => {
    if (t === 'human') return 'info';
    return 'neutral';
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <Card className="lg:col-span-5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trophy size={18} className="text-brand-600" /> {t.enterRanked}
          </CardTitle>
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
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">{t.targetBlueprint}</label>
            <select
              className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none"
              value={selectedBlueprintId}
              onChange={(e) => setSelectedBlueprintId(e.target.value)}
            >
              {submitted.length === 0 ? <option value="">No submitted blueprints</option> : null}
              {submitted.map((bp) => (
                <option key={bp.id} value={bp.id}>
                  {bp.name} ({bp.mode})
                </option>
              ))}
            </select>
            <p className="text-[10px] text-slate-500 mt-2">
              Seeded demo: select{' '}
              <span className="font-mono">{mode === 'team' ? 'bp_demo_team_mechline' : 'bp_demo_1v1'}</span> and queue.
            </p>
          </div>

          <Button
            className="w-full h-12 text-lg shadow-brand-500/20"
            disabled={!selectedBlueprintId || queueMutation.isPending}
            isLoading={queueMutation.isPending}
            onClick={() => queueMutation.mutate()}
          >
            {t.enterRanked}
          </Button>

          {queueMutation.error ? (
            <div className="text-xs text-red-600 break-words">{String(queueMutation.error)}</div>
          ) : null}

          {activeMatchId ? (
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-slate-600">Queue</span>
                <Badge variant={statusBadgeVariant(activeMatch?.status ?? queued?.status ?? 'queued')}>
                  {activeMatch?.status ?? queued?.status ?? 'queued'}
                </Badge>
              </div>
              {activeMatch ? (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Opponent</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (!activeMatch.user_b || activeMatch.user_b === 'unknown') return;
                        navigate(`/profile/${encodeURIComponent(activeMatch.user_b)}?mode=${encodeURIComponent(mode)}`);
                      }}
                      className="text-xs font-semibold text-slate-800 hover:underline"
                      aria-label="Open opponent profile"
                    >
                      {activeMatch.opponent_display_name}
                    </button>
                    <Badge variant={opponentBadgeVariant(activeMatch.opponent_type)}>
                      {activeMatch.opponent_type.toUpperCase()}
                    </Badge>
                    {activeMatch.opponent_type === 'human' && activeMatch.opponent_elo != null ? (
                      <span className="text-[10px] text-slate-500 font-mono">Elo {activeMatch.opponent_elo}</span>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {activeMatch?.matchmaking_reason ? (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Matchmaking</span>
                  <span className="text-[10px] text-slate-500">{activeMatch.matchmaking_reason}</span>
                </div>
              ) : null}
              {activeMatch?.portal_id ? (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Portal</span>
                  <Badge variant="neutral">{portalName(activeMatch.portal_id) ?? '—'}</Badge>
                </div>
              ) : null}
              {activeMatch?.augments_a?.length ? (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Augments</span>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {activeMatch.augments_a.slice(0, 3).map((a) => (
                      <Badge key={`${a.round}:${a.augment_id}`} variant="info">
                        {augmentName(a.augment_id) ?? a.augment_id}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="text-xs text-slate-600 font-mono break-all">match_id: {activeMatchId}</div>
              <div>
                <div className="flex justify-between items-center text-[10px] text-slate-500 mb-1">
                  <span>Progress</span>
                  <span className="font-mono">{activeMatch?.progress ?? queued?.progress ?? 0}%</span>
                </div>
                <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-600 transition-all"
                    style={{ width: `${activeMatch?.progress ?? queued?.progress ?? 0}%` }}
                  ></div>
                </div>
              </div>
              {activeMatch?.status === 'failed' ? (
                <div className="text-xs text-red-600 break-words">{activeMatch.error_message || 'Match failed'}</div>
              ) : null}
              {activeMatch?.status === 'done' ? (
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-500">Result</span>
                    <Badge
                      variant={
                        activeMatch.result === 'A' ? 'success' : activeMatch.result === 'B' ? 'error' : 'neutral'
                      }
                    >
                      {activeMatch.result}
                    </Badge>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-500">Elo Δ</span>
                    <span className="text-sm font-bold text-slate-800">
                      {activeMatch.elo_delta_a > 0 ? '+' : ''}
                      {activeMatch.elo_delta_a}
                    </span>
                  </div>
                  <Button variant="secondary" className="w-full" onClick={() => navigate(`/replay/${activeMatchId}`)}>
                    Open Replay
                  </Button>
                </div>
              ) : activeMatch?.status === 'failed' ? (
                <div className="space-y-2">
                  <Button
                    variant="secondary"
                    className="w-full"
                    disabled={!selectedBlueprintId || queueMutation.isPending}
                    isLoading={queueMutation.isPending}
                    onClick={() => queueMutation.mutate()}
                  >
                    {t.retry}
                  </Button>
                  <Button variant="outline" className="w-full" onClick={() => setActiveMatchId(null)}>
                    Clear Active Match
                  </Button>
                </div>
              ) : (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setActiveMatchId(null)}
                  disabled={activeMatch?.status === 'running'}
                >
                  Clear Active Match
                </Button>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="lg:col-span-7">
        <CardHeader>
          <CardTitle>{t.recentMatches}</CardTitle>
        </CardHeader>
        <div className="divide-y divide-slate-100">
          {matches.length === 0 ? (
            <CardContent>
              <div className="text-sm text-slate-500">No matches yet.</div>
            </CardContent>
          ) : (
            matches.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  if (m.status === 'done') navigate(`/replay/${m.id}`);
                  else setActiveMatchId(m.id);
                }}
                className="w-full text-left p-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <div className="font-bold text-slate-800">{m.opponent}</div>
                    <Badge variant={opponentBadgeVariant(m.opponent_type)}>{m.opponent_type.toUpperCase()}</Badge>
                    {m.opponent_type === 'human' && m.opponent_elo != null ? (
                      <span className="text-[10px] text-slate-500 font-mono">Elo {m.opponent_elo}</span>
                    ) : null}
                    {m.portal_id ? <Badge variant="neutral">{portalName(m.portal_id) ?? m.portal_id}</Badge> : null}
                  </div>
                  <div className="text-xs text-slate-500 font-mono">{m.id}</div>
                </div>
                <div className="flex items-center gap-3">
                  {m.status === 'done' && m.result ? (
                    <Badge variant={m.result === 'win' ? 'success' : m.result === 'loss' ? 'error' : 'neutral'}>{m.result}</Badge>
                  ) : (
                    <Badge variant={statusBadgeVariant(m.status)}>{m.status}</Badge>
                  )}
                  <span className="text-sm font-bold text-slate-800">
                    {m.status === 'done' ? (
                      <>
                        {m.elo_change > 0 ? '+' : ''}
                        {m.elo_change}
                      </>
                    ) : (
                      <span className="font-mono text-slate-500">{m.progress ?? 0}%</span>
                    )}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </Card>
    </div>
  );
};
