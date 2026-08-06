+++
priority = "p2"
kind = "implement"
summary = "ued-x86-runtime: reproducible arm64 FEX image build + x86 native variant verification"
+++

# ued-x86-runtime: reproducible arm64 FEX image build + x86 native variant verification

The FEX editor runtime is wired in (`ensure_editor` → `uned/docker-compose.yml` image
`ued-x86-runtime` → `uned/entrypoint.sh` + the `wine` run_x86 shim). Two pieces remain:

## U4 — reproducible arm64 FEX base

`uned/Dockerfile.fex` bakes the substrate (`/opt/UED22`, scripts, the `libXt.so.6` wmctrl fix, the
`wine` shim) onto a base image `ARG BASE`. For the demo the base was the pre-existing snapshot
`fex-editor-ready:latest` (FEX + a pinned wine-10 x86 userland + native arm64 X tools + the
`/wineprefix32c` prefix). That snapshot is not reproducible. Build a `ued-x86-wine10-base` image
from scratch: FEX, the pinned wine-10 x86 debs (record shas), and — per the spike — install the
arm64 X tools (Xvfb/xdotool/fluxbox/wmctrl/xclip/libXt) BEFORE the raw `dpkg-deb -x` of the wine
userland, which otherwise breaks apt. A `bin/` script should build+pin it. Note: the base is ~36 GB;
building from scratch needs disk headroom this host lacked (94% full).

## U3 — x86_64 native-wine variant

`uned/Dockerfile` (native wine) is the x86_64 variant of the same tag. The shared `entrypoint.sh` is
now arch-agnostic (uniform `wine` launch; window-owner pid via `xdotool getwindowpid`). This was NOT
exercised on an x86 host — on arm64 the native amd64 image runs under qemu and GPFs (the very bug
this work routes around). Verify `level materialize` on a real x86_64 host: the native `wine` launch,
the xdotool pid capture, and the H3 verify.

Ref: board item `to-plan/generic-platform-transparent-x86-windows` (the editor half is now built; the
`level preview --game` half is separate).
