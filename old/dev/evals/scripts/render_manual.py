"""Render a task's "before" block: the baseline's own panorama + ONE
UED-style quad view (Top/Front/Iso/Side) of the whole room, no highlight --
shown once per task, not per execution (execution rendering is
extract_execution.py + render_execution.py). Frame is the union bbox of
every task entry with an `actor` (not just touched ones, since there's no
execution yet), FRAME_PAD padded -- same
computed-not-hand-authored approach render_execution.py uses for an
execution's own frame.

Usage: render_manual.py <task_id> --before
"""
import argparse, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from render_photos import render_photos
from build_gold import base_trunk_for
import render_common as rc

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"

def render_before(task_id: str) -> None:
    task = TASKS[task_id]
    baseline = base_trunk_for(task)
    out_dir = TASKS_DIR / task_id / "before"
    out_dir.mkdir(parents=True, exist_ok=True)
    actors = [e["actor"] for e in task["entries"] if e.get("actor")]
    frame = rc.frame_from_actors([baseline], task["level"], actors, rc.FRAME_PAD)
    rc.diagram_live(baseline, task["level"], frame, None, out_dir / "quad.png")
    render_photos(task, baseline, out_dir)
    print("rendered before block for", task_id, "->", out_dir)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id")
    ap.add_argument("--before", action="store_true", required=True,
                     help="render the task's before block (the only thing this script does)")
    args = ap.parse_args()
    render_before(args.task_id)
