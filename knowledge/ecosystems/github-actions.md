---
id: ecosystems/github-actions
kind: ecosystem
summary: Pinned CI actions, container images and tool versions in workflows.
applies_to: [.github/workflows, .github/actions]
---

# GitHub Actions

## Capability profile

| Fact | Method | Source | Reliability |
| --- | --- | --- | --- |
| declared pins | `tool` | workflow and action YAML | reproducible |
| available action versions | `api` | repository tags and releases | reproducible |
| action publish time | `tool` | `action_publish_time` (GitHub Release API) | reproducible |
| image available tags | `api` | the image registry | reproducible |
| image publish time | `web` | registry tag metadata | heuristic |
| advisories | `web` | published advisories for the action or image | heuristic |

Image publish time and advisories are heuristic here: registries expose them inconsistently, so a
finding built on them may comment but not block ([`../policy/verdicts.md`](../policy/verdicts.md)).

## Requirements

- Binaries: `skopeo` when image metadata is required.
- Hosts: `api.github.com`, `github.com`, `hub.docker.com`, `registry-1.docker.io`, `auth.docker.io`,
  `ghcr.io`.

A run carries no credential for the hosting platform: commands are given an environment without one,
deliberately, so that nothing a task executes can spend the agent's identity. Ask the API directly
instead of through a command line that needs a login. Anonymous access is rate-limited, so prefer the
endpoint that answers the question over the index that has to be searched.

## Detect

- Workflow and action YAML under `.github/workflows/` and `.github/actions/`.
- Pins of the form `uses: owner/name@ref`, where the reference is a tag, a branch, or a commit
  digest.
- Container images: `jobs.<id>.container`, `jobs.<id>.services.<name>.image`, and equivalent
  `image:` keys in product-owned reusable workflows.
- Local `uses: ./…` references have no registry version and are out of scope.
- Tool versions pinned in `env:`, such as a build-tool version variable, count as pins when the
  product documents them.

Call `list_declared_pins` (or the `list_action_pins` alias) first on every repository-wide outdated
sweep for this ecosystem. That tool is the census: every third-party `uses:` and `image:` above,
once per package. Then record a fact for each package it returns — including pins that are fine —
before querying registries. The agent fails the task when recorded subjects do not cover that
census. Never invent the pin list by reading workflow files by eye; a sweep that stops at the first
few interesting pins is incomplete, not clean.

## What counts as a concrete version here

The two forms in this ecosystem are pinned differently by convention, and [`../CONTRACT.md`](../CONTRACT.md)
asks the ecosystem to say which is which, because `floating` versus `outdated` follows from it:

| Reference | Concrete? |
| --- | --- |
| `uses: owner/name@v5`, `@v5.2.1`, `@<40-hex digest>` | yes — a major tag is this ecosystem's ordinary pin |
| `uses: owner/name@main`, `@master`, `@latest`, any branch | no |
| `image: name:1.2.3`, `name:25.0.1_9-jdk`, `name@sha256:…` | yes |
| `image: name:latest`, `:stable`, `:25-jdk`, `:bookworm` | no, whenever the registry publishes version tags |

A major action tag moves under the pin, so it is a float in the strict sense, and calling it one
would put a permanent finding on almost every workflow in existence for following the convention its
own ecosystem documents. An image line tag is the opposite case: registries publish exact tags beside
it, the cost of the exactness is nothing, and running whatever `:25-jdk` resolved to this morning is
the thing this capability exists to notice.

## Evidence recipes

**Action candidates.** For each third-party `uses: owner/name@current`, call
`cleared_pin_target` with `ecosystem=ecosystems/github-actions` and `kind=action`. Use its `target`
as `Moves to` when set; put `pending` tips under Pending quarantine. Do **not** invent the concrete
tag from a narrow GitHub query or by eye. After the tool answers, do **not** re-query the registry (`fetch`, ecosystem CLIs) to second-guess `target`, `pending`, or a null target. When `current_cleared` is `false`, emit `kind: quarantine` with `forbidden_state` (cite `evidence_key`); when it is `null` and the pack marks `float_like` (or `current` is a channel such as `@stable` / `@latest` / major-only with no dated tip), emit `kind: floating` with `forbidden_state`; otherwise emit `kind: unknown_age` with `forbidden_state` — say the release date is unknown, never quarantine. Do not leave the pin silent. Floating references such as `@main`, `@master`, `@latest`
never appear as `target` (the tool returns a concrete cleared tag or null).

Routine only: a security finding whose only fixed version is still in window still uses
`needs_unlock` and may prepare a PR after a person unlocks — that path is unchanged.

**Action publish time.** Always call `action_publish_time` for a single known concrete tag when not
using `cleared_pin_target`:

```text
action_publish_time(package=owner/name, tag=v7.0.1)  →  published_at (else created_at)
```

Pass that into `check_quarantine`. **Never** use a commit's committer date: it predates the Release
and falsely clears the window. When `found: false`, treat as unverified — do not clear.

Prefer `cleared_pin_target` for choosing `Moves to` — it uses Release dates internally.

**Image candidates.** For each third-party `image:` / container pin, call `cleared_pin_target` with
`ecosystem=ecosystems/github-actions` and `kind=image`. Channel tags (`25-jdk`, `1.24-bookworm`,
`latest`) are never `target`; the tool returns the newest cleared concrete tag on the same major
(and variant suffix), e.g. `25.0.3_9-jdk` or `1.24.5-bookworm`, or null. Do not invent the tag with
a narrow Hub query — that is how demo2 drifted to an older `25.0.2_10-jdk`. When `current_cleared`
is `false`, emit `kind: quarantine` with `forbidden_state` (cite `evidence_key`); when it is `null`,
emit `kind: unknown_age` with `forbidden_state` — say the release date is unknown, never quarantine.

**Image publish time.** Inside `cleared_pin_target` the Hub `last_updated` field is used as a
heuristic timestamp (clearing needs margin). For a one-off check outside that tool, use the same
field or `skopeo inspect`. For a digest pin, use the manifest creation time.

**Advisories.** Search published advisories for the action repository and for the image name; a
compromised action is a supply-chain event, not a version problem. Prefer official publishers when
replacing an abandoned action or an unmaintained base image.

## Update procedure

1. Run the comment pass; respect bundles when the product documents them.
2. Move `uses:` to the cleared tag, or to a full commit digest when product policy requires digest
   pinning. A major-line jump ships only after an issue unlock.
3. Move image references to the cleared concrete tag or digest, and keep the same image consistent
   across every workflow that mentions it.
4. For a version pinned in `env:`, move the variable and any matching download URL in the same
   change-set.

Verification for this ecosystem is whatever surface the product names in its overlay — typically a
workflow linter or schema check it already runs in CI
([`../policy/verification.md`](../policy/verification.md)). Do not attempt to execute workflows
locally. When the overlay names no `github-actions` surface, findings here are human-only: reported,
never prepared as an automated fix. "CI will run on the pull request" is not a surface the agent can
record.

## Cautions

- Never widen permissions or expose secrets to make a bump work. If a newer action needs broader
  access, that is a finding for a human, not a change to apply.
- Patterns that check out an untrusted head with elevated permissions are a code vulnerability, not
  a dependency matter ([`../capabilities/code-vuln.md`](../capabilities/code-vuln.md)). Do not
  weaken existing guards while editing workflows.
- A major move of a widely used setup or checkout action needs an issue and a human unlock, then its
  own change request.
- Never replace a pinned tag with a floating reference to clear an advisory.
- Do not leave or introduce a floating image tag when a concrete version exists. Runtime, operating
  system and JDK image majors need a human unlock like any other major.
