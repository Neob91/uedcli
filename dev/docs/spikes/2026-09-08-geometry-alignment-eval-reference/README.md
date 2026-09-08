# Geometry-alignment eval — UNATCO reference solutions

`index.html` is the reference-solution page for two UNATCO HQ tasks (widen Manderley's office,
raise its ceiling), used to validate what "correct" means per aspect before grading subagent
trials against it. Designed to grow to dozens of tasks across 5 levels — see "Adding a new task."

## Vocabulary — the closed set every uedcli geometry verb's RESULT reduces to

`scripts/spec_format.py` has the full definitions; in short, every task (`scripts/specs/<id>.py`)
is a flat list of `entries`, each one of four kinds:

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

## Adding a new task

Add `scripts/specs/<task_id>.py` exporting one `TASK` dict (shape in `spec_format.py`) — nothing
else changes. `registry.py` auto-discovers it; every script downstream (`build_gold.py`,
`gen_scenario_diffs.py`, `render_from_gold.py`, `gen_oracle.py`, `build_page.py`) reads
`from registry import TASKS`, never a hardcoded task list. Pick a descriptive, level-prefixed
`id` (e.g. `wanchai_widen_bar`) — every output path is namespaced by it
(`img/<id>/`, `diffs/<id>/`, `oracle/<id>.json`), so ids across levels/tasks can never collide.

Two more per-task fields exist specifically so a new level doesn't need script changes: `frame`
(the world-space AABB `actor diagram --frame` crops every picture to — the room this task edits,
not the whole level) and `level` (used to find `<level>_allnames.txt` in `BASE_TRUNKS_DIR`, the
full actor-name list `actor diagram` draws from).

## Pipeline — never hand-build a picture, a diff, or an oracle

1. `scripts/specs/<id>.py` — the single source of truth for one task (vocabulary above).
2. `scripts/build_gold.py <task_id> <out_dir>` — applies every `update` entry's own op, then moves
   each `anchor` entry by its target's task delta, onto a fresh copy of the baseline trunk. Produces
   the one fully-correct ("gold") trunk per task that every scenario's picture and diff render from.
3. `scripts/gen_scenario_diffs.py` — for each scenario: dumps every member actor's normalized state
   (`brush vertex list` for brushes, `actor prop get Location` for point actors) from the baseline
   and the gold trunk, and writes a REAL unified diff (`diff -u`) to `diffs/<task_id>/<scenario_id>.diff`.
   No custom JSON ops vocabulary — if a subagent's trunk is dumped the same way, it's directly
   comparable the same way any two revisions are.
4. `scripts/render_from_gold.py` — renders each scenario's picture from its task's gold trunk,
   highlighting just that scenario's actors, into `img/<task_id>/<scenario_id>.png`. A picture
   always reflects the fully-correct scene (never a partially-applied one) — this is what fixed the
   earlier bug where a "correct" picture was quietly rendered from a trunk missing one other
   aspect's fix.
5. `scripts/gen_oracle.py` — writes the flat, per-task, MACHINE-CHECKABLE oracle to
   `oracle/<task_id>.json` — the spec's `entries` list, straight through, no diff-text parsing.
6. `scripts/build_page.py` — assembles `index.html` from every task's `before`/`scenarios` + the
   real `.diff` files + a small set of hand-captured supplementary photos in `img/<task_id>/` that
   no diff drives (each scenario's own `extra_photos`).

Re-run in that order after editing a `specs/<id>.py`. Never hand-edit a `diffs/*.diff`, an
`oracle/*.json`, or a picture directly.

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

An actor missing/renamed in either trunk (a real subagent failure mode) is caught and classified as
`missing` (or `anchor_unresolved` for a dependent whose own anchor is missing) rather than crashing
the grading run.

**Known limit:** `anchor` only ever compares position (Location, or a brush's corners). A future
task needing "this fixture must ROTATE with its anchor" would silently misgrade (a rotation-only
change reads as delta `(0,0,0)` → `never_touched`) rather than fail loud. Not built — neither
current task needs it; extend `read_position` (or add a parallel rotation check) when one does.

## Base trunks

Base trunk projects (`unatco_gt`, and future levels' extractions) and each level's
`<level>_allnames.txt` live in job-scratch, not this repo. Set `BASE_TRUNKS_DIR` to wherever your
own extraction lives before running the scripts.
