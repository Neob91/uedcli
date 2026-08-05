+++
priority = "p2"
kind = "verify"
summary = "Confirm the base driver's `var config string HudHideCommands` actually reads the value the entrypoint writes into DeusEx.ini — the one unverified link in the generic --game HUD-hide."
+++

# Verify HudHideCommands config-var resolves from the active game ini

The generic `level preview --game` hides the DeusEx HUD via `UedPreviewBaseDriver`'s
`var config string HudHideCommands` (set to `"ShowHud 0"`), run through `P.ConsoleCommand`. The host
passes it as `UED_HUD_HIDE`; `game-entrypoint.sh` writes:

```
[UedPreview.UedPreviewBaseDriver]
HudHideCommands=ShowHud 0
```

into the assembled `DeusEx.ini`. `UedPreviewBaseDriver extends Actor` with NO `config(...)` group, so
it relies on a plain `var config` reading from the engine's active (default) game ini — DeusEx.ini
here. This was NOT live-verified (no amd64 container available; see the integration step below).

Verify on a box that can boot the game: build the base-driver-only image, render a DeusEx map, and
confirm the HUD is gone. If the config var does NOT pick up the ini value, the fix is small — either
declare the class `config(System)`/the game ini, or drop the config-var route and send the HUD-hide
command over the wire in `SetupPreviewState` (the batch already threads `window_title`, so a
`hud_hide` field is the same shape). Do not add a fallback that hides both ways silently.

## Also unverified-live: the typed-driver removal (2026-08-04)

The DeusEx typed driver (`UedPreviewDeusExDriver`) was removed; DeusEx now hides its HUD purely via
`HudHideCommands="ShowHud 0"` on the base driver. This is **not live-verified** (the amd64 DeusEx boot
is environmentally blocked here). Two things to confirm in the same render:

- `"ShowHud 0"` runs the SAME exec the typed driver called (`dxp.ShowHud(False)`), so it is
  functionally equivalent — but no live frame confirms the HUD is actually gone yet.
- The removed typed driver also nulled the rare DeusEx `inHand` in-hand-tool ref. The base driver
  does not (it is not a stock field). A fresh preview pawn almost never has one, so this should be a
  no-op — confirm no in-hand tool renders in a DeusEx frame. If one ever does, add its hide to
  `HudHideCommands` (e.g. a `putawaytool`-style exec), not a typed field.
