+++
priority = "p3"
kind = "debug"
summary = "UED22 keeps `Model.Surfs` across `bspRepartition` (live trace: `Surfs.Num` never moves, zero `bspAddVector` calls after it). Native clears and re-allocates them, then compensates with `reorder_surfs_canonical` + the kept Vectors pool — an emulation that silently absorbs a re-derived surf axis that drifted below the dedup threshold."
spikes = ["dev/docs/spikes/2026-09-06-island-n6-vector-pool/"]
+++

# Native re-allocates Surfs at the repartition where UED22 keeps them

Measured 2026-09-06 in `spikes/2026-09-06-island-n6-vector-pool/logs/addvector-call-trace.log`: after
the `bspRepartition` marker there is not one `bspAddVector` call, and every `bspAddNode` line reports
`nsurf=29` — the count the incremental CSG left. The editor's `EmptyModel(0,0)` clears Nodes and
Verts only; Surfs, Points and Vectors all survive, and the rebuild re-links nodes to the surfs that
are already there.

Native clears `model.surfs` at that checkpoint (`bspcsg.rs`, the repartition block) and lets
`bsp_build` re-allocate one surf per distinct source surf id, then compensates for the resulting
permutation with `reorder_surfs_canonical`. Points and Vectors are now kept (the Island N=6 fix), so
a re-allocated surf resolves its `pBase`/axes against the pools the incremental pass built.

That works because the re-derived values land within the dedup thresholds. It also means a re-derived
value that drifted — up to 2e-5 for a normal, 4e-4 for a texture axis, 0.002 for a base point — is
absorbed into the old slot instead of showing up as a divergence. Keeping `model.surfs` across the
repartition, as the editor does, would remove the compensation and the absorption together, and would
retire `reorder_surfs_canonical`.

Not urgent — no known divergence traces to it — but it is the last structural deviation at this
checkpoint, and every pool-order fix so far has been a workaround for it.
