"""Persistence for manual grades: one JSON file per execution
(grades/<task_id>/<run_id>.json), so a grade survives a page reload and
stays editable at any time. No DB -- a human grades a few dozen executions,
not thousands."""
import datetime, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
GRADES = ROOT / "grades"

def _path(task_id: str, run_id: str) -> pathlib.Path:
    return GRADES / task_id / f"{run_id}.json"

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
    if not GRADES.exists():
        return out
    for task_dir in GRADES.iterdir():
        if not task_dir.is_dir():
            continue
        for f in task_dir.glob("*.json"):
            r = json.loads(f.read_text())
            out[f"{r['task_id']}/{r['run_id']}"] = r
    return out
