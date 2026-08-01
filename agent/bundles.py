"""Collapse coupled-bundle member findings into one tracked unit before publish.

Parallel ecosystem analysts correctly emit one finding per member pin. Tracking and fix
scheduling must not: a bundle is one problem, one issue, one branch. See DESIGN Found in
operation item 11 and knowledge/policy/bundles.md.
"""

from __future__ import annotations

from agent.evidence import Subject
from agent.findings import Finding, Kind, merge, slug

BUNDLE = "bundle"
"""Second segment of a finding key when the finding is keyed by bundle id rather than pin."""

_KIND_RANK = {
    Kind.VULNERABLE: 5,
    Kind.FLOATING: 4,
    Kind.BUNDLE: 3,
    Kind.QUARANTINE: 2,
    Kind.UNKNOWN_AGE: 2,
    Kind.OUTDATED: 1,
}


def is_bundle_key(key: str) -> bool:
    parts = key.split(":")
    return len(parts) >= 3 and parts[1] == BUNDLE


def member_subjects(finding: Finding) -> tuple[Subject, ...]:
    """Every pin this finding covers — members when collapsed, otherwise the subject alone."""
    if finding.members:
        return finding.members
    return (finding.subject,)


def legacy_key(finding: Finding, subject: Subject) -> str:
    """The per-pin key this subject would have had without a bundle field.

    Used to find and close pre-collapse dual issues so the next maintain does not thrash.
    """
    parts = [finding.capability]
    if subject.ecosystem:
        parts += [subject.ecosystem, subject.package or ""]
        identity = finding.advisory or (
            finding.kind.value if finding.kind else slug(finding.summary)
        )
        parts.append(identity)
    else:
        identity = slug(finding.slug) if finding.slug.strip() else slug(finding.summary)
        parts += [subject.path or "", identity]
        if finding.symbol:
            parts.append(finding.symbol)
    return ":".join(part for part in parts if part)


def group_key(finding: Finding) -> str:
    """What fix jobs and branch names group by: the bundle id when set, otherwise the pin."""
    if finding.bundle.strip():
        return f"{BUNDLE}|{slug(finding.bundle)}"
    return finding.subject.key()


def collapse(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """One tracked finding per bundle id (per capability); unrelated findings pass through.

    Analysts still emit member findings with `bundle: <id>` set. This runs after merge so two
    tasks that reported the same member stay one row, then those rows become one issue.
    """
    plain: list[Finding] = []
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        named = finding.bundle.strip()
        if not named:
            plain.append(finding)
            continue
        grouped.setdefault((finding.capability, slug(named)), []).append(finding)
    collapsed = [_combine(bundle_id=bid, members=items) for (_, bid), items in grouped.items()]
    return merge((*plain, *collapsed))


def _combine(*, bundle_id: str, members: list[Finding]) -> Finding:
    """Strictest judgement over the set, with every member named and cited."""
    if len(members) == 1:
        only = members[0]
        return Finding(
            capability=only.capability,
            klass=only.klass,
            severity=only.severity,
            subject=only.subject,
            summary=only.summary,
            rationale=only.rationale,
            evidence=only.evidence,
            remediation=only.remediation,
            location=only.location,
            advisory=only.advisory,
            advisories=only.advisory_ids,
            symbol=only.symbol,
            slug=only.slug,
            forbidden_state=only.forbidden_state,
            target=only.target,
            needs_unlock=only.needs_unlock,
            kind=only.kind,
            bundle=bundle_id,
            members=(only.subject,),
            via=only.via,
        )

    ranked = sorted(
        members,
        key=lambda item: (
            -item.klass.rank,
            -item.severity.rank,
            -_KIND_RANK.get(item.kind, 0) if item.kind else 0,
            item.key,
        ),
    )
    winner = ranked[0]
    subjects = tuple(
        dict.fromkeys(item.subject for item in sorted(members, key=lambda item: item.subject.key()))
    )
    advisories = tuple(sorted({aid for item in members for aid in item.advisory_ids}))
    kinds = [item.kind for item in members if item.kind is not None]
    kind = max(kinds, key=lambda item: _KIND_RANK.get(item, 0)) if kinds else winner.kind
    evidence = tuple(dict.fromkeys(key for item in members for key in item.evidence))
    named = ", ".join(
        f"{item.subject.ecosystem}:{item.subject.package}"
        if item.subject.ecosystem and item.subject.package
        else (item.subject.package or item.subject.path or item.key)
        for item in sorted(members, key=lambda item: item.subject.key())
    )
    remediations = tuple(dict.fromkeys(item.remediation for item in members if item.remediation))
    targets = tuple(dict.fromkeys(item.target for item in members if item.target))
    return Finding(
        capability=winner.capability,
        klass=max(members, key=lambda item: item.klass.rank).klass,
        severity=max(members, key=lambda item: item.severity.rank).severity,
        subject=subjects[0],
        summary=f"Bundle `{bundle_id}` needs a move ({named}).",
        rationale="\n\n".join(dict.fromkeys(item.rationale for item in ranked if item.rationale)),
        evidence=evidence,
        remediation=" ".join(remediations),
        location=winner.location,
        advisory=advisories[0] if len(advisories) == 1 else ", ".join(advisories),
        advisories=advisories,
        symbol=winner.symbol,
        slug=winner.slug,
        forbidden_state=any(item.forbidden_state for item in members),
        target=targets[0] if len(targets) == 1 else "",
        needs_unlock=any(item.needs_unlock for item in members),
        kind=kind,
        bundle=bundle_id,
        members=subjects,
        via=next((item.via for item in ranked if item.via.strip()), ""),
    )


def subjects_as_json(subjects: tuple[Subject, ...]) -> list[dict[str, str | None]]:
    return [item.as_json() for item in subjects]


def subjects_from_json(raw: object) -> tuple[Subject, ...]:
    if not isinstance(raw, list):
        return ()
    found: list[Subject] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        found.append(
            Subject(
                ecosystem=_optional(item.get("ecosystem")),
                package=_optional(item.get("package")),
                version=_optional(item.get("version")),
                path=_optional(item.get("path")),
            )
        )
    return tuple(found)


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
