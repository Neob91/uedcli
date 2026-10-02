+++
priority = "p?"
kind = "unknown"
summary = "penetration_depths per-edge _clip_cell chain may be slow at UNATCO scale"
+++

# penetration_depths per-edge _clip_cell chain may be slow at UNATCO scale

`uedcli/actor_survey.py::penetration_depth` (around line 1179), the loop calling
`_clip_cell(bounded, normal_3d, offset_3d)` once per edge of the overlap polygon (line ~1296,
inside `for normal_3d, offset_3d in _overlap_lateral_planes(...)`) — itself inside the per-
`(source-cell, face)` loop over `cells` a few lines above.

Concern: a source cell's `half_spaces` count (and so its `_clip_cell` cost) can grow large after
`_partition_by_brushes` carves a cell against many later Subtracts in trunk order — real UNATCO-
scale content can have this. Each `_clip_cell` call is itself an H-rep → V-rep vertex enumeration
(`_polytope_from_planes`, `O(planes^3)` plane triples), repeated once per overlap edge, repeated
once per (cell, face) pair.

Unmeasured — no profiling has been done against real UNATCO-scale content. Filed per review
finding on `crosses` detection Fix 4 (session `session_01SXWrrh7Y5c7uVSn4gTgVut`), not confirmed
slow.
