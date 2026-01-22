from __future__ import annotations

import argparse
from datetime import UTC, datetime

from neuroleague_api.db import SessionLocal
from neuroleague_api.growth_metrics import rollup_growth_metrics


def _parse_days(range_raw: str | None, days_raw: int | None) -> int:
    if range_raw:
        raw = str(range_raw).strip().lower()
        if raw.endswith("d"):
            raw = raw[:-1]
        try:
            return max(1, min(365, int(raw)))
        except Exception:  # noqa: BLE001
            return 7
    if days_raw is not None:
        return max(1, min(365, int(days_raw)))
    return 7


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Roll up growth metrics into metrics_daily/funnel_daily."
    )
    parser.add_argument(
        "--range", dest="range", default=None, help="e.g. 7d, 30d (default 7d)"
    )
    parser.add_argument(
        "--days",
        dest="days",
        type=int,
        default=None,
        help="alias for --range (integer days)",
    )
    args = parser.parse_args()

    days = _parse_days(args.range, args.days)
    with SessionLocal() as session:
        res = rollup_growth_metrics(session, days=days)

    now = datetime.now(UTC).isoformat()
    print(
        f"[metrics_rollup] ok at {now} (days={res.days}, {res.start_date.isoformat()}..{res.end_date.isoformat()})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
