"""Whether a deps-outdated result reported every uncleared current pin it owns.

`cleared_pin_target` records `current-cleared` evidence (boolean or null) in the run-global store.
Facts are shared; obligations are not.

- `current_cleared is false` → the pin is young: finding kind `quarantine` (or floating/vulnerable
  when those win the kind order) with `forbidden_state`.
- `current_cleared is null` → publish time unknown: finding kind `unknown_age` (or floating/
  vulnerable), never `quarantine` — "in quarantine" would claim a date we do not have.

Other tasks — and other ecosystems in the same run — are not charged for that fact.

Only tool-written facts are consulted — a model that re-records the whole tool payload under the
same question must not trip or silence the gate. Sharing facts ≠ sharing obligations: the same
class of ownership as the pin census gate.
"""

from __future__ import annotations

from collections.abc import Iterable

from agent.evidence import Evidence, Question
from agent.findings import Finding, Kind

_YOUNG = frozenset({Kind.QUARANTINE, Kind.FLOATING, Kind.VULNERABLE})
_UNKNOWN = frozenset({Kind.UNKNOWN_AGE, Kind.FLOATING, Kind.VULNERABLE})
_TOOL_RECIPE = "@cleared_pin_target"
CAPABILITY = "capabilities/deps-outdated"
NAMED = 8


def incomplete_current_quarantine(
    records: Iterable[Evidence],
    findings: tuple[Finding, ...] | list[Finding],
    *,
    capability: str,
    ecosystem: str,
) -> str | None:
    """Why this outdated result omitted an uncleared current pin it owns, or `None` when complete.

    Only `capabilities/deps-outdated` with a concrete ecosystem is gated. Uncleared facts whose
    subject belongs to another ecosystem stay in the run store for the task that owns them.
    """
    if capability != CAPABILITY or not ecosystem:
        return None
    young = _pins(records, ecosystem=ecosystem, value=False)
    unknown = _pins(records, ecosystem=ecosystem, value=None)
    if not young and not unknown:
        return None
    covered_young = _covered(findings, allowed=_YOUNG)
    covered_unknown = _covered(findings, allowed=_UNKNOWN)
    missing_young = sorted(young - covered_young)
    missing_unknown = sorted(unknown - covered_unknown)
    if not missing_young and not missing_unknown:
        return None
    parts: list[str] = []
    if missing_young:
        parts.append(
            f"current_cleared is false for {_fmt(missing_young)} — need kind quarantine "
            "(or floating/vulnerable) with forbidden_state"
        )
    if missing_unknown:
        parts.append(
            f"current_cleared is null for {_fmt(missing_unknown)} — need kind unknown_age "
            "(or floating/vulnerable) with forbidden_state; do not call this quarantine"
        )
    return (
        "cleared_pin_target reported an unresolved pin age, but this result has no matching "
        "finding. " + " ".join(parts) + ". Report the pin in use — do not leave it silent, and do "
        "not 'fix' a young pin by adopting a newer tip that is also in the window"
    )


def _pins(
    records: Iterable[Evidence], *, ecosystem: str, value: bool | None
) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for record in records:
        if not record.is_verified:
            continue
        if record.question != Question.CURRENT_CLEARED:
            continue
        if not record.recipe.endswith(_TOOL_RECIPE):
            continue
        if record.value is not value:
            continue
        record_ecosystem = record.subject.ecosystem or ""
        package = record.subject.package or ""
        if not package or record_ecosystem != ecosystem:
            continue
        out.add((record_ecosystem, package))
    return out


def _covered(findings: Iterable[Finding], *, allowed: frozenset[Kind]) -> set[tuple[str, str]]:
    return {
        (finding.subject.ecosystem or "", finding.subject.package or "")
        for finding in findings
        if finding.kind in allowed and finding.forbidden_state and finding.subject.package
    }


def _fmt(items: list[tuple[str, str]]) -> str:
    named = ", ".join(f"`{eco}:{package}`" for eco, package in items[:NAMED])
    more = f" (+{len(items) - NAMED} more)" if len(items) > NAMED else ""
    return f"{named}{more}"
