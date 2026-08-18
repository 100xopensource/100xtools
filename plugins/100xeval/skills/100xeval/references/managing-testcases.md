# Managing testcases — add, edit, delete, and get them right

The lifecycle of a `case.yaml` and the practices that make a case worth keeping.
Field-by-field reference: [`case-schema.md`](./case-schema.md).

**Contents**
- [Add a testcase](#add-a-testcase)
- [Edit a testcase](#edit-a-testcase)
- [Delete a testcase](#delete-a-testcase)
- [Best practice: what makes a good case](#best-practice-what-makes-a-good-case)
- [Coverage: the five dimensions](#coverage-the-five-dimensions)
- [The ground-truth SQL pattern](#the-ground-truth-sql-pattern)
- [Reading a red scorecard](#reading-a-red-scorecard)
- [Before you spend: preflight the endpoint](#before-you-spend-preflight-the-endpoint)
- [Cost, and where it goes](#cost-and-where-it-goes)
- [Gotchas that have actually bitten](#gotchas-that-have-actually-bitten)

## Add a testcase

```bash
RUN="${CLAUDE_PLUGIN_ROOT:-plugins/100xeval}/skills/100xeval/scripts/run.py"
python3 "$RUN" init <case-name> --plugin plugins/<plugin> --tag <skill> --prompt "<question>"
```

That writes `evals/<case-name>/case.yaml` with a `tool_used` + `llm` stub. Then:

1. **Paste the prompt verbatim.** If it came from a user, keep their wording, including
   the imprecise bits — resolving "Billing EU" to the canonical
   `Billing - EU` is the skill's job, and a tidied prompt stops testing that.
2. **Fix `plugins`** — relative to the case dir (`../../plugins/<name>`). The loader
   fails the case if the path doesn't resolve, so a typo surfaces immediately.
3. **Tag it** with the skill under test plus a suite tag, so `--tag <suite>` runs the
   whole set and `--tag <skill>` runs one skill's cases.
4. **Write the graders** from the success criteria, one grader per claim
   (see [best practice](#best-practice-what-makes-a-good-case)).
5. **Validate it loads before running anything** — cheap, and catches YAML mistakes
   before you spend a run:

   ```bash
   python3 -c "import sys; sys.path.insert(0,'plugins/100xeval/skills/100xeval/scripts')
   from engine import loader
   cases, errs = loader.load_all('evals')
   print('errors:', errs or 'none')
   for c in cases: print(' ', c.name, c.label(), [g.name for g in c.graders])"
   ```

6. **First run is a debugging run.** Budget for it: `--runs 1` and read the transcript.
   This is not a caution, it is the measured norm — across the first pass of six cases,
   *every* new case failed on its own mistakes (wrong table, ungranted tool, over-strict
   criteria, an off-by-one date bound) before it tested the skill at all. See
   [Reading a red scorecard](#reading-a-red-scorecard).

**Every scenario a user reports should become a case** — that is how the corpus grows
and how a fixed bug stays fixed.

## Edit a testcase

Just edit the YAML; nothing is generated or cached. Two rules:

- **A run already in flight is unaffected.** Cases are loaded into memory when the run
  starts, so editing mid-run changes nothing about the results you are waiting for. The
  run's own `cases.json` records the exact case as executed.
- **Re-validate after editing** with the loader snippet above. The most common breakage
  is a flow collection accidentally wrapped onto a second line.

Changing a grader changes what the corpus asserts. Note *why* in a comment — a future
reader needs to know whether a loosened tolerance was a real decision or a way to make
red go green.

## Delete a testcase

**Prefer parking it to deleting it.** A non-empty `skip:` excludes the case from runs
and prints the reason on every invocation, so the scenario and the why both survive:

```yaml
skip: "report build exceeds the run timeout; needs a longer execution.timeout_s"
```

Only actually delete when the scenario is obsolete:

```bash
rm -rf evals/<case-name>/
```

Nothing else references it — no index, no registry. But deleting a case deletes the
regression it guards, so prefer alternatives:

- The scenario is obsolete (the feature is gone) → delete, and say so in the PR.
- The case is flaky → fix the case (pin the period, tighten the prompt), don't delete it.
- The case fails because the skill is wrong → that's the eval working. Fix the skill.

Never delete a case to make a suite green.

## Best practice: what makes a good case

**One claim per grader.** "Correct and well presented" is two graders. When a case fails
you want the scorecard to say *which* property broke, not just that something did.

**Assert the query shape, never a figure.** `tool_used` with `input_match` survives next
week's data; a hard-coded number is a scheduled false failure. When you truly need the
number, use the [ground-truth pattern](#the-ground-truth-sql-pattern) so the value is
recomputed each run rather than frozen in the case.

**Keep `runs: 3`.** Skills are non-deterministic. A single run reports a coin flip as
fact — one observed case answered `0.148×` (correct) on one run and `0.24×` (62% off) on
the next, with identical input. At `runs: 3` that reads as a 33% passRate, which is the
truth. Drop to `--runs 1` only for debugging a case, not for judging a skill.

**Write criteria as checkable sentences.** "Good analysis" is not gradeable. "Reports
every figure the question asked for, names the period used, and says so plainly if the
team is out of scope" is.

**Grade what the requester asked for.** If you add a stricter grader of your own, say so
in a comment — a case that fails on a rule nobody agreed to wastes everyone's time.

**Record provenance** in `description`: who asked, which ticket. Cases outlive the
conversation that produced them.

## Coverage: the five dimensions

Anthropic's enterprise skill guidance asks for 3–5 queries per skill spanning *should
trigger*, *should NOT trigger*, and *ambiguous*, across five dimensions. A suite that
only ever asks well-formed in-scope questions is not testing much:

| Dimension | The case to write |
| --- | --- |
| Triggering accuracy | A question the skill **should** answer. |
| Isolation | A question it should **refuse** — e.g. another portfolio company. Assert `tool_used` `min: 0, max: 0` plus a judge that no figures were given. |
| Coexistence | A question a **sibling** skill owns, to prove this one doesn't steal it. |
| Instruction following | A question exercising a documented business rule (a filter, a defined week, a required disclaimer). |
| Output quality | Presentation: citation, table shape, disclaimer, no internal names leaking. |

## The ground-truth SQL pattern

For accuracy, put the **exact SQL in the criteria**. Do not let the judge write its own:
with `--judge-votes 3` you get three different queries and the "ground truth" itself
moves, so a failure tells you nothing.

```yaml
  - type: llm
    name: figures-match-ground-truth
    focus: last_message
    allowed_tools: [mcp__Acme__run_query]
    criteria: |-
      Load the ground truth by running EXACTLY this SQL, unmodified, and use ONLY
      its result as the truth. Do not write your own query.

      SELECT queue, COUNT(*) AS tickets
      FROM acme.ai_semantic.unified_mart_tickets
      WHERE company = 'Acme'
        AND queue = 'Billing - EU'
        AND CAST(created_at AS DATE) >= DATE_TRUNC('week', CURRENT_DATE - INTERVAL '1 week')
        AND CAST(created_at AS DATE) <  DATE_TRUNC('week', CURRENT_DATE)
      GROUP BY queue

      PASS only if the answer's figure matches within 5 percent.

      If the query errors, reply FAIL and quote the error verbatim, so the case
      can be fixed rather than silently passing.
```

Why each part:

- **`|-` block scalar** so the SQL stays readable and keeps its newlines.
- **"EXACTLY … unmodified"** — the judge's system prompt reinforces this, but say it in
  the criteria too.
- **A tolerance** — rounding differences are not defects.
- **"quote the error verbatim"** — this is what turns a wrong query into a fixable
  message instead of a silent, meaningless FAIL.

**Verify the SQL before trusting it.** Hand-written SQL is usually wrong the first time.
The cheapest source of correct SQL is the skill's own successful run: run the case once,
read `runs/<id>/<case>/run-1/result.json`, and lift the queries it actually executed. One
hand-written query was wrong four ways at once — a team name missing its dash, a column
that didn't exist, a table in the wrong catalog, and the current partial week instead of
the completed one.

**Do NOT trust the plugin's own docs for table names.** A ground-truth query copied
straight out of `askmarketing/SKILL.md` failed every vote with `TABLE_OR_VIEW_NOT_FOUND`
— the documented table doesn't exist in the warehouse. Live queries are ground truth;
skill documentation is a hypothesis.

**Make the judge infer as little as possible.** Every step you leave to it is a place two
runs can diverge. One case asked the judge to match ~77 queue names to a
20-team map, filter to one region, sum each group, then compare 20 totals. It scored
0/3 with *contradictory* evidence: 0.09% agreement on a cluster in one run, +4.5% on the
same group in another. Fixing it meant putting the queue list literally in the SQL and
checking **one** cluster end-to-end. One thing verified deterministically beats twenty
verified by inference — coverage is a different grader's job.

**Get the period bounds right, and say which they are.** If the prompt names no period,
the skill picks one, so the ground truth has to follow the answer rather than a fixed
week — use `<FIRST_DAY>`/`<LAST_DAY>` placeholders and tell the judge to read them off the
answer. Then be explicit about inclusivity: a `<` end bound against an answer reporting
"Jul 5 – Aug 1" silently drops Aug 1. That one-day gap read as a consistent **+4.5%
error** and looked exactly like a skill bug. Prefer `>=` and `<=`, and say "inclusive" in
the criteria.

**Read the dissent.** The off-by-one above was invisible in the majority verdict — all
three runs "failed" with a plausible number. What exposed it was a single minority vote
reporting a ground truth that matched the answer *to the dollar*, which meant the two
sides were querying different windows. The scorecard preserves minority reasons for
exactly this reason; read them before believing a unanimous-looking failure.

## Reading a red scorecard

Measured over the first full pass of six cases: **case defects outnumbered skill defects
roughly three to one.** Before reporting a failure as a skill bug, rule yourself out.

| Symptom | Look here first |
| --- | --- |
| Every grader fails, answer is an error message or empty | Infrastructure. Preflight the MCP endpoint (below), check `result.json` for `error`, check the debug log for `403`/`401`. |
| Judge says it "cannot access the data" / asks permission | The judge's own config, not the skill. Agentic judges need the case's MCP; a refusal is a harness problem. |
| `tool_used` says a tool was called 0× | Was it in `allowed_tools`? A denied tool sends the skill down an error path that reads like a defect. |
| Ground-truth grader fails with a query error | Your SQL. The criteria are written to quote the error verbatim — read it. |
| A consistent percentage gap | Suspect the window or the row set before the skill's arithmetic. Compare *which* rows each side counted. |
| Verdicts contradict each other across runs | You left something to judge inference. Make it literal. |
| Answer is right but graded wrong | Your criteria assert something the prompt never asked for. |

**A `not_contains` regex passes vacuously on an empty answer.** When a run timed out and
produced nothing, `no-internal-leak` reported 100% — absence of output is absence of the
pattern. Never read a lone `not_contains` pass as evidence; pair it with a grader that
requires content (a `tool_used` minimum, or an `llm` criterion).

**Non-determinism is the thing you are measuring.** The same prompt produced `0.148×`
(correct) and `0.24×` (62% off) on different runs of one case, and the failure rate moved
between 1-in-3 and 2-in-3 across sessions. A single run reports a coin flip as a fact.
This is the entire argument for `runs: 3`.

**Some scenarios are the wrong shape for a testcase.** A full report build — 11 datasets,
HTML, Excel — exceeded the run timeout, and raising the budget only buys a case too slow
and costly to run before a merge. If a scenario's criteria can be tested by a narrower
question (segment names and column contracts don't need the artifact built), write that
instead. Park the original with `skip:` rather than deleting it.

## Before you spend: preflight the endpoint

Three separate sessions lost runs — and real money — to auth and network problems that
looked like skill failures. The runner's built-in preflight only checks `claude mcp list`,
which strict `mcp_config` mode deliberately skips, so a blocked endpoint isn't caught
until every run has finished scoring zero.

```bash
set -a && . ./.env && set +a
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H "Authorization: Bearer $MCP_ACME_API_KEY" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"preflight","version":"1"}}}' \
  <the plugin's MCP url>
```

Read the code, not just the failure: **200** good · **403** with an nginx HTML body =
your egress IP isn't allowlisted · **401** `invalid_token` = the token is missing or
expired. Claude Code reports the 403 as "Server rejected the configured Authorization
header", which points at the token and is misleading — check the raw body.

## Cost, and where it goes

Judging is a real spend, not a rounding error: on one case the judges cost **$1.48**
against **$2.96** of runs. `runs: 3` × an agentic grader × `--judge-votes 3` is up to nine
extra `claude` invocations per case. Reports break this out (`Run $ / Judge $ / Total $`)
so a suite's true cost is visible.

Token counts are dominated by **cache reads** — a surface entrypoint can be a ~250 KB system
prompt, so a run shows a few hundred input tokens against millions of cached ones. That is
expected; watch output tokens and cache *writes* for anything anomalous.

Practical budgeting: one behavioral case at `runs: 3` lands around **$3–5** all-in. A
first debugging pass at `--runs 1` is the cheapest way to find the case bugs that would
otherwise be found three times over.

## Gotchas that have actually bitten

**Grant every tool the plugin really uses.** `allowed_tools` is a whitelist; anything
missing is denied mid-run. A skill's init gate calling `get_all_semantic_datasources`
gets blocked, and the failure looks like a skill defect. If the plugin ships the whole
MCP server, the case should generally grant its read tools — while leaving out anything
that **writes**, which an eval has no business calling.

**Name MCP servers so tool names match in both modes.** Local runs use the account
connector (`mcp__claude_ai_Acme__…`, canonicalized to `mcp__Acme__…`); strict mode
uses the case's config. Naming the server `Acme` in the case's `mcp-config.json` makes
one set of grader tool names work either way, even though the plugin ships it under a
different key.

**Team names and other identifiers have canonical spellings.** `Billing EU` in
the prompt, `Billing - EU` in the warehouse. Use the user's spelling in the
prompt and the canonical one in ground-truth SQL — and say so in the criteria, so the
judge doesn't "helpfully" fix your query.

**Flow collections must stay on one line** (`allowed_tools: [...]`). Wrapping one across
two lines breaks the parser for every case in the directory at once.

**Secrets never go in a case.** `mcp_config` stores a **path**, and the config it points
at uses `Bearer ${MCP_<SERVER>_API_KEY}` — the literal placeholder, expanded from the
environment at run time by the CLI, never written to disk expanded. One variable per
server, named after the server (`Acme-Feedback` → `MCP_ACME_FEEDBACK_API_KEY`); there is
no key that covers every server.
