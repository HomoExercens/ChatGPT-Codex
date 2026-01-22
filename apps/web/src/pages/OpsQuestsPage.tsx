import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ListChecks } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type Cadence = 'daily' | 'weekly';

type QuestDef = {
  id: string;
  cadence: Cadence;
  key: string;
  title: string;
  description: string;
  goal_count: number;
  event_type: string;
  reward_cosmetic_id: string;
  reward_amount: number;
};

type OpsQuestsOut = {
  server_time_kst: string;
  ruleset_version: string;
  daily_period_key: string;
  weekly_period_key: string;
  daily_selected: QuestDef[];
  weekly_selected: QuestDef[];
  overrides: Record<string, any>;
  all_quests: QuestDef[];
  storage_key: string;
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

function keysToCsv(keys: string[] | null | undefined): string {
  if (!Array.isArray(keys)) return '';
  return keys.map((k) => String(k).trim()).filter(Boolean).join(', ');
}

function csvToKeys(csv: string): string[] {
  return csv
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

export const OpsQuestsPage: React.FC = () => {
  const qc = useQueryClient();
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const enabled = Boolean(adminToken.trim());

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const { data, refetch } = useQuery({
    queryKey: ['ops', 'quests', enabled],
    queryFn: () => apiFetch<OpsQuestsOut>('/api/ops/quests'),
    enabled,
    staleTime: 5_000,
  });

  const dailyOverride = useMemo(() => {
    const raw = (data?.overrides as any)?.daily;
    return raw && Array.isArray(raw.quest_keys) ? (raw.quest_keys as string[]) : null;
  }, [data?.overrides]);

  const weeklyOverride = useMemo(() => {
    const raw = (data?.overrides as any)?.weekly;
    return raw && Array.isArray(raw.quest_keys) ? (raw.quest_keys as string[]) : null;
  }, [data?.overrides]);

  const [dailyCsv, setDailyCsv] = useState('');
  const [weeklyCsv, setWeeklyCsv] = useState('');

  useEffect(() => {
    setDailyCsv(keysToCsv(dailyOverride));
  }, [dailyOverride]);
  useEffect(() => {
    setWeeklyCsv(keysToCsv(weeklyOverride));
  }, [weeklyOverride]);

  const overrideMutation = useMutation({
    mutationFn: async ({ cadence, questKeys, clear }: { cadence: Cadence; questKeys: string[]; clear: boolean }) =>
      apiFetch<OpsQuestsOut>('/api/ops/quests/override', {
        method: 'POST',
        body: JSON.stringify({ cadence, quest_keys: questKeys, clear }),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'quests'] });
      await refetch();
    },
  });

  const sortedAll = useMemo(() => {
    const items = data?.all_quests ?? [];
    return [...items].sort((a, b) => `${a.cadence}:${a.key}`.localeCompare(`${b.cadence}:${b.key}`));
  }, [data?.all_quests]);

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
            <ListChecks size={18} className="text-slate-500" /> Quests (Daily / Weekly)
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
              <div className="text-[11px] font-bold text-slate-500 uppercase">Server</div>
              <div className="mt-1 text-xs text-slate-700 font-mono break-all">{data?.server_time_kst ?? '—'}</div>
              <div className="mt-1 text-xs text-slate-500 font-mono">ruleset {data?.ruleset_version ?? '—'}</div>
            </div>
          </div>

          {!enabled ? <div className="text-sm text-slate-500">Enter admin token to load.</div> : null}

          {enabled && data ? (
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
              <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-4 py-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="font-bold text-slate-800">Today (Daily)</div>
                  <Badge variant="neutral">{data.daily_period_key}</Badge>
                </div>
                <div className="text-xs text-slate-500">Selected quests (deterministic unless overridden):</div>
                <div className="space-y-1">
                  {data.daily_selected.map((q) => (
                    <div key={q.id} className="text-sm text-slate-800">
                      <span className="font-mono text-xs text-slate-500 mr-2">{q.key}</span>
                      <span className="font-bold">{q.title}</span> <span className="text-xs text-slate-500">×{q.goal_count}</span>
                    </div>
                  ))}
                </div>
                <Input label="Override keys (comma-separated)" value={dailyCsv} onChange={(e) => setDailyCsv(e.target.value)} />
                <div className="flex gap-2">
                  <Button
                    type="button"
                    onClick={() => overrideMutation.mutate({ cadence: 'daily', questKeys: csvToKeys(dailyCsv), clear: false })}
                    disabled={overrideMutation.isPending}
                    isLoading={overrideMutation.isPending}
                  >
                    Apply override
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => overrideMutation.mutate({ cadence: 'daily', questKeys: [], clear: true })}
                    disabled={overrideMutation.isPending}
                  >
                    Clear
                  </Button>
                </div>
              </div>

              <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-4 py-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="font-bold text-slate-800">This Week (Weekly)</div>
                  <Badge variant="neutral">{data.weekly_period_key}</Badge>
                </div>
                <div className="text-xs text-slate-500">Selected quests (deterministic unless overridden):</div>
                <div className="space-y-1">
                  {data.weekly_selected.map((q) => (
                    <div key={q.id} className="text-sm text-slate-800">
                      <span className="font-mono text-xs text-slate-500 mr-2">{q.key}</span>
                      <span className="font-bold">{q.title}</span> <span className="text-xs text-slate-500">×{q.goal_count}</span>
                    </div>
                  ))}
                </div>
                <Input label="Override keys (comma-separated)" value={weeklyCsv} onChange={(e) => setWeeklyCsv(e.target.value)} />
                <div className="flex gap-2">
                  <Button
                    type="button"
                    onClick={() => overrideMutation.mutate({ cadence: 'weekly', questKeys: csvToKeys(weeklyCsv), clear: false })}
                    disabled={overrideMutation.isPending}
                    isLoading={overrideMutation.isPending}
                  >
                    Apply override
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => overrideMutation.mutate({ cadence: 'weekly', questKeys: [], clear: true })}
                    disabled={overrideMutation.isPending}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            </div>
          ) : null}

          {enabled && data ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Quest Definitions</CardTitle>
                <Badge variant="neutral">{sortedAll.length} total</Badge>
              </CardHeader>
              <CardContent className="space-y-2">
                {sortedAll.map((q) => (
                  <div key={q.id} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant={q.cadence === 'daily' ? 'info' : 'brand'}>{q.cadence}</Badge>
                          <span className="text-xs font-mono text-slate-500">{q.key}</span>
                          <span className="font-bold text-slate-800 truncate">{q.title}</span>
                        </div>
                        <div className="mt-1 text-xs text-slate-500 font-mono">
                          event {q.event_type} · goal {q.goal_count} · reward {q.reward_cosmetic_id}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
                <div className="text-[11px] text-slate-500 font-mono pt-2">overrides storage: {data.storage_key}</div>
              </CardContent>
            </Card>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

