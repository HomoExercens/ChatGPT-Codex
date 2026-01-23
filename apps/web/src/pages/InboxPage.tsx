import React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { apiFetch } from '../lib/api';
import type { MarkNotificationReadResponse, NotificationsResponse } from '../api/types';
import { Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';

export const InboxPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isFetching, error } = useQuery({
    queryKey: ['notifications', 'inbox', 'page'],
    queryFn: () => apiFetch<NotificationsResponse>('/api/notifications?limit=30'),
    staleTime: 5_000,
  });

  const items = data?.items ?? [];
  const unread = data?.unread_count ?? 0;

  return (
    <div className="max-w-2xl mx-auto">
      <Card>
        <CardHeader>
          <CardTitle>
            Inbox {unread > 0 ? <span className="text-slate-400 text-sm font-semibold">({unread} unread)</span> : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isFetching ? <div className="text-sm text-slate-500">Loading…</div> : null}
          {error ? <div className="text-sm text-red-600 break-words">{String(error)}</div> : null}

          {items.length ? (
            <div className="divide-y divide-slate-100 border border-slate-200 rounded-2xl overflow-hidden bg-white">
              {items.map((n) => {
                const isUnread = !n.read_at;
                return (
                  <button
                    key={n.id}
                    type="button"
                    className={`w-full text-left px-4 py-3 hover:bg-slate-50 transition-colors ${
                      isUnread ? 'bg-brand-50/40' : 'bg-white'
                    }`}
                    onClick={async () => {
                      try {
                        await apiFetch<MarkNotificationReadResponse>(`/api/notifications/${encodeURIComponent(n.id)}/read`, {
                          method: 'POST',
                        });
                      } catch {
                        // best-effort
                      } finally {
                        queryClient.invalidateQueries({ queryKey: ['notifications'] });
                      }

                      const href = (n.href ?? '').trim();
                      if (!href) return;
                      if (href.startsWith('/s/')) {
                        window.location.href = href;
                        return;
                      }
                      if (href.startsWith('/')) {
                        navigate(href);
                        return;
                      }
                      try {
                        window.open(href, '_blank', 'noreferrer');
                      } catch {
                        // ignore
                      }
                    }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm font-bold text-slate-900 truncate">{n.title ?? 'Notification'}</div>
                        {n.body ? <div className="text-xs text-slate-600 mt-1 line-clamp-2">{n.body}</div> : null}
                      </div>
                      {isUnread ? <span className="mt-1 w-2 h-2 rounded-full bg-brand-600 shrink-0" /> : null}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-2 font-mono">{new Date(n.created_at).toLocaleString()}</div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="text-sm text-slate-500">No notifications yet.</div>
          )}

          <div className="pt-2 flex justify-end">
            <Button variant="secondary" onClick={() => queryClient.invalidateQueries({ queryKey: ['notifications'] })}>
              Refresh
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

