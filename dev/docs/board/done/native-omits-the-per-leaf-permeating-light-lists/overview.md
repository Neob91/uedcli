+++
priority = "p2"
kind = "unknown"
summary = "Superseded by `port-the-per-leaf-permeating-light-lists-model`, which carries the same finding plus the algorithm decoded instruction-by-instruction and the correction that the region is produced by the ZONING build, not the lighting bake."
+++

# Native OMITS the per-LEAF permeating light lists — superseded

The finding stands and is re-measured on `03_NYC_UNATCOHQ` (mislabeled `01_NYC_UNATCOHQ` until
2026-08-31, see `unatco-baseline-trunk-is-actually-03-nyc`): `Model.Lights` region 1 is
`Lights[0, 5405)`, 761 of 776 leaves carrying a run, and native emits none of it while stubbing every
leaf's `iPermeating` to `0`.

Two things this item got wrong, both corrected in
`port-the-per-leaf-permeating-light-lists-model`, which is where the work now lives:

* the region is produced by `csgRebuild` → `TestVisibility` → `FEditorVisibility::Portalize`, i.e. the
  ZONING build — `shadowIlluminateBsp` never touches `Model.Lights` or `Model.Leaves` for the level
  model. So it is a `zones.rs` port, not a `light.rs` one.
* the within-run order is not an unsorted "gather-discovery order": it is DESCENDING
  `Level->Actors` index, which falls out of a per-leaf PREPEND under an ascending-actor outer loop.

The new item also carries the full flood algorithm (portal-beam recursion with clip polygons), the
`iVolumetric`/`iVisibilityMask` rules, and the two things to verify before porting.
