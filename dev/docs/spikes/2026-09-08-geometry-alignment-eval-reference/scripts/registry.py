"""Auto-discovers every specs/<task_id>.py and aggregates their `TASK` dicts
into one TASKS = {id: TASK} map. Adding a new task is: add a new
specs/<file>.py exporting TASK (see spec_format.py for the shape) -- nothing
else changes. No file in this pipeline lists task ids by hand.
"""
import importlib.util, pathlib

SPECS_DIR = pathlib.Path(__file__).parent / "specs"

def _load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(f"specs.{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TASK

TASKS = {}
for _f in sorted(SPECS_DIR.glob("*.py")):
    if _f.stem.startswith("_"):
        continue
    _task = _load(_f)
    if _task["id"] in TASKS:
        raise ValueError(f"duplicate task id {_task['id']!r}: {_f} and an earlier spec file both define it")
    TASKS[_task["id"]] = _task
