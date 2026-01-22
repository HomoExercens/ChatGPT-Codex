import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowRight, Download, Heart, Loader2, MessageCircle, PlayCircle, Sparkles } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch, apiFetchBlob } from '../lib/api';
import { useMetaFlags } from '../lib/flags';
import { useSettingsStore } from '../stores/settings';
import { TRANSLATIONS } from '../lib/translations';

type DemoPreset = {
  id: 'mech' | 'storm' | 'void';
  title: string;
  subtitle: string;
  blueprint_id: string;
};

type DemoRunResponse = {
  match_id: string;
  replay_id: string;
  challenge_id: string;
  blueprint_id: string;
  share_url: string;
  kit_url: string;
};

type BestClipJobsOut = {
  thumbnail: { job_id: string; status: string; cache_key: string };
  vertical_mp4: { job_id: string; status: string; cache_key: string };
};

type RenderJobOut = {
  id: string;
  kind: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  progress: number;
  cache_key: string;
  artifact_url: string | null;
  error_message: string | null;
};

const DEMO_RUN_STORAGE_KEY = 'neuroleague.demo_run_last';

export const DemoPage: React.FC = () => {
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const t = TRANSLATIONS[lang].common;

  const { data: flags } = useMetaFlags();
  const steamAppId = (flags?.steam_app_id ?? '').trim();
  const discordInviteUrl = (flags?.discord_invite_url ?? '').trim();

  const { data: presets } = useQuery({
    queryKey: ['demoPresets'],
    queryFn: () => apiFetch<DemoPreset[]>('/api/demo/presets'),
    staleTime: 60_000,
  });

  const defaultPreset = useMemo<DemoPreset['id']>(() => {
    const ids = new Set((presets ?? []).map((p) => p.id));
    if (ids.has('mech')) return 'mech';
    return (presets?.[0]?.id ?? 'mech') as DemoPreset['id'];
  }, [presets]);

  const [presetId, setPresetId] = useState<DemoPreset['id']>('mech');
  useEffect(() => setPresetId(defaultPreset), [defaultPreset]);

  const trackMutation = useMutation({
    mutationFn: async ({
      type,
      meta,
    }: {
      type:
        | 'demo_run_start'
        | 'demo_run_done'
        | 'demo_kit_download'
        | 'demo_beat_this_click'
        | 'wishlist_click'
        | 'discord_click';
      meta?: Record<string, any>;
    }) => {
      await apiFetch<{ ok: boolean }>('/api/events/track', {
        method: 'POST',
        body: JSON.stringify({ type, source: 'demo', meta: meta ?? {} }),
      });
      return true;
    },
  });

  const demoRunMutation = useMutation({
    mutationFn: async (pid: DemoPreset['id']) =>
      apiFetch<DemoRunResponse>('/api/demo/run', { method: 'POST', body: JSON.stringify({ preset_id: pid }) }),
  });

  const [run, setRun] = useState<DemoRunResponse | null>(null);
  const [bestClipUrl, setBestClipUrl] = useState<string | null>(null);
  const [bestClipJobId, setBestClipJobId] = useState<string | null>(null);
  const [bestClipError, setBestClipError] = useState<string | null>(null);

  useEffect(() => {
    if (run) return;
    if (typeof sessionStorage === 'undefined') return;
    try {
      const raw = sessionStorage.getItem(DEMO_RUN_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<DemoRunResponse>;
      if (
        parsed &&
        typeof parsed.match_id === 'string' &&
        typeof parsed.replay_id === 'string' &&
        typeof parsed.challenge_id === 'string' &&
        typeof parsed.blueprint_id === 'string' &&
        typeof parsed.share_url === 'string' &&
        typeof parsed.kit_url === 'string'
      ) {
        setRun(parsed as DemoRunResponse);
      }
    } catch {
      // ignore
    }
  }, [run]);

  useEffect(() => {
    return () => {
      if (bestClipUrl && bestClipUrl.startsWith('blob:')) {
        try {
          URL.revokeObjectURL(bestClipUrl);
        } catch {
          // ignore
        }
      }
    };
  }, [bestClipUrl]);

  const bestClipJobsMutation = useMutation({
    mutationFn: async (matchId: string) =>
      apiFetch<BestClipJobsOut>(`/api/matches/${encodeURIComponent(matchId)}/best_clip_jobs`, {
        method: 'POST',
        body: JSON.stringify({}),
      }),
  });

  const pollJob = async (jobId: string): Promise<RenderJobOut> => {
    for (let i = 0; i < 120; i++) {
      const job = await apiFetch<RenderJobOut>(`/api/render_jobs/${encodeURIComponent(jobId)}`);
      if (job.status === 'failed') throw new Error(job.error_message || 'Render job failed');
      if (job.status === 'done') return job;
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error('Timed out waiting for render job');
  };

  useEffect(() => {
    let cancelled = false;
    const runAsync = async () => {
      if (!run) return;
      setBestClipUrl(null);
      setBestClipError(null);

      try {
        const jobs = await bestClipJobsMutation.mutateAsync(run.match_id);
        if (cancelled) return;
        setBestClipJobId(jobs.vertical_mp4.job_id);

        const done = await pollJob(jobs.vertical_mp4.job_id);
        if (cancelled) return;
        if (!done.artifact_url) throw new Error('Render finished but artifact URL missing');
        const blob = await apiFetchBlob(done.artifact_url);
        if (cancelled) return;
        setBestClipUrl(URL.createObjectURL(blob));
      } catch (e: any) {
        if (cancelled) return;
        setBestClipError(String(e?.message ?? e ?? 'Failed to generate best clip'));
      }
    };
    runAsync();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.match_id]);

  const selectedPreset = useMemo(() => (presets ?? []).find((p) => p.id === presetId) ?? null, [presets, presetId]);

  const wishlistUrls = useMemo(() => {
    const raw = steamAppId.trim();
    const appId = /^\d+$/.test(raw) ? raw : '';
    if (!appId) return null;
    return {
      appId,
      steam: `steam://store/${appId}`,
      web: `https://store.steampowered.com/app/${appId}`,
    };
  }, [steamAppId]);

  const openExternal = async (url: string) => {
    const w = window as any;
    const bridge = w?.neuroleagueDesktop;
    if (bridge && typeof bridge.openExternal === 'function') {
      try {
        const res = bridge.openExternal(url);
        if (res && typeof res.then === 'function') return Boolean(await res);
        if (typeof res === 'boolean') return res;
        return true;
      } catch {
        return false;
      }
    }
    if (url.startsWith('steam://')) {
      try {
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = url;
        document.body.appendChild(iframe);
        setTimeout(() => iframe.remove(), 2000);
        return true;
      } catch {
        // fall through
      }
    }
    try {
      window.open(url, '_blank', 'noopener,noreferrer');
      return true;
    } catch {
      try {
        window.location.href = url;
        return true;
      } catch {
        return false;
      }
    }
  };

  const onWishlistClick = async () => {
    if (!wishlistUrls) return;

    const bridge = (window as any)?.neuroleagueDesktop;
    if (bridge && typeof bridge.openExternal === 'function') {
      trackMutation.mutate({
        type: 'wishlist_click',
        meta: { app_id: wishlistUrls.appId, path: 'steam', platform: 'desktop' },
      });
      const ok = await openExternal(wishlistUrls.steam);
      if (!ok) {
        trackMutation.mutate({
          type: 'wishlist_click',
          meta: { app_id: wishlistUrls.appId, path: 'https', platform: 'desktop' },
        });
        await openExternal(wishlistUrls.web);
      }
      return;
    }

    trackMutation.mutate({
      type: 'wishlist_click',
      meta: { app_id: wishlistUrls.appId, path: 'steam', platform: 'web' },
    });
    void openExternal(wishlistUrls.steam);
    setTimeout(() => {
      // If Steam didn't take focus, open the web store as a fallback.
      if (!document.hasFocus()) return;
      trackMutation.mutate({
        type: 'wishlist_click',
        meta: { app_id: wishlistUrls.appId, path: 'https', platform: 'web', fallback: true },
      });
      void openExternal(wishlistUrls.web);
    }, 800);
  };

  const onDiscordClick = async () => {
    const url = discordInviteUrl || 'https://discord.com/';
    trackMutation.mutate({ type: 'discord_click', meta: { url } });
    await openExternal(url);
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-brand-600" />
            <h1 className="text-2xl font-extrabold text-slate-900">{lang === 'ko' ? '데모 런 (5분)' : 'Demo Run (5 min)'}</h1>
            <Badge variant="brand" className="ml-1">
              {lang === 'ko' ? 'Steam Demo' : 'Steam Demo'}
            </Badge>
          </div>
          <div className="text-sm text-slate-600 mt-1">
            {lang === 'ko'
              ? '프리셋 빌드로 1판 즉시 시뮬 → 리플레이/베스트 클립 → Creator Kit.zip → Beat This'
              : 'Pick a preset → instant sim → replay/best clip → Creator Kit.zip → Beat This'}
          </div>
        </div>
        <Button variant="secondary" onClick={() => navigate('/home')} type="button">
          {lang === 'ko' ? '홈' : 'Home'}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{lang === 'ko' ? '1) 프리셋 선택' : '1) Pick a preset'}</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {(presets ?? []).map((p) => (
            <button
              key={p.id}
              type="button"
              className={`text-left rounded-2xl border p-4 transition ${
                p.id === presetId ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:bg-slate-50'
              }`}
              onClick={() => setPresetId(p.id)}
            >
              <div className="font-extrabold text-slate-900">{p.title}</div>
              <div className="text-xs text-slate-600 mt-1">{p.subtitle}</div>
              <div className="mt-3 text-[11px] text-slate-500 font-mono">{p.blueprint_id}</div>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{lang === 'ko' ? '2) 데모 런 시작' : '2) Start the demo run'}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Button
            size="lg"
            onClick={async () => {
              setRun(null);
              setBestClipUrl(null);
              setBestClipError(null);
              setBestClipJobId(null);
              try {
                if (typeof sessionStorage !== 'undefined') {
                  sessionStorage.removeItem(DEMO_RUN_STORAGE_KEY);
                }
              } catch {
                // ignore
              }
              await trackMutation.mutateAsync({ type: 'demo_run_start', meta: { preset_id: presetId } });
              const out = await demoRunMutation.mutateAsync(presetId);
              setRun(out);
              try {
                if (typeof sessionStorage !== 'undefined') {
                  sessionStorage.setItem(DEMO_RUN_STORAGE_KEY, JSON.stringify(out));
                }
              } catch {
                // ignore
              }
              trackMutation.mutate({ type: 'demo_run_done', meta: { preset_id: presetId, match_id: out.match_id, replay_id: out.replay_id } });
            }}
            disabled={demoRunMutation.isPending}
            type="button"
          >
            {demoRunMutation.isPending ? (
              <>
                <Loader2 className="animate-spin mr-2" size={16} /> {lang === 'ko' ? '시뮬 중…' : 'Simulating…'}
              </>
            ) : (
              <>
                <PlayCircle className="mr-2" size={18} /> {lang === 'ko' ? 'Play Demo Run' : 'Play Demo Run'}
              </>
            )}
          </Button>

          {run ? (
            <>
              <Button
                variant="secondary"
                onClick={() => navigate(`/replay/${encodeURIComponent(run.match_id)}?t=0&end=12`)}
                type="button"
              >
                {lang === 'ko' ? '리플레이 보기' : 'Open Replay'} <ArrowRight className="ml-2" size={16} />
              </Button>
              <Button variant="secondary" onClick={() => window.open(run.share_url, '_blank')} type="button">
                {lang === 'ko' ? '공유 랜딩 열기' : 'Open Share Landing'}
              </Button>
            </>
          ) : null}

          <div className="text-xs text-slate-500">
            {selectedPreset ? (lang === 'ko' ? `선택됨: ${selectedPreset.title}` : `Selected: ${selectedPreset.title}`) : null}
          </div>
        </CardContent>
      </Card>

      {run ? (
        <Card>
          <CardHeader>
            <CardTitle>{lang === 'ko' ? '3) 베스트 클립 + Creator Pack' : '3) Best Clip + Creator Pack'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-xs text-slate-500 font-semibold uppercase">{lang === 'ko' ? '베스트 클립' : 'Best Clip'}</div>
                <div className="text-sm text-slate-600 mt-1">
                  {bestClipUrl ? (lang === 'ko' ? '완료' : 'Ready') : lang === 'ko' ? '생성 중…' : 'Generating…'}
                  {bestClipJobId ? <span className="ml-2 text-[11px] font-mono text-slate-400">{bestClipJobId}</span> : null}
                </div>
                {bestClipError ? <div className="mt-2 text-sm text-red-600">{bestClipError}</div> : null}
                {bestClipUrl ? (
                  <video
                    className="mt-3 w-full rounded-xl border border-slate-200 bg-black"
                    src={bestClipUrl}
                    controls
                    playsInline
                    preload="metadata"
                  />
                ) : (
                  <div className="mt-3 w-full aspect-[9/16] rounded-xl border border-dashed border-slate-300 bg-slate-50 flex items-center justify-center text-slate-500 text-sm">
                    {lang === 'ko' ? '렌더 완료 시 자동 표시' : 'Auto-shows when render completes'}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-xs text-slate-500 font-semibold uppercase">{lang === 'ko' ? 'Creator Kit.zip' : 'Creator Kit.zip'}</div>
                <div className="text-sm text-slate-600 mt-1">
                  {lang === 'ko'
                    ? 'MP4 + 썸네일 + 캡션 + QR (4개 파일)'
                    : 'MP4 + thumbnail + caption + QR (4 files)'}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {bestClipUrl ? (
                    <a
                      className="inline-flex"
                      href={run.kit_url}
                      download
                      onClick={(e) => {
                        trackMutation.mutate({ type: 'demo_kit_download', meta: { match_id: run.match_id, replay_id: run.replay_id } });
                        void e;
                      }}
                    >
                      <Button size="lg" type="button">
                        <Download className="mr-2" size={18} /> {lang === 'ko' ? 'Download Kit.zip' : 'Download Kit.zip'}
                      </Button>
                    </a>
                  ) : null}

                  <Button
                    size="lg"
                    variant="secondary"
                    onClick={() => {
                      trackMutation.mutate({ type: 'demo_beat_this_click', meta: { challenge_id: run.challenge_id, replay_id: run.replay_id } });
                      navigate(`/challenge/${encodeURIComponent(run.challenge_id)}`);
                    }}
                    type="button"
                  >
                    {lang === 'ko' ? 'Beat This' : 'Beat This'} <ArrowRight className="ml-2" size={16} />
                  </Button>
                </div>

                <div className="mt-4 pt-4 border-t border-slate-100">
                  <div className="text-xs text-slate-500 font-semibold uppercase">
                    {lang === 'ko' ? 'Wishlist / Community' : 'Wishlist / Community'}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button size="lg" onClick={onWishlistClick} disabled={!wishlistUrls} type="button">
                      <Heart className="mr-2" size={18} /> {lang === 'ko' ? 'Wishlist Now' : 'Wishlist Now'}
                    </Button>
                    <Button size="lg" variant="secondary" onClick={onDiscordClick} type="button">
                      <MessageCircle className="mr-2" size={18} /> {lang === 'ko' ? 'Join Discord' : 'Join Discord'}
                    </Button>
                  </div>
                  {!wishlistUrls ? (
                    <div className="mt-2 text-[11px] text-slate-500">
                      {lang === 'ko'
                        ? 'NEUROLEAGUE_STEAM_APP_ID를 설정하면 위시리스트 링크가 활성화됩니다.'
                        : 'Set NEUROLEAGUE_STEAM_APP_ID to enable the wishlist link.'}
                    </div>
                  ) : null}
                </div>
                <div className="mt-2 text-[11px] text-slate-500 font-mono break-all">{run.kit_url}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};
