---
id: policy/verdicts
kind: policy
summary: Finding classes, severity scale, forbidden states, and which evidence may block a change.
---

# Verdicts

How a set of findings becomes a decision. Read this together with
[`unknowns.md`](unknowns.md), which covers what happens when a fact could not be established.

## Classes

Every finding belongs to exactly one class, and the class decides which track may remediate it.

| Class | Produced by | Fix track |
| --- | --- | --- |
| `security` | `capabilities/code-vuln`, `capabilities/deps-vuln` | security branch |
| `routine` | `capabilities/code-quality`, `capabilities/deps-outdated` | routine branch |

Never move a finding between classes to make shipping easier, and never mix classes in one
change request.

## Severity

| Severity | Meaning |
| --- | --- |
| `critical` | Exploitable now, or breaks the product for every user. Reachable vulnerability, leaked secret, data loss. |
| `high` | Serious defect or vulnerability with a plausible path to impact. Wrong results, missing authorisation, unhandled failure on a main path. |
| `medium` | Real problem with limited or conditional impact. Degradation, edge-case failure, a vulnerability in tooling a user of the product never installs. |
| `low` | Worth knowing, no immediate impact. Routine version drift (`outdated`), defensive improvement. |

Severity describes impact on this product rather than the number a scanner printed, but it is not
an open judgement: each capability document states how its findings are graded, and that statement
is the rule. Where the rule is a table, follow the table. For `deps-outdated`, a floating pin is
`medium` and a quarantine break on the pin in use is `high` — the runner enforces those floors.

Do not grade a finding down because the vulnerable code looks unused, or up because it looks
alarming. Both are arguments from reading rather than from evidence, and they come out differently
on two readings of the same input — which would make the verdict depend on the run rather than on
the code. What you observed belongs in the finding's text, where a human can weigh it and, if they
choose, accept the finding explicitly.

## What blocks

A finding blocks only when **both** conditions hold: its class and severity are in the table below,
and the evidence behind it is reproducible.

| Class | Severity | Blocks |
| --- | --- | --- |
| `security` | `critical`, `high` | yes |
| `security` | `medium`, `low` | no — comment |
| `routine` | `critical` | yes |
| `routine` | `high`, `medium`, `low` | no — comment |
| forbidden state | any | yes |

A routine finding blocks only at `critical`, which in practice means the change breaks the product.
Version drift never blocks: holding a change hostage to an unrelated outdated dependency is how a
gate loses the room's consent.

This table is the whole definition. Do not invent additional blocking conditions in a run, and do not
raise a severity in order to reach a block — if something should block and cannot, that is a policy
question for a human, not a judgement call to make silently.

## Evidence ceiling

Class and severity say what a finding deserves; the evidence says what it is allowed to do.

| Evidence reliability | Highest permitted action |
| --- | --- |
| `reproducible` (`tool`, `api`) | block the change |
| `heuristic` (`web`, `model`) | comment with source link and obtained value |

A finding may always be reported with a weaker action than permitted. It may never be reported
with a stronger one. When a finding rests on several pieces of evidence, the weakest one
determines the ceiling.

So a critical vulnerability established only by reading a web page comments rather than blocks — and
says why, with the link, so a human can promote it in seconds.

## Forbidden states

These are policy breaches, not ordinary findings. They are reported even when nothing else is
wrong, and they require reproducible evidence like any other blocking claim.

- A pinned version that is still inside the quarantine window
  ([`quarantine.md`](quarantine.md)).
- A changed pin that violates an unmet hold ([`holds.md`](holds.md)).
- A partial move of a coupled bundle ([`bundles.md`](bundles.md)).
- Widened permissions or secrets introduced to make a dependency bump work.

A forbidden state is never "fixed" by moving further in the same direction — for example by
adopting an even newer version that is also inside the window.

## Review verdict

| Verdict | When | Run result |
| --- | --- | --- |
| request changes | At least one blocking finding remains. | `blocked` |
| inconclusive | A required check failed to run ([`unknowns.md`](unknowns.md)). | `inconclusive` |
| comment | Only non-blocking findings, or unresolved questions to answer. | `pass` |
| approve | No blocking findings, threads clear or resolved. | `pass` |

Approval is a statement about what was checked, and it is only available when the checks actually
ran. A documented gap — an ecosystem whose profile marks a fact as unobtainable — does not prevent
approval, but it is named in the body so the reader knows the boundary of the claim. A **failed**
check does prevent approval: see [`unknowns.md`](unknowns.md) for why the two are treated
differently.

Draft changes are skipped: report that and stop.

## Maintenance outcome

A maintenance run reports the strongest applicable state: a critical finding without a fix or
mitigation, a forbidden state, remaining actionable findings, or a clean tree. Maintenance never
blocks a product merge; blocking is the reviewing run's job.

## Noise

A finding that cannot be supported with evidence is not reported at all. Once a review contains
plausible guesses, the substantive findings stop being read, and the whole gate loses its value.
Prefer an explicit gap over a confident invention.
