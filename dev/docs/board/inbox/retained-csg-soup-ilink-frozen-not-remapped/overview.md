+++
priority = "p2"
kind = "debug"
summary = "The retained world CSG soup (Model.Polys) freezes each poly's i_link=i_surf at bsp_build time and is never remapped after reorder_surfs_canonical/bsp_opt_geom permute/reindex surfs; zone-split fragments (Pass D, appended after bsp_build) are absent from the soup. Predicted to diverge Model.Polys iLink/count from UED22 at the first N where surfs are permuted or optgeom changes surf count. Passes at N=2 only because the permutation is identity there."
+++

# Retained CSG soup `i_link` is frozen, not remapped after surf permute / optgeom

The world CSG soup (`Model.Polys`, the post-`bspBuild` FPoly list the editor keeps and native now
retains + Python assembly emits) captures each poly's `i_link = i_surf` at `bsp_build` time. After
that, the pipeline permutes and reindexes surfs:

- `reorder_surfs_canonical` relabels the Surfs pool to the editor's incremental-CSG order and remaps
  `node.i_surf`, but does NOT touch the frozen soup's `i_link`.
- `bsp_opt_geom` can change the surf count / linkage; again the soup is untouched.
- Zone-split fragments (Pass D, appended AFTER `bsp_build`) never enter the frozen soup at all, so
  the soup can be missing polys the final Surfs pool references.

## Prediction

`Model.Polys` `iLink` and/or poly count will diverge from UED22 at the first N where surfs are
actually permuted (non-identity `reorder_surfs_canonical`) or optgeom changes the surf count. It
passes at WanChai/UNATCO/NYC_Bar N=2 only because the surf permutation is the identity there and the
unsplit fixtures add no Pass-D fragments — so `i_link == i_surf` still holds by luck.

## Not an N=2 blocker

The lockstep ladder's per-N re-gate will catch this the moment it bites, so no fix now. When it does:
either remap the soup `i_link` through the same permutation `reorder_surfs_canonical` applies to
`node.i_surf`, and rebuild/extend the soup to include Pass-D fragments — or reconstruct the emitted
soup from the final surfs rather than freezing it at `bsp_build`.

Evidence pin: the unsplit-box case is covered by
`bspcsg::tests::world_build_retains_the_csg_soup_with_ed_processed_set` (identity permutation, so
green) — that test does NOT exercise a permuted-surf or optgeom-count-change case.
