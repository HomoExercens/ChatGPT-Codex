import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CalendarClock, ChevronLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type OpsWeeklyOut = {
  week_id: string;
  theme: {
    week_id: string;
    name: string;
    description: string;
    featured_portals: Array<Record<string, any>>;
    featured_augments: Array<Record<string, any>>;
    tournament_rules: Record<string, any>;
  };
  override: Record<string, any> | null;
  override_active: boolean;
  storage_key: string;
};

type ModifiersOut = {
  portals: Array<{ id: string; name: string }>;
  augments: Array<{ id: string; name: string; tier?: number }>;
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

function splitIds(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(/[\s,]+/g)
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ).sort();
}

export const OpsWeeklyPage: React.FC = () => {
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const [weekId, setWeekId] = useState('');

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [portalIdsRaw, setPortalIdsRaw] = useState('');
  const [augmentIdsRaw, setAugmentIdsRaw] = useState('');
  const [matchesCounted, setMatchesCounted] = useState('10');
  const [queueOpen, setQueueOpen] = useState(true);

  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const enabled = Boolean(adminToken.trim());

  const { data: modifiers } = useQuery({
    queryKey: ['meta', 'modifiers'],
    queryFn: () => apiFetch<ModifiersOut>('/api/meta/modifiers'),
    staleTime: 30_000,
  });

  const { data: weekly, refetch } = useQuery({
    queryKey: ['ops', 'weekly', weekId, enabled],
    queryFn: () =>
      apiFetch<OpsWeeklyOut>(
        weekId ? `/api/ops/weekly?week_id=${encodeURIComponent(weekId)}` : '/api/ops/weekly',
      ),
    enabled,
    staleTime: 5_000,
  });

  useEffect(() => {
    if (!weekly) return;
    if (!weekId) setWeekId(weekly.week_id);
  }, [weekly, weekId]);

  const portalsById = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of modifiers?.portals ?? []) map.set(p.id, p.name);
    return map;
  }, [modifiers?.portals]);

  const augmentsById = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of modifiers?.augments ?? []) map.set(a.id, a.name);
    return map;
  }, [modifiers?.augments]);

  const portalIds = useMemo(() => splitIds(portalIdsRaw), [portalIdsRaw]);
  const augmentIds = useMemo(() => splitIds(augmentIdsRaw), [augmentIdsRaw]);

  async function applyOverride(): Promise<void> {
    if (!enabled) return;
    setIsSaving(true);
    setStatusMsg(null);
    try {
      const payload = {
        week_id: weekId,
        name: name || null,
        description: description || null,
        featured_portal_ids: portalIds,
        featured_augment_ids: augmentIds,
        tournament_rules: { matches_counted: Number(matchesCounted || 10), queue_open: queueOpen },
      };
      await apiFetch<OpsWeeklyOut>('/api/ops/weekly/override', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setStatusMsg('Saved weekly override.');
      await refetch();
    } catch (err: any) {
      setStatusMsg(String(err?.message || err));
    } finally {
      setIsSaving(false);
    }
  }

  async function clearOverride(): Promise<void> {
    if (!enabled) return;
    setIsSaving(true);
    setStatusMsg(null);
    try {
      await apiFetch<OpsWeeklyOut>('/api/ops/weekly/override', {
        method: 'POST',
        body: JSON.stringify({ clear: true, week_id: weekId || null }),
      });
      setStatusMsg('Cleared weekly override.');
      await refetch();
    } catch (err: any) {
      setStatusMsg(String(err?.message || err));
    } finally {
      setIsSaving(false);
    }
  }

  function loadFromTheme(): void {
    if (!weekly) return;
    setName(weekly.theme?.name || '');
    setDescription(weekly.theme?.description || '');
    const pIds = (weekly.theme?.featured_portals ?? []).map((p: any) => String(p?.id || '')).filter(Boolean);
    const aIds = (weekly.theme?.featured_augments ?? []).map((a: any) => String(a?.id || '')).filter(Boolean);
    setPortalIdsRaw(pIds.join(','));
    setAugmentIdsRaw(aIds.join(','));
    const rules: any = weekly.theme?.tournament_rules ?? {};
    setMatchesCounted(String(rules.matches_counted ?? 10));
    setQueueOpen(Boolean(rules.queue_open ?? true));
  }

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
            <CalendarClock size={18} className="text-slate-500" /> Weekly Theme Override
          </CardTitle>
          <Badge variant="neutral">{weekly?.week_id ?? '—'}</Badge>
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
              <Input
                label="Week ID (ISO)"
                value={weekId}
                onChange={(e) => setWeekId(e.target.value)}
                placeholder="2026W03"
              />
            </div>
            <div className="md:col-span-3 flex items-end">
              <Button type="button" variant="secondary" onClick={() => refetch()} className="w-full" disabled={!enabled}>
                Refresh
              </Button>
            </div>
          </div>

          {weekly ? (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-bold text-slate-800">{weekly.theme?.name ?? '—'}</div>
                <Badge variant={weekly.override_active ? 'brand' : 'neutral'}>
                  {weekly.override_active ? 'override active' : 'default (seeded)'}
                </Badge>
              </div>
              <div className="mt-1 text-xs text-slate-600">{weekly.theme?.description ?? ''}</div>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="text-[11px] font-bold text-slate-500 uppercase">Featured Portals</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(weekly.theme?.featured_portals ?? []).map((p: any) => (
                      <Badge key={String(p?.id)} variant="neutral">
                        {String(p?.name ?? portalsById.get(String(p?.id)) ?? p?.id)}
                      </Badge>
                    ))}
                    {!(weekly.theme?.featured_portals ?? []).length ? (
                      <span className="text-xs text-slate-500">—</span>
                    ) : null}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="text-[11px] font-bold text-slate-500 uppercase">Featured Augments</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(weekly.theme?.featured_augments ?? []).slice(0, 14).map((a: any) => (
                      <Badge key={String(a?.id)} variant="neutral">
                        {String(a?.name ?? augmentsById.get(String(a?.id)) ?? a?.id)}
                      </Badge>
                    ))}
                    {!(weekly.theme?.featured_augments ?? []).length ? (
                      <span className="text-xs text-slate-500">—</span>
                    ) : null}
                  </div>
                </div>
              </div>
              <div className="mt-2 text-xs text-slate-500 font-mono">
                override storage key: {weekly.storage_key}
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Enter admin token to load.</div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Set Override</CardTitle>
              <div className="flex items-center gap-2">
                <Button type="button" variant="secondary" onClick={loadFromTheme} disabled={!weekly}>
                  Use current theme
                </Button>
                <Button type="button" variant="outline" onClick={clearOverride} disabled={!enabled || isSaving}>
                  Clear override
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <div className="md:col-span-6">
                  <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Weekly Theme 2026W03" />
                </div>
                <div className="md:col-span-6">
                  <Input
                    label="Description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Featured portal & augment pool rotates weekly."
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <div className="md:col-span-6">
                  <Input
                    label="Featured portal IDs (comma/space separated)"
                    value={portalIdsRaw}
                    onChange={(e) => setPortalIdsRaw(e.target.value)}
                    placeholder="portal_income_plus2, portal_free_reroll"
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    {portalIds.map((id) => (
                      <Badge key={id} variant={portalsById.has(id) ? 'neutral' : 'warning'}>
                        {id}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="md:col-span-6">
                  <Input
                    label="Featured augment IDs (comma/space separated)"
                    value={augmentIdsRaw}
                    onChange={(e) => setAugmentIdsRaw(e.target.value)}
                    placeholder="aug_econ_gold3, aug_synergy_sigil_token"
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    {augmentIds.slice(0, 18).map((id) => (
                      <Badge key={id} variant={augmentsById.has(id) ? 'neutral' : 'warning'}>
                        {id}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <div className="md:col-span-3">
                  <Input
                    label="Tournament matches counted"
                    value={matchesCounted}
                    onChange={(e) => setMatchesCounted(e.target.value)}
                    placeholder="10"
                  />
                </div>
                <div className="md:col-span-3 flex items-end">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={queueOpen}
                      onChange={(e) => setQueueOpen(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    Queue open
                  </label>
                </div>
                <div className="md:col-span-6 flex items-end gap-2">
                  <Button type="button" onClick={applyOverride} isLoading={isSaving} disabled={!enabled || isSaving} className="flex-1">
                    Save override
                  </Button>
                </div>
              </div>

              {statusMsg ? (
                <div className="text-xs text-slate-600">
                  <span className="font-mono">{statusMsg}</span>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </CardContent>
      </Card>
    </div>
  );
};

