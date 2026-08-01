#!/usr/bin/env bash
# Local mirror of .github/workflows/ci.yml — same steps, same scopes.
# Fail here so a push cannot discover the same failure on GitHub Actions.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

# When this script runs from a git hook, Git exports GIT_DIR / GIT_INDEX_FILE /
# GIT_AUTHOR_* / GIT_COMMITTER_* into the environment. Those leak into pytest
# helpers that run `git` in temp repos (worktrees break; state commits pick up
# the human author). CI runners do not set them.
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_COMMON_DIR GIT_PREFIX
unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_AUTHOR_DATE
unset GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL GIT_COMMITTER_DATE

echo "==> Ruff check"
uv run ruff check agent tests knowledge/scripts

echo "==> Ruff format"
uv run ruff format --check agent tests knowledge/scripts

echo "==> Mypy"
uv run mypy

echo "==> Pytest"
uv run pytest -q

echo "==> CLI help"
uv run agent --help >/dev/null

echo "==> Markdown lint"
npx --yes markdownlint-cli2@0.23.2 "**/*.md"

echo "==> Library contracts"
python3 knowledge/scripts/library.py check

echo "OK — matches CI jobs (runner + knowledge)."
