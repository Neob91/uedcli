# Geometry-alignment eval

`index.html` is a manual grading webapp for geometry-alignment tasks (level-edit prompts like
"widen this office" or "raise this ceiling") — every picture on it is generated, never hand-built.
Designed to grow to dozens of tasks across multiple levels — see "Adding a new task." For how to
actually produce an execution (run a subagent against a task, isolated, with only the skill under
test in scope), see `EVAL-PROCEDURE.md` and `scripts/run_eval.py`; this doc covers the task-spec
format and the rendering/grading pipeline that consumes whatever trunk that produces.

## Purpose

This isn't a pass/fail gate on its own — it's how we improve the skills agents use for geometry
work, and it doubles as a check on `uedcli` itself. Grading isn't just "did the edit land right":
when an execution goes wrong, ask whether the skill under test needs work, or whether `uedcli`'s
own verbs didn't give the agent what it needed to do the edit correctly (a missing query, an
awkward multi-step where one verb should exist, a footgun nothing warns about). Note tool-surface
gaps as they come up, not just skill failures — that's a real output of this eval, not a side
effect.

Grading isn't the end state — it's what tells you what to fix next, and which of two different
things to fix:

- **Skill gap** (the agent had the right tool but used it wrong): edit the skill under test
  directly — `plugins/uedcli/skills/<name>/SKILL.md` — then run the SAME task against the SAME
  skill again (`run_eval.py`) to confirm the fix actually changed the outcome. An edit you haven't
  re-verified isn't a fix yet.
- **Tool gap** (`uedcli` itself didn't give the agent what it needed): flag it to the human running
  the eval rather than letting it die in a grading note — don't log it to the board yourself. The
  human decides whether it's board-worthy.

## Vocabulary — what an execution is graded against

Grading is manual: a human looks at the pictures. What gets a picture is a real diff of the whole
level — every actor that differs between baseline and subject, created/updated/deleted, whether the
task mentioned it or not (see "Pipeline" step 5). `scripts/spec_format.md` has the full definitions;
in short, a task (`tasks/<id>/task.json`) carries `entries`, a flat list of `actor`/`what` pairs —
just an optional plain-language label, shown next to a diffed actor's picture when its name matches.
An actor the diff catches with no matching entry still gets shown, flagged as not declared in the
spec, for the human to look at.

Some task files' entries also carry `kind`/`target`/`at`/`delta`/`to` — read only by
`scripts/build_gold.py` (optional, builds a synthetic "fully correct" demo trunk), not by grading:
`update(target="corners", at=[...], delta=[...])` moves those corners; `anchor(to=<actor>)` moves by
whatever delta the gold trunk actually gave its anchor; `target="unchanged"` needs no op.

## Adding a new task

Add `tasks/<task_id>/task.json` (shape in `spec_format.md`) — nothing else changes. `registry.py`
auto-discovers it; every script downstream (`build_gold.py`, `render_manual.py`,
`extract_execution.py`, `render_execution.py`, `build_page.py`, `run_eval.py`) reads
`from registry import TASKS`, never a hardcoded task list. Pick a descriptive, level-prefixed
directory name (e.g. `wanchai_widen_bar`) — every output path is namespaced by it
(`tasks/<id>/before/`, `tasks/<id>/executions/`), so ids across levels/tasks can never collide.

No `frame` field — the crop every picture uses is computed, not hand-picked (see "Pipeline" below).
`level`/`dx_map` are the two fields that exist purely so a new DX level needs no script changes:
`dx_map` names the shipped map to import the baseline from (see "Base trunks" below), `level`
names the trunk tree it's imported into and sets `UEDCLI_LEVEL`.

## Pipeline — never hand-build a picture

1. `tasks/<id>/task.json` — the single source of truth for one task (vocabulary above).
2. `scripts/build_gold.py <task_id> <out_dir>` — OPTIONAL: applies every `update` entry's own op,
   then moves each `anchor` entry by its target's task delta, onto a fresh copy of the baseline
   trunk. Produces a synthetic "fully correct" trunk — useful for a known-good demo execution, not
   needed for grading a real subagent's trunk (that's just whatever it produced).
3. `scripts/render_manual.py <task_id> --before` — renders the task-level before block (once per
   task, not per execution): the baseline's own panorama + one whole-room quad view, no highlight.
   Its crop is the union bbox of every task entry's baseline position, padded — not hand-picked.
4. Get a subject trunk to grade: `scripts/run_eval.py <task_id> <skill_dir>` runs an isolated agent
   session and produces one (see `EVAL-PROCEDURE.md` for how and why); or point at any trunk you
   already have — a hand-built one, one from `build_gold.py`, anything.
5. `scripts/extract_execution.py <task_id> <subject_trunk> [--run-id ID] [--label TEXT]` — the ONLY
   step that touches the subject trunk. Persists the diff between the baseline and the subject as a
   real `git diff` patch (`diff.patch`), plus the 8-frame `level photo --native` panorama tour
   (unavoidably rendered now, since it's a whole-scene shot, not per-actor). Once this has run, the
   subject trunk (which can be an ephemeral job tmp dir) is never needed again — everything past
   this point works from just the cached base trunk + `diff.patch`. Writes
   `tasks/<task_id>/executions/<run_id>/{execution.json,diff.patch,panorama/pan_N.png}`.
6. `scripts/render_execution.py <task_id> <run_id>` — a real diff of the WHOLE level, computed by
   copying the base trunk twice, applying `diff.patch` to one copy, and comparing: every actor
   whose full T3D block or CSG `order_value` differs at all, or that exists in only one copy, gets
   a BEFORE and an AFTER quad view (Top/Front/Iso/Side), that actor highlighted, labeled
   `CREATED`/`UPDATED`/`DELETED`. This is not filtered through the task's own `entries`: an actor
   the task never mentioned still shows up, flagged as undeclared, because the human needs to see
   the truth, not a subset filtered through what the task predicted. EVERY picture in the execution
   — every actor, both BEFORE and AFTER — shares ONE crop: the union bbox of everything touched,
   padded. This is load-bearing, not an optimization: an actor that didn't move must land at the
   same screen position in every picture, or before/after and actor-to-actor comparison isn't
   reliable. A `DELETED` actor's AFTER picture (or any diffed actor missing from one of the two
   copies) is a composite: that actor's own directory physically copied in from the other copy into
   a throwaway scratch copy, still highlighted, so its absence is visible, not just implied.
   Re-runnable any time (e.g. after a rendering bug fix) without touching the subject trunk or an
   existing grade — only `manifest.json` and `entries/` get replaced. Writes
   `tasks/<task_id>/executions/<run_id>/{manifest.json,entries/<actor>_{before,after}.png}`.
7. `scripts/build_page.py` assembles `index.html` from every task's before block plus every
   `tasks/<task_id>/executions/*/manifest.json` it finds — no registration needed, dropping a new
   execution directory in is enough.
8. `scripts/serve.py [port]` (default 8756) replaces plain `python -m http.server`: same static
   file serving, plus `GET /api/grades` and `POST /api/grade` (stdlib only, no new deps) backing
   `tasks/<task_id>/executions/<run_id>/grade.json`.

Never hand-edit a picture, a `manifest.json`, or a `grade.json` directly. The `maps/<level>/`-scoping,
base-trunk fingerprint check, and why `patch` (not `git apply`) is used to apply `diff.patch` are all
explained in `extract_execution.py`'s and `render_execution.py`'s own docstrings.

## Grading — manual, from pictures

A card per execution: a panorama tour, then one BEFORE/AFTER pair of quad pictures per actor it
actually touched. Click a picture to enlarge; ←/→ moves between actors (swipe works too, and keeps
your before/after choice), ↑/↓ flips before/after (swipe or the on-screen buttons on mobile). Score
0–10 + a note, saved immediately via the API above and editable any time — no submit-once lock.

A `grade.json` is per-viewer live state, not reference material — don't hand-author one for a
committed execution.

## Base trunks

A task's `dx_map` field (its shipped map, e.g. `03_NYC_UNATCOHQ`) is imported fresh from this
checkout's own `dev/games/deusex/Maps/<dx_map>.dx` the first time anything needs it —
`build_gold.base_trunk_for` — a few seconds per level (measured: UNATCO ~7s, NYC_Bar ~2s, WanChai
Market ~9s), cached after that and shared by every task on the same map. Not this repo's problem to
commit — DX content isn't ours to commit — but not something you set up by hand either.

Cached under `BASE_TRUNKS_DIR` (default `dev/evals/_scratch/base_trunks/`, gitignored); override
it if you want the cache somewhere else. `run_eval.py`'s own `eval_runs/` (one subject trunk per
agent run) lives alongside it, same directory.
