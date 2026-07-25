#!/usr/bin/env python3
r"""Does UnrealEd's `[Core.System] Paths` accept a MIDDLE-DIRECTORY wildcard, so the
asset-wiring cutover can craft a FEW `Paths` lines over `/resources/*` instead of one
per (mounted dir x extension)? Andrzej: "prefer the simplification, but verify it."

Each variant boots a FRESH ephemeral editor with a custom `unrealtournament.ini`
bind-mounted over the baked one BEFORE wine launches (the correct mechanism per the
spec review — a post-launch `sed` is clobbered when the GUI editor rewrites its ini).
The only way the test package can resolve is the injected Paths line: the real package
`LUM_CoreTex.utx` is mounted at `/resources/A/` and NOWHERE else, and the baked content
Paths (`../Textures/*.utx` → /opt/Textures) resolve nothing (that dir doesn't exist).
Then `OBJ LOAD PACKAGE=LUM_CoreTex` (name only, NO FILE=) forces a Paths search; the
log shows whether it resolved.

Variants:
  V1  Paths=/resources/*/*.utx    middle-dir `*` + explicit ext   (the simplification)
  V2  Paths=/resources/*/*.*      middle-dir `*` + any ext         (max simplification)
  V3  Paths=/resources/A/*.utx    no middle `*` (per-dir)          (KNOWN-GOOD control)
  V4  (no injected line)          baked only                       (NEGATIVE control → must FAIL)

Run on the HOST from Tools/uedctl:  PYTHONPATH=. python3 .../probe.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from uedctl import editor
from uedctl.driver import Driver

TEX = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures/LUM_CoreTex.utx"
SCRATCH = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/paths-wildcard")
BAKED_INI = Path(__file__).resolve().parents[4] / "uned" / "UED22" / "unrealtournament.ini"
# ^ Tools/uedctl/uned/UED22/unrealtournament.ini (probe is at Tools/uedctl/dev/docs/spikes/<slug>/)


def log(*a):
    print(*a, flush=True)


def make_ini(inject_line: str | None) -> Path:
    """Baked ini with `inject_line` added right after the [Core.System] header, EXACT BYTES preserved.
    Must be binary: read_text/write_text apply universal-newlines and turn the ini's CRLF into LF,
    which wine's ini parser (CRLF-sensitive) GPFs on at boot — the bug that made the first run's V1-V3
    all time out on readiness."""
    data = BAKED_INI.read_bytes()
    if inject_line is not None:
        marker = b"[Core.System]"
        i = data.index(marker) + len(marker)
        eol = b"\r\n" if data[i:i + 2] == b"\r\n" else b"\n"
        j = i + len(eol)
        data = data[:j] + inject_line.encode() + eol + data[j:]
    out = SCRATCH / f"ini_{uuid.uuid4().hex}.ini"
    out.write_bytes(data)
    return out


def run_variant(tag: str, inject_line: str | None) -> str:
    ed_id = f"pw{uuid.uuid4().hex[:10]}"
    container = editor.editor_container(ed_id)
    ini = make_ini(inject_line)
    res_dir = SCRATCH / "resources"
    log(f"\n===== {tag}: Paths line = {inject_line!r} =====")
    try:
        subprocess.run(
            ["docker", "compose", "run", "-d", "-p", "0:6080", "--name", container,
             # Simulate the POST-cutover state: the entrypoint's `sed -i` on unrealtournament.ini
             # (the /deusex Paths block) rename-over FAILS on our single-file bind mount and kills
             # boot; point its deusex dir at nothing so that block is skipped (the real build deletes
             # it, spec §7). This is itself a build finding: unrealtournament.ini can't be
             # bind-mounted while anything sed-edits it.
             "-e", "UED_DEUSEX_ASSETS_DIR=/nonexistent-so-entrypoint-skips-its-ini-sed",
             "-v", f"{editor._wineprefix_volume(ed_id)}:/wineprefix",
             "-v", f"{ini}:/opt/UED22/unrealtournament.ini",
             "-v", f"{res_dir}:/resources:ro", "uned"],
            cwd=editor._compose_dir(), capture_output=True, text=True, check=True)
        editor._wait_ready(container, 120.0)
        ed = Driver(container=container)
        # confirm the injected Paths line actually reached the running config
        grep = subprocess.run(["docker", "exec", container, "grep", "-c", "resources",
                               "/opt/UED22/unrealtournament.ini"], capture_output=True, text=True)
        log(f"  ini has {grep.stdout.strip()} /resources Paths line(s)")
        off = ed.log_size()
        ed.exec("OBJ LOAD PACKAGE=LUM_CoreTex")     # name only -> forces a [Core.System] Paths search
        time.sleep(2.0)
        ed.exec("OBJ LIST CLASS=Texture")           # flush + enumerate loaded textures
        time.sleep(2.0)
        tail = ed.read_log_since(off)
        cant = ("Can't find" in tail) or ("Failed to load" in tail) or ("Error loading" in tail)
        # DEFINITIVE positive: a KNOWN LUM_CoreTex texture object (grey_stone_tile) shows up in the
        # loaded-texture enumeration -> the package resolved via this Paths line. (The package NAME
        # alone isn't reliably printed; a concrete object name is.)
        loaded = "grey_stone_tile" in tail
        verdict = "RESOLVED" if loaded else ("FAILED(cant-find)" if cant else "NOT-RESOLVED(silent)")
        log(f"  cant_find={cant}  saw_grey_stone_tile={loaded}  -> {verdict}")
        for l in tail.splitlines():
            if any(k in l for k in ("grey_stone_tile", "LUM_CoreTex", "Can't find", "Failed", "Bind")):
                log("   |", l.strip()[:160])
        return f"{tag}: {verdict}"
    except Exception as e:
        log(f"  ERROR: {e}")
        return f"{tag}: ERROR {e}"
    finally:
        editor.stop_editor(ed_id)
        ini.unlink(missing_ok=True)


def main():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    (SCRATCH / "resources" / "A").mkdir(parents=True)
    shutil.copy2(TEX, SCRATCH / "resources" / "A" / "LUM_CoreTex.utx")
    # a junk non-package file to see if */*.* chokes on it
    (SCRATCH / "resources" / "A" / "README.txt").write_text("not a package\n")
    # Decisive minimal set (fast): wildcard vs a per-dir POSITIVE control vs a no-path NEGATIVE
    # control. If V1 RESOLVES and V4 does NOT, the middle-dir wildcard works. V3 confirms the harness
    # detects a known-good resolution. (V2 `*/*.*` is a bonus, tested only if V1 works.)
    results = [
        run_variant("V4neg_baked",  None),                       # negative control: must NOT resolve
        run_variant("V3pos_perdir", "Paths=/resources/A/*.utx"), # positive control: must resolve
        run_variant("V1_star_ext",  "Paths=/resources/*/*.utx"), # THE question
    ]
    log("\n===== SUMMARY =====")
    for r in results:
        log("  " + r)


if __name__ == "__main__":
    sys.exit(main())
