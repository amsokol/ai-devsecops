---
id: policy/grouping
kind: policy
summary: How to split dependency and code changes into reviewable change requests.
---

# Grouping

A change request is a unit of human review. Group changes so that one reviewer can hold the
whole story in their head at once.

## Prefer

- **Security remediations on their own.** One finding per branch, minimal remediation, shipped
  before routine work in the same run.
- **Routine work separately.** Patch and minor dependency moves, code-quality fixes and other
  non-security findings. Default is one finding per change request.
- **Patch and minor of the same ecosystem together** when they are low-risk and unrelated to a
  major framework.
- **One change request per major**, after a human unlock, never batched with unrelated patches.
- **Same reason together** — for example all type-stub minors — when the review story is
  identical.

## Avoid

- Mixing security remediations with routine work in one change request. This is a hard rule, not
  a preference: it forces a reviewer to weigh urgency and risk in the same breath.
- Mixing unrelated ecosystems unless a coupled bundle requires it ([`bundles.md`](bundles.md)).
- Attaching a major move to a pile of unrelated patches.
- Touching unrelated code "while we are here".

## Risk tiers

A heuristic for how freely to group:

| Tier | Examples | Default |
| --- | --- | --- |
| Low | type stubs, linters, small libraries, patch-only moves | group freely on the routine track |
| Medium | utilities, middleware, CLI helpers | small groups; skim the changelog |
| High | language frameworks, database drivers, auth, crypto, build toolchain | separate change request; read the release notes |

A security advisory always takes the security track regardless of tier.

## Majors

Any major move needs an issue and a human unlock before a routine change request is opened.
Patch and minor may ship when quarantine, holds and bundles allow.

What counts as major — if unsure, treat it as major:

- A semantic-version major, including `0.x` to `1.x` when that is the package's breaking line.
- A major-line float jump in a CI action pin, such as `@v5` to `@v7`.
- A container, operating system or runtime image major tag.
- A language or toolchain floor jump, such as the `go` directive, `requires-python`, the Rust
  toolchain pin, or a Node engines range.

The hold is a field on the finding, not a resolution to remember. State the version the remediation
moves to; the agent measures the move itself and holds a semantic-version major whether or not
anything asked it to. For the majors no comparison can see — the float jump, the image tag, the
raised floor — say so on the finding, and the agent holds it on your word. A held finding is
reported and never changed: no branch, no change request, in that run or any later one.

Procedure during maintenance:

1. Open or update an issue for the candidate, but only when the move would be shippable after
   the unlock alone — quarantine cleared, bundle members available. An issue that asks for
   approval the agent cannot act on wastes a human's attention.
2. Do not open a routine change request until a human unlocks on that issue.
3. After the unlock, ship one change request for that major, or for one unlocked bundle, and
   link the release notes or migration guide in the body.

The unlock is recorded on the issue where it was granted, and it stays granted: a fix that fails to
verify is retried under the same approval rather than by asking again. Approval is for the move, not
for one attempt at it, and re-asking teaches people to approve without reading.

Exceptions: a security remediation may include a major move without a routine unlock, still
respecting bundle atomicity — so do not hold one, and the agent will not hold it for you. Never
attach a routine major to a security change request.

## Monorepos

Update shared libraries and workspace packages before leaf applications when versions must stay
aligned, and always say which package path was changed.

## Bundles versus groups

A **bundle** ([`bundles.md`](bundles.md)) is an atomic version train: its members must move
together or not at all. A **group** is a review convenience. A single unlocked bundle that spans
ecosystems or codegen is usually one change request even when grouping rules would otherwise
split it — on the security track when the move remediates a vulnerability, otherwise on the
routine track.

## When the list is long

1. Propose a prioritised batch: security first, then routine patch, then minor, then unlocked
   majors. Open issues for majors that still await unlock.
2. Execute only that batch, still splitting security from routine.
3. Leave a short note about what remains, so the next run does not rediscover it from scratch.
