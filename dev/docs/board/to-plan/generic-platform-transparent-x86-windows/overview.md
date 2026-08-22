+++
priority = "p2"
kind = "implement"
summary = "Generic platform-transparent x86-Windows runtime for game + editor (FEX on arm, native on x86)"
+++

# Generic platform-transparent x86-Windows runtime for game + editor (FEX on arm, native on x86)

One wrapper that runs an x86 Windows program (DeusEx.exe or unrealed.exe) under the
host-appropriate x86-execution engine, transparently. Reused by `level preview --game` and
`level materialize`. Owner ruling (2026-08-06): this is **not** a fallback and does not violate
no-env-switching — the logic is identical, only the x86 substrate adapts, the way Docker already
picks native-vs-qemu.

## Why

`level materialize` drives UnrealEd in `linux/amd64` under Docker. On arm64 that runs via qemu-i386,
which **deterministically GPFs** in `SyntaxHighlighting::AddQuote` (AkelEdit code-editor control)
during editor startup — the editor never reaches ready, so materialize fails on every arm host.

Proven this session: the GPF is a **qemu-i386 misemulation bug, not an UnrealEd bug**. The identical
`unrealed.exe` under **FEX + wine-10** on the same arm64 host runs that code path with no access
violation, completes full engine init, loads all `EditPackages`, and opens its windows — including
the Script Editor (`WCodeFrame`), the window that GPFs under qemu. (The only remaining stop was a
Mesh-browser `RenDev` viewport assertion, which materialize never triggers.)

## Shape (to spec)

- A multi-arch runtime image: arm64 variant = FEX + wine-10 x86 userland (cf.
  `fextest-wine10-ready`); amd64 variant = native wine. Same tag; the arch variant's entrypoint uses
  the right engine. uedcli invokes it identically — no arch branch in uedcli code.
- A parametrized entrypoint + Python launcher generalizing today's `ensure_editor` (editor) and the
  game bring-up in `preview_game.py` / `game-entrypoint.sh`: wine prefix, `DISPLAY`/Xvfb,
  esync/fsync, dll overrides, crafted ini + `[Core.System] Paths`, package/asset mounts, the
  wedge-relaunch loop, and a ready signal (editor window vs `:7777` bind).
- Consumers: `level materialize` (unrealed.exe; needs a headless render device, no browser windows)
  and `level preview --game` (DeusEx.exe; boots to `:7777`, renders a frame).

## Open questions / risks

- Game-under-FEX+wine-10 was only ever taken to the boot banner in spikes (blocked then by a retail
  CD check + a 6 GiB cap, now lifted to 16 GiB). End-to-end `:7777` + frame under FEX still needs
  validation for the `--game` half.
- Materialize under FEX needs a headless render device (SoftDrv) configured and the startup browser
  viewports suppressed so `RenDev` never asserts.
- x86 variant (native wine) is assumed to run both exes cleanly (no emulation); confirm.

Evidence + throwaway harness this session under `.claude/` (FEX editor container `fex-ed`, X host
`xdisp`, screenshots). Not yet pinned to a committed spike.
