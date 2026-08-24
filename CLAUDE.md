# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Public, Apache-2.0 tooling for maintaining Claude Code plugins, extracted from a private
plugin fleet. One repo, one directory per tool under `plugins/`. Each tool is an ordinary
Claude Code plugin *and* a CI gate — that dual role is why they are built to run offline,
from a clean clone, with no install step.

```
.claude-plugin/marketplace.json   one entry per plugin; CI checks it against plugins/
docs/                             OKF knowledge bundle — concepts, NOT shipped with plugins
examples/<tool>/                  worked eval cases + vendored third-party plugins
plugins/<name>/                   self-contained plugin: manifest, README, skills/
scripts/check_docs.py             OKF bundle conformance + link check
.github/workflows/ci.yml          test · static · examples · docs · manifests
```

Two things about `examples/` that look odd until you know why:

- **`examples/plugin-eval/cases` is a second case root.** The default is `evals/`, so the
  example cases are only found with `--cases-dir examples/plugin-eval/cases`. CI dry-runs them, which proves they parse and
  resolve their plugins without a model call.
- **`vendor/` is skipped by plugin discovery** (`lint.py`). Third-party code copied in for
  fixtures is not ours to score, and discovering it would turn our own sweep into a report
  card on someone else's plugin. Lint it deliberately with `--target` if you want to.

## Repo-wide invariants

These hold for every plugin here and explain most of the layout decisions. Read them before
moving files.

**1. A plugin must be self-contained.** A marketplace install copies `plugins/<name>/` and
nothing else — no repo root, no `docs/`, no sibling plugin. Everything a plugin needs to
*operate* lives inside its own directory. Consequences worth knowing, because each looks
arbitrary in isolation:

- Skill `references/` stay the source of truth for how to use a tool; `docs/` links to them
  rather than restating them.
- `scripts/check_docs.py` is a repo-level script, not a plugin unit test — the plugin suite
  has to pass for someone who has only the plugin.
- Anything a plugin genuinely needs is duplicated *into* it, not imported from the root.

**2. Python stdlib only.** No third-party dependencies anywhere, including tests. Hard
constraint, not a preference — `yamlmin.py` exists rather than a PyYAML dependency.

**3. Nothing internal, customer-specific, or unlicensed ships.** This repo was extracted
from a private one. Fixtures use `Acme` and `example.com`/`example.net`. Real connector
URLs, plugin names, store/customer names, captured `claude mcp list` output, ticket IDs
(`AIP-`/`OST-`), internal doc paths, and vendor system prompts must not appear. Sweep before
committing — a captured `claude mcp list` fixture leaked through the first port and was
caught only on a second pass.

**4. Trust-boundary files need author ≠ reviewer.** `.github/workflows/*`,
`plugins/100xdrift-check/templates/workflows/drift-check.yml`,
`plugins/100xdrift-check/templates/skills/drift-check/SKILL.md`,
`plugins/100x-continuity/scripts/engine/redact.py`,
`plugins/100x-continuity/scripts/engine/bundle.py`, and
`plugins/100x-continuity/templates/store-service/server.py` decide what CI does with
model output, what tools the model gets, and what runs automatically on a user's machine.
`redact.py` is on that list because it is the only thing standing between a full session
transcript and a folder that syncs to somebody's cloud account; `bundle.py` because it is
what refuses a hostile archive somebody else wrote before it is unpacked onto a reader's
disk, and what refuses to publish a staged file holding a credential; `server.py` because
it is the template that decides who can read whose session, on infrastructure the user
runs. A change that weakens a pattern in any of them is a privacy incident, not a bug. Checks there only ever tighten; if a change relaxes a guard, say
so explicitly rather than letting a reviewer find it.

**5. Every plugin scores 1.00** on the static linter this repo ships. CI dogfoods it, so a
change that makes our own plugins look bad fails here rather than in someone else's repo.

## The three documentation surfaces

Easy to put something in the wrong one. They have different audiences and different
lifetimes:

| Surface | Answers | Ships with the plugin? |
| --- | --- | --- |
| `plugins/<name>/README.md` | How do I install and run this? | Yes |
| `skills/<name>/SKILL.md` + `references/` | How should Claude operate it? | Yes |
| `docs/` (OKF bundle) | What is this concept and why does it exist? | **No** |

`docs/` is [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
v0.2: one concept per file, YAML frontmatter, `type` required, `index.md`/`log.md` reserved,
provenance in a `generated: { by, at }` mapping whose `by` follows the spec's actor
convention. The bundle root declares `okf_version` in `index.md` frontmatter — the one place
a reserved file is allowed any.

It is concept-only by design and must never become load-bearing for operating a plugin, per
invariant 1. Links inside it are relative rather than bundle-absolute so they resolve on
GitHub; `docs/index.md` records that deviation.

`scripts/check_docs.py` enforces all of the above plus link resolution, and fails on a
leftover v0.1 `timestamp` field so a spec migration cannot half-happen.

**`docs/adr/` is the one directory under `docs/` that is not part of the bundle.** An ADR
records a decision and the trade behind it; an OKF doc explains a thing that exists.
Conformance skips it — dressing an ADR in `type:` frontmatter to get it past the checker
would be calling it something it is not — but the link check does not, because a broken
link is a broken link either way.

## Commands

No install, build, or lockfile step anywhere.

```bash
# From the REPO ROOT
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only   # design quality, free
python3 scripts/check_docs.py                                                # docs bundle

# Why a plugin scored what it scored (the report prints scores, not findings)
python3 -c "
import sys; sys.path.insert(0, 'plugins/100xeval/skills/100xeval/scripts')
from engine import static
for f in static.analyze('plugins/100xeval')['findings']: print(f)"
```

```bash
# Engine tests — offline; no model, MCP, or network calls. Two plugins ship a suite and
# CI's `test` job matrixes over both, so a new suite means a new row in that matrix.
# The path is wherever `scripts/` and `tests/` sit: a skill directory when one skill owns
# the engine, the plugin root when several skills share it (100x-continuity).
cd plugins/100xeval/skills/100xeval          # or plugins/100x-continuity
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'

# One module / class / test
PYTHONPATH=scripts python3 -m unittest tests.test_lint
PYTHONPATH=scripts python3 -m unittest tests.test_lint.TestSecurityChecks.test_path_traversal_flagged
```

**The repo's Python floor is 3.11**, which is above the macOS system `python3` (3.9). The
suites use `contextlib.chdir` and `X | None` annotations at runtime, so on a stock Mac they
fail for reasons that have nothing to do with the change under test. `uv run --python 3.11
--no-project python -m unittest …` runs them on the real floor.

**`tests/` sits beside `scripts/`, not inside it** — `scripts/` is the runtime payload that
ships and that Claude invokes, so the suite stays out of it. Both the `cd` and
`PYTHONPATH=scripts` are required: tests import `engine.*` absolutely and have no idea where
they live. Note the shell's cwd persists between tool calls — a command run from the repo
root fails if you are still inside the skill directory, and vice versa.

CI runs exactly these. If they pass locally they pass there. Behavioral eval runs cost money
and need credentials, so they are **not** wired into this repo's CI — see
`plugins/100xeval/README.md` to run them.

`scripts/hooks/pre-commit` runs all of the above plus a secret and internal-reference sweep
over **staged** content, in about two seconds. Enable per clone with `git config
core.hooksPath scripts/hooks`; `--no-verify` bypasses it. Generic secret shapes live in the
hook; org-specific names go in the gitignored `scripts/hooks/leak-patterns.local` (copy the
`.example`) — a public list of the names you are hiding publishes them.

## Plugins

### 100xeval — behavioral + static evaluation

**Eval flow:** `run.py` → `cli` → `loader` → `orchestrator` → harness → graders → `reporter`.

- **`loader.py`** walks `evals/**/case.yaml`, flattens `execution.*` onto a `Case`, and
  validates. Paths in `plugins:` resolve **relative to the case file**, not the repo root.
- **`orchestrator.run_case`** runs one case `runs` times concurrently, scores each grader as
  `passRate = passed/runs`, and takes a weighted mean. Concurrency is a **suite-wide**
  budget shared across cases, not per-case.
- **`harnesses/`** is the runtime seam, registered via `base.register_harness`. Only
  `claude_code` is implemented; `codex` is a seam that aborts in preflight.
- **`graders.py`** holds a `_GRADERS` name→function registry populated at import time
  (`tool_used`, `regex`, `llm`, `static`). `llm` delegates to `judge.py`, majority voting
  over N votes.
- **`reporter.py`** emits markdown/JSON/HTML with a `schemaVersion` on the JSON.

**The two axes — `harness` vs `entrypoint`** are independent and the single easiest thing to
get wrong. `harness` is the **runtime** that executes and observes the turn; `entrypoint` is
the **surface** emulated, its real system prompt swapped in with `--system-prompt`
(replacing, not appending). A surface is never a harness — the loader rejects
`harness: cowork` and `harness: claude_chat` with a message naming the right pair.

Default `entrypoint: none` passes no `--system-prompt`. **`cowork` is the one entrypoint
tracked here**, by explicit decision — see the git history for that file. Any *other*
surface prompt stays gitignored by default, because it usually belongs to whoever operates
that surface. `--entrypoint <name>` overrides every case in a run. Any *other* name must resolve to a file or preflight aborts — a case that
emulates nothing still scores, and a pass for the wrong reason is worse than a failure.

**The static layer — lint → check ID → sub-score.** `lint.py` emits `Finding`s whose `.msg`
**starts with** a bracketed ID (`[FM3]`, `[PD1]`, `[SEC1]`). The **prefix names the
sub-score**, so `static.py` derives the mapping from `_PREFIX_TO_SUBCHECK`
(`FM` · `PD` · `RH` · `ST` · `EC` · `SEC`) rather than keeping a per-ID table, then weights
them (`security` ×2, `token_efficiency` ×0.5) and applies a flag-count penalty.

- **Adding a check:** pick the prefix for its sub-score, take the next free number, add a row
  to `docs/100xeval/check-ids.md`. An unregistered prefix *raises* (`UnknownCheckPrefix`)
  instead of scoring nothing; `TestCheckIdContract` fails in both directions, and
  `scripts/check_docs.py` fails if the docs page and `lint.py` disagree.
- `_ID_RE` is anchored to the start of the message on purpose — findings interpolate content
  from the plugin under test, and a bracketed token in there must not read as a check ID now
  that unknown prefixes raise.
- **SEC1 (secrets) scans every text file; SEC2/SEC3 scan skill prose only**
  (`_PROSE_SUFFIXES`). SEC2/SEC3 read a file as *instructions to the model*, so applying them
  to bundled source flagged every plugin that ships a script. SEC3 further requires a read
  verb near the `../`, so `plugins: ["../../plugins/x"]` doesn't fire.
- `token_efficiency` is the one sub-score with no check ID — computed directly by counting
  duplicate ≥20-char lines across **all** of a plugin's SKILL.md files. Its `seen` set spans
  the whole plugin on purpose: scoped per file it only caught a skill repeating itself and
  scored copy-paste between siblings at a clean 1.00, which is the case it exists for.
- `static.analyze()` only reads `.msg`, so any module exposing `lint_plugin(dir, root)` can
  replace `lint.py`.

**MCP has exactly one path: strict plugin config** (`--mcp-config … --strict-mcp-config`), so
tool names have exactly one scheme, `mcp__<Server>__<tool>`. The claude.ai account connector was
supported and was **deliberately removed** — it loads only under an interactive claude.ai login,
so a run that leaned on one could never be reproduced headlessly, and a pass could come from a
server the plugin never declared. Nothing falls back to it: there is no `claude mcp list`
preflight, no `canonical_tool_name`/`expand_tool_aliases` normalization, and
`build_strict_mcp_config` returns None only when a plugin declares no server at all.

Auth comes from `MCP_<SERVER>_API_KEY` in the environment, or from
`MCP_<SERVER>_CLIENT_ID`/`_CLIENT_SECRET` which `mcp_oauth.py` exchanges for a short-lived token
(discovering the endpoint via RFC 9728 → RFC 8414, Basic auth and no scope by default because
that is what real connectors accept). A minted token is published to the **child process env** so
the config on disk still holds only `${VAR}` — both spawn sites (harness and agentic judge) apply
the overlay, and missing the judge would fail the grader that checks the numbers. The
variable is **per server, with no global fallback**: a plugin can declare two vendors' servers,
and one shared key would hand each vendor the other's credential. A server with no credential is
still passed through to `--strict-mcp-config`, just without an `Authorization` header — hiding it
would change what the plugin under test receives. **A bad, expired, or missing token surfaces as
`tool_used` "called 0×", not as an auth error, and nothing preflights it.** Check the token
before blaming the skill — and check the server-name *case* second. `_grade_tool_used` matches
with `fnmatch.fnmatchcase`, so a grader written `mcp__acme__*` never matches a server declared
`Acme`, and the failure looks identical to bad auth.

`MCP_<SERVER>_API_KEY` is sent verbatim as `Authorization: Bearer`, and nothing probes the
server to find out what it wants. That is why it works for vendors whose "API key" is
bearer-acceptable and fails for anything else: a vendor wanting `X-Api-Key`, or a bearer-only
OAuth endpoint, needs its own `headers` block in the case's `mcp_config` — `_inject_bearer`
skips any server that already sets `Authorization`. Which of the two paths runs is decided
purely by **which env vars exist**, never by asking the server: a static key present makes
`mintable()` false, so it always wins and no network call happens. Worth knowing before
reaching for the OAuth path: `client_credentials` is not universal, and a vendor whose
authorization server omits that grant cannot be minted for at all.

**A behavioral run is NOT isolated from the operator's own Claude Code config.** `--plugin-dir`
adds the plugin under test; it does not subtract anything. User-level plugins and skills in
`~/.claude` load as well, so a case can be satisfied by tooling that is not in the plugin under
test — verified, not theorised: a case written against a vendored plugin's MCP server was
scored 1.00 by a run that invoked a *user-installed* plugin's skill to do the work. The plugin
under test contributed nothing. The score was real; the attribution was wrong. Read a local
green as "the assertion held on this machine", and expect a clean-home CI run to reach it by a
different route or not at all. When a behavioral score matters, check the transcript's
`tool_use` names against what the plugin actually ships.

### 100xdrift-check — cross-plugin drift review

**Nothing in `skills/` reviews anything.** The plugin exposes exactly two installer skills;
the reviewer and the workflow live under `templates/` and are copied into the *user's* repo:

| Plugin path | Installed to | By |
| --- | --- | --- |
| `templates/skills/drift-check/` | `.claude/skills/drift-check/` | `install-skill` |
| `templates/workflows/drift-check.yml` | `.github/workflows/drift-check.yml` | `install-workflow` |

`install-workflow` installs the reviewer too **if absent**, and deliberately does not
refresh an existing copy — refreshing is `install-skill`'s job, so a repo that edited its
vendored copy keeps it. A file added under `templates/` is a file written into someone
else's repo.

**The vendoring is load-bearing, not a convenience.** The Action starts a bare Claude Code
session with no plugins installed, and the plugin ships no reviewer skill of its own, so
the workflow's `/drift-check` prompt resolves against the vendored copy or nothing at all.
It also pins the contract to the commit under review. The cost: the copy goes stale
silently, and in the consuming repo anyone who can open a PR can edit it.

This repo does **not** vendor a copy — `.claude/skills/` carries only the two `-concepts`
skills, which explain the tools rather than operate them. To try the reviewer here, install
it into a scratch repo, or use the fixture under `examples/plugin-drift-check/`.

`templates/skills/drift-check/SKILL.md` and `templates/workflows/drift-check.yml` are **one
contract split across two files**. The skill writes `drift-report.md` whose first line must
be `<!-- drift-status: critical|warning|good -->`; the workflow's `github-script` step
parses that marker to pick the comment's icon and headline, and classifies marker-less
skip/fallback notes itself. Change the vocabulary in one file without the other and every
report silently degrades to "warning".

The tool allowlist lives in the **workflow**, never in the skill — permissions belong to the
caller.

**Scope is one repository and there is no setting for it.** Siblings are the repo's other
plugins; the reviewer never reads `../`, never clones, never fetches. What counts as a
reviewable file is the workflow's `paths:` list — the single scope knob, which the reviewer
reads rather than assuming. That list and the `git diff -- '<pathspec>'` in the collect step
must change together; if they disagree, the job runs and finds nothing.

The workflow is not active in this repo — it is a template for repos that install it.

**No `disable-model-invocation` on these skills**, though all three want it: three SKILL.md
files carrying that one line read as duplication to `token_efficiency`, which counts
frontmatter. Re-add it together with a fix excluding frontmatter from that metric.

### 100x-continuity — a factory that builds a team's session handoff

**It is not a handoff plugin. It is the thing that writes one.** An Operator installs it
in Claude Code, answers questions about their team and their storage, and it emits a
**Kit** — a tailored plugin, with the store baked in, written into *their* plugin repo
with its marketplace row. Their Teammates install the Kit and use it in Cowork; they never
see this. Everything below follows from that one fact. `plugins/100x-continuity/CONTEXT.md`
is the glossary: Factory, Kit, Emit, Plan, Operator, Teammate, Handle, Bundle, Store.

Missing the factory framing is the single most expensive mistake here. `skills/` holds
`set-up-handoff`, `verify` and `store-service` — none of them hand anything over. The
skills a person actually talks to (`hand-off`, `pick-up`) live under `templates/kit/` and
exist only inside emitted Kits, the same split 100xdrift-check uses for its reviewer.

**One entry point, and Plan and Emit are phases rather than skills.** They were two skills;
the chain then had a step nobody started. In the first real run `verify` was named four
times and never performed, and the Operator ended up asking how to test any of it — so
`set-up-handoff` runs interview → plan → approval → write → verify, and its self-check says
`verify` was *run*, not offered. `verify` stays separately invokable because "a teammate
says pick-up is broken" must not re-interview anyone. See `docs/adr/0001-one-setup-skill.md`.

| Factory path | Becomes, in the Operator's repo |
| --- | --- |
| `templates/kit/**` | the Kit's manifest, README, two skills, two references, `tests/`, `evals/` |
| `scripts/run.py`, `scripts/engine/*.py` | the Kit's own copy of the engine |
| `templates/kit/fragments/*.md` | spliced into the skills; never copied as files |
| `scripts/emit.py` | stays here — the only factory-side module |

**Emitting is a script, not a copy-and-substitute done by hand** (`scripts/emit.py`,
`tests/test_emit.py`). A skill copying twenty files and filling placeholders does it
slightly differently every run, and the difference surfaces in a Teammate's session weeks
later. Four rules it owns:

- **Placeholders are all-or-nothing.** One unfilled `{{TEAM}}` aborts the write. A
  placeholder that reaches a Kit still loads and still instructs the model, silently.
  Fragments are rendered *before* being spliced, because substitution is a single pass and
  a value carried in by a fragment would otherwise never be filled.
- **A Kit describes one store.** The passages for the other are never copied in — a skill
  offering two routes invites the model to try the one that team never set up.
- **`source` in the marketplace row is relative to the repo root.** Getting it wrong
  yields a manifest that validates and an install that finds nothing.
- **A non-empty directory with no `kit.json` is refused**, and the marketplace path is
  resolved *before* any file is written, so a wrong `--into` cannot leave half a plugin in
  someone's repo.

**`kit.json` is the whole point of the config tier.** Precedence is flag › environment ›
**kit** › config file › default, so a Teammate who configured nothing gets the team's
store and an Operator debugging can still override. `root` is stored with `~` unexpanded:
a Teammate's home is not the Operator's, and the part after it usually is the same. The
file's presence is also how a re-emit tells a Kit from somebody else's plugin.

**A publication is one immutable bundle plus a marker.** `bundle.zip` holds
`manifest.json` + `start-here.html` + `transcript/` + `artifacts/`; `publication.json`
sits beside it and is written **last**, so an interrupted publish leaves a directory every
reader skips rather than a publication that looks small. Inside the archive the manifest
is likewise the last member. `page.py` renders the landing page — self-contained HTML, no
script and no network, because it is opened straight from a synced folder.

**The manifest describes content and nothing else** — no timestamp, no source path, no
store. Those are facts about a *publication*, and keeping them out is what makes bundles
**reproducible**: the same conversation and files pack to identical bytes, so a republish
of unchanged work is recognised as the publication it already is (`already_published`)
instead of filed twice. A publication id is `<stamp>-<sha12>`, so changed work lands
beside its predecessor and nothing is ever rewritten — conflict copies in a synced folder
are structurally impossible rather than resolved after the fact.

**Store paths are human-readable on purpose.** `<root>/<namespace>/<session>/<publication>/`
— because the handoff *is* a path a person pastes, so an opaque digest tree would make the
product unusable. The tradeoff is stated in the skills rather than engineered away: a
folder store has **no access control at all**, and redaction is its only boundary.

**Two store kinds, and `s3` is deliberately not one of them.** `folder` is a directory a
sync client watches — verified working inside Cowork, where a Teammate's granted drives
appear under `~/mnt/`. `service` is object storage behind an MCP server the *Operator*
runs and registers with their org, which mints presigned URLs — so a Kit still holds no
credential and still cannot list or read back what it PUTs. `config.check_store_kind`
rejects `s3`/`minio` by name pointing at that path, because it is the wrong shape rather
than a missing feature. `wire.py` holds the URL refusals (https only, no credentials, no
redirects, optional host pin) once for both directions; a second copy is how one of them
becomes the lenient one.

**Every failure carries two strings.** `say` is one plain sentence for a Teammate; `hint`
is the engine's own wording for whoever maintains it. The Kit skills are told to repeat
`say` and never `hint`, because relaying `hint` verbatim is how *transcript* and *bundle*
reached people who had never heard of either — measured at 0/3 before the split existed.
`_plain()` in `cli.py` is deliberately lossy: anything it cannot map collapses to "that
didn't work, and nothing was sent", because a vague true sentence beats an exact one full
of words the reader has no use for.

**Artifacts travel verbatim and are scanned, never rewritten.** They are files a person
composed, so `bundle.py` fails closed instead: a credential-shaped value inside a text
artifact stops the publish by name, a credential-shaped *filename* is refused outright,
and a non-text file is reported `unscanned` rather than clean. Reading is the mirrored
problem — a bundle arrives from someone else, so every member is validated (inside the
known directories, no absolute paths, no `..`, no links or devices, no Windows drive or
backslash shapes, size and count capped) before a byte is written to disk. The zip
metadata carries no file-type bits unless written with them, so `_safe_members` checks
`stat.S_IFMT` only when present and refuses anything that is not a regular file.

**`pick-up` never guesses which publication you meant.** There is no "most recent
publish" fallback and no index session: a handle or a publication id is always required.
An index would be one more file two machines can disagree about inside a synced folder,
and the directory tree already holds the answer.

**Inside Cowork, `${CLAUDE_PLUGIN_ROOT}` may not resolve.** The base path a skill is told
it has does not exist there; the files are reachable under
`~/mnt/.remote-plugins/plugin_<id>/`. Both Kit skills try the advertised path first and
fall back to that one, scoped to `.remote-plugins` — never a search across `~/mnt`, which
also holds the team's synced drives.

`transcript.py`, `digest.py`, `redact.py` and the presigned-PUT logic came from the
retired 100xcontinuity rather than being shared with it (invariant 1) — the fixes there
were hard-won, and the copy was the point. One difference: `identify()` here reads
**`aiTitle`**, the field the host actually writes; reading `title` alone returned None for
every real session, silently.

`redact.py`'s patterns look like `100xeval`'s `SECRET_PATTERNS` and must not be merged
with them: the linter optimizes for **precision** (a false positive costs a plugin its
security sub-score), the redactor for **recall** (redacting a placeholder costs nothing,
missing a credential costs everything).

`templates/store-service/` is a FastMCP server implementing the service-store contract
— two tools plus listing and access, ownership from the verified principal, server-chosen
keys, a per-publication reader list — with a Dockerfile and no deploy recipe, because
where it runs is the Operator's. `principal()` fails closed without a verified identity.
It is a starting point the user owns, and it is on the trust-boundary list.

**Two test layers, and only one of them gates anything.** `templates/kit/tests/contract_test.py`
ships *inside* every Kit: deterministic, no model, no money, driven from a synthetic session
in a throwaway `HOME` because packing a real conversation would put it in the store. It
branches on `kit.json` and skips the half its store does not have, so a folder Kit and a
service Kit each report what they actually proved. CI emits a Kit and runs it. The Kit's
`evals/` are `claude plugin eval` cases about what the *model* does with the two skills;
they cost money, gate nothing, and exist for the failures a contract test structurally
cannot see — a skill that fires on the wrong words, or leaks internal vocabulary.

That split came from a real run: the contract test found that `fetch` never checked the
digest the store reported, and the eval cases found the two prompt defects. Neither tool
would have found the other's.

The **repo's own** `evals/` need the sibling 100xeval plugin, so they are repo-only and not
part of what a marketplace install operates. They cost money and are not in CI. Their
graders read the **emitted Kit and the store**, not the transcript — and any case built
mainly from absence assertions needs one positive assertion too, or a run that never
happened scores well.

## Adding a plugin

1. `plugins/<name>/` with `.claude-plugin/plugin.json` and a `README.md` — CI's manifest job
   fails if a plugin is missing from `.claude-plugin/marketplace.json` or vice versa, and
   `ST1` fires without the README.
2. Keep it self-contained (invariant 1). Tests beside the runtime payload, not inside it.
3. Run the static check — it must score 1.00 before merge.
4. Optionally add `docs/<name>/` to the OKF bundle, and list it in `docs/index.md`.

## Gotchas

**Secret-shaped strings in test fixtures must be assembled at run time** (see
`tests/test_lint.py`), or the linter permanently flags its own fixtures and the security
sub-score becomes noise nobody reads.

**Linter checks earn their place by catching something probably wrong**, not something that
merely differs from a house style. The internal version's convention checks were dropped on
purpose. Every check needs a test asserting both directions: the dirty case fires and the
clean fixture stays clean.
