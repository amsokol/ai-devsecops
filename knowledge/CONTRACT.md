# Library ↔ agent contract

Contract version: **1** (draft).

This document defines what a knowledge author may rely on when writing a skill, and what the
agent guarantees in return. It is the only place where runtime facts are normative for the
library; every other document in this repository is prose written for humans and models.

Audience: authors of documents under `playbooks/`, `capabilities/`, `ecosystems/`, `policy/`,
`scm/` and product overlays.

Rule of thumb: if a skill instructs the agent to do something not described here, that
instruction is invalid. Skills describe *which* source to consult and *how* to interpret the
result; they never invent tools, flags or data formats.

## 1. Execution model

A run has two phases, and skills must respect the boundary between them.

**Evidence acquisition.** Facts are collected by any permitted means: running a scanner,
querying a registry API, invoking an ecosystem CLI, reading release notes, extracting values
from a web page. Every fact is recorded as an *evidence record* (section 4).

**Decision.** Judgement is applied to the collected evidence only. During this phase the agent
performs no network access and runs no commands. A skill that asks for "just check one more
thing" while deciding is written incorrectly; the need must be declared as required evidence.

Work is executed by subagents in four roles. The first two do the work this library describes; the
last two exist because a person can write a comment, and neither of them produces findings:

| Role | Purpose | Mutating tools |
| --- | --- | --- |
| `analyst` | collect evidence, produce findings | no |
| `fixer` | change code and run verification, in an isolated worktree | yes, files only |
| `intent` | read what somebody's comment asks for, and nothing else | no tools at all |
| `writer` | answer that person in prose | no |

A `fixer` changes files and runs commands; it does not touch git and does not touch the hosting
platform. The branch, the commit and everything published belong to the agent, which does them after
the session ends and after checking that verification actually ran (section 7). A skill therefore
never instructs a subagent to commit, push, or open anything — see
[`playbooks/maintain.md`](playbooks/maintain.md) for which step belongs to whom.

An `intent` session is given two pieces of text — the agent's own remark and the reply to it — and
returns which of a fixed set of intents the reply expresses. It gets no tools and no library documents:
its answer must depend on those two texts and nothing else. What each intent then causes is a table in
the agent, so nothing a skill says can widen it, and no reading of a comment can grant a permission.

A `writer` session is given the playbook and the capability document behind the finding under
discussion, and writes one reply for a person to read. It may read the repository, has no worktree, and
produces no findings and no evidence: whatever it writes is prose in a comment, and nothing else in the
run depends on it. Skills therefore need not address it; the parts of a document that explain *why* a
finding matters are what it uses.

The two are divided by what is left when the session ends, not by what they write. A `fixer` leaves a
worktree the product's own verification can be run against, so what it produced can be labelled and
applied; a `writer` leaves text. This is why a question about *how to fix* something goes to a `fixer`
even when the answer is published as a comment: a patch quoted from prose is a patch nobody checked,
and it is the one a person would apply.

Subagents run in parallel and cannot see each other's context. A skill must not assume that
another subagent has already established a fact; everything it needs must be either in its own
slice of the library or acquired as evidence.

## 2. Tools

The agent exposes exactly the tools listed below. Names are stable; semantics are guaranteed.

### 2.1 Repository access (all roles)

| Tool | Guarantee |
| --- | --- |
| `read_file` | Reads a file inside the target repository. Paths outside it are rejected. |
| `list_files` | Lists paths by glob inside the target repository. |
| `search_text` | Regex search over tracked files; returns matches with paths and line numbers. |
| `read_change` | For one file, what the change under review added and removed, with line numbers. |

`read_change` is available only when the run has a change under review. Skills for repository-wide
work must not depend on it.

### 2.2 Commands (all roles)

`run_command` executes an allowlisted binary with arguments. Guarantees and limits:

- only binaries on the allowlist may be invoked; anything else fails immediately, and this is
  not a reason to retry with a different spelling;
- there is no shell: no pipes, no redirection, no command chaining;
- the working directory is the target repository, or the worktree for `fixer`;
- a **scratch directory** outside the repository is available and may be used as the working
  directory for temporary artefacts, such as a probe that must write files. It is discarded when
  the task ends, so probe output can never reach a commit. `analyst` may write there through
  `run_command` even though it has no `edit_file`;
- each call has a timeout; on timeout the call fails and the fact stays unverified;
- exit code, stdout and stderr are returned; long output is truncated with an explicit marker;
- commands must not install packages, modify global state, or push to a remote.

A skill names the tool it needs in prose (for example, the ecosystem's audit command) and
describes how to read its output. If the binary is not permitted for the current run, the
required fact becomes unverified (section 5).

**How a binary becomes permitted.** An ecosystem document declares the binaries its procedures
need, in its `Requirements` section. The agent grants a declared binary only if it also falls
within the agent's own ceiling — the set of binaries the agent is willing to run at all. A
declaration is a request, not a permission: adding a line to a knowledge document cannot widen
what the agent may execute. Anything declared but outside the ceiling is refused at startup with
an explicit message, so the gap is visible instead of surfacing as a mysterious failure mid-run.

### 2.3 Network (analyst and fixer)

| Tool | Guarantee |
| --- | --- |
| `fetch` | GET an allowlisted https URL. A response that parses as JSON counts as an API answer and is reproducible; anything else is a page and is heuristic. |

Rules:

- an ecosystem document declares the hosts its procedures need, in its `Requirements` section,
  and the agent grants them only within its own ceiling — same mechanism and same reasoning as
  for binaries (section 2.2);
- no credentials, tokens or repository secrets are ever attached to `fetch`;
- POST and other mutating HTTP verbs are not available; mutation happens only through the
  actions in section 2.5;
- a large answer is not handed over whole. Name the part needed, and ask for names alone where the
  names are the answer — a version list is the keys of a releases object, not the files under them.
  A document that would not fit is refused with its size rather than truncated into something that
  no longer parses.

**There is no tool that reads the hosting platform.** Pull request metadata, comments and threads
are read by the agent's own code, before and after the sessions, and what a task needs from them is
in its prompt. A skill must therefore never instruct a session to look something up on the platform:
what is not in the prompt or in the repository is not available to it.

### 2.4 Derived facts (all roles)

| Tool | Guarantee |
| --- | --- |
| `compare_versions` | Ecosystem-aware ordering of two version strings, and the semantic-version relationship between them: major, minor, patch, or unordered. |
| `list_declared_pins` | Deterministic census of every direct registry pin the named ecosystem's manifests declare. Path/git/workspace pins are omitted from the coverage set. |
| `list_action_pins` | Compatibility alias for `list_declared_pins` on `ecosystems/github-actions`. |
| `action_publish_time` | GitHub Release `published_at` (else `created_at`) for an action `owner/name` + concrete tag. Does not use committer dates. |
| `cleared_pin_target` | Newest quarantine-cleared concrete `target` (and `pending` young tips) for a package pin in any listed ecosystem (`ecosystem` document id required; `kind` only for github-actions). Also returns `current_resolved` / `current_cleared`; the runner records `current-cleared` evidence from that answer. |
| `check_quarantine` | Given a publication timestamp, answers whether the window has elapsed, when it will, and how to phrase the pending line. |
| `known_fact` | Whether this run — or the cache of immutable facts — already answered a question about a subject. |
| `record_fact` | Records an established fact against the calls it rests on, and returns the evidence key a finding cites. |
| `record_gap` | Records that a fact could not be established, with the reason. |

Skills must not compute version ordering or date arithmetic by reasoning. These questions have
exact answers, and a model's arithmetic is neither reproducible nor auditable.

`list_declared_pins` is required at the start of a repository-wide `deps-outdated` sweep for
every listed ecosystem: pass the ecosystem document id. The agent fails the task when recorded
subjects do not cover that census. Never invent the pin list by reading manifests by eye.
`list_action_pins` remains as an alias for `ecosystems/github-actions` only.

On maintain `deps-outdated`, the runner **may** pre-acquire that census and every registry pin's
`current-cleared` answer before the sweeper session starts, write them into run evidence, and hand
the model a compact prep pack path in `given`. When those registry tools are absent from the
session, the analyst/sweeper must judge from the pack and evidence — do not try to re-query
registries another way. When prep fails and the tools remain, the tools-first path above still
applies.

On maintain `deps-vuln`, the runner **may** pre-run the ecosystem's advisory scanner (the same
command the ecosystem document names), seed `advisories` evidence, and hand the vuln session a pack.
When `run_command` / `fetch` are absent after that prep, judge from the pack — do not re-crawl.
Ecosystems whose advisories are `web` or `none` keep today's path (no scanner prep).


`action_publish_time` is required for quarantine arithmetic on github-actions tags when checking one
known tag: pass its `published_at` into `check_quarantine`. A publish-time fact that cites a
committer date fails the task — that clock predates the Release and falsely clears the window.

`cleared_pin_target` is required when setting `Moves to` / `target` for an outdated or floating
finding (routine) in every listed ecosystem document, and whenever a pin is examined for quarantine
of the version **in use**. Pass the ecosystem id, package, and current pin; for
`ecosystems/github-actions` also pass `kind` `action` or `image`. Do not invent the concrete version
via a narrow registry fetch. Security `needs_unlock` for a young fixed advisory version is unchanged:
a person may still unlock a PR. BSR covers **modules and remote plugins** (the tool tries `module`
then `plugin` label list; for empty protoc-plugin labels, `bufbuild/plugins` catalog then
`source_url` Release, then GitHub `owner/name` last); when those fail the tool returns
`target=null` and often `current_cleared=null` — emit `unknown_age`, do not invent a date or call it
quarantine.

The runner records a `current-cleared` evidence fact from each successful answer (value `true`,
`false`, or null when the publish time could not settle). Cite that key on findings — do not call
`record_fact` for `current-cleared` yourself. Evidence is **run-shared** (one store for the whole
run so the same pin is not asked twice); completeness obligations are **not**. When
`current_cleared` is `false`, the **`deps-outdated` task for that package's ecosystem** must emit
`kind: quarantine` (or floating/vulnerable when those win) with `forbidden_state: true`. When it is
`null`, emit `kind: unknown_age` (or floating/vulnerable) with `forbidden_state: true` — the summary
and issue title must say the release date is unknown; do not use `quarantine`. The agent fails
**that** task if the finding is missing — the same class of gate as an incomplete pin census,
scoped the same way (capability + ecosystem). A `deps-vuln` task, or `deps-outdated` for another
ecosystem, is not charged for the fact. Unverified publish time for a *candidate* still counts as
not cleared for Moves to; for the pin in use it is `unknown_age`, not quarantine.

After a successful `cleared_pin_target` call — including answers the runner seeded via outdated
prep — do **not** re-list the same registry with `fetch`,
`run_command`, or ecosystem CLIs (`go list -m -u`, `cargo outdated`, `pip index`, `buf registry …`,
Hub/PyPI/BCR pages) to second-guess `target`, `pending`, `current_cleared`, or a null target. A null
`target` with whatever `pending` the tool returned is a complete answer for routine Moves to when
the pin in use is already cleared; when it is not, the finding is still required. Use `known_fact`
before any registry read. Narrow exceptions that remain allowed when those tools are offered:
`list_declared_pins` (and the `list_action_pins` alias) / `action_publish_time` for census and
github-actions publish time; the BSR **resolve probe** only to
confirm a *specific* plugin tag already named (bundle / unlock), never to discover candidates.

`compare_versions` answers only about version strings. It does not decide whether a change counts
as **major for policy purposes**: a major-line float jump in a CI action pin, a runtime image tag
move, or a raised language or toolchain floor are all major without being a semantic-version major.
That classification is judgement and lives in [`policy/grouping.md`](policy/grouping.md). When the
tool returns `unordered` — the strings are not comparable in this ecosystem's scheme — treat the
question as unverified rather than guessing a direction.

`known_fact` matters most where acquisition is expensive: publication timestamps are immutable and
version lists change slowly, so a cached answer is both cheaper and more stable than a repeated web
extraction. Ask it before acquiring anything.

`record_fact` accepts only the identifiers of calls the task actually made, which is what makes an
evidence key mean something. A fact cannot be recorded for work that was skipped, and reliability is
derived from those calls rather than chosen — so a finding cannot be promoted into one that blocks by
describing its source differently.

### 2.5 Mutation (fixer only, and only when the run permits it)

| Tool | Guarantee |
| --- | --- |
| `edit_file` | Replaces an exact fragment of a file inside the isolated worktree. Paths outside it are rejected. |

`run_command` (section 2.2) also writes, because an ecosystem's own tool is how a lock file is
regenerated. For a `fixer` its working directory is the worktree, so those writes land in the same
isolated tree.

**No tool mutates git or the hosting platform.** No subagent creates a branch, commits, pushes,
comments, opens an issue or opens a change request. The agent does all of that itself, once, after
aggregation:

- it is what makes a repeated run idempotent — a subagent commenting per finding would duplicate
  threads that the agent reconciles by key (section 7);
- a commit message and a change's contents are then derived from the finding rather than from how a
  model read an instruction;
- "never force-push", "never touch the default branch" and "never rewrite history" are guaranteed by
  the absence of the tool instead of by a sentence in a prompt.

Merging is never available to anyone. The agent may report that a change is acceptable; a human or a
platform rule performs the merge.

### 2.6 Not available

Interactive prompts and approval dialogs; arbitrary shell; arbitrary network; reading files
outside the target repository; environment variables and secrets; package installation; history
rewriting; merging; disabling or editing platform rules; modifying the library itself.

## 3. Untrusted content

Everything that comes from outside the library and the agent's own configuration is data, never
instruction. This includes file contents, diffs, dependency metadata, registry pages, release
notes, changelogs, issue and pull request text, and command output.

Guarantees from the agent:

- external content is passed to the model inside an isolated block, marked as untrusted;
- instructions found inside such content are ignored, including instructions to approve a
  change, to skip a check, to widen an allowlist, or to ignore these rules;
- a subagent's output is untrusted input for aggregation: it is validated as data and never
  interpreted as an instruction.

Requirement for skill authors: never write a procedure that lets external text decide the
verdict. A pull request description may explain intent, and that explanation may be quoted in a
comment, but it is not evidence.

## 4. Evidence records

Every fact used for a decision is recorded. Fields:

| Field | Meaning |
| --- | --- |
| `question` | What was being established, in a stable form (for example, `publish-time`, `advisories`, `latest-version`). |
| `subject` | What it is about: ecosystem and package, or a file path. |
| `value` | The value obtained, or absent when unverified. |
| `origin` | How it was obtained: `tool`, `api`, `web`, `model`. |
| `source` | Concrete source: command invoked, URL requested, or file path. |
| `observed_at` | When it was obtained. |
| `reliability` | `reproducible` for `tool` and `api`; `heuristic` for `web` and `model`. |
| `status` | `verified` or `unverified`; when unverified, a reason is required. |

`reliability` is derived from `origin`, not chosen by the model. It determines what the agent is
allowed to do with the resulting finding (section 6).

## 5. Unverified facts

When a fact cannot be established — no tooling exists for the ecosystem, the host is
unreachable, a page changed shape, the command timed out, or the budget ran out — the agent
records an evidence entry with `status: unverified` and a reason.

Guarantees:

- an unverified fact is never reported as a clean result;
- an unverified fact never produces a finding by itself, and never blocks a change;
- unverified facts are surfaced in the run summary, so that gaps in coverage are visible instead
  of silent.

For ecosystems where a whole class of facts is unobtainable, the ecosystem document declares
this in its capability profile with `none`, and the agent reports it as unverified without
attempting acquisition.

## 6. Findings

A finding is a claim that something needs attention. Fields:

| Field | Meaning |
| --- | --- |
| `key` | Stable identifier used for idempotency (see below). |
| `capability` | Which capability produced it. |
| `class` | `security` or `routine`. |
| `severity` | `critical`, `high`, `medium`, `low`. |
| `subject` | File and symbol, or ecosystem and package. |
| `location` | Where to attach a comment right now: file and line, or manifest and line. Volatile by design and deliberately absent from `key`. |
| `summary` | One sentence, addressed to the author of the code. |
| `slug` | Stable kebab-case identity for a **path** finding. Required when `subject` is a path. Part of the key — never derived from `summary`. |
| `rationale` | Why it matters here, referring to the evidence. |
| `evidence` | References to the evidence records supporting it. |
| `remediation` | What to do, when known. |
| `kind` | What is wrong, from the closed vocabulary below. Required for a finding about a package. |
| `target` | The version the remediation moves to, when it is a version move and there is one. |
| `needs_unlock` | This may not ship until a person approves it on its issue. |
| `bundle` | Coupled-bundle identifier from the comment pass (`agent: bundle <id>`). When set, the agent keys and tracks the finding by that id, not by the member pin. |
| `via` | How a transitive package entered the resolved graph (`direct → … → subject`). Required for `kind: vulnerable` when the subject is not a direct declared pin; shown on the issue as "Brought in by". Omit when the subject itself is declared. |

**What a problem is called, not how it was worded.** A finding about a package names its `kind`, and
the vocabulary is closed:

| `kind` | When |
| --- | --- |
| `quarantine` | The version in use, or the one a reference resolves to, is inside the window (`current_cleared` is false). |
| `unknown_age` | Publication time for the pin in use could not be established (`current_cleared` is null). Not quarantine. |
| `floating` | The reference is not a concrete version: a branch, a channel, a rolling tag. |
| `outdated` | A newer version exists, has cleared quarantine, **and** the move can ship now (see kind order). |
| `bundle` | Members that must move together are at versions that do not agree. |
| `vulnerable` | An advisory covers what is pinned. |

The finding's identity is built from it, so the same problem next week must arrive under the same word.
Before this field existed the identity fell back to a slug of the summary, and a summary is written
afresh every run: the second live maintenance run rephrased four findings, every key moved, and four
issues were raised beside the four already describing the same problems. One of those carried an
approval a person had given, which then matched nothing, and the agent asked them for it again. Nothing
none of these words fit belongs in a fifth word invented on the spot — report it under the closest one
and say the rest in the summary, and if that keeps happening this table is what should grow.

**When more than one word fits, the reference decides — not the judgement.** More than one usually
does fit: a rolling image tag is both a float and behind a newer release, and both sentences are true.
Choosing between true sentences is the kind of question a model answers differently on Tuesday, and
the word is part of the identity, so the run after picks the other one and files the same problem
twice. The two live runs that followed the introduction of this field did exactly that with one image
tag: `floating` in one run, `outdated` in the next, two issues for one line of YAML.

So it is settled by a test on the reference, applied in this order, first match wins:

1. an advisory covers what is pinned → `vulnerable`;
2. the reference does not name one immutable version → `floating`, and nothing below is asked. There
   is no "outdated" for a reference that has no version to be behind. What counts as naming a version
   is the ecosystem's, and its document says so plainly, because `@v5` is an ordinary pin for a
   GitHub action and `:25-jdk` is a rolling tag for a container image;
3. it disagrees with the members it must move with → `bundle`;
4. the version in use — or the one a floating reference resolves to — has a known age that has not
   cleared quarantine (`current_cleared` is `false`) → `quarantine`, and set `forbidden_state: true`.
   This is the forbidden state on the default branch, not "a tip exists somewhere";
5. publication time for that pin could not be established (`current_cleared` is null) →
   `unknown_age`, and set `forbidden_state: true`. The issue title and summary must say the release
   date is unknown; do not use `quarantine` (that word claims a date);
6. a newer version exists and has cleared → `outdated` **only when that move can ship now** (the
   pin's bundle and any NOTES / comment-pass cross-bundle or constraint blockers can move in the
   same change, or human unlock is the sole remaining blocker for a major). Otherwise omit the
   finding: name the blocker in the report; do not open a dependency-update issue for a bump that
   cannot build.

Young *candidates* that were seen but not adopted belong under **Pending quarantine** reporting
([`policy/quarantine.md`](policy/quarantine.md)), not as the sole reason for `kind: quarantine` when
the pin in use is already cleared. When floating or vulnerable wins steps 2 or 1 and the resolved
tip is still inside the window, keep that kind and still set `forbidden_state: true`. When those
kinds win and the age is unknown, keep that kind and still set `forbidden_state: true`.

One reference produces one finding. A pin that is both floating and covered by an advisory is one
`vulnerable` finding whose summary says it also floats — not two, because two issues about one line
ask a person to fix the same line twice.

**A pin with nowhere cleared to move names no target.** For a finding about a package, `target` is
what says there is somewhere to go, and the agent reads it that way: a finding without one is
reported and never queued for a fix. When `cleared_pin_target` names a cleared `target` — including
an older cleared version to pin down to while the tip is still young — use that value. Do not name
the current uncleared version, and do not invent a lower version the tool did not return: a session
asked to fix a pin that cannot move invents a move, and the first live maintenance run downgraded an
action by a major version that way. Never "fix" an in-window pin by adopting a newer tip that is
also inside the window.

**Holds are enforced, not remembered.** `needs_unlock` is a declaration and the agent acts on it:
a held finding is reported and never changed, in that run and every later one, until an approval is
recorded on its issue. The agent adds the same hold wherever it can prove one — `target` against the
current version is a semantic-version major — so forgetting the field cannot switch the policy off,
and setting it can only ever add a hold. What the field is *for* is the majors no comparison can see,
which [`policy/grouping.md`](policy/grouping.md) lists.

**Stable keys.** The key is composed of the parts that identify the problem and excludes the
parts that drift between runs. For dependency findings: capability, ecosystem, package, and
`kind` — not the current version, not the summary, and not the advisory identifier. Every advisory
against one pin is one bump and one issue; the advisory ids live in the finding body. (An older
contract keyed each advisory separately; that opened nine tickets for one `urllib3` pin.) For a
finding that names a `bundle`, the key is capability, `bundle`, the bundle id, and `kind` — never
the member ecosystem or package — so a couple that spans manifests opens one issue and stays one
issue when only one member is dirty. For code findings: capability, file path, **`slug`**, and
enclosing symbol — not line numbers, and not the summary. The slug is a stable kebab-case id the
task names explicitly; rephrasing the summary must not change it. When exactly one open agent issue
already covers the same capability + path + symbol, the agent updates that issue (migrating the key)
instead of opening a duplicate. A key that changes on
every run turns a single problem into a stream of duplicate comments.

`location` carries the volatile position that `key` omits, because an inline comment still has to
land on a line. The two answer different questions: `key` asks "is this the same problem as before",
`location` asks "where do I put the comment today".

**Blocking rights.** Whether a finding may block depends on the reliability of the evidence
behind it:

| Evidence reliability | Highest permitted action |
| --- | --- |
| `reproducible` | block the change, when severity and class warrant it |
| `heuristic` | comment with the source link and the obtained value, so a human can confirm in seconds |

This is not a weakened gate: it separates "demonstrated" from "looks like". A skill may lower
the action for a finding, but never raise it above what the evidence permits.

**Confidence and noise.** A finding that the model cannot support with evidence must not be
reported. Silence is preferable to a plausible guess: once a review contains noise, the
substantive comments stop being read.

## 7. Results and idempotency

Each subagent writes its result to a file at a path supplied by the agent, as JSON, and the
agent validates it after the session ends. The final assistant message is not a protocol: it may
be summarised, truncated or chatty, and parsing it is a known source of fragility.

Task outcome, one of:

| Outcome | Meaning |
| --- | --- |
| `findings` | The task completed and produced findings. |
| `clean` | The task completed, all required facts verified, nothing to report. |
| `unverified` | The task could not establish the facts it needed. |
| `exhausted` | The budget or time limit was reached before completion. |

`clean` requires that the required evidence was verified. A task that could not check anything
reports `unverified`, never `clean`.

If the result file is missing or fails validation, the agent retries the task once and then
records `unverified`. A missing result is never treated as success.

### Fix tasks

A `fixer` task answers a different question — "is this change made and proved safe?" — so it has its
own outcomes. One task covers one subject: every finding the agent grouped onto the same package pin
or the same file arrives together, because they share a remediation and splitting them would open
several change requests carrying the same edit.

| Outcome | Meaning |
| --- | --- |
| `fixed` | The worktree carries the change and the verification it needed passed. |
| `refused` | The task decided not to ship: verification failed, or a blocker remains. A reason is required. |
| `unverified` | The task could not establish what it needed to proceed. |
| `exhausted` | The budget or time limit was reached first. |

Refusing is a correct answer, not a failure. A fix that ships on a hope costs more than one that did
not ship, because the next person to see the branch has to establish from scratch whether it is safe.

**A fix task does not always end in a branch.** When somebody replies to one of the agent's remarks
asking how to fix it, the same task runs against the head of the change under review, and what it
leaves behind is offered to that person as a change they may apply — a `suggestion` block when the
edit replaces exactly the lines the remark hangs on, and a diff to read otherwise. Nothing is
committed and nothing is pushed. Two things follow for skill authors. The `notes` of such a task are
published to that person verbatim, so they are a short paragraph addressed to a human about why the
change is what it is, not a list of edits they can already see. And the smallest change wins twice
over: one confined to the lines under discussion can be applied with a click, while one that also
touches other files cannot.

**Verification is checked, not claimed.** Which surfaces to run is judgement and lives in
[`policy/verification.md`](policy/verification.md). Whether they ran is not: the agent matches the
run's own record of executed commands against the verification commands the product's overlay
defines, and an outcome of `fixed` requires **one surface run in full** — every command the overlay
lists for it — with no failing command among any that ran. A partly run surface counts as no
verification, and a task that reports `fixed` without the record is recorded as refused, with the
mismatch as the reason.

A surface is whole because half of one decides nothing: a lock file that installs cleanly and a lock
file whose test suite still passes are different claims, and only the second is a fix. A skill may
tell a task which surfaces a change affects; it may never suggest that a subset of a surface is
enough.

**A failure that predates the change is attributed, not shipped.** When a verification command
fails, the agent re-runs it with the change taken away. If it fails there too, the fix still does
not ship — a red branch is a branch nobody trusts, whoever made it red — but the run reports that
the product's own checks were already failing, and which ones. A skill must not tell a task to work
around such a failure: excluding it, ignoring it or "fixing" it in passing turns one reviewable
change into two unrelated ones.

Two consequences for skill authors. Never describe verification that did not run — the claim is
compared against the record and only makes the result untrustworthy. When a product's overlay
defines no verification commands at all, or names no surface for an enabled ecosystem, no fix can be
proved safe for the findings that surface would have covered, so no fix task is created for them;
the finding is reported for humans instead
([`policy/verification.md`](policy/verification.md)). That is a property of the product's setup, not
something a skill can work around.

### Expected gaps versus failures

Every `unverified` outcome carries a reason, and the reason splits into two kinds with opposite
consequences:

| Kind | Reasons | Meaning |
| --- | --- | --- |
| Expected gap | `no-tooling` | The ecosystem document declares this fact unobtainable. A known, accepted limit. |
| Failure | `unavailable`, `unexpected-shape`, `not-permitted`, `exhausted`, missing or invalid result | Something that was supposed to work did not. |

This distinction is load-bearing. Without it, a broken scanner is indistinguishable from a documented
limit, and infrastructure damage reads as a clean bill of health.

### Run result

The agent derives one run result from the task outcomes, and it is what the surrounding CI acts on:

| Run result | When | Effect on merge |
| --- | --- | --- |
| `pass` | Every required task reached `findings`, `clean`, or an expected gap, and nothing blocking remains. | permitted |
| `blocked` | A blocking finding remains, or a forbidden state was found. | refused |
| `inconclusive` | Any required task ended in a **failure** kind above. | refused |

`inconclusive` is not a finding and makes no claim about the code. It says the check did not happen.
It refuses the merge for the same reason a missing test run does: the absence of a result is not a
result. Reporting `pass` with a note that nothing could be checked would make the gate suppressible
by anyone who can break a scanner or exhaust a budget.

An expected gap never produces `inconclusive`. An ecosystem with no audit tooling would otherwise
block every change forever, which teaches humans to bypass the gate.

Fix tasks do not enter this table. A run result describes what is known about the code, and a fix is
an action taken about something already known: a fix that did not ship leaves the finding exactly as
the analysis reported it. What the fix tasks did is in the run record and in what the agent published,
and a fixer that keeps failing is caught by the escalation rule in
[`playbooks/maintain.md`](playbooks/maintain.md) rather than by a verdict nobody reads.

Neither do the sessions a comment wakes. An `intent` session returns which intent a reply expresses,
and a `writer` session returns either the reply or an honest inability to write one; both are validated
the same way, and neither produces findings, evidence or a verdict. A run that only answered somebody
says exactly that, and makes no claim about the code.

Idempotency guarantees from the agent: comments are reconciled by finding `key`, so a repeated
run updates or leaves existing threads alone instead of duplicating them; a finding that
disappeared is resolved rather than silently forgotten. Skills therefore do not need to check
whether a comment already exists. A reply the agent writes to a person carries the same marker, which
is also what stops a later run from mistaking its own comment for somebody's question.

## 8. Budgets and degradation

Every task has a step limit and a wall-clock limit; the run as a whole has a budget. These are
configuration and are not visible as knowledge, but two consequences are normative for skills:

- procedures must be written so that partial progress is useful — collect evidence first, then
  reason, rather than reasoning towards a single final answer;
- when a task ends as `exhausted` or `unverified`, the run still produces a verdict — but a failure
  kind makes that verdict `inconclusive` rather than `pass`, naming what was not checked. A run
  never fails silently and never converts incompleteness into approval.

## 9. Determinism expectations

The gate is a blocking check, so the same input should give the same answer. Skills support this
by preferring exact sources over reasoning: a scanner over an opinion about vulnerabilities, a
registry API over a recollection of release dates, `compare_versions` over judging version
strings. Where a fact can only be obtained heuristically, the resulting finding is marked
accordingly and cannot block, which bounds the effect of nondeterminism instead of hiding it.

## 10. Compatibility

[`library.yaml`](library.yaml) declares the `contract_version` this prose implements. The agent
declares the set of contract versions it can read. A mismatch is a startup error, not surprising
behaviour in the middle of a review. Product versioning is the agent release alone — knowledge ships
inside that release; there is no separate library pin or `min_agent_version`.

Changes to this document are breaking when they remove a tool, rename a field, change an
outcome, or restrict what was previously permitted; such changes require a breaking bump of the
**agent** version — the middle number while the product is on `0.x`. Adding a tool or an optional
field is compatible.

The normative schemas for evidence records, findings and result files live next to their validators
in the runner package. This document describes them for skill authors; where the two disagree, the
agent's schema wins and this document is a bug.

## 11. What a release carries

An agent release carries the knowledge tree a run consumes: `library.yaml`, `INDEX.md`, and every
document the index lists, bundled with the runner. Templates under `overlay/templates/` stay in the
repository for products to copy by hand; no run reads them from the library path. A run may record a
content digest of identity, index and bodies for audit; it does not compare that digest to a separate
pin — the agent tag *is* the knowledge release.
