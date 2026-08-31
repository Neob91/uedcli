+++
priority = "p1"
kind = "debug"
summary = "texture_ref/i_actor systematic offset traced to a golden-build actor-set mismatch (round 1); ROUND 2: the actor-set widening was shipped SAFE (geometry counts unchanged, incl. movers-included on UNATCO) but does NOT close the divergence -- the actor-set-mismatch theory is REFUTED as a sufficient explanation, real cause is leaked GetVisibleSurfs camera exports + native/editor object-naming differences; p_base divergence is a separate, real Points-array reorder"
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

## Round 2 (2026-08-31, owner-directed): widening shipped, verified SAFE, but does NOT close the divergence

Owner ruling: widen `build_ued_lit_golden.py`'s default actor set to everything except classes that
are actually brush-bearing, determined via the class schema (not name-matching) -- then, per a
follow-up mid-task, ALSO empirically test the TRUE full set (movers included) rather than assuming
the docstring's contamination warning without measuring it.

**Implementation.** `build_ued_lit_golden.py`'s default `keep` now computes every trunk class EXCEPT
`Engine.Mover` descendants -- resolved via `classindex.ClassIndex` + the existing `movers.is_mover`
predicate (the same schema-aware check `doctor`/dispatch/native materialize already use), not a name
guess. Caught `DeusEx.BreakableGlass` on Wanchai automatically (a real Mover subclass whose name
doesn't end in "Mover" -- exactly the class of bug `movers.is_mover`'s own docstring warns
name-matching would miss). A class whose mover-ness can't be resolved (package off the search path,
or a bare-name cross-package collision that disagrees) is excluded conservatively, with a stderr
note. Added `--keep-classes ALL` (every trunk class, no filtering) and `--allow-brush-bearing`
(bypasses the existing refuse-on-brush-bearing check) so the true full set -- movers included -- can
be built deliberately for measurement; the safety refusal still gates the normal/default path
unchanged.

**Safety verification (the owner's explicit bar): PASSED on every level tried.** Geometry COUNTS
(nodes/surfs/leaves/verts/points/vectors) after widening, vs the existing narrow-actor-set goldens:

| level | nodes | surfs | leaves | verts | points | vectors |
|---|---:|---:|---:|---:|---:|---:|
| `DX.dx` (widened) | 26=26 | 26=26 | 5=5 | 250=250 | 32=32 | 6=6 |
| UNATCO (widened) | 6314=6314 | 3616=3616 | 762=762 | 76488=76488 | 10752=10752 | 599=599 |
| NYC Bar (widened) | 1620=1620 | 953=953 | 283=283 | 20878=20878 | 2762=2762 | 138=138 |
| UNATCO (movers INCLUDED, `ALL`) | 6314=6314 | 3616=3616 | 762=762 | 76488=76488 | 10752=10752 | 599=599 |

All byte-identical. Confirmed genuinely inert (not count-coincidence) via index-for-index content
comparison on `DX.dx`: nodes and leaves are field-identical, only surfs' `i_actor`/`texture_ref`
shift (the expected object-ref renumbering from a larger population).

**The owner's specific follow-up -- movers included, no exclusions, real measurement, not the
docstring's untested assumption:** built UNATCO with `--keep-classes ALL --allow-brush-bearing`
(1437 actors, 762 "brush" entries = 734 world brushes + 28 `DeusExMover`s). Result: counts
unchanged (table above) -- movers pasted via `EDIT PASTE` do **not** merge into the world model.
Confirmed structurally: the built package carries 764 `Model` exports vs 736 without movers, exactly
+28 = the mover count, each mover keeping its own small private Model (9322/9088/8515/8083 bytes
serial size, etc.) separate from the world Model -- matching the real production `MAP LOAD` behavior
the original docstring worried a paste-built golden would diverge from, not the "pastes any
brush-bearing actor as a world brush" mechanism it warned about. **So for these 28 movers, on this
level, the contamination the docstring warns about does not occur.**

It is not entirely free, though: content-level comparison found `node_flags` differs on 862/6314
world nodes (13.7%) between the movers-excluded and movers-included builds. Confirmed REAL, not
build-to-build noise -- two independent builds of the IDENTICAL movers-excluded actor set are 100%
byte-identical across nodes/surfs/leaves, zero diffs, so this harness's build is fully deterministic.
Every other node field (`plane`, `i_leaf`, `i_zone`, etc.) is untouched; surfs differ only in the
expected `i_actor`/`texture_ref` shift; leaves are 100% identical either way. A smaller
same-direction effect (20/6314 nodes) already exists between the ORIGINAL narrow golden and the
movers-EXCLUDED widened one, so `node_flags` has some sensitivity to actor population in general,
much more so once movers are added. `unrealed/quirks.md` documents `0x08 NF_PolyOccluded` +
`0x10 NF_BoxOccluded` as "occlusion bits the editor's live-viewport render pass writes... session
-dependent" in one prior measurement -- but that doesn't explain what we see here, since our own
reproducibility check shows zero session-to-session noise in this headless pipeline; the observed
bits (`8,16,64,128` and combinations) are a deterministic function of the actor set here, not of
which session built it.

**Decision: NOT shipped as the new default.** The owner's stated criterion was "if counts stay
IDENTICAL... ship the true full-actor-set default, use it everywhere" -- counts did stay identical,
but the node_flags finding is new information the criterion didn't anticipate (a real, deterministic
content difference outside the count-based bar). Also, native's OWN world-model build already
excludes movers from world CSG (`parity_compare.build_native_model` filters to
`_in_world_csg`-qualifying brushes only), so the movers-EXCLUDED widened default is the
internally-consistent choice for comparing against native's current behavior. Given a real, if
narrow, complication was found, this is a decision for the owner/coordinating session, not something
to pick unilaterally per the project's own "measure it, stop, report the evidence... wait for the
yes" rule -- flagged here rather than defaulted to "ALL".

**The motivating hypothesis is REFUTED, more strongly than round 1 found.** Re-ran `compare_content`
(native's full assembled build vs the now-WIDENED golden) on `DX.dx`, NYC Bar and UNATCO -- the
fields that were diverging before widening are statistically UNCHANGED after:

| level | before (nodes / surfs / leaves field-diffs) | after |
|---|---|---|
| `DX.dx` | 8 / 65 / 5 | 8 / 65 / 5 -- **identical** |
| NYC Bar | 2066 / 2739 / 354 | 2091 / 2830 / 637 -- **worse** (new `i_volumetric` leaf divergence) |
| UNATCO | 22202 / 10940 / 1496 | 22199 / 10941 / 1496 -- **noise-level** |

Direct export-table diff on `DX.dx` (native: 23 imports/52 exports/115 names; widened golden: 26/57/143)
shows why: even with matching actor POPULATIONS, the golden's table still doesn't match native's,
because (a) the already-known leaked `Camera6`-`Camera11` `GetVisibleSurfs` temp-viewport exports are
still present -- they leak regardless of which actors were pasted, a separate unfixed bug, not an
actor-population effect -- and (b) native's own serializer names per-brush auxiliary objects
differently from the real editor's own naming (`Model_Brush3Polys`/`Model_Brush4Polys`/... on
native's side vs `Polys6`/`Polys8`/`Polys10`/... on the golden's side) -- a structural difference
between the two build mechanisms that no amount of actor-set widening can close, since `texture_ref`/
`i_actor` are raw indices into these mismatched tables. Of the two options round 1 logged as real
alternatives (widen the actor set, or compare object-refs by resolved semantic identity instead of
raw index), only the first was tried here and it does not deliver on its own; the second is the one
now worth trying, and likely also needs the leaked-camera cleanup fixed first for `DX.dx`-scale
levels where it's a larger share of the mismatch.

**New blocker found, not chased (out of scope, budget):** `06_HongKong_WanChai_Market`'s widened
build (movers excluded, 2261 actors incl. `BreakableGlass`-excluded) CRASHES the editor reproducibly
at the first `EDIT PASTE` -- same failure point on 2 independent attempts (retry-once-then-file
applied). Its existing narrow golden is untouched and still valid; the widened one could not be
built this round. Root cause not investigated.

**State left behind:** `build_ued_lit_golden.py` is changed (uncommitted, per task instruction) to
ship the movers-excluded widened default plus the `ALL`/`--allow-brush-bearing` escape hatches; the
safety refusal is unchanged. This round's widened goldens live at `/tmp/uedcli-widen-test/` (DX.dx,
NYC Bar, UNATCO widened, UNATCO `ALL`, a UNATCO widened repro-control build) -- NOT installed over the
live shared `/tmp/uedcli-parity-cache/` cache entries, since that cache is read by other sessions and
this round's own numbers argue against silently treating "widened" as an improvement to adopt.
Installing over the live cache (or not) is the coordinating session's call.
