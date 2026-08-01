"""Deterministic prep for deps-outdated: census + cleared targets before the LLM judges.

Variant A: the runner acquires every registry pin's current-cleared answer and writes a pack the
sweeper reads; the model writes findings and must not re-crawl registries when those tools are
hidden. Findings are still model output — the runner does not invent issues.
"""

from __future__ import annotations

import json
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.evidence import Evidence, Origin, Question, Subject
from agent.session import Session, TaskTools
from agent.tools.network import HostNotPermitted
from agent.tools.pins import DeclaredPin, list_declared_pins, packages
from agent.tools.targets import ClearedPinTarget, cleared_pin_target

GITHUB_ACTIONS = "ecosystems/github-actions"
NAMED = 12


@dataclass(frozen=True, slots=True)
class PreparedPack:
    """What the executor injects into the sweeper prompt after a successful census."""

    path: Path
    given: tuple[str, ...]
    ok: bool
    """True when the pin list was obtained; registry tools may then be hidden."""
    registry: int
    uncleared: int
    errors: tuple[str, ...]


def prepare_outdated_pack(
    *,
    root: Path,
    ecosystem: str,
    capability: str,
    session: Session,
    tools: TaskTools,
    quarantine_days: int,
    now: datetime,
    pack_dir: Path,
) -> PreparedPack:
    """Census every registry pin, record current-cleared, write pack.json, return prompt given."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    try:
        pins = list_declared_pins(root, ecosystem)
    except ValueError as error:
        return PreparedPack(
            path=pack_dir / "pack.json",
            given=(
                f"- Outdated prep failed for `{ecosystem}`: {error}. Use list_declared_pins and "
                "cleared_pin_target yourself.",
            ),
            ok=False,
            registry=0,
            uncleared=0,
            errors=(str(error),),
        )

    registry_pins = tuple(pin for pin in pins if pin.source == "registry")
    covered = packages(pins)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    uncleared_names: list[str] = []
    with_target = 0

    for pin in registry_pins:
        if pin.package not in covered:
            continue
        row, pin_error = _one_pin(
            pin,
            ecosystem=ecosystem,
            capability=capability,
            session=session,
            tools=tools,
            quarantine_days=quarantine_days,
            now=now,
        )
        rows.append(row)
        if pin_error:
            errors.append(pin_error)
        if row.get("current_cleared") is not True:
            uncleared_names.append(pin.package)
        if row.get("target"):
            with_target += 1

    pack_path = pack_dir / "pack.json"
    document = {
        "ecosystem": ecosystem,
        "capability": capability,
        "pins": rows,
        "summary": {
            "total": len(pins),
            "registry": len(rows),
            "uncleared": len(uncleared_names),
            "with_target": with_target,
            "errors": errors,
        },
    }
    pack_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    named = ", ".join(f"`{name}`" for name in uncleared_names[:NAMED])
    more = f" (+{len(uncleared_names) - NAMED} more)" if len(uncleared_names) > NAMED else ""
    uncleared_line = (
        f"- Uncleared current pins ({len(uncleared_names)}): {named}{more}."
        if uncleared_names
        else "- Uncleared current pins: none."
    )
    given = (
        f"- Outdated prep pack (runner-acquired): `{pack_path}`. Read it with `read_file` when you "
        "need pin detail. Do not call list_declared_pins, cleared_pin_target, fetch, or "
        "action_publish_time for this ecosystem — those answers are already in the pack and in "
        "evidence.",
        f"- Census: {len(rows)} registry pin(s) of {len(pins)} declared; "
        f"{with_target} with a cleared `target`.",
        uncleared_line,
        "- For every pin where `current_cleared` is false, emit `kind: quarantine` with "
        "`forbidden_state: true` (cite `evidence_key`). For every pin where `current_cleared` is "
        "null: if `float_like` is true (channel refs such as `stable` / `latest` / major-only), "
        "emit `kind: floating` with `forbidden_state: true` — there is no dated tip to quarantine; "
        "otherwise emit `kind: unknown_age` with `forbidden_state: true` and say the release date "
        "is unknown (do not call that quarantine). For cleared pins with a non-null `target`, emit "
        "outdated/floating **only when the move can ship now** (bundle + NOTES cross-bundle/"
        "constraint blockers included); if another pin or bundle must move first and cannot in "
        "this change, omit the outdated finding and name the blocker in the report — do not open "
        "a dependency-update issue for a bump that cannot build. Do not list fine pins as "
        "findings.",
    )
    return PreparedPack(
        path=pack_path,
        given=given,
        ok=True,
        registry=len(rows),
        uncleared=len(uncleared_names),
        errors=tuple(errors),
    )


def _one_pin(
    pin: DeclaredPin,
    *,
    ecosystem: str,
    capability: str,
    session: Session,
    tools: TaskTools,
    quarantine_days: int,
    now: datetime,
) -> tuple[dict[str, Any], str | None]:
    kind = pin.kind if ecosystem == GITHUB_ACTIONS else ""
    subject = Subject(ecosystem=ecosystem, package=pin.package, version=pin.current)
    declared = session.evidence.add(
        Evidence.verified(
            question=Question.DECLARED_PIN,
            subject=subject,
            value=pin.current,
            origin=Origin.TOOL,
            source=f"{pin.path}:{pin.kind}",
            observed_at=now,
            recipe=f"{capability}@list_declared_pins",
        )
    )

    base: dict[str, Any] = {
        "package": pin.package,
        "current": pin.current,
        "path": pin.path,
        "kind": pin.kind,
        "source": pin.source,
        "declared_evidence_key": declared.key,
        "current_resolved": None,
        "current_cleared": None,
        "target": None,
        "pending": [],
        "evidence_key": "",
        "line": None,
        "float_like": False,
    }

    memo_key = (ecosystem, pin.package, pin.current, kind)
    with session.pin_lock:
        remembered = session.pin_targets.get(memo_key)
        if isinstance(remembered, ClearedPinTarget):
            answer = remembered
            source = f"{ecosystem}:{pin.package}@{pin.current}→{answer.target or 'none'} (cached)"
        else:
            try:

                def run_command(command: list[str]) -> Any:
                    return tools.commands.run(tuple(command))

                answer = cleared_pin_target(
                    tools.http,
                    ecosystem=ecosystem,
                    package=pin.package,
                    current=pin.current,
                    kind=kind,
                    days=quarantine_days,
                    now=now,
                    run_command=run_command,
                )
            except (HostNotPermitted, OSError, ValueError, urllib.error.HTTPError) as error:
                # Fail-closed: null current_cleared trips the gate until a finding exists.
                gap = session.evidence.add(
                    Evidence.verified(
                        question=Question.CURRENT_CLEARED,
                        subject=subject,
                        value=None,
                        origin=Origin.API,
                        source=f"{ecosystem}:{pin.package}@{pin.current} (prep failed)",
                        observed_at=now,
                        recipe=f"{capability}@cleared_pin_target",
                    )
                )
                base["evidence_key"] = gap.key
                return base, f"{pin.package}: {error}"
            session.pin_targets[memo_key] = answer
            source = f"{ecosystem}:{pin.package}@{pin.current}→{answer.target or 'none'}"

    cleared_subject = Subject(
        ecosystem=ecosystem,
        package=pin.package,
        version=answer.current_resolved or pin.current,
    )
    stored = session.evidence.add(
        Evidence.verified(
            question=Question.CURRENT_CLEARED,
            subject=cleared_subject,
            value=answer.current_cleared,
            origin=Origin.API,
            source=source,
            observed_at=now,
            recipe=f"{capability}@cleared_pin_target",
        )
    )
    base.update(
        {
            "current_resolved": answer.current_resolved,
            "current_cleared": answer.current_cleared,
            "target": answer.target,
            "pending": list(answer.pending),
            "evidence_key": stored.key,
            "line": answer.line,
            "float_like": answer.float_like,
        }
    )
    return base, None
