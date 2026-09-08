"""For every scenario in spec.py: dump each member actor's normalized state
(brush vertex list for brushes, effective Location for point actors) from
the baseline and the gold trunk, and write a REAL unified diff (diff -u) --
this is the human-readable artifact on the reference page. No custom JSON
ops vocabulary; if a subagent's trunk is dumped the same way, this is
directly comparable the same way any two revisions are.
"""
import difflib, os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from spec import TASKS
from build_gold import WT, PY, BASE_TRUNKS_DIR

ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference")
DIFFS = ROOT / "diffs"
GOLD_CACHE = pathlib.Path(os.environ.get("DIFF_TRUNK_CACHE", "/home/agent/.claude/jobs/92851c21/tmp/diff_trunks2"))

def dump_members(project: pathlib.Path, members: list[str]) -> str:
    """`brush vertex list` exits 0 even on a point actor (just "0 vertices"),
    so detect brush-ness by whether its own output reports any."""
    env = {**os.environ, "UEDCLI_PROJECT": str(project), "UEDCLI_LEVEL": "unatco"}
    lines = []
    for name in members:
        r = subprocess.run([PY, "-m", "uedcli", "brush", "vertex", "list", name],
                            cwd=WT, env=env, capture_output=True, text=True, check=True)
        if not r.stdout.startswith(f"{name}: 0 vertices"):
            lines.append(r.stdout)
        else:
            r = subprocess.run([PY, "-m", "uedcli", "actor", "prop", "get", name, "Location"],
                                cwd=WT, env=env, capture_output=True, text=True, check=True)
            lines.append(f"{name}: {r.stdout.strip()}\n")
    return "\n".join(lines)

def gen_task_diffs(task_id: str):
    spec = TASKS[task_id]
    baseline = BASE_TRUNKS_DIR / spec["base_trunk"]
    gold = GOLD_CACHE / task_id
    for scen_id, scen in spec["scenarios"].items():
        before = dump_members(baseline, scen["members"])
        after = dump_members(gold, scen["members"])
        diff_lines = list(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"before/{scen_id}", tofile=f"after/{scen_id}"))
        (DIFFS / f"{scen_id}.diff").write_text("".join(diff_lines))
        print("wrote", f"{scen_id}.diff", f"({len(diff_lines)} lines)")

if __name__ == "__main__":
    DIFFS.mkdir(parents=True, exist_ok=True)
    for task_id in TASKS:
        gen_task_diffs(task_id)
