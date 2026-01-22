import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Flag, User as UserIcon } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import type { Mode } from '../api/types';
import { apiFetch } from '../lib/api';
import { useSettingsStore } from '../stores/settings';

type UserProfile = {
  user: { id: string; display_name: string; is_guest: boolean; avatar_url?: string | null };
  rating: { mode: Mode; elo: number; games_played: number };
  latest_submitted_blueprint: { id: string; name: string; mode: Mode; ruleset_version: string; submitted_at?: string | null } | null;
  recent_matches: Array<{
    id: string;
    created_at: string;
    status: string;
    result: 'win' | 'loss' | 'draw' | null;
    opponent_display_name: string;
    opponent_user_id: string | null;
    opponent_type: 'human' | 'bot';
    replay_id: string | null;
  }>;
  follower_count: number;
  following_count: number;
  is_following: boolean;
  badges?: Array<{ id: string; name: string; earned_at: string; source: string }>;
  referrals?: Array<{
    id: string;
    new_user_id: string;
    new_user_display_name?: string | null;
    status: 'pending' | 'credited' | 'invalid';
    created_at: string;
    credited_at?: string | null;
  }>;
  quest_history?: Array<{
    period_key: string;
    cadence: string;
    key: string;
    title: string;
    progress_count: number;
    goal_count: number;
    claimed_at?: string | null;
  }>;
};

export const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { userId } = useParams<{ userId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const lang = useSettingsStore((s) => s.language);
  const [reportError, setReportError] = useState<string | null>(null);

  const initialMode = (searchParams.get('mode') as Mode | null) ?? '1v1';
  const [mode, setMode] = useState<Mode>(initialMode === 'team' ? 'team' : '1v1');

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    next.set('mode', mode);
    setSearchParams(next, { replace: true });
  }, [mode, searchParams, setSearchParams]);

  const title = useMemo(() => (lang === 'ko' ? '프로필' : 'Profile'), [lang]);

  const { data } = useQuery({
    queryKey: ['profile', userId, mode],
    queryFn: () => apiFetch<UserProfile>(`/api/users/${encodeURIComponent(userId ?? '')}/profile?mode=${encodeURIComponent(mode)}`),
    enabled: Boolean(userId),
  });

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<{ user_id: string }>('/api/auth/me'),
    staleTime: 60_000,
  });

  const followMutation = useMutation({
    mutationFn: async () => {
      if (!userId) throw new Error('missing userId');
      return apiFetch<{ following: boolean }>('/api/users/' + encodeURIComponent(userId) + '/follow', {
        method: 'POST',
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['profile', userId, mode] });
    },
  });

  const reportProfile = async () => {
    if (!userId) return;
    const reason = window.prompt(lang === 'ko' ? '신고 사유' : 'Report reason', 'inappropriate') ?? '';
    if (!reason.trim()) return;
    setReportError(null);
    try {
      await apiFetch<{ report_id: string }>('/api/reports', {
        method: 'POST',
        body: JSON.stringify({ target_type: 'profile', target_id: userId, reason }),
      });
    } catch (e) {
      setReportError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <Card className="lg:col-span-5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserIcon size={18} className="text-brand-600" /> {title}
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
          {!data ? (
            <div className="text-sm text-slate-500">Loading…</div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <div className="text-lg font-bold text-slate-900">{data.user.display_name}</div>
                <Badge variant="neutral" className="font-mono">
                  {data.user.id}
                </Badge>
                {data.user.is_guest ? <Badge variant="neutral">GUEST</Badge> : null}
              </div>

              <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center gap-3 text-xs text-slate-600">
                  <span>
                    {lang === 'ko' ? '팔로워' : 'Followers'}{' '}
                    <span className="font-mono font-bold text-slate-800">{data.follower_count ?? 0}</span>
                  </span>
                  <span>
                    {lang === 'ko' ? '팔로잉' : 'Following'}{' '}
                    <span className="font-mono font-bold text-slate-800">{data.following_count ?? 0}</span>
                  </span>
                </div>
                {me?.user_id && me.user_id !== data.user.id ? (
                  <Button
                    size="sm"
                    variant={data.is_following ? 'secondary' : 'primary'}
                    onClick={() => followMutation.mutate()}
                    isLoading={followMutation.isPending}
                    type="button"
                  >
                    {data.is_following ? (lang === 'ko' ? '언팔로우' : 'Unfollow') : lang === 'ko' ? '팔로우' : 'Follow'}
                  </Button>
                ) : null}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl border border-slate-200 bg-white">
                  <div className="text-xs text-slate-500">Elo</div>
                  <div className="text-2xl font-bold text-slate-900">{data.rating.elo}</div>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-white">
                  <div className="text-xs text-slate-500">{lang === 'ko' ? '경기 수' : 'Games'}</div>
                  <div className="text-2xl font-bold text-slate-900">{data.rating.games_played}</div>
                </div>
              </div>

              <div className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                  {lang === 'ko' ? '대표 블루프린트' : 'Latest Submitted Blueprint'}
                </div>
                {data.latest_submitted_blueprint ? (
                  <div className="space-y-1">
                    <div className="font-bold text-slate-800">{data.latest_submitted_blueprint.name}</div>
                    <div className="text-xs text-slate-500 font-mono">{data.latest_submitted_blueprint.id}</div>
                    <div className="text-xs text-slate-500">{data.latest_submitted_blueprint.ruleset_version}</div>
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">
                    {lang === 'ko' ? '제출된 블루프린트가 없습니다.' : 'No submitted blueprint yet.'}
                  </div>
                )}
              </div>

              <div className="p-3 rounded-xl border border-slate-200 bg-white">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                  {lang === 'ko' ? '배지' : 'Badges'}
                </div>
                {data.badges && data.badges.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {data.badges.slice(0, 8).map((b) => (
                      <Badge key={b.id} variant="brand">
                        {b.name}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">
                    {lang === 'ko' ? '아직 획득한 배지가 없습니다.' : 'No badges earned yet.'}
                  </div>
                )}
              </div>

              <div className="p-3 rounded-xl border border-slate-200 bg-white">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                  {lang === 'ko' ? '퀘스트 히스토리 (최근 7일)' : 'Quest History (Last 7 Days)'}
                </div>
                {Array.isArray(data.quest_history) && data.quest_history.length > 0 ? (
                  <div className="space-y-2">
                    {data.quest_history.slice(0, 12).map((q) => {
                      const done = (q.progress_count || 0) >= (q.goal_count || 1);
                      return (
                        <div key={`${q.period_key}:${q.key}`} className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-bold text-slate-800 truncate">{q.title}</div>
                            <div className="text-xs text-slate-500 font-mono truncate">
                              {q.period_key} · {q.key}
                            </div>
                          </div>
                          <Badge variant={q.claimed_at ? 'success' : done ? 'warning' : 'neutral'} className="shrink-0">
                            {q.claimed_at ? 'CLAIMED' : done ? 'READY' : `${q.progress_count}/${q.goal_count}`}
                          </Badge>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">
                    {lang === 'ko' ? '최근 퀘스트 기록이 없습니다.' : 'No recent quest history yet.'}
                  </div>
                )}
              </div>

              <div className="p-3 rounded-xl border border-slate-200 bg-white">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                  {lang === 'ko' ? '추천 보상' : 'Referral Rewards'}
                </div>
                {data.referrals && data.referrals.length > 0 ? (
                  <div className="space-y-2">
                    {data.referrals.slice(0, 5).map((r) => (
                      <div key={r.id} className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-slate-800 truncate">
                            {r.new_user_display_name || (lang === 'ko' ? '신규 연구원' : 'New Researcher')}
                          </div>
                          <div className="text-xs text-slate-500 font-mono truncate">{r.new_user_id}</div>
                        </div>
                        <Badge
                          variant={r.status === 'credited' ? 'success' : r.status === 'pending' ? 'warning' : 'neutral'}
                          className="shrink-0"
                        >
                          {r.status.toUpperCase()}
                        </Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">
                    {lang === 'ko' ? '아직 추천 보상이 없습니다.' : 'No referral rewards yet.'}
                  </div>
                )}
              </div>

              <Button variant="outline" onClick={() => navigate('/leaderboard')} type="button">
                {lang === 'ko' ? '리더보드 보기' : 'Open Leaderboard'}
              </Button>

              <Button variant="secondary" onClick={() => void reportProfile()} type="button">
                <Flag size={16} className="mr-2" /> {lang === 'ko' ? '프로필 신고' : 'Report Profile'}
              </Button>
              {reportError ? <div className="text-xs text-red-600 break-words">{reportError}</div> : null}
            </>
          )}
        </CardContent>
      </Card>

      <Card className="lg:col-span-7">
        <CardHeader>
          <CardTitle>{lang === 'ko' ? '최근 경기' : 'Recent Matches'}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {!data ? (
            <div className="p-4 text-sm text-slate-500">Loading…</div>
          ) : data.recent_matches.length === 0 ? (
            <div className="p-4 text-sm text-slate-500">{lang === 'ko' ? '경기 기록이 없습니다.' : 'No matches yet.'}</div>
          ) : (
            <div className="divide-y divide-slate-100">
              {data.recent_matches.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => navigate(`/replay/${m.id}`)}
                  className="w-full text-left p-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <div className="font-bold text-slate-800">{m.opponent_display_name}</div>
                      <Badge variant={m.opponent_type === 'human' ? 'info' : 'neutral'}>{m.opponent_type.toUpperCase()}</Badge>
                    </div>
                    <div className="text-xs text-slate-500 font-mono">{m.id}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    {m.status === 'done' && m.result ? (
                      <Badge variant={m.result === 'win' ? 'success' : m.result === 'loss' ? 'error' : 'neutral'}>
                        {m.result}
                      </Badge>
                    ) : (
                      <Badge variant="warning">{m.status}</Badge>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
