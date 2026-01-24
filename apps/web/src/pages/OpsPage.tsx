import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, FlaskConical, LineChart, ShieldAlert } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type MetricsSummaryOut = {
  range: string;
  from_date: string;
  to_date: string;
  kpis: Record<string, unknown>;
  daily: Array<{ date: string; metrics: Record<string, number> }>;
};

type FunnelOut = {
  funnel: string;
  range: string;
  steps: Array<{ step: string; users: number }>;
};

type FunnelDailyOut = {
  funnel: string;
  range: string;
  steps: Array<{
    step: string;
    today: number;
    avg_7d: number;
    yesterday: number;
    delta: number;
    delta_pct: number | null;
  }>;
};

type ExperimentOut = {
  key: string;
  status: string;
  variants: Array<{
    id: string;
    assigned: number;
    converted: number;
    conversion_rate: number;
    kpis?: Record<string, { converted: number; rate: number }>;
  }>;
};

type ExperimentsOut = {
  range: string;
  experiments: ExperimentOut[];
};

type HeroFeedExperimentSummaryOut = {
  range: string;
  experiment_key: string;
  variants: Record<
    string,
    {
      assigned: number;
      kpis: Record<string, { converted: number; rate: number }>;
    }
  >;
  guardrails: {
    http_5xx: number;
    http_429: number;
    video_load_fail_events: number;
    render_jobs_queued: number;
    render_jobs_running: number;
  };
};

type ShortsVariantsOut = {
  range: string;
  start_date: string;
  end_date: string;
  primary_kpi: string;
  filters: { utm_source?: string | null; utm_medium?: string | null; utm_campaign?: string | null };
  available_channels: string[];
  groups: Array<{
    utm_source: string;
    n_share_open: number;
    tables: Array<{
      key: string;
      variants: Array<{
        id: string;
        n: number;
        completion_rate: number;
        share_rate: number;
        start_click_rate: number;
        primary_kpi_rate: number;
        ranked_done_rate: number;
        app_open_deeplink_rate: number;
      }>;
    }>;
  }>;
  tables: Array<{
    key: string;
    variants: Array<{
      id: string;
      n: number;
      completion_rate: number;
      share_rate: number;
      start_click_rate: number;
      primary_kpi_rate: number;
      ranked_done_rate: number;
      app_open_deeplink_rate: number;
    }>;
  }>;
};

type PreflightLatestOut = {
  available: boolean;
  report: Record<string, any>;
  artifact_url: string | null;
  markdown_url: string | null;
};

type OpsStatusOut = {
  timestamp: string;
  ruleset_version: string;
  pack_hash: string | null;
  db: { ok: boolean; error?: string | null };
  storage: { ok: boolean; backend?: string; error?: string | null };
  ray: { ok: boolean; configured: boolean; nodes: number; error?: string | null };
  worker_ok: boolean;
  render_jobs: { queued: number; running: number };
  pending_jobs_count: number;
  reports_pending: number;
  scheduler: { enabled: boolean; interval_minutes: number };
  last_rollup_at: string | null;
  last_balance_report_at: string | null;
  last_backup_at: string | null;
  last_backup_key: string | null;
};

type RecentErrorsOut = {
  window_minutes: number;
  limit: number;
  items: Array<{
    path: string;
    method: string;
    status: number;
    count: number;
    last_request_id: string | null;
    last_at: string | null;
  }>;
};

type RecentAlertsOut = {
  limit: number;
  last_run_at: string | null;
  last_run: Record<string, any>;
  items: Array<{
    alert_key: string;
    summary: string | null;
    created_at: string;
    outbox_id: string | null;
    outbox_status: string | null;
    outbox_attempts: number | null;
    outbox_sent_at: string | null;
    outbox_last_error: string | null;
  }>;
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

export const OpsPage: React.FC = () => {
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const [range, setRange] = useState('7d');
  const [shortsChannel, setShortsChannel] = useState('all');

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const enabled = Boolean(adminToken.trim());

  const { data: summary, error: summaryError } = useQuery({
    queryKey: ['ops', 'metrics', 'summary', range, enabled],
    queryFn: () => apiFetch<MetricsSummaryOut>(`/api/ops/metrics/summary?range=${encodeURIComponent(range)}`),
    enabled,
    staleTime: 10_000,
  });

  const { data: funnel } = useQuery({
    queryKey: ['ops', 'metrics', 'funnel', range, enabled],
    queryFn: () => apiFetch<FunnelOut>(`/api/ops/metrics/funnel?range=${encodeURIComponent(range)}&funnel=growth_v1`),
    enabled,
    staleTime: 10_000,
  });

  const { data: shareFunnelDaily } = useQuery({
    queryKey: ['ops', 'metrics', 'funnel_daily', 'share_v1', range, enabled],
    queryFn: () => apiFetch<FunnelDailyOut>(`/api/ops/metrics/funnel_daily?range=${encodeURIComponent(range)}&funnel=share_v1`),
    enabled,
    staleTime: 10_000,
  });

  const { data: clipsFunnelDaily } = useQuery({
    queryKey: ['ops', 'metrics', 'funnel_daily', 'clips_v1', range, enabled],
    queryFn: () => apiFetch<FunnelDailyOut>(`/api/ops/metrics/funnel_daily?range=${encodeURIComponent(range)}&funnel=clips_v1`),
    enabled,
    staleTime: 10_000,
  });

  const { data: demoFunnelDaily } = useQuery({
    queryKey: ['ops', 'metrics', 'funnel_daily', 'demo_v1', range, enabled],
    queryFn: () => apiFetch<FunnelDailyOut>(`/api/ops/metrics/funnel_daily?range=${encodeURIComponent(range)}&funnel=demo_v1`),
    enabled,
    staleTime: 10_000,
  });

  const { data: experiments } = useQuery({
    queryKey: ['ops', 'metrics', 'experiments', range, enabled],
    queryFn: () => apiFetch<ExperimentsOut>(`/api/ops/metrics/experiments?range=${encodeURIComponent(range)}`),
    enabled,
    staleTime: 10_000,
  });

  const { data: heroFeedSummary } = useQuery({
    queryKey: ['ops', 'metrics', 'experiments', 'hero_feed_v1_summary', range, enabled],
    queryFn: () =>
      apiFetch<HeroFeedExperimentSummaryOut>(`/api/ops/metrics/experiments/hero_feed_v1_summary?range=${encodeURIComponent(range)}`),
    enabled,
    staleTime: 10_000,
  });

  const { data: experimentsToday } = useQuery({
    queryKey: ['ops', 'metrics', 'experiments', '1d', enabled],
    queryFn: () => apiFetch<ExperimentsOut>('/api/ops/metrics/experiments?range=1d'),
    enabled,
    staleTime: 10_000,
    refetchInterval: 30_000,
  });

  const { data: shortsVariants } = useQuery({
    queryKey: ['ops', 'metrics', 'shorts_variants', range, shortsChannel, enabled],
    queryFn: () => {
      let url = `/api/ops/metrics/shorts_variants?range=${encodeURIComponent(range)}`;
      if (shortsChannel !== 'all') url += `&utm_source=${encodeURIComponent(shortsChannel)}`;
      return apiFetch<ShortsVariantsOut>(url);
    },
    enabled,
    staleTime: 10_000,
  });

  const { data: preflight } = useQuery({
    queryKey: ['ops', 'preflight', enabled],
    queryFn: () => apiFetch<PreflightLatestOut>('/api/ops/preflight/latest'),
    enabled,
    staleTime: 10_000,
  });

  const { data: status } = useQuery({
    queryKey: ['ops', 'status', enabled],
    queryFn: () => apiFetch<OpsStatusOut>('/api/ops/status'),
    enabled,
    staleTime: 10_000,
  });

  const { data: recentErrors } = useQuery({
    queryKey: ['ops', 'metrics', 'errors_recent', enabled],
    queryFn: () => apiFetch<RecentErrorsOut>('/api/ops/metrics/errors_recent?minutes=60&limit=12'),
    enabled,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });

  const { data: recentAlerts } = useQuery({
    queryKey: ['ops', 'metrics', 'alerts_recent', enabled],
    queryFn: () => apiFetch<RecentAlertsOut>('/api/ops/metrics/alerts_recent?limit=12'),
    enabled,
    staleTime: 10_000,
    refetchInterval: 30_000,
  });

  const kpis = summary?.kpis ?? {};
  const kpiRows = useMemo(() => {
    const pairs = Object.entries(kpis);
    return pairs.map(([k, v]) => ({ key: k, value: v }));
  }, [kpis]);

  const latestDaily = useMemo(() => {
    const rows = summary?.daily ?? [];
    if (!rows.length) return null;
    return rows[rows.length - 1];
  }, [summary?.daily]);

  const todayMetrics = latestDaily?.metrics ?? {};
  const wishlistClicksToday = Number(todayMetrics['wishlist_click_users'] ?? 0);
  const demoKitDownloadsToday = Number(
    demoFunnelDaily?.steps?.find((s) => s.step === 'demo_kit_download')?.today ?? 0
  );
  const demoStartToday = Number(demoFunnelDaily?.steps?.find((s) => s.step === 'demo_run_start')?.today ?? 0);
  const demoDoneToday = Number(demoFunnelDaily?.steps?.find((s) => s.step === 'demo_run_done')?.today ?? 0);
  const demoCompletionRate = demoStartToday > 0 ? demoDoneToday / demoStartToday : null;

  const errors5xx = useMemo(() => {
    const items = recentErrors?.items ?? [];
    return items.filter((r) => r.status >= 500).reduce((acc, r) => acc + (r.count ?? 0), 0);
  }, [recentErrors?.items]);

  const availableShortsChannels = useMemo(() => {
    const chans = shortsVariants?.available_channels ?? [];
    const uniq = new Set<string>();
    for (const c of chans) {
      const v = (c || '').trim();
      if (v) uniq.add(v);
    }
    return ['all', ...Array.from(uniq)];
  }, [shortsVariants?.available_channels]);

  const preflightModes = useMemo(() => {
    const modes = preflight?.report?.modes;
    return Array.isArray(modes) ? modes : [];
  }, [preflight?.report]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert size={18} className="text-slate-500" /> Ops Dashboard
          </CardTitle>
          <Badge variant={enabled ? 'success' : 'warning'}>{enabled ? 'Admin enabled' : 'Enter admin token'}</Badge>
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
              <div className="mt-2 text-xs text-slate-500">
                This page calls admin-gated endpoints with <span className="font-mono">X-Admin-Token</span>.
              </div>
            </div>
            <div className="md:col-span-3">
              <Input label="Range" value={range} onChange={(e) => setRange(e.target.value)} placeholder="7d or 30d" />
            </div>
            <div className="md:col-span-3 flex items-end">
              <Button type="button" variant="secondary" onClick={() => window.location.reload()} className="w-full">
                Refresh
              </Button>
            </div>
          </div>
          {summaryError ? (
            <div className="text-sm text-red-600">
              Failed to load ops metrics: {String(summaryError)}
              <div className="text-xs text-slate-500 mt-1">Tip: set NEUROLEAGUE_ADMIN_TOKEN in the API process.</div>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/moderation">
              Moderation Inbox →
            </a>
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/featured">
              Featured →
            </a>
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/hero">
              Hero Clips →
            </a>
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/build-of-day">
              Build of Day →
            </a>
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/quests">
              Quests →
            </a>
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/discord">
              Discord →
            </a>
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/packs">
              Packs →
            </a>
            <a className="font-semibold text-brand-700 hover:underline" href="/ops/weekly">
              Weekly →
            </a>
            <span className="text-slate-400">·</span>
            <span className="text-slate-500">
              smoke: <span className="font-mono">NEUROLEAGUE_PUBLIC_BASE_URL=… NEUROLEAGUE_ADMIN_TOKEN=… make deploy-smoke</span>
            </span>
          </div>
        </CardContent>
      </Card>

      {enabled ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert size={18} className="text-slate-500" /> Deploy Sanity
            </CardTitle>
            <Badge variant="neutral">{status?.ruleset_version ?? '—'}</Badge>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-12 gap-3">
            <div className="md:col-span-4 rounded-xl border border-slate-200 bg-white px-3 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">DB</div>
              <div className="mt-1 flex items-center gap-2">
                <Badge variant={status?.db?.ok ? 'success' : 'danger'}>{status?.db?.ok ? 'ok' : 'fail'}</Badge>
                <span className="text-xs text-slate-600 truncate">{status?.db?.error ?? ''}</span>
              </div>
            </div>
            <div className="md:col-span-4 rounded-xl border border-slate-200 bg-white px-3 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">Storage</div>
              <div className="mt-1 flex items-center gap-2">
                <Badge variant={status?.storage?.ok ? 'success' : 'danger'}>{status?.storage?.ok ? 'ok' : 'fail'}</Badge>
                <span className="text-xs text-slate-600">{status?.storage?.backend ?? '—'}</span>
              </div>
            </div>
            <div className="md:col-span-4 rounded-xl border border-slate-200 bg-white px-3 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">Ray</div>
              <div className="mt-1 flex items-center gap-2">
                <Badge variant={status?.ray?.ok ? 'success' : 'warning'}>{status?.ray?.ok ? 'ok' : 'down'}</Badge>
                <span className="text-xs text-slate-600">nodes {status?.ray?.nodes ?? 0}</span>
              </div>
            </div>
            <div className="md:col-span-4 rounded-xl border border-slate-200 bg-white px-3 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">Worker</div>
              <div className="mt-1 flex items-center gap-2">
                <Badge variant={status?.worker_ok ? 'success' : 'warning'}>{status?.worker_ok ? 'ok' : 'down'}</Badge>
                <span className="text-xs text-slate-600">pending jobs {status?.pending_jobs_count ?? 0}</span>
              </div>
            </div>
            <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-3 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">Render Jobs</div>
              <div className="mt-1 text-xs text-slate-700">
                queued {status?.render_jobs?.queued ?? 0} · running {status?.render_jobs?.running ?? 0}
              </div>
            </div>
            <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-3 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">Scheduler</div>
              <div className="mt-1 text-xs text-slate-700">
                {status?.scheduler?.enabled ? 'enabled' : 'disabled'} · every {status?.scheduler?.interval_minutes ?? 0}m
              </div>
              <div className="mt-1 text-xs text-slate-500">
                last rollup {status?.last_rollup_at ?? '—'} · last balance {status?.last_balance_report_at ?? '—'}
              </div>
            </div>
            <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-3 py-3">
              <div className="text-[11px] font-bold text-slate-500 uppercase">Moderation</div>
              <div className="mt-1 text-xs text-slate-700">open reports {status?.reports_pending ?? 0}</div>
              <div className="mt-1 text-xs text-slate-500">last backup {status?.last_backup_at ?? '—'}</div>
            </div>
            <div className="md:col-span-12 text-xs text-slate-500">
              pack_hash: <span className="font-mono">{status?.pack_hash ?? '—'}</span>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert size={18} className="text-slate-500" /> Next Fest Live
              </CardTitle>
              <Badge variant="neutral">today</Badge>
            </CardHeader>
            <CardContent>
              {enabled ? (
                <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                  <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-3 py-3">
                    <div className="text-[11px] font-bold text-slate-500 uppercase">Demo completion</div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">
                      {demoCompletionRate !== null ? `${(demoCompletionRate * 100).toFixed(1)}%` : '—'}
                    </div>
                    <div className="mt-1 text-xs text-slate-600">
                      start {demoStartToday} · done {demoDoneToday}
                    </div>
                  </div>
                  <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-3 py-3">
                    <div className="text-[11px] font-bold text-slate-500 uppercase">Conversion</div>
                    <div className="mt-1 text-xs text-slate-700">kit downloads {demoKitDownloadsToday}</div>
                    <div className="mt-1 text-xs text-slate-700">wishlist clicks {wishlistClicksToday}</div>
                  </div>
                  <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-3 py-3">
                    <div className="text-[11px] font-bold text-slate-500 uppercase">Stability</div>
                    <div className="mt-1 text-xs text-slate-700">5xx errors (60m) {errors5xx}</div>
                    <div className="mt-1 text-xs text-slate-700">
                      render backlog {(status?.render_jobs?.queued ?? 0) + (status?.render_jobs?.running ?? 0)}
                    </div>
                  </div>
                  <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-3 py-3">
                    <div className="text-[11px] font-bold text-slate-500 uppercase">Alerts</div>
                    <div className="mt-1 text-xs text-slate-700">
                      last check <span className="font-mono">{recentAlerts?.last_run_at ?? '—'}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-700">recent alerts {recentAlerts?.items?.length ?? 0}</div>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-slate-500">Enter admin token to view festival KPIs.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert size={18} className="text-slate-500" /> Alerts
              </CardTitle>
              <Badge variant={recentAlerts?.items?.length ? 'warning' : 'neutral'}>
                {recentAlerts?.items?.length ? 'active' : 'none'}
              </Badge>
            </CardHeader>
            <CardContent>
              {enabled ? (
                <>
                  <div className="text-xs text-slate-500">
                    last check: <span className="font-mono">{recentAlerts?.last_run_at ?? '—'}</span>
                  </div>
                  {recentAlerts?.items?.length ? (
                    <div className="mt-3 space-y-2">
                      {recentAlerts.items.map((row) => (
                        <div key={row.alert_key + row.created_at} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-xs text-slate-700 font-mono truncate">{row.alert_key}</div>
                            <Badge variant={row.outbox_status === 'sent' ? 'success' : row.outbox_status ? 'warning' : 'neutral'}>
                              {row.outbox_status ?? '—'}
                            </Badge>
                          </div>
                          <div className="mt-1 text-[11px] text-slate-600">
                            {row.summary ?? '—'} · {row.created_at}
                          </div>
                          {row.outbox_last_error ? (
                            <div className="mt-1 text-[11px] text-red-600 font-mono truncate">{row.outbox_last_error}</div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 text-sm text-slate-500">No alerts sent recently.</div>
                  )}
                </>
              ) : (
                <div className="text-sm text-slate-500">Enter admin token to view alerts.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert size={18} className="text-slate-500" /> Recent Errors (last 60m)
              </CardTitle>
              <Badge variant={recentErrors?.items?.length ? 'warning' : 'success'}>
                {recentErrors?.items?.length ? 'active' : 'none'}
              </Badge>
            </CardHeader>
            <CardContent>
              {enabled ? (
                recentErrors?.items?.length ? (
                  <div className="space-y-2">
                    {recentErrors.items.map((row) => (
                      <div
                        key={`${row.method}:${row.path}:${row.status}`}
                        className="rounded-xl border border-slate-200 bg-white px-3 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-xs text-slate-700 font-mono truncate">
                            {row.method} {row.path}
                          </div>
                          <Badge variant={row.status >= 500 ? 'danger' : 'warning'}>{row.status}</Badge>
                        </div>
                        <div className="mt-1 text-[11px] text-slate-600">
                          count {row.count} · last {row.last_at ?? '—'} · request_id{' '}
                          <span className="font-mono">{row.last_request_id ?? '—'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">No errors in the last hour.</div>
                )
              ) : (
                <div className="text-sm text-slate-500">Enter admin token to view recent errors.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity size={18} className="text-brand-600" /> Growth KPIs
              </CardTitle>
              <Badge variant="neutral">{summary?.range ?? range}</Badge>
            </CardHeader>
            <CardContent>
              {enabled ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {kpiRows.length ? (
                    kpiRows.map((row) => (
                      <div key={row.key} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                        <div className="text-[11px] font-bold text-slate-500 uppercase">{row.key}</div>
                        <div className="text-sm font-semibold text-slate-800">{String(row.value)}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-sm text-slate-500">No rollups yet. Run make ops-metrics-rollup.</div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-slate-500">Enter admin token to view metrics.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <LineChart size={18} className="text-slate-500" /> Funnels (daily)
              </CardTitle>
              <Badge variant="neutral">{shareFunnelDaily?.range ?? range}</Badge>
            </CardHeader>
            <CardContent className="space-y-4">
              {enabled ? (
                <>
                  <div className="text-xs text-slate-500">Today · 7d avg · Δ vs yesterday</div>
                  {[
                    { title: 'Share funnel (share_v1)', data: shareFunnelDaily },
                    { title: 'Clips funnel (clips_v1)', data: clipsFunnelDaily },
                    { title: 'Demo funnel (demo_v1)', data: demoFunnelDaily },
                  ].map((block) => (
                    <div key={block.title} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-bold text-slate-800">{block.title}</div>
                        <Badge variant="neutral">{block.data?.steps?.length ? 'ok' : 'empty'}</Badge>
                      </div>
                      {block.data?.steps?.length ? (
                        <div className="mt-3 space-y-2">
                          {block.data.steps.map((s) => {
                            const deltaVariant = s.delta > 0 ? 'success' : s.delta < 0 ? 'danger' : 'neutral';
                            const avgLabel = Number.isFinite(s.avg_7d) ? s.avg_7d.toFixed(1) : '0.0';
                            return (
                              <div
                                key={s.step}
                                className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                              >
                                <div className="text-xs font-semibold text-slate-800">{s.step}</div>
                                <div className="flex items-center gap-2 text-xs">
                                  <Badge variant="neutral">today {s.today}</Badge>
                                  <Badge variant="neutral">avg {avgLabel}</Badge>
                                  <Badge variant={deltaVariant}>
                                    Δ {s.delta >= 0 ? '+' : ''}
                                    {s.delta}
                                  </Badge>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="mt-2 text-sm text-slate-500">No funnel data yet. Run ops rollup.</div>
                      )}
                    </div>
                  ))}
                </>
              ) : (
                <div className="text-sm text-slate-500">Enter admin token to view funnels.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <LineChart size={18} className="text-slate-500" /> Funnel (growth_v1)
              </CardTitle>
              <Badge variant="neutral">{funnel?.range ?? range}</Badge>
            </CardHeader>
            <CardContent>
              {funnel?.steps?.length ? (
                <div className="space-y-2">
                  {funnel.steps.map((s) => (
                    <div key={s.step} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2">
                      <div className="text-sm font-semibold text-slate-800">{s.step}</div>
                      <Badge variant="neutral">{s.users}</Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-500">No funnel data yet.</div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-5 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FlaskConical size={18} className="text-slate-500" /> Today Experiment Summary
              </CardTitle>
              <Badge variant="neutral">{experimentsToday?.range ?? '1d'}</Badge>
            </CardHeader>
            <CardContent className="space-y-2">
              {experimentsToday?.experiments?.length ? (
                experimentsToday.experiments.map((exp) => {
                  const sorted = [...exp.variants].sort((a, b) => (b.conversion_rate ?? 0) - (a.conversion_rate ?? 0));
                  const best = sorted[0];
                  const forkRate = best?.kpis?.blueprint_fork?.rate ?? best?.conversion_rate ?? 0;
                  const sampleOk = (best?.assigned ?? 0) >= 50;
                  return (
                    <div key={exp.key} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-bold text-slate-800 truncate">{exp.key}</div>
                        <div className="flex items-center gap-2">
                          <Badge variant={sampleOk ? 'neutral' : 'warning'}>{sampleOk ? 'ok' : 'low n'}</Badge>
                          <Badge variant="neutral">{exp.status}</Badge>
                        </div>
                      </div>
                      {best ? (
                        <div className="mt-1 text-xs text-slate-600">
                          winner <span className="font-mono font-semibold">{best.id}</span> · assigned {best.assigned} · fork{' '}
                          {(forkRate * 100).toFixed(1)}%
                        </div>
                      ) : (
                        <div className="mt-1 text-xs text-slate-500">No variants.</div>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="text-sm text-slate-500">No experiments found.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FlaskConical size={18} className="text-slate-500" /> Hero Feed v1 (KPI + guardrails)
              </CardTitle>
              <Badge variant="neutral">{heroFeedSummary?.range ?? range}</Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              {heroFeedSummary ? (
                <>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant={heroFeedSummary.guardrails.http_5xx > 0 ? 'warning' : 'neutral'}>5xx {heroFeedSummary.guardrails.http_5xx}</Badge>
                    <Badge variant={heroFeedSummary.guardrails.http_429 > 0 ? 'warning' : 'neutral'}>429 {heroFeedSummary.guardrails.http_429}</Badge>
                    <Badge variant={heroFeedSummary.guardrails.video_load_fail_events > 0 ? 'warning' : 'neutral'}>
                      video_load_fail {heroFeedSummary.guardrails.video_load_fail_events}
                    </Badge>
                    <Badge variant="neutral">
                      render backlog {heroFeedSummary.guardrails.render_jobs_queued + heroFeedSummary.guardrails.render_jobs_running} (
                      {heroFeedSummary.guardrails.render_jobs_queued}q/{heroFeedSummary.guardrails.render_jobs_running}r)
                    </Badge>
                  </div>

                  <div className="space-y-2">
                    {Object.entries(heroFeedSummary.variants ?? {}).map(([vid, v]) => {
                      const k = v.kpis ?? {};
                      const clip3 = k.clip_view_3s?.rate ?? 0;
                      const beat = k.beat_this_click?.rate ?? 0;
                      const done = k.match_done?.rate ?? 0;
                      const reply = k.reply_clip_shared?.rate ?? 0;
                      const quest = k.quest_claimed?.rate ?? 0;
                      const vfail = k.video_load_fail?.rate ?? 0;
                      return (
                        <div key={vid} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-bold text-slate-800">
                              <span className="font-mono">{vid}</span>
                            </div>
                            <Badge variant={v.assigned < 50 ? 'warning' : 'neutral'}>assigned {v.assigned}</Badge>
                          </div>
                          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-600">
                            <div>clip_view_3s {(clip3 * 100).toFixed(1)}%</div>
                            <div>beat_this_click {(beat * 100).toFixed(1)}%</div>
                            <div>match_done {(done * 100).toFixed(1)}%</div>
                            <div>reply_clip_shared {(reply * 100).toFixed(1)}%</div>
                            <div>quest_claimed {(quest * 100).toFixed(1)}%</div>
                            <div>video_load_fail {(vfail * 100).toFixed(1)}%</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="text-sm text-slate-500">No summary yet.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FlaskConical size={18} className="text-slate-500" /> Experiments
              </CardTitle>
              <Badge variant="neutral">{experiments?.range ?? range}</Badge>
            </CardHeader>
            <CardContent className="space-y-4">
              {experiments?.experiments?.length ? (
                experiments.experiments.map((exp) => (
                  <div key={exp.key} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-bold text-slate-800">{exp.key}</div>
                      <Badge variant="neutral">{exp.status}</Badge>
                    </div>
                    <div className="mt-2 space-y-1">
                      {[...exp.variants]
                        .sort((a, b) => (b.conversion_rate ?? 0) - (a.conversion_rate ?? 0))
                        .map((v, idx) => {
                          const forkRate = v.kpis?.blueprint_fork?.rate ?? v.conversion_rate ?? 0;
                          const shareOpenRate = v.kpis?.share_open?.rate ?? 0;
                          const startClickRate = v.kpis?.start_click?.rate ?? 0;
                          const guestStartRate = v.kpis?.guest_start_success?.rate ?? 0;
                          const firstReplayOpenRate = v.kpis?.first_replay_open?.rate ?? 0;
                          const rankedQueueRate = v.kpis?.ranked_queue?.rate ?? 0;
                          const completionRate = v.kpis?.clip_completion?.rate ?? 0;
                          const openRankedRate = v.kpis?.clip_open_ranked?.rate ?? 0;
                          const replayOpenRate = v.kpis?.replay_open?.rate ?? 0;
                          const rankedDoneRate = v.kpis?.ranked_done?.rate ?? 0;

                          return (
                            <div key={v.id} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                              <div className="flex items-center justify-between text-xs text-slate-700">
                                <span className="font-mono font-semibold">{v.id}</span>
                                <span className="flex items-center gap-2">
                                  {idx === 0 ? <Badge variant="brand">winner</Badge> : null}
                                  {v.assigned < 50 ? <Badge variant="warning">low n</Badge> : null}
                                  <span>
                                    assigned {v.assigned} · fork {(forkRate * 100).toFixed(1)}%
                                  </span>
                                </span>
                              </div>
                              <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-600">
                                <div>share_open {(shareOpenRate * 100).toFixed(1)}%</div>
                                <div>start_click {(startClickRate * 100).toFixed(1)}%</div>
                                <div>guest_start {(guestStartRate * 100).toFixed(1)}%</div>
                                <div>first_replay_open {(firstReplayOpenRate * 100).toFixed(1)}%</div>
                                <div>ranked_queue {(rankedQueueRate * 100).toFixed(1)}%</div>
                                <div>clip_completion {(completionRate * 100).toFixed(1)}%</div>
                                <div>clip_open_ranked {(openRankedRate * 100).toFixed(1)}%</div>
                                <div>replay_open {(replayOpenRate * 100).toFixed(1)}%</div>
                                <div>ranked_done {(rankedDoneRate * 100).toFixed(1)}%</div>
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-slate-500">No experiments found.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FlaskConical size={18} className="text-slate-500" /> Shorts Variants
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant="neutral">{shortsVariants?.range ?? range}</Badge>
                <select
                  value={shortsChannel}
                  onChange={(e) => setShortsChannel(e.target.value)}
                  className="h-8 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700"
                >
                  {availableShortsChannels.map((c) => (
                    <option key={c} value={c}>
                      {c === 'all' ? 'All channels' : c}
                    </option>
                  ))}
                </select>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {shortsVariants?.tables?.length ? (
                <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-bold text-slate-800">All</div>
                    <div className="text-xs text-slate-500">
                      {shortsVariants.start_date} → {shortsVariants.end_date}
                    </div>
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    Primary KPI: ranked_done / share_open
                  </div>
                  <div className="mt-2 space-y-3">
                    {shortsVariants.tables.map((tbl) => (
                      <div key={`all_${tbl.key}`} className="overflow-x-auto">
                        <div className="mb-1 text-[11px] font-semibold text-slate-600">{tbl.key}</div>
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-left text-slate-500">
                              <th className="py-1 pr-3">variant</th>
                              <th className="py-1 pr-3">n</th>
                              <th className="py-1 pr-3">kpi%</th>
                              <th className="py-1 pr-3">completion%</th>
                              <th className="py-1 pr-3">share%</th>
                              <th className="py-1 pr-3">start_click%</th>
                              <th className="py-1">app_open%</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tbl.variants.map((v) => (
                              <tr key={v.id} className="border-t border-slate-100 text-slate-700">
                                <td className="py-1 pr-3 font-mono font-semibold">{v.id}</td>
                                <td className="py-1 pr-3">{v.n}</td>
                                <td className="py-1 pr-3 font-semibold">{(v.primary_kpi_rate * 100).toFixed(1)}%</td>
                                <td className="py-1 pr-3">{(v.completion_rate * 100).toFixed(1)}%</td>
                                <td className="py-1 pr-3">{(v.share_rate * 100).toFixed(1)}%</td>
                                <td className="py-1 pr-3">{(v.start_click_rate * 100).toFixed(1)}%</td>
                                <td className="py-1">{(v.app_open_deeplink_rate * 100).toFixed(1)}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {shortsVariants?.groups?.length ? (
                shortsVariants.groups.map((g) => (
                  <div key={g.utm_source} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <div className="text-sm font-bold text-slate-800">{g.utm_source}</div>
                        <Badge variant="neutral">{g.n_share_open} share_open</Badge>
                      </div>
                      <div className="text-xs text-slate-500">
                        {shortsVariants?.start_date} → {shortsVariants?.end_date}
                      </div>
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">
                      Primary KPI: ranked_done / share_open
                    </div>
                    <div className="mt-2 space-y-3">
                      {g.tables.map((tbl) => (
                        <div key={`${g.utm_source}_${tbl.key}`} className="overflow-x-auto">
                          <div className="mb-1 text-[11px] font-semibold text-slate-600">{tbl.key}</div>
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-slate-500">
                                <th className="py-1 pr-3">variant</th>
                                <th className="py-1 pr-3">n</th>
                                <th className="py-1 pr-3">kpi%</th>
                                <th className="py-1 pr-3">completion%</th>
                                <th className="py-1 pr-3">share%</th>
                                <th className="py-1 pr-3">start_click%</th>
                                <th className="py-1">app_open%</th>
                              </tr>
                            </thead>
                            <tbody>
                              {tbl.variants.map((v) => (
                                <tr key={v.id} className="border-t border-slate-100 text-slate-700">
                                  <td className="py-1 pr-3 font-mono font-semibold">{v.id}</td>
                                  <td className="py-1 pr-3">{v.n}</td>
                                  <td className="py-1 pr-3 font-semibold">{(v.primary_kpi_rate * 100).toFixed(1)}%</td>
                                  <td className="py-1 pr-3">{(v.completion_rate * 100).toFixed(1)}%</td>
                                  <td className="py-1 pr-3">{(v.share_rate * 100).toFixed(1)}%</td>
                                  <td className="py-1 pr-3">{(v.start_click_rate * 100).toFixed(1)}%</td>
                                  <td className="py-1">{(v.app_open_deeplink_rate * 100).toFixed(1)}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              ) : !shortsVariants?.tables?.length ? (
                <div className="text-sm text-slate-500">No shorts variant data yet.</div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Patch Preflight</CardTitle>
              <Badge variant={preflight?.available ? 'success' : 'warning'}>{preflight?.available ? 'available' : 'missing'}</Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-xs text-slate-600">
                Compare two packs and write a deterministic report under <span className="font-mono">ops/</span>.
              </div>
              {preflight?.artifact_url ? (
                <a className="text-sm text-brand-700 font-bold hover:underline" href={preflight.artifact_url}>
                  Open latest JSON
                </a>
              ) : null}
              {preflight?.markdown_url ? (
                <a className="text-sm text-brand-700 font-bold hover:underline" href={preflight.markdown_url}>
                  Open latest MD
                </a>
              ) : null}
              {preflightModes.length ? (
                <div className="space-y-2">
                  {preflightModes.slice(0, 2).map((m: any) => (
                    <div key={String(m.mode)} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-bold text-slate-800">mode: {String(m.mode)}</div>
                        <Badge variant="neutral">pool {Number(m.pool_size ?? 0)}</Badge>
                      </div>
                      <div className="mt-2 text-xs text-slate-600 font-mono break-all">
                        {String(m.baseline_pack_hash ?? '').slice(0, 10)}… → {String(m.candidate_pack_hash ?? '').slice(0, 10)}…
                      </div>
                      {Array.isArray(m.top_shifts) && m.top_shifts.length ? (
                        <div className="mt-2 space-y-1">
                          {m.top_shifts.slice(0, 3).map((row: any) => (
                            <div key={String(row.blueprint_id)} className="text-xs text-slate-700">
                              {String(row.blueprint_name ?? row.blueprint_id)} Δ {Number(row.delta ?? 0).toFixed(3)}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="mt-2 text-xs text-slate-500">No shifts (or no data).</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-500">
                  No preflight report yet. Run <span className="font-mono">make ops-preflight</span>.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};
