#!/usr/bin/env bash
set -euo pipefail

# Cloudflare Named Tunnel helper (stable preview/staging).
#
# Creates/updates:
# - Named Tunnel (Cloudflare Tunnel)
# - DNS record: PREVIEW_DOMAIN -> <tunnel_id>.cfargotunnel.com
# - cloudflared credentials + config under ~/.cloudflared/
#
# Safety:
# - Requires explicit env vars; does nothing without them.
# - Writes credentials outside the repo (never commit).

require() {
  local name="${1}"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env: ${name}" >&2
    exit 2
  fi
}

need_bin() {
  local b="${1}"
  if ! command -v "${b}" >/dev/null 2>&1; then
    echo "Missing dependency: ${b}" >&2
    exit 2
  fi
}

need_bin curl
need_bin python3

require CLOUDFLARE_API_TOKEN
require CLOUDFLARE_ACCOUNT_ID
require CLOUDFLARE_ZONE_ID
require PREVIEW_DOMAIN

TUNNEL_NAME="${TUNNEL_NAME:-neuroleague-preview}"
TUNNEL_SERVICE_URL="${TUNNEL_SERVICE_URL:-http://127.0.0.1:3000}"

CLOUDFLARED_DIR="${CLOUDFLARED_DIR:-${HOME}/.cloudflared}"
mkdir -p "${CLOUDFLARED_DIR}"

api() {
  local method="${1}"
  local url="${2}"
  local data="${3:-}"
  if [[ -n "${data}" ]]; then
    curl -fsS -X "${method}" "${url}" \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      -H "Content-Type: application/json" \
      --data "${data}"
  else
    curl -fsS -X "${method}" "${url}" \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      -H "Content-Type: application/json"
  fi
}

cf_base="https://api.cloudflare.com/client/v4"
account="${CLOUDFLARE_ACCOUNT_ID}"
zone="${CLOUDFLARE_ZONE_ID}"
domain="${PREVIEW_DOMAIN}"

echo "[cf] tunnel name=${TUNNEL_NAME}"
echo "[cf] preview domain=${domain}"
echo "[cf] service url=${TUNNEL_SERVICE_URL}"

echo "[cf] looking up existing tunnel…"
tunnel_list="$(api GET "${cf_base}/accounts/${account}/cfd_tunnel?name=${TUNNEL_NAME}")"
tunnel_id="$(python3 - <<'PY'
import json,sys
obj=json.loads(sys.stdin.read() or "{}")
res=obj.get("result") or []
if isinstance(res,list) and res:
  print(str(res[0].get("id") or ""))
PY
<<<"${tunnel_list}")"

cred_path="${CLOUDFLARED_DIR}/${TUNNEL_NAME}.json"
config_path="${CLOUDFLARED_DIR}/${TUNNEL_NAME}.yml"

if [[ -z "${tunnel_id}" ]]; then
  echo "[cf] creating tunnel…"
  tunnel_secret="$(
    python3 - <<'PY'
import base64,os
print(base64.b64encode(os.urandom(32)).decode("utf-8"))
PY
  )"
  create_payload="$(python3 - <<PY
import json
print(json.dumps({"name":"${TUNNEL_NAME}","tunnel_secret":"${tunnel_secret}"}))
PY
  )"
  created="$(api POST "${cf_base}/accounts/${account}/cfd_tunnel" "${create_payload}")"
  tunnel_id="$(python3 - <<'PY'
import json,sys
obj=json.loads(sys.stdin.read() or "{}")
print(str((obj.get("result") or {}).get("id") or ""))
PY
<<<"${created}")"
  if [[ -z "${tunnel_id}" ]]; then
    echo "${created}" >&2
    echo "Failed to create tunnel" >&2
    exit 3
  fi

  cat >"${cred_path}" <<JSON
{
  "AccountTag": "${account}",
  "TunnelID": "${tunnel_id}",
  "TunnelSecret": "${tunnel_secret}"
}
JSON
  chmod 600 "${cred_path}" || true
  echo "[cf] wrote credentials: ${cred_path}"
else
  echo "[cf] found tunnel id=${tunnel_id}"
  if [[ ! -f "${cred_path}" ]]; then
    echo "[warn] credentials file missing: ${cred_path}" >&2
    echo "[warn] if you created this tunnel elsewhere, copy the credentials JSON onto this machine before running cloudflared." >&2
  fi
fi

echo "[cf] ensure DNS record…"
target="${tunnel_id}.cfargotunnel.com"
dns_list="$(api GET "${cf_base}/zones/${zone}/dns_records?type=CNAME&name=${domain}")"
dns_id="$(python3 - <<'PY'
import json,sys
obj=json.loads(sys.stdin.read() or "{}")
res=obj.get("result") or []
if isinstance(res,list) and res:
  print(str(res[0].get("id") or ""))
PY
<<<"${dns_list}")"

dns_payload="$(python3 - <<PY
import json
print(json.dumps({"type":"CNAME","name":"${domain}","content":"${target}","proxied":True,"ttl":1}))
PY
)"

if [[ -n "${dns_id}" ]]; then
  api PUT "${cf_base}/zones/${zone}/dns_records/${dns_id}" "${dns_payload}" >/dev/null
  echo "[cf] updated DNS record id=${dns_id}"
else
  created_dns="$(api POST "${cf_base}/zones/${zone}/dns_records" "${dns_payload}")"
  dns_id="$(python3 - <<'PY'
import json,sys
obj=json.loads(sys.stdin.read() or "{}")
print(str((obj.get("result") or {}).get("id") or ""))
PY
<<<"${created_dns}")"
  if [[ -z "${dns_id}" ]]; then
    echo "${created_dns}" >&2
    echo "Failed to create DNS record" >&2
    exit 4
  fi
  echo "[cf] created DNS record id=${dns_id}"
fi

cat >"${config_path}" <<YML
tunnel: ${tunnel_id}
credentials-file: ${cred_path}

ingress:
  - hostname: ${domain}
    service: ${TUNNEL_SERVICE_URL}
  - service: http_status:404
YML
chmod 600 "${config_path}" || true
echo "[cf] wrote config: ${config_path}"

if command -v cloudflared >/dev/null 2>&1; then
  echo
  echo "Next:"
  echo "  export NEUROLEAGUE_PUBLIC_BASE_URL=\"https://${domain}\""
  echo "  ./scripts/dev.sh"
  echo
  echo "Run tunnel:"
  echo "  cloudflared tunnel --config \"${config_path}\" run"
else
  echo
  echo "[warn] cloudflared not found in PATH."
  echo "Install it (user-local) and then run:"
  echo "  cloudflared tunnel --config \"${config_path}\" run"
fi

