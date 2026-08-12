# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Report it privately through GitHub's [private vulnerability
reporting](https://github.com/100xopensource/100xtools/security/advisories/new) on this
repository. Include what you found, how to reproduce it, and what an attacker gets. We aim
to acknowledge within a few working days.

## What is in scope

These tools run a model with tool access over content in your repository, so the
interesting failure modes are about **what the model is allowed to do**, not about memory
safety:

- A path that lets skill content (contributor-authored, therefore untrusted) escalate
  beyond the read-only tool allowlist in `drift-check.yml`.
- A path that causes a token — `EVAL_MCP_BEARER`, `ANTHROPIC_API_KEY`,
  `CLAUDE_CODE_OAUTH_TOKEN` — to be written to disk, into a report, into an artifact, or
  into a PR comment.
- A path that lets a case file or plugin under evaluation execute code outside the run's
  temporary workspace.
- A workflow injection through an attacker-controllable GitHub context value.

## What is out of scope

- **The linter missing a secret.** `engine/lint.py`'s SEC1 check is a smoke detector, not a
  secret scanner. It catches common shapes and will miss a clever one. Run a real secret
  scanner in your pipeline too; a missed pattern is a bug report, not a vulnerability.
- **A model producing a wrong verdict.** drift-check is advisory and non-blocking by
  design. A bad review is a quality issue.
- **Prompt injection that only affects the report's text.** The mitigation is structural —
  the model has read-only tools and cannot merge, commit, or change permissions. Injection
  that changes what a report *says* is expected; injection that changes what the job *does*
  is a vulnerability.

## Notes for operators

- **Artifacts are readable by anyone with repo read access.** The 100xdrift-check workflow
  uploads the full execution transcript. Don't enable it on a repo where the skill content
  itself is sensitive.
- **`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` is a personal credential** and
  bills against that person's plan. For a team repo, prefer an organization API key.
- **Eval runs execute the plugin under test** with whatever MCP servers it declares. Treat
  running an untrusted plugin through 100xeval the same way you'd treat running its code.
- **Keep the tool allowlist in the workflow**, not in the skill. Permissions belong to the
  caller; a skill that could widen its own permissions would defeat the model.
