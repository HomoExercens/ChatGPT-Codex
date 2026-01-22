import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Info, Save, Shield, UploadCloud, UserPlus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from '../components/ui';
import { MOCK_CREATURES } from '../domain/constants';
import type { Creature } from '../domain/models';
import { RARITY, type Rarity } from '../domain/models';
import { apiFetch } from '../lib/api';
import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';
import type { BlueprintLineage, BlueprintOut, BuildCodeDecodeOut, BuildCodeImportOut, Mode } from '../api/types';

type BlueprintSpec = {
  ruleset_version: string;
  mode: '1v1' | 'team';
  team: Array<{
    creature_id: string;
    formation: 'front' | 'back';
    items: { weapon?: string | null; armor?: string | null; utility?: string | null };
  }>;
};

function coerceSpec(spec: unknown): BlueprintSpec | null {
  if (!spec || typeof spec !== 'object') return null;
  const s = spec as any;
  if (s.mode !== '1v1' && s.mode !== 'team') return null;
  if (!Array.isArray(s.team)) return null;
  return s as BlueprintSpec;
}

type DraftRoundLog = {
  round: number;
  start_gold: number;
  start_level: number;
  start_shop?: { creatures?: string[]; items?: string[] };
  actions?: Array<Record<string, unknown>>;
  end_gold?: number;
  end_level?: number;
};

function coerceDraftLog(meta: Record<string, unknown> | undefined): DraftRoundLog[] | null {
  if (!meta) return null;
  const log = (meta as any).draft_log;
  if (!Array.isArray(log)) return null;
  return log as DraftRoundLog[];
}

function formatDraftAction(action: Record<string, unknown>): string {
  const type = String(action.type ?? 'unknown');
  const ok = action.ok === undefined ? undefined : Boolean(action.ok);
  if (type === 'pass') return 'PASS';
  if (type === 'reroll') return `${ok === false ? 'REROLL_FAIL' : 'REROLL'} (-${action.cost ?? 1})`;
  if (type === 'level_up') return `${ok === false ? 'LEVEL_UP_FAIL' : 'LEVEL_UP'} (-${action.cost ?? '?'})`;
  if (type === 'buy_creature') {
    const cid = String(action.creature_id ?? '?');
    const rarity = String(action.rarity ?? '?');
    const slot = String(action.slot ?? '?');
    const cost = String(action.cost ?? '?');
    return `${ok === false ? 'BUY_C_FAIL' : 'BUY_C'} [${slot}] ${cid} (r${rarity}, -${cost})`;
  }
  if (type === 'buy_item') {
    const iid = String(action.item_id ?? '?');
    const slot = String(action.item_slot ?? '?');
    const rarity = String(action.rarity ?? '?');
    const cost = String(action.cost ?? '?');
    return `${ok === false ? 'BUY_I_FAIL' : 'BUY_I'} ${slot}=${iid} (r${rarity}, -${cost})`;
  }
  return type.toUpperCase();
}

const ITEM_OPTIONS: Record<'weapon' | 'armor' | 'utility', Array<{ id: string; name: string }>> = {
  weapon: [
    { id: 'plasma_lance', name: 'Plasma Lance' },
    { id: 'ember_blade', name: 'Ember Blade' },
    { id: 'thorn_spear', name: 'Thorn Spear' },
    { id: 'ion_repeater', name: 'Ion Repeater' },
    { id: 'crystal_staff', name: 'Crystal Staff' },
    { id: 'void_dagger', name: 'Void Dagger' },
  ],
  armor: [
    { id: 'reinforced_plate', name: 'Reinforced Plate' },
    { id: 'nanofiber_cloak', name: 'Nanofiber Cloak' },
    { id: 'thorn_mail', name: 'Thorn Mail' },
    { id: 'coolant_shell', name: 'Coolant Shell' },
    { id: 'medic_vest', name: 'Medic Vest' },
    { id: 'runic_barrier', name: 'Runic Barrier' },
  ],
  utility: [
    { id: 'targeting_array', name: 'Targeting Array' },
    { id: 'clockwork_core', name: 'Clockwork Core' },
    { id: 'healing_drones', name: 'Healing Drones' },
    { id: 'adrenaline_module', name: 'Adrenaline Module' },
    { id: 'smoke_emitter', name: 'Smoke Emitter' },
    { id: 'phoenix_ash', name: 'Phoenix Ash' },
    { id: 'knight_sigil', name: 'Knight Sigil (+synergy)' },
    { id: 'mech_sigil', name: 'Mech Sigil (+synergy)' },
    { id: 'mystic_sigil', name: 'Mystic Sigil (+synergy)' },
    { id: 'beast_sigil', name: 'Beast Sigil (+synergy)' },
    { id: 'fire_sigil', name: 'Fire Sigil (+synergy)' },
    { id: 'void_sigil', name: 'Void Sigil (+synergy)' },
  ],
};

export const ForgePage: React.FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const lang = useSettingsStore((s) => s.language);
  const t = TRANSLATIONS[lang].common;
  const preselectBlueprintId = searchParams.get('bp');
  const importFromQuery = searchParams.get('import');

  const { data: blueprints = [] } = useQuery({
    queryKey: ['blueprints'],
    queryFn: () => apiFetch<BlueprintOut[]>('/api/blueprints'),
  });

  const first = blueprints[0];
  const [blueprintId, setBlueprintId] = useState<string>(first?.id ?? '');
  const blueprint = blueprints.find((b) => b.id === blueprintId) ?? first;
  const [newMode, setNewMode] = useState<Mode>('1v1');

  const { data: lineage } = useQuery({
    queryKey: ['blueprintLineage', blueprint?.id],
    queryFn: () => apiFetch<BlueprintLineage>(`/api/blueprints/${encodeURIComponent(blueprint!.id)}/lineage`),
    enabled: Boolean(blueprint?.id),
    staleTime: 10_000,
  });
  const lineageChain = lineage?.chain ?? [];
  const lineageChildren = lineage?.children ?? [];

  useEffect(() => {
    if (blueprints.length === 0) return;
    if (preselectBlueprintId && blueprints.some((b) => b.id === preselectBlueprintId)) {
      setBlueprintId(preselectBlueprintId);
      return;
    }
    if (!blueprintId) setBlueprintId(blueprints[0].id);
  }, [blueprints, blueprintId, preselectBlueprintId]);

  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [showDraftSummary, setShowDraftSummary] = useState(false);

  const [draftName, setDraftName] = useState('');
  const [spec, setSpec] = useState<BlueprintSpec | null>(null);
  const [submitCooldownSec, setSubmitCooldownSec] = useState<number | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [importCode, setImportCode] = useState('');
  const [importName, setImportName] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const [importDecodedFor, setImportDecodedFor] = useState<string | null>(null);
  const [autoImportStarted, setAutoImportStarted] = useState(false);

  useEffect(() => {
    if (!blueprint) return;
    setDraftName(blueprint.name);
    setSpec(coerceSpec(blueprint.spec));
  }, [blueprint?.id]);

  const draftLog = useMemo(() => coerceDraftLog(blueprint?.meta), [blueprint?.id]);
  const draftNote = useMemo(() => {
    const note = (blueprint?.meta as any)?.note;
    return typeof note === 'string' ? note : null;
  }, [blueprint?.id]);
  const draftEnv = useMemo(() => {
    const env = (blueprint?.meta as any)?.draft_env;
    return typeof env === 'string' ? env : null;
  }, [blueprint?.id]);
  const draftSeed = useMemo(() => {
    const seed = (blueprint?.meta as any)?.draft_seed;
    return typeof seed === 'number' ? seed : null;
  }, [blueprint?.id]);
  const draftError = useMemo(() => {
    const err = (blueprint?.meta as any)?.error;
    return typeof err === 'string' ? err : null;
  }, [blueprint?.id]);

  const activeSlots = spec?.mode === 'team' ? 3 : 1;
  const slots: Array<Creature | null> = useMemo(() => {
    const byId = new Map(MOCK_CREATURES.map((c) => [c.id, c]));
    const out: Array<Creature | null> = [null, null, null, null, null];
    if (!spec) return out;
    for (let i = 0; i < Math.min(activeSlots, spec.team.length); i++) {
      out[i] = byId.get(spec.team[i].creature_id) ?? null;
    }
    return out;
  }, [activeSlots, spec]);

  const filteredCreatures = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return MOCK_CREATURES;
    return MOCK_CREATURES.filter((c) => c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q));
  }, [search]);

  const getRarityColor = (r: Rarity) => {
    switch (r) {
      case RARITY.COMMON:
        return 'bg-slate-200 text-slate-700';
      case RARITY.RARE:
        return 'bg-blue-100 text-blue-700';
      case RARITY.EPIC:
        return 'bg-purple-100 text-purple-700';
      case RARITY.LEGENDARY:
        return 'bg-amber-100 text-amber-700';
      default:
        return 'bg-slate-100';
    }
  };

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!blueprint) throw new Error('No blueprint selected');
      if (!spec) throw new Error('Blueprint spec not ready');
      return apiFetch<BlueprintOut>(`/api/blueprints/${blueprint.id}`, {
        method: 'PUT',
        body: JSON.stringify({ name: draftName, spec }),
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] });
    },
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!blueprint) throw new Error('No blueprint selected');
      return apiFetch<BlueprintOut>(`/api/blueprints/${blueprint.id}/submit`, { method: 'POST' });
    },
    onSuccess: async () => {
      setSubmitCooldownSec(null);
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] });
    },
    onError: (err) => {
      setSubmitCooldownSec(null);
      const msg = err instanceof Error ? err.message : String(err);
      try {
        const parsed = JSON.parse(msg);
        const detail = parsed?.detail ?? parsed;
        if (detail?.error === 'submit_cooldown') {
          const retry = Number(detail?.retry_after_sec ?? NaN);
          if (Number.isFinite(retry) && retry > 0) setSubmitCooldownSec(Math.round(retry));
        }
      } catch {
        // noop
      }
    },
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      if (!blueprint) throw new Error('No blueprint selected');
      return apiFetch<{ ok: boolean; spec_hash: string }>(`/api/blueprints/${blueprint.id}/validate`, { method: 'POST' });
    },
  });

  const createMutation = useMutation({
    mutationFn: async () =>
      apiFetch<BlueprintOut>('/api/blueprints', {
        method: 'POST',
        body: JSON.stringify({
          name: newMode === 'team' ? 'New Team Blueprint' : 'New 1v1 Blueprint',
          mode: newMode,
        }),
      }),
    onSuccess: async (bp) => {
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] });
      setBlueprintId(bp.id);
    },
  });

  const decodeBuildCodeMutation = useMutation({
    mutationFn: async (code: string) => {
      const cleaned = (code || '').trim();
      if (!cleaned) throw new Error('Missing build code');
      return apiFetch<BuildCodeDecodeOut>('/api/build_code/decode', {
        method: 'POST',
        body: JSON.stringify({ code: cleaned }),
      });
    },
    onSuccess: (out, code) => {
      const cleaned = (code || '').trim();
      if (!out.ok) {
        setImportDecodedFor(null);
        setImportError(out.error || 'Invalid build code');
        return;
      }
      setImportError(null);
      setImportDecodedFor(cleaned);
    },
    onError: (err) => {
      setImportDecodedFor(null);
      const msg = err instanceof Error ? err.message : String(err);
      setImportError(msg);
    },
  });

  const importBuildCodeMutation = useMutation({
    mutationFn: async (code: string) => {
      const cleaned = (code || '').trim();
      if (!cleaned) throw new Error('Missing build code');
      return apiFetch<BuildCodeImportOut>('/api/build_code/import', {
        method: 'POST',
        body: JSON.stringify({ code: cleaned, name: importName.trim() || null }),
      });
    },
    onSuccess: async (out) => {
      if (!out.ok) {
        const err = (out.blueprint as any)?.error;
        setImportError(typeof err === 'string' && err ? err : 'Import failed');
        return;
      }
      const id = (out.blueprint as any)?.id;
      if (typeof id !== 'string' || !id) {
        setImportError('Import failed');
        return;
      }
      setImportError(null);
      setShowImport(false);
      setImportCode('');
      setImportName('');
      setImportDecodedFor(null);
      decodeBuildCodeMutation.reset();
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] });
      setBlueprintId(id);
      navigate(`/forge?bp=${encodeURIComponent(id)}`);
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : String(err);
      setImportError(msg);
    },
  });

  useEffect(() => {
    const code = (importFromQuery || '').trim();
    if (!code) return;
    if (autoImportStarted) return;
    setAutoImportStarted(true);
    setShowImport(true);
    setImportCode(code);
    decodeBuildCodeMutation.mutate(code);
  }, [autoImportStarted, importFromQuery]);

  const copyBuildCode = async () => {
    const code = blueprint?.build_code;
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      // ignore
    }
  };

  const handleSelectCreature = (creature: Creature) => {
    if (selectedSlot === null) return;
    if (!spec) return;
    if (selectedSlot >= activeSlots) return;
    const next = structuredClone(spec);
    next.team[selectedSlot].creature_id = creature.id;
    setSpec(next);
    setSelectedSlot(null);
  };

  const setItem = (slotIndex: number, slot: 'weapon' | 'armor' | 'utility', value: string | null) => {
    if (!spec) return;
    if (slotIndex >= activeSlots) return;
    const next = structuredClone(spec);
    next.team[slotIndex].items = { ...next.team[slotIndex].items, [slot]: value };
    setSpec(next);
  };

  const synergy = useMemo(() => {
    const tags = slots.slice(0, activeSlots).flatMap((c) => (c ? c.synergies : []));
    const counts = new Map<string, number>();
    for (const tag of tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
    return [...counts.entries()].filter(([, n]) => n >= 2).map(([tag, n]) => ({ tag, n }));
  }, [activeSlots, slots]);

  const selectedItems = useMemo(() => {
    if (!spec || selectedSlot === null || selectedSlot >= activeSlots) return null;
    return spec.team[selectedSlot]?.items ?? {};
  }, [activeSlots, selectedSlot, spec]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-140px)]">
      {showImport ? (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4">
          <Card className="w-full max-w-xl">
            <CardHeader>
              <CardTitle>Import Build Code</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowImport(false);
                  setImportCode('');
                  setImportName('');
                  setImportError(null);
                  setImportDecodedFor(null);
                  decodeBuildCodeMutation.reset();
                }}
              >
                Close
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                label="Build Code"
                placeholder="NL1_..."
                value={importCode}
                onChange={(e) => {
                  setImportCode(e.target.value);
                  setImportError(null);
                  setImportDecodedFor(null);
                  decodeBuildCodeMutation.reset();
                }}
              />
              <Input
                label="Name (optional)"
                placeholder="Imported Build"
                value={importName}
                onChange={(e) => setImportName(e.target.value)}
              />

              {decodeBuildCodeMutation.isPending ? (
                <div className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2">Decoding…</div>
              ) : decodeBuildCodeMutation.data?.ok ? (
                <div className="text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 space-y-2">
                  <div className="flex flex-wrap gap-2 items-center">
                    <Badge variant="info">{decodeBuildCodeMutation.data.mode ?? '—'}</Badge>
                    <span className="text-slate-700">
                      ruleset: <span className="font-mono">{decodeBuildCodeMutation.data.ruleset_version ?? '—'}</span>
                    </span>
                    <span className="text-slate-500">
                      pack: <span className="font-mono">{decodeBuildCodeMutation.data.pack_hash ?? '—'}</span>
                    </span>
                  </div>
                  {Array.isArray(decodeBuildCodeMutation.data.blueprint_spec?.team) ? (
                    <div className="text-slate-600">
                      team:{' '}
                      <span className="font-mono">
                        {decodeBuildCodeMutation.data.blueprint_spec.team
                          .map((s: any) => String(s?.creature_id ?? '?'))
                          .join(', ')}
                      </span>
                    </div>
                  ) : null}
                  {(decodeBuildCodeMutation.data.warnings ?? []).length ? (
                    <div className="space-y-1">
                      <div className="text-slate-500 font-semibold">Warnings</div>
                      <ul className="list-disc pl-5">
                        {(decodeBuildCodeMutation.data.warnings ?? []).slice(0, 6).map((w, idx) => (
                          <li key={`${w.type}-${idx}`} className="text-amber-800">
                            <span className="font-mono">{w.type}</span>: {w.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="text-slate-500">No warnings.</div>
                  )}
                </div>
              ) : null}

              {importError ? (
                <div className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">{importError}</div>
              ) : null}
              <div className="flex gap-2 justify-end">
                <Button
                  variant="secondary"
                  onClick={() => {
                    setShowImport(false);
                    setImportCode('');
                    setImportName('');
                    setImportError(null);
                    setImportDecodedFor(null);
                    decodeBuildCodeMutation.reset();
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => decodeBuildCodeMutation.mutate(importCode)}
                  isLoading={decodeBuildCodeMutation.isPending}
                  disabled={!importCode.trim()}
                >
                  Preview
                </Button>
                <Button
                  onClick={() => importBuildCodeMutation.mutate(importCode)}
                  isLoading={importBuildCodeMutation.isPending}
                  disabled={!importDecodedFor || importDecodedFor !== importCode.trim() || !decodeBuildCodeMutation.data?.ok}
                >
                  Import
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}
      <Card className="lg:col-span-3 flex flex-col h-full overflow-hidden">
        <CardHeader className="py-3 space-y-3">
          <div className="flex gap-2">
            <select
              className="px-3 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none text-sm"
              value={newMode}
              onChange={(e) => setNewMode(e.target.value as Mode)}
              aria-label="New blueprint mode"
            >
              <option value="1v1">1v1</option>
              <option value="team">Team (3v3)</option>
            </select>
            <Button variant="secondary" size="sm" onClick={() => createMutation.mutate()} isLoading={createMutation.isPending}>
              + New
            </Button>
            <select
              className="flex-1 px-3 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none text-sm"
              value={blueprint?.id ?? ''}
              onChange={(e) => setBlueprintId(e.target.value)}
              aria-label="Select blueprint"
            >
              {blueprints.map((bp) => (
                <option key={bp.id} value={bp.id}>
                  {bp.name} ({bp.status})
                </option>
              ))}
            </select>
          </div>

          <Input placeholder={t.searchCreatures} className="h-9 text-sm" value={search} onChange={(e) => setSearch(e.target.value)} />

          <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar">
            {['Tank', 'DPS', 'Support'].map((role) => (
              <Badge key={role} variant="neutral" className="cursor-pointer hover:bg-slate-200 whitespace-nowrap">
                {role}
              </Badge>
            ))}
          </div>
        </CardHeader>
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {filteredCreatures.map((creature) => (
            <div
              key={creature.id}
              onClick={() => selectedSlot !== null && handleSelectCreature(creature)}
              className={`flex items-center gap-3 p-2 rounded-xl border cursor-pointer hover:bg-slate-50 transition-all ${
                selectedSlot !== null ? 'ring-2 ring-brand-200 hover:ring-brand-400' : 'border-slate-100'
              }`}
            >
              <img src={creature.imageUrl} className="w-10 h-10 rounded-lg bg-slate-200 object-cover" alt={creature.name} />
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-slate-800 truncate">{creature.name}</div>
                <div className="flex gap-1 mt-0.5">
                  <span className={`text-[10px] px-1 rounded ${getRarityColor(creature.rarity)}`}>{creature.role}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="lg:col-span-6 flex flex-col gap-4">
        <div className="bg-white p-2 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center gap-2">
          <div className="flex items-center gap-2 px-2 min-w-0">
            <span className="text-sm font-bold text-slate-600">{t.targetBlueprint}:</span>
            <input
              className="text-sm font-medium bg-transparent outline-none border-b border-transparent focus:border-brand-300 min-w-0"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
            />
            {blueprint?.status === 'draft' ? <Badge variant="warning">{t.draft}</Badge> : <Badge variant="success">Submitted</Badge>}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setShowImport(true);
                setImportError(null);
                setImportDecodedFor(null);
                decodeBuildCodeMutation.reset();
              }}
            >
              <UserPlus size={16} className="mr-2" /> Import
            </Button>
            <Button size="sm" variant="ghost" onClick={copyBuildCode} disabled={!blueprint?.build_code}>
              <Copy size={16} className="mr-2" /> Copy Code
            </Button>
            <Button size="sm" variant="ghost" onClick={() => validateMutation.mutate()} isLoading={validateMutation.isPending}>
              Validate
            </Button>
            <Button size="sm" variant="ghost" onClick={() => updateMutation.mutate()} isLoading={updateMutation.isPending}>
              <Save size={16} className="mr-2" /> {t.save}
            </Button>
            <Button size="sm" onClick={() => submitMutation.mutate()} isLoading={submitMutation.isPending}>
              <UploadCloud size={16} className="mr-2" /> {t.submit}
            </Button>
          </div>
        </div>

        {updateMutation.error ? <div className="text-xs text-red-600">{String(updateMutation.error)}</div> : null}
        {submitCooldownSec !== null ? (
          <div className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2">
            Submit locked — try again in <span className="font-mono">{submitCooldownSec}s</span>.
          </div>
        ) : submitMutation.error ? (
          <div className="text-xs text-red-600">{String(submitMutation.error)}</div>
        ) : null}
        {validateMutation.data ? (
          <div className="text-xs text-green-700 bg-green-50 border border-green-100 rounded-xl px-3 py-2">
            OK — spec_hash: <span className="font-mono">{validateMutation.data.spec_hash}</span>
          </div>
        ) : null}

        {draftLog ? (
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <button
              type="button"
              className="w-full flex items-center justify-between"
              onClick={() => setShowDraftSummary((v) => !v)}
            >
              <div className="flex items-center gap-2">
                <Info size={16} className="text-slate-500" />
                <span className="text-sm font-bold text-slate-800">Draft Summary</span>
                {draftNote === 'policy_inference' ? (
                  <Badge variant="info">POLICY</Badge>
                ) : (
                  <Badge variant="warning">FALLBACK</Badge>
                )}
              </div>
              <span className="text-xs text-slate-500">{showDraftSummary ? 'Hide' : 'Show'}</span>
            </button>
            {showDraftSummary ? (
              <div className="mt-3 space-y-3">
                <div className="text-[10px] text-slate-500 font-mono">
                  env: {draftEnv ?? '—'} | seed: {draftSeed ?? '—'}
                </div>
                {draftNote !== 'policy_inference' && draftError ? (
                  <div className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-2 py-1">
                    {draftError}
                  </div>
                ) : null}
                {draftLog.map((r) => (
                  <div key={r.round} className="bg-slate-50 border border-slate-100 rounded-lg p-2">
                    <div className="flex justify-between items-center">
                      <div className="text-xs font-bold text-slate-700">
                        R{r.round} • L{r.start_level} • G{r.start_gold}
                      </div>
                      {r.end_gold != null && r.end_level != null ? (
                        <div className="text-[10px] text-slate-500 font-mono">
                          → L{r.end_level} • G{r.end_gold}
                        </div>
                      ) : null}
                    </div>
                    <div className="mt-1 text-[10px] text-slate-500 font-mono break-words">
                      offer.c: {(r.start_shop?.creatures ?? []).join(', ') || '—'}
                      <br />
                      offer.i: {(r.start_shop?.items ?? []).join(', ') || '—'}
                    </div>
                    <div className="mt-2 space-y-1">
                      {(r.actions ?? []).length > 0 ? (
                        (r.actions ?? []).slice(0, 8).map((a, idx) => (
                          <div key={idx} className="text-[10px] text-slate-700 font-mono">
                            {formatDraftAction(a)}
                          </div>
                        ))
                      ) : (
                        <div className="text-[10px] text-slate-400">No actions</div>
                      )}
                      {(r.actions ?? []).length > 8 ? (
                        <div className="text-[10px] text-slate-400">…</div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="flex-1 bg-slate-100 rounded-3xl border-2 border-slate-200 border-dashed relative overflow-hidden flex items-center justify-center">
          <div
            className="absolute inset-0 opacity-10"
            style={{ backgroundImage: 'radial-gradient(#94a3b8 1px, transparent 1px)', backgroundSize: '24px 24px' }}
          ></div>

          <div className="relative z-10 grid grid-cols-3 gap-8">
            {[0, 1, 2, 3, 4].map((index) => {
              const disabled = index >= activeSlots;
              return (
                <button
                  key={index}
                  onClick={() => !disabled && setSelectedSlot(index)}
                  type="button"
                  className={`
                      w-24 h-24 md:w-32 md:h-32 rounded-3xl flex flex-col items-center justify-center transition-all cursor-pointer shadow-lg
                      ${index === 1 || index === 3 ? 'mt-12' : ''}
                      ${slots[index] ? 'bg-white border-2 border-brand-500' : 'bg-slate-200/50 border-2 border-slate-300 border-dashed hover:bg-slate-200'}
                      ${selectedSlot === index ? 'ring-4 ring-brand-400 ring-offset-2 scale-105' : ''}
                      ${disabled ? 'opacity-40 cursor-not-allowed hover:bg-slate-200/50' : ''}
                    `}
                  aria-label={`Formation slot ${index + 1}`}
                  disabled={disabled}
                >
                  {slots[index] ? (
                    <>
                      <img src={slots[index]!.imageUrl} className="w-12 h-12 md:w-16 md:h-16 rounded-xl mb-1 object-cover" alt="" />
                      <span className="text-[10px] font-bold text-slate-700 bg-slate-100 px-2 rounded-full max-w-[90%] truncate">
                        {slots[index]!.name}
                      </span>
                    </>
                  ) : (
                    <UserPlus className="text-slate-400" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <Card className="lg:col-span-3 h-full overflow-y-auto">
        <CardHeader>
          <CardTitle>{t.synergies}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {synergy.length > 0 ? (
            synergy.map((s) => (
              <div key={s.tag}>
                <div className="flex justify-between items-center mb-1">
                  <span className="font-bold text-sm text-slate-700 flex items-center gap-2">
                    <Shield size={14} className="text-blue-500" /> {s.tag}
                  </span>
                  <span className="text-xs text-slate-500">{s.n}/{activeSlots}</span>
                </div>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500" style={{ width: `${Math.min(100, (s.n / activeSlots) * 100)}%` }}></div>
                </div>
              </div>
            ))
          ) : (
            <div className="text-center text-slate-400 py-6">
              <Info size={32} className="mx-auto mb-2 opacity-50" />
              <p className="text-sm">{t.noSynergy}</p>
            </div>
          )}

          <div className="pt-4 border-t border-slate-100 space-y-3">
            <h4 className="text-xs font-bold text-slate-400 uppercase">{t.inventory}</h4>
            {selectedSlot === null || selectedSlot >= activeSlots ? (
              <div className="text-xs text-slate-500">Select a slot to edit equipment.</div>
            ) : (
              <div className="space-y-3">
                {(['weapon', 'armor', 'utility'] as const).map((slot) => (
                  <div key={slot}>
                    <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">{slot}</label>
                    <select
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none text-sm"
                      value={(selectedItems?.[slot] ?? '') as string}
                      onChange={(e) => setItem(selectedSlot, slot, e.target.value ? e.target.value : null)}
                    >
                      <option value="">(none)</option>
                      {ITEM_OPTIONS[slot].map((opt) => (
                        <option key={opt.id} value={opt.id}>
                          {opt.name}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-slate-100 space-y-3">
            <h4 className="text-xs font-bold text-slate-400 uppercase">Lineage</h4>
            {lineageChain.length ? (
              <div className="space-y-2">
                {lineageChain.slice(0, 6).map((n, idx) => (
                  <div key={n.blueprint_id} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-bold text-slate-800 truncate">{n.name}</div>
                        <div className="text-[11px] text-slate-500 truncate">
                          by {n.display_name} · <span className="font-mono">{n.blueprint_id}</span>
                        </div>
                      </div>
                      <Badge variant={n.status === 'submitted' ? 'success' : 'neutral'}>{n.status}</Badge>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                      {typeof n.children_count === 'number' ? <span>forks: {n.children_count}</span> : null}
                      {idx === 0 && n.origin_code_hash ? (
                        <span className="font-mono">origin: {String(n.origin_code_hash).slice(0, 10)}…</span>
                      ) : null}
                    </div>
                    {n.status === 'submitted' ? (
                      <div className="mt-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => (window.location.href = `/s/build/${encodeURIComponent(n.blueprint_id)}`)}
                        >
                          View Share Page
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-slate-500">Lineage not available.</div>
            )}

            <div className="pt-2 space-y-2">
              <h5 className="text-[11px] font-bold text-slate-400 uppercase">Top Forks</h5>
              {lineageChildren.length ? (
                <div className="space-y-2">
                  {lineageChildren.slice(0, 6).map((n) => (
                    <div key={n.blueprint_id} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-slate-800 truncate">{n.name}</div>
                          <div className="text-[11px] text-slate-500 truncate">
                            by {n.display_name} · <span className="font-mono">{n.blueprint_id}</span>
                          </div>
                        </div>
                        <Badge variant={n.status === 'submitted' ? 'success' : 'neutral'}>{n.status}</Badge>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                        {typeof n.children_count === 'number' ? <span>forks: {n.children_count}</span> : null}
                      </div>
                      {n.status === 'submitted' ? (
                        <div className="mt-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => (window.location.href = `/s/build/${encodeURIComponent(n.blueprint_id)}`)}
                          >
                            View Share Page
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-slate-500">No forks yet.</div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
