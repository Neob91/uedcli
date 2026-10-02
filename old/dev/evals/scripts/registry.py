"""Auto-discovers every tasks/<task_id>/task.json and aggregates them into
one TASKS = {id: TASK} map. Adding a new task is: add a new
tasks/<id>/task.json (see spec_format.md for the shape) -- nothing else
changes. No file in this pipeline lists task ids by hand.
"""
import json, pathlib

TASKS_DIR = pathlib.Path(__file__).resolve().parents[1] / "tasks"

TASKS = {}
for _d in sorted(p for p in TASKS_DIR.iterdir() if p.is_dir()):
    _f = _d / "task.json"
    if not _f.exists():
        continue
    _task = json.loads(_f.read_text())
    if "id" in _task:
        raise ValueError(f"{_f} carries an 'id' field -- the id comes from the directory name only")
    _task["id"] = _d.name
    if _task["id"] in TASKS:
        raise ValueError(f"duplicate task id {_task['id']!r}")
    TASKS[_task["id"]] = _task
