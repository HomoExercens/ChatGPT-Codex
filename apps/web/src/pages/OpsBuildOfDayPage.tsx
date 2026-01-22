import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Trophy } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type Mode = '1v1' | 'team';

type OpsBuildOfDayEntry = {
  date: string;
  mode: Mode;
  source: 'override' | 'auto' | 'none';
  picked_blueprint_id?: string | null;
  picked_name?: string | null;
  override_blueprint_id?: string | null;
  auto_blueprint_id?: string | null;
};

type OpsBuildOfDayOut = {
  today: string;
  mode: Mode;
  storage_key: string;
  entries: OpsBuildOfDayEntry[];
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

export const OpsBuildOfDayPage: React.FC = () => {
  const qc = useQueryClient();
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const enabled = Boolean(adminToken.trim());

  const [mode, setMode] = useState<Mode>('1v1');
  const [days, setDays] = useState('7');
  const [date, setDate] = useState('');
  const [blueprintId, setBlueprintId] = useState('');

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const queryPath = useMemo(() => {
    const qp = new URLSearchParams();
    qp.set('mode', mode);
    qp.set('days', String(Number.parseInt(days || '7', 10) || 7));
    return `/api/ops/build_of_day?${qp.toString()}`;
  }, [mode, days]);

  const { data, refetch, error } = useQuery({
    queryKey: ['ops', 'build_of_day', mode, days, enabled],
    queryFn: () => apiFetch<OpsBuildOfDayOut>(queryPath),
    enabled,
    staleTime: 5_000,
  });

  useEffect(() => {
    if (!data?.today) return;
    if (date.trim()) return;
    setDate(data.today);
  }, [data?.today]);

  const overrideMutation = useMutation({
    mutationFn: async ({ blueprint_id }: { blueprint_id: string | null }) =>
      apiFetch<OpsBuildOfDayOut>('/api/ops/build_of_day/override', {
        method: 'POST',
        body: JSON.stringify({
          mode,
          date: date.trim() || null,
          blueprint_id,
        }),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'build_of_day'] });
      await refetch();
    },
  });

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
            <Trophy size={18} className="text-slate-500" /> Build of the Day (Ops)
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" onClick={() => refetch()} disabled={!enabled}>
              Refresh
            </Button>
          </div>
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
                Calls admin-gated endpoints with <span className="font-mono">X-Admin-Token</span>.
              </div>
            </div>
            <div className="md:col-span-3">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Mode</label>
              <select
                className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-slate-50"
                value={mode}
                onChange={(e) => setMode(e.target.value as Mode)}
              >
                <option value="1v1">1v1</option>
                <option value="team">team</option>
              </select>
            </div>
            <div className="md:col-span-3">
              <Input label="Days" value={days} onChange={(e) => setDays(e.target.value)} placeholder="7" />
            </div>
          </div>

          {!enabled ? <div className="text-sm text-slate-500">Enter admin token to load.</div> : null}
          {error ? <div className="text-sm text-red-600">Failed to load: {String(error)}</div> : null}

          <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Override</div>
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
              <div className="md:col-span-4">
                <Input label="Date (KST)" value={date} onChange={(e) => setDate(e.target.value)} placeholder={data?.today ?? 'YYYY-MM-DD'} />
              </div>
              <div className="md:col-span-8">
                <Input
                  label="Blueprint ID"
                  value={blueprintId}
                  onChange={(e) => setBlueprintId(e.target.value)}
                  placeholder="bp_..."
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-2 justify-end">
              <Button
                variant="secondary"
                onClick={() => overrideMutation.mutate({ blueprint_id: null })}
                disabled={!enabled}
                isLoading={overrideMutation.isPending}
              >
                Clear Override
              </Button>
              <Button
                onClick={() => overrideMutation.mutate({ blueprint_id: blueprintId.trim() || null })}
                disabled={!enabled || !blueprintId.trim()}
                isLoading={overrideMutation.isPending}
              >
                Set Override
              </Button>
            </div>
            {data?.storage_key ? (
              <div className="text-[11px] text-slate-500">
                storage_key: <span className="font-mono">{data.storage_key}</span>
              </div>
            ) : null}
          </div>

          {enabled && data?.entries?.length ? (
            <div className="space-y-2">
              {data.entries.map((e) => (
                <div key={`${e.date}-${e.mode}`} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant={e.source === 'override' ? 'brand' : e.source === 'auto' ? 'info' : 'neutral'}>
                          {e.source}
                        </Badge>
                        <span className="text-xs font-mono text-slate-500">{e.date}</span>
                        <span className="text-xs text-slate-500">{e.mode}</span>
                      </div>
                      <div className="mt-1 text-sm font-bold text-slate-800 truncate">{e.picked_name || e.picked_blueprint_id || '—'}</div>
                      <div className="mt-1 text-[11px] text-slate-500 font-mono break-all">
                        picked: {e.picked_blueprint_id || '—'}
                      </div>
                      {e.override_blueprint_id ? (
                        <div className="mt-1 text-[11px] text-slate-500 font-mono break-all">
                          override: {e.override_blueprint_id}
                        </div>
                      ) : null}
                      {e.auto_blueprint_id ? (
                        <div className="mt-1 text-[11px] text-slate-500 font-mono break-all">
                          auto: {e.auto_blueprint_id}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex flex-col gap-2 shrink-0">
                      {e.picked_blueprint_id ? (
                        <>
                          <a
                            className="text-sm font-semibold text-brand-700 hover:underline"
                            href={`/s/build/${encodeURIComponent(e.picked_blueprint_id)}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open share →
                          </a>
                          <a className="text-xs text-slate-500 hover:underline" href={`/gallery`} target="_blank" rel="noreferrer">
                            Gallery →
                          </a>
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : enabled ? (
            <div className="text-sm text-slate-500">No entries.</div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

