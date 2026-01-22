#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

REMOTE_NAME="${1:-}"
REMOTE_URL="${2:-}"

ALL_ZERO_RE='^0{40}$'

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

note() {
  echo "== $* ==" >&2
}

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: Working tree not clean. Commit/stash before pushing." >&2
  git status --short >&2
  exit 1
fi

if ! command -v rg >/dev/null 2>&1; then
  fail "ripgrep (rg) is required for secret scanning."
fi

mapfile -t UPDATES < <(cat || true)

if [[ "${#UPDATES[@]}" -eq 0 ]]; then
  note "No ref updates on stdin; running basic checks on HEAD"
  UPDATES=("HEAD $(git rev-parse HEAD) refs/heads/main 0000000000000000000000000000000000000000")
fi

note "Ref safety (no delete / no force push)"
for line in "${UPDATES[@]}"; do
  read -r local_ref local_sha remote_ref remote_sha <<<"${line}"
  [[ -z "${local_ref:-}" ]] && continue

  if [[ "${remote_ref}" == "refs/heads/main" && "${local_sha}" =~ ${ALL_ZERO_RE} ]]; then
    fail "Refusing to delete main (${remote_ref})."
  fi

  if [[ ! "${remote_sha}" =~ ${ALL_ZERO_RE} && ! "${local_sha}" =~ ${ALL_ZERO_RE} ]]; then
    if ! git merge-base --is-ancestor "${remote_sha}" "${local_sha}" >/dev/null 2>&1; then
      fail "Non-fast-forward update detected (force push/reset). Refusing."
    fi
  fi
done

note "Disallowed file paths scan (tree at pushed commit)"
DISALLOWED_TREE_PATTERN='(\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|\.keystore$|(^|/)credentials[^/]*$|(^|/)id_rsa(\..*)?$|(^|/)id_ed25519(\..*)?$|\.sqlite3?$|\.db$|(^|/)\.env($|\.))'
ENV_ALLOW_PATTERN='(^|/)\.env\.example$|(^|/)\.env\.[^/]+\.example$'

for line in "${UPDATES[@]}"; do
  read -r _local_ref local_sha _remote_ref _remote_sha <<<"${line}"
  [[ -z "${local_sha:-}" ]] && continue
  [[ "${local_sha}" =~ ${ALL_ZERO_RE} ]] && continue

  hits="$(git ls-tree -r --name-only "${local_sha}" \
    | rg --no-messages "${DISALLOWED_TREE_PATTERN}" \
    | rg --no-messages -v "${ENV_ALLOW_PATTERN}" || true)"

  if [[ -n "${hits}" ]]; then
    echo "${hits}" >&2
    fail "Disallowed secret/credential file appears in pushed tree."
  fi
done

note "Commits to be pushed (summary)"
if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
  git log --oneline --decorate @{u}..HEAD | head -n 50 >&2 || true
  git diff --stat @{u}..HEAD >&2 || true
else
  echo "(no upstream set yet; showing last 10 commits)" >&2
  git log -n 10 --oneline --decorate >&2
  git show --stat --oneline --decorate -n 1 HEAD >&2 || true
fi

note "Secret scan (commit patches)"
HIGH_SIGNAL_PATTERN='(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|sk_live_[0-9a-zA-Z]{10,}|AIza[0-9A-Za-z\\-_]{35}|eyJ[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{20,}|^\\+\\s*['"'"'\"]?-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----)'
MED_SIGNAL_PATTERN='(api[_-]?key|client[_-]?secret|private[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|pwd|secret)\\s*[:=]\\s*['"'"'\"][^'"'"'\"\\s]{20,}['"'"'\"]'

scan_range_for_line() {
  local line="$1"
  local local_sha remote_sha range
  read -r _local_ref local_sha _remote_ref remote_sha <<<"${line}"

  [[ -z "${local_sha:-}" ]] && return 0
  [[ "${local_sha}" =~ ${ALL_ZERO_RE} ]] && return 0

  if [[ "${remote_sha}" =~ ${ALL_ZERO_RE} ]]; then
    range="${local_sha}"
  else
    range="${remote_sha}..${local_sha}"
  fi

  matches="$(git log --format= --patch --no-color "${range}" \
    | rg -n --no-messages --replace '[REDACTED]' "${HIGH_SIGNAL_PATTERN}" || true)"
  if [[ -n "${matches}" ]]; then
    echo "${matches}" >&2
    fail "High-signal secret detected in commits-to-push. Stop and rotate/revoke immediately if real."
  fi

  matches="$(git log --format= --patch --no-color "${range}" \
    | rg -n --no-messages -i --replace '[REDACTED]' "${MED_SIGNAL_PATTERN}" || true)"
  if [[ -n "${matches}" ]]; then
    echo "${matches}" >&2
    fail "Possible secret-looking assignment detected in commits-to-push. Verify before pushing."
  fi
}

for line in "${UPDATES[@]}"; do
  scan_range_for_line "${line}"
done

note "Test (minimum): make test-fast"
if [[ ! -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  fail "Missing .venv. Run 'make bootstrap' once (may download deps), then retry."
fi

if ! command -v make >/dev/null 2>&1; then
  fail "'make' is required to run the test target."
fi

make test-fast

note "Pre-push checks PASSED"
