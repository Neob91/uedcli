# NYC_Bar N=119 — the lightmap allocate walk skips 0-vertex nodes

**Result: one root cause, fixed faithfully, no mask.** UnrealEd allocates the world `LightMap` array
by recursing the BSP from node 0, and allocates a record only when the node it is standing on has
vertices. A vertex-less node neither allocates nor CLAIMS its surf, so a surf that also sits on a
later non-empty node gets its record at that later position. Native's walk had no vertex gate and
claimed each surf at the first node carrying it. Board:
`nyc-bar-n-119-world-model2-lightmap-array-order`.

## The divergence

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`. Over the world `Model2`,
`points` (885), `vectors` (55), `bounds` (247), `leafhulls` (2595), `leaves` (147) and `lightbits` are
byte-identical, and the 538 nodes differ only in the gate-masked occlusion bits. `lightmap` (276
records) diverges from index 144, and the surfs' `iLightMap` links shift with it.

Recovering each side's record→surf sequence from the surf links and diffing them isolates it to two
surfs — no content difference at all, just position:

| surf | native record | UED22 record |
|------|---------------|--------------|
| 174  | 144           | 228          |
| 178  | 152           | 229          |

Each of those surfs sits on exactly two nodes, and the pair is the tell:

| surf | early node | `NumVertices` | late node | `NumVertices` |
|------|-----------|---------------|-----------|---------------|
| 174  | 226       | **0**         | 447       | 3             |
| 178  | 239       | **0**         | 449       | 3             |

## What the disassembly says

`UEditorEngine::shadowIlluminateBsp` (`Editor.dll 0xa5e10`) empties the world `LightMap`, sets every
surf's `iLightMap` to -1, runs the mover pass, and then calls the recursive allocate-meshes walk
`Editor.dll 0x100a4a90` on node 0 (`0x100a60a9`). That walk is:

```text
Alloc(iNode):
  node = Model->Nodes[iNode]                       ; 64-byte FBspNode, Nodes at Model+0x58
  surf = Model->Surfs[node->iSurf]                 ; node+0x1c,        Surfs at Model+0x98
  if node->NumVertices != 0                        ; node+0x36 (BYTE)   0x100a4ae1
     && !(surf->PolyFlags & 0x400081)              ; surf+0x04          0x100a4ae7
     && surf->iLightMap == -1:                     ; surf+0x18          0x100a4af0
       surf->iLightMap = Model->LightMap.Add(1, 0x28)
  if node->iChild[1] != -1: Alloc(node->iChild[1]) ; node+0x24          0x100a4b10
  if node->iChild[0] != -1: Alloc(node->iChild[0]) ; node+0x20          0x100a4b20
  if node->iPlane    != -1: Alloc(node->iPlane)    ; node+0x28          0x100a4b30
```

Three things follow, and only the first was missing from native:

1. **`NumVertices != 0` is the FIRST test**, before the claim — so a 0-vertex node passes its surf
   over silently. (The raytrace pass `Editor.dll 0x100a5010` applies the same gate when it gathers a
   surf's node vertices, `0x100a533e`.)
2. The dedup is `surf->iLightMap == -1`, i.e. a surf is claimed only when a record is actually
   appended — never by a node that skipped it.
3. The child order is `node+0x24`, `node+0x20`, `node+0x28`. `node+0x24` is the second on-disk child
   slot, which native calls `i_back`, and `node+0x20` the first, which native calls `i_front` (same
   convention as `UModel::PointRegion`, spike `2026-09-06-pointregion-planedot-f32`) — so native's
   existing `i_back` → `i_front` → `i_plane` order was already right.

## The fix

`light.rs::lightmap_emit_order`: gate the claim on `n.num_vertices != 0`, and claim a surf only when
it is actually pushed (the editor's `iLightMap == -1`), instead of marking every surf seen on first
visit. That is the whole change; `bake`'s two concat passes are untouched.

## Evidence

- `uedcli/tests/test_engine_facts.py::test_light_apply_allocates_a_lightmap_only_at_a_node_with_vertices`
  pins the eight `Editor.dll` instruction encodings above. It lives there, not in the harness,
  because `pytest.ini`'s `testpaths = uedcli` never collects `dev/docs/spikes/`.
- `harness/test_lightmap_alloc_zero_vert_gate.py` (in the `2026-09-03-incremental-actor-parity`
  harness, which can reach the gitignored maps) re-runs the walk over every world `Model` of the
  shipped Deus Ex maps, predicting each Model's own record→surf order from its own nodes and surfs:
  **161/161 exact with the gate, 158/161 without** (NYC_Bar N=119's reference plus retail
  `03_NYC_MolePeople`, `09_NYC_Graveyard`, `14_OceanLab_UC`). 21 of the 161 carry 0-vertex nodes at
  all; the other 18 have no surf duplicated across one.
- `light.rs` unit test `lightmap_emit_order_skips_zero_vertex_nodes`.
- `parity_gate.py`: NYC_Bar N=119 PASS, no new mask. `ladder_run.py` NYC_Bar N=120.. continues past
  it; UNATCO N=1..115, WanChai N=1..44, Island N=1..122, OceanLab N=1..47 unchanged.

## The defensive sweep is unaffected

`bake` ends with a post-walk sweep that appends a record for any lightmappable surf the walk from
root missed. The gate does not widen what that sweep can do: `bake_surf` returns `None` for a surf
with no vertices, and a surf's vertex list is filled only from nodes with `NumVertices > 0`, so a
surf carried only by 0-vertex nodes has no bake to append — the same `iLightMap = -1` UED22 leaves.
The sweep can still only fire for a surf whose non-empty nodes are all unreachable from the root,
which was equally true before. Measured over the 161 shipped world Models: 0 unreachable nodes, and
the sweep fires on none of them.
