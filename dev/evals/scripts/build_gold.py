"""Build the gold (fully-correct) trunk for a task from its specs/<id>.py:
apply every `update(target="corners")` entry's own op, then move every
`anchor` entry by its target anchor's task delta (since in the gold trunk
the anchor's actual delta IS the task delta). `update(target="unchanged")`
entries get no operation -- they stay exactly as the baseline left them.
"""
import os, shutil, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS

WT = str(pathlib.Path(__file__).resolve().parents[4])  # the uedcli checkout -- cwd uedcli needs for `-m uedcli` module resolution
# The main checkout's venv specifically, not WT's -- a worktree's own .venv/ (if it has one at all)
# has no uedcli_native built; only /workspace/uedcli/.venv does.
PY = "/workspace/uedcli/.venv/bin/python"
if "BASE_TRUNKS_DIR" not in os.environ:
    sys.exit("BASE_TRUNKS_DIR not set -- point it at wherever your base trunk extractions live "
             "(see README.md's \"Base trunks\" section); no default, DX content isn't ours to assume a path for")
BASE_TRUNKS_DIR = pathlib.Path(os.environ["BASE_TRUNKS_DIR"])

def build_gold(task_id: str, out_dir: pathlib.Path):
    spec = TASKS[task_id]
    src = BASE_TRUNKS_DIR / spec["base_trunk"]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(src, out_dir)
    env = {**os.environ, "UEDCLI_PROJECT": str(out_dir), "UEDCLI_LEVEL": spec["level"]}

    anchor_delta = {}
    for e in spec["entries"]:
        if e["kind"] != "update" or e.get("target") != "corners":
            continue
        args = [PY, "-m", "uedcli", "brush", "vertex", "move", e["actor"]]
        for corner in e["at"]:
            args += ["--at", ",".join(str(c) for c in corner)]
        args += ["--by", ",".join(str(c) for c in e["delta"])]
        subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
        anchor_delta[e["actor"]] = e["delta"]

    # group `anchor` entries by their actual delta (== their target's task delta) to move in batches
    by_delta = {}
    for e in spec["entries"]:
        if e["kind"] != "anchor":
            continue
        d = tuple(anchor_delta[e["to"]])
        by_delta.setdefault(d, []).append(e["actor"])
    for delta, actors in by_delta.items():
        args = [PY, "-m", "uedcli", "actor", "move", *actors, "--by", ",".join(str(c) for c in delta)]
        subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
    # update(target="unchanged") entries: nothing to do

if __name__ == "__main__":
    task_id = sys.argv[1]
    out_dir = pathlib.Path(sys.argv[2])
    build_gold(task_id, out_dir)
    print("built gold trunk for", task_id, "->", out_dir)
