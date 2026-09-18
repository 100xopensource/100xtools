```mermaid
flowchart TD
    S["The session Alex is finishing"] --> H["hand-off"]
    H --> P["Package the conversation, a readable<br/>summary, and the files Alex names"]
    P --> R["Take out anything credential-shaped"]
    R --> M["Ask where to put it"]
    M --> SRV[["{{SERVICE_NAME}}<br/>the server your organisation runs"]]
    SRV -- "a one-time address, and the code" --> UP["Send the bytes straight there"]
    UP --> OBJ[("Your organisation's object storage")]
    H --> C(["One short code"])
    C -. "Alex sends Dana the code" .-> U["pick-up"]
    U --> Q["Ask what that code points at"]
    Q --> SRV
    SRV -- "a one-time address, and the digest to expect" --> DL["Read the bytes back"]
    DL --> OBJ
    DL --> V["Check what arrived against that digest"]
    V --> D["Dana carries the work on"]
```

Three things that diagram is trying to show:

- **The server hands out addresses, not contents.** The conversation goes straight between
  the machine and the storage. It never travels through the server, and it never travels
  through a tool result either.
- **The server decides who reads what.** A handoff is readable by the person who sent it
  until they share it. A refusal is an access decision, not a missing handoff — one message
  to the sender fixes it, and there is no other route to try.
- **The digest is what makes the read trustworthy.** The server says what it holds, and
  `pick-up` refuses anything whose bytes disagree. There is one bad read here, not two, and
  waiting never fixes it — nothing is syncing in the background.
