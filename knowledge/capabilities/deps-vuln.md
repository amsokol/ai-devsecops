---
id: capabilities/deps-vuln
kind: capability
summary: Known vulnerabilities in dependencies, and how to choose a remediation.
---

# Vulnerable dependencies

Applies to the ecosystems the product overlay enables. The concrete scanner or advisory source
for each is in that ecosystem's document.

## What to look for

- Advisories affecting declared dependencies or anything in the resolved graph.
- Advisories affecting build, development and tool dependencies. They run on developer machines
  and in CI, which is where credentials live.
- Advisories affecting pinned CI actions and container images when that ecosystem is enabled.
- Withdrawn or yanked versions, and packages whose maintainer changed in a way the registry
  flags — supply-chain signals that no CVE describes.

These are `kind: vulnerable` in the result, and the advisory identifier is what tells two of them
about one package apart ([`../CONTRACT.md`](../CONTRACT.md)). A supply-chain signal with no advisory
identifier is still `vulnerable`; there can be one such finding per package, so put everything the
signal amounts to in the one summary rather than splitting it.

When reviewing a change, the scope is advisories **introduced or made worse** by that change. A
pre-existing vulnerability is not the reviewer's business; it belongs to a maintenance run, which
tracks it in an issue. Which pins the change actually moved is a question for `read_change`, not
something to infer from a whole lock file: the lines it added are the ones this change is answerable
for.

## Evidence needed

- Scanner output for each enabled ecosystem, where a scanner exists. This is reproducible
  evidence and may support a blocking finding.
- Where no scanner exists, whatever the ecosystem document prescribes, marked as heuristic. Do not
  invent advisory identifiers, and do not recall vulnerabilities from memory: an unsupported
  advisory identifier is worse than silence, because it looks verifiable.
- For each **candidate fix** of an advisory you already found: publication time, so quarantine can
  be evaluated when choosing the remediation. Publication time is not evidence of a problem on its
  own.
- Whether the vulnerable package is a bundle member.

Where the ecosystem's capability profile marks advisories as unobtainable, record the fact as
unverified and say so in the report. Never present an unscanned ecosystem as clean
([`../policy/unknowns.md`](../policy/unknowns.md)).

A package that is merely young — inside the quarantine window, with no advisory against it — is
**not** a finding of this capability. That concern belongs to
[`deps-outdated`](deps-outdated.md). Reporting it here turns a clean advisory scan into a block for
the wrong reason, and the author cannot tell which check actually failed.

## Judgement criteria

Every finding of this capability names an advisory (or a supply-chain signal the registry flags:
yanked, withdrawn, maintainer takeover). Prefer the fixed version that also satisfies the quarantine
duration. When the only fixed version is inside the window, do not adopt it silently: set
`needs_unlock` and say on the issue that a person **may** unlock because fixing the advisory
outweighs quarantine — that unlock is the security exception
([`../policy/quarantine.md`](../policy/quarantine.md), [`../policy/holds.md`](../policy/holds.md)).
A pin comment naming the advisory remains valid too; never invent an exception without one of those.

## Severity

Severity follows the dependency's role, and only its role. Decide in this order and stop at the
first line that applies:

| The affected package is | Severity |
| --- | --- |
| a runtime dependency, and the advisory is remote code execution, authentication bypass or data loss | `critical` |
| a runtime dependency | `high` |
| a development, build or CI-only dependency | `medium` |
| a version withdrawn or yanked with no known flaw | `low` |

Runtime means the product installs it to run: a declared dependency, or anything the resolved graph
pulls in for one. Development and build dependencies are the ones a user of the product never
installs.

Whether the vulnerable code is reachable does not change the severity, and this is deliberate.
Reachability here can only be argued from reading the source, an argument that comes out differently
on two readings of the same code, and severity decides whether a merge is refused. A gate whose
answer moves while its input does not is worse than a strict one. Absence of an import is not
absence of use either: the change that adds a dependency is usually the change before the one that
calls it.

So say what you found about reachability in the finding's text — it is the first thing a human wants
in order to judge urgency — and leave the severity where the table puts it. A finding a human
decides to accept is accepted explicitly, as a security exception with a stated reason, not by the
run quietly grading it down ([`../policy/holds.md`](../policy/holds.md)).

## Fix policy

Security class only, on its own branch, never batched with routine dependency work — even when
those routine moves also cleared quarantine.

- A major move is allowed as part of a remediation without a routine unlock.
- When the vulnerable pin is a bundle member, the remediation is the whole bundle. If any member
  cannot move, do not ship a partial fix: keep the issue open and record which members and
  conditions are unmet ([`../policy/bundles.md`](../policy/bundles.md)).
- A transitive-only remediation that changes no declared member — a lock override or resolution
  pin — may ship on its own when it fully addresses the advisory and passes verification.
- Verify the surfaces the change touches before shipping.

## False positives

- The advisory applies to a different package with a similar name, or to a different platform.
- The affected version range does not actually include the resolved version.
- The affected component is an optional extra the product does not install.
- The scanner reports a development dependency as if it shipped to production.
- The advisory was withdrawn after publication.
- A pin is inside quarantine but no advisory touches it. That is `deps-outdated`, not this task.

When a scanner result cannot be confirmed, report it as a finding with the scanner named as the
source rather than restating it as established fact.
