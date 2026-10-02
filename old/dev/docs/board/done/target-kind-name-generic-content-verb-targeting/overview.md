+++
priority = "p?"
kind = "unknown"
summary = "`--target KIND/NAME` — generic content-verb targeting (level/stash/prefab)"
+++

# `--target KIND/NAME` — generic content-verb targeting (level/stash/prefab)

— BUILT
2026-07-12. Two new `LevelSource`s (`StashLevelSource`/`PrefabLevelSource`) + a parse/routing
front branch in `_resolve_level_source` + the one `cli._target_flag` helper on the shared content
verbs; a prefab is now edited in place with any content verb (no apply/re-capture/promote
roundtrip). Includes the prerequisite `stashlib.read_prefab` meta-clobber fix and the
`parse_poly_target`→`parse_poly_selector` rename (frees "target" on `brush poly set`). Path
traversal refused before any source is built (`validate_member_name`). Spec:
`spec.md`; decision 2026-07-12 03:06 UTC; folded into
`architecture.md` ("The `LevelSource` seam and `--target`"). **Non-goals (by design):** no
instance/placement refresh of already-applied copies; no new lifecycle verbs; last-writer-wins on
a concurrent same-box edit (atomic swap, no merge).
