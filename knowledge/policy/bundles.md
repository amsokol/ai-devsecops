---
id: policy/bundles
kind: policy
summary: Coupled dependencies that must be scanned, unlocked, moved and verified together.
---

# Coupled bundles

Some pins are not independent. They share a version family, a codegen path, or a release train.
Treat them as a **bundle**: scan, unlock, plan, apply and verify together — never partially. A
half-moved bundle is usually worse than no move at all, because it produces a state nobody
tested.

## When something is a bundle

Declare a bundle when any of these hold:

- Two or more manifests must stay on the same version, such as a library and its plugin, or an
  application and its type definitions.
- A move requires regeneration or a lock refresh across ecosystems.
- Unlocking needs evidence from more than one registry.
- A human comment says *lockstep*, *aligned*, *move together*, or names sibling pins.

If unsure, prefer a bundle over risking a half-applied move.

## Marker convention

Use a shared bundle identifier on every member:

```text
# agent: bundle <id>
# agent: hold =X.Y.Z — bump bundle to A.B.x when ALL unlock:
#   - registry-a: pkg @ A.B.0
#   - registry-b: remote @ vA.B.0
```

| Marker | Meaning |
| --- | --- |
| `agent: bundle <id>` | Pins with this identifier move as one unit |
| `hold` on any member | Blocks the whole bundle until the unlock is satisfied |
| `bump bundle to X when ALL …` | Every listed condition must pass before any member moves |

Prose such as "keep in lockstep with …" implies coupling even without the marker. Infer the
bundle, then name it explicitly in the plan so a human can correct the inference.

## Procedure

1. Discover bundles during the comment pass ([`holds.md`](holds.md)).
2. List the members: ecosystem, file, current pin, and how availability will be checked.
3. Collect evidence for each member using its ecosystem document.
4. Reconcile the unlock for the **bundle**, not per line:
   - any unmet condition blocks the entire bundle;
   - any held member without an override blocks the entire bundle;
   - partial evidence — one registry confirmed, another not — blocks, unless a comment
     explicitly allows the substitute;
   - uncertain evidence counts as unmet. Never guess in favour of moving.
5. Plan one row per bundle: the action is bump, hold or blocked for the whole set.
6. Apply as one change-set: move every member to the agreed version family, run the required
   regeneration, refresh every affected lock, and update or remove stale comments on every
   member.
7. Verify after the full bundle is applied, not after the first file.

## Anti-patterns

- Unlocking because one registry shipped while another is unconfirmed.
- Moving one manifest and leaving a coupled plugin, lock or generated code behind.
- Reporting one member as a candidate and another as held within the same bundle.
- Splitting a bundle across change requests without documenting the risk.
- Shipping a security fix for one member while its siblings stay on the old train.

## Reporting

When any bundle exists, report it — with an explicit empty marker when there are none:

```markdown
## Coupled bundles
- `example` — members: file A, file B; pinned …, target …; unlock: all met | missing …; action: bump | blocked
```

No member of a blocked bundle may move alone.

**Cross-bundle blockers.** Bundles can depend on other bundles (NOTES may say so explicitly — e.g.
a codegen plugin that imports another plugin's types). A dependent package in the same repository
can also constrain a member below the cleared tip. In those cases the **shippable unit** is larger
than one `bundle:` id: do not emit routine `outdated` for a member whose move would break a
dependent that cannot move in the same change. Report the unmet condition; open an outdated (or
major-unlock) issue only when every required piece can ship together, or when human approval is the
sole remaining blocker for a major ([`grouping.md`](grouping.md)).

**Findings and issues.** Every member finding that belongs to a named bundle must carry
`bundle: <id>` in the result JSON. The agent collapses those members into one tracked finding
keyed by the bundle id — one issue, one fix branch — for routine drift and for majors alike. Do
not omit the field on an otherwise independent-looking outdated finding when NOTES or a marker
named the couple; that is how a BSR plugin and a cargo crate become two tickets for one move.
Do not open an outdated issue at all when the couple (or its blockers) cannot move yet — silence
beats a ticket that only documents hope.

## Majors and unlock issues

A routine major move inside a bundle follows the unlock rule in [`grouping.md`](grouping.md),
with one refinement:

1. When the only remaining blocker is human approval — every member has a cleared, available
   target — open **one** issue for the bundle, keyed by the bundle identifier. Never one issue
   per member.
2. While any non-human blocker remains — a sibling in quarantine, no safe version, incomplete
   unlock evidence, an explicit hold, **or a cross-bundle / dependency constraint that prevents
   shipping** — do not open the unlock issue. Keep reporting the bundle as blocked with the unmet
   conditions named. The same rule applies to routine (non-major) outdated: do not open a
   dependency-update issue for a bump that cannot ship.
3. After the unlock, ship the whole bundle in one change request.

## Security

Bundles apply to security remediations exactly as they do to routine moves. Urgency does not
justify a partial move.

- **The vulnerable pin is a bundle member.** The remediation is the whole bundle on one agreed
  version family: move all members, regenerate, refresh all affected locks, verify once. Ship on
  the security track. Sibling moves needed only to keep the train aligned are part of that
  remediation, not routine work.
- **The bundle cannot fully unlock.** Do not ship a partial fix. Keep the issue open and record
  which members and conditions are unmet.
- **A transitive-only remediation** — a lock override or resolution pin that changes no declared
  member — is not a partial bundle move. It is allowed when it fully addresses the advisory and
  passes verification. If the only real fix requires changing a member pin, the whole-bundle rule
  applies again.

An explicit human exception, naming the advisory and allowing the partial move, is required to
deviate. Never invent one.
