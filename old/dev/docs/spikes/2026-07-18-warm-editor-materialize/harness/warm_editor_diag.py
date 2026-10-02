#!/usr/bin/env python3
"""SP-E diagnostic v2 — nail the intermittent reused-build FAILURE mechanism + test the fix.

The v1 harness (`warm_editor_probe.py`) found that reused warm builds fail intermittently at the
H3 verify's `UCC.exe batchexport` step (builds 2,3,5 of 6 failed; 1,4,6 succeeded). This script
isolates WHY and whether the spec §4.3 mitigation (a defensive `dismiss_blocking_dialog()` before
each reused build) fixes it. One warm editor, three phases:

  A. BASELINE   — N builds, NO pre-build dismissal. Before each: snapshot `wmctrl -l` (is the GC
                  "Cleaning up…" xmessage dialog up?). On failure: capture the UCC batchexport
                  stderr AND the saved /work/*.dx size (bad save vs UCC-side failure).
  B. MITIGATED  — N builds, WITH `dismiss_blocking_dialog()` + a short settle before each build.
  C. CROSS-LEVEL (SP-E.2) — build the anchor trunk (disjoint UNATCO textures) after castle in the
                  same warm editor; check its build + residue.

Run: cd Tools/uedcli && .venv/bin/python dev/docs/spikes/2026-07-18-warm-editor-materialize/harness/warm_editor_diag.py
Env: DIAG_N (builds per phase, default 4).
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

from uedcli import apply, config, trunk           # noqa: E402
from uedcli import editor as editor_mod           # noqa: E402
from uedcli import store_export                   # noqa: E402
from uedcli.driver import Driver                  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.packages import search_path_package_names  # noqa: E402
from uedcli.uuid7 import uuid7                     # noqa: E402

CASTLE_DIR = TOOL / "_scratch/castle/uedcli"
ANCHOR_TRUNK = TOOL / "_scratch/anchor/uedcli/maps/anchor"
OUT_DIR = Path(os.environ.get("OUT_DIR", str(TOOL / "_scratch/warm-spike")))
OUT_DIR.mkdir(parents=True, exist_ok=True)
RES = OUT_DIR / "warm_diag_results.json"
N = int(os.environ.get("DIAG_N", "4"))

R: dict = {"baseline": [], "mitigated": [], "cross_level": [], "notes": []}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def save():
    RES.write_text(json.dumps(R, indent=2))


# Capture UCC batchexport failures with full stderr + the saved .dx size in-container.
_ORIG_EXPORT_T3D = store_export.export_dx_t3d
_LAST_EXPORT_FAIL: dict = {}


def _wrapped_export_t3d(container: str, dx_path: str) -> str:
    try:
        size = subprocess.run(["docker", "exec", container, "stat", "-c", "%s", dx_path],
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        size = "?"
    try:
        return _ORIG_EXPORT_T3D(container, dx_path)
    except subprocess.CalledProcessError as e:
        _LAST_EXPORT_FAIL.clear()
        _LAST_EXPORT_FAIL.update({
            "dx_path": dx_path, "dx_size": size,
            "returncode": e.returncode,
            "stderr_tail": (e.stderr or "")[-800:],
            "stdout_tail": (e.stdout or "")[-400:],
        })
        raise


store_export.export_dx_t3d = _wrapped_export_t3d


def load_castle():
    project = config.load_project(str(CASTLE_DIR))
    uc = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, uc)
    packages = search_path_package_names(config.composed_search_files(project, uc))
    level, _ = trunk.read_level(Path(config.project_maps_dir(project)) / "foobar")
    state_dir = config.state_dir(project.root, create=True)
    return dict(level=level, packages=packages, search_dirs=search_dirs, state_dir=state_dir,
                project=project, uc=uc)


def windows(probe: Driver) -> str:
    try:
        return probe.dexec_bash("DISPLAY=:99 wmctrl -l 2>&1 || true").strip()
    except Exception as e:
        return f"probe-error:{e}"


def has_gc_dialog(wlist: str) -> bool:
    return "xmessage" in wlist.lower()


def one_build(ctx, out_path, tag, probe, pre_dismiss: bool) -> dict:
    _LAST_EXPORT_FAIL.clear()
    win_before = windows(probe)
    dialog_before = has_gc_dialog(win_before)
    dismissed = None
    if pre_dismiss:
        dismissed = probe.dismiss_blocking_dialog()
        time.sleep(1.5)
    t0 = time.monotonic()
    res = apply.run_materialize(
        level=ctx["level"], packages=ctx["packages"], search_dirs=ctx["search_dirs"],
        out_path=str(out_path), overwrite=True, state_dir=ctx["state_dir"])
    dt = round(time.monotonic() - t0, 1)
    rec = {"tag": tag, "rc": res.rc, "seconds": dt,
           "dialog_up_before": dialog_before,
           "windows_before": win_before.replace("\n", " | ")[:300],
           "dismissed": dismissed,
           "fail_detail": dict(_LAST_EXPORT_FAIL) if res.rc != 0 else None,
           "msg": res.message[:160]}
    log(f"  {tag}: rc={res.rc} {dt}s dialog_before={dialog_before} dismissed={dismissed} "
        f"{'FAIL '+str(_LAST_EXPORT_FAIL.get('dx_size'))+'B/'+repr(_LAST_EXPORT_FAIL.get('stderr_tail','')[-90:]) if res.rc else 'ok'}")
    return rec


def main():
    ctx = load_castle()
    mounts = resource_mounts(ctx["search_dirs"])
    warm_id = uuid7()
    log("booting warm editor…")
    container = editor_mod.ensure_editor(warm_id, mounts=mounts, state_dir=ctx["state_dir"])
    probe = Driver(container=container)
    apply.ensure_editor = lambda _i, **_k: container
    apply.stop_editor = lambda *_a, **_k: None
    try:
        log(f"Phase A BASELINE — {N} builds, no pre-dismiss")
        for i in range(1, N + 1):
            R["baseline"].append(one_build(ctx, OUT_DIR / f"base{i}.dx", f"base-{i}", probe, False))
            save()
        log(f"Phase B MITIGATED — {N} builds, dismiss+settle before each")
        for i in range(1, N + 1):
            R["mitigated"].append(one_build(ctx, OUT_DIR / f"mit{i}.dx", f"mit-{i}", probe, True))
            save()
        # Phase C: cross-level (SP-E.2). Load anchor trunk directly; build via castle's mount ctx.
        log("Phase C CROSS-LEVEL — anchor (UNATCO textures) after castle")
        try:
            anchor_level, _ = trunk.read_level(ANCHOR_TRUNK)
            refs = sorted(set(apply._level_referenced_packages(anchor_level)))
            log(f"  anchor refs packages: {refs}")
            actx = {**ctx, "level": anchor_level}
            # ensure a leading dismissal so this isn't sabotaged by a prior dialog
            rec = one_build(actx, OUT_DIR / "xlevel_anchor.dx", "xlevel-anchor", probe, True)
            rec["anchor_ref_packages"] = refs
            R["cross_level"].append(rec)
            # a castle build immediately after, to check reverse residue
            R["cross_level"].append(
                one_build(ctx, OUT_DIR / "xlevel_castle_after.dx", "xlevel-castle-after", probe, True))
            save()
        except Exception as e:      # noqa: BLE001
            R["notes"].append(f"cross-level error: {e}")
            log(f"  cross-level error: {e}")
    finally:
        log("teardown…")
        editor_mod.stop_editor(warm_id, ctx["state_dir"])
        save()

    def rate(phase):
        n = len(R[phase])
        f = sum(1 for r in R[phase] if r["rc"] != 0)
        return f"{f}/{n} failed"
    R["summary"] = {"baseline": rate("baseline"), "mitigated": rate("mitigated"),
                    "cross_level": rate("cross_level")}
    save()
    log(f"SUMMARY: {R['summary']}")
    print(json.dumps(R, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
