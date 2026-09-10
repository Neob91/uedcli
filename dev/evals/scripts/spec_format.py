"""The task-spec format every file under specs/ uses. Not imported for its
code (there is none) -- read this before writing a new specs/<task_id>.py.

Each specs/<task_id>.py exports one module-level `TASK` dict:

  id, level, title, req   -- identity + the task prompt (as given to a subagent)
  dx_map                   -- the shipped map this task's baseline is imported from
                               (dev/games/deusex/Maps/<dx_map>.dx, no extension here) --
                               `build_gold.base_trunk_for` imports it fresh into
                               BASE_TRUNKS_DIR/<dx_map>/maps/<level>/ on first use (a few
                               seconds; cached after that, shared by every task on the
                               same dx_map)
  photo_camera              -- dict(at=[x,y,z], pitch=UU) for the 8x45°
                               `level photo --native` tour (yaw 0,8192,...,
                               57344) rendered by scripts/render_photos.py
                               from ANY trunk (the gold reference, or a
                               trial's subject trunk) -- one definition per
                               task feeds both. `pitch` in rotation units,
                               16384=90°; use e.g. 4096 to tilt up toward a
                               ceiling task's fixtures.
  before                   -- dict(quad=img_name, note=str, photos=[img_name,
                               ...]) for the task-level "before any edit"
                               context block on the page: one UED-style quad
                               view (Top/Front/Iso/Side) of the whole room,
                               no highlight, plus the panorama tour. `quad`
                               is rendered by render_manual.py's
                               render_before(), never hand-captured.
  entries                  -- the flat list of acceptance criteria (below)

No `frame` field: the crop every picture uses is computed, not hand-picked --
render_manual.py derives it per execution from the union bbox of whatever that
execution actually touched (see its own docstring). A hand-authored per-task
frame used to exist and quietly excluded actors outside it from every picture
(a real bug, caught and fixed); don't reintroduce one.

`entries` is the closed vocabulary every uedcli geometry verb's RESULT
reduces to (move/resize/clip/scale/rotate all just produce some final
property/shape value; only existence is structurally different) -- four
kinds:

  update  -- an actor's props (or specific named corners, or a full T3D
             `Begin Brush...End Brush` block for a non-delta reshape like a
             clip) must equal an ABSOLUTE target: a task-pinned value
             (target="corners", at=[...], delta=[...]), or the baseline value
             (target="unchanged").
  anchor  -- an actor's delta must equal a SPECIFIC other actor's (`to`)
             ACTUAL delta in the SAME trunk being graded -- not a hardcoded
             number, so "the flagpole is broken" stays distinguishable from
             "the wall itself moved by the wrong amount," and an equally
             valid alternative solution at a different absolute position
             still grades correct. Verified per-actor from real geometry
             (which wall/anchor an actor is actually attached to), never
             assumed uniform across a scenario.
  create  -- a NEW actor should exist, not present in the baseline. Grading
             is manual (a human looking at the picture), so there's no
             expected-geometry match to encode: `actor` names an EXISTING
             actor near where the new one belongs, used only to frame the
             before/after shot -- not the new actor's own name (unknown
             ahead of time; the agent picks it). Always rendered, since
             whether anything was actually added can't be detected without
             a fixed name to check.
  delete  -- an actor must no longer exist. `actor` is the real baseline
             name here -- unlike `create`, there's a fixed actor to check.

`update`'s full-geometry form (a T3D `Begin Brush...End Brush` block for a
non-delta reshape) has no code path anywhere in this pipeline yet -- no
current task needs one; add real handling (in `render_manual.py`'s
`_entry_changed`/`_bucket`) only when a real task does, not speculatively.

Every entry carries a `what`: plain-language identification of the actor
(what it is, not why it matters) -- shown next to its picture on the page.
Grading is manual (a human looking at the pictures), so `what` is purely for
the reader; nothing mechanical consumes it.

Image names in `before` are relative to this task's own img/<task_id>/
directory (see registry.py) -- no cross-task namespacing needed.
"""
