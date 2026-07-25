//=============================================================================
// UedPreviewLink — the minimal preview TCP link (spec D5 + gate folds).
// Ported (minimal) from uplayctl's UPlayCtlLink wire scaffolding — reference
// design only, no dependency. TcpLink on 127.0.0.1:7777, MODE_Line/RMODE_Event,
// framed `#<id> ... OK/ERR` protocol. Wire surface (deliberately tiny):
//   Ping | GetCurrentLevelName | GetPlayerPosition | GetPlayerRotation
//   TravelToLevel <map>            (replies OK BEFORE the open — the travel
//                                   destroys this link; the console re-spawns it)
//   PrepareCamera <x> <y> <z> <pitchUU> <yawUU>
//     Pose the frozen pawn's view: eye at (x,y,z) — the verb owns the SINGLE
//     eye->pawn BaseEyeHeight subtraction (spec §3) — angles as RAW FROTATOR UU
//     ints (the host does deg->uu with the GMath-parity quantizer, keeping the
//     rotation convention single-sourced host-side, same principle as the native
//     tier's camera basis). Roll forced 0 (D10). It POSES ONLY — it does not
//     capture; the host X-grabs the window. Replies `OK` synchronously; the batch
//     script (preview_batch.py) waits a short SETTLE before grabbing, because posing
//     does not repaint the window — the render loop does, on its next pass — so
//     grabbing too soon captures the PREVIOUS pose. The settle can't live here: the
//     `bPlayersOnly` freeze also freezes this actor's Tick/Timer. (Was `Screenshot`,
//     renamed 2026-07-17 — it never screenshotted.)
//
// D9 preview state (freeze + noclip + clean) is applied from PostBeginPlay — the
// console spawns this link the moment the level is possessed, BEFORE any client
// connects — and re-ensured on every Screenshot (idempotent).
// FREEZE (build-time choice, spec §5): `bPlayersOnly`. If SP-1 shows it stops
// rendering OR stops this link answering, flip _FreezeWorld to the
// TimeDilation~0 variant and recompile — no runtime fallback.
//
// Generic: names only Engine.* (NB `bCheatsEnabled` is a Deus-Ex-added field on
// this install's Engine.PlayerPawn — spec D7 gate-fold caveat for other games).
//=============================================================================
class UedPreviewLink extends TcpLink;

var UedPreviewBaseDriver Driver;
var config string SubstrateDriverClass;
var int CurReqId;

// PrepareCamera replies SYNCHRONOUSLY (the settle sleep lives in preview_batch.py, not here):
// the `bPlayersOnly` freeze we apply for a static frame ALSO freezes this non-player link
// actor's Tick/Timer, so a deferred in-verb reply can never fire. The socket poll that
// dispatches ReceivedLine runs in the engine's network layer (unfrozen), so a synchronous
// reply works; the batch script waits the short settle before X-grabbing (spec §3, corrected).

function PostBeginPlay()
{
    Super.PostBeginPlay();
    LinkMode = MODE_Line; ReceiveMode = RMODE_Event;
    // With AcceptClass set, the engine spawns one instance per ACCEPTED connection to run
    // ReceivedLine; that instance must not bind/listen (the listener owns the port) and
    // must stay alive to serve its connection.
    if ( BindPort(7777, True) == 0 ) return;
    Listen();
    Log("UedPreviewLink: listening on 7777");
    Driver = SpawnDriver();
    SetupPreviewState(FindPlayer());          // D9: frozen/clean at possession
}

function UedPreviewBaseDriver SpawnDriver()
{
    local class<Actor> dc;
    if (SubstrateDriverClass == "") return None;
    dc = class<Actor>(DynamicLoadObject(SubstrateDriverClass, class'Class', True));
    if (dc == None) return None;
    return UedPreviewBaseDriver(Spawn(dc));
}

// The whole D9 state, idempotent: cheats ungate Ghost; Ghost = engine noclip
// (CheatFlying sets EyeHeight=BaseEyeHeight — the exact-eye contract, spec §3);
// bPlayersOnly freezes every non-player actor; the substrate driver cleans the frame.
function SetupPreviewState(PlayerPawn P)
{
    if (P == None) return;
    P.bCheatsEnabled = True;
    if (P.Physics != PHYS_Flying) P.Ghost();
    P.Level.bPlayersOnly = True;              // the build-time freeze choice (see header)
    if (Driver != None) Driver.CleanFrameForPreview(P);
}

event Accepted() { SendText("HELLO uedpreview 1"); }

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
    local Actor A;
    local class<Actor> C;

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
    else if (cmd == "ListActors")
    {
        // Enumerate every actor of <Package.Class> as `Actor <Name> <x> <y> <z>` — lets the host
        // anchor `@Actor` poses and `--sample` to real in-map positions the game knows (e.g.
        // Engine.PathNode blankets every walkable spot). Read-only; fine under the freeze.
        C = class<Actor>(DynamicLoadObject(Trim(rest), class'Class', True));
        if (C == None) { Reply("ERR unknown-class "$Trim(rest)); }
        else
        {
            ForEach AllActors(C, A)
                Reply("Actor "$string(A.Name)$" "$int(A.Location.X)$" "$int(A.Location.Y)$" "$int(A.Location.Z));
            Reply("OK ListActors");
        }
    }
    else if (cmd == "GetActorLocation")
    {
        // Resolve one `@Name` ref (any class, case-insensitive) → its Location. Used by the batch
        // to turn actor-relative poses into eye/look points for retail maps (where the host has
        // no trunk to resolve against).
        ForEach AllActors(class'Actor', A)
            if (string(A.Name) ~= Trim(rest))
            {
                Reply("Location "$int(A.Location.X)$" "$int(A.Location.Y)$" "$int(A.Location.Z));
                Reply("OK GetActorLocation");
                return;
            }
        Reply("ERR actor-not-found "$Trim(rest));
    }
    else if (cmd == "GetPlayerPosition")
    {
        l = P.Location;
        Reply("Position "$int(l.X)$" "$int(l.Y)$" "$int(l.Z));
        Reply("OK GetPlayerPosition");
    }
    else if (cmd == "GetPlayerRotation")
    {
        Reply("Rotation "$P.ViewRotation.Pitch$" "$P.ViewRotation.Yaw$" "$P.ViewRotation.Roll);
        Reply("OK GetPlayerRotation");
    }
    else if (cmd == "TravelToLevel")
    {
        // Reply BEFORE the travel — the `open` destroys this link; the Viewport-owned
        // console re-spawns a fresh one on the target level (see UedPreviewConsole).
        Reply("OK TravelToLevel "$Trim(rest));
        P.ConsoleCommand("open "$Trim(rest));
    }
    else if (cmd == "PrepareCamera")
    {
        SetupPreviewState(P);                 // re-ensure (idempotent, cheap)
        l.X = NextInt(rest); l.Y = NextInt(rest); l.Z = NextInt(rest);
        l.Z -= P.BaseEyeHeight;               // the ONE eye->pawn subtraction (spec §3)
        P.SetLocation(l);                     // Ghost: no collision, cannot be blocked
        P.ViewRotation.Pitch = NextInt(rest); // raw UU (host clamps to +-89.9 deg)
        P.ViewRotation.Yaw   = NextInt(rest);
        P.ViewRotation.Roll  = 0;             // level horizon (D10 - roll DOES reach pixels)
        Reply("OK PrepareCamera");            // synchronous; the batch script settles then grabs
    }
    else Reply("ERR unknown-command "$cmd);
}

defaultproperties
{
    AcceptClass=class'UedPreview.UedPreviewLink'
    SubstrateDriverClass="UedPreviewDX.UedPreviewDeusExDriver"
}
