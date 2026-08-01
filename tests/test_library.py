from __future__ import annotations

from pathlib import Path

import pytest
from agent.errors import ConfigError
from agent.library import Library


def test_index_is_read_with_kinds_and_applies_to(library: Library) -> None:
    assert len(library) == 12
    assert library.get("ecosystems/python-uv").applies_to == ("pyproject.toml", "uv.lock")
    assert library.get("playbooks/pr-review").kind == "playbook"


def test_body_strips_the_header(library: Library) -> None:
    body = library.get("policy/verdicts").body()
    assert body.startswith("Classes, severities")
    assert "kind:" not in body


def test_links_are_resolved_to_index_ids(library: Library) -> None:
    assert library.links("playbooks/pr-review") == ("policy/verdicts",)


def test_closure_lists_roots_first_then_what_they_link_to(library: Library) -> None:
    assert library.closure(("playbooks/pr-review", "capabilities/deps-outdated")) == (
        "playbooks/pr-review",
        "capabilities/deps-outdated",
        "policy/verdicts",
        "policy/quarantine",
        "evidence/acquisition",
    )


def test_fact_method_reads_capability_profile(library: Library) -> None:
    assert library.fact_method("ecosystems/python-uv", "advisories") == "tool"
    assert library.fact_method("ecosystems/bazel", "advisories") == "none"
    assert library.fact_method("ecosystems/python-uv", "missing") is None


def test_closure_does_not_pull_in_a_playbook_mentioned_by_another(library: Library) -> None:
    """A playbook is chosen by the trigger. Prose that mentions it is not a dependency."""
    assert library.closure(("playbooks/maintain",)) == ("playbooks/maintain",)


def test_applies_to_matches_files_and_directories(library: Library) -> None:
    actions = library.get("ecosystems/github-actions")
    assert actions.matches_path(".github/workflows/ci.yml")
    assert not actions.matches_path("src/workflows/ci.yml")
    uv = library.get("ecosystems/python-uv")
    assert uv.matches_path("services/api/pyproject.toml")
    assert not uv.matches_path("pyproject.toml.bak")


def test_ecosystems_for_paths_ignores_disabled_ones(library: Library) -> None:
    paths = ("uv.lock", ".github/workflows/ci.yml")
    assert library.ecosystems_for_paths(paths, ("ecosystems/python-uv",)) == (
        "ecosystems/python-uv",
    )


def test_digest_changes_with_content(library_root: Path) -> None:
    first = Library.load(library_root).digest
    (library_root / "policy/verdicts.md").write_text(
        "---\nid: policy/verdicts\nkind: policy\nsummary: s\n---\n\nChanged.\n", encoding="utf-8"
    )
    assert Library.load(library_root).digest != first


def test_digest_ignores_what_never_reaches_a_run(library_root: Path) -> None:
    """Repository scaffolding is not hashed — only identity, index and indexed bodies."""
    first = Library.load(library_root).digest
    (library_root / "README.md").write_text("# Library\n", encoding="utf-8")
    (library_root / "scripts").mkdir()
    (library_root / "scripts/library.py").write_text("print('tooling')\n", encoding="utf-8")
    (library_root / "overlay/templates").mkdir(parents=True)
    (library_root / "overlay/templates/NOTES.md").write_text("# Notes\n", encoding="utf-8")

    assert Library.load(library_root).digest == first


def test_renaming_a_document_is_a_change(library_root: Path) -> None:
    first = Library.load(library_root).digest
    index = library_root / "INDEX.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace("policy/verdicts", "policy/blocking"),
        encoding="utf-8",
    )
    renamed = library_root / "policy/blocking.md"
    original = library_root / "policy/verdicts.md"
    renamed.write_text(
        original.read_text(encoding="utf-8").replace("policy/verdicts", "policy/blocking"),
        encoding="utf-8",
    )
    original.unlink()

    assert Library.load(library_root).digest != first


def test_unsupported_contract_is_a_startup_error(library_root: Path) -> None:
    (library_root / "library.yaml").write_text(
        "schema: 1\ncontract_version: 999\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="contract version 999"):
        Library.load(library_root)


def test_indexed_document_without_a_file_is_a_startup_error(library_root: Path) -> None:
    (library_root / "policy/verdicts.md").unlink()
    with pytest.raises(ConfigError, match="is indexed but"):
        Library.load(library_root)


def test_missing_identity_file_is_named_in_the_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not look like a knowledge library"):
        Library.load(tmp_path)
