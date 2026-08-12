---
name: weekly-report
description: Builds the weekly sales summary for Acme North from the orders table. Use when someone asks for last week's numbers, the weekly summary, or the regional sales report.
---

# Weekly sales report — Acme North

Read the orders table at `reports.orders` and summarise the week.

## Window

Sum every order from **the last 7 days ending today**, inclusive.

## Output

A markdown table, one row per store, newest first, with a total row. Currency in whole
units, and name the currency in the header. Always cite the table and the window you used.

Refuse the request if it asks for a region other than North — each region has its own
plugin, and cross-region totals come from `reports.rollup` instead.
