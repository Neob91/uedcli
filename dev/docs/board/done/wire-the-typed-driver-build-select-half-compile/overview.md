+++
priority = "p3"
kind = "implement"
summary = "The typed-driver path (hUCC gate, `typed_driver` row field, the DeusEx reference driver) was removed as cruft. Re-add all of it if a game ever needs typed HUD/field access the base driver's stock levers + HudHideCommands can't reach."
+++

# Re-add the typed-driver path if a game ever needs typed field access

The generic base driver hides every shipped substrate's frame with stock Engine fields plus
per-substrate `HudHideCommands`. No game needs typed field access, so the typed-driver machinery
(`preview_game.SUBSTRATES`'s `typed_driver` field, the v469 hUCC `ensure_image` gate, the reference
`UedPreviewDeusExDriver.uc`, `uedcli/game/inputs/` hUCC provisioning) was **removed as cruft**. The
link keeps a generic optional override (`UedPreviewLink.var config string SubstrateDriverClass`,
empty → base driver), unwritten today. If a future substrate needs typed access, re-introduce a typed
driver package + hUCC toolchain + `build.sh`/`game-entrypoint.sh` wiring, all-or-exit-2 — never a
silent fallback to the base driver.
