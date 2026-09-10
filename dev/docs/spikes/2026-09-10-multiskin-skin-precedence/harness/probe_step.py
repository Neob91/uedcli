"""Small console driver for the live probe — send exec lines to an ephemeral UED22 container and
print the editor-log tail each produced.

    python3 probe_step.py <container> '<EXEC LINE>' ['<EXEC LINE>' ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.driver import Driver  # noqa: E402

d = Driver(sys.argv[1])
for line in sys.argv[2:]:
    off = d.log_size()
    d.exec(line)
    tail = d.read_log_since(off)
    print(f"$ {line}\n{tail.strip()[-3000:]}\n{'-' * 60}")
