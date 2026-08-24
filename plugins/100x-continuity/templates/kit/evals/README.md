# Eval cases for {{KIT_NAME}}

Six cases checking what the *model* does with this plugin: whether the skills fire on the
words a person actually uses, stay quiet on the words they don't, put a credential decision
in a pop-up, and keep internal vocabulary out of the chat.

```bash
claude plugin eval .
```

These cost money and need a model, so they gate nothing. **`tests/contract_test.py` is what
gates a release** — it is deterministic, free, and covers the mechanics. Run these when a
skill's wording changes, which is the only thing they can catch that the contract test
cannot.

| Case | Pins down |
| --- | --- |
| `hand-off-fires-on-natural-words` | routing from "hand this over to Dana" |
| `hand-off-stays-out-of-an-ordinary-write` | that saving a note does not package a session |
| `credential-file-stops-and-asks` | the stop happens, and in a pop-up |
| `pick-up-fires-on-a-pasted-code` | routing from a pasted code alone |
| `pick-up-explains-an-unknown-code` | a code that opens nothing invents nothing |
| `errors-stay-in-plain-words` | the failure path repeats `say`, never `hint` |

Edits in this directory are build output. The next run of the factory overwrites them. Fix
a case in the factory, then emit this plugin again.
