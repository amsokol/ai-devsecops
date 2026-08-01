"""Findings tracked as issues: one per finding, updated not duplicated, closed with proof."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from agent.absence import Absences
from agent.coverage import Coverage
from agent.domain import Outcome, RunResult
from agent.evidence import Evidence, Origin, Reliability, Subject
from agent.findings import Action, Finding, Kind, Klass, Location, Severity, merge
from agent.issues import LABEL, Tracking, track_findings
from agent.scm.fake import FakePlatform
from agent.scm.marker import read
from agent.scm.port import Issue
from agent.verdict import Judged, TaskOutcome, Verdict

HEAD = "0f1e2d3c4b5a69788796a5b4c3d2e1f009182736"
WHEN = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)
CAPABILITY = "capabilities/deps-vuln"
CLEAN = TaskOutcome(
    id="deps-vuln@python-uv", capability=CAPABILITY, required=True, outcome=Outcome.CLEAN
)
UNVERIFIED = TaskOutcome(
    id="deps-vuln@python-uv", capability=CAPABILITY, required=True, outcome=Outcome.UNVERIFIED
)


def finding(*, advisory: str = "PYSEC-2026-1", version: str = "3.1.3") -> Finding:
    return Finding(
        capability=CAPABILITY,
        klass=Klass.SECURITY,
        severity=Severity.HIGH,
        subject=Subject(ecosystem="ecosystems/python-uv", package="jinja2", version=version),
        summary=f"jinja2 {version} is affected by {advisory}",
        rationale="pip-audit reports it against the resolved pin.",
        remediation="Bump jinja2 to 3.1.6.",
        advisory=advisory,
        advisories=(advisory,) if advisory else (),
        kind=Kind.VULNERABLE,
        location=Location(path="pyproject.toml", line=12),
    )


def judged(item: Finding, *, capped: bool = False) -> Judged:
    return Judged(
        finding=item, action=Action.BLOCK, reliability=Reliability.REPRODUCIBLE, capped=capped
    )


def verdict_of(*items: Judged) -> Verdict:
    return Verdict(result=RunResult.BLOCKED, judged=items, blocking=items)


def covering(*packages: str) -> Coverage:
    """A run that examined exactly these packages of the ecosystem the findings here belong to."""
    return Coverage.of(
        Evidence.verified(
            question="latest-version",
            subject=Subject(ecosystem="ecosystems/python-uv", package=package),
            value="3.1.6",
            origin=Origin.API,
            source="https://pypi.org/",
            observed_at=WHEN,
            recipe=f"{CAPABILITY}@fetch",
        )
        for package in packages
    )


def track(
    platform: FakePlatform,
    verdict: Verdict,
    *,
    outcomes: tuple[TaskOutcome, ...] = (CLEAN,),
    limit: int = 10,
    memory: dict[str, Any] | None = None,
    coverage: Coverage | None = None,
) -> Tracking:
    """One run of the reconciliation, carrying the streaks forward when a test passes a memory.

    A test that passes none is a first run, which is what most of them are about; closing needs two,
    so a test about a closure is a test that keeps the memory between its calls.
    """
    carried = memory if memory is not None else {}
    counted = Absences.of(carried, outcomes=outcomes, run="run-1", when=WHEN, coverage=coverage)
    record = track_findings(
        platform, verdict=verdict, absences=counted, head=HEAD, limit=limit, label=LABEL
    )
    if memory is not None:
        memory.update(counted.document(carried))
    return record


def until_closed(platform: FakePlatform, verdict: Verdict, **rest: Any) -> Tracking:
    """The run in which an absent finding is finally closed, having been absent once before."""
    memory: dict[str, Any] = {}
    track(platform, verdict, memory=memory, **rest)
    return track(platform, verdict, memory=memory, **rest)


def what(record: Tracking) -> list[str]:
    return [item.what for item in record.posted]


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform()


def test_a_new_finding_becomes_one_labelled_issue_carrying_its_key(platform: FakePlatform) -> None:
    record = track(platform, verdict_of(judged(finding())))

    assert what(record) == ["raised"]
    assert record.raised == 1
    tracked = platform.tracked[0]
    assert read(tracked.body) == finding().key
    assert platform.labels[tracked.number] == (LABEL,)
    assert tracked.title == "🟠 vulnerability — jinja2"
    assert LABEL == "ai agent"


def test_an_issue_under_the_legacy_label_is_still_found(platform: FakePlatform) -> None:
    """Renaming the label must not raise a second ticket for the same finding key."""
    from agent.scm import marker as scm_marker

    key = finding().key
    body = f"old body\n\n{scm_marker.render(key)}"
    platform.tracked.append(
        Issue(number=9, key=key, title="⚠️ agent: vulnerability — jinja2", body=body, reference="")
    )
    platform.labels[9] = ("agent",)
    record = track(platform, verdict_of(judged(finding())))
    assert "raised" not in what(record)
    assert any(item.what == "updated" for item in record.posted)
    assert len(platform.tracked) == 1
    assert "agent:" not in platform.tracked[0].title


def test_issue_titles_name_the_kind_for_a_human_scanning_the_list(platform: FakePlatform) -> None:
    from agent.findings import with_kind_severity

    cases = (
        (Kind.FLOATING, "floating dependency", "dtolnay/rust-toolchain", "🟡"),
        (Kind.QUARANTINE, "quarantine broken", "actions/checkout", "🟠"),
        (Kind.UNKNOWN_AGE, "release date unknown", "buf.build/connectrpc/rust", "🟡"),
        (Kind.OUTDATED, "dependency update", "serde", "⚪"),
        (Kind.VULNERABLE, "vulnerability", "jinja2", "⚪"),
    )
    for kind, phrase, package, emoji in cases:
        item = with_kind_severity(
            Finding(
                capability=(
                    "capabilities/deps-vuln"
                    if kind is Kind.VULNERABLE
                    else "capabilities/deps-outdated"
                ),
                klass=Klass.SECURITY if kind is Kind.VULNERABLE else Klass.ROUTINE,
                severity=Severity.LOW,
                subject=Subject(ecosystem="ecosystems/cargo", package=package),
                summary=f"{package} problem",
                rationale="test",
                kind=kind,
                forbidden_state=kind in {Kind.QUARANTINE, Kind.FLOATING, Kind.UNKNOWN_AGE},
            )
        )
        track(platform, verdict_of(judged(item)))
        assert platform.tracked[-1].title == f"{emoji} {phrase} — {package}"
        if kind is Kind.QUARANTINE:
            assert item.severity is Severity.HIGH
            assert "**high**" in platform.tracked[-1].body
        if kind is Kind.FLOATING:
            assert item.severity is Severity.MEDIUM
            assert "**medium**" in platform.tracked[-1].body


def test_bundle_issue_title_composes_kind_phrase_and_bundle_id(platform: FakePlatform) -> None:
    from agent.findings import with_kind_severity

    item = with_kind_severity(
        Finding(
            capability="capabilities/deps-outdated",
            klass=Klass.ROUTINE,
            severity=Severity.LOW,
            subject=Subject(ecosystem="ecosystems/bsr", package="buf.build/connectrpc/rust"),
            summary="bundle quarantine",
            rationale="test",
            kind=Kind.QUARANTINE,
            bundle="rust-connect",
            forbidden_state=True,
        )
    )
    track(platform, verdict_of(judged(item)))
    assert platform.tracked[0].title == "🟠 quarantine broken — bundle rust-connect"
    assert "**high**" in platform.tracked[0].body


def test_transitive_vuln_issue_names_how_the_package_was_brought_in(
    platform: FakePlatform,
) -> None:
    item = Finding(
        capability=CAPABILITY,
        klass=Klass.SECURITY,
        severity=Severity.HIGH,
        subject=Subject(ecosystem="ecosystems/python-uv", package="h11", version="0.14.0"),
        summary="h11 0.14.0 is affected by GHSA-xxxx",
        rationale="Brought in through httpx; pip-audit reports GHSA-xxxx against the lock.",
        remediation="Bump httpx so the lock picks a fixed h11, or override h11.",
        advisory="GHSA-xxxx",
        advisories=("GHSA-xxxx",),
        kind=Kind.VULNERABLE,
        via="httpx → h11",
    )
    track(platform, verdict_of(judged(item)))
    body = platform.tracked[0].body
    assert "Brought in by: httpx → h11" in body
    assert read(body) == item.key


def test_the_same_finding_next_week_is_not_a_second_issue(platform: FakePlatform) -> None:
    """The whole promise of tracking by key: a weekly run on an unfixed problem writes nothing."""
    track(platform, verdict_of(judged(finding())))

    again = track(platform, verdict_of(judged(finding())))

    assert what(again) == ["unchanged"]
    assert len(platform.tracked) == 1
    assert not platform.notes


def test_a_finding_that_changed_updates_the_issue_it_already_has(platform: FakePlatform) -> None:
    track(platform, verdict_of(judged(finding())))

    moved = track(platform, verdict_of(judged(finding(version="3.1.4"))))

    assert what(moved) == ["updated"]
    assert len(platform.tracked) == 1
    assert "3.1.4" in platform.tracked[0].body


def test_a_title_leaves_out_what_drifts_so_a_saved_search_keeps_matching(
    platform: FakePlatform,
) -> None:
    track(platform, verdict_of(judged(finding())))
    first = platform.tracked[0].title

    track(platform, verdict_of(judged(finding(version="3.1.4"))))

    assert platform.tracked[0].title == first
    assert "3.1.3" not in first
    assert "PYSEC" not in first


def test_a_finding_that_is_gone_is_closed_with_the_evidence_that_settles_it(
    platform: FakePlatform,
) -> None:
    track(platform, verdict_of(judged(finding())))

    cleared = until_closed(platform, verdict_of())

    assert what(cleared) == ["closed"]
    assert cleared.closed == 1
    assert not platform.tracked
    key, note = platform.notes[0]
    assert key == finding().key
    assert CAPABILITY in note
    assert HEAD[:12] in note
    assert "reopens this issue" in note
    assert "new issue" not in note


def test_a_finding_that_returns_reopens_the_closed_issue(platform: FakePlatform) -> None:
    """One subject — one ticket: history stays on the closed issue, not a twin."""
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)
    number = platform.tracked[0].number
    track(platform, verdict_of(), memory=memory)
    track(platform, verdict_of(), memory=memory)
    assert not platform.tracked
    assert len(platform.closed) == 1

    again = track(platform, verdict_of(judged(finding())), memory=memory)

    assert what(again) == ["reopened"]
    assert again.raised == 0
    assert again.numbers[finding().key] == number
    assert len(platform.tracked) == 1
    assert platform.tracked[0].number == number
    assert not platform.closed
    assert any(call.what == "reopen_issue" for call in platform.calls)
    assert any(call.what == "raise_issue" for call in platform.calls)  # the first raise only
    assert sum(1 for call in platform.calls if call.what == "raise_issue") == 1
    assert any("open once more" in body for _, body in platform.notes)


def test_reopening_does_not_consume_the_new_issue_quota(platform: FakePlatform) -> None:
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)
    track(platform, verdict_of(), memory=memory)
    track(platform, verdict_of(), memory=memory)

    again = track(platform, verdict_of(judged(finding())), memory=memory, limit=0)

    assert what(again) == ["reopened"]
    assert again.raised == 0
    assert len(platform.tracked) == 1


def test_one_complete_run_without_a_finding_is_not_yet_a_closure(platform: FakePlatform) -> None:
    """A closure is a claim nobody revisits, and a task is asked to be exhaustive rather than
    proved to be. One run of it costs a week of visibility; being wrong costs the tracker."""
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)

    once = track(platform, verdict_of(), memory=memory)

    assert what(once) == ["kept-open"]
    assert "next run" in once.posted[0].detail
    assert len(platform.tracked) == 1
    assert not platform.notes


def test_a_finding_that_comes_back_starts_its_absence_over(platform: FakePlatform) -> None:
    """Otherwise two absences months apart, with the problem reported in between, close an issue
    about a problem that is still there."""
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)
    track(platform, verdict_of(), memory=memory)
    track(platform, verdict_of(judged(finding())), memory=memory)

    again = track(platform, verdict_of(), memory=memory)

    assert what(again) == ["kept-open"]
    assert len(platform.tracked) == 1


def test_a_run_that_could_not_look_does_not_spend_the_absence(platform: FakePlatform) -> None:
    """A narrowed or broken run leaves the count exactly as it was. Treating "did not look" as one
    of the two would close everything in a repository whose runs alternate between ecosystems."""
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)
    track(platform, verdict_of(), memory=memory)
    track(platform, verdict_of(), outcomes=(), memory=memory)

    third = track(platform, verdict_of(), outcomes=(UNVERIFIED,), memory=memory)

    assert what(third) == ["kept-open"]
    assert len(platform.tracked) == 1
    assert what(track(platform, verdict_of(), memory=memory)) == ["closed"]


def test_an_issue_a_person_is_reading_settles_on_the_first_answer(
    platform: FakePlatform,
) -> None:
    """The wait is for the issues nobody is looking at. Somebody who wrote on this one is told what
    the recheck found on it, and "come back next week" is the wrong reply to that."""
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)
    asked = Absences.of(
        memory, outcomes=(CLEAN,), run="run-2", when=WHEN, asked=frozenset({finding().key})
    )

    record = track_findings(
        platform, verdict=verdict_of(), absences=asked, head=HEAD, limit=10, label=LABEL
    )

    assert what(record) == ["closed"]
    assert not platform.tracked


def test_a_quarantine_issue_is_not_closed_on_first_unlock_miss(
    platform: FakePlatform,
) -> None:
    """Unlock wake puts the key in `asked`, but a single recheck that omitted quarantine must not
    close a forbidden-state issue — that closed demo2 #4 while checkout was still in window."""
    from agent.findings import Kind

    pin = Finding(
        capability="capabilities/deps-outdated",
        klass=Klass.ROUTINE,
        severity=Severity.MEDIUM,
        subject=Subject(
            ecosystem="ecosystems/github-actions",
            package="actions/checkout",
            version="v7",
        ),
        summary="checkout tip still in quarantine",
        rationale="release date inside window",
        remediation="Pin to v7.0.0",
        target="v7.0.0",
        kind=Kind.QUARANTINE,
    )
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(pin)), memory=memory)
    asked = Absences.of(
        memory,
        outcomes=(
            TaskOutcome(
                id="deps-outdated@github-actions",
                capability="capabilities/deps-outdated",
                required=True,
                outcome=Outcome.CLEAN,
            ),
        ),
        run="run-2",
        when=WHEN,
        asked=frozenset({pin.key}),
        coverage=Coverage.of(
            (
                Evidence.verified(
                    question="declared-pin",
                    subject=Subject(
                        ecosystem="ecosystems/github-actions", package="actions/checkout"
                    ),
                    value="v7",
                    origin=Origin.TOOL,
                    source="list",
                    observed_at=WHEN,
                    recipe="capabilities/deps-outdated@list_action_pins",
                ),
            )
        ),
    )

    record = track_findings(
        platform, verdict=verdict_of(), absences=asked, head=HEAD, limit=10, label=LABEL
    )

    assert what(record) == ["kept-open"]
    assert len(platform.tracked) == 1


def test_a_sweep_that_did_not_reach_the_package_cannot_close_its_issue(
    platform: FakePlatform,
) -> None:
    """The live failure this guards: a check that completed, and got through part of the tree.

    Its report is a list of findings and looks no different from a thorough run's. What tells them
    apart is the evidence, which names what was actually examined.
    """
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)

    short = track(platform, verdict_of(), memory=memory, coverage=covering("cryptography"))

    assert what(short) == ["kept-open"]
    assert "did not get to it this run" in short.posted[0].detail
    assert len(platform.tracked) == 1


def test_a_run_that_did_not_reach_a_package_does_not_spend_its_absence(
    platform: FakePlatform,
) -> None:
    """Same rule as a check that did not finish: only runs that looked are allowed to count."""
    memory: dict[str, Any] = {}
    track(platform, verdict_of(judged(finding())), memory=memory)
    track(platform, verdict_of(), memory=memory, coverage=covering("jinja2"))
    track(platform, verdict_of(), memory=memory, coverage=covering("cryptography"))

    third = track(platform, verdict_of(), memory=memory, coverage=covering("jinja2"))

    assert what(third) == ["closed"]


def test_a_check_that_did_not_finish_leaves_the_issue_exactly_as_it_was(
    platform: FakePlatform,
) -> None:
    """Silence is the correct output here. "Still present" would be as unfounded as a closure, and a
    weekly note that nothing is known is what teaches a team to mute the agent."""
    track(platform, verdict_of(judged(finding())))

    unproved = track(platform, verdict_of(), outcomes=(UNVERIFIED,))

    assert what(unproved) == ["kept-open"]
    assert "never got to the end" in unproved.posted[0].detail
    assert len(platform.tracked) == 1
    assert not platform.notes


def test_a_capability_that_never_ran_cannot_close_anything(platform: FakePlatform) -> None:
    track(platform, verdict_of(judged(finding())))

    narrowed = track(platform, verdict_of(), outcomes=())

    assert what(narrowed) == ["kept-open"]
    assert "did not run" in narrowed.posted[0].detail
    assert len(platform.tracked) == 1


def test_one_ecosystem_of_a_capability_cannot_close_another(platform: FakePlatform) -> None:
    """`--only deps-outdated@cargo` must not close a python-uv issue of the same capability."""
    cargo_cap = "capabilities/deps-outdated"
    cargo = Finding(
        capability=cargo_cap,
        klass=Klass.ROUTINE,
        severity=Severity.MEDIUM,
        subject=Subject(ecosystem="ecosystems/cargo", package="serde", version="1.0.0"),
        summary="serde is outdated",
        rationale="registry has a newer cleared release.",
        remediation="Bump serde.",
        location=Location(path="Cargo.toml", line=1),
    )
    track(
        platform,
        verdict_of(judged(cargo)),
        outcomes=(
            TaskOutcome(
                id="deps-outdated@cargo",
                capability=cargo_cap,
                required=True,
                outcome=Outcome.FINDINGS,
            ),
        ),
    )
    assert len(platform.tracked) == 1

    # A later run that only completes python-uv must not treat the cargo finding as absent-proven.
    only_uv = TaskOutcome(
        id="deps-outdated@python-uv",
        capability=cargo_cap,
        required=True,
        outcome=Outcome.CLEAN,
    )
    memory: dict[str, Any] = {}
    first = track(
        platform,
        verdict_of(),
        outcomes=(only_uv,),
        memory=memory,
    )
    second = track(
        platform,
        verdict_of(),
        outcomes=(only_uv,),
        memory=memory,
    )
    assert what(first) == ["kept-open"]
    assert "ecosystems/cargo" in first.posted[0].detail
    assert what(second) == ["kept-open"]
    assert len(platform.tracked) == 1
    assert not platform.closed


def test_a_run_stays_within_the_new_issues_it_is_allowed(platform: FakePlatform) -> None:
    """Left for the next run rather than dropped: the ceiling counts subjects, not advisories."""
    findings = verdict_of(
        judged(finding(advisory="PYSEC-2026-1")),
        judged(
            Finding(
                capability=CAPABILITY,
                klass=Klass.SECURITY,
                severity=Severity.HIGH,
                subject=Subject(ecosystem="ecosystems/python-uv", package="urllib3", version="1.0"),
                summary="urllib3 is affected",
                rationale="pip-audit reports it.",
                remediation="Bump urllib3.",
                advisory="PYSEC-2026-2",
                kind=Kind.VULNERABLE,
                location=Location(path="pyproject.toml", line=12),
            )
        ),
        judged(
            Finding(
                capability=CAPABILITY,
                klass=Klass.SECURITY,
                severity=Severity.HIGH,
                subject=Subject(
                    ecosystem="ecosystems/python-uv", package="requests", version="1.0"
                ),
                summary="requests is affected",
                rationale="pip-audit reports it.",
                remediation="Bump requests.",
                advisory="PYSEC-2026-3",
                kind=Kind.VULNERABLE,
                location=Location(path="pyproject.toml", line=13),
            )
        ),
    )

    record = track(platform, findings, limit=2)

    assert what(record) == ["raised", "raised", "deferred"]
    assert record.raised == 2
    assert "limit of 2" in record.posted[-1].detail


def test_vulnerability_findings_take_the_new_issue_ceiling_before_routine(
    platform: FakePlatform,
) -> None:
    """A small weekly budget still surfaces advisories before version drift."""
    routine = Finding(
        capability="capabilities/deps-outdated",
        klass=Klass.ROUTINE,
        severity=Severity.LOW,
        subject=Subject(ecosystem="ecosystems/cargo", package="aaaa-first-alphabetically"),
        summary="aaaa is behind",
        rationale="cleared target exists",
        kind=Kind.OUTDATED,
    )
    vuln = Finding(
        capability="capabilities/deps-vuln",
        klass=Klass.SECURITY,
        severity=Severity.HIGH,
        subject=Subject(ecosystem="ecosystems/cargo", package="zzzz-last-alphabetically"),
        summary="zzzz is affected",
        rationale="advisory",
        advisory="GHSA-zzzz",
        kind=Kind.VULNERABLE,
    )
    record = track(platform, verdict_of(judged(routine), judged(vuln)), limit=1)
    assert record.raised == 1
    assert what(record) == ["raised", "deferred"]
    assert platform.tracked[0].title == "🟠 vulnerability — zzzz-last-alphabetically"
    assert record.posted[0].key == vuln.key
    assert record.posted[1].key == routine.key


def test_same_subject_advisories_share_one_issue_and_one_ceiling_slot(
    platform: FakePlatform,
) -> None:
    """Nine CVEs on one pin are one conversation and one weekly slot, not nine of each."""
    merged = merge(
        (
            finding(advisory="PYSEC-2026-1"),
            finding(advisory="PYSEC-2026-2"),
            finding(advisory="PYSEC-2026-3"),
        )
    )
    assert len(merged) == 1
    assert merged[0].key.endswith(":vulnerable")
    assert set(merged[0].advisory_ids) == {
        "PYSEC-2026-1",
        "PYSEC-2026-2",
        "PYSEC-2026-3",
    }
    record = track(platform, verdict_of(judged(merged[0])), limit=1)
    assert record.raised == 1
    assert what(record) == ["raised"]
    assert "PYSEC-2026-1" in platform.tracked[0].body
    assert "PYSEC-2026-2" in platform.tracked[0].body


def test_per_advisory_issues_migrate_onto_the_pin_ticket(platform: FakePlatform) -> None:
    """Older agents keyed each CVE; the pin ticket takes over and closes the leftovers."""
    legacy_key = f"{CAPABILITY}:ecosystems/python-uv:jinja2:PYSEC-2026-1"
    platform.tracked.append(
        Issue(number=1, key=legacy_key, title="old", body=f"marker {legacy_key}")
    )
    platform.labels[1] = (LABEL,)
    merged = merge((finding(advisory="PYSEC-2026-1"), finding(advisory="PYSEC-2026-2")))[0]
    assert merged.kind is Kind.VULNERABLE
    record = track(platform, verdict_of(judged(merged)), limit=5)
    assert record.raised == 1
    assert any(item.what == "migrated" and item.key == legacy_key for item in record.posted)
    assert len(platform.tracked) == 1
    assert platform.tracked[0].key == merged.key
    assert platform.tracked[0].key.endswith(":vulnerable")


def test_an_issue_nobody_marked_is_not_the_agent_s_to_touch(platform: FakePlatform) -> None:
    """A label is not authorship: anyone can apply one, and closing a human's issue is unrecoverable
    in the only sense that matters — they stop trusting the thing that did it."""
    platform.tracked.append(
        Issue(
            number=99,
            key="",
            title="Please look at the login flow",
            body="No marker here, so this belongs to whoever wrote it.",
        )
    )
    platform.labels[99] = (LABEL,)

    record = track(platform, verdict_of())

    assert not record.posted
    assert len(platform.tracked) == 1


def test_a_platform_failure_costs_the_issues_and_not_the_run(platform: FakePlatform) -> None:
    platform.fail = "the token cannot see this repository"

    record = track(platform, verdict_of(judged(finding())))

    assert "token cannot see" in record.failure
    assert not record.posted


def test_code_finding_soft_dedups_when_slug_drifts_but_path_and_symbol_match(
    platform: FakePlatform,
) -> None:
    """#32 vs #56: same file+symbol, rephrased summary/slug → update the open issue, no duplicate."""

    def code(*, slug: str, summary: str) -> Finding:
        return Finding(
            capability="capabilities/code-quality",
            klass=Klass.ROUTINE,
            severity=Severity.HIGH,
            subject=Subject(path="go/echo/cmd/client/main.go"),
            summary=summary,
            rationale="Exit 0 on RPC failure.",
            remediation="os.Exit(1) after logging.",
            location=Location(path="go/echo/cmd/client/main.go", line=51),
            symbol="main",
            slug=slug,
        )

    first = code(
        slug="on-echo-rpc-failure-exit-status-so-shells-see-success",
        summary="On Echo RPC failure the client returns without a non-zero exit status.",
    )
    track(platform, verdict_of(judged(first)))
    assert len(platform.tracked) == 1
    number = platform.tracked[0].number

    second = code(
        slug="on-echo-rpc-failure-exit-so-callers-see-success",
        summary="On Echo RPC failure the client returns from main without a non-zero exit.",
    )
    record = track(platform, verdict_of(judged(second)))
    assert len(platform.tracked) == 1
    assert platform.tracked[0].number == number
    assert read(platform.tracked[0].body) == second.key
    assert "raised" not in what(record)
    assert any(item.what == "updated" for item in record.posted)


def test_a_code_finding_title_uses_phrase_and_summary_not_path(
    platform: FakePlatform,
) -> None:
    item = Finding(
        capability="capabilities/code-quality",
        klass=Klass.ROUTINE,
        severity=Severity.HIGH,
        subject=Subject(path="go/echo/cmd/client/main.go"),
        summary=(
            "On Echo RPC failure the client returns from main without a non-zero exit, "
            "so callers see success."
        ),
        rationale="Exit 0 on RPC failure.",
        remediation="os.Exit(1) after logging.",
        location=Location(path="go/echo/cmd/client/main.go", line=48),
        symbol="main",
        slug="echo-client-nonzero-exit",
    )
    track(platform, verdict_of(judged(item)))
    title = platform.tracked[0].title
    assert title.startswith("🟠 code quality — ")
    assert "go/echo" not in title
    assert "code-quality" not in title
    assert "non-zero exit" in title
    assert "go/echo/cmd/client/main.go" in platform.tracked[0].body
