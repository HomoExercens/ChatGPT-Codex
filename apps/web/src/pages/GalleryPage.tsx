import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, GitFork, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Skeleton } from '../components/ui';
import { apiFetch } from '../lib/api';
import type { BuildOfDay, GalleryBlueprintRow, Mode } from '../api/types';

function fmtPct(x: number): string {
  if (!Number.isFinite(x)) return '—';
  return `${Math.round(x * 100)}%`;
}

export const GalleryPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [mode, setMode] = useState<Mode>('1v1');
  const [tag, setTag] = useState<string>('');
  const [q, setQ] = useState<string>('');

  const tagFilter = tag.trim() || undefined;

  const { data: buildOfDay } = useQuery({
    queryKey: ['buildOfDay', mode],
    queryFn: () => apiFetch<BuildOfDay>(`/api/gallery/build_of_day?mode=${encodeURIComponent(mode)}`),
    staleTime: 60_000,
  });
  const bodBlueprint = buildOfDay?.blueprint ?? null;
  const bodDate = buildOfDay?.date ?? '';

  const { data: rows, isLoading, error } = useQuery({
    queryKey: ['gallery', mode, tagFilter],
    queryFn: () =>
      apiFetch<GalleryBlueprintRow[]>(
        `/api/gallery/blueprints?mode=${encodeURIComponent(mode)}${tagFilter ? `&tag=${encodeURIComponent(tagFilter)}` : ''}&sort=trending&limit=50`,
      ),
    staleTime: 30_000,
  });

  const filteredRows = useMemo(() => {
    const list = rows ?? [];
    const query = q.trim().toLowerCase();
    if (!query) return list;
    return list.filter((r) => {
      const hay = `${r.name} ${r.creator.display_name} ${r.synergy_tags.join(' ')}`.toLowerCase();
      return hay.includes(query);
    });
  }, [rows, q]);

  const tagOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of rows ?? []) {
      for (const t of r.synergy_tags ?? []) set.add(t);
    }
    return Array.from(set).sort();
  }, [rows]);

  const forkMutation = useMutation({
    mutationFn: async (blueprintId: string) =>
      apiFetch<{ id: string }>(`/api/blueprints/${encodeURIComponent(blueprintId)}/fork`, {
        method: 'POST',
        body: JSON.stringify({}),
      }),
    onSuccess: async (bp) => {
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] });
      const id = (bp as any)?.id;
      if (typeof id === 'string' && id) navigate(`/forge?bp=${encodeURIComponent(id)}`);
    },
  });

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Blueprint Gallery</h1>
          <p className="text-slate-600 mt-1">Browse the latest submitted builds. Fork, tweak, submit, and queue.</p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant={mode === '1v1' ? 'primary' : 'secondary'} onClick={() => setMode('1v1')}>
            1v1
          </Button>
          <Button variant={mode === 'team' ? 'primary' : 'secondary'} onClick={() => setMode('team')}>
            Team (3v3)
          </Button>
        </div>
      </div>

      {bodBlueprint ? (
        <Card className="border-brand-200 bg-gradient-to-br from-brand-50 to-white">
          <CardHeader>
            <div className="flex flex-col">
              <CardTitle>Build of the Day</CardTitle>
              <span className="text-xs text-slate-500">{bodDate}</span>
            </div>
            <Badge variant="brand">{bodBlueprint.mode.toUpperCase()}</Badge>
          </CardHeader>
          <CardContent className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <div className="min-w-0">
              <div className="font-bold text-slate-900 truncate">{bodBlueprint.name}</div>
              <div className="text-sm text-slate-600 truncate">
                by{' '}
                <button
                  type="button"
                  className="underline underline-offset-2 hover:text-brand-700"
                  onClick={() => navigate(`/profile/${encodeURIComponent(bodBlueprint.creator.user_id)}?mode=${mode}`)}
                >
                  {bodBlueprint.creator.display_name}
                </button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(bodBlueprint.synergy_tags ?? []).slice(0, 6).map((t) => (
                  <Badge key={t} variant="info">
                    {t}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button
                variant="secondary"
                onClick={() => {
                  const code = bodBlueprint.build_code;
                  if (code) void copyToClipboard(code);
                }}
                disabled={!bodBlueprint.build_code}
              >
                <Copy size={16} className="mr-2" /> Copy Build Code
              </Button>
              <Button onClick={() => forkMutation.mutate(bodBlueprint.blueprint_id)} isLoading={forkMutation.isPending}>
                <GitFork size={16} className="mr-2" /> Fork
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="flex flex-col md:flex-row gap-3 md:items-end">
          <div className="flex-1">
            <Input
              label="Search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Name, creator, or synergy tag…"
            />
          </div>
          <div className="w-full md:w-64">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Synergy Tag</label>
            <div className="relative">
              <Search size={16} className="absolute left-3 top-3 text-slate-400" />
              <select
                className="w-full pl-9 pr-3 py-2 rounded-xl border bg-slate-50 focus:bg-white transition-colors outline-none focus:ring-2 focus:ring-brand-200 border-slate-200 focus:border-brand-500"
                value={tag}
                onChange={(e) => setTag(e.target.value)}
              >
                <option value="">All</option>
                {tagOptions.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Card>
          <CardContent>
            <div className="text-sm text-red-600">Failed to load gallery: {String(error)}</div>
          </CardContent>
        </Card>
      ) : null}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="space-y-3">
                <Skeleton className="h-6 w-2/3" />
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-10 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredRows.map((r) => (
            <Card key={r.blueprint_id}>
              <CardHeader>
                <div className="min-w-0">
                  <CardTitle className="truncate">{r.name}</CardTitle>
                  <div className="text-xs text-slate-600 truncate">
                    by{' '}
                    <button
                      type="button"
                      className="underline underline-offset-2 hover:text-brand-700"
                      onClick={() => navigate(`/profile/${encodeURIComponent(r.creator.user_id)}?mode=${mode}`)}
                    >
                      {r.creator.display_name}
                    </button>
                  </div>
                </div>
                <Badge variant="neutral">{r.mode.toUpperCase()}</Badge>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-1.5">
                  {(r.synergy_tags ?? []).slice(0, 8).map((t) => (
                    <Badge key={t} variant="info">
                      {t}
                    </Badge>
                  ))}
                </div>

                <div className="flex items-center justify-between text-sm">
                  <div className="text-slate-700">
                    <span className="font-semibold">{fmtPct(r.stats.winrate)}</span> winrate
                  </div>
                  <div className="text-slate-500">{r.stats.matches} matches</div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    className="flex-1"
                    onClick={() => {
                      const code = r.build_code;
                      if (code) void copyToClipboard(code);
                    }}
                    disabled={!r.build_code}
                  >
                    <Copy size={16} className="mr-2" /> Copy Code
                  </Button>
                  <Button className="flex-1" onClick={() => forkMutation.mutate(r.blueprint_id)} isLoading={forkMutation.isPending}>
                    <GitFork size={16} className="mr-2" /> Fork
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
