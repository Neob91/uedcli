+++
priority = "p3"
kind = "implement"
summary = "native mover sphere filter runs the full BSP node walk in pure Python"
+++

# native mover sphere filter runs the full BSP node walk in pure Python

`_precompute_sphere_filter`/`light_apply_movers` (`uedcli/native/unbuilt.py:409-504`) walks the
entire world BSP node list (`world_model.nodes`) once per mover, with a manual stack doing per-node
float arithmetic on Python attributes/tuples (`n.plane[2]`, `_f32(...)` wrapping) — O(movers × nodes)
in the CPython interpreter. Structurally identical per-node walks elsewhere (lighting flood,
visibility) are already ported to Rust with rayon (`light.rs`, `visible_surfs.rs`).

OceanLab is the ladder's mover-heavy level (`NATIVE-MATERIALIZE.md`'s lockstep ladder) and pays this
cost per mover per native build.

Fix: port to Rust, expose via PyO3 next to `brush_lightmap_indices`, which already crosses this
boundary for the adjacent per-mover step. Priority p3 (not p2) because it's OceanLab-specific and
medium effort, not a lever hit on every level's build.

Found by: 2026-09-12 performance audit (subagent-driven, native-materialize scope).
