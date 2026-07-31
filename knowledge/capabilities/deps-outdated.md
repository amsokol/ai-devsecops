---
id: capabilities/deps-outdated
kind: capability
summary: Dependency version drift, under quarantine, holds, grouping and bundle rules.
---

# Outdated dependencies

Applies to the ecosystems the product overlay enables, and only those. Never scan an ecosystem
the product has not enabled, and never invent one that has no document here.

Read together with [`../policy/quarantine.md`](../policy/quarantine.md),
[`../policy/holds.md`](../policy/holds.md), [`../policy/grouping.md`](../policy/grouping.md) and
[`../policy/bundles.md`](../policy/bundles.md).

## What to look for

- Declared pins that are behind an available version, in every manifest of every enabled
  ecosystem — including development, build and tool dependencies.
- Lock entries that resolve to older versions than the declared requirement allows.
- Build-system and toolchain pins when the ecosystem document treats them as pins.
- Pins that are currently inside the quarantine window, which is a forbidden state rather than
  ordinary drift ([`../policy/verdicts.md`](../policy/verdicts.md)).
- Floating references where a concrete version exists, which defeat both quarantine and
  reproducibility.

Each of those is a `kind` in the result — `outdated`, `quarantine`, `floating`, `bundle` — and the
finding's identity is built from it rather than from the sentence describing it
([`../CONTRACT.md`](../CONTRACT.md)). A pin fits more than one of them more often than not, and the
contract's ordered test settles which word it gets: one reference, one finding, the first word that
matches. A reference that floats *and* resolves into the quarantine window is `floating`, because
that is what has to change and pinning it concretely answers the quarantine question too. Reporting
both would ask a person to fix one line of one manifest on two issues.

When reviewing a change, the scope is only pins and lock entries the change touches — and the change
itself says which those are. Ask `read_change` for each manifest and lock in scope and work from the
lines it added; a whole file shows every pin in it, including the ones that were already there.
Reporting those makes a change wait for a line somebody else wrote, and worse, a pin that entered
quarantine after the branch was cut would block every open change until the window elapsed. That is
how a gate gets switched off. Pins nobody touched belong to the repository-wide run, which is where
the standing state of the tree is judged; there the scope is the full graph for enabled ecosystems.

The full graph means every pin, and a pin that turns out to be fine is not a pin that can be skipped.
Enumerate them all first, from the tree, before asking a registry anything; then work through the
list. What makes this more than advice is that the agent measures it: the subjects facts were
recorded about are what it treats as examined, and a pin with no fact behind it is a pin this run did
not check. Nothing is claimed about such a pin — its issue is not closed on the strength of a run
that never reached it — and the report says the sweep came up short. Two consecutive live runs over
the same six actions examined four and then all six, and the shorter one read exactly like the
thorough one.

## Evidence needed

- Current declared pins and resolved lock versions, read from the tree.
- Available versions, from the ecosystem's registry.
- Publication time for every candidate, and for any pin suspected of being inside the window.
- The comment pass result: holds, unlocks and bundle membership.
- After a lock refresh: publication times for every new or changed lock entry. A refresh often
  pulls in something newer than the package that was bumped.

A version comparison is made with the `compare_versions` tool, not by reading the strings.
Ecosystems disagree about what is newer, and the tool encodes those rules.

For routine `Moves to`, call `cleared_pin_target` once per pin and trust its `target` / `pending` /
null answer. Do not follow it with a second registry crawl (`fetch`, `go list -m -u`, `cargo
outdated`, `pip index`, Hub/BCR/`buf registry` listings) to confirm or replace that answer — that is
how a clean sweep burns millions of tokens. Discover pins from the tree (and
`list_action_pins` for github-actions); discover the remediable version from the tool.

## Judgement criteria

A candidate is proposable only when all of the following hold: it has cleared quarantine, no hold
blocks it, its bundle can move as a whole, and it is not a major without a human unlock.

A `kind: quarantine` finding waits on the **clock**, not on a person, **only when there is no
cleared `target` to move to**. Its issue must not ask for approval or a pull request, and an unlock
comment on it is refused ([`../policy/quarantine.md`](../policy/quarantine.md)). When a floating or
resolved tip is still in the window but a cleared concrete version exists, set `target` to that
cleared version, keep the young tip under Pending quarantine, and treat the finding as the remediable
move (floating→concrete / pin-down) — including human-only unlock when there is no verification
surface. Do not reuse the clock-only footer on those findings.

A caret or range requirement that already permits a newer release still counts as drift when the
declared or locked version is behind. Move the declared pin as well, so the intended floor is
explicit rather than incidental.

Do not treat transitive-only drift as a direct finding. Regenerate locks after moving the source
pin, and report transitive vulnerabilities through
[`deps-vuln.md`](deps-vuln.md) instead.

## Severity

Version drift is `low` by default and `medium` when the gap is large, when the current pin is
unsupported, or when it blocks a needed security move. A pin inside the quarantine window is a
forbidden state and is reported as such regardless of severity.

## Fix policy

Routine class only, never batched into a security change request.

- Patch and minor moves may ship once cleared.
- Majors require an issue and a human unlock first ([`../policy/grouping.md`](../policy/grouping.md)).
  State the version each finding would move to; that is what the agent measures the move against, and
  a move it cannot measure is one it cannot hold back on its own.
- Move the manifest and refresh the lock in one change-set, then verify only the surfaces the
  change touches, plus any build-system couplings.
- Do not ship a change whose lock refresh introduces an entry still inside the quarantine window.

Always report versions that were seen but not adopted, with publication and approximate clear
times, even when nothing shipped.

## False positives

- A pre-release, yanked or withdrawn version presented as the latest.
- A newer major that the ecosystem publishes under a different package name or module path.
- A version that exists in the registry index but has no artefact for the product's platform or
  language version.
- A pin deliberately held by a comment that the comment pass would have found — which is why that
  pass runs first.
- A "newer" version that is only newer by string order, such as `1.10` against `1.9`.
