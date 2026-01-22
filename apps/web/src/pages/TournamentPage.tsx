import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Star } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { useSettingsStore } from '../stores/settings';
import { TRANSLATIONS } from '../lib/translations';
import type { BlueprintOut, MatchDetail, Mode, QueueResponse, TournamentMe, TournamentRow, WeeklyTheme } from '../api/types';

export const TournamentPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const lang = useSettingsStore((s) => s.language);
  const t = useMemo(() => TRANSLATIONS[lang].common, [lang]);

  const [mode, setMode] = useState<Mode>('team');

  const { data: theme } = useQuery({
    queryKey: ['weeklyTheme'],
    queryFn: () => apiFetch<WeeklyTheme>('/api/meta/weekly'),
    staleTime: 60_000,
  });

  const weekId = theme?.week_id ?? '';

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

  const { data: me } = useQuery({
    queryKey: ['tournamentMe', weekId, mode],
    queryFn: () => apiFetch<TournamentMe>(`/api/tournament/me?week_id=${encodeURIComponent(weekId)}&mode=${encodeURIComponent(mode)}`),
    enabled: Boolean(weekId),
    staleTime: 5_000,
  });

  const { data: leaderboard = [] } = useQuery({
    queryKey: ['tournamentLeaderboard', weekId, mode],
    queryFn: () =>
      apiFetch<TournamentRow[]>(
        `/api/tournament/leaderboard?week_id=${encodeURIComponent(weekId)}&mode=${encodeURIComponent(mode)}&limit=50`,
      ),
    enabled: Boolean(weekId),
    staleTime: 5_000,
  });

  const [activeMatchId, setActiveMatchId] = useState<string | null>(null);

  const queueMutation = useMutation({
    mutationFn: () =>
      apiFetch<QueueResponse>('/api/tournament/queue', {
        method: 'POST',
        body: JSON.stringify({ blueprint_id: selectedBlueprintId, seed_set_count: 3 }),
      }),
    onSuccess: async (data) => {
      setActiveMatchId(data.match_id);
      await queryClient.invalidateQueries({ queryKey: ['matches', mode] });
      await queryClient.invalidateQueries({ queryKey: ['tournamentMe', weekId, mode] });
      await queryClient.invalidateQueries({ queryKey: ['tournamentLeaderboard', weekId, mode] });
    },
  });

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
      queryClient.invalidateQueries({ queryKey: ['tournamentMe', weekId, mode] });
      queryClient.invalidateQueries({ queryKey: ['tournamentLeaderboard', weekId, mode] });
    }
  }, [activeMatch, mode, queryClient, weekId]);

  const remaining = useMemo(() => {
    if (!me) return 0;
    return Math.max(0, (me.matches_counted_limit ?? 0) - (me.matches_counted ?? 0));
  }, [me]);

  const statusBadgeVariant = (status: string): 'info' | 'warning' | 'success' | 'error' | 'neutral' => {
    if (status === 'done') return 'success';
    if (status === 'running') return 'warning';
    if (status === 'failed') return 'error';
    if (status === 'queued') return 'info';
    return 'neutral';
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <Card className="lg:col-span-5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Star size={18} className="text-brand-600" /> Tournament
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
          {theme ? (
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-xs font-bold text-slate-600">Weekly Theme</div>
                <Badge variant="neutral" className="font-mono">
                  {theme.week_id}
                </Badge>
              </div>
              <div className="text-sm font-bold text-slate-800">{theme.name}</div>
              <div className="text-xs text-slate-600">{theme.description}</div>
              <div className="pt-2">
                <div className="text-xs text-slate-500 mb-1">Featured Portals</div>
                <div className="flex flex-wrap gap-1.5">
                  {theme.featured_portals.slice(0, 3).map((p) => (
                    <Badge key={p.id} variant="info">
                      {p.name}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="pt-2">
                <div className="text-xs text-slate-500 mb-1">Featured Augments</div>
                <div className="flex flex-wrap gap-1.5">
                  {theme.featured_augments.slice(0, 6).map((a) => (
                    <Badge key={a.id} variant="neutral">
                      {a.name}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Loading weekly theme…</div>
          )}

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
              Tournament does not change Elo. Your first {me?.matches_counted_limit ?? 10} matches are counted.
            </p>
          </div>

          <Button
            className="w-full h-12 text-lg shadow-brand-500/20"
            disabled={!selectedBlueprintId || queueMutation.isPending || !theme?.tournament_rules?.queue_open}
            isLoading={queueMutation.isPending}
            onClick={() => queueMutation.mutate()}
          >
            Queue Tournament Match
          </Button>

          {queueMutation.error ? <div className="text-xs text-red-600 break-words">{String(queueMutation.error)}</div> : null}

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-xl border border-slate-200 bg-white">
              <div className="text-xs text-slate-500">Points</div>
              <div className="text-2xl font-bold text-slate-900">{me?.points ?? 0}</div>
              <div className="text-[10px] text-slate-500">Rank: {me?.rank ?? '—'}</div>
            </div>
            <div className="p-3 rounded-xl border border-slate-200 bg-white">
              <div className="text-xs text-slate-500">Matches Left</div>
              <div className="text-2xl font-bold text-slate-900">{remaining}</div>
              <div className="text-[10px] text-slate-500">
                Counted: {me?.matches_counted ?? 0}/{me?.matches_counted_limit ?? 10}
              </div>
            </div>
          </div>

          {activeMatchId ? (
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-slate-600">Queue</span>
                <Badge variant={statusBadgeVariant(activeMatch?.status ?? 'queued')}>{activeMatch?.status ?? 'queued'}</Badge>
              </div>
              {activeMatch?.status === 'done' ? (
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-500">Result</span>
                  <Badge variant={activeMatch.result === 'A' ? 'success' : activeMatch.result === 'B' ? 'error' : 'neutral'}>
                    {activeMatch.result === 'A' ? 'win' : activeMatch.result === 'B' ? 'loss' : 'draw'}
                  </Badge>
                </div>
              ) : null}
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  onClick={() => queryClient.invalidateQueries({ queryKey: ['match', activeMatchId] })}
                  type="button"
                >
                  Refresh
                </Button>
                <Button
                  onClick={() => navigate(`/replay/${encodeURIComponent(activeMatchId)}`)}
                  disabled={!activeMatch || activeMatch.status !== 'done'}
                  type="button"
                >
                  Open Replay
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="lg:col-span-7">
        <CardHeader>
          <CardTitle>Leaderboard</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {leaderboard.length === 0 ? (
            <div className="p-4 text-sm text-slate-500">No tournament matches yet. Queue one to appear here.</div>
          ) : (
            <div className="divide-y divide-slate-100">
              {leaderboard.map((row) => (
                <div key={row.user_id} className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <Badge variant="neutral" className="font-mono">
                      #{row.rank}
                    </Badge>
                    <button
                      type="button"
                      className="font-bold text-slate-800 hover:underline truncate"
                      onClick={() => navigate(`/profile/${encodeURIComponent(row.user_id)}?mode=${encodeURIComponent(mode)}`)}
                    >
                      {row.display_name}
                    </button>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="info">{row.points} pts</Badge>
                    <span className="text-xs text-slate-500 font-mono">
                      {row.wins}-{row.losses}-{row.draws}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
