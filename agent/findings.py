"""Findings: the vocabulary, the stable key, and what a finding is allowed to do.

The criteria for calling something critical are knowledge and live in the library. The vocabulary
and the arithmetic are here, because two runs on one input must produce the same key, the same
deduplication and the same ceiling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import StrEnum

from agent.evidence import Reliability, Subject


class Klass(StrEnum):
    SECURITY = "security"
    ROUTINE = "routine"

    @property
    def rank(self) -> int:
        return 1 if self is Klass.SECURITY else 0


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {
            Severity.LOW: 0,
            Severity.MEDIUM: 1,
            Severity.HIGH: 2,
            Severity.CRITICAL: 3,
        }[self]


class Action(StrEnum):
    """What the run does about a finding. Never stronger than the evidence permits."""

    BLOCK = "block"
    COMMENT = "comment"


class Kind(StrEnum):
    """What is wrong with a pin, in words that do not change when the sentence does.

    The key of a dependency finding needs something to tell two problems about one package apart,
    and until this existed that something was a slug of the summary. A summary is written by a model
    every run: the second live maintenance run rephrased all four of its findings, every key moved,
    and four issues were raised beside the four that already described the same problems. Worse
    quietly, a hold that a person had approved on one of those issues no longer matched anything, so
    the agent asked for the approval again.

    Closed on purpose, and small. A vocabulary with an "other" in it is a summary slug wearing a
    different name; when a capability finds something none of these describe, this list is what
    should grow, in a release somebody decided on.
    """

    QUARANTINE = "quarantine"
    """The version in use, or the one a reference resolves to, is inside the quarantine window."""
    UNKNOWN_AGE = "unknown_age"
    """Publication time for the pin in use could not be established — not the same as quarantine."""
    FLOATING = "floating"
    """The reference is not a concrete version: a branch, a channel, a rolling tag."""
    OUTDATED = "outdated"
    """A newer version exists and has cleared quarantine."""
    BUNDLE = "bundle"
    """Members that must move together are at versions that do not agree."""
    VULNERABLE = "vulnerable"
    """An advisory covers what is pinned. Keyed by kind so one pin is one issue."""


_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return _SLUG.sub("-", text.strip().lower()).strip("-")


@dataclass(frozen=True, slots=True)
class Location:
    """Where to attach a comment today. Volatile, and deliberately absent from the key."""

    path: str
    line: int | None = None

    def as_json(self) -> dict[str, object]:
        return {"path": self.path, "line": self.line}


@dataclass(frozen=True, slots=True)
class Finding:
    capability: str
    klass: Klass
    severity: Severity
    subject: Subject
    summary: str
    rationale: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    """Keys of the evidence records behind the claim, in the run's evidence store."""
    remediation: str = ""
    location: Location | None = None
    advisory: str = ""
    """Advisory id(s) for the body and the report. Not part of the key when `kind` is vulnerable —
    nine CVEs on one pin are one problem, and a key per advisory opened nine issues for one bump."""
    symbol: str = ""
    slug: str = ""
    """Stable identity for a code finding. Part of the key; never derived from `summary`.

    Package findings use `kind` instead. An empty slug on a path finding falls back to a summary
    slug only for in-process fixtures — result.json requires an explicit slug so wording drift
    cannot open a second issue.
    """
    forbidden_state: bool = False
    target: str = ""
    """The version the remediation would move to, when the finding is a version move.

    Deliberately absent from the key: it changes every time a newer release appears while the
    problem stays the one problem. What it is for is arithmetic the agent does itself — how far a
    move goes, which decides whether it may ship without asking anybody."""
    needs_unlock: bool = False
    """Declared by the task: this needs a person's approval before it may ship.

    A declaration, not a decision. What it causes is in `agent/unlock.py`, and the agent adds the
    same hold where it can prove one, so a task that forgets to declare a major move does not turn
    policy off."""
    kind: Kind | None = None
    """What is wrong, from a closed vocabulary, for a finding about a package. Part of the key."""
    bundle: str = ""
    """Coupled-bundle id from the comment pass. When set, key by bundle, not member pin."""
    members: tuple[Subject, ...] = field(default_factory=tuple)
    """Every pin a collapsed bundle finding covers. Empty means just `subject`."""
    advisories: tuple[str, ...] = field(default_factory=tuple)
    """Every advisory id folded into this finding. Empty means use `advisory` alone when set."""
    via: str = ""
    """How a transitive package entered the graph: direct pin → … → subject.

    For `kind: vulnerable` on a package that is not a direct declared pin, required in knowledge so
    the issue names what to bump. Empty when the subject itself is the declared pin.
    """

    @property
    def advisory_ids(self) -> tuple[str, ...]:
        if self.advisories:
            return self.advisories
        return (self.advisory,) if self.advisory.strip() else ()

    @property
    def key(self) -> str:
        """Stable across runs: what identifies the problem, never what drifts.

        A version, a line number or a scanner's wording change between runs while the problem stays
        the same, and a key that moves turns one problem into a stream of duplicate comments.

        For a vulnerable pin the identity is `kind`, not the advisory id: every advisory against one
        package is one bump and one conversation. Other package findings still use the advisory when
        one is present (legacy) or `kind` otherwise. Code findings use an explicit `slug`, never the
        summary: the second live maintenance run rephrased a Go client defect and opened a duplicate
        beside the open PR that already fixed it.

        A finding that names a bundle is keyed by that id instead of by whichever member the
        analyst happened to emit — otherwise a BSR+cargo couple opens two issues for one move.
        """
        named = self.bundle.strip()
        identity = _identity(self)
        if named:
            return ":".join(
                part for part in (self.capability, "bundle", slug(named), identity) if part
            )
        parts = [self.capability]
        if self.subject.ecosystem:
            parts += [self.subject.ecosystem, self.subject.package or "", identity]
        else:
            parts += [self.subject.path or "", _code_slug(self)]
            if self.symbol:
                parts.append(self.symbol)
        return ":".join(part for part in parts if part)

    def reliability(self, records: dict[str, Reliability]) -> Reliability:
        """The weakest reliability among the records behind it.

        A claim is only as demonstrated as its shakiest input, so one heuristic fact makes the whole
        finding heuristic. With no evidence at all it is heuristic too — an unsupported claim cannot
        earn the right to block.
        """
        if not self.evidence:
            return Reliability.HEURISTIC
        found = [records.get(key, Reliability.HEURISTIC) for key in self.evidence]
        return (
            Reliability.REPRODUCIBLE
            if all(item is Reliability.REPRODUCIBLE for item in found)
            else Reliability.HEURISTIC
        )

    def as_json(self) -> dict[str, object]:
        return {
            "key": self.key,
            "capability": self.capability,
            "class": self.klass.value,
            "severity": self.severity.value,
            "subject": self.subject.as_json(),
            "location": self.location.as_json() if self.location else None,
            "summary": self.summary,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "remediation": self.remediation,
            "advisory": self.advisory,
            "advisories": list(self.advisory_ids),
            "symbol": self.symbol,
            "slug": self.slug,
            "forbidden_state": self.forbidden_state,
            "target": self.target,
            "needs_unlock": self.needs_unlock,
            "kind": self.kind.value if self.kind else "",
            "bundle": self.bundle,
            "via": self.via,
            "members": [
                {
                    "ecosystem": item.ecosystem,
                    "package": item.package,
                    "version": item.version,
                    "path": item.path,
                }
                for item in self.members
            ],
        }


def with_kind_severity(finding: Finding) -> Finding:
    """Raise severity floors the knowledge requires for certain kinds — never lower.

    Quarantine broken is high; floating and unknown publish date are medium. The model may still
    emit `low`; the runner owns these floors so the issue list and the body agree with policy
    regardless of the session.
    """
    if finding.kind is Kind.QUARANTINE and finding.severity.rank < Severity.HIGH.rank:
        return replace(finding, severity=Severity.HIGH)
    if (
        finding.kind in {Kind.FLOATING, Kind.UNKNOWN_AGE}
        and finding.severity.rank < Severity.MEDIUM.rank
    ):
        return replace(finding, severity=Severity.MEDIUM)
    return finding


def _code_slug(finding: Finding) -> str:
    """Explicit slug when set; otherwise a summary slug (fixtures / pre-slug in-memory findings)."""
    named = finding.slug.strip()
    if named:
        return slug(named)
    return slug(finding.summary)


def _identity(finding: Finding) -> str:
    """The segment of the key that names the problem after capability and subject.

    Vulnerable findings always use `kind`: the advisory id changes the detail on the issue, not
    which conversation owns the pin. Everything else keeps the historical rule — advisory when
    present, else kind, else a summary slug.
    """
    if finding.kind is Kind.VULNERABLE:
        return Kind.VULNERABLE.value
    return finding.advisory or (finding.kind.value if finding.kind else slug(finding.summary))


def code_fingerprint(finding: Finding) -> tuple[str, str, str] | None:
    """Match key for soft-dedup of code issues: capability + path + symbol (slug ignored)."""
    if finding.bundle.strip() or finding.subject.ecosystem or finding.subject.package:
        return None
    path = (finding.subject.path or "").strip()
    if not path:
        return None
    return (finding.capability, path, finding.symbol.strip())


def code_fingerprint_from_key(key: str) -> tuple[str, str, str] | None:
    """Parse a code finding key into the soft-dedup fingerprint, or `None` when not a code key."""
    parts = [part for part in key.split(":") if part]
    if len(parts) < 3:
        return None
    capability, path = parts[0], parts[1]
    if path.startswith("ecosystems/") or path == "bundle":
        return None
    if len(parts) == 3:
        return (capability, path, "")
    if len(parts) == 4:
        return (capability, path, parts[3])
    return None


def merge(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """One problem found by two tasks is one finding, judged by the stricter of the two.

    Resolved by a rule rather than by asking a stronger model: escalation would put latency, cost
    and nondeterminism into a blocking check, and a gate that answers differently on a rerun stops
    being believed. Both original judgements stay in the manifest.

    Vulnerable findings about one pin share a key, so every advisory against that pin lands in one
    finding here — one issue, one fix branch — rather than one ticket per CVE.
    """
    by_key: dict[str, Finding] = {}
    for finding in findings:
        existing = by_key.get(finding.key)
        if existing is None:
            by_key[finding.key] = finding
            continue
        by_key[finding.key] = _stricter(existing, finding)
    return tuple(
        sorted(
            by_key.values(),
            key=lambda item: (-item.klass.rank, -item.severity.rank, item.key),
        )
    )


def _stricter(first: Finding, second: Finding) -> Finding:
    """The two judgements combined, keeping every part the key is built from.

    Every part, because the result is stored under the key it was merged by. Dropping one — `kind`
    was dropped, silently, from the moment it was added — produces a finding whose own key is not
    the key it is filed under, so the run reports one problem and tracks another, and next week both
    of them again.
    """
    klass = first.klass if first.klass.rank >= second.klass.rank else second.klass
    severity = first.severity if first.severity.rank >= second.severity.rank else second.severity
    winner = first if (first.klass, first.severity) == (klass, severity) else second
    evidence = tuple(dict.fromkeys(first.evidence + second.evidence))
    advisories = tuple(dict.fromkeys([*first.advisory_ids, *second.advisory_ids]))
    advisory = advisories[0] if len(advisories) == 1 else ", ".join(advisories)
    rationales = tuple(
        dict.fromkeys(text for text in (first.rationale, second.rationale) if text.strip())
    )
    summary = winner.summary
    if len(advisories) > 1 and winner.kind is Kind.VULNERABLE:
        package = winner.subject.package or winner.subject.path or "package"
        summary = f"{package} is affected by {len(advisories)} advisories ({advisory})."
    return Finding(
        capability=winner.capability,
        klass=klass,
        severity=severity,
        subject=winner.subject,
        summary=summary,
        rationale="\n\n".join(rationales) if rationales else winner.rationale,
        evidence=evidence,
        remediation=winner.remediation or first.remediation or second.remediation,
        location=winner.location or first.location or second.location,
        advisory=advisory,
        symbol=winner.symbol or first.symbol or second.symbol,
        slug=winner.slug or first.slug or second.slug,
        forbidden_state=first.forbidden_state or second.forbidden_state,
        target=winner.target or first.target or second.target,
        # Either task asking for a person is enough. One that saw a reason to hold saw something the
        # other did not, and the cheap way to be wrong here is to ship a move nobody approved.
        needs_unlock=first.needs_unlock or second.needs_unlock,
        kind=winner.kind or first.kind or second.kind,
        bundle=winner.bundle or first.bundle or second.bundle,
        members=tuple(dict.fromkeys(first.members + second.members)),
        advisories=advisories,
        via=winner.via or first.via or second.via,
    )
