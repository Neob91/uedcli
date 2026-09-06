+++
priority = "p3"
kind = "implement"
summary = "visible_surfs.rs skips OccludeBsp's frustum-cone subtree reject, so native's traversal reaches 51 subtrees per UNATCO N=26 build that UED22 discards -- and box-tests nodes the editor never tests, marking one extra NF_BoxOccluded."
spikes = ["dev/docs/spikes/2026-09-06-boundvisible-port/"]
+++

# Port `URender::OccludeBsp`'s frustum-cone subtree reject

`uedcli-native/src/visible_surfs.rs` ports every other per-node filter but not step 6
(`render.dll 0x100197b8`–`0x10019884`): with `sign = IsFront ? +1 : −1`, the node is popped — whole
subtree skipped — when all four `sign * (node->Plane | Frame->ViewSides[k])` are `> 0`
(`FPlane::operator|` = the 3-component dot; `ViewSides[4]` at `FSceneNode+0xfc/0x108/0x114/0x120`,
the four unit frustum-corner rays, `normalize(±FX2, ±FY2, Proj.Z)` through `Uncoords`).

It was left out as a pure early-out: the four-plane clip in `rasterize_node` already produces an
empty footprint for anything outside the cone, so skipping it was believed to change cost only.

## Why that is no longer harmless

Since the `BoundVisible` port (2026-09-06) the traversal has a side effect: it writes
`NF_BoxOccluded` into `Model.Nodes[].NodeFlags`, and `LIGHT APPLY`'s shadow-ray walker reads that
bit. A subtree the editor discards at step 6 is never box-tested by the editor — native descends and
tests it.

Measured on a UNATCO N=26 golden build (`spikes/2026-09-06-boundvisible-port/`,
`harness/compare_box_tests.py` against the live capture): native runs **276** box tests to UED22's
**225**. All 225 shared tests agree; the 51 extra are subtrees the editor never reached. They leave
native marking node 64 `NF_BoxOccluded` where UED22 leaves it clear.

No lightmap moves at N=26 — the parity gate passes — and the flag bit itself is gate-excluded. But
the divergence is real and can bite at a higher N or on another level, where an extra mark lands on
a node a `PF_BrightCorners` shadow ray actually crosses.

## What a build here needs

1. Reproduce `ViewSides[4]` for the gather frame in native's own face basis (FOV 90, 1024², so the
   four corner rays are `normalize(±right ± up + forward)` — confirm against a live `FSceneNode`
   dump rather than deriving it; `harness/boundvisible_frame_probe.py` already reads the frame and
   only needs the four vectors added to its dump).
2. Apply the test at the same point in `traverse` the editor applies it (after `IsFront`, before the
   per-surface filters and before descending).
3. Re-verify with `compare_box_tests.py` — target: native's box-test set becomes exactly the
   editor's 225 — and re-run the ladder (`ladder_run.py`) from N=1, since this prunes subtrees the
   current rasterizer visits.
