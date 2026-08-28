# Eval cases for {{KIT_NAME}}

These cases check what the *model* does with this plugin: whether the skills fire on the
words a person actually uses, stay quiet on the words they don't, put a credential decision
in a pop-up, and keep internal vocabulary out of the chat. The table below is the list
this plugin actually carries.

{{EVAL_INVOCATION}}

These cost money and need a model, so nothing runs them for you — which is exactly why
they are also on your setup board with the whole command on the card, rather than left as
a directory somebody might notice. **`tests/contract_test.py` is what gates a release** — it is deterministic, free, and covers the mechanics. Run these when a
skill's wording changes, which is the only thing they can catch that the contract test
cannot.

| Case | Pins down |
| --- | --- |
{{EVAL_TABLE}}

## What this harness cannot reach

Worth knowing before you read a green run as proof, because both of these are properties
of the runner rather than of this plugin:

- **There is no conversation in the sandbox.** Each run gets a throwaway home, so the
  engine finds no session to package and `hand-off` stops at its own session check. Nothing
  past that point — choosing files, the scrub, the credential stop, the code coming back —
  is exercised here. `tests/contract_test.py` covers those mechanics; what stays unproven
  is the *model's* judgement inside them.
- **A store that answers but has lost the bytes cannot be set up here.** A publication
  whose row exists and whose object is gone needs a live server holding that state, and
  the sandbox cannot stand one up. It is the failure that reported the wrong half of the
  exchange as broken, so it is covered in `tests/contract_test.py` with the transport
  stubbed instead.
- **`AskUserQuestion` is not offered to a headless run.** So the rule that a
  credential-shaped file goes to a pop-up rather than a line in the chat cannot be scored
  at all. It is a real rule and it is written into the skill; it is simply not observable
  from here.

Neither is a reason to skip these cases. Routing, refusals and wording are most of what
goes wrong in a skill, and all of it is visible.

Edits in this directory are build output. The next run of the factory overwrites them. Fix
a case in the factory, then emit this plugin again.
