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
            Inbox {unread > 0 ? <span className="text-muted text-sm font-semibold">({unread} unread)</span> : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isFetching ? <div className="text-sm text-muted">Loading…</div> : null}
          {error ? <div className="text-sm text-danger-500 break-words">{String(error)}</div> : null}

          {items.length ? (
            <div className="divide-y divide-border/10 border border-border/12 rounded-2xl overflow-hidden bg-surface-2/35">
              {items.map((n) => {
                const isUnread = !n.read_at;
                return (
                  <button
                    key={n.id}
                    type="button"
                    className={`w-full text-left px-4 py-3 transition-colors hover:bg-surface-1/30 ${
                      isUnread ? 'bg-brand-500/10' : 'bg-surface-1/10'
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
                        <div className="text-sm font-bold text-fg truncate">{n.title ?? 'Notification'}</div>
                        {n.body ? <div className="text-xs text-muted mt-1 line-clamp-2">{n.body}</div> : null}
                      </div>
                      {isUnread ? <span className="mt-1 w-2 h-2 rounded-full bg-brand-400 shrink-0" /> : null}
                    </div>
                    <div className="text-[11px] text-muted/70 mt-2 font-mono">{new Date(n.created_at).toLocaleString()}</div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="text-sm text-muted">No notifications yet.</div>
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
