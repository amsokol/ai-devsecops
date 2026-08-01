---
id: ecosystems/cargo
kind: ecosystem
summary: Dependency facts and update procedure for Rust projects.
applies_to: [Cargo.toml, Cargo.lock, rust-toolchain.toml]
---

# Cargo (Rust)

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | every `Cargo.toml`, plus `Cargo.lock` | reproducible |
| available versions | `api` | crates.io | reproducible |
| publish time | `api` | crates.io | reproducible |
| advisories | `tool` | `cargo audit` or `cargo deny` | reproducible |

## Requirements

- Binaries: `cargo`, and `cargo-audit` or `cargo-deny` for advisories; `cargo-outdated` when
  available.
- Hosts: `crates.io`, `index.crates.io`.

## Detect

- Workspace and package `Cargo.toml`, plus `Cargo.lock`.
- `rust-toolchain.toml` or `rust-toolchain` when present. Toolchain pins are report-only unless
  product policy or an unlock comment allows moving them.

## Evidence recipes

**Declared pins.** Call `list_declared_pins` with `ecosystem=ecosystems/cargo` first on every
repository-wide outdated sweep. Record a fact for every package in its `packages` list — including
pins that are fine — before querying crates.io. The agent fails the task when the census is not
covered. Path and git deps are omitted from that list. Then read requirements from
`[dependencies]`, `[dev-dependencies]`, `[build-dependencies]` and workspace `workspace.dependencies`
as the tool already enumerated them.

**Candidates / Moves to.** For each direct crate pin, call `cleared_pin_target` with
`ecosystem=ecosystems/cargo`, `package=<crate>`, and `current` as the manifest requirement (or the
locked version when classifying the resolved pin). Use its `target` as `Moves to` when set; put
`pending` tips under Pending quarantine. Do **not** invent the concrete version from a narrow
crates.io fetch or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target. When `current_cleared` is `false`, emit `kind: quarantine` with `forbidden_state` (cite `evidence_key`); when it is `null`, emit `kind: unknown_age` with `forbidden_state` — say the release date is unknown, never quarantine. Do not leave the pin silent.

`cargo outdated` remains useful to discover which crates lag; it does not choose `Moves to`.

Do **not** conclude that direct pins are current from `cargo update --dry-run`. That command
reports lockfile resolution changes and routinely misses a stale manifest pin — for example
`serde = "1.0.228"` while the registry has `1.0.229` and the lock still resolves the older one.
This is the single most common mistake in this ecosystem.

Routine only: a security finding whose only fixed version is still in window still uses
`needs_unlock` and may prepare a PR after a person unlocks — that path is unchanged.

**Publish time.** Prefer `cleared_pin_target` (it uses crates.io `created_at` internally). For a
one-off check of a known version:

```text
https://crates.io/api/v1/crates/<crate>/versions
```

Use `created_at`. Skip yanked entries. For a crate with a long release history this document may be
too large to hand over whole; `select: versions.0` gives the newest entry, and the crate's own
`https://crates.io/api/v1/crates/<crate>/<version>` answers about one version directly.

**Advisories.**

```bash
cargo audit
```

Use `cargo deny check advisories` when the product is configured for `cargo-deny`.

## Update procedure

1. Run the comment pass and respect bundles. Crates frequently couple to schema-registry plugins
   or generated code ([`bsr.md`](bsr.md)).
2. Edit the declared pin in `Cargo.toml`.
3. Refresh the lock for that crate: `cargo update -p <crate>`, or
   `cargo update -p <crate> --precise <version>` when a specific version is required.
4. Keep manifest and lock in the same change-set.

Light verification when the overlay defines nothing more specific: `cargo check`, or `cargo test`
for the touched workspace members.

## Cautions

- A semver-compatible caret requirement still counts as drift when the declared or locked version
  is behind a cleared newer release. Move the declared pin so the intended floor is explicit.
- Git-tag and path dependencies are compared against the remote tag or commit policy, and
  quarantine applies to the published tag or commit time when it can be established.
- A major move needs an issue and a human unlock, especially for web frameworks, crypto, async
  runtimes and widely used core crates.
- Do not move the Rust toolchain pin without an explicit unlock; treat a toolchain major or minor
  change as a major move.
