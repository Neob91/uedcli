+++
priority = "p1"
kind = "implement"
summary = "DONE (2026-09-13): UE1 mesh geometry decode ported to Rust (parse_mesh_raw, uedcli-native/src/mesh_read.rs); umesh.py's parse_mesh is a thin wrapper. Owner visually confirmed level photo + class preview renders across varied meshes in both Deus Ex and Unreal Gold; superseded Python decoders deleted."
+++

# Port UE1 mesh geometry decode to Rust — done

Spec/plan/build all independently reviewed; corpus parity 439 meshes/5 packages, 0 mismatches.
Owner visual sign-off given after seeing `level photo`/`class preview` renders (Manderley's office
and other mesh-rich areas in `01_NYC_UNATCOHQ.dx`/`08_NYC_Bar.dx`, `IsvKran32.unr`, plus standalone
mesh classes in both substrates). Old Python decoders deleted in the same pass. Detail:
`dev/docs/board/done/port-ue1-mesh-geometry-decode-to-rust/spec.md`/`plan.md`.
