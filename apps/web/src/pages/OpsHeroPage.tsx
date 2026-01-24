import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type HeroMode = '1v1' | 'team';

type HeroCandidate = {
  replay_id: string;
  match_id?: string | null;
  user_id?: string | null;
  created_at?: string;
  wow_score?: number;
  wow_breakdown?: Record<string, number>;
  engagement?: Record<string, unknown>;
  features?: Record<string, unknown>;
  diversity?: Record<string, unknown>;
  diversity_penalty_selected?: number;
  diversity_penalty_selected_detail?: Record<string, unknown>;
  diversity_penalty_vs_selected?: number;
  diversity_penalty_vs_selected_detail?: Record<string, unknown>;
};

type HeroCandidatesOut = {
  generated_at?: string | null;
  ruleset_version?: string | null;
  window_days?: number | null;
  requested_range?: string | null;
  config?: Record<string, unknown>;
  by_mode?: Record<
    string,
    {
      pinned: string[];
      excluded: string[];
      selected: string[];
      items: HeroCandidate[];
    }
  >;
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

function fmtNum(n: unknown): string {
  const x = Number(n);
  if (!Number.isFinite(x)) return '—';
  return x.toFixed(3);
}

export const OpsHeroPage: React.FC = () => {
  const qc = useQueryClient();
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const [range, setRange] = useState('14d');
  const [mode, setMode] = useState<HeroMode>('1v1');

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const enabled = Boolean(adminToken.trim());

  const { data, error, isFetching } = useQuery({
    queryKey: ['ops', 'hero_clips', 'candidates', range, enabled],
    queryFn: () => apiFetch<HeroCandidatesOut>(`/api/ops/hero_clips/candidates?range=${encodeURIComponent(range)}`),
    enabled,
    staleTime: 10_000,
  });

  const selectedIds = useMemo(() => new Set((data?.by_mode?.[mode]?.selected ?? []).map((x) => String(x))), [data, mode]);
  const pinnedIds = useMemo(() => new Set((data?.by_mode?.[mode]?.pinned ?? []).map((x) => String(x))), [data, mode]);
  const excludedIds = useMemo(() => new Set((data?.by_mode?.[mode]?.excluded ?? []).map((x) => String(x))), [data, mode]);

  const recomputeMutation = useMutation({
    mutationFn: () => apiFetch('/api/ops/hero_clips/recompute', { method: 'POST' }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'hero_clips', 'candidates'] });
    },
  });

  const updateOverrideMutation = useMutation({
    mutationFn: (payload: { mode: HeroMode; op: 'pin' | 'unpin' | 'exclude' | 'unexclude'; replay_id: string }) =>
      apiFetch('/api/ops/hero_clips/override', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'hero_clips', 'candidates'] });
    },
  });

  const items = data?.by_mode?.[mode]?.items ?? [];

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-3">
        <Link to="/ops" className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-fg">
          <ChevronLeft size={16} /> Back
        </Link>
        <div className="flex items-center gap-2">
          <Badge variant="neutral">Hero Clips</Badge>
          <Badge variant="neutral">{mode}</Badge>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles size={18} className="text-muted" /> Hero Auto-curator v2
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
            <div className="md:col-span-6">
              <Input label="Admin token" value={adminToken} onChange={(e) => setAdminToken(e.target.value)} placeholder="NEUROLEAGUE_ADMIN_TOKEN" />
              <div className="mt-2 text-xs text-muted">
                Uses <span className="font-mono">X-Admin-Token</span> via localStorage (<span className="font-mono">{ADMIN_TOKEN_KEY}</span>).
              </div>
            </div>
            <div className="md:col-span-3">
              <Input label="Range" value={range} onChange={(e) => setRange(e.target.value)} placeholder="14d" />
            </div>
            <div className="md:col-span-3 flex items-end gap-2">
              <Button type="button" variant="secondary" onClick={() => qc.invalidateQueries({ queryKey: ['ops', 'hero_clips', 'candidates'] })} className="w-full">
                Refresh
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <button
              type="button"
              className={`px-3 py-2 rounded-2xl border transition-colors ${
                mode === '1v1'
                  ? 'border-brand-500/35 bg-brand-500/12 text-fg shadow-glow-brand'
                  : 'border-border/12 bg-surface-2/35 text-fg/80 hover:bg-surface-2/45'
              }`}
              onClick={() => setMode('1v1')}
            >
              1v1
            </button>
            <button
              type="button"
              className={`px-3 py-2 rounded-2xl border transition-colors ${
                mode === 'team'
                  ? 'border-brand-500/35 bg-brand-500/12 text-fg shadow-glow-brand'
                  : 'border-border/12 bg-surface-2/35 text-fg/80 hover:bg-surface-2/45'
              }`}
              onClick={() => setMode('team')}
            >
              team
            </button>
            <span className="text-muted/60">·</span>
            <span className="text-muted">
              generated: <span className="font-mono">{data?.generated_at ?? '—'}</span>
            </span>
            <span className="text-muted/60">·</span>
            <span className="text-muted">
              ruleset: <span className="font-mono">{data?.ruleset_version ?? '—'}</span>
            </span>
            <span className="text-muted/60">·</span>
            <span className="text-muted">
              window: <span className="font-mono">{data?.window_days ?? '—'}d</span>
            </span>
          </div>

          {error ? <div className="text-sm text-danger-500 break-words">Failed to load: {String(error)}</div> : null}
          {enabled ? (
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" disabled={recomputeMutation.isPending} onClick={() => recomputeMutation.mutate()}>
                {recomputeMutation.isPending ? 'Recomputing…' : 'Recompute now'}
              </Button>
              <div className="text-xs text-muted flex items-center">
                Writes <span className="font-mono mx-1">ops/hero_clips.auto.json</span> + merges override.
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted">Paste an admin token to enable ops.</div>
          )}
        </CardContent>
      </Card>

      {enabled ? (
        <Card>
          <CardHeader>
            <CardTitle>Override</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-sm text-muted">Pinned clips always appear first. Excluded clips never appear.</div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="neutral">Pinned: {data?.by_mode?.[mode]?.pinned?.length ?? 0}</Badge>
              <Badge variant="neutral">Excluded: {data?.by_mode?.[mode]?.excluded?.length ?? 0}</Badge>
              <Badge variant="neutral">Selected: {data?.by_mode?.[mode]?.selected?.length ?? 0}</Badge>
            </div>

            <div className="space-y-2">
              <div className="text-xs font-bold text-muted uppercase">Pinned</div>
              <div className="flex flex-wrap gap-2">
                {(data?.by_mode?.[mode]?.pinned ?? []).slice(0, 12).map((rid) => (
                  <div key={rid} className="px-2 py-1 rounded-2xl border border-border/12 bg-surface-2/35 flex items-center gap-2">
                    <a className="font-mono text-xs text-fg/80 hover:underline" href={`/s/clip/${encodeURIComponent(rid)}`} target="_blank" rel="noreferrer">
                      {rid}
                    </a>
                    <button
                      type="button"
                      className="text-xs font-semibold text-brand-200 hover:underline"
                      onClick={() => updateOverrideMutation.mutate({ mode, op: 'unpin', replay_id: rid })}
                    >
                      Unpin
                    </button>
                  </div>
                ))}
              </div>
              {(data?.by_mode?.[mode]?.pinned ?? []).length > 12 ? <div className="text-xs text-muted">…</div> : null}
            </div>

            <div className="space-y-2">
              <div className="text-xs font-bold text-muted uppercase">Excluded</div>
              <div className="flex flex-wrap gap-2">
                {(data?.by_mode?.[mode]?.excluded ?? []).slice(0, 12).map((rid) => (
                  <div key={rid} className="px-2 py-1 rounded-2xl border border-border/12 bg-surface-2/35 flex items-center gap-2">
                    <a className="font-mono text-xs text-fg/80 hover:underline" href={`/s/clip/${encodeURIComponent(rid)}`} target="_blank" rel="noreferrer">
                      {rid}
                    </a>
                    <button
                      type="button"
                      className="text-xs font-semibold text-brand-200 hover:underline"
                      onClick={() => updateOverrideMutation.mutate({ mode, op: 'unexclude', replay_id: rid })}
                    >
                      Unexclude
                    </button>
                  </div>
                ))}
              </div>
              {(data?.by_mode?.[mode]?.excluded ?? []).length > 12 ? <div className="text-xs text-muted">…</div> : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {enabled ? (
        <Card>
          <CardHeader>
            <CardTitle>Top candidates (50)</CardTitle>
            <div className="text-xs text-muted">Deterministic scoring + reliability shrink + diversity constraints.</div>
          </CardHeader>
          <CardContent className="space-y-3">
            {isFetching && !items.length ? <div className="text-sm text-muted">Loading…</div> : null}
            {items.length ? (
              <div className="space-y-3">
                {items.map((it, idx) => {
                  const rid = String(it.replay_id || '');
                  const isPinned = pinnedIds.has(rid);
                  const isExcluded = excludedIds.has(rid);
                  const isSelected = selectedIds.has(rid);
                  const bd = it.wow_breakdown ?? {};
                  const reliability = (bd as any).reliability_factor;
                  const decay = (bd as any).decay;
                  const completionWilson = (bd as any).completion_rate_wilson;
                  const completionRaw = (bd as any).completion_rate;
                  const divSel = it.diversity_penalty_selected ?? (bd as any).diversity_penalty_selected;
                  const divVs = it.diversity_penalty_vs_selected ?? (bd as any).diversity_penalty_vs_selected;
                  const diversity = (it.diversity ?? {}) as any;
                  return (
                    <div key={rid} className="p-3 rounded-3xl border border-border/12 bg-surface-2/35 shadow-glass">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="neutral">#{idx + 1}</Badge>
                            <a className="font-mono text-xs text-fg hover:underline" href={`/s/clip/${encodeURIComponent(rid)}`} target="_blank" rel="noreferrer">
                              {rid}
                            </a>
                            <Badge variant="success">wow {fmtNum(it.wow_score)}</Badge>
                            {isSelected ? <Badge variant="brand">SELECTED</Badge> : null}
                            {isPinned ? <Badge variant="warning">PIN</Badge> : null}
                            {isExcluded ? <Badge variant="error">EXCLUDED</Badge> : null}
                          </div>
                          <div className="mt-1 text-xs text-muted">
                            user: <span className="font-mono">{it.user_id ?? '—'}</span> · portal:{' '}
                            <span className="font-mono">{String(diversity.portal_id ?? '—')}</span> · synergy:{' '}
                            <span className="font-mono">{String(diversity.primary_synergy ?? '—')}</span> · creature:{' '}
                            <span className="font-mono">{String(diversity.primary_creature ?? '—')}</span>
                          </div>
                          <div className="mt-1 text-xs text-muted">
                            reliability {fmtNum(reliability)} · decay {fmtNum(decay)} · completion(wilson) {fmtNum(completionWilson)} · raw {fmtNum(completionRaw)}
                          </div>
                        </div>
                        <div className="shrink-0 flex flex-col gap-2 items-end">
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              variant="secondary"
                              disabled={updateOverrideMutation.isPending}
                              onClick={() => updateOverrideMutation.mutate({ mode, op: isPinned ? 'unpin' : 'pin', replay_id: rid })}
                            >
                              {isPinned ? 'Unpin' : 'Pin'}
                            </Button>
                            <Button
                              type="button"
                              variant={isExcluded ? 'secondary' : 'destructive'}
                              disabled={updateOverrideMutation.isPending}
                              onClick={() => updateOverrideMutation.mutate({ mode, op: isExcluded ? 'unexclude' : 'exclude', replay_id: rid })}
                            >
                              {isExcluded ? 'Unexclude' : 'Exclude'}
                            </Button>
                          </div>
                          <div className="text-[11px] text-muted">
                            diversity: sel {fmtNum(divSel)} · vs {fmtNum(divVs)}
                          </div>
                        </div>
                      </div>

                      <details className="mt-3">
                        <summary className="cursor-pointer text-sm font-semibold text-fg/85">Breakdown</summary>
                        <div className="mt-2 grid grid-cols-1 md:grid-cols-12 gap-3">
                          <div className="md:col-span-6 rounded-2xl border border-border/12 bg-surface-2/30 p-3">
                            <div className="text-xs font-bold text-muted uppercase">wow_breakdown</div>
                            <pre className="mt-2 text-[11px] leading-4 text-fg/80 overflow-auto">{JSON.stringify(it.wow_breakdown ?? {}, null, 2)}</pre>
                          </div>
                          <div className="md:col-span-6 rounded-2xl border border-border/12 bg-surface-2/30 p-3">
                            <div className="text-xs font-bold text-muted uppercase">engagement / features / diversity</div>
                            <pre className="mt-2 text-[11px] leading-4 text-fg/80 overflow-auto">
                              {JSON.stringify({ engagement: it.engagement ?? {}, features: it.features ?? {}, diversity: it.diversity ?? {} }, null, 2)}
                            </pre>
                          </div>
                        </div>
                      </details>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-sm text-muted">No candidates yet. Try recompute.</div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};
