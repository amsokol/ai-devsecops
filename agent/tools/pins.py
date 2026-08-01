"""Deterministic census of declared dependency pins across ecosystems.

The model must not invent which pins exist. Found-in-operation item 1: incomplete enumeration
closed live issues and produced drifting finding sets. GitHub Actions already had
`list_action_pins`; this module extends the same guarantee to every listed ecosystem.

Only registry-backed **direct** pins in product manifests enter the coverage set (`packages`).
Path, git, workspace and file: deps are returned for visibility but omitted from the incomplete-
sweep gate — same spirit as skipping local `uses: ./…` actions. Tooling caches and downloaded
module trees (`.agent/…`, Go `pkg/mod`, …) are never walked: a `buf.yaml` inside a cached module is
not a pin the product can bump, and opening an outdated issue for it is noise.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent.tools.actions import ActionPin
from agent.tools.actions import list_action_pins as list_github_action_pins

SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "target",
        "vendor",
        "__pycache__",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".agent",
        ".cursor",
        ".cargo",
        "site-packages",
        "__pypackages__",
    }
)
"""Directory names that never contain product-owned manifests for this census."""

SKIP_PATH_SEGMENTS = (("pkg", "mod"),)
"""Consecutive path segments that mark a cache (Go module download tree), not a product pin."""


ECOSYSTEMS = frozenset(
    {
        "ecosystems/github-actions",
        "ecosystems/cargo",
        "ecosystems/npm",
        "ecosystems/python-uv",
        "ecosystems/python-pip-compile",
        "ecosystems/go-modules",
        "ecosystems/bazel",
        "ecosystems/bsr",
    }
)

_PEP508_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_GO_REQUIRE = re.compile(r"^(\S+)\s+(\S+)")
_BAZEL_DEP = re.compile(
    r"bazel_dep\s*\(\s*name\s*=\s*\"([^\"]+)\"\s*,\s*version\s*=\s*\"([^\"]+)\"\s*\)"
)
_BAZEL_INCLUDE = re.compile(r"include\(\s*\"//:([^\"]+)\"\s*\)")
_NPM_NON_REGISTRY = re.compile(
    r"^(file:|link:|workspace:|git\+|git:|github:|http://|https://|npm:)", re.I
)


@dataclass(frozen=True, slots=True)
class DeclaredPin:
    """One declared pin found in a manifest the ecosystem owns."""

    package: str
    """Identity for Coverage / findings / `cleared_pin_target`."""
    current: str
    """Requirement or pin as written in the manifest."""
    path: str
    """Repository-relative declaring file."""
    kind: str
    """Section: runtime, dev, build, peer, tool, plugin, module, action, image, …"""
    source: str = "registry"
    """`registry` enters the incomplete-sweep set; path/git/workspace do not."""

    def as_json(self) -> dict[str, str]:
        return {
            "package": self.package,
            "current": self.current,
            "path": self.path,
            "kind": self.kind,
            "source": self.source,
        }


def list_declared_pins(root: Path, ecosystem: str) -> tuple[DeclaredPin, ...]:
    """Every direct pin the ecosystem's manifests declare, ordered and unique by package.

    Unknown ecosystem ids raise `ValueError`. An empty tree is a successful empty census.
    """
    if ecosystem not in ECOSYSTEMS:
        known = ", ".join(sorted(ECOSYSTEMS))
        raise ValueError(f"unknown ecosystem {ecosystem!r}; expected one of: {known}")
    if ecosystem == "ecosystems/github-actions":
        return _from_actions(list_github_action_pins(root))
    handlers = {
        "ecosystems/cargo": _cargo_pins,
        "ecosystems/npm": _npm_pins,
        "ecosystems/python-uv": _python_uv_pins,
        "ecosystems/python-pip-compile": _pip_compile_pins,
        "ecosystems/go-modules": _go_pins,
        "ecosystems/bazel": _bazel_pins,
        "ecosystems/bsr": _bsr_pins,
    }
    return _unique(handlers[ecosystem](root))


def packages(pins: tuple[DeclaredPin, ...] | tuple[ActionPin, ...]) -> frozenset[str]:
    """Coverage set: registry-backed packages only."""
    found: set[str] = set()
    for pin in pins:
        if isinstance(pin, ActionPin):
            found.add(pin.package)
            continue
        if pin.source == "registry":
            found.add(pin.package)
    return frozenset(found)


def normalize_pypi(name: str) -> str:
    """PEP 503 normalization so Jinja2 and jinja2 share one Coverage slot."""
    return re.sub(r"[-_.]+", "-", name).lower()


def normalize_bsr(name: str) -> str:
    """Always `buf.build/owner/name` so Coverage matches `cleared_pin_target` subjects."""
    value = name.strip()
    if value.startswith("https://"):
        value = value.removeprefix("https://")
    if value.startswith("buf.build/"):
        return value.split(":", 1)[0]
    if "/" in value and not value.startswith("buf.build/"):
        return f"buf.build/{value.split(':', 1)[0]}"
    return value.split(":", 1)[0]


def _from_actions(pins: tuple[ActionPin, ...]) -> tuple[DeclaredPin, ...]:
    return tuple(
        DeclaredPin(
            package=pin.package,
            current=pin.reference,
            path=pin.path,
            kind=pin.kind,
            source="registry",
        )
        for pin in pins
    )


def _unique(pins: list[DeclaredPin]) -> tuple[DeclaredPin, ...]:
    found: dict[str, DeclaredPin] = {}
    for pin in pins:
        if pin.source != "registry":
            continue
        found.setdefault(pin.package, pin)
    return tuple(sorted(found.values(), key=lambda item: (item.kind, item.package, item.path)))


def _walk(
    root: Path, *, names: frozenset[str] | None = None, suffix: str | None = None
) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _is_skipped(path):
            continue
        if names is not None and path.name not in names:
            continue
        if suffix is not None and not path.name.endswith(suffix):
            continue
        found.append(path)
    return found


def _is_skipped(path: Path) -> bool:
    """True for tooling caches and other trees that are not product-owned manifests."""
    parts = path.parts
    if any(part in SKIP_DIRS for part in parts):
        return True
    for index in range(len(parts) - 1):
        for segment in SKIP_PATH_SEGMENTS:
            length = len(segment)
            if parts[index : index + length] == segment:
                return True
    return False


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# --- cargo -----------------------------------------------------------------


def _cargo_pins(root: Path) -> list[DeclaredPin]:
    pins: list[DeclaredPin] = []
    for path in _walk(root, names=frozenset({"Cargo.toml"})):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except OSError, tomllib.TOMLDecodeError:
            continue
        relative = _rel(root, path)
        for section, kind in (
            ("dependencies", "runtime"),
            ("dev-dependencies", "dev"),
            ("build-dependencies", "build"),
        ):
            pins += _cargo_table(data.get(section), path=relative, kind=kind)
        workspace = data.get("workspace")
        if isinstance(workspace, dict):
            pins += _cargo_table(workspace.get("dependencies"), path=relative, kind="workspace")
    return pins


def _cargo_table(raw: Any, *, path: str, kind: str) -> list[DeclaredPin]:
    if not isinstance(raw, dict):
        return []
    pins: list[DeclaredPin] = []
    for name, spec in raw.items():
        package = str(name)
        current, source = _cargo_spec(spec)
        if current is None:
            continue
        pins.append(
            DeclaredPin(package=package, current=current, path=path, kind=kind, source=source)
        )
    return pins


def _cargo_spec(spec: Any) -> tuple[str | None, str]:
    if isinstance(spec, str):
        return spec.strip() or None, "registry"
    if not isinstance(spec, dict):
        return None, "registry"
    if "path" in spec:
        return str(spec.get("version") or "path"), "path"
    if "git" in spec:
        return str(spec.get("tag") or spec.get("rev") or spec.get("branch") or "git"), "git"
    version = spec.get("version")
    if version is None:
        return None, "registry"
    return str(version).strip() or None, "registry"


# --- npm -------------------------------------------------------------------


def _npm_pins(root: Path) -> list[DeclaredPin]:
    pins: list[DeclaredPin] = []
    for path in _walk(root, names=frozenset({"package.json"})):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        relative = _rel(root, path)
        self_name = str(data.get("name") or "")
        for section, kind in (
            ("dependencies", "runtime"),
            ("devDependencies", "dev"),
            ("peerDependencies", "peer"),
        ):
            block = data.get(section)
            if not isinstance(block, dict):
                continue
            for name, version in block.items():
                package = str(name)
                if package == self_name:
                    continue
                current = str(version).strip()
                source = "registry"
                if _NPM_NON_REGISTRY.match(current):
                    local = current.startswith(("file:", "link:", "workspace:"))
                    source = "path" if local else "git"
                pins.append(
                    DeclaredPin(
                        package=package,
                        current=current,
                        path=relative,
                        kind=kind,
                        source=source,
                    )
                )
    return pins


# --- python-uv -------------------------------------------------------------


def _python_uv_pins(root: Path) -> list[DeclaredPin]:
    pins: list[DeclaredPin] = []
    for path in _walk(root, names=frozenset({"pyproject.toml"})):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except OSError, tomllib.TOMLDecodeError:
            continue
        relative = _rel(root, path)
        project = data.get("project")
        if isinstance(project, dict):
            pins += _pep508_list(project.get("dependencies"), path=relative, kind="runtime")
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for group, reqs in optional.items():
                    pins += _pep508_list(reqs, path=relative, kind=f"optional:{group}")
        groups = data.get("dependency-groups")
        if isinstance(groups, dict):
            for group, reqs in groups.items():
                pins += _pep508_list(reqs, path=relative, kind=f"group:{group}")
        build = data.get("build-system")
        if isinstance(build, dict):
            pins += _pep508_list(build.get("requires"), path=relative, kind="build-system")
    return pins


def _pep508_list(raw: Any, *, path: str, kind: str) -> list[DeclaredPin]:
    if not isinstance(raw, list):
        return []
    pins: list[DeclaredPin] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        pin = _pep508_pin(item, path=path, kind=kind)
        if pin is not None:
            pins.append(pin)
    return pins


def _pep508_pin(requirement: str, *, path: str, kind: str) -> DeclaredPin | None:
    text = requirement.strip()
    if not text or text.startswith(("#", "-")):
        return None
    if "://" in text or text.startswith((".", "/", "git+", "path:")):
        return None
    match = _PEP508_NAME.match(text)
    if match is None:
        return None
    package = normalize_pypi(match.group(1))
    return DeclaredPin(package=package, current=text, path=path, kind=kind, source="registry")


# --- python-pip-compile ----------------------------------------------------


def _pip_compile_pins(root: Path) -> list[DeclaredPin]:
    pins: list[DeclaredPin] = []
    for path in _walk(root, suffix=".in"):
        if not path.name.startswith("requirements"):
            continue
        pins += _read_requirements_in(root, path, seen=set())
    return pins


def _read_requirements_in(root: Path, path: Path, *, seen: set[Path]) -> list[DeclaredPin]:
    resolved = path.resolve()
    if resolved in seen:
        return []
    seen.add(resolved)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    relative = _rel(root, path)
    pins: list[DeclaredPin] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ")):
            target = line.split(None, 1)[1].strip()
            included = (path.parent / target).resolve()
            if included.is_file():
                pins += _read_requirements_in(root, included, seen=seen)
            continue
        if line.startswith(("-c ", "--constraint ")):
            continue
        if line.startswith(("-e ", "--editable ")):
            continue
        pin = _pep508_pin(line, path=relative, kind="runtime")
        if pin is not None:
            pins.append(pin)
    return pins


# --- go-modules ------------------------------------------------------------


def _go_pins(root: Path) -> list[DeclaredPin]:
    pins: list[DeclaredPin] = []
    for path in _walk(root, names=frozenset({"go.mod"})):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        relative = _rel(root, path)
        pins += _parse_go_mod(text, path=relative)
    return pins


def _parse_go_mod(text: str, *, path: str) -> list[DeclaredPin]:
    """Direct requires plus tool-block modules, versioned from their require lines.

    Go's `tool (` lines name a package path with no version; the pin lives on the module's
    `require` row (often `// indirect`). Treating an empty tool line as floating was a false
    positive (demo2 #74/#75). Tool identity for quarantine/proxy is the **module** path, not the
    `/cmd/…` import path.
    """
    requires: dict[str, str] = {}
    direct: list[DeclaredPin] = []
    tools: list[str] = []
    block: str | None = None
    for raw in text.splitlines():
        code, _, comment = raw.partition("//")
        line = code.strip()
        indirect = "indirect" in comment
        if not line:
            continue
        if line == ")":
            block = None
            continue
        if line.startswith("require ("):
            block = "require"
            continue
        if line.startswith("tool ("):
            block = "tool"
            continue
        if line.startswith("require "):
            parsed = _go_require_line(line.removeprefix("require ").strip(), path=path, kind="runtime")
            if parsed is not None:
                requires[parsed.package] = parsed.current
                if not indirect:
                    direct.append(parsed)
            continue
        if line.startswith("tool ") and not line.startswith("tool ("):
            rest = line.removeprefix("tool ").strip()
            if rest:
                tools.append(rest)
            continue
        if block == "require":
            parsed = _go_require_line(line, path=path, kind="runtime")
            if parsed is not None:
                requires[parsed.package] = parsed.current
                if not indirect:
                    direct.append(parsed)
        elif block == "tool":
            tools.append(line)

    pins = list(direct)
    seen = {pin.package for pin in pins}
    for tool in tools:
        matched = _go_module_for_tool(tool, requires)
        if matched is None:
            # No require row yet — still report the tool path so the census is complete; empty
            # current remains a gap the sweeper must name (not invent a version).
            if tool not in seen:
                pins.append(
                    DeclaredPin(package=tool, current="", path=path, kind="tool", source="registry")
                )
                seen.add(tool)
            continue
        module, version = matched
        if module in seen:
            continue
        pins.append(
            DeclaredPin(package=module, current=version, path=path, kind="tool", source="registry")
        )
        seen.add(module)
    return pins


def _go_module_for_tool(tool: str, requires: dict[str, str]) -> tuple[str, str] | None:
    """Longest require module path that prefixes a tool package path."""
    best: tuple[str, str] | None = None
    for module, version in requires.items():
        if tool == module or tool.startswith(f"{module}/"):
            if best is None or len(module) > len(best[0]):
                best = (module, version)
    return best


def _go_require_line(line: str, *, path: str, kind: str) -> DeclaredPin | None:
    match = _GO_REQUIRE.match(line)
    if match is None:
        return None
    return DeclaredPin(
        package=match.group(1),
        current=match.group(2),
        path=path,
        kind=kind,
        source="registry",
    )


# --- bazel -----------------------------------------------------------------


def _bazel_pins(root: Path) -> list[DeclaredPin]:
    pins: list[DeclaredPin] = []
    roots = [root / "MODULE.bazel", *sorted(root.glob("*.MODULE.bazel"))]
    seen: set[Path] = set()
    queue = [path for path in roots if path.is_file()]
    while queue:
        path = queue.pop(0)
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        relative = _rel(root, path)
        for match in _BAZEL_DEP.finditer(text):
            pins.append(
                DeclaredPin(
                    package=match.group(1),
                    current=match.group(2),
                    path=relative,
                    kind="module",
                    source="registry",
                )
            )
        for match in _BAZEL_INCLUDE.finditer(text):
            included = root / match.group(1)
            if included.is_file():
                queue.append(included)
    return pins


# --- bsr -------------------------------------------------------------------


def _bsr_pins(root: Path) -> list[DeclaredPin]:
    pins: list[DeclaredPin] = []
    for path in _walk(root, names=frozenset({"buf.yaml"})):
        pins += _bsr_yaml(path, root=root, deps=True, plugins=False)
    for path in _walk(root):
        if not path.name.startswith("buf.gen") or path.suffix.lower() not in {
            ".yaml",
            ".yml",
        }:
            continue
        pins += _bsr_yaml(path, root=root, deps=False, plugins=True)
    return pins


def _bsr_yaml(path: Path, *, root: Path, deps: bool, plugins: bool) -> list[DeclaredPin]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError, yaml.YAMLError:
        return []
    if not isinstance(document, dict):
        return []
    relative = _rel(root, path)
    pins: list[DeclaredPin] = []
    if deps:
        raw_deps = document.get("deps") or []
        if isinstance(raw_deps, list):
            for item in raw_deps:
                if not isinstance(item, str):
                    continue
                package, _, current = item.partition(":")
                pins.append(
                    DeclaredPin(
                        package=normalize_bsr(package),
                        current=current or item,
                        path=relative,
                        kind="module",
                        source="registry",
                    )
                )
    if plugins:
        raw_plugins = document.get("plugins") or []
        if isinstance(raw_plugins, list):
            for item in raw_plugins:
                if not isinstance(item, dict):
                    continue
                remote = item.get("remote")
                if not isinstance(remote, str) or not remote.strip():
                    continue
                package, _, current = remote.partition(":")
                pins.append(
                    DeclaredPin(
                        package=normalize_bsr(package),
                        current=current or remote,
                        path=relative,
                        kind="plugin",
                        source="registry",
                    )
                )
    return pins
