from __future__ import annotations

import argparse
from datetime import timedelta

from neuroleague_api.db import SessionLocal
from neuroleague_api.ops_cleanup import cleanup_render_jobs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cleanup old render jobs (and optionally purge cached artifacts)."
    )
    parser.add_argument(
        "--done-days",
        type=int,
        default=7,
        help="Delete done/failed jobs older than N days (default: 7).",
    )
    parser.add_argument(
        "--orphan-hours",
        type=int,
        default=12,
        help="Mark queued/running jobs older than N hours as failed (default: 12).",
    )
    parser.add_argument(
        "--purge-artifacts",
        action="store_true",
        help="Also delete cached artifacts for deleted jobs (local filesystem or S3 backend).",
    )
    parser.add_argument(
        "--keep-shared-days",
        type=int,
        default=7,
        help="If purging artifacts, skip jobs for share_open replays/matches in the last N days (default: 7).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute counts but do not modify DB or delete artifacts.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Max jobs to process per category (default: 2000).",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        out = cleanup_render_jobs(
            session,
            done_ttl=timedelta(days=int(args.done_days)),
            orphan_ttl=timedelta(hours=int(args.orphan_hours)),
            purge_artifacts=bool(args.purge_artifacts),
            keep_shared_ttl=timedelta(days=int(args.keep_shared_days))
            if bool(args.purge_artifacts) and int(args.keep_shared_days) > 0
            else None,
            dry_run=bool(args.dry_run),
            delete_limit=int(args.limit),
        )

    for k in sorted(out.keys()):
        print(f"{k}={out[k]}")


if __name__ == "__main__":
    main()
