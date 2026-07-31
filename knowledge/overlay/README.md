---
id: overlay/README
kind: overlay
summary: What a product must define in its own overlay, and what it may not override.
---

# Product overlay

The overlay is the product's half of the configuration. The library says what "good" means in
general; the overlay says what it means here. Nothing in the library is copied into the overlay, and
nothing that belongs in the library is restated there — a duplicated rule is a rule that will drift.

## Files

| File | Contains |
| --- | --- |
| `agent.yaml` | **values**: what a review does and what maintenance does — models, spending, queue limits — plus enabled ecosystems, hotspots, quarantine duration, local exceptions, verification commands (omit a surface to keep that ecosystem's findings human-only) |
| `NOTES.md` | **knowledge**: product invariants and cautions the agent must respect while reviewing |

Templates for both are in [`templates/`](templates/).

The split is by nature, not by topic. Values are executed and computed with, so they are structured
and validated: an unknown key or a malformed entry stops the run at startup with a precise message.
Knowledge is written for a model to read, so it stays prose.

The reason values are not prose: a duration or a command extracted from a sentence disappears the
moment someone rewords the sentence, and nothing fails — the run simply proceeds with a different
quarantine window or an unverified fix. A silent change of meaning is worse than a loud syntax error.

## One block per kind of run

The agent does two things — it reviews a change, and it maintains the default branch — and
`agent.yaml` is organised around exactly that. `review:` and `maintenance:` each state their own
models and their own ceilings, and `maintenance:` also states how much it may leave behind in the
tracker. Nothing about maintenance is configured anywhere else.

Both blocks are written in full and neither inherits from the other. It costs a few repeated lines
and buys the property that matters to whoever edits the file: everything a run does is visible where
that run is named, instead of being assembled from a section about models, a section about spending
and a section about volume — three ways of slicing one file, two of which read as "maintenance".

A maintenance run started by hand is held to the same numbers as one that woke on a schedule. The
work is identical, so a second set of numbers would only be a second thing to keep in step.

## Models and limits are the product's, and required

The agent names no model anywhere — not in code, not in the configuration it ships — and it ships no
ceiling either; an overlay missing them does not start. This is not configuration taste. A product
outlives any one provider: a subscription ends, an adapter appears, a project decides its reviews are
worth a more expensive model. A default inside the agent would make each of those a fork of the
agent, and would let the agent decide how much of somebody else's money a run costs.

Two consequences worth knowing. A model is written as `provider/model`, because the provider decides
which models exist — a model name alone is not an address, and with the provider beside it, moving a
role elsewhere is one word on one line. And provider credentials come from the environment, never
from the overlay: this file is in version control.

A ceiling nobody wants is written as `null` rather than left out. A missing key is a question nobody
answered, and reading it as "no limit" would make the most expensive setting in the file the one
nobody typed.

## Which copy a review reads

On a change request the agent reads `agent.yaml` and `NOTES.md` **from the merge base**, not from the
change. The overlay settles what a finding means here, and the notes enter every task's prompt, so a
change that carried its own overlay could set the quarantine to zero, drop the ecosystem whose
dependency it bumps, or instruct the model in the notes — and the run would obey while reporting a
pass. An edit to the overlay takes effect once it is merged, and a review whose overlay differs from
the change says so in its first line. A maintenance run reads the checkout, because there the checkout
is the default branch.

## Size discipline

`NOTES.md` goes into the model's context on every task of every run, so its size is paid for
continuously — unlike `agent.yaml`, which the agent reads as data. Keep the notes to invariants and
cautions; they are not project documentation. Long notes crowd out the code under review and make
every run slower and more expensive, and the agent will warn when they grow past the limit the run
configures.

If something is worth more than a few lines, it probably belongs in the product's own documentation,
with the overlay naming only the consequence the agent must respect.

## What the overlay may not do

The overlay narrows scope and supplies values. It does not redefine judgement:

- It may not weaken rules of the `security` class, or lower a severity to avoid a block.
- It may not remove the requirement for a human unlock on major moves; it may add stricter holds.
- It may not shorten quarantine for a specific package without a documented exception naming the
  advisory.
- It may not use `maintenance.queue` to silence anything. A limit defers reporting to the
  next scheduled run; it never drops a finding, and it never changes which findings block a change
  request.
- It may not grant the agent tools or hosts. Requirements are declared by ecosystem documents and
  granted by the agent within its own ceiling ([`../CONTRACT.md`](../CONTRACT.md)).

A local exception is acceptable when it is written down with a reason and a subject. An exception
without a reason is indistinguishable from an accident, and the agent treats it as one.
