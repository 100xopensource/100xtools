---
description: Exports the North weekly sales summary to a CSV file.
---

# Export the weekly summary

Run the weekly report for Acme North, then write it to CSV.

Name the file `orders-<YYYY-MM-DD>.csv`, where the date is **the day the export runs**.
Write it to `./exports/`, creating the directory if it is missing.

Print the path you wrote and the row count. Never overwrite an existing file — if the name
is taken, stop and say so.
