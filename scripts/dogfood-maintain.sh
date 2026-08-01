#!/usr/bin/env bash
# Dogfood maintain against a product checkout (default: sibling ai-devsecops-demo2).
#
# Canonical one-liner from the monorepo root:
#
#   ./scripts/dogfood-maintain.sh
#
# See DOGFOOD.md for env, flags, and how to watch a run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_REPO="$(cd "$ROOT/.." && pwd)/ai-devsecops-demo2"
STATE_DIR="${DOGFOOD_STATE_DIR:-/tmp/ai-devsecops-dogfood}"
CFG_DIR="$STATE_DIR/config-nosandbox"

REPO="$DEFAULT_REPO"
PUBLISH=1
PLAN_ONLY=0
BACKGROUND=0
NO_CACHE=0
ONLY=()
EXTRA=()

usage() {
  cat <<'EOF'
Usage: ./scripts/dogfood-maintain.sh [options]

  Full local maintain against the demo product, with Cursor sandbox disabled
  (this machine cannot provide the SDK sandbox).

  Default: stay in the foreground and exit only when maintain finishes
  (exit code = maintain's). Pass --bg to detach.

Options:
  --repo PATH       Product checkout (default: ../ai-devsecops-demo2)
  --plan-only       Print the plan; do not run tasks
  --no-publish      Analyse only; do not open/update GitHub issues or fix PRs
  --publish         Open/update issues and fix PRs (default)
  --no-cache        Ignore the fact cache
  --only TASK       Run only this planned task (repeatable)
  --fg, --wait      Foreground: block until maintain exits (default)
  --bg              Background via setsid; print log + run dir and return now
  -h, --help        This help

Environment:
  CURSOR_API_KEY          required (unless --plan-only)
  AGENT_GITHUB_TOKEN      preferred for --publish; else AGENT_GATE_GH_TOKEN or `gh auth token`
  GH_TOKEN                set automatically from AGENT_GITHUB_TOKEN
  DOGFOOD_STATE_DIR       where config + logs live (default: /tmp/ai-devsecops-dogfood)

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:?}"
      shift 2
      ;;
    --plan-only)
      PLAN_ONLY=1
      shift
      ;;
    --no-publish)
      PUBLISH=0
      shift
      ;;
    --publish)
      PUBLISH=1
      shift
      ;;
    --no-cache)
      NO_CACHE=1
      shift
      ;;
    --only)
      ONLY+=(--only "$2")
      shift 2
      ;;
    --fg|--wait)
      BACKGROUND=0
      shift
      ;;
    --bg)
      BACKGROUND=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$REPO" ]]; then
  echo "error: product repo not found: $REPO" >&2
  exit 1
fi
if [[ ! -f "$REPO/.devsecops/agent.yaml" ]]; then
  echo "error: no overlay at $REPO/.devsecops/agent.yaml" >&2
  exit 1
fi

mkdir -p "$STATE_DIR"
rm -rf "$CFG_DIR"
cp -a "$ROOT/agent/config" "$CFG_DIR"
python3 - <<PY
from pathlib import Path
p = Path("$CFG_DIR") / "backends.yaml"
text = p.read_text()
if "sandbox: true" not in text and "sandbox: false" not in text:
    raise SystemExit(f"unexpected backends.yaml:\n{text}")
p.write_text(text.replace("sandbox: true", "sandbox: false", 1))
assert "sandbox: false" in p.read_text()
print(f"config: {p} (sandbox: false)")
PY

# Cursor IDE / agent shells often inject a broken local HTTPS proxy. Unset for this process tree.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy CURL_CA_BUNDLE || true

export AGENT_GITHUB_TOKEN="${AGENT_GITHUB_TOKEN:-${AGENT_GATE_GH_TOKEN:-}}"
if [[ -z "${AGENT_GITHUB_TOKEN}" ]] && command -v gh >/dev/null 2>&1; then
  if TOKEN="$(gh auth token 2>/dev/null || true)" && [[ -n "$TOKEN" ]]; then
    export AGENT_GITHUB_TOKEN="$TOKEN"
  fi
fi
export GH_TOKEN="${GH_TOKEN:-$AGENT_GITHUB_TOKEN}"

if [[ "$PLAN_ONLY" -eq 0 && -z "${CURSOR_API_KEY:-}" ]]; then
  echo "error: CURSOR_API_KEY is not set" >&2
  exit 1
fi
if [[ "$PUBLISH" -eq 1 && "$PLAN_ONLY" -eq 0 && -z "${AGENT_GITHUB_TOKEN}" ]]; then
  echo "error: need AGENT_GITHUB_TOKEN / AGENT_GATE_GH_TOKEN / gh auth for --publish" >&2
  exit 1
fi

if [[ -n "${AGENT_GITHUB_TOKEN}" ]]; then
  if LOGIN="$(GH_TOKEN="$AGENT_GITHUB_TOKEN" gh api user --jq .login 2>/dev/null || true)" && [[ -n "$LOGIN" ]]; then
    echo "github: $LOGIN"
  else
    echo "warning: could not resolve GitHub login (token present, API check failed)" >&2
  fi
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$STATE_DIR/maintain-${STAMP}.log"

ARGS=(
  maintain
  --repo "$REPO"
  --config-dir "$CFG_DIR"
)
[[ "$PLAN_ONLY" -eq 1 ]] && ARGS+=(--plan-only)
[[ "$PUBLISH" -eq 1 && "$PLAN_ONLY" -eq 0 ]] && ARGS+=(--publish)
[[ "$NO_CACHE" -eq 1 ]] && ARGS+=(--no-cache)
ARGS+=("${ONLY[@]}")
ARGS+=("${EXTRA[@]}")

echo "repo:    $REPO"
echo "agent:   $ROOT (uv run --extra cursor)"
echo "log:     $LOG"
echo "mode:    $([[ "$BACKGROUND" -eq 1 ]] && echo 'background (--bg)' || echo 'foreground (blocks until maintain exits)')"
echo "cmd:     uv run --extra cursor agent ${ARGS[*]}"

cd "$ROOT"
export PYTHONUNBUFFERED=1

run_fg() {
  echo
  echo "Blocking until maintain finishes. Ctrl+C stops it. Log also at: $LOG"
  echo
  set +e
  uv run --extra cursor agent "${ARGS[@]}" 2>&1 | tee "$LOG"
  local rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

run_bg() {
  # Detach so closing the parent shell does not kill the run.
  setsid -f env \
    PYTHONUNBUFFERED=1 \
    AGENT_GITHUB_TOKEN="${AGENT_GITHUB_TOKEN:-}" \
    GH_TOKEN="${GH_TOKEN:-}" \
    CURSOR_API_KEY="${CURSOR_API_KEY:-}" \
    PATH="$PATH" \
    HOME="$HOME" \
    uv run --extra cursor agent "${ARGS[@]}" >"$LOG" 2>&1
  sleep 3
  if ! pgrep -f "/.venv/bin/agent maintain --repo $REPO" >/dev/null 2>&1; then
    echo "error: maintain did not stay up; last log lines:" >&2
    tail -40 "$LOG" >&2 || true
    exit 1
  fi
  RUN="$(ls -td "$REPO"/.agent/runs/2026* 2>/dev/null | head -1 || true)"
  echo "pid:     $(pgrep -f "/.venv/bin/agent maintain --repo $REPO" | head -1)"
  echo "run:     ${RUN:-"(not created yet — check log)"}"
  cat <<EOF

OK — maintain is running in the background.
This script exits now on purpose (--bg). That is not a crash.
Next time, omit --bg (or pass --fg / --wait) to block until it finishes.

  alive?  pgrep -af 'agent maintain'
  log:    tail -f $LOG
          (often empty until a task finishes; prefer the run dir)
EOF
  if [[ -n "${RUN:-}" ]]; then
    cat <<EOF
  tasks:  ls $RUN/tasks
  done:   find $RUN/tasks -name result.json
  prep:   find $RUN/tasks -path '*/prep/pack.json'
EOF
  fi
}

if [[ "$BACKGROUND" -eq 1 ]]; then
  run_bg
else
  set +e
  run_fg
  rc=$?
  set -e
  RUN="$(ls -td "$REPO"/.agent/runs/2026* 2>/dev/null | head -1 || true)"
  echo
  echo "maintain finished exit=$rc"
  echo "run:     ${RUN:-}"
  echo "log:     $LOG"
  exit "$rc"
fi
