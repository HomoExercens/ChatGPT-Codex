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

export function GesturePager(props: {
  index: number;
  count: number;
  onIndexChange: (nextIndex: number) => void;
  reduceMotion: boolean;
  className?: string;
  pageClassName?: string;
  renderPage: (index: number) => React.ReactNode;
  onTap?: () => void;
}) {
  const { index, count, onIndexChange, reduceMotion, className, pageClassName, renderPage, onTap } = props;
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const startRef = React.useRef<{ y: number; t: number; moved: boolean; lastY: number } | null>(null);
  const pendingIndex = React.useRef<number | null>(null);

  const [dragY, setDragY] = React.useState(0);
  const [animating, setAnimating] = React.useState(false);

  const heightRef = React.useRef(0);

  React.useEffect(() => {
    pendingIndex.current = null;
    setAnimating(false);
    setDragY(0);
  }, [count]);

  const measure = () => {
    const h = containerRef.current?.clientHeight ?? 0;
    heightRef.current = h > 0 ? h : heightRef.current;
    return heightRef.current;
  };

  const settle = (next: number | null) => {
    const h = measure();
    pendingIndex.current = next;
    if (next === null) {
      if (Math.abs(dragY) < 1) {
        setAnimating(false);
        setDragY(0);
        return;
      }
      setAnimating(true);
      setDragY(0);
      return;
    }
    setAnimating(true);
    if (next > index) setDragY(-h);
    else if (next < index) setDragY(h);
    else setDragY(0);
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (animating) return;
    if (count <= 1) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (isInteractiveTarget(e.target)) return;
    const h = measure();
    if (!h) return;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    startRef.current = { y: e.clientY, lastY: e.clientY, t: performance.now(), moved: false };
    setDragY(0);
    setAnimating(false);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = startRef.current;
    if (!st || animating) return;
    const dyRaw = e.clientY - st.y;
    st.lastY = e.clientY;
    if (!st.moved && Math.abs(dyRaw) > 8) st.moved = true;

    let dy = dyRaw;
    if (index === 0 && dy > 0) dy *= 0.35;
    if (index === count - 1 && dy < 0) dy *= 0.35;
    setDragY(dy);
  };

  const onPointerUp = () => {
    const st = startRef.current;
    startRef.current = null;
    if (!st) return;

    const h = measure();
    const dt = Math.max(1, performance.now() - st.t);
    const dy = dragY;
    const v = dy / dt; // px/ms

    // Tap (no meaningful movement).
    if (!st.moved) {
      onTap?.();
      pendingIndex.current = null;
      setAnimating(false);
      setDragY(0);
      return;
    }

    const threshold = Math.max(64, Math.round(h * 0.18));
    const vThreshold = 0.65;

    const wantsNext = dy < -threshold || v < -vThreshold;
    const wantsPrev = dy > threshold || v > vThreshold;

    if (wantsNext) settle(clampIndex(index + 1, count));
    else if (wantsPrev) settle(clampIndex(index - 1, count));
    else settle(null);
  };

  const onPointerCancel = () => {
    startRef.current = null;
    if (Math.abs(dragY) < 1) {
      pendingIndex.current = null;
      setAnimating(false);
      setDragY(0);
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
      className={cn('relative h-full w-full overflow-hidden touch-none', className)}
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
