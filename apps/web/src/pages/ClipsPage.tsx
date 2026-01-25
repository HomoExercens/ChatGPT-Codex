import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Heart, MessageCircle, Share2, Sparkles, Volume2, VolumeX, Wand2, Zap } from 'lucide-react';

import { CreatureSilhouettes } from '../components/CreatureSilhouettes';
import { GesturePager, type GesturePagerThresholds, type SwipeAttemptInfo } from '../components/GesturePager';
import { Icon } from '../components/Icon';
import { ReactionBurst } from '../components/ReactionBurst';
import { ScrimOverlay } from '../components/ScrimOverlay';
import { Badge, BottomSheet, Button } from '../components/ui';
import type {
  ClaimQuestOut,
  ClipEventResponse,
  ClipFeedItem,
  ClipFeedOut,
  Mode,
  QuestAssignment,
  QuestsTodayOut,
  RepliesResponse,
  ReactResponse,
  Replay,
} from '../api/types';
import { apiFetch } from '../lib/api';
import { getExperimentVariant, useExperiments } from '../lib/experiments';
import { playSfx, tapJuice, vibrate } from '../lib/juice';
import { getLastReactionType, setLastReactionType, type ReactionType } from '../lib/reactions';
import { toast } from '../lib/toast';
import { TRANSLATIONS } from '../lib/translations';
import { appendUtmParams } from '../lib/utm';
import { useChromeStore } from '../stores/chrome';
import { useSettingsStore } from '../stores/settings';

type SlideState = {
  liked?: boolean;
  likes?: number;
  videoReady?: boolean;
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
const FTUE_KEY = 'neuroleague.ftue.play.v1.dismissed';
const HERO_FEED_KEY = 'neuroleague.play.hero_feed.v1.seen';
const GESTURE_HINT_KEY = 'neuroleague.play.gesture_hints.v2_1_1.dismissed';
const TICKS_PER_SEC = 20;

const DEFAULT_GESTURE_THRESHOLDS = Object.freeze({
  doubleTapMs: 260,
  doubleTapSlopPx: 14,
  pager: {
    tapSlopPx: 10,
    dragStartPx: 12,
    verticalDominance: 1.2,
    swipeCommitFrac: 0.18,
    swipeCommitMinPx: 64,
    swipeVelocityPxMs: 0.65,
  } satisfies GesturePagerThresholds,
});

const GESTURE_ATTEMPT_SAMPLING_KEY = 'neuroleague.play.gesture_attempt_sampling.v1';
const GESTURE_ATTEMPT_SAMPLE_RATE = 0.3;
const GESTURE_ATTEMPT_SESSION_CAP = 20;

type HudOutcome = 'win' | 'loss' | 'draw';
type ClipHudMoment =
  | { kind: 'kill' | 'crit' | 'synergy'; atSec: number }
  | { kind: 'damage'; atSec: number; amount: number; crit: boolean };

type ClipHudData = {
  outcome: HudOutcome;
  winnerHpPct: number | null;
  hasKill: boolean;
  hasCrit: boolean;
  hasSynergy: boolean;
  moments: ClipHudMoment[];
};

type DamageFloat = {
  id: string;
  amount: number;
  crit: boolean;
  x: number;
  y: number;
};

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function parseClipRangeFromShareUrl(shareUrl: string | null | undefined): { startTick: number; endTick: number } | null {
  const raw = (shareUrl || '').trim();
  if (!raw) return null;
  if (typeof window === 'undefined') return null;
  try {
    const u = new URL(raw, window.location.origin);
    const s = Number.parseFloat((u.searchParams.get('start') || '').trim());
    const e = Number.parseFloat((u.searchParams.get('end') || '').trim());
    if (!Number.isFinite(s) || !Number.isFinite(e)) return null;
    const startTick = Math.max(0, Math.round(s * TICKS_PER_SEC));
    const endTick = Math.max(startTick, Math.round(e * TICKS_PER_SEC));
    return { startTick, endTick };
  } catch {
    return null;
  }
}

function hashU32(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function safeGetStorage(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function safeSetStorage(storage: Storage | undefined, key: string, value: string): void {
  try {
    storage?.setItem(key, value);
  } catch {
    // ignore
  }
}

function offsetForDamage(replayId: string, idx: number): { x: number; y: number } {
  const h = hashU32(`${replayId}:${idx}:dmg`);
  const x = ((h & 0xff) / 255) * 2 - 1;
  const y = (((h >> 8) & 0xff) / 255) * 2 - 1;
  return { x: Math.round(x * 44), y: Math.round(y * 24) };
}

function buildClipHudData(params: {
  clip: ClipFeedItem;
  replay: Replay;
}): ClipHudData | null {
  const { clip, replay } = params;
  const range = parseClipRangeFromShareUrl(clip.share_url_vertical);
  if (!range) return null;

  const units = (replay.header.units ?? []) as Array<{ team: 'A' | 'B'; max_hp: number }>;
  const maxHpA = units.filter((u) => u.team === 'A').reduce((acc, u) => acc + Number(u.max_hp || 0), 0);
  const maxHpB = units.filter((u) => u.team === 'B').reduce((acc, u) => acc + Number(u.max_hp || 0), 0);
  const end = replay.end_summary;
  const winner = end?.winner;
  const outcome: HudOutcome = winner === 'A' ? 'win' : winner === 'B' ? 'loss' : 'draw';

  const winnerHp = winner === 'A' ? Number(end.hp_a || 0) : winner === 'B' ? Number(end.hp_b || 0) : 0;
  const winnerMax = winner === 'A' ? maxHpA : winner === 'B' ? maxHpB : 0;
  const winnerHpPct = winnerMax > 0 ? clamp01(winnerHp / winnerMax) : null;

  const startTick = range.startTick;
  const endTick = range.endTick;
  const segLenSec = Math.max(0.01, (endTick - startTick) / TICKS_PER_SEC);

  const tags = (clip.tags ?? []).map((t) => String(t).toLowerCase());
  const hasSynergy = tags.some((t) => t.includes('synergy'));

  const attackCritByKey = new Map<string, boolean>();
  const deathTicks = new Set<number>();
  let hasCrit = false;
  let hasKill = false;

  type RawDamage = { t: number; atSec: number; amount: number; crit: boolean };
  const damages: RawDamage[] = [];

  for (const ev of replay.timeline_events ?? []) {
    const t = Number((ev as any).t ?? -1);
    if (!Number.isFinite(t) || t < startTick || t > endTick) continue;
    const type = String((ev as any).type ?? '');
    const payload = ((ev as any).payload ?? {}) as Record<string, unknown>;

    if (type === 'ATTACK') {
      const source = String(payload.source ?? '');
      const target = String(payload.target ?? '');
      const crit = Boolean(payload.crit);
      const key = `${t}:${source}:${target}`;
      attackCritByKey.set(key, crit);
      if (crit) hasCrit = true;
    }
    if (type === 'DEATH') {
      deathTicks.add(t);
      hasKill = true;
    }
    if (type === 'DAMAGE') {
      const source = String(payload.source ?? '');
      const target = String(payload.target ?? '');
      const amount = Number(payload.amount ?? 0);
      if (!Number.isFinite(amount) || amount <= 0) continue;
      const key = `${t}:${source}:${target}`;
      const crit = Boolean(attackCritByKey.get(key));
      if (crit) hasCrit = true;
      damages.push({ t, atSec: (t - startTick) / TICKS_PER_SEC, amount: Math.round(amount), crit });
    }
  }

  const topDamage = damages
    .slice()
    .sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0) || a.t - b.t)
    .slice(0, 6)
    .sort((a, b) => a.t - b.t);

  const moments: ClipHudMoment[] = [];

  // A single always-visible "SYNERGY" cue if tags suggest it.
  if (hasSynergy) {
    moments.push({ kind: 'synergy', atSec: Math.min(0.6, Math.max(0.2, segLenSec * 0.18)) });
  }

  // First CRIT / KILL badge timing (earliest in segment).
  const firstCrit = damages.find((d) => d.crit);
  if (firstCrit) moments.push({ kind: 'crit', atSec: clamp01(firstCrit.atSec / segLenSec) * segLenSec });

  const killTick = Array.from(deathTicks.values()).sort((a, b) => a - b)[0];
  if (Number.isFinite(killTick)) {
    const atSec = (killTick - startTick) / TICKS_PER_SEC;
    moments.push({ kind: 'kill', atSec: Math.max(0, Math.min(segLenSec - 0.05, atSec)) });
  }

  for (const d of topDamage) {
    const atSec = Math.max(0, Math.min(segLenSec - 0.02, d.atSec));
    moments.push({ kind: 'damage', atSec, amount: d.amount, crit: d.crit });
  }

  // Deterministic trigger order.
  moments.sort((a, b) => a.atSec - b.atSec || a.kind.localeCompare(b.kind));

  return { outcome, winnerHpPct, hasKill, hasCrit, hasSynergy, moments };
}

export const ClipsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const lang = useSettingsStore((s) => s.language);
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);
  const soundEnabled = useSettingsStore((s) => s.soundEnabled);
  const setSoundEnabled = useSettingsStore((s) => s.setSoundEnabled);
  const nav = useMemo(() => TRANSLATIONS[lang].nav, [lang]);
  const [ftueOpen, setFtueOpen] = useState(() => {
    try {
      return localStorage.getItem(FTUE_KEY) !== '1';
    } catch {
      return true;
    }
  });
  const [heroEligible] = useState(() => {
    try {
      return localStorage.getItem(HERO_FEED_KEY) !== '1';
    } catch {
      return true;
    }
  });
  const [gestureHintsOpen, setGestureHintsOpen] = useState(() => {
    try {
      return localStorage.getItem(GESTURE_HINT_KEY) !== '1';
    } catch {
      return true;
    }
  });
  const [gestureHintsFading, setGestureHintsFading] = useState(false);
  const dismissGestureHints = React.useCallback(() => {
    try {
      localStorage.setItem(GESTURE_HINT_KEY, '1');
    } catch {
      // ignore
    }
    setGestureHintsFading(false);
    setGestureHintsOpen(false);
  }, []);

  const { data: experiments } = useExperiments();
  const feedAlgo = useMemo(() => {
    const v = getExperimentVariant(experiments, 'clips_feed_algo', 'v2');
    return v === 'v3' ? 'v3' : 'v2';
  }, [experiments]);
  const gestureThresholdVariant = useMemo(() => {
    const v = getExperimentVariant(experiments, 'gesture_thresholds_v1', 'control');
    return v === 'variant_a' || v === 'variant_b' ? v : 'control';
  }, [experiments]);
  const gestureThresholds = useMemo(() => {
    const cfg = (experiments?.gesture_thresholds_v1?.config ?? {}) as Record<string, unknown>;
    const n = (key: string, fallback: number) => {
      const v = cfg[key];
      return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
    };
    const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
    return {
      doubleTapMs: Math.round(clamp(n('double_tap_ms', DEFAULT_GESTURE_THRESHOLDS.doubleTapMs), 160, 420)),
      doubleTapSlopPx: Math.round(clamp(n('double_tap_slop_px', DEFAULT_GESTURE_THRESHOLDS.doubleTapSlopPx), 6, 28)),
      pager: {
        tapSlopPx: Math.round(clamp(n('tap_slop_px', DEFAULT_GESTURE_THRESHOLDS.pager.tapSlopPx), 6, 24)),
        dragStartPx: Math.round(clamp(n('drag_start_px', DEFAULT_GESTURE_THRESHOLDS.pager.dragStartPx), 8, 28)),
        verticalDominance: clamp(n('vertical_dominance', DEFAULT_GESTURE_THRESHOLDS.pager.verticalDominance), 1.05, 1.8),
        swipeCommitFrac: clamp(n('swipe_commit_frac', DEFAULT_GESTURE_THRESHOLDS.pager.swipeCommitFrac), 0.12, 0.35),
        swipeCommitMinPx: Math.round(clamp(n('swipe_commit_min_px', DEFAULT_GESTURE_THRESHOLDS.pager.swipeCommitMinPx), 32, 160)),
        swipeVelocityPxMs: clamp(n('swipe_velocity_px_ms', DEFAULT_GESTURE_THRESHOLDS.pager.swipeVelocityPxMs), 0.2, 1.4),
      } satisfies GesturePagerThresholds,
    };
  }, [experiments]);
  const heroFeedVariant = useMemo(() => {
    const v = getExperimentVariant(experiments, 'hero_feed_v1', 'hero_first');
    return v === 'control' ? 'control' : 'hero_first';
  }, [experiments]);
  const heroEnabled = useMemo(() => heroEligible && heroFeedVariant === 'hero_first', [heroEligible, heroFeedVariant]);

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
    queryKey: ['clipsFeed', mode, sort, feedAlgo, heroEnabled ? 'hero_first' : `no_hero:${heroFeedVariant}`],
    queryFn: ({ pageParam }) => {
      const qp = new URLSearchParams();
      qp.set('mode', mode);
      qp.set('sort', sort);
      qp.set('algo', feedAlgo);
      qp.set('limit', '12');
      if (!pageParam && heroEnabled) qp.set('hero', '1');
      if (pageParam) qp.set('cursor', String(pageParam));
      return apiFetch<ClipFeedOut>(`/api/clips/feed?${qp.toString()}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    staleTime: 10_000,
  });

  const clips: ClipFeedItem[] = useMemo(() => (data?.pages ?? []).flatMap((p) => p.items ?? []), [data?.pages]);

  useEffect(() => {
    if (!heroEnabled) return;
    if (!data?.pages?.length) return;
    try {
      localStorage.setItem(HERO_FEED_KEY, '1');
    } catch {
      // ignore
    }
  }, [data?.pages?.length, heroEnabled]);

  useEffect(() => {
    if (!gestureHintsOpen) return;
    if (ftueOpen) return;

    setGestureHintsFading(false);
    const fadeAt = window.setTimeout(() => setGestureHintsFading(true), 2000);
    const hideAt = window.setTimeout(() => dismissGestureHints(), reduceMotion ? 2000 : 2350);
    return () => {
      window.clearTimeout(fadeAt);
      window.clearTimeout(hideAt);
    };
  }, [dismissGestureHints, ftueOpen, gestureHintsOpen, reduceMotion]);

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<{ user_id: string }>('/api/auth/me'),
    staleTime: 60_000,
  });

  const { data: questsToday } = useQuery({
    queryKey: ['questsToday'],
    queryFn: () => apiFetch<QuestsTodayOut>('/api/quests/today'),
    staleTime: 5_000,
  });

  const claimQuestMutation = useMutation({
    mutationFn: async (assignment: QuestAssignment) =>
      apiFetch<ClaimQuestOut>('/api/quests/claim', {
        method: 'POST',
        body: JSON.stringify({ assignment_id: assignment.assignment_id }),
      }),
    onSuccess: async (out, assignment) => {
      await queryClient.invalidateQueries({ queryKey: ['questsToday'] });
      await queryClient.invalidateQueries({ queryKey: ['meProfile'] });
      try {
        await apiFetch('/api/events/track', {
          method: 'POST',
          body: JSON.stringify({
            type: 'quest_claimed',
            source: 'play',
            meta: {
              assignment_id: assignment.assignment_id,
              quest_id: assignment.quest.id,
              quest_key: assignment.quest.key,
              cadence: assignment.quest.cadence,
              period_key: assignment.period_key,
            },
          }),
        });
      } catch {
        // best-effort
      }
      if (out?.level_up) {
        playSfx('success');
        vibrate([18, 40, 18]);
      } else {
        playSfx('click');
        vibrate(18);
      }
      const xp = Number(out?.xp_awarded ?? 0);
      const level = Number(out?.level ?? 1);
      const streak = Number(out?.streak_days ?? 0);
      const shield = Number(out?.streak_freeze_tokens ?? 0);
      const protectedStreak = Boolean(out?.streak_protected);
      toast.success(
        lang === 'ko'
          ? `보상 획득! +${xp} XP · Lv.${level} · 스트릭 ${streak}일${protectedStreak ? ' (보호됨)' : ''} · 쉴드 ${shield}/1`
          : `Reward claimed! +${xp} XP · Lv.${level} · Streak ${streak}d${protectedStreak ? ' (protected)' : ''} · Shield ${shield}/1`
      );
    },
    onError: (e) => toast.error(lang === 'ko' ? '보상 수령 실패' : 'Claim failed', e instanceof Error ? e.message : String(e)),
  });

  const videoRefs = useRef<Record<number, HTMLVideoElement | null>>({});
  const shakeRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [activeIndex, setActiveIndex] = useState(0);
  const activeClip = useMemo(() => clips[activeIndex] ?? null, [activeIndex, clips]);
  const viewed = useRef<Set<string>>(new Set());
  const viewed3s = useRef<Set<string>>(new Set());
  const view3sTimer = useRef<number | null>(null);
  const view3sStart = useRef<number>(0);
  const completed = useRef<Set<string>>(new Set());
  const videoLoadFailed = useRef<Set<string>>(new Set());
  const [slideState, setSlideState] = useState<Record<string, SlideState>>({});
  const [questsOpen, setQuestsOpen] = useState(false);
  const [quickRemixOpen, setQuickRemixOpen] = useState(false);
  const [repliesOpen, setRepliesOpen] = useState(false);
  const [repliesTab, setRepliesTab] = useState<'top' | 'recent'>('top');
  const playChromeHidden = useChromeStore((s) => s.playChromeHidden);
  const setPlayChromeHidden = useChromeStore((s) => s.setPlayChromeHidden);

  const trackPlayUiEvent = React.useCallback(
    (type: string, meta?: Record<string, unknown>) => {
      apiFetch('/api/events/track', {
        method: 'POST',
        body: JSON.stringify({
          type,
          source: 'play',
          meta: {
            mode,
            sort,
            feed_algo: feedAlgo,
            hero_variant: heroFeedVariant,
            gesture_thresholds_variant: gestureThresholdVariant,
            ...(meta ?? {}),
          },
        }),
      }).catch(() => {
        // best-effort
      });
    },
    [feedAlgo, gestureThresholdVariant, heroFeedVariant, mode, sort]
  );

  type GestureAttemptSamplingState = {
    v: 1;
    sample_rate: number;
    sampled: boolean;
    remaining: number;
  };

  const takeGestureAttemptToken = React.useCallback((): { ok: boolean; meta?: Record<string, unknown> } => {
    const ss = typeof sessionStorage !== 'undefined' ? sessionStorage : undefined;
    const ls = typeof localStorage !== 'undefined' ? localStorage : undefined;

    const raw = safeGetStorage(ss, GESTURE_ATTEMPT_SAMPLING_KEY);
    let state: GestureAttemptSamplingState | null = null;
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as Partial<GestureAttemptSamplingState>;
        if (
          parsed &&
          parsed.v === 1 &&
          typeof parsed.sample_rate === 'number' &&
          Number.isFinite(parsed.sample_rate) &&
          typeof parsed.sampled === 'boolean' &&
          typeof parsed.remaining === 'number' &&
          Number.isFinite(parsed.remaining)
        ) {
          state = {
            v: 1,
            sample_rate: Math.max(0, Math.min(1, parsed.sample_rate)),
            sampled: Boolean(parsed.sampled),
            remaining: Math.max(0, Math.min(999, Math.round(parsed.remaining))),
          };
        }
      } catch {
        state = null;
      }
    }

    if (!state) {
      const sampleRate = Math.max(0, Math.min(1, GESTURE_ATTEMPT_SAMPLE_RATE));
      const sessionId =
        (safeGetStorage(ss, 'neuroleague.session_id') ?? safeGetStorage(ls, 'neuroleague.session_id') ?? '').trim() ||
        (safeGetStorage(ls, 'neuroleague.device_id') ?? '').trim();
      const r = sessionId ? (hashU32(`gesture_attempts:${sessionId}`) % 10_000) / 10_000 : Math.random();
      const sampled = sampleRate >= 1 ? true : r < sampleRate;
      state = { v: 1, sample_rate: sampleRate, sampled, remaining: GESTURE_ATTEMPT_SESSION_CAP };
    }

    safeSetStorage(ss, GESTURE_ATTEMPT_SAMPLING_KEY, JSON.stringify(state));

    if (!state.sampled) return { ok: false };
    if (state.remaining <= 0) return { ok: false };

    state.remaining -= 1;
    safeSetStorage(ss, GESTURE_ATTEMPT_SAMPLING_KEY, JSON.stringify(state));

    return {
      ok: true,
      meta: {
        gesture_attempt_sample_rate: state.sample_rate,
        gesture_attempt_sampled: 1,
        gesture_attempt_session_cap: GESTURE_ATTEMPT_SESSION_CAP,
        gesture_attempt_session_remaining: state.remaining,
      },
    };
  }, []);

  const trackGestureAttempt = React.useCallback(
    (type: 'tap_attempt' | 'swipe_attempt', meta: Record<string, unknown>) => {
      const tok = takeGestureAttemptToken();
      if (!tok.ok) return;
      trackPlayUiEvent(type, { ...(tok.meta ?? {}), ...(meta ?? {}) });
    },
    [takeGestureAttemptToken, trackPlayUiEvent]
  );

  const autoHideTimer = useRef<number | null>(null);
  const autoHideBlockedRef = useRef<boolean>(false);
  const [keyboardMode, setKeyboardMode] = useState(false);
  const [a11yFocusWithin, setA11yFocusWithin] = useState(false);

  const clearAutoHide = React.useCallback(() => {
    if (autoHideTimer.current) {
      window.clearTimeout(autoHideTimer.current);
      autoHideTimer.current = null;
    }
  }, []);

  const hideChrome = React.useCallback(
    (reason: string = 'user') => {
      clearAutoHide();
      if (!playChromeHidden) {
        setPlayChromeHidden(true);
        if (reason !== 'init' && reason !== 'blocked' && reason !== 'unmount') {
          trackPlayUiEvent('chrome_autohide_hidden', { reason, replay_id: activeClip?.replay_id ?? null });
        }
      }
    },
    [activeClip?.replay_id, clearAutoHide, playChromeHidden, setPlayChromeHidden, trackPlayUiEvent]
  );

  const armAutoHide = React.useCallback(() => {
    clearAutoHide();
    if (autoHideBlockedRef.current) return;
    autoHideTimer.current = window.setTimeout(() => {
      if (autoHideBlockedRef.current) return;
      hideChrome('idle');
    }, 6500);
  }, [clearAutoHide, hideChrome]);

  const showChrome = React.useCallback(
    (reason: string = 'user') => {
      const wasHidden = playChromeHidden;
      setPlayChromeHidden(false);
      if (wasHidden && reason !== 'init' && reason !== 'blocked' && reason !== 'unmount') {
        trackPlayUiEvent('chrome_autohide_shown', { reason, replay_id: activeClip?.replay_id ?? null });
      }
      armAutoHide();
    },
    [activeClip?.replay_id, armAutoHide, playChromeHidden, setPlayChromeHidden, trackPlayUiEvent]
  );

  useEffect(() => {
    showChrome('init');
    return () => {
      clearAutoHide();
      setPlayChromeHidden(false);
    };
  }, [setPlayChromeHidden, showChrome]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Tab' || e.key === 'Shift' || e.key.startsWith('Arrow')) {
        setKeyboardMode(true);
        showChrome('keyboard');
      }
    };
    const onPointerDown = () => setKeyboardMode(false);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('pointerdown', onPointerDown, { passive: true });
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('pointerdown', onPointerDown);
    };
  }, [showChrome]);

  useEffect(() => {
    const onFocusIn = () => {
      setA11yFocusWithin(true);
      showChrome('focus');
    };
    const onFocusOut = () => {
      window.setTimeout(() => {
        const el = document.activeElement as HTMLElement | null;
        const hasFocus = Boolean(el && el !== document.body && el !== document.documentElement);
        setA11yFocusWithin(hasFocus);
      }, 0);
    };

    window.addEventListener('focusin', onFocusIn);
    window.addEventListener('focusout', onFocusOut);
    return () => {
      window.removeEventListener('focusin', onFocusIn);
      window.removeEventListener('focusout', onFocusOut);
    };
  }, [showChrome]);

  useEffect(() => {
    autoHideBlockedRef.current = reduceMotion || ftueOpen || questsOpen || quickRemixOpen || repliesOpen || keyboardMode || a11yFocusWithin;
    if (autoHideBlockedRef.current) {
      setPlayChromeHidden(false);
      clearAutoHide();
      return;
    }
    armAutoHide();
  }, [
    a11yFocusWithin,
    armAutoHide,
    clearAutoHide,
    ftueOpen,
    keyboardMode,
    questsOpen,
    quickRemixOpen,
    reduceMotion,
    repliesOpen,
    setPlayChromeHidden,
  ]);

  const lastTap = useRef<{ t: number; x: number; y: number } | null>(null);
  const pendingSingleTap = useRef<number | null>(null);
  const clearPendingSingleTap = React.useCallback(() => {
    if (pendingSingleTap.current) {
      window.clearTimeout(pendingSingleTap.current);
      pendingSingleTap.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearPendingSingleTap();
      lastTap.current = null;
    };
  }, [clearPendingSingleTap]);

  const lastReactAt = useRef<number>(0);
  const [reactionBurst, setReactionBurst] = useState<{ key: string; reaction: ReactionType } | null>(null);

  const reactMutation = useMutation({
    mutationFn: async ({ replayId, reactionType }: { replayId: string; reactionType: ReactionType }) => {
      return await apiFetch<ReactResponse>(`/api/clips/${encodeURIComponent(replayId)}/react`, {
        method: 'POST',
        body: JSON.stringify({ reaction_type: reactionType, source: 'play_double_tap' }),
      });
    },
    onError: (e) => {
      toast.error(lang === 'ko' ? '리액션 실패' : 'Reaction failed', e instanceof Error ? e.message : String(e));
    },
  });

  const [hudMatchId, setHudMatchId] = useState<string | null>(null);
  const hudTargetMatchId = activeClip?.match_id ?? null;
  useEffect(() => {
    if (!hudTargetMatchId) {
      setHudMatchId(null);
      return;
    }
    const handle = window.setTimeout(() => setHudMatchId(hudTargetMatchId), 180);
    return () => window.clearTimeout(handle);
  }, [hudTargetMatchId]);

  const { data: hudReplay } = useQuery({
    queryKey: ['playHudReplay', hudMatchId],
    queryFn: () => apiFetch<Replay>(`/api/matches/${encodeURIComponent(hudMatchId!)}/replay`),
    enabled: Boolean(hudMatchId),
    staleTime: 60_000,
  });

  const activeHud: ClipHudData | null = useMemo(() => {
    if (!activeClip || !hudReplay) return null;
    try {
      return buildClipHudData({ clip: activeClip, replay: hudReplay });
    } catch {
      return null;
    }
  }, [activeClip, hudReplay]);

  const hudRuntime = useRef<{
    replayId: string;
    moments: ClipHudMoment[];
    fired: Set<number>;
    lastTime: number;
    strongCount: number;
  } | null>(null);
  const [hudFlash, setHudFlash] = useState<{ id: string; label: string; tone: 'kill' | 'crit' | 'synergy' } | null>(null);
  const [damageFloats, setDamageFloats] = useState<DamageFloat[]>([]);
  const fxCounter = useRef(0);
  const juiceLockUntil = useRef<number>(0);
  const [lowPerf, setLowPerf] = useState(false);
  const perfState = useRef<{ lastT: number; slowStreak: number; fastStreak: number; low: boolean }>({
    lastT: 0,
    slowStreak: 0,
    fastStreak: 0,
    low: false,
  });

  useEffect(() => {
    if (reduceMotion) {
      setLowPerf(false);
      perfState.current = { lastT: 0, slowStreak: 0, fastStreak: 0, low: false };
      return;
    }

    let raf = 0;
    const step = (t: number) => {
      const st = perfState.current;
      const last = st.lastT;
      st.lastT = t;
      if (last > 0) {
        const dt = t - last;
        const slow = dt > 55;
        const fast = dt < 40;

        st.slowStreak = slow ? st.slowStreak + 1 : Math.max(0, st.slowStreak - 1);
        st.fastStreak = fast ? st.fastStreak + 1 : Math.max(0, st.fastStreak - 1);

        if (!st.low && st.slowStreak >= 10) {
          st.low = true;
          st.fastStreak = 0;
          setLowPerf(true);
        } else if (st.low && st.fastStreak >= 20) {
          st.low = false;
          st.slowStreak = 0;
          setLowPerf(false);
        }
      }
      raf = window.requestAnimationFrame(step);
    };
    raf = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(raf);
  }, [reduceMotion]);

  useEffect(() => {
    if (!activeClip?.replay_id || !activeHud) {
      hudRuntime.current = null;
      setHudFlash(null);
      setDamageFloats([]);
      return;
    }
    hudRuntime.current = {
      replayId: activeClip.replay_id,
      moments: activeHud.moments,
      fired: new Set<number>(),
      lastTime: 0,
      strongCount: 0,
    };
    setHudFlash(null);
    setDamageFloats([]);
  }, [activeClip?.replay_id, activeHud?.moments]);

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
      type: 'view' | 'like' | 'share' | 'completion';
      meta?: Record<string, unknown>;
    }) =>
      apiFetch<ClipEventResponse>(`/api/clips/${encodeURIComponent(replayId)}/event`, {
        method: 'POST',
        body: JSON.stringify({ type, source: 'clips', meta: meta ?? {} }),
      }),
  });

  const playOpenTracked = useRef(false);
  useEffect(() => {
    if (playOpenTracked.current) return;
    playOpenTracked.current = true;
    apiFetch('/api/events/track', {
      method: 'POST',
      body: JSON.stringify({
        type: 'play_open',
        source: 'play',
        meta: { mode, sort, feed_algo: feedAlgo, hero_variant: heroFeedVariant },
      }),
    }).catch(() => {
      // best-effort
    });
  }, [feedAlgo, heroFeedVariant, mode, sort]);

  useEffect(() => {
    const item = clips[activeIndex];
    if (!item) return;

    // fire view event once per session
    if (!viewed.current.has(item.replay_id)) {
      viewed.current.add(item.replay_id);
      trackEventMutation.mutate({
        replayId: item.replay_id,
        type: 'view',
        meta: { surface: 'play', mode, sort, feed_algo: feedAlgo },
      });
    }

    // "meaningful view" event with watched_ms (>=3s), used for FTUE funnel coverage.
    if (view3sTimer.current) {
      window.clearTimeout(view3sTimer.current);
      view3sTimer.current = null;
    }
    if (!viewed3s.current.has(item.replay_id)) {
      view3sStart.current = typeof performance !== 'undefined' ? performance.now() : Date.now();
      view3sTimer.current = window.setTimeout(() => {
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
        const watchedMs = Math.max(0, Math.round(now - view3sStart.current));
        viewed3s.current.add(item.replay_id);
        trackEventMutation.mutate({
          replayId: item.replay_id,
          type: 'view',
          meta: { surface: 'play', mode, sort, feed_algo: feedAlgo, watched_ms: watchedMs },
        });
      }, 3000);
    }

    // autoplay active video, pause others
    for (const [idxStr, v] of Object.entries(videoRefs.current)) {
      const i = Number(idxStr);
      if (!Number.isFinite(i) || !v) continue;
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

    return () => {
      if (view3sTimer.current) {
        window.clearTimeout(view3sTimer.current);
        view3sTimer.current = null;
      }
    };
  }, [activeIndex, clips, feedAlgo, fetchNextPage, hasNextPage, isFetchingNextPage, mode, sort, trackEventMutation]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      e.preventDefault();
      const dir = e.key === 'ArrowDown' ? 1 : -1;
      const nextIdx = clampIndex(activeIndex + dir, clips.length);
      setActiveIndex(nextIdx);
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
    onError: (e) => toast.error('Like failed', e instanceof Error ? e.message : String(e)),
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
    onSuccess: () => toast.success(lang === 'ko' ? '링크 복사됨' : 'Link copied'),
    onError: (e) => toast.error(lang === 'ko' ? '공유 실패' : 'Share failed', e instanceof Error ? e.message : String(e)),
  });

  const title = nav.play ?? (lang === 'ko' ? '플레이' : 'Play');

  const triggerShake = (ms: number) => {
    const el = shakeRefs.current[activeIndex];
    if (!el) return;
    el.classList.remove('nl-shake');
    // Force reflow to restart animation.
    void el.offsetWidth;
    el.classList.add('nl-shake');
    window.setTimeout(() => el.classList.remove('nl-shake'), ms);
  };

  const triggerHitStop = (video: HTMLVideoElement, ms: number, slowmo?: { rate: number; ms: number }) => {
    if (reduceMotion || lowPerf) return;
    const now = Date.now();
    if (now < juiceLockUntil.current) return;
    juiceLockUntil.current = now + ms + (slowmo?.ms ?? 0) + 80;

    const originalRate = video.playbackRate || 1;
    const resume = () => {
      if (slowmo) {
        video.playbackRate = slowmo.rate;
        window.setTimeout(() => {
          try {
            video.playbackRate = originalRate;
          } catch {
            // ignore
          }
        }, slowmo.ms);
      }
      video.play().catch(() => {
        // ignore
      });
    };

    try {
      video.pause();
    } catch {
      // ignore
    }
    window.setTimeout(resume, ms);
  };

  const handleHudTime = (video: HTMLVideoElement, replayId: string) => {
    const rt = hudRuntime.current;
    if (!rt || rt.replayId !== replayId) return;
    const t = video.currentTime;
    if (!Number.isFinite(t)) return;

    // Reset triggers on loop.
    if (t + 0.1 < rt.lastTime) {
      rt.fired.clear();
      rt.strongCount = 0;
      setHudFlash(null);
      setDamageFloats([]);
    }
    rt.lastTime = t;

    for (let i = 0; i < rt.moments.length; i++) {
      if (rt.fired.has(i)) continue;
      const m = rt.moments[i];
      if (t + 0.04 < m.atSec) continue;
      rt.fired.add(i);

      if (m.kind === 'damage') {
        const id = `dmg_${fxCounter.current++}`;
        const off = offsetForDamage(replayId, i);
        setDamageFloats((prev) => [...prev, { id, amount: m.amount, crit: m.crit, x: off.x, y: off.y }].slice(-10));
        window.setTimeout(() => {
          setDamageFloats((prev) => prev.filter((d) => d.id !== id));
        }, 900);
        continue;
      }

      const flashId = `flash_${fxCounter.current++}`;
      const tone = m.kind === 'kill' ? 'kill' : m.kind === 'crit' ? 'crit' : 'synergy';
      setHudFlash({ id: flashId, label: m.kind.toUpperCase(), tone });
      window.setTimeout(() => {
        setHudFlash((prev) => (prev?.id === flashId ? null : prev));
      }, 700);

      if (reduceMotion) continue;
      if (rt.strongCount >= 2) continue;
      rt.strongCount += 1;
      if (m.kind === 'kill') {
        triggerShake(lowPerf ? 160 : 340);
        triggerHitStop(video, 70, { rate: 0.72, ms: 240 });
      } else if (m.kind === 'crit') {
        triggerShake(lowPerf ? 140 : 240);
        triggerHitStop(video, 50, { rate: 0.86, ms: 160 });
      } else if (m.kind === 'synergy') {
        triggerShake(lowPerf ? 120 : 180);
        triggerHitStop(video, 30, { rate: 0.9, ms: 120 });
      }
    }
  };

  const questCard = useMemo(() => {
    const daily = questsToday?.daily ?? [];
    if (!daily.length) return null;
    const completedCount = daily.filter((q) => (q.progress_count ?? 0) >= (q.quest.goal_count ?? 1)).length;
    const claimableCount = daily.filter((q) => q.claimable).length;
    const primary =
      daily.find((q) => q.claimable) ??
      daily.find((q) => (q.progress_count ?? 0) < (q.quest.goal_count ?? 1)) ??
      daily[0] ??
      null;
    if (!primary) return null;
    const goal = Math.max(1, Number(primary.quest.goal_count ?? 1));
    const prog = Math.max(0, Number(primary.progress_count ?? 0));
    const pct = Math.max(0, Math.min(1, prog / goal));
    return { daily, completedCount, claimableCount, primary, goal, prog, pct };
  }, [questsToday?.daily]);

  const triggerDoubleTapReaction = React.useCallback(() => {
    const replayId = activeClip?.replay_id;
    if (!replayId) return;
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    if (now - lastReactAt.current < 650) return;
    lastReactAt.current = now;

    const reactionType = getLastReactionType();
    setLastReactionType(reactionType);
    setReactionBurst({ key: `burst_${replayId}_${Date.now()}`, reaction: reactionType });
    reactMutation.mutate({ replayId, reactionType });
    trackPlayUiEvent('double_tap_reaction', { replay_id: replayId, reaction_type: reactionType });
    tapJuice();
  }, [activeClip?.replay_id, reactMutation, trackPlayUiEvent]);

  const handlePagerTap = React.useCallback(
    (info: { clientX: number; clientY: number }) => {
      if (gestureHintsOpen) dismissGestureHints();

      const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
      const prev = lastTap.current;
      const isDoubleTap =
        Boolean(prev) &&
        now - (prev?.t ?? 0) <= gestureThresholds.doubleTapMs &&
        Math.hypot((prev?.x ?? 0) - info.clientX, (prev?.y ?? 0) - info.clientY) <= gestureThresholds.doubleTapSlopPx;

      if (isDoubleTap) {
        clearPendingSingleTap();
        lastTap.current = null;
        trackGestureAttempt('tap_attempt', {
          replay_id: activeClip?.replay_id ?? null,
          kind: 'double_candidate',
          canceled: 0,
          cancel_reason: null,
        });
        triggerDoubleTapReaction();
        return;
      }

      lastTap.current = { t: now, x: info.clientX, y: info.clientY };
      clearPendingSingleTap();

      pendingSingleTap.current = window.setTimeout(() => {
        pendingSingleTap.current = null;
        lastTap.current = null;
        trackGestureAttempt('tap_attempt', {
          replay_id: activeClip?.replay_id ?? null,
          kind: 'single_candidate',
          canceled: 0,
          cancel_reason: null,
        });

        // Tap-to-unmute: only from a confirmed single tap.
        const v = videoRefs.current[activeIndex];
        if (v && v.muted) {
          tapJuice();
          try {
            v.muted = false;
          } catch {
            // ignore
          }
          setSoundEnabled(true);
          trackPlayUiEvent('unmute_click', { via: 'tap', replay_id: activeClip?.replay_id ?? null });
          v.play().catch(() => {
            toast.info(lang === 'ko' ? '음성 재생이 차단됨 (다시 탭)' : 'Audio blocked (tap again)');
          });
          toast.info(lang === 'ko' ? '사운드 ON' : 'Sound on');
          showChrome('tap_unmute');
          return;
        }

        // If chrome auto-hide is blocked (a11y/overlay), never hide on tap.
        if (autoHideBlockedRef.current) {
          showChrome('tap');
          return;
        }

        // Single tap toggles chrome (immersive).
        if (playChromeHidden) showChrome('tap_toggle');
        else hideChrome('tap_toggle');
      }, gestureThresholds.doubleTapMs);
    },
    [
      activeClip?.replay_id,
      activeIndex,
      autoHideBlockedRef,
      clearPendingSingleTap,
      dismissGestureHints,
      gestureHintsOpen,
      hideChrome,
      gestureThresholds.doubleTapMs,
      gestureThresholds.doubleTapSlopPx,
      lang,
      playChromeHidden,
      setSoundEnabled,
      showChrome,
      trackGestureAttempt,
      trackPlayUiEvent,
      triggerDoubleTapReaction,
    ]
  );

  const activeIndexRef = useRef(activeIndex);
  useEffect(() => {
    activeIndexRef.current = activeIndex;
  }, [activeIndex]);

  const handleSwipeAttempt = React.useCallback(
    (info: SwipeAttemptInfo) => {
      const idx = activeIndexRef.current;
      const replayId = clips[idx]?.replay_id ?? null;
      trackGestureAttempt('swipe_attempt', {
        replay_id: replayId,
        direction_candidate: info.directionCandidate,
        dx: Math.round(info.dx),
        dy: Math.round(info.dy),
        velocity: Number(info.velocity.toFixed(3)),
        committed: info.committed ? 1 : 0,
        cancel_reason: info.cancelReason,
      });
    },
    [clips, trackGestureAttempt]
  );

  const handlePagerIndexChange = React.useCallback(
    (nextIdx: number) => {
      clearPendingSingleTap();
      lastTap.current = null;

      const prevIdx = activeIndexRef.current;
      const prevReplayId = clips[prevIdx]?.replay_id ?? null;
      const nextReplayId = clips[nextIdx]?.replay_id ?? null;
      if (nextIdx > prevIdx) trackPlayUiEvent('swipe_next', { from_replay_id: prevReplayId, to_replay_id: nextReplayId });
      if (nextIdx < prevIdx) trackPlayUiEvent('swipe_prev', { from_replay_id: prevReplayId, to_replay_id: nextReplayId });

      setActiveIndex(nextIdx);
      showChrome('swipe');
    },
    [clearPendingSingleTap, clips, showChrome, trackPlayUiEvent]
  );

  const renderClipPage = (idx: number) => {
    const item = clips[idx];
    if (!item) {
      return (
        <div className="h-full w-full flex items-center justify-center bg-bg">
          <div className="text-muted">{isFetching ? 'Loading…' : 'No clips yet.'}</div>
        </div>
      );
    }

    const local = slideState[item.replay_id] ?? {};
    const liked = local.liked ?? false;
    const likes = local.likes ?? item.stats.likes;
    const isActive = idx === activeIndex;
    const hasVideo = Boolean(item.vertical_mp4_url);
    const shouldLoadVideo = hasVideo && (idx === activeIndex || idx === activeIndex + 1);
    const showHud = isActive && activeHud && activeClip?.replay_id === item.replay_id;

    const chromeAnim = `transition-[opacity,transform] duration-[var(--nl-dur)] ease-[var(--nl-ease-out)] ${
      playChromeHidden ? 'opacity-0 pointer-events-none translate-y-2' : 'opacity-100 pointer-events-auto translate-y-0'
    }`;
    const safeBottomPad = 'pb-[calc(var(--nl-tabbar-h)+env(safe-area-inset-bottom)+14px)]';

    return (
      <div
        key={`${item.replay_id}:${idx}`}
        data-testid="play-clip"
        data-replay-id={item.replay_id}
        className={`relative h-full w-full bg-bg ${isActive ? 'pointer-events-auto' : 'pointer-events-none'}`}
      >
        <div
          ref={(el) => {
            if (el) shakeRefs.current[idx] = el;
            else delete shakeRefs.current[idx];
          }}
          className="absolute inset-0"
        >
          <img
            src={item.thumb_url}
            alt="Clip thumbnail"
            className={`h-full w-full object-cover ${shouldLoadVideo ? 'opacity-100' : 'opacity-85'}`}
          />
          {shouldLoadVideo && !local.videoReady ? (
            <div className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/10 to-black/50 animate-pulse" />
          ) : null}
          {hasVideo && shouldLoadVideo ? (
            <video
              ref={(el) => {
                if (el) videoRefs.current[idx] = el;
                else delete videoRefs.current[idx];
              }}
              src={item.vertical_mp4_url ?? undefined}
              poster={item.thumb_url}
              className={`absolute inset-0 h-full w-full object-cover ${local.videoReady ? 'opacity-100' : 'opacity-0'}`}
              playsInline
              muted={!soundEnabled}
              loop
              preload={idx === activeIndex ? 'auto' : 'metadata'}
              controls={false}
              aria-label="Clip video"
              onLoadedData={() => {
                setSlideState((s) => ({ ...s, [item.replay_id]: { ...(s[item.replay_id] ?? {}), videoReady: true } }));
              }}
              onError={() => {
                if (videoLoadFailed.current.has(item.replay_id)) return;
                videoLoadFailed.current.add(item.replay_id);
                setSlideState((s) => ({ ...s, [item.replay_id]: { ...(s[item.replay_id] ?? {}), videoReady: false } }));
                apiFetch('/api/events/track', {
                  method: 'POST',
                  body: JSON.stringify({
                    type: 'video_load_fail',
                    source: 'play',
                    meta: {
                      replay_id: item.replay_id,
                      url: item.vertical_mp4_url ?? null,
                      mode,
                      sort,
                      feed_algo: feedAlgo,
                      hero_variant: heroFeedVariant,
                    },
                  }),
                }).catch(() => {
                  // best-effort
                });
                if (idx === activeIndex) toast.error(lang === 'ko' ? '비디오 로드 실패' : 'Video failed to load');
              }}
              onTimeUpdate={(e) => {
                if (!isActive) return;
                const v = e.currentTarget;
                handleHudTime(v, item.replay_id);

                if (completed.current.has(item.replay_id)) return;
                const dur = v.duration;
                if (!Number.isFinite(dur) || dur <= 0) return;
                const ratio = v.currentTime / dur;
                if (ratio < 0.8) return;
                completed.current.add(item.replay_id);
                trackEventMutation.mutate({ replayId: item.replay_id, type: 'completion' });
              }}
            />
          ) : null}

          <ScrimOverlay />
        </div>

        {isActive && reactionBurst ? (
          <ReactionBurst reaction={reactionBurst.reaction} burstKey={reactionBurst.key} reduceMotion={reduceMotion} />
        ) : null}

        {showHud ? (
          <div className={chromeAnim}>
            <div className="absolute left-3 z-20 pointer-events-none" style={{ top: `calc(env(safe-area-inset-top) + 72px)` }}>
              <div className="flex flex-col gap-2">
                <div
                  data-testid="clip-hud-outcome"
                  className={`nl-pop-in text-fg font-black tracking-tight leading-none text-xl px-3 py-2 rounded-2xl border backdrop-blur ${
                    activeHud.outcome === 'win'
                      ? 'bg-success-500/22 border-success-500/25'
                      : activeHud.outcome === 'loss'
                        ? 'bg-danger-500/22 border-danger-500/25'
                        : 'bg-surface-1/45 border-border/12'
                  }`}
                >
                  {activeHud.outcome === 'win' ? 'WIN' : activeHud.outcome === 'loss' ? 'LOSE' : 'DRAW'}
                </div>

                {activeHud.winnerHpPct != null ? (
                  <div className="w-[168px] bg-surface-1/45 border border-border/12 rounded-2xl p-2 backdrop-blur">
                    <div className="flex items-center justify-between text-[10px] text-fg/80 font-bold">
                      <span>{lang === 'ko' ? '남은 HP' : 'HP left'}</span>
                      <span className="nl-tabular-nums">{Math.round(activeHud.winnerHpPct * 100)}%</span>
                    </div>
                    <div className="mt-1 h-2 rounded-full bg-white/10 overflow-hidden">
                      <div
                        className={`h-full ${
                          activeHud.outcome === 'win'
                            ? 'bg-success-500'
                            : activeHud.outcome === 'loss'
                              ? 'bg-danger-500'
                              : 'bg-fg/60'
                        }`}
                        style={{ width: `${Math.round(activeHud.winnerHpPct * 100)}%` }}
                      />
                    </div>
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-1">
                  {activeHud.hasKill ? (
                    <span className="text-[10px] font-black px-2 py-1 rounded-full bg-surface-1/45 text-fg border border-border/10">
                      KILL
                    </span>
                  ) : null}
                  {activeHud.hasCrit ? (
                    <span className="text-[10px] font-black px-2 py-1 rounded-full bg-surface-1/45 text-fg border border-border/10">
                      CRIT
                    </span>
                  ) : null}
                  {activeHud.hasSynergy ? (
                    <span className="text-[10px] font-black px-2 py-1 rounded-full bg-surface-1/45 text-fg border border-border/10">
                      SYNERGY
                    </span>
                  ) : null}
                </div>
              </div>
            </div>

            {hudFlash ? (
              <div className="absolute inset-0 z-20 pointer-events-none flex items-center justify-center">
                <div
                  className={`nl-hud-flash ${
                    hudFlash.tone === 'kill'
                      ? 'text-red-100'
                      : hudFlash.tone === 'crit'
                        ? 'text-yellow-100'
                        : 'text-violet-100'
                  }`}
                >
                  {hudFlash.label}
                </div>
              </div>
            ) : null}

            {damageFloats.length ? (
              <div className="absolute inset-0 z-20 pointer-events-none">
                {damageFloats.map((d) => (
                  <div
                    key={d.id}
                    className={`nl-dmg-float text-3xl font-black ${d.crit ? 'text-yellow-200' : 'text-white'} nl-tabular-nums`}
                    style={{
                      left: `calc(50% + ${d.x}px)`,
                      top: `calc(45% + ${d.y}px)`,
                    }}
                  >
                    {d.amount}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className={`absolute bottom-0 left-0 right-0 z-10 p-4 flex items-end justify-between gap-6 ${safeBottomPad} ${chromeAnim}`}>
          <div className="max-w-[70%] space-y-2">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => navigate(`/profile/${encodeURIComponent(item.author.user_id)}?mode=${encodeURIComponent(item.mode)}`)}
                className="pointer-events-auto text-fg font-bold hover:underline nl-video-text"
              >
                {item.author.display_name}
              </button>
              <Badge variant="neutral" className="bg-surface-1/40 text-fg border-border/10">
                {item.mode}
              </Badge>
            </div>
            <div className="text-fg text-lg font-extrabold leading-tight nl-video-text">
              {item.blueprint_name ?? 'Untitled Build'}
            </div>
            <div className="flex items-center gap-2">
              <CreatureSilhouettes seed={item.replay_id} count={item.mode === 'team' ? 3 : 1} />
              {item.hero ? (
                <Badge
                  data-testid="hero-badge"
                  variant="neutral"
                  className="bg-brand-500/15 text-fg border-brand-500/25 text-[10px]"
                >
                  HERO
                </Badge>
              ) : item.featured ? (
                <Badge variant="neutral" className="bg-surface-1/40 text-fg border-border/10 text-[10px]">
                  Featured
                </Badge>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1">
              {(item.tags ?? []).slice(0, 4).map((tag) => (
                <Badge key={tag} variant="neutral" className="bg-surface-1/35 text-fg border-border/10 text-[10px]">
                  {tag}
                </Badge>
              ))}
            </div>
            {item.best_clip_status !== 'ready' ? (
              <div className="text-xs text-fg/70 nl-video-text">
                {item.best_clip_status === 'rendering' ? 'Rendering best clip…' : 'Best clip not ready yet.'}
              </div>
            ) : null}
            <div className="text-[11px] text-fg/60 nl-tabular-nums nl-video-text">
              views {item.stats.views} · shares {item.stats.shares} · forks {item.stats.forks}
            </div>
            <div className="pt-2 space-y-2 pointer-events-auto">
              <Button
                type="button"
                size="lg"
                variant="primary"
                className={`w-full rounded-2xl ${isActive && ftueOpen ? 'animate-pulse-slow' : ''}`}
                onClick={() => {
                  tapJuice();
                  navigate(`/beat?replay_id=${encodeURIComponent(item.replay_id)}&src=clip_view`);
                }}
                aria-label="Beat This"
              >
                <Icon icon={Zap} size={20} />
                <span className="ml-2">{lang === 'ko' ? 'Beat This (도전)' : 'Beat This'}</span>
              </Button>
              <Button
                type="button"
                size="lg"
                variant="secondary"
                className="w-full rounded-2xl bg-surface-1/40 text-fg border-border/12 hover:bg-surface-1/50"
                onClick={() => {
                  tapJuice();
                  apiFetch('/api/events/track', {
                    method: 'POST',
                    body: JSON.stringify({
                      type: 'quick_remix_click',
                      source: 'play',
                      meta: { replay_id: item.replay_id, mode: item.mode, sort, feed_algo: feedAlgo },
                    }),
                  }).catch(() => {
                    // best-effort
                  });
                  setQuickRemixOpen(true);
                }}
                aria-label="Quick Remix"
                disabled={!item.replay_id}
              >
                <Icon icon={Wand2} size={20} />
                <span className="ml-2">{lang === 'ko' ? 'Quick Remix (프리셋)' : 'Quick Remix'}</span>
              </Button>
            </div>
          </div>

          <div className="flex flex-col items-center gap-3 pb-2 pointer-events-auto">
            <Button
              type="button"
              size="icon"
              variant={liked ? 'primary' : 'secondary'}
              className="rounded-full"
              onClick={() => {
                tapJuice();
                likeMutation.mutate(item);
              }}
              aria-label="Like clip"
            >
              <Icon icon={Heart} size={20} filled={liked} className={liked ? 'text-black' : ''} />
            </Button>
            <div className="text-fg/80 text-[11px] font-bold nl-tabular-nums nl-video-text">{likes}</div>

            <Button
              type="button"
              size="icon"
              variant="secondary"
              className="rounded-full"
              onClick={() => {
                tapJuice();
                setRepliesTab('top');
                setRepliesOpen(true);
              }}
              aria-label="Replies (view reply chain)"
            >
              <Icon icon={MessageCircle} size={20} />
            </Button>
            <div className="text-fg/80 text-[11px] font-bold nl-video-text">Replies</div>

            <Button
              type="button"
              size="icon"
              variant="secondary"
              className="rounded-full"
              onClick={() => {
                tapJuice();
                shareMutation.mutate(item);
              }}
              aria-label="Copy share link"
            >
              <Icon icon={Share2} size={20} />
            </Button>
            <div className="text-fg/80 text-[11px] font-bold nl-tabular-nums nl-video-text">
              {item.stats.shares}
            </div>
          </div>
        </div>

        {idx === clips.length - 2 && hasNextPage ? (
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10">
            <Badge variant="neutral" className="bg-surface-1/45 text-fg border-border/10">
              Loading more…
            </Badge>
          </div>
        ) : null}
      </div>
    );
  };

  const chromeAnim = `transition-[opacity,transform] duration-[var(--nl-dur)] ease-[var(--nl-ease-out)] ${
    playChromeHidden ? 'opacity-0 pointer-events-none -translate-y-2' : 'opacity-100 pointer-events-auto translate-y-0'
  }`;

  return (
    <>
      <div className="relative h-[100dvh] bg-bg overflow-hidden overscroll-none">
        <div className={`absolute top-0 left-0 right-0 z-20 px-4 pt-[calc(env(safe-area-inset-top)+12px)] pb-3 ${chromeAnim}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="text-fg font-extrabold tracking-tight nl-video-text">{title}</div>
              <Badge variant="neutral" className="bg-surface-1/35 text-fg border-border/10">
                {mode}
              </Badge>
              <Badge variant="neutral" className="bg-surface-1/35 text-fg border-border/10">
                {sort}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="icon"
                variant="secondary"
                className="bg-surface-1/35 text-fg border-border/12 hover:bg-surface-1/45 rounded-full"
	                onClick={() => {
	                  const next = !soundEnabled;
	                  setSoundEnabled(next);
	                  if (next) trackPlayUiEvent('unmute_click', { via: 'button', replay_id: activeClip?.replay_id ?? null });
	                  tapJuice();
	                  toast.info(
	                    next ? (lang === 'ko' ? '사운드 ON' : 'Sound on') : lang === 'ko' ? '사운드 OFF' : 'Sound off'
	                  );
                  const v = videoRefs.current[activeIndex];
                  if (v) {
                    try {
                      v.muted = !next;
                    } catch {
                      // ignore
                    }
                    if (next && v.paused) {
                      v.play().catch(() => {
                        toast.info(lang === 'ko' ? '화면을 탭해 재생하세요' : 'Tap the video to play');
	                      });
	                    }
	                  }
	                  showChrome('sound_button');
	                }}
                aria-label={soundEnabled ? 'Mute' : 'Unmute'}
              >
                <Icon icon={soundEnabled ? Volume2 : VolumeX} size={20} />
              </Button>
              <Button
                size="sm"
                variant={mode === '1v1' ? 'secondary' : 'outline'}
                className={mode === '1v1' ? 'bg-surface-1/35 border-border/12 text-fg' : 'bg-transparent border-border/12 text-fg/85'}
                onClick={() => {
                  tapJuice();
                  setMode('1v1');
                }}
                type="button"
              >
                1v1
              </Button>
              <Button
                size="sm"
                variant={mode === 'team' ? 'secondary' : 'outline'}
                className={mode === 'team' ? 'bg-surface-1/35 border-border/12 text-fg' : 'bg-transparent border-border/12 text-fg/85'}
                onClick={() => {
                  tapJuice();
                  setMode('team');
                }}
                type="button"
              >
                Team
              </Button>
              <Button
                size="sm"
                variant={sort === 'trending' ? 'secondary' : 'outline'}
                className={sort === 'trending' ? 'bg-surface-1/35 border-border/12 text-fg' : 'bg-transparent border-border/12 text-fg/85'}
                onClick={() => {
                  tapJuice();
                  setSort('trending');
                }}
                type="button"
              >
                Trending
              </Button>
              <Button
                size="sm"
                variant={sort === 'new' ? 'secondary' : 'outline'}
                className={sort === 'new' ? 'bg-surface-1/35 border-border/12 text-fg' : 'bg-transparent border-border/12 text-fg/85'}
                onClick={() => {
                  tapJuice();
                  setSort('new');
                }}
                type="button"
              >
                New
              </Button>
            </div>
          </div>

          {questCard ? (
            <button
              type="button"
              data-testid="today-quest-card"
              className={`mt-3 w-full max-w-md pointer-events-auto rounded-3xl bg-surface-1/45 border border-border/12 backdrop-blur-xl shadow-glass px-3 py-2 text-left ${
                questCard.claimableCount > 0 ? 'shadow-glow-brand border-brand-500/25' : ''
              }`}
              onClick={() => {
                tapJuice();
                setQuestsOpen(true);
                apiFetch('/api/events/track', {
                  method: 'POST',
                  body: JSON.stringify({
                    type: 'quest_viewed',
                    source: 'play',
                    meta: {
                      daily_period_key: questsToday?.daily_period_key ?? null,
                      weekly_period_key: questsToday?.weekly_period_key ?? null,
                    },
                  }),
                }).catch(() => {
                  // best-effort
                });
                showChrome();
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-black tracking-widest text-fg/80 uppercase">
                  {lang === 'ko' ? '오늘의 퀘스트' : "Today's Quests"}
                </div>
                <div className="text-[11px] nl-tabular-nums text-fg/70">
                  {questCard.completedCount}/{questCard.daily.length}
                  {questCard.claimableCount > 0 ? (
                    <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full bg-brand-500/15 border border-brand-500/20 text-fg font-black">
                      CLAIM
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="mt-1 text-sm text-fg font-extrabold truncate">{questCard.primary.quest.title}</div>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-brand-500 to-accent-500 transition-all duration-700"
                    style={{ width: `${questCard.pct * 100}%` }}
                  />
                </div>
                <div className="text-[11px] nl-tabular-nums text-fg/70">
                  {questCard.prog}/{questCard.goal}
                </div>
              </div>
            </button>
          ) : null}
        </div>

        {ftueOpen ? (
          <div className="absolute left-4 right-4 z-30 pointer-events-none" style={{ top: `calc(env(safe-area-inset-top) + 64px)` }}>
            <div className="pointer-events-auto max-w-md bg-surface-1/55 border border-border/12 rounded-3xl p-3 backdrop-blur-xl shadow-glass">
              <div className="text-fg text-sm font-extrabold tracking-tight">{lang === 'ko' ? '2분 루프' : '60s Loop'}</div>
              <div className="text-fg/80 text-xs mt-1">
                {lang === 'ko'
                  ? '클립 보기 → Beat This → 내 Reply가 원본에 추가됩니다.'
                  : 'Watch → Beat This → Your reply appears on the original.'}
              </div>
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  className="text-xs font-bold px-3 py-2 rounded-2xl bg-surface-2/40 hover:bg-surface-2/60 text-fg border border-border/10"
                  onClick={() => {
                    try {
                      localStorage.setItem(FTUE_KEY, '1');
                    } catch {
                      // ignore
                    }
                    setFtueOpen(false);
                    showChrome();
                  }}
                >
                  {lang === 'ko' ? '확인' : 'Got it'}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {clips.length === 0 ? (
          <div className="h-full flex items-center justify-center text-muted">{isFetching ? 'Loading…' : 'No clips yet.'}</div>
        ) : (
          <GesturePager
            index={clampIndex(activeIndex, clips.length)}
            count={clips.length}
            onIndexChange={handlePagerIndexChange}
            reduceMotion={reduceMotion}
            onTap={handlePagerTap}
            onSwipeAttempt={handleSwipeAttempt}
            thresholds={gestureThresholds.pager}
            renderPage={renderClipPage}
          />
	        )}
	
	        <div data-testid="active-replay-id" data-replay-id={activeClip?.replay_id ?? ''} className="sr-only" />

	        {gestureHintsOpen && !ftueOpen ? (
	          <button
	            type="button"
	            onClick={() => {
	              tapJuice();
	              dismissGestureHints();
	            }}
	            className={`absolute left-1/2 z-30 -translate-x-1/2 pointer-events-auto ${
	              reduceMotion ? 'opacity-95' : gestureHintsFading ? 'opacity-0' : 'opacity-100'
	            } transition-opacity duration-300 ease-out bottom-[calc(var(--nl-tabbar-h)+env(safe-area-inset-bottom)+14px)]`}
	            aria-label={lang === 'ko' ? '제스처 힌트 닫기' : 'Dismiss gesture hints'}
	          >
	            <div className="rounded-full border border-border/12 bg-surface-1/55 backdrop-blur-xl shadow-glass px-3 py-2 text-[11px] font-bold nl-video-text text-fg/80">
	              <div className="flex items-center gap-2">
	                <Icon icon={Sparkles} size={20} />
	                <span className="whitespace-nowrap">{lang === 'ko' ? '스와이프 ↑/↓' : 'Swipe ↑/↓'}</span>
	                <span className="mx-1 h-4 w-px bg-border/20" aria-hidden="true" />
	                <Icon icon={Heart} size={20} />
	                <span className="whitespace-nowrap">{lang === 'ko' ? '더블탭 = 리액션' : 'Double-tap to react'}</span>
	              </div>
	            </div>
	          </button>
	        ) : null}
	      </div>

      <BottomSheet
        open={questsOpen}
        title={lang === 'ko' ? '오늘의 퀘스트' : "Today's Quests"}
        onClose={() => setQuestsOpen(false)}
      >
        <div className="space-y-3">
          {(questsToday?.daily ?? []).map((a) => {
            const goal = Math.max(1, Number(a.quest.goal_count ?? 1));
            const prog = Math.max(0, Number(a.progress_count ?? 0));
            const pct = Math.max(0, Math.min(1, prog / goal));
            const claimed = Boolean(a.claimed_at);
            return (
              <div key={a.assignment_id} className="rounded-3xl border border-border/12 bg-surface-2/40 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-extrabold text-fg truncate">{a.quest.title}</div>
                    <div className="text-xs text-muted mt-0.5 line-clamp-2">{a.quest.description}</div>
                  </div>
                  <div className="shrink-0 text-[11px] font-mono text-fg/70">
                    {prog}/{goal}
                  </div>
                </div>
                <div className="mt-2 h-2 w-full rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-brand-500 to-accent-500 transition-all duration-700"
                    style={{ width: `${pct * 100}%` }}
                  />
                </div>
                <div className="mt-2 flex items-center justify-between gap-3">
                  {claimed ? (
                    <span className="text-xs font-bold text-muted">Claimed</span>
                  ) : a.claimable ? (
                    <span className="text-xs font-bold text-success-500">Ready!</span>
                  ) : (
                    <span className="text-xs font-bold text-muted">In progress</span>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant={a.claimable ? 'primary' : 'secondary'}
                    disabled={claimed || !a.claimable || claimQuestMutation.isPending}
                    onClick={() => {
                      tapJuice();
                      claimQuestMutation.mutate(a);
                    }}
                  >
                    {claimed ? 'Claimed' : a.claimable ? (lang === 'ko' ? '보상 받기' : 'Claim') : lang === 'ko' ? '진행 중' : 'Progress'}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </BottomSheet>

      <BottomSheet open={quickRemixOpen} title="Quick Remix" onClose={() => setQuickRemixOpen(false)}>
        {activeClip ? (
          <div className="space-y-3">
            <div className="text-sm text-muted">
              Pick a preset to apply minimal tweaks to the original build, then start a “Beat This” challenge.
            </div>
            <div className="grid grid-cols-1 gap-2">
              <Button
                variant="primary"
                onClick={() => {
                  tapJuice();
                  setQuickRemixOpen(false);
                  navigate(`/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view&qr=survivability`);
                }}
              >
                Tankier (survivability)
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  tapJuice();
                  setQuickRemixOpen(false);
                  navigate(`/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view&qr=damage`);
                }}
              >
                Melt Faster (damage)
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  tapJuice();
                  setQuickRemixOpen(false);
                  navigate(`/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view&qr=counter`);
                }}
              >
                Counter-first (counter)
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  tapJuice();
                  setQuickRemixOpen(false);
                  navigate(`/beat?replay_id=${encodeURIComponent(activeClip.replay_id)}&src=clip_view`);
                }}
              >
                Just Beat This (no remix)
              </Button>
            </div>
          </div>
        ) : null}
      </BottomSheet>

      <BottomSheet open={repliesOpen} title="Replies" onClose={() => setRepliesOpen(false)}>
        {activeClip ? (
          <>
            <div className="flex gap-2 pb-3">
              <Button size="sm" variant={repliesTab === 'top' ? 'primary' : 'secondary'} onClick={() => setRepliesTab('top')}>
                Top Replies
              </Button>
              <Button size="sm" variant={repliesTab === 'recent' ? 'primary' : 'secondary'} onClick={() => setRepliesTab('recent')}>
                Recent
              </Button>
            </div>
            <div className="max-h-[70vh] overflow-auto">
              {repliesFetching ? <div className="text-sm text-muted py-3">Loading…</div> : null}
              {repliesError ? <div className="text-sm text-danger-500 py-3 break-words">{String(repliesError)}</div> : null}
              {repliesData?.items?.length ? (
                <div className="space-y-2">
                  {repliesData.items.map((r, i) => (
                    <button
                      key={r.reply_replay_id}
                      type="button"
                      className="w-full text-left bg-surface-2/35 border border-border/12 rounded-3xl overflow-hidden hover:bg-surface-2/45 transition-colors shadow-glass"
                      onClick={() => {
                        setRepliesOpen(false);
                        navigate(`/replay/${encodeURIComponent(r.match_id)}?reply_to=${encodeURIComponent(activeClip.replay_id)}`);
                      }}
                    >
                      <div className="flex gap-3 p-3">
                        <img
                          src={`/s/clip/${encodeURIComponent(r.reply_replay_id)}/thumb.png`}
                          alt="Reply thumbnail"
                          className="w-20 h-14 rounded-2xl border border-border/12 object-cover bg-surface-3/40"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            {repliesTab === 'top' ? (
                              <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-brand-500 text-black">
                                #{i + 1}
                              </span>
                            ) : null}
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                r.outcome === 'win'
                                  ? 'bg-success-500/15 text-success-500 border border-success-500/25'
                                  : r.outcome === 'loss'
                                  ? 'bg-danger-500/15 text-danger-500 border border-danger-500/25'
                                  : 'bg-surface-2/70 text-fg/75 border border-border/10'
                              }`}
                            >
                              {r.outcome.toUpperCase()}
                            </span>
                            <div className="text-sm font-semibold text-fg truncate">{r.challenger_display_name ?? 'Guest'}</div>
                          </div>
                          <div className="text-xs text-muted mt-1 truncate">{r.blueprint_name ?? 'Starter Build'}</div>
                          <div className="text-[11px] text-muted mt-2">
                            👍 {r.reactions?.up ?? 0} · 😂 {r.reactions?.lol ?? 0} · 🤯 {r.reactions?.wow ?? 0} · shares{' '}
                            {r.shares ?? 0}
                          </div>
                          <div className="text-[11px] text-muted">fork depth {r.lineage?.fork_depth ?? 0}</div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : !repliesFetching && !repliesError ? (
                <div className="text-sm text-muted py-3">No replies yet.</div>
              ) : null}
            </div>
          </>
        ) : null}
      </BottomSheet>
    </>
  );
};
