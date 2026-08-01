---
id: ecosystems/go-modules
kind: ecosystem
summary: Dependency facts and update procedure for Go modules.
applies_to: [go.mod, go.sum]
---

# Go modules

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | `go.mod`, `go.sum` | reproducible |
| available versions | `tool` | `go list -m -u all` | reproducible |
| publish time | `api` | module proxy `.info` | reproducible |
| advisories | `tool` | `govulncheck` when installed | reproducible |

When `govulncheck` is not available, advisories for this ecosystem are unverified. Report the gap;
do not substitute recalled vulnerabilities.

## Requirements

- Binaries: `go`, and `govulncheck` for advisories.
- Hosts: `proxy.golang.org`, `sum.golang.org`.

## Detect

- `go.mod` and `go.sum` at the repository root and in any nested modules.
- Direct `require` pins **and** the `tool (` block. Tools installed through the module graph are
  direct pins for policy and quarantine purposes, and they are frequently forgotten.
  A `tool (` line has no version by design: the census takes the version from that module's
  `require` row (often marked `// indirect`) and uses the **module** path as the pin identity, so
  quarantine/`cleared_pin_target` hit the module proxy — not a false `floating` on an empty tool
  line.
- In a multi-module repository, work only on the modules the product enables.

## Evidence recipes

**Declared pins.** Call `list_declared_pins` with `ecosystem=ecosystems/go-modules` first on every
repository-wide outdated sweep. It covers direct `require` lines and the `tool` block; `// indirect`
is omitted. Record a fact for every package in its `packages` list — including pins that are fine —
before querying the proxy. The agent fails the task when the census is not covered.

**Candidates / Moves to.** For each direct module pin, call `cleared_pin_target` with
`ecosystem=ecosystems/go-modules`, `package=<module path>`, and `current` as the `go.mod` version.
Use its `target` as `Moves to` when set; put `pending` tips under Pending quarantine. Do **not**
invent the concrete version from a narrow proxy fetch or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target. When `current_cleared` is `false`, emit `kind: quarantine` with `forbidden_state` (cite `evidence_key`); when it is `null`, emit `kind: unknown_age` with `forbidden_state` — say the release date is unknown, never quarantine. Do not leave the pin silent.

`go list -m -u all` remains useful to discover which modules lag; it does not choose `Moves to`.
Prefer tooling the repository already provides — a Makefile target or script — when it exists.

Routine only: security `needs_unlock` for a young fixed advisory version is unchanged.

**Publish time.** Prefer `cleared_pin_target` (proxy `@v/<version>.info` `Time` internally). For a
one-off check:

```text
https://proxy.golang.org/<module>/@v/<version>.info
```

Use the `Time` field. For modules the proxy does not serve, the version's commit timestamp in
version control is an acceptable substitute.

**Advisories.**

```bash
govulncheck ./...
```

## Update procedure

1. Run the comment pass and respect bundles.
2. `go get <module>@<version>`, or a careful `go.mod` edit. Tool modules move the same way as
   libraries.
3. Run `go mod tidy` in that module.
4. Keep `go.sum` consistent; do not hand-edit it except to resolve a known conflict.
5. After moving a tool module, reinstall it before running any verification that invokes it.

Light verification when the overlay defines nothing more specific: `go test ./...`, narrowing the
package set if the repository is large, then `go build ./...`.

## Cautions

- A major move usually changes the module path, and the old path keeps resolving. Both facts matter:
  the move needs an issue and a human unlock, and the import paths must change with it.
- Respect the `go` directive. Raising the language version is a major move and needs an unlock.
- Do not add a `replace` directive unless the repository already uses them; it hides the real
  dependency from every other tool.
