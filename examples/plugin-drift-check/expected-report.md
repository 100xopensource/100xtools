<!-- drift-status: critical -->

_Scope: this repository — 2 plugins searched._

### plugins/acme-north/skills/weekly-report/SKILL.md

The window moved from a rolling 7 days to the ISO week, and the report is now labelled with
an ISO week number.

| sibling plugin | sibling file | verdict | why (one line) |
| --- | --- | --- | --- |
| acme-south | skills/weekly-report/SKILL.md | likely-applies | Carries the same rolling-7-day window and the same double-count on the run day |

```
- Sum every order from **the last 7 days ending today**, inclusive.
+ Sum every order in the **ISO week, Monday to Sunday**, inclusive. Label the report with
+ that week's ISO week number.
```

### plugins/acme-north/agents/reconciler.md

The reconciler now joins on the ISO week number instead of the report's end date.

| sibling plugin | sibling file | verdict | why (one line) |
| --- | --- | --- | --- |
| acme-south | agents/reconciler.md | conflicts | South keys ledger rows `<store>-<end-date>` and rejects colliding keys — ISO week numbers repeat across years |

Porting this would break South's loader. The two regions need different join keys, and the
North change is only safe because North's ledger does not have that constraint.

### plugins/acme-north/commands/export-csv.md

The export filename now uses the covered week's Monday instead of the run date.

| sibling plugin | sibling file | verdict | why (one line) |
| --- | --- | --- | --- |
| acme-south | commands/export-csv.md | sibling-specific | South names by fiscal period and writes one file per store, because finance ingests it that way |

_Advisory only — reviewers decide apply/ignore per sibling. Legitimate variation is
expected._
