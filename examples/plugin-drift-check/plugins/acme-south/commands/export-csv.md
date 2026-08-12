---
description: Exports the South weekly sales summary to a CSV file.
---

# Export the weekly summary

Run the weekly report for Acme South, then write it to CSV.

Name the file `orders-<period>-<store>.csv`, where `<period>` is the South fiscal period
(`P01`–`P13`) the report falls in, not a date. Finance ingests these by period code and
one file per store; a date-named single file is rejected by the loader.

Write it to `./exports/`, creating the directory if it is missing.

Print the paths you wrote and the row count. Never overwrite an existing file — if the name
is taken, stop and say so.
