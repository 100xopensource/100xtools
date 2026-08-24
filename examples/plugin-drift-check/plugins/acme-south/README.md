# acme-south

Weekly sales reporting for the Acme South region. Copied from `acme-north` and since
adapted: South exports by fiscal period, and its ledger is keyed on the report end date.

| Component | What it does |
|---|---|
| `skills/weekly-report` | Builds the weekly summary from `reports.orders` |
| `commands/export-csv` | Writes one CSV per store, named by fiscal period |
| `agents/reconciler` | Reconciles the summary against `ledger.weekly` |

Fiction, for the drift-check example. Nothing here connects to anything.
