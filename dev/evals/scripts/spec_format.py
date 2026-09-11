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
  entries                  -- optional `what` labels (below) -- NOT what drives
                               what gets shown

No `frame` field: the crop every picture uses is computed, not hand-picked --
render_manual.py derives it per execution from the union bbox of whatever that
execution actually touched (see its own docstring). A hand-authored per-task
frame used to exist and quietly excluded actors outside it from every picture
(a real bug, caught and fixed); don't reintroduce one.

Grading is manual -- a human looks at the pictures. So detection is a real
diff of the whole trunk (`render_manual.py`'s `_diff_actors`): baseline vs.
subject, every actor, classified created/updated/deleted by whether its full
T3D block or CSG order_value differs at all. `entries` does NOT gate this --
an agent that touches an actor the task never mentions still shows up, which
is the point: the human needs to see the truth, not a subset filtered through
what the task predicted. `entries` only supplies an optional `what` label,
looked up by actor name, for a diffed actor that happens to match one; when
none matches, the page just says so and flags it for the human to look at.

Each `entries` item: `actor` (the actor's real name in the baseline OR the
name it's expected to get) and `what` (plain-language identification of the
actor -- what it is, not why it matters). Neither `render_manual.py` nor
`build_page.py` reads anything else off an entry.

`build_gold.py` (builds the demo "fully correct" trunk for a task) is
SEPARATE from grading and still reads `kind`/`target`/`at`/`delta`/`to`:
`update(target="corners", at=[...], delta=[...])` moves those corners;
`anchor(to=<actor>)` moves by whatever delta the gold trunk actually gave its
anchor. Only include these fields on an entry you want `build_gold.py` to
apply -- an entry with just `actor`/`what` (no `kind`) is a pure display
label and `build_gold.py` leaves that actor untouched. `build_gold.py` has no
handling for a `create`-kind entry (never did -- it can't synthesize a new
actor).

A newly created actor gets its `what` shown only if you happen to already
know its real name (rare -- the agent picks it). Otherwise it just shows up
unlabeled, correctly, with no framing workaround needed.

Don't leave `entries` empty even on a pure-creation task: `render_before`
frames the task's whole-room "before" shot from the union bbox of `entries`'
own actors (there's no execution yet to diff), and an empty list gives it
nothing to frame around. Keep at least one `actor`/`what` entry (no `kind`
needed) naming something nearby, purely as a frame anchor.

Image names in `before` are relative to this task's own img/<task_id>/
directory (see registry.py) -- no cross-task namespacing needed.
"""
