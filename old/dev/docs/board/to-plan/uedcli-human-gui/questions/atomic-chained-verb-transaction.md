# Atomic chained-verb transaction command — needed, and what shape?

## Context

Split out of `p2-editing-and-concurrency-model.md` (2026-09-20): that question's other two
decisions (human edit persistence; whether P2 shifts `direction/trunk-and-editor.md`) are answered
and folded into `spec.md` / `dev/docs/rationale/gui-editing.md`. This one stays open on its own.

The owner raised the idea of a uedcli command that runs a set of chained verbs as one transaction —
all-or-nothing, under one flock hold. Useful for both CLI and GUI. Standing principle: the GUI and
CLI must share one concurrency behavior — the GUI uses the same model-side write path + flock, no
GUI-specific concurrency. The standing rule stays flock + refuse-same-actor-concurrent-edit
(`safety.md`); no merge UI.

Not needed for `gui-p2-actor-translate-ctrl-drag` (P2's first slice) — a single Save there commits
one selection's worth of Location changes as one write-path call, no multi-verb chaining involved.

## Open

- Do we add a transaction verb at all, or is per-verb flock + refuse-on-conflict always sufficient?
- If added, what is its shape — a CLI command taking a stdin list of verbs, or a named batch file?
- How does refuse-on-conflict compose across a chain — does one verb's conflict roll back the whole
  chain, or leave earlier verbs committed?

## Answer

