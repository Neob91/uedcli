# Spec — generic platform-transparent x86-Windows runtime

## What it is

One runtime that runs an x86 Windows program (`DeusEx.exe` or `unrealed.exe`) under wine in a
container, choosing the x86-execution engine by host arch **transparently**: FEX + wine-10 on arm64,
native wine on x86. Same program, same logic, same output — only the substrate adapts. Reused by
`level materialize` (editor) and `level preview --game` (game), replacing today's two divergent
container paths (`uned/` + `ensure_editor`, and `game/` + `game-entrypoint.sh`).

Owner ruling (2026-08-06): substrate adaptation under identical logic is not a fallback and does not
violate no-env-switching.

## Why (proven this session)

`level materialize` runs UnrealEd in `linux/amd64`. On arm64 that is qemu-i386, which
**deterministically GPFs** in `SyntaxHighlighting::AddQuote` (AkelEdit code-editor control) during
editor startup — the editor never reaches ready, so materialize fails on every arm host. The GPF is a
qemu misemulation, not an UnrealEd bug: the identical `unrealed.exe` under **FEX + wine-10** ran that
path with no access violation, completed full engine init, loaded all `EditPackages`, and opened the
Script Editor (`WCodeFrame`) window.

## Design

**Image** — one multi-arch tag (e.g. `ued-x86-runtime`):
- arm64: FEX (`FEXInterpreter`/`FEXBash`) + a pinned wine-10 x86 userland + x86 RootFS (the
  `fextest-wine10-ready` recipe: `dpkg-deb -x` the pinned wine-10 debs into both the RootFS and the
  real fs, since FEX serves RootFS files only to the ELF loader).
- amd64: native wine.
- Both carry a native Xvfb + X tools and expose one interface. The only arch-aware line is a
  `run_x86` shim — `FEXBash -c "wine …"` on arm, `wine …` on amd64 — inside the image (substrate),
  never in uedcli.

**Launcher** (Python; generalizes `ensure_editor` + the game bring-up):
- Start the container with the program's mounts (packages/assets), memory, network.
- Bring up Xvfb (native arm64, 24-bpp — 32-bpp won't start), `DISPLAY` local.
- Craft the engine ini `[Core.System] Paths` from the mounts (reuse `replace_core_system_paths`).
- Launch the target `.exe` via `run_x86` with `WINEESYNC/WINEFSYNC` + dll-overrides.
- Wedge-relaunch loop (generalize `UED_LAUNCH_TRIES`/`UED_WEDGE_S`).
- Wait on a **ready signal** passed by the caller: editor = window resolves and is drivable (no
  Critical Error); game = `:7777` bound.
- Expose the driver interface (docker exec + `wine_ctl`) for console commands.

**Consumers** pass only what differs — the `.exe`, ini/Paths, mounts, ready signal, commands:
- `level materialize`: `unrealed.exe`, editor packages, crafted `unrealtournament.ini`,
  ready=editor-drivable, drives `MAP IMPORTADD/REBUILD/SAVE`; headless render device (SoftDrv), no
  browser windows.
- `level preview --game`: `DeusEx.exe`, game content, ready=`:7777`, renders a frame.

## Unknowns — spiked 2026-08-06

- **U2 — materialize under FEX+wine-10: RESOLVED (works).** Spike
  `dev/docs/spikes/2026-08-06-materialize-under-fex/`: the editor boots, drives, and materializes a
  real 79 KB level → valid `.dx` under FEX, no object-system corruption; `MAP LOAD`/`ULevel::PostLoad`
  on real content is fine. Concrete build inputs: (a) render device MUST be `SoftDrv`
  (`WindowedRenderDevice`/`RenderDevice`/`GameRenderDevice`) — else the Mesh browser asserts `RenDev`
  and Ignoring drops to Recovery Mode; (b) the real `wine_ctl`/`Driver` interface is a drop-in once
  `/run/uned.pid` holds the **live `FEXInterpreter` pid** (the `unrealed.exe` PE stub is `<defunct>`);
  (c) the FEX image needs arm64 X tools installed cleanly (the raw `dpkg-deb -x` wine userland breaks
  apt — install X tools BEFORE it). Still to build: a FEX-aware `ensure_editor` (create the FEX
  container with the resource mounts + crafted SoftDrv ini + Xvfb/fluxbox + live pid), after which the
  literal `run_materialize` + H3 verify runs unchanged.
- **U1 — game under FEX+wine-10: root-caused, path found.** Spike
  `dev/docs/spikes/2026-08-06-game-under-fex/`: the "corruption" is NOT a FEX/render-device
  incompatibility — our `room.dx` `PostLoad`s cleanly via the boot `LoadMap` path. The crash is
  confined to the runtime menu→map `ClientTravel` (big menu graph resident + load/GC). Build path:
  load the preview map via the boot path (as `Entry.dx`), not a runtime travel. A rendered frame
  wasn't captured (blocked by the environmental boot-IPC wedge, worsened by parallel memory
  contention — retry-beatable per `game-entrypoint.sh`).
- **U3 — x86 variant (native wine)** runs both exes cleanly (assumed; confirm, may need an x86 host).
- **U4 — reproducible FEX wine-10 userland build** (a `bin/` script; pin the wine-10 deb shas; install
  arm64 X tools in the image before the raw wine extraction — see U2c).

## Non-goals

- Replacing native x86 execution on x86 hosts (they use native wine, no emulation).
- Changing T3D/materialize logic — only how the editor is executed.
