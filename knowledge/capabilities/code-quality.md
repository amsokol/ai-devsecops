---
id: capabilities/code-quality
kind: capability
summary: Correctness and maintainability risks in code; style is out of scope.
---

# Code quality

## What to look for

Defects that change what the code does or make it fail under conditions a user will meet:

- Unhandled errors and swallowed exceptions on paths that can fail.
- Lost execution branches: early returns that skip required work, conditions that can never be
  true, fall-through that was not intended.
- Resource leaks — files, sockets, locks, subprocesses, transactions not released on the error
  path.
- Incorrect use of an API: ignored return values, wrong argument order, misuse of a library
  contract that the type system does not catch.
- Concurrency problems: shared mutable state without synchronisation, races between check and
  use, blocking calls on an event loop.
- Behaviour at boundaries: empty input, absent optional values, very large input, integer and
  timezone edges.
- Broken contracts: changed public API, exit codes, configuration loading, or CLI entry points,
  where callers were not updated.

**Style is out of scope.** Line length, import order, naming conventions, and preferences between
equivalent idioms belong to linters and formatters, which answer the same question identically on
every run. A model's opinion on style is not reproducible, and in a blocking check it produces
noise that costs the substantive findings their audience. Report a formatting matter only when it
hides a real defect.

## Evidence needed

- The change under review, or the source surfaces named in the overlay for a repository-wide run.
- The surrounding code needed to establish that the defect is real: the caller, the error path,
  the type or contract being misused.
- The output of the project's own checks when they are available, so that findings already caught
  by tooling are not duplicated.

## Judgement criteria

A finding requires a concrete path to wrong behaviour, described in one sentence. "This could be
cleaner" is not a finding; "when `parse` returns `None` this dereferences it and raises" is.

Prefer defects in code that runs. A flaw in an unreachable branch, a test fixture, or an example
is at most low severity, and often not worth reporting at all.

Respect the hotspots and severity expectations named in the product overlay: the same defect can
matter differently in a payment path and in a debug script.

## Severity

| Severity | Typical case |
| --- | --- |
| `critical` | Data loss, or failure on the main path for every user |
| `high` | Wrong result, unhandled failure on a common path, broken public contract |
| `medium` | Failure under a specific but realistic condition; leak under load |
| `low` | Defensive improvement; defect in rarely reached code |

## Fix policy

Routine class only. Remediation is the smallest change that fixes the defect, on the routine
track, never mixed with security work ([`../policy/grouping.md`](../policy/grouping.md)). Do not
refactor surrounding code while fixing.

A fix ships only after the verification surfaces for the touched code pass.

## False positives

The most common sources of noise in this capability, all of which must be checked before
reporting:

- The condition is impossible because of a guarantee established earlier in the function.
- The error is handled by a decorator, middleware, or context manager rather than locally.
- The apparent leak is managed by the framework's lifecycle.
- The pattern is deliberate and documented nearby.
- The project's linters already report it, in which case the finding adds nothing.
