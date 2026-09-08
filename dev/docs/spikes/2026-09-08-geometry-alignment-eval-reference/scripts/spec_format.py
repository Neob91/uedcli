"""The task-spec format every file under specs/ uses. Not imported for its
code (there is none) -- read this before writing a new specs/<task_id>.py.

Each specs/<task_id>.py exports one module-level `TASK` dict:

  id, level, title, req   -- identity + the task prompt (as given to a subagent)
  base_trunk               -- which baseline project (in BASE_TRUNKS_DIR) this
                               task starts from
  frame                    -- explicit world-space AABB "X0,Y0,Z0,X1,Y1,Z1"
                               (uedcli `actor diagram --frame`) that crops
                               every picture to the room this task edits --
                               NOT the whole level. Per-task because a
                               different task on the same level may edit a
                               different room; `level` alone isn't enough.
  photo_camera              -- dict(at=[x,y,z], pitch=UU) for the 8x45°
                               `level photo --native` tour (yaw 0,8192,...,
                               57344) rendered by scripts/render_photos.py
                               from ANY trunk (the gold reference, or a
                               trial's subject trunk) -- one definition per
                               task feeds both. `pitch` in rotation units,
                               16384=90°; use e.g. 4096 to tilt up toward a
                               ceiling task's fixtures.
  before                   -- dict(diags=[(img_name, caption), ...],
                               photos=[img_name, ...]) for the task-level
                               "before any edit" context block on the page
  entries                  -- the flat list of acceptance criteria (below)
  scenarios                -- dict(scenario_id -> dict(title, view, note,
                               members=[actor,...], extra_photos=[(img,cap),...]))
                               for HUMAN-READABLE grouping on the page only;
                               does not affect grading, which always walks
                               `entries` flat regardless of scenario boundaries

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
  create  -- a NEW actor must exist, not present in the baseline, of a given
             class with matching props (and full geometry for a brush).
             Graded by diffing the actor-NAME SET between baseline and
             subject trunk (no fixed name to look up), not a lookup.
  delete  -- an actor must no longer exist.

`create`/`delete` and `update`'s full-geometry form are part of the
vocabulary but NOT implemented in check_trunk.py (raises NotImplementedError
if an entry ever uses one) -- add real handling only when a real task needs
one, not speculatively.

Every entry carries a `why`: plain language, not consumed by the mechanical
check. Grading cares about the RESULT, not how an agent got there --
check_trunk.py prints `why` under every FAILURE line, so a mechanical fail is
a prompt to check whether the intent was satisfied some other way, not an
automatic hard fail.

Image names in `before`/`scenarios[...].extra_photos` are relative to this
task's own img/<task_id>/ directory (see registry.py) -- no cross-task
namespacing needed.
"""
