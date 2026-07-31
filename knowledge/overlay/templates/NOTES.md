---
id: overlay/NOTES
kind: overlay
summary: Product invariants and cautions the agent must respect. Replace with this product's own.
---

# Product notes — PRODUCT_NAME

Invariants and cautions that are true of **this** product and cannot live in a shared library. Keep
this short: it is loaded on every task of every run.

Write each entry as a consequence for the agent, not as background. "The scheduler assumes tasks are
idempotent, so flag any handler that writes before validating" is useful. "We use a scheduler" is not.

## Invariants

<!--
- Configuration is loaded exactly once at startup; a change that reads configuration at request time
  is a defect even when it works.
- The public API is consumed by external clients; changing a response field is a breaking change even
  if no internal caller uses it.
-->

## Cautions

<!--
- The generated client under `path/` is checked in; changing the schema without regenerating leaves
  the tree inconsistent.
- Two components pin the same tool and must move together.
-->

## Out of scope

<!--
- Vendored third-party sources under `path/` are not reviewed.
- Example projects are not held to the product's severity bar.
-->
