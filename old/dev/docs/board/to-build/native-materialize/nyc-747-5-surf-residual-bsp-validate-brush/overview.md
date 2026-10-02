+++
priority = "p1"
kind = "debug"
summary = "FIXED: bsp_validate_brush_links's texture-identity gate was never wired up (FPoly.texture always 0 at ingestion) -- NYC 747 surfs now byte-exact"
+++

# NYC 747 -5 surf residual: bsp_validate_brush_links texture-identity gate was never wired up

Owner-directed follow-up on the worst-parity levels. `03_NYC_747.dx`'s post-`d07622e`-fix residual
(surfs native=2021 golden=2026, d=-5) was flagged by that fix's own write-up as "plausibly the same
mechanism [as OceanLab Lab], not independently re-investigated." Directly checked: **not the same
mechanism** — a distinct bug.

Full write-up, per-brush attribution evidence, and non-regression numbers:
`dev/docs/native-materialize-findings.md`, search "NYC 747 -5 surf residual".

## Summary

Root cause: `bsp_validate_brush_links` (`uedcli-native/src/bspcsg.rs`) links two brush-local polys
into one final surf when they match on plane/normal/texture/TextureU/TextureV/PolyFlags. Its
texture-equality check (`polys[i].texture != polys[j].texture`) was an unconditional NO-OP for every
brush ever ingested: `FPoly.texture` was never populated from the T3D `Texture=` at brush-marshal
time (`brush_marshal.py`'s `_build_brush_input` / `lib.rs`'s `brush_from_tuple` never carried a
texture-identity field), so every freshly-ingested poly kept the `FPoly::new` default (0), making
0==0 always true regardless of the polys' real, different authored textures.

`03_NYC_747.dx`'s `Brush473` (291-poly `CSG_Add PolyFlags=32`) is the first brush in the investigated
corpus with two coplanar, same-facing, same-UV-axis polys that carry GENUINELY DIFFERENT T3D
`Texture=` values (confirmed for all 5 wrongly-merged pairs) — with the gate blind to texture
identity, native wrongly merged them (native 117 surfs for this brush vs the real editor's 122).

Fixed: threaded a per-poly texture-identity dedup id through the marshal tuple into `FPoly.texture`.
`bsp_validate_brush_links` itself untouched (its comparison logic was already correct, just fed a
constant). Verified against the real, live-editor-built full-level golden's per-poly `i_brush_poly`
identity (not a synthetic isolated build — the existing full-level golden already gives ground
truth). New regression test (`brush_from_tuple_threads_per_poly_texture_identity`, `lib.rs`).

**Result: NYC 747 surfs now byte-exact (2026=2026, d=+0; was d=-5).** Nodes/leaves/verts/points/
vectors unchanged (nodes d=+68, leaves d=-10) — the same still-open `bsp_build`/`FindBestSplit`
repartition-order class already open on UNATCO/freeclinic08/nsfhq04/OceanLab Lab. Not investigated
further this round.

Non-regression confirmed via `parity_report.py` on all four required goldens: `DX.dx` exact on all 6
counts; NYC Bar (`02_NYC_Bar.dx`) exact on all 6; UNATCO (`03_NYC_UNATCOHQ.dx`) nodes/surfs/leaves
exact (verts/points residual unchanged); OceanLab Lab (`14_OceanLab_Lab.dx`) surfs exact, unchanged
from its own already-shipped fix (nodes/leaves/verts/points/vectors residual unchanged). `cargo
test`: 101/101 (100 pre-existing + 1 new). Scoped pytest touching the affected native paths:
164/164.

Harness: new script `dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/nyc747_surf_diff.py`
(per-brush surf attribution, reusing `fc08_surf_diff.py`'s pattern). New permanent env-gated
diagnostic `UEDCLI_BSPCSG_LINK_DUMP` (`bspcsg.rs`'s `brush_loop1`), matching the existing
`UEDCLI_BSPCSG_PREMERGE_DUMP`/`UEDCLI_BSPCSG_SOUP_ORDER` pattern.

## Left uncommitted

This item's code changes (`uedcli-native/src/bspcsg.rs`, `uedcli-native/src/lib.rs`,
`uedcli/native/brush_marshal.py`) are uncommitted in the worktree `nyc747-parity-residual` per this
round's task instructions — the coordinating session verifies (full non-regression incl. re-running
`parity_report.py` on DX.dx/NYC Bar/UNATCO/OceanLab Lab) and commits.
