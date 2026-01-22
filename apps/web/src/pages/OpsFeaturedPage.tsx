import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Star } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type FeaturedKind = 'clip' | 'build' | 'user' | 'challenge';

type FeaturedItem = {
  id: string;
  kind: FeaturedKind;
  target_id: string;
  title_override?: string | null;
  priority: number;
  starts_at?: string | null;
  ends_at?: string | null;
  status: string;
  created_at: string;
  created_by?: string | null;
  href: string;
};

type FeaturedPreviewOut = {
  day: string;
  starts_at: string;
  ends_at: string;
  items: Array<{
    kind: FeaturedKind;
    target_id: string | null;
    source: string;
    featured_id: string | null;
    priority: number | null;
    href: string | null;
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

export const OpsFeaturedPage: React.FC = () => {
  const qc = useQueryClient();
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const enabled = Boolean(adminToken.trim());

  const [kind, setKind] = useState<FeaturedKind | 'all'>('all');
  const [activeOnly, setActiveOnly] = useState(false);

  const [showAdd, setShowAdd] = useState(false);
  const [addKind, setAddKind] = useState<FeaturedKind>('clip');
  const [addTargetId, setAddTargetId] = useState('');
  const [addPriority, setAddPriority] = useState('0');
  const [addTitle, setAddTitle] = useState('');
  const [addStartsAt, setAddStartsAt] = useState('');
  const [addEndsAt, setAddEndsAt] = useState('');
  const [priorityDraft, setPriorityDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const queryPath = useMemo(() => {
    const qp = new URLSearchParams();
    if (kind !== 'all') qp.set('kind', kind);
    qp.set('active', activeOnly ? 'true' : 'false');
    return `/api/ops/featured?${qp.toString()}`;
  }, [kind, activeOnly]);

  const { data, refetch } = useQuery({
    queryKey: ['ops', 'featured', kind, activeOnly, enabled],
    queryFn: () => apiFetch<FeaturedItem[]>(queryPath),
    enabled,
    staleTime: 5_000,
  });

  const { data: preview } = useQuery({
    queryKey: ['ops', 'featured', 'preview', enabled],
    queryFn: () => apiFetch<FeaturedPreviewOut>('/api/ops/featured/preview?offset_days=1'),
    enabled,
    staleTime: 10_000,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (!Array.isArray(data)) return;
    setPriorityDraft((prev) => {
      const next = { ...prev };
      for (const it of data) {
        if (next[it.id] === undefined) next[it.id] = String(it.priority ?? 0);
      }
      return next;
    });
  }, [data]);

  const createMutation = useMutation({
    mutationFn: async () => {
      const starts_at = addStartsAt ? new Date(addStartsAt).toISOString() : null;
      const ends_at = addEndsAt ? new Date(addEndsAt).toISOString() : null;
      const payload = {
        kind: addKind,
        target_id: addTargetId.trim(),
        priority: Number.parseInt(addPriority || '0', 10) || 0,
        starts_at,
        ends_at,
        title_override: addTitle.trim() ? addTitle.trim() : null,
      };
      return apiFetch<FeaturedItem>('/api/ops/featured', { method: 'POST', body: JSON.stringify(payload) });
    },
    onSuccess: async () => {
      setShowAdd(false);
      setAddTargetId('');
      setAddTitle('');
      setAddPriority('0');
      setAddStartsAt('');
      setAddEndsAt('');
      await qc.invalidateQueries({ queryKey: ['ops', 'featured'] });
      await refetch();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => apiFetch<{ ok: boolean }>(`/api/ops/featured/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'featured'] });
      await refetch();
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, priority }: { id: string; priority: number }) =>
      apiFetch<FeaturedItem>(`/api/ops/featured/${encodeURIComponent(id)}/update`, {
        method: 'POST',
        body: JSON.stringify({ priority }),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['ops', 'featured'] });
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
            <Star size={18} className="text-slate-500" /> Featured Curation
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" onClick={() => refetch()} disabled={!enabled}>
              Refresh
            </Button>
            <Button type="button" onClick={() => setShowAdd(true)} disabled={!enabled}>
              Add Featured
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
            </div>
            <div className="md:col-span-3">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Kind</label>
              <select
                className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-slate-50"
                value={kind}
                onChange={(e) => setKind(e.target.value as any)}
              >
                <option value="all">all</option>
                <option value="clip">clip</option>
                <option value="build">build</option>
                <option value="user">user</option>
                <option value="challenge">challenge</option>
              </select>
            </div>
            <div className="md:col-span-3">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Filter</label>
              <select
                className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-slate-50"
                value={activeOnly ? 'active' : 'all'}
                onChange={(e) => setActiveOnly(e.target.value === 'active')}
              >
                <option value="all">all (incl. expired)</option>
                <option value="active">active only</option>
              </select>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-bold text-slate-800">Tomorrow Preview</div>
              <Badge variant="neutral">{preview?.day ?? '—'}</Badge>
            </div>
            {enabled ? (
              preview?.items?.length ? (
                <div className="mt-2 space-y-1">
                  {preview.items.map((it) => (
                    <div key={`${it.kind}:${it.target_id ?? 'none'}`} className="flex items-center justify-between gap-3 text-xs">
                      <span className="font-mono text-slate-600">{it.kind}</span>
                      <span className="flex items-center gap-2 min-w-0">
                        <Badge variant={it.source === 'ops_override' ? 'brand' : 'neutral'}>{it.source}</Badge>
                        {it.href ? (
                          <a className="text-brand-700 font-semibold hover:underline truncate" href={it.href} target="_blank" rel="noreferrer">
                            {it.target_id}
                          </a>
                        ) : (
                          <span className="text-slate-500 truncate">{it.target_id ?? '—'}</span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-sm text-slate-500">No preview data yet.</div>
              )
            ) : (
              <div className="mt-2 text-sm text-slate-500">Enter admin token to load preview.</div>
            )}
          </div>

          {!enabled ? <div className="text-sm text-slate-500">Enter admin token to load.</div> : null}

          {enabled && Array.isArray(data) ? (
            <div className="space-y-2">
              {data.length === 0 ? (
                <div className="text-sm text-slate-500">No featured items yet.</div>
              ) : (
                data.map((it) => (
                  <div key={it.id} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant={it.status === 'active' ? 'success' : 'neutral'}>{it.status}</Badge>
                          <span className="text-xs font-mono text-slate-500">{it.kind}</span>
                          <a className="text-sm font-bold text-brand-700 hover:underline truncate" href={it.href} target="_blank" rel="noreferrer">
                            {it.title_override || it.target_id}
                          </a>
                        </div>
                        <div className="mt-1 text-xs text-slate-500 font-mono break-all">target_id: {it.target_id}</div>
                        <div className="mt-1 text-[11px] text-slate-500">
                          priority {it.priority} · starts {it.starts_at || '—'} · ends {it.ends_at || '—'}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Input
                          className="w-[110px]"
                          value={priorityDraft[it.id] ?? String(it.priority ?? 0)}
                          onChange={(e) => setPriorityDraft((m) => ({ ...m, [it.id]: e.target.value }))}
                        />
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() =>
                            updateMutation.mutate({
                              id: it.id,
                              priority: Number.parseInt(priorityDraft[it.id] ?? String(it.priority ?? 0), 10) || 0,
                            })
                          }
                          disabled={updateMutation.isPending}
                        >
                          Save
                        </Button>
                        <Button
                          type="button"
                          variant="destructive"
                          onClick={() => deleteMutation.mutate(it.id)}
                          disabled={deleteMutation.isPending}
                        >
                          Remove
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {showAdd ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
              <div className="font-bold text-slate-800">Add Featured</div>
              <Button type="button" variant="ghost" onClick={() => setShowAdd(false)}>
                Close
              </Button>
            </div>
            <div className="p-5 space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <div className="md:col-span-4">
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Kind</label>
                  <select
                    className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-slate-50"
                    value={addKind}
                    onChange={(e) => setAddKind(e.target.value as FeaturedKind)}
                  >
                    <option value="clip">clip</option>
                    <option value="build">build</option>
                    <option value="user">user</option>
                    <option value="challenge">challenge</option>
                  </select>
                </div>
                <div className="md:col-span-8">
                  <Input label="Target ID" value={addTargetId} onChange={(e) => setAddTargetId(e.target.value)} placeholder="r_seed_001 / bp_demo_1v1 / user_demo / ch_..." />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <div className="md:col-span-4">
                  <Input label="Priority" value={addPriority} onChange={(e) => setAddPriority(e.target.value)} />
                </div>
                <div className="md:col-span-8">
                  <Input label="Title override (optional)" value={addTitle} onChange={(e) => setAddTitle(e.target.value)} />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <div className="md:col-span-6">
                  <Input label="Starts at (optional)" type="datetime-local" value={addStartsAt} onChange={(e) => setAddStartsAt(e.target.value)} />
                </div>
                <div className="md:col-span-6">
                  <Input label="Ends at (optional)" type="datetime-local" value={addEndsAt} onChange={(e) => setAddEndsAt(e.target.value)} />
                </div>
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <Button type="button" variant="secondary" onClick={() => setShowAdd(false)}>
                  Cancel
                </Button>
                <Button
                  type="button"
                  onClick={() => createMutation.mutate()}
                  isLoading={createMutation.isPending}
                  disabled={!addTargetId.trim() || createMutation.isPending}
                >
                  Create
                </Button>
              </div>
              {createMutation.isError ? (
                <div className="text-sm text-red-600">{String((createMutation.error as any)?.message || createMutation.error)}</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
