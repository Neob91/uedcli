"""Render every scenario's reference picture from its task's gold trunk,
highlighting just that scenario's member actors. A picture always reflects
the fully-correct scene (never a partially-applied one)."""
import os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from spec import TASKS
from build_gold import WT, PY
from compass import add_compass

ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference")
OUT_IMG = ROOT / "img"
GOLD_CACHE = pathlib.Path(os.environ.get("DIFF_TRUNK_CACHE", "/home/agent/.claude/jobs/92851c21/tmp/diff_trunks2"))
FRAME = "59,-360,200,620,140,500"
NAMES_FILE = pathlib.Path(os.environ.get("ALL_ACTOR_NAMES_FILE", "/home/agent/.claude/jobs/92851c21/tmp/allnames.txt"))

def render_scenario(task_id: str, scen_id: str, scen: dict):
    trunk = GOLD_CACHE / task_id
    names = NAMES_FILE.read_text().split()
    args = [PY, "-m", "uedcli", "actor", "diagram", *names,
            "--layout", "single", "--view", scen["view"], "--faces", "wire",
            "--brush-colors", "csg", "--frame", FRAME, "--size", "1000"]
    for actor in scen["members"]:
        args += ["--highlight", actor]
    args += ["--out", str(OUT_IMG / f"{scen_id}.png")]
    env = {**os.environ, "UEDCLI_PROJECT": str(trunk), "UEDCLI_LEVEL": "unatco"}
    subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
    if scen["view"] == "top":
        add_compass(OUT_IMG / f"{scen_id}.png")
    print("rendered", scen_id, f"({scen['view']} view, {len(scen['members'])} actors)")

if __name__ == "__main__":
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    for task_id, spec in TASKS.items():
        for scen_id, scen in spec["scenarios"].items():
            render_scenario(task_id, scen_id, scen)
