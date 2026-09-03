+++
priority = "p1"
kind = "debug"
summary = "Native ships BSP nodes whose ring has <3 distinct points; every editor golden has zero, corpus-wide. Fully explains Paris Club's +2, most of Chateau's +4 / Helibase's +9, 97 nodes of OceanLab's +465; hides count-cancellation in 'exact' 04_NYC_Underground. Localized to zones.rs Pass D's Frag emission skipping the editor's bspAddNode vertex-fill dedup+kill rule (fix_ring covers orphans only)."
+++

# Pass-D zone-split emits degenerate zero-area fragment nodes the editor never stores

Found by the 2026-09-03 BUILT-parity worst-tier localization
(`dev/docs/spikes/2026-09-03-built-parity-worst-tier/`). A corpus census (`degen_census.py`) of
nodes whose ring has fewer than 3 distinct `i_vertex` entries, native vs cached editor golden:

| level                        | d_nodes | native degen      | editor degen |
|------------------------------|---------|-------------------|--------------|
| `10_paris_club`              | +2      | 2                 | 0            |
| `10_paris_chateau`           | +4      | 3                 | 0            |
| `06_hongkong_helibase`       | +9      | 7                 | 0            |
| `14_oceanlab_lab`            | +465    | 97 (+1 zero-area) | 0            |
| `15_area51_entrance`         | +85     | 2                 | 0            |
| `03_nyc_747`                 | +68     | 1                 | 0            |
| `06_hongkong_wanchai_garage` | -68     | 1                 | 0            |
| `12_vandenberg_gas`          | +659    | 2                 | 0            |
| `04_nyc_underground`         | +0      | 2                 | 0            |

Every other cached level (including all exact ones): 0/0. The editor invariant is clean: no golden
anywhere stores a node with under 3 distinct ring points. `04_nyc_underground`'s "node-exact"
status hides 2 such nodes — count-level error cancellation.

## Minimal repro (offline, no editor needed)

`10_paris_club`, `Brush20` (scaled `CSG_Subtract`, `Rotation=(Yaw=16384)`,
`PostScale=(Scale=(X=0.681818))`): its z=96 face is one whole 4-vert quad in the golden (node 1170,
verts bit-identical to native's). Native instead carries the quad (with a T-vertex) plus two
zero-area edge-strip fragments along the ring edge `x=1328..1328.0001220703125` (nodes 2083/2084;
rings `[A,P1,P1,A]` / `[P0,A,A]` — repeated point indices). Node-id ranges pin their creation to the
TestVisibility phase (`STAGE post-repartition`=2067 < 2083/2084 < `post-testvisibility`=2118), i.e.
`zones.rs` Pass D. The grazing plane is `Brush30`'s portal sheet at `W=-1328.0001220703125` —
bit-identical in both models, so this is split/keep behavior, not transform precision.
`10_paris_chateau` `Brush80` shows the same shape on clean integer coordinates (zero-width strips on
the face's own `x=-896` edge) — not an FP-noise artifact.

## Mechanism

`zones.rs::passd_process` emits one `Frag` node per surviving (nonzero-zone) landing from
`node_landings` (Sutherland-Hodgman `clip_poly`, `1e-4` on-plane band). A landing that is a
zero/near-zero-width strip (splitting plane grazing a face edge) survives and becomes a real node.
The editor's `AssignAllZones` fill path (decoded in `fix_ring`'s doc comment: `bspAddNode`'s
vertex-fill runs `bspAddPoint` per vertex with consecutive-duplicate dropping by resolved point
index plus a first==last dedupe, then `if NumVertices < 3 -> NumVertices = 0`, and `bspCleanup`
culls the ringless node) never keeps one. Native applies the equivalent collapse (`fix_ring`) to
Pass-D orphan rings only; the live `Frag`/`OriginalRing` path skips it. The `fix_ring` doc comment
already flags "making the collapse universal + index-based" for "a map that puts a grazing-corner
dup on a live fragment" (it says the follow-up is in `board/inbox/`, but no such item existed —
this item is now it); club/chateau/helibase are those maps.

Also relevant: the editor's Pass-D filter splits via `SplitWithNode(VeryPrecise)` (0.01 threshold)
vs `clip_poly`'s 1e-4 band — club's 0.000122-wide strip splits natively but is inside the editor's
on-plane band, so the editor produces no such landing at all. Fixing the fill rule alone already
collapses both observed shapes (the snapped strip rings have <3 distinct indices).

## Fix sketch

Apply the editor fill rule on the `Frag`/`OriginalRing` emission path: resolved-index consecutive
dedup + first==last trim; if fewer than 3 survive, do not create the node (editor: node created
ringless, then culled — net node count identical). Verify: club `+2 -> 0`, chateau/helibase most of
the way to zero, `04_nyc_underground` exact without cancellation, no currently-exact level
regresses (full-corpus `degen_census.py` + `sweep_corpus.py` A/B). Pin with a regression test on
club `Brush20`'s fragment set. Consider aligning the clip band with `SplitWithNode(VeryPrecise)`'s
0.01 as a separate, separately-measured follow-up.

Harness: `dev/docs/spikes/2026-09-03-built-parity-worst-tier/harness/` — `degen_census.py` (the
corpus census), `node_frag_diff.py` (per-brush fragment dump), `club_precise.py` (full-precision
minimal repro), `find_splitter.py` (grazing-plane locator).
