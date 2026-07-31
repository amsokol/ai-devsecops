---
id: policy/holds
kind: policy
summary: Human holds and unlocks expressed as comments next to dependency pins.
---

# Holds and unlocks

Before proposing or applying any dependency change, run a **comment pass** over the manifests
and the notes near them. Human comments are first-class policy: they express holds, unlock
conditions, coupled bundles, and intended targets. This pass is never skipped, and its result is
evidence like any other.

## Where to look

- Manifest lines and a few lines above and below each dependency.
- Nearby `#`, `//` and `/* */` comments.
- For formats without comments, such as `package.json`: sibling documents,
  `DEPENDENCIES.md`, `docs/deps*`.
- Search terms: `agent:`, `bundle`, `pin`, `hold`, `do not bump`, `until`, `when`, `blocked`,
  `lockstep`, `aligned`, `move together`.

## Markers

The preferred form is an `agent:` prefix:

```text
# agent: hold — <reason>
# agent: unlock when ALL: <conditions>
# agent: security ok — <advisory> (exception to quarantine)
# agent: bundle <id>
# agent: ok to patch/minor; majors need human approval
```

Plain prose without a prefix still counts when it clearly refers to that pin. Humans should not
have to learn a syntax to be obeyed.

## Grammar

| Phrase | Meaning |
| --- | --- |
| `hold`, `pin`, `do not bump` | Block automatic bumps unless the stated condition is met |
| `bundle <id>` | Coupled set — see [`bundles.md`](bundles.md); a hold applies to the whole bundle |
| `bump to X when …`, `until …` | Allowed target plus unlock condition |
| `bump bundle to X when ALL …` | Every listed condition must pass before any member moves |
| `ok to patch`, `patch only` | Cap the change at patch, or at patch and minor if stated |
| `security ok`, named advisory | That advisory may bypass quarantine; still report it |

## Implicit hold on majors

Any **major** version move is an implicit hold until a human unlocks it, even when no comment
exists next to the pin. What counts as major is defined in [`grouping.md`](grouping.md).

Patch and minor candidates are not implicit holds, though they remain subject to quarantine,
explicit holds and bundle rules.

Security remediations are not routine majors: when a vulnerability requires a major move, it
ships on the security track under the rules in
[`../capabilities/deps-vuln.md`](../capabilities/deps-vuln.md).

The product overlay may add stricter holds. It may not remove this default.

## Unlocks from humans

An unlock may also arrive as a comment from a human on the issue that tracks the finding. Any
clear authorisation counts — there is no magic phrase to match. Details of that flow are in
[`../playbooks/maintain.md`](../playbooks/maintain.md).

## Rules

- An unmet hold, explicit or implicit, blocks the routine change for that pin. For a bundle it
  blocks every member.
- A satisfied unlock permits the change, still subject to quarantine, grouping and bundles.
- A quarantine exception must be explicit and must name the advisory. Never invent one. On a
  vulnerability issue whose only fixed version is still inside the window, a write-access unlock
  comment is that exception ([`quarantine.md`](quarantine.md)); a routine quarantine issue has no
  such path.
- After a successful unlock and bump, refresh or remove the now-stale hold comments on every
  pin that was touched. A stale hold is worse than no hold: the next run will believe it.

## Order of work

1. Discover manifests from the enabled ecosystems in the overlay.
2. Run the comment pass — holds, unlocks, bundles.
3. Collect version and advisory evidence per ecosystem.
4. Reconcile with [`quarantine.md`](quarantine.md), [`grouping.md`](grouping.md) and
   [`bundles.md`](bundles.md).
5. Apply only candidates that are both unlocked and cleared, then verify.
