+++
priority = "p?"
kind = "unknown"
summary = "`movers.is_mover` is SCHEMA-AWARE — `board/to-build/` #9.4 BUILT 2026-07-25"
+++

# `movers.is_mover` is SCHEMA-AWARE — `board/to-build/` #9.4 BUILT 2026-07-25

(the last #9
sub-item; the `## 9.` section is gone). Mover-ness is now "does the class descend from
`Engine.Mover`?", resolved against the offline `classindex.ClassIndex`, replacing the
`bare.endswith("Mover")` guess that BOTH rejected real movers (`CaroneElevatorSet.CEDoor`,
`…CaroneElevator`, `DeusEx.BreakableGlass`) and accepted non-movers (`Engine.Remover`). Andrzej
resolved the open sub-question — **"Doctor may require config": one predicate, no split**
(`direction/conventions.md`, 2026-07-25 10:18 UTC) — so `is_mover(actor, index)` takes the index at EVERY call
site (doctor, event graph, native preview, native materialize, brushcsg, the dispatch verbs), and
a run with no class resolver RAISES (clean exit 2 naming the verb) instead of calling every mover
a static brush. The editor-authored-keyframes caveat is deleted from
`docs/leveldesign/deusex/recipes/elevator.md` Parts 2–3, and the native build's `*Mover`-suffix
CSG-leak gap (was an `inbox` chore) is closed with it. **Remnants → `board/inbox/`:** the resolver
requirement widened to six more verbs (flag), and `canonicalize_mover_blob` has no production
caller (chore).
