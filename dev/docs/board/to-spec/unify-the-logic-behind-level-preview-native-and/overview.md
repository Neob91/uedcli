+++
priority = "p3"
kind = "implement"
summary = "One scale/sheer gate and one CSG core across the two preview tiers"
+++

# One scale/sheer gate and one CSG core across the two preview tiers

`actor preview --faces textured` and `level preview --native` both draw brush geometry, and two
things about them are still split. Neither is the pipeline-wide duplication this item was originally
filed for — see `spec.md` for what was measured.

- **Two CSG cores.** `solve_world_surfaces` (the ortho textured tier) runs
  `uedcli_native.build_geometry_bspcsg`; `build_scene` (the native perspective tier) runs the older
  coarse `uedcli_native.build_geometry`. Same module, 80 lines apart. One trunk can be carved two
  ways, and only `bspcsg` is held to the byte-parity work.
- **Three scale/sheer refusals.** `cli/rendering.py:_reject_transformed_brushes`,
  `preview_native._reject_scaled`, and `brushcsg.py` each re-derive "is this `FScale` the identity"
  and disagree on whether to report the first offender or the batch.

Decided (owner, 2026-08-22): collapse the three refusals onto one predicate (S1), and point
`build_scene` at `build_geometry_bspcsg` (S2) — the later-implemented core, already materialize's
default. Merging the two rasterizers is REJECTED: it would put the Rust extension on the
`--faces wire` path, which today needs neither it nor a game install. Rationale in
`rationale/preview.md`.

Neither tier renders a scaled brush today, so S2 changes no preview output. Scaled brushes are
unblocked by `bspcsg-core-apply-scaled-brushes`, not by this item — which is why this dropped to p3.

Surfaced 2026-08-05 rendering OG Deus Ex levels: both tiers refused the maps' scaled brushes (mirror
`X=-1`, pervasive), and the offline textured render was only reachable by stripping scales to
identity.
