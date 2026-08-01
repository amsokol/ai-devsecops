"""Newest quarantine-cleared target for dependency pins.

The model classifies the problem; it must not invent which concrete version wins. This module lists
registry candidates, applies quarantine arithmetic, and returns target / pending / current state.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agent.tools.actions import action_publish_time
from agent.tools.commands import CommandResult, NotPermitted
from agent.tools.dates import quarantine
from agent.tools.network import HostNotPermitted, HttpClient
from agent.tools.versions import Step, compare_versions

GHA = "ecosystems/github-actions"
CARGO = "ecosystems/cargo"
NPM = "ecosystems/npm"
PYTHON_UV = "ecosystems/python-uv"
PYTHON_PIP = "ecosystems/python-pip-compile"
GO = "ecosystems/go-modules"
BAZEL = "ecosystems/bazel"
BSR = "ecosystems/bsr"

KIND_ACTION = "action"
KIND_IMAGE = "image"

_MAJOR = re.compile(r"^v?(?P<major>\d+)$")
_ACTION_CONCRETE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?"
    r"(?:[-.](?P<pre>[0-9A-Za-z.-]+))?$"
)
# Container tags: version numbers (`.` or `_`) plus optional variant suffix (-jdk, -bookworm, …).
_IMAGE_TAG = re.compile(r"^v?(?P<body>\d+(?:[._]\d+)*)(?P<suffix>(?:-[A-Za-z][\w.-]*)*)$")
_FLOATING = frozenset({"main", "master", "latest", "stable", "head", "nightly"})
_PRE_HINT = re.compile(r"(?i)(alpha|beta|rc|dev|pre|preview)")

_MAX_LOOKUPS = 40
_TAG_PAGES = 5

RunCommand = Callable[[list[str]], CommandResult]


@dataclass(frozen=True, slots=True)
class ClearedPinTarget:
    """Arithmetic answer: remediable cleared move, pending young tips, and current tip state."""

    ecosystem: str
    kind: str
    package: str
    current: str
    line: str | None
    current_resolved: str | None
    current_cleared: bool | None
    target: str | None
    pending: tuple[str, ...]
    float_like: bool = False
    """True when `current` is a channel / floating ref (stable, latest, major-only, …)."""

    def as_json(self) -> dict[str, Any]:
        return {
            "ecosystem": self.ecosystem,
            "kind": self.kind,
            "package": self.package,
            "current": self.current,
            "line": self.line,
            "current_resolved": self.current_resolved,
            "current_cleared": self.current_cleared,
            "target": self.target,
            "pending": list(self.pending),
            "float_like": self.float_like,
        }


@dataclass(frozen=True, slots=True)
class _Candidate:
    version: str
    published_at: str | None
    heuristic: bool = False


@dataclass(frozen=True, slots=True)
class _ImageTag:
    """Parsed container tag: numeric version parts and variant suffix."""

    nums: tuple[int, ...]
    suffix: str
    raw: str


def cleared_pin_target(
    http: HttpClient,
    *,
    ecosystem: str,
    package: str,
    current: str,
    days: int,
    now: datetime,
    kind: str = "",
    run_command: RunCommand | None = None,
) -> ClearedPinTarget:
    """Newest cleared concrete target on the pin's line, plus pending uncleared newer tips."""
    ecosystem = ecosystem.strip()
    package = package.strip()
    current = current.strip().removeprefix("refs/tags/")
    kind = kind.strip()
    if not ecosystem or not package or not current:
        raise ValueError("ecosystem, package and current are required")

    if ecosystem == GHA:
        if kind not in {KIND_ACTION, KIND_IMAGE}:
            raise ValueError("github-actions requires kind 'action' or 'image'")
        if kind == KIND_ACTION:
            return _for_action(http, package=package, current=current, days=days, now=now)
        return _for_image(http, package=package, current=current, days=days, now=now)

    if ecosystem == CARGO:
        return _for_cargo(http, package=package, current=current, days=days, now=now)
    if ecosystem == NPM:
        return _for_npm(http, package=package, current=current, days=days, now=now)
    if ecosystem in {PYTHON_UV, PYTHON_PIP}:
        return _for_pypi(
            http, ecosystem=ecosystem, package=package, current=current, days=days, now=now
        )
    if ecosystem == GO:
        return _for_go(http, package=package, current=current, days=days, now=now)
    if ecosystem == BAZEL:
        return _for_bazel(http, package=package, current=current, days=days, now=now)
    if ecosystem == BSR:
        return _for_bsr(
            http,
            package=package,
            current=current,
            days=days,
            now=now,
            run_command=run_command,
        )
    raise ValueError(f"unsupported ecosystem {ecosystem!r}")


# --- shared pick / line -------------------------------------------------------


def _from_candidates(
    *,
    ecosystem: str,
    kind: str,
    package: str,
    current: str,
    candidates: list[_Candidate],
    days: int,
    now: datetime,
    float_like: bool = False,
) -> ClearedPinTarget:
    line = _semver_line(ecosystem, current)
    filtered = [
        item
        for item in candidates
        if _on_line(ecosystem, current, item.version) and not _is_prerelease(item.version)
    ]
    ordered = _sort_versions(ecosystem, [item.version for item in filtered])
    by_name = {item.version: item for item in filtered}
    statuses: dict[str, bool | None] = {}
    for name in ordered[:_MAX_LOOKUPS]:
        item = by_name[name]
        if not item.published_at:
            statuses[name] = None
            continue
        when = _parse_time(item.published_at)
        margin = 1.0 if item.heuristic else 0.0
        statuses[name] = quarantine(when, days=days, now=now, margin_days=margin).cleared
    for name in ordered[_MAX_LOOKUPS:]:
        statuses[name] = None
    return _pick(
        ecosystem=ecosystem,
        kind=kind,
        package=package,
        current=current,
        line=line,
        ordered=ordered,
        statuses=statuses,
        float_like=float_like,
    )


def _pick(
    *,
    ecosystem: str,
    kind: str,
    package: str,
    current: str,
    line: str | None,
    ordered: list[str],
    statuses: dict[str, bool | None],
    float_like: bool,
) -> ClearedPinTarget:
    cleared = [name for name in ordered if statuses.get(name) is True]
    uncleared = [name for name in ordered if statuses.get(name) is False]

    if float_like:
        tip = ordered[0] if ordered else None
        return ClearedPinTarget(
            ecosystem=ecosystem,
            kind=kind,
            package=package,
            current=current,
            line=line,
            current_resolved=tip,
            current_cleared=statuses.get(tip) if tip else None,
            target=cleared[0] if cleared else None,
            pending=tuple(uncleared),
            float_like=True,
        )

    resolved = current
    current_cleared = statuses.get(resolved)

    if current_cleared is True:
        target = next((name for name in cleared if _newer(ecosystem, name, resolved)), None)
        pending = tuple(name for name in uncleared if _newer(ecosystem, name, resolved))
    else:
        target = next((name for name in cleared if name != resolved), None)
        pending = tuple(uncleared)

    if target == resolved:
        target = None

    return ClearedPinTarget(
        ecosystem=ecosystem,
        kind=kind,
        package=package,
        current=current,
        line=line,
        current_resolved=resolved,
        current_cleared=current_cleared,
        target=target,
        pending=pending,
        float_like=False,
    )


def _newer(ecosystem: str, left: str, right: str) -> bool:
    if ecosystem == GHA:
        left_image = _parse_image_tag(left)
        right_image = _parse_image_tag(right)
        if left_image and right_image:
            return _image_key(left) > _image_key(right)
    return compare_versions(ecosystem, left, right).order == 1


def _on_line(ecosystem: str, current: str, candidate: str) -> bool:
    """Routine targets stay on the same major line (not a major jump from current)."""
    comparison = compare_versions(ecosystem, candidate, current)
    if comparison.unordered:
        # Major-only action refs: fall back to parsed major digit.
        return _semver_line(ecosystem, candidate) == _semver_line(ecosystem, current)
    return comparison.step is not Step.MAJOR


def _semver_line(ecosystem: str, ref: str) -> str | None:
    if ecosystem == GHA:
        return _action_line(ref) or _image_line(ref)
    match = re.match(r"^v?(\d+)", ref.strip())
    return match.group(1) if match else None


def _sort_versions(ecosystem: str, names: list[str]) -> list[str]:
    def key(name: str) -> tuple[object, ...]:
        # Descending via negated compare against a sentinel is awkward; pairwise bubble via
        # compare_versions to a zero-pad is enough with tuple from regex.
        if ecosystem in {PYTHON_UV, PYTHON_PIP}:
            parts = re.match(r"^v?(\d+(?:\.\d+)*)", name)
            if not parts:
                return (0,)
            nums = tuple(int(p) for p in parts.group(1).split("."))
            return nums + (0,) * (4 - len(nums))
        parsed = _parse_image_tag(name)
        if parsed and len(parsed.nums) >= 2:
            return (*_image_key(name), name)
        match = _ACTION_CONCRETE.match(name) or re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", name)
        if match:
            groups = match.groups()
            return (*(int(g or 0) for g in groups[:3]), name)
        return (0, 0, 0, name)

    return sorted(names, key=key, reverse=True)


def _is_prerelease(version: str) -> bool:
    # Allow versions like 1.0.0 only — reject 1.0.0-rc1, 1.0.0a1
    if _PRE_HINT.search(version) and re.search(
        r"[-.]?(a|b|rc|alpha|beta|dev|pre|preview)\d*", version, re.I
    ):
        return True
    return bool(re.search(r"\d+(a|b|rc)\d+", version, re.I))


# --- github-actions -----------------------------------------------------------


def _for_action(
    http: HttpClient,
    *,
    package: str,
    current: str,
    days: int,
    now: datetime,
) -> ClearedPinTarget:
    if "/" not in package:
        raise ValueError("action package must be owner/name")
    line = _action_line(current)
    names = _github_tag_names(http, package)
    concrete = [name for name in names if _action_concrete(name) and _action_line(name) == line]
    concrete = _sort_action(concrete)
    statuses = _action_statuses(http, package, concrete, days=days, now=now)
    return _pick(
        ecosystem=GHA,
        kind=KIND_ACTION,
        package=package,
        current=current,
        line=line,
        ordered=concrete,
        statuses=statuses,
        float_like=_action_float_like(current),
    )


def _for_image(
    http: HttpClient,
    *,
    package: str,
    current: str,
    days: int,
    now: datetime,
) -> ClearedPinTarget:
    line = _image_line(current)
    repo = _hub_repository(package)
    name_filter = f"{line}." if line else None
    tagged = _hub_tags(http, repo, name_filter=name_filter)
    concrete = [
        name for name, _ in tagged if _image_concrete(name) and _image_same_line(current, name)
    ]
    times = {name: when for name, when in tagged if name in set(concrete)}
    concrete = _sort_image(concrete)
    statuses = _image_statuses(concrete, times, days=days, now=now)
    return _pick(
        ecosystem=GHA,
        kind=KIND_IMAGE,
        package=package,
        current=current,
        line=line,
        ordered=concrete,
        statuses=statuses,
        float_like=_image_float_like(current),
    )


def _action_float_like(current: str) -> bool:
    if current.lower() in _FLOATING:
        return True
    return bool(_MAJOR.match(current))


def _parse_image_tag(tag: str) -> _ImageTag | None:
    text = tag.strip()
    if not text or text.lower() in _FLOATING:
        return None
    match = _IMAGE_TAG.match(text)
    if not match:
        return None
    nums = tuple(int(part) for part in re.split(r"[._]", match.group("body")))
    if not nums:
        return None
    return _ImageTag(nums=nums, suffix=match.group("suffix") or "", raw=text)


def _image_float_like(current: str) -> bool:
    """Channel / floating tags: latest, 25-jdk, 1.24, 1.24-bookworm — not concrete versions."""
    if current.lower() in _FLOATING:
        return True
    parsed = _parse_image_tag(current)
    if parsed is None:
        return True
    return not _image_concrete(current)


def _action_line(ref: str) -> str | None:
    major = _MAJOR.match(ref)
    if major:
        return major.group("major")
    concrete = _ACTION_CONCRETE.match(ref)
    return concrete.group("major") if concrete else None


def _image_line(ref: str) -> str | None:
    parsed = _parse_image_tag(ref)
    return str(parsed.nums[0]) if parsed else None


def _action_concrete(name: str) -> bool:
    if name.lower() in _FLOATING or _MAJOR.match(name):
        return False
    return _ACTION_CONCRETE.match(name) is not None


def _image_concrete(name: str) -> bool:
    """Concrete when the tag has at least major.minor.patch (`.`/`_` count as separators).

    Channels like `25-jdk`, `1.24`, `1.24-bookworm` stay non-concrete; `25.0.3_9-jdk`,
    `1.24.5`, `1.24.5-bookworm`, `3.20.1` are concrete.
    """
    parsed = _parse_image_tag(name)
    return parsed is not None and len(parsed.nums) >= 3


def _image_same_line(current: str, candidate: str) -> bool:
    """Same major, same variant suffix; channel minor (1.24) locks the minor component."""
    cur = _parse_image_tag(current)
    cand = _parse_image_tag(candidate)
    if cur is None or cand is None:
        return False
    if cur.suffix != cand.suffix:
        return False
    if cur.nums[0] != cand.nums[0]:
        return False
    if _image_float_like(current) and len(cur.nums) >= 2:
        return len(cand.nums) >= 2 and cand.nums[1] == cur.nums[1]
    return True


def _sort_action(names: list[str]) -> list[str]:
    def key(name: str) -> tuple[int, int, int, str]:
        match = _ACTION_CONCRETE.match(name)
        if not match:
            return (0, 0, 0, name)
        return (
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch") or 0),
            name,
        )

    return sorted(names, key=key, reverse=True)


def _sort_image(names: list[str]) -> list[str]:
    return sorted(names, key=_image_key, reverse=True)


def _image_key(name: str) -> tuple[int, ...]:
    parsed = _parse_image_tag(name)
    if not parsed:
        return (0,)
    return parsed.nums


def _action_statuses(
    http: HttpClient,
    package: str,
    ordered: list[str],
    *,
    days: int,
    now: datetime,
) -> dict[str, bool | None]:
    statuses: dict[str, bool | None] = {}
    for name in ordered[:_MAX_LOOKUPS]:
        release = action_publish_time(http, package, name)
        if not release.found or not release.published_at:
            statuses[name] = None
            continue
        when = _parse_time(release.published_at)
        statuses[name] = quarantine(when, days=days, now=now).cleared
    for name in ordered[_MAX_LOOKUPS:]:
        statuses[name] = None
    return statuses


def _image_statuses(
    ordered: list[str],
    times: dict[str, str | None],
    *,
    days: int,
    now: datetime,
) -> dict[str, bool | None]:
    statuses: dict[str, bool | None] = {}
    for name in ordered:
        raw = times.get(name)
        if not raw:
            statuses[name] = None
            continue
        when = _parse_time(raw)
        statuses[name] = quarantine(when, days=days, now=now, margin_days=1.0).cleared
    return statuses


def _github_tag_names(http: HttpClient, package: str) -> list[str]:
    owner, _, repo = package.partition("/")
    names: list[str] = []
    for page in range(1, _TAG_PAGES + 1):
        url = f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=100&page={page}"
        payload = _json_get(http, url)
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(item["name"])
        if len(payload) < 100:
            break
    return names


def _hub_repository(package: str) -> str:
    name = package.strip().removeprefix("docker.io/")
    if "/" not in name:
        return f"library/{name}"
    if name.startswith("library/"):
        return name
    parts = name.split("/")
    if len(parts) == 2 and parts[0] in {"library", "_"}:
        return f"library/{parts[1]}"
    if len(parts) == 2:
        return name
    return name


def _hub_tags(
    http: HttpClient,
    repository: str,
    *,
    name_filter: str | None = None,
) -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []
    query = "page_size=100&ordering=-last_updated"
    if name_filter:
        query += f"&name={name_filter}"
    url = f"https://hub.docker.com/v2/repositories/{repository}/tags?{query}"
    for _ in range(_TAG_PAGES):
        payload = _json_get(http, url)
        if not isinstance(payload, dict):
            break
        results = payload.get("results")
        if not isinstance(results, list):
            break
        for item in results:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            updated = item.get("last_updated")
            found.append((name, updated if isinstance(updated, str) else None))
        next_url = payload.get("next")
        if not isinstance(next_url, str) or not next_url:
            break
        url = next_url
    return found


# --- cargo --------------------------------------------------------------------


def _for_cargo(
    http: HttpClient, *, package: str, current: str, days: int, now: datetime
) -> ClearedPinTarget:
    url = f"https://crates.io/api/v1/crates/{urllib.parse.quote(package)}/versions"
    payload = _json_get(http, url)
    versions = payload.get("versions") if isinstance(payload, dict) else None
    if not isinstance(versions, list):
        raise ValueError(f"{url} did not return versions")
    candidates: list[_Candidate] = []
    for item in versions:
        if not isinstance(item, dict):
            continue
        if item.get("yanked") is True:
            continue
        num = item.get("num")
        created = item.get("created_at")
        if isinstance(num, str):
            candidates.append(
                _Candidate(
                    version=num,
                    published_at=created if isinstance(created, str) else None,
                )
            )
    return _from_candidates(
        ecosystem=CARGO,
        kind="",
        package=package,
        current=_strip_cargo_req(current),
        candidates=candidates,
        days=days,
        now=now,
    )


def _strip_cargo_req(current: str) -> str:
    """Manifest reqs like ^1.0.228 → 1.0.228 for comparison."""
    return re.sub(r"^[\^~>=<\s]+", "", current.strip()).split(",", 1)[0].strip()


# --- npm ----------------------------------------------------------------------


def _for_npm(
    http: HttpClient, *, package: str, current: str, days: int, now: datetime
) -> ClearedPinTarget:
    encoded = urllib.parse.quote(package, safe="@")
    if package.startswith("@"):
        encoded = package.replace("/", "%2F")
    meta = _json_get(http, f"https://registry.npmjs.org/{encoded}")
    if not isinstance(meta, dict):
        raise ValueError("npm registry did not return a package object")
    versions = meta.get("versions")
    raw_times = meta.get("time")
    times: dict[str, object] = raw_times if isinstance(raw_times, dict) else {}
    if not isinstance(versions, dict):
        raise ValueError("npm package has no versions map")
    current_ver = _strip_npm_req(current)
    candidates: list[_Candidate] = []
    for name in versions:
        if not isinstance(name, str) or _is_prerelease(name):
            continue
        stamp = times.get(name)
        published = stamp if isinstance(stamp, str) else None
        candidates.append(_Candidate(version=name, published_at=published))
    # Prefer per-version time for the newest few when package-wide time is missing.
    ordered_names = _sort_versions(NPM, [c.version for c in candidates])
    filled: list[_Candidate] = []
    for name in ordered_names[:_MAX_LOOKUPS]:
        item = next(c for c in candidates if c.version == name)
        if item.published_at:
            filled.append(item)
            continue
        detail = _json_get(http, f"https://registry.npmjs.org/{encoded}/{name}")
        published = None
        if isinstance(detail, dict):
            raw_time = detail.get("time")
            if isinstance(raw_time, dict) and isinstance(raw_time.get(name), str):
                published = raw_time[name]
            elif isinstance(detail.get("publish_time"), (int, float)):
                published = datetime.utcfromtimestamp(detail["publish_time"]).isoformat() + "Z"
        filled.append(_Candidate(version=name, published_at=published))
    filled.extend(c for c in candidates if c.version not in {f.version for f in filled})
    return _from_candidates(
        ecosystem=NPM,
        kind="",
        package=package,
        current=current_ver,
        candidates=filled,
        days=days,
        now=now,
    )


def _strip_npm_req(current: str) -> str:
    return re.sub(r"^[\^~>=<\s]+", "", current.strip()).split(" ", 1)[0].strip()


# --- pypi ---------------------------------------------------------------------


def _for_pypi(
    http: HttpClient,
    *,
    ecosystem: str,
    package: str,
    current: str,
    days: int,
    now: datetime,
) -> ClearedPinTarget:
    name = package.strip()
    current_ver = _strip_pep440_req(current)
    names = _pypi_version_names(http, name)
    names = [v for v in names if isinstance(v, str) and not _is_prerelease(v)]
    names = [v for v in _sort_versions(ecosystem, names) if _on_line(ecosystem, current_ver, v)]
    if current_ver and current_ver not in names and not _is_prerelease(current_ver):
        # Listing fell back to a short window (RSS): always keep the pin in use on the board.
        merged = [*names, current_ver]
        names = [
            ver
            for ver in _sort_versions(ecosystem, merged)
            if _on_line(ecosystem, current_ver, ver)
        ]
    timed: list[_Candidate] = []
    for ver in names[:_MAX_LOOKUPS]:
        timed.append(
            _Candidate(version=ver, published_at=_pypi_version_published(http, name, ver))
        )
    for ver in names[_MAX_LOOKUPS:]:
        timed.append(_Candidate(version=ver, published_at=None))
    return _from_candidates(
        ecosystem=ecosystem,
        kind="",
        package=package,
        current=current_ver,
        candidates=timed,
        days=days,
        now=now,
    )


def _strip_pep440_req(current: str) -> str:
    """Bare version from a pin string: `connectrpc==0.11.1`, `==0.11.1`, `^1.2`, or `0.11.1`."""
    text = current.strip()
    if "==" in text:
        text = text.rsplit("==", 1)[-1].strip()
    return re.sub(r"^[\^~>=<\s!]+", "", text).split(",", 1)[0].strip()


def _pypi_version_names(http: HttpClient, name: str) -> list[str]:
    """Release names for a project.

    The full `/pypi/<name>/json` payload embeds every file for every release and can exceed the
    HTTP body limit (ruff is multi‑MB). When that response is truncated or unusable, fall back to
    the project releases RSS — recent enough for tip/pending, while the pin in use is dated via
    the per-version JSON endpoint.
    """
    url = f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json"
    try:
        response = http.get(url)
    except urllib.error.HTTPError as error:
        raise ValueError(f"{url}: HTTP {error.code}") from error
    if not response.truncated:
        try:
            meta = json.loads(response.body)
        except ValueError:
            meta = None
        if isinstance(meta, dict):
            releases = meta.get("releases")
            if isinstance(releases, dict):
                return [ver for ver in releases if isinstance(ver, str)]
    return _pypi_rss_versions(http, name)


def _pypi_rss_versions(http: HttpClient, name: str) -> list[str]:
    url = f"https://pypi.org/rss/project/{urllib.parse.quote(name)}/releases.xml"
    try:
        response = http.get(url)
    except urllib.error.HTTPError as error:
        raise ValueError(f"{url}: HTTP {error.code}") from error
    titles = re.findall(r"<title>([^<]+)</title>", response.body)
    # First <title> is the channel title ("PyPI recent updates for …").
    versions = [title.strip() for title in titles[1:] if title.strip()]
    if not versions:
        raise ValueError(f"{url} named no releases")
    return versions


def _pypi_version_published(http: HttpClient, name: str, ver: str) -> str | None:
    detail = _json_get(
        http, f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(ver)}/json"
    )
    if not isinstance(detail, dict):
        return None
    urls = detail.get("urls") if isinstance(detail.get("urls"), list) else []
    published = None
    if urls and isinstance(urls[0], dict):
        published = urls[0].get("upload_time_iso_8601") or urls[0].get("upload_time")
    info = detail.get("info")
    if not published and isinstance(info, dict):
        published = info.get("upload_time_iso_8601") or info.get("upload_time")
    return published if isinstance(published, str) else None


# --- go -----------------------------------------------------------------------


def _for_go(
    http: HttpClient, *, package: str, current: str, days: int, now: datetime
) -> ClearedPinTarget:
    module = package.strip()
    list_url = f"https://proxy.golang.org/{_go_path(module)}/@v/list"
    try:
        response = http.get(list_url)
        names = [
            line.strip()
            for line in response.body.splitlines()
            if line.strip() and not _is_prerelease(line.strip())
        ]
    except urllib.error.HTTPError as error:
        raise ValueError(f"{list_url}: HTTP {error.code}") from error
    current_ver = current.strip()
    names = [v for v in _sort_versions(GO, names) if _on_line(GO, current_ver, v)]
    candidates: list[_Candidate] = []
    for ver in names[:_MAX_LOOKUPS]:
        info_url = f"https://proxy.golang.org/{_go_path(module)}/@v/{ver}.info"
        try:
            info = _json_get(http, info_url)
        except ValueError:
            candidates.append(_Candidate(version=ver, published_at=None))
            continue
        published = info.get("Time") if isinstance(info, dict) else None
        candidates.append(
            _Candidate(version=ver, published_at=published if isinstance(published, str) else None)
        )
    for ver in names[_MAX_LOOKUPS:]:
        candidates.append(_Candidate(version=ver, published_at=None))
    return _from_candidates(
        ecosystem=GO,
        kind="",
        package=package,
        current=current_ver,
        candidates=candidates,
        days=days,
        now=now,
    )


def _go_path(module: str) -> str:
    """Encode a module path the way the Go module proxy expects."""
    return urllib.parse.quote(module, safe="/")


# --- bazel --------------------------------------------------------------------


def _for_bazel(
    http: HttpClient, *, package: str, current: str, days: int, now: datetime
) -> ClearedPinTarget:
    """BCR versions with publish times: BCR first, upstream GitHub Release as fallback.

    BCR does not put timestamps in metadata.json. The date the UI shows is when the version
    landed in bazel-central-registry — recovered from the commits API on that module's
    `source.json`. Upstream Releases are a fallback when BCR history is missing. Repository
    refs in metadata are often `github:owner/repo`, not https URLs.
    """
    name = package.strip()
    url = (
        "https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/"
        f"main/modules/{urllib.parse.quote(name)}/metadata.json"
    )
    meta = _json_get(http, url)
    if not isinstance(meta, dict):
        raise ValueError("BCR metadata missing")
    versions = meta.get("versions")
    yanked_raw = meta.get("yanked_versions")
    yanked: dict[str, object] = yanked_raw if isinstance(yanked_raw, dict) else {}
    if not isinstance(versions, list):
        raise ValueError("BCR metadata has no versions")
    repo = meta.get("repository")
    github = None
    if isinstance(repo, list) and repo:
        github = str(repo[0])
    elif isinstance(repo, str):
        github = repo
    owner_repo = _github_owner_repo(github) if github else None
    current_ver = current.strip()
    names = [
        v for v in versions if isinstance(v, str) and v not in yanked and not _is_prerelease(v)
    ]
    names = [v for v in _sort_versions(BAZEL, names) if _on_line(BAZEL, current_ver, v)]
    # Always date the pin in use, even when it falls outside the tip window we crawl for Moves to.
    lookup = list(names[:_MAX_LOOKUPS])
    if current_ver in names and current_ver not in lookup:
        lookup.append(current_ver)
    dated: dict[str, _Candidate] = {}
    for ver in lookup:
        published, heuristic = _bazel_publish_time(http, module=name, version=ver, owner_repo=owner_repo)
        dated[ver] = _Candidate(version=ver, published_at=published, heuristic=heuristic)
    candidates: list[_Candidate] = []
    for ver in names:
        if ver in dated:
            candidates.append(dated[ver])
        else:
            candidates.append(_Candidate(version=ver, published_at=None, heuristic=True))
    return _from_candidates(
        ecosystem=BAZEL,
        kind="",
        package=package,
        current=current_ver,
        candidates=candidates,
        days=days,
        now=now,
    )


def _bazel_publish_time(
    http: HttpClient, *, module: str, version: str, owner_repo: str | None
) -> tuple[str | None, bool]:
    """Return (published_at, heuristic). BCR commit date first; GitHub Release second."""
    bcr = _bcr_publish_time(http, module, version)
    if bcr:
        return bcr, False
    if owner_repo:
        release = action_publish_time(http, owner_repo, version)
        if not release.found and not version.startswith("v"):
            release = action_publish_time(http, owner_repo, f"v{version}")
        if release.found and release.published_at:
            return release.published_at, True
    return None, True


def _bcr_publish_time(http: HttpClient, module: str, version: str) -> str | None:
    """When `modules/<module>/<version>/source.json` first appeared on BCR's default branch."""
    path = f"modules/{module}/{version}/source.json"
    return _github_path_oldest_commit(http, repo="bazelbuild/bazel-central-registry", path=path)


def _github_owner_repo(url: str) -> str | None:
    """Normalize BCR/GitHub repository refs to `owner/name`.

    BCR metadata commonly uses `github:owner/name` (not an https URL).
    """
    text = url.strip().removesuffix(".git")
    if text.startswith("github:"):
        text = text.removeprefix("github:")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if text.startswith(prefix):
            rest = text[len(prefix) :].strip("/")
            parts = rest.split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return None
    if text.count("/") == 1:
        return text
    return None


# --- bsr ----------------------------------------------------------------------


def _for_bsr(
    http: HttpClient,
    *,
    package: str,
    current: str,
    days: int,
    now: datetime,
    run_command: RunCommand | None,
) -> ClearedPinTarget:
    """Modules and remote plugins share one tool surface.

    Prefer `buf registry module|plugin label list` (modules expose `create_time`). Protoc plugins
    often return exit 0 with an empty label list while the Buf-managed catalog still knows the
    version — that catalog is `bufbuild/plugins` on GitHub (`buf.plugin.yaml` + commit date, then
    `source_url` → GitHub Release). Guessing `owner/name` from the BSR path alone is last resort:
    `buf.build/connectrpc/rust` is not GitHub `connectrpc/rust`.
    """
    empty = ClearedPinTarget(
        ecosystem=BSR,
        kind="",
        package=package,
        current=current,
        line=_semver_line(BSR, current),
        current_resolved=current,
        current_cleared=None,
        target=None,
        pending=(),
    )
    module = _bsr_module_ref(package)
    labels: list[tuple[str, str | None]] = []
    if run_command is not None:
        try:
            labels = _buf_labels(run_command, module)
        except NotPermitted:
            labels = []

    prefer_v = current.strip().startswith("v")
    current_ver = current.strip().removeprefix("v")
    candidates: list[_Candidate] = []
    if labels:
        for name, when in labels:
            ver = name.removeprefix("v") if name.startswith("v") else name
            if _is_prerelease(ver):
                continue
            candidates.append(_Candidate(version=ver, published_at=when, heuristic=when is None))
    if not candidates:
        try:
            candidates = _bsr_candidates_from_plugins_catalog(http, module, current=current_ver)
        except (ValueError, urllib.error.HTTPError, NotPermitted, HostNotPermitted):
            candidates = []
    if not candidates:
        owner_repo = _bsr_github_repo(module)
        if owner_repo is None:
            return empty
        try:
            candidates = _bsr_candidates_from_github(http, owner_repo)
        except (ValueError, urllib.error.HTTPError, NotPermitted, HostNotPermitted):
            return empty

    if not candidates:
        return empty
    answer = _from_candidates(
        ecosystem=BSR,
        kind="",
        package=package,
        current=current_ver,
        candidates=candidates,
        days=days,
        now=now,
    )
    return _bsr_with_pin_style(answer, prefer_v=prefer_v)


def _bsr_module_ref(package: str) -> str:
    module = package.strip().removeprefix("https://").removeprefix("http://")
    module = module.removeprefix("buf.build/")
    if not module.startswith("buf.build/"):
        module = f"buf.build/{module}" if module else module
    return module


def _bsr_github_repo(module: str) -> str | None:
    """Map `buf.build/owner/name` to GitHub `owner/name` (last-resort heuristic only)."""
    text = module.removeprefix("buf.build/").strip("/")
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _bsr_owner_plugin(module: str) -> tuple[str, str] | None:
    text = module.removeprefix("buf.build/").strip("/")
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _bsr_candidates_from_plugins_catalog(
    http: HttpClient, module: str, *, current: str
) -> list[_Candidate]:
    """Versions from `bufbuild/plugins`; publish time = catalog commit, else `source_url` Release."""
    owner_plugin = _bsr_owner_plugin(module)
    if owner_plugin is None:
        return []
    owner, plugin = owner_plugin
    base = f"plugins/{owner}/{plugin}"
    listing = _json_get(
        http, f"https://api.github.com/repos/bufbuild/plugins/contents/{base}?ref=main"
    )
    if not isinstance(listing, list):
        return []
    versions: list[str] = []
    for entry in listing:
        if not isinstance(entry, dict) or entry.get("type") != "dir":
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        ver = name.strip().removeprefix("v")
        if not ver or _is_prerelease(ver):
            continue
        versions.append(ver)
    if not versions:
        return []
    names = [v for v in _sort_versions(BSR, versions) if _on_line(BSR, current, v)]
    lookup = list(names[:_MAX_LOOKUPS])
    if current in names and current not in lookup:
        lookup.append(current)
    dated: dict[str, _Candidate] = {}
    source_urls: dict[str, str] = {}
    for ver in lookup:
        folder = f"v{ver}"
        published, heuristic = _bsr_plugin_publish_time(
            http, path=f"{base}/{folder}/buf.plugin.yaml", version=ver, source_urls=source_urls
        )
        dated[ver] = _Candidate(version=ver, published_at=published, heuristic=heuristic)
    candidates: list[_Candidate] = []
    for ver in names:
        if ver in dated:
            candidates.append(dated[ver])
        else:
            candidates.append(_Candidate(version=ver, published_at=None, heuristic=True))
    return candidates


def _bsr_plugin_publish_time(
    http: HttpClient,
    *,
    path: str,
    version: str,
    source_urls: dict[str, str],
) -> tuple[str | None, bool]:
    """Return (published_at, heuristic). Catalog commit first; source_url Release second."""
    catalog = _github_path_oldest_commit(http, repo="bufbuild/plugins", path=path)
    if catalog:
        return catalog, False
    source = source_urls.get(version) or _bsr_plugin_source_url(http, path)
    if source:
        source_urls[version] = source
        owner_repo = _github_owner_repo(source)
        if owner_repo:
            release = action_publish_time(http, owner_repo, version)
            if not release.found and not version.startswith("v"):
                release = action_publish_time(http, owner_repo, f"v{version}")
            if release.found and release.published_at:
                return release.published_at, True
    return None, True


def _bsr_plugin_source_url(http: HttpClient, path: str) -> str | None:
    url = f"https://raw.githubusercontent.com/bufbuild/plugins/main/{path}"
    try:
        response = http.get(url)
    except urllib.error.HTTPError:
        return None
    match = re.search(r"(?m)^source_url:\s*(\S+)\s*$", response.body)
    if not match:
        return None
    return match.group(1).strip().strip("\"'")


def _github_path_oldest_commit(http: HttpClient, *, repo: str, path: str) -> str | None:
    """Oldest commit on the first page for `path` (add-to-catalog date for rarely-touched files)."""
    url = (
        f"https://api.github.com/repos/{repo}/commits"
        f"?path={urllib.parse.quote(path, safe='')}&per_page=100"
    )
    try:
        response = http.get(url)
    except urllib.error.HTTPError:
        return None
    try:
        payload = json.loads(response.body)
    except ValueError:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    entry = payload[-1] if isinstance(payload[-1], dict) else None
    if entry is None:
        return None
    commit = entry.get("commit")
    if not isinstance(commit, dict):
        return None
    for key in ("committer", "author"):
        who = commit.get(key)
        if isinstance(who, dict):
            when = who.get("date")
            if isinstance(when, str) and when.strip():
                return when.strip()
    return None


def _bsr_candidates_from_github(http: HttpClient, owner_repo: str) -> list[_Candidate]:
    url = f"https://api.github.com/repos/{owner_repo}/releases?per_page=40"
    payload = _json_get(http, url)
    if not isinstance(payload, list):
        raise ValueError(f"{url} did not return a release list")
    found: list[_Candidate] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("draft") or item.get("prerelease"):
            continue
        tag = item.get("tag_name")
        if not isinstance(tag, str) or not tag.strip():
            continue
        ver = tag.strip().removeprefix("v")
        if _is_prerelease(ver):
            continue
        published = item.get("published_at") or item.get("created_at")
        found.append(
            _Candidate(
                version=ver,
                published_at=published if isinstance(published, str) else None,
                heuristic=False,
            )
        )
    return found


def _buf_labels(run_command: RunCommand, module: str) -> list[tuple[str, str | None]]:
    """List labels for a BSR module or, if that fails or is empty, for a remote plugin."""
    for entity in ("module", "plugin"):
        result = run_command(
            [
                "buf",
                "registry",
                entity,
                "label",
                "list",
                module,
                "--format",
                "json",
                "--page-size",
                "50",
            ]
        )
        if result.exit_code != 0:
            continue
        labels = _parse_buf_labels(result.stdout)
        if labels:
            return labels
    return []


def _bsr_with_pin_style(answer: ClearedPinTarget, *, prefer_v: bool) -> ClearedPinTarget:
    if not prefer_v:
        return answer

    def style(value: str | None) -> str | None:
        if value is None:
            return None
        return value if value.startswith("v") else f"v{value}"

    return ClearedPinTarget(
        ecosystem=answer.ecosystem,
        kind=answer.kind,
        package=answer.package,
        current=style(answer.current) or answer.current,
        line=answer.line,
        current_resolved=style(answer.current_resolved),
        current_cleared=answer.current_cleared,
        target=style(answer.target),
        pending=tuple(style(item) or item for item in answer.pending),
    )


def _parse_buf_labels(stdout: str) -> list[tuple[str, str | None]]:
    text = stdout.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except ValueError:
        return []
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        labels = (
            payload.get("labels")
            or payload.get("moduleLabels")
            or payload.get("pluginLabels")
            or payload.get("results")
        )
        rows = labels if isinstance(labels, list) else []
    else:
        rows = []
    found: list[tuple[str, str | None]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("label") or item.get("id")
        if not isinstance(name, str):
            continue
        when = (
            item.get("createTime")
            or item.get("create_time")
            or item.get("updated")
            or item.get("commitTime")
        )
        found.append((name, when if isinstance(when, str) else None))
    return found


# --- http helpers -------------------------------------------------------------


def _json_get(http: HttpClient, url: str) -> Any:
    try:
        response = http.get(url)
    except urllib.error.HTTPError as error:
        raise ValueError(f"{url}: HTTP {error.code}") from error
    if response.truncated:
        raise ValueError(f"{url} response was truncated")
    try:
        return json.loads(response.body)
    except ValueError as error:
        raise ValueError(f"{url} did not return JSON") from error


def _parse_time(raw: str) -> datetime:
    text = raw.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(text)
