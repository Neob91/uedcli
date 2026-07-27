+++
priority = "p3"
kind = "chore"
summary = "The two zero-caller `canonicalize_mover*` helpers DELETED — two `board/inbox/` entries CLOSED 2026-07-25"
+++

# The two zero-caller `canonicalize_mover*` helpers DELETED — two `board/inbox/` entries CLOSED 2026-07-25

(the dedicated one and the older `canonicalize_mover_blob` duplicate).
`canonicalize_movers_in_level` and `canonicalize_mover_blob` had no production caller — the latter
explicitly "retained for callers/tests", the shim pattern `direction.md` "No back-compat cruft"
forbids — so both are gone, with the two blob tests. `test_qualify.py`'s level-granularity test was
first rewritten to loop `canonicalize_mover` itself and then, in the review round below, deleted
outright — it exercised a loop the test had written, and the real funnel is covered by
`test_movers` + `test_prefab_migration`. Its comment had claimed a "live-qualify funnel
mover-canonicalization step" that `qualify.py` does not have, and deferred to a
`test_mover_integration.py` that does not exist. `architecture.md` corrected on the same point: the
fold runs at ONE funnel (capture), not two. The `2026-07-15-native-materialize` spike harness was
updated to the per-actor loop so it still runs.
