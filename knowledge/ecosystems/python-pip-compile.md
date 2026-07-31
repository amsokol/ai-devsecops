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
| available versions | `api` | PyPI JSON | reproducible |
| publish time | `api` | PyPI JSON | reproducible |
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

**Declared pins.** Read exact `==` pins from each enabled `*.in` file.

**Candidates / Moves to.** For each direct pin, call `cleared_pin_target` with
`ecosystem=ecosystems/python-pip-compile`, `package=<name>`, and `current` as the `.in` pin. Use its
`target` as `Moves to` when set; put `pending` tips under Pending quarantine. Do **not** invent the
concrete version from a narrow PyPI fetch or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target.

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
