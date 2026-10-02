"""Golden build driver for the geo-confirm runs — build_ued_golden.main() with two adaptations:

1. `--no-obj-load`: brush BSP planes don't depend on texture resolution (the harness's own
   documented geometry-only option), so skip the slow package-load phase entirely.
2. `_wait_idle` replacement: the harness gates on WHOLE-CONTAINER CPU (`docker stats`), but this
   environment's container baseline is pegged by the X stack (Xvfb/fluxbox/x11vnc spin ~30-60%
   even when the editor is idle), so that gate never fires (measured: all 3 first-pass goldens
   died in `TimeoutError … [obj-load]`). Gate instead on the `unrealed.exe` PROCESS's own CPU
   (reads utime+stime deltas from /proc/<pid>/stat inside the container), which genuinely spins
   during pastes/rebuild and settles when the editor is done.

Everything else (editor boot, mounts, MAP NEW, _re_add, MAP REBUILD, map_save, xfer) is unchanged.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

import build_ued_golden as bg  # noqa: E402


def _editor_cpu_pct(container: str, sample_s: float = 2.0) -> float:
    script = (
        "P=$(pgrep -f unrealed.exe | head -1);"
        "[ -z \"$P\" ] && { echo '0 0 100'; exit 0; };"
        "T=$(getconf CLK_TCK);"
        "R1=$(awk '{print $14+$15}' /proc/$P/stat);"
        f"sleep {sample_s:.0f};"
        "R2=$(awk '{print $14+$15}' /proc/$P/stat);"
        "echo \"$R2 $R1 $T\""
    )
    try:
        res = subprocess.run(["docker", "exec", container, "sh", "-c", script],
                             capture_output=True, text=True, timeout=40)
    except (subprocess.TimeoutExpired, OSError):
        return 0.0
    try:
        r2, r1, t = (res.stdout or "").strip().split()
    except ValueError:
        return 0.0
    ticks = max(int(r2) - int(r1), 0)
    return ticks / float(t) / sample_s * 100.0


def _wait_idle(container: str, *, label: str, thresh: float = 15.0, quiet_reads: int = 8,
               min_seconds: float = 0.0, timeout: float = 3600.0) -> float:
    t0 = time.time()
    quiet = 0
    last = -1.0
    while True:
        cpu = _editor_cpu_pct(container)
        last = cpu
        quiet = quiet + 1 if cpu < thresh else 0
        el = time.time() - t0
        if quiet >= quiet_reads and el >= min_seconds:
            print(f"    [{label}] editor idle after {el:.0f}s (cpu {cpu:.1f}%)", flush=True)
            return el
        if el > timeout:
            raise TimeoutError(f"editor not idle after {timeout:.0f}s [{label}] "
                               f"(last editor cpu {last:.1f}%)")
        time.sleep(1.0)


bg._wait_idle = _wait_idle

if __name__ == "__main__":
    sys.exit(bg.main())