+++
priority = "p2"
kind = "chore"
summary = "§91 — the \"native over-produces Leaves 3.6×\" gap is a CORRUPT batch golden, NOT a native defect (spike §91, decode-proven)"
+++

# §91 — the "native over-produces Leaves 3.6×" gap is a CORRUPT batch golden, NOT a native defect (spike §91, decode-proven)

The batch golden's `Leaves` array is a truncated/partial
MAP-SAVE capture: its own tree has **4454** empty terminal cells but only **762** leaf entries
(refs/leaf 9.45 — impossible for a completed Pass A, which appends one leaf per cell). Native (2759,
refs/leaf **1.00**) and the real shipped `03_NYC_UNATCOHQ.dx` (2266, **1.00**) are BOTH correctly
1:1 — native's leaf policy matches UED22's disassembled Pass A (§70 §2). **No leaf fix is needed in
native.** The defect is DETERMINISTIC, not a barrier-timing truncation: a generous-barrier rebuild
(`--quiet-reads 30 --rebuild-min-seconds 90`, knobs added §91) gives a BYTE-IDENTICAL Model body
(still 762 leaves), so a longer wait does not fix it. Two follow-ups: **(a)** root-cause why the
headless `ed.rebuild()` path emits a non-1:1 `Leaves` array AND an under-built `Verts` pool (golden
verts/node 12.11 vs shipped 15.90 — likely the same headless `MAP REBUILD` not running the full
`TestVisibility` leaf-enum + Pass-D vert re-emit) — until fixed, the cached goldens' `Leaves`/`Verts`
are un-gradeable, use the shipped map + native §70 invariants; **(b)** add a `distinct(iLeaf) ==
len(Leaves)` (refs/leaf == 1.0) assertion to `bsp_health_check.py` so this golden is rejected at the
door (it currently only range-checks `iLeaf`, which is why the invalid golden passed).
**✅ BOTH DONE (§91 §9, 2026-07-19).** (a) Root cause: `MAP REBUILD` (== `BSP REBUILD GOOD`, NO
`ZONES` keyword) runs csgRebuild+bspBuild but NOT the visibility/leaf pass — `AssignLeaves` is gated
on the `ZONES` keyword of the SEPARATE `BSP REBUILD` parser (Editor.dll 0x65482, skipped via `je`
when ZONES absent), so the on-disk `Leaves` stays the stale incremental-paste array (signature: 2750
iLeaf slots on NON-terminal nodes). Decode-confirmed via UTF-16 exec tokens + vtable-slot 0x264.
FIX = the two-step full rebuild `MAP REBUILD; BSP REBUILD OPTIMAL OPTGEOM ZONES` (BSP REBUILD alone
gives an EMPTY model — no csgRebuild); now `build_ued_golden.py`'s `--rebuild-cmd` default. (b) The
refs/leaf==1.0 assertion is in `bsp_health_check.py` (rejects the old cached goldens, exit non-zero).
**Corrected UNATCO golden: Leaves 2934 (refs/leaf 1.00), Verts 98152, Zones 9 — vs native the "3.6×
Leaves" is now −6 % (both 1:1), "+24 % Verts" is now −3.5 %, "+2 Zones" is now EQUAL (9=9).** The
ONLY real residual is `Vectors +24 %` (shipped 596 ≈ golden 599, native 745). **ROOT-CAUSED
2026-07-19 (§91 §10, decode-proven — OVERTURNS the earlier "extra node-plane normals / §80
leak-repair flipped planes" guess):** the excess is **entirely texture axes** (vTextureU +105,
vTextureV +50; surf normals IDENTICAL at 257/257/257) carried by native's **extra surfaces** from
the less-merged CSG partition. Node planes are stored INLINE and never enter `Vectors`, so the
leak-repair contributes ZERO vectors; matched surfaces agree exactly (no sign bug); and the editor
itself keeps n/−n as separate vectors (golden 310 negation pairs) so "dedup n/−n" is wrong.
**No localized `bsp_add_vector` fix exists — closing Vectors couples to the incremental-`bspBrushCSG`
port** (§80 §5, the same work that closes node/surf topology). + the §70 §13.3 CSG-shatter zone
residual on native's OWN builds. Castle golden stays 1:1 under the fix.
