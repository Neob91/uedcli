# task.json format

The shape every `tasks/<task_id>/task.json` uses -- read this before writing a new one.

Each `tasks/<task_id>/task.json` is one JSON object (no `id` field -- the id is the directory
name; `registry.py` sets it when loading, so there's exactly one place id and directory can
disagree: nowhere):

- `level`, `title`, `req` -- identity + the task prompt (as given to a subagent).
- `dx_map` -- the shipped map this task's baseline is imported from
  (`dev/games/deusex/Maps/<dx_map>.dx`, no extension here) -- `build_gold.base_trunk_for` imports
  it fresh into `BASE_TRUNKS_DIR/<dx_map>/maps/<level>/` on first use (a few seconds; cached after
  that, shared by every task on the same `dx_map`).
- `photo_camera` -- `{"at": [x,y,z], "pitch": UU}` for the 8x45° `level photo --native` tour
  (yaw 0,8192,...,57344) rendered by `render_photos.py` from ANY trunk (the gold reference, or an
  execution's subject trunk) -- one definition per task feeds both. `pitch` in rotation units,
  16384=90°; use e.g. 4096 to tilt up toward a ceiling task's fixtures.
- `before` -- `{"note": str}` for the task-level "before any edit" context block on the page: one
  UED-style quad view (Top/Front/Iso/Side) of the whole room, no highlight, plus the panorama tour.
  The images themselves are always `before/quad.png` + `before/pan_0.png … pan_7.png` (rendered by
  `render_manual.py --before`, never hand-captured) -- nothing in `task.json` names them, since the
  directory holds nothing else.
- `entries` -- `actor`/`what` labels, below. Don't leave this empty even on a pure-creation task:
  `render_manual.py --before` frames the whole-room "before" shot from the union bbox of `entries`'
  own actors (there's no execution yet to diff against), and an empty list gives it nothing to
  frame around -- keep at least one `actor`/`what` entry naming something nearby, purely as a frame
  anchor.

No `frame` field: the crop every picture uses is computed, not hand-picked -- `render_execution.py`
derives it per execution from the union bbox of whatever that execution actually touched. A
hand-authored per-task frame used to exist and quietly excluded actors outside it from every
picture (a real bug, caught and fixed); don't reintroduce one.

## `entries`: what it's for, and what it's NOT for

Grading is manual -- a human looks at the pictures. What gets a picture is a real diff of the whole
trunk (baseline vs. subject, via `diff.patch` -- see `extract_execution.py`/`render_execution.py`):
every actor that's created, deleted, or whose full T3D block/CSG `order_value` differs at all.
`entries` does NOT gate
this -- an agent that touches an actor the task never mentions still shows up, flagged as not
declared in the spec, which is the point: the human needs to see the truth, not a subset filtered
through what the task predicted.

Each `entries` item carries `actor` (the actor's real name in the baseline, or the name it's
expected to get) and `what` (plain-language identification of the actor -- what it is, not why it
matters), looked up by actor name when a diffed actor happens to match one. Neither
`render_execution.py` nor `build_page.py` reads anything else off an entry.

`build_gold.py` (builds the demo "fully correct" trunk for a task) is SEPARATE from grading and
still reads `kind`/`target`/`at`/`delta`/`to`: `update(target="corners", at=[...], delta=[...])`
moves those corners; `anchor(to=<actor>)` moves by whatever delta the gold trunk actually gave its
anchor; `update(target="unchanged")` needs no op. Only include these fields on an entry you want
`build_gold.py` to apply -- an entry with just `actor`/`what` (no `kind`) is a pure display label,
and `build_gold.py` leaves that actor untouched. It has no handling for a `create`-kind entry --
never did, it can't synthesize a new actor -- so a task whose only edit is a creation has no
`update`/`anchor` entries at all, just the frame-anchor entry described above.
