import React, { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';
import { useAuthStore } from '../stores/auth';

type AuthResponse = { access_token: string; token_type: 'bearer' };

type DemoIds = {
  clip_replay_id?: string;
  featured_user_id?: string;
};

type ReportResponse = { ok: boolean; report_id: string };

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

function clampReason(reason: string): string {
  const trimmed = reason.trim().replace(/\s+/g, ' ');
  if (trimmed.length <= 280) return trimmed;
  return trimmed.slice(0, 277).trimEnd() + '…';
}

export const FeedbackPage: React.FC = () => {
  const token = useAuthStore((s) => s.token);
  const setToken = useAuthStore((s) => s.setToken);
  const location = useLocation();

  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const context = useMemo(() => (params.get('context') || 'general').trim().slice(0, 64), [params]);
  const replayId = useMemo(() => (params.get('replay_id') || '').trim() || null, [params]);

  const [demoIds, setDemoIds] = useState<DemoIds | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<string>('');
  const [contact, setContact] = useState<string>('');
  const [submittedId, setSubmittedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const ids = await apiFetch<DemoIds>('/api/assets/ops/demo_ids.json');
        if (cancelled) return;
        setDemoIds(ids);
      } catch {
        // Optional: allow the page to work even if seed data wasn't run.
        if (cancelled) return;
        setDemoIds({});
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (token) return;
    let cancelled = false;
    const run = async () => {
      try {
        const device_id = getOrCreateDeviceId();
        const resp = await apiFetch<AuthResponse>('/api/auth/guest', {
          method: 'POST',
          body: JSON.stringify({ device_id, method: 'feedback', source: 'feedback', next: '/feedback' }),
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

  const target = useMemo(() => {
    const idFromQuery = replayId;
    if (idFromQuery) return { target_type: 'clip' as const, target_id: idFromQuery };
    const demoReplay = (demoIds?.clip_replay_id || '').trim();
    if (demoReplay) return { target_type: 'clip' as const, target_id: demoReplay };
    const demoUser = (demoIds?.featured_user_id || '').trim();
    if (demoUser) return { target_type: 'profile' as const, target_id: demoUser };
    return null;
  }, [demoIds?.clip_replay_id, demoIds?.featured_user_id, replayId]);

  const submit = async () => {
    setError(null);
    setSubmittedId(null);
    if (!target) {
      setError('Missing demo ids. Run seed-data and refresh.');
      return;
    }
    const payload = clampReason(
      `[${context}] ${details}${contact.trim() ? ` (contact: ${contact.trim()})` : ''}`.trim()
    );
    if (!payload || payload.length < 4) {
      setError('Please describe what happened (at least a few words).');
      return;
    }
    try {
      const resp = await apiFetch<ReportResponse>('/api/reports', {
        method: 'POST',
        body: JSON.stringify({ ...target, reason: payload }),
      });
      setSubmittedId(resp.report_id);
      setDetails('');
      setContact('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-bg text-fg">
      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle>Report an issue</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-muted">
            Context: <span className="font-mono">{context}</span>
          </div>

          {loading ? <div className="text-sm text-muted">Loading…</div> : null}

          <div className="text-xs text-muted/70">
            Target: {target ? <span className="font-mono">{`${target.target_type}:${target.target_id}`}</span> : '—'}
          </div>

          <Input
            label="What happened?"
            value={details}
            onChange={(e) => setDetails(e.target.value)}
            placeholder="e.g. Beat This timed out, Replies didn't show, OG image 404, etc."
          />
          <Input
            label="Contact (optional)"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="email / discord handle"
          />

          {error ? <div className="text-xs text-danger-500 break-words">{error}</div> : null}
          {submittedId ? (
            <div className="text-xs text-success-500 bg-success-500/10 border border-success-500/20 rounded-2xl px-3 py-2">
              Submitted. report_id: <span className="font-mono">{submittedId}</span>
            </div>
          ) : null}

          <div className="flex gap-2">
            <Button onClick={() => void submit()} disabled={loading || !details.trim()}>
              Submit
            </Button>
            <Button variant="secondary" onClick={() => window.history.back()}>
              Back
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
