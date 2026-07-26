//=============================================================================
// UedPreviewBaseDriver — ABSTRACT per-substrate adapter (spec D6). The generic
// link never names a game class; anything needing a game's own typed classes
// (HUD/weapon hiding, conversation guard) is a method here, overridden by a
// concrete driver the link spawns BY NAME (DynamicLoadObject). The base is a
// safe no-op so the generic path works on any UE1 substrate.
//=============================================================================
class UedPreviewBaseDriver extends Actor
    abstract;

// Hide everything that would dirty a preview frame (HUD, first-person weapon,
// damage flash, conversation camera). Substrate-typed; generic default: nothing.
function CleanFrameForPreview(PlayerPawn P) {}

// The driver is spawned at the player's location (SpawnDriver → Spawn with no
// location), so its inherited Actor default (DrawType=DT_Sprite, Texture=S_Actor,
// bHidden=False) would render the generic actor sprite floating in every preview
// frame. Hide it — like the link (Info→bHidden=True) — so the driver that CLEANS
// the frame doesn't itself dirty it. Every substrate driver inherits this.
defaultproperties
{
    bHidden=True
}
