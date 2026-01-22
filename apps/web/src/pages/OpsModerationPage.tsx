import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ExternalLink, Gavel, ShieldAlert } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type OpsReport = {
  id: string;
  reporter_user_id: string | null;
  reporter_display_name: string | null;
  target_user_id: string | null;
  target_display_name: string | null;
  target_type: 'clip' | 'build' | 'profile' | string;
  target_id: string;
  reason: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
};

type OpsReportsListOut = {
  items: OpsReport[];
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

function targetUrl(r: OpsReport): string {
  if (r.target_type === 'clip') return `/s/clip/${encodeURIComponent(r.target_id)}?start=0&end=12&v=1`;
  if (r.target_type === 'build') return `/s/build/${encodeURIComponent(r.target_id)}`;
  if (r.target_type === 'profile') return `/s/profile/${encodeURIComponent(r.target_id)}?mode=1v1`;
  return '#';
}

export const OpsModerationPage: React.FC = () => {
  const qc = useQueryClient();
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const [onlyOpen, setOnlyOpen] = useState(true);

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const enabled = Boolean(adminToken.trim());

  const statusParam = onlyOpen ? 'open' : 'all';
  const { data, isLoading, error } = useQuery({
    queryKey: ['ops', 'reports', statusParam, enabled],
    queryFn: () => apiFetch<OpsReportsListOut>(`/api/ops/reports?status=${encodeURIComponent(statusParam)}&limit=80`),
    enabled,
    staleTime: 10_000,
  });

  const reports = data?.items ?? [];
  const openCount = useMemo(() => reports.filter((r) => r.status === 'open').length, [reports]);

  const resolveMut = useMutation({
    mutationFn: (reportId: string) => apiFetch(`/api/ops/reports/${encodeURIComponent(reportId)}/resolve`, { method: 'POST' }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'reports'] });
    },
  });

  const hideMut = useMutation({
    mutationFn: (r: OpsReport) =>
      apiFetch('/api/ops/moderation/hide_target', {
        method: 'POST',
        body: JSON.stringify({ target_type: r.target_type, target_id: r.target_id, reason: r.reason?.slice(0, 280) }),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'reports'] });
    },
  });

  const banMut = useMutation({
    mutationFn: (userId: string) =>
      apiFetch('/api/ops/moderation/soft_ban_user', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, duration_hours: 24, reason: 'ops soft ban (24h)' }),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'reports'] });
    },
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert size={18} className="text-slate-500" /> Moderation Inbox
          </CardTitle>
          <Badge variant={enabled ? 'success' : 'warning'}>{enabled ? `open ${openCount}` : 'Enter admin token'}</Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
            <div className="md:col-span-7">
              <Input
                label="Admin token"
                value={adminToken}
                onChange={(e) => setAdminToken(e.target.value)}
                placeholder="Set NEUROLEAGUE_ADMIN_TOKEN and paste it here"
              />
              <div className="mt-2 text-xs text-slate-500">
                This page calls admin-gated endpoints with <span className="font-mono">X-Admin-Token</span>.
              </div>
            </div>
            <div className="md:col-span-5 flex items-end gap-2">
              <Button type="button" variant={onlyOpen ? 'primary' : 'secondary'} onClick={() => setOnlyOpen(true)} className="w-full">
                Open only
              </Button>
              <Button type="button" variant={!onlyOpen ? 'primary' : 'secondary'} onClick={() => setOnlyOpen(false)} className="w-full">
                All
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {!enabled ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle size={18} className="text-amber-600" /> Admin disabled
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-slate-600">
            Set <span className="font-mono">NEUROLEAGUE_ADMIN_TOKEN</span> in your environment and paste it above.
          </CardContent>
        </Card>
      ) : null}

      {enabled ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Gavel size={18} className="text-slate-500" /> Reports
            </CardTitle>
            <Badge variant="neutral">{isLoading ? 'loading…' : `${reports.length} items`}</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {error ? <div className="text-sm text-red-600">{String(error)}</div> : null}
            {!isLoading && reports.length === 0 ? <div className="text-sm text-slate-500">No reports.</div> : null}
            {reports.map((r) => (
              <div key={r.id} className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={r.status === 'open' ? 'warning' : 'success'}>{r.status}</Badge>
                    <span className="text-sm font-semibold text-slate-800">{r.target_type}</span>
                    <span className="text-xs font-mono text-slate-500">{r.target_id}</span>
                  </div>
                  <a
                    className="text-xs text-brand-700 hover:underline inline-flex items-center gap-1"
                    href={targetUrl(r)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open target <ExternalLink size={14} />
                  </a>
                </div>

                <div className="text-sm text-slate-700">
                  <span className="font-semibold">Reason:</span> {r.reason}
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>reported_by {r.reporter_display_name ?? r.reporter_user_id ?? 'unknown'}</span>
                  <span>·</span>
                  <span>target_user {r.target_display_name ?? r.target_user_id ?? 'unknown'}</span>
                  <span>·</span>
                  <span>{new Date(r.created_at).toLocaleString()}</span>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    isLoading={resolveMut.isPending}
                    disabled={r.status !== 'open'}
                    onClick={() => resolveMut.mutate(r.id)}
                  >
                    Resolve
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    isLoading={hideMut.isPending}
                    onClick={() => hideMut.mutate(r)}
                  >
                    Hide globally
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    isLoading={banMut.isPending}
                    disabled={!r.target_user_id}
                    onClick={() => r.target_user_id && banMut.mutate(r.target_user_id)}
                  >
                    Soft ban (24h)
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};

