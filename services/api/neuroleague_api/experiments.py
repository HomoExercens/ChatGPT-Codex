from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import orjson
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.models import ABAssignment, Experiment


DEFAULT_EXPERIMENTS: dict[str, dict[str, Any]] = {
    "clip_len_v1": {
        "status": "running",
        "variants": [
            {"id": "10s", "weight": 0.34, "config": {"max_duration_sec": 10.0}},
            {"id": "12s", "weight": 0.33, "config": {"max_duration_sec": 12.0}},
            {"id": "15s", "weight": 0.33, "config": {"max_duration_sec": 15.0}},
        ],
    },
    "captions_v2": {
        "status": "running",
        "variants": [
            {"id": "A", "weight": 0.34, "config": {}},
            {"id": "B", "weight": 0.33, "config": {}},
            {"id": "C", "weight": 0.33, "config": {}},
        ],
    },
    "clips_feed_algo": {
        "status": "running",
        "variants": [
            {"id": "v2", "weight": 0.5, "config": {"algo": "v2"}},
            {"id": "v3", "weight": 0.5, "config": {"algo": "v3"}},
        ],
    },
    # Server-rendered /s/clip CTA ordering (anonymous traffic). Default keeps product order.
    "share_landing_clip_order": {
        "status": "running",
        "variants": [
            {"id": "beat_then_remix", "weight": 1.0, "config": {"order": "beat_then_remix"}},
            {"id": "remix_then_beat", "weight": 0.0, "config": {"order": "remix_then_beat"}},
        ],
    },
    "share_cta_copy": {
        "status": "running",
        "variants": [
            {"id": "beat_this", "weight": 0.5, "config": {"primary": "Beat This"}},
            {"id": "remix", "weight": 0.5, "config": {"primary": "Remix"}},
        ],
    },
    "quick_battle_default": {
        "status": "running",
        "variants": [
            {
                "id": "quick_battle",
                "weight": 0.5,
                "config": {"default": "quick_battle"},
            },
            {"id": "watch_clips", "weight": 0.5, "config": {"default": "watch_clips"}},
        ],
    },
}

BANDIT_VERSION = "bandit_v1"

_BANDIT_DEFAULTS_BY_EXPERIMENT: dict[str, dict[str, Any]] = {
    "clip_len_v1": {
        "baseline": "12s",
        "threshold_n": 150,
        "margin": 0.02,
        "min_share": 0.10,
        "max_share": 0.80,
        "step": 0.10,
        "days": 7,
    },
    "captions_v2": {
        "baseline": "A",
        "threshold_n": 150,
        "margin": 0.02,
        "min_share": 0.10,
        "max_share": 0.80,
        "step": 0.10,
        "days": 7,
    },
}


def ensure_default_experiments(
    session: Session, *, now: datetime | None = None
) -> None:
    now_dt = now or datetime.now(UTC)
    for key, spec in DEFAULT_EXPERIMENTS.items():
        row = session.get(Experiment, key)
        if row is not None:
            continue
        variants = spec.get("variants") or []
        status = str(spec.get("status") or "running")
        session.add(
            Experiment(
                key=str(key),
                status=status,
                variants_json=orjson.dumps(variants).decode("utf-8"),
                config_json=orjson.dumps({}).decode("utf-8"),
                start_at=now_dt,
                end_at=None,
                created_at=now_dt,
            )
        )
    session.commit()


def _variants_from_experiment(exp: Experiment) -> list[dict[str, Any]]:
    try:
        raw = orjson.loads(exp.variants_json or "[]")
    except Exception:  # noqa: BLE001
        raw = []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for v in raw:
        if not isinstance(v, dict):
            continue
        vid = str(v.get("id") or "").strip()
        if not vid:
            continue
        w = float(v.get("weight") or 0.0)
        cfg = v.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
        out.append({"id": vid[:32], "weight": max(0.0, w), "config": cfg})
    if not out:
        return []
    return out


def _load_json_dict(raw: str | None) -> dict[str, Any]:
    try:
        parsed = orjson.loads(raw or "{}")
    except Exception:  # noqa: BLE001
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dump_json(obj: Any) -> str:
    return orjson.dumps(obj).decode("utf-8")


def _normalize_bandit_weights(
    *,
    weights: dict[str, float],
    variant_ids: list[str],
    min_share: float,
    max_share: float,
) -> dict[str, float]:
    ids = [str(i) for i in variant_ids if str(i)]
    if not ids:
        return {}

    n = len(ids)
    min_share = max(0.0, float(min_share))
    max_share = max(0.0, float(max_share))
    if max_share <= 0.0:
        max_share = 1.0
    if min_share * n > 1.0:
        min_share = 1.0 / float(n)

    # Start with current weights, clamped.
    w0: dict[str, float] = {}
    for vid in ids:
        w = float(weights.get(vid) or 0.0)
        w0[vid] = max(0.0, min(1.0, w))

    # Normalize to sum=1.
    total = sum(w0.values())
    if total <= 0:
        w0 = {vid: 1.0 / float(n) for vid in ids}
    else:
        w0 = {vid: w / total for vid, w in w0.items()}

    # Clamp to min/max with a couple of correction passes.
    w = {vid: max(min_share, min(max_share, float(w0.get(vid) or 0.0))) for vid in ids}
    for _ in range(3):
        total = sum(w.values())
        if total <= 0:
            w = {vid: 1.0 / float(n) for vid in ids}
            break
        # Re-normalize while respecting bounds by adjusting the largest bucket.
        scale = 1.0 / total
        w = {vid: max(min_share, min(max_share, wv * scale)) for vid, wv in w.items()}
        # Fix any drift.
        total = sum(w.values())
        if abs(total - 1.0) < 1e-6:
            break
        # Add/subtract remainder to the largest weight within bounds.
        remainder = 1.0 - total
        best = max(ids, key=lambda vid: w.get(vid, 0.0))
        w[best] = max(min_share, min(max_share, w.get(best, 0.0) + remainder))

    # Final normalization (small drift).
    total = sum(w.values())
    if total > 0:
        w = {vid: float(wv) / total for vid, wv in w.items()}
    return w


def bandit_update_for_experiment(
    session: Session,
    *,
    experiment_key: str,
    now: datetime | None = None,
    table: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Guardrailed bandit: auto-promote a winning variant by adjusting Experiment.weights.

    - Does not change existing ABAssignment rows.
    - Only affects new assignments (weight-based pick).
    - Stores state under Experiment.config_json["bandit_v1"].
    """
    now_dt = now or datetime.now(UTC)
    ensure_default_experiments(session, now=now_dt)

    exp = session.get(Experiment, str(experiment_key))
    if exp is None:
        return {"ok": False, "error": "experiment_not_found"}
    if str(exp.status or "") != "running":
        return {"ok": True, "changed": False, "skipped": "not_running"}

    defaults = _BANDIT_DEFAULTS_BY_EXPERIMENT.get(str(experiment_key)) or {}
    cfg = _load_json_dict(exp.config_json)
    bandit_cfg = cfg.get(BANDIT_VERSION)
    bandit_cfg = bandit_cfg if isinstance(bandit_cfg, dict) else {}
    enabled = bool(bandit_cfg.get("enabled", True))
    if not enabled:
        return {"ok": True, "changed": False, "skipped": "disabled"}

    override = bandit_cfg.get("override_weights")
    override = override if isinstance(override, dict) else None

    if table is None:
        from neuroleague_api.growth_metrics import load_shorts_variants

        days = int(bandit_cfg.get("days") or defaults.get("days") or 7)
        data = load_shorts_variants(session, days=days)
        tables = data.get("tables") or []
        chosen_table = None
        for t in tables:
            if isinstance(t, dict) and str(t.get("key") or "") == str(experiment_key):
                chosen_table = t
                break
        table = chosen_table if isinstance(chosen_table, dict) else {}

    rows = table.get("variants") if isinstance(table, dict) else None
    rows = rows if isinstance(rows, list) else []
    perf: dict[str, dict[str, float]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        vid = str(r.get("id") or "").strip()
        if not vid:
            continue
        perf[vid] = {
            "n": float(r.get("n") or 0.0),
            "kpi": float(r.get("primary_kpi_rate") or r.get("ranked_done_rate") or 0.0),
        }

    variants = _variants_from_experiment(exp)
    ids = [str(v.get("id") or "") for v in variants if str(v.get("id") or "")]
    if not ids:
        return {"ok": True, "changed": False, "skipped": "no_variants"}

    baseline = str(bandit_cfg.get("baseline") or defaults.get("baseline") or ids[0])
    threshold_n = int(bandit_cfg.get("threshold_n") or defaults.get("threshold_n") or 0)
    margin = float(bandit_cfg.get("margin") or defaults.get("margin") or 0.0)
    min_share = float(bandit_cfg.get("min_share") or defaults.get("min_share") or 0.0)
    max_share = float(bandit_cfg.get("max_share") or defaults.get("max_share") or 1.0)
    step = float(bandit_cfg.get("step") or defaults.get("step") or 0.1)

    current = {str(v.get("id")): float(v.get("weight") or 0.0) for v in variants}
    current = _normalize_bandit_weights(
        weights=current, variant_ids=ids, min_share=min_share, max_share=max_share
    )

    if override:
        override_weights: dict[str, float] = {}
        for k, v in override.items():
            if isinstance(k, str):
                try:
                    override_weights[k] = float(v)
                except Exception:  # noqa: BLE001
                    continue
        new_w = _normalize_bandit_weights(
            weights=override_weights,
            variant_ids=ids,
            min_share=min_share,
            max_share=max_share,
        )
        changed = any(abs(float(new_w.get(i, 0.0)) - float(current.get(i, 0.0))) > 1e-6 for i in ids)
        for v in variants:
            vid = str(v.get("id") or "")
            v["weight"] = float(new_w.get(vid, 0.0))
        exp.variants_json = _dump_json(variants)
        bandit_cfg = {
            **bandit_cfg,
            "version": BANDIT_VERSION,
            "mode": "override",
            "baseline": baseline,
            "updated_at": now_dt.isoformat(),
            "weights": new_w,
        }
        cfg[BANDIT_VERSION] = bandit_cfg
        exp.config_json = _dump_json(cfg)
        session.add(exp)
        session.commit()
        return {
            "ok": True,
            "changed": bool(changed),
            "mode": "override",
            "weights": new_w,
        }

    base_perf = perf.get(baseline) or {}
    if threshold_n > 0 and float(base_perf.get("n") or 0.0) < float(threshold_n):
        return {"ok": True, "changed": False, "skipped": "baseline_low_n"}
    base_kpi = float(base_perf.get("kpi") or 0.0)

    winner: str | None = None
    best_delta = 0.0
    for vid in ids:
        if vid == baseline:
            continue
        p = perf.get(vid) or {}
        if threshold_n > 0 and float(p.get("n") or 0.0) < float(threshold_n):
            continue
        delta = float(p.get("kpi") or 0.0) - base_kpi
        if delta < float(margin):
            continue
        if winner is None or delta > best_delta + 1e-12:
            winner = vid
            best_delta = delta

    if not winner:
        bandit_cfg = {
            **bandit_cfg,
            "version": BANDIT_VERSION,
            "updated_at": now_dt.isoformat(),
            "baseline": baseline,
            "winner": None,
            "weights": current,
            "last_metrics": perf,
        }
        cfg[BANDIT_VERSION] = bandit_cfg
        exp.config_json = _dump_json(cfg)
        session.add(exp)
        session.commit()
        return {"ok": True, "changed": False, "winner": None, "weights": current}

    # Promote winner by `step`, funded by proportional cuts from others above min_share.
    old_winner = float(current.get(winner) or 0.0)
    target = min(float(max_share), old_winner + max(0.0, float(step)))
    delta = max(0.0, target - old_winner)

    reducible = {vid: max(0.0, float(current.get(vid, 0.0)) - float(min_share)) for vid in ids if vid != winner}
    total_reducible = sum(reducible.values())
    if total_reducible <= 1e-12 or delta <= 1e-12:
        return {"ok": True, "changed": False, "skipped": "no_reducible"}

    delta = min(delta, total_reducible)
    new_w = dict(current)
    new_w[winner] = old_winner + delta
    for vid in ids:
        if vid == winner:
            continue
        share = float(reducible.get(vid, 0.0)) / float(total_reducible) if total_reducible > 0 else 0.0
        new_w[vid] = float(new_w.get(vid, 0.0)) - (delta * share)

    new_w = _normalize_bandit_weights(weights=new_w, variant_ids=ids, min_share=min_share, max_share=max_share)
    changed = any(abs(float(new_w.get(i, 0.0)) - float(current.get(i, 0.0))) > 1e-6 for i in ids)
    if changed:
        for v in variants:
            vid = str(v.get("id") or "")
            v["weight"] = float(new_w.get(vid, 0.0))
        exp.variants_json = _dump_json(variants)

    bandit_cfg = {
        **bandit_cfg,
        "version": BANDIT_VERSION,
        "mode": "auto",
        "updated_at": now_dt.isoformat(),
        "baseline": baseline,
        "winner": winner,
        "winner_delta": best_delta,
        "weights": new_w,
        "last_metrics": perf,
    }
    cfg[BANDIT_VERSION] = bandit_cfg
    exp.config_json = _dump_json(cfg)
    session.add(exp)
    session.commit()
    return {
        "ok": True,
        "changed": bool(changed),
        "winner": winner,
        "weights": new_w,
        "baseline_kpi": base_kpi,
        "winner_delta": best_delta,
    }


def _pick_variant(
    *, subject: str, experiment_key: str, variants: list[dict[str, Any]]
) -> str:
    if not variants:
        return "control"
    total = sum(float(v.get("weight") or 0.0) for v in variants)
    if total <= 0:
        return str(variants[0].get("id") or "control")

    salt = Settings().auth_jwt_secret
    digest = hashlib.sha256(
        f"{salt}|{subject}|{experiment_key}".encode("utf-8")
    ).digest()
    r = int.from_bytes(digest[:8], "little", signed=False) / float(2**64)

    acc = 0.0
    for v in variants:
        acc += float(v.get("weight") or 0.0) / float(total)
        if r <= acc + 1e-12:
            return str(v.get("id") or "control")
    return str(variants[-1].get("id") or "control")


def assign_experiment(
    session: Session,
    *,
    subject_type: str,
    subject_id: str,
    experiment_key: str,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any], bool]:
    now_dt = now or datetime.now(UTC)
    ensure_default_experiments(session, now=now_dt)

    exp = session.get(Experiment, experiment_key)
    if exp is None:
        # Unknown experiment key → stable "control" behavior.
        return "control", {}, False

    existing = session.scalar(
        select(ABAssignment)
        .where(ABAssignment.subject_type == subject_type)
        .where(ABAssignment.subject_id == subject_id)
        .where(ABAssignment.experiment_key == experiment_key)
        .limit(1)
    )
    if existing is not None:
        variant = str(existing.variant or "control")
        cfg = {}
        for v in _variants_from_experiment(exp):
            if str(v.get("id")) == variant:
                cfg = v.get("config") if isinstance(v.get("config"), dict) else {}
                break
        return variant, cfg, False

    variants = _variants_from_experiment(exp)
    variant = _pick_variant(
        subject=f"{subject_type}:{subject_id}",
        experiment_key=experiment_key,
        variants=variants,
    )
    cfg = {}
    for v in variants:
        if str(v.get("id")) == variant:
            cfg = v.get("config") if isinstance(v.get("config"), dict) else {}
            break

    assignment = ABAssignment(
        id=f"ab_{uuid4().hex}",
        subject_type=str(subject_type),
        subject_id=str(subject_id),
        experiment_key=str(experiment_key),
        variant=str(variant),
        assigned_at=now_dt,
    )
    session.add(assignment)
    session.commit()
    return variant, cfg, True
