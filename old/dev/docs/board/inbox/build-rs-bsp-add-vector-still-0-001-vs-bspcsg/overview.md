+++
priority = "p3"
kind = "cleanup"
summary = "build.rs bsp_add_vector still uses the old 0.001 texture-axis dedup tol; bspcsg.rs was fixed to the disasm-correct 4e-4. build.rs's version is only reached by build_geometry_from_brushes (old path, differential test only), so no parity impact — but the divergent constant is a latent trap, and that path is arguably deletable per no-back-compat-cruft."
+++

# `build.rs` `bsp_add_vector` still `0.001` vs `bspcsg.rs` `4e-4`

Spun off from the `bsp_add_vector` 4e-4 fix (`oceanlab-n3-world-model-divergence-bsp-add`). That fix
changed the texture-axis dedup tol to the disasm-correct `THRESH_VECTORS_ARE_NEAR = 4.0e-4` in
`bspcsg.rs` (the native materialize path). A SECOND `bsp_add_vector` in `build.rs` (L58) still uses
`0.001`.

`build.rs`'s copy is reached only by `build_geometry_from_brushes`, whose sole caller is a
differential TEST (`test_csg_native_differential.py`), never production (`materialize.py` /
`preview_native.py` call `build_geometry_bspcsg`). So no parity impact today. But the divergent
constant is a latent trap. Options: sync it to `4e-4`, or (per no-back-compat-cruft) delete the old
`build_geometry`/`build_geometry_from_brushes` path if the differential test no longer earns its keep.
Owner call.
</content>
