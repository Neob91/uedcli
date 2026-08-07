+++
priority = "p2"
kind = "implement"
summary = "ued-x86-runtime: reproducible arm64 FEX image build + x86 native variant verification"
+++

# ued-x86-runtime: reproducible arm64 FEX image build + x86 native variant verification

The FEX editor runtime is wired in and PROVEN working: `ensure_editor` → `uned/docker-compose.yml`
image `ued-x86-runtime` → `uned/entrypoint.sh` + `uned/wine-fex-shim.sh` (the `run_x86` seam). On
this arm64 host, `level materialize` boots UnrealEd under FEX+wine-10 and produces an H3-verified
`.dx` end-to-end. What is NOT done is making the runtime IMAGE build from scratch — it is a hand-built
snapshot, so a fresh machine can't reproduce it.

## Out-of-box status (what a clean checkout gets)

- **Works out-of-box** — the dev toolchain: `bin/test`, `bin/uedcli`, and `level preview --native`
  need only `python3.12` on PATH + Docker + network. The Rust ext builds in a container automatically
  (`dev-container/Dockerfile`) and installs into the venv.
- **Does NOT work out-of-box** — `level materialize` (and `--game`) on arm64: it needs the
  `ued-x86-runtime` image, which today is a SNAPSHOT (see U4). A clean checkout can't build it.

## U4 — reproducible arm64 FEX base (the blocker)

`uned/Dockerfile.fex` bakes the substrate (`/opt/UED22`, scripts, the `libXt.so.6` wmctrl fix, the
`wine` shim, the wine-10 ENV) onto `ARG BASE=ued-x86-wine10-base:latest`. That base was the hand-made
snapshot `fex-editor-ready` (FEX + a pinned wine-10 x86 userland + native arm64 X tools + a
pre-initialised `/wineprefix32c`). It has no committed Dockerfile. Build `ued-x86-wine10-base` from
scratch (a `bin/` script should build+pin it):

1. **FEX** — from the `fex-emu` apt PPA (`ppa.launchpadcontent.net/fex-emu/fex/ubuntu`): `FEXInterpreter`,
   `FEXBash`. Plus an **x86 RootFS** for FEX (a Debian/Ubuntu x86 userland — the snapshot used an
   exported `dtools-rootfs`; a reproducible build should `debootstrap`/extract one and set FEX
   `Config.json` `RootFS`).
2. **wine-10 x86 userland** — download the winehq `wine-stable` **10.0** debs (amd64 + i386) and
   `dpkg-deb -x` each into **BOTH** the RootFS **and** the container's real `/` (FEX serves RootFS
   files only to the ELF loader; wine's runtime guest `open()` for PE dlls hits the real fs — miss it
   and wine dies `could not load kernel32.dll c0000135`). **Pin exactly 10.0** — `winehq-stable` now
   resolves to 11.0. Record the deb shas.
3. **Native arm64 X tools** — `Xvfb xdotool fluxbox wmctrl xclip x11-utils libXt6` — install BEFORE
   the raw `dpkg-deb -x` of the wine userland, which otherwise poisons apt's resolver (the current
   `Dockerfile.fex` `xtlibs` stage is a workaround for exactly this; the reproducible base should fold
   it in and drop that stage).
4. Pre-init the `WINEARCH=win32 WINEPREFIX=/wineprefix32c` prefix (`wineboot -u` under FEX).

Recipe evidence: `dev/docs/spikes/2026-08-04-deusex-fex-wine10-rpcss/harness/` (setup_all.sh +
README), `dev/docs/spikes/2026-08-06-materialize-under-fex/` (SoftDrv + live-pid + X-tools facts).
**Cost:** the base is ~36 GB; the from-scratch build needs real disk headroom (this host was 94-97%
full, which blocked it).

## U3 — x86_64 native-wine variant

`uned/Dockerfile` (native wine) is the x86_64 variant of the same tag. The shared `entrypoint.sh` is
arch-agnostic (uniform `wine` launch; window-owner pid via `xdotool getwindowpid`). NOT exercised on
an x86 host — on arm64 the amd64 image runs under qemu and GPFs (the bug this routes around). Verify
`level materialize` on a real x86_64 host: the native `wine` launch, the xdotool pid capture, H3.

Ref: board `to-plan/generic-platform-transparent-x86-windows` (editor half built; `preview --game`
half is separate, per `inbox/game-preview-game-under-fex-fix-startup-at-root`).
