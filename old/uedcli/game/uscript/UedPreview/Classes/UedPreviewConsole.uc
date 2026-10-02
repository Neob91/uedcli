//=============================================================================
// UedPreviewConsole — self-establishes the preview link with NO keyboard input.
//
// Ported (minimal) from uplayctl's UPlayCtlConsole (the proven reference — uedcli
// has NO runtime/build dependency on uplayctl; spec D1). The engine instantiates
// the class named by the game ini's `Console=` ONCE at viewport creation; the SAME
// object survives every level travel (Viewport-owned, not level-owned), so it is
// the one place a link can be (re-)spawned on every map with no keypress and no
// ?Mutator=. NotifyLevelChange does NOT fire for the initial level, so Tick polls
// on a ~1s throttle instead: whenever the level is possessed and no link exists,
// spawn one. UedPreviewLink's own PostBeginPlay then applies the D9 preview state
// (freeze + noclip + clean) at possession — before uedcli ever connects.
//
// Generic: `Console` is Engine.Console; this file names only Engine.* classes.
//=============================================================================
class UedPreviewConsole extends Console;

var float CheckAccum;

event Tick( float Delta )
{
    Super.Tick(Delta);
    CheckAccum += Delta;
    if ( CheckAccum < 1.0 ) return;
    CheckAccum = 0.0;
    if ( Viewport == None || Viewport.Actor == None ) return;   // not possessed yet
    if ( HasLink() ) return;
    Viewport.Actor.Spawn(class'UedPreview.UedPreviewLink');
    Log("UedPreviewConsole: spawned UedPreviewLink");
}

function bool HasLink()
{
    local UedPreviewLink L;
    ForEach Viewport.Actor.AllActors(class'UedPreview.UedPreviewLink', L)
        return True;
    return False;
}
