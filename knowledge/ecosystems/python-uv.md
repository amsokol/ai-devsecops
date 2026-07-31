---
id: ecosystems/python-uv
kind: ecosystem
summary: Dependency facts and update procedure for uv-managed Python projects.
applies_to: [pyproject.toml, uv.lock]
---

# Python (uv)

For projects where `uv` owns resolution. If the product locks with pip-compile instead, use
[`python-pip-compile.md`](python-pip-compile.md).

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | `pyproject.toml`, `uv.lock` | reproducible |
| available versions | `api` | PyPI JSON | reproducible |
| publish time | `api` | PyPI JSON | reproducible |
| advisories | `tool` | `pip-audit` | reproducible |

## Requirements

- Binaries: `uv`, `pip-audit`.
- Hosts: `pypi.org`.

When `pip-audit` is unavailable, advisories for this ecosystem are unverified. Do not fall back to
recalling vulnerabilities.

## Detect

- `pyproject.toml`: `dependencies`, any `[dependency-groups]`, and `[build-system].requires`.
- `uv.lock` for the resolved graph.
- A `requirements*.txt` present without uv is a sign the product is not uv-managed; check before
  assuming this ecosystem.

## Evidence recipes

**Candidates / Moves to.** For each direct pin, call `cleared_pin_target` with
`ecosystem=ecosystems/python-uv`, `package=<name>`, and `current` as declared (or locked when
classifying the resolved pin). Use its `target` as `Moves to` when set; put `pending` tips under
Pending quarantine. Do **not** invent the concrete version from a narrow PyPI fetch or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target.
Never establish the latest version by guessing the next number and seeing whether it exists.

`uv lock --upgrade --dry-run` remains a convenient cross-check for what resolution would move; it
does not choose `Moves to`.

Routine only: security `needs_unlock` for a young fixed advisory version is unchanged.

**Publish time.** Prefer `cleared_pin_target` (per-version `upload_time_iso_8601` internally). For a
one-off check:

```text
https://pypi.org/pypi/<package>/<version>/json
```

Use `upload_time_iso_8601`, falling back to `upload_time`. Absent value means unverified, which
means wait. Do not take a publication date from the package-wide document.

**Advisories.**

```bash
uv run pip-audit
```

## Update procedure

1. Run the comment pass and respect bundles ([`../policy/holds.md`](../policy/holds.md),
   [`../policy/bundles.md`](../policy/bundles.md)).
2. Edit the pin in `pyproject.toml`.
3. Refresh the lock with `uv lock`.
4. Keep manifest and lock in the same change-set.
5. Refresh or remove stale `agent:` comments on everything touched.

Light verification when the product overlay defines nothing more specific:

```bash
uv sync --frozen
```

## Cautions

- `[build-system].requires` entries are real pins; a newly introduced one is in scope.
- Do not raise `requires-python` unless product policy allows it. An interpreter floor jump is a
  major move and needs an unlock.
- A major move of a direct dependency needs an issue and a human unlock before a routine change
  request ([`../policy/grouping.md`](../policy/grouping.md)).
- After a lock refresh, re-check publication times for every new or changed lock entry: the
  refresh may pull in something younger than the package that was bumped.
