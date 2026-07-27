+++
priority = "p?"
kind = "unknown"
summary = "Native `brush intersect` / `brush deintersect` over a piped brush SET — BUILT 2026-07-25"
+++

# Native `brush intersect` / `brush deintersect` over a piped brush SET — BUILT 2026-07-25

Replaces the editor-driven `stash intersect`/`deintersect`, which are **deleted** (no shim, per
"no back-compat cruft"); the editor path survives only as the golden REGENERATOR
(`tests/editor_oracle.py`, `-m integration`, writes only under `UEDCLI_REGEN_GOLDENS=1`). Rust:
the decoded `bspBrushCSG` Intersect/Deintersect tail fills the `bspcsg.rs:1845` stub — Phase 1
(builder faces ↓ world) + Phase 2 (world faces ↓ builder hull, reusing FWTB's straddle recursion
with a NEW non-mutating collect leaf) + the four leaf callbacks + the two-pass iLink renumber.
Python: `brushcsg.py` + the two generator verbs sharing `brush build`'s output flags, plus
`--origin`/`--pivot` re-centring. **Parity: ALL 17 goldens match the LIVE editor face-for-face,
no xfails** (`fixtures/intersect/` — ordered add/subtract/re-add, overlapping and abutting
brushes, nested and disjoint voids, thin/rotated/off-grid geometry). Landing it also fixed a
CORE bug it uncovered: the repartition left every node `NF_IsNew`, so semisolid/nonsolid detail
brushes were silently dropped from the world (`level materialize` too) — see `decisions.md`
2026-07-25. Two cold reviews resolved. Spec
board item `bspcsg-core-apply-scaled-brushes` (its §4 claim that the editor's
wrap/builder are DIFFERENT boxes is corrected — `decisions.md` 2026-07-25).
