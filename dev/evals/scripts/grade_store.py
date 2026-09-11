"""Persistence for manual grades: one JSON file per execution
(tasks/<task_id>/executions/<run_id>/grade.json), so a grade survives a
page reload and stays editable at any time -- and re-rendering an
execution (render_execution.py) never touches this file. No DB -- a human
grades a few dozen executions, not thousands."""
import datetime, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"

def _path(task_id: str, run_id: str) -> pathlib.Path:
    return TASKS_DIR / task_id / "executions" / run_id / "grade.json"

def get(task_id: str, run_id: str) -> dict | None:
    p = _path(task_id, run_id)
    return json.loads(p.read_text()) if p.exists() else None

def put(task_id: str, run_id: str, score, note: str) -> dict:
    if score is not None:
        score = int(score)
        if not (0 <= score <= 10):
            raise ValueError(f"score must be 0-10 or null, got {score}")
    record = dict(task_id=task_id, run_id=run_id, score=score, note=note or "",
                  updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    p = _path(task_id, run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, indent=2) + "\n")
    return record

def all_grades() -> dict:
    """{"<task_id>/<run_id>": record, ...} for every graded execution."""
    out = {}
    for f in TASKS_DIR.glob("*/executions/*/grade.json"):
        r = json.loads(f.read_text())
        out[f"{r['task_id']}/{r['run_id']}"] = r
    return out
