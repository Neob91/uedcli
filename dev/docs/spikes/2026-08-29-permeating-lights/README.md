# Permeating light lists (`Model.Lights` region 1) — first port attempt

Implements the algorithm decoded in `port-the-per-leaf-permeating-light-lists-model` in
`uedcli-native/src/permeating_lights.rs`: a portal-beam flood (`ActorVisibility`) seeded per light,
reusing `zones::collect_leaf_portals` (already built for the zone union-find) for the
every-empty-leaf-to-empty-leaf adjacency graph.

**Not wired into `light::bake`.** On `01_NYC_UNATCOHQ` (node-exact tree):

- Leaf-reachability SET is EXACT: 748/762 leaves marked on both native and a freshly-built LIT
  golden, and it's the SAME 748 leaves both times.
- Per-leaf light CONTENT is wrong: only 4/762 leaves have an exact-match run (same lights, same
  order). Total entry count is close (native 4710 vs golden 4603) but the content differs.

So the portal graph + per-light radius reachability is fundamentally sound (which light reaches
*a* leaf, aggregated across all lights, matches exactly), but something in the per-light
attribution is wrong (which SPECIFIC light(s) reach which SPECIFIC leaf).

## Ruled out / tried

- Disabling `clip_beam` entirely (unclipped flood past the seed) causes runaway recursion blowup
  (didn't finish in 120s) — the beam clip is load-bearing for bounding the flood, not a no-op, so
  it's plausibly implicated but this experiment was inconclusive (killed before it could produce a
  comparable result).

## Suspected causes, not yet isolated

1. **Orientation** (`getvisiblesurfs`'s sibling danger, board item's unknown #1): the flood's
   `d = (Location - Base)·Normal < 0` gate depends on `FacePoly.normal` correctly pointing AWAY
   from the source leaf. This port derives it from `zones::Portal`'s existing `a`=front/`b`=back
   convention (already load-bearing for the zone union-find) — plausible but not independently
   verified for the FLOOD direction specifically.
2. **`FPoly::SplitWithPlaneFast`** (board item's unknown #2, still undecoded): `clip_beam` here is
   a from-scratch Sutherland-Hodgman clip, not a port of the real function. Its epsilons/exact
   half-space semantics could differ from the editor's in ways that redirect the flood.
3. **The re-entry gate's exact vertex set** — implemented as "any vertex of any of this leaf's
   portals", per the board item's prose; could be subtly different from what `GetPolyForLeaf`
   actually returns.

## Next step

A live differential trace of ONE light's flood (single portal-to-portal path) against a
gdb-instrumented editor, the same methodology `2026-08-29-area51-underbuild/` used to localize its
CSG bug — this static/offline comparison can find THAT it's wrong but not easily isolate WHERE.

## Reproduce

`harness/check_permeating.py` — see its docstring for the golden-rebuild command.
