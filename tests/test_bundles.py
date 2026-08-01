"""Coupled-bundle collapse: one issue, one branch, member migration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.absence import Absences
from agent.bundles import collapse, group_key, is_bundle_key, legacy_key
from agent.coverage import Coverage
from agent.domain import Outcome, RunResult
from agent.evidence import Reliability, Subject
from agent.findings import Action, Finding, Kind, Klass, Location, Severity
from agent.issues import LABEL, track_findings
from agent.scm.fake import FakePlatform
from agent.scm.port import Issue
from agent.verdict import Judged, TaskOutcome, Verdict

CAP = "capabilities/deps-outdated"
WHEN = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)
HEAD = "0f1e2d3c4b5a69788796a5b4c3d2e1f009182736"


def _member(
    *,
    ecosystem: str,
    package: str,
    path: str,
    bundle: str = "rust-buffa",
    kind: Kind = Kind.OUTDATED,
) -> Finding:
    return Finding(
        capability=CAP,
        klass=Klass.ROUTINE,
        severity=Severity.LOW,
        subject=Subject(ecosystem=ecosystem, package=package, version="0.1.0"),
        summary=f"{package} is outdated",
        rationale="registry has a newer cleared release.",
        remediation="Bump the bundle together.",
        location=Location(path=path, line=1),
        kind=kind,
        target="0.2.0",
        bundle=bundle,
    )


def test_collapse_merges_members_under_bundle_key() -> None:
    cargo = _member(ecosystem="ecosystems/cargo", package="buffa", path="Cargo.toml")
    bsr = _member(
        ecosystem="ecosystems/bsr", package="buf.build/anthropics/buffa", path="buf.gen.yaml"
    )
    merged = collapse((cargo, bsr))
    assert len(merged) == 1
    only = merged[0]
    assert is_bundle_key(only.key)
    assert only.key == f"{CAP}:bundle:rust-buffa:outdated"
    assert len(only.members) == 2
    assert group_key(only) == "bundle|rust-buffa"


def test_collapse_leaves_unbundled_findings_alone() -> None:
    pin = Finding(
        capability=CAP,
        klass=Klass.ROUTINE,
        severity=Severity.LOW,
        subject=Subject(ecosystem="ecosystems/cargo", package="serde", version="1.0.0"),
        summary="serde is outdated",
        rationale="newer",
        remediation="Bump serde.",
        kind=Kind.OUTDATED,
        target="1.0.1",
    )
    assert collapse((pin,)) == (pin,)


def test_track_raises_one_bundle_issue_and_migrates_members() -> None:
    platform = FakePlatform()
    cargo = _member(ecosystem="ecosystems/cargo", package="buffa", path="Cargo.toml")
    bsr = _member(
        ecosystem="ecosystems/bsr", package="buf.build/anthropics/buffa", path="buf.gen.yaml"
    )
    # Pre-collapse dual issues still open from an older agent.
    for finding in (cargo, bsr):
        key = legacy_key(finding, finding.subject)
        platform.tracked.append(
            Issue(number=len(platform.tracked) + 1, key=key, title="old", body=f"marker {key}")
        )
        platform.labels[platform.tracked[-1].number] = (LABEL,)

    collapsed = collapse((cargo, bsr))[0]
    judged = Judged(
        finding=collapsed,
        action=Action.COMMENT,
        reliability=Reliability.REPRODUCIBLE,
        capped=False,
    )
    verdict = Verdict(result=RunResult.PASS, judged=(judged,), blocking=())
    outcomes = (
        TaskOutcome(
            id="deps-outdated@cargo",
            capability=CAP,
            required=True,
            outcome=Outcome.FINDINGS,
        ),
        TaskOutcome(
            id="deps-outdated@bsr",
            capability=CAP,
            required=True,
            outcome=Outcome.FINDINGS,
        ),
    )
    memory: dict[str, Any] = {}
    absences = Absences.of(
        memory, outcomes=outcomes, run="r1", when=WHEN, coverage=Coverage(examined={})
    )
    record = track_findings(
        platform,
        verdict=verdict,
        absences=absences,
        head=HEAD,
        limit=10,
    )
    assert record.raised == 1
    assert any(item.what == "migrated" for item in record.posted)
    assert len(platform.tracked) == 1
    assert platform.tracked[0].key == collapsed.key
    assert "bundle rust-buffa" in platform.tracked[0].title


def test_bundle_absence_waits_when_one_ecosystem_did_not_run() -> None:
    platform = FakePlatform()
    collapsed = collapse(
        (
            _member(ecosystem="ecosystems/cargo", package="buffa", path="Cargo.toml"),
            _member(
                ecosystem="ecosystems/bsr",
                package="buf.build/anthropics/buffa",
                path="buf.gen.yaml",
            ),
        )
    )[0]
    judged = Judged(
        finding=collapsed,
        action=Action.COMMENT,
        reliability=Reliability.REPRODUCIBLE,
        capped=False,
    )
    verdict = Verdict(result=RunResult.PASS, judged=(judged,), blocking=())
    both = (
        TaskOutcome(
            id="deps-outdated@cargo",
            capability=CAP,
            required=True,
            outcome=Outcome.FINDINGS,
        ),
        TaskOutcome(
            id="deps-outdated@bsr",
            capability=CAP,
            required=True,
            outcome=Outcome.FINDINGS,
        ),
    )
    memory: dict[str, Any] = {}
    first = Absences.of(memory, outcomes=both, run="r1", when=WHEN)
    track_findings(platform, verdict=verdict, absences=first, head=HEAD, limit=10)
    memory = first.document(memory)

    only_cargo = (
        TaskOutcome(id="deps-outdated@cargo", capability=CAP, required=True, outcome=Outcome.CLEAN),
    )
    second = Absences.of(memory, outcomes=only_cargo, run="r2", when=WHEN)
    empty = Verdict(result=RunResult.PASS, judged=(), blocking=())
    record = track_findings(platform, verdict=empty, absences=second, head=HEAD, limit=10)
    assert any(item.what == "kept-open" for item in record.posted)
    assert "ecosystems/bsr" in record.posted[0].detail
    assert len(platform.tracked) == 1
