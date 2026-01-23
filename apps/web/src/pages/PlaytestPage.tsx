import React, { useEffect, useMemo, useState } from 'react';

import { Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { useAuthStore } from '../stores/auth';

type AuthResponse = { access_token: string; token_type: 'bearer' };

type DemoIds = {
  generated_at?: string;
  ruleset_version?: string;
  clip_replay_id?: string;
  clip_match_id?: string;
  clip_challenge_id?: string;
  best_build_id?: string;
  featured_user_id?: string;
};

const DEVICE_ID_KEY = 'neuroleague.device_id';

function getOrCreateDeviceId(): string {
  const existing = localStorage.getItem(DEVICE_ID_KEY);
  if (existing && existing.trim()) return existing;
  const id =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `dev_${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`;
  localStorage.setItem(DEVICE_ID_KEY, id);
  return id;
}

export const PlaytestPage: React.FC = () => {
  const token = useAuthStore((s) => s.token);
  const setToken = useAuthStore((s) => s.setToken);
  const [demoIds, setDemoIds] = useState<DemoIds | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Ensure we have a (guest) token so playtest events can be tracked.
  useEffect(() => {
    if (token) return;
    let cancelled = false;
    const run = async () => {
      try {
        const device_id = getOrCreateDeviceId();
        const resp = await apiFetch<AuthResponse>('/api/auth/guest', {
          method: 'POST',
          body: JSON.stringify({ device_id, method: 'playtest', source: 'playtest', next: '/playtest', ref: null }),
        });
        if (cancelled) return;
        setToken(resp.access_token);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [setToken, token]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const ids = await apiFetch<DemoIds>('/api/assets/ops/demo_ids.json');
        if (cancelled) return;
        setDemoIds(ids);
      } catch (e) {
        if (cancelled) return;
        setError('Missing demo ids. Run seed-data and refresh.');
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const demoReplayId = useMemo(() => (demoIds?.clip_replay_id || '').trim() || null, [demoIds?.clip_replay_id]);
  const demoClipUrl = useMemo(() => {
    if (!demoReplayId) return null;
    const sp = new URLSearchParams();
    sp.set('start', '0.0');
    sp.set('end', '2.0');
    sp.set('v', '1');
    sp.set('ref', 'playtest');
    return `/s/clip/${encodeURIComponent(demoReplayId)}?${sp.toString()}`;
  }, [demoReplayId]);

  const track = async (type: string, meta: Record<string, unknown>) => {
    try {
      await apiFetch('/api/events/track', {
        method: 'POST',
        body: JSON.stringify({ type, source: 'playtest', meta }),
      });
    } catch {
      // best-effort: playtest should still be usable if tracking fails.
    }
  };

  const [done, setDone] = useState<Record<number, boolean>>({});
  const toggleDone = (stepId: number) => {
    const next = !done[stepId];
    setDone((prev) => ({ ...prev, [stepId]: next }));
    if (next) void track('playtest_step_completed', { step_id: stepId, demo_replay_id: demoReplayId });
    if (next && stepId === 6) void track('playtest_completed', { demo_replay_id: demoReplayId });
  };

  useEffect(() => {
    void track('playtest_opened', { demo_replay_id: demoReplayId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, demoReplayId]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>NeuroLeague Playtest (2‑minute loop)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-slate-700">
            Goal: clip → Beat This → Quick Remix → match done → reply share → see your reply under Replies.
          </div>

          {error ? <div className="text-xs text-red-600 break-words">{error}</div> : null}

          <div className="flex flex-wrap gap-2">
            {demoClipUrl ? (
              <a href={demoClipUrl}>
                <Button onClick={() => void track('playtest_step_completed', { step_id: 1, via: 'start_button', demo_replay_id: demoReplayId })}>
                  Start Playtest
                </Button>
              </a>
            ) : (
              <Button disabled>Start Playtest</Button>
            )}
            <a href="/feedback?context=playtest">
              <Button variant="secondary">Report issue</Button>
            </a>
          </div>

          <div className="text-xs text-slate-500">
            Demo replay: {demoReplayId ? <span className="font-mono">{demoReplayId}</span> : '—'}
            {demoIds?.ruleset_version ? ` · ruleset: ${demoIds.ruleset_version}` : ''}
          </div>

          <div className="space-y-2">
            <div className="text-sm font-semibold">Steps</div>
            <div className="space-y-2 text-sm">
              <div className="flex items-start justify-between gap-3 border border-slate-200 rounded-xl px-3 py-2 bg-white">
                <div>
                  <div className="font-medium">1) Open the demo clip</div>
                  <div className="text-xs text-slate-500">On the share landing, you’ll see “Beat This” and “Quick Remix”.</div>
                </div>
                <Button variant={done[1] ? 'secondary' : 'primary'} onClick={() => toggleDone(1)}>
                  {done[1] ? 'Done' : 'Mark done'}
                </Button>
              </div>

              <div className="flex items-start justify-between gap-3 border border-slate-200 rounded-xl px-3 py-2 bg-white">
                <div>
                  <div className="font-medium">2) Click “Beat This”</div>
                  <div className="text-xs text-slate-500">This starts a challenge match against the original clip.</div>
                </div>
                <Button variant={done[2] ? 'secondary' : 'primary'} onClick={() => toggleDone(2)}>
                  {done[2] ? 'Done' : 'Mark done'}
                </Button>
              </div>

              <div className="flex items-start justify-between gap-3 border border-slate-200 rounded-xl px-3 py-2 bg-white">
                <div>
                  <div className="font-medium">3) Pick a Quick Remix preset</div>
                  <div className="text-xs text-slate-500">Try one: Tankier / Melt Faster / Counter.</div>
                </div>
                <Button variant={done[3] ? 'secondary' : 'primary'} onClick={() => toggleDone(3)}>
                  {done[3] ? 'Done' : 'Mark done'}
                </Button>
              </div>

              <div className="flex items-start justify-between gap-3 border border-slate-200 rounded-xl px-3 py-2 bg-white">
                <div>
                  <div className="font-medium">4) Wait for the match result</div>
                  <div className="text-xs text-slate-500">You’ll land on a replay page when the match is done.</div>
                </div>
                <Button variant={done[4] ? 'secondary' : 'primary'} onClick={() => toggleDone(4)}>
                  {done[4] ? 'Done' : 'Mark done'}
                </Button>
              </div>

              <div className="flex items-start justify-between gap-3 border border-slate-200 rounded-xl px-3 py-2 bg-white">
                <div>
                  <div className="font-medium">5) Share your Reply Clip</div>
                  <div className="text-xs text-slate-500">Use the share UI to publish a reply clip back to the original.</div>
                </div>
                <Button variant={done[5] ? 'secondary' : 'primary'} onClick={() => toggleDone(5)}>
                  {done[5] ? 'Done' : 'Mark done'}
                </Button>
              </div>

              <div className="flex items-start justify-between gap-3 border border-slate-200 rounded-xl px-3 py-2 bg-white">
                <div>
                  <div className="font-medium">6) Confirm your reply under “Replies”</div>
                  <div className="text-xs text-slate-500">Return to the original clip share page and check the Replies section.</div>
                </div>
                <Button variant={done[6] ? 'secondary' : 'primary'} onClick={() => toggleDone(6)}>
                  {done[6] ? 'Done' : 'Mark done'}
                </Button>
              </div>
            </div>
          </div>

          <div className="text-xs text-slate-500">
            Tip: If the preview URL changes (Quick Tunnel), re-open <span className="font-mono">/playtest</span> from the new base URL.
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
