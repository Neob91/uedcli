+++
priority = "p1"
kind = "debug"
summary = "N=2 (first world brush) divergence map: iLink + bDynamicLight fixed; remaining blockers are the point-pool order (gated), the world Polys soup (Rust), the Region SetActorZone recompute, and the Sky-case exclusion (owner)."
+++

# incremental-lockstep N=2: first-world-brush divergence map + remaining blockers

N=1 passes all three levels; NYC_Bar N=2 passes (its actor #2 is a point actor, no world brush).
UNATCO N=2 and WanChai N=2 add their first WORLD brush (Actors[2]) and diverge. Full gate + byte
analysis on the cached N=2 pairs (`_scratch/actor-parity/<level>/{native_N2,ref_N2}.dx`).

## Fixed this pass (committed, with regression tests)

- **Content-brush shape Polys `iLink`.** Native ran `_assign_ilinks` on every brush's own
  `Model_Brush<n>.Polys`, writing 0,1,2,... The editor leaves them all `-1`: it does NOT run the
  bspValidateBrush LINK phase on an imported CONTENT brush's shape model (the live builder brush
  `Polys4` still links, `[0,1]`, unchanged). Fix: drop `_assign_ilinks` from `unbuilt._fpolys`.
  Byte-verified UNATCO Brush74 / WanChai Brush3675.
- **`bDynamicLight` on brushes.** The trunk authors `bDynamicLight=True` on Brush74; the editor
  resets it to the class default (False) at MAP IMPORT and omits it. Fix: strip it in
  `materialize._trunk_to_actorspecs`'s brush branch. Byte-verified UNATCO Brush74. Scoped to brushes
  (only evidence is a brush); a Light's `bDynamicLight` is NOT touched.

## Remaining blockers - UNATCO N=2 (2 residuals)

1. **World `Model.Polys` (Polys3) is EMPTY; the ref keeps the 6-poly post-CSG soup.** The soup is
   the CSG output FPoly list (world-space, `iLink=iBrush=surf index`, `pf=0x40000000`, item
   `OUTSIDE`) - native's Rust core builds it as the input to `bspBuild` but discards it. It does NOT
   reference the Points pool (stores float coords), so it is independent of blocker 2. Emitting it
   faithfully needs the Rust core to EXPOSE its post-CSG polys (`preview_native._node_polys` only
   recovers node rings, breaks once a surf spans >1 node). Related:
   `editor-unatco-repartition-soup-size-unknown`.
2. **`Model2` body: Points-pool INSERTION ORDER (3 points) + the paired FVert `iSide`.** Vectors,
   nodes, surfs, all VALUES are byte-identical; only the order surf bases enter the Points pool
   differs - native uses canonical surf order (`reorder_points_canonical`, "bases first in surf
   order"), the editor uses BSP surf-ALLOCATION (DFS-creation) order. The off-by-default
   `UEDCLI_BSPCSG_INCREMENTAL_POINTS=1` produces UNATCO's points BYTE-IDENTICAL to the ref and makes
   the whole `Model2` body match - but it's gated off and does NOT fully fix WanChai (below), so
   promoting it to default is an architecture call. Related: `native-point-pool-byte-order`,
   `native-surfs-vectors-points-pool-byte-order`, `gated-incremental-points-path-can-panic-bsp`.

With INCREMENTAL_POINTS on + the soup, UNATCO N=2 would PASS. Neither is self-authorized here.

## Remaining blockers - WanChai N=2 (adds, on top of the above)

3. **`Region` PointRegion after rebuild.** Native hardcodes `_pointregion_prop` to
   `(LevelInfo0, iLeaf=-1, ZoneNumber=0)`. The editor's `SetActorZone` recomputes it from the built
   BSP: WanChai's SUBTRACT brush carves an air leaf, so its DefaultBrush (origin) AND Brush3675 both
   resolve to `(iLeaf=0, zone=1)`. UNATCO's brush matches at `(-1,0)` because an ADD brush in
   otherwise-solid space leaves the point in solid. Fix = wire native's built model through a
   PointRegion descent (machinery exists: `materialize._model_point_zone`; needs iLeaf too) into the
   placed-actor Region - a build-order/plumbing change (Region is set in `_trunk_to_actorspecs`,
   before the model is built).
4. **Texture GROUP-name case `Sky` vs `sky`.** Editor-global-FName-pool artifact, not derivable from
   the `.utx` (which stores `Sky`). Exclusion candidate - parked as an owner question on the
   incremental-lockstep item (`questions/texture-group-name-case-from-editor-global-fname-pool.md`).
5. **WanChai `Model2` shared-side `iSide` residual.** Even with INCREMENTAL_POINTS (which makes
   WanChai's Points AND Vectors byte-identical), one FVert `iSide` differs (native 9 vs ued 10) - a
   shared-side numbering residual in the CSG core, separate from the point order. Related:
   `native-point-vert-pool-byte-parity-port`, `unatco-verts-points-residual-after-the-zone`.

## Harness note

Rebuild native from a cached subset directly (no shipped-`.dx` lookup):
`parity_compare.build_native_lit_dx(subset, subset.parent.parent)` on
`_scratch/actor-parity/<level>/N2/maps/<level>`; gate with `parity_gate.py`. INCREMENTAL_POINTS is a
runtime env read, so it toggles without a recompile.
