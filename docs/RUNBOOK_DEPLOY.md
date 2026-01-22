# RUNBOOK — Public Alpha Deploy (VPS)

This runbook describes a “single VPS” deployment using `docker-compose.deploy.yml` (Caddy + web + api + worker + scheduler + Postgres + MinIO).

> Note: local WSL environments may not have the Docker CLI. Treat **GitHub Actions deploy-smoke-compose** as the canonical “compose boots” reference, and run the rehearsal checks on the actual VPS.

## 0) Prereqs
- A Linux VPS with Docker + Docker Compose v2 installed
- A domain (recommended) pointing to the VPS (`A` record)
- Ports open: `80` and `443`

## 1) Configure env
1) Copy the template:
- `cp .env.deploy.example .env.deploy`

2) Set at minimum:
- `NEUROLEAGUE_PUBLIC_BASE_URL=https://<your-domain>`
- `NEUROLEAGUE_ALLOWED_HOSTS=<your-domain>,localhost,127.0.0.1`
- `NEUROLEAGUE_ADMIN_TOKEN=<random-long-token>`
- `POSTGRES_PASSWORD=<strong-password>`
- `MINIO_ROOT_PASSWORD=<strong-password>`
- (Recommended for demos) `NEUROLEAGUE_SEED_ON_BOOT=1` — seed stable demo content + `ops/demo_ids.json` (idempotent)

## 2) Boot
- `docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d --build`

## 3) Verify (smoke)
- `NEUROLEAGUE_PUBLIC_BASE_URL=https://<your-domain> NEUROLEAGUE_ADMIN_TOKEN=<token> make deploy-smoke`
- (Recommended) `./scripts/vps_rehearsal_check.sh https://<your-domain>` — runs the extended smoke checks via curl.
- Web: open `<base_url>/` and confirm login works
- Ops: open `<base_url>/ops` and paste admin token to load status/metrics
- Moderation: open `<base_url>/ops/moderation` (reports triage + hide/soft-ban)
- Demo IDs (if seeded): `<base_url>/api/assets/ops/demo_ids.json`

### Smoke success criteria (what “green” means)
- `/api/ready` returns `200`
- Share landings return HTML with OG meta:
  - `/s/clip/{replay_id}`, `/s/build/{bp_id}`, `/s/profile/{user_id}`, `/s/challenge/{id}`
  - includes: `og:title`, `og:description`, `og:image`, `og:image:secure_url`, `og:image:width`, `og:image:height`, `og:url`, `twitter:card`
- `og:image` URL is **never-404** (`200` or `307`)
- Clip MP4 is mobile-friendly:
  - `/s/clip/{replay_id}/video.mp4` supports `Range` (`206`) and returns `Accept-Ranges` + `Content-Range`
  - cache headers: `ETag` + `Cache-Control: public, max-age=31536000, immutable`
- Creator Pack zip works:
  - `/s/clip/{replay_id}/kit.zip` returns `200` + `ETag` + immutable cache
  - zip contains 4 files (mp4/thumb/caption/qr)
- render_jobs queue drains (best clip / thumbnail generation completes)

## 3.5) CI Deploy Smoke (GitHub Actions)
- PR/commit마다 GitHub Actions `deploy-smoke-compose`가 `docker-compose.deploy.yml`을 실제로 기동해 스모크 검증한다.
- Inputs: `.env.deploy.ci.example`(dummy values, secrets 없이 구동)
- Checks:
  - `/api/ready`가 200이 될 때까지 wait/retry
  - `/s/clip|build|profile|challenge` OG meta 존재 + `og:image`가 200/307(never-404)
  - MP4 `Range`(206) + kit.zip listing
  - `render_jobs` 파이프라인(best clip/thumbnail) 생성→완료→asset fetch
  - `/api/assets/*` allowlist(특히 `ops/demo_ids.json`) 동작
- Failure 시 artifacts `deploy-smoke-diagnostics`로 `deploy-smoke.log` + `curl-diagnostics.txt` + docker compose logs를 업로드한다.
- Note: 로컬 WSL 환경에 docker CLI가 없을 수 있으므로, compose 배포 재현성은 CI 결과를 레퍼런스로 삼는다.

## 4) Upgrade / Rollback
Upgrade:
- `git pull`
- `docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d --build`

Rollback (example):
- `git checkout <previous_sha>`
- `docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d --build`

## 5) Troubleshooting (1‑minute checklist)
1) `docker compose -f docker-compose.deploy.yml --env-file .env.deploy ps`
2) `docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs -f --tail=200 api`
3) `docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs -f --tail=200 caddy`
4) `curl -fsS <base_url>/api/ready`
5) `curl -fsS <base_url>/api/health`
6) `/ops` → Deploy Sanity panel:
   - DB ok / Storage ok / Ray ok
   - Render jobs queued/running not exploding

## 6) Backup / Restore
See `scripts/backup_pg_to_s3.sh` and `scripts/restore_pg_from_s3.sh` (MinIO/S3 compatible).
