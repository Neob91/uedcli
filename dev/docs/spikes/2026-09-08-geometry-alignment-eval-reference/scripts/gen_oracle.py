"""Write the flat, per-task, machine-checkable oracle straight from spec.py
-- no diff-text parsing. Each task's `entries` list (kind: anchor/update/
create/delete) IS the oracle; this just adds base_trunk and writes it out.
"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from spec import TASKS

OUT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference/oracle")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for task_id, spec in TASKS.items():
        oracle = dict(task=task_id, base_trunk=spec["base_trunk"], entries=spec["entries"])
        (OUT / f"{task_id}.json").write_text(json.dumps(oracle, indent=2) + "\n")
        by_kind = {}
        for e in spec["entries"]:
            by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        print("wrote", f"{task_id}.json", "->", ", ".join(f"{v} {k}" for k, v in by_kind.items()))
