# Knowledge library

Part of the [`ai-devsecops`](../) monorepo. This directory is the agent's only source of
**judgement**: what counts as a problem, what to look at, in what order to act, what to be careful
about, and when to block rather than warn.

Everything here is prose, written for humans and models at the same time. There is no runner code, no
schema, no run configuration and no product-specific value in this tree — those live in `agent/` and
in each product's overlay. The shared design (knowledge + runner) is in [`../DESIGN.md`](../DESIGN.md).

## Layout

| Path | Contents |
| --- | --- |
| [`INDEX.md`](INDEX.md) | generated table of contents; the entry point for an agent |
| [`CONTRACT.md`](CONTRACT.md) | what a knowledge author may rely on, and what the agent guarantees |
| [`CHANGELOG.md`](CHANGELOG.md) | judgement changes for each product version |
| [`playbooks/`](playbooks/) | what to do for a given trigger |
| [`capabilities/`](capabilities/) | what to look for, and how to judge it |
| [`policy/`](policy/) | verdicts, quarantine, holds, grouping, bundles, verification, unknown facts |
| [`evidence/`](evidence/) | how facts are obtained and recorded |
| [`ecosystems/`](ecosystems/) | per-ecosystem sources, procedures and cautions |
| [`scm/`](scm/) | hosting-platform specifics |
| [`overlay/`](overlay/) | what a product defines for itself, with templates |

## How an agent uses it

1. Read [`INDEX.md`](INDEX.md) and the product overlay.
2. Select the playbook for the trigger.
3. Load only the capability, ecosystem and policy documents that playbook needs, filtered by the
   ecosystems the overlay enables and the files a change touches.
4. Acquire evidence, then decide over the evidence — never the other way round.

## Reading order for a human

Start with [`DESIGN.md`](../DESIGN.md) for the model, then [`CONTRACT.md`](CONTRACT.md) for the
boundaries, then one playbook end to end. The capability and ecosystem documents make more sense once
the two-phase structure is clear.

## Writing rules

- Address the agent in the imperative. Say what to do, not what the system does.
- Keep every claim actionable: if a paragraph cannot change a decision, delete it.
- Never invent a tool, a command flag, a host or an advisory. Requirements are declared in the
  ecosystem document and granted by the agent.
- Describe what to do when a fact cannot be established, not only the happy path.
- One statement lives in one place. Link instead of restating.
- Keep the header to the four fields the format defines; anything more is configuration and belongs
  in the agent.

## Versioning

The product version is the agent release (`pyproject.toml`). Knowledge and runner ship together;
there is no separate library pin or digest check. `library.yaml` carries only `contract_version`.
Breaking changes to the contract or to required document shape bump the middle number of the agent
version while on `0.x`.

## Status

The catalogue was migrated from `amsokol/ai-devsecops-skills`, which is frozen at its final tag for
products that have not moved yet. The mapping between old and new paths is in
[`DESIGN.md`](../DESIGN.md).
