+++
priority = "p2"
kind = "implement"
summary = "Redesign /scene's props payload: stop re-shipping class-constant default text per actor"
+++

# GUI Inspector: `/scene` props payload redesign

Built via a 5-round plan review then an 8-task subagent-driven-development build (Task 3 split into
3a/3b). Backend gains a raw `.u` package endpoint (real content ETag, gzip); `/scene` now ships a
flat sparse per-actor map instead of a resolved property tree. The frontend fetches packages lazily,
parses them via the already-built WASM resolver, and resolves each class's shape+defaults
client-side — the Inspector never blocks on a network round trip.

Two real architectural bugs were found and fixed during the plan-review loop: the shared resolver's
`poison()` method is a permanent whole-context degrade, and both the backend's per-level
`resolve_ctx` and the frontend's module-level WASM context are long-lived across many actors/
requests — poisoning either on an ordinary missing-package miss would have silently broken every
other actor for the rest of the session. A third, symmetric bug (a real race letting a transient
"package still loading" error get cached permanently) was found during the final whole-branch review
and fixed there, along with a `tsc -b`/`npm run build` regression (16 test fixtures never updated
for an earlier task's type change) and a missing `Vary` header on 304 responses.

Final whole-branch review: "Ready to merge: No" (one Critical, three Important). Fix wave applied,
scoped re-review confirmed all four addressed with real mutation-based verification, plus one more
small cosmetic-cleanup pass. READY TO MERGE.
