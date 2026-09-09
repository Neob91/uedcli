"""Render everything a human needs to MANUALLY grade one execution (a
subagent's subject trunk) of a task: a panorama tour, and one UED-style quad
view (Top/Front/Iso/Side, via `actor diagram --layout quad`) per oracle
entry, with only that entry's actor highlighted and labeled by what the
task expects of it -- created / updated / unchanged / deleted.

An entry's actor is looked up in the SUBJECT trunk. When it's not there
(the deleted case, or an update/anchor actor a subagent wrongly deleted),
the quad is rendered from a COMPOSITE: every other task-relevant actor from
the subject trunk (so the picture still shows the actual final room), plus
that one missing actor's own T3D block reinserted from the BASELINE (its
last known position) via `actor diagram --from-t3d`, still highlighted.
This is the only way to show "here's where it used to be" for an actor that
no longer exists in the trunk being graded.

Also renders each task's "before" block: the baseline's own panorama +
ONE quad view of the whole room, no highlight -- shown once per task, not
per execution.

Usage: render_manual.py <task_id> <subject_trunk> [--run-id ID] [--label TEXT]
       render_manual.py <task_id> --before   (renders the task's before block
                                               from its own base_trunk)
"""
import argparse, datetime, json, os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from render_photos import render_photos
from check_trunk import _actor_exists

WT = "/workspace/uedcli/.claude/worktrees/geom-eval"
PY = "/workspace/uedcli/.venv/bin/python"
ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference")
RUNS = ROOT / "runs"
IMG = ROOT / "img"
BASE_TRUNKS_DIR = pathlib.Path(os.environ.get("BASE_TRUNKS_DIR", "/home/agent/.claude/jobs/92851c21/tmp"))

LABELS = {"created": "CREATED", "updated": "UPDATED", "unchanged": "UNCHANGED", "deleted": "DELETED"}

def _run(project, args, **kw):
    env = {**os.environ, "UEDCLI_PROJECT": str(project), "UEDCLI_LEVEL": "unatco"}
    return subprocess.run([PY, "-m", "uedcli", *args], cwd=WT, env=env,
                           capture_output=True, text=True, **kw)

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

def _scene_names(project, frame):
    r = _run(project, ["actor", "find", "--overlapping-bbox", frame])
    r.check_returncode()
    return r.stdout.split()

def _show(project, names):
    """`actor show` block for `names` (possibly empty -> "")."""
    if not names:
        return ""
    r = _run(project, ["actor", "show", "-"], input="\n".join(names))
    r.check_returncode()
    return r.stdout

def _diagram_live(project, frame, highlight, out_path):
    names = _scene_names(project, frame)
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
    r = _run(project, args)
    r.check_returncode()

def _diagram_composite(scene_project, scene_names, missing_project, missing_actor, frame, out_path):
    """Render `scene_names` as they stand in `scene_project`, PLUS
    `missing_actor` reinserted from `missing_project` -- for an actor that
    doesn't exist in `scene_project` any more."""
    tmp = out_path.parent / "_t3d"
    tmp.mkdir(exist_ok=True)
    scene_file = tmp / f"{out_path.stem}_scene.t3d"
    missing_file = tmp / f"{out_path.stem}_missing.t3d"
    scene_file.write_text(_show(scene_project, scene_names))
    missing_file.write_text(_show(missing_project, [missing_actor]))
    args = ["actor", "diagram", "--from-t3d", str(scene_file), str(missing_file),
            "--layout", "quad", "--faces", "wire", "--brush-colors", "csg",
            "--frame", frame, "--highlight", missing_actor, "--size", "1800", "--out", str(out_path)]
    r = _run(scene_project, args)  # project irrelevant under --from-t3d, kept for a stable env
    r.check_returncode()

def render_entry(task, subject, baseline, entry, out_path):
    """Renders one entry's quad. Returns the bucket label. `entry["actor"]`
    missing from BOTH trunks (an unimplemented `create` case) renders the
    plain scene with no highlight."""
    actor = entry.get("actor")
    bucket = _bucket(entry)
    frame = task["frame"]
    if actor is None:
        _diagram_live(subject, frame, None, out_path)
        return bucket
    if _actor_exists(subject, actor):
        _diagram_live(subject, frame, actor, out_path)
        return bucket
    # actor absent from the subject trunk -- show the final scene with it
    # reinserted from wherever it last existed (baseline), still highlighted
    source = baseline if _actor_exists(baseline, actor) else None
    if source is None:
        _diagram_live(subject, frame, None, out_path)
        return bucket
    scene = [n for n in _scene_names(subject, frame) if n != actor]
    _diagram_composite(subject, scene, source, actor, frame, out_path)
    return bucket

def render_execution(task_id: str, subject: pathlib.Path, run_id: str, label: str | None = None) -> dict:
    task = TASKS[task_id]
    baseline = BASE_TRUNKS_DIR / task["base_trunk"]
    out_dir = RUNS / task_id / run_id
    entries_dir = out_dir / "img" / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for e in task["entries"]:
        actor = e.get("actor", "unknown")
        img_name = f"entries/{actor}"
        bucket = render_entry(task, subject, baseline, e, entries_dir / f"{actor}.png")
        entries.append(dict(actor=actor, bucket=bucket, label=LABELS[bucket], img=f"{img_name}.png", why=e["why"]))

    render_photos(task, subject, out_dir / "img")

    manifest = dict(
        task_id=task_id, run_id=run_id, label=label or run_id,
        subject_trunk=str(subject),
        rendered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        entries=entries,
        panorama=[f"pan_{i}.png" for i in range(8)],
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

def render_before(task_id: str) -> None:
    task = TASKS[task_id]
    baseline = BASE_TRUNKS_DIR / task["base_trunk"]
    out_dir = IMG / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    _diagram_live(baseline, task["frame"], None, out_dir / "before_quad.png")
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
