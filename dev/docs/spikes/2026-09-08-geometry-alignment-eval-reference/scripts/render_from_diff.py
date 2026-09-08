"""Render every aspect diff's reference picture. The single automated path
from diff JSON -> applied trunk -> PNG: rendering always applies the FULL
task diff (every aspect's ops combined) to the untouched baseline first,
then highlights just one aspect's actors -- so a picture can never drift out
of sync with the trunk it claims to show. Run after editing any diff JSON.
"""
import json, os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from apply_diff import apply_diff, WT, PY, BASE_TRUNKS_DIR
from compass import add_compass

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIFFS = ROOT / "diffs"
OUT_IMG = ROOT / "img"
TRUNK_CACHE = pathlib.Path(os.environ.get("DIFF_TRUNK_CACHE", "/home/agent/.claude/jobs/92851c21/tmp/diff_trunks"))
FRAME = "59,-360,200,620,140,500"
NAMES_FILE = pathlib.Path(os.environ.get("ALL_ACTOR_NAMES_FILE", "/home/agent/.claude/jobs/92851c21/tmp/allnames.txt"))

def ensure_trunk(diff_id: str) -> pathlib.Path:
    out = TRUNK_CACHE / diff_id
    if not out.exists():
        apply_diff(DIFFS / f"{diff_id}.json", out)
    return out

def render_aspect(diff_id: str):
    d = json.loads((DIFFS / f"{diff_id}.json").read_text())
    trunk = ensure_trunk(d["render_from"])
    names = NAMES_FILE.read_text().split()
    args = [PY, "-m", "uedcli", "actor", "diagram", *names,
            "--layout", "single", "--view", d["view"], "--faces", "wire",
            "--brush-colors", "csg", "--frame", FRAME, "--size", "1000"]
    for actor in d["highlight"]:
        args += ["--highlight", actor]
    args += ["--out", str(OUT_IMG / f"{diff_id}.png")]
    env = {**os.environ, "UEDCLI_PROJECT": str(trunk), "UEDCLI_LEVEL": "unatco"}
    subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
    if d["view"] == "top":
        add_compass(OUT_IMG / f"{diff_id}.png")
    print("rendered", diff_id, f"(from {d['render_from']}, {d['view']} view, {len(d['highlight'])} actors)")

if __name__ == "__main__":
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    for p in sorted(DIFFS.glob("*.json")):
        if p.stem.endswith("_full"):
            continue
        render_aspect(p.stem)
