+++
priority = "p3"
kind = "implement"
summary = "The typed-driver path (hUCC gate, `typed_driver` row field, the DeusEx reference driver) was removed as cruft. Re-add all of it if a game ever needs typed HUD/field access the base driver's stock levers + HudHideCommands can't reach."
+++

# Re-add the typed-driver path if a game ever needs typed field access

The generic base driver hides every shipped substrate's frame with stock Engine fields
(`Weapon`/`myHUD`/`bBehindView`/`FlashScale`/`FlashFog`) plus per-substrate `HudHideCommands`
console commands (DeusEx: `"ShowHud 0"`). No game needs typed field access, so the typed-driver
machinery was **removed as cruft** (no-cruft: no dormant opt-in):

- `preview_game.SUBSTRATES` no longer has a `typed_driver` field; `ensure_image` no longer gates on
  the v469 hUCC toolchain (the image is always the engine-only regular-UCC build).
- The reference `UedPreviewDeusExDriver.uc` (package `UedPreviewDX`) and the `uedcli/game/inputs/`
  hUCC provisioning are deleted, with their build/staging references.

The link keeps a **generic** optional override: `UedPreviewLink.var config string SubstrateDriverClass`
(empty → spawn the base driver). Nothing writes it today.

If a future substrate needs typed access, re-introduce: (1) a typed driver package subclassing
`UedPreviewBaseDriver`, (2) the hUCC toolchain + an `ensure_image` gate, (3) `build.sh` compiling the
typed package, (4) `game-entrypoint.sh` writing `SubstrateDriverClass` into the game ini. Wire ALL of
it or exit 2 if the field is set-but-unsupported — never degrade silently to the base driver.
