# acme-north

Weekly sales reporting for the Acme North region.

| Component | What it does |
|---|---|
| `skills/weekly-report` | Builds the weekly summary from `reports.orders` |
| `commands/export-csv` | Writes that summary to a CSV file |
| `agents/reconciler` | Reconciles the summary against `ledger.weekly` |

Fiction, for the drift-check example. Nothing here connects to anything.
