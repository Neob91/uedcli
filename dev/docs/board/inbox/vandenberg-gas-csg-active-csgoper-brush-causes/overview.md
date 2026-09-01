+++
priority = "p2"
kind = "debug"
summary = "Vandenberg Gas' node/vert over-build (+606/+9480) traced to Brush230 (idx 0, CsgOper absent = CSG_Active). Live A/B/C editor test proves a real, non-trivial effect that is neither skip nor treat-as-Add -- mechanism not understood, needs disassembly. No fix shipped."
+++

# Vandenberg Gas: CSG_Active-CsgOper brush causes a real, unexplained geometry reduction

`12_Vandenberg_Gas.dx` (870 brushes) is the current worst-parity level: nodes native=11289
golden=10683 (d=+606), surfs d=+2, leaves d=-134, verts d=+9480, points d=+696, vectors d=+130 —
`LENGTH MISMATCH` on nodes/surfs/leaves (real tree-shape divergence). Confirmed on a fresh rebuild
against current master (post the OceanLab `Base`-fix and NYC 747 texture-identity fix, both
verified zero-effect here).

Full write-up, evidence, and the decisive live A/B/C test: `dev/docs/native-materialize-findings.md`,
search "Vandenberg Gas +606 node over-build".

## Summary

Per-brush attribution (surf-count + node-plane-owner) pointed at `Brush54` (world-CSG idx=3,
412-poly `CSG_Subtract`, non-uniformly scaled) as the dominant single outlier. Live isolation of
Brush54 ALONE (with a synthetic enclosing shell) showed the divergence is NOT intrinsic to its own
geometry — native produces literally zero effect in isolation while the real editor carves 472
nodes correctly. The real culprit is upstream: Brush54's true preceding context is
`[Brush230, Brush2054, Brush73]`, and `Brush230` (world-CSG idx=0) is a degenerate one-poly
`Engine.Brush` with NO `CsgOper=` property at all (an apparent stray original-game authoring
artifact — carries `LightBrightness`/`LightHue`/`LightSaturation`/`TempScale`, none normal Brush
properties).

`Engine.Brush.CsgOper`'s real class default is `CSG_Active` (ordinal 0), confirmed via
`uedcli.classdefaults`/the real `Engine.u` — NOT `CSG_Add`, which is what
`uedcli/native/brush_marshal.py::_build_brush_input` currently defaults an absent `CsgOper` to.

A decisive three-way live UED22 test (`[Brush2054, Brush73, Brush54]` preceded by a variant of
Brush230):

| build | Brush230 variant | editor nodes/surfs/leaves/verts/points/vectors |
|---|---|---|
| A | omitted entirely | 483 / 193 / 87 / 4938 / 301 / 426 |
| B | as authored (no `CsgOper=`) | **181 / 84 / 46 / 1904 / 184 / 182** |
| C | explicit `CsgOper=CSG_Add` (same geometry) | 483 / 193 / 87 / 4938 / 301 / 426 |

C == A exactly (an explicit leading Add on this geometry is a real no-op, as expected). B is wildly
different from BOTH A and C — refuting both "CSG_Active is skipped" and "CSG_Active behaves like
CSG_Add" (native's current, buggy assumption). The real editor does something else entirely for a
literal `CsgOper`-absent brush that roughly halves the resulting geometry of what follows it.
Native's own build of set B (504 nodes) reproduces neither A/C's correct value nor B's real,
drastic reduction (181) — it's simply wrong, in an unmeasured direction.

## Why not fixed

The Rust core has no representation for `CsgOper::Active` at all (`oper_from_i32` rejects ordinal
`0` outright) — there is no existing code path to redirect into. Per the standing no-guessing rule,
shipping either "treat as Add" (already what happens today, refuted by the A/B/C test) or "exclude
from world CSG" (also refuted — B ≠ A) would be shipping a confidently-WRONG behavior. The real
mechanism (why `CSG_Active` roughly halves the following subtracts' output) needs disassembly-level
investigation (`dev/docs/unrealed/extracting-from-dll.md`) not done this round — the live A/B/C test
proves WHAT happens, not WHY.

Already checked and ruled out: `bspcsg.rs`'s own already-filed `first_add_seed` gap ("a leading Add
that isn't a real world-shell corrupts everything downstream") — build C (a genuine leading
`CSG_Add` on this same degenerate geometry) matches A exactly, so that mechanism does not apply
here. This is a distinct, new, unexplained mechanism.

## Scope / regression risk

`Brush230` is the ONLY non-Mover `Engine.Brush` actor with no `CsgOper=` across every cached level
trunk checked (DX.dx, NYC Bar, UNATCO, Wanchai Market, OceanLab Lab, NYC 747, freeclinic08,
nsfhq04) — so this is very likely low-frequency across the corpus, though unmeasured beyond the
cached set. Whether the same mechanism explains part of the level's remaining diffuse 402-brush
node-owner residual (net +606 vs Brush54's own +901, heavy cancellation) is unmeasured.

## Next steps (not done this round)

- Disassemble `csgRebuild`'s per-brush dispatch (`Editor.dll`) to find what it actually does for
  `CsgOper == CSG_Active` (0) — a genuinely different branch, an off-by-one jump-table read, or
  something else. `dev/docs/unrealed/extracting-from-dll.md` has the method.
- Once understood, decide whether native needs a real `CsgOper::Active` handling path (would need
  Rust + marshal changes) and re-verify against this item's own A/B/C goldens
  (`dev/docs/spikes/2026-09-01-vandenberg-gas-node-overbuild/harness/`) plus the full level.
- Check whether other OG levels carry a similar CsgOper-absent brush (not found in the cached set,
  but the cached set doesn't cover the whole 21-level corpus).

## Harness

Committed under `dev/docs/spikes/2026-09-01-vandenberg-gas-node-overbuild/harness/`:
`vandenberg_attrib.py` (per-brush surf + node-owner attribution), `vandenberg_isolate_golden.py` +
`vandenberg_isolate_check.py` (Brush54-alone live isolation, refuted "intrinsic" hypothesis),
`vandenberg_csgoper_test_golden.py` + `vandenberg_csgoper_test_compare.py` (the A/B live builds),
`vandenberg_csgoper_explicit_add_golden.py` (the C live build), `vandenberg_csgoper_native_compare.py`
(native vs editor on sets A/B).
