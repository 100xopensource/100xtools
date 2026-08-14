# Behavioral eval cases for 100xcontinuity

Four cases that drive the skill end to end against a real store on disk. They exist to test
the **skill's judgement**, not the engine — the engine has 87 unit tests beside `scripts/`,
and a behavioral case that only re-checks the plumbing is a model call you paid for twice.

## The rule these cases follow

**Verify from the store, never from the transcript.** A model that replies "Saved!" and
wrote nothing must fail. So the load-bearing graders are `llm` in agentic mode with
`allowed_tools: [Bash]`, and their criteria name the exact commands to run against the
store directory. They are told to judge only on that output and to ignore the reply.

## Running them

Seed first — two cases start from a store that already holds something:

```bash
python3 plugins/100xcontinuity/evals/seed.py

python3 plugins/100xeval/skills/100xeval/scripts/run.py eval \
  --cases-dir plugins/100xcontinuity/evals \
  --concurrency 1 \
  --runs-dir /tmp/100xcontinuity-evals/.runs
```

`--concurrency 1` is deliberate. At the default of 4 the concurrent runners contend on
`~/.claude.json` and some lose the race, which surfaces as a run that never happened.

These cost real money (roughly $2–4 for the four) and are **not** wired into CI, matching
how this repo treats behavioral evals generally.

## The cases

| Case | What it proves | Runs |
| --- | --- | --- |
| `saves-a-summary` | A save request really reaches the store, and the reply doesn't overclaim cloud backup | 3 |
| `restores-an-earlier-session` | Work saved under an earlier session comes back, content intact | 1 |
| `unattributed-save-is-surfaced` | An unresolved session id still saves **and** the user is told | 1 |
| `evicted-artifact-is-not-empty` | A cloud-evicted blob is diagnosed as not-downloaded, not as empty, and is not overwritten | 1 |

The last two are the ones worth the money. Both test whether the SKILL.md prose actually
steers behaviour in a situation where everything "succeeds" and the user still loses.

## Two things learned the hard way

**Absence assertions pass when a run produces nothing.** `evicted-artifact-is-not-empty`
originally scored **0.75 on a run that never executed**: its `not_contains` regex matched
an empty message, and its "did you overwrite the store" check passed because nothing had
touched the store. Both were absence assertions, and absence is free when there is no
output. It now carries a positive `drove-the-engine` trace assertion so an empty run fails
loudly. Any case built mainly from absence checks needs one.

**The store is not reset between runs of the same case.** At `runs: 3`, a store-reading
grader passes on runs 2 and 3 once run 1 has written the artifact. Re-run `seed.py` between
comparisons when a per-run verdict matters, and read a 100% store-check on a multi-run case
with that in mind.

## Known flake: intermittent runner refusals

Save-shaped prompts through this plugin intermittently trip a runner-side safety
classifier. The run ends with `stop_reason: refusal` and the message *"Sonnet 5's
safeguards flagged this message"*.

It is a runtime issue, not a plugin or case defect, and it was characterised rather than
solved:

- The same command refuses on one attempt and completes on the next, with identical input.
- Rephrasing the content — removing the business framing entirely, then reflowing the
  prompt to a single line — did not help; both variants refused 3/3.
- The control matters most: `unattributed-save-is-surfaced`, which scored 1.00 in a clean
  run, later refused on 1 of 2 repeat attempts with a byte-identical prompt. So the trigger
  is not any one case's wording.

`saves-a-summary` therefore carries `runs: 3`, so the flake shows up as a partial passRate
rather than a hard red. On the runs that do complete, every grader passes — including the
agentic store check, which confirms `handover.md` really lands with the right content.

**The harness hides the reason.** A refusal reaches the report as `claude exited 1:` with
an empty message, which reads like a crash. The explanation is present in the runner's JSON
(`result`), it is just not carried into `result.json`. Worth fixing upstream in 100xeval.
