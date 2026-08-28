## {{KIT_NAME}} — handing a session from one person to the next

`{{KIT_SOURCE}}` is a plugin that lets somebody hand a Claude session to a colleague, and
lets that colleague pick it up. [100x-continuity]({{FACTORY_URL}}) {{FACTORY_VERSION}}
generated it for {{TEAM}} on {{EMITTED_AT}}.

{{STORE_SENTENCE}}

### What a person gets

Two skills, both driven by ordinary sentences rather than commands:

- `hand-off` — packages this conversation and the files named with it, removes anything
  credential-shaped, files it, and gives back one short code.
- `pick-up` — turns that code back into the conversation, a readable summary of it, and
  the files that travelled with it.

### Still yours to do

{{BOARD_NOTE}}
{{OPERATOR_TODO}}

### Driving it from your own code

The two skills are the surface for a person. Everything they do is one command-line
program underneath, so a script or a skill of yours can do the same without a model in
the loop:

```bash
{{ENGINE_COMMANDS}}
```

Every command prints JSON and exits non-zero when it fails. A failure carries an
`error` object rather than a finished sentence, because the right thing to say depends
on who is reading and which half of the exchange broke:

| field | what it is |
| --- | --- |
| `code` | one of the closed set below; branch on this, never on wording |
| `op` | the command that was running |
| `origin` | which part broke: `input`, `store`, `network` or `engine` |
| `fix_by` | who can act: `user`, `sender`, `operator` or `nobody` |
| `remedy` | that action, in ordinary words, safe to show a person |
| `hint` | this engine's own wording, for your logs and not for a chat |

{{ERROR_CODES}}

### Regenerating it

`{{KIT_SOURCE}}` is a build output. Re-running the 100x-continuity factory against this
repo rewrites every file in that directory and this section of this file, and touches
nothing else here. A change worth keeping belongs in the answers you give the factory,
not in that directory.
