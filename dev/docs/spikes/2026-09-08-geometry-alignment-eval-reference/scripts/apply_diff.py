"""Apply one aspect/full diff JSON to its base trunk, producing a new project
dir. The single place a diff turns into an actual trunk -- used both to
render the reference picture and, later, to build grading fixtures.

Base trunks (unatco_gt, and this level's other extracted project copies) are
job-scratch, not committed -- set BASE_TRUNKS_DIR to wherever your own copy
of the UNATCO project extraction lives. See ../README.md.
"""
import json, os, shutil, subprocess, sys, pathlib

REPO = pathlib.Path(__file__).resolve().parents[5]
WT = str(REPO)
PY = str(REPO / ".venv" / "bin" / "python")
BASE_TRUNKS_DIR = pathlib.Path(os.environ.get("BASE_TRUNKS_DIR", "/home/agent/.claude/jobs/92851c21/tmp"))

def apply_diff(diff_path: pathlib.Path, out_dir: pathlib.Path) -> None:
    d = json.loads(diff_path.read_text())
    src = BASE_TRUNKS_DIR / d["base_trunk"]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(src, out_dir)
    env = {**os.environ, "UEDCLI_PROJECT": str(out_dir), "UEDCLI_LEVEL": "unatco"}
    for op in d["ops"]:
        if op["kind"] == "brush_vertex_move":
            args = [PY, "-m", "uedcli", "brush", "vertex", "move", op["actor"]]
            for corner in op["at"]:
                args += ["--at", ",".join(str(c) for c in corner)]
            args += ["--by", ",".join(str(c) for c in op["by"])]
            subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
        elif op["kind"] == "actor_move":
            args = [PY, "-m", "uedcli", "actor", "move", *op["actors"], "--by", ",".join(str(c) for c in op["by"])]
            subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
        elif op["kind"] == "assert_unchanged":
            pass  # nothing to apply; checked at grading time against a subagent's trunk
        else:
            raise ValueError(f"unknown op kind: {op['kind']}")

if __name__ == "__main__":
    apply_diff(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
    print("applied", sys.argv[1], "->", sys.argv[2])
