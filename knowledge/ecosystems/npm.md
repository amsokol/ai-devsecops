---
id: ecosystems/npm
kind: ecosystem
summary: Dependency facts and update procedure for Node projects.
applies_to: [package.json, package-lock.json, pnpm-lock.yaml, yarn.lock]
---

# npm (Node)

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | `package.json` and the lockfile | reproducible |
| available versions | `api` | npm registry | reproducible |
| publish time | `api` | npm registry | reproducible |
| advisories | `tool` | the package manager's audit command | reproducible |

## Requirements

- Binaries: one of `npm`, `pnpm`, `yarn`, matching the lockfile in the tree.
- Hosts: `registry.npmjs.org`.

## Detect

- `package.json` plus exactly one lockfile: `package-lock.json`, `pnpm-lock.yaml`, or `yarn.lock`.
- Match the package manager to the lockfile. Never switch managers to make a command work; that
  rewrites the lock and turns a dependency bump into a migration.
- Read `dependencies`, `devDependencies` and `peerDependencies`.

## Evidence recipes

**Declared pins.** Call `list_declared_pins` with `ecosystem=ecosystems/npm` first on every
repository-wide outdated sweep. Record a fact for every package in its `packages` list — including
pins that are fine — before querying the registry. The agent fails the task when the census is not
covered. `file:` / `link:` / `workspace:` / git specs are omitted from that list.

**Candidates / Moves to.** For each direct package pin, call `cleared_pin_target` with
`ecosystem=ecosystems/npm`, `package=<name>`, and `current` as declared (or locked when classifying
the resolved pin). Use its `target` as `Moves to` when set; put `pending` tips under Pending
quarantine. Do **not** invent the concrete version from a narrow registry query or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target. When `current_cleared` is `false`, emit `kind: quarantine` with `forbidden_state` (cite `evidence_key`); when it is `null`, emit `kind: unknown_age` with `forbidden_state` — say the release date is unknown, never quarantine. Do not leave the pin silent.

`npm outdated` / `pnpm outdated` / `yarn outdated` remain useful to discover lag; they do not choose
`Moves to`.

Routine only: security `needs_unlock` for a young fixed advisory version is unchanged.

**Publish time.** Prefer `cleared_pin_target` (registry `time` internally). For a one-off check:

```text
https://registry.npmjs.org/<package>/<version>
```

The package-wide document also carries `time[<version>]`, but for a long-lived package it lists every
version ever published and may be too large for a tool to hand over; a date read from a document that
arrived incomplete is not the registry's answer
([`../policy/unknowns.md`](../policy/unknowns.md)). Scoped packages are requested with the slash
encoded: `https://registry.npmjs.org/@scope%2Fname/<version>`.

**Advisories.**

```bash
npm audit --json
pnpm audit
yarn npm audit
```

## Update procedure

1. Run the comment pass and respect bundles.
2. Move the pin with the project's own manager, for example `npm install <package>@<version>`,
   `pnpm add <package>@<version>`, or `yarn add <package>@<version>`.
3. Keep the lockfile change together with `package.json`. Never delete the lockfile to "refresh"
   it — that discards the resolution the product tested against.

Light verification when the overlay defines nothing more specific: the project's test script, then
its build, and at minimum a successful install from the lock.

## Cautions

- `package.json` cannot hold comments, so holds live in sibling documents. Check them before
  concluding that a pin is free to move ([`../policy/holds.md`](../policy/holds.md)).
- A major move of a framework, bundler, test runner or the TypeScript compiler needs an issue and a
  human unlock, then its own change request with release notes linked.
- Check `peerDependencies` after any move: a satisfied install can still leave a peer range broken.
- Do not raise the `engines` range unless product policy allows it; a runtime floor jump is a major
  move.
