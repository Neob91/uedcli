+++
priority = "p1"
kind = "bug"
summary = "UNATCO N=26 lighting diverges because UED22's shadow ray reads a stray NF_BoxOccluded bit written at a fixed 1024-byte stride into Model.Nodes; not portable, needs an owner ruling."
+++

# `LIGHT APPLY` shadow rays read transient `NF_BoxOccluded` node flags native never sets

Blocks the incremental lockstep ladder: UNATCO `03_NYC_UNATCOHQ` is byte-exact through N=25 and
fails at N=26 on the world `Model` — UED22 lists `Light155` on `Brush420` surfs 28/30/32, native does
not. The BSP is byte-identical; only the lighting differs.

## Root cause (live-confirmed)

`FBspNode::IsCsg` = `NumVertices > 0 && (NodeFlags & (ExtraNodeFlags|0x21)) == 0`. The shadow-ray
walker strips `0x10` at its whole-segment sites but NOT at its crossing sites, and a
`PF_BrightCorners` ray passes `ExtraNodeFlags = 0x14` — so a node carrying `0x10`
(`NF_BoxOccluded`/`NF_BrightCorners`) does not occlude at a crossing. During the golden's
`MAP IMPORT` → `MAP REBUILD` → `LIGHT APPLY` batch the blocking wall node carries `0x10` (set by the
editor's own rasterization) and all 341 `Light155` rays come back CLEAR; replaying `LIGHT APPLY` on
the same saved tree gives that node `0x00` and every ray blocked, exactly like native.

Full evidence, the three live captures and the offline replay that reproduces UED22's stored
bit-planes: `dev/docs/spikes/2026-09-05-lightapply-node-flags/spike.md`.

## There is no fix to port — the bit is a stray write

Both porting questions were measured and answered (the flags are set ONCE before the raytrace, not
per light), and then the marked set itself was measured across builds:

| build | nodes with `0x10` | byte offsets |
|---|---|---|
| golden recipe N=26 (80 nodes), twice | 16, 32, 48 | 1024, 2048, 3072 |
| golden recipe **N=27** (90 nodes, different tree) | 16, 32, 48 | 1024, 2048, 3072 |
| `MAP LOAD` of the built N=26, with and without a rebuild | 17, 33, 49, 65 | 1088, 2112, 3136, 4160 |

Always `base + k*1024` bytes; base and count depend on the PIPELINE, never on the geometry. Real box
occlusion cannot survive a geometry change with identical node indices. Replaying the bake with just
those `0x10` bits reproduces 27/27 of UED22's stored bit-planes (24/27 without them), so this single
stray bit on node 48 is the entire divergence.

Native cannot faithfully reproduce a memory scribble. Owner ruling needed on what the ladder should
do with it.

## Note on the existing exclusion

The gate's `node_flags & ~0x18` exclusion stays correct for the SAVED package (those bytes come from
a render after lighting and no loader consumes them) — but "no reader consumes them" was taken to
mean native need not model them at all, and the BUILDER consumes them.
