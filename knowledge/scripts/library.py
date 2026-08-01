#!/usr/bin/env python3
"""Validate the knowledge library and generate its index.

Usage:
    python3 scripts/library.py check      # validate headers, sections, links, index
    python3 scripts/library.py index      # rewrite INDEX.md from document headers
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
INDEX = ROOT / "INDEX.md"
IDENTITY = ROOT / "library.yaml"
CHANGELOG = REPO / "CHANGELOG.md"
PYPROJECT = REPO / "pyproject.toml"

# Top-level documents are prose about the library, not library documents.
STANDALONE = {"CONTRACT.md", "INDEX.md"}

# Templates are artefacts products copy; their id names the future path in the product.
TEMPLATE_DIR = "overlay/templates"

HEADER_FIELDS = {"id", "kind", "summary", "applies_to"}

REQUIRED_SECTIONS = {
    "playbook": [
        "Trigger",
        "Tasks",
        "Evidence needed",
        "Aggregation",
        "Verdict and actions",
        "Degradation",
    ],
    "capability": [
        "What to look for",
        "Evidence needed",
        "Judgement criteria",
        "Severity",
        "Fix policy",
        "False positives",
    ],
    "ecosystem": [
        "Capability profile",
        "Requirements",
        "Detect",
        "Evidence recipes",
        "Update procedure",
        "Cautions",
    ],
    "scm": ["Capabilities", "Procedures", "Permissions"],
    "policy": [],
    "overlay": [],
}

INDEX_ORDER = ["playbook", "capability", "policy", "ecosystem", "scm", "overlay"]

INDEX_PREAMBLE = """# Index

Generated from document headers by `scripts/library.py`. This is the only file an agent reads in
full on every run; bodies are loaded on demand, selected by playbook, by the ecosystems the overlay
enables, and by the files a change touches.

Templates under `overlay/templates/` are artefacts for products to copy and are deliberately absent
from this index.
"""


class Document:
    def __init__(self, path: Path, header: dict[str, str]) -> None:
        self.path = path
        self.id = header.get("id", "")
        self.kind = header.get("kind", "")
        self.summary = header.get("summary", "")
        self.applies_to = header.get("applies_to", "")

    @property
    def applies_to_cell(self) -> str:
        raw = self.applies_to.strip().strip("[]")
        if not raw:
            return "—"
        return ", ".join(f"`{item.strip()}`" for item in raw.split(",") if item.strip())


def parse_header(text: str) -> dict[str, str] | None:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None
    return dict(re.findall(r"^(\w+):\s*(.*)$", match.group(1), re.M))


def library_documents() -> list[Path]:
    paths = []
    for path in sorted(ROOT.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in STANDALONE or rel.startswith(TEMPLATE_DIR) or rel.startswith("fixtures/"):
            continue
        paths.append(path)
    return paths


def load(errors: list[str]) -> list[Document]:
    docs: list[Document] = []
    seen: dict[str, str] = {}
    for path in library_documents():
        rel = path.relative_to(ROOT).as_posix()
        header = parse_header(path.read_text())
        if header is None:
            errors.append(f"{rel}: missing header")
            continue
        unexpected = set(header) - HEADER_FIELDS
        if unexpected:
            errors.append(f"{rel}: unexpected header fields {sorted(unexpected)}")
        doc = Document(path, header)
        if doc.id != rel[:-3]:
            errors.append(f"{rel}: id is {doc.id!r}, expected {rel[:-3]!r}")
        if doc.id in seen:
            errors.append(f"{rel}: duplicate id, also in {seen[doc.id]}")
        seen[doc.id] = rel
        if not doc.summary:
            errors.append(f"{rel}: empty summary")
        if doc.kind not in REQUIRED_SECTIONS:
            errors.append(f"{rel}: unknown kind {doc.kind!r}")
        else:
            body = path.read_text()
            for section in REQUIRED_SECTIONS[doc.kind]:
                if not re.search(rf"^#+\s+{re.escape(section)}\s*$", body, re.M):
                    errors.append(f"{rel}: missing required section {section!r}")
        docs.append(doc)
    return docs


def check_identity(errors: list[str]) -> None:
    if not IDENTITY.is_file():
        errors.append(f"{IDENTITY.name}: missing")
        return
    text = IDENTITY.read_text()
    if not re.search(r"^contract_version:\s*\d+\s*$", text, re.M):
        errors.append(f"{IDENTITY.name}: missing contract_version")
    if re.search(r"^version:\s*", text, re.M):
        errors.append(
            f"{IDENTITY.name}: product version lives in pyproject.toml — remove version here"
        )
    if re.search(r"^min_agent_version:\s*", text, re.M):
        errors.append(f"{IDENTITY.name}: min_agent_version is obsolete in the monorepo")


def check_links(errors: list[str]) -> None:
    for path in sorted(ROOT.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        for _, link in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", path.read_text()):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            if not target.exists():
                errors.append(f"{rel}: broken link {link}")


#: Kinds selected by identifier rather than by link: ecosystems come from the overlay's enabled
#: list, and overlay documents live in the product. Link reachability says nothing about them.
SELECTED_BY_ID = {"ecosystem", "overlay"}


def check_reachable(docs: list[Document], errors: list[str]) -> None:
    """Every document should be reachable from a playbook, directly or transitively."""
    by_id = {doc.id: doc for doc in docs}
    reachable = {doc.id for doc in docs if doc.kind == "playbook"}
    frontier = list(reachable)
    while frontier:
        current = by_id[frontier.pop()]
        text = current.path.read_text()
        for _, link in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = (current.path.parent / link.split("#", 1)[0]).resolve()
            try:
                target_id = target.relative_to(ROOT).as_posix()[:-3]
            except ValueError:
                continue
            if target_id in by_id and target_id not in reachable:
                reachable.add(target_id)
                frontier.append(target_id)
    for doc in docs:
        if doc.kind in SELECTED_BY_ID:
            continue
        if doc.id not in reachable:
            errors.append(f"{doc.id}: not reachable from any playbook")


def render_index(docs: list[Document]) -> str:
    rows = ["| id | kind | summary | applies_to |", "| --- | --- | --- | --- |"]
    for kind in INDEX_ORDER:
        for doc in [d for d in docs if d.kind == kind]:
            rows.append(f"| `{doc.id}` | {doc.kind} | {doc.summary} | {doc.applies_to_cell} |")
    return INDEX_PREAMBLE + "\n" + "\n".join(rows) + "\n"


def product_version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(), re.M)
    if not match:
        raise SystemExit(f"{PYPROJECT}: no version")
    return match.group(1)


def check_changelog(errors: list[str]) -> None:
    """The newest root changelog section must match the monorepo product version."""
    if not CHANGELOG.is_file():
        errors.append(f"{CHANGELOG}: missing")
        return
    headings = re.findall(r"^##\s+(\S+)", CHANGELOG.read_text(), re.M)
    if not headings:
        errors.append(f"{CHANGELOG.name}: no version section")
        return
    expected = product_version()
    if headings[0] != expected:
        errors.append(
            f"{CHANGELOG.name}: the newest section is {headings[0]!r}, but "
            f"pyproject.toml says {expected!r}"
        )


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "check"
    errors: list[str] = []
    docs = load(errors)

    if command == "index":
        INDEX.write_text(render_index(docs))
        print(f"wrote {INDEX.relative_to(ROOT)} with {len(docs)} documents")
        return 0

    if command != "check":
        print(__doc__)
        return 2

    check_identity(errors)
    check_links(errors)
    check_reachable(docs, errors)
    check_changelog(errors)
    if INDEX.read_text() != render_index(docs):
        errors.append("INDEX.md is stale — run: python3 scripts/library.py index")

    if errors:
        print(f"{len(errors)} problem(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"{len(docs)} documents checked, no problems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
