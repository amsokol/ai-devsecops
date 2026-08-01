"""Deterministic newest cleared target for dependency pins."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.tools.commands import CommandResult
from agent.tools.network import Response
from agent.tools.targets import cleared_pin_target

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
DAYS = 7


class FakeHttp:
    """Serves canned registry JSON for cleared_pin_target tests."""

    def __init__(self, routes: dict[str, object], *, truncated: set[str] | None = None) -> None:
        self.routes = routes
        self.truncated = truncated or set()

    def get(self, url: str) -> Response:
        for prefix, body in self.routes.items():
            if url.startswith(prefix) or url == prefix:
                text = body if isinstance(body, str) else json.dumps(body)
                return Response(
                    url=url,
                    status=200,
                    headers={},
                    body=text,
                    truncated=url in self.truncated or prefix in self.truncated,
                )
        raise AssertionError(f"unexpected URL {url}")


def test_action_major_pin_targets_cleared_not_young_tip() -> None:
    """@v7 tip v7.0.1 in window → Moves to v7.0.0; pending names the young tip."""
    http = FakeHttp(
        {
            "https://api.github.com/repos/actions/checkout/tags": [
                {"name": "v7.0.1"},
                {"name": "v7.0.0"},
                {"name": "v7"},
                {"name": "v6.0.0"},
            ],
            "https://api.github.com/repos/actions/checkout/releases/tags/v7.0.1": {
                "published_at": "2026-07-20T15:10:05Z"
            },
            "https://api.github.com/repos/actions/checkout/releases/tags/v7.0.0": {
                "published_at": "2026-06-18T13:53:05Z"
            },
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/github-actions",
        kind="action",
        package="actions/checkout",
        current="v7",
        days=DAYS,
        now=NOW,
    )
    assert answer.ecosystem == "ecosystems/github-actions"
    assert answer.line == "7"
    assert answer.current_resolved == "v7.0.1"
    assert answer.current_cleared is False
    assert answer.target == "v7.0.0"
    assert answer.pending == ("v7.0.1",)


def test_image_channel_picks_newest_cleared_not_older() -> None:
    """Floating 25-jdk must not drift to an older cleared build (demo2 PR #8)."""
    http = FakeHttp(
        {
            "https://hub.docker.com/v2/repositories/library/eclipse-temurin/tags": {
                "results": [
                    {"name": "25.0.3_9-jdk", "last_updated": "2026-07-10T00:00:00.000000Z"},
                    {"name": "25.0.2_10-jdk", "last_updated": "2026-06-01T00:00:00.000000Z"},
                    {"name": "25.0.3_9-jdk-jammy", "last_updated": "2026-07-11T00:00:00.000000Z"},
                    {"name": "24.0.2_12-jdk", "last_updated": "2026-05-01T00:00:00.000000Z"},
                ],
                "next": None,
            }
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/github-actions",
        kind="image",
        package="eclipse-temurin",
        current="25-jdk",
        days=DAYS,
        now=NOW,
    )
    assert answer.line == "25"
    assert answer.target == "25.0.3_9-jdk"
    assert "25.0.2_10-jdk" not in (answer.target,)
    assert "jdk-jammy" not in (answer.target or "")


def test_image_golang_channel_locks_minor_and_suffix() -> None:
    """golang:1.24-bookworm → newest cleared 1.24.x-bookworm, not plain or 1.23."""
    http = FakeHttp(
        {
            "https://hub.docker.com/v2/repositories/library/golang/tags": {
                "results": [
                    {
                        "name": "1.24.5-bookworm",
                        "last_updated": "2026-07-20T00:00:00.000000Z",
                    },
                    {
                        "name": "1.24.4-bookworm",
                        "last_updated": "2026-06-01T00:00:00.000000Z",
                    },
                    {"name": "1.24.5", "last_updated": "2026-06-01T00:00:00.000000Z"},
                    {
                        "name": "1.23.10-bookworm",
                        "last_updated": "2026-06-01T00:00:00.000000Z",
                    },
                ],
                "next": None,
            }
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/github-actions",
        kind="image",
        package="golang",
        current="1.24-bookworm",
        days=DAYS,
        now=NOW,
    )
    assert answer.line == "1"
    assert answer.target == "1.24.4-bookworm"
    assert answer.pending == ("1.24.5-bookworm",)


def test_cleared_current_with_only_pending_younger_has_no_target() -> None:
    http = FakeHttp(
        {
            "https://api.github.com/repos/actions/checkout/tags": [
                {"name": "v7.0.1"},
                {"name": "v7.0.0"},
            ],
            "https://api.github.com/repos/actions/checkout/releases/tags/v7.0.1": {
                "published_at": "2026-07-20T15:10:05Z"
            },
            "https://api.github.com/repos/actions/checkout/releases/tags/v7.0.0": {
                "published_at": "2026-06-18T13:53:05Z"
            },
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/github-actions",
        kind="action",
        package="actions/checkout",
        current="v7.0.0",
        days=DAYS,
        now=NOW,
    )
    assert answer.current_cleared is True
    assert answer.target is None
    assert answer.pending == ("v7.0.1",)


def test_cargo_newer_cleared_wins_yanked_excluded() -> None:
    http = FakeHttp(
        {
            "https://crates.io/api/v1/crates/serde/versions": {
                "versions": [
                    {"num": "1.0.230", "created_at": "2026-07-20T00:00:00Z", "yanked": False},
                    {"num": "1.0.229", "created_at": "2026-06-01T00:00:00Z", "yanked": False},
                    {"num": "1.0.228", "created_at": "2026-05-01T00:00:00Z", "yanked": False},
                    {"num": "1.0.227", "created_at": "2026-04-01T00:00:00Z", "yanked": True},
                ]
            }
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/cargo",
        package="serde",
        current="1.0.228",
        days=DAYS,
        now=NOW,
    )
    assert answer.target == "1.0.229"
    assert answer.pending == ("1.0.230",)
    assert answer.ecosystem == "ecosystems/cargo"


def test_cargo_young_tip_pin_down() -> None:
    http = FakeHttp(
        {
            "https://crates.io/api/v1/crates/serde/versions": {
                "versions": [
                    {"num": "1.0.230", "created_at": "2026-07-20T00:00:00Z", "yanked": False},
                    {"num": "1.0.229", "created_at": "2026-06-01T00:00:00Z", "yanked": False},
                ]
            }
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/cargo",
        package="serde",
        current="1.0.230",
        days=DAYS,
        now=NOW,
    )
    assert answer.current_cleared is False
    assert answer.target == "1.0.229"
    assert answer.pending == ("1.0.230",)


def test_npm_newer_cleared_wins() -> None:
    http = FakeHttp(
        {
            "https://registry.npmjs.org/left-pad": {
                "versions": {"1.0.0": {}, "1.1.0": {}, "1.2.0": {}, "2.0.0": {}},
                "time": {
                    "1.0.0": "2026-01-01T00:00:00.000Z",
                    "1.1.0": "2026-06-01T00:00:00.000Z",
                    "1.2.0": "2026-07-20T00:00:00.000Z",
                    "2.0.0": "2026-06-15T00:00:00.000Z",
                },
            }
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/npm",
        package="left-pad",
        current="1.0.0",
        days=DAYS,
        now=NOW,
    )
    assert answer.target == "1.1.0"
    assert answer.pending == ("1.2.0",)
    assert answer.line == "1"


def test_pypi_young_tip_pending_and_pin_down() -> None:
    http = FakeHttp(
        {
            "https://pypi.org/pypi/requests/json": {
                "releases": {"2.31.0": [], "2.32.0": [], "2.32.1": [], "3.0.0": []}
            },
            "https://pypi.org/pypi/requests/2.32.1/json": {
                "urls": [{"upload_time_iso_8601": "2026-07-20T00:00:00.000000Z"}]
            },
            "https://pypi.org/pypi/requests/2.32.0/json": {
                "urls": [{"upload_time_iso_8601": "2026-06-01T00:00:00.000000Z"}]
            },
            "https://pypi.org/pypi/requests/2.31.0/json": {
                "urls": [{"upload_time_iso_8601": "2026-05-01T00:00:00.000000Z"}]
            },
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/python-uv",
        package="requests",
        current="2.32.1",
        days=DAYS,
        now=NOW,
    )
    assert answer.target == "2.32.0"
    assert answer.pending == ("2.32.1",)


def test_pypi_requirement_form_dates_the_pin_in_use() -> None:
    """Prep passes `name==version`; that must not leave current_cleared null (#86/#79)."""
    http = FakeHttp(
        {
            "https://pypi.org/pypi/connectrpc/json": {"releases": {"0.11.1": [], "0.11.0": []}},
            "https://pypi.org/pypi/connectrpc/0.11.1/json": {
                "urls": [{"upload_time_iso_8601": "2026-07-15T06:33:29.396530Z"}]
            },
            "https://pypi.org/pypi/connectrpc/0.11.0/json": {
                "urls": [{"upload_time_iso_8601": "2026-06-01T00:00:00.000000Z"}]
            },
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/python-pip-compile",
        package="connectrpc",
        current="connectrpc==0.11.1",
        days=DAYS,
        now=NOW,
    )
    assert answer.current == "0.11.1"
    assert answer.current_cleared is True
    assert answer.current_resolved == "0.11.1"


def test_pypi_truncated_package_json_falls_back_to_rss() -> None:
    """Full /json for busy packages (ruff) exceeds the body limit — still date the pin (#87)."""
    http = FakeHttp(
        {
            "https://pypi.org/pypi/ruff/json": "{not-json-because-truncated",
            "https://pypi.org/rss/project/ruff/releases.xml": """\
<?xml version="1.0"?>
<rss><channel>
<title>PyPI recent updates for ruff</title>
<title>0.15.22</title>
<title>0.15.21</title>
</channel></rss>
""",
            "https://pypi.org/pypi/ruff/0.15.22/json": {
                "urls": [{"upload_time_iso_8601": "2026-07-16T15:13:19.452734Z"}]
            },
            "https://pypi.org/pypi/ruff/0.15.21/json": {
                "urls": [{"upload_time_iso_8601": "2026-07-09T20:00:53.000000Z"}]
            },
        },
        truncated={"https://pypi.org/pypi/ruff/json"},
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/python-pip-compile",
        package="ruff",
        current="ruff==0.15.22",
        days=DAYS,
        now=NOW,
    )
    assert answer.current_cleared is True
    assert answer.current_resolved == "0.15.22"


def test_floating_action_without_concrete_tip_is_float_like() -> None:
    """@stable with no dated concrete tip is a floating ref, not a missing publish date (#84)."""
    http = FakeHttp(
        {
            "https://api.github.com/repos/dtolnay/rust-toolchain/tags": [
                {"name": "stable"},
                {"name": "v1"},
            ],
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/github-actions",
        kind="action",
        package="dtolnay/rust-toolchain",
        current="stable",
        days=DAYS,
        now=NOW,
    )
    assert answer.float_like is True
    assert answer.current_resolved is None
    assert answer.current_cleared is None
    assert answer.target is None


def test_go_newer_cleared_wins() -> None:
    http = FakeHttp(
        {
            "https://proxy.golang.org/github.com/pkg/errors/@v/list": "v0.9.0\nv0.9.1\nv0.8.1\n",
            "https://proxy.golang.org/github.com/pkg/errors/@v/v0.9.1.info": {
                "Version": "v0.9.1",
                "Time": "2026-07-20T00:00:00Z",
            },
            "https://proxy.golang.org/github.com/pkg/errors/@v/v0.9.0.info": {
                "Version": "v0.9.0",
                "Time": "2026-06-01T00:00:00Z",
            },
            "https://proxy.golang.org/github.com/pkg/errors/@v/v0.8.1.info": {
                "Version": "v0.8.1",
                "Time": "2026-01-01T00:00:00Z",
            },
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/go-modules",
        package="github.com/pkg/errors",
        current="v0.8.1",
        days=DAYS,
        now=NOW,
    )
    assert answer.target == "v0.9.0"
    assert answer.pending == ("v0.9.1",)


def test_bazel_yanked_excluded_and_bcr_publish_time() -> None:
    http = FakeHttp(
        {
            "https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/"
            "main/modules/rules_python/metadata.json": {
                "versions": ["0.40.0", "1.0.0", "1.1.0"],
                "yanked_versions": {"1.1.0": "broken"},
                "repository": ["github:bazelbuild/rules_python"],
            },
            "https://api.github.com/repos/bazelbuild/bazel-central-registry/commits"
            "?path=modules%2Frules_python%2F0.40.0%2Fsource.json": [
                {"commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}}
            ],
            "https://api.github.com/repos/bazelbuild/bazel-central-registry/commits"
            "?path=modules%2Frules_python%2F1.0.0%2Fsource.json": [
                {"commit": {"committer": {"date": "2026-06-01T00:00:00Z"}}}
            ],
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/bazel",
        package="rules_python",
        current="0.40.0",
        days=DAYS,
        now=NOW,
    )
    # Major jump 0→1 is not routine target; line stays on 0.
    assert answer.line == "0"
    assert answer.target is None
    assert answer.current_cleared is True


def test_bazel_same_major_newer_cleared() -> None:
    http = FakeHttp(
        {
            "https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/"
            "main/modules/rules_python/metadata.json": {
                "versions": ["1.0.0", "1.1.0", "1.2.0"],
                "yanked_versions": {"1.2.0": "yanked"},
                "repository": ["github:bazelbuild/rules_python"],
            },
            "https://api.github.com/repos/bazelbuild/bazel-central-registry/commits"
            "?path=modules%2Frules_python%2F1.0.0%2Fsource.json": [
                {"commit": {"committer": {"date": "2026-06-01T00:00:00Z"}}}
            ],
            "https://api.github.com/repos/bazelbuild/bazel-central-registry/commits"
            "?path=modules%2Frules_python%2F1.1.0%2Fsource.json": [
                {"commit": {"committer": {"date": "2026-07-20T00:00:00Z"}}}
            ],
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/bazel",
        package="rules_python",
        current="1.0.0",
        days=DAYS,
        now=NOW,
    )
    # 1.1.0 young (Jul 20 + 7d = Jul 27, NOW Jul 26) → pending; yanked tip excluded.
    assert answer.target is None
    assert "1.1.0" in answer.pending
    assert "1.2.0" not in answer.pending
    assert answer.current_cleared is True


def test_bazel_bcr_date_preferred_over_upstream_release() -> None:
    """BCR commit date is source of truth; a conflicting GitHub Release must not win."""
    http = FakeHttp(
        {
            "https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/"
            "main/modules/rules_rust/metadata.json": {
                "versions": ["0.71.3"],
                "yanked_versions": {},
                "repository": ["github:bazelbuild/rules_rust"],
            },
            "https://api.github.com/repos/bazelbuild/bazel-central-registry/commits"
            "?path=modules%2Frules_rust%2F0.71.3%2Fsource.json": [
                {"commit": {"committer": {"date": "2026-07-02T03:28:44Z"}}}
            ],
            # Would keep the pin in quarantine if used (young) — must be ignored when BCR answers.
            "https://api.github.com/repos/bazelbuild/rules_rust/releases/tags/0.71.3": {
                "published_at": "2026-07-24T00:00:00Z"
            },
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/bazel",
        package="rules_rust",
        current="0.71.3",
        days=14,
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert answer.current_cleared is True


def test_bazel_falls_back_to_github_release_when_bcr_has_no_commit() -> None:
    http = FakeHttp(
        {
            "https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/"
            "main/modules/rules_rust/metadata.json": {
                "versions": ["0.71.3"],
                "yanked_versions": {},
                "repository": ["github:bazelbuild/rules_rust"],
            },
            "https://api.github.com/repos/bazelbuild/bazel-central-registry/commits"
            "?path=modules%2Frules_rust%2F0.71.3%2Fsource.json": [],
            "https://api.github.com/repos/bazelbuild/rules_rust/releases/tags/0.71.3": {
                "published_at": "2026-07-02T03:28:44Z"
            },
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/bazel",
        package="rules_rust",
        current="0.71.3",
        days=14,
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert answer.current_cleared is True


def test_bsr_fake_command_newer_cleared() -> None:
    labels = [
        {"name": "v1.2.0", "createTime": "2026-07-20T00:00:00Z"},
        {"name": "v1.1.0", "createTime": "2026-06-01T00:00:00Z"},
        {"name": "v1.0.0", "createTime": "2026-01-01T00:00:00Z"},
    ]

    def run_command(command: list[str]) -> CommandResult:
        assert command[0] == "buf"
        assert command[2] == "module"
        return CommandResult(
            command=tuple(command),
            exit_code=0,
            stdout=json.dumps(labels),
            stderr="",
            timed_out=False,
        )

    answer = cleared_pin_target(
        FakeHttp({}),  # type: ignore[arg-type]
        ecosystem="ecosystems/bsr",
        package="bufbuild/protovalidate",
        current="v1.0.0",
        days=DAYS,
        now=NOW,
        run_command=run_command,
    )
    assert answer.target == "v1.1.0"
    assert answer.pending == ("v1.2.0",)


def test_bsr_falls_back_to_plugin_label_list() -> None:
    """Remote plugins are not modules; module list fails and must not become a false null target."""
    labels = [
        {"name": "v0.9.0", "createTime": "2026-07-17T20:55:52Z"},
        {"name": "v0.8.1", "createTime": "2026-07-01T16:01:47Z"},
        {"name": "v0.9.1", "createTime": "2026-07-23T21:06:45Z"},
    ]
    seen: list[str] = []

    def run_command(command: list[str]) -> CommandResult:
        seen.append(command[2])
        if command[2] == "module":
            return CommandResult(
                command=tuple(command),
                exit_code=1,
                stdout="",
                stderr="not a module",
                timed_out=False,
            )
        return CommandResult(
            command=tuple(command),
            exit_code=0,
            stdout=json.dumps(labels),
            stderr="",
            timed_out=False,
        )

    answer = cleared_pin_target(
        FakeHttp({}),  # type: ignore[arg-type]
        ecosystem="ecosystems/bsr",
        package="buf.build/anthropics/buffa",
        current="v0.8.1",
        days=DAYS,
        now=NOW,
        run_command=run_command,
    )
    assert seen == ["module", "plugin"]
    assert answer.target == "v0.9.0"
    assert answer.pending == ("v0.9.1",)


def test_bsr_empty_plugin_labels_use_plugins_catalog_then_github() -> None:
    """Protoc plugins often return an empty label list; catalog miss falls through to Releases."""

    def run_command(command: list[str]) -> CommandResult:
        # module fails; plugin "succeeds" with empty body — the live buffa shape.
        if command[2] == "module":
            return CommandResult(
                command=tuple(command),
                exit_code=1,
                stdout="",
                stderr="does not exist",
                timed_out=False,
            )
        return CommandResult(
            command=tuple(command), exit_code=0, stdout="", stderr="", timed_out=False
        )

    http = FakeHttp(
        {
            "https://api.github.com/repos/bufbuild/plugins/contents/"
            "plugins/anthropics/buffa?ref=main": [],
            "https://api.github.com/repos/anthropics/buffa/releases": [
                {
                    "tag_name": "v0.9.1",
                    "published_at": "2026-07-23T21:06:45Z",
                    "draft": False,
                    "prerelease": False,
                },
                {
                    "tag_name": "v0.9.0",
                    "published_at": "2026-07-17T20:55:52Z",
                    "draft": False,
                    "prerelease": False,
                },
                {
                    "tag_name": "v0.8.1",
                    "published_at": "2026-07-01T16:01:47Z",
                    "draft": False,
                    "prerelease": False,
                },
            ],
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/bsr",
        package="buf.build/anthropics/buffa",
        current="v0.8.1",
        days=DAYS,
        now=NOW,
        run_command=run_command,
    )
    assert answer.target == "v0.9.0"
    assert answer.pending == ("v0.9.1",)


def test_bsr_plugins_catalog_dates_connectrpc_rust() -> None:
    """buf.build/connectrpc/rust is not GitHub connectrpc/rust — catalog + source_url win."""
    http = FakeHttp(
        {
            "https://api.github.com/repos/bufbuild/plugins/contents/"
            "plugins/connectrpc/rust?ref=main": [
                {"name": "v0.8.0", "type": "dir"},
                {"name": "source.yaml", "type": "file"},
            ],
            "https://api.github.com/repos/bufbuild/plugins/commits"
            "?path=plugins%2Fconnectrpc%2Frust%2Fv0.8.0%2Fbuf.plugin.yaml": [
                {"commit": {"committer": {"date": "2026-07-07T14:24:41Z"}}}
            ],
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/bsr",
        package="buf.build/connectrpc/rust",
        current="v0.8.0",
        days=14,
        now=datetime(2026, 8, 1, tzinfo=UTC),
        run_command=None,
    )
    assert answer.current_cleared is True
    assert answer.target is None


def test_bsr_github_fallback_without_buf_command() -> None:
    http = FakeHttp(
        {
            "https://api.github.com/repos/bufbuild/plugins/contents/"
            "plugins/anthropics/buffa?ref=main": [],
            "https://api.github.com/repos/anthropics/buffa/releases": [
                {
                    "tag_name": "v0.9.0",
                    "published_at": "2026-07-17T20:55:52Z",
                    "draft": False,
                    "prerelease": False,
                },
                {
                    "tag_name": "v0.8.1",
                    "published_at": "2026-07-01T16:01:47Z",
                    "draft": False,
                    "prerelease": False,
                },
            ],
        }
    )
    answer = cleared_pin_target(
        http,  # type: ignore[arg-type]
        ecosystem="ecosystems/bsr",
        package="buf.build/anthropics/buffa",
        current="v0.8.1",
        days=DAYS,
        now=NOW,
        run_command=None,
    )
    assert answer.target == "v0.9.0"


def test_bsr_without_buf_or_github_returns_null_target() -> None:
    import urllib.error

    class MissingHttp:
        def get(self, url: str) -> Response:
            raise urllib.error.HTTPError(url, 404, "missing", hdrs=None, fp=None)  # type: ignore[arg-type]

    answer = cleared_pin_target(
        MissingHttp(),  # type: ignore[arg-type]
        ecosystem="ecosystems/bsr",
        package="bufbuild/protovalidate",
        current="1.0.0",
        days=DAYS,
        now=NOW,
        run_command=None,
    )
    assert answer.target is None
    assert answer.pending == ()
