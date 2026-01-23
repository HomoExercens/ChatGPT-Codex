import { useSettingsStore } from '../stores/settings';

type SfxKind = 'click' | 'success' | 'fail';

let audioCtx: AudioContext | null = null;

function getAudioCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Ctx = window.AudioContext || (window as any).webkitAudioContext;
  if (!Ctx) return null;
  if (!audioCtx) audioCtx = new Ctx();
  return audioCtx;
}

function beep({ freq, ms, type, gain }: { freq: number; ms: number; type: OscillatorType; gain: number }): void {
  const ctx = getAudioCtx();
  if (!ctx) return;
  const now = ctx.currentTime;

  const osc = ctx.createOscillator();
  const g = ctx.createGain();

  osc.type = type;
  osc.frequency.setValueAtTime(freq, now);

  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(Math.max(0.0001, gain), now + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, now + ms / 1000);

  osc.connect(g);
  g.connect(ctx.destination);

  try {
    if (ctx.state === 'suspended') void ctx.resume();
  } catch {
    // ignore
  }

  osc.start(now);
  osc.stop(now + ms / 1000 + 0.02);
}

export function playSfx(kind: SfxKind): void {
  const { soundEnabled, reduceMotion } = useSettingsStore.getState();
  if (!soundEnabled) return;
  if (reduceMotion) return;

  if (kind === 'click') {
    beep({ freq: 520, ms: 60, type: 'square', gain: 0.06 });
    return;
  }
  if (kind === 'success') {
    beep({ freq: 660, ms: 90, type: 'sine', gain: 0.08 });
    beep({ freq: 990, ms: 110, type: 'sine', gain: 0.06 });
    return;
  }
  beep({ freq: 180, ms: 140, type: 'sawtooth', gain: 0.05 });
}

export function vibrate(pattern: number | number[]): void {
  const { hapticsEnabled } = useSettingsStore.getState();
  if (!hapticsEnabled) return;
  if (typeof navigator === 'undefined' || typeof navigator.vibrate !== 'function') return;
  try {
    navigator.vibrate(pattern);
  } catch {
    // ignore
  }
}

export function tapJuice(): void {
  playSfx('click');
  vibrate(12);
}

