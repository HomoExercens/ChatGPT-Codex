import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ChevronLeft, MessageSquare } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type OpsDiscordOut = {
  mode: string;
  enabled: boolean;
  queued: number;
  sent: number;
  failed: number;
  last_sent_at?: string | null;
  last_error?: string | null;
  last_error_at?: string | null;
};

type OpsDiscordTestOut = {
  ok: boolean;
  outbox_id: string;
  status: string;
  payload: Record<string, any>;
  processed: Record<string, any>;
};

type OpsDiscordRegisterOut = {
  ok: boolean;
  scope: string;
  response: any;
};

const ADMIN_TOKEN_KEY = 'neuroleague.admin_token';

function loadAdminToken(): string {
  try {
    return (localStorage.getItem(ADMIN_TOKEN_KEY) || '').trim();
  } catch {
    return '';
  }
}

function saveAdminToken(token: string): void {
  try {
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
  } catch {
    // ignore
  }
}

export const OpsDiscordPage: React.FC = () => {
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const enabled = Boolean(adminToken.trim());
  const [testResult, setTestResult] = useState<OpsDiscordTestOut | null>(null);
  const [registerResult, setRegisterResult] = useState<OpsDiscordRegisterOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const { data: status, refetch } = useQuery({
    queryKey: ['ops', 'discord', enabled],
    queryFn: () => apiFetch<OpsDiscordOut>('/api/ops/discord'),
    enabled,
    staleTime: 5_000,
  });

  const testPostMutation = useMutation({
    mutationFn: async () => apiFetch<OpsDiscordTestOut>('/api/ops/discord/test_post', { method: 'POST' }),
    onSuccess: async (res) => {
      setError(null);
      setTestResult(res);
      await refetch();
    },
    onError: (err: any) => {
      setError(String(err?.message || err));
    },
  });

  const registerMutation = useMutation({
    mutationFn: async () => apiFetch<OpsDiscordRegisterOut>('/api/ops/discord/register_commands', { method: 'POST' }),
    onSuccess: async (res) => {
      setError(null);
      setRegisterResult(res);
      await refetch();
    },
    onError: (err: any) => {
      setError(String(err?.message || err));
    },
  });

  const payloadPretty = useMemo(() => {
    if (!testResult?.payload) return '';
    try {
      return JSON.stringify(testResult.payload, null, 2);
    } catch {
      return String(testResult.payload);
    }
  }, [testResult?.payload]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/ops" className="text-sm text-slate-600 hover:text-slate-800 inline-flex items-center gap-2">
          <ChevronLeft size={16} /> Back to Ops
        </Link>
        <Badge variant={enabled ? 'success' : 'warning'}>{enabled ? 'Admin enabled' : 'Enter admin token'}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare size={18} className="text-slate-500" /> Discord Launch Loop
          </CardTitle>
          <Button type="button" variant="secondary" onClick={() => refetch()} disabled={!enabled}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
            <div className="md:col-span-6">
              <Input
                label="Admin token"
                value={adminToken}
                onChange={(e) => setAdminToken(e.target.value)}
                placeholder="Set NEUROLEAGUE_ADMIN_TOKEN and paste it here"
              />
            </div>
            <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-4 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">Status</div>
              <div className="mt-1 text-sm text-slate-800">
                mode <span className="font-mono">{status?.mode ?? '—'}</span> · queued {status?.queued ?? 0} · sent{' '}
                {status?.sent ?? 0} · failed {status?.failed ?? 0}
              </div>
              <div className="mt-1 text-xs text-slate-500 font-mono break-all">last_sent {status?.last_sent_at ?? '—'}</div>
              <div className="mt-1 text-xs text-red-600 font-mono break-all">{status?.last_error ? `last_error ${status.last_error}` : ''}</div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => testPostMutation.mutate()} isLoading={testPostMutation.isPending} disabled={!enabled}>
              Send test post
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => registerMutation.mutate()}
              isLoading={registerMutation.isPending}
              disabled={!enabled}
            >
              Register commands
            </Button>
          </div>

          {error ? <div className="text-sm text-red-600">{error}</div> : null}

          {testResult ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-bold text-slate-800">Test post result</div>
                <Badge variant={testResult.status === 'sent' ? 'success' : 'warning'}>{testResult.status}</Badge>
              </div>
              <div className="mt-2 text-[11px] text-slate-500 font-mono break-all">outbox_id {testResult.outbox_id}</div>
              <pre className="mt-3 text-[11px] leading-snug text-slate-700 overflow-auto max-h-[360px]">
                {payloadPretty}
              </pre>
            </div>
          ) : (
            <div className="text-sm text-slate-500">
              {enabled ? 'Click “Send test post” to generate a payload preview.' : 'Enter admin token to load.'}
            </div>
          )}

          {registerResult ? (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <div className="text-sm font-bold text-slate-800">Register commands</div>
              <div className="mt-1 text-xs text-slate-500 font-mono">scope {registerResult.scope}</div>
              <pre className="mt-2 text-[11px] leading-snug text-slate-700 overflow-auto max-h-[260px]">
                {JSON.stringify(registerResult.response, null, 2)}
              </pre>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

