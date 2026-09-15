+++
priority = "p2"
kind = "implement"
summary = "GUI: explicit rebuild — pinned build state, mode gating, fullbright overlay for GUI edits"
depends-on = ["uedcli-serve-share-one-in-process-scene-cache"]
+++

# GUI: explicit rebuild — pinned build state, mode gating, fullbright overlay for GUI edits

UnrealEd never auto-rebuilds: BSP geometry + lighting stay exactly as they were last built, however
much the trunk moves, until the user explicitly rebuilds. This item ports that model into the GUI —
see `spec.md`. Owner-raised 2026-09-14, refined over several follow-ups in the same conversation;
`spec.md` is the settled write-up of everything agreed.
