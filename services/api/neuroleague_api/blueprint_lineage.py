from __future__ import annotations

from typing import Iterable

from sqlalchemy import update
from sqlalchemy.orm import Session

from neuroleague_api.models import Blueprint


def _safe_int(v: object, default: int = 0) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return default


def compute_root_and_depth(
    db: Session,
    *,
    blueprint: Blueprint,
    max_hops: int = 32,
    full_chain: bool = True,
) -> tuple[str, int, list[str]]:
    """
    Returns (root_blueprint_id, depth, chain_ids) for `blueprint`.

    - depth is 0 for root, 1 for direct child, ...
    - chain_ids is ordered [self, parent, ..., root]
    """
    # Fast-path: prefer persisted fields if present (only when full chain is not required).
    root_id = str(getattr(blueprint, "fork_root_blueprint_id", "") or "").strip()
    depth = _safe_int(getattr(blueprint, "fork_depth", 0), 0)
    if (not full_chain) and root_id and depth >= 0:
        return root_id or str(blueprint.id), depth, [str(blueprint.id)]

    chain: list[Blueprint] = []
    seen: set[str] = set()
    cur: Blueprint | None = blueprint
    for _ in range(max(1, int(max_hops))):
        if cur is None:
            break
        cid = str(cur.id)
        if cid in seen:
            break
        seen.add(cid)
        chain.append(cur)
        pid = str(getattr(cur, "forked_from_id", "") or "").strip()
        if not pid:
            break
        cur = db.get(Blueprint, pid)

    root = chain[-1] if chain else blueprint
    root_id = str(getattr(root, "id", blueprint.id))
    depth = max(0, len(chain) - 1)
    chain_ids = [str(n.id) for n in chain] if chain else [str(blueprint.id)]
    return root_id, depth, chain_ids


def ensure_persisted_root_and_depth(
    db: Session,
    *,
    blueprint_id: str,
    root_blueprint_id: str,
    depth: int,
) -> None:
    try:
        db.execute(
            update(Blueprint)
            .where(Blueprint.id == str(blueprint_id))
            .values(
                fork_root_blueprint_id=str(root_blueprint_id),
                fork_depth=max(0, int(depth)),
            )
        )
    except Exception:  # noqa: BLE001
        pass


def increment_fork_counts(
    db: Session,
    *,
    blueprint_ids: Iterable[str],
    delta: int = 1,
) -> None:
    ids = [str(i) for i in blueprint_ids if str(i)]
    if not ids:
        return
    try:
        db.execute(
            update(Blueprint)
            .where(Blueprint.id.in_(ids))  # type: ignore[arg-type]
            .values(fork_count=Blueprint.fork_count + int(delta))
        )
    except Exception:  # noqa: BLE001
        pass
