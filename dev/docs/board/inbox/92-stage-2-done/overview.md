+++
priority = "p2"
kind = "unknown"
summary = "§92 STAGE 2 DONE (dome CAP), STAGE 3 = the dome's SLOPED facets"
+++

# §92 STAGE 2 DONE (dome CAP), STAGE 3 = the dome's SLOPED facets

Stage 2 decoded the
`Brush755` dome divergence: the cause was NOT `SplitWithPlane`/`TryToMerge` but a MISSING per-brush
pre-pass — the editor's **`bspValidateBrush`** (`Editor.dll 0x37290`) `iLink`-shares coplanar
same-facing brush faces into ONE surf. Ported into `bspcsg.rs::bsp_brush_csg` (finalized-normal gate,
exact-axis kept, temp-space remap): UNATCO N=105 `only-native` **28→20**, castle byte-identity
UNCHANGED, N=104 clean; regression + two cold reviewers resolved. Decision `rationale/MIGRATION.md` 2026-07-19
08:58 UTC; §92 §11; spec `spec.md` (LANDED). **Stage 3:** the
20 residual `only-native` at N=105 are the dome's SLOPED (non-coplanar) facets — a class
`bspValidateBrush` does not touch. Re-bisect `unatco_subset.py bisect 105 762` on `only-native` for
the next first-divergence, decode + port + castle-gate. `only-native` grows 28→534 over N=105→762 —
still a handful of classes / weeks of cycles.
