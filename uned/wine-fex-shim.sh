#!/bin/sh
# run_x86 shim (arm64 FEX substrate): make `wine` on PATH run the x86 wine-10 userland under FEX, so
# every wine call — the editor launch AND the offline `UCC.exe` the H3 verify runs via `docker exec
# … wine …` — is transparently emulated. This is the ONE arch-aware seam, and it lives in the image;
# uedcli calls `wine` identically on every host (on x86 hosts `wine` is native and this shim is
# absent). The wine-10 env (WINEPREFIX/WINEARCH/WINELOADER/…) comes from the image ENV, which
# FEXBash inherits. Absolute wine path, so no recursion through this shim.
exec FEXBash -c 'exec /opt/wine-stable/bin/wine "$@"' fex-wine "$@"
