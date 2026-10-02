# Area51 Entrance / Training Final breadth check (2026-09-01)

Checked whether the `CsgOper::Active`-fix's standing 3-for-3 pattern (Vandenberg Gas/FreeClinic08/
NSFHQ04 — all `CsgOper`-absent world-CSG-index-0 brushes) applies to Area51 or Training Final.
**Negative for both**: zero `CsgOper`-absent `Engine.Brush` actors in either level's world-CSG set
(1343 for Area51, 764 for Training Final) — both are pure Add/Subtract, not affected by that fix.

Static per-brush node-owner attribution (final-tree) is diffuse on both (the fc08/nsfhq04
"wrong level of attribution" trap): Area51 548/1343 brushes differ, no dominant outlier; Training
Final 297/764 differ, with an unconfirmed static lead on 4 near-consecutive small brushes
(`Brush907`/`909`/`911`/`915`, world-CSG idx 660-668) — not live-verified this round (later
superseded: 2026-09-03's prefix search found the level's real first divergence at `Brush162`,
idx 686, a different brush — this static lead did not hold up).

**Area51: live prefix binary search localizes the ENTIRE residual to one brush, `Brush1852`.**
Converges to n=506 (`Brush1851`) exact, n=507 diverges. Decisive test: removing `Brush1852` from
the full 1343-brush level closes the residual to zero on all three counts (native and editor
independently rebuilt, both land on nodes=12580 surfs=6057 leaves=3264). Isolated addition: native
gains +135 nodes/+51 leaves; the real editor gains +50 nodes/+0 leaves — the editor absorbs this
brush's `CSG_Add` with no new leaf region, native creates 51. `Brush1852` is one of 4 placements of
an identical 6-poly shape (`Brush1849/1850/1851/1852`, same geometry+rotation); the first 3 (each a
different `Location`) build byte-identical through n=506, only the 4th diverges — rules out the
brush's own geometry, points at something positional/context-dependent in how it CSGs against the
accumulated world tree.

No fix shipped — mechanism not disassembly-confirmed (no-guessing rule). Suggestive of an
Add-brush-largely-inside-solid over-fragmentation class, same family as other worst-tier residuals,
but no live capture ties it to a specific `bspcsg.rs` path this round.

Harness: `area51_attrib.py`/`tf_attrib.py` (static per-brush node-owner attribution), 
`area51_prefix_search.py` (binary search, wraps `prefix_search_lib.PrefixSearch`),
`area51_remove1852.py` (the decisive removal test).
