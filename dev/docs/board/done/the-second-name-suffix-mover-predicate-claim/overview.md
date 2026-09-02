+++
priority = "p2"
kind = "unknown"
summary = "The second name-suffix mover predicate: claim corrected, FIX deferred into the open scoping spec — `board/inbox/` re-homed 2026-07-25"
+++

# The second name-suffix mover predicate: claim corrected, FIX deferred into the open scoping spec — `board/inbox/` re-homed 2026-07-25

`preview.classify_brush` still uses
`bare.endswith("Mover")`, which falsified `architecture.md`'s "no name-guess fallback anywhere".
The docs now state what is true (one surviving name test, outside `is_mover`, with its live
divergence spelled out) and the FIX is folded into `board/to-spec/`'s open "why do SEVEN verbs require
the games config?" item as an explicit part of its scope — threading a `ClassIndex` in would make
`actor`/`stash`/`prefab preview` an eighth resolver-requiring verb family while that item is
asking to scope the requirement back down. **Remnant:** the divergence is live until that item is
answered.
