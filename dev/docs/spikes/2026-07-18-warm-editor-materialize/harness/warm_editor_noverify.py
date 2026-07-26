#!/usr/bin/env python3
"""SP-E decisive test — is the H3-verify UCC batchexport the reused-build disruptor?

v2 (`warm_editor_diag.py`) found reused builds fail intermittently because MAP SAVE silently
produces NO /work/*.dx file (UCC: "Can't find file"), and the failures ALTERNATE with successes —
exactly what you'd expect if the UCC.exe batchexport that runs (as a 2nd wine process in the warm
editor's own container/WINEPREFIX) on a SUCCESSFUL build corrupts the GUI editor's ability to drive
the NEXT build.

This isolates it: two phases in ONE warm editor.
  A. NO-VERIFY  — N builds with no_verify=True (skips the UCC batchexport entirely). MAP SAVE still
                  runs + swaps, so a silently-missing save still fails loudly. If ALL succeed →
                  the UCC batchexport was the disruptor.
  B. SEPARATE-VERIFY — N builds where the H3 verify export runs in a FRESH EPHEMERAL editor
                  container (the isolation fix: docker cp the saved .dx there + export), leaving the
                  warm editor untouched by any 2nd wine process. If ALL succeed → the fix works.

Run: cd Tools/uedcli && .venv/bin/python dev/docs/spikes/2026-07-18-warm-editor-materialize/harness/warm_editor_noverify.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

TOOL = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(TOOL))

from uedcli import apply, config, trunk               # noqa: E402
from uedcli import editor as editor_mod               # noqa: E402
from uedcli import store_export                       # noqa: E402
from uedcli.driver import Driver                      # noqa: E402
from uedcli.container_assets import resource_mounts   # noqa: E402
from uedcli.packages import search_path_package_names  # noqa: E402
from uedcli.uuid7 import uuid7                          # noqa: E402

CASTLE_DIR = TOOL / "_scratch/castle/uedcli"
OUT_DIR = Path(os.environ.get("OUT_DIR", str(TOOL / "_scratch/warm-spike")))
OUT_DIR.mkdir(parents=True, exist_ok=True)
RES = OUT_DIR / "warm_noverify_results.json"
N = int(os.environ.get("NV_N", "4"))
R: dict = {"no_verify": [], "separate_verify": [], "notes": []}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def save():
    RES.write_text(json.dumps(R, indent=2))


def load_castle():
    project = config.load_project(str(CASTLE_DIR))
    uc = config.load_user_config()
    return dict(
        level=trunk.read_level(Path(config.project_maps_dir(project)) / "foobar")[0],
        packages=search_path_package_names(config.composed_search_files(project, uc)),
        search_dirs=config.composed_search_dirs(project, uc),
        state_dir=config.state_dir(project.root, create=True))


def build(ctx, out_path, tag, *, no_verify) -> dict:
    t0 = time.monotonic()
    res = apply.run_materialize(
        level=ctx["level"], packages=ctx["packages"], search_dirs=ctx["search_dirs"],
        out_path=str(out_path), overwrite=True, state_dir=ctx["state_dir"], no_verify=no_verify)
    dt = round(time.monotonic() - t0, 1)
    rec = {"tag": tag, "rc": res.rc, "seconds": dt,
           "artifact_bytes": out_path.stat().st_size if out_path.exists() else None,
           "msg": res.message[:150]}
    log(f"  {tag}: rc={res.rc} {dt}s bytes={rec['artifact_bytes']} :: {res.message[:70]}")
    return rec


def main():
    ctx = load_castle()
    mounts = resource_mounts(ctx["search_dirs"])
    warm_id = uuid7()
    log("booting warm editor…")
    container = editor_mod.ensure_editor(warm_id, mounts=mounts, state_dir=ctx["state_dir"])
    apply.ensure_editor = lambda _i, **_k: container
    apply.stop_editor = lambda *_a, **_k: None
    try:
        log(f"Phase A NO-VERIFY — {N} builds (no UCC batchexport in the warm container)")
        for i in range(1, N + 1):
            R["no_verify"].append(build(ctx, OUT_DIR / f"nv{i}.dx", f"noverify-{i}", no_verify=True))
            save()

        # Phase B: verify, but route the UCC export to a SEPARATE ephemeral container so no 2nd
        # wine process ever runs in the warm editor's prefix. Patch store_export.export_dx_t3d used
        # by the H3 verify to: boot (once) a throwaway editor, docker cp the warm /work dx into it,
        # export there. This mimics the isolation fix without touching the warm editor.
        log("Phase B booting a SEPARATE verify container…")
        verify_id = uuid7()
        verify_container = editor_mod.ensure_editor(verify_id, mounts=mounts, state_dir=ctx["state_dir"])
        orig_export = store_export.export_dx_t3d

        def _isolated_export(warm_cont, dx_path):
            # dx_path is a /work path inside the WARM container; move it to the verify container.
            tmp_host = OUT_DIR / f"_verify_{uuid7().split('-')[0]}.dx"
            subprocess.run(["docker", "cp", f"{warm_cont}:{dx_path}", str(tmp_host)],
                           capture_output=True, text=True, check=True)
            subprocess.run(["docker", "cp", str(tmp_host), f"{verify_container}:{dx_path}"],
                           capture_output=True, text=True, check=True)
            tmp_host.unlink(missing_ok=True)
            return orig_export(verify_container, dx_path)

        store_export.export_dx_t3d = _isolated_export
        try:
            log(f"Phase B SEPARATE-VERIFY — {N} builds (UCC runs in the verify container only)")
            for i in range(1, N + 1):
                R["separate_verify"].append(
                    build(ctx, OUT_DIR / f"sv{i}.dx", f"sepverify-{i}", no_verify=False))
                save()
        finally:
            store_export.export_dx_t3d = orig_export
            editor_mod.stop_editor(verify_id, ctx["state_dir"])
    finally:
        log("teardown warm editor…")
        editor_mod.stop_editor(warm_id, ctx["state_dir"])

    def rate(p):
        return f"{sum(1 for r in R[p] if r['rc'] != 0)}/{len(R[p])} failed"
    R["summary"] = {"no_verify": rate("no_verify"), "separate_verify": rate("separate_verify")}
    save()
    log(f"SUMMARY: {R['summary']}")
    print(json.dumps(R, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
