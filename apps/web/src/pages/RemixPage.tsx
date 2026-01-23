import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import type { BlueprintOut } from '../api/types';
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

export const RemixPage: React.FC = () => {
  const token = useAuthStore((s) => s.token);
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const blueprintId = useMemo(() => (params.get('blueprint_id') || params.get('bp') || '').trim(), [params]);
  const sourceReplayId = useMemo(() => (params.get('source_replay_id') || params.get('replay_id') || '').trim() || null, [params]);
  const src = useMemo(
    () => (params.get('src') || params.get('source') || 'share_landing').trim().slice(0, 64),
    [params]
  );
  const ref = useMemo(() => (params.get('ref') || '').trim() || null, [params]);
  const remixCtaVariant = useMemo(() => (params.get('rxv') || '').trim().slice(0, 32) || null, [params]);

  const lenv = useMemo(() => (params.get('lenv') || '').trim() || null, [params]);
  const cv = useMemo(() => (params.get('cv') || '').trim() || null, [params]);
  const ctpl = useMemo(() => (params.get('ctpl') || '').trim() || null, [params]);
  const utm = useMemo(() => {
    const out: Record<string, string> = {};
    for (const k of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
      const v = params.get(k);
      if (v) out[k] = v;
    }
    return out;
  }, [params]);

  useEffect(() => {
    if (!blueprintId) {
      setError('Missing blueprint_id');
      return;
    }

    const next = sanitizeNext(`${location.pathname}${location.search}`);
    if (!token) {
      const sp = new URLSearchParams();
      sp.set('next', next);
      if (ref) sp.set('ref', ref);
      if (src) sp.set('src', src);
      if (lenv) sp.set('lenv', lenv);
      if (cv) sp.set('cv', cv);
      if (ctpl) sp.set('ctpl', ctpl);
      for (const [k, v] of Object.entries(utm)) sp.set(k, v);
      navigate(`/start?${sp.toString()}`, { replace: true });
      return;
    }

    let cancelled = false;
    const run = async () => {
      try {
        // Track click intent (best-effort).
        try {
          await apiFetch('/api/events/track', {
            method: 'POST',
            body: JSON.stringify({
              type: 'fork_click',
              source: src,
              ref,
              utm,
              meta: {
                blueprint_id: blueprintId,
                replay_id: sourceReplayId,
                source_replay_id: sourceReplayId,
                remix_cta_v1: remixCtaVariant,
              },
            }),
          });
        } catch {
          // ignore
        }

        const forked = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(blueprintId)}/fork`, {
          method: 'POST',
          body: JSON.stringify({
            name: 'Remix',
            source_replay_id: sourceReplayId,
            source: src,
            note: src ? `remix:${src}${remixCtaVariant ? `:${remixCtaVariant}` : ''}` : undefined,
            auto_submit: false,
          }),
        });
        if (cancelled) return;
        navigate(`/forge/${encodeURIComponent(forked.id)}`, { replace: true });
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [
    blueprintId,
    ctpl,
    cv,
    lenv,
    location.pathname,
    location.search,
    navigate,
    ref,
    remixCtaVariant,
    sourceReplayId,
    src,
    token,
    utm,
  ]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Remixing…</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-slate-600">Forking the build into your Lab, then opening Forge.</div>
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
            blueprint_id: {blueprintId || '—'}
            {sourceReplayId ? ` · replay_id: ${sourceReplayId}` : ''}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
