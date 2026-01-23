import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { EyeOff, Flag, Heart, MessageCircle, Share2, Sparkles, Trophy, Wand2, Zap } from 'lucide-react';

import { Badge, Button } from '../components/ui';
import type { BlueprintOut, ClipEventResponse, ClipFeedItem, ClipFeedOut, Mode, QueueResponse, RepliesResponse } from '../api/types';
import { apiFetch } from '../lib/api';
import { getExperimentVariant, useExperiments } from '../lib/experiments';
import { readShareVariants } from '../lib/shareVariants';
import { TRANSLATIONS } from '../lib/translations';
import { appendUtmParams } from '../lib/utm';
import { useSettingsStore } from '../stores/settings';

type SlideState = {
  liked?: boolean;
  likes?: number;
  forkedBlueprintId?: string;
  pending?: 'fork' | 'rank' | 'like' | 'share' | null;
  error?: string | null;
};

type ClipShareUrlOut = {
  share_url_vertical: string;
  start_sec: number;
  end_sec: number;
  variant: string;
  captions_template_id: string | null;
  captions_version: string;
};

const clampIndex = (idx: number, total: number) => Math.max(0, Math.min(total - 1, idx));

export const ClipsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const lang = useSettingsStore((s) => s.language);
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);
  const t = useMemo(() => TRANSLATIONS[lang].common, [lang]);
  const nav = useMemo(() => TRANSLATIONS[lang].nav, [lang]);

  const { data: experiments } = useExperiments();
  const feedAlgo = useMemo(() => {
    const v = getExperimentVariant(experiments, 'clips_feed_algo', 'v2');
    return v === 'v3' ? 'v3' : 'v2';
  }, [experiments]);
  const shareCta = useMemo(() => {
    const v = getExperimentVariant(experiments, 'share_cta_copy', 'remix');
    return v === 'beat_this' ? 'beat_this' : 'remix';
  }, [experiments]);

  const [searchParams, setSearchParams] = useSearchParams();
  const initialMode = (searchParams.get('mode') as Mode | null) ?? '1v1';
  const initialSort = (searchParams.get('sort') as 'trending' | 'new' | null) ?? 'trending';
  const [mode, setMode] = useState<Mode>(initialMode === 'team' ? 'team' : '1v1');
  const [sort, setSort] = useState<'trending' | 'new'>(initialSort === 'new' ? 'new' : 'trending');

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    next.set('mode', mode);
    next.set('sort', sort);
    setSearchParams(next, { replace: true });
  }, [mode, sort, searchParams, setSearchParams]);

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isFetching,
  } = useInfiniteQuery({
    queryKey: ['clipsFeed', mode, sort, feedAlgo],
    queryFn: ({ pageParam }) => {
      const qp = new URLSearchParams();
      qp.set('mode', mode);
      qp.set('sort', sort);
      qp.set('algo', feedAlgo);
      qp.set('limit', '12');
      if (pageParam) qp.set('cursor', String(pageParam));
      return apiFetch<ClipFeedOut>(`/api/clips/feed?${qp.toString()}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    staleTime: 10_000,
  });

  const clips: ClipFeedItem[] = useMemo(() => (data?.pages ?? []).flatMap((p) => p.items ?? []), [data?.pages]);

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<{ user_id: string }>('/api/auth/me'),
    staleTime: 60_000,
  });

  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRefs = useRef<Array<HTMLVideoElement | null>>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const activeClip = useMemo(() => clips[activeIndex] ?? null, [activeIndex, clips]);
  const viewed = useRef<Set<string>>(new Set());
  const completed = useRef<Set<string>>(new Set());
  const [slideState, setSlideState] = useState<Record<string, SlideState>>({});
  const [quickRemixOpen, setQuickRemixOpen] = useState(false);
  const [repliesOpen, setRepliesOpen] = useState(false);
  const [repliesTab, setRepliesTab] = useState<'top' | 'recent'>('top');

  const { data: repliesData, isFetching: repliesFetching, error: repliesError } = useQuery({
    queryKey: ['clipReplies', activeClip?.replay_id, repliesTab],
    queryFn: () =>
      apiFetch<RepliesResponse>(
        `/api/clips/${encodeURIComponent(activeClip!.replay_id)}/replies?sort=${encodeURIComponent(repliesTab)}&limit=12`
      ),
    enabled: Boolean(repliesOpen && activeClip?.replay_id),
    staleTime: 10_000,
  });

  const trackEventMutation = useMutation({
    mutationFn: ({
      replayId,
      type,
      meta,
    }: {
      replayId: string;
      type: 'view' | 'like' | 'share' | 'fork_click' | 'open_ranked' | 'completion';
      meta?: Record<string, unknown>;
    }) =>
      apiFetch<ClipEventResponse>(`/api/clips/${encodeURIComponent(replayId)}/event`, {
        method: 'POST',
        body: JSON.stringify({ type, source: 'clips', meta: meta ?? {} }),
      }),
  });

  const ensureFork = async (item: ClipFeedItem): Promise<string> => {
    if (!item.blueprint_id) throw new Error('No blueprint attached to this clip');
    const existing = slideState[item.replay_id]?.forkedBlueprintId;
    if (existing) return existing;
    const forked = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(item.blueprint_id)}/fork`, {
      method: 'POST',
      body: JSON.stringify({
        name: `${item.blueprint_name ?? 'Build'} (Remix)`,
        source_replay_id: item.replay_id,
        note: 'clips_feed',
      }),
    });
    setSlideState((s) => ({ ...s, [item.replay_id]: { ...(s[item.replay_id] ?? {}), forkedBlueprintId: forked.id } }));
    return forked.id;
  };

  const remixMutation = useMutation({
    mutationFn: async (item: ClipFeedItem) => {
      await trackEventMutation.mutateAsync({ replayId: item.replay_id, type: 'fork_click' });
      const forkedId = await ensureFork(item);
      return forkedId;
    },
    onSuccess: (forkedId) => {
      navigate(`/forge/${encodeURIComponent(forkedId)}`);
    },
  });

  const openRankedMutation = useMutation({
    mutationFn: async (item: ClipFeedItem) => {
      await trackEventMutation.mutateAsync({ replayId: item.replay_id, type: 'open_ranked' });
      const forkedId = await ensureFork(item);
      await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(forkedId)}/submit`, { method: 'POST', body: JSON.stringify({}) });
      const queued = await apiFetch<QueueResponse>('/api/ranked/queue', {
        method: 'POST',
        body: JSON.stringify({ blueprint_id: forkedId, seed_set_count: 1, ...readShareVariants() }),
      });
      return { queued, forkedId };
    },
    onSuccess: async ({ queued }) => {
      await queryClient.invalidateQueries({ queryKey: ['matches', mode] });
      await queryClient.invalidateQueries({ queryKey: ['homeSummary'] });
      navigate(`/ranked?mode=${encodeURIComponent(mode)}&match_id=${encodeURIComponent(queued.match_id)}&auto=1`);
    },
  });

  useEffect(() => {
    if (!clips.length) return;
    const root = containerRef.current;
    if (!root) return;

    const slides = Array.from(root.querySelectorAll<HTMLElement>('[data-clip-index]'));
    const obs = new IntersectionObserver(
      (entries) => {
        const best = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => (b.intersectionRatio ?? 0) - (a.intersectionRatio ?? 0))[0];
        if (!best) return;
        const idx = Number((best.target as HTMLElement).dataset.clipIndex ?? '0');
        if (Number.isFinite(idx)) setActiveIndex(clampIndex(idx, clips.length));
      },
      { root, threshold: [0.55, 0.7, 0.85] }
    );

    for (const el of slides) obs.observe(el);
    return () => obs.disconnect();
  }, [clips.length]);

  useEffect(() => {
    const item = clips[activeIndex];
    if (!item) return;

    // fire view event once per session
    if (!viewed.current.has(item.replay_id)) {
      viewed.current.add(item.replay_id);
      trackEventMutation.mutate({ replayId: item.replay_id, type: 'view' });
    }

    // autoplay active video, pause others
    for (let i = 0; i < videoRefs.current.length; i++) {
      const v = videoRefs.current[i];
      if (!v) continue;
      if (i === activeIndex) {
        if (v.paused) {
          v.play().catch(() => {
            // autoplay might be blocked; stay muted and allow user to tap play.
          });
        }
      } else {
        if (!v.paused) v.pause();
      }
    }

    // prefetch more when near the end
    if (hasNextPage && activeIndex >= clips.length - 4 && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [activeIndex, clips, fetchNextPage, hasNextPage, isFetchingNextPage, trackEventMutation]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      e.preventDefault();
      const dir = e.key === 'ArrowDown' ? 1 : -1;
      const nextIdx = clampIndex(activeIndex + dir, clips.length);
      const root = containerRef.current;
      const target = root?.querySelector<HTMLElement>(`[data-clip-index="${nextIdx}"]`);
      target?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeIndex, clips.length, reduceMotion]);

  const likeMutation = useMutation({
    mutationFn: async (item: ClipFeedItem) => {
      const resp = await trackEventMutation.mutateAsync({ replayId: item.replay_id, type: 'like' });
      return resp;
    },
    onSuccess: (resp, item) => {
      setSlideState((s) => ({
        ...s,
        [item.replay_id]: {
          ...(s[item.replay_id] ?? {}),
          liked: resp.liked ?? undefined,
          likes: resp.likes ?? undefined,
        },
      }));
    },
  });

  const shareMutation = useMutation({
    mutationFn: async (item: ClipFeedItem) => {
      const minted = await apiFetch<ClipShareUrlOut>(
        `/api/clips/${encodeURIComponent(item.replay_id)}/share_url?orientation=vertical`
      );
      await trackEventMutation.mutateAsync({
        replayId: item.replay_id,
        type: 'share',
        meta: {
          clip_len_v1: minted.variant,
          captions_v2: minted.captions_template_id,
          start_sec: minted.start_sec,
          end_sec: minted.end_sec,
          replay_id: item.replay_id,
          captions_template_id: minted.captions_template_id,
          captions_version: minted.captions_version,
        },
      });
      const base = appendUtmParams(minted.share_url_vertical, { utm_source: 'clips_share', utm_medium: 'copy' });
      const ref = me?.user_id;
      const withRef = ref && !base.includes('ref=') ? `${base}${base.includes('?') ? '&' : '?'}ref=${encodeURIComponent(ref)}` : base;
      const url = `${window.location.origin}${withRef}`;
      try {
        await navigator.clipboard.writeText(url);
      } catch {
        // ignore clipboard failures
      }
      return url;
    },
  });

  const hideMutation = useMutation({
    mutationFn: async (item: ClipFeedItem) =>
      apiFetch<{ hidden: boolean }>(`/api/clips/${encodeURIComponent(item.replay_id)}/hide`, {
        method: 'POST',
        body: JSON.stringify({}),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['clipsFeed', mode, sort, feedAlgo] });
    },
  });

  const reportMutation = useMutation({
    mutationFn: async ({ target_type, target_id, reason }: { target_type: 'clip' | 'profile' | 'build'; target_id: string; reason: string }) =>
      apiFetch<{ report_id: string }>('/api/reports', {
        method: 'POST',
        body: JSON.stringify({ target_type, target_id, reason }),
      }),
  });

  const title = nav.clips ?? (lang === 'ko' ? '클립' : 'Clips');

  return (
    <div className="-mx-4 md:-mx-6 -mt-4 md:-mt-6">
      <div className="relative h-[calc(100vh-64px-96px)] md:h-[calc(100vh-64px-32px)] bg-black overflow-hidden">
        <div className="absolute top-0 left-0 right-0 z-20 p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="text-white font-extrabold tracking-tight">{title}</div>
            <Badge variant="neutral" className="bg-white/10 text-white border-transparent">
              {mode}
            </Badge>
            <Badge variant="neutral" className="bg-white/10 text-white border-transparent">
              {sort}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={mode === '1v1' ? 'secondary' : 'outline'}
              className={mode === '1v1' ? 'bg-white/10 text-white border-white/20' : 'bg-transparent text-white border-white/20'}
              onClick={() => setMode('1v1')}
              type="button"
            >
              1v1
            </Button>
            <Button
              size="sm"
              variant={mode === 'team' ? 'secondary' : 'outline'}
              className={mode === 'team' ? 'bg-white/10 text-white border-white/20' : 'bg-transparent text-white border-white/20'}
              onClick={() => setMode('team')}
              type="button"
            >
              Team
            </Button>
            <Button
              size="sm"
              variant={sort === 'trending' ? 'secondary' : 'outline'}
              className={sort === 'trending' ? 'bg-white/10 text-white border-white/20' : 'bg-transparent text-white border-white/20'}
              onClick={() => setSort('trending')}
              type="button"
            >
              Trending
            </Button>
            <Button
              size="sm"
              variant={sort === 'new' ? 'secondary' : 'outline'}
              className={sort === 'new' ? 'bg-white/10 text-white border-white/20' : 'bg-transparent text-white border-white/20'}
              onClick={() => setSort('new')}
              type="button"
            >
              New
            </Button>
          </div>
        </div>

        <div ref={containerRef} className="h-full overflow-y-scroll snap-y snap-mandatory">
          {clips.length === 0 ? (
            <div className="h-full flex items-center justify-center text-white/70">
              {isFetching ? 'Loading…' : 'No clips yet.'}
            </div>
          ) : (
            clips.map((item, idx) => {
              const local = slideState[item.replay_id] ?? {};
              const liked = local.liked ?? false;
              const likes = local.likes ?? item.stats.likes;
              const isActive = idx === activeIndex;
              const hasVideo = Boolean(item.vertical_mp4_url);

              return (
                <div
                  key={`${item.replay_id}:${idx}`}
                  data-clip-index={idx}
                  className="snap-start h-full relative flex items-center justify-center bg-black"
                >
                  {hasVideo ? (
                    <video
                      ref={(el) => {
                        videoRefs.current[idx] = el;
                      }}
                      src={item.vertical_mp4_url ?? undefined}
                      className="h-full w-full object-contain"
                      playsInline
                      muted
                      loop
                      preload="metadata"
                      controls={false}
                      aria-label="Clip video"
                      onTimeUpdate={(e) => {
                        if (!isActive) return;
                        if (completed.current.has(item.replay_id)) return;
                        const v = e.currentTarget;
                        const dur = v.duration;
                        if (!Number.isFinite(dur) || dur <= 0) return;
                        const ratio = v.currentTime / dur;
                        if (ratio < 0.8) return;
                        completed.current.add(item.replay_id);
                        trackEventMutation.mutate({ replayId: item.replay_id, type: 'completion' });
                      }}
                    />
                  ) : (
                    <img src={item.thumb_url} alt="Clip thumbnail" className="h-full w-full object-contain opacity-80" />
                  )}

                  <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-black/70 via-black/10 to-black/30" />

                  <div className="absolute bottom-0 left-0 right-0 z-10 p-4 flex items-end justify-between gap-6">
                    <div className="max-w-[70%] space-y-2">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => navigate(`/profile/${encodeURIComponent(item.author.user_id)}?mode=${encodeURIComponent(item.mode)}`)}
                          className="pointer-events-auto text-white font-bold hover:underline"
                        >
                          {item.author.display_name}
                        </button>
                        <Badge variant="neutral" className="bg-white/10 text-white border-transparent">
                          {item.mode}
                        </Badge>
                      </div>
                      <div className="text-white text-lg font-extrabold leading-tight">
                        {item.blueprint_name ?? 'Untitled Build'}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {(item.tags ?? []).slice(0, 4).map((tag) => (
                          <Badge
                            key={tag}
                            variant="neutral"
                            className="bg-white/10 text-white border-transparent text-[10px]"
                          >
                            {tag}
                          </Badge>
                        ))}
                      </div>
                      {item.best_clip_status !== 'ready' ? (
                        <div className="text-xs text-white/70">
                          {item.best_clip_status === 'rendering' ? 'Rendering best clip…' : 'Best clip not ready yet.'}
                        </div>
                      ) : null}
                      <div className="text-[11px] text-white/60 font-mono">
                        views {item.stats.views} · shares {item.stats.shares} · forks {item.stats.forks}
                      </div>
                    </div>

                    <div className="flex flex-col items-center gap-3 pb-2">
                      <Button
                        type="button"
                        size="icon"
                        variant={liked ? 'primary' : 'secondary'}
                        className="pointer-events-auto rounded-full"
                        onClick={() => likeMutation.mutate(item)}
                        aria-label="Like clip"
                      >
                        <Heart size={18} className={liked ? 'text-white' : ''} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">{likes}</div>

                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="pointer-events-auto rounded-full"
                        onClick={() => shareMutation.mutate(item)}
                        aria-label="Copy share link"
                      >
                        <Share2 size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">{item.stats.shares}</div>

                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="pointer-events-auto rounded-full"
                        onClick={() => hideMutation.mutate(item)}
                        aria-label="Hide clip"
                      >
                        <EyeOff size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">Hide</div>

                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="pointer-events-auto rounded-full"
                        onClick={() => {
                          const reason = window.prompt('Report reason', 'inappropriate') ?? '';
                          if (!reason.trim()) return;
                          reportMutation.mutate({ target_type: 'clip', target_id: item.replay_id, reason });
                        }}
                        aria-label="Report clip"
                      >
                        <Flag size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">Report</div>

                      <Button
                        type="button"
                        size="icon"
                        variant={shareCta === 'beat_this' ? 'primary' : 'secondary'}
                        className="pointer-events-auto rounded-full"
                        onClick={() => navigate(`/beat?replay_id=${encodeURIComponent(item.replay_id)}&src=clip_view`)}
                        aria-label="Beat This (challenge original)"
                      >
                        <Zap size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">Beat This</div>

                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="pointer-events-auto rounded-full"
                        onClick={() => setQuickRemixOpen(true)}
                        aria-label="Quick Remix presets"
                        disabled={!item.replay_id}
                      >
                        <Wand2 size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">Quick Remix</div>

                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="pointer-events-auto rounded-full"
                        onClick={() => {
                          setRepliesTab('top');
                          setRepliesOpen(true);
                        }}
                        aria-label="Replies (view reply chain)"
                      >
                        <MessageCircle size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">Replies</div>

                      <Button
                        type="button"
                        size="icon"
                        variant={shareCta === 'remix' ? 'primary' : 'secondary'}
                        className="pointer-events-auto rounded-full"
                        onClick={() => remixMutation.mutate(item)}
                        aria-label="Remix (fork build)"
                        disabled={!item.blueprint_id}
                      >
                        <Sparkles size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">Remix</div>

                      <Button
                        type="button"
                        size="icon"
                        variant="secondary"
                        className="pointer-events-auto rounded-full"
                        onClick={() => openRankedMutation.mutate(item)}
                        aria-label="Open ranked with remixed build"
                        disabled={!item.blueprint_id}
                      >
                        <Trophy size={18} />
                      </Button>
                      <div className="text-white/80 text-[11px] font-bold">{t.enterRanked}</div>
                    </div>
                  </div>

                  <div className="absolute right-4 top-20 z-10 pointer-events-none">
                    {isActive ? (
                      <Badge variant="neutral" className="bg-white/10 text-white border-transparent">
                        {hasVideo ? 'PLAYING' : 'THUMB'}
                      </Badge>
                    ) : null}
                  </div>

                  {idx === clips.length - 2 && hasNextPage ? (
                    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10">
                      <Badge variant="neutral" className="bg-white/10 text-white border-transparent">
                        Loading more…
                      </Badge>
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </div>

        <div className="absolute bottom-4 left-4 z-20 pointer-events-none flex items-center gap-2 text-white/60 text-[11px]">
          <Sparkles size={14} />
          <span>{lang === 'ko' ? '스크롤 또는 ↑/↓ 로 이동' : 'Scroll or use ↑/↓ to navigate'}</span>
        </div>
      </div>

      {quickRemixOpen && activeClip ? (
        <div
          className="fixed inset-0 z-[100] bg-black/60 flex items-center justify-center p-4"
          onClick={() => setQuickRemixOpen(false)}
        >
          <div
            className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <div className="font-bold text-slate-800">Quick Remix</div>
              <button
                type="button"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800"
                onClick={() => setQuickRemixOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="px-4 py-4 space-y-2">
              <div className="text-sm text-slate-600">
                Pick a preset to apply minimal tweaks to the original build, then start a “Beat This” challenge.
              </div>
              <div className="grid grid-cols-1 gap-2 pt-2">
                <Button
                  variant="primary"
                  onClick={() => {
                    setQuickRemixOpen(false);
                    navigate(
                      `/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view&qr=survivability`
                    );
                  }}
                >
                  Tankier (survivability)
                </Button>
                <Button
                  variant="primary"
                  onClick={() => {
                    setQuickRemixOpen(false);
                    navigate(`/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view&qr=damage`);
                  }}
                >
                  Melt Faster (damage)
                </Button>
                <Button
                  variant="primary"
                  onClick={() => {
                    setQuickRemixOpen(false);
                    navigate(`/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view&qr=counter`);
                  }}
                >
                  Counter-first (counter)
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setQuickRemixOpen(false);
                    navigate(`/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view`);
                  }}
                >
                  Just Beat This (no remix)
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {repliesOpen && activeClip ? (
        <div
          className="fixed inset-0 z-[100] bg-black/60 flex items-center justify-center p-4"
          onClick={() => setRepliesOpen(false)}
        >
          <div
            className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <div className="font-bold text-slate-800">Replies</div>
              <button
                type="button"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800"
                onClick={() => setRepliesOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="px-4 py-3 flex gap-2">
              <Button size="sm" variant={repliesTab === 'top' ? 'primary' : 'secondary'} onClick={() => setRepliesTab('top')}>
                Top Replies
              </Button>
              <Button
                size="sm"
                variant={repliesTab === 'recent' ? 'primary' : 'secondary'}
                onClick={() => setRepliesTab('recent')}
              >
                Recent
              </Button>
            </div>
            <div className="px-4 pb-4 max-h-[70vh] overflow-auto">
              {repliesFetching ? <div className="text-sm text-slate-500 py-3">Loading…</div> : null}
              {repliesError ? (
                <div className="text-sm text-red-600 py-3 break-words">{String(repliesError)}</div>
              ) : null}
              {repliesData?.items?.length ? (
                <div className="space-y-2">
                  {repliesData.items.map((r) => (
                    <button
                      key={r.reply_replay_id}
                      type="button"
                      className="w-full text-left bg-white border border-slate-200 rounded-2xl overflow-hidden hover:bg-slate-50 transition-colors"
                      onClick={() => {
                        setRepliesOpen(false);
                        navigate(`/replay/${encodeURIComponent(r.match_id)}?reply_to=${encodeURIComponent(activeClip.replay_id)}`);
                      }}
                    >
                      <div className="flex gap-3 p-3">
                        <img
                          src={`/s/clip/${encodeURIComponent(r.reply_replay_id)}/thumb.png`}
                          alt="Reply thumbnail"
                          className="w-20 h-14 rounded-xl border border-slate-200 object-cover bg-slate-100"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                r.outcome === 'win'
                                  ? 'bg-green-100 text-green-700'
                                  : r.outcome === 'loss'
                                  ? 'bg-red-100 text-red-700'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {r.outcome.toUpperCase()}
                            </span>
                            <div className="text-sm font-semibold text-slate-800 truncate">
                              {r.challenger_display_name ?? 'Guest'}
                            </div>
                          </div>
                          <div className="text-xs text-slate-600 mt-1 truncate">{r.blueprint_name ?? 'Starter Build'}</div>
                          <div className="text-[11px] text-slate-500 mt-2">
                            👍 {r.reactions?.up ?? 0} · 😂 {r.reactions?.lol ?? 0} · 🤯 {r.reactions?.wow ?? 0} · shares{' '}
                            {r.shares ?? 0}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            fork depth {r.lineage?.fork_depth ?? 0}
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : !repliesFetching && !repliesError ? (
                <div className="text-sm text-slate-500 py-3">No replies yet.</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
