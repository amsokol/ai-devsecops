"""What each role needs from whatever backend runs it.

These requirements live in code rather than in the configuration on purpose. A role's needs follow
from what its code does — an analyst that cannot call the tool registry has nothing to establish a
fact with — so they are not a knob. Mapping a role to a backend and a model *is* a decision, and
that part is configuration.

The check itself happens at startup. A `fixer` bound to an adapter that cannot modify files must
fail before the run opens issues and branches, not halfway through a maintenance run that then
reports it changed nothing.
"""

from __future__ import annotations

from enum import StrEnum

from agent.domain import Role


class Ability(StrEnum):
    """Something an adapter either implements or does not. Only stated where it is known."""

    TOOLS = "tools"
    """Can expose the agent's tool registry to a session.

    This is what a `fixer` needs to change files, too. Mutation is one of our tools — `edit_file`
    inside an isolated worktree, with the path checks and the never-send list applied — rather than
    a property of an SDK, so there is no separate ability for it. An earlier version declared one,
    and it was a distinction with nothing behind it: every adapter that can expose the registry can
    expose the tool that writes.
    """

    STRUCTURED_OUTPUT = "structured-output"
    """Can constrain a session's answer to a schema.

    Recorded rather than required: results arrive as a file the core validates, so no role depends
    on this. Adapters still declare it, because an eval comparing two SDKs needs to know.
    """

    TOKEN_ACCOUNTING = "token-accounting"  # noqa: S105 - an ability, not a credential
    """Reports what a session spent. Without it the run's token ceiling cannot bind."""


NEEDS: dict[Role, frozenset[Ability]] = {
    Role.INTENT: frozenset(),
    Role.ANALYST: frozenset({Ability.TOOLS}),
    Role.SWEEPER: frozenset({Ability.TOOLS}),
    Role.VULN: frozenset({Ability.TOOLS}),
    Role.FIXER: frozenset({Ability.TOOLS}),
    Role.WRITER: frozenset(),
}
"""What a role cannot work without.

`intent` and `writer` need nothing special: one classifies a short text, the other formulates one,
and both answer in a file like everybody else. `analyst`, `sweeper`, `vuln` and `fixer` need the
registry — the first three because a finding must rest on a call, the last because every edit and
every verification command it runs goes through it. `sweeper` and `vuln` are the same work shape as
`analyst`; the split exists so a product can bind a different model to outdated sweeps or to
vulnerability work alone.
"""


def needs(role: Role) -> frozenset[Ability]:
    return NEEDS[role]
