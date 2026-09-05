# LIGHT APPLY reads TRANSIENT node flags — UNATCO N=26's `Light155` divergence

**Result: root cause pinned, live-confirmed. No fix shipped — the faithful fix is a new port.**

## The divergence

UNATCO `03_NYC_UNATCOHQ`, first 26 actors (actor 26 = `Brush514`). Native and UED22 build a
byte-identical BSP (nodes, surfs, verts, points, vectors all match), but the world `Model` differs in
lighting: UED22 lists `Light155` on three `Brush420` surfaces (28, 30, 32) and native does not
(native `Lights` 73 entries / `LightBits` 3045 B; UED22 76 / 3128 B). N=25 passes; N=1..25 pass.

## What it is NOT

- Not the BSP: every node (plane, children, zone, vert ring) is byte-identical.
- Not the walker: `linecheck.rs::seg_clear` was re-checked instruction-by-instruction against the
  captured disassembly of `Editor.dll 0x17ce190`
  (`spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-walker-full-disasm.log`) — the
  whole-segment/crossing split, the `t = d2/(d1-d2)` crossing, `mid = p2 + t*(p2-p1)`, near-child =
  `p2`'s side, `p2 := mid` on the far continuation, the `combine_state` rules at all three
  classification sites, and the terminal's global-flag test all match.
- Not the gather: the editor casts exactly 341 `Light155` rays at surf 28 — the same in-radius set
  native computes.

## What it IS

`FBspNode::IsCsg` is `NumVertices > 0 && (NodeFlags & (ExtraNodeFlags|0x21)) == 0`. The walker's two
**whole-segment** classification sites strip `0x10` first (`and $0xef` at `0x17ce240`/`0x17ce284`);
its **crossing** sites do not (`0x17ce32f`, `0x17ce34e`, `0x17ce3d8`, `0x17ce3f2`). A shadow ray for a
`PF_BrightCorners` surface passes `ExtraNodeFlags = 0x14`, so at a crossing a node carrying `0x10`
(`NF_BoxOccluded` / `NF_BrightCorners` — the same bit) is **not CSG and does not occlude**.

At `LIGHT APPLY` time the live nodes carry renderer scratch in exactly those bits, and native's nodes
carry zero. Live capture, first shadow ray of surf 28, UNATCO N=26:

| run | live node 48 (`Brush420`'s `y=304` wall, surf 29) | 341 `Light155` rays |
|-----------------------------------------|------------------|------------------|
| golden recipe (`MAP IMPORT` → `MAP REBUILD` → `LIGHT APPLY`, one `EXEC` batch, gdb attached first) | `flags=0x10` | **all CLEAR** |
| `MAP LOAD <the same built .dx>` → `LIGHT APPLY` | `flags=0x00` | all BLOCKED |
| `MAP LOAD` → `MAP REBUILD` → `LIGHT APPLY` (batched) | `flags=0x00` | all BLOCKED |
| native | (always 0) | all BLOCKED |

Logs: `logs/golden-pipeline-unatco-n26-surf28.log`, `logs/maploadreplay-unatco-n26-surf28.log`.

The live node array is the SAME 80 nodes in the same order (`ArrayNum` 672 is over-allocation; slots
80..671 are zeroed, `NumVertices = 0`, so they never occlude and indices line up 1:1 with the saved
tree). Three nodes carry `0x10` in the golden run (16, 32, 48) and a different three/four in the
`MAP LOAD` run (17, 33, 49, 65) — viewpoint-dependent, so it is renderer occlusion state, not
anything derived from `PolyFlags`.

Offline cross-check (`harness/replay_all.py`, a Python re-implementation of `bake_surf` +
`seg_clear`): replaying UED22's own build with its saved flags reproduces 24 of 27 stored bit-planes
byte-exactly and fails exactly the three `Light155` ones; making node 48 non-occluding reproduces all
three byte-exactly, including the 341-bit wedge, and leaves every other light dark.

## Why it appears at N=26 and not before

The flag is set by the editor's own rasterization, so it depends on the whole scene. Adding
`Brush514` (1072, 928, 0 — nowhere near `Light155` at 20.8, 488.4, 313.1) changes which nodes the
renderer marks, and node 48 becomes one of them.

## Closed: the live flags fully explain the golden, and only `0x10` matters

Replaying UED22's own build with the flags the probe captured (`harness/replay_all.py --flags`)
reproduces **27 of 27** stored bit-planes byte-exactly, against 24/27 with the saved flags. Masking
the captured flags down to just their `0x10` bits — three nodes (16, 32, 48) out of 80 — still gives
**27/27**. So the whole divergence is: *which nodes carry `NF_BoxOccluded` when the raytrace runs*.
`NF_PolyOccluded` (`0x08`) is in no `IsCsg` mask and does not matter.

Two questions a port had to settle, both now measured
(`harness/nodeflag_changes_during_lightapply.py`, which prints the flag array only when a weighted
checksum over it changes): across **1400 consecutive rays spanning 5 lights** on one surface the flag
set never changed once. The flags are set ONCE before the raytrace pass, not per light, and the
raytrace runs after the gather.

## Who writes the bit

`render.dll 0x100193db`: `or byte ptr [edi + 0x37], 0x10` — `NodeFlags |= NF_BoxOccluded` on the node
in `edi`, taken when the virtual call at `0x100193d5` (`[edx+0x80]`, the span-buffer/box visibility
test) returns 0. This sits inside the same `URender::OccludeBsp` family `visible_surfs.rs` already
ports; the marking comes from its render-bound (box) occlusion step — **the one step that port
deliberately skips.**

Addresses: `rdis.py` prints Engine.dll's PREFERRED VAs, but the live editor loads Engine.dll
relocated by `-0xE9E0000` (`0x101ae190` -> `0x17ce190`); Editor.dll and render.dll are not relocated.

## The faithful fix (not built here)

`visible_surfs.rs` ports `URender::GetVisibleSurfs` but explicitly skips its render-bound (box)
occlusion step, on the stated grounds that it is "conservative, so skipping it should change cost and
not the surface set". That is now falsified — not through `GetVisibleSurfs`' own output, but because
the `NF_BoxOccluded` bits it leaves on the nodes are read afterwards by the shadow-ray walker. Native
must set the same bits on the same nodes and let `linecheck` see them (`is_csg(..., strip=false)`
already tests `0x10` at crossings, so no walker change is needed).

## STOP — the marks are not occlusion. They are a 1024-byte-stride stray write.

There is nothing to port. The `0x10` bits do not depend on the level at all:

| build | nodes carrying `0x10` | their byte offsets into `Model.Nodes` |
|-------------------------------|------------------|--------------------------|
| golden recipe, N=26 (80 live nodes) | 16, 32, 48       | 1024, 2048, 3072 |
| golden recipe, N=26, second run     | 16, 32, 48       | 1024, 2048, 3072 |
| golden recipe, **N=27** (90 live nodes, different tree) | 16, 32, 48 | 1024, 2048, 3072 |
| `MAP LOAD` of the built N=26 `.dx`  | 17, 33, 49, 65   | 1088, 2112, 3136, 4160 |
| `MAP LOAD` + `MAP REBUILD`, N=26    | 17, 33, 49, 65   | 1088, 2112, 3136, 4160 |

Every hit is at `base + k*1024` bytes. The base and the count vary by PIPELINE (0 and 3 for a fresh
build, one node = 64 bytes and 4 after a load), never by geometry: N=27 changes the tree and the
marked node INDICES do not move. Deterministic per pipeline, repeatable run to run.

Box occlusion cannot produce an arithmetic progression in node index that survives a geometry change.
Something writes `|= 0x10` at `+0x37` of every 1024th byte of the node array — an out-of-bounds or
wrongly-strided write from another structure. (`GetVisibleSurfs` rasterizes `0x400 x 0x400` faces;
1024 is also that.) `render.dll 0x100193db` is the instruction that ORs the bit; whether it is the
one scribbling, or merely shares the constant, is not established.

**Consequence: UNATCO N=26 parity is not reachable by a faithful fix.** UED22 lists `Light155` on
those three `Brush420` surfaces only because a stray `0x10` landed on node 48 — the wall that would
otherwise block every one of those 341 rays. Native reproducing that would mean reproducing an editor
memory scribble, which is not an algorithm. This needs the owner: accept the affected surfaces as a
documented reference defect, change what the ladder compares, or rebuild the reference some other
way. Do not mask it on an agent's authority.

## The `visible_surfs.rs` box-occlusion step (now moot for this bug)

## Relation to the `node_flags & ~0x18` exclusion

The gate excludes `NF_PolyOccluded|NF_BoxOccluded` from the SAVED package. That stays correct — the
saved values come from a render after lighting and no loader consumes them. But "no reader consumes
them" was read as "native need not model them at all", and the builder does consume them.
