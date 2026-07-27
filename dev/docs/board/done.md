# Done (recent) + partially-done with remnants

Recently-completed work and `[~]` items that are substantially implemented but carry **deferred
remnants**. Kept for reference — the convention is to *delete* fully-done items, so this is a short
tail, not a permanent archive. When a remnant here becomes active work, promote it to the matching
`to-*.md` queue.

---

- **Per-surface texture verbs, STEP 1 of 5 — DONE** (2026-07-26, was `p1` on `to-build.md`; plan
  `../plans/2026-07-26-poly-surface-step1-plan.md`, spec
  `../specs/2026-07-26-poly-surface-verbs.md` §2.0–§2.2/§2.5/§3.1). `brush poly set` lost
  `--pan-to`/`--pan-by` (deleted outright, no shim) and now assigns stored ATTRIBUTES only; three new
  verbs transform the texture FRAME: **`brush poly pan (--to|--by) U,V`** (whole texels, writes
  `Pan`, never `Origin`), **`brush poly rotate --by UU`** (unreal rotation units, exact `n̂ ×` path at
  quarter turns, Rodrigues otherwise) and **`brush poly scale --by FU,FV`** (names the APPARENT size,
  so it divides the stored magnitudes). Both transforms re-anchor on the face centroid — `rotate` by
  `Origin' = C − R(C − Origin)`, `scale` by a 2×2 Gram solve, which is what keeps a SKEWED frame
  correct under a non-uniform factor. All four per-face verbs now print `BRUSH:idx` selectors on
  stdout instead of brush names (owner ruling: a bare name silently widens the set downstream).
  Durable write-ups: `../architecture.md` "Surface edits" and `../rationale/surface.md`; the
  user-facing half is in `docs/usage.md` and `docs/leveldesign/general/textures-and-surfaces.md`.
  **Built in the `poly-surface-step1` worktree; the build gate ran its full two rounds, and both
  found real defects.** Round 1: six findings plus two wording items and an extra pin — an
  `OverflowError` traceback on an arbitrary-precision `rotate --by`; `scale` naming the frame
  instead of the factor on an absurd factor; a degraded argparse message from a one-member mutex
  group; a stale CLI spelling in a live spike comparison table; the two level-design doc indexes not
  listing the new verbs; and step 1 missing from this file and misdescribed on `to-plan.md`.
  Round 2: five findings, including a **data-corruption bug round 1's own fix had introduced** —
  `scale --by` wrote a ZERO-LENGTH texture axis into the trunk at exit 0 with clean stdout, because
  the writability guard restated `emit`'s floor as six decimal places when the real floor is
  `emit.CLEAN_EPS = 1e-3` (`clean` snaps within `CLEAN_EPS` of an integer, and zero is an integer).
  Three ordinary `--by 10,10` calls destroyed a unit axis; reachable on real content at `--by 667`
  on the `0.6667` axes the editor-exported fixtures contain. Round 2 also found the same guard's
  grow side leaking the band `[1e22, ~1.3e154]` (it asked `emit.clean`, which passes those, rather
  than `emit.fmt_vertex`, which refuses them), and that BOTH of the tests round 1 added for that
  guard passed for the wrong reason. The guard now asks the serializer itself and is pinned at the
  emitted-text level. All findings from both rounds are fixed.
  **THEN THE TURN DIRECTION CHANGED, after the gate had closed.** Step 1 was built on the residual
  that `rotate` follows the *polygon* normal, which turns the texture the opposite way from what the
  author sees on a subtractive brush; a concurrent session put that to the owner and **ruling
  2026-07-27 reversed it — `n̂` is flipped on a subtract, so the verb turns against the VISIBLE
  surface normal**. Implemented as given (`surface._visible_normal`), with the ruling's own
  acceptance test pinned both ways; the docs were rewritten to describe the new behaviour, so nothing
  still describes the shipped verb as polygon-normal. This change came AFTER the two-round gate and
  therefore takes a fresh build round of its own.
  **REMNANTS, all filed separately on `inbox.md` rather than covered by this entry:** (1)
  `brush poly align` still prints touched brush NAMES while its four siblings print per-face
  selectors — the same owner ruling covers it, but the align restructure is steps 2–5; (2) a
  `CsgOper` that is neither `CSG_Add` nor `CSG_Subtract` (`CSG_Intersect`/`CSG_Deintersect`) has no
  visible surface normal for the 2026-07-27 ruling to apply to, so `rotate` currently exits 2 naming
  the value — the conservative interim, needing the owner's call; (3) a MIRRORED brush — scale
  determinant negative, i.e. an ODD number of negative components — still inverts the turn; outside
  the ruling, documented not corrected, and a geometric argument rather than a measured one.
  **`scale --to`** (absolute world units per tile) is NOT built: it needs the texture catalog, and
  it is part of step 5 on [`to-plan.md`](to-plan.md).


- [~] **`uedcli docs list|show|search` — SHIPPED, with the packaging half deliberately deferred**
  (2026-07-26, was item 11 on `to-build.md`; spec `../specs/2026-07-24-docs-command.md`, which
  doubled as the plan). uedcli now serves its own **user-facing** docs (`docs/usage.md` +
  `docs/leveldesign/**`) from the CLI, so a shipped Claude skill routes a user to a page by
  querying the tool and carries zero doc copies. `show` resolves through the enumerated served set
  rather than a path join (traversal and developer-tree leakage die structurally); a `README.md`
  folds to its directory topic and the root one to `index`; a duplicate topic key is a hard error
  naming both files; every failure is a clean exit 2 via the existing `_SelectionExit`. New module
  `uedcli/userdocs.py`, 58 tests in `uedcli/tests/test_docs_command.py`. Durable write-ups:
  `../architecture.md` "Commands (namespaced)" and `../rationale/userdocs.md`.
  **Built in the `docs-command` worktree; the build gate ran two rounds (6 findings, then 12), all
  fixed** — the round-2 set included an unreadable directory reading back as an empty one
  (`pathlib`'s glob swallows `scandir`'s `OSError`), a missing UTF-8 BOM strip on `docs show -`,
  and two user-doc claims that overstated the search ranking.
  **REMNANTS, both filed separately on `inbox.md` rather than covered by this entry:** (1) the
  wheel/Nuitka `uedcli/_docs` bundle — generation, `.gitignore`, `package-data`, the Nuitka
  `--include-data-dir`, the drift guard — so an installed build ships with no docs today and every
  `docs` verb exits 2 there; (2) two `[OWNER — confirm]` items carrying proposed `direction/`
  wording for the decisions that are his (the product intent, and the duplicate-key hard error),
  which currently live only in the agent-owned `rationale/`.

- **`POLY TEXALIGN` semantics spike — DONE** (2026-07-26, was `p1 [spike]` on `inbox.md`). Measured
  all nine of UnrealEd 2.2's surface-alignment modes live (44 faces × 9 modes twice — from a zero pan
  and from an authored non-zero one — plus eight one-wedge levels bracketing the guard thresholds,
  all via `MAP EXPORT` readback) and diffed them against `brush poly align`. Write-up +
  committed harness + a golden of every measured frame:
  `../spikes/2026-07-26-unrealed-texalign-semantics/`; durable engine facts: `../unrealed/texalign.md`
  (new) and the rewritten `POLY` section of `../unrealed/commands.md`; six regressions in
  `test_engine_facts.py::test_texalign_*`. Headline findings: **nine** mode tokens not six
  (`DEFAULT`/`WALLPAN`/`WALLCOLUMN` were missing from the doc); **`ONETILE` and `WALLCOLUMN` are
  no-ops** in UED22, so the editor has no fit-a-tile-to-a-face mode at all; `TEXELS=` is parsed and
  ignored; no mode ever changes texel density. The remaining REMNANT is not spike work — it is the
  four spec decisions the findings raise, which are the owner's and are filed as an
  `[OWNER — decide]` item on `inbox.md`.

- [~] **#12 `brush build extrude` + `brush build revolve` — SHIPPED, but the build gate's ten
  findings were ALL deferred, unfixed, at Andrzej's explicit instruction (2026-07-25).** Built in a
  feature worktree over seven commits (B1 `profile.py` → B2 extrude → B3 cap tiling → B4 revolve →
  B5 advisories → B6 the UU units retrofit → B7 doc sweep), each landing green, then squash-merged.
  Suite 2559 passed / 13 skipped, up 100 tests with no new skips. Round 1 of the build gate (1 cold
  Opus, given `CLAUDE.md` + the spec + the plan, no priming) returned **ten findings, none
  structural**; Andrzej directed in-session: *"Land what you have, fix the rest in another feature
  branch."* Because nothing was fixed, the artifact did not change and **round 2 never fired** —
  under `CLAUDE.md` "Review gates" that is the *form* of a passed gate but not the substance, since
  findings 1 and 2 are in-scope defects and the file names deferring in-scope defects to dodge round
  2 as gaming the gate. Recorded as Andrzej's ruling, a legitimate disposition, so the reason lives
  outside chat. The shipped **geometry** was independently verified correct in that round (1400
  fuzz cases + 75 configurations, zero faults) — every finding was docs or tests, none geometry.
  **All ten findings were then fixed on the follow-up branch `profile-generator-fixes`**
  (2026-07-25/26), along with the pre-existing `decimal.InvalidOperation` traceback filed beside
  them. That branch was then reviewed TWICE, and each round found defects in the previous round's
  own fixes — which is the pattern `CLAUDE.md` "Review gates" says to expect, at full strength:
  - **Round 1 (8 findings)** — including one real defect in shipped `revolve` geometry (below) and
    one bookkeeping error: the coordinate `[debug]` item had TWO halves, only one was fixed, and
    the whole entry was deleted. The unfixed half (a degenerate-but-positive `--depth`/`--height`
    naming neither flag nor value) is **re-filed on `inbox.md`**.
  - **Round 2 (13 findings), all in round 1's fixes.** The worst was a REGRESSION those fixes
    introduced: `emit.MAX_COORD` was hand-set to 1e21, a full decade below the real wall, so the
    new guard rejected coordinates `master` emitted fine (5e21 round-tripped before, exited 2
    after — enough to make an existing trunk unreadable to `actor show`/`level doctor`), while
    three places in the record claimed it narrowed nothing. The constant is gone: `_quantize6`
    asks Decimal where the limit is, so the accepted range equals the emittable range by
    construction. That also closed a hole where `clean` returned early for an integral value and
    never quantized, so `1e200` passed the "single front door" and failed later in `fmt_vertex`.
    Round 2 also caught `_denoise` being applied to only ONE of revolve's three hint families
    (the caps kept a residue-decided texture basis), a `level materialize --core coarse` flag
    written into three user docs that **does not exist** (the same not-runnable-example defect
    this batch set out to fix), spec §5.7 still carrying the superseded side-quad formula, and an
    "off by up to Δ/2" error magnitude overstated 10–20× in four places (the real supremum is
    `90° − 2·atan(√cos(Δ/2))` — 0.56° at the default 22.5° facet).
  - **Round 3 (8 findings), run PAST `CLAUDE.md`'s two-round ceiling at Andrzej's explicit
    instruction** — recorded because the ceiling is a written rule and this is a deliberate
    one-item exception, not a precedent. It earned its slot: it caught the `fmt_loc` narrowing
    described above (a REGRESSION introduced by round 2's own fix, one decade out from the one
    round 2 had caught), the nonexistent `--core coarse` flag surviving in `builders.py` and
    `architecture.md` after the record claimed it removed, the superseded side-quad formula still
    standing in the PLAN doc after the spec was corrected, a `_tex_basis` docstring claiming the
    editor-blessed parity fixtures pin its tie-break when `builder_parity.json` carries no texture
    vectors at all, and this very entry contradicting itself on the coordinate guard.
    **Every round found real defects in the previous round's fixes — three for three.** Round 3's
    own fixes ship unreviewed. Two pre-existing defects found while probing are logged on `inbox.md` rather than
  fixed: `brush vertex move` escaping as a bare `ValueError` traceback, and a 1-uu revolve
  building a non-manifold brush at exit 0 (identical on `master`). Note also that the
  "State the profile-sweep caveats…" commit additionally rewrote `--rotate`'s help on
  `brush intersect`/`deintersect`, which its subject does not mention. What the fixes added
  beyond the literal findings, and why:
  - `_hint_disagreements` in `test_profile_generators.py`. Finding 8 was that the 90° revolve case
    pinned nothing, and the reason turned out to be sharper than "thin coverage": at 90° an
    unrotated far-cap hint is exactly perpendicular to the true normal, so `_face`'s flip test
    (`_dot(nw, out) < 0`) is a no-op and the winding comes out right by accident. `doctor` can
    never see that. But `_face` also uses the hint for the emitted `Normal` and as the seed for
    `_tex_basis` — and the editor PRESERVES TextureU/V while recomputing `Normal`, so the surviving
    defect is a mis-projected texture, not a bad solid. The new oracle asserts every face's stored
    hint agrees with its own winding-derived normal and that both texture axes lie in the face
    plane. Measured on the same mutation matrix: 90° far-cap-unrotated goes 0 doctor findings → 2
    hint disagreements, sides-unrotated 0 → 32, control clean at every angle.
  - A signed-volume assertion on the extrude oracles (finding 3), since a vertex set is
    orientation-blind and `check_watertight` only catches winding that is INCONSISTENT between
    neighbours, not a uniform inversion.
  - `model.CoordinateError`, replacing a `decimal.InvalidOperation` traceback (finding 7). It
    lives in `model` because `emit` may not import `geometry` — `geometry` already imports `emit`.
    **Where the check goes took three tries, and the first two were regressions** — the durable
    lesson: a magnitude guard in the SHARED front door narrows whatever the WIDEST emitter could
    write. `emit.MAX_COORD = 1e21` (round 1) rejected vertices master emitted; moving it to the
    real 1e22 wall and probing the quantize from `_guard` (round 2) still rejected **Locations**,
    because `fmt_loc` formats with `f"{d:.6f}"` and has no precision wall at all while
    `fmt_vertex` rounds through `quantize(_SIX_DP)` and does. Either way an existing trunk became
    unreadable to `actor show`/`level doctor`. Final shape: no magnitude constant anywhere;
    `_guard` rejects only NON-FINITE (unwritable by either emitter) and `emit.quantize6` turns the
    precision failure into a named error at each quantize site. `rotation.py` quantizes at three
    sites of its own that `clean` never sees, so those route through `quantize6` too — `emit`'s
    "single write path" docstring was false for a rotated actor until they did.
  - **A real defect in shipped `revolve`, found by the round-2 review** (`builders.py`, the
    side-quad loop). The outward hint was the 2D edge normal `(dv, −du)` turned by the facet's
    mid-angle, and an in-code comment asserted that IS the quad's true normal. It is not:
    de-rotated, the true normal is proportional to `(dv, −du·cos(Δ/2))`, so the two agree only
    when `du == 0` or `dv == 0` — i.e. only for an axis-parallel profile edge. Every profile in
    the test suite was a rectangle, so nothing caught it. On a slanted edge (a tapered turned
    column, a chamfered arch ring) the hint was off by `90° − 2·atan(√cos(Δ/2))` — 0.56° at the
    default 22.5° facet, 2.27° at 45°, 9.88° at 90°, nearing Δ/2 only as Δ→180°. It never
    mis-wound a face
    (`_dot(nw, shortcut) = dv² + du²·cos(Δ/2) > 0` always), which is why `doctor` and the new
    signed-volume check were both silent — but `_face` also seeds `_tex_basis` from the hint, and
    the editor PRESERVES TextureU/V while recomputing `Normal`, so the error shipped into the
    built map as a texture basis tilted out of the face plane (measured: 20 faces at 90°/4, 32 at
    360°/8, worst axis ≈1° out). The hint is now the quad's own Newell normal, oriented outward by
    the mid-angle direction (whose sign is all that was ever needed), and `_denoise` snaps its
    float noise so `_tex_basis`'s `argmin` seed cannot flip on rounding — without that, two faces
    of the committed golden changed texture basis by 90°. `test_a_slanted_profile_revolve_has_an
    _exact_outward_hint` covers the case `CORRIDOR` structurally could not.
  **Remnant:** the spec and plan are **deliberately NOT deleted** (the usual fate of ephemeral docs
  once work lands) — delete them once the follow-up branch has merged and settled.

- [x] **#10 build review — round 1 only, round 2 SKIPPED at Andrzej's explicit instruction
  (2026-07-25).** Round 1 ran the full build tier (2 Opus + 1 Haiku, cold, given `CLAUDE.md` + the
  §10 spec text, no priming). Resolving it **did change the artifact**, so the gate's own rule would
  have fired a round 2 (1 Opus); Andrzej directed in-session that this item stop after one round.
  Recorded here rather than only in chat, per the "reason goes on the board" rule — the gate text in
  `CLAUDE.md` is unchanged and this is a one-item exception, not a precedent. **Fixed** in round 1:
  PNG round-trip removed from the breakdown path (it now returns a Pillow `Image`); `--out` naming an
  existing directory / `""` / `.` now exits 2 instead of silently writing a sibling file; NaN/inf
  dimensions now rejected by the guard (`<= 0` waves NaN through); the enforcement test widened from
  "required float flags" to "every float flag, minus an explicit angle allow-list" (a dimension with
  a DEFAULT was invisible to it) and the three places that overstated it corrected; `README.md`'s
  `--png` quickstart and its retired dev-container claim; five stale test names/comments; dead
  `single=`/`zoom=`/`zoom_region=`/`format=` kwargs in two test files; two `inbox.md` items this
  change completed or obsoleted; the 2026-07-22 ledger claim that the annotation internals "stay
  label-named" (superseded, not reworded). **Logged** to `inbox.md`: two ANDRZEJ-decide items (guard
  layer placement; the partial 10.3 rename), the pre-existing `test_zoom_does_not_highlight`
  weakness, and the red intermediate commit. The Haiku reviewer returned no findings but misreported
  the suite counts and cited spec line numbers as if read from the file — treated as low-confidence.

- [x] **#10 Preview output + naming cleanup — all four sub-items built 2026-07-25.** **10.1** PNG is
  now the ONLY on-disk preview form: `preview.py` still returns PPM/P6 bytes in memory (the
  stdlib-only guarantee), the write boundary encodes to PNG with Pillow, `--out`'s extension is
  REPLACED by `.png`, and `--png` was deleted outright. **10.2** the `_RemovedFlag` action and all 9
  shims are gone (so the two older entries below that describe `_RemovedFlag` behaviour are
  historical — the action no longer exists); deleting them re-opened a prefix-abbreviation hole (`--class` abbreviated into the
  surviving `--class-exact`, silently restoring the exact-only footgun), so the SURVIVOR was renamed
  `--class-exact` → **`--exact-class`** — load-bearing, not taste (`decisions.md` 2026-07-25 18:15
  UTC; pinned by `test_parser_find_rejects_bare_class_as_unrecognized`). **10.3** the
  preview-annotation internals renamed `label` → `annotation` (`AnnotationSpec`,
  `parse_annotation_spec`, `DEFAULT_ANNOTATIONS`, the `annotations=` render kwarg); the drawn-text
  machinery keeps "label" and both docstrings now define the two senses against the actor `label`
  dimension. **10.4** every builder verb rejects a non-positive dimension through ONE shared guard
  (`dispatch._POSITIVE_BUILD_DIMS` + `_check_positive_build_dims`), exit 2 naming flag and value;
  #12's `extrude`/`revolve` plug in by adding one table row, enforced by
  `test_every_builder_shape_declares_its_positive_dimensions`.

- [x] **Review-gate rounds 2 and 3 on the same batch — resolved 2026-07-25.** Round 2 (two cold
  reviewers) withdrew the round-1 "the move is a COPY" inference (see the round-1 entry below),
  tightened `container_stat`/`container_file_head` so a `stat`/`od` FAILURE no longer reads as "file
  absent", added the minimum-table-size rule, hoisted `brush scale --pivot-actor` above the class
  resolver, and corrected the `is_solid`/seven-verbs/caller-name claims. Round 3 (**three** cold
  reviewers — load-bearing code) found the fixes' own defects: three quoted measurements were wrong
  (the corpus is 264 packages on the composed path, not an ad-hoc 230; the offsets-only worst case is
  99.0 %, not 99.8 %; the tightest per-entry margin is 4 bytes in `Quotes_Music.umx`, not 22 in
  `MPCharacters.u`), the per-entry minimums contradicted their own derivation (now the true bounds
  5/7/12, which also shrinks the blind window), the header-verdict cache was permanent and justified
  by the very hypotheses round 2 had withdrawn (now bounded by `recheck=30 s` and reset when the file
  vanishes), the pre-save-stat signal had two surviving mutations, and the `core.dll` extraction had
  landed with **no committed harness and no regression** — the one rule that keeps a spike from
  rotting. That is now `spikes/2026-07-25-map-save-mechanism/` (two harnesses + write-up) plus
  `test_engine_facts.py`, which re-asserts both the string-run order AND the "no `ReadFile` ⇒ the
  import table settles nothing" negative so the retracted inference cannot be re-derived silently.
  **Left standing, with reasons:** `preview.classify_brush`'s name-suffix predicate (logged in
  `to-spec.md` as part of the open scoping decision — pre-empting it is Andrzej's call, not the
  batch's), and the unpushed commits (the orchestrator owns pushing this branch). **A round-3
  finding was dismissed as a false positive:** `--pivot`/`--pivot-actor` are already an argparse
  mutually-exclusive group on both `brush scale` and `actor rotate`, verified by running both.

- [x] **Review-gate round 1 on the five-fix batch — resolved 2026-07-25.** Two cold reviewers over
  `432e65163..`: the biggest finding was that the `map_save` docs justified the structural check with
  a save mechanism this editor does not use — `UObject::SavePackage` writes `Save.tmp`, rewrites the
  header LAST inside it, and then MOVES it onto the target (📖 `core.dll` strings, now a documented
  UnrealEd fact in `unrealed/commands.md` + `spikes/2026-07-25-map-save-mechanism/`). **Round 2's own
  follow-up correction, recorded here because this entry first got it wrong too:** whether that move
  is a rename or a byte COPY is NOT determined — `core.dll` imports no `ReadFile` either, so its file
  I/O bypasses the import table entirely and the missing `MoveFile*` proves nothing. The check stands
  as insurance; the rationale, `architecture.md`, the `map_save` docstring and the `decisions.md`
  entry were corrected, and `commands.md`'s "truncated `Leaves` array" example was retracted (spike
  §91 disproved it). Also: `settle`/`stable_reads`, the per-probe `timeout=`,
  the elapsed-time message, the empty-file guard, the offset lower bound, the probe scripts and the
  magic-vs-`upackage` parity are now each pinned by a test (11 mutations applied to `driver.py`, all
  11 caught, none before); `container_stat`/`container_file_head` no longer collapse a `stat`/`od`
  FAILURE into "not there"; `brush scale --pivot-actor` resolves its actor before the class resolver
  too; `test_real_class_hierarchy_decides_mover_ness` now covers the case-sensitivity half of the
  re-measurement; the `build_ued_golden` harness dropped its own retired size-only wait; and
  `test_qualify`'s hand-rolled canonicalization loop is deleted (covered by `test_movers` +
  `test_prefab_migration`). Three findings deferred to `inbox.md` with detail: the remaining unbounded
  `docker exec` calls (count corrected to 8 across 6 methods + `xfer.py`), the missing `map_save`
  integration test, and the `Save.tmp` collision/leftover.

- [~] **The second name-suffix mover predicate: claim corrected, FIX deferred into the open scoping
  spec — `inbox.md` `[implement] p2` re-homed 2026-07-25.** `preview.classify_brush` still uses
  `bare.endswith("Mover")`, which falsified `architecture.md`'s "no name-guess fallback anywhere".
  The docs now state what is true (one surviving name test, outside `is_mover`, with its live
  divergence spelled out) and the FIX is folded into `to-spec.md`'s open "why do SEVEN verbs require
  the games config?" item as an explicit part of its scope — threading a `ClassIndex` in would make
  `actor`/`stash`/`prefab preview` an eighth resolver-requiring verb family while that item is
  asking to scope the requirement back down. **Remnant:** the divergence is live until that item is
  answered.

- [x] **`brush scale`'s flag-conflict check moved above the resolver — `inbox.md` `[chore] p3`
  CLOSED 2026-07-25.** The `--to` + `--pivot`/`--pivot-actor` mutual-exclusion check sat below
  `_mover_index`, so `brush scale --to 2,2,2 --pivot 0,0,0` with no games config blamed the missing
  config instead of the conflicting flags. Now checked with the other cheap argument checks, pinned
  by a regression that stubs the resolver seam to raise.

- [x] **The two zero-caller `canonicalize_mover*` helpers DELETED — two `inbox.md` `[chore] p3`
  entries CLOSED 2026-07-25** (the dedicated one and the older `canonicalize_mover_blob` duplicate).
  `canonicalize_movers_in_level` and `canonicalize_mover_blob` had no production caller — the latter
  explicitly "retained for callers/tests", the shim pattern `direction.md` "No back-compat cruft"
  forbids — so both are gone, with the two blob tests. `test_qualify.py`'s level-granularity test was
  first rewritten to loop `canonicalize_mover` itself and then, in the review round below, deleted
  outright — it exercised a loop the test had written, and the real funnel is covered by
  `test_movers` + `test_prefab_migration`. Its comment had claimed a "live-qualify funnel
  mover-canonicalization step" that `qualify.py` does not have, and deferred to a
  `test_mover_integration.py` that does not exist. `architecture.md` corrected on the same point: the
  fold runs at ONE funnel (capture), not two. The `2026-07-15-native-materialize` spike harness was
  updated to the per-actor loop so it still runs.

- [x] **Three #9.4 documentation claims corrected — `inbox.md` `[chore] p3` CLOSED 2026-07-25.**
  (a) `architecture.md` said a bare class name resolves as an OR ("a mover if ANY candidate
  descends"); the code requires the candidates to AGREE and raises `ClassRefError` on a split.
  (b) `docs/usage.md` listed `level materialize` and `level preview` among the verbs that ask the
  mover question — neither does (only `level preview --native` reaches `_mover_index`); they need
  the same config for an unrelated reason, now stated as such. (c) `decisions.md` 2026-07-25 10:18
  UTC's "12 classes / four rejected" enumeration was re-measured against the real composed path
  (**9** case-sensitive `*Mover` names, 12 only case-insensitively; **17** `Engine.Mover`
  descendants; **8** real movers rejected by the old guess; **0** false positives) and corrected in
  place with a dated note — the decision itself stands.

- [x] **`driver.map_save`'s write verification rebuilt — `inbox.md` `[debug] p1` CLOSED 2026-07-25.**
  The old rule ("two equal non-zero sizes ⇒ finished"; "`stat` exit 1 ⇒ no file, anything else ⇒
  docker failed") could not tell *finished* from *stalled* (a truncated map's size is just as stable
  as a finished one's) nor *file-missing* from *container-dead* (a stopped container, a missing
  container and a permission error ALL exit 1 — re-verified live), and its `subprocess.run` had no
  `timeout=`. Replaced by four stacked signals: a pre-`MAP SAVE` stat the file must differ from; N
  equal readings across a settle window; a structural check of the written package's header
  (`driver.package_header_problem`); and liveness from a probe SENTINEL, not an exit code, with each
  `docker exec` bounded. `container_file_size` is deleted in favour of `container_stat` /
  `container_file_head` / `package_problem` over one `_container_probe`. The two tests that could not
  fail (both passed `timeout=0.0`) and the docker-failure test that mocked an impossible
  `returncode=126` pairing were rebuilt on a fake clock that exercises the real 600 s/1 s/3 s
  defaults. `decisions.md` 2026-07-25 11:31 UTC; `architecture.md` "Editor driver";
  `unrealed/commands.md`. **Remnant → `inbox.md`:** driver's other `docker exec` calls (8 across 6
  methods, plus `xfer.remove`) are still unbounded.

- [x] **`movers.is_mover` is SCHEMA-AWARE — `to-build.md` #9.4 BUILT 2026-07-25** (the last #9
  sub-item; the `## 9.` section is gone). Mover-ness is now "does the class descend from
  `Engine.Mover`?", resolved against the offline `classindex.ClassIndex`, replacing the
  `bare.endswith("Mover")` guess that BOTH rejected real movers (`CaroneElevatorSet.CEDoor`,
  `…CaroneElevator`, `DeusEx.BreakableGlass`) and accepted non-movers (`Engine.Remover`). Andrzej
  resolved the open sub-question — **"Doctor may require config": one predicate, no split**
  (`decisions.md` 2026-07-25 10:18 UTC) — so `is_mover(actor, index)` takes the index at EVERY call
  site (doctor, event graph, native preview, native materialize, brushcsg, the dispatch verbs), and
  a run with no class resolver RAISES (clean exit 2 naming the verb) instead of calling every mover
  a static brush. The editor-authored-keyframes caveat is deleted from
  `docs/leveldesign/deusex/recipes/elevator.md` Parts 2–3, and the native build's `*Mover`-suffix
  CSG-leak gap (was an `inbox` chore) is closed with it. **Remnants → `inbox.md`:** the resolver
  requirement widened to six more verbs (flag), and `canonicalize_mover_blob` has no production
  caller (chore).

- [x] **Small fixes batch — five of `to-build.md` #9 BUILT 2026-07-25** (one commit each; 9.4, the
  schema-aware `mover key` gate, landed separately — see the entry above).
  **9.1** `class show` now EXITS 2 naming an unreadable/missing ANCESTOR package instead of printing
  own-only props with a stderr note — the degrade branch, its `--category` special case and
  `test_class_show_category_rejects_degraded_schema` are deleted (`direction.md` "No silent
  half-answers"); the fallback's last user, `ClassIndex._package`, went with it. **9.2**
  `driver.map_save` WAITS FOR and VERIFIES its own output (and returns the size): driving is
  fire-and-forget and `MAP SAVE` answers nothing over the console, so it polls the file inside the
  container, raising `DriverError` naming the path on timeout — instead of letting a wedged editor
  surface as an opaque `docker cp` exit 1. (The review gate caught that the first cut checked ONCE,
  immediately, which false-fails a slow save. The engine fact is pinned in `unrealed/commands.md`
  "Driving is fire-and-forget"; the "truncated golden" this entry originally cited as the other
  motive was later RETRACTED — spike §91 showed that golden is deterministic, not truncated.)
  **Its accept rule was REPLACED 2026-07-25** — the two-equal-sizes + `stat`-exit-code version
  described here is gone; see the entry below and `decisions.md` 2026-07-25 11:31 UTC.
  **9.3** `actor folder set/unset` are PRODUCERS (touched Names → stdout, count → stderr), so the
  folder and label dimensions now behave identically and folder edits chain in a pipeline.
  **9.6** `uedcli cache gc [--max-bytes N] [--max-entries N]` wires the shipped
  `schema_cache.sweep()` to the CLI (reclaim orphaned `v<N>/` dirs + LRU-evict to a cap; a negative
  cap exits 2). Docs updated in the same commits (`usage.md`, `architecture.md`).
  **9.5 was MOOT as written** — its premise (the two `test_native_materialize.py` box-sweep tests
  die on the spike harness import) does NOT reproduce: both PASS at HEAD, because `line_check.py`
  now sits in the spikes tree and self-inserts its sibling harness on `sys.path`. Marking two GREEN
  tests skipped would have deleted real coverage of the "pawn falls through the floor" bug, so
  instead `_load_line_check()` now turns a harness-side `ImportError` into a SKIP naming the spike
  env while letting a `uedcli` `ImportError` propagate (a real regression must stay red). Flagged on
  `inbox.md` for Andrzej.

- [x] **Mover `SavedPos`/`SavedRot` stripped as engine-stamped — FIXED 2026-07-25 03:07 UTC.**
  `level materialize` (and `preview --game`'s internal build) aborted on EVERY map containing a
  mover: the rebuilt map's re-export carries `SavedPos=(-12345,-12345,-12345)` and
  `SavedRot=(Pitch=123,Yaw=456,Roll=789)` that the trunk never emits, and neither is a class
  default. `AMover::PostLoad()` writes both unconditionally on every load of a Mover object —
  disassembled BY NAME out of both shipped engines (UED22 `Engine.dll` `?PostLoad@AMover@@UAEXXZ`
  RVA 0x171140; DX `Engine.dll` RVA 0xaf7e0), no guard, right after `Super::PostLoad()` — so no
  authored value can survive a round trip. Fix: add the two to `normalize.COMPUTED_PROPS` beside
  `BasePos`/`BaseRot`. Live-confirmed end to end: the built `.dx` holds NO sentinel, the
  post-verify's own UCC re-export of that same file does, and materialize now passes. `SavedTrigger`
  is excluded FOR CAUSE — `Engine.TriggerLight` declares its own, and the set is keyed by bare name
  across all classes. Two adjacent suspicions from the bug report (`bDynamicLightMover`, `KeyPos[]`
  echoes) were live-checked and DISPROVED — both re-export verbatim, so they are authored content.
  Spike `spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/` (harness: `scan_corpus.py`,
  `disasm_postload.py`); decision `decisions.md` 2026-07-25 03:07 UTC; `unrealed/t3d.md`
  authored-vs-computed taxonomy; `architecture.md` "Mover support". Pinned by
  `test_engine_facts.py::test_amover_postload_unconditionally_stamps_the_savedpos_savedrot_sentinels`
  plus three `test_normalize.py` regressions.
  **Remnant** (filed on `inbox.md`, `[chore] p2`): `level preview --game`'s internal materialize
  still runs the H3 post-verify with no way to skip it, though a preview `.dx` is throwaway.

- [x] **The post-verify compares TYPED effective values; contraction DELETED — BUILT 2026-07-25
  02:15 UTC.** The compare seam stopped canonicalizing text and started comparing values: every
  property of both sides resolves to the stored value if stated, else the class default, decoded by
  its DECLARED type (`typedprops.py` = pure value semantics; `classdefaults.ClassDefaults` compiles
  the decoded `.u` schema + defaults into it, one resolution per distinct class). Two actors are
  equal iff they would import to the same object. `normalize.contract_actor`,
  `normalize._is_all_zero_struct`, `classdefaults.values_equal` and
  `rotation.canonical_rotation_value` are gone — one mechanism, not two. Fixes three things
  contraction could not: `4.0` == `4` (typed float, at float32); an omitted struct member takes the
  DEFAULT member, not zero (`Engine.Camera`'s `Location=(X=100,Y=200)` is Z=300, carried through
  `parse_t3d` by the self-invalidating `Actor.location_text` side-channel, which keeps the parser
  schema-free); and an explicit zero SCALAR/bool compares equal to an omitted line via the type's
  zero from the schema, while a `StrProperty` reading `0` still does not. Also generalizes the
  member-diff to EVERY struct prop and normalizes enum name-vs-ordinal. `verify._first_diff` now
  names the differing PROPERTY and both values (or the class default the omitting side falls
  through to). Decision `decisions.md` 2026-07-25 02:15 UTC; `unrealed/t3d.md` "Partial
  struct/array property values"; `architecture.md` "The compare view vs the identity hash".
  **Remnant** (filed on `inbox.md`, p2): ingest still WRITES a partial `Location` back zero-filled.

- [x] **Native mesh decode + render — SPIKED 2026-07-25** (`spikes/2026-07-25-native-mesh-decode/`).
  The complete UE1 `UMesh`/`ULodMesh` body decodes in pure Python, verified consume-to-exact-end on
  **902 meshes** (466 retail Deus Ex v68 + 436 UED22 v69), and renders textured thumbnails offline —
  no editor, no container, no `umodel.exe`. Five non-guessable findings pinned by
  `tests/test_mesh_decode.py`: `FMeshAnimSeq.Group` is a single FName (not a TArray) and its
  serialized order puts `Notifys` before `Rate`; `UMesh` re-serializes its own bounds inline while
  per-frame bounds are plain TArrays; `SpecialVerts` sit at the FRONT of each frame (wedge indices
  are relative to `frame_base + SpecialVerts`); the 5-byte `ULodMesh` tail is stock UE1, not a
  licensee addition. Vertex stride (DX 8-byte int16 quad vs stock 4-byte packed dword) is
  **self-describing** via the TLazyArray skip offset, so ONE decoder serves both — the generic-UE1
  goal. Class thumbnails resolve skins from CLASS defaults (`MultiSkins[i]`), not the mesh's own
  Textures array. **Remnants:** productise the harness into `uedcli/` (rides the asset-catalog
  build); `RemapAnimVerts` element layout unverified (empty everywhere in the corpus).

- [x] **Class-default contraction at the compare seam + the write side stops omitting to mean
  zero — BUILT 2026-07-25 00:36 UTC.** UnrealEd omits what equals the CLASS DEFAULT; uedcli tested
  against ZERO. Fixed in four parts: (1) `normalize.contract_actor` (fed by `classdefaults.ClassDefaults`)
  contracts BOTH compare sides against the real class defaults — whole property, `Rotation` members,
  `Location`, and the editor's `Tag=<class>` default-stamp (the last only where the class does not
  itself default `Tag`, since `TNM.Trestkon` defaults `Tag='Player'`); (2) `canonical_level_hash` is
  now PURE and schema-free (it is the preview build-CACHE KEY) with the post-verify moved to a
  separate `normalize.compare_view`, which `verify._first_diff` also consumes (the duplicated
  reduction is gone); (3) class defaults resolve BEFORE the editor container exists, `defaults` is a
  REQUIRED no-fallback argument of `verify_dx_matches`, and an unresolvable class exits 2 naming the
  actor; (4) four write paths stopped omitting a property to mean zero — `actor rotate --to/--by`,
  `brush build --rotate`, `normalize_actor`'s all-zero `Location` clear and its `Tag` strip, and
  `transform.bake`'s `PrePivot` drop. Three of those were SILENT wrong-map bugs that post-verify
  passed. Two cold reviews resolved. Decision `decisions.md` 2026-07-25 00:36 UTC; `unrealed/t3d.md`
  "Partial struct/array property values"; `architecture.md` "The compare view vs the identity hash".
  **SUPERSEDED 2026-07-25 02:15 UTC** — the contraction MECHANISM (parts 1's `contract_actor` and
  its helpers) was replaced by the typed effective-value compare above, which also closed both of
  this item's remnants; parts 2-4 (the pure identity hash, the no-fallback up-front resolution, and
  the write-side rule) stand.

- [x] **Native `brush intersect` / `brush deintersect` over a piped brush SET — BUILT 2026-07-25.**
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
  `specs/2026-07-24-intersect-deintersect-native-brushset.md` (its §4 claim that the editor's
  wrap/builder are DIFFERENT boxes is corrected — `decisions.md` 2026-07-25).

- **Generator-flag cleanup: `--folder`/`--label` move to the generators; ditch `--group`** — BUILT
  2026-07-24 (`22f82b8a8` code + `960275b0d` docs; suite green). Three parts, all shipped: (1) `--folder`
  + repeatable `--label` added to the `brush build` shapes and `actor build` (they emit the existing
  `// uedcli-folder:`/`// uedcli-labels:` carriers); (2) both flags REMOVED from `actor add`, which is now
  a **pure carrier-consumer** (post-hoc organization = `actor folder set` / `actor label`) — an explanatory
  comment at the `actor add` parser records why; (3) `--group` dropped from `brush build` in favour of
  `--prop Group=`. The two surviving `--group` flags are out of scope and intentionally kept (`prefab/stash
  place`'s placement group, `actor find --group`'s engine-prop filter). REVERSES the folder/label-on-`actor
  add` rule; `direction.md` ("Folders"/"Labels"/"Generator pattern") reconciled, `docs/usage.md` updated,
  tests migrated (`test_generators.py`/`test_folders.py`/`test_labels_verbs.py`/`test_cli.py`). Coupled
  prerequisite for the native `intersect`/`deintersect` item (still in `to-plan.md`), which shares
  `brush build`'s output-flag set. Decision `decisions.md` 2026-07-24 17:04 UTC; spec
  `specs/2026-07-24-generator-flag-cleanup.md` (status corrected).

- **`actor preview` param cleanup — `--layout`/`--frame`/`--show`, point-actor panes, optional `--out`**
  — BUILT 2026-07-24 (`a97573383`; suite green). The shared `cli.py::_preview_opts` helper (used by
  `actor`/`stash`/`prefab preview`) went 17 flags → 13, with every hidden-interaction rule removed:
  `--single`+`--breakdown` → **`--layout {quad,single,breakdown}`** (default `quad`, so mutual exclusion
  is free); `--zoom`+`--zoom-region`+`--zoom-factor` → **`--frame TARGET`** (one input taking either a
  `BRUSH[:IDX]` selector or an explicit six-field world AABB) + `--frame-tightness`; the three
  `--show-*` booleans → one comma-set **`--show`**; `--out` made optional (a `uedcli-preview-*` temp file
  is minted and its absolute path printed). `--layout breakdown` now gives each **point** actor its own
  captioned pane (framed via `_point_pane_region`, expanded to at least `Location ± 32 UU` so a
  zero-extent marker centres instead of jamming into a corner — regression-pinned). A **breaking CLI
  change** across the three verbs; each removed spelling errored via `_RemovedFlag` with a migration
  message (matching the `--class`/`--zoom-poly`/`--split` precedents). Decision `decisions.md` 2026-07-24
  19:01 UTC; spec `specs/2026-07-24-preview-params-cleanup.md` (status corrected).

- **`class list`/`class show` — orthogonalize the overloaded `--all`** — BUILT 2026-07-19 (`7b7664a67`),
  surfaced 2026-07-24 as untracked-DONE work in a board audit (it was built directly, never on the board;
  spec header was stale at "draft"). `--all` split into `--include-non-actor` (E1 reroot
  `Engine.Actor`→`Core.Object`), `--include-abstract` (E2 show abstract/non-placeable), and `--depth N|all`
  (E3 depth, unified spelling on both verbs; `all`→`math.inf`, uncapped); hidden `--all` emits a targeted
  split-hint. Defaults unchanged; tests migrated (`test_class_discovery.py`/`test_ingest_validation.py`,
  green). Spec `specs/2026-07-18-class-flag-orthogonalization.md` (status corrected), decision
  `decisions.md` 2026-07-19.

- **`actor preview` — on-face number overlap: minimal reshuffle + white keyline + lower opacity** —
  BUILT 2026-07-23. p2. When two numbers overlap on screen (incl. two faces of one brush), `_resolve_decals`
  applies a TINY nudge — shrink ≤10%, move ≤10% of the number's diagonal (`_onface_candidates` offers only
  near-full sizes; no rotation, no deep shrink) — and `_draw_overlap_keyline` draws a constant 1-screen-px
  WHITE ring just outside the strokes wherever they still overlap, so shapes stay readable. Number opacity
  dropped ~20% (`_decal_opacity` 0.70→0.56, floor→0.12). `--breakdown` (per-brush grid) is the default
  preview. Iterated heavily with Andrzej on renders; supersedes the elaborate 20%-tolerance/60%-floor/
  cap-rotation resolver of the same day. Decision `2026-07-23 19:05 UTC` (supersedes `15:22`/`16:03`);
  spec `specs/2026-07-23-decal-anti-overlap.md` now historical. Follow-up `2026-07-23 20:03 UTC`:
  numbers are sized in a fixed 2-digit SLOT (`_text_bitmap` widens+centres a short number to
  `_DECAL_SLOT_DIGITS`=2), so a lone `5` scales like `12`. Follow-up `2026-07-24 05:27`/`06:43 UTC`: breakdown DITCHES the legend
  AND all overview labels — the SCENE pane is a plain CSG map (`labels="none"`), brushes identified by
  their captioned per-brush panes — and frames every pane with a minimal 16px border (`_BREAKDOWN_PAD`,
  `render_brushes_pgm(frame_pad=)`). The intermediate on-face-name overview was tried then removed.

- **`actor preview --breakdown` — per-brush grid** (+ `--zoom` name/poly, `--brush-colors`,
  legend-reserve) — BUILT 2026-07-23. p2. A near-square GRID (`ceil(sqrt(N))` cols) of panes: pane 0 is
  the whole scene in CSG with a name-only legend (roster incl. point actors, no numbers); each
  following pane is ONE brush, `--focus`ed + zoomed to its AABB with all faces numbered + name
  captioned. Point actors get no pane (named in the overview). `dispatch._render_breakdown_grid`, Pillow
  stitch (kept in dispatch — `preview.py` buffers are square-only). Replaces **`--split`** (the
  non-shadowing number-group
  filmstrip, built 2026-07-22 then superseded same-week): `--breakdown` sidesteps number-overlap by
  giving each brush a big zoomed shot instead of graph-coloring groups; `split_groups`/`_group_decals`/
  `_boxes_overlap`/`_SPLIT_*` and the `render_brushes_pgm(only_polys=)` gate were removed. **`--zoom-poly`
  → `--zoom`** (clean rename): now frames a bare brush NAME (whole AABB) OR `BRUSH:idx` (one poly).
  Kept from the `--split` work: the `_scene_geometry`/`_framing` extraction, `reserve_legend`/
  `draw_legend` split (legend reserved into a band, drawn once per filmstrip), `--brush-colors
  {csg,legend}`, band cap. Two cold-review passes. Decisions `2026-07-23 06:01`/`10:00 UTC`; the
  `spikes/poly-split-groups/` spike is superseded (kept as history).

- **`actor preview` HYBRID per-brush label tint + legend + `--focus`** — BUILT 2026-07-22.
  Extends the label system so a cold reader can map every label→brush even when two brushes share a
  CSG op (one wireframe hue). The wireframe stays CSG-coloured; each **actor** now gets a distinct
  categorical **tint** (`preview.assign_tints` → `_TINT_PALETTE`, ~10 hues, cycled) used as the accent
  (leader/arrow/box-border + a faint tint WASH of the label box, `_pale`) for that brush's poly-index
  labels and as the fill of a point actor's marker (a haloed filled diamond); index digits stay black.
  A top-left **legend** (`_draw_legend`, one row per labelled brush = tint square + NAME, per labelled
  point = tint diamond + NAME) maps tint→name, and **actor names moved OFF the geometry into it**
  (`name:*` selectors gate legend rows, `poly:*` gate on-geometry indices). New **`--focus BRUSH`**
  (cli/dispatch → renderer): only the focused brush shows indices (bold, its tint), every other brush
  dims to a faint wireframe; **`--highlight` overrides focus** (a highlighted poly/actor stays
  vivid+bold on top and keeps its index). All gated behind the `color_by_csg` (real-preview) path — the
  legacy black/grey path keeps on-geometry names + no legend. Bad `--focus` name / point actor → clean
  exit 2. Cold-reader validated (`_scratch/labelclarity/hybrid/`, iso @460): default views ~4.3
  (two same-CSG rooms now cleanly split by tint), `--focus` ~4.7 for the dense case; beats the ~3.5
  baseline. `docs/usage.md` updated. See **inbox** for two residual notes (palette-cycle collision at
  11+ actors; dense-default center still busy — `--focus` is the remedy).

- **Granular `--labels` grammar + density-aware label placement** — BUILT 2026-07-22.
  `actor preview`'s single `--labels {none,all,highlighted}` switch is replaced by a composable
  colon-filter grammar parsed to a `LabelSpec` (bare kind = ALL, filters narrow, commas union; kinds
  `poly`/`name`, filters `vis`/`hi`/`brush`/`point`; keywords `none`/`all`/`highlighted`; default
  `poly:vis,poly:hi,name`). Adds **brush-name labels** (net-new). All three label kinds place through
  one pass that minimises a cost over a geometry `DensityGrid` (flee dense knots, never cover a point
  icon, moderate drift cap); brush names anchor at the least-dense point on their own wireframe. Spec
  + plan cold-review-gated (spec + Part-A gates); decisions 2026-07-22 09:54 UTC; spec
  `specs/2026-07-22-labels-granularity.md`, plan `plans/2026-07-22-labels-granularity-plan.md`. Tests
  in `test_preview.py`/`test_cli.py`/`test_actor_preview.py`.

- **Spiral staircase — wedge-tread + central-column redo** — BUILT 2026-07-22.
  `builders.spiral_staircase` no longer emits rotated rectangular slabs (planks that didn't
  tessellate, no column, mirrored-V in front/side). It now returns `steps+1` convex brushes: a
  central `cylinder` column (radius `inner_radius`, base at z=0, full height) plus one **wedge
  (pie-slice) tread** per step — a convex 6-face prism (top/bottom trapezoid + inner/outer chord + 2
  radial sides), rotated `k·degrees_per_step` about Z, climbing one `rise` per step so the tread tops
  ascend strictly monotonically (a single helix). Each wedge passes `validate_brush` (rotation about
  Z preserves planarity/winding). `--at` anchors the column-axis base. `spiral_3`/`spiral_4` parity
  goldens regenerated and moved to `OFFLINE_ONLY` (builder-sourced, dropped from the LIVE capture
  suite — rotated coords make DEINTERSECTION invent vertices, same as `stair_*`). Tests in
  `test_builders.py`/`test_generators.py`; decisions 2026-07-22 08:28 UTC. (Split out of the
  one-actor `brush build` spec, 2026-07-21.)

- **`actor preview` — rename `brush preview` + ergonomics + point actors + overlays** — BUILT
  2026-07-21 (both coupled specs in one pass). The wireframe verb moved from the `brush` group to
  `actor` (no alias; `--tree` still excluded). Ergonomics: unified `--from-t3d <FILE…|->` (also
  migrated onto `stash capture`, dropped `--from-stdin`); `--zoom-poly` is now a `BRUSH:idx` selector
  that frames-only; split `--highlight-poly` (repeatable set form); the renderer `highlight` param is
  a `(name,idx)` set; six-way CSG-op brush colouring (highlight = the brush's own vivid hue + bolder
  line, red retired); `--zoom-factor` (default 0.8). Point actors: DT_Sprite billboards (masked blit,
  `DrawScale·USize×VSize`), DT_Mesh/DT_None markers, `--show-collision` cylinders + `--show-light-
  range`/`--show-sound-range` spheres — fields resolved in dispatch via the `_class_defaults` seam +
  a `TextureResolver.resolve_masked`, schema-unavailable degrading to a marker + note (no traceback).
  Engine facts (sprite footprint, `25·(x+1)` radii, 2·CollisionHeight box) pinned in
  `test_engine_facts.py`. Specs `specs/2026-07-21-brush-preview-ergonomics.md` +
  `specs/2026-07-21-actor-preview.md`; UED palette/radii facts folded into `unrealed/rendering.md`.

- **`brush build` staircase = ONE non-convex brush + `doctor` T-junction-aware watertight** — BUILT
  2026-07-21. `builders.staircase` now returns a single non-convex `Brush` (UED `LinearStairBuilder`
  outer hull: Base + back + per-step Step/Rise + tiled convex Side strips, `2 + 4n` faces, floor-
  anchored), reversing the 2026-07-18 box-per-step. `doctor.check_watertight` reworked to
  per-supporting-line directed-interval parity (canonical WELD-quantized line key + B2 branch
  precedence) so T-junctions read closed while a real hole collinear with a healthy seam still
  flags. Multi-actor dispatch branch KEPT (spiral still `list[Brush]`>1); `stair_*` dropped from the
  LIVE parity suite (`OFFLINE_ONLY`) with offline value goldens re-blessed. Spec
  `specs/2026-07-21-brush-build-single-actor.md`; decisions 2026-07-21 12:06 UTC + 12:22 addendum.
  **Remnant:** the native CSG core's convex assumption is now falsified for this brush — tracked as
  the `[implement]` "Native CSG core assumes CONVEX brushes" item in `inbox.md`.

- **Level is the ambient `$UEDCLI_LEVEL`; `--target`→`--tree`; drop `level select`** — BUILT
  2026-07-20 (2-reviewer cold gates on BOTH the spec and the build; all findings resolved). Fixes the p1
  CLI-probe finding (shared unlocked pointer → concurrent cross-writes): the machine-local
  `.uedcli/current-level` pointer + `level select` verb are GONE, replaced by the per-process
  `$UEDCLI_LEVEL` env (resolved via `level_select.resolve_level(env_level=…)`, precedence `--tree` >
  env > clean exit-2 naming both set-methods). `--target KIND/NAME` renamed `--tree KIND/NAME`
  everywhere and extended to `level materialize`/`preview` (level-kind only). A **mutating** verb
  resolved from the env echoes `editing level 'X' (from $UEDCLI_LEVEL)` to stderr (at
  `TrunkLevelSource.save`), the visibility guard against a stale export. Spec
  `specs/2026-07-20-tree-flag-and-env-level.md`; decisions 2026-07-20 21:30 UTC (supersedes 2026-07-05
  19:07/19:28). Suite-wide test sweep (`test_tree_flag.py`, env-based `test_level_select.py`,
  `set_selected`→`monkeypatch.setenv`). **Remnant:** the p2 `level delete/rename/clone` spec item
  (to-spec) still references "retarget the selected pointer" — reword to `$UEDCLI_LEVEL` when specced.

- **`mover key` keyframe model rework** — BUILT 2026-07-20. `spec
  specs/2026-07-20-mover-key-base-relative-frame.md`, decisions 2026-07-20 16:18 UTC. `mover key
  add` removed; new **`mover key count <name> [<n>]`** gets/sets `NumKeys` (2..8, non-destructive) via
  the shared `movers.set_num_keys`; `NumKeys` off `propedit.HARD_REJECT` so `actor prop set
  NumKeys=<n>` is identical in effect. `move`/`rotate <i>` are edit-only (`1 ≤ i < NumKeys`) with a
  **required** `--from-base`/`--from-world` frame on `--to` (`--by` frame-agnostic). Touched
  cli/dispatch/movers/propedit + usage.md/architecture.md/README + leveldesign recipes; tests in
  test_movers/test_actor_prop/test_dispatch/test_name_not_found_sweep. Engine-fact pin
  `test_it_keeps_numkeys_when_a_key_is_zeroed` (spike `spikes/2026-07-20-mover-numkeys-trailing-zero/`).
- **schema-cache `class show` seed-drop (remaining half)** — BUILT 2026-07-20 (2-reviewer cold-gated,
  built in a subagent). Dropped `class show`'s `shared` full-`Package` seed so its prop walk takes the
  `load_package_schema` warm-cache path — measured ~2.1–2.4× warm, output byte-identical. Reviewers
  confirmed it's actually MORE divergence-safe than the seed (chain + props now share one memoized
  disc). `dispatch._dispatch_class` + coupled test (`_cache is None`) + `architecture.md`; decision
  2026-07-20 00:30 UTC. Pre-existing non-category degrade-test gap flagged to inbox. Commits
  `72e00f9d9`, `2b7be0e19`.

- **Lazy-import per-verb modules — DROPPED as obsolete (Andrzej, 2026-07-20).** The item's premise
  (~1s import tax, ~2s→1.1s warm-start win) was measured on the **retired dev CONTAINER** (`_dev-run.sh`,
  gone 2026-07-14). Re-measured HOST-NATIVE (the current runtime): `bin/uedcli level select` ≈ 0.21s
  total, of which uedcli imports are only **~37ms** (`-X importtime`: `uedcli.cli` cum 37ms, `model`
  20ms, `dataclasses` 15ms); the rest is Python+wrapper startup. A lazy restructure would save ~20-30ms
  while being invasive on the shared cli/dispatch bottleneck AND constrained (the top-level `dispatch()`
  exception guard pins `driver`/`editor`/`geometry` imports). Not worth it — closed, not built.

- **`actor scale`/`apply-transform` → `brush scale`/`brush apply-transform`** — BUILT 2026-07-20 (WIDE
  breaking, 2-reviewer cold-gated). Gate verified first: MainScale/PostScale are `ABrush` native fields
  (not on Engine.Actor; no non-brush trunk actor carries them; a mesh uses DrawScale) → moved to the
  `brush` namespace. As brush verbs they now REJECT a non-brush (point) actor all-or-nothing (new guard
  + tests). `actor rotate` stays. Reviewers caught the missing guard test (added) + this board item.
  cli/dispatch/transform/doctor + usage/architecture/quirks + 4 test files; decision 2026-07-20 00:00
  UTC. Commits `41b5a38ef`, `995388b9f`.

- **`actor find --class` → `--class-exact` + `--subclass-of`** — BUILT 2026-07-19 (WIDE breaking,
  2-reviewer cold-gated). `--class-exact` = exact match (old behaviour); `--subclass-of` =
  descendant-aware via `ClassIndex.descends_from` (expands to level classes descending from a base);
  the two OR in `dispatch._find_class_filter`. Bare `--class` REMOVED via a `_RemovedFlag` (errored +
  blocks argparse abbreviation resurrecting the footgun). Reviewers caught 3 missed stale refs
  (README, two find `--help` strings) — fixed. cli/dispatch/usage/architecture + `test_cli`/
  `test_dispatch`; decision 13:30 UTC; leveldesign KB docs deferred to inbox. Commits `1d9dc2d48`,
  `8b9e523e0`.

- **[~] CLI usability nits (batch)** — 4/7 DONE 2026-07-19: `--facing -X/-Y/-Z` space form now parses
  (`_FACING_NEG` in `_CoordArgumentParser`, regression in `test_cli.py`); `mover key add` help
  clarified (key 0 = base, first add = key 1); `prop get` help notes Rotation reads back in raw rotator
  UNITS (get/set round-trip, `actor rotate` is the degree verb); `--at` anchor doc was ALREADY present.
  Commit `18913531b`. **Remnants → `inbox.md` (3, deferred with tradeoffs):** `--prefab-dir` position
  consistency (touches the documented `prefab [--prefab-dir] <sub>` form), single-name-verb-multi-name
  scoped error (argparse wart), and upstream-pipe-error-as-data (fuzzy detect/annotate).

- **Remaining mutators → producers** — DONE 2026-07-19. `actor delete` / `move` / `prop set|unset`
  and `brush poly set` now print their touched names to stdout (one/line) + a summary to stderr,
  matching `rotate`/`scale`/`order`/`align` — so they chain via `| verb -`. (For `delete` the stdout
  is the removed names, a log/count.) usage.md updated; 8 regressions (3 roundtrip tests drained the
  new `set` stdout line). Commit `15bd6acd5`.

- **`actor duplicate` verb** — BUILT 2026-07-19 (2-reviewer cold-gated). Sugar for `actor show <names>
  | actor add -`: copies actors in place with fresh names, prints them to stdout (both a `-`/stdin
  CONSUMER and a producer). Extracted the `actor add` ingest body into a shared
  `dispatch._ingest_actor_t3d(args, src, level, text, *, verb)` (reviewer-confirmed behavior-preserving
  for add); `--folder` override + `--target`; folder guards extended to `duplicate`. Docs
  (usage/architecture) + 5 tests. Commit `c3bfb1d1c`.

- **`help=` enforcement test (board #9)** — BUILT 2026-07-19. New `test_help_completeness.py` walks
  the real argparse tree from `cli.build_parser()` and asserts every subcommand + argument has a help
  that (a) exists, (b) doesn't echo the flag/command name, (c) clears a 10-char minimum — plus a
  classifier self-test so a future gap fails CI. Filled the 6 gaps it surfaced (the terse `brush build`
  `X/Y/Z extent` dimension helps → descriptive units/axis). Commit `18d96bfca`.

- **Doc sweep: UModel-serialize corpus version labels** — DONE 2026-07-19. The `parse_model_with_zones`
  →`parse_model_serial` half was ALREADY done (quirks.md already correct; the old symbol exists nowhere
  but the board). The v69→v68 half rested on a WRONG premise: on-disk the corpus is MIXED (105 v68 + 15
  v69 in DeusExAssets/Maps; original-shipped = v68, UnrealEd-2.2-rebuilt = v69), and the `UModel::Serialize`
  Model-body format is IDENTICAL across the v68↔v69 bump (researched: v68/69 differ only header-level —
  heritage-table→generation-info at 68, minor UT99 increment at 69). So relabeled the spike doc +
  `test_umodel_serialize.py` as **v68–v69 (format version-stable)**, not bare v68 or v69. Commit `9699c9699`.

- **`level status --json` + git-history help reconcile** — BUILT 2026-07-19. `level status --json`
  emits `{kind, name, actors, duplicate_order_values, git, texture_packages}` (`{"selected": null}`
  when nothing selected). Reworded the top-level `--help` "Git is the history" → clarifies it is the
  project's OWN git and history exists only once it is its own repo (`level status` reports when not) —
  resolving the probe's contradiction. Commit `0d70a564f`.

- **`--target` coverage on the read verbs** — BUILT 2026-07-19 (2-reviewer cold-gated). Added
  `--target level|stash|prefab` to `actor show`, `level status`, `level doctor`, `event graph`, and
  `stash capture` (naming the SOURCE) — the CLI-usability-probe race escape hatch. `actor build`
  DELIBERATELY SKIPPED (Andrzej 2026-07-19: a generator reads no box; the race is on `actor add`).
  Added uniform `display_name`/`kind` to the three `LevelSource` classes; rewrote `_level_status`
  through the seam (kind-labelled header, git hint only for a trunk); capture rejects `--target` +
  `--from-*`. Decision `decisions.md` 2026-07-19 12:30 UTC; architecture/usage reconciled; regressions
  in `test_target_flag.py`. Commit `73d952536`.

- **`level list` verb** — BUILT 2026-07-19 (2-reviewer cold-gated). Enumerates the project's levels
  (trunk dirs with an `actors/` tree under `<maps>`, dotted dirs skipped), one name/line to stdout
  (pipe-friendly) + count/selected to stderr; `--json` → `[{name, selected}]`. New
  `level_select.list_levels` helper; `dispatch._level_list`; docs (architecture/usage) + 11 tests.
  Review fixes: stale-selection flagged on stderr (kept consistent with --json), dot-guard test now
  exercises the guard. Commit `1e4ca932d`.

- **[~] SP-E warm-editor materialize spike** — RAN 2026-07-19 (2-reviewer cold-gated), findings folded
  into the spec §8 + `quirks.md`; harnesses committed under
  `spikes/2026-07-18-warm-editor-materialize/harness/`. Answered SP-E.1 (reused successful builds are
  canonically == a fresh build), SP-E.3 (resident `OBJ LOAD` = harmless re-read), SP-E.5 (timing:
  warm saves ~16 s/build ~20%; verify ~42 s > boot ~15 s), SP-E.6 (RSS flat, no cap needed). **Remnant
  → the spike surfaced a BLOCKER now parked in `inbox.md` as an open design decision:** the H3 verify
  run against the warm editor breaks ~50% of reused builds (`MAP SAVE` silently lost); needs a fix
  (separate verify editor vs idle barrier) + an SP-E re-run before the build. SP-E.2 (possible real
  cross-level residue) + SP-E.7 (colliding names) deferred behind that fix.

- **Native class→package import resolution (§88 blocker 1)** — BUILT 2026-07-19. Every actor class
  was imported under `Engine` (`pkgref._package_of_class` called a NON-EXISTENT
  `uprops.package_of_class`, always falling back to `"Engine"`), so any real level's DeusEx-package
  classes (`Engine.DeusExMover`, …) made the game linker abort loading and revert to the boot map —
  fatal on UNATCO/Catacombs/HK, invisible on the castle/tiny maps (genuine-Engine classes only).
  Fix: `pkgref.build_class_package_index` scans the composed `.u` code set for each class's real
  defining package (cross-checked against the golden UNATCO import table — all 95 real classes
  match), threaded through `assemble_level(class_packages=…)` into `Resolver._package_of_class`.
  NativeUnatco now imports `DeusEx.DeusExMover`/`DeusEx.ATM` (77 DeusEx + 13 Engine, zero
  misclassed) and **boot-confirmed** past the class abort (loads UNATCO's real texture packages,
  reaches blocker 2); castle import table + Model body **byte-UNCHANGED** (43.04% / 485 surfs /
  1156 nodes / 283624 B). Regression: `test_class_package_index_resolves_deusex_classes_to_real_
  packages` + `test_real_deusex_class_imports_as_deusex_not_engine`. Scoped OUT (→ inbox): closing
  the 9 355 prop-skip warnings + restoring Sound/Music imports (surfaces a separate `MyLevel`
  local-object-ref import defect); and blocker 2 (load-time renderer CPU loop).

- **Movers excluded from native world CSG (`_in_world_csg`)** — BUILT 2026-07-19. Native's world-CSG
  brush selection pulled in ANY brush-bearing actor, including **Movers** (`DeusExMover`, 23 in HK /
  28 in UNATCO) — dynamic actors (doors/lifts) whose brushes UnrealEd keeps as private Models and
  never CSGs into the world. Feeding them into CSG filled doorways solid and shattered empty-space
  connectivity. Fix: `materialize._build_level_model`'s `csg_order` filters via the shared
  `movers.is_mover` predicate; `_trunk_to_actorspecs` still emits movers as actors (emission is
  independent of CSG). Measured (real builds, `shatter_probe.py`): HK leaf-blobs **21→2**, zones
  **24→5** (= editor golden's 5); UNATCO leaf-blobs **18→7**, zones **20→9** (editor 7); castle
  (no movers) byte-UNCHANGED (485 surfs / 1156 nodes / 43.04%, no-op). Regression:
  `test_mover_excluded_from_world_csg_but_emitted_as_actor`. (That remnant — a Mover subclass not
  named `*Mover`, e.g. `DeusEx.BreakableGlass`, still leaking into CSG — was CLOSED 2026-07-25 when
  `is_mover` became the schema-aware class-hierarchy test; see the entry at the top of this file.)

- **Native brush SCALE applied in `_build_brush_input`** — BUILT 2026-07-19 (root cause of native
  over-solidification on real DX levels; spike `2026-07-15-native-materialize/sections/87` §9–§10).
  `materialize._build_brush_input` was silently DROPPING every brush's `MainScale`/`PostScale`, so
  scaled brushes built at UNIT size and scaled-up SUBTRACTs carved tiny holes (room interiors stayed
  SOLID). Fix bakes the full linear map `L = PostScale·R·MainScale` (`rotation.actor_linear`) into
  the Rust core's `rot`, gated on non-identity scale (unscaled brushes untouched → castle
  byte-identical). The cold-review gate surfaced a MIRROR case (`det(L)<0`, HK has 30): the ring is
  pre-reversed (as `transform.bake`) so a mirrored subtract isn't built inside-out. Real-level `[A]`
  (editor-empty→native-solid, `shatter_probe.py`): HK 74.5%→**0.3%** (surfs 2664→5572/5224 golden,
  leaf-blobs 131→21), UNATCO 15.3%→1.1% (3581→4056, 44→18), Catacombs 9.7%→0.9%. Committed regression
  `tests/test_native_scale.py` (4 tests: scaled-vs-explicit differential + MainScale leg + mirror +
  unscaled-gate — real-level trunks are gitignored `_scratch/`; each verified red on the buggy
  path). 1811 offline green. **p2 remnants:** (a) exclude Mover-class actors from `csg_order` —
  residual leaf-blob/zone shatter (§9.4); (b) texture-axis transform under scale rides forward `L`
  (editor uses inverse-transpose covector — byte-parity/appearance only, needs live editor evidence);
  (c) native-ingest nits — `det(L)=0` scaled brush silently drops polys (no `SCALE_EPS` guard here),
  sheer_rate in `(0,0.05]` deadzone needlessly loses byte-parity. NativeUnatco headless-boot payoff
  (does correct solidity clear the documented UNATCO load-hang) — see §87 §10.3.

- **Unify stash/prefab/trunk onto ONE per-actor T3D tree** — BUILT 2026-07-18 (decision 2026-07-18 23:01 UTC + addendum; spec `specs/2026-07-18-unify-t3d-trees.md`; plan `plans/2026-07-18-build-unify-t3d-trees.md`). New shared `t3dtree.py` (per-actor tree I/O + rank algebra + body strip/inject + `check_safe_segment` + `write/read_sidecars`) is the SINGLE code path for all three trees; `trunk.py` thin re-exports; `stash_register.py`/`stashlib.py` rewritten to `actors/<name>/{actor.t3d, order_value, folder}` + sibling `meta.json`/`packages`; `tree_io.py` DELETED. **Hard cutover** (Andrzej): old single-blob prefabs give a clean exit-2 `old-format prefab 'X' — re-capture it` (verified live on `lantern`/`computer_console`), never a traceback; stale flat stashes read empty. **Folder persisted per member** (full trunk parity; `apply --folder` overrides). `test_t3d_tree_consistency.py` asserts the same actor set writes BYTE-IDENTICAL `actors/` trees as trunk/stash/prefab (the invariant, enforced). 1807 offline green; committed HEAD run green. **Consequence for this repo:** ~11 committed prefabs (`lantern`, `computer_console`{,_big,_aligned}, `road_corner`, `stairs`, `trimmer`, `wall/pillar`, `wall/wall`, `reception_desk_lume/stand`, `x`) are old-format and must be re-captured. Inbox follow-ups: folder/order verbs could take `--target stash|prefab` now; prune the ephemeral spec+plan.

- **CLI consistency & clarity audit (unattended build #12, report-only)** — DELIVERED 2026-07-19.
  Report `dev/docs/reviews/2026-07-19-cli-consistency-audit.md` (full verb inventory + 8 findings,
  2 high / 3 medium / 3 low, each verified against `cli.py`/`dispatch.py`). NO behaviour changed.
  Top: [H1] `brush poly set` lacks `-`/stdin (breaks the `poly find | poly set` pipe its own help
  advertises); [H2] `actor move` is single-actor-only while `rotate`/`scale` take a set + `-`; [M1]
  mutator summary destination inconsistent (some → stdout, rubric says stderr); [M2] `brush vertex
  list`/`actor prop get`/`mover key list` lack `--json`; [M3] `brush build` has no `--prop` though
  `actor build` does. Accepted fixes are filed as NEW inbox items (below) for Andrzej to triage —
  this item shipped only the review. Completes the 2026-07-18 unattended build queue (items 1-12).

- **Native cross-check on heavy-SUBTRACT retail level — Paris-Catacombs** (2026-07-19, §86
  `sections/86-catacombs-parity.md`; harness `build_native_catacombs.py`). Measurement + diagnosis,
  no production code touched. Ingested `10_Paris_Catacombs.dx` (1283 Brush + 18 DeusExMover, pinned
  by Brush-export count; 2710-actor trunk, 9984 tex-refs 0-miss) and built `NativeCatacombs.dx`
  UNLIT via `bspcsg`: **61 s / 176 MB / no crash / no CSG degenerate** on the densest overlapping-
  subtract geometry — building at all is the headline. RAW ground-truth diff: whole-body 16.27 %
  positional (editor lighting = 42.7 % of body, unlit). **NEW finding the castle+UNATCO never
  surfaced: the SURFACE SET diverges — Surfs +436 (+6.7 %)** vs UNATCO's −0.2 %/castle's exact;
  overlapping SUBTRACT makes native fragment/merge world surfaces differently from `bspBrushCSG`.
  Reproduces the two §84 gaps: over-zoning **33 vs 17 (+94 %)** and uniform BSP over-split **+10…
  +17 %** (NOT worse than UNATCO despite subtract density). **Deferred → inbox:** chase the surface-
  set fragmentation (coplanar-merge / T-junction on overlapping subtracts) — needs a heavy-subtract
  level kept in the parity loop.

- **`poly align` + `brush poly find` BUILT** (build #5, 2026-07-18; item 11; decisions.md
  2026-07-18 21:40 UTC; spec `specs/2026-07-18-poly-align.md`). `polyalign.py`: a stateless
  `brush poly find <brush> [--item/--facing/--texture/--json]` producer printing `BRUSH:idx`
  selectors, and `brush poly align (--wall|--floor|--ring) [--fresh-frame][--fit-perimeter]
  (targets…|-)` that makes a texture flow continuously across a face set. UV convention
  `U=(V−Origin)·TextureU+PanU` (scale in `|TextureU|`); continuity defined in WORLD space, written
  back per-brush via each brush's own inverse rotation (offset in float `Origin`, `Pan` kept
  integer). `--ring` advances U by chord `2r·sin(π/N)`; leave-seam default + `--fit-perimeter`.
  31 tests in `test_polyalign.py` (UV-continuity goldens across shared seams, ring wrap, adopt-seed
  vs `--fresh-frame`, find filters, every error path, + 2 engine-fact regressions). Docs: usage.md,
  architecture.md "Surface texture alignment", t3d.md UV convention. **Deferred → inbox:** `--face`
  fit-to-surface, turning (non-coplanar) wall runs, sphere wrap, `--seam` anchor, scaled-brush
  textured continuity, `poly find` across multiple brushes, `--fit-perimeter` true pixel-tile meet.

- **LightMap grid-sizing rule PINNED byte-exact** (`light.rs` `axis_grid`/`bake_surf`, 2026-07-18,
  §20 §22). Decoded the editor's `FLightMapIndex` grid formula from the golden `Test_Castle.dx`:
  grid dim = `Clamp(ceil(extent/lumel_scale), 2, 256)` (was `trunc((extent−0.25)/scale − 0.5)+1`,
  under-counting 134/484 records by −1); scale = `(extent+0.25)/(size−1)` (was `extent/(size−1)`);
  extent = `(vert−Base)·Tex` subtract-base-FIRST (f32-rounds differently from `v·Tex − Base·Tex`
  on angled surfaces — 484/484 vs 412/484). RAW positional: `LightMap` 76.2%→**87.0%**, `LightBits`
  48434 B→49701 B (was −1082 vs editor, now +185). `UClamp`/`VClamp`/`u_scale`/`Pan.x` now 484/484.
  Guards unregressed (nodes 1156, surfs 485, Points 2035, LightMap 484/14528 B). New Rust regression
  `axis_grid_matches_editor_ceil_rule`; harness `lightmap_grid_diff.py`. **Remnant:** `Pan.y`/`VScale`
  427/484 — the 57 misses are records where native's base-point/TextureV **geometry** differs from
  editor by f32 (Points/Vectors not yet byte-exact, owned outside `light.rs`); follow for free as
  those reach parity. `LightBits` content gap now dominated by per-leaf permeating-light omission
  (§21 A) + LOS/backface bits (§17), separate larger levers.

- **Native Pass-D +9 orphan-vert overshoot CLOSED** (`zones.rs` `fix_ring`, 2026-07-18, §70 §12).
  Native entered `bspOptGeom` with +9 vert slots (10527 vs editor 10518), carried to Verts 16172 vs
  16163. Localized (`preopt_runs2.py`) to two orphan runs (+3 @5596, +6 @7591), then pinned via a new
  `bspaddnode_ring_oracle.py` (breakpoints editor `bspAddNode`, logs per-ring `(ivp, nv)`) to
  **exactly 3 spurious `[A,B,B]` orphan triangles** native's `clip_poly` emits that the editor's
  `FPoly::Fix` (drop consecutive verts `< 0.002`) collapses below 3 and drops. Fix applies `FPoly::Fix`
  to Pass-D orphan rings only (no node created ⇒ node-order/`tail_order` untouched). RAW
  (`ground_truth_bytediff.py`): PRE-optgeom **10527→10518 = editor**; **Verts 16172→16163 = editor**;
  Verts posmatch **24.8%→27.3%**; Nodes **91.6%→92.6%**; whole-body **42.4%→43.0%**. Guards intact
  (soup 853/853, surfs 485, vectors 26, Points 2035/24422 first-diff @1586, NumSharedSides 2739
  byte-identical, Bounds 484, LeafHulls 308/3866/1710, LightMap 484, nodes 1156/1156); `cargo test` 38,
  offline **1744 passed**. **REMNANT (deferred, RE'd infeasible in-lane, §70 §12):** the surviving
  orphan verts' `iVertex` still carry native's snapped indices, not the editor's stale pre-compaction
  ones (which run up to 2642 — a transient CSG point numbering native never builds; reproducing it
  conflicts with the `bspcsg.rs` pool clear + `reorder_points_canonical` Points-parity guard). Verts
  section length-close (53860 vs 53866, −6 = compact-int width of smaller indices) but not
  byte-identical.
- **`event graph`** — BUILT 2026-07-18 (unattended build #4, to-build item 10). New `event graph
  [--dot|--json]` verb + pure `eventgraph.py` module (`build_graph`/`lint_graph` + text/DOT/JSON
  formatters): scans the selected level's trunk for the Tag↔Event trigger wiring (edge A→B when
  `A.Event == B.Tag`) and lints dangling wires / unreachable receivers / unreachable movers /
  cycles (Tarjan SCC → a real cycle path). Model-side, no editor; wiring→stdout, lint→stderr,
  `--json` folds lint in; exit 0 even with findings (query verb). Load-bearing choices in
  decisions.md 2026-07-18 20:54 UTC: unset `Tag` NOT a matchable receiver; lint advisory. Tests
  `test_eventgraph.py` (31, green); docs in usage.md + architecture.md. **Remnants (inbox):**
  multi-event array props (Dispatcher `OutEvents`/Counter) not modelled; no `--strict` exit; tagless
  movers not lint-flagged. NOTE: the cli.py+dispatch.py hunks were swept into concurrent commit
  `cd364b6ac`; the module+tests+docs committed separately.
- **[~] Native `bspOptGeom` pass-1 over-weld — LIVE dup-guard table** (`bspoptgeom.rs`, 2026-07-18,
  `42-bspoptgeom-decode.md §9`). The T-junction dup-guard read a STATIC pre-pass1 vertex-occurrence
  table; the editor's inserter (`0x31920`) updates it live on every weld. Fixed by threading `&mut
  table` through `add_point_link` and appending `(node, point)` after each `insert_ring_vertex`. RAW
  (`ground_truth_bytediff.py`, `NativeCastle.dx` vs `Test_Castle.dx`): pass-1 welds **977→975** (==
  editor); **Verts count 16183→16172** (editor 16163); **Verts section 53924→53887 B** (editor 53866);
  **NumSharedSides byte-identical 2739** (kept); Nodes section 54035→54034 B (== editor). Guards
  unregressed (nodes 1156/1156, soup 853/853, surfs 485, vectors 26, Points 2035, Bounds 484,
  LeafHulls 308/3866/1710, LightMap 484); `optgeom_validate` golden fixpoint holds; offline 1705
  passed; `cargo test bspoptgeom` 4/4. Evidence: `editor-tree-oracle/weld_livetable_diff.py`.
  **Remnant:** Verts still +9 (Pass-D orphan slots) + orphan `iVertex` stale-index bytes — out of lane
  (`zones.rs`/`passes.rs`), tracked in `inbox.md`.
- **[~] Native Surfs/Vectors/Points pool byte-ORDER** — BUILT 2026-07-18 (§82 §10.19-§10.20).
  RE'd the on-disk pool order to native's repartition CLEARING the incremental-CSG surf pool (editor
  KEEPS it and only compacts): a post-build `reorder_surfs_canonical`+`rebuild_vector_pool`+
  `reorder_points_canonical` (`bspcsg.rs`) restores editor order. Results: node `iSurf` byte-EXACT,
  surf `iBrushPoly`/`polyFlags`/vector-refs byte-EXACT, Vectors ORDER 26/26, Points count/length
  byte-EXACT (2035/24422, +26 orphans dropped), surf `pBase` mismatch 477→112, whole-body positional
  match **29.2%→43.6%**; node isomorphism preserved (1156/1156). Guards intact; cargo 37 + offline
  1701 green. **REMNANT (deferred, not pool-numbering lane):** Points intra-block sub-order (base
  #132+, ring order) + orphan `iVertex` (Verts section) is a `bspRefresh` reachability-DFS point-
  compaction artifact of PRE-compaction indices — not reconstructable from the final model — and is
  further gated by the bspOptGeom vert-count weld divergence (16183 vs 16163, `bspoptgeom.rs` lane).
  Residual Vectors bytes = 1-3 ULP normal-value FP (`fpoly` lane); surf `iActor`/`iLightMap` =
  package-export / LightMap-array numbering (assembly / `light.rs` lanes).

- **Geometry bundle (unattended build #3)** — BUILT 2026-07-18 (spec
  `specs/2026-07-18-staircase-redo.md`; plan `plans/2026-07-18-build3-geometry.md`; decisions
  2026-07-18 20:09 UTC). Two offline items: (8) **`brush build staircase` redo** — `builders.staircase`
  now returns `list[Brush]` (one convex box per step, filled floor-to-tread column) instead of one
  non-convex brush; each box passes `level doctor` (the old single brush tripped 60+ phantom
  watertight errors and hung one `rise` below the floor); `_build_brushes` unwraps the list (N actors
  `Staircase0…`); parity goldens re-blessed offline (`stair_*` only); the UED single-brush reference
  preserved as engine-fact guard. **[SUPERSEDED 2026-07-21: staircase reverts to ONE non-convex brush
  (T-junctions handled by the now T-junction-aware `check_watertight`); the guard test is now
  `test_builder_matches_ued_linear_stair_taxonomy`. See the 2026-07-21 entry above / decisions.md
  12:06 UTC.]** (9)
  **`brush replace <name> -`** — in-place shape swap taking only the piped generator's PolyList while
  keeping the target's Name/`order_value`/Group/CsgOper/actor-level PolyFlags/Location/PrePivot (7
  clean error paths, all exit-2/no-traceback; empty stdin → exit 0); supersedes the dropped `brush
  resize`. Post-build 2-cold-reviewer gate run: added the missing `brush replace` regression suite
  (7 dispatch paths + on-disk rank-preservation round-trip) + doc fixes. Python suite green (1713);
  committed HEAD verified green in isolation.

- **Small-features bundle (unattended build #2)** — BUILT 2026-07-18. Three offline features:
  (5) **`actor bbox <names…|->`** — world AABB (min/max/size/center) enclosing the passed actors as
  ONE box (multi-actor case IS the union — no `--union` flag); reuses `writes.union_bounds` (honours
  rotation/scale/location, point actor = zero-size box); `--field min|max|size|center` bare
  extractor + `--json`; count summary → stderr; unknown name → clean exit 2. (6) **`--json` output**
  on `actor find` (JSON name array), `brush poly list` (`{actor, polys:[…]}`), `project show`
  (`{root,game,maps,prefabs,catalog,search_path}`), and the new `bbox` — default text output
  unchanged. (7) **`--rotate PITCH,YAW,ROLL`** on the generators (`brush build`/`actor build`) —
  SETS the `Rotation` field absolutely (fresh actor = identity, no ambiguity), stored not
  vertex-baked, warns off-grid on brushes; NOT on `actor add`. All regression-tested
  (`test_bbox.py` + extensions to generators/trunk-verbs/project-show); Python suite green.

- **Bug-fix bundle (unattended build #1)** — BUILT 2026-07-18. Four offline fixes:
  (1) `level doctor` portal-sheet false positive — `_brush_polyflags` now reads the effective flags
  (actor-level `PolyFlags` OR'd with per-poly flags), so a `brush build sheet` zone-portal, whose
  `PF_NotSolid|PF_Portal` live only on its polys, is skipped from watertight checks instead of
  tripping phantom open-edge errors; (2) `level status`/`_git_hint` reports the edited PROJECT's own
  repo, not uedcli's — returns "not a git repo" when the project only sits inside uedcli's source
  tree (was leaking the tool branch); (3) `--base-name`/actor-add no longer strips trailing digits
  (`Pillar1`/`Pillar2` stay distinct, not both `Pillar`); (4) XS bundle — surface-flag names
  case-insensitive (`encode_flags` + `poly set` choices), `brush clip` prints a no-op message when
  the plane misses the brush interior, duplicate point-actor Location warning on `actor add`, `--at`
  help states it is the geometric center on every axis. All regression-tested; Python suite green.

- **Lightmap `PF_Portal` over-cull fixed — portals now get records** — BUILT 2026-07-18
  (spike §20 §21). `light.rs::PF_NO_LIGHTMAP` wrongly included `PF_Portal`, so native skipped the
  4 two-sided water-portal surfaces the editor lightmaps. Corrected to the editor's exact skip-mask
  `0x400081 = PF_Unlit|PF_FakeBackdrop|PF_Invisible` (grounded in the oracle `Test_Castle.dx` +
  disasm `Editor 0x100a6031`; pinned by Rust test `lightmap_skip_mask_matches_editor_disasm`).
  Raw bytes: `LightMap` 480→**484 recs / 14528 B == editor**; `LightBits` 48015→48431 B (gap
  1498→1082); `Lights` 3928→3955. Remnant: the far-larger `Lights` gap (→11392) is the missing
  per-leaf permeating region — see the `[spec]` item in `inbox.md`.

- **Scale support — `MainScale`/`PostScale` USE/STORE/BAKE** — BUILT 2026-07-18 (plan
  `plans/2026-07-18-scale-plan.md`; spec `specs/2026-07-18-scale-support.md`; decisions 2026-06-25 /
  2026-07-18 14:03; spikes `2026-06-25-scale-transform-mechanics.md` +
  `2026-06-25-mainscale-postscale-applytransform.md`). New `transform.py` algebra module (FScale
  parse/emit, `sheer_coeff` snap, linear matrix, `bake`); scale parsed into typed `model.Actor`
  fields + emitted de-duped; `rotation.actor_linear` folds `PostScale·R·MainScale` into every
  world-geometry consumer + the clip/vertex inverse; `actor scale (--to|--by)`, `actor
  apply-transform`, `actor rotate --to`; `MainScale`/`PostScale` in `propedit.TYPED_FIELDS`. Offline
  suite green; engine-facts pin `sheer_coeff` + emission; editor-parity differential is
  `test_scale_integration.py` (`-m integration`).
  **Remnants (boarded elsewhere):** `--native` preview + native binary build still reject/pass-identity
  scale (a separate deferred workstream — see inbox "Native materialize silently IGNORES PostScale");
  the combined scale+sheer matrix ORDER (`Sheer·Scale`) is validated only by the integration
  differential (single-effect cases match the live spike); no PostScale-authoring verb (`actor
  post-scale` deferred); texture-lock exact vectors are integration-gated (offline asserts the L
  transform, not editor bytes).

- **CSG-order control — `actor order` + `actor add --order`** — BUILT 2026-07-18 (plan
  `plans/2026-07-18-csg-order-plan.md`; spec `specs/2026-07-18-csg-order-control.md`; decisions same
  ledger entry). `actor order <names…|-> (--first|--last|--before NAME|--after NAME)` reorders
  existing actors' CSG precedence; `actor add --order (first|last|before=NAME|after=NAME)` places new
  ones (default `last` == append). Multi = block move preserving relative order (incl. non-contiguous).
  The make-or-break seam: `TrunkLevelSource.save(..., ranks=<override>)` — the override channel that
  lets a reorder reach disk (the `changed`-diff then fires + folds into `canonical_level_hash`).
  `order_ops.compute_reorder_ranks`/`compute_add_ranks` over `trunk.ranks_between`; neighbour lookup
  excludes the moved set. Guards (named exit-2): trunk-only, unknown/missing/self-reference NAME,
  and `rank_between` exhaustion (adjacent imported ranks, `--first` vs a `'0'` min). Folded into
  `architecture.md` (Commands). Tests: `test_order_ops.py`, `test_order_verbs.py`,
  `test_level_source.py`. Closes the inbox "can't place a brush FIRST" item.

- **Actor folders — hierarchical actor organization (the "groups overhaul")** — BUILT 2026-07-18
  (plan `plans/2026-07-18-actor-folders-plan.md`; spec
  `specs/2026-07-18-actor-folders-hierarchical.md`; decisions 2026-07-18 12:14/12:32/12:45 UTC).
  `Actor.folder: str|None` typed field + per-actor trunk `folder` sidecar (atomic write/remove);
  the delta-write diff compares folder BOTH directions incl `"x"`→None. New pure `folderlib.py`
  (path/pattern grammar + the §3 globstar match). `actor folder set --to <path> <names|->` /
  `unset` / `get` (`(none)` sentinel); `actor add --folder`; `actor find --folder <pattern>` /
  `--no-folder`; `actor show` `// uedcli-folder:` carrier (+ `--t3d-only`); `stash/prefab apply
  --folder` (beside `--group`). ALL folder surfaces reject `--target stash|prefab`. Folder excluded
  from the canonical hash / never emitted to the map. Folded into `architecture.md` ("Folders");
  `unrealed/t3d.md` already documents the carrier. Tests: `test_folderlib.py`, `test_folders.py`.
  **Deferred → inbox:** `folder rename <old> <new>`, exact-single-node match, `--from-group` bulk
  migration sugar.

- **Actor-name composition pipe — stdin `-` + `actor add` prints Names** — BUILT 2026-07-18
  (plan `plans/2026-07-18-actor-name-compose-pipe-plan.md`; spec
  `specs/2026-07-18-actor-name-compose-pipe.md`; decisions 2026-07-18 14:03 UTC). `actor add`
  prints allocated Names to stdout (after save) + count to stderr; `actor delete/rotate/prop
  set|unset|get/show` read `-` = newline name list from stdin via `dispatch._resolve_target_names`
  (sole source, empty → no-op exit 0, dedup on canonical name); multi-actor `prop set/unset` is
  two-phase-atomic (cross-class), `prop get -` emits `<name>\t<key>=<value>`. Folded into
  `architecture.md` (Command API). (Remnant closed 2026-07-18: `actor folder set --to … -` now
  reads `-` from stdin via the same `_resolve_target_names` seam — shipped with the folders feature.)

- **`actor prop set|unset|get` subcommands + dot-paths + class-default fallback + unified package
  core** — BUILT + 3-reviewer-gated 2026-07-18 (same day as the spec). Ships: `upackage.py` (the
  ONE low-level UE1 package reader; `uprops` migrated onto it — `utexture`/`dxpkg` migration is a
  separate inbox chore), the `SerializeExpr` bytecode walker + UClass-tail DEFAULTS decoder
  (1914/1914 DX classes corpus-clean; `unrealed/class-schema.md` "UClass body"), `propedit.py`
  (dot-path grammar, whole-value vs targeted edits, effective-value get, dump-all, typed-field
  registry with Location zero-fill), retirement of `actor get` + the `--set/--unset` flags,
  `actor find --prop` EFFECTIVE-value matching + `actor build --prop` validation, and the §9 live
  probe result (partial values are member-wise onto the CLASS DEFAULT —
  `spikes/2026-07-18-partial-value-import-semantics/`, `unrealed/t3d.md`). Live E2E against the
  real v68 install ran green (set/get/unset/find + real enum errors). Spec (ephemeral):
  `specs/2026-07-18-actor-prop-subcommands.md`; durable record decisions.md 2026-07-18 10:02 +
  10:30 UTC; folded into `architecture.md` "Class-property schema, DEFAULTS & the actor prop
  verbs". **Remnant flags (inbox):** store-explicit struct edits + `--kv` round-trips manufacture
  the explicit-default shapes the two open H3 post-verify items trip on — their practical
  priority rises now.

- **Project layout reorg: free `uedcli.toml` at the repo root + in-repo `.uedcli/` state dir** —
  BUILT 2026-07-18 (4 slices: `421b8add0` flag-day cutover + LUM migration, `e301a37cf` state-dir
  threading, `3dc4c7ccb` package-relative tool assets + cwd-relative CLI paths + `repo_paths.py`
  deletion, + the docs/board sweep). A project is a repo with `<root>/uedcli.toml` (root-relative
  managed-dir keys, defaults `maps/`/`prefabs/`/`texture-catalog/`; `id`/`name` dropped); ALL
  machine-local state in the self-ignoring `<root>/.uedcli/` (`config.state_dir`, `*` .gitignore
  written on first create); tool-install assets package-relative (`tool_assets.py`); relative CLI
  paths resolve against the cwd; `UEDCLI_REPO_ROOT`/`UEDCLI_PREFAB_DIR`/`UEDCLI_TEXTURE_CATALOG`
  retired. Spec/plan (ephemeral): `specs/2026-07-17-project-layout-uedcli-toml.md`,
  `plans/2026-07-18-project-layout-uedcli-toml-plan.md`; durable record decisions.md 2026-07-17
  20:58 UTC. The slice-2 `texture classify set` lock deviation was RESOLVED 2026-07-18: texture
  flocks are catalog-adjacent `<catalog>/.locks/` (decisions.md 2026-07-18 07:53). The live
  materialize/preview check PASSED (spec §10.6 — inbox record).

- **Offline class discovery + qualify-and-validate on ingest** — BUILT + tested + live-verified
  2026-07-17 (spec `specs/2026-07-17-class-discovery-and-author-validation.md`; decisions.md
  2026-07-17 19:37 UTC). New `class list`/`class show` verbs over an offline `classindex.ClassIndex`;
  bare→FQCN class qualification + existence validation + texture existence validation wired into
  every ingest/emit seam (`actor add`, stash capture/apply, prefab apply, the generators, `brush poly
  set --texture`); `verify.py` H3 reconciliation (`requalify_classes_to_loaded`) keeps post-verify
  live-vs-live. Abstract detection via the shipped ScriptText source (`unrealed/class-schema.md`).
  `class list` is a rooted depth-limited BROWSE (default now = an indented inheritance TREE rooted at
  Engine.Actor, abstract nodes `*`, a collapsed frontier node's hidden direct-subclass count as `(N)`,
  depth auto-fits ~60 lines; `--subclass-of` reroots, `--depth` counts from the shown root, `--flat`
  gives the pipeable one-per-line list, `--all` reroots at Core.Object) — a flat 1200-class dump was
  unusable (Andrzej; tree per decisions.md 2026-07-18 10:56 UTC). `class show` groups props per declaring class; default truncates ancestor sections to a
  ~60-line budget (`… N more hidden` note), `--all` = full chain. (DX props carry no `var(Category)`.) Post-build review (two cold reviewers) findings all resolved: foreign-`.u` index-bounds
  robustness (no traceback), the untested real bodies now covered (`test_ingest_validation.py`), one
  canonical no-package-path message, `TextureResolver.exists` cache, ancestry cycle-guard, and a
  RELAXED `uprops` EOF gate (tolerates trailing padding — `CaroneElevatorSet.u` now parses instead of
  skip-noting). Gates green: `bin/test` 1337 passed / 1 skipped / 2 xfailed, 35 cargo. Live: `class
  list`/`show` on real DX; `actor add` of bare `Class=Light` stores `Engine.Light`; unknown
  class/texture → exit 2. **Remnants (boarded in `inbox.md`):** the annotated class catalog (curated
  placeability/guidance) + the backward-compat exit-status change note.

- [~] **bspcsg FindBestSplit param fix + `bspOptGeom` wire-in** — BUILT 2026-07-17 (spec
  `specs/2026-07-17-findbestsplit-params-fix.md`). Repartition path now uses Balance=12/PortalBias=0/
  Opt=GOOD (stride `max(NumPolys/10,1)`), threaded through `split_poly_list` so the temp-brush convex
  partition keeps its invariant OPTIMAL/50/70; `bspOptGeom` runs at the build tail after `bspRefresh`.
  MEASURED effect (full castle vs editor 1156/485/2035/16163/2739): over-fragmentation FIXED, nodes
  1263→**1028**, surfs 454, points 1579, `NumSharedSides` 0→**940**, verts 3604→4040, solidity 98.96%.
  Gates green (cargo 33, `bin/test` 1269). **Remnants (still open, see inbox):** node-for-node prefix
  still 0 — first-divergence is the §8.3 cospatial-facing-in surplus face (needs a live differential
  trace); and pass-1 T-junction insertion under-fires (verts 4040 vs 16163).
- **`--game --map` actor-relative poses + `--list-actors` query** — BUILT + live-verified 2026-07-17
  (spec `specs/2026-07-17-game-actor-relative-poses.md`; decision 16:24). `at:@Actor`/`look:@Actor`/
  `orbit:@Actor` now resolve against the RUNNING game for retail `--map` (link verbs `ListActors`/
  `GetActorLocation`; `preview_shots.py` baked into the image; batch resolves + poses). `--list-actors
  CLASS [--sample N]` query mode prints a map's actors (no screenshots) to compose `@Name` refs. Fixes
  the `at:@PlayerStart` gap. Live: delivered 40 NON-PlayerStart shots across 5 OG maps entirely via
  the CLI (`--list-actors Engine.PathNode --sample 8` → `at:@PathNodeN;rot:...`).

- **`level preview --game` — ONE-EXEC batch drive (from ~9s to ~2.2s warm)** — BUILT + live-verified
  2026-07-17 (spec `specs/2026-07-17-game-preview-container-daemon.md`; decision 14:42; 2-reviewer
  design gate). Replaced the warm container's ~8-10 per-op `docker exec`/`stats`/`cp` round-trips with
  ONE `docker inspect` (reuse gate) + ONE `docker exec` of the in-container `preview_batch.py`
  (deliver → 3-phase travel/skip → per-shot `PrepareCamera`+settle+X-grab → framed PNGs on stdout).
  Renamed link verb `Screenshot`→`PrepareCamera` (poses only, replies sync; the settle moved to the
  batch because `bPlayersOnly` freezes the link actor's Tick/Timer). `ensure_image` source-hash marker
  fast-path (skips docker on the warm path). A persistent published-port DAEMON was designed then
  REJECTED by review. Live: cold ~60s → **warm reuse ~2.2s** → **10-shot 8.37s all distinct** → idle
  self-death. +`test_preview_batch.py` (fake link). **Remnant (→ inbox):** ≤1s target unmet (dev-CLI
  Python startup floor) — needs the Nuitka binary + folding the 2nd docker call + settle tuning.

- [~] **`level preview --game` — WARM reusable container + live map delivery** — BUILT + live-verified
  2026-07-17 (spec `specs/2026-07-17-game-preview-warm-container.md`, 4 review rounds; decisions
  2026-07-17 06:57/07:30/08:31). `--game` now delivers into ONE warm per-user container
  (`uedcli-game-preview-<uid>`, flock + fingerprint-label reuse + inline idle watchdog); map delivery
  is a hash-named (`materialized__…`/`copied__…`, dot-free/lowercased/capped) build written to
  `uedcli/tmp/preview/`, bind-mounted at `/resources/preview`, POST-boot symlinked into Maps — the
  SP-R-confirmed reload path (`spikes/2026-07-17-game-preview-reload-keying/`). Live: cold 79s → reuse
  17s → idle self-death (exit 0). `.dx`+`.unr` inputs; `--keep-alive` pins; `--rebuild` mints a fresh
  name. Post-build review gate (2 cold reviewers) resolved: `stop_game`/lock-hang bounding, `--game`
  actor-typo → named error, docker-hang → named error not traceback, pin preserved across forced
  reboots, skip-travel when already on the map, `.dx`/`.unr` ext-qualified stems, +16 warm-core
  tests. **Remnants (→ inbox):** additive re-farm on reuse + dangling-symlink sweep (currently the
  fingerprint reboots on overlay change instead); the boot-time `/resources/preview`-not-globbed
  assertion.

- **`level preview --native` — the offline draft preview backend** — BUILT 2026-07-16 (spec +
  plan 2026-07-16, decision 12:13 UTC). `level preview` now renders freely-posed textured stills
  entirely offline (Rust CSG carve + `render.rs` rasterizer + native `utexture.py` decode; SHOT
  grammar shared with the future `--game` tier); the editor-screenshot backend
  (`preview_render.py`, `TARGET[:MODE][=NAME]`, `MODE_INI`, `query.overview_brush`) is DELETED.
  U/V/Pan mapping pinned against live editor+game references
  (`spikes/2026-07-16-native-preview-anchor/`); golden blessed post-anchor. `--game` = clean
  reserved exit-2. **Remnants:** `--lit` fast-follow (spec §8, consumes the N-4 bake); the
  in-game `--game` tier itself (spec 2026-07-13).

- [~] **Native from-scratch `.dx` game-load — loads + renders clean** (2026-07-15). A natively
  materialized `.dx` (real Rust CSG, no editor) now loads in the live game, possesses the player,
  and renders with 0 `OccludeBsp`/singularity/Critical. Fixed: six load-blocking serialization/
  structure bugs, then the `FBspNode` field cross-wiring (`iRenderBound=0` into an empty Bounds
  array → NULL-FBox render crash; commit 51e47618b) — with a regression test pinning the crash
  condition + the real on-disk field semantics (vs `DXOnly.dx`), and the spike doc
  `50-model-ondisk-layout-and-render.md`. **Remnant:** the room isn't yet *playable* — the player
  falls through the floor (BSP leaf/solidity not assigned; view is black = unlit). Promoted to
  inbox "[plan] Native BSP leaf/solidity assignment" + N-4 lighting.

## Partially done (deferred remnants noted)

- **Asset-wiring cutover — Part C (retire static compose mounts + entrypoint sed)** — BUILT
  2026-07-14. Removed `docker-compose.yml`'s static `/deusex`+`/content`+Sounds/Music stub mounts,
  deleted `entrypoint.sh`'s `$DEUSEX_ASSETS_DIR` `Paths` `sed` block, and dropped the
  `UED_DEUSEX_ASSETS_DIR=/nonexistent` stopgap. The no-GUI build container
  (`stub.ephemeral_build_container`) self-wires its assets like the GUI editor (crafted
  `[Core.System] Paths` ini bind-mounted pre-launch, shared `editor.engine_ini_mount`). Decision:
  decisions.md 2026-07-14 13:30. Its **deferred remnant is now RESOLVED** by the config-drive
  finalization below.

- **Stub-build + texture-sync discovery config-driven, then unified onto ONE mount set** — BUILT
  2026-07-14. `texture sync` is project-scoped: discovers EVERY package (all extensions — a `.u` can
  hold textures) from `config.composed_search_files(project, user_config)` (project shadows base) and
  writes the catalog to `<project>/texture-catalog/` (`config.project_catalog_dir`). Stub-build sources
  its v68 `.u` from the whole composed search path (one `search_dirs`, first-`.u`-wins), threaded
  through `stub_missing_packages`/`ensure_stub`/`compute_cache_key` and `stub_closure.resolve`;
  `substrate stub` + the lazy trigger in `qualify.export_and_qualify` too. **ONE uniform mount set for
  ALL containers** (editor/preview/texture/stub): `container_assets.split_dirs`/`classify_dir` DELETED;
  everything mounts the whole composed set via `resource_mounts` → `/resources/<n>`. Safety = Paths
  order: `/stubs` (v69) first, so a stub shadows any v68 `.u` on the editor's Paths. Retired
  `packages.substrate_code_dirs`/`enumerate_substrate_packages`; `repo_paths.install_system_root`/
  `install_content_dirs` kept only as test install pointers. Live-verified: `foobar` materialize
  (editor unaffected with 45 v68 `.u` now on Paths — inert via demand-load + stubs-first), stub source
  → `/resources/r002/DXOgg.u`, `texture sync --package Airfield` → 108 textures → project catalog.
  Decisions: decisions.md 2026-07-14 17:40 then 19:21 (the uniform-mount supersession); docs reconciled
  (`architecture.md` texture-catalog + schema + stubbing + container sections). Two cold reviewers
  flagged the one real risk (one HIGH): an unstubbed v68 code package referenced by materialize/preview
  would demand-load the v68 `.u` and wedge the editor. GUARDED — `ensure_load`'s
  `packages.unloadable_v68_packages` gate refuses it with a clean named error before any `OBJ LOAD`.
  **Deferred remnant (capability):** AUTO-stub referenced packages in `level materialize` so such a
  level actually builds (not just fails cleanly) — `inbox.md`.

- **`--target KIND/NAME` — generic content-verb targeting (level/stash/prefab)** — BUILT
  2026-07-12. Two new `LevelSource`s (`StashLevelSource`/`PrefabLevelSource`) + a parse/routing
  front branch in `_resolve_level_source` + the one `cli._target_flag` helper on the shared content
  verbs; a prefab is now edited in place with any content verb (no apply/re-capture/promote
  roundtrip). Includes the prerequisite `stashlib.read_prefab` meta-clobber fix and the
  `parse_poly_target`→`parse_poly_selector` rename (frees "target" on `brush poly set`). Path
  traversal refused before any source is built (`validate_member_name`). Spec:
  `specs/2026-07-12-uedcli-target-flag-design.md`; decision 2026-07-12 03:06 UTC; folded into
  `architecture.md` ("The `LevelSource` seam and `--target`"). **Non-goals (by design):** no
  instance/placement refresh of already-applied copies; no new lifecycle verbs; last-writer-wins on
  a concurrent same-box edit (atomic swap, no merge).

- [~] **`dxconcli` — git-trackable Deus Ex conversation source ↔ `.con`** — v1 BUILT 2026-07-05/06
  (standalone `Tools/dxconcli/`, own `.venv-dxconcli`; 116 offline tests + a corpus-gated full
  round-trip; the CLI decompiles/validates/recompiles real game files e.g. Mission1.con's 71
  conversations). Byte-exact Layer-1 codec (`con_codec`, cmp-clean over 25 real `.con`); two-way
  Layer-2 (`con_source`): all verbs, `if`/`choice`/`random`, fragments (Tarjan SCC/tail-position),
  a total deterministic decompile. All 6 verbs (`new`/`compile`/`decompile`/`validate`/`search`/
  `voices`) with a no-traceback error boundary. Plan:
  `plans/2026-07-05-dxconcli-implementation-plan.md`; spec:
  `specs/2026-06-26-uedcli-deusex-con-tool-design.md`. A live spike corrected the
  `Jump.conversationID` model (`spikes/2026-07-05-deusex-con-jump-conid-live/`).
  Inline-collapse pass DONE 2026-07-06 (single-use fragments inlined; Mission1 −77% fragments);
  multi-error `validate` DONE 2026-07-06 (reports every broken conversation in one pass, each
  located).
  **Deferred remnants:** choice `skill:` gates (refused — no corpus data for the
  wire encoding). Phase-4 golden fixtures folded into the per-verb tests + corpus round-trip.

- [~] `[implement]` **`actor rotate` (multi-actor group rotation)** — IMPLEMENTED 2026-06-19
  (offline suite green; the live materialize round-trip is substrate-gated —
  `tests/test_rotate_integration.py`, `integration`-marked + deselected). Rotates a group about a
  shared pivot model-side; orbit Location by the matrix + compose orientation into `Rotation` by
  per-component FRotator field-addition (editor parity); `PolyList` stays local. **Done since:**
  `PrePivot` honoured everywhere (2026-06-19); rotation-aware `brush clip`/`brush vertex move`.
  **Deferred remnant:** honour **scale** (`MainScale`/`PostScale`) in the world transform (still
  ignored — a measurement gap for the rare scaled imported brush, never stored-geometry
  corruption; see `unrealed/quirks.md` "Pivots"); non-uniform-scale + rotation order-sensitivity;
  a *fractional* corner on a *rotated* brush may not match `vertex move --at` (float inversion).

- [~] `[implement]` **Vertex / poly editing verbs (text surface).** VERTEX MOVE + surface
  texture/flags/pan editing (`poly set`) are DONE (`vertex.py`, `surface.py`, offline-tested).
  Surfaces addressed model-side by `(brush Name, poly index)`, with `poly list` + the
  numbered-wireframe `preview` for picking; flags addressed by NAME, never raw bit values.
  **Deferred remnant:** `poly scale | rotate` (surface edits, same model-side pattern); live
  verification of vertex move on the editor (offline-only so far).

- [~] **Builder-brush identification predicate — CONFIRMED ROBUST** (2026-06-23, Spike 1 in
  `spikes/2026-06-23-capability-gaps-round2.md`). Editor always assigns inner model `Model<N>` +
  explicit `CsgOper` to authored brushes; uedcli uses `Model_{actorname}`; inner name `Brush` is a
  singleton reserved for the live builder brush, never duplicated. No false positive possible.
  Documented; no code change needed.

- [~] `[implement]` **Store-centric model (UnrealEd as a build/preview tool)** — IMPLEMENTED
  2026-06-18 (offline suite green). The session store's model-side T3D is authoritative; `apply`
  reads THEIRS offline, ensure-loads the manifest, materializes (full re-import), post-verifies
  against the INTENDED result (H3); `level open`/`create`/the open-gate are gone, replaced by
  `session start [<dx>]` + `package load`. Folds in `export_and_qualify` and
  `dxpkg.transitive_closure`, live-verified 2026-06-20. See `architecture.md`,
  `unrealed/quirks.md`, `decisions.md` 2026-06-18. (Open follow-ups tracked in `to-spec.md`.)

- [~] **`BRUSH ADDMOVER` + `ACTOR KEYFRAME NUM=#` — CONFIRMED console-drivable** (2026-06-23,
  Spike 7). `BRUSH ADDMOVER` creates a `Mover` actor (log: `Preparing brush <name>`);
  `ACTOR KEYFRAME NUM=#` sets `KeyNum=N`. Keyframe POSITION requires T3D authoring
  (`KeyPos(N)=(...)` + `NumKeys=N`). Superseded for authoring by the model-side mover support
  (`to-build.md` #7); documented in `unrealed/commands.md`.

- [~] **`ACTOR DUPLICATE`/`MIRROR`/`APPLYTRANSFORM` — CONFIRMED console-drivable** (2026-06-23,
  Spike 8). `ACTOR DUPLICATE` copies selection with ~16uu XY offset. `ACTOR MIRROR X=-1`/`Y=-1`/
  `Z=-1` sets `MainScale` per-axis (corrected from the wrong `BRUSH MIRROR XY` inference).
  `ACTOR APPLYTRANSFORM` bakes scale into vertices. uedcli does symmetry model-side; these console
  verbs are documented for completeness in `unrealed/commands.md`. (The model-side `actor mirror`
  CLI verb is tracked in `to-spec.md`.)

## Done

- [x] **Batch `actor add`/`stash capture` no longer silently drop duplicate-Named actors +
  `brush build`/`actor build` `--name`→`--base-name`** — 2026-07-12 (branch `uedcli-impl`). Root
  cause: `model.parse_t3d` keys actors in a `dict[Name]`, so user-concatenated T3D (e.g. 14
  `brush build --base-name Merlon | actor add`) lost all-but-last *at parse*, before the uniquify
  loop ran. Fix: new `model.parse_t3d_actors` (ordered, duplicate-preserving); `parse_t3d`
  refactored to build its dict from it. Both raw-ingest points use it — `actor add` mints a
  distinct `<stem>_<rand>` per actor (and now prints `added N actor(s)`); `stash capture`
  filters-by-name-first then uniquifies the chosen set. Separately, the generator name flag became
  `--base-name` (a stem — the Name always gets a `_<rand>` suffix at add) on both `brush build`
  (renamed from `--name`, hard break, no alias) and `actor build` (new — previously every point
  actor was named after its class → collapsed on batch add). Spec:
  `specs/2026-07-12-batch-add-unique-names-and-base-name.md`; decisions 2026-07-12 12:15 UTC (both
  entries); folded into `architecture.md` (generator verbs + the model-side ingest invariant) and
  `usage.md`. Tests: `parse_t3d_actors` dup-preservation, `actor add` 14-merlon + mixed regressions
  + the count print, `stash capture` dup + filter-then-uniquify, CLI `--base-name`/no-legacy-`--name`.
  Offline suite green (the only 2 failures are a pre-existing env-permission issue on a repo-pinned
  texture lock dir, untouched by this change). Reviewed by two cold subagents at spec AND build; all
  findings resolved (the filter-then-uniquify order came from a spec-review finding).

- [x] **`brush`/`stash`/`prefab preview` render host-side — no container** — 2026-07-12
  (branch `uedcli-impl`, commit `d9d7e98af`). These three preview verbs were the ONLY container
  users that drove neither the editor nor UCC; they used the standing `dx-lum-uned` container purely
  as an ImageMagick + `/work` file-staging utility. Now `_render_actors_to_out` (`dispatch.py`)
  writes the PPM straight to the host `--out`, and `--png` decodes PPM→PNG with Pillow (already the
  sole third-party dep) — zero docker, no editor. The `container` param was dropped from the helper
  and all three call sites. Fixed a latent path bug along the way (the `--png` extension swap used
  `rsplit(".",1)` on the whole path, mangling `--out` when the filename had no extension but a parent
  dir contained a dot → now `os.path.splitext`), and wrapped the write/convert so Pillow/OS errors
  surface as a clean `_SelectionExit` exit-2 message instead of a traceback (per the no-exception
  rule). Tests added: `--png` Pillow path, the no-extension/dotted-parent regression, the clean-error
  path (`tests/test_stash_dispatch.py`). Docs reconciled: `architecture.md` "Preview internals" +
  the image-deps note (ImageMagick now scoped to the `level preview` editor-screenshot path only —
  `wine_ctl.py`'s `import`/`convert`), `preview.py` docstring, `cli.py --png` help. Full offline
  suite green (997 passed). Reviewed by two cold subagents; both findings resolved.
  **Remnant (low pri):** the older two preview tests still monkeypatch a `no_docker` guard onto
  `dispatch.subprocess.run`, which is now inert (the path makes no subprocess call) — harmless, could
  be dropped on a future pass. The `from PIL import Image` sits lazily in the `--png` branch, aligning
  with the open lazy-import item in `inbox.md`.

- [x] **`bin/test` — scope pytest to the `uedcli` package (fixes tree-walk hang) + rename from
  `bin/uedcli-test`** — 2026-07-12 (branch `uedcli-impl`, commit `6cd30ce58`). Root cause of a
  reproducible multi-minute hang: `pytest.ini` had **no `testpaths`**, so the wrapper's args branch
  (`pytest -k … -q`, no path) made pytest recursively collect the ENTIRE `Tools/uedcli` tree — the
  baked editor, asset dirs, and a stray `dev/docs/spikes/bspspike/test_umodel_serialize.py` that
  hardcodes another machine's `/home/human/...` paths. (No-arg runs passed an explicit `uedcli`
  target, so they were fine — which is why it looked intermittent.) Fix: `testpaths = uedcli` in
  `pytest.ini` scopes every bare pytest (incl. `-k`) to the package; an explicit path arg still
  overrides. Verified: the previously-hanging `bin/test -k "preview or stash"` now finishes in ~24s.
  Renamed the wrapper `bin/uedcli-test` → `bin/test` and updated all references (`CLAUDE.md`,
  `README.md`, `docs/README.md`, `dev/docs/dev-runtime.md`, `bin/_dev-run.sh` header), noting in each
  that it must be run **path-qualified** (`bin/test`) since `test` is a shell builtin.
  **Wrapper-hang debugging note for the next session:** the dev wrapper's own hang symptom can also be
  caused by concurrent `bin/test` runs leaving stray `docker exec … pytest` processes inside the warm
  `uedcli-run-*` container — if the wrapper stalls, `docker exec <c> python -m pytest uedcli -k … -q`
  directly (repo is mounted at the same host path inside the container) bypasses it and is the fast
  way to confirm the container itself is healthy.

- [x] **Dropped the mover `BaseRot≠0` keyframe warning** — 2026-07-07. The interim stderr caution on
  `mover key add`/`move`/`rotate` against a base-rotated mover was noise: `KeyPos[i]` is
  world-additive (`Location = BasePos + KeyPos[i]`, not rotated by `BaseRot`) and `KeyRot[i]`
  field-adds to `BaseRot` — confirmed by a live measurement (90°-yaw base, `KeyPos(1)=(X=256)` → world
  +X) and the disassembled editor transform, folded into
  `spikes/2026-06-25-mover-keyframe-basepos-semantics.md`. Removed `_warn_base_rot` + its 3 call sites
  (`dispatch.py`); regression test `test_it_does_not_warn_on_a_base_rotated_mover_key_op`; docs made
  confirmed-fact (`architecture.md` "Mover support", `decisions.md` 2026-07-07 12:11 UTC).

- [x] **`level preview` — batch editor-screenshot snapshot renderer** — BUILT + **live-verified
  end-to-end** 2026-07-06 (4 clean fresh-boot passes; `test_preview_integration.py`: two distinct
  poses, mean-abs-diff 9.9 > 3.0, both bright mean ~146). `POS@ROT[:MODE][=NAME]` shot grammar +
  rotation presets + `--out-dir`/`--mode`; per-command ephemeral editor grouped by mode (one boot
  per mode via a full-window `[U2Viewport2] RendMap`/ShowFlags ini override); per shot: `CAMERA
  ALIGN` pose → `ACTOR SELECT NONE` → `wmctrl` sweep → click-repaint → `driver.screenshot` → chrome
  crop `(104,92,1596,1104)`. Modes shaded/lit/wire/zones/polys/skybox (radii deferred — ShowActors
  enum value TBD, see the `level preview` modes item in `inbox.md`). **Replaces the old VNC `level preview --rotate` handoff.** Two
  live-boot bugs found + fixed along the way: the override-ini bind source must be daemon-visible
  (`.uedcli/tmp/`, not the sandbox-private `/tmp`), and `_wait_ready` must require a resolved
  `window=<id>` (not the transient `window=<unresolved>` line). Recipe: `unrealed/rendering.md`
  "Posed shots"; spec `specs/2026-07-06-uedcli-level-preview-snapshots-design.md`; decisions
  2026-07-06 12:01/12:59/15:58.
- [x] **Poly identification tooling** — `uedcli preview` (model-side wireframe: UED-style quad
  default, true-30° iso, thick/bright front edges, front-only labels, `--zoom-poly`/`--zoom-region`,
  `--single`, `--png`) + **`uedcli poly list <brush>`** text table (idx / facing / texture /
  flags-by-NAME / centroid / area). Verified on the downtown bench.
- [x] **Native brush clipping** — `clip.py` (Sutherland-Hodgman), exposed as `uedcli brush clip`,
  verified end-to-end (Z=0 clip halved a live brush, stayed selectable).
- [x] **`select_by_name` brush box sizing** — brush targets drive a box sized to union world bounds
  (+margin) for full containment. Verified end-to-end. See [[uned-brush-selectability]].
- [x] **Native render `Bounds` (c0) + collision `LeafHulls` (cc) — faithful `FilterBound` emit**
  (`uedcli-native/src/passes.rs::bsp_build_bounds`, 2026-07-18). Replaced the empty-Bounds +
  approximate-hull stub with a verbatim port of the editor's `bspBuildBounds`/`FilterBound`/
  `SplitPartitioner`/`BuildInfiniteFPoly` (recipe: `re-raw-zones/bounds-and-zonelayout.md` §1).
  Ground-truth raw bytes: Bounds `0→484` entries (`12102 B`, length byte-EXACT, all IsValid=1),
  LeafHulls `4028→3866` ints (`15466 B`, byte-EXACT length, **all 308 hull plane-ref sets
  byte-identical**). Residual = ≤0.005-unit FBox float drift inherited from the not-yet-parity Point
  pool (`pBase`), see [[82c-bounds-leafhulls-decode]]. Live-verified: `NativeCastle` boots headless
  and renders a clean first-person frame (no OccludeBsp "Anomalous singularity").
- [x] **Camera rotation via `CAMERA ALIGN`** — perspective `CAMERA ALIGN NAME=<actor>` ADOPTS the
  named (point) actor's full rotation (pitch/yaw/roll); the pure-console, no-mouse rotation setter
  (pose a `Light`, `SELECTNAME`, `CAMERA ALIGN`, delete). RMB-drag also rotates (scriptable). The
  earlier "preserves rotation" claim was corrected 2026-06-20. (Was wired as the VNC-era `level
  preview --rotate`; that flag is gone — the same `CAMERA ALIGN` pose now drives the
  editor-screenshot `level preview` renderer, above.) See `unrealed/commands.md` `CAMERA ALIGN`.
