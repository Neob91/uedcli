# Spike: does `level materialize` work under FEX+wine-10 on arm64? (2026-08-06)

**Question (the owner's gate).** `level materialize` drives UnrealEd in Docker `linux/amd64`; on
arm64 that is qemu-i386, which deterministically GPFs in `SyntaxHighlighting::AddQuote` so the editor
never reaches ready. Session work showed FEX+wine-10 clears that GPF and *opens* the editor — but a
review flagged (blocker #5) that FEX+wine-10 corrupts the object system for the **game**
(`ClientTravel`: `ULevel::PostLoad` AV, `StaticAllocateObject` assertion — spike
`2026-08-04-deusex-cd-bypass-and-game-travel-wall`), and materialize allocates/serializes many
objects too. So: prove a real, verified `.dx` under FEX before building anything.

## TL;DR — YES. UnrealEd materializes under FEX+wine-10 on arm64. The object-system corruption that kills the game does NOT hit the editor.

Drove a real level through the FEX editor end-to-end with **no crash, no assertion**:
`MAP NEW → MAP IMPORTADD (79 KB level T3D) → MAP REBUILD → MAP SAVE` produced a valid **79,521-byte
`.dx`** (magic `c1832a9e`); `MAP LOAD` of it — i.e. `ULevel::PostLoad` on real content, the game's
exact FEX crash point — succeeded, editor stayed alive, and `MAP EXPORT` round-tripped **15 actors**.
Evidence: `evidence/editor-fully-booted-under-fex.png`, `evidence/small-materialized-under-fex.dx`,
`evidence/editor-boot.log`.

## The two facts that make it work

1. **FEX+wine-10 clears the qemu `AddQuote` GPF.** The identical `unrealed.exe` boots through full
   engine init and opens every window, including the Script Editor (`WCodeFrame`) that GPFs under
   qemu. `+seh` shows no `c0000005` anywhere.
2. **Render device MUST be `SoftDrv`, not `OpenGLDrv`.** With the stock `OpenGLDrv` the Mesh browser's
   startup viewport asserts `RenDev` (`WinViewport.cpp:430`, `WBrowserMesh::RefreshViewport`), and
   Ignoring it drops the editor to `[Recovery Mode]` (which cannot `MAP SAVE`). Setting
   `WindowedRenderDevice`/`RenderDevice`/`GameRenderDevice=SoftDrv.SoftwareRenderDevice` in the engine
   ini removes the assertion; the editor boots clean and is fully drivable. `LIBGL_ALWAYS_SOFTWARE=1`
   alone (what the qemu entrypoint sets) does **not** fix it — the device class must change.

## Harness (committed, re-runnable)

Three containers on one docker network (`harness/boot_fex_editor.sh`):
- `xdisp` (native arm64): `Xvfb :99` 24-bpp over TCP — the shared X server. (32-bpp won't start.)
- `driver` (amd64 `dx-lum-uned`): `fluxbox` WM + `xdotool`. Drives the editor **by window title**
  over the shared display (`harness/drive.sh`) — cross-container, since the editor PID lives in the
  FEX container and `wine_ctl`'s PID/`search --pid` resolution doesn't apply. This confirms the
  review's finding #4 (the real driver's PID-based window resolution needs replacing for FEX) and
  shows title-based driving works.
- `fex-ed` (`fextest-wine10-ready`): `FEXInterpreter` + wine-10 runs `unrealed.exe` → `xdisp`.

Package gotcha: use the pristine lowercase engine set (`core.u`/`editor.u`/`fire.u`/`ipdrv.u`); a
copied uppercase `Core.u` collides with `core.u` on wine's case-fold and fails `Can't find edit
package 'Core'`.

## What this does NOT yet prove (→ build phase)

- **Byte-parity** of the materialized `.dx` vs the x86-native editor output (the H3 gate). This host
  is arm-only, so there is no native reference here; the fixture drove BSP to 0 nodes (its brush
  order needs a subtract first), so a representative geometry + parity check belongs in the real
  `level materialize` integration.
- The real path (`ensure_editor` → `Driver` → `_materialize` → `_save_and_swap_verified`) still needs
  wiring to a FEX runtime; its PID-based window resolution must move to title-based (finding #4).

## Not pinned with a test (yet)

Environmental/tooling result (like the parent FEX spikes) — needs FEX + a 6 GB container + an X host,
can't run in CI. Pin the checkable half in the build phase: an H3 byte-parity golden of a real
materialized level.

## Integration progress toward the real `level materialize` path (2026-08-06)

Working toward running the actual `run_materialize` → `Driver` (docker exec `wine_ctl`) code against
a FEX editor. `Driver` assumes editor + Xvfb + `xdotool` + `wine_ctl` + files all in ONE container
(`self.container`), so the real runtime is a single self-contained FEX editor container.

- **Arm64 X tools into the FEX image (solved).** `fextest-wine10-ready`'s apt is broken for new
  installs — the wine-10 userland was `dpkg-deb -x`'d in raw, so the resolver refuses every install
  (even already-present base libs; the held mesa packages poison it). Fix that works: `apt-mark
  unhold` the mesa holds, then **download the deb set and `dpkg -i --force-depends`** (bypass the
  resolver — the runtime libs are actually present). Installed `xvfb xdotool fluxbox wmctrl xclip
  x11-utils x11-xkb-utils xauth` this way. The real runtime image should install X tools cleanly in a
  layer BEFORE the raw wine extraction.
- **Single self-contained container boots + renders** (native arm64 `Xvfb :99` local, FEX editor →
  `:99`), no Critical Error with the SoftDrv ini.
- **`wine_ctl` needs title-based window resolution under FEX (review finding #4, confirmed).** The
  editor window's `_NET_WM_PID` is a FEX/wine internal pid (e.g. 2627), NOT the launcher pid, and the
  `unrealed.exe` PE process shows `<defunct>` while `FEXInterpreter` runs it. So `xdotool search
  --pid` (and the `/run/uned.pid` liveness check) fail. Manual **title-based** driving works and
  already materialized the 79 KB `.dx` above. `_resolve_window`/`_assert_alive` must fall back to
  `xdotool search --name "Unreal"` + window-existence when the pid path yields nothing.
- **Open wrinkle:** in a single container the local `fluxbox` didn't advertise `_NET_ACTIVE_WINDOW`
  (windowactivate failed; frame not maximized), whereas `fluxbox` in a separate driver container
  worked. The `uned` entrypoint runs `fluxbox` successfully in-container, so the recipe exists — a
  startup/config detail to port.

Remaining to a real H3-verified `.dx` under FEX: port the title-based `wine_ctl` + the in-container
`fluxbox`, point `ensure_editor` at the FEX container, run `run_materialize` end-to-end.
