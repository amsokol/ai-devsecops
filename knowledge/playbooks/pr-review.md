---
id: playbooks/pr-review
kind: playbook
summary: Review a proposed change and produce a verdict; never open issues or fix branches.
---

# Playbook: change review

This run is **verdict only**. It reviews the proposed change, answers humans in the conversation,
and decides whether the change may proceed. It never opens issues and never creates branches, and it
changes nothing on its own initiative — a reviewer that also repairs the code cannot be trusted to
judge it. The one change it will prepare is one somebody asked for, offered in the conversation for
them to apply; see the trigger below.

## Trigger

- A change request is opened, updated with new commits, or reopened.
- A human replies in one of the agent's review threads.
- A manual run.

A run woken by a reply works only in that thread: the comment is read for what it asks for, and the
answer goes into the same conversation. Such a run judges nothing and publishes no verdict — it
analysed nothing, so it has no stance to revise and no thread it may resolve.

What the answer *is* depends on what was asked. A question about why the remark matters is answered in
prose. A question about how to fix it is answered with the change: it is made against the head of the
change under review, in an isolated copy where this product's verification can be run over it, and
offered in the thread as something the author may apply. The review still commits nothing and pushes
nothing — the copy is discarded, and the branch under review moves only if a person moves it. The
exception is a change from outside the repository, where the answer is prose whatever was asked; the
next section says why.

## Changes from outside the repository

A change whose head lives in a fork is read and never executed. No command runs against it: not a
scanner, not an install, not this product's verification. The reason is not the code's quality but
where the run happens — a review job holds the credentials the agent speaks with, and a build script
from a fork is a stranger's code running beside them
([`../scm/github.md`](../scm/github.md)).

Three things follow, and each is stated in the review rather than absorbed quietly:

- a capability that needs a command records `not-permitted` and reports what reading and the
  registries did establish. Approximating the command's answer from reading is worse than the gap: a
  reader cannot tell it apart from having run something.
- no change is prepared. A patch nothing was run over cannot carry a verification label, and offering
  it without one invites a click on an edit nobody checked.
- a change that touches dependency manifests will therefore usually be **inconclusive** rather than
  approved, and that is the intended answer. Nothing verified those pins. Approval waits for a run on
  a head somebody with write access has taken responsibility for — typically by bringing the commits
  onto a branch in this repository.

Comments from bots, including this agent's own, must never start a run: that is how review loops
begin. One run per change request at a time; a newer event supersedes an in-progress run, and the
surviving run loads the full conversation state rather than only the newest event.

Draft changes are skipped: report that and stop.

## Tasks

Tasks follow from the trigger and the changed files, not from a model's improvisation:

| Task | Runs when |
| --- | --- |
| [`../capabilities/code-quality.md`](../capabilities/code-quality.md) | source files changed |
| [`../capabilities/code-vuln.md`](../capabilities/code-vuln.md) | source files or workflow files changed |
| [`../capabilities/deps-outdated.md`](../capabilities/deps-outdated.md) | manifests or locks changed for an enabled ecosystem |
| [`../capabilities/deps-vuln.md`](../capabilities/deps-vuln.md) | manifests or locks changed for an enabled ecosystem |

Tasks run in parallel and independently; none of them may assume another one's result. A capability
that has nothing in scope is reported as not applicable, which is different from passing.

## Evidence needed

- The diff, and enough surrounding code to judge each candidate finding.
- For dependency tasks, **only the pins and lock entries the change touches**: current version,
  target version, publication time, advisories, and the comment pass result for those pins.
- Prior review threads on this change, and the conversation, so that answered questions are not
  re-asked and fixed findings are not re-reported.

The general acquisition procedure is in
[`../evidence/acquisition.md`](../evidence/acquisition.md); ecosystem documents supply the sources.

## Aggregation

1. Collect the task results. A missing or invalid result counts as unverified, never as clean.
2. Deduplicate by finding key. The same problem reported by two tasks is one finding.
3. Cap each finding's action by the reliability of its evidence
   ([`../policy/verdicts.md`](../policy/verdicts.md)).
4. Reconcile with existing threads, and only where the evidence allows it. A finding that is still
   present stays on its existing thread instead of becoming a new comment. A finding may be answered
   and resolved **only** when the task that owns it finished with outcome `clean` on this head — that
   is, it looked and confirmed the problem is gone. When that task ended unverified or exhausted, the
   thread stays open, because absence in a run that did not look is not a fix
   ([`../policy/unknowns.md`](../policy/unknowns.md)).
5. Compute the verdict from what remains, and from whether any required task failed
   ([`../policy/verdicts.md`](../policy/verdicts.md)).

## Verdict and actions

Post exactly one review body, then the inline threads. Evidence belongs on the line it concerns, not
in a summary table.

```markdown
## Decision
**Approve** | **Request changes** | **Comment** | **Inconclusive** — <one short reason>

## Findings

### code-quality — Pass | Fail | N/A | Not checked
<one short line, or short bullets when Fail>

### code-vuln — Pass | Fail | N/A | Not checked
### deps-outdated — Pass | Fail | N/A | Not checked
### deps-vuln — Pass | Fail | N/A | Not checked

## Coupled bundles
- none

## Pending quarantine
- none

## Not checked
- none

## Threads
- none
```

Rules for the body: omit capability sections that did not run; use `N/A` when a capability had
nothing in scope, and `Not checked` when it had something in scope but could not establish it. Keep
bullets to roughly twenty words; no wide tables, no screenshots, no pasted logs beyond a few lines.
**Coupled bundles**, **Pending quarantine** and **Not checked** are always present, with an explicit
`- none` when empty — an omitted section reads as "nothing to say" when it should read as "nothing
found".

Under **Not checked**, name the fact, the subject and the reason, and say whether it is a documented
gap or a failure. Those two look identical to a reader and mean opposite things.

A question asked in one of the agent's threads is answered by the run that reply wakes, in that same
thread, and never by leaving it for the next verdict. A reviewer that posts a verdict while ignoring a
direct question is worse than one that says nothing. A change offered there carries the label the
verification earned — `verified` or not — because the person reading it decides whether to apply it.

Merge authority belongs to the check result, not to the platform's approval event; details are in
[`../scm/github.md`](../scm/github.md).

## Degradation

The run always produces a verdict, and the verdict always says which of the two failure modes it is
in ([`../policy/unknowns.md`](../policy/unknowns.md)).

- A **documented gap** — a fact the ecosystem profile marks as unobtainable — is listed under **Not
  checked** and does not stand in the way of approval.
- A **failure** — a scanner that would not run, a host that did not answer, a source whose shape
  changed, a permission that was refused, a budget that ran out — makes the verdict inconclusive. The
  review says what did not run and why, and it does not approve. A failing check is not a finding
  about the code, and it is also not permission to merge.
- If every task fails, the verdict is inconclusive, never an empty approval. An empty review that
  reads as approval is the worst possible outcome of a broken run, because it is indistinguishable
  from a good one.

Never work around a failure by lowering the claim. "No vulnerabilities found" after a scanner crash is
the kind of statement that destroys trust in every other line of the review.
