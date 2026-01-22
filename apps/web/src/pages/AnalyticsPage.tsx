import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import {
  Bar,
  BarChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';
import type { BlueprintOut, Mode } from '../api/types';

type AnalyticsOverview = {
  summary: {
    matches_total: number;
    wins: number;
    losses: number;
    draws: number;
    winrate: number;
    human_matches?: number;
    human_match_rate?: number;
    elo_current: number;
    division: string;
  };
  elo_series: Array<{
    index: number;
    match_id: string;
    at: string;
    result: 'win' | 'loss' | 'draw';
    elo: number;
    delta: number;
  }>;
  matchups: Array<{
    opponent: string;
    matches: number;
    wins: number;
    losses: number;
    draws: number;
    winrate: number;
  }>;
};

type AnalyticsMatchups = {
  matches_total: number;
  rows: Array<{
    opponent: string;
    matches: number;
    wins: number;
    losses: number;
    draws: number;
    winrate: number;
    sample_match_ids: string[];
  }>;
};

type BuildInsights = {
  matches_total: number;
  items: Array<{ id: string; uses: number; wins: number; losses: number; draws: number; winrate: number }>;
  synergies: Array<{ id: string; uses: number; wins: number; losses: number; draws: number; winrate: number }>;
  recommendations: string[];
};

type VersionCompare = {
  note?: string;
  error?: string;
  blueprint_a?: { id: string; name: string };
  blueprint_b?: { id: string; name: string };
  summary_lines?: string[];
  by_opponent?: Array<{
    opponent: string;
    a: { matches: number; winrate: number; sample_match_ids: string[] };
    b: { matches: number; winrate: number; sample_match_ids: string[] };
    delta_winrate: number;
  }>;
};

type CoachResponse = {
  mode: Mode;
  cards: Array<{
    id: string;
    title: string;
    body: string;
    evidence: Array<{ label: string; value: string }>;
    tags: string[];
    cta?: { label: string; href: string } | null;
  }>;
};

type ModifiersStats = {
  mode: Mode;
  matches_total: number;
  portals: Array<{
    portal_id: string;
    portal_name: string;
    matches: number;
    wins: number;
    losses: number;
    draws: number;
    winrate: number;
  }>;
  augments: Array<{
    augment_id: string;
    augment_name: string;
    tier: number | null;
    category: string | null;
    matches: number;
    wins: number;
    losses: number;
    draws: number;
    winrate: number;
  }>;
};

export const AnalyticsPage: React.FC = () => {
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const tn = TRANSLATIONS[lang].nav;

  const [mode, setMode] = useState<Mode>('1v1');

  const { data } = useQuery({
    queryKey: ['analytics', 'overview', mode],
    queryFn: () => apiFetch<AnalyticsOverview>(`/api/analytics/overview?mode=${encodeURIComponent(mode)}`),
  });

  const { data: coach } = useQuery({
    queryKey: ['analytics', 'coach', mode],
    queryFn: () => apiFetch<CoachResponse>(`/api/analytics/coach?mode=${encodeURIComponent(mode)}`),
  });

  const { data: matchups } = useQuery({
    queryKey: ['analytics', 'matchups', mode],
    queryFn: () => apiFetch<AnalyticsMatchups>(`/api/analytics/matchups?mode=${encodeURIComponent(mode)}`),
  });

  const { data: insights } = useQuery({
    queryKey: ['analytics', 'build-insights', mode],
    queryFn: () => apiFetch<BuildInsights>(`/api/analytics/build-insights?mode=${encodeURIComponent(mode)}`),
  });

  const { data: modifiers } = useQuery({
    queryKey: ['analytics', 'modifiers', mode],
    queryFn: () => apiFetch<ModifiersStats>(`/api/analytics/modifiers?mode=${encodeURIComponent(mode)}`),
  });

  const { data: blueprints = [] } = useQuery({
    queryKey: ['blueprints'],
    queryFn: () => apiFetch<BlueprintOut[]>('/api/blueprints'),
  });

  const blueprintsForMode = useMemo(() => blueprints.filter((bp) => bp.mode === mode), [blueprints, mode]);
  const [compareA, setCompareA] = useState<string>('');
  const [compareB, setCompareB] = useState<string>('');

  useEffect(() => {
    if (blueprintsForMode.length === 0) {
      if (compareA) setCompareA('');
      if (compareB) setCompareB('');
      return;
    }

    if (blueprintsForMode.length < 2) {
      if (compareA !== blueprintsForMode[0].id) setCompareA(blueprintsForMode[0].id);
      if (compareB) setCompareB('');
      return;
    }

    if (!compareA || !blueprintsForMode.some((bp) => bp.id === compareA)) setCompareA(blueprintsForMode[0].id);
    if (!compareB || !blueprintsForMode.some((bp) => bp.id === compareB)) setCompareB(blueprintsForMode[1].id);
  }, [blueprintsForMode, compareA, compareB]);

  const { data: compare } = useQuery({
    queryKey: ['analytics', 'version-compare', mode, compareA, compareB],
    queryFn: () =>
      apiFetch<VersionCompare>(
        `/api/analytics/version-compare?mode=${encodeURIComponent(mode)}&blueprint_a_id=${encodeURIComponent(compareA)}&blueprint_b_id=${encodeURIComponent(compareB)}`
      ),
    enabled: Boolean(compareA && compareB),
  });

  const series = useMemo(() => data?.elo_series ?? [], [data?.elo_series]);
  const hasMatches = (data?.summary.matches_total ?? 0) > 0;
  const topItems = useMemo(
    () =>
      (insights?.items ?? []).slice(0, 8).map((row) => ({
        id: row.id,
        uses: row.uses,
        winrate: Math.round(row.winrate * 100),
      })),
    [insights?.items]
  );

  const coachCards = coach?.cards ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 size={18} className="text-brand-600" /> {tn.analytics}
        </CardTitle>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant={mode === '1v1' ? 'primary' : 'secondary'}
            onClick={() => setMode('1v1')}
            aria-pressed={mode === '1v1'}
            type="button"
          >
            1v1
          </Button>
          <Button
            size="sm"
            variant={mode === 'team' ? 'primary' : 'secondary'}
            onClick={() => setMode('team')}
            aria-pressed={mode === 'team'}
            type="button"
          >
            Team (3v3)
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {coachCards.length ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {coachCards.slice(0, 3).map((card) => (
              <div key={card.id} className="p-4 rounded-2xl border border-slate-200 bg-white space-y-3">
                <div className="text-sm font-bold text-slate-900">{card.title}</div>
                <div className="text-sm text-slate-600 leading-relaxed">{card.body}</div>

                {(card.evidence ?? []).length ? (
                  <div className="space-y-1 text-xs text-slate-600">
                    {card.evidence.slice(0, 3).map((e) => (
                      <div key={`${card.id}-${e.label}`} className="flex items-center justify-between gap-3">
                        <span className="font-semibold text-slate-700">{e.label}</span>
                        <span className="font-mono text-slate-500">{e.value}</span>
                      </div>
                    ))}
                  </div>
                ) : null}

                {(card.tags ?? []).length ? (
                  <div className="flex flex-wrap gap-2">
                    {card.tags.slice(0, 4).map((tg) => (
                      <Badge key={`${card.id}-${tg}`} variant="neutral">
                        {tg}
                      </Badge>
                    ))}
                  </div>
                ) : null}

                {card.cta?.href ? (
                  <Button size="sm" variant="secondary" onClick={() => navigate(card.cta!.href)}>
                    {card.cta.label}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        {!hasMatches ? (
          <div className="p-6 rounded-2xl border border-slate-200 bg-slate-50 flex flex-col items-start gap-3">
            <div className="text-sm font-bold text-slate-800">No match data yet</div>
            <div className="text-sm text-slate-600">
              Queue your first {mode === 'team' ? 'team' : '1v1'} ranked match to unlock Elo history and matchup breakdowns.
            </div>
            <Button onClick={() => navigate('/ranked')}>Go to Ranked</Button>
          </div>
        ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-4 rounded-2xl border border-slate-200 bg-white">
                  <div className="text-[10px] uppercase text-slate-400 font-bold">Division</div>
                  <div className="text-lg font-bold text-slate-800">{data?.summary.division}</div>
                </div>
              <div className="p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-[10px] uppercase text-slate-400 font-bold">Elo</div>
                <div className="text-lg font-bold text-slate-800">{data?.summary.elo_current}</div>
              </div>
              <div className="p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-[10px] uppercase text-slate-400 font-bold">Winrate</div>
                <div className="text-lg font-bold text-slate-800">
                  {((data?.summary.winrate ?? 0) * 100).toFixed(1)}%
                </div>
              </div>
              <div className="p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-[10px] uppercase text-slate-400 font-bold">Matches</div>
                <div className="text-lg font-bold text-slate-800">{data?.summary.matches_total}</div>
              </div>
              <div className="p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-[10px] uppercase text-slate-400 font-bold">Human Match Rate</div>
                <div className="text-lg font-bold text-slate-800">
                  {(((data?.summary.human_match_rate ?? 0) as number) * 100).toFixed(0)}%
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  {(data?.summary.human_matches ?? 0) as number}/{data?.summary.matches_total ?? 0}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-7 p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-sm font-bold text-slate-800 mb-3">Elo over time</div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={series}>
                      <XAxis dataKey="index" hide />
                      <YAxis hide />
                      <RechartsTooltip
                        contentStyle={{
                          borderRadius: '12px',
                          border: 'none',
                          boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                        }}
                        formatter={(value: any, name) =>
                          name === 'elo' ? [String(value), 'Elo'] : [String(value), name]
                        }
                      />
                      <Line type="monotone" dataKey="elo" stroke="#2563eb" strokeWidth={3} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="lg:col-span-5 p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-sm font-bold text-slate-800 mb-3">Top matchups</div>
                <div className="divide-y divide-slate-100">
                  {(data?.matchups ?? []).map((m) => (
                    <div key={m.opponent} className="py-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-bold text-slate-800 truncate">{m.opponent}</div>
                        <div className="text-xs text-slate-500">
                          {m.matches} games · {m.wins}-{m.losses}-{m.draws}
                        </div>
                      </div>
                      <div className="text-sm font-bold text-slate-800">
                        {(m.winrate * 100).toFixed(0)}%
                      </div>
                    </div>
                  ))}
                  {(data?.matchups ?? []).length === 0 ? (
                    <div className="text-sm text-slate-500 py-4">No matchup data.</div>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-6 p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-sm font-bold text-slate-800 mb-3">Matchups (by archetype)</div>
                <div className="divide-y divide-slate-100">
                  {(matchups?.rows ?? []).slice(0, 10).map((row) => (
                    <div key={row.opponent} className="py-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-bold text-slate-800 truncate">{row.opponent}</div>
                        <div className="text-xs text-slate-500">
                          {row.matches} games · {row.wins}-{row.losses}-{row.draws} · {(row.winrate * 100).toFixed(0)}%
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {row.sample_match_ids.map((mid) => (
                            <Button key={mid} variant="outline" size="sm" onClick={() => navigate(`/replay/${mid}`)}>
                              Replay
                            </Button>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                  {(matchups?.rows ?? []).length === 0 ? (
                    <div className="text-sm text-slate-500 py-4">No matchup data.</div>
                  ) : null}
                </div>
              </div>

              <div className="lg:col-span-6 p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-sm font-bold text-slate-800 mb-3">Build Insights (top items)</div>
                {topItems.length === 0 ? (
                  <div className="text-sm text-slate-500">No build insights yet.</div>
                ) : (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={topItems}>
                        <XAxis dataKey="id" hide />
                        <YAxis hide domain={[0, 100]} />
                        <RechartsTooltip
                          contentStyle={{
                            borderRadius: '12px',
                            border: 'none',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                          }}
                          formatter={(value: any, name) =>
                            name === 'winrate' ? [`${String(value)}%`, 'Winrate'] : [String(value), name]
                          }
                        />
                        <Bar dataKey="winrate" fill="#2563eb" radius={[8, 8, 8, 8]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <div className="mt-4 space-y-1">
                  {(insights?.recommendations ?? []).slice(0, 4).map((r) => (
                    <div key={r} className="text-xs text-slate-600">
                      • {r}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-6 p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-sm font-bold text-slate-800 mb-3">Portals (your matches)</div>
                <div className="divide-y divide-slate-100">
                  {(modifiers?.portals ?? []).slice(0, 8).map((p) => (
                    <div key={p.portal_id} className="py-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-bold text-slate-800 truncate">{p.portal_name}</div>
                        <div className="text-xs text-slate-500 font-mono">
                          {p.matches} · {p.wins}-{p.losses}-{p.draws}
                        </div>
                      </div>
                      <div className="text-sm font-bold text-slate-800">{(p.winrate * 100).toFixed(0)}%</div>
                    </div>
                  ))}
                  {(modifiers?.portals ?? []).length === 0 ? (
                    <div className="text-sm text-slate-500 py-4">No portal data yet.</div>
                  ) : null}
                </div>
              </div>

              <div className="lg:col-span-6 p-4 rounded-2xl border border-slate-200 bg-white">
                <div className="text-sm font-bold text-slate-800 mb-3">Augments (your side)</div>
                <div className="divide-y divide-slate-100">
                  {(modifiers?.augments ?? []).slice(0, 10).map((a) => (
                    <div key={a.augment_id} className="py-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-bold text-slate-800 truncate">
                          {a.augment_name}{' '}
                          {a.tier ? (
                            <span className="text-[10px] font-mono text-slate-500 ml-2">T{a.tier}</span>
                          ) : null}
                        </div>
                        <div className="text-xs text-slate-500 font-mono">{a.matches} matches</div>
                      </div>
                      <div className="text-sm font-bold text-slate-800">{(a.winrate * 100).toFixed(0)}%</div>
                    </div>
                  ))}
                  {(modifiers?.augments ?? []).length === 0 ? (
                    <div className="text-sm text-slate-500 py-4">No augment data yet.</div>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="p-4 rounded-2xl border border-slate-200 bg-white">
              <div className="text-sm font-bold text-slate-800 mb-3">Version Compare (Blueprint A/B)</div>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-end">
                  <div className="md:col-span-5">
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Blueprint A</label>
                    <select
                      className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none"
                      value={compareA}
                      onChange={(e) => setCompareA(e.target.value)}
                    >
                      {blueprintsForMode.map((bp) => (
                        <option key={bp.id} value={bp.id}>
                          {bp.name} ({bp.mode})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="md:col-span-5">
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Blueprint B</label>
                    <select
                      className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none"
                      value={compareB}
                      onChange={(e) => setCompareB(e.target.value)}
                    >
                      {blueprintsForMode.map((bp) => (
                        <option key={bp.id} value={bp.id}>
                          {bp.name} ({bp.mode})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

              {blueprintsForMode.length < 2 ? (
                <div className="text-xs text-slate-500 mt-3">Create or train another blueprint in this mode to compare.</div>
              ) : null}

              {compare?.error ? <div className="text-xs text-red-600 mt-3">{compare.error}</div> : null}
              {compare?.note ? <div className="text-xs text-slate-500 mt-3">{compare.note}</div> : null}
              {(compare?.summary_lines ?? []).length ? (
                <div className="mt-3 space-y-1">
                  {compare?.summary_lines?.map((line) => (
                    <div key={line} className="text-xs text-slate-700">
                      {line}
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="mt-4 divide-y divide-slate-100">
                {(compare?.by_opponent ?? []).slice(0, 10).map((row) => (
                  <div key={row.opponent} className="py-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-bold text-slate-800 truncate">{row.opponent}</div>
                      <div className="text-xs text-slate-500">
                        A {(row.a.winrate * 100).toFixed(0)}% ({row.a.matches}) · B {(row.b.winrate * 100).toFixed(0)}% ({row.b.matches}) · Δ {(row.delta_winrate * 100).toFixed(0)}%
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {row.a.sample_match_ids.map((mid) => (
                          <Button key={`a-${mid}`} variant="outline" size="sm" onClick={() => navigate(`/replay/${mid}`)}>
                            Replay A
                          </Button>
                        ))}
                        {row.b.sample_match_ids.map((mid) => (
                          <Button key={`b-${mid}`} variant="outline" size="sm" onClick={() => navigate(`/replay/${mid}`)}>
                            Replay B
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
                {(compare?.by_opponent ?? []).length === 0 ? (
                  <div className="text-sm text-slate-500 py-4">No compare data yet.</div>
                ) : null}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
