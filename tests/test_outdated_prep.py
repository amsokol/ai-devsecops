"""Deterministic outdated prep: census + cleared targets before the sweeper judges."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from agent.census import incomplete_pin_sweep
from agent.domain import PlannedTask, Role
from agent.evidence import Question
from agent.outdated_prep import prepare_outdated_pack
from agent.quarantine_gate import incomplete_current_quarantine
from agent.session import Session
from agent.storage import FactCache
from agent.toolkit import REGISTRY_TOOLS, Toolkit, Toolkits
from agent.tools import Grants
from agent.tools.targets import ClearedPinTarget

MOMENT = datetime(2026, 7, 26, tzinfo=UTC)
CAPABILITY = "capabilities/deps-outdated"
ECOSYSTEM = "ecosystems/cargo"


def _session(root: Path) -> Session:
    return Session(
        repository=root,
        grants=Grants(binaries=frozenset(), hosts=frozenset()),
        cache=FactCache(root / "cache", writable=False),
        scratch_root=root / "scratch",
    )


def _task() -> PlannedTask:
    return PlannedTask(
        id="deps-outdated@cargo",
        capability=CAPABILITY,
        role=Role.SWEEPER,
        required=True,
        ecosystem=ECOSYSTEM,
        knowledge=(CAPABILITY,),
    )


def _canned(package: str, *, cleared: bool, target: str | None) -> ClearedPinTarget:
    return ClearedPinTarget(
        ecosystem=ECOSYSTEM,
        kind="",
        package=package,
        current="1.0.0",
        line="1",
        current_resolved="1.0.0",
        current_cleared=cleared,
        target=target,
        pending=(),
    )


def test_prepare_outdated_pack_writes_census_and_short_given(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[dependencies]\nserde = "1.0.0"\ntokio = "1.0.0"\n',
        encoding="utf-8",
    )
    session = _session(tmp_path)
    tools = session.for_task("deps-outdated@cargo")
    answers = {
        "serde": _canned("serde", cleared=True, target=None),
        "tokio": _canned("tokio", cleared=False, target="1.0.1"),
    }

    def fake_cleared(
        _http: object,
        *,
        ecosystem: str,
        package: str,
        current: str,
        days: int,
        now: datetime,
        kind: str = "",
        run_command: object = None,
    ) -> ClearedPinTarget:
        return answers[package]

    with patch("agent.outdated_prep.cleared_pin_target", side_effect=fake_cleared):
        prepared = prepare_outdated_pack(
            root=tmp_path,
            ecosystem=ECOSYSTEM,
            capability=CAPABILITY,
            session=session,
            tools=tools,
            quarantine_days=7,
            now=MOMENT,
            pack_dir=tmp_path / "prep",
        )

    assert prepared.ok
    assert prepared.registry == 2
    assert prepared.uncleared == 1
    document = json.loads(prepared.path.read_text(encoding="utf-8"))
    assert document["summary"]["registry"] == 2
    assert document["summary"]["uncleared"] == 1
    assert {row["package"] for row in document["pins"]} == {"serde", "tokio"}
    assert all("evidence_key" in row and row["evidence_key"] for row in document["pins"])

    given_text = "\n".join(prepared.given)
    assert str(prepared.path) in given_text
    assert "`tokio`" in given_text
    assert "serde = " not in given_text  # short given, not a dump of the pack

    declared = [item for item in session.evidence if item.question == Question.DECLARED_PIN]
    cleared = [item for item in session.evidence if item.question == Question.CURRENT_CLEARED]
    assert {item.subject.package for item in declared} == {"serde", "tokio"}
    assert {item.subject.package for item in cleared} == {"serde", "tokio"}
    assert incomplete_pin_sweep(tmp_path, _task(), tuple(session.evidence)) is None


def test_uncleared_without_finding_fails_quarantine_gate(tmp_path: Path) -> None:
    from agent.evidence import Subject
    from agent.findings import Finding, Kind, Klass, Severity

    (tmp_path / "Cargo.toml").write_text('[dependencies]\nserde = "1.0.0"\n', encoding="utf-8")
    session = _session(tmp_path)
    tools = session.for_task("deps-outdated@cargo")

    with patch(
        "agent.outdated_prep.cleared_pin_target",
        return_value=_canned("serde", cleared=False, target=None),
    ):
        prepare_outdated_pack(
            root=tmp_path,
            ecosystem=ECOSYSTEM,
            capability=CAPABILITY,
            session=session,
            tools=tools,
            quarantine_days=7,
            now=MOMENT,
            pack_dir=tmp_path / "prep",
        )

    records = tuple(session.evidence)
    assert (
        incomplete_current_quarantine(
            records, (), capability=CAPABILITY, ecosystem=ECOSYSTEM
        )
        is not None
    )
    finding = Finding(
        capability=CAPABILITY,
        klass=Klass.ROUTINE,
        severity=Severity.MEDIUM,
        subject=Subject(ecosystem=ECOSYSTEM, package="serde"),
        summary="serde pin state",
        rationale="pin not cleared",
        forbidden_state=True,
        kind=Kind.QUARANTINE,
    )
    assert (
        incomplete_current_quarantine(
            records, (finding,), capability=CAPABILITY, ecosystem=ECOSYSTEM
        )
        is None
    )


def test_hide_registry_tools_after_successful_prep(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nserde = "1.0.0"\n', encoding="utf-8")
    session = _session(tmp_path)
    toolkit = Toolkit(
        session=session,
        task=_task(),
        now=MOMENT,
        quarantine_days=7,
    )
    with patch(
        "agent.outdated_prep.cleared_pin_target",
        return_value=_canned("serde", cleared=True, target=None),
    ):
        prepared = prepare_outdated_pack(
            root=tmp_path,
            ecosystem=ECOSYSTEM,
            capability=CAPABILITY,
            session=session,
            tools=toolkit._tools,
            quarantine_days=7,
            now=MOMENT,
            pack_dir=tmp_path / "prep",
        )
    assert prepared.ok
    toolkit.hide_registry_tools()
    names = {tool.name for tool in toolkit.tools()}
    assert names.isdisjoint(REGISTRY_TOOLS)
    assert "read_file" in names
    assert "compare_versions" in names
    assert "check_quarantine" in names
    assert "record_fact" in names


def test_failed_census_leaves_registry_tools_visible(tmp_path: Path) -> None:
    """Unknown ecosystem → prep fails; sweeper keeps registry tools (degradation)."""
    session = _session(tmp_path)
    toolkit = Toolkits(session=session, now=MOMENT, quarantine_days=7).for_task(_task())
    prepared = prepare_outdated_pack(
        root=tmp_path,
        ecosystem="ecosystems/not-a-real-ecosystem",
        capability=CAPABILITY,
        session=session,
        tools=toolkit._tools,
        quarantine_days=7,
        now=MOMENT,
        pack_dir=tmp_path / "prep",
    )
    assert not prepared.ok
    assert "Outdated prep failed" in prepared.given[0]
    names = {tool.name for tool in toolkit.tools()}
    assert "cleared_pin_target" in names
    assert "list_declared_pins" in names
