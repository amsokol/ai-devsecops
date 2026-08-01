"""Whether a deps-outdated sweep examined every pin the census found."""

from __future__ import annotations

from pathlib import Path

from agent.coverage import Coverage
from agent.domain import PlannedTask
from agent.evidence import Evidence
from agent.tools.pins import list_declared_pins, packages

CAPABILITY = "capabilities/deps-outdated"
NAMED = 8
COMMITTER = "committer.date"
GITHUB_ACTIONS = "ecosystems/github-actions"


def incomplete_pin_sweep(
    root: Path,
    task: PlannedTask,
    records: tuple[Evidence, ...] | list[Evidence],
) -> str | None:
    """Why this task's result is incomplete, or `None` when the census was covered.

    Every listed ecosystem with a deterministic census fails rather than publishing a partial
    finding list. GitHub Actions also refuses publish-time facts that cite a committer date.
    """
    if task.capability != CAPABILITY or not task.ecosystem:
        return None
    if task.ecosystem == GITHUB_ACTIONS and (reason := _committer_clock(records)):
        return reason
    try:
        census = packages(list_declared_pins(root, task.ecosystem))
    except ValueError:
        return None
    if not census:
        return None
    bucket = f"{CAPABILITY}:{task.ecosystem}"
    examined = Coverage.of(records).examined.get(bucket, frozenset())
    missing = census - examined
    if not missing:
        return None
    named = ", ".join(f"`{name}`" for name in sorted(missing)[:NAMED])
    more = f" (+{len(missing) - NAMED} more)" if len(missing) > NAMED else ""
    return (
        f"list_declared_pins found {len(census)} package(s) for {task.ecosystem} but this run "
        f"only recorded facts for {len(examined)}; not examined: {named}{more}. Call "
        "list_declared_pins and record a fact for every pin — including those that are fine — "
        "before finishing"
    )


def incomplete_action_sweep(
    root: Path,
    task: PlannedTask,
    records: tuple[Evidence, ...] | list[Evidence],
) -> str | None:
    """Compatibility alias for the github-actions incomplete-sweep gate."""
    return incomplete_pin_sweep(root, task, records)


def _committer_clock(records: tuple[Evidence, ...] | list[Evidence]) -> str | None:
    bad: list[str] = []
    for record in records:
        if not record.is_verified:
            continue
        if record.question != "publish-time":
            continue
        source = record.source or ""
        if COMMITTER not in source:
            continue
        package = record.subject.package or "(unknown)"
        bad.append(package)
    if not bad:
        return None
    named = ", ".join(f"`{name}`" for name in sorted(set(bad))[:NAMED])
    return (
        f"publish-time for {named} cites committer.date. For github-actions call "
        "action_publish_time (GitHub Release published_at) and pass that into check_quarantine. "
        "A commit date is earlier than the release and falsely clears the window"
    )
