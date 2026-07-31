---
id: policy/quarantine
kind: policy
summary: Release quarantine — do not adopt a version until it has been published for N days.
---

# Release quarantine

**Approach:** do not adopt a version until it has been published for at least **N** days. The
approach lives here; the duration **N** is product-specific and comes from the overlay only.
Never invent **N**, and never round it in the agent's favour.

When the product's own tooling has a cooldown setting of its own, the two must agree. A package
manager configured to wait a different number of days than **N** will quietly produce candidates the
policy rejects, or hide ones it would accept; the overlay's notes name any such setting so that a
change to **N** is known to require a change there too.

Publication timestamps are evidence. How to obtain them for a given ecosystem is described in
that ecosystem's document; the general procedure is in
[`../evidence/acquisition.md`](../evidence/acquisition.md).

## Date arithmetic

Age and clear-time arithmetic is performed by the `check_quarantine` tool, never by reasoning. Given
a publication timestamp and **N**, the tool answers whether the version has cleared, when it will
clear, and how to phrase the pending line. Hand-rolled `published + N` is not acceptable: it is
unreproducible and it silently disagrees with itself across a run.

When the publication timestamp is unverified, treat the candidate as **not cleared**. Waiting is
always the safe direction.

## Heuristic timestamps

Some ecosystems have no authoritative publication time, and the date can only be derived from
somewhere else — an upstream release, a commit. Such a timestamp is heuristic
([`../evidence/acquisition.md`](../evidence/acquisition.md)) and is used asymmetrically, because the
two directions carry different risk:

- it may keep a candidate **waiting**, since waiting is harmless;
- it may **clear** a candidate only when the version is unambiguously older than the window. Close to
  the boundary, wait for the next run instead of trusting a date that came from a different system.

Without this asymmetry an ecosystem with no timestamps would either freeze forever or adopt versions
on a guessed date. Neither is acceptable, and the choice between them should not depend on the mood of
a run.

## Candidate versions

For a version you might bump **to**:

1. Establish its publication time as evidence.
2. Ask `check_quarantine` whether it has cleared **N**. Not cleared means wait — do not bump.
3. Prefer the newest version that has already cleared the window.
4. Unverified publication time counts as not cleared.

## Versions already pinned in the tree

A currently pinned version that is younger than **N** is a forbidden state
([`verdicts.md`](verdicts.md)), not a routine finding.

During maintenance: open or update an issue for it, report the forbidden state, and do not
"fix" it by adopting an even newer version that is also inside the window. Prefer waiting, or a
documented security exception, or an older version that has already cleared.

During review of a change: introducing or keeping such a pin in the change is a blocking
finding.

## Lock refreshes

A fix is not shippable when refreshing the lock introduces any entry that is still inside the
window — the same rule as adopting that version directly. Prefer waiting, or constrain
resolution to a cleared version when the ecosystem allows it.

## Security exception

An exception must be explicit and must name the advisory and the pin, either in a comment next
to the pin ([`holds.md`](holds.md)) or in the issue or change-request body. Never infer an
exception from urgency, and never create one to unblock a routine bump.

## Unlock comments on quarantine findings

A comment on an issue is not a way around the clock. Three cases, and they must not be mixed:

| Finding | What the issue says | What an unlock comment does |
| --- | --- | --- |
| Routine / quarantine-only (`kind: quarantine`, no cleared `target`) | Waiting for the **window** to clear. Do **not** say the finding waits for a person, and do not ask for a pull request. | **Refuse.** Reply that the agent will not prepare a change while quarantine still holds. |
| Routine quarantine tip in window, but a cleared concrete `target` exists | Remediable move to that cleared pin (and pending for the young tip). Use human-only / major footers as for any other move — not clock-only. | **Allow** when that footer allows (including CI PR when there is no surface). |
| Security / vulnerability whose only fixed version is still inside the window | Waiting for a person: say explicitly that they **may** unlock, because fixing the advisory outweighs quarantine. | **Allow.** The unlock is the security exception; prepare the change (verify locally when a surface exists; otherwise CI on the PR is the proof). |
| Human-only for lack of a verification surface, and not held by quarantine | Waiting for a person to ask for a pull request so CI can be the proof ([`verification.md`](verification.md)). | **Allow**, as that policy already says. |

The first row is the common maintenance case: a pin already on the default branch that has not
cleared **N** and has no older cleared candidate to pin to. Mixing the human-only footer onto it
teaches people to unlock the clock, and then forces the agent either to break quarantine or to look
as if it ignored them.

## Pending quarantine reporting

Always report versions that were **seen but not adopted** because they are still inside the
window — both direct candidates and lock entries that a cleared bump would have introduced.
Report them even when nothing shipped, and use an explicit empty marker when there are none:

```markdown
## Pending quarantine
- none
```

Otherwise one short bullet per item — package with its ecosystem or surface, version,
publication time, and approximate clear time, phrased by `check_quarantine`:

```markdown
## Pending quarantine
- `syn` 3.0.3 (cargo lock) — published 2026-07-22T00:35Z, clears ~2026-07-24T00:35Z
```

Omit packages that already shipped in this run. Avoid wide tables: these reports are read on
phones as often as on desktops.
