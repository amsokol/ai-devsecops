---
id: ecosystems/python-pip-compile
kind: ecosystem
summary: Dependency facts and update procedure for Python projects locked with pip-compile.
applies_to: [requirements.in, requirements.txt]
---

# Python (pip-compile)

For projects where `*.in` files are the source of truth and `pip-compile` produces the locks. If
`uv.lock` owns resolution instead, use [`python-uv.md`](python-uv.md).

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | `requirements*.in` | reproducible |
| resolved versions | `tool` | `requirements*.txt` | reproducible |
| available versions | `api` | PyPI JSON; releases RSS when the full package document is too large | reproducible |
| publish time | `api` | Per-version PyPI JSON (`/pypi/<name>/<ver>/json`) | reproducible |
| advisories | `tool` | `pip-audit` against the locks | reproducible |

## Requirements

- Binaries: `pip`, `pip-compile`, `pip-audit`, `python`.
- Hosts: `pypi.org`.

## Detect

- Source pins: `requirements.in`, `requirements-dev.in`, and any similarly named `*.in` the
  product documents.
- Locks: the `requirements*.txt` files produced by `pip-compile`.
- Another build system may import only the runtime lock. Both locks are still regenerated when both
  exist.

## Evidence recipes

**Declared pins.** Call `list_declared_pins` with `ecosystem=ecosystems/python-pip-compile` first
on every repository-wide outdated sweep. It reads enabled `requirements*.in` files (and `-r`
includes). Record a fact for every package in its `packages` list — including pins that are fine —
before querying PyPI. The agent fails the task when the census is not covered.

**Candidates / Moves to.** For each direct pin, call `cleared_pin_target` with
`ecosystem=ecosystems/python-pip-compile`, `package=<name>`, and `current` as the `.in` pin. Use its
`target` as `Moves to` when set; put `pending` tips under Pending quarantine. Do **not** invent the
concrete version from a narrow PyPI fetch or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target. When `current_cleared` is `false`, emit `kind: quarantine` with `forbidden_state` (cite `evidence_key`); when it is `null`, emit `kind: unknown_age` with `forbidden_state` — say the release date is unknown, never quarantine. Do not leave the pin silent.

Routine only: security `needs_unlock` for a young fixed advisory version is unchanged.

**Publish time.** Prefer `cleared_pin_target`. For a one-off check, same registry as uv:

```text
https://pypi.org/pypi/<package>/<version>/json
```

Use `upload_time_iso_8601` or `upload_time` from the per-version address only
([`../policy/unknowns.md`](../policy/unknowns.md)).

**Advisories.**

```bash
pip-audit -r requirements.txt -r requirements-dev.txt
```

Audit the locks the product enables, not an ad-hoc subset.

`pip-audit` resolves every `-r` lock into **one** environment. When runtime and dev pins disagree
on a shared package (for example `urllib3==1.26.4` in the app lock and `urllib3==2.7.0` in the
dev lock), resolution fails before any advisory is checked. That is **not** a clean audit:

1. Treat the conflict as its own finding — inconsistency between the enabled requirement sets —
   under `capabilities/deps-outdated` or a routine note that names both pins and the resolver
   error. Do not report `clean` for `deps-vuln`.
2. Prefer `outcome: unverified` with reason `unexpected-shape` (or `unavailable` when the tool
   cannot run at all) when the audit never produced an advisory list. Silence about vulns after a
   red resolver is a defect: the check did not look.
3. Fix path: align the shared pin in the `.in` files (usually to the cleared, higher floor both
   sets can share), recompile both locks, re-run `pip-audit`. Only then may absence of advisories
   mean "nothing found".

## Update procedure

1. Run the comment pass and respect bundles.
2. Edit the **`.in`** pin to the cleared target.
3. Regenerate the locks with the same Python major and minor version the product's CI uses:

   ```bash
   pip-compile --strip-extras -o requirements.txt requirements.in
   pip-compile --strip-extras -o requirements-dev.txt requirements-dev.in
   ```

   Match the flags recorded in the existing lock header when present.
4. Keep `.in` and `.txt` changes in the same change-set. Never hand-edit a compiled lock except to
   resolve a documented conflict after recompiling.
5. When another build system vendors a lock, refresh that graph in the same change request if the
   product requires it.

Light verification when the overlay defines a surface for this ecosystem: install both locks, then
run the product's own checks. When the overlay names no `python-pip-compile` surface — for example
because the checkers are themselves installed from the locks under edit — findings are human-only
from the start ([`../policy/verification.md`](../policy/verification.md)). Do not invent a surface
the product did not declare.

## Cautions

- Always move the source pin and then recompile. A lock-only change for a direct dependency is not
  a valid remediation, and it will be undone by the next compile.
- Compiling with a different Python version than CI produces hashes that CI rejects.
- A major move needs an issue and a human unlock first, including web frameworks, crypto and RPC
  stacks.
- A Python package coupled to a schema-registry plugin or to a sibling pin in another ecosystem is
  a bundle: unlock and move the whole set ([`../policy/bundles.md`](../policy/bundles.md)).
