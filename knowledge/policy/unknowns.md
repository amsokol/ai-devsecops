---
id: policy/unknowns
kind: policy
summary: What to do when a required fact cannot be established.
---

# Unknown facts

Coverage is never complete. Some ecosystems have no audit tooling, some registries publish no
timestamps, hosts go down, pages change shape, and budgets run out. This document defines the
only acceptable behaviour in those cases.

## The rule

A fact that could not be established is recorded as unverified, with a reason. It is never
silently converted into any of the following:

- a clean result ("no vulnerabilities found" when nothing could be scanned);
- a finding ("possibly vulnerable" with no evidence);
- an approval ("looks fine" when the check did not run).

## Two kinds of unknown

The reason matters more than the fact, because it decides what the run is allowed to conclude.

| Reason | Kind | Example |
| --- | --- | --- |
| `no-tooling` | expected gap | The ecosystem's capability profile marks this fact as `none`. |
| `unavailable` | failure | Host unreachable, request failed, command timed out. |
| `unexpected-shape` | failure | The source responded, but the value could not be located. |
| `not-permitted` | failure | The required binary or host is outside the agent's ceiling, or this run executes nothing at all because the change came from outside the repository. |
| `exhausted` | failure | The task ran out of budget before finishing. |

An **expected gap** is a documented limit. It is reported and it does not stand in the way: an
ecosystem with no audit tooling must not block every change forever, because a gate that always
refuses gets bypassed and then ignored.

A **failure** means something that was supposed to work did not. It makes the run inconclusive
([`verdicts.md`](verdicts.md)), which refuses the merge without claiming anything about the code.

The reason this distinction exists: merge authority is the check result, so if a failure produced a
passing check with a footnote, the whole gate would be suppressible by anyone able to break a scanner,
block a host, or exhaust a budget. The absence of a result is not a result.

`unexpected-shape` deserves the loudest reporting of the five. It usually means a registry changed its
response format, so a recipe needs a human — and until someone fixes it, every run on that ecosystem
will be inconclusive.

## A partial answer is not an answer

A response that did not arrive whole establishes nothing, even when the part that arrived contains
something that looks like the value. Registry documents that list every version of a package are the
usual case: a tool may decline to hand such a document over, or deliver it cut short, and a date or a
version taken from the remainder is a guess wearing a source URL. Ask a narrower question instead —
the address that names the single version, or the part of the document that holds the answer — and if
neither is available, record the fact as unverified rather than reading what happened to fit in the
window.

Guessing is not a narrower question. Probing whether a version exists, incrementing a number and
probing again, answers where the guesses stopped rather than where the releases did; the run then
records a latest version that was never published as the newest and calls it reproducible.

## Effect on findings

Whatever the reason, an unverified fact never becomes a finding by itself and never opens an issue —
**except** when the missing fact is the publish time of a pin already in use: that is
`kind: unknown_age` on the deps-outdated task ([`quarantine.md`](quarantine.md)), because silence
would hide an uncheckable pin and calling it quarantine would invent a date. There is still nothing
to "fix" automatically; the issue is the gap made visible.

When an entire capability could not run, say that plainly instead of reporting the capability as
passing. "Dependency vulnerabilities: not checked, no scanner for this ecosystem" is useful.
"Dependency vulnerabilities: pass" in the same situation is a lie that the reader cannot detect.

## Effect on resolution

An unverified capability may not resolve or close anything. A finding is closed because a task
verified that it is gone — outcome `clean` — never because it is absent from a run that did not look.
Otherwise the first scanner outage closes every open issue as fixed, and the record of known problems
disappears exactly when the tooling is least trustworthy.

## Retrying

Retry once when the reason is `unavailable`, since transient failures are common. Do not retry
`no-tooling` or `not-permitted`: the answer will not change within the run, and the attempt only
spends budget.

Do not work around a `not-permitted` reason by looking for another binary or another host that
happens to be allowed. Requirements are declared in the ecosystem document and granted by the
agent; circumventing that is a policy breach, not resourcefulness.

## Reporting

Unverified facts belong in a dedicated section of the report, not scattered among findings.
Group them by subject, name the reason, and say which kind it is, because that is what tells the
reader whether to fix the pipeline or accept the limit. Keep the entries short.

If the same expected gap appears in every run, it is a standing decision worth revisiting: either the
ecosystem needs different tooling, or the overlay should name another source for that fact.

A run with no human audience — a scheduled maintenance run — has nowhere to put this section where
someone will read it, so a failure there must be escalated once it repeats
([`../playbooks/maintain.md`](../playbooks/maintain.md)). Otherwise a broken recipe reads as a quiet
repository.
