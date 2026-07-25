#!/usr/bin/env python3
"""SP-E — warm-editor materialize spike harness (reused-editor cleanliness + timing split).

Drives MULTIPLE `level materialize` builds through ONE booted UnrealEd container — the exact
"warm editor" the spec `specs/2026-07-18-warm-editor-materialize.md` §8 proposes — and instruments
the seven SP-E questions live. It does this the FAITHFUL way: it monkeypatches ONLY the container
lifecycle seams (`apply.ensure_editor` → return the one warm container; `apply.stop_editor` →
no-op) and then calls the *real* `apply.run_materialize` N times, so every build runs the true
production drive (full re-import → MAP REBUILD → LIGHT APPLY → MAP SAVE → H3 verify with the live
qualify pass against the reused editor). The only thing that changes vs today is that the container
is booted ONCE up front and torn down ONCE at the end instead of per build.

Run HOST-NATIVE in the dev venv (same runtime `bin/uedctl` uses):
    cd Tools/uedctl && .venv/bin/python dev/docs/spikes/2026-07-18-warm-editor-materialize/harness/warm_editor_probe.py

Env knobs: WARM_N (warm castle builds, default 6), SKIP_COLD=1, SKIP_CROSS=1.
Outputs: a JSON blob to stdout AND to $OUT_DIR/warm_spike_results.json (default under _scratch).
Editor .dx artifacts land in $OUT_DIR (gitignored _scratch) — never the tracked tree.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

TOOL = Path(__file__).resolve().parents[5]          # …/Tools/uedctl
sys.path.insert(0, str(TOOL))

from uedctl import apply, config, trunk                       # noqa: E402
from uedctl import editor as editor_mod                       # noqa: E402
from uedctl import driver as driver_mod                       # noqa: E402
from uedctl.driver import Driver                              # noqa: E402
from uedctl.container_assets import resource_mounts           # noqa: E402
from uedctl.packages import editor_search_dirs, search_path_package_names  # noqa: E402
from uedctl.normalize import canonical_level_hash             # noqa: E402
from uedctl.store_export import export_dx_level               # noqa: E402
from uedctl.uuid7 import uuid7                                 # noqa: E402

CASTLE_DIR = TOOL / "_scratch/castle/uedctl"
CASTLE_LEVEL = "foobar"
ANCHOR_DIR = TOOL / "_scratch/anchor/uedctl"
ANCHOR_LEVEL = "anchor"

OUT_DIR = Path(os.environ.get("OUT_DIR", str(TOOL / "_scratch/warm-spike")))
OUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_PATH = OUT_DIR / "warm_spike_results.json"

WARM_N = int(os.environ.get("WARM_N", "6"))

RESULTS: dict = {"builds": [], "obj_load_calls": [], "phases": {}, "notes": []}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save() -> None:
    RESULTS_PATH.write_text(json.dumps(RESULTS, indent=2))


# ─────────────────────────────── context loading ───────────────────────────────

def load_ctx(project_dir: Path, level_name: str) -> dict:
    project = config.load_project(str(project_dir))
    uc = config.load_user_config()
    if uc is None:
        raise SystemExit("no ~/.uedctl/config.toml — needed for base game paths")
    search_dirs = config.composed_search_dirs(project, uc)
    package_names = search_path_package_names(config.composed_search_files(project, uc))
    maps_dir = Path(config.project_maps_dir(project))
    level, _ranks = trunk.read_level(maps_dir / level_name)
    state_dir = config.state_dir(project.root, create=True)
    return {
        "project": project, "search_dirs": search_dirs, "packages": package_names,
        "level": level, "state_dir": state_dir,
    }


# ─────────────────────────────── instrumentation ───────────────────────────────

_CUR_BUILD = {"tag": "?"}
_ORIG_OBJ_LOAD = Driver.obj_load


def _instrumented_obj_load(self: Driver, package: str, file_path: str) -> None:
    """Wrap Driver.obj_load: record the Editor.log delta + any error, tagged by current build.
    On warm builds ≥2 these calls hit ALREADY-RESIDENT packages (SP-E.3)."""
    try:
        before = self.log_size()
    except Exception:
        before = -1
    err = None
    t0 = time.monotonic()
    try:
        _ORIG_OBJ_LOAD(self, package, file_path)
    except Exception as e:                        # noqa: BLE001 — record, don't abort the build
        err = f"{type(e).__name__}: {e}"
        raise
    finally:
        dt = time.monotonic() - t0
        try:
            after = self.log_size()
        except Exception:
            after = -1
        RESULTS["obj_load_calls"].append({
            "build": _CUR_BUILD["tag"], "package": package,
            "log_before": before, "log_after": after,
            "log_delta": (after - before) if before >= 0 and after >= 0 else None,
            "seconds": round(dt, 3), "error": err,
        })
    save()


Driver.obj_load = _instrumented_obj_load


def probe_rss(probe: Driver) -> int | None:
    """Editor process VmRSS in KiB, via /run/uned.pid → /proc/<pid>/status."""
    try:
        out = probe.dexec_bash(
            "pid=$(cat /run/uned.pid 2>/dev/null | tr -d '[:space:]'); "
            "[ -n \"$pid\" ] && grep VmRSS /proc/$pid/status 2>/dev/null | awk '{print $2}'")
        out = out.strip().splitlines()
        return int(out[-1]) if out and out[-1].isdigit() else None
    except Exception:
        return None


def probe_log_size(probe: Driver) -> int | None:
    try:
        return probe.log_size()
    except Exception:
        return None


def liveness(probe: Driver) -> str:
    """wine_ctl status → 'alive+window' / 'alive-nowindow' / 'dead'."""
    try:
        out = probe.dexec_bash("python3 /opt/uned/wine_ctl.py status 2>&1 || true")
        alive = "alive=True" in out
        has_win = any(seg.startswith("window=") and seg[7:8].isdigit()
                      for seg in out.replace("\n", " ").split())
        return "alive+window" if (alive and has_win) else ("alive-nowindow" if alive else "dead")
    except Exception as e:                         # noqa: BLE001
        return f"probe-error:{e}"


# ─────────────────────────────── one build ───────────────────────────────

def do_build(ctx: dict, out_path: Path, tag: str, probe: Driver | None) -> dict:
    _CUR_BUILD["tag"] = tag
    rss_before = probe_rss(probe) if probe else None
    log_before = probe_log_size(probe) if probe else None
    live_before = liveness(probe) if probe else None
    t0 = time.monotonic()
    res = apply.run_materialize(
        level=ctx["level"], packages=ctx["packages"], search_dirs=ctx["search_dirs"],
        out_path=str(out_path), overwrite=True, state_dir=ctx["state_dir"],
        no_verify=False, keep_build=False)
    dt = time.monotonic() - t0
    rss_after = probe_rss(probe) if probe else None
    log_after = probe_log_size(probe) if probe else None
    live_after = liveness(probe) if probe else None
    rec = {
        "tag": tag, "out": str(out_path), "rc": res.rc, "message": res.message,
        "seconds": round(dt, 2),
        "rss_before_kib": rss_before, "rss_after_kib": rss_after,
        "log_before": log_before, "log_after": log_after,
        "live_before": live_before, "live_after": live_after,
        "artifact_bytes": out_path.stat().st_size if out_path.exists() else None,
    }
    RESULTS["builds"].append(rec)
    save()
    log(f"  build {tag}: rc={res.rc} {dt:.1f}s rss={rss_before}->{rss_after}KiB "
        f"log={log_before}->{log_after} live={live_after} :: {res.message[:80]}")
    return rec


# ─────────────────────────────── SP-E.1 comparison ───────────────────────────────

def canon_of_hostdx(probe: Driver, host_dx: Path, cmp_name: str) -> str | None:
    """docker cp a host .dx into the warm container /work and canonical-hash its UCC export.
    Same export oracle H3 uses; equal hashes across builds ⇒ no resident-state contamination."""
    if not host_dx.exists():
        return None
    cpath = f"/work/{cmp_name}.dx"
    subprocess.run(["docker", "cp", str(host_dx), f"{probe.container}:{cpath}"],
                   capture_output=True, text=True, check=True)
    try:
        lvl = export_dx_level(probe.container, cpath)
        return canonical_level_hash(lvl)
    except Exception as e:                         # noqa: BLE001
        RESULTS["notes"].append(f"canon export failed for {cmp_name}: {e}")
        return None


# ─────────────────────────────── main ───────────────────────────────

def main() -> int:
    log(f"OUT_DIR={OUT_DIR}  WARM_N={WARM_N}")
    castle = load_ctx(CASTLE_DIR, CASTLE_LEVEL)
    log(f"castle level: {len(castle['level'].actors)} actors; "
        f"{len(castle['packages'])} packages on composed path; "
        f"{len(castle['search_dirs'])} search dirs")

    # ── Phase 0: genuine COLD ephemeral build (real ensure+stop) — the §1 baseline ──
    cold_dx = OUT_DIR / "cold.dx"
    if os.environ.get("SKIP_COLD") != "1":
        log("Phase 0: genuine cold ephemeral build (boot+drive+teardown)…")
        t0 = time.monotonic()
        res = apply.run_materialize(
            level=castle["level"], packages=castle["packages"], search_dirs=castle["search_dirs"],
            out_path=str(cold_dx), overwrite=True, state_dir=castle["state_dir"])
        RESULTS["phases"]["cold_total_s"] = round(time.monotonic() - t0, 2)
        RESULTS["phases"]["cold_rc"] = res.rc
        RESULTS["phases"]["cold_msg"] = res.message
        log(f"  cold total {RESULTS['phases']['cold_total_s']}s rc={res.rc} :: {res.message[:80]}")
        save()

    # ── Phase 1: boot ONE warm editor (real ensure_editor with castle mounts) ──
    log("Phase 1: booting ONE warm editor…")
    search_dirs = castle["search_dirs"]
    mounts = resource_mounts(search_dirs)
    warm_id = uuid7()
    t0 = time.monotonic()
    warm_container = editor_mod.ensure_editor(warm_id, mounts=mounts, state_dir=castle["state_dir"])
    RESULTS["phases"]["boot_s"] = round(time.monotonic() - t0, 2)
    RESULTS["phases"]["warm_container"] = warm_container
    log(f"  booted {warm_container} in {RESULTS['phases']['boot_s']}s")
    save()
    probe = Driver(container=warm_container)

    # Redirect the lifecycle seams so run_materialize reuses THIS container and never tears it down.
    apply.ensure_editor = lambda _id, **_k: warm_container
    apply.stop_editor = lambda *_a, **_k: None

    try:
        # ── Phase 2: N warm castle builds (SP-E.1/3/4/5/6) ──
        log(f"Phase 2: {WARM_N} warm castle builds through the reused editor…")
        for i in range(1, WARM_N + 1):
            do_build(castle, OUT_DIR / f"warm{i}.dx", f"castle-warm-{i}", probe)

        # ── Phase 3: cross-level warm build (SP-E.2) — disjoint packages (UNATCO vs Core/LUM) ──
        if os.environ.get("SKIP_CROSS") != "1":
            log("Phase 3: cross-level warm build (anchor, UNATCO textures) after castle…")
            try:
                anchor = load_ctx(ANCHOR_DIR, ANCHOR_LEVEL)
                # Build anchor through the SAME warm editor booted with castle's (superset) mounts.
                anchor_ctx = {**anchor, "packages": anchor["packages"],
                              "search_dirs": castle["search_dirs"], "state_dir": castle["state_dir"]}
                log(f"  anchor level: {len(anchor['level'].actors)} actors; "
                    f"refs packages {sorted(_ref_pkgs(anchor['level']))}")
                do_build(anchor_ctx, OUT_DIR / "anchor.dx", "anchor-warm-after-castle", probe)
                # And a castle build immediately AFTER anchor — does anchor residue harm castle?
                do_build(castle, OUT_DIR / "castle_after_anchor.dx",
                         "castle-warm-after-anchor", probe)
            except Exception as e:                 # noqa: BLE001
                RESULTS["notes"].append(f"cross-level phase error: {e}")
                log(f"  cross-level phase error: {e}")
                save()

        # ── SP-E.1 artifact equivalence: cold vs warm1 vs warm2 (canonical export) ──
        log("SP-E.1: canonical-export comparison cold/warm1/warm2…")
        hashes = {
            "cold": canon_of_hostdx(probe, cold_dx, "cmp_cold"),
            "warm1": canon_of_hostdx(probe, OUT_DIR / "warm1.dx", "cmp_warm1"),
            "warm2": canon_of_hostdx(probe, OUT_DIR / "warm2.dx", "cmp_warm2"),
        }
        RESULTS["phases"]["canonical_hashes"] = hashes
        RESULTS["phases"]["warm1_eq_warm2"] = (hashes["warm1"] is not None
                                               and hashes["warm1"] == hashes["warm2"])
        RESULTS["phases"]["cold_eq_warm2"] = (hashes["cold"] is not None
                                              and hashes["cold"] == hashes["warm2"])
        log(f"  hashes={hashes}")
        save()

    finally:
        # ── teardown: time the single real teardown ──
        log("Teardown: stopping warm editor…")
        t0 = time.monotonic()
        editor_mod.stop_editor(warm_id, castle["state_dir"])
        RESULTS["phases"]["teardown_s"] = round(time.monotonic() - t0, 2)
        save()

    # ── derived timing summary ──
    warm_drives = [b["seconds"] for b in RESULTS["builds"] if b["tag"].startswith("castle-warm")]
    if warm_drives:
        boot = RESULTS["phases"].get("boot_s", 0)
        teardown = RESULTS["phases"].get("teardown_s", 0)
        RESULTS["phases"]["warm_drive_first_s"] = warm_drives[0]
        RESULTS["phases"]["warm_drive_rest_avg_s"] = (
            round(sum(warm_drives[1:]) / len(warm_drives[1:]), 2) if len(warm_drives) > 1 else None)
        RESULTS["phases"]["est_cold_per_build_s"] = round(boot + warm_drives[0] + teardown, 2)
        RESULTS["phases"]["est_warm_saving_per_build_s"] = round(boot + teardown, 2)
    save()
    log(f"DONE. results → {RESULTS_PATH}")
    print(json.dumps(RESULTS, indent=2))
    return 0


def _ref_pkgs(level) -> set:
    return set(apply._level_referenced_packages(level))


if __name__ == "__main__":
    sys.exit(main())
