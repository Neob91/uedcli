+++
priority = "p2"
kind = "debug"
summary = "Generic base-driver clean cannot hide the DeusEx HUD; ShowHud exec is a no-hUCC seam"
+++

# Generic base-driver clean cannot hide the DeusEx HUD; ShowHud exec is a no-hUCC seam

Spike `dev/docs/spikes/2026-08-04-generic-hud-hide/` asked whether `CleanFrameForPreview` could be
generic (stock `Engine.*` fields only), dropping the per-game driver. **Verdict: PARTIAL.**

- A stock-field clean (`Weapon=None`, `bBehindView=False`, `FlashScale=vect(1,1,1)`) hides the
  first-person **weapon** + flash on any UE1 game — `DeusExPlayer.RenderOverlays` draws the weapon via
  `Super.RenderOverlays` gated on stock `Weapon`.
- It does **not** hide the DeusEx **HUD**: DeusEx renders the HUD through its own `rootWindow`
  (`DeusExRootWindow`), not stock `PlayerPawn.myHUD`, so `myHUD=None` is a no-op there. Hiding it needs
  a DeusEx lever. So the base driver's generic default cannot be HUD-complete on DeusEx; a per-game
  hook stays.

Actionable: `ShowHud` is an **`exec function`** on `DeusExPlayer`, so `P.ConsoleCommand("ShowHud 0")`
hides the HUD with **no compiled DeusEx driver** — an engine-only package (regular UCC) reaches it.
That removes the `hUCC`-only `UedPreviewDX` build from the HUD path (see
`level-preview-game-blocked-on-this-box-two`). Candidate: keep a thin per-substrate string
(`hud_hide_console_cmd = "ShowHud 0"`) instead of a typed driver. Owner's call on the design.

Full mechanism, schema, and the generic `CleanFrameForPreview` text: the spike doc.
