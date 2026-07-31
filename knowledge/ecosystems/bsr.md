---
id: ecosystems/bsr
kind: ecosystem
summary: Buf Schema Registry modules and remote plugins, including the plugin resolve probe.
applies_to: [buf.yaml, buf.lock, buf.gen.yaml]
---

# Buf Schema Registry (BSR)

The ecosystem with the least tooling support, and therefore the one where the difference between
proven and assumed matters most.

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | `buf.yaml`, `buf.lock`, `buf.gen.*.yaml` | reproducible |
| module labels | `tool` | `buf registry` CLI | reproducible |
| remote plugin candidates | `tool` | plugin label list, else GitHub Releases for `owner/name` | reproducible / heuristic dates from Release |
| remote plugin tag exists | `tool` | resolve probe, see below | reproducible |
| publish time | `web` | label timestamps, else GitHub Release `published_at` | heuristic when from GitHub |
| advisories | `none` | — | — |

There is no audit tool for this registry. Advisories are unverified; treat these pins as
supply-chain sensitive and review release notes for high-impact modules and plugins instead of
inventing findings.

## Requirements

- Binaries: `buf`.
- Hosts: `buf.build`, `api.github.com`.
- Registry authentication is required when the product consumes remote plugins.

## Detect

| Kind | Where | Example |
| --- | --- | --- |
| Module dependency | `buf.yaml` under `deps:` | `buf.build/bufbuild/protovalidate:v1.2.2` |
| Module lock | `buf.lock` | resolved commit or digest |
| Remote plugin | `buf.gen.*.yaml` under `plugins[].remote` | `buf.build/owner/plugin:v0.8.1` |
| Coupled application pin | another manifest | a crate or module on the same version family |

Run the comment pass first: this ecosystem is where holds and bundles appear most often.

## Evidence recipes

**Candidates / Moves to.** For each module dependency **and** each remote plugin pin, call
`cleared_pin_target` with `ecosystem=ecosystems/bsr`, `package=buf.build/owner/name` (or
`owner/name`), and `current` as the pinned label. The tool lists module labels, then plugin labels;
when both fail or the plugin label list is empty (common for protoc plugins such as
`buf.build/anthropics/buffa`), it falls back to GitHub Releases for `owner/name` and applies
quarantine to those tags. Use its `target` as `Moves to` when set; put `pending` tips under Pending
quarantine. Do **not** invent the concrete label from a narrow `buf` listing or by eye, and
do **not** re-run `buf registry …` / HTML fetches to second-guess the tool after it answered. When
`buf` and GitHub are both unavailable the tool returns `target=null` — record a gap; do not invent.

`buf registry module|plugin label list … --format json` remains the underlying listing inside the
tool. Ignore branch-like labels unless the pin itself uses one.

Routine only: security `needs_unlock` for a young fixed advisory version is unchanged.

**Module labels (discovery only when the tool cannot run).**

```bash
buf registry module label list buf.build/owner/module --format json --page-size 50
buf registry plugin label list buf.build/owner/plugin --format json --page-size 50
```

**Remote plugin tags — the resolve probe.** Use this to **confirm a specific tag already chosen**
(bundle unlock / verify the named `target` exists), not to discover candidates. The registry's
plugin information commands frequently reject or falsely deny protoc plugins, so their output alone
is never unlock evidence. Prove the tag by resolving it, in the scratch directory so nothing can
reach the repository:

```yaml
version: v2
plugins:
  - remote: buf.build/owner/plugin:v0.9.0
    out: out
```

Run `buf generate` in that directory and read the outcome:

| Result | Meaning |
| --- | --- |
| exit 0 with files produced | the tag exists — the unlock condition is met |
| a not-found error naming the latest available version | the tag does not exist |
| any other error, including authentication or network failure | not confirmed, therefore unmet |

Never point the output at real generated sources, and never treat "not confirmed" as "exists".

Release notes from the plugin's own project are supporting evidence only; they do not replace the
probe when a bundle requires a registry tag. An HTML fetch of a registry page proves nothing, since
the page is a client-rendered shell.

**Publish time.** Use label or commit timestamps from the registry JSON when present, and treat an
absent value as unverified, which means wait.

## Update procedure

1. Move every bundle member together — typically a plugin tag together with the application pin on
   the same version family ([`../policy/bundles.md`](../policy/bundles.md)).
2. **Module dependencies:** after changing a label in `buf.yaml`, run `buf dep update` and keep the
   resulting `buf.lock` change with the manifest change.
3. **Remote plugins:** move the tag in `buf.gen.*.yaml`. This does not change `buf.lock` unless a
   module dependency also moved.
4. Regenerate the stubs. This requires registry authentication when the product uses remote plugins.
5. Refresh or remove stale `agent:` comments on every member.

Verification is the product's codegen step followed by compiling and testing the consumers.

## Cautions

- The module label, the lock, and the generated stubs are one change-set. Shipping the label alone
  leaves the repository in a state nobody built.
- A remote plugin tag is proven by the probe, never by a page or an assumption.
- When the CLI is pinned in more than one place — for example as a Go tool and as a Bazel toolchain —
  those pins move together unless a hold says otherwise ([`bazel.md`](bazel.md)).
- A codegen or plugin major that changes generated APIs needs an issue and a human unlock; prefer one
  issue for the coupled bundle when human approval is the only remaining blocker.
- Probe artefacts stay in the scratch directory and are never committed.
