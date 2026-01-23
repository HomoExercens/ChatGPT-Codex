# Cloudflare Named Tunnel — Stable Preview/Staging (Runbook)

Quick Tunnel(`*.trycloudflare.com`)은 URL이 매번 바뀌므로 공유 링크를 고정하기 어렵습니다.  
Cloudflare **Named Tunnel + your domain**을 쓰면 `https://staging.yourdomain.com` 같은 고정 URL로 “지속 가능한 프리뷰/스테이징”을 만들 수 있습니다.

> 이 문서는 “외부 자원(도메인/Cloudflare 계정)”이 준비되었을 때, 레포의 로컬 실행을 안정적으로 외부에 노출하는 방법을 정리합니다.  
> 실제 배포(컨테이너/서버 운영)는 `docs/RUNBOOK_DEPLOY.md`를 따르세요.

## 0) 요구 조건
- Cloudflare DNS로 관리되는 도메인(Zone)
- Cloudflare 계정(Account)
- `cloudflared` 설치
- 로컬에서 NeuroLeague가 단일 포트로 실행 중이어야 함
  - dev: `./scripts/dev.sh` → `http://127.0.0.1:3000`
  - 또는 (Docker 가능 시) prod-like: `make prod-up` → `http://127.0.0.1:8080`

## 1) 필요한 값(환경변수)
Named Tunnel 생성/적용은 아래 값이 **모두** 있을 때만 실행합니다.

- `CLOUDFLARE_API_TOKEN`
  - 권한 예시:
    - Account: Cloudflare Tunnel `Edit`
    - Zone: DNS `Edit`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_ZONE_ID`
- `PREVIEW_DOMAIN` (예: `staging.neuroleague.example.com`)

옵션:
- `TUNNEL_NAME` (default: `neuroleague-preview`)
- `TUNNEL_SERVICE_URL` (default: `http://127.0.0.1:3000`)

## 2) 실행(스크립트)
레포에 포함된 템플릿 스크립트:
- `scripts/cloudflare_named_tunnel.sh`

예시:
```bash
export CLOUDFLARE_API_TOKEN="..."
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_ZONE_ID="..."
export PREVIEW_DOMAIN="staging.neuroleague.example.com"
export TUNNEL_SERVICE_URL="http://127.0.0.1:3000"

./scripts/cloudflare_named_tunnel.sh
```

이 스크립트는:
- Named Tunnel을 생성(또는 기존 tunnel 조회)
- `PREVIEW_DOMAIN`에 대한 DNS(CNAME → `<tunnel_id>.cfargotunnel.com`)를 생성/업데이트
- `~/.cloudflared/` 아래에 credentials/config 파일을 작성

## 3) 로컬 앱 실행(중요)
OG meta의 절대 URL 정합성을 위해, **항상** 외부 base URL을 지정하세요:
```bash
export NEUROLEAGUE_PUBLIC_BASE_URL="https://${PREVIEW_DOMAIN}"
./scripts/dev.sh
```

Vite host guard:
- dev 서버는 Host allowlist가 필요합니다.
- `apps/web/vite.config.ts`는 `NEUROLEAGUE_PUBLIC_BASE_URL`의 hostname과 `VITE_ALLOWED_HOSTS`를 allowlist에 자동 포함합니다.

## 4) 스모크(필수)
```bash
BASE="https://${PREVIEW_DOMAIN}"
curl -fsS "$BASE/" >/dev/null
curl -fsS "$BASE/api/ready" >/dev/null
curl -fsS "$BASE/playtest" >/dev/null
curl -fsS "$BASE/s/clip/$(curl -fsS "$BASE/api/assets/ops/demo_ids.json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["clip_replay_id"])')?start=0.0&end=2.0&v=1" | rg 'property="og:image"' >/dev/null
```

## 5) 운영 팁(권장)
- `cloudflared`는 시스템 서비스(systemd)로 띄워 “항상 켜져 있는” 프리뷰를 만들 수 있습니다.
- 도메인/VPS/SSH가 준비되면, Named Tunnel 대신 `docker-compose.deploy.yml` 기반 VPS 배포로 전환하는 것이 운영/관측/백업 측면에서 더 낫습니다. (`docs/RUNBOOK_DEPLOY.md`)

