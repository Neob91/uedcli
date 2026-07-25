//=============================================================================
// UedPreviewDeusExDriver — the Deus Ex substrate driver (spec D6/§5). Binds
// DeusEx.u with typed access; lives in its OWN package (UedPreviewDX — it cannot
// be named `DeusEx`, the game's package). Compiling against the real DeusEx.u is
// what verifies these call paths — a wrong field/method fails the build.
//=============================================================================
class UedPreviewDeusExDriver extends UedPreview.UedPreviewBaseDriver;

#exec OBJ LOAD FILE=DeusEx.u

// Clean the preview frame (spec §5, Andrzej 2026-07-15 revision):
//  - ShowHud(False): hides HUD + scope (DeusExPlayer.uc:6525 -> DeusExRootWindow).
//  - NULL the first-person render SOURCES directly: PlayerPawn.RenderOverlays draws the
//    viewmodel only if(Weapon!=None) (PlayerPawn.uc:242); DeusExPlayer.RenderOverlays draws
//    inHand only if set (:4286). Synchronous — no put-away animation (vs PutInHand(None)).
//  - Zero the damage flash; force first-person (a conversation routes the camera to
//    ConCamera via bBehindView — D9's freeze-at-possession makes an active conversation
//    unlikely; this is the belt-and-suspenders).
function CleanFrameForPreview(PlayerPawn P)
{
    local DeusExPlayer dxp;
    dxp = DeusExPlayer(P);
    if (dxp == None) return;
    dxp.ShowHud(False);
    dxp.Weapon = None;
    dxp.inHand = None;
    dxp.DesiredFlashScale = 0;
    dxp.FlashScale = vect(0,0,0);
    dxp.bBehindView = False;
}
