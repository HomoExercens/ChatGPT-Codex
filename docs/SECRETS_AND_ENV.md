# Secrets & Env — 절대 커밋 금지 규칙

이 문서는 NeuroLeague 배포 시 “시크릿을 Git에 절대 넣지 않고”, 안전하게 운영하기 위한 최소 규칙입니다.

## 핵심 규칙 (절대 위반 금지)
- `.env.deploy`는 **서버에만** 두고 Git에 커밋하지 않습니다.
  - 템플릿은 `.env.deploy.example`만 사용합니다.
- 아래 파일/패턴은 커밋/푸시 금지:
  - `.env`, `.env.*`(예외: `*.example`), `*.pem`, `*.key`, `id_rsa`, `id_ed25519`, `credentials*`
- 시크릿 의심 문자열(토큰/키/프라이빗키 블록)이 보이면 즉시 중단하고 회전(rotate)합니다.

## 서버의 `.env.deploy` 권장 운영
- 위치: `/opt/neuroleague/repo/.env.deploy` (예시)
- 권한: `chmod 600 .env.deploy`
- 소유자: deploy 사용자
- 백업: 시크릿 파일은 별도 안전한 비밀 저장소(1Password/Bitwarden/SSM 등)에 보관

## 반드시 랜덤/강하게 설정해야 하는 값
- `NEUROLEAGUE_AUTH_JWT_SECRET`
  - JWT 서명 키. 노출 시 세션 탈취 위험 → 즉시 rotate.
- `NEUROLEAGUE_ADMIN_TOKEN`
  - `/ops` 접근 토큰. 노출 시 운영 기능 노출 → 즉시 rotate.
- `POSTGRES_PASSWORD`
- `MINIO_ROOT_PASSWORD`

## Public preview hardening (권장)
공개 프리뷰(Quick Tunnel/스테이징)는 자동 스캐너/봇 유입 가능성이 높습니다.

- `NEUROLEAGUE_PREVIEW_MODE=true`
  - 목적: “비싼 작업”이 **익명 트래픽으로 큐에 쌓이지 않도록** 기본 차단
  - 현재 동작(v1): `/s/clip/*/kit.zip?hq=1`에서 HQ MP4가 캐시 미스일 때 **렌더 잡을 enqueue하지 않고 404**로 처리(캐시 히트만 허용)
  - 운영 팁:
    - 프리뷰/스테이징에서는 `true` 권장
    - 정식 운영(크리에이터 툴/다운로드가 중요)에서는 `false`로 전환 고려

## 공개로 두면 안 되는 값 (예시)
- Discord OAuth: `NEUROLEAGUE_DISCORD_CLIENT_ID`, `NEUROLEAGUE_DISCORD_CLIENT_SECRET`
- (추가될 수 있음) 외부 API 키, 결제 키, 웹훅 시크릿 등

## 로테이션(폐기) 절차(요약)
1) 영향을 받은 시크릿을 새 값으로 생성
2) 서버 `.env.deploy` 업데이트
3) `docker compose ... up -d`로 재기동
4) (필요 시) 기존 세션/토큰 무효화 정책 적용

## 로컬/CI 예시 파일의 역할
- `.env.deploy.example`: 배포용 템플릿(절대 시크릿 넣지 않음)
- `.env.deploy.ci.example`: CI에서 compose smoke를 돌리기 위한 더미 값(외부 서비스 의존 최소화)
