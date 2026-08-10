---
type: tool
title: 100xeval
description: Behavioral and static evaluation for Claude Code plugins, answering whether a plugin actually gave the right answer.
resource: ../../plugins/100xeval
tags: [100xeval, evals, testing]
timestamp: 2026-08-10T00:00:00Z
---

# 100xeval

100xeval answers one question: **did this plugin actually give the right answer?**

Prompt changes have no compiler. A reworded instruction that quietly stops a skill from
filtering by store looks exactly like a change that broke nothing — until a user finds it.
100xeval is the thing that notices, by running the plugin for real and grading what came
back.

## Two layers

**Behavioral** actually runs the plugin against saved [eval cases](eval-case.md) with its
own MCP attached, then applies [graders](grader.md) to the result: did it query the right
data, present it correctly, get the numbers right. This costs money and needs credentials,
because it is a real model call.

**Static** scores plugin *design* with no model call at all — free, offline, no API key. It
walks the plugin, emits tagged findings, and folds them into a
[design score](design-score.md). This is the layer you can afford to run on every commit.

The two are independent. A plugin can be beautifully structured and give wrong answers, or
be a mess that happens to work. Static catches the first kind of problem cheaply; only
behavioral catches the second.

## Why cases, not assertions in code

A case is a folder with a `case.yaml`, not a test function. That is deliberate: the corpus
has to be editable by whoever hit the bug, and reviewable as a diff by whoever owns the
skill. Adding a scenario should not require touching Python.

## What it is not

It is not a general LLM eval framework. It grades Claude Code *plugins* — their skills,
their tool calls, their MCP servers. Benchmarking models is a different job with different
tools.

## See also

* [Eval case](eval-case.md) - the unit it operates on
* [Scoring](scoring.md) - how a run becomes a verdict
* [Plugin README](../../plugins/100xeval/README.md) - how to install and run it
