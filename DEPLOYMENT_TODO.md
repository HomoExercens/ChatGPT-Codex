# Deployment v0 TODO — “인터넷에 올리기” 체크리스트

외부 입력(도메인/DNS/VPS/SSH)이 아직 없다면, 아래 TODO를 채우면 즉시 배포할 수 있습니다.

## 0) 필요한 값(채워야 함)
- `DEPLOY_DOMAIN`: 예) `neuroleague.example.com`
- `NEUROLEAGUE_PUBLIC_BASE_URL`: 예) `https://neuroleague.example.com`
- VPS: IP/호스트 + SSH 접속 정보
  - `DEPLOY_SSH_HOST`: 예) `ubuntu@1.2.3.4`
  - `DEPLOY_SSH_KEY_PATH`: 로컬 키 파일 경로

## 1) 인프라 사전 준비
- [ ] DNS: `DEPLOY_DOMAIN` A 레코드 → VPS IP
- [ ] 방화벽/보안그룹: 80/tcp, 443/tcp open
- [ ] VPS에 Docker + Compose v2 설치 (Ubuntu 예시)
  - [ ] `sudo apt-get update`
  - [ ] `sudo apt-get install -y docker.io docker-compose-plugin`
  - [ ] (권장) `sudo usermod -aG docker $USER` 후 재로그인

## 2) 시크릿/환경변수 준비
- [ ] 서버에서 `.env.deploy` 생성 (템플릿: `.env.deploy.example`)
- [ ] 권한: `chmod 600 .env.deploy` (서버 파일)
- [ ] 필수 시크릿/암호를 랜덤/강하게 설정:
  - `NEUROLEAGUE_AUTH_JWT_SECRET`
  - `NEUROLEAGUE_ADMIN_TOKEN`
  - `POSTGRES_PASSWORD`
  - `MINIO_ROOT_PASSWORD`
- [ ] 자세한 규칙: `docs/SECRETS_AND_ENV.md`

## 3) TLS(HTTPS) 리허설 → 운영 전환
- [ ] (권장) 최초 기동은 Let’s Encrypt **staging**으로:
  - `.env.deploy`에 아래 추가:
    - `CADDY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory`
- [ ] staging에서 충분히 확인 후 운영 전환:
  - `CADDY_ACME_CA` 라인을 제거(또는 prod directory로 변경)
  - `docker compose ... up -d` 재기동
- [ ] 주의: Let’s Encrypt rate limit (런북 참고)

## 4) 배포 실행(자동화 스크립트)
외부 입력 3개가 준비되면 아래 스크립트를 사용:
- `scripts/deploy_vps.sh`

예시:
```bash
export DEPLOY_DOMAIN="neuroleague.example.com"
export DEPLOY_SSH_HOST="ubuntu@1.2.3.4"
export DEPLOY_SSH_KEY_PATH="$HOME/.ssh/id_ed25519"
./scripts/deploy_vps.sh
```

## 5) 스모크 테스트/운영 체크리스트
- [ ] `docs/RUNBOOK_DEPLOY.md`의 smoke/ops checklist 수행
- [ ] `/api/ready` 200
- [ ] `/s/clip/<id>` OG meta 정상 + `og:image` never-404
- [ ] `render_jobs` backlog 급증/정체 없음
- [ ] `remix_v3` funnel / reply_clip_shared / reaction_click 모니터링

