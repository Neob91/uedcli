"""Render a task's 8x45deg `level photo --native` tour from ANY trunk (the
gold reference, or a trial's subject trunk) -- one `photo_camera` definition
per task (specs/<id>.py) feeds both, so a trial's photos are directly
comparable to the reference's."""
import os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from build_gold import WT, PY

YAWS = [0, 8192, 16384, 24576, 32768, 40960, 49152, 57344]  # 8x45deg

def render_photos(task: dict, trunk: pathlib.Path, out_dir: pathlib.Path, prefix: str = "pan"):
    """Writes out_dir/<prefix>_<i>.png for i in 0..7, from `trunk`'s
    task["level"]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cam = task["photo_camera"]
    x, y, z = cam["at"]
    pitch = cam.get("pitch", 0)
    shots = [f"at:{x},{y},{z};rot:{pitch},{yaw};name:{prefix}_{i}" for i, yaw in enumerate(YAWS)]
    env = {**os.environ, "UEDCLI_PROJECT": str(trunk), "UEDCLI_LEVEL": task["level"]}
    args = [PY, "-m", "uedcli", "level", "photo", "--native", "--faces", "textured",
            "--size", "512x384", *shots, "--out-dir", str(out_dir)]
    subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
    print("rendered", f"{prefix}_0..{len(YAWS)-1}", "->", out_dir)
