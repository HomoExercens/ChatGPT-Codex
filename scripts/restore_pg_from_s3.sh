#!/usr/bin/env bash
set -euo pipefail

DB_URL="${NEUROLEAGUE_DB_URL:-${DATABASE_URL:-}}"
if [[ -z "${DB_URL}" ]]; then
  echo "restore: missing NEUROLEAGUE_DB_URL (or DATABASE_URL)" >&2
  exit 1
fi

case "${DB_URL}" in
  postgresql*|postgres*)
    ;;
  *)
    echo "restore: DB_URL must be postgres" >&2
    exit 1
    ;;
esac

BUCKET="${NEUROLEAGUE_STORAGE_S3_BUCKET:-}"
if [[ -z "${BUCKET}" ]]; then
  echo "restore: missing NEUROLEAGUE_STORAGE_S3_BUCKET" >&2
  exit 1
fi

PREFIX="${NEUROLEAGUE_BACKUP_PREFIX:-backups/pg}"
KEY="${1:-}"

# SQLAlchemy URL -> libpq URL
PG_URL="${DB_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
PG_URL="${PG_URL/postgres+psycopg:\/\//postgresql:\/\/}"

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

if [[ -z "${KEY}" ]]; then
  KEY="$(python3 - <<'PY'
from __future__ import annotations

import os
from datetime import datetime, timezone

import boto3  # type: ignore

bucket = os.environ["NEUROLEAGUE_STORAGE_S3_BUCKET"]
prefix = (os.environ.get("NEUROLEAGUE_BACKUP_PREFIX") or "backups/pg").strip("/")
endpoint_url = os.environ.get("NEUROLEAGUE_STORAGE_S3_ENDPOINT_URL") or None
region = os.environ.get("NEUROLEAGUE_STORAGE_S3_REGION") or None

client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

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

if not all_objs:
    raise SystemExit("no backups found")
print(str(all_objs[-1].get("Key") or ""))
PY
)"
fi

if [[ -z "${KEY}" ]]; then
  echo "restore: could not determine backup key" >&2
  exit 1
fi

echo "restore: downloading s3://${BUCKET}/${KEY}" >&2
python3 - "${tmp}" "${KEY}" <<'PY'
from __future__ import annotations

import os
import sys

import boto3  # type: ignore

out_path = sys.argv[1]
bucket = os.environ["NEUROLEAGUE_STORAGE_S3_BUCKET"]
key = sys.argv[2]
endpoint_url = os.environ.get("NEUROLEAGUE_STORAGE_S3_ENDPOINT_URL") or None
region = os.environ.get("NEUROLEAGUE_STORAGE_S3_REGION") or None

client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
client.download_file(bucket, key, out_path)
PY

echo "restore: pg_restore into ${PG_URL}" >&2
pg_restore --clean --if-exists --no-owner --no-privileges --dbname "${PG_URL}" "${tmp}"
echo "restore: done" >&2
