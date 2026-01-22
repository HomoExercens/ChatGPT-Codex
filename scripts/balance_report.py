from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import orjson

from neuroleague_api.balance_report import compute_balance_report
from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal


def _md_top(rows: list[dict], *, title: str, n: int = 5) -> str:
    lines = [f"### {title}"]
    for r in rows[:n]:
        lc = bool(r.get("low_confidence"))
        lc_txt = " · low_confidence" if lc else ""
        lines.append(
            f"- `{r.get('id')}` — uses={int(r.get('uses') or 0)}, "
            f"wr={(float(r.get('winrate') or 0.0) * 100):.1f}%, "
            f"avg_elo={float(r.get('avg_elo_delta') or 0.0):+.1f}{lc_txt}"
        )
    if len(lines) == 1:
        lines.append("- (no data)")
    return "\n".join(lines)


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(
        description="Generate a deterministic balance report from the DB."
    )
    parser.add_argument(
        "--queue-type",
        default="ranked",
        choices=["ranked", "tournament"],
        help="Match queue type to include.",
    )
    parser.add_argument(
        "--limit", type=int, default=10_000, help="Max matches per mode to scan."
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(settings.artifacts_dir) / "ops"),
        help="Output directory (default: artifacts/ops).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d")
    report_name = f"balance_report_{stamp}"

    with SessionLocal() as session:
        payload = compute_balance_report(
            session,
            ruleset_version=settings.ruleset_version,
            queue_type=str(args.queue_type),
            generated_at=now.isoformat(),
            limit_matches=int(args.limit),
        )

    json_bytes = orjson.dumps(
        payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
    )
    json_path = out_dir / f"{report_name}.json"
    json_latest = out_dir / "balance_report_latest.json"
    json_path.write_bytes(json_bytes)
    json_latest.write_bytes(json_bytes)

    md_lines = [
        "# Balance Report (Auto)",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ruleset_version: `{payload.get('ruleset_version')}`",
        f"- queue_type: `{payload.get('queue_type')}`",
        f"- low_confidence_min_samples: `{payload.get('low_confidence_min_samples')}`",
        "",
    ]

    modes = payload.get("modes") or {}
    for mode in ("1v1", "team"):
        m = modes.get(mode) or {}
        md_lines.append(f"## Mode: {mode}")
        overall = m.get("overall") or {}
        md_lines.append(
            f"- matches_total: `{int(m.get('matches_total') or 0)}` · "
            f"wr={(float(overall.get('winrate') or 0.0) * 100):.1f}% · "
            f"avg_elo={float(overall.get('avg_elo_delta') or 0.0):+.1f}"
        )
        md_lines.append("")
        md_lines.append(
            _md_top(list(m.get("portals") or []), title="Top portals (by uses)")
        )
        md_lines.append("")
        md_lines.append(
            _md_top(list(m.get("augments") or []), title="Top augments (by uses)")
        )
        md_lines.append("")
        md_lines.append(
            _md_top(list(m.get("items") or []), title="Top items (by uses)")
        )
        md_lines.append("")
        md_lines.append(
            _md_top(list(m.get("sigils") or []), title="Top sigils (by uses)")
        )
        md_lines.append("")

    md = "\n".join(md_lines).rstrip() + "\n"
    md_path = out_dir / f"{report_name}.md"
    md_latest = out_dir / "balance_report_latest.md"
    md_path.write_text(md, encoding="utf-8")
    md_latest.write_text(md, encoding="utf-8")

    print(str(json_path))
    print(str(md_path))


if __name__ == "__main__":
    main()
