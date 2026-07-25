#!/usr/bin/env python3
"""SP-R follow-up: pin the map-name COLLISION threshold (R4-B F1 claimed a hard
63-char FName cap with SILENT truncation → stale-serve). The main spike found NO
collision at 70 chars differing past char 63, contradicting a 63 cap. This boots
ONE container and drives collision pairs (Entry vs DX, DIFFERENT content, differing
ONLY past char K) at growing lengths to find where — if anywhere — the second name
truncates onto the first and serves the resident (identical screenshot hash).
"""
import sys, time, hashlib, subprocess
from pathlib import Path

UEDCTL = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(UEDCTL))
from uedctl import config, preview_game as pg           # noqa: E402

MAPS = Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps")
OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/spike-reload")
POOL, MAPSDIR, SIZE = "/work/spikepool", "/work/dx/Maps", (640, 480)


def dexec(c, *a, timeout=60):
    return subprocess.run(["docker", "exec", c, *a], capture_output=True, text=True, timeout=timeout)


def inject(c, src: Path, stem: str):
    dexec(c, "mkdir", "-p", POOL)
    subprocess.run(["docker", "cp", str(src), f"{c}:{POOL}/{stem}.dx"],
                   capture_output=True, text=True, timeout=60, check=True)
    dexec(c, "ln", "-sf", f"{POOL}/{stem}.dx", f"{MAPSDIR}/{stem}.dx")


def pos(c):
    for ln in pg.link_cmd(c, "GetPlayerPosition"):
        if "Position " in ln:
            x, y, z = ln.split("Position ", 1)[1].split()[:3]
            return int(x), int(y), int(z)
    return None


def shot(c, row, name):
    p = pos(c)
    if p:
        pg.link_cmd(c, f"Screenshot {p[0]} {p[1]} {p[2]} 0 128")   # yaw 128: look aside, avoid dead-on wall
        time.sleep(1)
    try:
        pg.xgrab(c, row, OUT / name)
        return hashlib.sha256((OUT / name).read_bytes()).hexdigest()[:12]
    except Exception as e:
        return f"ERR:{e}"


def travel(c, stem):
    try:
        pg.travel_to(c, stem); return True
    except pg.GamePreviewError:
        return False


def main():
    m_entry, m_dx = MAPS / "Entry.dx", MAPS / "DX.dx"
    project = config.load_project(str(UEDCTL.parent.parent / "uedctl"))
    row = pg._substrate_row(project.game)
    c, _ = pg.start_game(project, config.load_user_config(), row, SIZE)
    print(f"READY container={c}", flush=True)
    try:
        # collision pairs differing ONLY past char 63, at total lengths L:
        for L in (80, 120, 180, 250):
            common = ("materialized__collideL%d__" % L)
            common = common + "z" * (63 - len(common))     # first 63 identical
            assert len(common) == 63, len(common)
            a = (common + "a" * (L - 63))[:L]
            b = (common + "b" * (L - 63))[:L]
            inject(c, m_entry, a); ra = travel(c, a); ha = shot(c, row, f"ext_a_{L}.png")
            inject(c, m_dx, b);    rb = travel(c, b); hb = shot(c, row, f"ext_b_{L}.png")
            collided = ha == hb and not ha.startswith("ERR")
            print(f"L={L}: a_loads={ra} b_loads={rb} hA={ha} hB={hb} COLLIDED={collided}",
                  flush=True)
        print("=== EXTEND COMPLETE ===", flush=True)
    finally:
        pg.stop_game(c)


if __name__ == "__main__":
    main()
