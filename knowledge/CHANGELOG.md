# Changelog

What changed in the knowledge prose shipped with the agent. The **product version** is the agent
release in [`../pyproject.toml`](../pyproject.toml) — runner and knowledge move together. This file
records judgement and contract changes so a product bumping `@vX.Y.Z` knows what the gate will do
differently.

`contract_version` in [`library.yaml`](library.yaml) changes only when [`CONTRACT.md`](CONTRACT.md)
changes what an agent must implement.

There is deliberately no "unreleased" section. A knowledge change bumps the product version in
`pyproject.toml` in the same pull request, and `scripts/library.py check` fails when the newest
section below disagrees with that number.

## 0.3.0 — 2026-07-31

Ships inside agent `0.3.0`. No separate library pin, digest artefact, or `min_agent_version`.

### Changed

- Monorepo delivery: knowledge is bundled with the agent wheel; products pin one agent tag.
- [`library.yaml`](library.yaml) keeps only `contract_version` (still 2).

## 0.5.7 — 2026-07-28

Needs agent `>= 0.2.5`. Contract stays at `2`: result shapes unchanged; after `cleared_pin_target`
answers, registry second-guessing is forbidden; BSR covers plugins as well as modules.

### Changed

- [`CONTRACT.md`](CONTRACT.md): trust `cleared_pin_target` — do not re-crawl the registry after it
  answers (`target` / `pending` / null). BSR tool path covers modules **and** remote plugins.
- [`capabilities/deps-outdated.md`](capabilities/deps-outdated.md) and every
  [`ecosystems/*.md`](ecosystems/): same no-second-guess rule; BSR Candidates applies to plugins,
  resolve probe only to confirm a named tag.
- [`ecosystems/bsr.md`](ecosystems/bsr.md): when buf label lists are empty, `cleared_pin_target`
  uses GitHub Releases for `owner/name`; host `api.github.com` required.
- [`DESIGN.md`](../DESIGN.md) Found in operation: token-waste / false-null BSR plugin path marked Done
  in 0.5.7 / agent 0.2.5.

## 0.5.6 — 2026-07-28

Needs agent `>= 0.2.4`. Contract stays at `2`: result shapes unchanged; `cleared_pin_target` required
for routine `Moves to` on every listed ecosystem.

### Changed

- [`CONTRACT.md`](CONTRACT.md) tool `cleared_pin_target`: all ecosystems (cargo, npm, python-uv,
  python-pip-compile, go-modules, bazel, bsr, github-actions). `ecosystem` required; `kind` only for
  github-actions. BSR best-effort when `buf` is missing.
- Every [`ecosystems/*.md`](ecosystems/) Candidates / Moves to section requires the tool; do not
  invent newest via a narrow registry fetch.
- [`ecosystems/github-actions.md`](ecosystems/github-actions.md): image `Moves to` described as
  universal channel→concrete (any Hub image family), not JDK-only examples.
- [`playbooks/maintain.md`](playbooks/maintain.md): when a fix is refused or cannot be proposed,
  report that failure on the issue (scheduled/manual as well as wake).
- [`DESIGN.md`](../DESIGN.md) Found in operation item 6 marked Done for all listed ecosystems.

## 0.5.5 — 2026-07-28

Needs agent `>= 0.2.3`. Contract stays at `2`: result shapes unchanged; `cleared_pin_target` added
for github-actions routine `Moves to`.

### Added

- [`CONTRACT.md`](CONTRACT.md) tool `cleared_pin_target`: newest quarantine-cleared concrete target
  (and pending young tips) for action and image pins. Required for routine `Moves to` on
  [`ecosystems/github-actions.md`](ecosystems/github-actions.md). Security `needs_unlock` unchanged.

### Changed

- [`DESIGN.md`](../DESIGN.md) Found in operation item 6 marked Done for github-actions (deterministic
  target choice).

## 0.5.4 — 2026-07-27

Needs agent `>= 0.2.2`. Contract stays at `2`: result shapes are unchanged; derived-fact tools are
added for github-actions outdated sweeps and action quarantine clocks.

### Added

- [`CONTRACT.md`](CONTRACT.md) tool `list_action_pins`: deterministic census of third-party `uses:`
  and container `image:` pins under `.github/`. Required at the start of a repository-wide
  `deps-outdated` sweep for [`ecosystems/github-actions.md`](ecosystems/github-actions.md); the agent
  fails the task when recorded subjects do not cover that census.
- [`CONTRACT.md`](CONTRACT.md) tool `action_publish_time`: GitHub Release `published_at` for an
  action tag. Required for quarantine on this ecosystem; committer dates are forbidden (they predate
  the Release and falsely clear the window).

### Changed

- [`capabilities/deps-outdated.md`](capabilities/deps-outdated.md) and
  [`policy/quarantine.md`](policy/quarantine.md): clock-only footer and refuse-unlock apply only when
  there is no cleared `target`. A quarantine tip still in window with a named cleared move is
  remediable (human-only / major rules as usual), not "wait for the clock".
- [`ecosystems/github-actions.md`](ecosystems/github-actions.md): publish time must come from
  `action_publish_time` on the **concrete** tip (e.g. `@v7` → `v7.0.1`); no committer-date fallback.
- [`DESIGN.md`](../DESIGN.md) Found in operation items 1 (github-actions census), 7 (cleared target),
  and the committer-vs-release clock miss marked Done / recorded in 0.5.4.

## 0.5.3 — 2026-07-27

Needs agent `>= 0.2.1`. Contract stays at `2`: result and tool shapes are unchanged; what changes is
how quarantine findings talk to a person, what an unlock comment may cause, and how fix branches
behave when a change request is already open or was closed.

### Changed

- [`policy/quarantine.md`](policy/quarantine.md) separates three unlock cases: routine
  `kind: quarantine` waits on the clock and **refuses** an unlock comment; a vulnerability whose only
  fixed version is still inside the window **offers** unlock as a security exception; human-only for
  lack of a verification surface stays as in 0.5.2. [`policy/verification.md`](policy/verification.md),
  [`policy/holds.md`](policy/holds.md), [`capabilities/deps-outdated.md`](capabilities/deps-outdated.md),
  [`capabilities/deps-vuln.md`](capabilities/deps-vuln.md) and [`playbooks/maintain.md`](playbooks/maintain.md)
  follow that table so issue copy and wake behaviour cannot mix "waiting for a person" onto a
  quarantine-only finding.
- [`playbooks/maintain.md`](playbooks/maintain.md) Fix branches: an **open** change request stays
  untouched (comment on the issue with the PR link; no silent retarget); a **closed** one is
  announced, abandoned `agent/…` refs are deleted, and a new PR is opened from the default branch.
- [`DESIGN.md`](../DESIGN.md) Found in operation records incomplete pin enumeration, drifting
  concrete `target` choice, and "cleared candidate exists but footer still waits on the clock"
  (items 1, 6, 7) for later deterministic tools.

## 0.5.2 — 2026-07-27

Needs agent `>= 0.2.0`. Contract stays at `2`: result and tool shapes are unchanged; what changes is
when a fix may be prepared and how a person authorises one without a local surface.

### Changed

- [`policy/verification.md`](policy/verification.md) names three cases: no `verification` section at
  all, an enabled ecosystem with no surface of its own (human-only from the start), and a surface that
  exists. Omitting a surface is how a product declares "do not fix here"; light recipes in ecosystem
  documents are candidates for the overlay, not defaults the agent invents. Minimal proof for
  workflows, compiled locks and meta builds is still a command the overlay lists — "CI will run on
  the PR" is not a surface.
- A person with write access may unlock a pull request on a human-only finding so CI on that PR is
  the proof. Stated in verification policy and [`playbooks/maintain.md`](playbooks/maintain.md);
  without that comment the finding stays reported and the code stays alone.
- [`CONTRACT.md`](CONTRACT.md), ecosystem docs for `github-actions`, `python-pip-compile` and
  `bazel`, and the overlay template spell the same rule so a product and a skill author see one
  story.

## 0.5.1 — 2026-07-26

Two live maintenance runs over the same unchanged repository disagreed with each other, and both
disagreements trace to this library rather than to the agent. One image tag was `floating` in the
first run and `outdated` in the second, which filed the same line of YAML as two issues. And the
first run examined four of the six actions in that repository, said nothing about the other two, and
was indistinguishable from the run that checked them all.

A run's judgement is allowed to improve. Which of two true words it uses for the identity of a
finding, and which pins it bothers to look at, are not judgement.

### Changed

- `kind` is decided by an ordered test on the reference, first match wins, instead of by choosing
  between words that all fit: `vulnerable`, then `floating`, then `bundle`, then `quarantine`, then
  `outdated`. A reference with no version to be behind is `floating` and nothing further is asked of
  it. One reference now yields one finding — `capabilities/deps-outdated.md` previously invited two
  for a pin that both floats and sits in the window, which asks a person to fix one line twice.
- `ecosystems/github-actions.md` says which references in it name a version, because the test above
  turns on that and the answer is not the same for both forms it carries. A major action tag (`@v5`)
  is an ordinary pin; a container line tag (`:25-jdk`) is a float wherever the registry publishes
  exact tags. Calling `@v5` a float would put a standing finding on nearly every workflow for
  following its own ecosystem's convention.

### Added

- A repository-wide sweep must enumerate every pin before querying anything, and record a fact for
  each one it examined, including the ones that are fine. This is measured rather than asked for: an
  agent reads the examined set out of the evidence, treats a pin with no fact behind it as unchecked,
  and neither closes its issue nor counts its absence. Stated in `capabilities/deps-outdated.md` and
  in `ecosystems/github-actions.md`.

## 0.5.0 — 2026-07-25

Breaking: a finding about a package must name its `kind`, and an agent must validate it. Products move
by pinning an agent that implements `contract_version: 2`; nothing in an overlay changes.

### Added

- `kind` in the result contract, from a closed vocabulary: `quarantine`, `floating`, `outdated`,
  `bundle`, `vulnerable`. It is what a problem is *called*, and a finding's identity is built from it.
  Until now that identity fell back to a slug of the summary — prose a model writes afresh every run.
  The second live maintenance run rephrased all four of its findings, every key moved, and four issues
  were raised beside the four already describing the same problems. One of those carried an approval a
  person had given; it then matched nothing, and the agent asked them for it again. A key that moves
  does not merely duplicate, it forgets.
  [`CONTRACT.md`](CONTRACT.md), [`capabilities/deps-outdated.md`](capabilities/deps-outdated.md) and
  [`capabilities/deps-vuln.md`](capabilities/deps-vuln.md) say which kinds each capability produces and
  that one pin may be two findings under two kinds.

## 0.4.5 — 2026-07-25

### Changed

- [`CONTRACT.md`](CONTRACT.md) says what an absent `target` means for a finding about a package: there
  is nowhere to move, so the finding is reported and never queued for a fix. Quarantine produces one
  of these every week — the newest release is real and worth reporting, and no cleared version exists
  until the clock runs out. The first live maintenance run queued one, and the session did what a
  session asked to fix an unfixable pin does: it invented a move and downgraded an action by a major
  version. Naming the current version, or a lower one, to have something in the field is now named as
  the mistake it is.

## 0.4.4 — 2026-07-25

### Changed

- Evidence recipes no longer send a session to a command that has to log in first.
  [`evidence/acquisition.md`](evidence/acquisition.md) states the reason once, where the order of
  preference is: a task's commands are given an environment with no token, no registry login and no
  key, because a command may be running code that arrived in the change under review. A tool that
  authenticates before it answers is therefore not a tool for acquisition, however capable it is.
- [`ecosystems/github-actions.md`](ecosystems/github-actions.md) asks the platform API directly for an
  action's publish date instead of going through `gh`, which cannot authenticate inside a run, and says
  what to do when a tag has no release of its own. It also warns off the releases index: its bodies are
  release notes measured in tens of kilobytes, and a version question is answered by names alone. The
  first live run of a six-ecosystem repository spent ten refused calls on `gh` and four more on an index
  too large to hand over.
- The same document names the image registry hosts — `hub.docker.com`, `registry-1.docker.io`,
  `auth.docker.io`, `ghcr.io` — instead of saying "the registries the product's images come from". A
  host that is not named is a host that is not granted, so container image facts were unobtainable in
  practice while the profile claimed they were reproducible.
- [`ecosystems/bazel.md`](ecosystems/bazel.md) drops `gh` for the same reason, and keeps
  `api.github.com`.

## 0.4.3 — 2026-07-25

### Changed

- A major move that needs a person's approval is now a field on the finding rather than a rule a
  session is asked to remember. [`CONTRACT.md`](CONTRACT.md) adds `target` and `needs_unlock` to the
  finding shape: the agent measures the move itself and holds a semantic-version major whether or not
  anything declared one, and `needs_unlock` is for the majors no comparison can see — a `@v5` to `@v7`
  action pin, an image tag, a raised toolchain floor. A held finding is reported and never changed
  until an approval is recorded on its issue. Setting the field can only add a hold, never remove one.
  Nothing a skill must do differently, beyond stating the version a remediation moves to; what changes
  is that forgetting to say "this needs approval" no longer ships the move.
- [`policy/grouping.md`](policy/grouping.md) states that the unlock, once granted, stays granted: a
  fix that fails to verify is retried under the same approval rather than by asking again. Approval is
  for the move, not for one attempt at it, and re-asking is how people learn to approve without
  reading. It also says plainly that a security remediation carrying a major move must not be held —
  waiting is the greater risk there, and the agent will not invent a hold for one.
- [`playbooks/maintain.md`](playbooks/maintain.md) narrows what a session writes into an unlock issue.
  The agent now writes why the issue is waiting, what a comment on it will cause, and the record of
  the approval afterwards; the session supplies the finding and the target version.

## 0.4.2 — 2026-07-25

### Changed

- A change from outside the repository is read and never executed, and the knowledge now says what
  that means for a run. [`playbooks/pr-review.md`](playbooks/pr-review.md) gains a section on it: a
  capability that needs a command records `not-permitted` and reports what reading and the registries
  established, no change is prepared, and a change touching dependency manifests will usually be
  inconclusive rather than approved — because nothing verified those pins. Approximating a scanner's
  answer from reading is now explicitly worse than the gap.
- [`scm/github.md`](scm/github.md) says why, in terms of what a review job contains rather than of
  the code's quality: it holds an installation token and a model key, and a build script from a fork
  runs under the same user as the process holding both, where a scrubbed environment does not help
  because `/proc` still has the original. It also names the workflow shapes that turn the safe
  default back into a compromise — `pull_request_target` with a checkout of the head,
  `persist-credentials`, event context pasted into `run:`, actions pinned by tag, self-hosted runners
  on public repositories — and where the real gate on execution is.

### Fixed

- The tool names in [`CONTRACT.md`](CONTRACT.md) and [`policy/quarantine.md`](policy/quarantine.md)
  are the ones the agent actually offers. `date_math` is `check_quarantine`, `read_diff` is
  `read_change`, `http_get` is `fetch`, and `evidence_cache` was never one tool: it is `known_fact`,
  `record_fact` and `record_gap`, whose guarantees are now stated. Skills that told a session to call
  a name that does not exist were spending a step to find that out, and the quarantine document did
  it for the one piece of arithmetic it forbids doing by hand.
- `scm_read` is gone from the contract, because no such tool exists and none should: the platform is
  read by the agent's own code, and what a task needs from it is in its prompt. The contract promising
  it invited skills to instruct a session to go and look something up on the pull request.
- `contract_version` stays at `1`. No agent ever implemented the names above, so this is a correction
  of the description rather than a change of what an agent must implement; moving the number would
  announce an incompatibility that does not exist.

## 0.4.1 — 2026-07-25

### Changed

- "How do I fix this?" is answered with the change rather than with a description of it. A reply asking
  that in one of the agent's review threads now runs a `fixer` against the head of the change under
  review, in an isolated copy where the product's verification can be run over the edit, and offers the
  result in the thread — a `suggestion` block when it replaces exactly the lines the remark hangs on, a
  diff to read otherwise. The review still commits nothing and pushes nothing.
- The line between `fixer` and `writer` is stated in [`CONTRACT.md`](CONTRACT.md): what a session leaves
  behind, not what it writes. A `fixer` leaves a tree that can be verified and therefore labelled; a
  `writer` leaves text. This is why a question about how to fix something goes to the fixer even though
  the answer is published as a comment — a patch quoted from prose is one nobody checked, and it is the
  one a person would apply.
- Skill authors get two consequences of that. The `notes` of such a task are published verbatim to the
  person who asked, so they are one paragraph addressed to a human about why the change looks like this;
  and the smallest change wins twice, because one confined to the lines under discussion can be applied
  with a click while a wider one cannot.
- [`scm/github.md`](scm/github.md) says why merge authority is the status check and not the platform's
  approval flow, instead of only saying that it is. The platform's review mechanism is used for
  everything it is good at — the body, the threads, the suggestions — and each alternative gate fails on
  something specific: a required approval count is satisfied by anybody, an app cannot be a code owner
  without introducing a machine user account, no account may approve a pull request it opened, and an
  approval has no state for "could not establish".

## 0.4.0 — 2026-07-25

### Added

- Two roles for the case where a person writes a comment: `intent`, which reads what the comment asks
  for and gets no tools and no documents at all, and `writer`, which answers in prose. Neither produces
  findings, evidence or a verdict, and what an intent causes is a table in the agent — so a misread
  comment costs a session and can never grant a permission nobody gave. Products must bind both in
  `review.models` and `maintenance.models`; the overlay template shows where.

### Changed

- A maintenance run woken by an issue comment is narrowed to the check that owns that issue's finding,
  instead of sweeping the repository as well. Somebody who writes on one issue is asking about one
  thing, and answering with a week of unrelated findings buries the answer.
- The division of labour on a wake is stated where it belongs. Whether a comment may start a run, and
  what it asks for, are settled before any task exists; the status a person then reads on their issue is
  written by the agent from recorded facts, so a task must not write a second one. A question about a
  review remark is answered in that thread by the run the reply wakes, and that run publishes no
  verdict.
- Write access of whoever commented is asked of the platform's permission endpoint rather than inferred
  from the association attached to a comment — an organisation member is not necessarily allowed to
  write here — and a credential that cannot ask is a refusal to act rather than a default yes.

## 0.3.0 — 2026-07-25

### Changed

- The product overlay is organised by kind of run. `review:` and `maintenance:` each state their own
  models and their own ceilings, and `maintenance:` also carries `queue:` — how many issues a run may
  open and how many fix branches may await review. This replaces the earlier split by kind of
  setting, where models were grouped by role, spending by whether anybody was waiting, and volume by
  neither: three ways of slicing one file, two of which read as "maintenance".
- Models and spending ceilings are required of the overlay, and a model is written as
  `provider/model`. The agent names no model and no ceiling anywhere, so an overlay that names none
  does not start — a run on a model nobody chose is worse than a refusal to start. A ceiling nobody
  wants is written as `null`, because a missing key is a question nobody answered.
- A review reads the overlay from the merge base rather than from the change under review. The
  overlay settles what a finding means here and its notes enter every prompt, so a change carrying
  its own overlay could otherwise set the quarantine to zero, drop the ecosystem whose dependency it
  bumps, or instruct the model — and the run would obey while reporting a pass.

## 0.2.0 — 2026-07-25

### Changed

- A fix counts as verified only when every command of an affected surface ran and passed, and
  failures that were already failing on the unchanged head are reported as pre-existing rather than
  blamed on the fix. A run that stopped at the first green command was calling a fix proven when it
  had proven one command.
- Findings about one subject become one fix task and one branch. Three advisories against one pin are
  one bump, and three branches carrying the same edit is how a weekly run teaches a team to stop
  reading it.

## 0.1.5 — 2026-07-25

### Changed

- Version discovery asks a registry for version names instead of for every file of every release.
  The full document was large enough to be truncated before the model saw the versions it needed, so
  the answer degraded to a guess with no sign that it had.

## 0.1.4 — 2026-07-25

### Changed

- A review's scope is the change itself: the lines the diff touched, established by a tool rather
  than inferred by the model, and a task that cannot cover its scope refuses instead of answering
  about part of it.

## 0.1.3 — 2026-07-25

### Fixed

- A pin held back only by quarantine is no longer reported as a dependency vulnerability. The two are
  different states: one is waiting, the other is exposed.

## 0.1.2 — 2026-07-25

### Changed

- Dependency advisories are graded by the role of the dependency rather than by an attempt to
  establish reachability, which no scanner here can prove and no model should be asked to guess.

## 0.1.1 — 2026-07-25

### Fixed

- The release artefact packs without a packing timestamp, so the same content produces the same
  digest. A digest that changed with the clock made pinning meaningless.

## 0.1.0 — 2026-07-25

### Added

- First release: playbooks, capabilities, policies, ecosystem procedures and the overlay contract,
  at contract version 1.
