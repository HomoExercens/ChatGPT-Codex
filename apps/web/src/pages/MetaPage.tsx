import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Zap } from 'lucide-react';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';

type PatchNotes = { notes: Array<{ version: string; date: string; title: string }> };
type Archetypes = { archetypes: Array<{ id: string; name: string; winrate: number }> };
type Season = { season_name: string; ruleset_version: string; patch_notes: PatchNotes['notes'] };
type BalanceRow = { id: string; name: string; uses: number; winrate: number; avg_elo_delta: number };
type BalanceMode = {
  low_confidence_min_samples: number;
  mode: '1v1' | 'team';
  data: {
    matches_total: number;
    items: BalanceRow[];
    creatures: BalanceRow[];
    augments: BalanceRow[];
    sigils: BalanceRow[];
  };
};

export const MetaPage: React.FC = () => {
  const lang = useSettingsStore((s) => s.language);
  const tn = TRANSLATIONS[lang].nav;
  const tc = TRANSLATIONS[lang].common;

  const { data: notes } = useQuery({ queryKey: ['meta', 'patchNotes'], queryFn: () => apiFetch<PatchNotes>('/api/meta/patch-notes') });
  const { data: top } = useQuery({ queryKey: ['meta', 'top'], queryFn: () => apiFetch<Archetypes>('/api/meta/archetypes/top') });
  const { data: season } = useQuery({ queryKey: ['meta', 'season'], queryFn: () => apiFetch<Season>('/api/meta/season') });
  const { data: balance } = useQuery({ queryKey: ['ops', 'balance', '1v1'], queryFn: () => apiFetch<BalanceMode>('/api/ops/balance/latest?mode=1v1') });

  const lowN = balance?.low_confidence_min_samples ?? 50;
  const items = balance?.data?.items ?? [];
  const confident = items.filter((r) => (r.uses ?? 0) >= lowN);
  const over = [...confident].sort((a, b) => (b.winrate ?? 0) - (a.winrate ?? 0)).slice(0, 5);
  const under = [...confident].sort((a, b) => (a.winrate ?? 0) - (b.winrate ?? 0)).slice(0, 5);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <Card className="lg:col-span-5 border-accent-200 bg-gradient-to-b from-white to-brand-50/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-accent-700">
            <Zap size={18} /> {tc.metaSnapshot}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(top?.archetypes ?? []).map((a) => (
            <div key={a.id} className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100 shadow-sm">
              <div className="text-sm font-bold text-slate-700">{a.name}</div>
              <Badge variant="warning">{(a.winrate * 100).toFixed(1)}% WR</Badge>
            </div>
          ))}
          {!top ? <div className="text-sm text-slate-500">Loading…</div> : null}

          <div className="pt-3 border-t border-slate-100" />
          <div className="text-xs text-slate-500">Balance Watch (Ranked 1v1)</div>
          {balance ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <div className="text-[11px] font-bold text-emerald-700">Overperforming</div>
                {over.length ? (
                  over.map((r) => (
                    <div key={r.id} className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100 shadow-sm">
                      <div className="text-[11px] font-bold text-slate-700">{r.name || r.id}</div>
                      <Badge variant="success">{((r.winrate || 0) * 100).toFixed(0)}%</Badge>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-slate-500">Not enough data (need ≥ {lowN}).</div>
                )}
              </div>
              <div className="space-y-2">
                <div className="text-[11px] font-bold text-rose-700">Underperforming</div>
                {under.length ? (
                  under.map((r) => (
                    <div key={r.id} className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100 shadow-sm">
                      <div className="text-[11px] font-bold text-slate-700">{r.name || r.id}</div>
                      <Badge variant="error">{((r.winrate || 0) * 100).toFixed(0)}%</Badge>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-slate-500">Not enough data (need ≥ {lowN}).</div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Loading…</div>
          )}
        </CardContent>
      </Card>

      <Card className="lg:col-span-7">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {tn.meta}
            {season?.season_name ? <Badge variant="neutral">{season.season_name}</Badge> : null}
            {season?.ruleset_version ? <Badge variant="neutral">{season.ruleset_version}</Badge> : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-xs text-slate-500">{tc.patchNotes}</div>
          {(notes?.notes ?? []).map((n, idx) => (
            <div key={idx} className="pb-3 border-b border-slate-100 last:border-0 last:pb-0">
              <div className="flex justify-between items-baseline mb-1">
                <span className="font-bold text-sm text-slate-800">{n.version}</span>
                <span className="text-[10px] text-slate-400">{n.date}</span>
              </div>
              <p className="text-xs text-slate-600">{n.title}</p>
            </div>
          ))}
          {!notes ? <div className="text-sm text-slate-500">Loading…</div> : null}
        </CardContent>
      </Card>
    </div>
  );
};
