"""Render everything a human needs to MANUALLY grade one execution (a
subagent's subject trunk) of a task: a panorama tour, and TWO UED-style
quad views (Top/Front/Iso/Side, via `actor diagram --layout quad`) --
BEFORE and AFTER -- per oracle entry the execution ACTUALLY touched -- its
full T3D block or CSG order_value differs at all from the baseline, or it
was created/removed (see `_entry_changed`). An entry whose actor is
untouched gets no picture at all: most tasks have far more `entries` than
an execution ever really touches.

EVERY picture for one execution -- BEFORE and AFTER, every touched actor --
shares the SAME `--frame`: the union bbox of every touched actor (both its
baseline and subject position, so both fit), padded by FRAME_PAD. This is
load-bearing, not an optimization: an actor that didn't move must land at
the exact same screen position whether you're looking at its own picture
or another actor's, and whether you're looking at BEFORE or AFTER -- a
per-actor or per-variant frame would shift it, making before/after (or
actor-to-actor) comparison unreliable. Stays bbox-filtered (`actor find
--overlapping-bbox`), never the full level (measured: a literal "every
actor in the level" render was ~103s vs ~6s bbox-filtered -- 17x slower,
and would cost hours at this scale).

An entry's actor is looked up in whichever trunk is being rendered (subject
for AFTER, baseline for BEFORE). When it's not there (a subagent-deleted
actor for AFTER, or a not-yet-existing one for BEFORE), the quad is
rendered from a COMPOSITE: the scene as it stands in that trunk, plus the
missing actor's own T3D block reinserted from the OTHER trunk, still
highlighted -- see `_render_view`.

Also renders each task's "before" block: the baseline's own panorama + ONE
quad view of the whole room, no highlight -- shown once per task, not per
execution. Its frame is the union bbox of every task entry (not just
touched ones, since there's no execution yet), FRAME_PAD padded.

Usage: render_manual.py <task_id> <subject_trunk> [--run-id ID] [--label TEXT]
       render_manual.py <task_id> --before   (renders the task's before block
                                               from its own base_trunk)
"""
import argparse, datetime, json, os, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from render_photos import render_photos

ROOT = pathlib.Path(__file__).resolve().parents[1]
WT = str(ROOT.parents[1])  # the uedcli checkout -- cwd uedcli needs for `-m uedcli` module resolution
# The main checkout's venv specifically, not WT's -- a worktree's own .venv/ (if it has one at all)
# has no uedcli_native built; only /workspace/uedcli/.venv does.
PY = "/workspace/uedcli/.venv/bin/python"
RUNS = ROOT / "runs"
IMG = ROOT / "img"
if "BASE_TRUNKS_DIR" not in os.environ:
    sys.exit("BASE_TRUNKS_DIR not set -- point it at wherever your base trunk extractions live "
             "(see README.md's \"Base trunks\" section); no default, DX content isn't ours to assume a path for")
BASE_TRUNKS_DIR = pathlib.Path(os.environ["BASE_TRUNKS_DIR"])
FRAME_PAD = 64

LABELS = {"created": "CREATED", "updated": "UPDATED", "unchanged": "UNCHANGED", "deleted": "DELETED"}

def _run(project, level, args, **kw):
    env = {**os.environ, "UEDCLI_PROJECT": str(project), "UEDCLI_LEVEL": level}
    return subprocess.run([PY, "-m", "uedcli", *args], cwd=WT, env=env,
                           capture_output=True, text=True, **kw)

def _actor_exists(project: pathlib.Path, level: str, actor: str) -> bool:
    r = _run(project, level, ["actor", "prop", "get", actor, "Location"])
    return not (r.returncode != 0 and "Actor not found" in r.stderr + r.stdout)

def _order_value(project: pathlib.Path, level: str, actor: str) -> str | None:
    """The actor's raw LexoRank CSG-order sidecar (maps/<level>/actors/<actor>/
    order_value) -- NOT part of its T3D block (`actor show` never emits it;
    it's a trunk-side file, see uedcli/trunk.py), so a pure CSG-order change
    (`actor order`, no geometry touched) is otherwise invisible to a T3D diff."""
    p = project / "maps" / level / "actors" / actor / "order_value"
    return p.read_text() if p.exists() else None

def _show(project, level, names):
    """`actor show` block for `names` (possibly empty -> "")."""
    if not names:
        return ""
    r = _run(project, level, ["actor", "show", "-"], input="\n".join(names))
    r.check_returncode()
    return r.stdout

def _entry_changed(baseline, subject, task, entry) -> bool:
    """True if ANYTHING about `entry`'s actor differs between baseline and
    subject -- exists in only one of the two trunks, its full T3D block
    (every vertex, every property, CSG op, texture -- not just position, and
    not just the task's own expected corners) differs at all, or its CSG
    order_value differs (a reorder with no geometry change). A narrower
    position/corner-only check can call a real but unrelated change
    "unchanged" it isn't; this is ground truth, the same dump `actor show`
    always produces, byte for byte.

    A `create` entry's `actor` is an EXISTING actor used only to frame the
    shot (see spec_format.py) -- not the new actor's own name, which is
    unknown ahead of time, so there's nothing to diff. Always touched:
    grading is manual, and whether something was actually added is exactly
    what the human looks at the picture to judge."""
    if entry["kind"] == "create":
        return True
    actor = entry["actor"]
    level = task["level"]
    base_exists = _actor_exists(baseline, level, actor)
    sub_exists = _actor_exists(subject, level, actor)
    if base_exists != sub_exists:
        return True
    if not sub_exists:
        return False
    if _show(baseline, level, [actor]) != _show(subject, level, [actor]):
        return True
    return _order_value(baseline, level, actor) != _order_value(subject, level, actor)

def _bucket(entry):
    k = entry["kind"]
    if k == "update":
        return "unchanged" if entry.get("target") == "unchanged" else "updated"
    if k == "anchor":
        return "updated"
    if k == "create":
        return "created"
    if k == "delete":
        return "deleted"
    raise ValueError(f"unknown entry kind {k!r}: {entry}")

_BBOX_RE = re.compile(r"min\s+([-\d.]+),([-\d.]+),([-\d.]+)\s*\n\s*max\s+([-\d.]+),([-\d.]+),([-\d.]+)")

def _bbox_union_call(project, level, actors):
    """Union bbox over `actors` in `project`, via ONE `actor bbox` call --
    it already unions a multi-actor set itself, so this is ~1.5s regardless
    of set size, vs ~1.5s PER ACTOR calling it one at a time (measured: a
    35-actor frame went from 100s+ to a couple of seconds). `actor bbox`
    errors hard if ANY name doesn't exist in `project`, so on failure this
    falls back to filtering out the missing ones first (individually, only
    on that rare path -- a create/delete entry, of which neither current
    task has any) and retrying."""
    if not actors:
        return None
    r = _run(project, level, ["actor", "bbox", *actors])
    if r.returncode != 0:
        existing = [a for a in actors if _actor_exists(project, level, a)]
        if not existing:
            return None
        r = _run(project, level, ["actor", "bbox", *existing])
        if r.returncode != 0:
            return None
    m = _BBOX_RE.search(r.stdout)
    if not m:
        return None
    x0, y0, z0, x1, y1, z1 = map(float, m.groups())
    return (x0, y0, z0), (x1, y1, z1)

def _frame_from_actors(projects, level, actors, pad):
    """A `--frame` string: the union bbox of `actors` across every project in
    `projects` (an actor missing from one project just contributes nothing
    from that one), padded by `pad` on every side. None if none of the
    actors exist in any project."""
    boxes = [b for p in projects if (b := _bbox_union_call(p, level, actors)) is not None]
    if not boxes:
        return None
    x0 = min(b[0][0] for b in boxes) - pad
    y0 = min(b[0][1] for b in boxes) - pad
    z0 = min(b[0][2] for b in boxes) - pad
    x1 = max(b[1][0] for b in boxes) + pad
    y1 = max(b[1][1] for b in boxes) + pad
    z1 = max(b[1][2] for b in boxes) + pad
    return ",".join(str(round(v, 2)) for v in (x0, y0, z0, x1, y1, z1))

def _scene_names(project, level, frame):
    r = _run(project, level, ["actor", "find", "--overlapping-bbox", frame])
    r.check_returncode()
    return r.stdout.split()

def _diagram_live_names(project, level, names, frame, highlight, out_path):
    names = list(names)
    # --overlapping-bbox tests each actor's own bbox against `frame`; a
    # point actor mounted slightly proud of a wall (e.g. a light sconce) can
    # sit just outside it and get dropped -- always keep the highlight
    # target in the render set regardless, or --highlight has nothing to
    # highlight and the whole call errors.
    if highlight and highlight not in names:
        names.append(highlight)
    args = ["actor", "diagram", *names,
            "--layout", "quad", "--faces", "wire", "--brush-colors", "csg",
            "--frame", frame, "--size", "1800", "--out", str(out_path)]
    if highlight:
        args += ["--highlight", highlight]
    r = _run(project, level, args)
    r.check_returncode()

def _diagram_live(project, level, frame, highlight, out_path):
    _diagram_live_names(project, level, _scene_names(project, level, frame), frame, highlight, out_path)

def _diagram_composite(scene_project, level, scene_names, missing_project, missing_actor, frame, out_path):
    """Render `scene_names` as they stand in `scene_project`, PLUS
    `missing_actor` reinserted from `missing_project` -- for an actor that
    doesn't exist in `scene_project`."""
    tmp = out_path.parent / "_t3d"
    tmp.mkdir(exist_ok=True)
    scene_file = tmp / f"{out_path.stem}_scene.t3d"
    missing_file = tmp / f"{out_path.stem}_missing.t3d"
    scene_file.write_text(_show(scene_project, level, scene_names))
    missing_file.write_text(_show(missing_project, level, [missing_actor]))
    args = ["actor", "diagram", "--from-t3d", str(scene_file), str(missing_file),
            "--layout", "quad", "--faces", "wire", "--brush-colors", "csg",
            "--frame", frame, "--highlight", missing_actor, "--size", "1800", "--out", str(out_path)]
    r = _run(scene_project, level, args)  # project irrelevant under --from-t3d, kept for a stable env
    r.check_returncode()

def _render_view(render_project, other_project, level, frame, actor, out_path):
    """Render `actor` highlighted from `render_project`'s current state, its
    scene bbox-filtered to `frame`. If `actor` doesn't exist there (deleted
    for an AFTER render, not-yet-created for a BEFORE render), reinsert it
    from `other_project` (composite) so it's still visible at its last
    known position."""
    names = _scene_names(render_project, level, frame)
    if _actor_exists(render_project, level, actor):
        _diagram_live_names(render_project, level, names, frame, actor, out_path)
        return
    if _actor_exists(other_project, level, actor):
        scene = [n for n in names if n != actor]
        _diagram_composite(render_project, level, scene, other_project, actor, frame, out_path)
        return
    _diagram_live_names(render_project, level, names, frame, None, out_path)

def render_execution(task_id: str, subject: pathlib.Path, run_id: str, label: str | None = None) -> dict:
    task = TASKS[task_id]
    baseline = BASE_TRUNKS_DIR / task["base_trunk"]
    out_dir = RUNS / task_id / run_id
    entries_dir = out_dir / "img" / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)

    level = task["level"]
    touched = [e for e in task["entries"] if _entry_changed(baseline, subject, task, e)]
    touched_actors = [e["actor"] for e in touched]
    frame = _frame_from_actors([baseline, subject], level, touched_actors, FRAME_PAD)

    entries = []
    for e in touched:
        actor = e["actor"]
        bucket = _bucket(e)
        before_path = entries_dir / f"{actor}_before.png"
        after_path = entries_dir / f"{actor}_after.png"
        _render_view(baseline, subject, level, frame, actor, before_path)
        _render_view(subject, baseline, level, frame, actor, after_path)
        entries.append(dict(actor=actor, bucket=bucket, label=LABELS[bucket], what=e["what"],
                             img_before=f"entries/{actor}_before.png",
                             img_after=f"entries/{actor}_after.png"))

    render_photos(task, subject, out_dir / "img")

    manifest = dict(
        task_id=task_id, run_id=run_id, label=label or run_id,
        subject_trunk=str(subject),
        rendered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        n_task_entries=len(task["entries"]),
        entries=entries,
        panorama=[f"pan_{i}.png" for i in range(8)],
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

def render_before(task_id: str) -> None:
    """The task-level before block: the whole-room quad + panorama, shown
    once per task (not per execution). Frame is the union bbox of every
    task entry's baseline position, FRAME_PAD padded -- same computed-not-
    hand-authored approach as an execution's own frame, just over the
    task's full entry set instead of one execution's touched subset."""
    task = TASKS[task_id]
    baseline = BASE_TRUNKS_DIR / task["base_trunk"]
    out_dir = IMG / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = _frame_from_actors([baseline], task["level"], [e["actor"] for e in task["entries"]], FRAME_PAD)
    _diagram_live(baseline, task["level"], frame, None, out_dir / "before_quad.png")
    render_photos(task, baseline, out_dir, prefix="pan_before")
    print("rendered before block for", task_id, "->", out_dir)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("task_id")
    ap.add_argument("subject_trunk", nargs="?")
    ap.add_argument("--before", action="store_true", help="render the task's before block instead of an execution")
    ap.add_argument("--run-id", default=None, help="defaults to a UTC timestamp")
    ap.add_argument("--label", default=None, help="human-readable name shown on the page")
    args = ap.parse_args()

    if args.before:
        render_before(args.task_id)
        sys.exit(0)

    if not args.subject_trunk:
        ap.error("subject_trunk is required unless --before")
    run_id = args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = render_execution(args.task_id, pathlib.Path(args.subject_trunk), run_id, args.label)
    print(f"rendered {len(manifest['entries'])} entries + panorama -> runs/{args.task_id}/{run_id}/manifest.json")
