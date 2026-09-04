+++
priority = "p2"
kind = "finding"
summary = "built-golden node bit 0x10 is NF_BoxOccluded (a per-frame render scratch flag), not a lighting flag — exclusion candidate"
+++

# Built-golden node bit 0x10 is NF_BoxOccluded (render scratch), not a lighting flag

## Symptom

WanChai N=6 (`06_HongKong_WanChai_Market`) is byte-exact except one bit: world `Model Model2`
node 17 has `node_flags = 0x10` in the UED22 golden vs `0x00` native. All node/surf/vector/point
counts and every other field are byte-identical; the parity gate reports a single residual
(`BODY model model2`). Node 17: `iSurf=22`, plane `(0,1,0,-512)`, `nv=4`, interior leaf-chain node.
Surf 22 is `PF_LowShadowDetail` (`0x8000`) — **not** `PF_BrightCorners`.

## What bit 0x10 actually is

UE1 reuses bit `0x10` for two unrelated `EBspNodeFlags`: `NF_BrightCorners` (a lighting-pass RAY
parameter) and `NF_BoxOccluded` (a renderer per-frame node scratch flag). The task framed this as a
`NF_BrightCorners` lighting flag; the binaries show it is `NF_BoxOccluded` from the renderer.

Evidence (Editor/Engine/Render.dll, UED22, disasm 2026-09-04):

- The lighting pass writes **no** node flags. `Editor.dll` `?shadowIlluminateBsp@` (`0x100a5e10`)
  and its per-lumel loop only *pass* `ExtraNodeFlags=0x14` to `LineCheck` (`0x100a597a`); a scan of
  the whole `Editor.dll` `.text` finds **zero** writes to NodeFlags (in-memory offset `+0x37`).
- The **only** code in the whole toolset that sets node bit `0x10` is two sites in `Render.dll`,
  both in one occlusion function (`0x100193db`, `0x10019526`): after a bounding-box visibility
  vtable call (`edx+0x80`) returns "not visible", `or byte ptr [node+0x37], 0x10`. Profiling
  counters + `rdtsc` around them confirm it is the render occlusion-cull path (`URender::OccludeBsp`).
- That same function **clears** the bit per node before re-testing: `and cl, 0xef` →
  `mov [node+0x37], cl` (`0x10019373`). So `NF_BoxOccluded` is cleared and recomputed for every node
  on **every** rendered frame, from the current camera.
- Offset `+0x37` is confirmed NodeFlags: the poly-occlusion path clears/sets bit `0x08` there
  (`and …,0xf7` / `or …,8`) and `IsCsg` tests `0x21` there (`test …,0x21`).

So node 17's `0x10` is a leftover from the last viewport frame the editor rendered between
`MAP REBUILD`/`LIGHT APPLY` and `MAP SAVE`: node 17's bounding box was box-occluded from that
camera, the bit was left set, and `MAP SAVE` serialized it (NodeFlags is a full on-disk byte).

## Why native can't (and shouldn't) reproduce it

- It is a function of the editor's camera/viewport state at save time — native has no renderer and
  no camera, so nothing in the trunk determines it.
- It is render/gameplay/savegame **inconsequential**: both editor and game clear and recompute
  `NF_BoxOccluded` at the start of every frame's occlusion pass, so the saved value is never read.

## Fix vs exclude

**Recommend EXCLUDE**, same category as the already-accepted "MAP REBUILD object-table GC
bookkeeping" exclusion (render/gameplay/runtime/savegame inconsequential). Concretely: the parity
gate should mask node `NF_BoxOccluded` (`0x10`) — and, by the same argument, `NF_PolyOccluded`
(`0x08`) — out of the node-body comparison, since both are per-frame renderer scratch bits.

Not a fixable rule: there is no trunk-derivable condition; reproducing it would mean porting
`URender::OccludeBsp` with a specific camera to set a bit that is overwritten on the first frame.

**Needs (per `NATIVE-MATERIALIZE.md` exclusion policy): an opus review confirming inconsequence +
the owner's explicit yes** before it counts as an exclusion. Parked here; do not self-authorize.

## Repro / evidence

- Cached: `_scratch/actor-parity/06_hongkong_wanchai_market/{native_N6,ref_N6}.dx`.
- Gate: `parity_gate.py native_N6.dx ref_N6.dx` → 1 residual (`BODY model model2`).
- Disasm sites above are in `uned/UED22/{Editor,Engine,Render}.dll`.
