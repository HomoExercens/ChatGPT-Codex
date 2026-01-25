import React from 'react';
import { cn } from '../lib/cn';

function clampIndex(idx: number, total: number) {
  return Math.max(0, Math.min(total - 1, idx));
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(
    target.closest(
      'button, a, input, textarea, select, summary, [role="button"], [role="link"], [data-gesture-ignore="true"]'
    )
  );
}

type TapInfo = {
  clientX: number;
  clientY: number;
};

export type SwipeAttemptInfo = {
  dx: number;
  dy: number;
  velocity: number;
  directionCandidate: 'next' | 'prev';
  committed: boolean;
  cancelReason: string | null;
};

export type GesturePagerThresholds = {
  tapSlopPx: number;
  dragStartPx: number;
  verticalDominance: number;
  swipeCommitFrac: number;
  swipeCommitMinPx: number;
  swipeVelocityPxMs: number;
};

export function GesturePager(props: {
  index: number;
  count: number;
  onIndexChange: (nextIndex: number) => void;
  reduceMotion: boolean;
  className?: string;
  pageClassName?: string;
  renderPage: (index: number) => React.ReactNode;
  onTap?: (info: TapInfo) => void;
  onSwipeAttempt?: (info: SwipeAttemptInfo) => void;
  thresholds?: Partial<GesturePagerThresholds>;
}) {
  const { index, count, onIndexChange, reduceMotion, className, pageClassName, renderPage, onTap, onSwipeAttempt } =
    props;
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const startRef = React.useRef<{
    x0: number;
    y0: number;
    t0: number;
    lastX: number;
    lastY: number;
    lastT: number;
    dragging: boolean;
    canceled: boolean;
    cancelReason: string | null;
  } | null>(null);
  const pendingIndex = React.useRef<number | null>(null);

  const [dragY, setDragY] = React.useState(0);
  const [animating, setAnimating] = React.useState(false);
  const dragYRef = React.useRef(0);

  const heightRef = React.useRef(0);

  const PRESS_PULSE_MS = 120;
  const [pressPulse, setPressPulse] = React.useState(false);
  const pressPulseTimerRef = React.useRef<number | null>(null);

  const n = (value: unknown, fallback: number) =>
    typeof value === 'number' && Number.isFinite(value) ? value : fallback;

  const clearPressPulse = React.useCallback(() => {
    if (pressPulseTimerRef.current) {
      window.clearTimeout(pressPulseTimerRef.current);
      pressPulseTimerRef.current = null;
    }
    setPressPulse(false);
  }, []);

  React.useEffect(() => {
    pendingIndex.current = null;
    setAnimating(false);
    setDragY(0);
    dragYRef.current = 0;
  }, [count]);

  React.useEffect(() => clearPressPulse, [clearPressPulse]);

  const measure = () => {
    const h = containerRef.current?.clientHeight ?? 0;
    heightRef.current = h > 0 ? h : heightRef.current;
    return heightRef.current;
  };

  const settle = (next: number | null) => {
    const h = measure();
    pendingIndex.current = next;
    if (next === null) {
      if (Math.abs(dragYRef.current) < 1) {
        setAnimating(false);
        setDragY(0);
        dragYRef.current = 0;
        return;
      }
      setAnimating(true);
      setDragY(0);
      dragYRef.current = 0;
      return;
    }
    setAnimating(true);
    if (next > index) setDragY(-h);
    else if (next < index) setDragY(h);
    else setDragY(0);
    dragYRef.current = next > index ? -h : next < index ? h : 0;
  };

  const TAP_SLOP_PX = n(props.thresholds?.tapSlopPx, 10);
  const DRAG_START_PX = n(props.thresholds?.dragStartPx, 12);
  const VERTICAL_DOMINANCE = n(props.thresholds?.verticalDominance, 1.2);
  const SWIPE_COMMIT_FRAC = n(props.thresholds?.swipeCommitFrac, 0.18);
  const SWIPE_COMMIT_MIN_PX = n(props.thresholds?.swipeCommitMinPx, 64);
  const SWIPE_VELOCITY_PX_MS = n(props.thresholds?.swipeVelocityPxMs, 0.65);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (animating) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (isInteractiveTarget(e.target)) return;
    const h = measure();
    if (!h) return;
    clearPressPulse();
    setPressPulse(true);
    pressPulseTimerRef.current = window.setTimeout(() => {
      pressPulseTimerRef.current = null;
      setPressPulse(false);
    }, PRESS_PULSE_MS);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    startRef.current = {
      x0: e.clientX,
      y0: e.clientY,
      t0: now,
      lastX: e.clientX,
      lastY: e.clientY,
      lastT: now,
      dragging: false,
      canceled: false,
      cancelReason: null,
    };
    setDragY(0);
    dragYRef.current = 0;
    setAnimating(false);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = startRef.current;
    if (!st || animating) return;
    if (st.canceled) return;
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    st.lastX = e.clientX;
    st.lastY = e.clientY;
    st.lastT = now;

    const dxRaw = e.clientX - st.x0;
    const dyRaw = e.clientY - st.y0;
    const dxAbs = Math.abs(dxRaw);
    const dyAbs = Math.abs(dyRaw);

    // Don't lock into a swipe until the user has moved beyond slop.
    if (!st.dragging) {
      if (dxAbs < TAP_SLOP_PX && dyAbs < TAP_SLOP_PX) return;
      clearPressPulse();

      // Prefer vertical pager; ignore obvious horizontal drags.
      if (dxAbs >= DRAG_START_PX && dxAbs >= dyAbs * VERTICAL_DOMINANCE) {
        st.canceled = true;
        st.cancelReason = 'horizontal_dominance';
        setDragY(0);
        dragYRef.current = 0;
        return;
      }

      // Start vertical drag once it dominates.
      const looksVertical = dyAbs >= DRAG_START_PX && (dyAbs >= dxAbs * VERTICAL_DOMINANCE || dyAbs > dxAbs);
      if (!looksVertical) return;
      st.dragging = true;
    }

    let dy = dyRaw;
    if (index === 0 && dy > 0) dy *= 0.35;
    if (index === count - 1 && dy < 0) dy *= 0.35;
    setDragY(dy);
    dragYRef.current = dy;
  };

  const onPointerUp = () => {
    const st = startRef.current;
    startRef.current = null;
    clearPressPulse();
    if (!st) return;
    if (st.canceled) {
      const dx = st.lastX - st.x0;
      const dy = st.lastY - st.y0;
      const dt = Math.max(1, st.lastT - st.t0);
      const directionCandidate: 'next' | 'prev' = dy < 0 ? 'next' : 'prev';
      const velocity = Math.abs(dy) / dt;
      onSwipeAttempt?.({
        dx,
        dy,
        velocity,
        directionCandidate,
        committed: false,
        cancelReason: st.cancelReason ?? 'canceled',
      });
      pendingIndex.current = null;
      setAnimating(false);
      setDragY(0);
      dragYRef.current = 0;
      return;
    }

    const h = measure();
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const dt = Math.max(1, now - st.t0);
    const dxAbs = Math.abs(st.lastX - st.x0);
    const dyAbs = Math.abs(st.lastY - st.y0);
    const dy = dragYRef.current;
    const v = dy / dt; // px/ms (avg)

    // Tap (no meaningful movement).
    if (!st.dragging && dxAbs < TAP_SLOP_PX && dyAbs < TAP_SLOP_PX) {
      onTap?.({ clientX: st.lastX, clientY: st.lastY });
      pendingIndex.current = null;
      setAnimating(false);
      setDragY(0);
      dragYRef.current = 0;
      return;
    }

    // No swipe paging when there isn't another page, but still animate back to rest.
    if (count <= 1) {
      settle(null);
      return;
    }

    const threshold = Math.max(SWIPE_COMMIT_MIN_PX, Math.round(h * SWIPE_COMMIT_FRAC));
    const vThreshold = SWIPE_VELOCITY_PX_MS;

    const wantsNext = dy < -threshold || v < -vThreshold;
    const wantsPrev = dy > threshold || v > vThreshold;

    if (st.dragging) {
      const rawDx = st.lastX - st.x0;
      const rawDy = st.lastY - st.y0;
      const directionCandidate: 'next' | 'prev' = rawDy < 0 ? 'next' : 'prev';
      const nextIndex = wantsNext
        ? clampIndex(index + 1, count)
        : wantsPrev
          ? clampIndex(index - 1, count)
          : index;
      const committedClamped = nextIndex !== index;
      const cancelReason =
        committedClamped ? null : wantsNext || wantsPrev ? 'edge_clamp' : 'threshold_not_met';
      onSwipeAttempt?.({
        dx: rawDx,
        dy: rawDy,
        velocity: Math.abs(rawDy) / dt,
        directionCandidate,
        committed: Boolean(committedClamped),
        cancelReason,
      });
    }

    if (wantsNext) settle(clampIndex(index + 1, count));
    else if (wantsPrev) settle(clampIndex(index - 1, count));
    else settle(null);
  };

  const onPointerCancel = () => {
    const st = startRef.current;
    startRef.current = null;
    clearPressPulse();
    if (st && st.dragging) {
      const dx = st.lastX - st.x0;
      const dy = st.lastY - st.y0;
      const dt = Math.max(1, st.lastT - st.t0);
      const directionCandidate: 'next' | 'prev' = dy < 0 ? 'next' : 'prev';
      const velocity = Math.abs(dy) / dt;
      onSwipeAttempt?.({
        dx,
        dy,
        velocity,
        directionCandidate,
        committed: false,
        cancelReason: 'pointer_cancelled',
      });
    }
    if (Math.abs(dragYRef.current) < 1) {
      pendingIndex.current = null;
      setAnimating(false);
      setDragY(0);
      dragYRef.current = 0;
      return;
    }
    settle(null);
  };

  const onTransitionEnd = (e: React.TransitionEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    if (!animating) return;
    const next = pendingIndex.current;
    pendingIndex.current = null;
    setAnimating(false);
    setDragY(0);
    if (next !== null && next !== index) onIndexChange(next);
  };

  const prevIdx = index > 0 ? index - 1 : null;
  const nextIdx = index + 1 < count ? index + 1 : null;

  const transition = animating
    ? reduceMotion
      ? 'transition-[transform,opacity] duration-200 ease-out'
      : 'transition-[transform,opacity] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]'
    : '';

  // Translate a 3-page stack (prev/current/next) by dragY.
  const stackStyle: React.CSSProperties = {
    transform: `translate3d(0, ${dragY}px, 0)`,
  };

  return (
    <div
      ref={containerRef}
      data-testid="gesture-pager"
      className={cn('relative h-full w-full overflow-hidden touch-none overscroll-none select-none', className)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
    >
      <div
        className={cn('absolute inset-0', transition)}
    style={stackStyle}
    onTransitionEnd={onTransitionEnd}
  >
        <div
          data-testid="press-feedback"
          data-active={pressPulse ? '1' : '0'}
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute inset-0 z-10 bg-gradient-to-b from-white/5 via-black/0 to-black/10',
            pressPulse ? 'opacity-100' : 'opacity-0',
            reduceMotion ? '' : 'transition-opacity duration-150 ease-out'
          )}
        />
        {prevIdx !== null ? (
          <div className={cn('absolute inset-0 -translate-y-full', pageClassName)}>{renderPage(prevIdx)}</div>
        ) : null}
        <div className={cn('absolute inset-0', pageClassName)}>{renderPage(index)}</div>
        {nextIdx !== null ? (
          <div className={cn('absolute inset-0 translate-y-full', pageClassName)}>{renderPage(nextIdx)}</div>
        ) : null}
      </div>
    </div>
  );
}
