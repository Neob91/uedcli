"""Headless Chromium hard-links libatk-1.0/libatk-bridge-2.0/libatspi (accessibility) through
DT_NEEDED, and this host ships none of them. Headless never uses a11y, so generate no-op stub
shared objects exporting exactly the symbols the binary references -- enough for the dynamic linker.
"""
import os
import re
import subprocess
from pathlib import Path

BIN = os.environ.get("SURFSEL_CHROME") or "/home/agent/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"
OUT = Path(os.environ.get("SURFSEL_LIBS", "_scratch/surfsel/libs"))

undef = subprocess.run(["nm", "-D", "--undefined-only", BIN], capture_output=True, text=True).stdout
syms = [ln.split()[-1] for ln in undef.splitlines() if re.match(r"^\s+U\s+(atk_|atspi_)", ln)]

groups = {
    "libatk-bridge-2.0.so.0": [s for s in syms if s.startswith("atk_bridge_")],
    "libatk-1.0.so.0": [s for s in syms if s.startswith("atk_") and not s.startswith("atk_bridge_")],
    "libatspi.so.0": [s for s in syms if s.startswith("atspi_")],
}

OUT.mkdir(parents=True, exist_ok=True)
for soname, names in groups.items():
    src = OUT / f"stub_{soname.replace('.', '_').replace('-', '_')}.c"
    src.write_text("".join(f"void {n}(void) {{}}\n" for n in names))
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(OUT / soname), "-Wl,-soname," + soname, str(src)], check=True)
    print(f"{soname}: {len(names)} symbols")
