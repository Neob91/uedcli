+++
priority = "p1"
kind = "debug"
summary = "WanChai N=45's whole divergence is ONE over-included per-leaf permeating light: leaf 20 gets Spotlight22 where UED22 lists only Light189, and that one extra `Model.Lights` entry shifts every later offset."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# WanChai N=45 — leaf 20 gets one permeating light UED22 does not

Replaces `wanchai-n45-spotlight22-light-runs-differ-on-4`, whose four divergent lightmap runs were a
`FLightMapIndex` decode bug in `lmdiag.py` and do not exist. With the field read correctly native and
UED22 agree on all 210 lightmap runs at N=45, and the gather's box tests match a live editor capture
call for call.

## The divergence

    leaf_perm_diff.py <native_N45.dx> <ref_N45.dx>
    leaves 91 91; Model.Lights 687 686
    leaf[20] zone=1  nat=(spotlight22, light189)  ued=(light189,)  extra=[spotlight22]
    differing leaves: 1 of 91

`Model.Lights` is two arrays end to end — region 1, the per-leaf permeating lists indexed by
`FLeaf.iPermeating`, and region 2, the per-surf shadow runs indexed by `FLightMapIndex.iLightActors`.
This is region 1. The single extra entry shifts every later `iPermeating` and `iLightActors` by one,
which is the entire `BODY model model2` failure: all 210 lightmap records classify identically (same
runs, same dark-vs-empty status), `LightBits` is byte-identical, and leaf 20 is the only leaf whose
content differs.

## It is the SMALLEST reproducer of the campaign's shared blocker

Four of the five ladder levels are now blocked on this one gap, all with the same shape (one leaf,
one extra light, everything else byte-exact): `unatco-n-226-leaf-12-gets-a-permeating-light157`,
`oceanlab-n-93-leaf-96-gets-a-permeating`, `island-n-123-world-model2-leaf-permeating-light`, and
this. WanChai N=45 is by far the cheapest to work in — **91 leaves, 11 lights, 45 actors**, against
Island N=123's 163 leaves — so it is where the live capture should be taken.

## Where the fix is

`uedcli-native/src/permeating_lights.rs` — the portal-beam flood (`FEditorVisibility::ActorVisibility`,
`Editor.dll 0xa6d00`). This is that module's known, documented error shape: on UNATCO 727/762 leaves
match exactly and the mismatches are "extra, never missing, lights" — a beam clip still marginally too
permissive at one portal after the `SplitWithPlaneFast` epsilon and the plane-normalize fixes.

Two candidates the module itself flags as unconfirmed, either of which would show up exactly like this:

- `SP_Coplanar` (every vertex inside the ±0.25 band) is treated as kept-whole; the real
  `ActorVisibility` call site has not been disassembled for that branch.
- the re-entry radius gate (any portal vertex strictly within radius) and the `d < 0 && d > -radius`
  face gate.

`portal-graph-builds-self-portals-from-stale` is a masked stopgap in the same flood and is owed a
faithful fix; check whether it touches leaf 20's crossings before assuming it does not.

Next step is a live `ActorVisibility` capture for Spotlight22 — which leaf-to-leaf crossing native
keeps and the editor drops — rather than more static reasoning.
`2026-09-07-gather-box-verdict/harness/box_verdict_probe.py` is a working gdb template (breakpoints
armed for a whole `LIGHT APPLY`, `render.dll` rebased through `/proc/<pid>/maps`).

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 45 --to 45 \
        --keep-native
    dev/docs/spikes/2026-09-07-gather-box-verdict/harness/leaf_perm_diff.py \
        _scratch/actor-parity/06_hongkong_wanchai_market/{native,ref}_N45.dx
