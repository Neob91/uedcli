#!/usr/bin/env python3
"""SP-E final discriminator — is the live OBJ DEPENDENCIES qualify dump the reused-build disruptor?

Established so far (warm_editor_noverify.py): reused builds are 0/4-clean with no_verify, but 2/4
fail (alternating) whenever the H3 verify runs against the warm editor — and isolating ONLY the UCC
batchexport to a separate container did NOT fix it. The remaining warm-editor interaction inside
verify is the live qualify pass's `OBJ DEPENDENCIES` dump (qualify_driver=ed). This tests it:

  N warm builds where the H3 verify runs the UCC export on the warm container BUT with
  qualify_driver=None (NO OBJ DEPENDENCIES dump against the warm editor). If 0/N fail → the qualify
  dump is the disruptor. If it still alternates → the disruptor is the map_save→UCC-read sequence
  itself, not the qualify dump.

Run: cd Tools/uedctl && .venv/bin/python dev/docs/spikes/2026-07-18-warm-editor-materialize/harness/warm_editor_qualify_probe.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

TOOL = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(TOOL))

from uedctl import apply, config, trunk               # noqa: E402
from uedctl import editor as editor_mod               # noqa: E402
from uedctl import verify as verify_mod               # noqa: E402
from uedctl.driver import Driver                      # noqa: E402
from uedctl.container_assets import resource_mounts   # noqa: E402
from uedctl.packages import search_path_package_names  # noqa: E402
from uedctl.uuid7 import uuid7                          # noqa: E402

CASTLE_DIR = TOOL / "_scratch/castle/uedctl"
OUT_DIR = Path(os.environ.get("OUT_DIR", str(TOOL / "_scratch/warm-spike")))
OUT_DIR.mkdir(parents=True, exist_ok=True)
RES = OUT_DIR / "warm_qualify_results.json"
N = int(os.environ.get("Q_N", "4"))
R: dict = {"no_qualify_verify": []}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


# Force the H3 verify to run WITHOUT the live qualify dump (drop qualify_driver).
_ORIG_VERIFY = apply.verify_dx_matches


def _verify_no_qualify(*, container, dx_path, expected, qualify_driver=None):
    return _ORIG_VERIFY(container=container, dx_path=dx_path, expected=expected, qualify_driver=None)


apply.verify_dx_matches = _verify_no_qualify


def load_castle():
    project = config.load_project(str(CASTLE_DIR))
    uc = config.load_user_config()
    return dict(
        level=trunk.read_level(Path(config.project_maps_dir(project)) / "foobar")[0],
        packages=search_path_package_names(config.composed_search_files(project, uc)),
        search_dirs=config.composed_search_dirs(project, uc),
        state_dir=config.state_dir(project.root, create=True))


def main():
    ctx = load_castle()
    warm_id = uuid7()
    log("booting warm editor…")
    container = editor_mod.ensure_editor(warm_id, mounts=resource_mounts(ctx["search_dirs"]),
                                         state_dir=ctx["state_dir"])
    apply.ensure_editor = lambda _i, **_k: container
    apply.stop_editor = lambda *_a, **_k: None
    try:
        log(f"{N} warm builds — H3 verify WITH UCC export on warm, WITHOUT qualify dump")
        for i in range(1, N + 1):
            t0 = time.monotonic()
            res = apply.run_materialize(
                level=ctx["level"], packages=ctx["packages"], search_dirs=ctx["search_dirs"],
                out_path=str(OUT_DIR / f"nq{i}.dx"), overwrite=True, state_dir=ctx["state_dir"])
            dt = round(time.monotonic() - t0, 1)
            R["no_qualify_verify"].append({"tag": f"noqual-{i}", "rc": res.rc, "seconds": dt,
                                           "msg": res.message[:120]})
            log(f"  noqual-{i}: rc={res.rc} {dt}s :: {res.message[:70]}")
            RES.write_text(json.dumps(R, indent=2))
    finally:
        log("teardown…")
        editor_mod.stop_editor(warm_id, ctx["state_dir"])
    fails = sum(1 for r in R["no_qualify_verify"] if r["rc"] != 0)
    R["summary"] = f"{fails}/{len(R['no_qualify_verify'])} failed"
    RES.write_text(json.dumps(R, indent=2))
    log(f"SUMMARY: {R['summary']}")
    print(json.dumps(R, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
