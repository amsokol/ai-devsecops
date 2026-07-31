---
id: policy/verification
kind: policy
summary: Which verification surfaces to run after a fix, including absences and build-system couplings.
---

# Verification

The product overlay lists **commands**, grouped by surface. This document decides **which surfaces
to run**, and what the absence of a surface means. A fix ships only when the required surfaces pass;
on failure, either fix forward or roll back — never lower a policy or disable a check to make
verification pass.

An overlay should reuse the commands its CI already runs rather than inventing separate ones. A
surface verified one way by the agent and another way by CI will disagree eventually, and the
disagreement will surface as a fix that passed here and failed there.

## Naming surfaces

A surface that belongs to one enabled ecosystem is named after that ecosystem's short id — the part
after `ecosystems/` — so `ecosystems/cargo` pairs with a surface `cargo`, and
`ecosystems/python-pip-compile` with `python-pip-compile`. The agent selects that surface from the
finding's ecosystem and from the paths a change touched. Any other surface name is opt-in: it runs
only when a coupling below, a library rule, or a note in the product's `NOTES.md` requires it.

## When the product cannot prove a fix

Three cases, and they are not the same:

1. **No `verification` section at all.** Nothing can be shown safe. No fix task is created for any
   finding; every finding is reported for a person. That is a property of the product's setup, not
   something a skill works around ([`../CONTRACT.md`](../CONTRACT.md)).
2. **An enabled ecosystem has no surface of its own.** Findings for that ecosystem are **human-only
   from the start**: reported and tracked, never queued for an automated fix, never refused after a
   session that could not have proved anything. Omitting the surface is how a product declares
   "nothing to prove with here, do not fix" — write why in `NOTES.md`, so the next person editing
   the overlay does not treat the gap as an accident.
3. **A surface exists and a fix was attempted.** Then the rules below apply: run the surfaces in
   scope in full, ship only on pass, refuse with a reason on failure.

A light verification recipe in an ecosystem document is a candidate the product may adopt into its
overlay. It is not a default the agent invents when the overlay is silent for that ecosystem.
Silence means human-only.

### Authorized prepare without a surface

A person with write access may still ask, on that finding's issue, for a pull request — the same
unlock path that releases a major hold. The agent then prepares the change **without** claiming
local verification: the pull request body states that CI on the PR is the proof they asked for.
The agent never invents this path on its own; "CI will run later" is not a surface, and it is not
an unlock. Without that comment the finding stays reported and the code stays alone.

This path does **not** apply to a routine quarantine finding. Quarantine is the clock
([`quarantine.md`](quarantine.md)); a comment cannot waive it. The only unlock that may adopt a
version still inside the window is a **security** exception on a vulnerability finding, stated
explicitly on that issue.

### Minimal proof for surfaces that are never "built"

Some ecosystems do not compile in the agent's worktree the way a crate or a Go module does.
Workflows, lock files whose checkers are themselves installed from the pins under change, and meta
builds that fetch the world are the usual examples. Minimal proof is still a **command the overlay
lists**, not a hope that CI will catch it later:

| Kind of change | Examples of minimal proof a product may declare |
| --- | --- |
| Workflow / action YAML | a workflow linter or schema check the product already runs in CI |
| Compiled Python locks | install-and-test only when those tools are not themselves taken from the locks under edit; otherwise omit the surface |
| Meta build / whole-repo fetch | a narrow documented target the product accepts as enough; otherwise omit the surface |

"The product's CI will run on the pull request" is not a verification surface the agent can record.
If that is the only proof that exists, omit the surface and leave the finding for a person — the
same outcome as case 2 above, stated on purpose.

## Change-scoped

Do not run the product's full checklist for every change. Running everything is slow enough that
it discourages small fixes, which is how repositories end up with large risky ones.

1. List the surfaces whose manifests, locks or sources the fix actually changed.
2. For each, run **all** of that surface's commands from the overlay, in the order listed.
3. Skip unrelated surfaces — a Rust-only pin move does not need the Go suite.
4. Always apply the couplings below, which can add surfaces that do not appear in the changed
   paths.

Skipping a surface is a judgement you may make; skipping part of one is not. Selectivity is about
which surfaces the change reaches, and once a surface is in scope its commands are what the product
means by "this works". A surface run partly counts as not run at all.

When a command fails for a reason that has nothing to do with the fix — the check was already
failing on this branch — say so and refuse. Do not silence it, exclude it or fix it in passing: the
agent re-runs the failing command without the change and reports a pre-existing failure as such, so
an honest refusal costs nothing and an unrelated repair costs a reviewer their afternoon.

When the scope is genuinely cross-cutting or unclear, run the union of the involved surfaces, or the
product's documented full suite when the overlay says to.

## Build-system couplings

A meta build system often ingests another ecosystem's resolution: a Cargo lock, a Go module file, a
pip lock. Changing the language side changes what the meta build resolves, even though its own files
were not edited. Treat it as affected.

| Changed | Typical wiring | Also verify |
| --- | --- | --- |
| Cargo manifest or lock | a Cargo-derived crate repository in a Bazel include | the Bazel surface |
| Go module files | a Go dependency include | the Bazel surface |
| A pip lock | a pip parse rule reading that lock | the Bazel surface |
| Schema-registry pins consumed by codegen | generation rules | the Bazel surface, and regeneration when the product requires it |

Rules:

1. When a coupled lock or manifest changes and the meta build system is enabled for the product, run
   its verification commands too.
2. Refresh the meta build system's lock when the product requires it after such a change.
3. Do not run a code-generating target as routine verification when it rewrites checked-in sources.
   Run it only when the change is itself about generated code and the overlay says so.
4. Honour any extra couplings the overlay names, such as a tool pinned in two places.

## Advisory scans

Advisory scans are run when that ecosystem changed, or when the fix is itself a vulnerability
remediation for it. Their output is evidence like any other; never describe a scan that did not run.

## Recording

Record in the change-request body which surfaces ran, which were skipped as out of scope, the
commands used, and their results. This is what lets a reviewer trust a green fix without repeating
the work. A finding deferred because its ecosystem has no surface is recorded as deferred with that
reason — not as a failed fix — so a person reading the run does not look for a branch that was never
meant to exist.
