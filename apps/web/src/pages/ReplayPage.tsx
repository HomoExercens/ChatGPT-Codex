import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Bookmark,
  Eye,
  EyeOff,
  Flame,
  GitFork,
  Maximize2,
  Pause,
  Play,
  Share2,
  SkipBack,
  SkipForward,
  Skull,
  Sparkles,
  Swords,
} from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { BattleViewport } from '../components/replay/BattleViewport';
import type { BlueprintOut, MatchDetail, ModifiersMeta, QueueResponse, Replay } from '../api/types';
import { apiFetch, apiFetchBlob } from '../lib/api';
import { readShareVariants } from '../lib/shareVariants';
import { TRANSLATIONS } from '../lib/translations';
import { appendUtmParams } from '../lib/utm';
import { useSettingsStore } from '../stores/settings';

const RECOMMENDED_STARTER_BUILDS: Record<'1v1' | 'team', Array<{ id: string; label: string }>> = {
  '1v1': [
    { id: 'bp_demo_1v1', label: 'Mech Counter' },
    { id: 'bp_demo_storm_1v1', label: 'Storm Control' },
    { id: 'bp_demo_vine_1v1', label: 'Vine Sustain' },
  ],
  team: [
    { id: 'bp_demo_team_mechline', label: 'Mechline' },
    { id: 'bp_demo_team_mysticcircle', label: 'Mystic Circle' },
    { id: 'bp_demo_team_beastpack', label: 'Beast Pack' },
  ],
};

export const ReplayPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);
  const t = useMemo(() => TRANSLATIONS[lang].common, [lang]);

  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const [tick, setTick] = useState(0);
  const [showOverlay, setShowOverlay] = useState(true);
  const [clipStartTick, setClipStartTick] = useState<number | null>(null);
  const [clipEndTick, setClipEndTick] = useState<number | null>(null);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [webmUrl, setWebmUrl] = useState<string | null>(null);
  const [gifUrl, setGifUrl] = useState<string | null>(null);
  const [clipGenStatus, setClipGenStatus] = useState<'idle' | 'thumb' | 'webm' | 'gif'>('idle');
  const [clipGenError, setClipGenError] = useState<string | null>(null);
  const [bestMp4Url, setBestMp4Url] = useState<string | null>(null);
  const [challengeLink, setChallengeLink] = useState<string | null>(null);
  const [challengeError, setChallengeError] = useState<string | null>(null);

  const { data: match } = useQuery({
    queryKey: ['match', id],
    queryFn: () => apiFetch<MatchDetail>(`/api/matches/${id}`),
    enabled: Boolean(id),
  });

  const { data: replay } = useQuery({
    queryKey: ['replay', id],
    queryFn: () => apiFetch<Replay>(`/api/matches/${id}/replay`),
    enabled: Boolean(id),
  });

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<{ user_id: string; is_guest: boolean }>('/api/auth/me'),
    staleTime: 60_000,
  });

  const durationTicks = replay?.end_summary.duration_ticks ?? 0;
  const highlights = (replay?.highlights ?? match?.highlights ?? []).slice(0, 3);
  const portalId = replay?.header.portal_id ?? match?.portal_id ?? null;
  const augA = (replay?.header.augments_a ?? match?.augments_a ?? []) as Array<{ round: number; augment_id: string }>;
  const augB = (replay?.header.augments_b ?? match?.augments_b ?? []) as Array<{ round: number; augment_id: string }>;

  const { data: modifiersMeta } = useQuery({
    queryKey: ['metaModifiers'],
    queryFn: () => apiFetch<ModifiersMeta>('/api/meta/modifiers'),
    staleTime: 60 * 60 * 1000,
  });

  type BestClipOut = {
    match_id: string;
    replay_id: string;
    start_tick: number;
    end_tick: number;
    start_sec: number;
    end_sec: number;
    title: string;
    summary: string;
    share_url: string;
    share_url_vertical: string;
    assets: Array<{
      kind: 'thumbnail' | 'vertical_mp4';
      cache_key: string;
      status: 'missing' | 'queued' | 'running' | 'done' | 'failed';
      job_id?: string | null;
      error_message?: string | null;
    }>;
  };

  type ClipShareUrlOut = {
    share_url_vertical: string;
    start_sec: number;
    end_sec: number;
    variant: string;
    captions_template_id: string | null;
    captions_version: string;
  };

  const { data: bestClip } = useQuery({
    queryKey: ['bestClip', id, match?.replay_id],
    queryFn: () => apiFetch<BestClipOut>(`/api/matches/${id}/best_clip`),
    enabled: Boolean(id && match?.replay_id),
  });

  const portalName = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of modifiersMeta?.portals ?? []) map.set(p.id, p.name);
    return (id?: string | null) => (id ? map.get(id) ?? id : null);
  }, [modifiersMeta?.portals]);

  const augmentName = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of modifiersMeta?.augments ?? []) map.set(a.id, a.name);
    return (id?: string | null) => (id ? map.get(id) ?? id : null);
  }, [modifiersMeta?.augments]);

  const formatClock = (ticks: number) => {
    const totalSeconds = Math.floor(ticks / 20);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };

  useEffect(() => {
    if (!isPlaying) return;
    const handle = window.setInterval(() => {
      setTick((prev) => {
        const playUntil = clipEndTick ?? durationTicks;
        const next = Math.min(playUntil, prev + speed);
        if (next >= playUntil) setIsPlaying(false);
        return next;
      });
    }, 50);
    return () => window.clearInterval(handle);
  }, [clipEndTick, durationTicks, isPlaying, speed]);

  useEffect(() => {
    setTick(0);
    setIsPlaying(false);
    setClipStartTick(null);
    setClipEndTick(null);
    setClipGenStatus('idle');
    setClipGenError(null);
    setChallengeLink(null);
    setChallengeError(null);
    setBestMp4Url((u) => {
      if (u) URL.revokeObjectURL(u);
      return null;
    });
    setThumbUrl((u) => {
      if (u) URL.revokeObjectURL(u);
      return null;
    });
    setWebmUrl((u) => {
      if (u) URL.revokeObjectURL(u);
      return null;
    });
    setGifUrl((u) => {
      if (u) URL.revokeObjectURL(u);
      return null;
    });
  }, [id]);

  useEffect(() => {
    return () => {
      if (bestMp4Url) URL.revokeObjectURL(bestMp4Url);
      if (thumbUrl) URL.revokeObjectURL(thumbUrl);
      if (webmUrl) URL.revokeObjectURL(webmUrl);
      if (gifUrl) URL.revokeObjectURL(gifUrl);
    };
  }, [bestMp4Url, gifUrl, thumbUrl, webmUrl]);

  useEffect(() => {
    if (!replay || durationTicks <= 0) return;
    const tParam = searchParams.get('t');
    const endParam = searchParams.get('end');

    const tSeconds = tParam ? Number(tParam) : NaN;
    if (Number.isFinite(tSeconds)) {
      const tTicks = Math.max(0, Math.min(durationTicks, Math.round(tSeconds * 20)));
      setTick(tTicks);
      setClipStartTick(tTicks);
    }

    const endSeconds = endParam ? Number(endParam) : NaN;
    if (Number.isFinite(endSeconds)) {
      const endTicks = Math.max(0, Math.min(durationTicks, Math.round(endSeconds * 20)));
      setClipEndTick(endTicks);
    }
  }, [durationTicks, replay?.digest, searchParams]);

  type RenderJobOut = {
    id: string;
    kind: string;
    status: 'queued' | 'running' | 'done' | 'failed';
    progress: number;
    cache_key: string;
    artifact_url: string | null;
    error_message: string | null;
    params: Record<string, unknown>;
  };

  const waitForRenderJob = async (jobId: string, timeoutMs = 60_000): Promise<RenderJobOut> => {
    const started = Date.now();
    while (true) {
      const job = await apiFetch<RenderJobOut>(`/api/render_jobs/${jobId}`);
      if (job.status === 'done') return job;
      if (job.status === 'failed') throw new Error(job.error_message || 'Render failed');
      if (Date.now() - started > timeoutMs) throw new Error('Render timed out');
      await new Promise((r) => window.setTimeout(r, 2000));
    }
  };

  const bookmarkMutation = useMutation({
    mutationFn: async () => {
      if (!match?.replay_id) throw new Error('Replay not ready');
      const label = window.prompt('Bookmark label', 'Bookmark') || 'Bookmark';
      return apiFetch(`/api/replays/${match.replay_id}/bookmark`, {
        method: 'POST',
        body: JSON.stringify({ t: tick, label }),
      });
    },
  });

  const sharecardMutation = useMutation({
    mutationFn: async () => {
      if (!match?.replay_id) throw new Error('Replay not ready');
      const created = await apiFetch<{ job_id: string }>(`/api/matches/${match.id}/sharecard_jobs`, {
        method: 'POST',
        body: JSON.stringify({ theme: 'dark', locale: lang }),
      });
      const job = await waitForRenderJob(created.job_id, 180_000);
      if (!job.artifact_url) throw new Error('Sharecard not ready');
      const blob = await apiFetchBlob(job.artifact_url);
      const url = URL.createObjectURL(blob);
      return { url, filename: `neuroleague_sharecard_${match.id}.png` };
    },
    onSuccess: ({ url, filename }) => {
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.rel = 'noopener';
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    },
  });

  const remixMutation = useMutation({
    mutationFn: async () => {
      const blueprintId = match?.blueprint_a_id;
      if (!blueprintId) throw new Error('No blueprint attached to this replay');
      const sourceReplayId = match?.replay_id ?? null;

      try {
        await apiFetch('/api/events/track', {
          method: 'POST',
          body: JSON.stringify({
            type: 'fork_click',
            source: 'clip_view',
            ref: me?.user_id ?? null,
            utm: {},
            meta: { match_id: match?.id, replay_id: sourceReplayId, blueprint_id: blueprintId },
          }),
        });
      } catch {
        // ignore
      }

      const forked = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(blueprintId)}/fork`, {
        method: 'POST',
        body: JSON.stringify({
          name: 'Remix',
          source_replay_id: sourceReplayId,
          source: 'clip_view',
          note: 'remix:clip_view',
          auto_submit: false,
        }),
      });
      return forked.id;
    },
    onSuccess: (forkedId) => {
      navigate(`/forge/${encodeURIComponent(forkedId)}`);
    },
  });

  const bestClipMutation = useMutation({
    mutationFn: async () => {
      if (!id) throw new Error('Match not found');
      const created = await apiFetch<{ vertical_mp4: { job_id: string } }>(`/api/matches/${id}/best_clip_jobs`, {
        method: 'POST',
      });
      const job = await waitForRenderJob(created.vertical_mp4.job_id, 180_000);
      if (!job.artifact_url) throw new Error('Best clip not ready');
      const blob = await apiFetchBlob(job.artifact_url);
      return URL.createObjectURL(blob);
    },
    onSuccess: (url) => {
      setBestMp4Url((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    },
  });

  const starterMode: '1v1' | 'team' = match?.mode === 'team' ? 'team' : '1v1';
  const starterRankedMutation = useMutation({
    mutationFn: async (starter: { id: string; label: string }) => {
      const forked = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(starter.id)}/fork`, {
        method: 'POST',
        body: JSON.stringify({ name: `${starter.label} (Starter)` }),
      });
      const submitted = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(forked.id)}/submit`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      const queued = await apiFetch<QueueResponse>('/api/ranked/queue', {
        method: 'POST',
        body: JSON.stringify({ blueprint_id: submitted.id, seed_set_count: 1, ...readShareVariants() }),
      });
      return queued;
    },
    onSuccess: (queued) => {
      navigate(`/ranked?mode=${encodeURIComponent(starterMode)}&match_id=${encodeURIComponent(queued.match_id)}&auto=1`);
    },
  });

  const stats = useMemo(() => {
    if (!replay) return null;
    let damageA = 0;
    let damageB = 0;
    let healsA = 0;
    let healsB = 0;
    let deathsA = 0;
    let deathsB = 0;
    const synergyA = new Set<string>();
    const synergyB = new Set<string>();

    for (const e of replay.timeline_events) {
      if (e.type === 'DAMAGE') {
        const source = String(e.payload?.source ?? '');
        const amount = Number(e.payload?.amount ?? 0);
        if (source.startsWith('A')) damageA += amount;
        if (source.startsWith('B')) damageB += amount;
      }
      if (e.type === 'HEAL') {
        const source = String(e.payload?.source ?? '');
        const amount = Number(e.payload?.amount ?? 0);
        if (source.startsWith('A')) healsA += amount;
        if (source.startsWith('B')) healsB += amount;
      }
      if (e.type === 'DEATH') {
        const unit = String(e.payload?.unit ?? '');
        if (unit.startsWith('A')) deathsA += 1;
        if (unit.startsWith('B')) deathsB += 1;
      }
      if (e.type === 'SYNERGY_TRIGGER') {
        const team = String(e.payload?.team ?? '');
        const tag = String(e.payload?.tag ?? '');
        if (team === 'A' && tag) synergyA.add(tag);
        if (team === 'B' && tag) synergyB.add(tag);
      }
    }

    return {
      damageA,
      damageB,
      healsA,
      healsB,
      deathsA,
      deathsB,
      synergyA: Array.from(synergyA),
      synergyB: Array.from(synergyB),
    };
  }, [replay]);

  const insights = useMemo(() => {
    if (!replay || !stats) return [];
    const winner = replay.end_summary.winner;
    const endedByTimeout = replay.end_summary.duration_ticks >= 60 * 20;
    const outcome =
      winner === 'A'
        ? lang === 'ko'
          ? `${t.replayYou} ${t.victory}`
          : `${t.replayYou} ${t.victory}`
        : winner === 'B'
          ? lang === 'ko'
            ? `${t.replayYou} ${t.defeat}`
            : `${t.replayYou} ${t.defeat}`
          : lang === 'ko'
            ? '무승부'
            : 'Draw';

    const finish = endedByTimeout ? (lang === 'ko' ? '시간 종료' : 'Timeout') : lang === 'ko' ? '전멸' : 'Elimination';
    const top = highlights[0];
    const pivot = top ? `${top.title} (${formatClock(top.start_t)}–${formatClock(top.end_t)})` : lang === 'ko' ? '전환점 없음' : 'No pivot highlight';

    const line1 = lang === 'ko' ? `결과: ${outcome} · ${finish}` : `Outcome: ${outcome} · ${finish}`;
    const line2 =
      lang === 'ko'
        ? `피해량: ${t.replayYou} ${stats.damageA} vs ${t.replayOpponent} ${stats.damageB} · 처치: ${stats.deathsB} / ${stats.deathsA}`
        : `Damage: ${t.replayYou} ${stats.damageA} vs ${t.replayOpponent} ${stats.damageB} · Kills: ${stats.deathsB} / ${stats.deathsA}`;
    const line3 = lang === 'ko' ? `핵심 구간: ${pivot}` : `Turning point: ${pivot}`;
    return [line1, line2, line3];
  }, [formatClock, highlights, lang, replay, stats, t.defeat, t.replayOpponent, t.replayYou, t.victory]);

  const highlightColor = (h: MatchDetail['highlights'][number]) => {
    const kind = h.tags?.find((tag) => tag.startsWith('type:')) ?? '';
    if (kind === 'type:death') return { dot: 'bg-red-500', bar: 'bg-red-400/60' };
    if (kind === 'type:synergy') return { dot: 'bg-purple-500', bar: 'bg-purple-400/60' };
    if (kind === 'type:damage_spike') return { dot: 'bg-amber-500', bar: 'bg-amber-400/60' };
    if (kind === 'type:hp_swing') return { dot: 'bg-blue-500', bar: 'bg-blue-400/60' };
    return { dot: 'bg-brand-600', bar: 'bg-brand-400/60' };
  };

  const markers = useMemo(() => {
    if (!replay || durationTicks <= 0) return [];
    const points: Array<{ t: number; color: string; title: string }> = [];
    for (const h of highlights) {
      points.push({
        t: h.start_t,
        color: highlightColor(h).dot,
        title: `#${h.rank} ${h.title}`,
      });
    }
    return points;
  }, [durationTicks, highlights, replay]);

  const highlightRanges = useMemo(() => {
    if (durationTicks <= 0) return [];
    return highlights.map((h) => {
      const left = (h.start_t / durationTicks) * 100;
      const width = (Math.max(1, h.end_t - h.start_t) / durationTicks) * 100;
      return { h, left, width, color: highlightColor(h).bar };
    });
  }, [durationTicks, highlights]);

  const windowEvents = useMemo(() => {
    if (!replay) return [];
    const start = Math.max(0, tick - 30);
    const end = Math.min(durationTicks, tick + 30);
    return replay.timeline_events.filter((e) => e.t >= start && e.t <= end).slice(-20);
  }, [durationTicks, replay, tick]);

  const activeHighlight = useMemo(() => {
    return highlights.find((h) => tick >= h.start_t && tick <= h.end_t) ?? null;
  }, [highlights, tick]);

  const highlightCaption = useMemo(() => {
    if (!activeHighlight) return null;
    const kind = activeHighlight.tags?.find((tag) => tag.startsWith('type:')) ?? '';
    const synergy = activeHighlight.tags?.find((tag) => tag.startsWith('synergy:'))?.slice('synergy:'.length);
    const lead = activeHighlight.tags?.find((tag) => tag.startsWith('lead:'))?.slice('lead:'.length);
    const team = activeHighlight.tags?.find((tag) => tag.startsWith('team:'))?.slice('team:'.length);

    const who =
      (team ?? lead) === 'a' ? t.replayYou : (team ?? lead) === 'b' ? t.replayOpponent : lang === 'ko' ? '양팀' : 'Both';

    if (kind === 'type:death') return lang === 'ko' ? `전환점: ${who} 처치 발생` : `Turning point: ${who} elimination`;
    if (kind === 'type:synergy')
      return lang === 'ko'
        ? `전환점: ${who} 시너지 발동${synergy ? ` · ${synergy}` : ''}`
        : `Turning point: ${who} synergy online${synergy ? ` · ${synergy}` : ''}`;
    if (kind === 'type:damage_spike') return lang === 'ko' ? `전환점: 폭딜 타이밍 (${who})` : `Turning point: damage spike (${who})`;
    if (kind === 'type:hp_swing') return lang === 'ko' ? `전환점: 역전 교환 (${who})` : `Turning point: HP swing (${who})`;
    return activeHighlight.title;
  }, [activeHighlight, lang, t.replayOpponent, t.replayYou]);

  const withReferral = (url: string) => {
    const ref = match?.user_a;
    if (!ref) return url;
    if (!url.startsWith('/s/')) return url;
    if (url.includes('ref=')) return url;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}ref=${encodeURIComponent(ref)}`;
  };

  const copyClipLink = async (kind: 'share' | 'app') => {
    if (!id) return;
    let startTick = clipStartTick ?? tick;
    let endTick = clipEndTick;
    if (endTick != null && endTick < startTick) {
      [startTick, endTick] = [endTick, startTick];
    }

    const next = new URLSearchParams(searchParams);
    next.set('t', (startTick / 20).toFixed(1));
    if (endTick != null) next.set('end', (endTick / 20).toFixed(1));
    else next.delete('end');

    setSearchParams(next, { replace: true });

    const appUrl = `${window.location.origin}/replay/${id}?${next.toString()}`;
    const shareParams = new URLSearchParams();
    shareParams.set('start', (startTick / 20).toFixed(1));
    if (endTick != null) shareParams.set('end', (endTick / 20).toFixed(1));
    if (kind === 'share' && match?.user_a) shareParams.set('ref', match.user_a);
    const shareUrl = match?.replay_id
      ? `${window.location.origin}/s/clip/${match.replay_id}?${shareParams.toString()}`
      : appUrl;
    const url = kind === 'share' ? shareUrl : appUrl;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      window.prompt('Copy link', url);
    }
  };

  const copyDiscordText = async () => {
    if (!id) return;
    let startTick = clipStartTick ?? tick;
    let endTick = clipEndTick;
    if (endTick != null && endTick < startTick) {
      [startTick, endTick] = [endTick, startTick];
    }
    const shareParams = new URLSearchParams();
    shareParams.set('start', (startTick / 20).toFixed(1));
    if (endTick != null) shareParams.set('end', (endTick / 20).toFixed(1));
    if (match?.user_a) shareParams.set('ref', match.user_a);
    const shareUrl = match?.replay_id
      ? `${window.location.origin}/s/clip/${match.replay_id}?${shareParams.toString()}`
      : `${window.location.origin}/replay/${id}`;
    const text =
      lang === 'ko'
        ? `이 장면 이겨봐: ${shareUrl}`
        : `Beat this clip: ${shareUrl}`;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      window.prompt('Copy', text);
    }
  };

  const clipRange = useMemo(() => {
    const startTick = clipStartTick ?? tick;
    const defaultEnd = Math.min(durationTicks, startTick + 60); // 3s default
    const endTick = clipEndTick ?? defaultEnd;
    const s = Math.max(0, Math.min(durationTicks, startTick));
    const e = Math.max(0, Math.min(durationTicks, endTick));
    return e >= s ? { startTick: s, endTick: e } : { startTick: e, endTick: s };
  }, [clipEndTick, clipStartTick, durationTicks, tick]);

  const clipEndpoints = useMemo(() => {
    if (!match?.replay_id) return null;
    const start = (clipRange.startTick / 20).toFixed(1);
    const end = (clipRange.endTick / 20).toFixed(1);
    const base = `/api/replays/${match.replay_id}`;
    return {
      shareThumb: `/s/clip/${match.replay_id}/thumb.png?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
      webm: `${base}/clip?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=webm&fps=12&scale=1&theme=dark&async=0`,
      gif: `${base}/clip?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=gif&fps=12&scale=1&theme=dark&async=0`,
    };
  }, [clipRange.endTick, clipRange.startTick, match?.replay_id]);

  const replyToReplayId = useMemo(() => {
    const fromMatch = match?.challenge?.target_replay_id ?? null;
    const fromQuery = (searchParams.get('reply_to') || '').trim() || null;
    return fromMatch || fromQuery;
  }, [match?.challenge?.target_replay_id, searchParams]);

  const isReplyClip = Boolean(match?.queue_type === 'challenge' && replyToReplayId);

  const beatThisMutation = useMutation({
    mutationFn: async () => {
      if (!match?.replay_id) throw new Error('Replay not ready');
      setChallengeError(null);
      const start = Number.parseFloat((clipRange.startTick / 20).toFixed(1));
      const end = Number.parseFloat((clipRange.endTick / 20).toFixed(1));
      const created = await apiFetch<{ challenge_id: string; share_url: string }>('/api/challenges', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'clip',
          target_replay_id: match.replay_id,
          start,
          end,
        }),
      });

      const url = `${window.location.origin}${withReferral(created.share_url)}`;
      try {
        await navigator.clipboard.writeText(url);
      } catch {
        window.prompt('Copy link', url);
      }
      return url;
    },
    onSuccess: (url) => {
      setChallengeLink(url);
    },
    onError: (e) => {
      setChallengeError(e instanceof Error ? e.message : String(e));
    },
  });

  const generateThumbnail = async () => {
    if (!match?.replay_id) return;
    setClipGenError(null);
    setClipGenStatus('thumb');
    try {
      const created = await apiFetch<{ job_id: string }>(`/api/replays/${match.replay_id}/thumbnail_jobs`, {
        method: 'POST',
        body: JSON.stringify({
          start: clipRange.startTick / 20,
          end: clipRange.endTick / 20,
          scale: 1,
          theme: 'dark',
        }),
      });
      const job = await waitForRenderJob(created.job_id, 60_000);
      if (!job.artifact_url) throw new Error('Thumbnail not ready');
      const blob = await apiFetchBlob(job.artifact_url);
      setThumbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
    } catch (e) {
      setClipGenError(String(e));
    } finally {
      setClipGenStatus('idle');
    }
  };

  const exportClip = async (format: 'webm' | 'gif') => {
    if (!match?.replay_id) return;
    setClipGenError(null);
    setClipGenStatus(format);
    try {
      const created = await apiFetch<{ job_id: string }>(`/api/replays/${match.replay_id}/clip_jobs`, {
        method: 'POST',
        body: JSON.stringify({
          start: clipRange.startTick / 20,
          end: clipRange.endTick / 20,
          format,
          fps: 12,
          scale: 1,
          theme: 'dark',
        }),
      });
      const job = await waitForRenderJob(created.job_id, 180_000);
      if (!job.artifact_url) throw new Error('Clip not ready');
      const blob = await apiFetchBlob(job.artifact_url);
      const url = URL.createObjectURL(blob);
      if (format === 'webm') {
        setWebmUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      } else {
        setGifUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      }
    } catch (e) {
      setClipGenError(String(e));
    } finally {
      setClipGenStatus('idle');
    }
  };

  const copyEndpointLink = async (url: string) => {
    const full = `${window.location.origin}${url}`;
    try {
      await navigator.clipboard.writeText(full);
    } catch {
      window.prompt('Copy link', full);
    }
  };

  const copyBestClipLink = async () => {
    if (!match?.replay_id) return;
    const minted = await apiFetch<ClipShareUrlOut>(
      `/api/clips/${encodeURIComponent(match.replay_id)}/share_url?orientation=vertical`
    );
    await apiFetch(`/api/clips/${encodeURIComponent(match.replay_id)}/event`, {
      method: 'POST',
      body: JSON.stringify({
        type: 'share',
        source: 'replay',
        meta: {
          clip_len_v1: minted.variant,
          captions_v2: minted.captions_template_id,
          start_sec: minted.start_sec,
          end_sec: minted.end_sec,
          replay_id: match.replay_id,
          captions_template_id: minted.captions_template_id,
          captions_version: minted.captions_version,
        },
      }),
    });
    const url = appendUtmParams(withReferral(minted.share_url_vertical), {
      utm_source: 'replay_share',
      utm_medium: 'copy',
    });
    await copyEndpointLink(url);
  };

  const copyReplyClipLink = async () => {
    if (!match?.replay_id) return;
    const parent = replyToReplayId;
    const minted = await apiFetch<ClipShareUrlOut>(
      `/api/clips/${encodeURIComponent(match.replay_id)}/share_url?orientation=vertical`
    );

    // Keep clip stats/share counts.
    await apiFetch(`/api/clips/${encodeURIComponent(match.replay_id)}/event`, {
      method: 'POST',
      body: JSON.stringify({
        type: 'share',
        source: 'reply_clip',
        meta: {
          clip_len_v1: minted.variant,
          captions_v2: minted.captions_template_id,
          start_sec: minted.start_sec,
          end_sec: minted.end_sec,
          replay_id: match.replay_id,
          captions_template_id: minted.captions_template_id,
          captions_version: minted.captions_version,
          parent_replay_id: parent,
        },
      }),
    });

    // Remix v2 signal (best-effort).
    try {
      await apiFetch('/api/events/track', {
        method: 'POST',
        body: JSON.stringify({
          type: 'reply_clip_shared',
          source: 'replay',
          meta: {
            match_id: id,
            reply_replay_id: match.replay_id,
            parent_replay_id: parent,
            replay_id: parent,
            challenge_id: match.challenge?.challenge_id ?? null,
          },
        }),
      });
    } catch {
      // ignore
    }

    const url = appendUtmParams(withReferral(minted.share_url_vertical), {
      utm_source: 'reply_clip_share',
      utm_medium: 'copy',
    });
    await copyEndpointLink(url);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-9 flex flex-col gap-4 min-h-[calc(100vh-140px)]">
        <div className="flex justify-between items-center bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-6">
            <div className="flex flex-col items-center">
              <span className="font-bold text-xl text-blue-600">{t.replayYou}</span>
              <Badge variant="info">Blueprint A</Badge>
            </div>
            <div className="text-2xl font-bold text-slate-300">VS</div>
            <div className="flex flex-col items-center">
              <span className="font-bold text-xl text-red-500">{t.replayOpponent}</span>
              <Badge variant="error">Blueprint B</Badge>
            </div>
            {match?.mode ? (
              <Badge variant="neutral">{match.mode === 'team' ? 'Team (3v3)' : '1v1'}</Badge>
            ) : null}
            {portalId ? <Badge variant="neutral">{portalName(portalId) ?? portalId}</Badge> : null}
            {match?.opponent_display_name ? (
              <div className="hidden md:flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-700 truncate max-w-[180px]">
                    {match.opponent_display_name}
                  </span>
                  <Badge variant={match.opponent_type === 'human' ? 'info' : 'neutral'}>
                    {match.opponent_type.toUpperCase()}
                  </Badge>
                  {match.opponent_type === 'human' && match.opponent_elo != null ? (
                    <span className="text-[10px] text-slate-400 font-mono">Elo {match.opponent_elo}</span>
                  ) : null}
                </div>
                {match.matchmaking_reason ? (
                  <div className="text-[10px] text-slate-400">{match.matchmaking_reason}</div>
                ) : null}
              </div>
            ) : null}
            <span className="hidden md:inline text-xs text-slate-400 font-mono">match_id: {id}</span>
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowOverlay((v) => !v)}
              aria-pressed={showOverlay}
            >
              {showOverlay ? <EyeOff size={16} className="mr-2" /> : <Eye size={16} className="mr-2" />} {t.overlay}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => remixMutation.mutate()}
              disabled={!match?.blueprint_a_id || remixMutation.isPending}
              isLoading={remixMutation.isPending}
            >
              <GitFork size={16} className="mr-2" /> {lang === 'ko' ? '리믹스' : 'Remix'}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => sharecardMutation.mutate()}
              disabled={!match?.replay_id || sharecardMutation.isPending}
              isLoading={sharecardMutation.isPending}
            >
              <Share2 size={16} className="mr-2" /> {t.share}
            </Button>
            <Button variant="ghost" size="icon" aria-label="Fullscreen">
              <Maximize2 size={18} />
            </Button>
          </div>
        </div>

        {portalId || augA.length || augB.length ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Portal & Augments</span>
                {portalId ? <Badge variant="neutral">{portalName(portalId) ?? portalId}</Badge> : <Badge variant="neutral">Legacy</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">{t.replayYou}</div>
                <div className="flex flex-wrap gap-1">
                  {augA.length ? (
                    augA.map((a) => (
                      <Badge key={`A-${a.round}-${a.augment_id}`} variant="info">
                        {augmentName(a.augment_id) ?? a.augment_id}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-slate-500">—</span>
                  )}
                </div>
              </div>
              <div>
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">{t.replayOpponent}</div>
                <div className="flex flex-wrap gap-1 justify-end">
                  {augB.length ? (
                    augB.map((a) => (
                      <Badge key={`B-${a.round}-${a.augment_id}`} variant="error">
                        {augmentName(a.augment_id) ?? a.augment_id}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-slate-500">—</span>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {sharecardMutation.error ? (
          <div className="text-xs text-red-600 break-words">{String(sharecardMutation.error)}</div>
        ) : null}

        {me?.is_guest ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Swords size={18} className="text-brand-600" /> First win in ~45 seconds
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm text-slate-600">
                Pick a recommended starter build and queue ranked in one tap.
              </div>
              <div className="flex flex-wrap gap-2">
                {RECOMMENDED_STARTER_BUILDS[starterMode].map((b) => (
                  <Button
                    key={b.id}
                    variant="secondary"
                    size="sm"
                    onClick={() => starterRankedMutation.mutate(b)}
                    isLoading={starterRankedMutation.isPending}
                    disabled={starterRankedMutation.isPending}
                  >
                    Queue with {b.label}
                  </Button>
                ))}
              </div>
              {starterRankedMutation.error ? (
                <div className="text-xs text-red-600 break-words">{String(starterRankedMutation.error)}</div>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Flame size={18} className="text-amber-500" /> Best Clip
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-12 gap-4">
            <div className="md:col-span-7 space-y-2">
              <div className="text-sm font-bold text-slate-800">{bestClip?.title ?? 'Turning Point'}</div>
              <div className="text-xs text-slate-600">{bestClip?.summary ?? ''}</div>
              {bestClip ? (
                <div className="text-[10px] font-mono text-slate-500">
                  {bestClip.start_sec.toFixed(1)}s–{bestClip.end_sec.toFixed(1)}s · replay_id: {bestClip.replay_id}
                </div>
              ) : (
                <div className="text-xs text-slate-500">Loading…</div>
              )}

              <div className="flex flex-wrap gap-2 items-center pt-1">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => bestClipMutation.mutate()}
                  disabled={!match?.replay_id || bestClipMutation.isPending}
                  isLoading={bestClipMutation.isPending}
                >
                  Generate Vertical MP4
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => copyBestClipLink()}
                  disabled={!match?.replay_id}
                >
                  Copy Best Clip Link
                </Button>
                {isReplyClip ? (
                  <Button variant="secondary" size="sm" onClick={() => copyReplyClipLink()} disabled={!match?.replay_id}>
                    Share Reply Clip
                  </Button>
                ) : null}
                {isReplyClip && replyToReplayId ? (
                  <a
                    href={`/s/clip/${encodeURIComponent(replyToReplayId)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-bold px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50"
                  >
                    View Original
                  </a>
                ) : null}
                {bestMp4Url && bestClip ? (
                  <a
                    href={`/s/clip/${encodeURIComponent(bestClip.replay_id)}/kit.zip?start=${bestClip.start_sec.toFixed(1)}&end=${bestClip.end_sec.toFixed(1)}&ref=in_app`}
                    download={`neuroleague_creator_kit_${id ?? 'match'}.zip`}
                    className="text-xs font-bold px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50"
                  >
                    Download Kit
                  </a>
                ) : null}
                {bestMp4Url ? (
                  <a
                    href={bestMp4Url}
                    download={`neuroleague_best_clip_${id ?? 'match'}.mp4`}
                    className="text-xs font-bold px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50"
                  >
                    Download MP4
                  </a>
                ) : null}
              </div>

              {bestClipMutation.error ? (
                <div className="text-xs text-red-600 break-words">{String(bestClipMutation.error)}</div>
              ) : null}
            </div>

            <div className="md:col-span-5">
              <div className="bg-white rounded-xl border border-slate-200 p-3">
                {bestMp4Url ? (
                  <video
                    src={bestMp4Url}
                    controls
                    playsInline
                    className="w-full rounded-lg border border-slate-200 bg-slate-950"
                  />
                ) : (
                  <div className="text-xs text-slate-500">
                    {bestClip?.assets?.find((a) => a.kind === 'vertical_mp4')?.status === 'done'
                      ? 'Best clip is ready. Click “Generate Vertical MP4” to load preview.'
                      : 'No vertical clip yet.'}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex-1 bg-slate-900 rounded-3xl relative overflow-hidden shadow-inner group">
          <BattleViewport
            replay={replay}
            tick={tick}
            showOverlay={showOverlay}
            highlightCaption={highlightCaption}
            isInHighlight={Boolean(activeHighlight)}
          />

          <div className="absolute top-4 right-4 bg-black/50 text-white px-3 py-1 rounded-full font-mono text-sm backdrop-blur-md">
            {formatClock(tick)} / {formatClock(durationTicks)}
          </div>

          {showOverlay ? (
            <div className="absolute left-4 bottom-4 bg-black/55 text-white rounded-2xl p-3 backdrop-blur-md border border-white/10 w-[260px]">
              <div className="flex items-center justify-between">
                <div className="text-xs uppercase tracking-wider text-white/70">{t.overlay}</div>
                {activeHighlight ? (
                  <Badge variant="brand" className="bg-white/10 text-white border-white/10">
                    #{activeHighlight.rank} {activeHighlight.title}
                  </Badge>
                ) : (
                  <Badge variant="neutral" className="bg-white/10 text-white border-white/10">
                    {formatClock(tick)}
                  </Badge>
                )}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div className="bg-white/5 rounded-xl p-2">
                  <div className="text-white/60">{t.replayYou}</div>
                  <div className="font-semibold">{stats ? stats.damageA : 0} DMG</div>
                  <div className="text-white/70">{stats ? stats.deathsB : 0} Kills</div>
                </div>
                <div className="bg-white/5 rounded-xl p-2">
                  <div className="text-white/60">{t.replayOpponent}</div>
                  <div className="font-semibold">{stats ? stats.damageB : 0} DMG</div>
                  <div className="text-white/70">{stats ? stats.deathsA : 0} Kills</div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
          <div className="relative h-8 mb-4">
            <input
              type="range"
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-brand-600"
              min={0}
              max={Math.max(1, durationTicks)}
              step={1}
              value={tick}
              onChange={(e) => setTick(parseInt(e.target.value))}
              aria-label="Replay timeline"
            />
            <div className="pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 h-4">
              {highlightRanges.map(({ h, left, width, color }) => (
                <div
                  key={`range-${h.rank}`}
                  className={`absolute top-1/2 -translate-y-1/2 h-1.5 ${color} rounded-full`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${h.title} (${formatClock(h.start_t)}–${formatClock(h.end_t)})`}
                ></div>
              ))}
              {markers.map((m, idx) => (
                <div
                  key={`${m.t}-${idx}`}
                  className={`absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 ${m.color} rounded-full border-2 border-white shadow-sm`}
                  style={{ left: `${(m.t / Math.max(1, durationTicks)) * 100}%` }}
                  title={m.title}
                ></div>
              ))}
            </div>
          </div>

          <div className="flex justify-center items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Back"
              onClick={() => setTick((v) => Math.max(0, v - 40))}
            >
              <SkipBack size={20} />
            </Button>
            <Button
              size="icon"
              className="w-12 h-12 rounded-full"
              onClick={() => setIsPlaying(!isPlaying)}
              aria-label="Play/Pause"
            >
              {isPlaying ? (
                <Pause size={24} className="fill-current" />
              ) : (
                <Play size={24} className="fill-current ml-1" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Forward"
              onClick={() => setTick((v) => Math.min(durationTicks, v + 40))}
            >
              <SkipForward size={20} />
            </Button>

            <div className="w-px h-8 bg-slate-200 mx-4"></div>

            <div className="flex gap-2 items-center">
              <span className="text-xs font-bold text-slate-400 uppercase">{t.events}:</span>
              <Badge variant="warning" className="cursor-pointer">
                <Flame size={10} className="mr-1" /> {t.highDamage}
              </Badge>
              <Badge variant="error" className="cursor-pointer">
                <Skull size={10} className="mr-1" /> {t.kills}
              </Badge>
            </div>

            <div className="w-px h-8 bg-slate-200 mx-4"></div>

            <div className="flex items-center gap-2">
              {[1, 2, 4].map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSpeed(s as 1 | 2 | 4)}
                  className={`text-xs font-bold px-2 py-1 rounded-lg border ${
                    speed === s
                      ? 'bg-brand-50 text-brand-700 border-brand-200'
                      : 'bg-white text-slate-500 border-slate-200'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>

            <Button
              variant="secondary"
              size="sm"
              className="ml-2"
              onClick={() => bookmarkMutation.mutate()}
              disabled={!match?.replay_id || bookmarkMutation.isPending}
            >
              <Bookmark size={16} className="mr-2" /> Bookmark
            </Button>
          </div>

          <div className="mt-4 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Clip</div>
              <div className="text-[10px] font-mono text-slate-500">
                t={((clipStartTick ?? tick) / 20).toFixed(1)}s
                {clipEndTick != null ? ` → end=${(clipEndTick / 20).toFixed(1)}s` : ''}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              <Button variant="outline" size="sm" onClick={() => setClipStartTick(tick)}>
                Set Start
              </Button>
              <Button variant="outline" size="sm" onClick={() => setClipEndTick(tick)}>
                Set End
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setClipStartTick(null);
                  setClipEndTick(null);
                  const next = new URLSearchParams(searchParams);
                  next.delete('t');
                  next.delete('end');
                  setSearchParams(next, { replace: true });
                }}
              >
                Clear
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => copyClipLink('share')}
                disabled={!replay || !match?.replay_id}
              >
                Copy Share Link
              </Button>
              <Button variant="secondary" size="sm" onClick={copyDiscordText} disabled={!replay}>
                {lang === 'ko' ? '디스코드용 복사' : 'Copy for Discord'}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => beatThisMutation.mutate()}
                disabled={!match?.replay_id || beatThisMutation.isPending}
                isLoading={beatThisMutation.isPending}
              >
                <Swords size={14} className="mr-2" /> Beat This Link
              </Button>
              <Button variant="outline" size="sm" onClick={() => copyClipLink('app')} disabled={!replay}>
                Copy App Link
              </Button>
              {reduceMotion ? (
                <span className="text-[10px] text-slate-500">Reduce motion ON</span>
              ) : null}
            </div>

            {clipGenError ? <div className="text-xs text-red-600">{clipGenError}</div> : null}
            {challengeError ? <div className="text-xs text-red-600">{challengeError}</div> : null}
            {challengeLink ? (
              <div className="text-[11px] text-slate-500 break-all">
                Beat This: <span className="font-mono">{challengeLink}</span>
              </div>
            ) : null}

            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 mt-2">
              <div className="md:col-span-5 bg-white rounded-xl border border-slate-200 p-3">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Thumbnail</div>
                <div className="flex flex-wrap gap-2 mt-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={generateThumbnail}
                    disabled={!clipEndpoints || clipGenStatus !== 'idle'}
                    isLoading={clipGenStatus === 'thumb'}
                  >
                    Generate Thumbnail
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => clipEndpoints && copyEndpointLink(clipEndpoints.shareThumb)}
                    disabled={!clipEndpoints}
                  >
                    Copy Thumbnail Link
                  </Button>
                </div>
                <div className="mt-3">
                  {thumbUrl ? (
                    <img
                      src={thumbUrl}
                      alt="Clip thumbnail"
                      className="w-full rounded-lg border border-slate-200"
                    />
                  ) : (
                    <div className="text-xs text-slate-500">No thumbnail yet.</div>
                  )}
                </div>
              </div>

              <div className="md:col-span-7 bg-white rounded-xl border border-slate-200 p-3">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Export</div>
                <div className="flex flex-wrap gap-2 mt-2 items-center">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => exportClip('webm')}
                    disabled={!clipEndpoints || clipGenStatus !== 'idle'}
                    isLoading={clipGenStatus === 'webm'}
                  >
                    Export WebM
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => exportClip('gif')}
                    disabled={!clipEndpoints || clipGenStatus !== 'idle'}
                    isLoading={clipGenStatus === 'gif'}
                  >
                    Export GIF
                  </Button>
                  {webmUrl ? (
                    <a
                      href={webmUrl}
                      download={`neuroleague_clip_${id ?? 'match'}.webm`}
                      className="text-xs font-bold px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50"
                    >
                      Download WebM
                    </a>
                  ) : null}
                  {gifUrl ? (
                    <a
                      href={gifUrl}
                      download={`neuroleague_clip_${id ?? 'match'}.gif`}
                      className="text-xs font-bold px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50"
                    >
                      Download GIF
                    </a>
                  ) : null}
                </div>
                {clipEndpoints ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button variant="ghost" size="sm" onClick={() => copyEndpointLink(clipEndpoints.webm)}>
                      Copy WebM Link
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => copyEndpointLink(clipEndpoints.gif)}>
                      Copy GIF Link
                    </Button>
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-slate-500">Replay not ready.</div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="lg:col-span-3 flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>{t.insights}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {insights.map((line, idx) => (
              <div key={`${idx}-${line}`} className="text-sm text-slate-700">
                {line}
              </div>
            ))}
            {insights.length === 0 ? <div className="text-sm text-slate-500">Loading…</div> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles size={18} className="text-accent-500" /> Highlights
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {highlights.map((h) => (
              <button
                key={h.rank}
                type="button"
                className="w-full text-left p-3 rounded-xl border border-slate-200 hover:bg-slate-50 transition-colors"
                onClick={() => setTick(h.start_t)}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-500">#{h.rank}</span>
                  <span className="text-[10px] font-mono text-slate-400">
                    {formatClock(h.start_t)}–{formatClock(h.end_t)}
                  </span>
                </div>
                <div className="font-bold text-sm text-slate-800 mt-1">{h.title}</div>
                <div className="text-xs text-slate-600 mt-1">{h.summary}</div>
                <div className="mt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 px-3 rounded-lg"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setTick(h.start_t);
                    }}
                  >
                    {t.jump}
                  </Button>
                </div>
              </button>
            ))}
            {(replay?.highlights ?? match?.highlights ?? []).length === 0 ? (
              <div className="text-sm text-slate-500">No highlights.</div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="flex-1 min-h-[240px]">
          <CardHeader>
            <CardTitle>{t.events}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[360px] overflow-y-auto">
            {windowEvents.map((e, idx) => (
              <button
                key={`${e.t}-${idx}`}
                type="button"
                onClick={() => setTick(e.t)}
                className={`w-full text-left p-2 rounded-lg border transition-colors ${
                  e.t === tick ? 'border-brand-300 bg-brand-50' : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="text-xs font-mono text-slate-500">{e.t}t</span>
                  <span className="text-xs font-bold text-slate-700">{e.type}</span>
                </div>
                {e.type === 'SYNERGY_TRIGGER' ? (
                  <div className="text-[11px] text-slate-600 mt-1">
                    {(() => {
                      const payload = e.payload ?? {};
                      const team = String(payload.team ?? '');
                      const tag = String(payload.tag ?? '');
                      const threshold = Number(payload.threshold ?? 0);
                      const count = Number(payload.count ?? 0);
                      const bonus = Number(payload.bonus ?? 0);
                      const tier = Number.isFinite(threshold) && threshold > 0 ? `T${Math.round(threshold)}` : 'T?';
                      const c = Number.isFinite(count) && count > 0 ? `x${Math.round(count)}` : '';
                      const b = Number.isFinite(bonus) && bonus > 0 ? ` (+${Math.round(bonus)} Sigil)` : '';
                      return `${team ? `${team} · ` : ''}${tag ? `${tag} ` : ''}${tier} ${c}${b}`.trim();
                    })()}
                  </div>
                ) : null}
              </button>
            ))}
            {windowEvents.length === 0 ? <div className="text-sm text-slate-500">Loading…</div> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
