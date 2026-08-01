# Run the collision case live, or close it as already covered by existing evidence?

## Context

The apply path decides same-name-package precedence HOST-SIDE (`packages._first_match`, first-wins)
and then `OBJ LOAD FILE=`s only the winning file, so the editor never sees the shadowed package. The
2026-07-01 paths-precedence spike already live-proved host-side first-wins selection and
overlay-shadows-base. Together these arguably already establish that a `Texture=P.T` binds to the
overlay object.

Options:

- A. Run the full live end-to-end spike (real `materialize` + byte-level readout of the bound
  texture) as belt-and-suspenders, then pin the host-side decision offline. Costs a substrate-gated
  live session.
- B. Close the item as covered by the host-side resolver plus the paths-precedence spike; add only
  the OFFLINE regression that `_first_match`/`obj_load_entries` pick the first-listed dir under a
  collision. No new live run.

Recommendation: B, plus the offline pin — the correctness-deciding logic is host-side and already
live-evidenced; the incremental live run mostly re-confirms `OBJ LOAD FILE=` residency, which apply
already does unconditionally. Pick A only if you want the bound-pixels readout on record.

## Answer

<!-- Empty = open. -->
