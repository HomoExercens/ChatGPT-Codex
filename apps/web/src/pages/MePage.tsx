import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { useAuthStore } from '../stores/auth';

type Me = { user_id: string; display_name: string; is_guest: boolean; discord_connected?: boolean; avatar_url?: string | null };

export const MePage: React.FC = () => {
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);

  const { data: me, isFetching, error } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<Me>('/api/auth/me'),
    staleTime: 30_000,
  });

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{me?.display_name ?? 'Me'}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isFetching ? <div className="text-sm text-slate-500">Loading…</div> : null}
          {error ? <div className="text-sm text-red-600 break-words">{String(error)}</div> : null}

          <div className="text-sm text-slate-700">
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">User</span>
              <span className="font-mono text-xs break-all">{me?.user_id ?? '—'}</span>
            </div>
            <div className="flex justify-between gap-4 mt-1">
              <span className="text-slate-500">Type</span>
              <span className="font-semibold">{me?.is_guest ? 'Guest' : 'Account'}</span>
            </div>
          </div>

          <div className="pt-2 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => navigate('/settings')}>
              Settings
            </Button>
            <Button variant="secondary" onClick={() => navigate('/home')}>
              Lab Home
            </Button>
          </div>

          <div className="pt-2">
            <Button
              variant="destructive"
              onClick={() => {
                setToken(null);
                navigate('/play', { replace: true });
              }}
            >
              Logout
            </Button>
            <div className="text-[11px] text-slate-500 mt-2">Logging out clears your local token and starts a new guest session next time.</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Account upgrade</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="text-sm text-slate-600">Optional: connect Discord in Settings to upgrade a guest to a real account.</div>
          <Button variant="secondary" onClick={() => navigate('/settings')}>
            Open Settings
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

