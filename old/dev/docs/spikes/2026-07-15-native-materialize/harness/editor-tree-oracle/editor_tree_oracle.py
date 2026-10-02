#!/usr/bin/env python3
r"""EDITOR-TREE ORACLE — log UnrealEd's incremental `bspAddNode` calls during a `MAP REBUILD`.

WHY (the wall).  Native `build_geometry_bspcsg` matches the editor's pre-repartition CSG soup
exactly through N=32 brushes and diverges at N=33 (`RoofNE`).  Section 82 §10.6 traced this to a
cumulative incremental world-BSP-tree ORDER divergence: native's tree routes the roof underside
through a DEAD merlon node (x=112) where the editor routes it to TowerNE's octagon face
(x=111.958).  The editor's INCREMENTAL tree is never serialized to the `.dx` (only its final,
soup-rebuilt tree is), so it can't be compared from the output alone.  This oracle OBSERVES the
editor building its tree, node by node.

HOW.  `bspAddNode` (Editor.dll RVA 0x34e80, ImageBase 0x10000000, loads un-relocated at
0x10000000 in classic 32-bit wine — verified) is the single node-emitter for the whole build
(splitter + coplanar chain + every incremental brush-face fragment).  We run the editor in a
gdb-equipped, ptrace-capable container (`dx-lum-uned-dbg` + compose.override.yml), MAP LOAD the
cached golden{N}.dx subset, attach gdb with a breakpoint at 0x10034e80 that logs each call's
args and continues, then MAP REBUILD.  MAP LOAD+REBUILD reproduces the same incremental tree that
built the golden (csgRebuild EmptyModel's then rebuilds purely from the brush actors, in Actors[]
= trunk order).

At the breakpoint (first insn, `push ebp` — prologue NOT yet run), args are at $esp:
    [esp]=ret  [esp+4]=Model  [esp+8]=iParent  [esp+0xc]=ENodePlace  [esp+0x10]=NodeFlags
    [esp+0x14]=EdPoly(FPoly*)
FPoly fields (verified via adis.py on bspAddNode): Base=+0x00, Normal=+0x0c, NumVertices=+0x1c0,
iLink=+0x1c4.  We log ret (→ caller/phase), Model (→ world vs temp), iParent, ENodePlace,
NodeFlags, iLink, NumVertices, Normal, Base.

Completion is detected by LOG QUIESCENCE (cmd_exec returns after 0.3s, NOT when REBUILD finishes;
under gdb the rebuild is slower) — when no new ADD line appears for `--quiet-secs`, detach.

Usage:
  editor_tree_oracle.py run N [--quiet-secs 6] [--out DIR]   # produce oracle-N.log
  editor_tree_oracle.py classify oracle-N.log                # phase-tag + world-tree slice
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]      # Tools/uedcli (editor-tree-oracle/ -> harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> root)
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))

from uedcli import config, container_assets, editor as editor_mod  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

import subset_diff  # noqa: E402

BSPADDNODE_VA = 0x10034E80


# --------------------------------------------------------------------------- targets
# The gdb machinery (bspAddNode RVA, ptrace override, printf script) is geometry-agnostic; only the
# SUBSET SOURCE (which cached golden{N}.dx, which asset mounts, which texture packages to OBJ LOAD)
# is substrate-specific.  A Target abstracts that so the same oracle serves the castle (the original
# hardcode) and the UNATCO dome-CSG-divergence subset (spec 2026-07-19-unatco-dome-csg-divergence).


class _Target:
    name = "?"

    @property
    def project_dir(self):
        raise NotImplementedError

    def golden(self, n: int):
        """Path to the cached editor golden{N}.dx (built on demand if the target supports it)."""
        raise NotImplementedError

    def ref_pkgs(self, n: int):
        """Texture/asset packages to OBJ LOAD before the rebuild (empty = none; castle never did)."""
        return []


class _CastleTarget(_Target):
    name = "castle"

    @property
    def project_dir(self):
        return subset_diff.CASTLE_PROJECT

    def golden(self, n: int):
        return subset_diff.build_editor_subset(n)

    def ref_pkgs(self, n: int):
        # Castle golden built without an explicit OBJ LOAD (its textures resolve from the boot ini
        # Paths); keep the original behaviour byte-for-byte so the castle capture is unchanged.
        return []


class _UnatcoTarget(_Target):
    """UNATCO dome-CSG-divergence subset: cached golden{N}.dx already exist under
    `_scratch/unatco-subset/` (built by `unatco_subset.build_editor_subset`); mounts are the UNATCO
    project's composed search dirs (bare deusex base — no LUM overlay); the referenced texture
    packages are OBJ LOADed exactly as `build_ued_golden` does so surfaces resolve during REBUILD."""
    name = "unatco"

    def _mod(self):
        import unatco_subset  # noqa: E402  (lazy: pulls in native + surf-diff harness)
        return unatco_subset

    @property
    def project_dir(self):
        # `<...>/unatco/uedcli/maps/unatco` -> project root `<...>/unatco/uedcli`.
        return self._mod().FULL_TRUNK.parent.parent

    def golden(self, n: int):
        u = self._mod()
        p = u.golden_path(n)
        if not p.exists():
            p = u.build_editor_subset(n)  # drives the editor — slow; normally pre-cached
        return p

    def ref_pkgs(self, n: int):
        from uedcli import trunk  # noqa: E402
        from uedcli.materialize import _short_class  # noqa: E402
        from uedcli.apply import _level_referenced_packages  # noqa: E402
        u = self._mod()
        lvl, _ = trunk.read_level(u.FULL_TRUNK)
        order = [nm for nm in lvl.order if _short_class(lvl.actors[nm].cls) in ("Brush", "LevelInfo")]
        brushes = [nm for nm in order if lvl.actors[nm].brush is not None]
        keep_brush = set(brushes[:n])
        keep = [nm for nm in order if lvl.actors[nm].brush is None or nm in keep_brush]
        sub = type("L", (), {"actors": {nm: lvl.actors[nm] for nm in keep}})()
        return _level_referenced_packages(sub)


_TARGETS = {t.name: t for t in (_CastleTarget(), _UnatcoTarget())}


def resolve_target(name: str) -> _Target:
    if name not in _TARGETS:
        raise SystemExit(f"unknown --target {name!r} (choose from {sorted(_TARGETS)})")
    return _TARGETS[name]
COMPOSE_BASE = ROOT / "uned" / "docker-compose.yml"
COMPOSE_OVERRIDE = HERE / "compose.override.yml"
DBG_IMAGE = "dx-lum-uned-dbg:latest"


# --------------------------------------------------------------------------- container

def _ensure_dbg_image() -> None:
    if subprocess.run(["docker", "image", "inspect", DBG_IMAGE],
                      capture_output=True).returncode != 0:
        subprocess.run([str(HERE / "build-dbg-image.sh")], check=True)


def _composed_mounts(project_dir: Path):
    """The castle project's composed asset mounts + engine-ini Paths (mirrors run_materialize)."""
    project = config.load_project(str(project_dir))
    uc = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, uc)
    return container_assets.resource_mounts(search_dirs)


def _state_dir(project_dir: Path) -> Path:
    """The project's `.uedcli/` state dir — threaded into editor.py's ini helpers (which since
    the 2026-07-17 20:58 refactor require an explicit `state_dir` for their tmp-ini path)."""
    project = config.load_project(str(project_dir))
    return config.state_dir(project.root, create=True)


def start_dbg_editor(container: str, mounts, state_dir: Path) -> None:
    """Start the gdb-equipped editor container via `docker compose -f base -f override run`, with the
    SAME asset mounts + crafted engine ini `ensure_editor` uses, plus ptrace caps from the override."""
    if subprocess.run(["docker", "ps", "-q", "-f", f"name=^{container}$"],
                      capture_output=True, text=True).stdout.strip():
        return
    _ini_path, ini_mount = editor_mod.engine_ini_mount(container, mounts, state_dir)
    wp_vol = f"uned-wp-{container[len('uned-'):]}" if container.startswith("uned-") else f"{container}-wp"
    cmd = ["docker", "compose", "-f", str(COMPOSE_BASE), "-f", str(COMPOSE_OVERRIDE),
           "run", "-d", "-p", "0:6080", "--name", container,
           "-v", f"{wp_vol}:/wineprefix", *ini_mount,
           *container_assets.docker_mount_args(mounts), "uned"]
    # UEDCLI_STUB_CACHE must be set explicitly: the compose file's `${UEDCLI_STUB_CACHE:-${HOME}/...}`
    # nested substitution is not supported by docker compose's interpolation (it resolves only the
    # outer `${HOME}` and drops the trailing path), so the un-set-var fallback mounts plain `$HOME`
    # itself as the bind source -> "mkdir $HOME: permission denied". `editor.ensure_editor` already
    # works around this (board chore 2026-07-18); mirrored here since this call bypasses that helper.
    env = {**os.environ, "UEDCLI_STUB_CACHE": str(config.stub_cache_root(create=True))}
    subprocess.run(cmd, cwd=str(ROOT / "uned"), env=env, check=True, capture_output=True, text=True)
    editor_mod._wait_ready(container, 120.0)


def stop_dbg_editor(container: str, state_dir: Path) -> None:
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True)
    wp_vol = f"uned-wp-{container[len('uned-'):]}" if container.startswith("uned-") else f"{container}-wp"
    subprocess.run(["docker", "volume", "rm", wp_vol], capture_output=True, text=True)
    editor_mod._engine_ini_path(container, state_dir).unlink(missing_ok=True)


# --------------------------------------------------------------------------- gdb

_GDB_SCRIPT = r"""
set pagination off
set confirm off
set height 0
set width 0
attach {pid}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
break *{va:#x}
commands
silent
set $e = *(unsigned int *)($esp + 0x14)
printf "ADD ret=%#x model=%#x parent=%d place=%d flags=%#x ilink=%d nv=%d N=%.5f,%.5f,%.5f B=%.5f,%.5f,%.5f\n", *(unsigned int *)($esp), *(unsigned int *)($esp + 4), *(int *)($esp + 8), *(int *)($esp + 0xc), *(unsigned int *)($esp + 0x10), *(int *)($e + 0x1c4), *(int *)($e + 0x1c0), *(float *)($e + 0xc), *(float *)($e + 0x10), *(float *)($e + 0x14), *(float *)($e), *(float *)($e + 4), *(float *)($e + 8)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _editor_pid(container: str) -> int:
    out = subprocess.run(["docker", "exec", container, "pgrep", "-fi", "unrealed.exe"],
                         capture_output=True, text=True).stdout.strip().splitlines()
    if not out:
        raise RuntimeError("editor pid not found")
    return int(out[0])


def _launch_gdb(container: str, pid: int, log_container: str) -> None:
    """Write the gdb script into the container and launch gdb -batch detached, logging to
    `log_container`.  gdb stays attached and continuing; it is torn down with the container."""
    script = _GDB_SCRIPT.format(pid=pid, va=BSPADDNODE_VA)
    subprocess.run(["docker", "exec", "-i", container, "bash", "-c",
                    "cat > /tmp/oracle.gdb"], input=script, text=True, check=True)
    # Detached: gdb runs in the background inside the container, redirecting to the log.
    subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                    "exec gdb -batch -x /tmp/oracle.gdb > /tmp/oracle.log 2>&1"], check=True)


def _wait_attached(container: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = subprocess.run(["docker", "exec", container, "bash", "-c",
                              "grep -c ORACLE_ATTACHED /tmp/oracle.log 2>/dev/null || true"],
                             capture_output=True, text=True).stdout.strip()
        if out and out != "0":
            return
        time.sleep(0.5)
    # dump whatever gdb said, for diagnosis
    diag = subprocess.run(["docker", "exec", container, "cat", "/tmp/oracle.log"],
                          capture_output=True, text=True).stdout
    raise RuntimeError(f"gdb did not attach within {timeout}s. gdb log:\n{diag[:2000]}")


def _log_line_count(container: str) -> int:
    out = subprocess.run(["docker", "exec", container, "bash", "-c",
                          "grep -c '^ADD ' /tmp/oracle.log 2>/dev/null || true"],
                         capture_output=True, text=True).stdout.strip()
    return int(out) if out and out.isdigit() else 0


def _wait_quiescent(container: str, quiet_secs: float, hard_timeout: float = 1200.0) -> int:
    """Block until the ADD-line count is stable for `quiet_secs` (rebuild finished) or hard timeout."""
    deadline = time.monotonic() + hard_timeout
    last = -1
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        n = _log_line_count(container)
        now = time.monotonic()
        if n != last:
            last, last_change = n, now
        elif n > 0 and (now - last_change) >= quiet_secs:
            return n
        time.sleep(1.0)
    return last


# --------------------------------------------------------------------------- run

def run(n: int, quiet_secs: float, out_dir: Path, target_name: str = "castle") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _ensure_dbg_image()
    target = resolve_target(target_name)

    # 1. Cached golden{N}.dx (built via the NORMAL editor materialize if absent).
    golden = target.golden(n)
    print(f"[oracle] target={target.name} golden N={n}: {golden}")

    # 2. Debug editor container with the target's composed assets mounted.
    mounts = _composed_mounts(target.project_dir)
    state_dir = _state_dir(target.project_dir)
    container = f"uned-oracle-{target.name}-n{n}"
    stop_dbg_editor(container, state_dir)  # clean any stale
    print(f"[oracle] starting {container} ({DBG_IMAGE}, ptrace) ...")
    start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        # 2b. OBJ LOAD the referenced texture packages (build_ued_golden parity) so surfaces resolve
        # during REBUILD.  Best-effort: CSG geometry (the ADD stream we capture) is texture-independent,
        # so a texture hiccup must not abort the capture.
        ref = target.ref_pkgs(n)
        if ref:
            print(f"[oracle] OBJ LOAD {len(ref)} referenced packages ...")
            try:
                from uedcli.packages import ensure_load, editor_search_dirs  # noqa: E402
                project = config.load_project(str(target.project_dir))
                uc = config.load_user_config()
                sdirs = config.composed_search_dirs(project, uc)
                ensure_load(drv, ref, search_dirs=editor_search_dirs(sdirs), mounts=mounts)
            except Exception as exc:  # noqa: BLE001
                print(f"[oracle] WARN: OBJ LOAD failed ({exc}); continuing (geometry is texture-independent)")

        # 3. Load the golden subset into the editor.
        subprocess.run(["docker", "cp", str(golden), f"{container}:/work/golden.dx"], check=True)
        print("[oracle] MAP LOAD golden.dx ...")
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)

        # 4. Attach gdb, then MAP REBUILD, then wait for quiescence.
        pid = _editor_pid(container)
        print(f"[oracle] attaching gdb to editor pid {pid} ...")
        _launch_gdb(container, pid, "/tmp/oracle.log")
        _wait_attached(container)
        print("[oracle] gdb attached; issuing MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        n_adds = _wait_quiescent(container, quiet_secs)
        print(f"[oracle] rebuild quiescent: {n_adds} bspAddNode calls logged")

        # 5. Pull the log.
        out = out_dir / f"oracle-{n}.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/oracle.log", str(out)], check=True)
        print(f"[oracle] wrote {out}")
        return out
    finally:
        stop_dbg_editor(container, state_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="materialize+load golden{N}, MAP REBUILD under gdb, log bspAddNode")
    r.add_argument("n", type=int, help="subset size (number of brushes)")
    r.add_argument("--target", default="castle", choices=sorted(_TARGETS),
                   help="subset source: castle (default) or unatco (dome-CSG-divergence golden{N}.dx)")
    r.add_argument("--quiet-secs", type=float, default=6.0,
                   help="log-quiescence window that means the rebuild finished (default 6s)")
    r.add_argument("--out", type=Path, default=HERE / "logs", help="output dir for oracle-N.log")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.n, args.quiet_secs, args.out, target_name=args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
