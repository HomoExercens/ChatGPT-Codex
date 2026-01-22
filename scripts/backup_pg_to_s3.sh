#!/usr/bin/env bash
set -euo pipefail

if [[ "${NEUROLEAGUE_BACKUP_ENABLED:-false}" != "true" ]]; then
  echo "backup: disabled (set NEUROLEAGUE_BACKUP_ENABLED=true)" >&2
  exit 0
fi

DB_URL="${NEUROLEAGUE_DB_URL:-${DATABASE_URL:-}}"
if [[ -z "${DB_URL}" ]]; then
  echo "backup: missing NEUROLEAGUE_DB_URL (or DATABASE_URL)" >&2
  exit 1
fi

case "${DB_URL}" in
  postgresql*|postgres*)
    ;;
  *)
    echo "backup: skipping non-postgres DB_URL" >&2
    exit 0
    ;;
esac

BUCKET="${NEUROLEAGUE_STORAGE_S3_BUCKET:-}"
if [[ -z "${BUCKET}" ]]; then
  echo "backup: missing NEUROLEAGUE_STORAGE_S3_BUCKET" >&2
  exit 1
fi

PREFIX="${NEUROLEAGUE_BACKUP_PREFIX:-backups/pg}"
KEEP="${NEUROLEAGUE_BACKUP_KEEP:-7}"

TS="$(date -u +"%Y%m%d_%H%M%S")"
OUT="/tmp/neuroleague_pg_${TS}.dump"

# SQLAlchemy URL -> libpq URL
PG_URL="${DB_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
PG_URL="${PG_URL/postgres+psycopg:\/\//postgresql:\/\/}"

echo "backup: pg_dump -> ${OUT}" >&2
pg_dump --no-owner --no-privileges --format=custom --file "${OUT}" "${PG_URL}"
SIZE_BYTES="$(wc -c < "${OUT}" | tr -d '[:space:]')"

BACKUP_KEY="$(BACKUP_SIZE_BYTES="${SIZE_BYTES}" python3 - "${OUT}" <<'PY'
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import boto3  # type: ignore

path = sys.argv[1]
bucket = os.environ["NEUROLEAGUE_STORAGE_S3_BUCKET"]
prefix = (os.environ.get("NEUROLEAGUE_BACKUP_PREFIX") or "backups/pg").strip("/")
keep = int(os.environ.get("NEUROLEAGUE_BACKUP_KEEP") or "7")
endpoint_url = os.environ.get("NEUROLEAGUE_STORAGE_S3_ENDPOINT_URL") or None
region = os.environ.get("NEUROLEAGUE_STORAGE_S3_REGION") or None

ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
key = f"{prefix}/neuroleague_pg_{ts}.dump"

client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
client.upload_file(path, bucket, key, ExtraArgs={"ContentType": "application/octet-stream"})

# Retention: keep last N backups under prefix.
all_objs: list[dict] = []
token: str | None = None
while True:
    args = {"Bucket": bucket, "Prefix": f"{prefix}/"}
    if token:
        args["ContinuationToken"] = token
    resp = client.list_objects_v2(**args)
    all_objs.extend(resp.get("Contents") or [])
    if resp.get("IsTruncated"):
        token = resp.get("NextContinuationToken")
        continue
    break

all_objs = [o for o in all_objs if isinstance(o, dict) and str(o.get("Key") or "").endswith(".dump")]
all_objs.sort(key=lambda o: o.get("LastModified") or datetime.fromtimestamp(0, tz=timezone.utc))

to_delete = all_objs[:-keep] if keep > 0 else all_objs
deleted = 0
if to_delete:
    # delete_objects supports up to 1000 keys per call.
    for i in range(0, len(to_delete), 1000):
        chunk = to_delete[i : i + 1000]
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": str(o.get("Key"))} for o in chunk if o.get("Key")]},
        )
        deleted += len(chunk)

meta = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "bucket": bucket,
    "backup_key": key,
    "prefix": prefix,
    "keep": keep,
    "deleted": deleted,
    "size_bytes": int(os.environ.get("BACKUP_SIZE_BYTES") or "0"),
}
client.put_object(
    Bucket=bucket,
    Key="ops/last_backup.json",
    Body=json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    ContentType="application/json",
)

print(key)
PY
)"

rm -f "${OUT}"

echo "backup: uploaded ${BACKUP_KEY} (${SIZE_BYTES} bytes)" >&2
echo "${BACKUP_KEY}"
