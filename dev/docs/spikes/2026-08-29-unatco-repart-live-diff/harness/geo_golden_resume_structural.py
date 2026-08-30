"""Structural-only (non-PF_Semisolid) smuggler golden via resume-capable chunked EDIT PASTE.

Adapted from `_scratch/geo_golden_resume.py` (the same resume-capable driver that built
`_scratch/geo-confirm-smuggler/golden_smuggler_resume.dx`, the full-level golden `breadth_gate.py`
uses) for the PASS-A-only structural trunk under `_scratch/smuggler-structural-only/` — built by
`smuggler_filter_trunk.py`, which drops smuggler's 79 `PF_Semisolid` (Pass-2 "detail") brushes.
Used by `smuggler-4-surf-delta-traced-to-4-pf-semisolid` to confirm PASS-A alone is node/surf/
leaf-EXACT for smuggler (unlike freeclinic08's already-diverged structural tree), isolating the
level's `+4` surf residual to PASS-2 (semisolid) processing specifically.

EDIT PASTE of a several-hundred-brush set GPFs a real wine/FUnrealEd 'Critical Error' dialog, in
bursts (verified: window-list capture shows the dialog). A single paste never survives reliably, so
pastes run in chunks; on a chunk crash the whole editor is lost, so this driver re-boots and
re-pastes the prefix up to the next target chunk, keeping monotonic progress in a state file. The
last boot that pastes every chunk follows through with MAP REBUILD + MAP SAVE and copies the golden
out.

Chunk budget per target: 3 crash-clamped attempts, pacing 90s between attempts. On exceeding the
budget it reports UNVERIFIED with the stuck chunk and exits 2.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness"))

import build_ued_golden as bg  # noqa: E402
from uedcli import config, trunk, writes, xfer  # noqa: E402
from uedcli.driver import Driver, DriverError  # noqa: E402
from uedcli.editor import ensure_editor, stop_editor  # noqa: E402
from uedcli.uuid7 import uuid7  # noqa: E402
from geo_golden_driver import _wait_idle  # noqa: E402

SLUG = "smuggler"
TRUNK = ROOT / "_scratch/smuggler-structural-only/maps/smuggler"
HOST_OUT = ROOT / "_scratch/smuggler-structural-only/golden_smuggler_structural_resume.dx"
STATE_FILE = ROOT / "_scratch/smuggler-structural-only/.golden_resume_structural.json"
CHUNK = int(os.environ.get("GOLDEN_CHUNK", "16"))
BUDGET = 3
PACE = 90

user_config = config.load_user_config()
project = bg._scratch_project(TRUNK, "deusex")
search_dirs = config.composed_search_dirs(project, user_config)
mounts = bg.resource_mounts(search_dirs)
state_dir = config.state_dir(project.root, create=True)

lvl, _ = trunk.read_level(TRUNK)
order = [n for n in lvl.order
         if bg._short_class(lvl.actors[n].cls) in ("Brush", "LevelInfo")]
classes = {n: lvl.actors[n].cls for n in order}
has_brush = {n: lvl.actors[n].brush is not None for n in order}
imp = bg.levelinfo_first_order(order, classes, has_brush)
brushes = [lvl.actors[n] for n in imp if has_brush[n]]
points = [lvl.actors[n] for n in imp
          if not has_brush[n] and lvl.actors[n].cls != "Brush"]
chunks = [brushes[i:i + CHUNK] for i in range(0, len(brushes), CHUNK)]
NOPS = len(chunks)


def _load_state():
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text())
    return {"best": -1, "caps": {}}  # best = fully pasted chunk index


def _save_state(s) -> None:
    STATE_FILE.write_text(json.dumps(s))


def _chunk_t3d(chunk, driver):
    return writes.emit_map([writes._shift_for_paste(a) for a in chunk])


def _capture(driver):
    print("  capturing crash evidence ...", flush=True)
    try:
        r = subprocess.run(
            ["docker", "exec", "-e", "DISPLAY=:99", driver.container, "bash", "-lc",
             "for w in $(xdotool search --onlyvisible '.' 2>/dev/null); do echo \"-- $w\"; "
             "xprop -id $w WM_NAME 2>/dev/null; done"],
            text=True, capture_output=True)
        print(r.stdout or r.stderr, flush=True)
    except Exception as e:
        print(f"  (winlist failed: {e})", flush=True)
    try:
        r = subprocess.run(
            ["docker", "exec", driver.container, "bash", "-lc",
             "find / -maxdepth 4 -name 'Unreal*.log' -o -name 'unreal*.log' 2>/dev/null | head"],
            text=True, capture_output=True)
        print("  log files:", r.stdout or r.stderr, flush=True)
        for p in (r.stdout.split() or []):
            rr = subprocess.run(["docker", "exec", driver.container, "bash", "-lc",
                                 f"tail -n 15 {p}"], text=True, capture_output=True)
            print(f"  === {p} tail ===", flush=True)
            print(rr.stdout[-1500:] or rr.stderr[-500:], flush=True)
    except Exception as e:
        print(f"  (log dump failed: {e})", flush=True)


def _boot_and_paste(s: dict, target: int):
    """Fresh boot; paste chunks 0..target. Returns ("ok", editor_top) | ("crash", stuck_chunk)."""
    ed_id = uuid7()
    container = None
    ed = None
    try:
        container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
        ed = Driver(container=container)
        print(f"  editor up: {container}", flush=True)
        ed.map_new()
        _wait_idle(container, label="map-new")
        ed.set_grid(1, 1, 1)
        if points:
            ed.map_importadd(writes._write_container_file(ed, writes.emit_map(points)))
        for ci in range(0, target + 1):
            print(f"    paste chunk {ci}/{target} ({len(chunks[ci])} brushes) ...", flush=True)
            ed.set_clipboard(_chunk_t3d(chunks[ci], ed))
            ed.edit_paste()
            print(f"      chunk {ci} pasted", flush=True)
        return "ok", ed, container, ed_id, state_dir
    except DriverError as e:
        print(f"  PASTE CRASH: {str(e)[:60]}", flush=True)
        _capture(ed)
        return "crash", None, container, ed_id, state_dir
    finally:
        pass  # teardown handled by caller along the success path


def _teardown(ed_id, state_dir, container):
    try:
        stop_editor(ed_id, state_dir)
    except Exception as e:
        print(f"  teardown note: {e}", flush=True)


def main() -> int:
    s = _load_state()
    print(f"resume drive: {NOPS} chunks of {CHUNK}; best={s['best']}, caps={s['caps']}", flush=True)
    target = s["best"] + 1
    while target < NOPS:
        if s["caps"].get(str(target), 0) >= BUDGET:
            print(f"UNVERIFIED: chunk {target} crashed {BUDGET}x; golden not built. "
                  f"state {STATE_FILE}", file=sys.stderr)
            return 2
        start = time.time()
        result = _boot_and_paste(s, target)
        kind, ed, container, ed_id, _sdir = result
        if kind == "crash":
            s["caps"][str(target)] = s["caps"].get(str(target), 0) + 1
            _save_state(s)
            print(f"  chunk {target} crashed (cap {s['caps'][str(target)]}/{BUDGET}); pacing",
                  flush=True)
            _teardown(ed_id, state_dir, container)
            time.sleep(PACE)
            continue
        if target == NOPS - 1:
            # All chunks pasted in THIS editor — rebuild and save it.
            print("  all chunks pasted — MAP REBUILD ...", flush=True)
            try:
                ed.exec("MAP REBUILD")
                _wait_idle(container, label="rebuild", timeout=2400, quiet_reads=10,
                           min_seconds=45)
            except Exception as e:
                print(f"  REBUILD CRASH: {str(e)[:80]}", flush=True)
                return 2
            work_out = xfer.work_path("dx")
            print("  MAP SAVE ...", flush=True)
            size = ed.map_save(work_out)
            HOST_OUT.parent.mkdir(parents=True, exist_ok=True)
            xfer.cp_out(container, work_out, str(HOST_OUT))
            _teardown(ed_id, state_dir, container)
            print(f"WROTE {HOST_OUT} ({size} bytes container-side, "
                  f"{HOST_OUT.stat().st_size} host-side)", flush=True)
            s["best"] = target
            _save_state(s)
            return 0
        # target pasted fully; record and keep going
        s["best"] = target
        _save_state(s)
        print(f"  chunk {target} done ({time.time() - start:.0f}s boot+paste)", flush=True)
        _teardown(ed_id, state_dir, container)
        target += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())