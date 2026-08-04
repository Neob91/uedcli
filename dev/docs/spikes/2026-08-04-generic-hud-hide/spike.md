# Spike: generic (stock-Engine-field) HUD + weapon hide for `level preview --game`

**Question.** Can the preview frame be cleaned — HUD + first-person weapon hidden — using ONLY stock
`Engine.PlayerPawn`/`Pawn`/`Actor` fields (no game-specific class or method), so a single generic
`CleanFrameForPreview` in the base driver works on any UE1 substrate and `--game` needs no per-game
driver (and no `hUCC`)?

**Verdict: PARTIAL.** The generic stock-field clean hides the first-person **weapon** (and the damage
flash / third-person view) on any UE1 game — it uses the exact stock levers the engine's own render
path checks. It does **not** hide the **DeusEx HUD**: DeusEx draws its HUD through its own window
framework (`rootWindow`), not the stock `PlayerPawn.myHUD` path, so `myHUD = None` has no effect on it.
Hiding the DeusEx HUD needs a DeusEx-specific lever (`ShowHud`/`rootWindow`) — i.e. a per-game driver.
So a purely-generic base-driver clean is sufficient for the weapon but **insufficient for the HUD on
DeusEx**, the tool's primary substrate.

## 1. Schema — every proposed field IS stock (necessary condition: PASS)

Decoded own-declared properties from the committed `uned/UED22/Engine.u` (`uedcli.uprops`):

| Field | Own-declared by | Kind |
|-------------------------------|---------------------|----------------|
| `myHUD` | `Engine.PlayerPawn` | Object |
| `FlashScale` | `Engine.PlayerPawn` | Struct(vector) |
| `FlashFog` | `Engine.PlayerPawn` | Struct(vector) |
| `DesiredFlashScale` | `Engine.PlayerPawn` | Float |
| `bCheatsEnabled` | `Engine.PlayerPawn` | Bool |
| `Weapon` | `Engine.Pawn` | Object |
| `bBehindView` | `Engine.Pawn` | Bool |
| `EyeHeight` / `BaseEyeHeight` | `Engine.Pawn` | Float |
| `Physics` | `Engine.Actor` | Byte |
| `bHidden` / `bCollideWorld` | `Engine.Actor` | Bool/Bool |

All stock. That the spike link variant (`harness/uscript/.../UedPreviewLink.uc`) **compiles clean against
`Engine.u` with the regular UED22 UCC** — referencing `myHUD`, `Weapon`, `bBehindView`, `FlashScale`,
`FlashFog`, `GiveTo`, `bWeaponUp`, `ConsoleCommand` — is a second, independent proof they are
engine-level. Pinned: `test_generic_hud_fields_are_stock.py`.

**Correction to the codebase.** `UedPreviewLink.uc`'s header (and spec D7 caveat) call `bCheatsEnabled`
"a Deus-Ex-added field on this install's `Engine.PlayerPawn`". It is **not** — it is own-declared by
`Engine.PlayerPawn` in both UED22's `Engine.u` (v69) and retail DeusEx's `Engine.u` (v68). The noclip
path (`bCheatsEnabled = True; Ghost()`) is therefore already generic. (Filed to the board.)

## 2. Mechanism — why generic hides the weapon but not the DeusEx HUD (from DeusEx.u source)

Read out of the retail `DeusEx.u` UnrealScript source (`uedcli.uprops._class_script_source`) — this is
the actual game code that decides what draws, i.e. ground truth, not a model of it:

**Weapon viewmodel — the generic lever IS the engine's own lever.**
```
// DeusExPlayer
event RenderOverlays( canvas Canvas )
{
    Super.RenderOverlays(Canvas);                 // stock PlayerPawn: draws the viewmodel iff Weapon != None
    if (!IsInState('Interpolating') && !IsInState('Paralyzed'))
        if ((inHand != None) && (!inHand.IsA('Weapon')))
            inHand.RenderOverlays(Canvas);        // ONLY non-weapon in-hand items
}
```
A held **weapon** is drawn by `Super.RenderOverlays` (stock `PlayerPawn`), gated on the stock `Weapon`
field. So generic `Weapon = None` hides it. The `inHand` branch explicitly skips weapons
(`!inHand.IsA('Weapon')`), so it only matters for a non-weapon tool in hand — the sole weapon-hide
residue a stock clean can't reach, and one a fresh preview pawn rarely has.

**HUD — drawn OUTSIDE the stock `myHUD` path.**
```
// DeusExPlayer
exec function ShowHud(bool bShow)
{
    local DeusExRootWindow root;
    root = DeusExRootWindow(rootWindow);
    if (root != None) root.ShowHud(bShow);        // the HUD lives in rootWindow, NOT myHUD
}
```
DeusEx's HUD (health, augs, ammo, compass, belt) is a `DeusExRootWindow` render, controlled by
`ShowHud`/`rootWindow`. Stock `myHUD` is never used for it, so nulling `myHUD` does nothing to the
DeusEx HUD. Hiding it requires the DeusEx lever `ShowHud(False)` — a game-specific call.

**Genericity across UE1.** The weapon result ports to any UE1 game (stock `Weapon` + stock
`RenderOverlays`). The HUD result does not generalise cleanly: stock Unreal/UT draw their HUD via
`myHUD.PostRender`, so `myHUD = None` would hide it there — but any game that replaces the HUD with its
own window/canvas framework (DeusEx, and mods like it) escapes the stock `myHUD` path. Since DeusEx is
the tool's substrate, the base-driver clean cannot be HUD-complete without a per-game hook.

`ShowHud` being an **`exec function`** means the DeusEx HUD can be hidden with no compiled DeusEx driver
at all — `P.ConsoleCommand("ShowHud 0")` over the existing link reaches it (engine-only package, regular
UCC). That is a cheaper per-game seam than the current typed `UedPreviewDX` driver (which needs `hUCC`),
though it is still DeusEx-specific.

## 3. The generic `CleanFrameForPreview` that works (for what it can reach)

```uc
// stock Engine fields only — hides weapon + flash + forces first-person; HUD NOT covered on DeusEx
function GenericClean(PlayerPawn P)
{
    P.myHUD = None;              // hides the HUD on stock-myHUD games (Unreal/UT); NO-OP on DeusEx
    P.Weapon = None;             // hides the first-person weapon on any UE1 game
    P.bBehindView = False;       // forces first-person (belt-and-suspenders vs a conversation cam)
    P.FlashScale = vect(1,1,1);  // 1,1,1 = no damage/pickup flash (0,0,0 would be full white)
    P.FlashFog = vect(0,0,0);
}
```
Note `FlashScale = vect(1,1,1)`, not `vect(0,0,0)`: in UE1 `FlashScale` is a multiplier where `1` is
neutral and `0` is full-screen white. The shipped DeusEx driver sets `vect(0,0,0)` alongside
`DesiredFlashScale = 0`, which the DeusEx flash tick reconciles; a generic clean should use neutral
`1,1,1`.

## 4. Live render — status

Harness is complete and committed (`harness/`): `build_pkg.sh` compiles the engine-only spike
`UedPreview.u` with the regular UED22 UCC (**done — 0 errors**, `harness/UedPreview.u`); `boot_game.sh` +
`run_render.sh` boot retail v68 `DeusEx.exe` (SoftDrv, headless :99) with `room.dx`; `drive.py` captures
three frames in one boot — baseline → `Clean generic` → `Clean dxhud` (`ShowHud 0`) — of the same room
and pose (eye at room centre looking +X at the Amark-marked wall). It gives a weapon first
(`Give DeusEx.WeaponPistol`) so the baseline frame shows a viewmodel to hide.

The three PNGs were **not captured on this box.** Every `DeusEx.exe` boot wedges at the "Deus Ex
(Starting)" splash — `DeusEx.log` frozen at the 21-line CPU-detect banner, thread state `Ssl`, ~0% CPU —
the known intermittent wine startup deadlock, which here fires on essentially every launch and does not
clear on relaunch (18-try loop, both `WINEESYNC` modes, reduced CPU set, smaller window: all wedge).
Contributing cause (as the owner flagged): the container's cgroup is hard-capped at 6 GiB (rootless
slice ceiling; `--memory` cannot raise it), and amd64 wine under arm64 qemu emulation plus DeusEx's
2 GiB forced working set thrashes it (`pgmajfault` climbing into the ~900k range during boot).

This is an **environment limitation, not a harness or hypothesis limitation** — board item
`engine-only-uedpreview-via-regular-ucc-renders` recorded a successful engine-only render of this exact
kind on 2026-08-03 (link bound ~12s), so the harness renders when the box has the headroom the emulated
boot needs. The verdict rests on the game's own render code plus the schema, both committed and pinned;
the render is the confirmation step. Reproduce with `harness/run_render.sh <out-dir>` on a box that can
boot the game (warm-prefix `dx-lum-uned-game` image, or a larger cgroup memory ceiling).

## Files

- `harness/uscript/UedPreview/Classes/` — engine-only spike link (`Clean generic` / `Clean dxhud` /
  `Give` wire commands) + console. `build_pkg.sh` → `harness/UedPreview.u` (v69, 0 errors).
- `harness/boot_game.sh`, `harness/drive.py`, `harness/run_render.sh` — boot + capture.
- `test_generic_hud_fields_are_stock.py` — pins §1 against `uned/UED22/Engine.u`. Lives here (not folded
  into `uedcli/tests/test_engine_facts.py`) because that tracked file needs the owner's yes to edit.
