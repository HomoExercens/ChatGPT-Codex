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
