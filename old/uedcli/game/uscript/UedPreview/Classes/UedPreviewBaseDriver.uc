//=============================================================================
// UedPreviewBaseDriver — the per-substrate frame adapter (spec D6). The clean uses
// ONLY stock Engine fields, so it works on any UE1 substrate with NO game-typed
// compile — the generic path spawns THIS class directly. The split:
//  - Stock levers (Weapon/bBehindView/FlashScale/FlashFog/myHUD) cover generic
//    games — myHUD is the stock Engine.PlayerPawn HUD ref, so nulling it hides the
//    HUD on games that draw through it (Unreal/UT).
//  - HudHideCommands is only for a game whose HUD escapes myHUD (DeusEx draws its
//    HUD through its own window framework): semicolon-separated console commands
//    run on the pawn (e.g. "ShowHud 0"), read from the active game ini.
// (Spike 2026-08-04-generic-hud-hide.)
//=============================================================================
class UedPreviewBaseDriver extends Actor;

// Per-substrate HUD-hide: semicolon-separated console commands run on the pawn.
// Empty on games the stock clean already covers; "ShowHud 0" on DeusEx. Config'd
// (no config group -> the active game ini) so a substrate needs no typed subclass
// just to hide its HUD.
var config string HudHideCommands;

// Hide everything that would dirty a preview frame. The stock levers below are the
// engine's OWN render gates (verified stock Engine.PlayerPawn/Pawn fields), so they
// hide the first-person weapon + stock HUD + damage flash + force first-person on any
// UE1 game; HudHideCommands adds the HUD hide for a game whose HUD escapes myHUD.
function CleanFrameForPreview(PlayerPawn P)
{
    local string rest, one;
    local int i;

    P.Weapon = None;                 // Super.RenderOverlays draws the viewmodel iff != None
    P.myHUD = None;                  // stock Engine.PlayerPawn HUD ref — hides the HUD on games that draw through it (no-op on DeusEx)
    P.bBehindView = False;           // force first-person (vs a conversation cam)
    P.FlashScale = vect(1,1,1);      // 1,1,1 = neutral (0,0,0 would be full white)
    P.FlashFog = vect(0,0,0);

    rest = HudHideCommands;
    while (rest != "")
    {
        i = InStr(rest, ";");
        if (i == -1) { one = rest; rest = ""; }
        else { one = Left(rest, i); rest = Mid(rest, i + 1); }
        while (Len(one) > 0 && Left(one, 1) == " ") one = Mid(one, 1);
        while (Len(one) > 0 && Right(one, 1) == " ") one = Left(one, Len(one) - 1);
        if (one != "") P.ConsoleCommand(one);
    }
}

// The driver is spawned at the player's location, so its inherited Actor default
// (DrawType=DT_Sprite, Texture=S_Actor, bHidden=False) would render the generic
// actor sprite in every preview frame. Hide it — like the link (Info->bHidden=True)
// — so the driver that CLEANS the frame doesn't itself dirty it. Subclasses inherit.
defaultproperties
{
    bHidden=True
}
