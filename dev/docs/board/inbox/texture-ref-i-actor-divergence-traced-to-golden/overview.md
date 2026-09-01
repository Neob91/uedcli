+++
priority = "p1"
kind = "debug"
summary = "ROUND 9 (2026-08-31, final close): raw-byte matching of texture_ref/i_actor is not achievable, not just unfinished. The full export-table CLASS set is enumerated with zero surprises across 3 goldens (DX.dx/NYC Bar/UNATCO): every export is real content (actors/Brush/Model), the Polys per-brush temp counter, the Camera6-Camera11 viewport leak, or a fixed LevelSummary+Level tail pair. But the table POSITION of real content is governed by the editor's internal UObject allocation-slot history across the whole OBJ LOAD->MAP NEW->EDIT PASTE->MAP REBUILD->LIGHT APPLY pipeline -- deterministic per fixed recipe (round 8), never derived from trunk content despite 8 rounds trying. Two of the sub-mechanisms are now confirmed categorically closed, not just hard: (1) the Camera viewport exports are proven to exist in EVERY retail Deus Ex map too (package-format.md, 4/map, universal) -- they encode which viewport a human had open at save time, information that was never in the trunk to begin with, for goldens or for the original shipped levels; (2) actor-body LatentAction bytes are proven non-reproducible by the editor against ITSELF on an identical trunk. Recommendation: keep resolved-identity comparison PERMANENTLY for texture_ref/i_actor -- this is not a workaround pending a decision, it is the only definition of 'correct' that a trunk-content-only system can ever satisfy."
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

## Round 3 (2026-08-31): `Polys` naming convention pinned; no fix shipped

Follow-up on round 2's `Model_Brush3Polys` (native) vs `Polys6` (golden) lead specifically -- the one
flagged as most likely a genuine, fixable native-code naming bug.

**The editor's naming rule, confirmed across 3 goldens.** Parsed `DX.dx`, NYC Bar and UNATCO's cached
golden export tables (`pkg_write.parse_package`), 1400+ `Model`/`Polys` exports total. A brush's inner
`Model` keeps whatever name its T3D `Brush=Model'Pkg.Model_Brush3'` line gives explicitly -- matches
native's own `Model_{actorname}` scheme exactly, no divergence there. Its `Polys` sub-object does not:
`t3d.md`'s `Begin PolyList ... End PolyList` grammar carries no `Name=` field, so the T3D importer
(golden building goes through `EDIT PASTE`, a T3D-parse path) auto-names it from the class's own
global counter: strictly `Polys<N>`, N a package-wide counter, unrelated to the owning brush. Every
golden: `N` steps by exactly +2 per successive brush in export order (UNATCO: 720 consecutive +2
steps over 723 pairs) -- never `<brush-name>Polys`.

**Why the exact N is not reproducible from the trunk.** The +2 (not +1) step means two `Polys`
objects are allocated per brush and only the even one is saved -- a discarded temp/working copy,
consistent with `quirks.md`'s already-documented extra world-aggregate `Engine.Polys` block per
level. The starting offset before the per-brush run differs by level (6 on `DX.dx`/NYC Bar, 4 on
UNATCO) and the world-model's own aggregate `Polys` lands OUT of the per-brush numeric run at an
arbitrary table position (UNATCO: `Polys1447`, appearing near the world `Model` export well before
the per-brush run tops out at `Polys1444`). None of this derives from the T3D trunk -- it's a
byproduct of `build_ued_lit_golden.py`'s own internal `EDIT PASTE`/CSG/temp-object churn in that one
editor session, which native doesn't run and can't replicate short of emulating the editor's per-brush
CSG-temp-object allocation order -- a materially bigger task than "a naming convention," out of this
round's scope.

**Renaming alone would not have closed the `texture_ref`/`i_actor` gap regardless.** Both fields are
raw POSITIONAL object-refs into the import/export index space (`umodel.py` `BspSurf.texture_ref`/
`i_actor`), not name-string lookups. Changing only the string attached to an already-reserved export
doesn't move its table position or the table's count, so a naming-only fix cannot by construction
change these fields -- table population/order is the actual lever, a separate axis from this round's
naming-convention question.

**Separate structural finding, not fixed, not this round's mandate:** `unbuilt.py`'s world-model
reservation (`lm = "Model_Level"`, `unbuilt.py:323-336`) never reserves a companion `Polys` export --
native has no counterpart to the golden's extra world-aggregate `Engine.Polys` block `quirks.md`
already documents. A genuine export-table COUNT gap (not naming), visible in the DX.dx export-table
diff (widened golden 57 exports vs native's 52). Flagged as a candidate for a future round.

**No fix shipped.** The naming convention is pinned with confidence; the reproducible value, and its
actual relevance to `texture_ref`/`i_actor`, are not. Per the task's own ground rules ("if the naming
rule ... turns out to be more complex than a simple mechanical pattern: do NOT guess/ship a fix"),
this is logged as open rather than guessed at. Full write-up in `native-materialize-findings.md`
(search "Round 3: `Polys` naming").

## Round 4 (2026-08-31): the `node_flags` follow-up, homed as its own item

Round 2's `node_flags` finding (862/6314 UNATCO world nodes differ, movers-excluded vs
movers-included) got a dedicated characterization pass — moved to its own board item since it turned
out to be about `node_flags`/occlusion mechanics, not `texture_ref`/`i_actor`:
`board/inbox/node-flags-0x40-0x80-divergence-from-movers-no/`. Short version: two-thirds of the
divergence (bits `0x40`/`0x80`) is a brand-new phenomenon with no disassembly-confirmed editor
setter anywhere in `Editor.dll`/`render.dll`/`core.dll`/`Engine.dll`/`unrealed.exe` — best-supported
(not live-confirmed) as uninitialized-memory noise tied to movers' extra per-actor CSG/paste
allocation work, not a real scene-aware algorithm. The remaining third (`0x08`/`0x10`) is fully
explained by the already-confirmed render-viewport occlusion leftover
(`node-flags-8-is-nf-polyoccluded-a-render-only`, done/) and isn't new. Neither supports switching
the default golden to movers-included; both point toward masking `node_flags` out of geometry-content
comparisons entirely regardless of which golden variant is used. Full detail in that item.

## Round 4 (2026-08-31): the "missing world-`Polys` export" from round 3 is NOT a count gap — corrected. Content of the real field is confirmed non-derivable. No fix shipped.

Follow-up on round 3's structural finding ("`unbuilt.py`'s world-model reservation never reserves a
companion `Polys` export... a genuine export-table COUNT gap"). Mandate: confirm the gap, determine
the real editor content, assess index-shift risk, ship if safe+knowable.

**Confirmed live, current tree, independently re-derived (not read from round 3 first):** golden
`dx_widened.dx` (unchanged since round 2/3) parses to 26/57/143; native's own fresh build (a
disposable worktree, needed only to work around the main-checkout's docker-mount permission bug —
see `docker-mount-source-permission-fails-from-main`) parses to 23/52/115 — exact match to round
1/3's cited number, re-confirmed on this session's tree rather than trusted.

**Round 3's "genuine COUNT gap" framing is wrong.** A per-class export diff (`Counter` over
`class_of_export`) shows `Polys`: **6 native, 6 golden — equal.** The real 57-vs-52 delta is: `Camera`
+6 (the already-known `GetVisibleSurfs` leak), `LevelSummary` +1 (new, see below), and a `Brush`/`Model`
-1/-1 wash (an unrelated, pre-existing dangling-actor artifact specific to this DX.dx trunk, already
surfaced as a live warning during native's own build: "`Brush1.Brush: refers to MyLevel.Model2, which
this level does not contain -- dropped`"). There is no `Polys`-count deficit to fix.

**What's real: a FIELD, not an export.** Native's world `Model` (`Model_Level`) never sets its own
`field_0x54` (`UModel.Polys=`) — `unbuilt.py`'s `_world_model_body` has no counterpart to
`assemble.py`'s `_empty_model_body`'s `m.field_0x54 = asm.eref(polys_name)` used for every OTHER
`Model` it writes. The golden's world `Model` DOES set it, to a real, non-empty `Polys` export.

**What that field actually points to — checked on 3 levels, confirmed NOT a stable "aggregate of
every surviving surf" (the natural reading of `quirks.md`'s `OBJ DEPENDENCIES`-based note, a
different, unrelated dump mechanism) and not reconstructible from `Model.Surfs`/`Nodes` by any
formula tried:**
- `DX.dx` (26 nodes = 26 surfs): world Polys has 26 entries spanning all 5 real brushes — looks
  aggregate-like, but inconclusive (surf count IS 26 here, a degenerate case).
- NYC Bar (1620 nodes / 953 surfs): world Polys has only **9** entries, **all one single actor** — an
  8-sided prism shape, clearly one brush's own poly set, not an aggregate of 953 surfs.
- UNATCO (6314 nodes / 3616 surfs): same pattern — only **6** entries, **all one single actor**.

Circumstantial (not live-verified) mechanism: `DX.dx`'s world `Polys15` sits numerically adjacent to
`Brush4`'s own dedicated `Polys14` (the LAST per-brush `Polys` in round 3's already-documented +2
global counter run) — consistent with the world Model's `Polys=` simply being left pointing at
whatever scratch `Polys` object the editor's internal per-brush CSG loop last touched, not a
deliberate aggregate. Would need a live `csgRebuild` capture to confirm; out of this round's scope.

**Risk (confirmed safe, now moot): `assemble.py`'s export-index resolution is fully name-based**
(`asm.index_of[name]` dict, `eref()`, body closures deferred until after all exports are reserved) —
no code anywhere indexes exports by a hardcoded position. Adding one more `_reserve()` call would not
shift or break any other reference. Round 3's "does reshuffling break a hardcoded index" worry does
not apply to this codebase.

**No fix shipped.** The count gap this was meant to close doesn't exist; the one real divergence (the
world Model's own `Polys=` field) has content confirmed wrong on 2 of 3 levels for the only formula
that seemed plausible ("aggregate of all surfs") — not merely unverified, actually refuted. Per the
standing no-guessing rule, this needs a live capture of the editor's internal per-brush CSG/`Polys`
scratch-reuse timing, not a native-code change. Full write-up: `native-materialize-findings.md`,
search "Round 4: CORRECTION to Round 3".

New, unrelated, unflagged finding surfaced (not chased): golden carries one `LevelSummary` export
(14 bytes, `"...Untitled..."`) native never emits — looks like `MAP SAVE`-time editor bookkeeping
(map-browser title metadata), not investigated further.

No production code changed this round (`uedcli-native/src/*`, `unbuilt.py` all untouched) — read-only
live re-parsing in a disposable worktree, removed after, no commits.

## Round 5 (2026-08-31): `p_base` re-verified, pinned as the pre-existing §10.20 residual, NOT the Wanchai/UNATCO Points-count bug; existing GC lever confirmed no help; no fix

Re-verified this round's `p_base` characterization via `parity_report.py` (cache hit): still 13/26
surfs diverge, same cyclic-3-point-subset-rotation shape as round 1's example, points/verts/vectors
still 0-delta. Cross-checked against `bspcsg.rs`'s `reorder_points_canonical` doc comment: this is the
SAME defect the 2026-07-18 Test_Castle spike (§10.20) already named and left open — "matches the
editor's LAYOUT (bases-first) but not its intra-block sub-order... a `bspRefresh` reachability-DFS-
compaction artifact of pre-compaction pool indices, not reconstructable from the final model" — now
reproduced byte-for-byte on `DX.dx`, just cleaner (0 count delta vs Test_Castle's own point-count
noise at the time). **Not the same bug as `wanchai-verts-points-residual-independently`'s +16
Points-COUNT residual** — that thread's `bsp_refresh_points_vectors`/`UEDCLI_BSPCSG_WORLD_KEEP_POINTS`
mechanism (a reachability GC) was tested directly against `DX.dx` and makes ZERO difference (byte-
identical `p_base` diffs on/off) — expected, since that GC preserves survivors' existing order rather
than reordering them, and `DX.dx` has nothing to GC (0 count delta) in the first place. Full
measurement + reasoning: `native-materialize-findings.md`, "`DX.dx`'s `p_base` reordering". No fix
shipped — real progress needs a live capture of the editor's Points pool CONTENT (not just counts)
during its internal compaction, which no existing harness does; per the no-guessing rule, logged as
open rather than attempted blind. No production code changed.

## Round 6 (2026-08-31): the `Camera6`-`Camera11` leak is REFUTED as a `LIGHT APPLY`/`GetVisibleSurfs` mechanism

Mandate: is the leaked-camera export set (round 1's "live confirmation of the already-suspected
`SpawnViewActor` reuses a free `Camera`" mechanism) genuinely internal to `LIGHT APPLY`, and so
something native's lighting bake should replicate — or a golden-build-script artifact? Answer: **the
golden-build-script framing was also wrong; it's a `LIGHT APPLY`-INDEPENDENT editor-session artifact.**
Native should NOT replicate it.

**Invariance across population, first sign.** Parsed 9 cached/widened `DX.dx`/NYC Bar/UNATCO golden
export tables spanning 5-195 real lights and 33-2974 total exports, across 3 different actor-set
filters plus 2 independent UNATCO rebuilds: every single one carries exactly 6 `Camera` exports named
exactly `Camera6`-`Camera11` — the count and the numeric suffix never move, regardless of how many
lights or actors were pasted.

**Decisive test: a live `--no-light` control build (the harness script already has this flag) on
`DX.dx`'s trunk — `MAP NEW` → `EDIT PASTE` (37 actors) → `MAP REBUILD` → `MAP SAVE`, `LIGHT APPLY`
never called.** Built live this round: **57 exports, still exactly 6 `Camera` exports, still
`Camera6`-`Camera11`** — byte-identical naming to every LIGHT-APPLY'd golden, with `LIGHT APPLY` never
having run. The leak predates lighting entirely.

**Corroborated by two pieces of evidence already on record but never cross-checked against the
`GetVisibleSurfs` theory:** `sections/31-package-wrapper-parity.md` (2026-07-18, `Test_Castle.dx`,
built the older UNLIT way) already documented the same "6 `Camera` viewport actors... serialized from
UnrealEd's viewport/browser session" as unreproducible session state, no `GetVisibleSurfs` theory
attached; and `dev/docs/unrealed/package-format.md`'s 88-retail-map measurement found **every retail
Deus Ex map carries exactly 4 viewport `Camera` actors**, universally, independent of content — the
same phenomenon at a much larger sample, confirming it's a normal "the editor saves its own open
viewports" fact, not an algorithm output. Why our pipeline gets 6 instead of retail's 4 is unresolved
(likely a headless-automation viewport-count difference, not examined this round — out of scope for
the question actually asked).

**Native should not replicate this.** `visible_surfs.rs` is a purely geometric port with no concept of
spawning actors/viewports at all, and there is now no real `LIGHT APPLY` mechanism here to port in the
first place — adding 6 fake `Camera` exports to native's output would be inventing content to chase a
superficial count, not replicating a verified editor quirk. Same category of gap
`materialize-verify-qualify-level-textures` already flagged for the verify path: a
package-wrapper/session-state artifact to exclude from comparison, not something for `level
materialize`'s content to reproduce.

No fix shipped, none should be — the mandate that would have justified one (a genuine `LIGHT
APPLY`-internal mechanism) does not hold. No production code touched. Full writeup:
`native-materialize-findings.md`, search "REFUTED as a `LIGHT APPLY`". Worktree
`camera-leak-investigation` left in place, uncommitted, for the coordinating session.

## Round 7 (2026-08-31): Camera-export exclusion implemented, TDD'd, shipped — measured ZERO effect on `texture_ref`/`i_actor`

Mandate: implement the round-6-confirmed Camera-artifact exclusion in `parity_report.py`'s content
comparison (precedent: `sections/31-package-wrapper-parity.md`, the same treatment as excluded
GUIDs/timestamps/name-table order), and measure whether it closes any of this thread's
`texture_ref`/`i_actor` divergence on DX.dx, `02_NYC_Bar`, `03_NYC_UNATCOHQ`.

**Camera position, confirmed on all 3 goldens: NOT always contiguous.** `DX.dx` (33 exports): 6
contiguous indices (18-23) at the tail. NYC Bar (683 exports) and UNATCO (2409 exports): scattered
among per-brush `Model`/`Polys` pairs — `[263,264,268,271,272,275]` / `[911,912,913,915,916,917]`.

**Shipped:** `parity_lib.export_renumber_map`/`renumber_actor_ref`/`renumber_surf_actor_refs` (pure,
TDD'd — 7 new tests in `test_parity_lib.py`, including the exact synthetic-interspersed-cameras
scenario the mandate asked for) + `parity_compare.golden_export_classes`, wired into `compare_content`
to renumber the golden's `i_actor` before comparing. `texture_ref` untouched by design (always a
negative import ref, never an export ref a Camera artifact could shift).

**Result: ZERO measured change on any of the 3 levels** — `surfs fields_differ`/`i_actor`
diffs/`texture_ref` diffs all byte-identical before/after (DX.dx 65/26/26, NYC Bar 2739/953/862,
UNATCO 10940/3616/3615), and the individual diff VALUES are identical too, not just the counts.
**Root cause: on every level, the maximum real `i_actor` any surf references sits immediately BEFORE
the first Camera artifact** (UNATCO: max ref 911, first Camera at export index 911; NYC Bar: max ref
264, first Camera at 263; DX.dx: Cameras are past all 12 real exports) — the artifact is inserted at a
session point that consistently comes after the last referenceable world-CSG brush, so stripping it
changes nothing on these levels even though it IS interspersed among the wider export table.

**Conclusion: this sharpens round 2's finding rather than reopening it.** The `texture_ref`/`i_actor`
divergence is confirmed to be entirely the native/editor object-serialization-order mismatch rounds
2-4 already isolated (`Model_<brush>Polys` vs `Polys<N>`, `sections/31`'s "Object numbering...
fundamentally unreproducible"), not the Camera leak. The exclusion is still shipped (uncommitted,
worktree `camera-export-exclusion`) — it's correct, zero-risk, and removes a real confound that could
matter on an untested, differently-shaped level in the corpus — but it does not, and structurally
cannot, close this thread's own divergence. `regression_gate.py`: PASS, no change. Scoped
`test_parity_lib.py` (46 tests, 7 new): pass, in the worktree's own isolated venv (a full `bin/test`
run this round hit an unrelated shared-venv `PIL`/DXT-codec flake from a concurrent session and was
not restarted per the owner's instruction not to run the full suite this session; confirmed unrelated
to this change — same test file passes clean via the main checkout's venv and via a fresh isolated
worktree venv). Full `bin/test` left for the coordinating session before it commits.
Full writeup: `native-materialize-findings.md`, search "Round 7".

## Round 8 (2026-08-31): the `Polys<N>` counter IS deterministic — and was never the lever. `i_actor` divergence closed to ZERO on all 3 levels by comparing resolved identity instead of raw table index

Mandate: decide on live evidence whether the editor's `Polys<N>` auto-name counter is derivable from
the trunk (fix native) or session state (exclude from comparison); then re-measure.

**Two independent builds of the same trunk produce BYTE-IDENTICAL tables — the "unreproducible
session state" framing is empirically wrong.** Round 2 left exactly the pair this test needs on disk:
`/tmp/uedcli-widen-test/unatco_widened.dx` (15:46) and `unatco_widened_run2.dx` (15:54) — same trunk,
same filter, separate fresh `uuid7()` editor containers, distinct GUIDs. Reparsed both: names
3357/3357 identical **in order**, imports 289/289 identical, exports 2890/2890 identical in every
field **including serial offsets**, all 736 `Polys<N>` names identical. Only the GUID differs. So the
counter is fully reproducible run to run; what it is NOT is derivable from the trunk — it counts the
editor process's own object allocations across `OBJ LOAD`/`MAP NEW`/`EDIT PASTE`/`MAP REBUILD`, and
the export table is written in `UObject` allocation-slot order with freed slots reused (the `DX.dx`
golden's actor export order matches neither trunk order nor `levelinfo_first_order`'s paste order).
`sections/31`'s practical verdict stands; its stated reason does not. A live 2-build repro on `DX.dx`
was also attempted but the host's docker `exec` is currently unstable (three separate editor
containers died mid-run); the UNATCO pair is the stronger evidence anyway (2890 exports vs 57).

**The counting rule, pinned:** `Polys4` = the builder brush's polys (its shape `Model` is named
plainly `Brush`); the world BSP `Model` is `Model2` on every level; per-brush `Polys` run `6, 8, 10,
…` (+2) in paste order, movers included; the world `Model`'s own `Polys` is the last number. So the
rule IS simple — it just starts from a session offset native has no way to know.

**Renaming was never the lever, and `i_actor` was already correct.** Both fields are raw POSITIONS in
each package's own table. Resolving each side's refs through its OWN table to the referenced object's
full dotted path:

| level | `i_actor` raw → resolved | `texture_ref` raw → resolved |
|---|---|---|
| `DX.dx` (26 surfs) | 26 → **0** | 26 → 26 |
| `02_NYC_Bar` (953) | 953 → **0** | 862 → **139** |
| `03_NYC_UNATCOHQ` (3616) | 3616 → **0** | 3615 → **0** |

**Shipped (comparison tooling only, no production code):** `parity_lib.object_paths` /
`resolve_object_ref` / `resolve_surf_refs` / `OBJECT_REF_NONE` / `SURF_OBJECT_REF_FIELDS` +
`parity_compare.object_paths`, wired into `compare_content`. TDD'd — 6 new tests including a
synthetic "identical content, different export order" case and a "genuinely different texture" case
that must still report. Round 7's Camera renumbering is strictly superseded (resolved identity is
immune to any export-table difference, cameras included) and was **deleted** along with its 7 tests —
flagged here because it removes a sibling session's just-landed work; revert that part if the
coordinating session disagrees. Harness tests: 52 pass.

`parity_report.py` before → after (`surfs` field-diff totals; nodes/leaves/geometry/lighting all
unchanged):

| level | geometry | surfs fields_differ | lighting |
|---|---|---|---|
| `DX.dx` | ✅ EXACT (6/6 counts d=+0) | 65 → **39** | ✅ 100% (26/26 records, 1536/1536 bits) |
| `02_NYC_Bar` | ✅ EXACT (6/6 counts d=+0) | 2739 → **1063** | ❌ 87.7% (821/936), 99.76% bits |
| `03_NYC_UNATCOHQ` | ❌ verts d=+5, points d=+16 | 10940 → **3709** | ❌ 83.6% (2797/3345), 99.27% bits |

**No level newly reaches content-exactness or FULL PARITY.** With the artifact gone the surf residual
is `p_base` alone (13 / 924 / 3709) — the §10.20 Points-order thread, unchanged — plus NYC Bar's 139
texture diffs. That makes `p_base` the single blocking surf field on two of the three levels, and
`DX.dx` (13 diffs, 26 surfs, geometry+lighting both already exact) the cleanest possible repro for it.

**Two new items filed from the `texture_ref` residual:**
`board/inbox/texture-group-index-misses-textures-inside-u/` (a real native bug: `.u` code packages
are never scanned for texture groups, so `DX.dx` ships `DeusExItems.BlackMaskTex` where the editor
AND the original map both say `DeusExItems.Skins.BlackMaskTex`) and
`board/inbox/golden-edit-paste-resolves-ambiguous-texture/` (NYC Bar's 139: the golden is the WRONG
side — native matches the trunk and the original shipped map).

**This thread's own question is now answered and closed.** `texture_ref`/`i_actor` are no longer a
divergence: `i_actor` is exact everywhere, and what remains under `texture_ref` is two separate,
independently-tracked texture-resolution issues.

## Round 9 (2026-08-31): is raw-byte matching achievable in principle, not just unfinished? Answer: no -- two independently-sufficient reasons, both now confirmed

Mandate (owner, via the coordinating session): round 8 closed this thread pragmatically (resolved
identity, ship it), but never asked whether the underlying raw-byte-position problem is actually
solvable if pursued further. Enumerate everything in a golden's export/import table beyond `Polys<N>`
and `Camera6`-`Camera11`, and for each unexplained piece, determine deterministic-and-derivable,
deterministic-but-not-yet-derived, or genuinely non-derivable.

### 1. The export CLASS set is fully enumerated -- zero surprises across 3 goldens

Classified every export in `dx_widened.dx` (57), `unatco_widened.dx`/`_run2.dx` (2890 each), and
`nycbar_widened.dx` (901) by class (`pkg_write.parse_package` + `class_of_export`). Every export
falls into exactly one of four buckets, no residual "unknown class" anywhere:

| bucket                                                     | DX.dx | UNATCO | NYC Bar |
|-------------------------------------------------------------|------:|-------:|---|
| real actor/asset content (Brush + every game-actor class)   |    37 |   1410 | 483 |
| `Model` (brush geometry, real content)                       |     6 |    736 | 205 |
| `Polys` (brush geometry, real content, auto-named)           |     6 |    736 | 205 |
| `Camera` (viewport artifact, NOT content)                    |     6 |      6 | 6 |
| `LevelSummary` + `Level` (save-time bookkeeping pair)        |   1+1 |    1+1 | 1+1 |

So "what's in the table" is a closed, answered question -- the open question was never "what other
kinds of objects are hiding in there" (there are none), it's "why does each object land at the table
POSITION it does."

### 2. `LevelSummary`+`Level`: new, small, and irrelevant to `texture_ref`/`i_actor`

Not previously checked for stability. Confirmed byte-identical (name, outer, flags, body, `soff`)
between the two independent UNATCO runs from round 8 -- deterministic, like everything else on that
pair. Position is a pinned, trivial rule: always the LAST two exports in the table, `LevelSummary`
then `Level`, on all 3 goldens (DX.dx 55,56 of 57; NYC Bar 899,900 of 901; UNATCO 2888,2889 of 2890).
Body is a short tagged-property blob (`b'1]\n\tUntitled\x00\x00'` on DX.dx, `b'P\x04]\n\tUntitled\x00\x01'`
on UNATCO) -- looks like it's just the map-browser title, defaulting to "Untitled" because none of
these test builds ever sets one; not fully decoded, not chased further, and it doesn't matter for
this thread: no `BspSurf` field ever references a `Level` or `LevelSummary` export, so fully pinning
this would not move `texture_ref`/`i_actor` even if characterized completely.

### 3. Real content's table POSITION: the one mechanism that actually matters, and it resists derivation for an architectural reason, not a knowledge gap

`texture_ref`/`i_actor` are raw indices into the table position real content lands at. Rounds 2-8
already established the position is NOT paste order, NOT trunk order, and NOT any formula tried
against `Model`/`Surfs`/`Nodes` -- it's "`UObject` allocation-slot order, freed slots reused" across
the full `OBJ LOAD`->`MAP NEW`->`EDIT PASTE`->`MAP REBUILD`->`LIGHT APPLY` pipeline. Round 8 already
proved this is deterministic given a fixed recipe (two independent UNATCO builds: 2890/2890 exports
identical in every field including `soff`). This round adds no new derivation -- none was found --
but reframes the conclusion: this is not "not yet reverse-engineered," it's asking for the internal
bookkeeping state of an allocator across five separate engine-internal operations that the trunk
itself never specifies. Matching it exactly would mean emulating UnrealEd's `UObject` allocator
call-for-call, not deriving a formula from level content -- round 3 already flagged this as
"a materially bigger reverse-engineering task than a naming convention," and nothing in 8 rounds of
trying (including live disassembly for the `node_flags` sub-question, see below) found a shortcut.

### 4. Two sub-mechanisms are now CONFIRMED categorically impossible, not just hard -- this is the new result

**`Camera6`-`Camera11` (round 6's finding), cross-checked against `unrealed/package-format.md`'s
independent 88-map retail measurement:** "viewport `Camera` actors (on the roster) | 4 per map, every
map | [UnrealEd's own exporter] omits **all** of them." Every one of the 88 shipped, original Deus Ex
maps -- not just our self-built goldens -- carries viewport-camera exports with no trunk-derivable
content: they record which viewport window was open on whichever human's screen when they hit File >
Save in 1999. There is no formula from level content to "which of 4 viewports had focus" because that
information was never part of the level's content in the first place -- it's UI/session state,
external to the trunk by definition, for the original retail levels as much as for any self-built
golden. This closes the door permanently, not just "for now": even a hypothetical perfect emulation of
UnrealEd's engine internals could not produce byte-identical Camera exports against a retail target,
because the missing input isn't computable, it's lost history.

**Actor-body `LatentAction` bytes (`actor-state-frame-latentaction-is-serialized`, filed alongside
round 8):** already proven the editor cannot reproduce these 4 bytes/actor against ITSELF, across two
independent builds of the identical trunk. Not a derivation gap -- the source data is uninitialized
heap memory, provably non-deterministic at the source. A hard ceiling independent of whether the
table-order problem is ever solved.

Both are now confirmed by evidence of the SAME strength as the `Polys<N>` counter's own
"deterministic but not derivable" finding, but landing on the opposite conclusion: `Polys<N>`'s
starting offset might still be derivable with enough reverse-engineering (unproven either way); these
two are proven NOT derivable, by construction, permanently.

### 5. The remaining "deterministic-but-not-yet-derived" pieces are small, separately tracked, and don't change the verdict

Not re-investigated live this round (already exhaustively attempted in rounds 3-5, all flagged as
needing a live `bspBrushCSG`/`bspRefresh`/`csgRebuild` capture this project has no harness for yet):
the world `Model`'s own `Polys=` field content (round 4, refuted "aggregate of all surfs," no formula
found on 3 levels), `p_base` Points-array intra-block order (round 5, same family, refuted formulas),
and `node_flags` `0x40`/`0x80` (`node-flags-0x40-0x80-divergence-from-movers-no`, disassembly across
5 binaries found no setter anywhere -- best-supported as uninitialized-memory noise, same family as
`LatentAction`, not live-confirmed). None of these gate `texture_ref`/`i_actor` specifically -- they
gate `p_base` and `node_flags`, tracked separately -- and none look bounded/small enough to be worth
a dedicated live-capture effort just to settle whether they're "hard" like Camera/LatentAction or
"unfinished" like `Polys<N>`'s offset; the practical answer (exclude/mask, don't chase) is unchanged
either way.

### Verdict

**Raw-byte matching of `texture_ref`/`i_actor` (and, by construction, of the whole export/import
table) is NOT achievable -- not "still open, needs more work," but closed on the evidence:**

1. The dominant mechanism (real content's table position, ~100% of every real export) is
   architecturally not a function of trunk content -- it needs the internal state of an object
   allocator across a 5-stage editor pipeline the trunk never specifies. Nothing found in 8 rounds
   suggests this shrinks to a bounded, portable rule set; every attempt (naming convention,
   actor-set widening, Camera exclusion, per-class counting) either found nothing or found the wrong
   axis.
2. Independent of #1, one confirmed real component of the table (`Camera` viewport exports) encodes
   information that was never part of any level's content, self-built or retail -- there is no
   version of "know the rules better" that recovers it.
3. Independent of both, actor body content itself has a proven non-derivable component
   (`LatentAction`) that the oracle cannot reproduce against itself.

**Recommendation: keep resolved-identity comparison (`parity_lib.resolve_object_ref`/
`resolve_surf_refs`, shipped round 8) as the PERMANENT definition of "correct" for `texture_ref`/
`i_actor`, not a workaround pending a decision.** This is not a redefinition chosen because it
measures better -- it is the only definition of correctness a system that only has trunk content to
work from can ever satisfy, since part of what raw-byte equality would demand (viewport UI state,
uninitialized memory) is provably absent from the trunk by construction, for goldens and for every
original shipped Deus Ex map alike. Nothing was built or shipped to `uedcli-native/src/` or
`uedcli/native/` this round -- pure read-only analysis of cached goldens
(`/tmp/uedcli-widen-test/{dx,unatco,unatco_run2,nycbar}_widened.dx`), no live container spin-up
needed since the determinism question was already answered by round 8's pair and the retail-Camera
cross-check only needed the already-committed `unrealed/package-format.md` measurement.

## Round 9 (2026-09-01): `p_base` -- live gdb REFUTES §10.20's "not reconstructable" framing for `DX.dx`'s simple case; exact mechanism pinned; no fix shipped (generalization to split polygons unverified)

Full detail: `native-materialize-findings.md`, "`DX.dx`'s `p_base` residual: §10.20 hypothesis
REFUTED for the simple case". Summary here since this item owns the `p_base` sub-thread.

Two new live gdb harnesses (`dev/docs/spikes/2026-09-01-dx-pbase-points-trace/harness/`,
`points_pool_refresh_trace.py` + `bspaddpoint_call_trace.py`) captured, across a real `MAP REBUILD` of
`DX.dx`'s trunk: (1) the full `Model.Points` array before/after every one of the 5 `bspRefresh` calls
the whole build makes, and (2) every `bspAddPoint` call's input point + returned pool index (new VA
`0x10035430`, resolved from the `UModel` vtable and cross-checked against the already-known
`bspRefresh` slot).

**Result: `bspRefresh`'s compaction preserves relative order (drop-orphans-and-close-gap only, never
reorders) -- the real reordering happens INSIDE the original CSG point-insertion sequence, which
follows a decoded, deterministic rule: each polygon's `Origin` first (exact dedup), then its `Vertex`
list in REVERSE authored order (tolerance dedup), walked polygon-by-polygon in authored order.** This
exactly reproduces golden's real base-block order for `Brush3` (5/5 points confirmed live) and, offline
via the same rule applied to `Brush8`'s T3D, predicts its surf 9/10/11 `p_base` = `{8,9,7}` exactly
(vs. native's current wrong `{7,8,9}`) -- not a one-brush fluke.

**Not "lost information" for this case -- native could in principle reconstruct it**, since native
already tracks CSG-processing order and has the T3D `Vertex` lists. But the full rule also needs a
periodic (per-`bspRefresh`-call) drop-and-later-readd choreography that native's current single
end-of-build `reorder_points_canonical` pass does not model, and `DX.dx`'s brushes are all UNSPLIT
whole boxes -- `UNATCO`/Wanchai's own `p_base` residual (924/3709) involves real CSG polygon splitting,
where a split fragment's vertex order isn't the T3D list at all, so this exact rule is unverified there.
**No fix shipped** -- implementing this safely needs a real architecture change to
`reorder_points_canonical` plus live re-verification on `UNATCO`/Wanchai (both currently node/surf/leaf
EXACT; a wrong generalization risks regressing that). Logged as a confirmed, narrower mechanism finding
rather than a shipped fix, per the standing no-guessing rule.

`DX.dx` stays at geometry EXACT / lighting 100% / `p_base` 13/26 -- does not reach FULL PARITY this
round. Worktree `.claude/worktrees/dx-pbase-live-gdb`, left uncommitted.

## Round 10 (2026-09-01): tried the gated, post-hoc version of round 9's insertion-order rule -- MEASURED and it makes `p_base` WORSE on all 3 tracked levels; not shipped

Full detail: `native-materialize-findings.md`, "Round 10: tried the gated, post-hoc version of the
§10.20-REFUTED insertion-order rule". Summary here since this item owns the `p_base` sub-thread.

Found that `PF_SPLIT_MARKER` (the obvious "was this split" signal) is unusable for this purpose --
it's reset every `bspBrushCSG` LOOP 2 entry for an unrelated purpose -- and built a cheaper, data-only
gate instead (`unsplit_ring::unsplit_reversed_ring`, `bspcsg.rs`, behind
`UEDCLI_BSPCSG_POINTS_ORIGIN_REVERSED`, off by default): proves per-surf, from data already in scope
(no new pipeline tracking), whether its final ring is its brush's own untouched authored polygon, and
only then replays "Origin then reversed ring" in `reorder_points_canonical`'s bases-first loop.

Measured via `parity_report.py` against the existing goldens (all 3 cache-hit, no live editor needed):
node/surf/leaf topology unaffected on every level (safety held by construction), but surf `p_base`
diffs got WORSE everywhere -- `DX.dx` 13/26 -> 20/26, UNATCO 3592/3709 -> 3612/3729, Wanchai
5249/8696 -> 5252/8699. A clean three-for-three negative result: even gated to the single safest case
(a surf PROVEN unsplit by direct value comparison, not a lineage-flag guess), a post-hoc resort over
the final model cannot reproduce the golden's true order -- confirms experimentally that the real
order needs the INCREMENTAL insertion + periodic drop-then-readd compaction replayed in build order,
which a single end-of-build pass structurally cannot do regardless of how precisely it's gated.

Not shipped -- flag stays off by default, zero effect on the default path. Kept as a negative-result
experiment with its own regression tests (`bspcsg::tests`, 2 new cases) so this specific dead end
isn't re-attempted blind. `DX.dx` remains `p_base` 13/26 -- does NOT reach FULL PARITY. Worktree
`.claude/worktrees/bsp-insertion-order`, left uncommitted.

## Round 11 (2026-09-01): live-captured a genuine CSG-split `bspAddPoint` sequence on a synthetic case -- decoded, but the split was fully transient (merged back before the final model), so the fragment rule UNATCO/Wanchai actually need is still unconfirmed

Full detail: `native-materialize-findings.md`, "Round 11: live-captured a genuine mid-CSG-split
`bspAddPoint` sequence". Mandate: round 9 pinned the insertion rule for UNSPLIT polygons only and
explicitly punted on whether it extends to CSG-SPLIT fragments -- the case that actually dominates
UNATCO/Wanchai's residual (924/3709 `p_base` diffs come from real polygon splitting, not whole-brush
in/out classification like `DX.dx`). This round tried to close that gap with a live capture.

`DX.dx` has no real split (confirmed again -- 26 nodes = 26 surfs). Built a synthetic 2/3-brush trunk
instead (a hollow room + two overlapping "pillar" `CSG_Add` boxes, 256uu overlap) via the existing
`build_ued_golden.py` + `bspaddpoint_call_trace.py` harnesses (no new gdb VAs needed -- straight
reuse). Live capture found a real split: 4 of 35 polygon groups in the 383-call trace are 9 calls
(Origin + 8 Vertex) instead of the usual 5, decoding cleanly as two 4-vertex fragment rings sharing
the cut edge, each walked in the polygon's own forward winding, with only the FIRST fragment getting
a fresh `Exact=1` Origin/`alloc_surf` call -- the second reuses it via `iLink`, exactly the branch
native's `bsp_add_node` already implements.

**But none of the 4 captured split fragments survive in the final built model** -- parsing the
golden showed all 4 straddling surfs end up as ONE whole node each, spanning the full authored range,
identical to an unsplit polygon. `bspMergeCoplanars` (already ported in native as
`bsp_merge_coplanars`, `bspcsg.rs`) fuses maximally-mergeable adjacent fragments (same plane, same
texture, sharing a full edge, no third neighbor) back together before the model is saved -- exactly
what this synthetic geometry produces. So the round captured a real split end-to-end but the wrong
SHAPE of split: it answers "what does the editor do with a split fragment that gets merged back",
not "what does it do with one that survives" -- the latter is what UNATCO/Wanchai's residual needs.

**No fix attempted.** Per the standing no-guessing rule, prototyping the incremental point-pool
architecture (rounds 9/10's scoped fix) against a rule not yet confirmed for the case it needs to
cover isn't worth doing blind. A future round needs a synthetic case built to DEFEAT the merge (e.g.
differing Y/Z extents between the two overlapping brushes -- a true T-junction, not a flush
full-height/width overlap) before the fragment-insertion-order question can be closed. No production
code touched. Worktree `.claude/worktrees/bspcsg-split-fragment-trace`, left uncommitted; the
synthetic trunk/golden/gdb log are throwaway (not committed -- the T3D recipe in the findings-ledger
entry is enough to regenerate).
