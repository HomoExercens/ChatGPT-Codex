import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Hand } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Skeleton } from '../components/ui';
import { apiFetch } from '../lib/api';

type MetricRow = { converted: number; rate: number };

type GestureCancelReason = {
  source: string;
  reason: string;
  count: number;
  pct: number;
};

type GestureMisfire = {
  swipe_attempt_count: number;
  swipe_commit_count: number;
  swipe_cancel_count: number;
  tap_attempt_count: number;
  tap_cancel_count: number;
  misfire_score: number;
  cancel_reasons_top: GestureCancelReason[];
};

type GestureSampling = {
  sessions_n: number;
  attempts_n: number;
  sample_rate_used: number;
  cap_hit_rate: number;
  avg_dropped_count: number;
};

type GestureCoverage = {
  uach_available_rate: number;
  container_hint_coverage: number;
  unknown_segment_rate: number;
};

type GestureThresholdsConfig = Partial<{
  double_tap_ms: number;
  double_tap_slop_px: number;
  tap_slop_px: number;
  drag_start_px: number;
  vertical_dominance: number;
  swipe_commit_frac: number;
  swipe_commit_min_px: number;
  swipe_velocity_px_ms: number;
}>;

type VariantSummary = {
  assigned: number;
  kpis: Record<string, MetricRow>;
  misfire: GestureMisfire;
  sampling: GestureSampling;
  coverage: GestureCoverage;
  thresholds_config?: GestureThresholdsConfig;
};

type Guardrails = {
  http_5xx: number;
  http_429: number;
  video_load_fail_events: number;
  render_jobs_queued: number;
  render_jobs_running: number;
};

type GestureThresholdsExperimentSummary = {
  range: string;
  segment: string;
  experiment_key: string;
  variants: Record<string, VariantSummary>;
  guardrails: Guardrails;
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

function fmtPct(n: unknown): string {
  const x = Number(n);
  if (!Number.isFinite(x)) return '—';
  return `${(x * 100).toFixed(1)}%`;
}

function fmtCount(n: unknown): string {
  const x = Number(n);
  if (!Number.isFinite(x)) return '—';
  if (Math.abs(x) >= 1000) return x.toFixed(0);
  if (Math.abs(x - Math.round(x)) < 1e-6) return String(Math.round(x));
  return x.toFixed(1);
}

function misfireBadgeVariant(score: number): 'success' | 'warning' | 'error' | 'neutral' {
  if (!Number.isFinite(score)) return 'neutral';
  if (score <= 0.22) return 'success';
  if (score <= 0.35) return 'warning';
  return 'error';
}

function guardrailVariant(n: number): 'neutral' | 'warning' {
  if (!Number.isFinite(n)) return 'neutral';
  return n > 0 ? 'warning' : 'neutral';
}

export const OpsGesturesPage: React.FC = () => {
  const qc = useQueryClient();
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const [range, setRange] = useState<'1d' | '7d'>('7d');
  const [segment, setSegment] = useState<'all' | 'android_chrome' | 'android_twa' | 'desktop_chrome' | 'ios_safari' | 'ios_chrome'>('all');

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const enabled = Boolean(adminToken.trim());

  const { data, error, isFetching } = useQuery({
    queryKey: ['ops', 'metrics', 'experiments', 'gesture_thresholds_v1_summary', range, segment, enabled],
    queryFn: () =>
      apiFetch<GestureThresholdsExperimentSummary>(
        `/api/ops/metrics/experiments/gesture_thresholds_v1_summary?range=${encodeURIComponent(range)}&segment=${encodeURIComponent(segment)}`
      ),
    enabled,
    staleTime: 10_000,
  });

  const variants = useMemo(() => {
    const entries = Object.entries(data?.variants ?? {});
    const rank = (k: string) => (k === 'control' ? 0 : k === 'variant_a' ? 1 : k === 'variant_b' ? 2 : 99);
    return entries.sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]));
  }, [data?.variants]);

  const hasVariants = variants.length > 0;
  const guardrails = data?.guardrails;
  const backlog = (guardrails?.render_jobs_queued ?? 0) + (guardrails?.render_jobs_running ?? 0);
  const samplingSummary = useMemo(() => {
    let sessions = 0;
    let attempts = 0;
    let capHitSessions = 0;
    let droppedSum = 0;
    let sampleRateSum = 0;
    for (const [, v] of variants) {
      const s = v?.sampling;
      const sn = Number(s?.sessions_n ?? 0);
      if (!Number.isFinite(sn) || sn <= 0) continue;
      sessions += sn;
      attempts += Number(s?.attempts_n ?? 0) || 0;
      capHitSessions += (Number(s?.cap_hit_rate ?? 0) || 0) * sn;
      droppedSum += (Number(s?.avg_dropped_count ?? 0) || 0) * sn;
      sampleRateSum += (Number(s?.sample_rate_used ?? 0) || 0) * sn;
    }
    return {
      sessions,
      attempts,
      cap_hit_rate: sessions > 0 ? capHitSessions / sessions : 0,
      avg_dropped_count: sessions > 0 ? droppedSum / sessions : 0,
      sample_rate_used: sessions > 0 ? sampleRateSum / sessions : 0,
    };
  }, [variants]);

  const coverageSummary = useMemo(() => {
    let sessions = 0;
    let uachSessions = 0;
    let hintSessions = 0;
    let unknownSessions = 0;
    for (const [, v] of variants) {
      const sn = Number(v?.assigned ?? 0);
      if (!Number.isFinite(sn) || sn <= 0) continue;
      sessions += sn;
      const c = v?.coverage as Partial<GestureCoverage> | undefined;
      uachSessions += (Number(c?.uach_available_rate ?? 0) || 0) * sn;
      hintSessions += (Number(c?.container_hint_coverage ?? 0) || 0) * sn;
      unknownSessions += (Number(c?.unknown_segment_rate ?? 0) || 0) * sn;
    }
    return {
      sessions,
      uach_available_rate: sessions > 0 ? uachSessions / sessions : 0,
      container_hint_coverage: sessions > 0 ? hintSessions / sessions : 0,
      unknown_segment_rate: sessions > 0 ? unknownSessions / sessions : 0,
    };
  }, [variants]);

  return (
    <div className="max-w-6xl mx-auto space-y-4" data-testid="ops-gestures-page">
      <div className="flex items-center justify-between gap-3">
        <Link to="/ops" className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-fg">
          <ChevronLeft size={16} /> Back
        </Link>
        <div className="flex items-center gap-2">
          <Badge variant="neutral">Gestures</Badge>
          <Badge variant="neutral">{data?.range ?? range}</Badge>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Hand size={18} className="text-muted" /> Gesture Tuning
          </CardTitle>
          <Badge variant={enabled ? 'success' : 'warning'}>{enabled ? 'Admin enabled' : 'Enter admin token'}</Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
            <div className="md:col-span-6">
              <Input label="Admin token" value={adminToken} onChange={(e) => setAdminToken(e.target.value)} placeholder="NEUROLEAGUE_ADMIN_TOKEN" />
              <div className="mt-2 text-xs text-muted">
                Uses <span className="font-mono">X-Admin-Token</span> via localStorage (<span className="font-mono">{ADMIN_TOKEN_KEY}</span>).
              </div>
            </div>

            <div className="md:col-span-3 space-y-1">
              <div className="block text-xs font-bold text-muted uppercase tracking-wider">Range</div>
              <div className="flex gap-2">
                {(['1d', '7d'] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    className={`flex-1 h-12 px-3 rounded-2xl border text-xs font-extrabold transition-colors ${
                      range === r
                        ? 'border-brand-500/35 bg-brand-500/12 text-fg shadow-glow-brand'
                        : 'border-border/12 bg-surface-2/35 text-fg/80 hover:bg-surface-2/45'
                    }`}
                    onClick={() => setRange(r)}
                  >
                    {r === '1d' ? '24h' : '7d'}
                  </button>
                ))}
              </div>
            </div>

            <div className="md:col-span-3 flex items-end gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => qc.invalidateQueries({ queryKey: ['ops', 'metrics', 'experiments', 'gesture_thresholds_v1_summary'] })}
                className="w-full"
              >
                Refresh
              </Button>
            </div>
          </div>

          <div className="space-y-1">
            <div className="block text-xs font-bold text-muted uppercase tracking-wider">Segment</div>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ['all', 'All'],
                  ['android_chrome', 'Android · Chrome'],
                  ['android_twa', 'Android · TWA'],
                  ['desktop_chrome', 'Desktop · Chrome'],
                  ['ios_safari', 'iOS · Safari'],
                  ['ios_chrome', 'iOS · Chrome'],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`h-11 px-3 rounded-2xl border text-xs font-extrabold transition-colors ${
                    segment === id
                      ? 'border-brand-500/35 bg-brand-500/12 text-fg shadow-glow-brand'
                      : 'border-border/12 bg-surface-2/35 text-fg/80 hover:bg-surface-2/45'
                  }`}
                  onClick={() => setSegment(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="text-xs text-muted">
              Segment is derived from user-agent + optional <span className="font-mono">X-App-Container</span> hint. If you see 0 samples, do not interpret misfire/KPI deltas.
            </div>
          </div>

          {error ? (
            <div className="text-sm text-danger-500 break-words">
              Failed to load: {String(error)}
              <div className="text-xs text-muted mt-1">Tip: set NEUROLEAGUE_ADMIN_TOKEN in the API process.</div>
            </div>
          ) : null}

          {enabled && guardrails ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant={guardrailVariant(guardrails.http_5xx)}>5xx {guardrails.http_5xx}</Badge>
              <Badge variant={guardrailVariant(guardrails.http_429)}>429 {guardrails.http_429}</Badge>
              <Badge variant={guardrailVariant(guardrails.video_load_fail_events)}>video_load_fail {guardrails.video_load_fail_events}</Badge>
              <Badge variant={backlog > 0 ? 'warning' : 'neutral'}>
                render backlog {backlog} ({guardrails.render_jobs_queued}q/{guardrails.render_jobs_running}r)
              </Badge>
            </div>
          ) : enabled ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="neutral">guardrails —</Badge>
            </div>
          ) : null}

          {enabled ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant={samplingSummary.sessions > 0 ? 'neutral' : 'warning'}>sample sessions {fmtCount(samplingSummary.sessions)}</Badge>
              <Badge variant={samplingSummary.sessions > 0 ? 'neutral' : 'warning'}>sample attempts {fmtCount(samplingSummary.attempts)}</Badge>
              <Badge variant={misfireBadgeVariant(samplingSummary.cap_hit_rate)}>cap_hit {fmtPct(samplingSummary.cap_hit_rate)}</Badge>
              <Badge variant="neutral">avg dropped {fmtCount(samplingSummary.avg_dropped_count)}</Badge>
              <Badge variant="neutral">sample_rate {fmtPct(samplingSummary.sample_rate_used)}</Badge>
            </div>
          ) : null}

          {enabled ? (
            <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="ops-gestures-coverage-strip">
              <Badge variant={coverageSummary.sessions > 0 ? 'neutral' : 'warning'}>sessions {fmtCount(coverageSummary.sessions)}</Badge>
              <Badge variant="neutral">uaData {fmtPct(coverageSummary.uach_available_rate)}</Badge>
              <Badge variant="neutral">container_hint {fmtPct(coverageSummary.container_hint_coverage)}</Badge>
              <Badge variant={segment === 'all' && coverageSummary.unknown_segment_rate > 0.25 ? 'warning' : 'neutral'}>
                unknown {fmtPct(coverageSummary.unknown_segment_rate)}
              </Badge>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {!enabled ? (
        <Card>
          <CardContent>
            <div className="text-sm text-muted">Paste an admin token to enable gesture ops.</div>
          </CardContent>
        </Card>
      ) : null}

      {enabled ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {isFetching && !data
            ? ['control', 'variant_a', 'variant_b'].map((k) => (
                <Card key={k}>
                  <CardHeader>
                    <CardTitle className="text-base">
                      <span className="font-mono">{k}</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Skeleton className="h-8 w-28" />
                    <div className="grid grid-cols-2 gap-2">
                      {Array.from({ length: 4 }).map((_, idx) => (
                        <Skeleton key={idx} className="h-14 w-full" />
                      ))}
                    </div>
                    <Skeleton className="h-20 w-full" />
                  </CardContent>
                </Card>
              ))
            : variants.map(([vid, v]) => {
                const k = v.kpis ?? {};
                const mis = v.misfire ?? ({} as GestureMisfire);
                const samp = v.sampling ?? ({} as GestureSampling);
                const score = Number(mis.misfire_score ?? 0);
                const label =
                  vid === 'control' ? 'Control' : vid === 'variant_a' ? 'Variant A' : vid === 'variant_b' ? 'Variant B' : vid;

                const reasons = (mis.cancel_reasons_top ?? []).slice(0, 3);
                const hasSample = Number(samp.sessions_n ?? 0) > 0;
                const cov = v.coverage ?? ({} as GestureCoverage);
                const cfg = (v.thresholds_config ?? {}) as GestureThresholdsConfig;
                const hasCfg =
                  Object.values(cfg).filter((x) => Number.isFinite(Number(x))).length > 0;
                return (
                  <Card key={vid} className="overflow-hidden">
                    <CardHeader>
                      <CardTitle className="flex items-center justify-between gap-3 text-base">
                        <span className="font-mono">{label}</span>
                        <div className="flex items-center gap-2">
                          <Badge variant={v.assigned < 50 ? 'warning' : 'neutral'}>sessions {v.assigned}</Badge>
                          <Badge variant={hasSample ? 'neutral' : 'warning'}>sample {fmtCount(samp.sessions_n ?? 0)}</Badge>
                        </div>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          ['clip_view_3s', k.clip_view_3s],
                          ['beat_this_click', k.beat_this_click],
                          ['match_done', k.match_done],
                          ['reply_clip_shared', k.reply_clip_shared],
                        ].map(([key, row]) => (
                          <div key={key} className="rounded-2xl border border-border/12 bg-surface-2/35 px-3 py-3">
                            <div className="text-[11px] font-bold text-muted uppercase">{key}</div>
                            <div className="mt-1 flex items-baseline justify-between gap-2">
                              <div className="text-sm font-extrabold tracking-tight text-fg nl-tabular-nums">{fmtPct((row as MetricRow | undefined)?.rate ?? 0)}</div>
                              <div className="text-[11px] text-muted nl-tabular-nums">{fmtCount((row as MetricRow | undefined)?.converted ?? 0)}</div>
                            </div>
                          </div>
                        ))}
                      </div>

                      <div className={`rounded-2xl border px-3 py-3 ${hasSample ? 'border-border/12 bg-surface-2/35' : 'border-warning-500/25 bg-warning-500/10'}`}>
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-[11px] font-bold text-muted uppercase">Sampling / Bias</div>
                          <Badge variant={hasSample ? 'neutral' : 'warning'}>{hasSample ? 'ok' : 'no sample'}</Badge>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted nl-tabular-nums">
                          <div>sessions {fmtCount(samp.sessions_n ?? 0)}</div>
                          <div>attempts {fmtCount(samp.attempts_n ?? 0)}</div>
                          <div>cap_hit {fmtPct(samp.cap_hit_rate ?? 0)}</div>
                          <div>avg dropped {fmtCount(samp.avg_dropped_count ?? 0)}</div>
                          <div>sample_rate {fmtPct(samp.sample_rate_used ?? 0)}</div>
                        </div>
                        {!hasSample ? (
                          <div className="mt-2 text-xs text-muted">
                            No sampled sessions for this segment/window. Do not interpret misfire or KPI deltas.
                          </div>
                        ) : null}
                      </div>

                      <div className="rounded-2xl border border-border/12 bg-surface-2/35 px-3 py-3" data-testid={`ops-gestures-coverage-variant-${vid}`}>
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-[11px] font-bold text-muted uppercase">Coverage / Trust</div>
                          <Badge
                            variant={segment === 'all' && Number(cov.unknown_segment_rate ?? 0) > 0.25 ? 'warning' : 'neutral'}
                            className="nl-tabular-nums"
                          >
                            unknown {fmtPct(cov.unknown_segment_rate ?? 0)}
                          </Badge>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted nl-tabular-nums">
                          <div>uaData {fmtPct(cov.uach_available_rate ?? 0)}</div>
                          <div>container_hint {fmtPct(cov.container_hint_coverage ?? 0)}</div>
                        </div>
                        <div className="mt-2 text-xs text-muted">
                          UAData coverage is best-effort (often HTTPS Chromium). container_hint comes from <span className="font-mono">X-App-Container</span>.
                        </div>
                      </div>

                      <div
                        className="rounded-2xl border border-border/12 bg-surface-2/35 px-3 py-3"
                        data-testid={`ops-gestures-config-echo-${vid}`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-[11px] font-bold text-muted uppercase">Current config</div>
                          <Badge variant={hasCfg ? 'neutral' : 'warning'}>{hasCfg ? 'ok' : 'missing'}</Badge>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted nl-tabular-nums">
                          <div>double tap {fmtCount(cfg.double_tap_ms)}ms</div>
                          <div>double slop {fmtCount(cfg.double_tap_slop_px)}px</div>
                          <div>tap slop {fmtCount(cfg.tap_slop_px)}px</div>
                          <div>drag start {fmtCount(cfg.drag_start_px)}px</div>
                          <div>vertical dom {fmtCount(cfg.vertical_dominance)}</div>
                          <div>commit frac {fmtCount(cfg.swipe_commit_frac)}</div>
                          <div>commit min {fmtCount(cfg.swipe_commit_min_px)}px</div>
                          <div>velocity {fmtCount(cfg.swipe_velocity_px_ms)}px/ms</div>
                        </div>
                        {!hasCfg ? (
                          <div className="mt-2 text-xs text-muted">
                            Config not available for this variant. Check the <span className="font-mono">gesture_thresholds_v1</span> experiment row.
                          </div>
                        ) : null}
                      </div>

                      <div className="rounded-2xl border border-border/12 bg-surface-2/35 px-3 py-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-[11px] font-bold text-muted uppercase">Misfire</div>
                          <Badge variant={misfireBadgeVariant(score)} className="nl-tabular-nums">
                            {fmtPct(score)}
                          </Badge>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted nl-tabular-nums">
                          <div>swipe attempts {fmtCount(mis.swipe_attempt_count ?? 0)}</div>
                          <div>swipe cancels {fmtCount(mis.swipe_cancel_count ?? 0)}</div>
                          <div>tap attempts {fmtCount(mis.tap_attempt_count ?? 0)}</div>
                          <div>tap cancels {fmtCount(mis.tap_cancel_count ?? 0)}</div>
                        </div>
                        <div className="mt-3 space-y-1">
                          <div className="text-[11px] font-bold text-muted uppercase">Cancel reasons (top)</div>
                          {reasons.length ? (
                            reasons.map((r, idx) => (
                              <div key={`${r.source}:${r.reason}:${idx}`} className="flex items-center justify-between gap-2 text-xs text-fg/80 nl-tabular-nums">
                                <div className="truncate">
                                  <span className="font-mono text-fg/70">{r.source}</span>
                                  <span className="text-muted/60 mx-1">·</span>
                                  <span className="font-semibold">{r.reason}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-muted">{fmtCount(r.count)}</span>
                                  <span className="text-muted">{fmtPct(r.pct)}</span>
                                </div>
                              </div>
                            ))
                          ) : (
                            <div className="text-xs text-muted">No attempt telemetry in this window.</div>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
          {!isFetching && data && !hasVariants ? (
            <Card className="lg:col-span-3">
              <CardContent>
                <div className="text-sm text-muted">No telemetry for this period yet.</div>
                <div className="mt-2 text-xs text-muted/70">
                  Ensure <span className="font-mono">tap_attempt</span>/<span className="font-mono">swipe_attempt</span> are enabled and sampled, then re-check after a few play sessions.
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
