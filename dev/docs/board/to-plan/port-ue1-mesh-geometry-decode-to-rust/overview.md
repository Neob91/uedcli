+++
priority = "p1"
kind = "implement"
summary = "Spec written + subagent-reviewed (2026-09-12) -- see spec.md. Ports the whole per-export mesh body (not just the hot arrays) into one Rust call, mirroring package_read.rs's pattern; deletion of the old Python decoders gated on the owner's visual sign-off over level photo + class preview renders across varied meshes in both Unreal Gold and Deus Ex. Needs plan.md next."
+++

# Port UE1 mesh geometry decode to Rust

Same profiling pass as `port-ue1-package-primitive-decode-to-rust-61m` (`level photo --native` on
original Unreal `IsvKran32.unr`, cProfile-scoped to `build_scene`, 2026-09-11). Mesh-actor triangle
extraction (`preview_native._mesh_actor_polys`, 1439 calls, 112.4s cumulative -- the single biggest
contributor to the ~75s total) spends real per-call time (not just call-count overhead) in mesh
vertex/triangle decoding:

| Function | Calls | Cumulative | Own time |
|---|---|---|---|
| `meshrender.resolve_skins` | 108 | 18.85s | 0.004s |
| `meshfacts.decode_mesh` | 108 | 15.76s | 0.007s |
| `umesh.parse_mesh` (line 235) | 108 | 7.12s | 0.50s |
| `umesh.lazy_array` (line 77) | 432 | 6.40s | 1.88s |
| `{method 'read' of BufferedReader}` | 3,542 | 7.01s | 7.01s (leaf, disk I/O) |

Only 108 DISTINCT meshes get decoded for 1439 actor instances (many instances share a mesh), so
this table is mesh-geometry parsing proper, not redundant re-decoding -- unlike the companion
package-primitive finding, this one is genuinely per-distinct-asset work: `TLazyArray<T>` element
walks (`lazy_array`), vertex/triangle/wedge table decode (`parse_mesh`), each doing struct-level
binary parsing in a pure-Python loop. A natural Rust port for the same reason as the package
primitives: self-contained format decode, no Python object-graph side effects beyond building
simple arrays, exposable via a `#[pyfunction]` mirroring `light.rs`/`render.rs`'s existing pattern.

Repro/spike: not yet committed as a harness -- do that as part of this item's spike/plan step, same
note as the companion item.
