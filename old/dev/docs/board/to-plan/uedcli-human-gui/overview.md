+++
priority = "p?"
kind = "implement"
summary = "A human GUI over the trunk: uedcli serve + browser client, for interleaved human/AI editing and AI-change audit."
+++

# uedcli human GUI

An UnrealEd-like editor for humans, so a person and the AI can edit the same T3D trunk
interchangeably without exporting to `.dx`/`.unr` and reimporting. Its first purpose is **auditing
AI changes**: ask the AI to change something, then see exactly what changed, actor by actor.

Architecture: a `uedcli serve` HTTP/WS backend over the existing model-side library, and a browser
client. The client is thin (camera + GPU draw only); all model, solve, lighting, texture, diff, git
and snapshot logic stays in `serve`. This also keeps a desktop wrapper (Tauri/Electron) a later
packaging step, not a rewrite.

Phased. **P1 (this spec): read/audit only** — no editing, so no write path, lock, or merge. See
`spec.md`. P2 (editing) and P3 (git-feature layer) are sketched in the spec as scope boundaries, not
specified here.

Two owner rulings shaped this item (see `questions/` for the one still open):

- **GUI shows git, never drives it.** No in-app branch/worktree creation or merge — consistent with
  `direction/trunk-and-editor.md` ("git stays git, driven by the user"). The GUI visualizes git;
  the user drives it in the terminal.
- **Concurrency stays flock + refuse-same-actor-edit** (the standing `safety.md` rule); the GUI uses
  the same model-side write path, no GUI-specific concurrency. An atomic-chained-commands idea is
  parked in `questions/`.
