"""Deterministic declared-pin census across ecosystems."""

from __future__ import annotations

from pathlib import Path

from agent.tools.pins import list_declared_pins, normalize_bsr, normalize_pypi, packages


def test_cargo_census_skips_path_and_git(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        """
[workspace.dependencies]
serde = "1.0.200"
api = { path = "rust/api" }
mimalloc = { git = "https://github.com/example/mimalloc", tag = "v1.0" }
bytes = { version = "1.0", default-features = false }

[dependencies]
tokio = "1.40"
""",
        encoding="utf-8",
    )
    pins = list_declared_pins(tmp_path, "ecosystems/cargo")
    names = packages(pins)
    assert names == frozenset({"serde", "bytes", "tokio"})
    assert "api" not in names
    assert "mimalloc" not in names


def test_npm_census_reads_deps_and_skips_workspace(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        """
{
  "name": "app",
  "dependencies": { "left-pad": "1.0.0", "local": "workspace:*" },
  "devDependencies": { "@scope/tool": "^2.0.0" }
}
""",
        encoding="utf-8",
    )
    names = packages(list_declared_pins(tmp_path, "ecosystems/npm"))
    assert names == frozenset({"left-pad", "@scope/tool"})


def test_python_uv_normalizes_names(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = ["Jinja2>=3.1", "httpx==0.28.1"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
""",
        encoding="utf-8",
    )
    names = packages(list_declared_pins(tmp_path, "ecosystems/python-uv"))
    assert normalize_pypi("Jinja2") == "jinja2"
    assert names == frozenset({"jinja2", "httpx", "pytest", "hatchling"})


def test_pip_compile_follows_requirement_includes(tmp_path: Path) -> None:
    (tmp_path / "requirements.in").write_text("connectrpc==0.11.1\n", encoding="utf-8")
    (tmp_path / "requirements-dev.in").write_text(
        "-r requirements.in\npytest==8.0\n", encoding="utf-8"
    )
    names = packages(list_declared_pins(tmp_path, "ecosystems/python-pip-compile"))
    assert names == frozenset({"connectrpc", "pytest"})


def test_go_census_direct_and_tool_skips_indirect(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        """
module example.com/app

go 1.22

tool (
        golang.org/x/vuln/cmd/govulncheck
)

require (
        connectrpc.com/connect v1.20.0
        golang.org/x/net v0.57.0 // indirect
        golang.org/x/vuln v1.6.0 // indirect
)
""",
        encoding="utf-8",
    )
    pins = list_declared_pins(tmp_path, "ecosystems/go-modules")
    names = packages(pins)
    assert names == frozenset({"connectrpc.com/connect", "golang.org/x/vuln"})
    by_name = {pin.package: pin for pin in pins}
    assert by_name["golang.org/x/vuln"].kind == "tool"
    assert by_name["golang.org/x/vuln"].current == "v1.6.0"
    assert by_name["connectrpc.com/connect"].kind == "runtime"
    assert by_name["connectrpc.com/connect"].current == "v1.20.0"


def test_go_tool_resolves_module_version_not_floating(tmp_path: Path) -> None:
    """tool ( path ) has no version; require holds it — demo2 #75 must not be floating."""
    (tmp_path / "go.mod").write_text(
        """
module example.com/app

go 1.26

tool (
        github.com/bufbuild/buf/cmd/buf
        github.com/golangci/golangci-lint/v2/cmd/golangci-lint
)

require (
        connectrpc.com/connect v1.20.0
        github.com/bufbuild/buf v1.72.0 // indirect
        github.com/golangci/golangci-lint/v2 v2.12.2 // indirect
)
""",
        encoding="utf-8",
    )
    pins = list_declared_pins(tmp_path, "ecosystems/go-modules")
    by_name = {pin.package: pin for pin in pins}
    assert set(by_name) == {
        "connectrpc.com/connect",
        "github.com/bufbuild/buf",
        "github.com/golangci/golangci-lint/v2",
    }
    assert by_name["github.com/golangci/golangci-lint/v2"].current == "v2.12.2"
    assert by_name["github.com/bufbuild/buf"].current == "v1.72.0"
    assert all(pin.current for pin in pins)


def test_bazel_census_follows_include(tmp_path: Path) -> None:
    (tmp_path / "MODULE.bazel").write_text(
        """
bazel_dep(name = "rules_go", version = "0.61.1")
include("//:go.MODULE.bazel")
""",
        encoding="utf-8",
    )
    (tmp_path / "go.MODULE.bazel").write_text(
        'bazel_dep(name = "gazelle", version = "0.51.3")\n',
        encoding="utf-8",
    )
    names = packages(list_declared_pins(tmp_path, "ecosystems/bazel"))
    assert names == frozenset({"rules_go", "gazelle"})


def test_bsr_census_modules_and_plugins(tmp_path: Path) -> None:
    (tmp_path / "buf.yaml").write_text(
        "deps:\n  - buf.build/bufbuild/protovalidate:v1.2.2\n",
        encoding="utf-8",
    )
    (tmp_path / "buf.gen.rust.yaml").write_text(
        "plugins:\n  - remote: buf.build/anthropics/buffa:v0.8.1\n",
        encoding="utf-8",
    )
    names = packages(list_declared_pins(tmp_path, "ecosystems/bsr"))
    assert names == frozenset(
        {
            normalize_bsr("buf.build/bufbuild/protovalidate"),
            normalize_bsr("buf.build/anthropics/buffa"),
        }
    )


def test_bsr_census_skips_agent_tools_and_go_mod_cache(tmp_path: Path) -> None:
    """Cached module trees are not product pins — demo2 #43/#44 were opened from these paths."""
    (tmp_path / "buf.yaml").write_text(
        "deps:\n  - buf.build/bufbuild/protovalidate:v1.2.2\n",
        encoding="utf-8",
    )
    cached = (
        tmp_path
        / ".agent"
        / "tools"
        / "go"
        / "pkg"
        / "mod"
        / "buf.build"
        / "go"
        / "protovalidate@v1.2.0"
    )
    cached.mkdir(parents=True)
    (cached / "buf.yaml").write_text(
        "deps:\n  - buf.build/rodaine/protogofakeit\n",
        encoding="utf-8",
    )
    outside_agent = tmp_path / "third" / "pkg" / "mod" / "cel.dev" / "expr@v0.25.2" / "proto"
    outside_agent.mkdir(parents=True)
    (outside_agent / "buf.yaml").write_text(
        "deps:\n  - buf.build/googleapis/googleapis\n",
        encoding="utf-8",
    )
    names = packages(list_declared_pins(tmp_path, "ecosystems/bsr"))
    assert names == frozenset({normalize_bsr("buf.build/bufbuild/protovalidate")})
    assert normalize_bsr("buf.build/rodaine/protogofakeit") not in names
    assert normalize_bsr("buf.build/googleapis/googleapis") not in names


def test_github_actions_via_list_declared_pins(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v7\n",
        encoding="utf-8",
    )
    names = packages(list_declared_pins(tmp_path, "ecosystems/github-actions"))
    assert names == frozenset({"actions/checkout"})
