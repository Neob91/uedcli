# Geometry-alignment eval — UNATCO reference solutions

`index.html` is the reference-solution page for two UNATCO HQ tasks (widen Manderley's office,
raise its ceiling), used to validate what "correct" means per aspect before grading subagent
trials against it.

## Pipeline — never hand-build a picture or a diff

1. `scripts/spec.py` — the single source of truth. For each task: which actors are **anchors**
   (the task pins an exact delta on these, e.g. "+48 east"), which are **dependents** (must move
   WITH a specific anchor — verified per-actor from real geometry, not assumed uniform: some
   fixtures/flags are physically on the south wall volume, others on the north one, and each is
   tagged with its own actual anchor), and which must stay **unchanged**. Scenario grouping (for
   the human page) is layered on top and does not affect grading.
2. `scripts/build_gold.py <task> <out_dir>` — applies every anchor's op, then moves each dependent
   by its anchor's task delta, onto a fresh copy of the baseline trunk. Produces the one
   fully-correct ("gold") trunk per task that every scenario's picture and diff render from.
3. `scripts/gen_scenario_diffs.py` — for each scenario: dumps every member actor's normalized state
   (`brush vertex list` for brushes, `actor prop get Location` for point actors) from the baseline
   and the gold trunk, and writes a REAL unified diff (`diff -u`) to `diffs/<scenario>.diff`. No
   custom JSON ops vocabulary — if a subagent's trunk is dumped the same way, it's directly
   comparable the same way any two revisions are.
4. `scripts/render_from_gold.py` — renders each scenario's picture from its task's gold trunk,
   highlighting just that scenario's actors, into `img/<scenario>.png`. A picture always reflects
   the fully-correct scene (never a partially-applied one) — this is what fixed the earlier bug
   where a "correct" picture was quietly rendered from a trunk missing one other aspect's fix.
5. `scripts/gen_oracle.py` — writes the flat, per-task, MACHINE-CHECKABLE oracle to
   `oracle/<task>.json`, straight from `spec.py` (no diff-text parsing).
6. `scripts/build_page.py` — assembles `index.html` from `spec.py` + the real `.diff` files + a
   small set of hand-captured supplementary photos in `img/` that no diff drives (`EXTRA_PHOTOS`).

Re-run in that order after editing `spec.py`. Never hand-edit a `diffs/*.diff`, an `oracle/*.json`,
or a picture directly.

## Grading a subagent's trunk

`scripts/check_trunk.py <oracle.json> <baseline_trunk> <subject_trunk>` classifies every actor:

- **anchor**: its own delta (via the specific `at` corners named in the oracle — NOT a whole-brush
  centroid, since an anchor is *resized*, not translated: only one face moves, so a centroid would
  dilute the real shift) must equal the task's exact delta, else `anchor_wrong`.
- **dependent**: its delta must equal its OWN anchor's *actual* delta in the SAME subject trunk
  (not a hardcoded number) — so a flagpole is graded on "did it move the same amount its wall
  actually moved," which stays meaningful even if that wall's own move was wrong. `never_touched`
  if its delta is zero when it shouldn't be; `touched_wrong` if it moved but doesn't match its
  anchor.
- **unchanged**: must equal the baseline exactly, else `touched_when_should_not_be`.

This three-way (subject vs. baseline vs. its-own-anchor) comparison is why the design splits
anchors from dependents in the first place — a flat "each actor must equal this hardcoded absolute
value" table can't tell "the flagpole is broken" apart from "the wall itself moved by the wrong
amount," and can't validate an equally-good alternative solution that got the relationship right at
a slightly different absolute position.

Grading only cares about the RESULT, not how an agent got there — every entry in `spec.py` also
carries a `why`: what it's actually FOR, in plain language, not consumed by the mechanical check.
`check_trunk.py` prints it under every FAILURE line. A mechanical failure isn't an automatic fail —
it's a prompt to check whether the underlying intent was satisfied some other way the mechanical
check didn't anticipate (a different, equally valid construction), before concluding it's wrong.

## Base trunks

`unatco_gt` (untouched UNATCO baseline) lives in job-scratch, not this repo. Set
`BASE_TRUNKS_DIR` to wherever your own extraction lives before running the scripts.
