import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Swords, Trophy } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { useSettingsStore } from '../stores/settings';
import type { MatchDetail, Mode } from '../api/types';

type ChallengeOut = {
  id: string;
  kind: string;
  mode: Mode;
  ruleset_version: string;
  target_blueprint_id?: string | null;
  target_replay_id?: string | null;
  start_sec?: number | null;
  end_sec?: number | null;
  portal_id?: string | null;
  augments_a?: Array<Record<string, unknown>>;
  augments_b?: Array<Record<string, unknown>>;
  creator: { user_id?: string | null; display_name?: string | null };
  created_at: string;
  status: string;
  attempts_total: number;
  wins_total: number;
};

type ChallengeAcceptResponse = { attempt_id: string; match_id: string; status: 'queued' | 'running' };

type ChallengeLeaderboardRow = {
  rank: number;
  user_id: string;
  display_name: string;
  wins: number;
  attempts: number;
};

export const ChallengePage: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const challengeId = String(id || '');

  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  const { data: challenge, error: challengeError } = useQuery({
    queryKey: ['challenge', challengeId],
    queryFn: () => apiFetch<ChallengeOut>(`/api/challenges/${encodeURIComponent(challengeId)}`),
    enabled: Boolean(challengeId),
  });

  const { data: leaderboard } = useQuery({
    queryKey: ['challenge', challengeId, 'leaderboard'],
    queryFn: () => apiFetch<ChallengeLeaderboardRow[]>(`/api/challenges/${encodeURIComponent(challengeId)}/leaderboard?limit=20`),
    enabled: Boolean(challengeId),
    staleTime: 10_000,
  });

  const acceptMutation = useMutation({
    mutationFn: async () => {
      return apiFetch<ChallengeAcceptResponse>(`/api/challenges/${encodeURIComponent(challengeId)}/accept`, {
        method: 'POST',
        body: JSON.stringify({ seed_set_count: 1 }),
      });
    },
  });

  const matchId = acceptMutation.data?.match_id ?? null;

  const { data: match } = useQuery({
    queryKey: ['match', matchId],
    queryFn: () => apiFetch<MatchDetail>(`/api/matches/${encodeURIComponent(matchId || '')}`),
    enabled: Boolean(matchId),
    refetchInterval: (query) => {
      const data = query.state.data as MatchDetail | undefined;
      if (!data) return 2000;
      return data.status === 'done' || data.status === 'failed' ? false : 2000;
    },
  });

  useEffect(() => {
    if (!matchId) return;
    if (!match) return;
    if (match.status === 'done') {
      navigate(`/replay/${encodeURIComponent(matchId)}`);
    }
  }, [match, matchId, navigate]);

  const copyChallengeShareLink = async () => {
    if (!challengeId) return;
    const url = `${window.location.origin}/s/challenge/${encodeURIComponent(challengeId)}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopyStatus(lang === 'ko' ? '복사됨' : 'Copied');
    } catch {
      window.prompt('Copy link', url);
    }
    window.setTimeout(() => setCopyStatus(null), 1500);
  };

  if (!challengeId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Challenge</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-slate-600">Missing challenge id.</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-7 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Swords size={18} className="text-brand-600" /> {lang === 'ko' ? '도전' : 'Challenge'}
            </CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant="neutral">{challenge?.mode ?? '—'}</Badge>
              {challenge?.portal_id ? <Badge variant="brand">portal: {challenge.portal_id}</Badge> : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {challengeError ? (
              <div className="text-sm text-red-600">Failed to load challenge: {String(challengeError)}</div>
            ) : null}
            <div className="text-sm text-slate-700 font-semibold">{challenge?.kind === 'clip' ? 'Beat this clip' : 'Beat this build'}</div>
            <div className="text-xs text-slate-500 font-mono break-all">{challengeId}</div>

            <div className="flex flex-wrap gap-2 items-center">
              <Button type="button" variant="secondary" size="sm" onClick={copyChallengeShareLink}>
                Copy Share Link
              </Button>
              {copyStatus ? <span className="text-xs text-slate-500">{copyStatus}</span> : null}
            </div>

            <div className="flex flex-wrap gap-2 items-center pt-2">
              <Button
                type="button"
                onClick={() => acceptMutation.mutate()}
                disabled={!challenge || acceptMutation.isPending || Boolean(matchId)}
                isLoading={acceptMutation.isPending}
              >
                <Trophy size={16} className="mr-2" /> Beat This
              </Button>
              {acceptMutation.error ? (
                <span className="text-xs text-red-600">{String(acceptMutation.error)}</span>
              ) : null}
            </div>

            {matchId ? (
              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="text-xs font-bold text-slate-600 uppercase">Match</div>
                <div className="text-xs font-mono text-slate-600 break-all">{matchId}</div>
                <div className="mt-2 flex items-center gap-2">
                  <Badge variant={match?.status === 'failed' ? 'error' : match?.status === 'done' ? 'success' : 'info'}>
                    {match?.status ?? 'queued'}
                  </Badge>
                  <span className="text-xs text-slate-500">{Math.round(match?.progress ?? 0)}%</span>
                  {match?.status === 'failed' && match?.error_message ? (
                    <span className="text-xs text-red-600">{match.error_message}</span>
                  ) : null}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="lg:col-span-5 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{lang === 'ko' ? '리더보드' : 'Leaderboard'}</CardTitle>
          </CardHeader>
          <CardContent>
            {leaderboard && leaderboard.length ? (
              <div className="space-y-2">
                {leaderboard.slice(0, 10).map((row) => (
                  <div key={row.user_id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral">#{row.rank}</Badge>
                      <div className="text-sm font-semibold text-slate-800">{row.display_name}</div>
                    </div>
                    <div className="text-xs text-slate-600">
                      {row.wins}W / {row.attempts} tries
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-500">No attempts yet.</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
