import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, PackageOpen } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { apiFetch } from '../lib/api';

type PackEntry = {
  path: string;
  ruleset_version: string | null;
  pack_hash: string | null;
  declared_pack_hash?: string | null;
  created_at?: string | null;
  valid?: boolean;
};

type OpsPacksOut = {
  active_ruleset_version: string;
  active_pack_hash: string | null;
  active_pack_path: string | null;
  available_packs: PackEntry[];
  candidate: PackEntry | null;
  promotion: Record<string, any> | null;
  storage_keys: Record<string, string>;
};

type PreflightLatestOut = {
  available: boolean;
  report: Record<string, any>;
  artifact_url: string | null;
  markdown_url: string | null;
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

export const OpsPacksPage: React.FC = () => {
  const [adminToken, setAdminToken] = useState(loadAdminToken());
  const [candidatePath, setCandidatePath] = useState('packs/default/v1/pack.json');
  const [note, setNote] = useState('');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    saveAdminToken(adminToken);
  }, [adminToken]);

  const enabled = Boolean(adminToken.trim());

  const { data: packs, refetch } = useQuery({
    queryKey: ['ops', 'packs', enabled],
    queryFn: () => apiFetch<OpsPacksOut>('/api/ops/packs'),
    enabled,
    staleTime: 5_000,
  });

  const { data: preflight } = useQuery({
    queryKey: ['ops', 'preflight', enabled],
    queryFn: () => apiFetch<PreflightLatestOut>('/api/ops/preflight/latest'),
    enabled,
    staleTime: 10_000,
  });

  useEffect(() => {
    if (!packs) return;
    if (packs.candidate?.path) setCandidatePath(packs.candidate.path);
  }, [packs]);

  const sortedAvailable = useMemo(() => {
    const items = packs?.available_packs ?? [];
    return [...items].sort((a, b) => String(a.path).localeCompare(String(b.path)));
  }, [packs?.available_packs]);

  const activePath = packs?.active_pack_path || 'packs/default/v1/pack.json';

  const preflightCmd = useMemo(() => {
    const cand = candidatePath || 'packs/default/v1/pack.json';
    return `make ops-preflight BASELINE=${activePath} CANDIDATE=${cand}`;
  }, [activePath, candidatePath]);

  async function setCandidate(): Promise<void> {
    if (!enabled) return;
    setBusy(true);
    setStatusMsg(null);
    try {
      await apiFetch<OpsPacksOut>('/api/ops/packs/candidate', {
        method: 'POST',
        body: JSON.stringify({ path: candidatePath }),
      });
      setStatusMsg('Candidate pack set.');
      await refetch();
    } catch (err: any) {
      setStatusMsg(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function promoteCandidate(): Promise<void> {
    if (!enabled) return;
    setBusy(true);
    setStatusMsg(null);
    try {
      await apiFetch<OpsPacksOut>('/api/ops/packs/promote', {
        method: 'POST',
        body: JSON.stringify({ note: note || null }),
      });
      setStatusMsg('Promotion plan written (see patch notes + ops storage keys).');
      await refetch();
    } catch (err: any) {
      setStatusMsg(String(err?.message || err));
    } finally {
      setBusy(false);
    }
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
            <PackageOpen size={18} className="text-slate-500" /> Packs Promotion
          </CardTitle>
          <Badge variant="neutral">{packs?.active_ruleset_version ?? '—'}</Badge>
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
            <div className="md:col-span-6 flex items-end gap-2">
              <Button type="button" variant="secondary" onClick={() => refetch()} disabled={!enabled} className="flex-1">
                Refresh
              </Button>
              <Link to="/ops/weekly" className="flex-1">
                <Button type="button" variant="outline" className="w-full" disabled={!enabled}>
                  Weekly override →
                </Button>
              </Link>
            </div>
          </div>

          {packs ? (
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
              <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-4 py-3">
                <div className="text-[11px] font-bold text-slate-500 uppercase">Active</div>
                <div className="mt-2 text-sm font-bold text-slate-800">ruleset: {packs.active_ruleset_version}</div>
                <div className="mt-1 text-xs text-slate-600 font-mono break-all">
                  pack_hash: {packs.active_pack_hash ?? '—'}
                </div>
                <div className="mt-1 text-xs text-slate-600 font-mono break-all">
                  pack_path: {packs.active_pack_path ?? '—'}
                </div>
              </div>
              <div className="md:col-span-6 rounded-xl border border-slate-200 bg-white px-4 py-3">
                <div className="text-[11px] font-bold text-slate-500 uppercase">Candidate</div>
                <div className="mt-2 text-xs text-slate-600">Select a pack.json under repo `packs/`.</div>
                <select
                  className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
                  value={candidatePath}
                  onChange={(e) => setCandidatePath(e.target.value)}
                >
                  {sortedAvailable.map((p) => (
                    <option key={p.path} value={p.path}>
                      {p.path} {p.valid === false ? '(INVALID)' : ''}
                    </option>
                  ))}
                </select>
                <div className="mt-2 flex gap-2">
                  <Button type="button" variant="secondary" onClick={setCandidate} isLoading={busy} disabled={!enabled || busy}>
                    Set candidate
                  </Button>
                  <Button type="button" onClick={promoteCandidate} isLoading={busy} disabled={!enabled || busy}>
                    Promote
                  </Button>
                </div>
                <div className="mt-2 text-xs text-slate-500 font-mono break-all">
                  storage keys: {Object.values(packs.storage_keys).join(' · ')}
                </div>
              </div>
              <div className="md:col-span-12">
                <Input
                  label="Promotion note (optional)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Approved for next weekly rotation"
                />
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Enter admin token to load.</div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Patch Preflight</CardTitle>
              <Badge variant={preflight?.available ? 'success' : 'warning'}>{preflight?.available ? 'available' : 'missing'}</Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-xs text-slate-600">
                Run preflight on the server by executing this command (local dev):
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-mono break-all">
                {preflightCmd}
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
            </CardContent>
          </Card>

          {statusMsg ? (
            <div className="text-xs text-slate-600">
              <span className="font-mono">{statusMsg}</span>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

