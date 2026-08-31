+++
priority = "p1"
kind = "debug"
summary = "texture_ref/i_actor systematic offset (MAJOR CORRECTION content-diff finding) traced to a golden-build actor-set mismatch, not a native import/export-table bug -- REFUTES the ordering hypothesis; p_base divergence is a separate, real Points-array reorder"
depends-on = ["native-light-apply-bake-where-it-stands-and", "wanchai-verts-points-residual-independently"]
+++

# texture_ref/i_actor divergence traced to golden actor-set filter, not a native ordering bug

Follow-up to the "MAJOR CORRECTION" entry in `dev/docs/native-materialize-findings.md` (2026-08-31),
which found every surf on `DX.dx`/NYC Bar diverges in `texture_ref`/`i_actor` and hypothesized a
package import/export-table ORDERING difference. This round confirms/refutes that hypothesis on
`DX.dx` (26 surfs, smallest clean case, cached golden).

## texture_ref / i_actor: hypothesis REFUTED. Root cause found: golden is built from a deliberately narrower actor set than native.

Parsed both packages' full import/export tables (`uedcli/native/pkg_write.parse_package`) for
native's assembled `DX.dx` vs its cached self-built golden. Native: 23 imports / 52 exports / 115
names. Golden: 14 imports / 33 exports / 87 names -- not a reordering of the same content, a
genuinely different POPULATION:

- Golden is missing 19 real actors native includes: `DXLogo3`, `DXText0/1`, `DeusExLevelInfo0`,
  `EidosLogo0`, `ElectricityEmitter0`, all 16 `InterpolationPoint*`, `IonStormLogo0`, `PlayerStart1`
  -- every decorative/non-geometry/non-light actor in the trunk.
- Golden instead contains 6 `Camera6`-`Camera11` exports native has none of, and that never came
  from the pasted trunk (the keep-classes filter below doesn't keep `Camera`). These match the
  already-noted "`FovAngle`... `SpawnViewActor` reuses a free `Camera`" mechanism
  (`native-light-apply-bake-where-it-stands-and`, "Two smaller leads") -- LIVE evidence that
  `GetVisibleSurfs`'s six 90°-apart temp visibility cameras are not cleaned up before `MAP SAVE` and
  leak into the saved package as real `Camera` exports. New, confirmed fact, not previously
  live-verified.

Root cause: `build_ued_lit_golden.py` (the script every `parity_report.py` golden is built with,
including via `parity_pipeline.ensure_golden`) pastes only `{Brush, LevelInfo} ∪ light-classes`
into the editor -- by design, documented in its own docstring ("keep too much and the golden's
GEOMETRY is contaminated, because `_re_add` pastes any brush-bearing actor as a world brush").
Correct and necessary for that script's original purpose (isolating world-BSP geometry + lighting
parity from mover/decorative-actor contamination). But `parity_report.py`'s NEW `compare_content`
step (added this session, commits `ad6b11b`/`0f09f6a`) reuses this same narrowed golden to diff
native's FULL-actor-set assembled package field-by-field -- comparing two packages built from
different actor populations. `texture_ref`/`i_actor` are absolute object-ref integers into each
package's OWN import/export table; their value depends on that table's total population, so this
comparison is apples-to-oranges by construction, independent of whether native's resolver/ordering
is correct. Both sides resolve to the SAME semantic identity where checked (e.g. every surf's
texture leaf-names to `BlackMaskTex` on both sides; the referenced brush names match too) --
consistent with this being a measurement-methodology gap, not a content bug.

This likely explains a large share of the "MAJOR CORRECTION" `texture_ref`/`i_actor` diff counts
across the WHOLE corpus, not just `DX.dx` -- every level's golden goes through the same
`build_ued_lit_golden.py` keep-classes filter. NOT verified beyond `DX.dx` this round (budget); the
scale on NYC Bar (2700+ diffs, more actors/textures) is consistent with the same mechanism but
unconfirmed.

**No fix shipped, and none should be guessed at.** Two real options exist and are a design call, not
a native-code fix: (a) build golden with a WIDER actor set that still doesn't contaminate geometry
(the filter's own comment already limits "keep too much" to brush-bearing classes -- decorative,
non-brush actors like `DXLogo`/`PlayerStart`/`InterpolationPoint` don't carry brushes and may be safe
to add), or (b) make `compare_content` resolve `texture_ref`/`i_actor` to semantic identity
(resolved name/outer-chain) before comparing, instead of raw index. Both touch tooling
(`build_ued_lit_golden.py` / `parity_report.py`'s `compare_content`), not `uedcli-native/src/` or
`unbuilt.py` -- per the standing rule, logged here for a decision rather than picked unilaterally.

## p_base: a separate, real Points-array reorder -- NOT the same mechanism, and not table-ref related

`p_base` is a plain index into the `Points` array (`uedcli/native/umodel.py` `BspSurf.p_base`), not
an object-ref -- unaffected by the actor-set mismatch above. On `DX.dx`, verts/points/vectors COUNTS
are already zero-delta (the corpus table's `DX.dx ✅` verts/points/vectors column) -- no count
residual, unlike UNATCO (+16) or Wanchai (+16/-8) -- so this is a cleaner isolated case: same point
COUNT, different point ORDER. Concretely, `Brush3`'s 6 surfs (indices 0-5) use points from the set
`{0,1,2,3,4}` on both sides, but native's last three surfs walk them `2,3,4` while golden's walk the
SAME three points as `3,4,2` -- a cyclic rotation of a 3-point subset, not noise. Same shape repeats
per-brush across the rest of `DX.dx`'s 26 surfs (see round's raw dump).

This looks like the SAME FAMILY as the tracked `wanchai-verts-points-residual-independently` Points
thread (a Points-array construction/ordering divergence) but is not confirmed to be the identical
mechanism -- Wanchai/UNATCO show a COUNT delta (extra points), `DX.dx` shows pure reordering with no
count delta, which could be a different code path or just a smaller/cleaner manifestation of the
same one. `DX.dx`'s isolated, count-clean 26-surf case is a good next repro target for that thread
given how much smaller and cleaner it is than Wanchai. Not chased further this round (out of scope,
per the task).

## Reproduction

Investigation script (throwaway, not committed --
`_scratch/investigate_reftable.py` in a clean worktree run, needed because `tool_root()`-relative
`umodel_win32` resolution fails from the main checkout --
`docker-mount-source-permission-fails-from-main`): builds native's lit `.dx` via
`parity_compare.build_native_lit_dx`, parses both native and the cached `DX.dx` golden with
`uedcli/native/pkg_write.parse_package`, dumps/diffs the full import and export tables plus a
per-surf `texture_ref`/`i_actor`/`p_base` table. Not committed (throwaway); rerun trivially from the
recipe above if needed again.
