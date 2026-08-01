"""Deterministic prep for deps-vuln: run the ecosystem scanner before the LLM judges.

Variant A: the runner owns the advisory crawl (pip-audit / govulncheck / cargo audit / npm audit),
seeds `advisories` evidence, and writes a pack the vuln session reads. Findings stay model output —
including `via` for transitive hits. When the scanner cannot run, tools stay visible (degrade).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.evidence import Evidence, Origin, Question, Subject
from agent.session import Session, TaskTools
from agent.tools.commands import NotPermitted
from agent.tools.pins import normalize_pypi

NAMED = 12
WEB_ECOSYSTEMS = frozenset({"ecosystems/github-actions"})
NONE_ECOSYSTEMS = frozenset({"ecosystems/bazel", "ecosystems/bsr"})


@dataclass(frozen=True, slots=True)
class PreparedVulnPack:
    """What the executor injects into the vuln prompt after a successful scanner run."""

    path: Path
    given: tuple[str, ...]
    ok: bool
    """True when the scanner ran and its output was parsed; scanner tools may then be hidden."""
    hit_packages: int
    advisory_count: int
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Hit:
    package: str
    version: str
    advisories: tuple[dict[str, Any], ...]


def prepare_vuln_pack(
    *,
    root: Path,
    ecosystem: str,
    capability: str,
    session: Session,
    tools: TaskTools,
    now: datetime,
    pack_dir: Path,
) -> PreparedVulnPack:
    """Run the ecosystem advisory scanner, record facts, write pack.json, return prompt given."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_path = pack_dir / "pack.json"

    if ecosystem in NONE_ECOSYSTEMS:
        return _failed(
            pack_path,
            ecosystem,
            f"`{ecosystem}` has no advisory scanner (profile method none). Record a gap; do not "
            "invent CVE ids.",
        )
    if ecosystem in WEB_ECOSYSTEMS:
        return _failed(
            pack_path,
            ecosystem,
            f"`{ecosystem}` advisories are web/heuristic — prep cannot pre-acquire them. Use "
            "`fetch` / reading yourself.",
        )

    try:
        command = _command_for(root, ecosystem)
    except ValueError as error:
        return _failed(pack_path, ecosystem, str(error))

    try:
        result = tools.commands.run(command)
    except NotPermitted as error:
        return _failed(
            pack_path,
            ecosystem,
            f"scanner not permitted ({error}). Use run_command yourself or record a gap.",
        )
    except OSError as error:
        return _failed(pack_path, ecosystem, f"scanner failed to start: {error}")

    (pack_dir / "scanner.stdout").write_text(result.stdout or "", encoding="utf-8")
    (pack_dir / "scanner.stderr").write_text(result.stderr or "", encoding="utf-8")

    if result.timed_out:
        return _failed(pack_path, ecosystem, f"{_fmt(command)} timed out")

    try:
        hits = _parse(ecosystem, result.stdout or "")
    except ValueError as error:
        # Non-zero exit with empty/unparseable stdout often means the binary is missing mid-PATH.
        detail = str(error)
        if result.exit_code not in (0, 1):
            detail = f"{detail}; exit {result.exit_code}; stderr: {(result.stderr or '')[:400]}"
        return _failed(pack_path, ecosystem, detail)

    scanner = command[0] if command[0] != "uv" else "pip-audit"
    rows: list[dict[str, Any]] = []
    advisory_count = 0
    for hit in hits:
        subject = Subject(ecosystem=ecosystem, package=hit.package, version=hit.version)
        ids = [str(item.get("id") or "").strip() for item in hit.advisories if item.get("id")]
        ids = [item for item in ids if item]
        advisory_count += len(ids)
        stored = session.evidence.add(
            Evidence.verified(
                question=Question.ADVISORIES,
                subject=subject,
                value=ids,
                origin=Origin.TOOL,
                source=_fmt(command),
                observed_at=now,
                recipe=f"{capability}@{scanner}",
            )
        )
        rows.append(
            {
                "package": hit.package,
                "version": hit.version,
                "advisories": list(hit.advisories),
                "evidence_key": stored.key,
            }
        )

    document = {
        "ecosystem": ecosystem,
        "capability": capability,
        "scanner": scanner,
        "command": list(command),
        "exit_code": result.exit_code,
        "hits": rows,
        "summary": {
            "hit_packages": len(rows),
            "advisory_count": advisory_count,
            "errors": [],
        },
    }
    pack_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    named = ", ".join(f"`{row['package']}`" for row in rows[:NAMED])
    more = f" (+{len(rows) - NAMED} more)" if len(rows) > NAMED else ""
    hits_line = (
        f"- Advisory hits ({len(rows)} package(s), {advisory_count} id(s)): {named}{more}."
        if rows
        else "- Advisory hits: none (scanner completed clean)."
    )
    given = (
        f"- Vuln prep pack (runner-acquired): `{pack_path}`. "
        "Read it with `read_file` when you need advisory detail. "
        "Do not re-run the ecosystem scanner (`run_command` / `fetch` for the same "
        "crawl) — answers are already in the pack and in evidence.",
        f"- Scanner: `{_fmt(command)}` (exit {result.exit_code}).",
        hits_line,
        "- Emit one finding per advisory (or one supply-chain signal) under `kind: vulnerable`. "
        "Cite each hit's `evidence_key`. When the package is not a direct declared pin, set `via` "
        "to the chain from a direct pin to the subject. Do not invent advisory ids.",
    )
    return PreparedVulnPack(
        path=pack_path,
        given=given,
        ok=True,
        hit_packages=len(rows),
        advisory_count=advisory_count,
        errors=(),
    )


def _failed(pack_path: Path, ecosystem: str, reason: str) -> PreparedVulnPack:
    return PreparedVulnPack(
        path=pack_path,
        given=(f"- Vuln prep failed for `{ecosystem}`: {reason}",),
        ok=False,
        hit_packages=0,
        advisory_count=0,
        errors=(reason,),
    )


def _fmt(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _command_for(root: Path, ecosystem: str) -> tuple[str, ...]:
    if ecosystem == "ecosystems/python-uv":
        return ("uv", "run", "pip-audit", "-f", "json")
    if ecosystem == "ecosystems/python-pip-compile":
        locks = _pip_compile_locks(root)
        if not locks:
            raise ValueError("no requirements*.txt locks found for pip-audit")
        command: list[str] = ["pip-audit", "-f", "json"]
        for lock in locks:
            command += ["-r", lock]
        return tuple(command)
    if ecosystem == "ecosystems/go-modules":
        return ("govulncheck", "-json", "./...")
    if ecosystem == "ecosystems/cargo":
        return ("cargo", "audit", "--json")
    if ecosystem == "ecosystems/npm":
        return _npm_audit_command(root)
    raise ValueError(f"no vuln scanner command for `{ecosystem}`")


def _pip_compile_locks(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.glob("requirements*.txt")
        if path.is_file()
    )


def _npm_audit_command(root: Path) -> tuple[str, ...]:
    if (root / "pnpm-lock.yaml").is_file():
        return ("pnpm", "audit", "--json")
    if (root / "yarn.lock").is_file():
        return ("yarn", "npm", "audit", "--json")
    return ("npm", "audit", "--json")


def _parse(ecosystem: str, stdout: str) -> tuple[_Hit, ...]:
    text = stdout.strip()
    if ecosystem in {"ecosystems/python-uv", "ecosystems/python-pip-compile"}:
        return _parse_pip_audit(text)
    if ecosystem == "ecosystems/go-modules":
        return _parse_govulncheck(text)
    if ecosystem == "ecosystems/cargo":
        return _parse_cargo_audit(text)
    if ecosystem == "ecosystems/npm":
        return _parse_npm_audit(text)
    raise ValueError(f"no parser for `{ecosystem}`")


def _parse_pip_audit(text: str) -> tuple[_Hit, ...]:
    if not text:
        return ()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"pip-audit JSON parse failed: {error}") from error
    deps: list[Any]
    if isinstance(raw, list):
        deps = raw
    elif isinstance(raw, dict) and isinstance(raw.get("dependencies"), list):
        deps = raw["dependencies"]
    else:
        raise ValueError("pip-audit JSON: expected a list or {{dependencies: [...]}}")
    hits: list[_Hit] = []
    for item in deps:
        if not isinstance(item, dict):
            continue
        name = normalize_pypi(str(item.get("name") or ""))
        version = str(item.get("version") or "").strip()
        vulns = item.get("vulns") or item.get("vulnerabilities") or []
        if not name or not isinstance(vulns, list) or not vulns:
            continue
        advisories = tuple(_pip_vuln(entry) for entry in vulns if isinstance(entry, dict))
        advisories = tuple(item for item in advisories if item.get("id"))
        if advisories:
            hits.append(_Hit(package=name, version=version, advisories=advisories))
    return tuple(hits)


def _pip_vuln(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry.get("id") or "").strip(),
        "fix_versions": [
            str(item) for item in (entry.get("fix_versions") or entry.get("fixed_in") or [])
        ],
        "aliases": [str(item) for item in (entry.get("aliases") or [])],
        "description": str(entry.get("description") or entry.get("details") or "").strip(),
    }


def _parse_govulncheck(text: str) -> tuple[_Hit, ...]:
    """govulncheck -json emits NDJSON objects; collect finding messages with OSV ids."""
    if not text.strip():
        return ()
    by_package: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        # Stream format: {"finding": {...}} or top-level finding fields.
        node = event.get("finding") if isinstance(event.get("finding"), dict) else event
        osv = node.get("osv") if isinstance(node, dict) else None
        if isinstance(osv, str) and osv.strip():
            osv_id = osv.strip()
        elif isinstance(osv, dict):
            osv_id = str(osv.get("id") or "").strip()
        else:
            continue
        if not osv_id:
            continue
        trace = node.get("trace") if isinstance(node, dict) else None
        package, version = _govuln_package(trace, node if isinstance(node, dict) else {})
        if not package:
            continue
        key = (package, version)
        by_package.setdefault(key, [])
        if not any(item.get("id") == osv_id for item in by_package[key]):
            by_package[key].append(
                {"id": osv_id, "fix_versions": [], "aliases": [], "description": ""}
            )
    return tuple(
        _Hit(package=package, version=version, advisories=tuple(advisories))
        for (package, version), advisories in sorted(by_package.items())
        if advisories
    )


def _govuln_package(trace: Any, node: dict[str, Any]) -> tuple[str, str]:
    if isinstance(trace, list):
        for frame in reversed(trace):
            if not isinstance(frame, dict):
                continue
            raw_module = frame.get("module")
            module = raw_module if isinstance(raw_module, dict) else frame
            path = str(module.get("path") or module.get("module") or "").strip()
            version = str(module.get("version") or "").strip()
            if path and not path.startswith("stdlib"):
                return path, version
    node_module = node.get("module")
    if isinstance(node_module, dict):
        return (
            str(node_module.get("path") or "").strip(),
            str(node_module.get("version") or "").strip(),
        )
    return "", ""


def _parse_cargo_audit(text: str) -> tuple[_Hit, ...]:
    if not text.strip():
        return ()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"cargo audit JSON parse failed: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("cargo audit JSON: expected an object")
    vulnerabilities = raw.get("vulnerabilities")
    listings: list[Any] = []
    if isinstance(vulnerabilities, dict) and isinstance(vulnerabilities.get("list"), list):
        listings = vulnerabilities["list"]
    elif isinstance(vulnerabilities, list):
        listings = vulnerabilities
    by_package: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in listings:
        if not isinstance(item, dict):
            continue
        advisory_raw = item.get("advisory")
        package_raw = item.get("package")
        advisory = advisory_raw if isinstance(advisory_raw, dict) else {}
        package = package_raw if isinstance(package_raw, dict) else {}
        name = str(package.get("name") or "").strip()
        version = str(package.get("version") or "").strip()
        advisory_id = str(advisory.get("id") or "").strip()
        if not name or not advisory_id:
            continue
        aliases = [str(a) for a in (advisory.get("aliases") or [])]
        description = str(advisory.get("title") or advisory.get("description") or "").strip()
        key = (name, version)
        by_package.setdefault(key, []).append(
            {
                "id": advisory_id,
                "fix_versions": [],
                "aliases": aliases,
                "description": description,
            }
        )
    return tuple(
        _Hit(package=package, version=version, advisories=tuple(advisories))
        for (package, version), advisories in sorted(by_package.items())
    )


def _parse_npm_audit(text: str) -> tuple[_Hit, ...]:
    if not text.strip():
        return ()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"npm audit JSON parse failed: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("npm audit JSON: expected an object")
    by_package: dict[tuple[str, str], list[dict[str, Any]]] = {}
    # npm v6: {"advisories": {id: {...}}}
    advisories = raw.get("advisories")
    if isinstance(advisories, dict):
        for entry in advisories.values():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("module_name") or "").strip()
            findings = entry.get("findings") if isinstance(entry.get("findings"), list) else []
            version = ""
            if findings and isinstance(findings[0], dict):
                version = str(findings[0].get("version") or "").strip()
            advisory_id = str(entry.get("github_advisory_id") or entry.get("id") or "").strip()
            if isinstance(entry.get("id"), int):
                advisory_id = str(entry.get("url") or advisory_id)
            cves = [str(c) for c in (entry.get("cves") or [])]
            if not name or not advisory_id:
                continue
            key = (name, version)
            by_package.setdefault(key, []).append(
                {
                    "id": (
                        advisory_id
                        if not advisory_id.isdigit()
                        else (cves[0] if cves else advisory_id)
                    ),
                    "fix_versions": (
                        [str(entry["patched_versions"])] if entry.get("patched_versions") else []
                    ),
                    "aliases": cves,
                    "description": str(entry.get("title") or "").strip(),
                }
            )
    # npm v7+: {"vulnerabilities": {name: {...}}}
    vulns = raw.get("vulnerabilities")
    if isinstance(vulns, dict):
        for name, entry in vulns.items():
            if not isinstance(entry, dict):
                continue
            package = str(name).strip()
            via_raw = entry.get("via")
            via = via_raw if isinstance(via_raw, list) else []
            version = str(entry.get("version") or "").strip()
            range_ = str(entry.get("range") or "").strip()
            if not version and range_:
                version = range_
            for item in via:
                if isinstance(item, str):
                    continue
                if not isinstance(item, dict):
                    continue
                advisory_id = str(item.get("url") or item.get("source") or item.get("name") or "")
                ghsa = re.search(r"GHSA-[\w-]+", advisory_id)
                cve = re.search(r"CVE-\d{4}-\d+", advisory_id)
                vid = (
                    ghsa.group(0)
                    if ghsa
                    else (cve.group(0) if cve else str(item.get("source") or "").strip())
                )
                if not package or not vid:
                    continue
                key = (package, version)
                by_package.setdefault(key, []).append(
                    {
                        "id": vid,
                        "fix_versions": (
                            [str(entry.get("fixAvailable"))] if entry.get("fixAvailable") else []
                        ),
                        "aliases": [],
                        "description": str(item.get("title") or "").strip(),
                    }
                )
    return tuple(
        _Hit(package=package, version=version, advisories=tuple(advisories))
        for (package, version), advisories in sorted(by_package.items())
        if advisories
    )
