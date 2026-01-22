from __future__ import annotations

from typing import Any, Literal

from neuroleague_sim.modifiers import AUGMENTS, PORTALS


SHARE_CAPTION_VERSION = "scv1"

DEFAULT_HASHTAGS: tuple[str, ...] = (
    "#neuroleague",
    "#autobattler",
    "#rlgame",
    "#indiegame",
)


def _portal_name(portal_id: str | None) -> str | None:
    pid = str(portal_id or "").strip()
    if not pid:
        return None
    p = PORTALS.get(pid)
    if p is not None and getattr(p, "name", None):
        return str(p.name)
    return pid.replace("portal_", "").replace("_", " ").strip().title() or pid


def _augment_name(augment_id: str) -> str:
    aid = str(augment_id or "").strip()
    if not aid:
        return ""
    a = AUGMENTS.get(aid)
    if a is not None and getattr(a, "name", None):
        return str(a.name)
    return aid.replace("augment_", "").replace("_", " ").strip().title() or aid


def _highlight_type(tags: list[str] | None) -> str:
    tag_set = {str(t) for t in (tags or []) if isinstance(t, str)}
    if "type:hp_swing" in tag_set:
        return "HP SWING"
    if "type:death" in tag_set:
        return "ELIMINATION"
    if "type:damage_spike" in tag_set:
        return "HIGH DMG"
    if "type:synergy" in tag_set:
        return "SYNERGY SPIKE"
    if "type:revive" in tag_set:
        return "REVIVE"
    return "TURNING POINT"


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


def clip_share_caption(
    replay_payload: dict[str, Any],
    *,
    match_result: Literal["A", "B", "draw"] | None,
    portal_id: str | None,
    augments: list[str],
    start_tick: int,
    end_tick: int,
    perspective: Literal["A", "B"] = "A",
    cta: Literal["Beat This", "Remix This", "Play Now"] = "Beat This",
    hashtags: tuple[str, ...] = DEFAULT_HASHTAGS,
) -> str:
    if match_result == "draw":
        result = "DRAW"
    elif match_result == perspective:
        result = "WIN"
    elif match_result in ("A", "B"):
        result = "LOSE"
    else:
        result = "RESULT"

    h = _pick_highlight(replay_payload, start_tick=start_tick, end_tick=end_tick)
    htype = _highlight_type(h.get("tags") if isinstance(h, dict) else None)

    portal = _portal_name(portal_id) or _portal_name(
        str((replay_payload.get("header") or {}).get("portal_id") or "") or None
    )

    aug_names: list[str] = []
    for aid in augments:
        nm = _augment_name(aid)
        if nm and nm not in aug_names:
            aug_names.append(nm)
        if len(aug_names) >= 3:
            break

    lines: list[str] = [f"{result} — {htype}"]
    meta: list[str] = []
    if portal:
        meta.append(f"Portal: {portal}")
    if aug_names:
        meta.append("Augments: " + " • ".join(aug_names))
    if meta:
        lines.append(" · ".join(meta))
    lines.append(f"{cta} in NeuroLeague")
    if hashtags:
        lines.append(" ".join([h for h in hashtags if h]))
    return "\n".join(lines).strip()


def build_share_caption(
    *,
    build_name: str,
    creator_name: str | None,
    mode: str | None,
    ruleset: str | None,
    cta: Literal["Remix This", "Quick Battle"] = "Remix This",
    hashtags: tuple[str, ...] = DEFAULT_HASHTAGS,
) -> str:
    lines = [f"Build: {str(build_name or '').strip() or 'NeuroLeague Build'}"]
    meta: list[str] = []
    if creator_name:
        meta.append(str(creator_name))
    if mode:
        meta.append(str(mode))
    if ruleset:
        meta.append(str(ruleset))
    if meta:
        lines.append(" · ".join(meta))
    lines.append(f"{cta} in NeuroLeague")
    if hashtags:
        lines.append(" ".join([h for h in hashtags if h]))
    return "\n".join(lines).strip()


def profile_share_caption(
    *,
    display_name: str,
    cta: Literal["Follow", "Watch Best Clip"] = "Follow",
    hashtags: tuple[str, ...] = DEFAULT_HASHTAGS,
) -> str:
    name = str(display_name or "").strip() or "NeuroLeague"
    lines = [f"{cta}: {name}", "NeuroLeague · Public Alpha"]
    if hashtags:
        lines.append(" ".join([h for h in hashtags if h]))
    return "\n".join(lines).strip()


def challenge_share_caption(
    *,
    title: str,
    portal_id: str | None,
    cta: Literal["Beat This"] = "Beat This",
    hashtags: tuple[str, ...] = DEFAULT_HASHTAGS,
) -> str:
    portal = _portal_name(portal_id)
    lines = [str(title or "NeuroLeague Challenge").strip() or "NeuroLeague Challenge"]
    if portal:
        lines.append(f"Portal: {portal}")
    lines.append(f"{cta} in NeuroLeague")
    if hashtags:
        lines.append(" ".join([h for h in hashtags if h]))
    return "\n".join(lines).strip()

