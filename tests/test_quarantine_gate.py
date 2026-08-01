"""Uncleared current pins must appear as forbidden-state findings for the owning task."""

from __future__ import annotations

from datetime import UTC, datetime

from agent.evidence import Evidence, Origin, Question, Subject
from agent.findings import Finding, Kind, Klass, Severity
from agent.quarantine_gate import incomplete_current_quarantine

MOMENT = datetime(2026, 7, 31, tzinfo=UTC)
ECO = "ecosystems/cargo"
PKG = "serde"
OUTDATED = "capabilities/deps-outdated"
VULN = "capabilities/deps-vuln"


def _gate(
    records: list[Evidence],
    findings: tuple[Finding, ...] = (),
    *,
    capability: str = OUTDATED,
    ecosystem: str = ECO,
) -> str | None:
    return incomplete_current_quarantine(
        records, findings, capability=capability, ecosystem=ecosystem
    )


def _cleared(*, value: bool | None, package: str = PKG, ecosystem: str = ECO) -> Evidence:
    return Evidence.verified(
        question=Question.CURRENT_CLEARED,
        subject=Subject(ecosystem=ecosystem, package=package, version="1.0.0"),
        value=value,
        origin=Origin.API,
        source=f"{ecosystem}:{package}@1.0.0→none",
        observed_at=MOMENT,
        recipe="capabilities/deps-outdated@cleared_pin_target",
    )


def _finding(
    *,
    kind: Kind,
    forbidden: bool,
    package: str = PKG,
    ecosystem: str = ECO,
) -> Finding:
    return Finding(
        capability="capabilities/deps-outdated",
        klass=Klass.ROUTINE,
        severity=Severity.MEDIUM,
        subject=Subject(ecosystem=ecosystem, package=package),
        summary=f"{package} pin state",
        rationale="test",
        forbidden_state=forbidden,
        kind=kind,
    )


def test_gate_ignores_model_recorded_tool_payload() -> None:
    """A model that stores the whole cleared_pin_target JSON must not trip the gate."""
    bogus = Evidence.verified(
        question=Question.CURRENT_CLEARED,
        subject=Subject(ecosystem=ECO, package="serde", version="1.0.0"),
        value={"current_resolved": "1.0.0", "current_cleared": True, "target": None},
        origin=Origin.API,
        source="model mistyped the tool answer",
        observed_at=MOMENT,
        recipe="capabilities/deps-outdated@record_fact",
    )
    assert _gate([bogus]) is None


def test_gate_ignores_cleared_tool_fact() -> None:
    assert _gate([_cleared(value=True)]) is None


def test_gate_requires_quarantine_finding_when_uncleared() -> None:
    reason = _gate([_cleared(value=False)])
    assert reason is not None
    assert "serde" in reason
    assert "forbidden_state" in reason


def test_gate_null_current_cleared_requires_unknown_age() -> None:
    reason = _gate([_cleared(value=None)])
    assert reason is not None
    assert "unknown_age" in reason
    assert "quarantine" in reason  # contrast in the message


def test_gate_rejects_quarantine_kind_for_null_age() -> None:
    reason = _gate(
        [_cleared(value=None)],
        (_finding(kind=Kind.QUARANTINE, forbidden=True),),
    )
    assert reason is not None
    assert "unknown_age" in reason


def test_gate_accepts_unknown_age_for_null() -> None:
    assert (
        _gate(
            [_cleared(value=None)],
            (_finding(kind=Kind.UNKNOWN_AGE, forbidden=True),),
        )
        is None
    )


def test_gate_accepts_quarantine_with_forbidden_state() -> None:
    assert (
        _gate(
            [_cleared(value=False)],
            (_finding(kind=Kind.QUARANTINE, forbidden=True),),
        )
        is None
    )


def test_gate_rejects_quarantine_without_forbidden_state() -> None:
    reason = _gate(
        [_cleared(value=False)],
        (_finding(kind=Kind.QUARANTINE, forbidden=False),),
    )
    assert reason is not None


def test_gate_rejects_outdated_kind_for_uncleared_current() -> None:
    reason = _gate(
        [_cleared(value=False)],
        (_finding(kind=Kind.OUTDATED, forbidden=True),),
    )
    assert reason is not None


def test_gate_accepts_floating_or_vulnerable_with_forbidden_state() -> None:
    assert (
        _gate(
            [_cleared(value=False)],
            (_finding(kind=Kind.FLOATING, forbidden=True),),
        )
        is None
    )
    assert (
        _gate(
            [_cleared(value=False)],
            (_finding(kind=Kind.VULNERABLE, forbidden=True),),
        )
        is None
    )


def test_gate_matches_package_and_ecosystem() -> None:
    reason = _gate(
        [_cleared(value=False, package="serde"), _cleared(value=False, package="tokio")],
        (_finding(kind=Kind.QUARANTINE, forbidden=True, package="serde"),),
    )
    assert reason is not None
    assert "tokio" in reason


def test_gate_ignores_foreign_ecosystem_uncleared_facts() -> None:
    """Run-global evidence must not charge cargo for a go-modules pin (dogfood cascade)."""
    records = [
        _cleared(value=False, package="serde", ecosystem=ECO),
        _cleared(
            value=False,
            package="github.com/bufbuild/buf",
            ecosystem="ecosystems/go-modules",
        ),
    ]
    cargo_covered = (_finding(kind=Kind.QUARANTINE, forbidden=True, package="serde"),)
    assert _gate(records, cargo_covered, ecosystem=ECO) is None
    reason = _gate(records, cargo_covered, ecosystem="ecosystems/go-modules")
    assert reason is not None
    assert "buf" in reason
    assert "serde" not in reason


def test_gate_skips_non_outdated_capability() -> None:
    """deps-vuln must not own current-quarantine obligations."""
    assert _gate([_cleared(value=False)], capability=VULN) is None


def test_gate_skips_when_ecosystem_missing() -> None:
    assert _gate([_cleared(value=False)], ecosystem="") is None
