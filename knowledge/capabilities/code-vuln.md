---
id: capabilities/code-vuln
kind: capability
summary: Security defects in the product's own code.
---

# Code vulnerabilities

## What to look for

- **Secret leakage:** credentials, tokens or keys committed to the tree, written to logs,
  embedded in error messages, or passed through a URL.
- **Unsafe deserialisation:** loading untrusted data with a constructor that can instantiate
  arbitrary types, such as a YAML load without a safe loader, or pickle on external input.
- **Unsafe subprocess use:** a shell invoked with interpolated input, an unvalidated binary path,
  arguments assembled from user data.
- **Path traversal:** file paths built from external input without normalisation and containment.
- **Server-side request forgery:** outbound requests to a host taken from input, redirects
  followed into a private network.
- **Injection into a query or template** built by string concatenation from external input.
- **Missing or wrong authorisation** on an operation that changes state or reveals data.
- **Weak or misused cryptography:** a hand-rolled construction, a broken primitive, a static or
  predictable key or nonce.
- **Workflow and pipeline patterns** that expose secrets to untrusted code — checking out an
  untrusted head with elevated permissions, or widening permissions to make something work.

## Evidence needed

- The code itself, and enough of the call graph to show that the untrusted input reaches the
  dangerous operation.
- The project's own security checks when available. Their output is reproducible evidence, and it
  should be preferred over an unaided reading.
- For a leaked secret: the concrete location, plus whether it is live. A rotated placeholder and
  an active key are different findings.

## Judgement criteria

Reachability decides. A dangerous pattern with no path from untrusted input is at most a
low-severity note. State the path in one sentence: where the data enters, and where it is used.

A passing build says nothing about security, and neither does the absence of a scanner finding.
Both are inputs, not conclusions.

Where the product overlay names hotspots, weight them: the same pattern in the authentication
path and in a local development script are not the same finding.

## Severity

| Severity | Typical case |
| --- | --- |
| `critical` | Live secret exposed, or remote code execution reachable from untrusted input |
| `high` | Authorisation bypass, injection reachable from a user-facing surface, secret written to logs |
| `medium` | Dangerous pattern reachable only under a specific configuration |
| `low` | Defensive hardening; pattern present but not reachable |

## Fix policy

Security class only. Remediation is the minimal change that closes the hole, on the security
track, never mixed with routine work
([`../policy/grouping.md`](../policy/grouping.md)). Unrelated security findings go on separate
branches.

A leaked credential is not fixed by deleting the line: say plainly in the finding that the
secret must be rotated, because the history still contains it.

## False positives

- The value that looks like a secret is a placeholder, a test fixture, or a public identifier.
- Input is validated or escaped by a layer above the flagged line.
- The framework escapes the value at render time.
- The construct is used only with literals under the developer's control.
- The pattern lives in a test that never runs against real input.

Report a suspected secret even when unsure of its validity, but say which it is: a confirmed
credential and a suspicious string carry different actions.
