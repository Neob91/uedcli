#!/usr/bin/env python3
"""Capture the LIVE editor's `FGlobalMath::TrigFLOAT` sine table (16384 f32s at core.dll VA
0x1013e934, the base of the `movss xmm, [eax*4 + 0x1013e934]` reads in
`FCoords::operator/=(FRotator)` 0x18a10) via one gdb attach to a throwaway dbg editor -- no map,
no rebuild.  Verifies core.dll's runtime base from /proc/<pid>/maps first (the Engine.dll rebase
trap, HANDOFF.md).

Usage: vdb_sintab_capture.py [out.bin]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_HARNESS / "editor-tree-oracle"))
import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path(__file__).resolve().parent.parent / "logs/sintab-live.bin")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
TAB_VA = 0x1013E934
TAB_BYTES = 16384 * 4


def main() -> int:
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')
    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)
    container = "uned-sintab"
    O.stop_dbg_editor(container, state_dir)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        pid = O._editor_pid(container)
        maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                              capture_output=True, text=True).stdout
        core_lines = [ln for ln in maps.splitlines() if "core.dll" in ln.lower()]
        print("core.dll maps:")
        for ln in core_lines[:4]:
            print(" ", ln)
        base = int(core_lines[0].split("-")[0], 16) if core_lines else None
        print(f"core.dll base: {base:#x}" if base else "core.dll base: NOT FOUND")
        if base is None:
            raise SystemExit("core.dll not mapped")
        # core.dll rebases (observed base 0x19a0000, declared 0x10000000) -- resolve via RVA.
        va = base + (TAB_VA - 0x10000000)
        print(f"table runtime VA: {va:#x}")
        gdb = (f"set pagination off\nset confirm off\nattach {pid}\n"
               f"dump binary memory /tmp/sintab.bin {va:#x} {va + TAB_BYTES:#x}\n"
               f"detach\nquit\n")
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/st.gdb"],
                       input=gdb, text=True, check=True)
        r = subprocess.run(["docker", "exec", container, "bash", "-c",
                            "gdb -batch -x /tmp/st.gdb 2>&1 | tail -5"],
                           capture_output=True, text=True)
        print(r.stdout)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["docker", "exec", container, "cat", "/tmp/sintab.bin"],
                              capture_output=True).stdout
        OUT.write_bytes(data)
        print(f"wrote {OUT} ({len(data)} bytes)")
        return 0 if len(data) == TAB_BYTES else 1
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    raise SystemExit(main())
