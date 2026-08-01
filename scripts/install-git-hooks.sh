#!/usr/bin/env bash
# Install the repo pre-commit hook into .git/hooks (no git config changes).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/.githooks/pre-commit"
dst="$root/.git/hooks/pre-commit"

if [[ ! -d "$root/.git" ]]; then
  echo "not a git checkout: $root" >&2
  exit 1
fi

chmod +x "$src" "$root/scripts/ci-check.sh" "$root/scripts/install-git-hooks.sh"
mkdir -p "$root/.git/hooks"
ln -sfn "$src" "$dst"
echo "installed pre-commit → $dst"
echo "runs: scripts/ci-check.sh (same checks as GitHub Actions)"
