"""Deterministic vuln prep: scanner → pack.json + advisories evidence before the LLM judges."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.domain import PlannedTask, Role
from agent.evidence import Question, Subject
from agent.session import Session
from agent.storage import FactCache
from agent.toolkit import SCANNER_TOOLS, Toolkit
from agent.tools import Grants
from agent.tools.commands import CommandResult, NotPermitted
from agent.vuln_prep import prepare_vuln_pack

MOMENT = datetime(2026, 8, 1, tzinfo=UTC)
CAPABILITY = "capabilities/deps-vuln"
ECOSYSTEM = "ecosystems/python-uv"


def _session(root: Path) -> Session:
    return Session(
        repository=root,
        grants=Grants(binaries=frozenset({"uv", "pip-audit"}), hosts=frozenset({"pypi.org"})),
        cache=FactCache(root / "cache", writable=False),
        scratch_root=root / "scratch",
    )


def _task() -> PlannedTask:
    return PlannedTask(
        id="deps-vuln@python-uv",
        capability=CAPABILITY,
        role=Role.VULN,
        required=True,
        ecosystem=ECOSYSTEM,
        knowledge=(CAPABILITY,),
    )


def _result(stdout: str, *, exit_code: int = 0, stderr: str = "") -> CommandResult:
    return CommandResult(
        command=("uv", "run", "pip-audit", "-f", "json"),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )


def _stub_run(monkeypatch: Any, tools: Any, handler: Any) -> None:
    """CommandRunner is frozen; patch the class method used by this instance."""
    monkeypatch.setattr(type(tools.commands), "run", handler)


def test_prepare_vuln_pack_seeds_advisories_and_hides_scanner_tools(
    tmp_path: Path, monkeypatch: Any
) -> None:
    session = _session(tmp_path)
    tools = session.for_task("deps-vuln@python-uv")
    payload = {
        "dependencies": [
            {
                "name": "requests",
                "version": "2.31.0",
                "vulns": [
                    {
                        "id": "GHSA-x",
                        "aliases": ["CVE-2024-1"],
                        "fix_versions": [">=2.32.0"],
                        "description": "demo",
                    }
                ],
            }
        ]
    }
    _stub_run(monkeypatch, tools, lambda self, argv, cwd=None: _result(json.dumps(payload)))

    prepared = prepare_vuln_pack(
        root=tmp_path,
        ecosystem=ECOSYSTEM,
        capability=CAPABILITY,
        session=session,
        tools=tools,
        now=MOMENT,
        pack_dir=tmp_path / "prep",
    )

    assert prepared.ok
    assert prepared.hit_packages == 1
    assert prepared.advisory_count == 1
    document = json.loads(prepared.path.read_text(encoding="utf-8"))
    assert document["hits"][0]["package"] == "requests"
    assert document["hits"][0]["version"] == "2.31.0"
    assert document["hits"][0]["advisories"][0]["id"] == "GHSA-x"
    stored = session.evidence.find(
        Question.ADVISORIES,
        Subject(ecosystem=ECOSYSTEM, package="requests", version="2.31.0"),
    )
    assert stored is not None
    assert stored.value == ["GHSA-x"]
    assert any("Vuln prep pack" in line for line in prepared.given)

    toolkit = Toolkit(
        session=session,
        task=_task(),
        now=MOMENT,
        quarantine_days=7,
    )
    toolkit.hide_scanner_tools()
    names = {tool.name for tool in toolkit.tools()}
    assert SCANNER_TOOLS.isdisjoint(names)


def test_clean_scan_is_successful_prep_with_no_hits(tmp_path: Path, monkeypatch: Any) -> None:
    session = _session(tmp_path)
    tools = session.for_task("deps-vuln@python-uv")
    _stub_run(
        monkeypatch,
        tools,
        lambda self, argv, cwd=None: _result(json.dumps({"dependencies": []})),
    )

    prepared = prepare_vuln_pack(
        root=tmp_path,
        ecosystem=ECOSYSTEM,
        capability=CAPABILITY,
        session=session,
        tools=tools,
        now=MOMENT,
        pack_dir=tmp_path / "prep",
    )

    assert prepared.ok
    assert prepared.hit_packages == 0
    assert prepared.advisory_count == 0
    document = json.loads(prepared.path.read_text(encoding="utf-8"))
    assert document["hits"] == []
    assert any("none (scanner completed clean)" in line for line in prepared.given)


def test_web_ecosystem_degrades(tmp_path: Path) -> None:
    session = _session(tmp_path)
    tools = session.for_task("deps-vuln@github-actions")
    prepared = prepare_vuln_pack(
        root=tmp_path,
        ecosystem="ecosystems/github-actions",
        capability=CAPABILITY,
        session=session,
        tools=tools,
        now=MOMENT,
        pack_dir=tmp_path / "prep",
    )

    assert not prepared.ok
    assert any("web/heuristic" in error for error in prepared.errors)
    toolkit = Toolkit(
        session=session,
        task=PlannedTask(
            id="deps-vuln@github-actions",
            capability=CAPABILITY,
            role=Role.VULN,
            required=True,
            ecosystem="ecosystems/github-actions",
            knowledge=(CAPABILITY,),
        ),
        now=MOMENT,
        quarantine_days=7,
    )
    assert SCANNER_TOOLS.issubset({tool.name for tool in toolkit.tools()})


def test_scanner_not_permitted_degrades(tmp_path: Path, monkeypatch: Any) -> None:
    session = _session(tmp_path)
    tools = session.for_task("deps-vuln@python-uv")

    def refuse(self: Any, argv: tuple[str, ...], cwd: Path | None = None) -> CommandResult:
        raise NotPermitted("uv")

    _stub_run(monkeypatch, tools, refuse)

    prepared = prepare_vuln_pack(
        root=tmp_path,
        ecosystem=ECOSYSTEM,
        capability=CAPABILITY,
        session=session,
        tools=tools,
        now=MOMENT,
        pack_dir=tmp_path / "prep",
    )

    assert not prepared.ok
    assert any("not permitted" in error for error in prepared.errors)


def test_hide_scanner_tools_filters_run_command_and_fetch(tmp_path: Path) -> None:
    toolkit = Toolkit(
        session=_session(tmp_path),
        task=_task(),
        now=MOMENT,
        quarantine_days=7,
    )
    before = {tool.name for tool in toolkit.tools()}
    assert "run_command" in before
    assert "fetch" in before
    toolkit.hide_scanner_tools()
    after = {tool.name for tool in toolkit.tools()}
    assert SCANNER_TOOLS.isdisjoint(after)
    assert "list_declared_pins" in after
