# Eval cases for {{KIT_NAME}}

These cases check what the *model* does with this plugin: whether the skills fire on the
words a person actually uses, stay quiet on the words they don't, put a credential decision
in a pop-up, and keep internal vocabulary out of the chat. The table below is the list
this plugin actually carries.

```bash
claude plugin eval .
```

These cost money and need a model, so they gate nothing. **`tests/contract_test.py` is what
gates a release** — it is deterministic, free, and covers the mechanics. Run these when a
skill's wording changes, which is the only thing they can catch that the contract test
cannot.

| Case | Pins down |
| --- | --- |
{{EVAL_TABLE}}

Edits in this directory are build output. The next run of the factory overwrites them. Fix
a case in the factory, then emit this plugin again.
