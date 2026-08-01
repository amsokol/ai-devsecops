---
id: playbooks/maintain
kind: playbook
summary: Maintain the default branch — track findings as issues, ship verified fixes, reconcile.
---

# Playbook: maintenance

This run works on the whole repository at its default branch. It records findings as issues, ships
fixes that verification proves safe, and closes what is no longer true. It never approves a product
change request: judging changes belongs to [`pr-review.md`](pr-review.md).

## Trigger

- A manual run.
- A human comment on an open issue labelled `ai agent`.
- A schedule, typically weekly.

Comments from bots must not trigger a run, and a comment in a change-request conversation is not a
maintenance trigger: that is the review's business.

When woken by an issue comment, the run is narrowed to the check that owns that issue's finding, and no
sweep over the rest of the repository happens. Somebody who writes on one issue is asking about one
thing, and answering with a week's worth of unrelated findings buries the answer.

A scheduled run exists because some findings appear without anyone touching the code: a new advisory
is published against a version already pinned, a candidate's quarantine window expires, a fix becomes
available for something that had none. Those are events in time, and without a scheduled run nobody
notices them until a human happens to ask — usually after the fact. The extra rules a scheduled run
follows are in **Scheduled runs** below.

## Tasks

For every capability the run enables, over every ecosystem the overlay enables:

- [`../capabilities/code-quality.md`](../capabilities/code-quality.md) and
  [`../capabilities/code-vuln.md`](../capabilities/code-vuln.md) over the surfaces the overlay names
  as hotspots.
- [`../capabilities/deps-outdated.md`](../capabilities/deps-outdated.md) and
  [`../capabilities/deps-vuln.md`](../capabilities/deps-vuln.md) over the full dependency graph.

Before any dependency task draws a conclusion, the comment pass must have run
([`../policy/holds.md`](../policy/holds.md)) and bundles must be known
([`../policy/bundles.md`](../policy/bundles.md)). A bump proposed without them is a bump against a
human's explicit wishes.

## Evidence needed

- Manifests, locks and source surfaces discovered from the overlay and the ecosystem documents.
- Holds, unlocks and bundle membership from the comment pass.
- Version, publication-time and advisory evidence per ecosystem.
- Open issues labelled `ai agent`, so that reporting stays idempotent.
- On a wake: the issue and its comment thread.

## Aggregation

1. Collect task results; a missing or invalid result is unverified, never clean.
2. Deduplicate by finding key, then cluster findings that share one remediation.
3. Match findings against open issues by key: update the existing issue rather than opening a second
   one for the same problem.
4. Decide, per finding, whether it is shippable now — cleared quarantine, no unmet hold, bundle able
   to move as a whole, cross-bundle blockers satisfied, verification available. Do not raise an
   outdated issue for a finding that fails this test.

## Verdict and actions

### Issues

One issue per finding. Dependency titles keep a stable subject (package / bundle); code titles use
a short capability phrase plus a trimmed summary — paths stay in the body:

```text
🟠 code quality — client exits 0 on Echo RPC failure
🟠 quarantine broken — serde
```

Label it `ai agent`, creating the label if it does not exist. The body carries the capability, severity,
evidence — paths, versions, publication times, advisory references — the suggested remediation, and
any quarantine note.

For a routine **major** move, open an unlock issue **only** when human approval is the sole remaining
blocker; state the version the move goes to and, where the size of the move is a judgement rather
than arithmetic, that the finding needs approval ([`../policy/grouping.md`](../policy/grouping.md)).
The agent writes the rest of that issue — why it is waiting, what a comment there will cause, and the
record of the approval once one is given. While a non-human blocker remains, report the finding as
blocked instead — an issue asking for approval the agent cannot act on wastes attention and teaches
humans to ignore it. The same bar applies to **routine outdated**: open a dependency-update issue
only when the move can ship now (bundle and cross-bundle blockers included), or when the pin **must**
change for another reason (quarantine, unknown_age, floating, vulnerable). A newer cleared tip that
cannot build with the rest of the tree is report noise, not an issue
([`../policy/bundles.md`](../policy/bundles.md)). For a bundle, open one issue for the bundle, never
one per member — set `bundle: <id>` on every member finding so the agent collapses them before
publish. Do not open a routine major issue for a move that is already shipping as a security
remediation.

A **quarantine** finding (`kind: quarantine`) is blocked by the clock, not by a person
([`../policy/quarantine.md`](../policy/quarantine.md)), when there is no cleared `target`. Say that
on the issue; do not ask for an unlock. An unlock comment there is refused. This includes a pin
**already on the default branch** whose `current_cleared` is not true — maintenance must raise or
update that issue; silence is a defect the runner refuses. A **vulnerability** whose only fixed
version is still inside the window is the opposite: say the person may unlock as a security
exception, and set `needs_unlock`.

### Fix branches

Two classes, never mixed in one change request, and one branch per subject: every finding of that
class about one package pin or one file travels together, because they share a remediation. Ship
security before routine when both have verified fixes in the same run. Either class may be absent
when there is nothing safe to ship.

**Division of labour.** Everything to do with git and the hosting platform is the agent's, and a fix
task cannot do it even if instructed to ([`../CONTRACT.md`](../CONTRACT.md), section 2.5):

| The agent | A fix task |
| --- | --- |
| fetches, creates the branch from the finding key and class, stages, commits, pushes | applies the change in the worktree it was given |
| opens or updates the change request and writes its body from the record | runs the verification the change needs and reports what it did |
| links the issues this change remediates, and only those | says why it refused, when it refuses |
| labels the pull request `ai agent` (same as tracked issues); title is `<class> fix for <subject>` without an `agent:` prefix | — |

So a fix task has exactly two jobs, and both are judgement:

1. Apply only fixes for **this** task's findings, which are all of one class and one subject. A
   worktree carrying two classes cannot be split afterwards, and the agent will not guess which
   change belongs to which finding.
2. Verify the surfaces in scope ([`../policy/verification.md`](../policy/verification.md)), each one
   in full. Report `fixed` only when they passed; when they fail, fix forward or report `refused` and
   say why. Never lower a policy or disable a check to make verification pass — the agent compares
   what ran against the overlay's commands, so a check that was skipped or altered is visible rather
   than assumed. When the overlay names no surface for this finding's ecosystem, there is no fix
   task at all unless a person with write access unlocks a pull request on its issue — then the
   change is prepared without local verification so CI on that PR can be the proof
   ([`../policy/verification.md`](../policy/verification.md)).

What the agent guarantees in return: it never force-pushes an open fix branch, never touches another
agent's branch or change request, never mixes classes in one change, and recreates a branch only when
no open change request remains on it and after saying so on the old one.

**Open change request on that branch.** The subject already has a fix under review. Do not prepare a
second branch, and do not push onto the open one to chase a newer target version — silent retargeting
rewrites what a reviewer is reading. Comment on the finding's issue instead: the pull request is
still open, with its link; when the finding's current target differs from what that PR proposes, say
so and leave the PR alone for a person to merge, close, or ask again.

**Closed change request, abandoned branch.** The previous attempt was rejected or abandoned, and the
finding is still open. Comment on that closed change request that a new attempt will follow, remove
the abandoned `agent/…` refs (local and remote — delete, do not force-push over the old tip), create
the branch again from the current default branch, apply today's remediation, and open a **new**
change request. Unlock stamps on the issue authorise the subject, not the tip of the old PR.

### Reconcile

Reconcile against **this** checkout only, and only on the strength of a task that actually looked:

1. List open issues labelled `ai agent`.
2. For each, identify the task that owns that finding's capability. Close the issue only when that
   task finished with outcome `clean` and the finding is absent — that is, it verified the tree rather
   than merely failing to report. Comment the evidence when closing.
3. When the owning task ended unverified or exhausted, leave the issue open and say nothing. Silence
   is correct here; a "still present" comment would be as unfounded as a closure.
4. Never close based on another branch or an unmerged fix.
5. When a finding returns after its issue was closed, the agent reopens that closed issue (same
   finding key) with a comment that it returned — it does not open a second ticket.

This condition is not pedantry. Closing on absence alone means the first scanner outage marks every
known problem as fixed, and the record disappears exactly when the tooling is least trustworthy
([`../policy/unknowns.md`](../policy/unknowns.md)).

### Woken by a human

Two things are settled by the agent before any task of such a run starts, and neither is a task's to
decide. *Whether this comment may start a run at all*: an account without write access to the
repository does not authorise anything, and neither does a comment on a conversation the agent did not
open. *What the comment asks for*: a dedicated `intent` session reads it and the agent chooses the
course from a table. Any clear authorisation counts as one — natural language, no phrase to match
exactly, and demanding one is a defect.

What reaches the work, therefore, is a run already narrowed to one finding:

1. That finding is the run's primary subject. Re-establish it first; a neighbouring finding of the same
   capability may be handled in passing, an unrelated sweep may not.
2. Ship it on the correct track when quarantine, bundles and verification allow. When they do not, the
   blocker is the answer, and it must be named — a quarantine clear time, an unmet bundle condition, a
   verification failure.
3. Never ask again for approval that was already given on that issue, and never report that finding as
   awaiting a human afterwards.
4. Do not write the status comment. The agent posts it, from what the run recorded, so that every
   sentence a person reads on their own issue is a fact rather than a summary. A second status from a
   task would be the agent talking twice, and the two would eventually disagree.

When somebody asks how to fix something rather than authorising it, no task runs at all: the answer is
written by the `writer` role and nothing in the repository is touched.

## Scheduled runs

A scheduled run does the same work under stricter restraint, because nobody is waiting for it. The
same run every week, unrestrained, becomes noise, and the first thing a team does with noise is turn
it off.

**Stay within the queue the overlay allows.** The overlay states how many agent change requests may
be open at once and how many new issues one run may open; when it is silent, the agent's own default
applies. When a limit is reached, do not drop the
remaining findings and do not squeeze them into one issue: leave them unreported and let the next run
take them. Work the queue in a fixed order — class `security` first, then `routine`, and by severity
within each class ([`../policy/verdicts.md`](../policy/verdicts.md)) — so that a backlog of routine
bumps can never crowd out an advisory.

**Say nothing when there is nothing.** A run that finds no new findings, closes nothing and ships
nothing writes nowhere: no comment, no issue, no summary. A weekly "all clear" trains people to skip
whatever the agent writes, and the one message that matters gets skipped with it. The run manifest
already records that the run happened and what it checked.

**One run at a time.** If a maintenance run is already in progress, the scheduled run does not queue
behind it and does not start beside it. Two runs mutating one default branch fight over the same
branches and issues; skipping a week costs less.

**Escalate a repeating failure once.** An inconclusive scheduled run has no audience — there is no
change request whose checks a human will read. So when the same failure reason recurs across
consecutive runs, open a single issue about the failure itself, keyed on the reason and the surface
that broke, and never a second one. This is the one exception to the silence rule above, and it is
what keeps a quietly broken source — a registry page that changed shape, an expired credential — from
looking like a clean repository for months
([`../policy/unknowns.md`](../policy/unknowns.md)).

## Degradation

- A documented gap is reported as a gap and does not stop the rest of the run
  ([`../policy/unknowns.md`](../policy/unknowns.md)).
- A failure — scanner, host, source shape, permission, budget — makes the run inconclusive for that
  capability. The other capabilities still complete, and the report names what did not run.
- An inconclusive capability neither opens nor closes issues, and never ships a fix that depends on
  the facts it failed to establish.
- When verification fails, or a fix is refused for any other reason, nothing ships. **Report that
  failure on the issue** — a comment in the agent's own words naming why — instead of leaving the
  issue silent. Silence after an attempted fix is indistinguishable from being ignored. The same
  duty applies when a verified branch could not be pushed or proposed. Wake already answers on the
  issue; scheduled and manual maintain must too.
- Concurrent wakes on different issues must not supersede each other's work.
