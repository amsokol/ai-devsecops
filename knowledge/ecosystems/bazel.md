---
id: ecosystems/bazel
kind: ecosystem
summary: Bazel module pins via the Central Registry, and couplings to language dependency graphs.
applies_to: [MODULE.bazel, MODULE.bazel.lock]
---

# Bazel (bzlmod)

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | `MODULE.bazel` and its includes | reproducible |
| available versions | `api` | Bazel Central Registry module metadata | reproducible |
| yanked versions | `api` | the same metadata | reproducible |
| publish time | `api` / `web` | BCR commit that added the version's `source.json`; else upstream GitHub Release | reproducible (BCR) / heuristic (Release) |
| advisories | `none` | — | — |

There is no audit tool for modules, so advisories here are a documented gap: report them as
unverified and review release notes for high-impact rules and toolchains instead of inventing
findings ([`../policy/unknowns.md`](../policy/unknowns.md)).

Publication time for a module version is the date it entered BCR: the commit on
`bazelbuild/bazel-central-registry` that added `modules/<name>/<version>/source.json`. That is the
source of truth for quarantine age. When that commit cannot be resolved, fall back to the upstream
project's GitHub Release for the same version (BCR `repository` often looks like
`github:owner/name`). The fallback is heuristic and is used asymmetrically:

- it may keep a candidate waiting;
- it may clear a candidate only when the version is **unambiguously** older than the window, not
  borderline. When the derived age is close to the boundary, wait for the next run rather than trusting
  a date that came from a different system.

Never invent a timestamp, and never treat "the version exists in the registry" as evidence of when it
appeared.

Do not describe this ecosystem as having no scanner for **versions**: the registry metadata is a
reliable version source.

## Requirements

- Binaries: `bazel` when a local resolution check is needed.
- Hosts: `raw.githubusercontent.com`, `registry.bazel.build`, `api.github.com`.

Upstream release dates come from the hosting platform's API, asked directly: a run has no credential
for it, so a command line that expects a login has nothing to log in with.

## Detect

- `MODULE.bazel`, any `*.MODULE.bazel` includes, and `MODULE.bazel.lock`.
- `bazel_dep(name = "…", version = "…")` entries.
- Pins that do not come from the registry — language toolchains, external tool toolchains. Report
  them; move them only when product policy or an unlock comment allows.
- **Language graph wiring**, which is the part most often missed: includes that pull another
  ecosystem's resolution into Bazel, such as a Cargo lock, a Go module file, or a pip lock. When
  those files change, Bazel's resolved graph changes too, even though no Bazel file was edited.

## Evidence recipes

**Declared pins.** Call `list_declared_pins` with `ecosystem=ecosystems/bazel` first on every
repository-wide outdated sweep. It extracts `bazel_dep(name=…, version=…)` from `MODULE.bazel` and
`include("//:…")` files. Record a fact for every package in its `packages` list — including pins
that are fine — before querying BCR. The agent fails the task when the census is not covered.
Macros that emit `bazel_dep` dynamically are not visible to this census.

**Candidates / Moves to.** For each `bazel_dep` pin, call `cleared_pin_target` with
`ecosystem=ecosystems/bazel`, `package=<module name>`, and `current` as the pinned version. Use its
`target` as `Moves to` when set; put `pending` tips under Pending quarantine. Do **not** invent the
concrete version from a narrow BCR or GitHub fetch or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target. When `current_cleared` is `false`, emit `kind: quarantine` with `forbidden_state` (cite `evidence_key`); when it is `null`, emit `kind: unknown_age` with `forbidden_state` — say the release date is unknown, never quarantine. Do not leave the pin silent. Yanked BCR versions never appear as
`target`.

`bazel mod deps` and `bazel mod graph` describe the resolved graph locally; they do not choose
`Moves to`.

Routine only: security `needs_unlock` for a young fixed advisory version is unchanged.

**Publish time.** Prefer `cleared_pin_target` (BCR versions + BCR `source.json` commit date; GitHub
Release only when BCR has no date). An absent date means unverified — wait.

## Update procedure

1. Run the comment pass and respect bundles.
2. Edit `bazel_dep(…, version = "…")` in `MODULE.bazel` or the relevant include.
3. Commit `MODULE.bazel.lock` when it changes; run the repository's tidy step when it uses one.
4. Toolchain and rules moves usually belong in their own change request, separate from application
   library moves.

Light verification when the overlay defines a surface for this ecosystem: a narrow documented build
rather than the whole repository on the first attempt. When the overlay names no `bazel` surface —
for example because a cold fetch does not fit a task — findings are human-only from the start
([`../policy/verification.md`](../policy/verification.md)).

## Cautions

- Only propose versions that exist in the registry, and never a yanked one.
- Refresh the lock in the same change-set as the module move; a stale lock makes the change
  unreproducible for everyone else.
- Registry metadata says nothing about non-registry pins. Do not treat it as covering toolchains or
  container images.
- When an external CLI is pinned both here and in another ecosystem — for example a schema tool
  pinned as a Go tool and as a Bazel toolchain — those pins are a bundle and move together
  ([`bsr.md`](bsr.md)).
- A major move of a rules module or of Bazel itself needs an issue and a human unlock.
- **Couplings:** when an include pulls another ecosystem's lock, a change on that side is also a
  Bazel change. Run the Bazel verification surface and refresh the lock when required, even though
  the change touched no Bazel file.
