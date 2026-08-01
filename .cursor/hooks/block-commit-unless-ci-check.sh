#!/usr/bin/env bash
# Cursor: refuse `git commit` when scripts/ci-check.sh would fail (same as GitHub Actions).
# Matcher already limits this hook to `git commit`; always re-check before allowing.
set -euo pipefail

# Consume hook stdin (required).
cat >/dev/null

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! (cd "$root" && ./scripts/ci-check.sh); then
  python3 -c 'import json; print(json.dumps({
    "permission": "deny",
    "user_message": "Commit blocked: scripts/ci-check.sh failed (same checks as GitHub Actions). Fix lint/format/types/tests first.",
    "agent_message": "Do not commit. Run ./scripts/ci-check.sh, fix every failure, then commit."
  }))'
  exit 0
fi

printf '%s\n' '{"permission":"allow"}'
exit 0
