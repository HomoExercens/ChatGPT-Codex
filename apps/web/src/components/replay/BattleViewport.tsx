import React, { useEffect, useMemo, useRef, useState } from 'react';

import type { Replay, ReplayUnit } from '../../api/types';
import { useSettingsStore } from '../../stores/settings';

type Props = {
  replay?: Replay;
  tick: number;
  showOverlay: boolean;
  highlightCaption?: string | null;
  isInHighlight?: boolean;
};

type RuntimeUnit = ReplayUnit & {
  hp: number;
  alive: boolean;
  death_t: number | null;
};

function clampInt(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.trunc(value)));
}

function readRgbVar(name: string, alpha: number): string {
  try {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const parts = raw
      .split(/\s+/)
      .map((v) => Number(v))
      .filter((n) => Number.isFinite(n));
    if (parts.length !== 3) return `rgba(255,255,255,${alpha})`;
    return `rgba(${parts[0]},${parts[1]},${parts[2]},${alpha})`;
  } catch {
    return `rgba(255,255,255,${alpha})`;
  }
}

function hash32(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function roundedRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.max(0, Math.min(r, Math.min(w, h) / 2));
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function laneOffsets(count: number): number[] {
  if (count <= 0) return [];
  if (count === 1) return [0];
  if (count === 2) return [-0.55, 0.55];
  if (count === 3) return [-0.85, 0, 0.85];
  const out: number[] = [];
  const mid = (count - 1) / 2;
  for (let i = 0; i < count; i++) out.push((i - mid) * 0.6);
  return out;
}

function drawRoleIcon(
  ctx: CanvasRenderingContext2D,
  role: string,
  x: number,
  y: number,
  size: number,
  color: string
): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = Math.max(1, size * 0.12);

  const r = size / 2;
  const kind = role.toLowerCase();

  if (kind.includes('tank')) {
    // Shield
    ctx.beginPath();
    ctx.moveTo(0, -r * 0.9);
    ctx.lineTo(r * 0.75, -r * 0.25);
    ctx.lineTo(r * 0.5, r * 0.75);
    ctx.lineTo(0, r);
    ctx.lineTo(-r * 0.5, r * 0.75);
    ctx.lineTo(-r * 0.75, -r * 0.25);
    ctx.closePath();
    ctx.globalAlpha = 0.95;
    ctx.fill();
  } else if (kind.includes('support')) {
    // Plus
    const w = r * 0.55;
    ctx.beginPath();
    ctx.moveTo(-w, -r * 0.12);
    ctx.lineTo(-r * 0.12, -r * 0.12);
    ctx.lineTo(-r * 0.12, -w);
    ctx.lineTo(r * 0.12, -w);
    ctx.lineTo(r * 0.12, -r * 0.12);
    ctx.lineTo(w, -r * 0.12);
    ctx.lineTo(w, r * 0.12);
    ctx.lineTo(r * 0.12, r * 0.12);
    ctx.lineTo(r * 0.12, w);
    ctx.lineTo(-r * 0.12, w);
    ctx.lineTo(-r * 0.12, r * 0.12);
    ctx.lineTo(-w, r * 0.12);
    ctx.closePath();
    ctx.globalAlpha = 0.95;
    ctx.fill();
  } else {
    // DPS: sword
    ctx.beginPath();
    ctx.moveTo(-r * 0.15, -r * 0.9);
    ctx.lineTo(r * 0.15, -r * 0.9);
    ctx.lineTo(r * 0.28, -r * 0.2);
    ctx.lineTo(r * 0.06, r * 0.2);
    ctx.lineTo(r * 0.22, r * 0.35);
    ctx.lineTo(0, r * 0.6);
    ctx.lineTo(-r * 0.22, r * 0.35);
    ctx.lineTo(-r * 0.06, r * 0.2);
    ctx.lineTo(-r * 0.28, -r * 0.2);
    ctx.closePath();
    ctx.globalAlpha = 0.95;
    ctx.fill();
  }

  ctx.restore();
}

function drawTagChip(
  ctx: CanvasRenderingContext2D,
  opts: {
    text: string;
    x: number;
    y: number;
    maxW: number;
    fill: string;
    textColor: string;
  }
): number {
  const { text, x, y, maxW, fill, textColor } = opts;
  ctx.save();
  ctx.font = '700 10px ui-sans-serif, system-ui, sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  const paddingX = 8;
  const textW = Math.min(maxW, Math.ceil(ctx.measureText(text).width));
  const w = Math.min(maxW, textW + paddingX * 2);
  const h = 18;

  roundedRectPath(ctx, x, y, w, h, 10);
  ctx.fillStyle = fill;
  ctx.fill();

  ctx.fillStyle = textColor;
  ctx.fillText(text, x + paddingX, y + h / 2 + 0.5);

  ctx.restore();
  return w;
}

function fallbackUnitsFromEvents(replay: Replay): ReplayUnit[] {
  const unitIds = new Set<string>();
  for (const e of replay.timeline_events) {
    const payload = e.payload ?? {};
    if (e.type === 'ATTACK' || e.type === 'DAMAGE' || e.type === 'HEAL') {
      const source = String(payload.source ?? '');
      const target = String(payload.target ?? '');
      if (source) unitIds.add(source);
      if (target) unitIds.add(target);
    }
    if (e.type === 'DEATH') {
      const unit = String(payload.unit ?? '');
      if (unit) unitIds.add(unit);
    }
  }
  const sorted = Array.from(unitIds).sort();
  return sorted.map((uid) => {
    const team = uid.startsWith('B') ? 'B' : 'A';
    const match = uid.match(/\d+/);
    const slotIndex = match ? clampInt(Number(match[0]) - 1, 0, 4) : 0;
    return {
      unit_id: uid,
      team,
      slot_index: slotIndex,
      formation: 'front',
      creature_id: uid,
      creature_name: uid,
      role: 'Unknown',
      tags: [],
      items: { weapon: null, armor: null, utility: null },
      max_hp: 100,
    };
  });
}

function buildRuntimeUnits(replay?: Replay, tick: number = 0): { units: RuntimeUnit[]; recent: Replay['timeline_events'] } {
  if (!replay) return { units: [], recent: [] };

  const srcUnits = replay.header.units?.length ? replay.header.units : fallbackUnitsFromEvents(replay);

  const byId = new Map<string, RuntimeUnit>();
  for (const u of srcUnits) {
    byId.set(u.unit_id, { ...u, hp: u.max_hp, alive: true, death_t: null });
  }

  const recentWindow = 24;
  const recent: Replay['timeline_events'] = [];

  for (const e of replay.timeline_events) {
    if (e.t > tick) break;
    const payload = e.payload ?? {};

    if (e.t >= tick - recentWindow) recent.push(e);

    if (e.type === 'DAMAGE') {
      const targetId = String(payload.target ?? '');
      const amount = Number(payload.amount ?? 0);
      const target = byId.get(targetId);
      if (target && Number.isFinite(amount)) {
        target.hp = clampInt(target.hp - amount, 0, target.max_hp);
        if (target.hp <= 0) target.alive = false;
      }
    }
    if (e.type === 'HEAL') {
      const targetId = String(payload.target ?? '');
      const amount = Number(payload.amount ?? 0);
      const target = byId.get(targetId);
      if (target && Number.isFinite(amount)) target.hp = clampInt(target.hp + amount, 0, target.max_hp);
    }
    if (e.type === 'DEATH') {
      const unitId = String(payload.unit ?? '');
      const target = byId.get(unitId);
      if (target) {
        target.hp = 0;
        target.alive = false;
        target.death_t = e.t;
      }
    }
    if (e.type === 'AUGMENT_TRIGGER') {
      const kind = String(payload.type ?? '');
      if (kind === 'revive') {
        const unitId = String(payload.unit ?? '');
        const hp = Number(payload.hp ?? 1);
        const target = byId.get(unitId);
        if (target) {
          target.hp = clampInt(Number.isFinite(hp) ? hp : 1, 0, target.max_hp);
          target.alive = target.hp > 0;
          target.death_t = null;
        }
      }
    }
  }

  return { units: Array.from(byId.values()), recent };
}

export const BattleViewport: React.FC<Props> = ({ replay, tick, showOverlay, highlightCaption, isInHighlight }) => {
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const cr = entry.contentRect;
        setSize({ w: Math.max(1, Math.floor(cr.width)), h: Math.max(1, Math.floor(cr.height)) });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const computed = useMemo(() => buildRuntimeUnits(replay, tick), [replay, tick]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = size.w;
    const h = size.h;
    if (!w || !h) return;

    let raf = 0;
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const bgA = readRgbVar('--nl-lab-900', 1);
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = bgA;
      ctx.fillRect(0, 0, w, h);

      const grid = ctx.createLinearGradient(0, 0, w, h);
      grid.addColorStop(0, 'rgba(255,255,255,0.06)');
      grid.addColorStop(1, 'rgba(255,255,255,0.02)');
      ctx.fillStyle = grid;
      ctx.fillRect(0, 0, w, h);

      if (isInHighlight && highlightCaption) {
        const pulse = reduceMotion ? 1 : 0.85 + 0.15 * Math.sin(tick / 3.5);
        ctx.save();
        ctx.strokeStyle = readRgbVar('--nl-brand-400', 0.55 * pulse);
        ctx.lineWidth = 4;
        ctx.shadowColor = readRgbVar('--nl-brand-500', 0.45 * pulse);
        ctx.shadowBlur = 18 * pulse;
        roundedRectPath(ctx, 8, 8, w - 16, h - 16, 22);
        ctx.stroke();
        ctx.restore();

        const padX = 18;
        const padY = 10;
        const bannerH = 46;
        ctx.save();
        ctx.globalAlpha = 1;
        roundedRectPath(ctx, padX, padY, w - padX * 2, bannerH, 16);
        ctx.fillStyle = 'rgba(2,6,23,0.55)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.14)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = 'rgba(255,255,255,0.95)';
        ctx.font = '800 14px ui-sans-serif, system-ui, sans-serif';
        ctx.fillText(highlightCaption, w / 2, padY + bannerH / 2 + 1);
        ctx.restore();
      }

      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(w / 2, 16);
      ctx.lineTo(w / 2, h - 16);
      ctx.stroke();

      const units = computed.units;
      if (!units.length) {
        ctx.fillStyle = 'rgba(255,255,255,0.65)';
        ctx.font = '600 14px ui-sans-serif, system-ui, sans-serif';
        ctx.fillText('Loading replay…', 24, 28);
        return;
      }

      const byTeam = {
        A: units.filter((u) => u.team === 'A').sort((a, b) => a.slot_index - b.slot_index),
        B: units.filter((u) => u.team === 'B').sort((a, b) => a.slot_index - b.slot_index),
      };

      const cardW = Math.min(188, Math.max(136, w * 0.21));
      const cardH = Math.min(84, Math.max(64, h * 0.15));
      const radius = 18;

      const frontX = { A: w * 0.37, B: w * 0.63 };
      const backX = { A: w * 0.23, B: w * 0.77 };
      const laneGap = Math.min(h * 0.23, cardH * 1.15);
      const centerY = h * 0.52;

      const pos = new Map<string, { x: number; y: number }>();
      (['A', 'B'] as const).forEach((team) => {
        const tUnits = byTeam[team];
        const front = tUnits.filter((u) => u.formation === 'front');
        const back = tUnits.filter((u) => u.formation === 'back');

        const frontYs = laneOffsets(front.length).map((o) => centerY + o * laneGap);
        const backYs = laneOffsets(back.length).map((o) => centerY + o * laneGap);

        for (let i = 0; i < front.length; i++) {
          pos.set(front[i].unit_id, { x: frontX[team], y: frontYs[i] ?? centerY });
        }
        for (let i = 0; i < back.length; i++) {
          pos.set(back[i].unit_id, { x: backX[team], y: backYs[i] ?? centerY });
        }
      });

      if (showOverlay) {
        for (const e of computed.recent) {
          if (e.type !== 'SYNERGY_TRIGGER') continue;
          const payload = e.payload ?? {};
          const team = String(payload.team ?? '');
          const tag = String(payload.tag ?? '');
          const threshold = Number(payload.threshold ?? 0);
          const bonus = Number(payload.bonus ?? 0);
          if (team !== 'A' && team !== 'B') continue;
          const age = tick - e.t;
          const maxAge = 22;
          if (age < 0 || age > maxAge) continue;
          const k = reduceMotion ? 1 : 1 - age / maxAge;
          const ring = Math.max(cardW, cardH) * (0.75 + (reduceMotion ? 0 : age / maxAge) * 0.75);
          ctx.strokeStyle = team === 'A' ? readRgbVar('--nl-brand-500', 0.6 * k) : readRgbVar('--nl-accent-500', 0.6 * k);
          ctx.lineWidth = 3;
          for (const u of units.filter((uu) => uu.team === team)) {
            const p = pos.get(u.unit_id);
            if (!p) continue;
            ctx.beginPath();
            ctx.ellipse(p.x, p.y, ring, ring, 0, 0, Math.PI * 2);
            ctx.stroke();
          }

          if (tag) {
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = '800 11px ui-sans-serif, system-ui, sans-serif';
            ctx.fillStyle = 'rgba(255,255,255,0.92)';
            ctx.shadowColor = 'rgba(0,0,0,0.35)';
            ctx.shadowBlur = 10;
            const tier = Number.isFinite(threshold) && threshold > 0 ? ` T${Math.round(threshold)}` : '';
            const b = Number.isFinite(bonus) && bonus > 0 ? ' +Sigil' : '';
            ctx.fillText(`${tag}${tier} Online${b}`, w / 2, h - 18);
            ctx.restore();
          }
        }

        for (const e of computed.recent) {
          if (e.type !== 'ATTACK') continue;
          const payload = e.payload ?? {};
          const source = String(payload.source ?? '');
          const target = String(payload.target ?? '');
          const crit = Boolean(payload.crit ?? false);
          const ps = pos.get(source);
          const pt = pos.get(target);
          if (!ps || !pt) continue;
          const age = tick - e.t;
          const maxAge = 10;
          if (age < 0 || age > maxAge) continue;
          const alpha = reduceMotion ? 0.7 : 0.7 * (1 - age / maxAge);

          ctx.save();
          ctx.strokeStyle = crit ? `rgba(245,158,11,${alpha})` : `rgba(255,255,255,${alpha})`;
          ctx.lineWidth = crit ? 3 : 2;
          ctx.shadowColor = crit ? `rgba(245,158,11,${alpha})` : `rgba(255,255,255,${alpha})`;
          ctx.shadowBlur = crit ? 14 : 8;
          ctx.beginPath();
          ctx.moveTo(ps.x, ps.y);
          ctx.lineTo(pt.x, pt.y);
          ctx.stroke();
          ctx.restore();
        }

        for (const e of computed.recent) {
          if (e.type !== 'DAMAGE' && e.type !== 'HEAL') continue;
          const payload = e.payload ?? {};
          const target = String(payload.target ?? '');
          const amount = Math.max(0, Number(payload.amount ?? 0));
          const pt = pos.get(target);
          if (!pt || !Number.isFinite(amount) || amount <= 0) continue;
          const age = tick - e.t;
          const maxAge = 14;
          if (age < 0 || age > maxAge) continue;
          const dy = reduceMotion ? 0 : -age * 1.8;
          const alpha = reduceMotion ? 0.95 : 0.95 * (1 - age / maxAge);

          const label = `${e.type === 'DAMAGE' ? '−' : '+'}${Math.round(amount)}`;
          ctx.save();
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.font = `900 ${e.type === 'DAMAGE' ? 18 : 16}px ui-sans-serif, system-ui, sans-serif`;

          const tw = ctx.measureText(label).width;
          const bubbleW = Math.max(34, Math.min(64, tw + 20));
          const bubbleH = 26;
          const bx = pt.x - bubbleW / 2;
          const by = pt.y + dy - cardH * 0.62 - bubbleH / 2;

          ctx.globalAlpha = alpha;
          roundedRectPath(ctx, bx, by, bubbleW, bubbleH, 14);
          ctx.fillStyle = 'rgba(2,6,23,0.52)';
          ctx.fill();

          ctx.strokeStyle = e.type === 'DAMAGE' ? `rgba(248,113,113,${alpha})` : `rgba(74,222,128,${alpha})`;
          ctx.lineWidth = 1;
          ctx.stroke();

          ctx.fillStyle = e.type === 'DAMAGE' ? `rgba(248,113,113,${alpha})` : `rgba(74,222,128,${alpha})`;
          ctx.shadowColor = 'rgba(0,0,0,0.35)';
          ctx.shadowBlur = 12;
          ctx.fillText(label, pt.x, pt.y + dy - cardH * 0.62);
          ctx.restore();
        }
      }

      for (const u of units) {
        const p = pos.get(u.unit_id);
        if (!p) continue;

        const x = p.x - cardW / 2;
        const y = p.y - cardH / 2;
        const fill = u.team === 'A' ? readRgbVar('--nl-brand-600', 0.86) : readRgbVar('--nl-accent-500', 0.82);
        const deadAlpha = u.alive ? 1 : 0.28;

        ctx.save();
        ctx.globalAlpha = 1;
        roundedRectPath(ctx, x, y, cardW, cardH, radius);
        ctx.fillStyle = 'rgba(2,6,23,0.22)';
        ctx.fill();
        ctx.restore();

        ctx.save();
        ctx.globalAlpha = u.alive ? 1 : deadAlpha;
        roundedRectPath(ctx, x, y, cardW, cardH, radius);
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.14)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Portrait
        const portraitR = Math.min(20, cardH * 0.34);
        const px = x + 16 + portraitR;
        const py = y + 18 + portraitR;
        const h32 = hash32(u.creature_id || u.unit_id);
        const vars = ['--nl-brand-500', '--nl-brand-400', '--nl-accent-500', '--nl-accent-700', '--nl-brand-700', '--nl-brand-300'];
        const aVar = vars[h32 % vars.length];
        const bVar = vars[(h32 >>> 8) % vars.length];
        const g = ctx.createRadialGradient(px - portraitR * 0.25, py - portraitR * 0.25, portraitR * 0.25, px, py, portraitR);
        g.addColorStop(0, readRgbVar(aVar, 0.95));
        g.addColorStop(1, readRgbVar(bVar, 0.85));
        ctx.beginPath();
        ctx.ellipse(px, py, portraitR, portraitR, 0, 0, Math.PI * 2);
        ctx.fillStyle = g;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.22)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Initial letter
        const initial = (u.creature_name || u.creature_id || 'U').trim().slice(0, 1).toUpperCase();
        ctx.fillStyle = 'rgba(255,255,255,0.92)';
        ctx.font = `900 ${Math.floor(portraitR * 0.9)}px ui-sans-serif, system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(initial, px, py + 1);

        // Name
        ctx.fillStyle = 'rgba(255,255,255,0.94)';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'alphabetic';
        ctx.font = '800 13px ui-sans-serif, system-ui, sans-serif';
        ctx.fillText(u.creature_name, x + 16 + portraitR * 2 + 12, y + 22);

        // Role icon + text
        const roleColor = 'rgba(255,255,255,0.88)';
        const iconSize = 14;
        drawRoleIcon(ctx, u.role, x + 16 + portraitR * 2 + 18, y + 38, iconSize, roleColor);
        ctx.fillStyle = 'rgba(255,255,255,0.78)';
        ctx.font = '700 11px ui-sans-serif, system-ui, sans-serif';
        ctx.fillText(u.role, x + 16 + portraitR * 2 + 30, y + 41);

        // Tags
        const tags = (u.tags ?? []).slice(0, 2).map((tt) => String(tt));
        let chipX = x + 16 + portraitR * 2 + 12;
        const chipY = y + cardH - 40;
        for (const tag of tags) {
          const wChip = drawTagChip(ctx, {
            text: tag,
            x: chipX,
            y: chipY,
            maxW: Math.max(56, cardW * 0.34),
            fill: 'rgba(2,6,23,0.35)',
            textColor: 'rgba(255,255,255,0.86)',
          });
          chipX += wChip + 6;
        }

        if (showOverlay) {
          const hpRatio = u.max_hp ? u.hp / u.max_hp : 0;
          const barX = x + 16;
          const barY = y + cardH - 16;
          const barW = cardW - 32;
          const barH = 7;

          roundedRectPath(ctx, barX, barY, barW, barH, 8);
          ctx.fillStyle = 'rgba(2,6,23,0.35)';
          ctx.fill();

          const hpW = barW * Math.max(0, Math.min(1, hpRatio));
          roundedRectPath(ctx, barX, barY, hpW, barH, 8);
          ctx.fillStyle = u.team === 'A' ? 'rgba(34,197,94,0.96)' : 'rgba(16,185,129,0.96)';
          ctx.fill();

          ctx.fillStyle = 'rgba(255,255,255,0.9)';
          ctx.font = '800 10px ui-monospace, SFMono-Regular, monospace';
          ctx.textAlign = 'right';
          ctx.fillText(`${u.hp}/${u.max_hp}`, x + cardW - 14, y + cardH - 20);
        }

        if (!u.alive) {
          ctx.globalAlpha = 1;
          roundedRectPath(ctx, x, y, cardW, cardH, radius);
          ctx.fillStyle = 'rgba(2,6,23,0.32)';
          ctx.fill();

          ctx.strokeStyle = 'rgba(255,255,255,0.32)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(x + 18, y + 18);
          ctx.lineTo(x + cardW - 18, y + cardH - 18);
          ctx.moveTo(x + cardW - 18, y + 18);
          ctx.lineTo(x + 18, y + cardH - 18);
          ctx.stroke();
        }

        ctx.restore();
      }
    };

    raf = window.requestAnimationFrame(draw);
    return () => window.cancelAnimationFrame(raf);
  }, [computed.recent, computed.units, highlightCaption, isInHighlight, reduceMotion, replay?.digest, showOverlay, size.h, size.w, tick]);

  return (
    <div ref={containerRef} className="absolute inset-0">
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
};
