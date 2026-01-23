import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import type { MatchDetail } from '../api/types';
import { apiFetch } from '../lib/api';
import { useAuthStore } from '../stores/auth';

function sanitizeNext(nextRaw: string): string {
  const next = (nextRaw || '').trim();
  if (!next) return '/home';
  if (!next.startsWith('/')) return '/home';
  if (next.startsWith('//')) return '/home';
  if (next.startsWith('/\\')) return '/home';
  if (next.startsWith('/%5c')) return '/home';
  if (next.includes('://')) return '/home';
  return next;
}

type BeatClipResponse = {
  challenge_id: string;
  attempt_id: string;
  match_id: string;
  status: 'queued' | 'running';
};

async function sleep(ms: number): Promise<void> {
  await new Promise((r) => setTimeout(r, ms));
}

export const BeatPage: React.FC = () => {
  const token = useAuthStore((s) => s.token);
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [matchId, setMatchId] = useState<string | null>(null);

  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const replayId = useMemo(() => (params.get('replay_id') || params.get('id') || '').trim(), [params]);
  const blueprintId = useMemo(() => (params.get('blueprint_id') || params.get('bp') || '').trim() || null, [params]);
  const src = useMemo(
    () => (params.get('src') || params.get('source') || 'share_landing').trim().slice(0, 64),
    [params]
  );
  const ref = useMemo(() => (params.get('ref') || '').trim() || null, [params]);

  useEffect(() => {
    if (!replayId) {
      setError('Missing replay_id');
      return;
    }

    const next = sanitizeNext(`${location.pathname}${location.search}`);
    if (!token) {
      const sp = new URLSearchParams();
      sp.set('next', next);
      if (ref) sp.set('ref', ref);
      if (src) sp.set('src', src);
      navigate(`/start?${sp.toString()}`, { replace: true });
      return;
    }

    let cancelled = false;
    const run = async () => {
      try {
        const beat = await apiFetch<BeatClipResponse>(`/api/challenges/clip/${encodeURIComponent(replayId)}/beat`, {
          method: 'POST',
          body: JSON.stringify({ blueprint_id: blueprintId, seed_set_count: 1, source: src }),
        });
        if (cancelled) return;
        setMatchId(beat.match_id);

        const deadline = Date.now() + 180_000;
        while (!cancelled && Date.now() < deadline) {
          const m = await apiFetch<MatchDetail>(`/api/matches/${encodeURIComponent(beat.match_id)}`);
          if (cancelled) return;
          if (m.status === 'done') {
            navigate(`/replay/${encodeURIComponent(beat.match_id)}?reply_to=${encodeURIComponent(replayId)}`, {
              replace: true,
            });
            return;
          }
          if (m.status === 'failed') {
            throw new Error(m.error_message || 'Match failed');
          }
          await sleep(1000);
        }
        throw new Error('Timed out waiting for match');
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [blueprintId, location.pathname, location.search, navigate, ref, replayId, src, token]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Starting challenge…</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-slate-600">Queuing a “Beat This” match and preparing your reply clip.</div>
          {error ? (
            <div className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
              <div className="font-mono break-all">{error}</div>
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" onClick={() => navigate('/home', { replace: true })}>
                  Go Home
                </Button>
              </div>
            </div>
          ) : null}
          <div className="text-xs text-slate-400 break-all">
            replay_id: {replayId || '—'}
            {matchId ? ` · match_id: ${matchId}` : ''}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

