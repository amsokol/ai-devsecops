# Index

Generated from document headers by `scripts/library.py`. This is the only file an agent reads in full
on every run; bodies are loaded on demand, selected by playbook, by the ecosystems the overlay
enables, and by the files a change touches.

Templates under `overlay/templates/` are artefacts for products to copy and are deliberately absent
from this index.

| id | kind | summary | applies_to |
| --- | --- | --- | --- |
| `playbooks/maintain` | playbook | Maintain the default branch — track findings as issues, ship verified fixes, reconcile. | — |
| `playbooks/pr-review` | playbook | Review a proposed change and produce a verdict; never open issues or fix branches. | — |
| `capabilities/code-quality` | capability | Correctness and maintainability risks in code; style is out of scope. | — |
| `capabilities/code-vuln` | capability | Security defects in the product's own code. | — |
| `capabilities/deps-outdated` | capability | Dependency version drift, under quarantine, holds, grouping and bundle rules. | — |
| `capabilities/deps-vuln` | capability | Known vulnerabilities in dependencies, and how to choose a remediation. | — |
| `evidence/acquisition` | policy | General procedure for obtaining facts and recording them as evidence. | — |
| `policy/bundles` | policy | Coupled dependencies that must be scanned, unlocked, moved and verified together. | — |
| `policy/grouping` | policy | How to split dependency and code changes into reviewable change requests. | — |
| `policy/holds` | policy | Human holds and unlocks expressed as comments next to dependency pins. | — |
| `policy/quarantine` | policy | Release quarantine — do not adopt a version until it has been published for N days. | — |
| `policy/unknowns` | policy | What to do when a required fact cannot be established. | — |
| `policy/verdicts` | policy | Finding classes, severity scale, forbidden states, and which evidence may block a change. | — |
| `policy/verification` | policy | Which verification surfaces to run after a fix, including absences and build-system couplings. | — |
| `ecosystems/bazel` | ecosystem | Bazel module pins via the Central Registry, and couplings to language dependency graphs. | `MODULE.bazel`, `MODULE.bazel.lock` |
| `ecosystems/bsr` | ecosystem | Buf Schema Registry modules and remote plugins, including the plugin resolve probe. | `buf.yaml`, `buf.lock`, `buf.gen.yaml` |
| `ecosystems/cargo` | ecosystem | Dependency facts and update procedure for Rust projects. | `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml` |
| `ecosystems/github-actions` | ecosystem | Pinned CI actions, container images and tool versions in workflows. | `.github/workflows`, `.github/actions` |
| `ecosystems/go-modules` | ecosystem | Dependency facts and update procedure for Go modules. | `go.mod`, `go.sum` |
| `ecosystems/npm` | ecosystem | Dependency facts and update procedure for Node projects. | `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` |
| `ecosystems/python-pip-compile` | ecosystem | Dependency facts and update procedure for Python projects locked with pip-compile. | `requirements.in`, `requirements.txt` |
| `ecosystems/python-uv` | ecosystem | Dependency facts and update procedure for uv-managed Python projects. | `pyproject.toml`, `uv.lock` |
| `scm/github` | scm | GitHub specifics — identity, merge authority, tokens and workflow constraints. | — |
| `overlay/README` | overlay | What a product must define in its own overlay, and what it may not override. | — |
