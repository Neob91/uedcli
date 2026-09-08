# Geometry-alignment eval — UNATCO reference solutions

`index.html` is the reference-solution page for two UNATCO HQ tasks (widen Manderley's office,
raise its ceiling), used to validate what "correct" means per aspect before grading subagent
trials against it.

## Vocabulary — the closed set every uedcli geometry verb's RESULT reduces to

`scripts/spec.py`'s module docstring has the full definitions; in short, every task is a flat list
of `entries`, each one of four kinds:

- **`update`** — an actor's `props` (or, for a brush, specific named corners, or a full T3D
  `Begin Brush...End Brush` block for a non-delta reshape like a clip) must equal an ABSOLUTE
  target: a task-pinned value, or `target="unchanged"` (= the baseline value).
- **`anchor`** — an actor's delta must equal a SPECIFIC other actor's (`to`) ACTUAL delta in the
  SAME trunk being graded — not a hardcoded number. Verified per-actor from real geometry, not
  assumed uniform (this office is built from two wall volumes, and fixtures/flagpoles split across
  both — each is tagged with the one it's actually attached to).
- **`create`** / **`delete`** — documented, not yet implemented (raises `NotImplementedError` if an
  oracle ever contains one). Neither current task needs them; add real handling only when one does.
  `create` grades by diffing the actor-NAME SET between baseline and subject trunk (no fixed name
  to look up for something newly created), not a lookup.

Move/resize/clip/scale all grade the same way (`update`, or `anchor` for a relative case) — no
per-verb code needed, since none of them are structurally different from "some property or shape
became a final value." Only existence (create/delete) is a different kind of check.

Every entry carries a `why`: plain language, not consumed by the mechanical check. Grading cares
about the RESULT, not how an agent got there — `check_trunk.py` prints `why` under every FAILURE
line, so a mechanical fail is a prompt to check whether the intent was satisfied some other way,
not an automatic hard fail.

Scenario grouping (for the human page) is layered on top of `entries` and does not affect grading.

## Pipeline — never hand-build a picture, a diff, or an oracle

1. `scripts/spec.py` — the single source of truth (vocabulary above).
2. `scripts/build_gold.py <task> <out_dir>` — applies every `update` entry's own op, then moves
   each `anchor` entry by its target's task delta, onto a fresh copy of the baseline trunk. Produces
   the one fully-correct ("gold") trunk per task that every scenario's picture and diff render from.
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
   `oracle/<task>.json` — `spec.py`'s `entries` list, straight through, no diff-text parsing.
6. `scripts/build_page.py` — assembles `index.html` from `spec.py` + the real `.diff` files + a
   small set of hand-captured supplementary photos in `img/` that no diff drives (`EXTRA_PHOTOS`).

Re-run in that order after editing `spec.py`. Never hand-edit a `diffs/*.diff`, an `oracle/*.json`,
or a picture directly.

## Grading a subagent's trunk

`scripts/check_trunk.py <oracle.json> <baseline_trunk> <subject_trunk>` classifies every entry:

- **`update(target="corners")`**: the specific named corners (NOT a whole-brush centroid — an
  `update` entry typically *resizes* the brush, only one face moves, so a centroid would dilute the
  real shift) must have moved by the exact task-pinned delta, else `wrong`.
- **`update(target="unchanged")`**: must equal the baseline exactly, else `touched_when_should_not_be`.
- **`anchor`**: its delta must equal its target's *actual* delta in the SAME subject trunk (not a
  hardcoded number) — so a flagpole is graded on "did it move the same amount its wall actually
  moved," which stays meaningful even if that wall's own move was wrong. `never_touched` if its
  delta is zero when it shouldn't be; `touched_wrong` if it moved but doesn't match its target.

This three-way (subject vs. baseline vs. its-own-target) comparison is why `anchor` is split from
`update` in the first place — a flat "each actor must equal this hardcoded absolute value" table
can't tell "the flagpole is broken" apart from "the wall itself moved by the wrong amount," and
can't validate an equally-good alternative solution that got the relationship right at a slightly
different absolute position.

## Base trunks

`unatco_gt` (untouched UNATCO baseline) lives in job-scratch, not this repo. Set
`BASE_TRUNKS_DIR` to wherever your own extraction lives before running the scripts.
