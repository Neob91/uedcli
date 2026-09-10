"""`MAP IMPORTADD` a host T3D into an ephemeral container and print the resulting `MAP EXPORT`
readback (the editor silently drops an object ref it cannot bind, so the readback is the proof).

    python3 import_t3d.py <container> <host.t3d> [--fresh]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli import xfer  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

d = Driver(sys.argv[1])
src = sys.argv[2]
if "--fresh" in sys.argv:
    d.map_new()
off = d.log_size()
cpath = xfer.cp_in(d.container, src, ext="t3d")
d.exec(f"MAP IMPORTADD FILE={to_z_path(cpath)}")
exp = xfer.work_path("t3d")
d.exec(f"MAP EXPORT FILE={to_z_path(exp)}")
host_out = src + ".export"
xfer.cp_out(d.container, exp, host_out)
txt = Path(host_out).read_text()
for m in re.finditer(r"Begin Actor Class=(?!Brush|LevelInfo)\w+.*?End Actor", txt, re.S):
    print(m.group())
print("---- log ----")
print(d.read_log_since(off).strip()[-2000:])
