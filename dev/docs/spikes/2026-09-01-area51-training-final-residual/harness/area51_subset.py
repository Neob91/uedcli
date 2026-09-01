#!/usr/bin/env python3
"""Area51 Entrance N-brush subset builder -- mirrors unatco_subset.py's pattern, for isolating
Brush1852's own incremental bspBrushCSG call (n=506 exact base -> n=507 adds Brush1852).
Source trunk: the cached extraction under breadth-parity-check's _scratch (read-only DATA, not code).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from spike_classindex import class_index  # noqa: E402
from uedcli import trunk  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402

FULL_TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/"
                  "uedcli-parity-cache/65b9261c371bdf8573cb7bf9128a3f6664b14d2ac360ef6fbfd4a0d292986ece/"
                  "trunk/maps/15_area51_entrance")
os.environ.setdefault("UEDCLI_PROJECT", str(FULL_TRUNK.parent.parent))
SUBSET_ROOT = ROOT / "_scratch/area51-subset"
BUILDER = HARNESS / "build_ued_golden.py"
PYTHON = ROOT / ".venv/bin/python"


def _brush_order(level):
    ci = class_index()
    return [n for n in level.order if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]


def golden_path(n: int) -> Path:
    return SUBSET_ROOT / f"golden{n}.dx"


def _make_subset_trunk(n: int) -> Path:
    level, _ = trunk.read_level(FULL_TRUNK)
    brushes = _brush_order(level)
    keep = set(brushes[:n])
    proj = SUBSET_ROOT / f"trunk{n}"
    dst = proj / "maps" / "15_area51_entrance"
    if dst.exists():
        shutil.rmtree(dst)
    dst_actors = dst / "actors"
    dst_actors.mkdir(parents=True)
    src_actors = FULL_TRUNK / "actors"
    for name in level.order:
        a = level.actors[name]
        cls = a.cls.split(".")[-1]
        if a.brush is not None and name not in keep:
            continue
        if a.brush is None and cls != "LevelInfo":
            continue
        shutil.copytree(src_actors / name, dst_actors / name)
    (proj / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')
    return dst


def build_editor_subset(n: int, force: bool = False, quiet_reads: int = 30) -> Path:
    out = golden_path(n)
    if out.exists() and not force:
        return out
    subset_trunk = _make_subset_trunk(n)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(PYTHON), str(BUILDER), "--trunk", str(subset_trunk), "--out", str(out),
           "--world-only", "--no-light", "--no-obj-load", "--overwrite",
           "--quiet-reads", str(quiet_reads), "--rebuild-min-seconds", "20"]
    print(f"[subset] editor-building N={n} ...", flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    tail = "\n".join(r.stdout.splitlines()[-8:])
    if r.returncode != 0 or not out.exists():
        print(tail)
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"editor subset build N={n} FAILED (rc={r.returncode})")
    print(f"[subset] N={n} -> {out}\n    {tail.splitlines()[-1] if tail else ''}", flush=True)
    return out


if __name__ == "__main__":
    n = int(sys.argv[1])
    force = "--force" in sys.argv
    print(build_editor_subset(n, force=force))
