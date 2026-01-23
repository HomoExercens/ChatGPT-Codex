# NEXT_STEPS_DEPLOY — “외부에서 접속 가능한 상태” 만들기

## 선택된 실행 경로
**A) Cloudflare Quick Tunnel 기반 공개 프리뷰**를 선택했습니다.

이유:
- 현재 환경에 `docker`가 없어 `docker-compose.prod.yml` / `docker-compose.deploy.yml`을 로컬에서 직접 기동할 수 없습니다.
- VPS/도메인/SSH 입력(`DEPLOY_SSH_HOST`, `DEPLOY_SSH_KEY_PATH`, `DEPLOY_DOMAIN`)이 제공되지 않았습니다.
- 대신 `cloudflared` Quick Tunnel로 로컬 실행(단일 포트)을 외부 HTTPS로 즉시 공개할 수 있습니다.

## 현재 프리뷰 상태
- 로컬 웹(단일 포트): `http://127.0.0.1:3000`
  - `/api/*`, `/s/*`, `/.well-known/*`는 Vite 프록시로 API(`http://127.0.0.1:8000`)에 전달됩니다.
- Quick Tunnel URL(이번 실행에서 발급): `artifacts/preview/preview_url.txt`
- 외부 스모크 로그(이번 실행): `artifacts/preview/preview_smoke.log`

## 15분 내 재현 방법 (Quick Tunnel)
### 0) 사전 준비
- Python/Node 의존성은 기존 `make dev` 흐름을 그대로 사용합니다.
- demo clip id는 시드 데이터에 포함된 `r_seed_001`을 사용합니다.

### 1) DB 마이그레이션 + 시드
```bash
make db-init seed-data-reset
```

### 2) cloudflared 설치(유저 로컬)
```bash
mkdir -p ~/.local/bin
curl -fsSL -o ~/.local/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x ~/.local/bin/cloudflared
~/.local/bin/cloudflared --version
```

### 3) Quick Tunnel 실행(먼저 URL을 얻는다)
```bash
~/.local/bin/cloudflared tunnel --url http://localhost:3000 --no-autoupdate
```
- 출력에 `https://<random>.trycloudflare.com`가 뜹니다. 그 값을 `PREVIEW_URL`로 사용합니다.

### 4) 앱 실행(단일 포트 3000) + OG 절대 URL 보정
Vite 프록시 때문에 API가 `Host`를 외부 URL로 자동 인식하지 못하므로, **반드시** 다음 환경변수로 절대 URL을 고정합니다:
```bash
export NEUROLEAGUE_PUBLIC_BASE_URL="$PREVIEW_URL"
./scripts/dev.sh
```

중요:
- Vite 최신 버전은 Host 체크가 있어 `*.trycloudflare.com` 요청을 403으로 막습니다.
- 이를 위해 `apps/web/vite.config.ts`에 `server.allowedHosts: ['.trycloudflare.com']`가 추가되어 있습니다(Quick Tunnel용).

## 스모크 테스트 체크리스트
### 외부(Quick Tunnel URL)
```bash
curl -fsS "$PREVIEW_URL/" >/dev/null
curl -fsS "$PREVIEW_URL/api/ready" >/dev/null
curl -fsS "$PREVIEW_URL/s/clip/r_seed_001?start=0.0&end=2.0&v=1" | rg 'property="og:title"' >/dev/null
curl -fsS "$PREVIEW_URL/api/ops/status" -o /dev/null -w "%{http_code}\n"  # 기대: 401 (admin token 없으면 잠김)
```

### 로컬
```bash
curl -fsS http://127.0.0.1:8000/api/ready >/dev/null
curl -fsS http://127.0.0.1:3000/ >/dev/null
```

## 운영상 주의사항(필수)
- Quick Tunnel(trycloudflare)은 **실험용**이며 URL이 매번 바뀌고, uptime 보장이 없습니다.
- 안정적 운영은:
  - (권장) 단일 VPS + Caddy + `docker-compose.deploy.yml` (런북: `docs/RUNBOOK_DEPLOY.md`)
  - 또는 Cloudflare “named tunnel”로 전환

## 중지/정리
프리뷰 중지:
- `./scripts/dev.sh`를 실행한 터미널에서 `Ctrl+C`
- `cloudflared`를 실행한 터미널에서 `Ctrl+C`

(백그라운드로 띄운 경우)
```bash
pkill -f cloudflared || true
pkill -f scripts/dev.sh || true
```

