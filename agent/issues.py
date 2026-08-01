"""Tracking findings as issues on the default branch, one issue per finding, across runs.

A maintenance run has no conversation to write in: there is no change request whose diff a reviewer
is reading, so a finding that is not tracked somewhere is a finding nobody will see. Issues are that
somewhere, and they are the part of the agent a team lives with week after week — which makes
restraint the whole design:

*One issue per finding, found again by its key.* Not by title, which is prose and gets edited, and
not by the label, which anybody can apply. A second issue for one problem is how a tracker becomes a
place people stop looking. A finding that returns after a complete close reopens that closed issue
rather than starting a fresh ticket — history and unlock stamps stay on one conversation.

*A closure states its evidence.* An issue is closed when the check that owns the finding reached a
complete answer without it, twice in a row. Complete rules out the scanner outage that would read as
a week of imaginary fixes; twice is because nobody reopens a closed issue to check, while a review
thread — which the next push reopens in front of a reader — settles on the first. See
`agent/absence.py`.

*Silence when nothing is proved.* A finding whose owning check failed leaves its issue exactly as it
was: no comment, no label change, nothing. "Still present" would be as unfounded as a closure, and a
weekly reminder that nothing is known is what teaches people to mute the agent.

The open set is read once, before anything is written. That order is not a matter of style: GitHub's
label listing is a secondary index, and it took five seconds to admit a new issue when this path was
first driven against a real repository. Reading it up front makes a run's own writes irrelevant to
what it sees, and "one run at a time" keeps two runs from racing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent.absence import Absences
from agent.bundles import group_key, legacy_key, member_subjects
from agent.escalate import Escalation
from agent.findings import (
    Action,
    Finding,
    Kind,
    Klass,
    Severity,
    code_fingerprint,
    code_fingerprint_from_key,
)
from agent.reconcile import Posted
from agent.scm import marker
from agent.scm.port import Issue, NewIssue, Platform, ScmError
from agent.unlock import Approval, held, is_routine_quarantine, read, render, stamped
from agent.verdict import Judged, Verdict

LABEL = "ai agent"
"""One label for everything the agent tracks, so a team can find, query or mute the whole set."""

LEGACY_LABELS = ("agent",)
"""Earlier label name; still read so open issues are not duplicated after a rename."""

VULN_CAPABILITIES = frozenset({"capabilities/deps-vuln", "capabilities/code-vuln"})
"""Findings from these checks take the new-issue ceiling before routine drift."""

RETURNED_NOTE = (
    "This finding is present again on the default branch after a complete check reported it, so "
    "this issue is open once more. History and any unlock stay here; the body has the current "
    "detail."
)

MIGRATED_NOTE = (
    "This pin is tracked under the coupled-bundle issue {reference} (`{key}`). Closing this "
    "member ticket so the bundle has one conversation."
)

ADVISORY_MIGRATED_NOTE = (
    "Advisories on this pin are tracked under {reference} (`{key}`). Closing this per-advisory "
    "ticket so the pin has one conversation."
)


@dataclass(slots=True)
class Tracking:
    """What became of the tracked set: what was opened, brought up to date, closed or left alone."""

    posted: list[Posted] = field(default_factory=list)
    raised: int = 0
    closed: int = 0
    failure: str = ""
    numbers: dict[str, int] = field(default_factory=dict)
    """Issue number per finding key, so a change request can name the issue it answers."""

    def as_json(self) -> dict[str, Any]:
        return {
            "posted": [item.as_json() for item in self.posted],
            "raised": self.raised,
            "closed": self.closed,
            "failure": self.failure,
            "tracked": dict(sorted(self.numbers.items())),
        }


def open_tracked(platform: Platform, *, label: str = LABEL) -> tuple[Issue, ...]:
    """Open issues under the current label and any legacy names, deduped by number."""
    return _labelled(platform.issues, label=label)


def closed_tracked(platform: Platform, *, label: str = LABEL) -> tuple[Issue, ...]:
    """Closed issues under the current label and any legacy names, deduped by number."""
    return _labelled(platform.closed_issues, label=label)


def _labelled(fetch: Callable[..., tuple[Issue, ...]], *, label: str) -> tuple[Issue, ...]:
    names = (label, *LEGACY_LABELS) if label == LABEL else (label,)
    by_number: dict[int, Issue] = {}
    for name in names:
        for item in fetch(label=name):
            by_number.setdefault(item.number, item)
    return tuple(by_number[number] for number in sorted(by_number))


def track_findings(
    platform: Platform,
    *,
    verdict: Verdict,
    absences: Absences,
    head: str,
    limit: int,
    escalations: tuple[Escalation, ...] = (),
    label: str = LABEL,
    known: tuple[Issue, ...] | None = None,
    approvals: dict[str, Approval] | None = None,
    surfaces: dict[str, tuple[tuple[str, ...], ...]] | None = None,
) -> Tracking:
    """Reconcile this run's findings with the issues already open, and record every step.

    A platform failure is recorded rather than raised, for the same reason a review's is: the
    analysis is already paid for, and losing its verdict because an issue could not be edited would
    make the run less reliable than the tracker it writes to.

    `absences` carries what earlier runs saw and is left holding what this one should remember. It
    is asked about every tracked key, the ones that came back included: a streak a reappearance does
    not clear is a streak that eventually closes an issue about a live problem.

    `known` is the open set when the run already read it — a run that plans fixes has to, because
    which holds a person released decides what it may ship. Listing it twice would ask the platform
    the same question either side of the work and let the two answers differ.

    `surfaces` is the overlay's verification map when the caller has one. Absent means the issue
    body does not claim anything about local proof; an empty map means every ecosystem is
    human-only unless unlocked for CI.
    """
    record = Tracking()
    try:
        return _track(
            platform,
            record,
            verdict,
            absences,
            head,
            limit,
            escalations,
            label,
            known,
            approvals or {},
            surfaces,
        )
    except ScmError as error:
        record.failure = str(error)
        return record


def _track(
    platform: Platform,
    record: Tracking,
    verdict: Verdict,
    absences: Absences,
    head: str,
    limit: int,
    escalations: tuple[Escalation, ...],
    label: str,
    known: tuple[Issue, ...] | None,
    approvals: dict[str, Approval],
    surfaces: dict[str, tuple[tuple[str, ...], ...]] | None,
) -> Tracking:
    listed = open_tracked(platform, label=label) if known is None else known
    existing = {item.key: item for item in listed if item.key}
    # Findings and escalations are reconciled by one loop because they are the same kind of thing to
    # a reader: one issue, found again by its key, closed when the check that owns it says so.
    wanted = {
        item.finding.key: (
            _title(item),
            _body(
                item,
                approvals.get(item.finding.key),
                no_surface=_no_surface(item, surfaces),
            ),
        )
        for item in verdict.judged
    }
    wanted |= {item.key: (item.title, item.body) for item in escalations}
    by_finding = {item.finding.key: item.finding for item in verdict.judged}
    _keep_approvals(platform, record, existing, approvals, rewritten=frozenset(wanted))
    # A broken check hides everything it would have found, so the news that it is broken does not
    # queue behind the findings of the checks that still work.
    exempt = {item.key for item in escalations}
    closed_by_key = _closed_by_key(
        platform, label=label, needed=frozenset(wanted) - frozenset(existing)
    )
    # Count the new-issue ceiling by subject (or bundle), not by advisory: nine CVEs on one pin
    # are one conversation's worth of attention, not nine slots against the weekly budget.
    # Vulnerability findings take those slots first so a quiet tracker still surfaces advisories.
    raised_subjects: set[str] = set()
    # Code soft-dedup: when the key moved (slug rephrased) but capability+path+symbol still match
    # exactly one open issue, update that issue instead of raising a duplicate.
    absorbed: set[str] = set()

    for key, (title, body) in sorted(
        wanted.items(),
        key=lambda item: _raise_priority(item[0], by_finding.get(item[0]), exempt),
    ):
        issue = existing.get(key)
        finding = by_finding.get(key)
        if issue is None:
            twin = _code_twin(existing, finding, wanted=frozenset(wanted), absorbed=absorbed)
            if twin is not None:
                old_key, issue = twin
                if issue.body.strip() != body.strip() or issue.title != title:
                    platform.edit_issue(issue, body, title=title)
                    record.posted.append(
                        Posted("updated", key, f"same path+symbol as `{old_key}`; key migrated")
                    )
                else:
                    record.posted.append(
                        Posted("unchanged", key, f"same path+symbol as `{old_key}`")
                    )
                record.numbers[key] = issue.number
                absorbed.add(old_key)
                absences.reported(key, finding)
                continue
            prior = closed_by_key.get(key)
            if prior is not None:
                platform.reopen_issue(prior)
                platform.note(prior, RETURNED_NOTE)
                if prior.body.strip() != body.strip() or prior.title != title:
                    platform.edit_issue(prior, body, title=title)
                record.numbers[key] = prior.number
                record.posted.append(Posted("reopened", key, "the finding is back"))
                absences.reported(key, finding)
                continue
            subject = _ceiling_subject(finding, key)
            if record.raised >= limit and key not in exempt and subject not in raised_subjects:
                # Left for the next run rather than dropped or merged into one issue: a finding
                # squeezed into somebody else's issue is a finding that loses its own key, and one
                # dropped silently is one nobody knows was found. Same subject as an issue already
                # raised this run still opens — the ceiling counts attention units, not advisories.
                record.posted.append(
                    Posted("deferred", key, f"this run's limit of {limit} new issue(s) is reached")
                )
                continue
            opened = platform.raise_issue(NewIssue(key=key, title=title, body=body), label=label)
            record.raised += 1
            raised_subjects.add(subject)
            record.numbers[key] = opened.number
            record.posted.append(Posted("raised", key, opened.reference))
            absences.reported(key, finding)
            continue
        record.numbers[key] = issue.number
        if issue.body.strip() != body.strip() or issue.title != title:
            platform.edit_issue(issue, body, title=title)
            record.posted.append(Posted("updated", key, "the finding changed"))
        else:
            record.posted.append(Posted("unchanged", key))
        absences.reported(key, finding)

    _migrate_member_issues(platform, record, existing, verdict.judged)
    _migrate_advisory_issues(platform, record, existing, verdict.judged)

    for key, issue in sorted(existing.items()):
        if key in wanted or key in absorbed:
            continue
        reason = absences.settled(key)
        if reason is not None:
            record.posted.append(Posted("kept-open", key, reason))
            continue
        platform.note(issue, _closing_note(key, head))
        platform.close_issue(issue)
        record.closed += 1
        record.posted.append(Posted("closed", key))
    return record


def _code_twin(
    existing: dict[str, Issue],
    finding: Finding | None,
    *,
    wanted: frozenset[str],
    absorbed: set[str],
) -> tuple[str, Issue] | None:
    """The sole open code issue sharing capability+path+symbol, when soft-dedup applies."""
    if finding is None:
        return None
    fingerprint = code_fingerprint(finding)
    if fingerprint is None:
        return None
    matches = [
        (key, issue)
        for key, issue in existing.items()
        if key not in wanted
        and key not in absorbed
        and code_fingerprint_from_key(key) == fingerprint
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _ceiling_subject(finding: Finding | None, key: str) -> str:
    if finding is None:
        return key
    return group_key(finding)


def _migrate_member_issues(
    platform: Platform,
    record: Tracking,
    existing: dict[str, Issue],
    judged: tuple[Judged, ...],
) -> None:
    """Close pre-collapse per-member issues once the bundle issue exists.

    Waiting for absence would leave two open tickets for one move across two complete runs.
    """
    for item in judged:
        finding = item.finding
        if not finding.bundle.strip():
            continue
        bundle_issue = existing.get(finding.key)
        if bundle_issue is None:
            bundle_issue = _issue_by_number(existing, record.numbers.get(finding.key))
        if bundle_issue is None:
            # Newly raised this run — synthesise enough to point at it.
            number = record.numbers.get(finding.key)
            if number is None:
                continue
            bundle_issue = Issue(
                number=number,
                key=finding.key,
                title="",
                body="",
            )
        for subject in member_subjects(finding):
            old = legacy_key(finding, subject)
            if old == finding.key:
                continue
            prior = existing.get(old)
            if prior is None:
                continue
            platform.note(
                prior,
                MIGRATED_NOTE.format(reference=f"#{bundle_issue.number}", key=finding.key),
            )
            platform.close_issue(prior)
            record.closed += 1
            record.posted.append(Posted("migrated", old, f"#{bundle_issue.number}"))
            existing.pop(old, None)


def _migrate_advisory_issues(
    platform: Platform,
    record: Tracking,
    existing: dict[str, Issue],
    judged: tuple[Judged, ...],
) -> None:
    """Close pre-collapse per-advisory issues once the pin's vulnerable issue exists.

    Older agents keyed each CVE separately; the pin now has one key ending in `vulnerable`.
    """
    kind_tails = {item.value for item in Kind}
    for item in judged:
        finding = item.finding
        if finding.kind is not Kind.VULNERABLE or finding.bundle.strip():
            continue
        if not finding.subject.ecosystem or not finding.subject.package:
            continue
        pin_issue = existing.get(finding.key)
        if pin_issue is None:
            pin_issue = _issue_by_number(existing, record.numbers.get(finding.key))
        if pin_issue is None:
            number = record.numbers.get(finding.key)
            if number is None:
                continue
            pin_issue = Issue(number=number, key=finding.key, title="", body="")
        prefix = f"{finding.capability}:{finding.subject.ecosystem}:{finding.subject.package}:"
        for old, prior in list(existing.items()):
            if old == finding.key or not old.startswith(prefix):
                continue
            suffix = old[len(prefix) :]
            if suffix in kind_tails:
                continue
            platform.note(
                prior,
                ADVISORY_MIGRATED_NOTE.format(reference=f"#{pin_issue.number}", key=finding.key),
            )
            platform.close_issue(prior)
            record.closed += 1
            record.posted.append(Posted("migrated", old, f"#{pin_issue.number}"))
            existing.pop(old, None)


def _issue_by_number(existing: dict[str, Issue], number: int | None) -> Issue | None:
    if number is None:
        return None
    for issue in existing.values():
        if issue.number == number:
            return issue
    return None


def _closed_by_key(platform: Platform, *, label: str, needed: frozenset[str]) -> dict[str, Issue]:
    """Newest closed agent issue per finding key, when at least one key is missing from open."""
    if not needed:
        return {}
    found: dict[str, Issue] = {}
    for item in closed_tracked(platform, label=label):
        if not item.key or item.key not in needed:
            continue
        prior = found.get(item.key)
        if prior is None or item.number > prior.number:
            found[item.key] = item
    return found


def _keep_approvals(
    platform: Platform,
    record: Tracking,
    existing: dict[str, Issue],
    approvals: dict[str, Approval],
    *,
    rewritten: frozenset[str],
) -> None:
    """Write down an approval on an issue this run is not otherwise rewriting.

    The ordinary path carries a fresh approval into the body along with everything else the finding
    says. This is for the run where the check that owns it did not finish: the issue keeps its old
    body and is left alone, and without this the grant would exist only in that run's record. The
    next run would find no stamp and ask the person again for permission they already gave, which
    the knowledge names as a defect in its own right.
    """
    for key, approval in sorted(approvals.items()):
        issue = existing.get(key)
        if issue is None or key in rewritten or read(issue.body) == approval:
            continue
        platform.edit_issue(issue, stamped(issue.body, approval))
        record.posted.append(Posted("approved", key, approval.sentence))


def _title(judged: Judged) -> str:
    """A title that names severity and kind for a human scanning the issue list.

    Package findings keep a stable subject in the title (package or bundle id) — version and
    advisory stay out, so saved searches keep matching while the body updates. Code findings have
    no package: the title uses a short human phrase for the capability plus a trimmed summary, and
    the path lives only in the body. The finding key (with its slug) is what the agent reads.
    """
    finding = judged.finding
    if finding.bundle.strip():
        what = f"bundle {finding.bundle.strip()}"
    elif (finding.subject.package or "").strip():
        what = (finding.subject.package or "").strip()
    elif (finding.subject.path or "").strip() or finding.capability in _TITLE_CAPABILITY:
        what = _title_summary(finding.summary)
    else:
        what = finding.capability.rsplit("/", 1)[-1].replace("-", " ")
    phrase = _TITLE_KIND.get(finding.kind) if finding.kind is not None else None
    if phrase is None:
        phrase = _TITLE_CAPABILITY.get(
            finding.capability, finding.capability.rsplit("/", 1)[-1].replace("-", " ")
        )
    return f"{_TITLE_SEVERITY[finding.severity]} {phrase} — {what}"


_TITLE_WHAT_MAX = 90
"""Characters for the summary side of a code-finding title; full text stays in the body."""


def _title_summary(summary: str) -> str:
    text = " ".join(summary.split()).strip().rstrip(".")
    if not text:
        return "code finding"
    if len(text) <= _TITLE_WHAT_MAX:
        return text
    cut = text[:_TITLE_WHAT_MAX].rsplit(" ", 1)[0].rstrip(",;:")
    return f"{cut}…" if cut else text[:_TITLE_WHAT_MAX]


_TITLE_SEVERITY = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "⚪",
}

_TITLE_KIND = {
    Kind.FLOATING: "floating dependency",
    Kind.QUARANTINE: "quarantine broken",
    Kind.UNKNOWN_AGE: "release date unknown",
    Kind.OUTDATED: "dependency update",
    Kind.VULNERABLE: "vulnerability",
    Kind.BUNDLE: "coupled bundle",
}

_TITLE_CAPABILITY = {
    "capabilities/code-quality": "code quality",
    "capabilities/code-vuln": "code vulnerability",
}


def _raise_priority(
    key: str, finding: Finding | None, exempt: frozenset[str] | set[str]
) -> tuple[int, str]:
    """Sort key for opening new issues: vulns and escalations before routine drift."""
    if key in exempt:
        return (0, key)
    if finding is not None and (
        finding.klass is Klass.SECURITY
        or finding.kind is Kind.VULNERABLE
        or finding.capability in VULN_CAPABILITIES
    ):
        return (1, key)
    return (2, key)


def _body(
    judged: Judged,
    approval: Approval | None = None,
    *,
    no_surface: bool = False,
) -> str:
    """The finding, its evidence, and what to do about it — then the marker.

    Written to be read on its own, because an issue is found weeks later by somebody who never saw
    the run: what it is, why it matters, what would fix it, and how sure the agent is.
    """
    finding = judged.finding
    lines = [
        f"**{finding.severity.value}** `{finding.klass.value}` — {finding.summary}",
        "",
        finding.rationale,
    ]
    if finding.remediation:
        lines += ["", f"**Remediation.** {finding.remediation}"]
    facts = [
        ("Capability", f"`{finding.capability}`"),
        ("Bundle", f"`{finding.bundle}`" if finding.bundle.strip() else ""),
        ("Subject", _subject(judged)),
        ("Members", _members(finding)),
        ("Moves to", finding.target),
        ("Advisory", ", ".join(finding.advisory_ids)),
        ("Brought in by", finding.via),
        ("Where", _where(judged)),
        ("Evidence", judged.reliability.value),
    ]
    lines += ["", *[f"- {name}: {value}" for name, value in facts if value]]
    if judged.action is Action.COMMENT and judged.capped:
        lines += [
            "",
            "This is reported rather than blocking: the evidence behind it is heuristic, and "
            "policy only lets demonstrated findings block.",
        ]
    lines += _decision(finding, approval, no_surface=no_surface)
    return marker.stamp("\n".join(lines), finding.key)


def _decision(
    finding: Finding, approval: Approval | None, *, no_surface: bool = False
) -> list[str]:
    """The one paragraph a person is here to act on, when the finding waits for them.

    Both halves are written for somebody arriving at this issue cold: what is being asked, and what
    saying yes will cause. An approval, once given, is stated in words and stamped in a comment the
    agent reads on later runs, so the question is asked exactly once.

    Routine quarantine is not a person-hold: the knowledge forbids the human-only footer there, and
    an unlock stamp does not waive the window. A security finding with `needs_unlock` is the
    exception that *does* ask — fixing the advisory outweighs quarantine.
    """
    if is_routine_quarantine(finding):
        if approval is not None:
            return [
                "",
                f"**{approval.sentence}** That stamp does not waive a routine quarantine wait. "
                "This pin stays until the window clears; a later run will act then without needing "
                "this approval.",
                "",
                render(approval),
            ]
        return [
            "",
            "**Waiting for quarantine.** This will not be changed automatically: the version is "
            "still inside the product's quarantine window. The blocker is the clock, not a person. "
            "A comment asking for a pull request will be refused until the window clears (a "
            "security finding may offer an exception; this one does not).",
        ]
    if approval is not None:
        if no_surface:
            return [
                "",
                f"**{approval.sentence}** A run will prepare the change **without local "
                "verification** and open it for review — CI on that pull request is the proof you "
                "asked for; this issue stays open until that is merged.",
                "",
                render(approval),
            ]
        return [
            "",
            f"**{approval.sentence}** A run will prepare the change, verify it and open it for "
            "review; this issue stays open until that is merged.",
            "",
            render(approval),
        ]
    hold = held(finding)
    if finding.klass is Klass.SECURITY and finding.needs_unlock:
        after = (
            "without local verification so CI on that PR can check it"
            if no_surface
            else "verifies it against this product's own commands"
        )
        return [
            "",
            f"**Waiting for a person.** This will not be changed automatically, because {hold}.",
            "",
            "Comment here to unlock a pull request — plain words, no phrase to match. Fixing the "
            f"advisory outweighs quarantine: the next run prepares the change as a security "
            f"exception, {after}, and opens it for review. Until then every run reports it and "
            "leaves the code alone.",
        ]
    if no_surface:
        why = (
            f"because {hold}"
            if hold
            else "because this product has no verification surface that can prove a fix for it"
        )
        return [
            "",
            f"**Waiting for a person.** This will not be changed automatically, {why}.",
            "",
            "Comment here to ask for a pull request — plain words, no phrase to match — and the "
            "next run prepares the change without local verification so CI on that PR can check "
            "it. Until then every run reports it and leaves the code alone.",
        ]
    if not hold:
        return []
    return [
        "",
        f"**Waiting for a person.** This will not be changed automatically, because {hold}.",
        "",
        "Comment here to approve it — plain words, no phrase to match — and the next run prepares "
        "the change, verifies it against this product's own commands and opens it for review. "
        "Until then every run reports it and leaves the code alone.",
    ]


def _no_surface(judged: Judged, surfaces: dict[str, tuple[tuple[str, ...], ...]] | None) -> bool:
    if surfaces is None:
        return False
    ecosystem = judged.finding.subject.ecosystem
    if not ecosystem:
        return not surfaces
    return ecosystem.removeprefix("ecosystems/") not in surfaces


def _subject(judged: Judged) -> str:
    subject = judged.finding.subject
    parts = [subject.ecosystem, subject.package, subject.version]
    return " ".join(f"`{part}`" for part in parts if part)


def _members(finding: Finding) -> str:
    subjects = member_subjects(finding)
    if len(subjects) <= 1 and not finding.bundle.strip():
        return ""
    named: list[str] = []
    for subject in subjects:
        if subject.ecosystem and subject.package:
            named.append(f"`{subject.ecosystem}:{subject.package}`")
        elif subject.package:
            named.append(f"`{subject.package}`")
        elif subject.path:
            named.append(f"`{subject.path}`")
    return ", ".join(named)


def _where(judged: Judged) -> str:
    location = judged.finding.location
    if location is None:
        return ""
    return f"`{location.path}`" + (f" line {location.line}" if location.line else "")


def _closing_note(key: str, head: str) -> str:
    """Why this issue is being closed, stated before it happens and naming what looked.

    A closure with no evidence cannot be told from one made because a scanner broke, and the
    difference matters most to whoever reads the issue a month later.
    """
    capability = key.split(":", 1)[0]
    if ":failure:" in key:
        return (
            f"`{capability}` ran to completion on {head[:12]}, so the failure this issue reports "
            "is over and it is closed. What that check covers is watched again from this run on."
        )
    return (
        f"`{capability}` ran to completion on {head[:12]} and this is no longer among its "
        "findings, so this issue is closed. If it returns, a later run reopens this issue."
    )
