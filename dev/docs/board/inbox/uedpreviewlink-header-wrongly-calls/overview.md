+++
priority = "p3"
kind = "debug"
summary = "UedPreviewLink header wrongly calls bCheatsEnabled a DeusEx-added field"
+++

# UedPreviewLink header wrongly calls bCheatsEnabled a DeusEx-added field

`uedcli/game/uscript/UedPreview/Classes/UedPreviewLink.uc` header comment:

> Generic: names only Engine.* (NB `bCheatsEnabled` is a Deus-Ex-added field on this install's
> Engine.PlayerPawn — spec D7 gate-fold caveat for other games).

`bCheatsEnabled` is **own-declared by `Engine.PlayerPawn`**, not added by DeusEx — verified by decoding
`uned/UED22/Engine.u` (v69) and retail `dxreal/system/Engine.u` (v68); both have it. So the noclip path
(`bCheatsEnabled = True; Ghost()`) is already generic, and the D7 caveat as written is wrong.

Evidence + pin: `dev/docs/spikes/2026-08-04-generic-hud-hide/` (schema table + `test_generic_hud_fields_are_stock.py`).

Fix (owner's call, touches a code comment + a `direction/` caveat): correct the `UedPreviewLink.uc`
header, and reword the spec/`direction` D7 gate-fold caveat that repeats the claim.
