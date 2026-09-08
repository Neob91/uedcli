"""Render every scenario's reference picture from its task's gold trunk,
highlighting just that scenario's member actors, into img/<task_id>/<scenario_id>.png.
A picture always reflects the fully-correct scene (never a partially-applied
one). `render_scenario` takes an explicit `trunk` so eval_trial.py can reuse
it unchanged to render a TRIAL's subject trunk the same way -- one rendering
path for both the reference and every graded run.
"""
import os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from build_gold import WT, PY, BASE_TRUNKS_DIR
from compass import add_compass

ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference")
OUT_IMG = ROOT / "img"
GOLD_CACHE = pathlib.Path(os.environ.get("DIFF_TRUNK_CACHE", "/home/agent/.claude/jobs/92851c21/tmp/diff_trunks2"))

def names_file_for(level: str) -> pathlib.Path:
    return BASE_TRUNKS_DIR / f"{level}_allnames.txt"

def render_scenario(trunk: pathlib.Path, level: str, frame: str, scen_id: str, scen: dict, out_dir: pathlib.Path):
    names = names_file_for(level).read_text().split()
    out_path = out_dir / f"{scen_id}.png"
    args = [PY, "-m", "uedcli", "actor", "diagram", *names,
            "--layout", "single", "--view", scen["view"], "--faces", "wire",
            "--brush-colors", "csg", "--frame", frame, "--size", "1000"]
    for actor in scen["members"]:
        args += ["--highlight", actor]
    args += ["--out", str(out_path)]
    env = {**os.environ, "UEDCLI_PROJECT": str(trunk), "UEDCLI_LEVEL": "unatco"}
    subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
    if scen["view"] == "top":
        add_compass(out_path)
    print("rendered", scen_id, f"({scen['view']} view, {len(scen['members'])} actors)", "from", trunk)

if __name__ == "__main__":
    for task_id, task in TASKS.items():
        out_dir = OUT_IMG / task_id
        out_dir.mkdir(parents=True, exist_ok=True)
        trunk = GOLD_CACHE / task_id
        for scen_id, scen in task["scenarios"].items():
            render_scenario(trunk, task["level"], task["frame"], scen_id, scen, out_dir)
