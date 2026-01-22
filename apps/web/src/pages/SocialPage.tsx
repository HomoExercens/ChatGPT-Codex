import React, { useMemo } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Users } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { useSettingsStore } from '../stores/settings';

type ActivityItem = {
  id: string;
  type: string;
  created_at: string;
  actor: { user_id: string; display_name: string; avatar_url?: string | null };
  payload: Record<string, any>;
  href?: string | null;
};

type ActivityFeedOut = { items: ActivityItem[]; next_cursor?: string | null };

export const SocialPage: React.FC = () => {
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isFetching } = useInfiniteQuery({
    queryKey: ['activityFeed'],
    queryFn: ({ pageParam }) => {
      const qp = new URLSearchParams();
      qp.set('limit', '30');
      if (pageParam) qp.set('cursor', String(pageParam));
      return apiFetch<ActivityFeedOut>(`/api/feed/activity?${qp.toString()}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 10_000,
  });

  const items = useMemo(() => (data?.pages ?? []).flatMap((p) => p.items ?? []), [data?.pages]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users size={18} className="text-brand-600" /> {lang === 'ko' ? '팔로잉 피드' : 'Following Feed'}
          </CardTitle>
          <Badge variant="neutral">{items.length ? `${items.length}` : lang === 'ko' ? '비어 있음' : 'empty'}</Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          {isFetching && !items.length ? (
            <div className="text-sm text-slate-500">Loading…</div>
          ) : items.length === 0 ? (
            <div className="text-sm text-slate-600">
              {lang === 'ko'
                ? '아직 활동이 없습니다. 리더보드에서 연구원을 팔로우해보세요.'
                : 'No activity yet. Follow players from the leaderboard.'}
              <div className="mt-3">
                <Button variant="secondary" onClick={() => navigate('/leaderboard')} type="button">
                  {lang === 'ko' ? '리더보드 열기' : 'Open Leaderboard'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((it) => (
                <button
                  key={it.id}
                  type="button"
                  className="w-full text-left rounded-xl border border-slate-200 bg-white px-3 py-3 hover:bg-slate-50 transition-colors"
                  onClick={() => {
                    if (it.href) navigate(it.href);
                    else navigate(`/profile/${encodeURIComponent(it.actor.user_id)}`);
                  }}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-bold text-slate-800 truncate">{it.actor.display_name}</div>
                      <div className="text-xs text-slate-500 font-mono truncate">{it.actor.user_id}</div>
                    </div>
                    <Badge variant="neutral" className="shrink-0">
                      {it.type}
                    </Badge>
                  </div>
                  <div className="mt-2 text-xs text-slate-600">
                    {it.payload?.match_id ? (
                      <span className="font-mono">match {String(it.payload.match_id)}</span>
                    ) : it.payload?.blueprint_id ? (
                      <span className="font-mono">bp {String(it.payload.blueprint_id)}</span>
                    ) : (
                      <span className="text-slate-500">{new Date(it.created_at).toLocaleString()}</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}

          {hasNextPage ? (
            <Button
              variant="secondary"
              onClick={() => fetchNextPage()}
              isLoading={isFetchingNextPage}
              disabled={isFetchingNextPage}
              type="button"
            >
              {lang === 'ko' ? '더 보기' : 'Load more'}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

