"""Build the gold (fully-correct) trunk for a task from spec.py: apply each
anchor's own op, then move every dependent by its ANCHOR's task_delta (since
in the gold trunk the anchor's actual delta IS the task delta). Unchanged
actors get no operation -- they stay exactly as the baseline left them.
"""
import os, shutil, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from spec import TASKS

WT = "/workspace/uedcli/.claude/worktrees/geom-eval"
PY = "/workspace/uedcli/.venv/bin/python"
BASE_TRUNKS_DIR = pathlib.Path(os.environ.get("BASE_TRUNKS_DIR", "/home/agent/.claude/jobs/92851c21/tmp"))

def build_gold(task_id: str, out_dir: pathlib.Path):
    spec = TASKS[task_id]
    src = BASE_TRUNKS_DIR / spec["base_trunk"]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(src, out_dir)
    env = {**os.environ, "UEDCLI_PROJECT": str(out_dir), "UEDCLI_LEVEL": "unatco"}

    anchor_delta = {}
    for a in spec["anchors"]:
        args = [PY, "-m", "uedcli", "brush", "vertex", "move", a["actor"]]
        for corner in a["at"]:
            args += ["--at", ",".join(str(c) for c in corner)]
        args += ["--by", ",".join(str(c) for c in a["task_delta"])]
        subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
        anchor_delta[a["actor"]] = a["task_delta"]

    # group dependents by their actual delta (== their anchor's task_delta) to move in batches
    by_delta = {}
    for actor, anchor in spec["dependents"]:
        d = tuple(anchor_delta[anchor])
        by_delta.setdefault(d, []).append(actor)
    for delta, actors in by_delta.items():
        args = [PY, "-m", "uedcli", "actor", "move", *actors, "--by", ",".join(str(c) for c in delta)]
        subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
    # unchanged actors: nothing to do

if __name__ == "__main__":
    task_id = sys.argv[1]
    out_dir = pathlib.Path(sys.argv[2])
    build_gold(task_id, out_dir)
    print("built gold trunk for", task_id, "->", out_dir)
