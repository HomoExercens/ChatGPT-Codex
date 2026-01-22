import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { writeShareVariants } from '../lib/shareVariants';
import { useAuthStore } from '../stores/auth';

type AuthResponse = { access_token: string; token_type: 'bearer' };

const DEVICE_ID_KEY = 'neuroleague.device_id';
const REF_KEY = 'neuroleague.ref';
const UTM_KEY = 'neuroleague.utm';

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

function sanitizeNext(nextRaw: string | null): string {
  const next = (nextRaw || '').trim();
  if (!next) return '/home';
  if (!next.startsWith('/')) return '/home';
  if (next.startsWith('//')) return '/home';
  if (next.startsWith('/\\')) return '/home';
  if (next.startsWith('/%5c')) return '/home';
  if (next.includes('://')) return '/home';
  return next;
}

export const StartPage: React.FC = () => {
  const token = useAuthStore((s) => s.token);
  const setToken = useAuthStore((s) => s.setToken);
  const location = useLocation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const next = useMemo(() => sanitizeNext(params.get('next')), [params]);
  const ref = useMemo(() => (params.get('ref') || '').trim() || null, [params]);
  const src = useMemo(() => (params.get('src') || '').trim() || null, [params]);
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
    if (ref) localStorage.setItem(REF_KEY, ref);
    if (Object.keys(utm).length) localStorage.setItem(UTM_KEY, JSON.stringify(utm));
    if (lenv || cv || ctpl) writeShareVariants({ lenv: lenv ?? undefined, cv: cv ?? undefined, ctpl: ctpl ?? undefined });
    getOrCreateDeviceId();
  }, [ctpl, cv, lenv, ref, utm]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (token) {
        navigate(next, { replace: true });
        return;
      }
      try {
        const device_id = getOrCreateDeviceId();
        const resp = await apiFetch<AuthResponse>('/api/auth/guest', {
          method: 'POST',
          body: JSON.stringify({ ref, device_id, method: 'deep_link', source: src, next, utm, lenv, cv, ctpl }),
        });
        if (cancelled) return;
        setToken(resp.access_token);
        navigate(next, { replace: true });
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [ctpl, cv, lenv, navigate, next, ref, setToken, src, token, utm]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Starting…</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-slate-600">Preparing your Lab pass and opening the app.</div>
          {error ? (
            <div className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
              <div className="font-mono">{error}</div>
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" onClick={() => navigate('/', { replace: true })}>
                  Go to Login
                </Button>
              </div>
            </div>
          ) : null}
          <div className="text-xs text-slate-400 break-all">
            next: {next}
            {ref ? ` · ref: ${ref}` : ''}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
