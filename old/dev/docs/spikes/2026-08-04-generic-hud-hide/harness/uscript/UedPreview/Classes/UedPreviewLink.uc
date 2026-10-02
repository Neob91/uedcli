//=============================================================================
// UedPreviewLink — SPIKE VARIANT (2026-08-04-generic-hud-hide).
//
// Copy of game/uscript/.../UedPreviewLink.uc, trimmed to prove/disprove a GENERIC
// (stock-Engine-field-only) HUD+weapon hide. Differences from the shipped link:
//   - No substrate driver. SetupPreviewState applies freeze+noclip but NEVER cleans
//     the frame; the clean is applied on demand by the `Clean <mode>` wire command so
//     ONE boot can capture baseline -> generic -> dxhud incrementally.
//   - `Clean generic`: nulls ONLY stock Engine fields (myHUD, Weapon, bBehindView,
//     FlashScale, FlashFog). This is the candidate GENERIC CleanFrameForPreview.
//   - `Clean dxhud`: the DeusEx game lever for the HUD via the pawn's own exec
//     function — P.ConsoleCommand("ShowHud 0") — with NO DeusEx-typed compile
//     dependency (engine-only package, regular v469 UCC). Reference for what a
//     game-specific driver achieves.
//   - `Give <WeaponClass>`: DynamicLoadObject + Spawn + GiveTo so the baseline frame
//     shows a first-person weapon to test hiding (generic, class named at runtime).
//
// Engine-only: names only Engine.* fields/methods (schema-verified stock).
//=============================================================================
class UedPreviewLink extends TcpLink;

var int CurReqId;

function PostBeginPlay()
{
    Super.PostBeginPlay();
    LinkMode = MODE_Line; ReceiveMode = RMODE_Event;
    if ( BindPort(7777, True) == 0 ) return;
    Listen();
    Log("UedPreviewLink(spike): listening on 7777");
    SetupPreviewState(FindPlayer());
}

// Freeze + noclip only. NO frame clean here (the spike applies it via `Clean`).
function SetupPreviewState(PlayerPawn P)
{
    if (P == None) return;
    P.bCheatsEnabled = True;
    if (P.Physics != PHYS_Flying) P.Ghost();
    P.Level.bPlayersOnly = True;
}

// The candidate GENERIC clean: stock Engine.PlayerPawn/Pawn fields only.
function GenericClean(PlayerPawn P)
{
    P.myHUD = None;                 // Engine.PlayerPawn (stock)
    P.Weapon = None;                // Engine.Pawn (stock) — Super.RenderOverlays draws it iff !=None
    P.bBehindView = False;          // Engine.Pawn (stock)
    P.FlashScale = vect(1,1,1);     // Engine.PlayerPawn (stock) — 1,1,1 = no flash (0,0,0 = full white)
    P.FlashFog = vect(0,0,0);       // Engine.PlayerPawn (stock)
}

event Accepted() { SendText("HELLO uedpreview-spike 1"); }

function string Trim(string s) { while (Len(s)>0 && (Right(s,1)==Chr(13)||Right(s,1)==Chr(10)||Right(s,1)==" ")) s=Left(s,Len(s)-1); return s; }
function string TrimLeft(string s) { while (Len(s)>0 && Left(s,1)==" ") s=Mid(s,1); return s; }
function int NextInt(out string s) { local int i; local string t; s=TrimLeft(s); i=InStr(s," "); if(i==-1){t=s;s="";}else{t=Left(s,i);s=Mid(s,i+1);} return int(t); }
function PlayerPawn FindPlayer() { local PlayerPawn P; foreach AllActors(class'PlayerPawn',P) return P; return None; }
function Reply(string s) { SendText("#"$CurReqId$" "$s); }

event ReceivedLine(string Line)
{
    local PlayerPawn P;
    local vector l;
    local string cmd, rest;
    local int i, sp;
    local class<Weapon> WC;
    local Weapon W;

    Line = Trim(Line);
    if (Left(Line,1) == "#") { sp = InStr(Line," "); CurReqId = int(Mid(Left(Line,sp),1)); Line = TrimLeft(Mid(Line,sp+1)); }
    else CurReqId = 0;
    i = InStr(Line, " ");
    if (i==-1) { cmd=Line; rest=""; } else { cmd=Left(Line,i); rest=Mid(Line,i+1); }

    if (cmd == "Ping") { Reply("Pong"); Reply("OK Ping"); return; }

    P = FindPlayer();
    if (P == None) { Reply("ERR no-player"); return; }

    if (cmd == "GetCurrentLevelName")
    {
        Reply("LevelName "$P.GetURLMap());
        Reply("OK GetCurrentLevelName");
    }
    else if (cmd == "TravelToLevel")
    {
        Reply("OK TravelToLevel "$Trim(rest));
        P.ConsoleCommand("open "$Trim(rest));
    }
    else if (cmd == "Give")
    {
        // Spawn a weapon by runtime-named class and force it into the pawn's hand so the
        // baseline frame shows a first-person weapon overlay to test hiding.
        WC = class<Weapon>(DynamicLoadObject(Trim(rest), class'Class', True));
        if (WC == None) { Reply("ERR unknown-weapon "$Trim(rest)); return; }
        W = Spawn(WC);
        if (W == None) { Reply("ERR spawn-failed "$Trim(rest)); return; }
        W.GiveTo(P);
        W.BecomeItem();
        P.Weapon = W;
        W.GotoState('Active');
        W.bWeaponUp = True;
        Reply("OK Give "$Trim(rest));
    }
    else if (cmd == "Clean")
    {
        rest = Trim(rest);
        if (rest == "generic") { GenericClean(P); Reply("OK Clean generic"); }
        else if (rest == "dxhud") { P.ConsoleCommand("ShowHud 0"); Reply("OK Clean dxhud"); }
        else Reply("ERR unknown-clean-mode "$rest);
    }
    else if (cmd == "PrepareCamera")
    {
        l.X = NextInt(rest); l.Y = NextInt(rest); l.Z = NextInt(rest);
        l.Z -= P.BaseEyeHeight;
        P.SetLocation(l);
        P.ViewRotation.Pitch = NextInt(rest);
        P.ViewRotation.Yaw   = NextInt(rest);
        P.ViewRotation.Roll  = 0;
        Reply("OK PrepareCamera");
    }
    else Reply("ERR unknown-command "$cmd);
}

defaultproperties
{
    AcceptClass=class'UedPreview.UedPreviewLink'
}
