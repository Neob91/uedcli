+++
priority = "p2"
kind = "implement"
summary = "Rebuild the mover/stash/surface LIVE round-trip integration tests on `run_materialize`"
+++

# Rebuild the mover/stash/surface LIVE round-trip integration tests on `run_materialize`

Slice 6 deleted `test_mover_integration.py`/`test_stash_integration.py`/
`test_surface_integration.py` (they were bound to the deleted `SessionStore`+`run_apply`). The
materialize round-trip is covered by `test_materialize_verb.py`, but the substrate-specific live
assertions those held have no equivalent — e.g. a mover's `KeyPos(1)`/`KeyPos(2)`/`KeyRot`/no-`CsgOper`
surviving a real editor cycle. Re-author on `run_materialize` + a trunk `Level` (start with the mover
one — highest-value). Substrate-gated (`-m integration`), so it can't be verified on a box without the
`dx-lum-uned` container. Surfaced by slice 6 (2026-07-07).
