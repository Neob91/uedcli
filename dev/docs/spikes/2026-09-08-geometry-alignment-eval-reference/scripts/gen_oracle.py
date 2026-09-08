"""Write the flat, per-task, machine-checkable oracle straight from spec.py
-- no diff-text parsing. This is what a grading script consumes: for each
actor, either an absolute task_delta (anchors) to check directly, an
anchor-relative expectation (dependents: must match THAT anchor's actual
delta in the trunk being graded) or an unchanged assertion.
"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from spec import TASKS

OUT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference/oracle")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for task_id, spec in TASKS.items():
        oracle = dict(
            task=task_id,
            base_trunk=spec["base_trunk"],
            anchors=[dict(actor=a["actor"], task_delta=a["task_delta"], at=a["at"]) for a in spec["anchors"]],
            dependents=[dict(actor=actor, anchor=anchor) for actor, anchor in spec["dependents"]],
            unchanged=list(spec["unchanged"]),
        )
        (OUT / f"{task_id}.json").write_text(json.dumps(oracle, indent=2) + "\n")
        print("wrote", f"{task_id}.json", "->",
              len(oracle["anchors"]), "anchors,", len(oracle["dependents"]), "dependents,",
              len(oracle["unchanged"]), "unchanged")
