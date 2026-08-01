# Local dogfood (demo2)

One command. Do not reinvent the Cursor sandbox / token / `--extra cursor` dance each time.

## Command

From the monorepo root (`amsokol/ai-devsecops`):

```bash
./scripts/dogfood-maintain.sh
```

That runs a full `maintain --publish` against the sibling checkout
`../ai-devsecops-demo2`, with `backends.cursor.sandbox: false` (this machine cannot
provide the SDK sandbox), logs under `/tmp/ai-devsecops-dogfood/`, and run records under
`ai-devsecops-demo2/.agent/runs/<id>/`.

By default the script **stays in the foreground** and only returns when maintain exits
(same exit code). Use `--bg` only when you want to detach.

Useful variants:

```bash
./scripts/dogfood-maintain.sh                # foreground: blocks until maintain exits (default)
./scripts/dogfood-maintain.sh --fg           # same, explicit
./scripts/dogfood-maintain.sh --wait         # alias for --fg
./scripts/dogfood-maintain.sh --plan-only    # task list only
./scripts/dogfood-maintain.sh --no-publish   # analyse, no GitHub writes
./scripts/dogfood-maintain.sh --bg           # detach; script returns now, maintain keeps running
./scripts/dogfood-maintain.sh --only deps-vuln@cargo
./scripts/dogfood-maintain.sh --repo /path/to/other-product
```

## Environment

| Variable | Role |
| --- | --- |
| `CURSOR_API_KEY` | Required for real sessions |
| `AGENT_GITHUB_TOKEN` | Preferred for `--publish` (App installation token) |
| `AGENT_GATE_GH_TOKEN` | Fallback if `AGENT_GITHUB_TOKEN` unset |
| `gh auth token` | Last-resort fallback |
| `DOGFOOD_STATE_DIR` | Override `/tmp/ai-devsecops-dogfood` |

The script unsets `HTTP(S)_PROXY` for the process tree — Cursor agent shells often inject a
localhost proxy that breaks `api.github.com`.

## Watch a run

`--bg` returns as soon as maintain is up — that is success, not a crash. The process keeps
running under `setsid`. Confirm with `pgrep -af 'agent maintain'`.

The log file is often empty until late: the agent prints little to stdout while sessions run.
Prefer the run directory:

```bash
pgrep -af 'agent maintain'
ls ai-devsecops-demo2/.agent/runs/<id>/tasks
find ai-devsecops-demo2/.agent/runs/<id>/tasks -name result.json
# prep packs (outdated + vuln Variant A):
find ai-devsecops-demo2/.agent/runs/<id>/tasks -path '*/prep/pack.json'
tail -f /tmp/ai-devsecops-dogfood/maintain-*.log   # optional; may stay empty for a while
```

After it finishes, read `report.md` / `manifest.json` in the run dir, then
`gh issue list -R amsokol/ai-devsecops-demo2` and `gh pr list -R amsokol/ai-devsecops-demo2`.

## When the agent (this chat) starts the run

The Cursor Shell tool must run the script with **full host permissions** (`required_permissions: ["all"]`).
A sandboxed launch can start `agent maintain` and even write prep packs, then die with
`PermissionError` when the Cursor SDK bridge is terminated — and GitHub calls through the IDE
proxy fail with `unexpected EOF`. Prefer asking the human to run `./scripts/dogfood-maintain.sh`
(or `--bg`) in a normal terminal if approval for `all` is awkward.

## What the script always does

1. Copies `agent/config` → `$DOGFOOD_STATE_DIR/config-nosandbox` and forces `sandbox: false`.
2. Resolves GitHub token; prints the login when the API is reachable.
3. Invokes `uv run --extra cursor agent maintain --repo <demo> --config-dir … [--publish]`.
4. Tees (or redirects) stdout/stderr to a stamped log file.
