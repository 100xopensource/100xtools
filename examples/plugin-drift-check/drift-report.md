<!-- drift-status: critical -->

_Scope: this repository — 2 plugins searched._

---

> [!CAUTION]
> **Changed in acme-north: `plugins/acme-north/skills/weekly-report/SKILL.md`**
>
> **Action required** — port this to acme-south; it needs its own pull request.
>
> **The change** — under `## Window`:
>
> ```diff
> - Sum every order from **the last 7 days ending today**, inclusive.
> + Sum every order in the **ISO week, Monday to Sunday**, inclusive. Label the report with
> + that week's ISO week number.
> ```
>
> The window moved from a rolling 7 days to the ISO week, labelled with an ISO week number.
>
> | sibling plugin | sibling file | matched on | verdict | why (one line) |
> | --- | --- | --- | --- | --- |
> | acme-south | `skills/weekly-report/SKILL.md` | Same skill name and path; near-identical frontmatter description | likely-applies | Carries the same rolling-7-day window and the same double-count on the run day |
>
> **To copy it across:** make the same edit above in South's file, under its own `## Window` —
> the two lines are identical today.
>
> > South carries a rule North has no equivalent of — _"South runs Sunday trading, so a store
> > with no Sunday row is missing data rather than closed."_ Keep it; this fix does not touch
> > it.

---

> [!WARNING]
> **Changed in acme-north: `plugins/acme-north/agents/reconciler.md`**
>
> **Alert** — read acme-south's copy before merging: it conflicts with this change. Nothing
> to port.
>
> **The change:**
>
> ```diff
> - Match each report row to a ledger row on the report's **end date**, then report the
> + Match each report row to a ledger row on the report's **ISO week number**, then report the
>   variance per store. A store missing from the ledger is a variance, not a zero.
>  
> + Joining on the end date broke whenever a report was re-run a day late: the same week
> + produced two different keys. The week number is stable whatever day you run it.
> ```
>
> The reconciler now joins on the ISO week number instead of the report's end date.
>
> | sibling plugin | sibling file | matched on | verdict | why (one line) |
> | --- | --- | --- | --- | --- |
> | acme-south | `agents/reconciler.md` | Same agent name and path; same role — reconciles the weekly summary against `ledger.weekly` | conflicts | South keys ledger rows `<store>-<end-date>` and rejects colliding keys — ISO week numbers repeat across years |
>
> **Nothing to copy across.** South's own file rules out exactly this change — _"The end date
> is the only join key, and it must stay one … an ISO week number is not unique across years
> and would collide on every rollover — never label or join on one."_ Copying it would break
> South's loader. North's change is safe in North only because North's ledger has no such rule.

---

> [!WARNING]
> **Changed in acme-north: `plugins/acme-north/commands/export-csv.md`**
>
> **No action** — acme-south names exports differently on purpose.
>
> **The change:**
>
> ```diff
> - Name the file `orders-<YYYY-MM-DD>.csv`, where the date is **the day the export runs**.
> + Name the file `orders-<YYYY-MM-DD>.csv`, where the date is **the Monday of the ISO week the
> + report covers**. Two exports of the same week now land on one filename instead of two that
> + differ only by which day someone happened to run them.
> +
>   Write it to `./exports/`, creating the directory if it is missing.
> ```
>
> The export filename now uses the covered week's Monday instead of the run date.
>
> | sibling plugin | sibling file | matched on | verdict | why (one line) |
> | --- | --- | --- | --- | --- |
> | acme-south | `commands/export-csv.md` | Same command name and path; same role — exports the weekly summary to CSV | different on purpose | South names by fiscal period and writes one file per store, because finance ingests it that way |
>
> **Nothing to copy across.** South's naming is deliberate and something else depends on it —
> _"Finance ingests these by period code and one file per store; a date-named single file is
> rejected by the loader."_

---

_Advisory only — reviewers decide apply/ignore per sibling. Legitimate variation is
expected._
