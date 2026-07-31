"""Where the bundled knowledge library lives.

The monorepo ships one product: runner + knowledge. Installed wheels carry `knowledge/` next to the
`agent` package; an editable checkout uses the tree-level `knowledge/` directory. Either way there
is no separate pin — the agent version *is* the knowledge version.
"""

from __future__ import annotations

from pathlib import Path

from agent.errors import ConfigError

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PACKAGE_ROOT.parent


def default_library_root() -> Path:
    """The knowledge tree that ships with this agent build."""
    packaged = _PACKAGE_ROOT / "knowledge"
    if (packaged / "INDEX.md").is_file():
        return packaged.resolve()
    checkout = _REPO_ROOT / "knowledge"
    if (checkout / "INDEX.md").is_file():
        return checkout.resolve()
    raise ConfigError(
        "bundled knowledge library is missing: expected INDEX.md under agent/knowledge "
        "(installed wheel) or knowledge/ (source checkout)"
    )
