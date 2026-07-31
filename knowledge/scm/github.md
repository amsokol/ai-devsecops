---
id: scm/github
kind: scm
summary: GitHub specifics — identity, merge authority, tokens and workflow constraints.
---

# GitHub

The change request is a pull request. The command-line client is `gh`, and it is a permitted binary
for both roles.

## Capabilities

| Capability | Available |
| --- | --- |
| Read pull request metadata, files, diff, reviews, threads | yes |
| Post a review body and inline threads | reviewing run, when it may mutate |
| Resolve a review thread | reviewing run, when the platform grants it |
| Open and update issues and issue comments | maintenance run |
| Open and update pull requests | maintenance run |
| Merge | never |

## Procedures

**Reviewing.** Scope is the pull request diff. Post one review body plus inline threads, recheck
previously opened threads against the current head, answer human questions, and resolve threads whose
findings are fixed.

**Maintenance.** Open or update issues, open or update fix pull requests when verification passes,
and reconcile against this checkout only. Never approve a product pull request.

**Merge authority is the status check, not the approval event.** GitHub refuses an approving review
from the same identity that authored the pull request, which is exactly the case for fix branches the
agent itself opened. Therefore the branch protection must not require an approving review; it must
require the review job's status check. The review still states its decision in the body — when an
approving review event is impossible, post the same decision as a plain comment and let the check
carry the authority.

The platform's own approval flow is used for everything it is good at: the review body, the inline
threads, the suggestions, resolving a thread whose finding is gone. It is only the authority to hold
the merge that is a check, and each of the alternatives fails on something specific:

| Instead of a check | What breaks |
| --- | --- |
| `Require approvals: N` | any N accounts with write access satisfy it, so a crashed run plus a colleague's approval merges unreviewed code — and the agent's own approval would substitute for a person's rather than add to it |
| The agent as a code owner | apps cannot be code owners or requested reviewers, so this needs a machine user account: a human-shaped identity in the organisation, whose comments read like a colleague's. Code ownership is also per path, so a finding in a file nobody assigned to the agent would not hold the merge |
| Either, on the agent's own fix pull requests | no account may approve a pull request it opened, so the gate would need a second identity and a second credential |

There is also no state for "could not establish" in an approval. An approval is present or absent, and
absent reads the same whether the run is thinking, refusing or dead; a failed check carries the reason,
the exit code and a link to the run record. This is why an inconclusive run comments rather than
requesting changes, and still fails the check.

A check run attaches to the commit the workflow ran against. The review job must therefore run on the
pull request head, either through the pull-request event or through a dispatch pinned to that branch.
Running the required job name from the default branch produces a green review that never satisfies
the protection rule, and the pull request stays blocked for reasons nobody can see.

On a blocking verdict, request changes where the platform allows it, and fail the check.

## Permissions

Least privilege, and two specific traps.

The default job token cannot push changes under the workflows directory: the app token lacks that
scope. Note that `workflows: write` is **not** a valid permission key — adding it makes GitHub reject
the workflow file at parse time, which looks like an unrelated syntax error. When maintenance must
change workflow files, check out with a separate credential that carries both repository and workflow
scope, and keep using the default token for the issue and pull-request API so that comments still come
from the bot identity.

## Changes from a fork

A head that lives in another repository is untrusted code, and **nothing from it is executed in the
review job**. Not a scanner, not an install, not the product's verification.

The reason is what the job contains rather than what the code might do. It holds an installation token
and a model provider's key, and a command over somebody else's manifest runs their build script under
the same user as the process holding both. Handing that command a scrubbed environment does not help:
a child process can read the parent's original environment out of `/proc`, along with the checkout and
anything else that user can read. The only real containments are a different security context — a
container with no network, a separate user — or not executing at all, which is free.

The review itself continues: reading the diff, reading files and querying registries need no
execution. What stops is commands, verification, and any prepared change. The consequences belong in
the review body rather than in a footnote — see
[`../playbooks/pr-review.md`](../playbooks/pr-review.md).

The product's own linters and tests may still run on a fork change, and normally should. They differ
from the agent in one way that decides everything: on the `pull_request` event a fork's job gets a
read-only token and no secrets, so there is nothing in it to steal. The agent cannot be in such a job,
because analysing anything requires a model credential.

These shapes are what turn that safe default back into a compromise, and each has produced real ones:

| Shape | What it gives away |
| --- | --- |
| `pull_request_target` with a checkout of the head | the fork's code runs in a job that has secrets and a writable token |
| `workflow_run` that checks out the head, or trusts an artefact from the fork's job | the same, one hop removed and harder to notice |
| `actions/checkout` with `persist-credentials: true` | the token is left in `.git/config`, where any install script finds it |
| `${{ github.event.pull_request.title }}` — or branch name, or body — inside `run:` | the value is pasted into the shell before it executes |
| Actions referenced by tag instead of commit SHA | whoever can move the tag runs code in the job |
| Self-hosted runners on a public repository | a stranger's job gets a machine with state and a network position |

The gate on execution is the repository setting that requires approval for outside contributors before
their workflows run at all. The agent's review is the check that can safely run *before* that
approval, and it exists partly to inform it: a maintainer who is told what a change touches —
workflows, build scripts, dependency sources, binary files — decides that question with something in
front of them.

Only human comments trigger runs. Bot comments — including the agent's own — must be filtered at the
workflow level, and every wake additionally requires that the commenter has write access to the
repository. Without that check, anyone who can comment can make the agent act. Write access is asked of
the platform's permission endpoint, not inferred from the association attached to a comment: an
organisation member is not necessarily allowed to write to this repository, and treating the two as the
same means taking orders from the wrong people. Asking it needs push access itself, so a credential
that cannot ask is a refusal to act rather than a permission granted by default.
