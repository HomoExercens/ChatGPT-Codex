from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont


TICKS_PER_SEC = 20
Aspect = Literal["16:9", "9:16"]
CAPTIONS_VERSION = "capv5"

BEST_CLIP_MIN_DURATION_SEC = 6.0
BEST_CLIP_FALLBACK_DURATION_SEC = 10.0


def _safe_font(size: int, *, bold: bool) -> Any:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def clamp_clip_params(
    *,
    replay_payload: dict[str, Any],
    start_sec: float,
    end_sec: float | None,
    fps: int,
    scale: int,
    max_duration_sec: float = 12.0,
) -> tuple[int, int, int, int]:
    end_summary = replay_payload.get("end_summary") or {}
    duration_ticks = int(end_summary.get("duration_ticks") or 0)
    duration_sec = duration_ticks / TICKS_PER_SEC if duration_ticks > 0 else 0.0

    start_sec = max(0.0, float(start_sec))
    if end_sec is None:
        end_sec = min(duration_sec, start_sec + 3.0)
    end_sec = max(0.0, float(end_sec))

    if end_sec < start_sec:
        start_sec, end_sec = end_sec, start_sec

    if (end_sec - start_sec) > max_duration_sec:
        end_sec = start_sec + max_duration_sec

    start_tick = int(math.floor(start_sec * TICKS_PER_SEC))
    end_tick = int(math.floor(end_sec * TICKS_PER_SEC))

    start_tick = max(0, min(duration_ticks, start_tick))
    end_tick = max(0, min(duration_ticks, end_tick))
    if end_tick <= start_tick:
        end_tick = min(duration_ticks, start_tick + 1)

    fps = max(5, min(30, int(fps)))
    scale = max(1, min(2, int(scale)))
    return start_tick, end_tick, fps, scale


def best_clip_segment(
    replay_payload: dict[str, Any],
    *,
    max_duration_sec: float = 12.0,
    min_duration_sec: float = BEST_CLIP_MIN_DURATION_SEC,
    fallback_duration_sec: float = BEST_CLIP_FALLBACK_DURATION_SEC,
) -> tuple[int, int]:
    end_summary = replay_payload.get("end_summary") or {}
    duration_ticks = int(end_summary.get("duration_ticks") or 0)
    duration_ticks = max(0, duration_ticks)
    if duration_ticks <= 1:
        return 0, max(1, duration_ticks)

    def _bounded_pair(start_tick: int, end_tick: int) -> tuple[int, int]:
        st = max(0, min(duration_ticks, int(start_tick)))
        et = max(0, min(duration_ticks, int(end_tick)))
        if et <= st:
            et = min(duration_ticks, st + 1)
        return st, et

    def _clamp_max(start_tick: int, end_tick: int) -> tuple[int, int]:
        st, et = _bounded_pair(start_tick, end_tick)
        max_ticks = max(1, int(float(max_duration_sec) * TICKS_PER_SEC))
        if (et - st) > max_ticks:
            et = min(duration_ticks, st + max_ticks)
        return _bounded_pair(st, et)

    def _expand_min(start_tick: int, end_tick: int) -> tuple[int, int]:
        st, et = _bounded_pair(start_tick, end_tick)
        min_ticks = max(1, int(float(min_duration_sec) * TICKS_PER_SEC))
        if (et - st) >= min_ticks:
            return st, et
        center = (st + et) // 2
        st = center - (min_ticks // 2)
        et = st + min_ticks
        if st < 0:
            et -= st
            st = 0
        if et > duration_ticks:
            st -= et - duration_ticks
            et = duration_ticks
            if st < 0:
                st = 0
        return _bounded_pair(st, et)

    highlights = replay_payload.get("highlights")
    top: dict[str, Any] | None = None
    if isinstance(highlights, list):
        for h in highlights:
            if isinstance(h, dict):
                top = h
                break

    if top:
        start_tick = int(top.get("start_t") or 0)
        end_tick = int(top.get("end_t") or (start_tick + int(2 * TICKS_PER_SEC)))
        start_tick, end_tick = _clamp_max(start_tick, end_tick)
        start_tick, end_tick = _expand_min(start_tick, end_tick)
    else:
        span = max(1, int(float(fallback_duration_sec) * TICKS_PER_SEC))
        mid = duration_ticks // 2
        start_tick = max(0, mid - (span // 2))
        end_tick = start_tick + span
        start_tick, end_tick = _clamp_max(start_tick, end_tick)
        start_tick, end_tick = _expand_min(start_tick, end_tick)
    return start_tick, end_tick


def cache_key(
    *,
    replay_digest: str,
    kind: str,
    start_tick: int,
    end_tick: int,
    fps: int,
    scale: int,
    theme: str = "dark",
    aspect: Aspect = "16:9",
    clip_len_variant: str | None = None,
    captions_version: str | None = None,
    captions_template_id: str | None = None,
    render_profile: str | None = None,
    renderer_version: str = "v1",
) -> str:
    msg = f"{renderer_version}:{kind}:{replay_digest}:{start_tick}:{end_tick}:{fps}:{scale}:{theme}"
    # Backward compatibility: only extend the key when non-default behavior is requested.
    if aspect != "16:9":
        msg += f":aspect={aspect}"
    if clip_len_variant and str(clip_len_variant) != "12s":
        msg += f":lenv={clip_len_variant}"
    if captions_version:
        msg += f":captions={captions_version}"
    if captions_template_id:
        msg += f":caption_tpl={captions_template_id}"
    if render_profile:
        msg += f":profile={render_profile}"
    return hashlib.sha256(msg.encode("utf-8")).hexdigest()


def _layout_xy(
    *,
    team: Literal["A", "B"],
    formation: str,
    slot_index: int,
    mode: str,
    w: int,
    h: int,
) -> tuple[int, int]:
    left_back_x = int(w * 0.25)
    left_front_x = int(w * 0.40)
    right_front_x = int(w * 0.60)
    right_back_x = int(w * 0.75)

    if team == "A":
        x = left_front_x if formation == "front" else left_back_x
    else:
        x = right_front_x if formation == "front" else right_back_x

    cy = h // 2
    if mode == "1v1":
        y = cy
    else:
        if formation == "front":
            y = cy - int(h * 0.16) if slot_index == 0 else cy + int(h * 0.16)
        else:
            y = cy
    return x, y


def _init_units(replay_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    header = replay_payload.get("header") or {}
    units = header.get("units") or []
    if not isinstance(units, list) or not units:
        raise ValueError("Replay missing header.units (required for clip render)")

    out: dict[str, dict[str, Any]] = {}
    for u in units:
        if not isinstance(u, dict):
            continue
        uid = str(u.get("unit_id") or "")
        if not uid:
            continue
        max_hp = int(u.get("max_hp") or 1)
        out[uid] = {
            "unit_id": uid,
            "team": str(u.get("team") or "A"),
            "formation": str(u.get("formation") or "front"),
            "slot_index": int(u.get("slot_index") or 0),
            "name": str(u.get("creature_name") or u.get("creature_id") or uid),
            "max_hp": max_hp,
            "hp": max_hp,
            "alive": True,
        }
    if not out:
        raise ValueError("Replay header.units parsed empty")
    return out


def _sorted_events(replay_payload: dict[str, Any]) -> list[dict[str, Any]]:
    events = replay_payload.get("timeline_events") or []
    if not isinstance(events, list):
        return []
    out = [e for e in events if isinstance(e, dict)]
    out.sort(key=lambda e: (int(e.get("t") or 0), str(e.get("type") or "")))
    return out


class _HpTracker:
    def __init__(self, replay_payload: dict[str, Any]):
        self.units = _init_units(replay_payload)
        self.events = _sorted_events(replay_payload)
        self.i = 0

    def advance_to(self, tick: int) -> dict[str, dict[str, Any]]:
        while self.i < len(self.events):
            e = self.events[self.i]
            et = int(e.get("t") or 0)
            if et > tick:
                break
            typ = str(e.get("type") or "")
            payload = e.get("payload") or {}
            if isinstance(payload, dict):
                if typ == "DAMAGE":
                    target = str(payload.get("target") or "")
                    amount = int(payload.get("amount") or 0)
                    if target in self.units:
                        u = self.units[target]
                        u["hp"] = max(0, int(u["hp"]) - max(0, amount))
                        u["alive"] = int(u["hp"]) > 0
                elif typ == "HEAL":
                    target = str(payload.get("target") or "")
                    amount = int(payload.get("amount") or 0)
                    if target in self.units:
                        u = self.units[target]
                        u["hp"] = min(int(u["max_hp"]), int(u["hp"]) + max(0, amount))
                        u["alive"] = int(u["hp"]) > 0
                elif typ == "DEATH":
                    uid = str(payload.get("unit") or "")
                    if uid in self.units:
                        u = self.units[uid]
                        u["hp"] = 0
                        u["alive"] = False
                elif typ == "AUGMENT_TRIGGER":
                    trig_type = str(payload.get("type") or "")
                    if trig_type == "revive":
                        uid = str(payload.get("unit") or "")
                        hp = int(payload.get("hp") or 1)
                        if uid in self.units:
                            u = self.units[uid]
                            u["hp"] = max(0, min(int(u["max_hp"]), hp))
                            u["alive"] = int(u["hp"]) > 0
            self.i += 1
        return self.units


def _pick_highlight(
    replay_payload: dict[str, Any], *, start_tick: int, end_tick: int
) -> dict[str, Any] | None:
    raw = replay_payload.get("highlights") or []
    if not isinstance(raw, list):
        return None
    mid = (int(start_tick) + int(end_tick)) // 2
    for h in raw:
        if not isinstance(h, dict):
            continue
        try:
            st = int(h.get("start_t") or 0)
            et = int(h.get("end_t") or 0)
        except Exception:  # noqa: BLE001
            continue
        if st <= mid <= et:
            return h
    return raw[0] if raw and isinstance(raw[0], dict) else None


def _portal_label(replay_payload: dict[str, Any]) -> str:
    header = replay_payload.get("header") or {}
    portal_id = str(header.get("portal_id") or "")
    if not portal_id:
        return ""
    return portal_id.replace("portal_", "").replace("_", " ").strip().upper()


def _augment_label(replay_payload: dict[str, Any]) -> str:
    header = replay_payload.get("header") or {}
    aug_raw = header.get("augments_a") or []
    if not isinstance(aug_raw, list):
        return ""
    for a in aug_raw:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("augment_id") or "").strip()
        if not aid:
            continue
        return aid.replace("augment_", "").replace("_", " ").strip().upper()
    return ""


def _normalize_caption_line(text: str, *, max_len: int) -> str:
    out = " ".join(str(text or "").strip().split())
    if not out:
        return ""
    if len(out) <= max_len:
        return out
    trimmed = out[: max(1, max_len - 1)].rstrip()
    return (trimmed + "…") if trimmed else "…"


def _highlight_tag_set(h: dict[str, Any] | None) -> set[str]:
    if not isinstance(h, dict):
        return set()
    tags = h.get("tags")
    if not isinstance(tags, list):
        return set()
    out: set[str] = set()
    for t in tags:
        if isinstance(t, (str, int, float)):
            out.add(str(t))
    return out


def _best_event_type(
    replay_payload: dict[str, Any], *, start_tick: int, end_tick: int
) -> str:
    end = replay_payload.get("end_summary") or {}
    winner = str(end.get("winner") or "")
    if winner in ("A", "B"):
        hp_key = "hp_a" if winner == "A" else "hp_b"
        try:
            hp = int(end.get(hp_key) or 0)
        except Exception:  # noqa: BLE001
            hp = None
        if hp is not None and hp <= 5:
            return "clutch"

    h = _pick_highlight(replay_payload, start_tick=start_tick, end_tick=end_tick)
    tag_set = _highlight_tag_set(h)

    if "type:revive" in tag_set:
        return "revive"
    if "type:synergy" in tag_set:
        return "synergy_spike"
    if "type:damage_spike" in tag_set:
        return "damage_spike"
    if "type:death" in tag_set:
        return "elimination"
    if "type:hp_swing" in tag_set:
        return "hp_swing"

    title = str(h.get("title") or "") if isinstance(h, dict) else ""
    title_l = title.strip().lower()
    if "hp" in title_l and "swing" in title_l:
        return "hp_swing"
    if "elim" in title_l or "death" in title_l:
        return "elimination"
    if "synergy" in title_l:
        return "synergy_spike"
    if "damage" in title_l:
        return "damage_spike"

    for e in _sorted_events(replay_payload):
        t = int(e.get("t") or 0)
        if t < int(start_tick):
            continue
        if t > int(end_tick):
            break
        typ = str(e.get("type") or "")
        payload = e.get("payload") or {}
        if typ == "AUGMENT_TRIGGER" and isinstance(payload, dict):
            trig_type = str(payload.get("type") or "")
            if trig_type == "revive":
                return "revive"
        if typ == "SYNERGY_TRIGGER":
            return "synergy_spike"

    return "generic"


@dataclass(frozen=True)
class CaptionsPlan:
    version: str
    template_id: str
    event_type: str
    lines: list[str]


_CAPTION_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "hp_swing": [
        ("hp_swing_01", "{TITLE}", "{SUMMARY}"),
        ("hp_swing_02", "HP SWING", "TURNING POINT"),
        ("hp_swing_03", "HP SWING", "PORTAL {PORTAL}"),
    ],
    "elimination": [
        ("elimination_01", "ELIMINATION", "ONE PICK ENDS IT"),
        ("elimination_02", "{TITLE}", "CLEAN FINISH"),
    ],
    "damage_spike": [
        ("damage_spike_01", "DAMAGE SPIKE", "{SUMMARY}"),
        ("damage_spike_02", "BURST", "MELTED"),
    ],
    "synergy_spike": [
        ("synergy_spike_01", "SYNERGY ONLINE", "POWER SPIKE"),
        ("synergy_spike_02", "{TITLE}", "{SUMMARY}"),
    ],
    "revive": [
        ("revive_01", "REVIVE PROC", "SECOND LIFE"),
        ("revive_02", "NO WAY", "REVIVE!"),
    ],
    "clutch": [
        ("clutch_01", "1 HP CLUTCH", "NEVER GIVE UP"),
        ("clutch_02", "CLUTCH", "ONE HP"),
        ("clutch_03", "LOW HP CLUTCH", "PORTAL {PORTAL}"),
    ],
    "generic": [
        ("generic_01", "{TITLE}", "{SUMMARY}"),
        ("generic_02", "TURNING POINT", "WATCH FULL REPLAY"),
        ("augment_01", "AUGMENT {AUGMENT}", "TURNING POINT"),
        # Viral short-form (captions_v2): one-line hook + one-line punch.
        ("A", "BEAT THIS", "{TITLE}"),
        ("B", "WAIT FOR IT", "{SUMMARY}"),
        ("C", "PORTAL {PORTAL}", "{TITLE}"),
    ],
}


def captions_plan_for_segment(
    *,
    replay_payload: dict[str, Any],
    replay_id: str | None = None,
    start_tick: int,
    end_tick: int,
    template_id: str | None = None,
    captions_variant: str | None = None,
) -> CaptionsPlan:
    header = replay_payload.get("header") or {}
    match_id = str(header.get("match_id") or "") or str(replay_payload.get("digest") or "")
    portal_label = _portal_label(replay_payload)
    augment_label = _augment_label(replay_payload)

    h = _pick_highlight(replay_payload, start_tick=start_tick, end_tick=end_tick)
    raw_title = str(h.get("title") or "Turning Point") if isinstance(h, dict) else "Turning Point"
    raw_summary = str(h.get("summary") or "") if isinstance(h, dict) else ""

    event_type = _best_event_type(replay_payload, start_tick=start_tick, end_tick=end_tick)
    event_templates = _CAPTION_TEMPLATES.get(event_type) or []
    generic_templates = _CAPTION_TEMPLATES["generic"]
    templates = event_templates or generic_templates

    forced_template_id: str | None = None
    if template_id:
        forced_template_id = str(template_id)
    else:
        v = str(captions_variant or "").strip()
        if v in {"A", "B", "C"}:
            forced_template_id = v
        elif replay_id:
            seed = f"{CAPTIONS_VERSION}:captions_v2:{replay_id}".encode("utf-8")
            idx = int(hashlib.sha256(seed).hexdigest()[:8], 16) % 3
            forced_template_id = ["A", "B", "C"][idx]

    if forced_template_id:
        chosen = next((t for t in event_templates if t[0] == forced_template_id), None)
        if chosen is None:
            chosen = next(
                (t for t in generic_templates if t[0] == forced_template_id), None
            )
    else:
        seed = f"{CAPTIONS_VERSION}:{event_type}:{match_id}".encode("utf-8")
        idx = int(hashlib.sha256(seed).hexdigest()[:8], 16) % max(1, len(templates))
        chosen = templates[idx] if templates else None

    if not chosen:
        chosen = ("generic_01", "{TITLE}", "{SUMMARY}")

    tpl_id, title_fmt, body_fmt = chosen
    ctx = {
        "TITLE": raw_title,
        "SUMMARY": raw_summary,
        "PORTAL": portal_label,
        "AUGMENT": augment_label,
    }

    try:
        title = title_fmt.format_map(ctx)
    except Exception:  # noqa: BLE001
        title = raw_title
    try:
        body = body_fmt.format_map(ctx)
    except Exception:  # noqa: BLE001
        body = raw_summary

    title = _normalize_caption_line(title, max_len=42)
    body = _normalize_caption_line(body, max_len=84)
    if not body and event_type == "generic":
        body = "WATCH FULL REPLAY"
    if not body:
        body = _normalize_caption_line((raw_summary or raw_title), max_len=84)

    include_meta = tpl_id not in {"A", "B", "C"}
    meta = _normalize_caption_line(
        (f"PORTAL: {portal_label}" if portal_label else "") if include_meta else "",
        max_len=42,
    )

    lines = [line for line in [title, body, meta] if line]
    if not lines:
        lines = ["Turning Point"]

    return CaptionsPlan(
        version=CAPTIONS_VERSION,
        template_id=tpl_id,
        event_type=event_type,
        lines=lines[:3],
    )


def caption_lines_for_segment(
    *,
    replay_payload: dict[str, Any],
    start_tick: int,
    end_tick: int,
    template_id: str | None = None,
) -> list[str]:
    plan = captions_plan_for_segment(
        replay_payload=replay_payload,
        start_tick=start_tick,
        end_tick=end_tick,
        template_id=template_id,
    )
    return plan.lines[:3]


def _wrap_text(
    *, draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int, max_lines: int
) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current: list[str] = []
    for w in words:
        test = " ".join([*current, w])
        if draw.textlength(test, font=font) <= max_width:
            current.append(w)
            continue
        if current:
            lines.append(" ".join(current))
        current = [w]
        if len(lines) >= max_lines - 1:
            break

    if current and len(lines) < max_lines:
        lines.append(" ".join(current))

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    # Add ellipsis if we ran out of room.
    joined = " ".join(lines)
    if joined != text and lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = (last + "…") if last else "…"
    return lines


def _render_frame(
    *,
    units: dict[str, dict[str, Any]],
    mode: str,
    tick: int,
    w: int,
    h: int,
    scale: int,
    theme: str,
    aspect: Aspect,
    captions_lines: list[str] | None = None,
) -> Image.Image:
    if aspect == "9:16":
        battle_h = int(h * 0.72)
        battle = _render_frame(
            units=units,
            mode=mode,
            tick=tick,
            w=w,
            h=battle_h,
            scale=scale,
            theme=theme,
            aspect="16:9",
            captions_lines=None,
        )
        bg = (2, 6, 23) if theme == "dark" else (248, 250, 252)
        img = Image.new("RGB", (w, h), bg)
        img.paste(battle, (0, 0))
        draw = ImageDraw.Draw(img)

        panel = (15, 23, 42) if theme == "dark" else (241, 245, 249)
        border = (51, 65, 85) if theme == "dark" else (203, 213, 225)
        y0 = battle_h
        draw.rectangle((0, y0, w, h), fill=panel)
        draw.line((0, y0, w, y0), fill=border, width=2)

        lines = [line for line in (captions_lines or []) if line]
        if not lines:
            lines = ["Turning Point"]

        pad = 18 * scale
        max_w = max(10, w - 2 * pad)
        title_font = _safe_font(22 * scale, bold=True)
        body_font = _safe_font(16 * scale, bold=False)
        meta_font = _safe_font(12 * scale, bold=False)
        title = lines[0]
        body = lines[1] if len(lines) > 1 else ""
        meta = lines[2] if len(lines) > 2 else ""

        ty = y0 + 14 * scale
        title_lines = _wrap_text(
            draw=draw, text=title, font=title_font, max_width=max_w, max_lines=1
        )
        for tl in title_lines:
            draw.text(
                (pad, ty),
                tl,
                font=title_font,
                fill=(226, 232, 240) if theme == "dark" else (15, 23, 42),
            )
            ty += int(title_font.size * 1.2)

        if body:
            body_lines = _wrap_text(
                draw=draw, text=body, font=body_font, max_width=max_w, max_lines=2
            )
            for bl in body_lines:
                draw.text(
                    (pad, ty),
                    bl,
                    font=body_font,
                    fill=(148, 163, 184) if theme == "dark" else (71, 85, 105),
                )
                ty += int(body_font.size * 1.25)

        if meta:
            meta_lines = _wrap_text(
                draw=draw, text=meta, font=meta_font, max_width=max_w, max_lines=1
            )
            if meta_lines:
                draw.text(
                    (pad, h - pad - meta_font.size),
                    meta_lines[0],
                    font=meta_font,
                    fill=(148, 163, 184) if theme == "dark" else (100, 116, 139),
                )

        return img

    if theme not in ("dark", "light"):
        theme = "dark"

    bg = (2, 6, 23) if theme == "dark" else (248, 250, 252)
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # Arena centerline.
    mid_x = w // 2
    line = (30, 41, 59) if theme == "dark" else (203, 213, 225)
    draw.line((mid_x, 40, mid_x, h - 40), fill=line, width=2)

    # Clock.
    f_small = _safe_font(14 * scale, bold=True)
    t_sec = tick / TICKS_PER_SEC
    draw.text(
        (16, 12),
        f"t={t_sec:.1f}s",
        font=f_small,
        fill=(148, 163, 184) if theme == "dark" else (71, 85, 105),
    )

    radius = 30 * scale
    hp_w = 72 * scale
    hp_h = 10 * scale

    order = sorted(
        units.values(),
        key=lambda u: (
            str(u.get("team")),
            str(u.get("formation")),
            int(u.get("slot_index") or 0),
            str(u.get("unit_id")),
        ),
    )
    for u in order:
        team = "A" if str(u.get("team")) != "B" else "B"
        formation = str(u.get("formation") or "front")
        slot_index = int(u.get("slot_index") or 0)
        x, y = _layout_xy(
            team=team,
            formation=formation,
            slot_index=slot_index,
            mode=mode,
            w=w,
            h=h,
        )

        alive = bool(u.get("alive"))
        hp = int(u.get("hp") or 0)
        max_hp = max(1, int(u.get("max_hp") or 1))
        ratio = max(0.0, min(1.0, hp / max_hp))

        if team == "A":
            base = (59, 130, 246)
        else:
            base = (248, 113, 113)
        if not alive:
            base = (100, 116, 139)

        # Unit body.
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=base,
            outline=(15, 23, 42),
            width=2,
        )

        # HP bar.
        bar_x0 = x - hp_w // 2
        bar_y0 = y + radius + 10 * scale
        draw.rounded_rectangle(
            (bar_x0, bar_y0, bar_x0 + hp_w, bar_y0 + hp_h),
            radius=4 * scale,
            fill=(15, 23, 42) if theme == "dark" else (226, 232, 240),
        )
        draw.rounded_rectangle(
            (bar_x0, bar_y0, bar_x0 + int(hp_w * ratio), bar_y0 + hp_h),
            radius=4 * scale,
            fill=(34, 197, 94) if alive else (148, 163, 184),
        )

        # Label.
        name = str(u.get("name") or u.get("unit_id") or "")
        label = "".join([c for c in name.split()[:2]])[:6] or str(u.get("unit_id"))
        f = _safe_font(14 * scale, bold=True)
        tw = draw.textlength(label, font=f)
        draw.text((x - tw / 2, y - 8 * scale), label, font=f, fill=(255, 255, 255))

    return img


def _iter_frame_ticks(*, start_tick: int, end_tick: int, fps: int) -> list[int]:
    span = max(1, end_tick - start_tick)
    n = max(1, (span * fps) // TICKS_PER_SEC + 1)
    out: list[int] = []
    for i in range(n):
        tick = start_tick + (i * TICKS_PER_SEC) // fps
        out.append(min(end_tick, tick))
    if out and out[-1] != end_tick:
        out.append(end_tick)
    return out


def render_thumbnail_png_bytes(
    *,
    replay_payload: dict[str, Any],
    start_tick: int,
    end_tick: int,
    scale: int,
    theme: str,
    aspect: Aspect = "16:9",
    captions_lines: list[str] | None = None,
) -> bytes:
    header = replay_payload.get("header") or {}
    mode = str(header.get("mode") or "1v1")

    w = (540 if aspect == "9:16" else 900) * scale
    h = (960 if aspect == "9:16" else 506) * scale
    mid = (start_tick + end_tick) // 2
    tracker = _HpTracker(replay_payload)
    units = tracker.advance_to(mid)
    img = _render_frame(
        units=units,
        mode=mode,
        tick=mid,
        w=w,
        h=h,
        scale=scale,
        theme=theme,
        aspect=aspect,
        captions_lines=captions_lines,
    )
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_gif_bytes(
    *,
    replay_payload: dict[str, Any],
    start_tick: int,
    end_tick: int,
    fps: int,
    scale: int,
    theme: str,
    aspect: Aspect = "16:9",
    captions_lines: list[str] | None = None,
) -> bytes:
    header = replay_payload.get("header") or {}
    mode = str(header.get("mode") or "1v1")

    w = (540 if aspect == "9:16" else 900) * scale
    h = (960 if aspect == "9:16" else 506) * scale
    ticks = _iter_frame_ticks(start_tick=start_tick, end_tick=end_tick, fps=fps)

    tracker = _HpTracker(replay_payload)
    frames: list[Image.Image] = []
    for t in ticks:
        units = tracker.advance_to(t)
        frames.append(
            _render_frame(
                units=units,
                mode=mode,
                tick=t,
                w=w,
                h=h,
                scale=scale,
                theme=theme,
                aspect=aspect,
                captions_lines=captions_lines,
            )
        )

    if not frames:
        raise RuntimeError("no frames")

    buf = BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / max(1, fps)),
        loop=0,
        optimize=False,
    )
    return buf.getvalue()


def render_webm_to_path(
    *,
    replay_payload: dict[str, Any],
    start_tick: int,
    end_tick: int,
    fps: int,
    scale: int,
    theme: str,
    out_path: Path,
    aspect: Aspect = "16:9",
    captions_lines: list[str] | None = None,
) -> None:
    from imageio_ffmpeg import get_ffmpeg_exe

    header = replay_payload.get("header") or {}
    mode = str(header.get("mode") or "1v1")

    w = (540 if aspect == "9:16" else 900) * scale
    h = (960 if aspect == "9:16" else 506) * scale
    ticks = _iter_frame_ticks(start_tick=start_tick, end_tick=end_tick, fps=fps)

    tracker = _HpTracker(replay_payload)
    ffmpeg = get_ffmpeg_exe()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".tmp.webm")

    with tempfile.TemporaryDirectory(prefix="neuroleague_clip_") as tmpdir:
        frames_dir = Path(tmpdir)
        for idx, t in enumerate(ticks):
            units = tracker.advance_to(t)
            img = _render_frame(
                units=units,
                mode=mode,
                tick=t,
                w=w,
                h=h,
                scale=scale,
                theme=theme,
                aspect=aspect,
                captions_lines=captions_lines,
            )
            img.save(frames_dir / f"frame_{idx:06d}.png", format="PNG", optimize=True)

        cmd = [
            ffmpeg,
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-framerate",
            str(int(fps)),
            "-start_number",
            "0",
            "-i",
            str(frames_dir / "frame_%06d.png"),
            "-an",
            "-c:v",
            "libvpx-vp9",
            "-b:v",
            "0",
            "-crf",
            "37",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            "-row-mt",
            "0",
            "-metadata",
            "creation_time=0",
            str(tmp_out),
        ]
        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="ignore")
            raise RuntimeError(stderr.strip() or "ffmpeg clip render failed")

    if not tmp_out.exists():
        raise RuntimeError("ffmpeg did not produce output")
    tmp_out.replace(out_path)


def render_mp4_to_path(
    *,
    replay_payload: dict[str, Any],
    start_tick: int,
    end_tick: int,
    fps: int,
    scale: int,
    theme: str,
    out_path: Path,
    aspect: Aspect = "16:9",
    captions_lines: list[str] | None = None,
    mp4_preset: str = "ultrafast",
    mp4_crf: int = 28,
) -> None:
    from imageio_ffmpeg import get_ffmpeg_exe

    header = replay_payload.get("header") or {}
    mode = str(header.get("mode") or "1v1")

    w = (540 if aspect == "9:16" else 900) * scale
    h = (960 if aspect == "9:16" else 506) * scale
    ticks = _iter_frame_ticks(start_tick=start_tick, end_tick=end_tick, fps=fps)

    tracker = _HpTracker(replay_payload)
    ffmpeg = get_ffmpeg_exe()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".tmp.mp4")

    mp4_crf = max(10, min(40, int(mp4_crf)))
    mp4_preset = str(mp4_preset or "ultrafast")

    with tempfile.TemporaryDirectory(prefix="neuroleague_clip_") as tmpdir:
        frames_dir = Path(tmpdir)
        for idx, t in enumerate(ticks):
            units = tracker.advance_to(t)
            img = _render_frame(
                units=units,
                mode=mode,
                tick=t,
                w=w,
                h=h,
                scale=scale,
                theme=theme,
                aspect=aspect,
                captions_lines=captions_lines,
            )
            img.save(frames_dir / f"frame_{idx:06d}.png", format="PNG", optimize=True)

        cmd = [
            ffmpeg,
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-framerate",
            str(int(fps)),
            "-start_number",
            "0",
            "-i",
            str(frames_dir / "frame_%06d.png"),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            mp4_preset,
            "-crf",
            str(mp4_crf),
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            "-map_metadata",
            "-1",
            "-metadata",
            "creation_time=0",
            "-movflags",
            "+faststart",
            str(tmp_out),
        ]
        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="ignore")
            raise RuntimeError(stderr.strip() or "ffmpeg mp4 render failed")

    if not tmp_out.exists():
        raise RuntimeError("ffmpeg did not produce output")
    tmp_out.replace(out_path)
