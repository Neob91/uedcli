+++
priority = "p3"
kind = "debug"
summary = "DavesBrushBuilders export table qsort tie (found while fixing the name-table Core/self-name tie)"
+++

# DavesBrushBuilders export table qsort tie

Found 2026-09-13 while fixing `dev/docs/board/inbox/uscript-name-order-core-vs-package-self-name/`
(now closed — see `ordering._gather_names`'s `Class`-kind special case). `DavesBrushBuilders`'s
NAME table is now byte-exact (`test_davesbrushbuilders_name_table_byte_exact`). The package still
fails the strict `gate()` on an unrelated EXPORT-table divergence:

```
first byte diff at offset 1238 in name-table: ...
EXPORT[6] body diverges at body-offset 2
```

Root cause (isolated, not fixed): two SEPARATE 2-way ties in the export-table's `obj_key`
(reference-count) sort, both single swapped pairs, everything else in the 57-entry export table
byte-exact:

- `R` (param of `BuildTetrahedron`, `obj_key=14`) vs `R` (param of `BuildDodecahedron`, `obj_key=14`).
  Gather order (`creation_order()`, which mirrors true source declaration order — verified against
  the `.uc` source, `BuildTetrahedron` declared before `BuildDodecahedron`) has `BuildTetrahedron.R`
  BEFORE `BuildDodecahedron.R`. Golden's actual output preserves that relative order. **Our**
  `msvc_qsort`, called with the real `exp_gather` array (57 items) and the real comparator, produces
  the REVERSED order for this pair.
- `M` (local of `Extrapolate5`, `obj_key=8`) vs `R` (param of `BuildCube`, `obj_key=8`): same shape,
  opposite direction — gather has `M` before `R(BuildCube)`; golden's actual order has `R(BuildCube)`
  before `M`; ours preserves gather order (matching neither a "always preserve gather order" nor an
  "always reverse" rule — the two pairs disagree on which direction is "right").

Both pairs are genuinely isolated ties (no other export shares `obj_key=14` or `=8` among these
objects) — same clean shape as the (now-fixed) name-table Core/self-name tie. Confirmed the EXPORT
gather itself is correct: `creation_order()` reproduces the source's true function declaration order
exactly (`Extrapolate3,4,5, BuildTetrahedron, BuildCube, BuildOctahedron, BuildIcosahedron,
BuildDodecahedron, Build` — verified against the `.uc` grep).

**Not yet determined**: whether this is a genuine residual bug in the `msvc_qsort` port (surfacing
on this specific 57-item array/comparator shape, which prior instruction-exact re-verifications
apparently didn't exercise), or another gather-order modeling gap like the name-table fix (e.g. a
subtlety in how the `SphereExtrapolation`/`F`/`dR` params between the two tied pairs are ordered,
shifting `msvc_qsort`'s median-of-3 partition boundaries). Per this campaign's "reproduce, don't
special-case" rule, whichever it is needs the same rigor as the name-table fix (ideally a live
`AllocateNameEntry`-style capture of the real UCC's own qsort/gather for this exact array shape) —
not a fitted swap of just these two pairs.

Also affects (likely, unconfirmed): `ExtendedBuilders`'s still-open, larger name-table divergence
may include an export-table component of the same bug class — not checked this pass.

Repro: `uedcli/tests/test_uscript_realpkg.py::test_davesbrushbuilders_name_table_byte_exact` (name
table only, passes); `gate(_compile("DavesBrushBuilders"), golden)` (fails, this bug).
