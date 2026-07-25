# In-game previewer — `level preview --game` (design spec)

**Status:** spec gate RUN 2026-07-16 (two cold reviewers; all findings folded below — the
reconciliation notes are marked *(gate fold, 2026-07-16)*). Ephemeral per-feature scratch — once
built, fold the durable parts into `architecture.md` + `unrealed/*.md` and the decisions into
`decisions.md` (see below).

**Decisions captured (Andrzej, 2026-07-13):** see `decisions.md` entry
`2026-07-13 … — level preview renders in-game via a uplayctl-style TCP link`. This spec links to it;
the decision + rejected alternatives live there (durable), not here. **Plus (Andrzej, 2026-07-16
15:49 UTC):** the game container's packages/ini are wired from the COMPOSED UEDCTL CONFIG PATHS
(`~/.uedctl/config.toml` `[games.*].paths` + the project `uedctl/config.toml` `paths`,
project-shadows-base) — NOT an uplayctl-style `/deusex` asset root + `/overlay` pair; see that
decisions.md entry and §5 "Asset & map wiring".

> **Context shift (gate fold, 2026-07-16).** The sibling `--native` tier SHIPPED 2026-07-16: the
> editor-screenshot backend and its `TARGET[:MODE][=NAME]` grammar are already DELETED, the shared
> SHOT grammar + pose trig + `shot_filename` live in `preview_shots.py`, and `dispatch._level_preview`
> routes `--game` to a reserved exit-2 today. Everywhere this spec says "replaces the editor
> preview" / "grows the grammar", read: ALREADY DONE — this build fills in the `--game` branch
> BESIDE `preview_native.render_shots`, consuming the shipped front half.

---

## 1. Problem / motivation

`level preview` today drives an ephemeral **UnrealEd** and screenshots its perspective pane. Two hard
limits, both hit while dogfooding the castle:

1. **The editor render can't be freely posed.** `CAMERA ALIGN NAME=<brush>` (auto-frame a brush) is
   the *only* console path that re-aims the headless render; free `POS@ROT` posing sets camera
   *position* only — its `Rotation` never reaches the pixels (spike
   `2026-07-12-preview-pose-calibration`). So there is **no hero/exterior/arbitrary-angle shot** — you
   get a size-locked, single-angle frame of whatever brush you name, always from the same canonical
   direction (inbox 2026-07-13 "auto-frame gives awkward interior compositions").
2. **Editor-lit ≠ in-game baked lighting.** `--mode lit` in the editor looked moody; the same map
   in-game washed out (the `LE_NonIncidence` fills over-brightened). The editor is not a faithful
   preview of what the player sees (inbox 2026-07-13 "lighting lesson").

**The fix:** render previews from the **actual game engine**, headless, posed freely. Boot the game on
the map, **freeze the world** (via `Level.bPlayersOnly` — `slomo 0` can't reach 0, §5), put the player
in **noclip** (no-collision) mode, **pose the pawn's view to an arbitrary world Location + Rotation**
(or a look-at / orbit convenience), and X-grab the engine's rendered frame. True lighting, sky
(fake-backdrop), textures, decorations — from any vantage.

This **replaces the editor as the preview driver** and **supersedes** the editor auto-frame preview.

---

## 2. Decisions (this spec implements)

| # | Decision | Detail |
|---|---|---|
| D1 | **New `uedctl` verb; the game engine replaces UnrealEd as the preview driver. NO uplayctl dependency — port a minimal preview stack into uedctl.** | `level preview` no longer boots an editor. It boots an ephemeral **game** container and drives it over a **uedctl-owned minimal TCP link** (freeze + noclip + pose + shot). uedctl does **not** import, shell out to, or share a package/image with `uplayctl` at build or runtime; the uplayctl link is only the proven *reference design*. uedctl ports the **minimal subset** it needs into its own tree (Andrzej, 2026-07-13). |
| D2 | **Supersedes the editor auto-frame preview; ONE faithful lit render, no modes.** | The `TARGET[:MODE][=NAME]` auto-frame grammar + per-mode editor boot are retired. There is no render-mode taxonomy (shaded/lit/wire/zones/polys/skybox) — the game renders one real, fully-lit reality. Debug views are already covered offline elsewhere: BSP/zone lint by `level doctor`, wireframe by `brush preview`. **`brush`/`stash`/`prefab preview` (the offline PGM renderer, `preview.py`) are UNAFFECTED** — only `preview_render.py` + `MODE_INI`/`parse_frame` go away. |
| D3 | **Pose inputs are positional SHOT tokens (not flags), batched.** | Each shot is one positional token (`at:…;rot:…` / `look:` / `orbit:`), so N tokens → N images in **one** boot+freeze (a batch is impossible with singular flags). Absolute loc/rot, look-at (point or `@actor`), and orbit conveniences. §3 is the authoritative grammar. |
| D4 | **Reuse a materialized `.dx` iff it is current for the trunk; `--rebuild` forces a fresh build.** | Cache key = `canonical_level_hash(trunk)` alone — the `.dx` is a pure function of the trunk. Packages are **loaded dynamically at game runtime** (not baked into the `.dx`), so they don't belong in the key; the rare relight/materialize-logic change is handled by `--rebuild`/`--no-cache`. `--map PATH.dx` bypasses caching. **No lock:** each preview runs its own ephemeral container and materialize swaps the `.dx` atomically, so a concurrent run can only read a complete file (at worst a harmless redundant rebuild). |
| D5 | **ONE high-level TCP verb, `Screenshot <LOC> <ROT>`, handles everything.** | The link exposes a single preview verb (pose + re-ensure clean/frozen). No granular `FreezeTime`/`SetNoclip`/`PoseCamera`/`HideHUD` commands on the wire. Plus a readiness/calibration probe (`GetCurrentLevelName`, `GetPlayerPosition`). |
| D6 | **HUD + first-person weapon hidden via a BY-NAME-loaded substrate driver — the generic link has ZERO DeusEx compile dependency.** | Frame-cleaning is `Driver.CleanFrameForPreview(P)` on a substrate driver spawned by name (`DynamicLoadObject`), exactly as uplayctl decouples its link. The generic link never names `DeusExPlayer`. DeusEx driver: `ShowHud(False)` + weapon put-away + flash/conversation guards (§5). |
| D7 | **Game-agnostic: any UE1 game (Unreal AND Deus Ex), not DX-only.** | The whole drive path (freeze/noclip/pose/capture) uses stock `Engine.*` only; the sole substrate-specific piece (frame-clean) is behind the by-name driver (D6). Game image is per-substrate via `[games.*]`. Unreal unverified now, but nothing is DX-only outside the substrate driver. |
| D8 | **v1 REQUIRES a valid PlayerStart; a spawn failure is a clean error, not a crash we hide.** | An authored trunk needs a spawnable PlayerStart for preview to boot (the game spawns the pawn there; a missing/in-solid PlayerStart aborts the boot — the logged spawn-crash). For v1 the previewer detects the boot/spawn failure and surfaces a clear exit-2 ("map has no spawnable PlayerStart — add one, or fix its placement"). **Deferred (post-v1, Andrzej):** auto-inject a safe PlayerStart so preview works on any trunk without one — explicitly NOT built now. |
| D9 | **Freeze + noclip + clean applied at POSSESSION, not lazily on the first shot.** | If the world runs live between travel and the first `Screenshot`, intro scripts/conversations/scripted pawns move (and a conversation can hijack the camera). The preview console sets `bPlayersOnly`+noclip+clean as soon as the target level is possessed, so it's already frozen/clean when uedctl connects. The verb only re-ensures + poses. |
| D10 | **Roll is NOT accepted; level horizon always. Pitch is engine-clamped.** | `rot` is `pitch,yaw` only — no roll field (Andrzej). The verb forces `ViewRotation.Roll = 0` (a rolled preview still is rarely wanted, and roll *would* otherwise reach pixels — `ViewShake` proves it — so it must be explicitly zeroed, not assumed ignored). Pitch is clamped by `UpdateRotation` to ≈ ±98.9° (±18000 units) — documented in `--help`. |
| D11 | **Capture = X-framebuffer grab of the game window off `:99` — uplayctl's proven method, already demonstrated.** | Exactly how `uplayctl shot` works: `wmctrl` finds the game window, `import -window` grabs it, `docker cp` out. **Proven this session** — `uplayctl shot` captured live game frames (the review's "uplayctl never screenshots" premise was wrong; its `shot` verb IS an X-grab). No gating spike for the grab itself; SP-1/SP-2b just re-confirm the frame is good once frozen + posed + HUD/weapon-hidden. |

---

## 3. CLI surface

```
uedctl level preview SHOT [SHOT ...] --out-dir DIR
                     [--size WxH]          # game viewport resolution (default 1280x960, 4:3)
                     [--map PATH.dx]       # preview a prebuilt map instead of the trunk (skips cache)
                     [--rebuild]           # force a fresh materialize, ignore the cache
                     [--keep-alive]        # skip teardown; publish + print the noVNC URL for live VNC
```

**SHOT tokens are positional** (D3 — flags can't batch). One token = one shot; fields are
`;`-separated `key:value` (the delimiters `;`/`:`/`,`/`@` never occur in FNames or numeric literals —
a self-contained delimiter-safety invariant, *not* the old `TARGET[:MODE][=NAME]` grammar):

- Absolute:      `at:X,Y,Z;rot:PITCH,YAW[;name:STEM]`
- Look-at point: `at:X,Y,Z;look:X,Y,Z[;name:STEM]`
- Look-at actor: `at:X,Y,Z;look:@ActorName[;name:STEM]`
- Orbit:         `orbit:@ActorName;radius:R;azimuth:A[;elev:B][;name:STEM]`  (camera on a ring around
  the target, aimed inward; `azimuth`/`elev` name the *ring* angles — distinct from camera `rot`)

Rules (all validated up front, all-or-nothing → clean exit 2 naming the offending token):
- **`rot`/`look`/`orbit` are mutually exclusive and exactly one is required** per token; `at`+neither
  `rot` nor `look` is an error (no silent default rotation). `orbit:` is a self-contained token.
- **Angles are degrees** (converted to UE 0–65535 units internally). `rot` = `pitch,yaw` — **no roll
  field** (the verb forces a level horizon, D10). Pitch beyond the engine clamp (≈±98.9°, D10) is
  accepted but the render clamps — noted in `--help`.
- **`look:@ActorName` / `orbit:@ActorName` aim at the actor's world AABB centre for BRUSH actors**
  (a brush's `Location` is its pivot, often near origin — the wrong target), reusing the
  overview/AABB machinery; point actors use `Location`. Resolver = the `actor find` name resolver
  (case-insensitive); unknown name → exit 2.
- **`name` output stems use `preview_shots.shot_filename`** *(gate fold: shipped 2026-07-16 —
  `frame_filename` is deleted)*: `taken` set + `-<k>` dedup, `_SLUG_SAFE` validation — **never
  silently overwrites** within a run. Default stem = the shot **index** (`shot-01`, `shot-02`, …).
- **`--size WxH`** patches the game's windowed viewport resolution — the ini keys are
  **`WindowedViewportX`/`WindowedViewportY` under `[WinDrv.WindowsClient]`** *(gate fold: the
  earlier `WindowPixelsX/Y` names do not exist in `DeusEx.ini`; verified against the live install
  ini — and the replace-in-place patcher hard-errors on an unknown key, so the wrong name fails
  loudly)* — at boot, within SoftDrv's max; the X-grab returns exactly that. Default `1280x960`
  (4:3). A single-run size (not per-shot).
- **Pitch is clamped HOST-SIDE to ±89.9° for `--game`** *(gate fold — supersedes "accepted but the
  render clamps")*: the engine's `UpdateRotation` clamp picks the pole by the SIGN OF `aLookUp`
  (`PlayerPawn.uc:3342+`), and headless `aLookUp==0` takes the else-branch to **49152 = maximally
  DOWN** — so an over-range `rot:99,0` would silently render the wrong pole. The verb clamps (and
  notes it in `--help`); the shared grammar itself stays unclamped (the native tier renders true
  ±90).
- A token that looks like the **old** grammar → exit 2 with the migration hint (shipped —
  `preview_shots.parse_shot` already does this for both backends).
- **`@actor` tokens are REJECTED with `--map`** *(gate fold — was undefined)*: `look:@X`/`orbit:@X`
  resolve against the SELECTED TRUNK's actors, and `--map PATH.dx` previews an arbitrary prebuilt
  binary unrelated to any trunk (or used with none selected). Resolving against the wrong trunk
  would silently mis-aim; live in-game resolution is future work. Clean exit-2 naming the token:
  "actor-relative shots need the trunk — use absolute at:/rot:/look:X,Y,Z with --map".

**Eye-height contract:** `at:X,Y,Z` is the **camera (eye)** the user wants. The host-side pose math
(look-at/orbit) computes in **eye space only**; the **`Screenshot` verb alone** subtracts
`BaseEyeHeight` to place the pawn (`SetLocation(z − BaseEyeHeight)`) — a **single** subtraction, no
double-drop. Under noclip the eye offset is exact and instant because `CheatFlying.BeginState` sets
`EyeHeight = BaseEyeHeight` (`PlayerPawn.uc:4249`); `BaseEyeHeight`≈40 standing (`Human.uc:415`). SP-3
confirms the constant live.

---

## 4. Freshness cache (D4)

- Cache path: gitignored `<project>/uedctl/tmp/preview/<level>.<hash12>.dx` — the artifact is
  **keyed by the trunk hash in its filename, no sidecar** *(gate fold — the earlier `.dx` +
  `.dx.hash` pair swapped non-atomically: two concurrent runs straddling a trunk edit could leave
  a fresh sidecar over a stale build, silently reused forever; a hash-named file is
  self-describing and each `os.replace` is atomic on its own)*. Stale hash-named siblings are
  pruned on write.
- **Key = `canonical_level_hash(trunk)` alone.** The `.dx` is a pure function of the trunk, and packages
  (textures/lights) are **loaded dynamically by the game at runtime** — not baked into the `.dx` — so
  they don't belong in the key. The one thing the hash can't see is a change to materialize/relight
  *logic* (rare, a code change); `--rebuild` covers it. This is the same oracle `verify` uses:
  "current for the trunk" = "materialize would produce the same level."
- On `level preview`:
  - `--map PATH.dx` → use verbatim (no cache).
  - `--rebuild`/`--no-cache` → always materialize (to the new hash-named path).
  - else if `<level>.<hash12>.dx` exists for `canonical_level_hash(trunk)` → **reuse** it.
  - else → materialize to the hash-named cache path.
  - The internal materialize call passes overwrite semantics directly (`run_materialize`'s
    programmatic API), never looping through the CLI-guarded `--out`/`--overwrite` path *(gate
    fold)*.
- **No lock needed.** Each preview boots its own ephemeral game container, and materialize swaps the
  `.dx` atomically (`apply._install_atomic` → `os.replace`), so a concurrent same-level run can only
  ever read a complete file; the worst case is a redundant rebuild, never corruption or a
  boot-on-half-written map. *(Deliberate acceptance, stated not implied — gate fold: a
  base-package/stub upgrade or a materialize-logic change silently reuses a stale cache until
  `--rebuild`; rare, accepted.)*
- *(gate fold, 2026-07-16: the former "semisolid predecessor" hard-blocker paragraph is DELETED —
  the qualify N-vs-N+1 bug was fixed 2026-07-14 (content matching) and the "semisolid breaks MAP
  SAVE" failure was a transient editor wedge; the full castle has since materialized end-to-end.
  SP validation may use any trunk.)*

---

## 5. Mechanism — the preview TCP link

Grounded in the uplayctl mechanism briefing (2026-07-13). uplayctl proves the whole
headless-game-over-TCP stack; **uedctl does not depend on it (D1)** — it **ports the minimal subset**
below into its own tree, using uplayctl's implementation only as the reference design.

**What uedctl ports (minimal, self-contained — new code under uedctl):**
- **A minimal preview game image**, built `FROM dx-lum-uned` (the editor base uedctl already owns —
  Xvfb `:99` + noVNC), with a **warm wineprefix BAKED into the image** (`RUN xvfb-run -a wineboot -u`
  — *gate fold: without it every per-command ephemeral boot pays a cold ~2-min wineboot; uplayctl's
  bake makes it a 2–4 s no-op*). A game entrypoint assembles the game root (below), patches the ini,
  launches wine `<Game>.exe -log -nosound`, boots the fast boot-map, then **travels to the target
  map over the link**.
- **Asset & map wiring is CONFIG-DRIVEN (Andrzej, 2026-07-16 15:49 UTC — decisions.md):** the
  container's package mounts come from `container_assets.resource_mounts` over
  `config.composed_search_dirs` (per-user `[games.*].paths` + project overlay,
  project-shadows-base) — the SAME uniform scheme every other uedctl container uses — and the game
  ini's `[Core.System] Paths` is GENERATED from that composed set (the crafted-ini pattern of
  `editor.engine_ini_mount`, extended with the game boot keys below). The entrypoint assembles the
  game root from the `/resources/<n>` mounts: `System/` copied from the base game's code dir,
  `Maps/`/`Textures/` symlink-farmed across ALL composed dirs **in composed order (project first =
  overlay shadows base by stem)**, the compiled preview `.u` dropped into System. The TARGET map
  (the hash-named cache artifact or `--map`) is `docker cp`'d into the Maps farm under its own
  stem. The BOOT map is staged at image build from the substrate's own assets (uplayctl stages
  `00_Training.dx` as `DX.dx` — per-substrate choice, part of the host substrate table below).
  *(Rejected at the 2026-07-16 decision: porting uplayctl's `/deusex` asset-root + `/overlay` pair.)*
- **Boot reliability (gate fold — both reviewers):** the launch ports uplayctl's
  `WINEESYNC=1`/`WINEFSYNC=1` (+ `wineserver -k` first) AND its **relaunch-on-deadlock loop**
  (added 2026-07-16, post-dating this spec: the wine server-side-sync startup wedge still fires
  frequently even with esync — retry the launch up to ~6× with a ~100 s per-attempt link-bind
  timeout instead of hanging the hang-guard on one wedged instance). Expected healthy cost:
  **~60–100 s boot-to-link + the travel** per preview invocation — the number that justifies
  batching N shots per boot and calibrates the §7 hang guard.
- **Readiness = the LINK, not a log scrape — the THREE-PHASE handshake** *(gate fold — one
  persistent connection dies at travel)*: (1) poll until a POSSESSED link answers on the boot map
  (`GetCurrentLevelName` returns a name; `ERR no-player` until the pawn exists); (2) send
  `TravelToLevel <target>`, retrying on `ERR no-player`, requiring `OK`; (3) **reconnect** (the
  travel destroys the accepted connection) and poll `GetCurrentLevelName == <target>`. Robust to
  the **buffered** DeusEx log and to mid-travel false-positives.
- **A minimal preview UnrealScript package** (uedctl's own, e.g. `UedPreview`): a `Console` subclass
  that spawns the link keypress-free + survives travel (Tick-poll ~1 s — `NotifyLevelChange` does
  NOT fire for the initial level, so polling is the only boot-map-safe trigger), plus a `TcpLink`
  on 127.0.0.1:7777 (`MODE_Line`, `RMODE_Event`); framed protocol copied (`#<id> … OK/ERR`).
  **The wire surface is `Screenshot` + the probes + `TravelToLevel`** *(gate fold — D5's original
  inventory omitted the travel verb its own boot flow needs)*, with `TravelToLevel`'s non-obvious
  contract ported verbatim: **reply `OK` BEFORE issuing the `open`** (the travel destroys the
  link; the console re-spawns it on the target level). **The link `.uc` names only `Engine.*`** —
  never a substrate class (the by-name substrate driver below). NB *(gate fold)*: `bCheatsEnabled`
  is a DEUS-EX-ADDED field on `Engine.PlayerPawn` — fine here (the package compiles against the
  game's own Engine.u), but the D7 "any UE1 substrate" claim carries this caveat; a stock-Unreal
  build must re-check the field exists.
- **Compile plumbing** *(gate fold — "compiled from source in uedctl's image build" glossed it)*:
  a Docker `RUN` cannot see the asset mounts, so the `.u` compiles in a MOUNTED builder container
  against the game's own code packages (uplayctl's two-step `build-image.sh` dance, staged UCC
  toolchain), is `docker cp`'d out, source-hash-stamped (recompile only on `.uc` change), then the
  thin `docker build` bakes it. The whole image build runs under a **flock** (two concurrent
  previews must not race the image tag/staged `.u`).
- **A minimal in-container client** `docker exec`'d inside the container (port unpublished).
- **Capture = X-grab off `:99`** — `wmctrl -lG`, keep windows whose title matches the substrate's
  game-window pattern, **exclude the Running/Starting/Recovery/Config splash windows, take the
  LARGEST** *(gate fold — a naive first-match grabs the splash; this is uplayctl's exact recipe)*,
  `import -window` → cp out. Proven live (`uplayctl shot`).
- **A small HOST-side per-substrate table** *(gate fold — D6's `.uc` driver seam doesn't cover
  host concerns)*: game ini filename + `LocalMap=` key, boot-map source, game-window title
  pattern, game exe name. DeusEx's row ships; other substrates add rows.

**Game-agnostic (D6/D7) — the generic link has ZERO substrate compile dependency.** The whole drive
path (freeze/noclip/pose/capture) is stock `Engine.*`. The only substrate-specific work — hiding the
HUD + first-person weapon (games differ: Unreal `myHUD`, Deus Ex `DeusExRootWindow`) — lives in a
**substrate driver spawned BY NAME** (`DynamicLoadObject` on a `SubstrateDriverClass` string — the
DeusEx default is BAKED in the link's defaultproperties exactly as uplayctl does; a future other
substrate overrides it via the generated ini section, not a recompile — *gate fold*), exactly
as uplayctl decouples its link from `UPlayCtlDeusExDriver`. The generic verb calls
`Driver.CleanFrameForPreview(P)`; the link never names `DeusExPlayer`.

**Freeze + noclip + clean at POSSESSION, not lazily (D9).** The preview console, as soon as the target
level is possessed (before uedctl connects), sets the world up ONCE — so intro scripts/conversations
never run live between travel and the first shot (a conversation would hijack the camera via
`ConCamera`):
```
P.bCheatsEnabled = True;        // ungate Ghost() — a generic PlayerPawn field (Andrzej: enabling cheats is fine)
P.Ghost();                      // generic Engine.PlayerPawn noclip: SetCollision(F,F,F)+bCollideWorld=F+
                                // GotoState('CheatFlying'). CheatFlying.BeginState sets EyeHeight=BaseEyeHeight
                                // (PlayerPawn.uc:4249) → eye offset exact + instant. (SetPhysics alone wouldn't
                                // hold — PlayerWalking re-derives physics each tick and drops the pawn.)
P.Level.bPlayersOnly = True;    // the ACTUAL freeze (Engine.LevelInfo). slomo 0 can't reach 0 (clamp FMax(T,0.1),
                                // GameInfo.uc:404); pause is WRONG — the player must keep ticking to render re-poses.
Driver.CleanFrameForPreview(P); // substrate: hide HUD + weapon + kill flash + guard conversation (below)
```
**Freeze mechanism is a BUILD-TIME choice decided by the spike — NOT a runtime fallback (Andrzej):**
SP-1 determines whether `bPlayersOnly` freezes-while-still-rendering **AND whether the TCP LINK
KEEPS ANSWERING under it** *(gate fold — HIGH: `bPlayersOnly` is documented "only update players",
and the link is a TcpLink ACTOR, not a player; if frozen actors stop ticking, the link goes dead
and — because D9 freezes at possession before uedctl ever connects — the readiness poll, the
travel, and every `Screenshot` die with it. The `TimeDilation≈0` alternative does NOT share this
failure mode: all actors still tick. The cheap pre-build probe: `RunConsoleCommand playersonly`
against a live uplayctl session, then any link command.)* If `bPlayersOnly` freezes-and-answers,
the build hardcodes it; else the build hardcodes `Level.TimeDilation`≈0 (bypassing the
`FMax(T,0.1)` clamp, accepting the `DeltaTime`≈0 risk). Exactly ONE is chosen and compiled in —
there is no runtime try-then-fallback.

**The ini boot-fix key set (gate fold — the full load-bearing list, exact names, each REPLACED in
its own section, hard error if absent):** `LocalMap=<boot map>` (`[URL]`),
`Console=<UedPreview console>` (`[Engine.Engine]`), `GameRenderDevice=SoftDrv.SoftwareRenderDevice`
+ `RenderDevice=SoftDrv.SoftwareRenderDevice` (headless software render), `WindowedColorBits=32`,
`StartupFullscreen=False`, `WindowedViewportX/Y=<--size>` (`[WinDrv.WindowsClient]`),
`FirstRun=400` (skips the first-run dialog) — plus the generated `[Core.System] Paths` from the
composed config set (the 2026-07-16 decision above). Any one missing wedges or breaks the
headless boot.

**The ONE TCP verb: `Screenshot <x> <y> <z> <pitch> <yaw>`** (no roll — D10). It re-ensures the
frozen/noclip/clean state (idempotent, cheap) then poses — `P` is a plain `Engine.PlayerPawn`:
```
P.SetLocation(vect(x, y, z - P.BaseEyeHeight));  // single eye→pawn subtraction (verb owns it; host passes eye Z)
P.ViewRotation.Pitch = degToUU(pitch);           // clamped to ≈±98.9° by UpdateRotation (PlayerPawn.uc:3342)
P.ViewRotation.Yaw   = degToUU(yaw);             // ViewRotation drives the first-person camera (DeusExPlayer.uc:7357)
P.ViewRotation.Roll  = 0;                         // level horizon — roll DOES reach pixels (ViewShake), so zero it
// No SetRotation/DesiredRotation writes: UpdateRotation runs every tick, sets DesiredRotation=ViewRotation and
// forces the pawn's OWN Rotation.Pitch/Roll=0 anyway (those writes would be dead). The camera uses ViewRotation,
// which holds across ticks because the input axes (aLookUp/aTurn) are 0 headless. → Reply OK; host X-grabs.
```

**Substrate `CleanFrameForPreview` (DeusEx).** `ShowHud(False)` (ungated — `DeusExPlayer.uc:6525` →
`DeusExRootWindow.ShowHud`) hides HUD + scope. **Weapon: null the first-person render sources
DIRECTLY** — set `P.Weapon=None` + `P.inHand=None`, because `PlayerPawn.RenderOverlays` draws the
viewmodel only `if(Weapon!=None)` (`PlayerPawn.uc:242`) and `DeusExPlayer.RenderOverlays` draws
`inHand` only if set (`:4286`); the next frame skips it — synchronous, no put-away anim (unlike the
async `PutInHand(None)`) (Andrzej: hide directly). *(gate fold: the earlier "restore the refs on
teardown if the container is reused" is DELETED — the container is per-command ephemeral, never
reused.)* Also zero the damage flash (`bNoFlash`/`DesiredFlashScale=0`) and **guard against an active
conversation**
(`InConversation()` routes the camera to `ConCamera`, bypassing first-person) — abort/skip it, force
`bBehindView=False`. (Doing this at possession per D9 avoids the mid-travel conversation entirely; the
guard is belt-and-suspenders.) The exact weapon-hide flag is confirmed in SP-2b.

**Per-shot orchestration** (uedctl host, one connection): the console has already frozen/cleaned the
world at possession; for each shot → `Screenshot x y z pitch yaw` (re-ensure + pose, reply OK) → X-grab
off `:99` + cp PNG out. No per-shot reboot; field writes are instantaneous. No editor-style
click-to-repaint race — the game viewport redraws continuously (a real advantage over the editor path);
the only settle is the async weapon put-away above.

**Rebuild path:** uedctl's preview package is **compiled from source in uedctl's image build**
(mirroring uplayctl's `wine UCC.exe Editor.MakeCommandlet` step), with a **source-hash fast-path** so
it recompiles only when the `.uc` changes. So: edit the link `.uc`, next preview boot auto-recompiles.
No prebuilt-`.u` surgery, no dependency on uplayctl's build.

**Ownership (resolved — Andrzej, 2026-07-13):** **no uplayctl dependency.** uedctl ports the minimal
subset above into its own tree — its own preview UnrealScript package, its own game image built on the
`dx-lum-uned` base it already owns, its own in-container client and orchestration. The verbs are added
to *uedctl's* link `.uc`, not uplayctl's. uplayctl's implementation is the reference/template only.
(Cost: a small amount of link/console/entrypoint boilerplate is duplicated; benefit: the two tools
stay fully decoupled and uedctl's previewer is self-contained.)

---

## 6. Render modes: dropped (decided, D2)

The editor modes (shaded/lit/wire/zones/polys/skybox) were editor-viewport RMODEs. In-game there is
**one** reality: fully-lit, textured, real sky — which is the whole point. **Decision: drop the mode
taxonomy entirely.** The debug views are already covered offline, no editor/game needed:
- **wireframe** → `brush preview` (the offline PGM wireframe renderer, `preview.py`),
- **BSP/zone/solidity lint** → `level doctor`.

So no in-game `--mode`/`--rmode` in v1. **`brush preview` / `stash preview` / `prefab preview` (the
`preview.py` PGM renderer) are UNAFFECTED** — the removals this paragraph listed (`preview_render.py` + `MODE_INI` +
`parse_frame` (the editor-screenshot path), not the offline wireframe verbs. (If a lit-vs-unlit game
debug view is ever wanted, `rmode N` over the link can add it later — explicitly not now.)

---

## 7. uedctl-side architecture

- `dispatch._level_preview` keeps its SHIPPED front half *(gate fold — the structure that landed
  2026-07-16)*: parse+validate all SHOT tokens up front (all-or-nothing → clean exit 2), resolve
  the backend flags, then route: `--native` → `preview_native.render_shots` (ships today; resolves
  `@actor`/poses internally via the shared `resolve_pose`), `--game` → the new
  `preview_game.render_shots(...)` replacing today's reserved exit-2 branch. `preview_game` uses
  the SAME shared resolution (`preview_shots.resolve_pose` + the trunk aim-point resolver) — with
  `--map`, `@actor` tokens are rejected per §3.
- `preview_game`: freshness-check/materialize (§4) → boot ephemeral game (mirror `editor.py`'s
  ephemeral-container lifecycle: per-command, **teardown in `finally`**, long-timeout hang guard per the
  background-work rules) → link-readiness poll (§5) → for each shot: `Screenshot x y z pitch yaw` +
  X-grab → cp PNG out. The console froze/cleaned at possession (D9); the host just poses + grabs.
- Look-at/orbit math is **model-side** (`preview_shots` grows pure `pose_from_lookat`,
  `pose_from_orbit` returning `(loc, rot_degrees)` in **eye space**), fully unit-tested; the link only
  ever receives a final `(loc, rot)` and does the single eye→pawn `BaseEyeHeight` subtraction.
- **Error taxonomy — every new failure surfaces as a named exit-2, never a traceback** (CLAUDE.md):
  game-boot failure (after the relaunch loop is exhausted), **no-spawnable-PlayerStart** (D8 —
  mechanism *(gate fold)*: for a TRUNK preview a MODEL-SIDE pre-check — does the trunk contain a
  PlayerStart? — errors cleanly BEFORE any boot; for `--map` binaries the possession-timeout path
  reports a distinct "never possessed a pawn on <map> — likely no spawnable PlayerStart" message,
  its observable signature pinned by SP-6), link unreachable / readiness timeout (hang guard), a
  `Screenshot` `ERR <reason>` reply, X-grab / `docker cp` failure, **image-build/UCC-compile
  failure, missing per-user games config, docker unavailable** *(gate fold — taxonomy gaps)*.
  Each maps to a clear message + regression test; `dispatch` catches the new `GamePreviewError`
  alongside `NativePreviewError`/`EditorBusyError`/`TimeoutError`/`DriverError` *(gate fold: the
  old `PreviewError` was deleted with the editor backend)*.
- **`--keep-alive`** deliberately **bypasses the `finally` teardown** (a `finally` normally always
  runs — this path guards it) and **prints the noVNC URL**. The port publish happens **at `docker
  run` time** (docker cannot publish on a running container), so `-p 0:6080` is passed
  unconditionally exactly as `editor.ensure_editor` already does — `--keep-alive` only changes
  teardown + printing *(gate fold — the earlier narrative read as a post-hoc publish)*. The
  kept-alive container is the user's to `docker rm` (documented in `--help`); the leak is
  intentional and visible.
- *(gate fold, 2026-07-16: the deletion list that stood here — `preview_render.py`, `MODE_INI`,
  the `TARGET[:MODE][=NAME]` grammar — was ALREADY PERFORMED by the native-tier cutover; nothing
  is left for this build to delete. `brush`/`stash`/`prefab preview` (the `preview.py` offline
  renderer) remain unaffected.)

---

## 8. Spike — remaining live unknowns

Source-reading + this session's usage **resolved** the big unknowns: freeze = `bPlayersOnly` not
`slomo 0`; the `.u` recompiles from source via the hash stamp; noclip = `Ghost()` (cheats enabled);
**and the X-grab capture is already proven** (`uplayctl shot` grabbed live game frames this session, so
D11's "render-present" risk is closed). What remains is a **live end-to-end run** of the built verb —
"build it, then verify," committed under `dev/docs/spikes/2026-07-13-ingame-preview/`. **v1 requires a
map with a valid PlayerStart** (D8); SP validation uses a **semisolid-free** test level (materialize
can't yet build a semisolid trunk — inbox p1). Against the single `Screenshot <x y z pitch yaw>` verb:

- **SP-1 Freeze renders AND the link survives it.** With `bPlayersOnly=True` (set at possession),
  does the game keep rendering so the X-grab yields a live frame — AND does the TcpLink keep
  answering (the link is an actor, not a player — §5 gate fold)? Confirm non-player motion is
  halted. (If either fails, the build hardcodes `TimeDilation`≈0 per §5.)
- **SP-2 Exact pose reflected in the pixels.** Confirm the grab reflects an arbitrary `(loc, pitch,
  yaw)` — **especially pitch** (the editor's fatal limitation); vary yaw+pitch and confirm the image
  changes. Confirm the pitch clamp (≈±98.9°) still reaches straight-down/up. Confirm `Ghost()` noclip
  lets the camera sit inside/above geometry and the frozen pawn holds position (doesn't fall).
- **SP-2b Clean frame.** Confirm `ShowHud(False)` + the direct weapon-actor hide remove the HUD
  (health/belt/crosshair) and the first-person weapon; confirm they stay hidden across shots and that
  no damage-flash / conversation overlay leaks in. Pin the exact weapon-hide flag here.
- **SP-3 Eye-height offset.** Confirm `at.Z − BaseEyeHeight` puts the camera at the requested eye Z
  (via `GetPlayerPosition` + a known sightline); confirm `CheatFlying` makes it exact + instant;
  confirm `WalkBob` contributes zero under CheatFlying+freeze (`DeusExPlayer.uc:7360` adds it to
  the camera — *gate fold*).
- **SP-4 Multi-shot in one freeze.** Re-pose + re-shoot N times over one connection: no drift, link
  survives, no per-shot reboot.
- **SP-5 `--size` reaches the pixels** *(gate fold)*: the `WindowedViewportX/Y` patch actually
  resizes the game window and the X-grab returns exactly WxH.
- **SP-6 The D8 spawn-failure signature** *(gate fold)*: boot a map with no (or an in-solid)
  PlayerStart and pin what it observably looks like through the link (possession never happens?
  a log line?) — the `--map` variant of the D8 clean error is built from this.

Fast pre-build smoke test with **existing** uplayctl primitives (reference only, not a dependency):
`SetPlayerLocation X Y Z` + `FaceActor <tag>` + `RunConsoleCommand playersonly` against a running
uplayctl session de-risks freeze+position+aim TODAY (can't prove arbitrary pitch or HUD/weapon hide →
needs the built verb).

---

## 9. Test plan

- **Offline (unit):** shot-grammar parse (all four forms + malformed/old-grammar/over-under-specified
  → clean exit 2 naming the token); `@actor` resolution **to AABB centre for brushes** vs `Location`
  for point actors; `pose_from_lookat` / `pose_from_orbit` trig (known vectors → known rotations, incl.
  straight-down/up gimbal cases); filename dedup (`taken`/`-<k>`, no silent overwrite); freshness-cache
  decision (fresh hash → reuse, stale/missing/`--rebuild` → materialize) with the container +
  materialize seams mocked; the new error-taxonomy paths each → their exit-2 message.
- **Integration (`-m integration`, live game, semisolid-free level):** boot → possession freeze/clean
  → `Screenshot` pose → X-grab round-trip produces a non-black PNG whose content **changes with
  `pitch`/`yaw`** (proving free posing — the editor's failure mode) and shows **no HUD/weapon**. Gated
  behind the game container like uplayctl's integration tests.

---

## 10. Out of scope / deferred

- Fixing the semisolid-materialize bug (separate inbox p1) — a **hard predecessor** for previewing
  full-detail trunks; the previewer just surfaces the failure until it's fixed.
- **Auto-injecting a safe PlayerStart** so preview works on a trunk without one (D8) — deferred to
  post-v1; v1 requires a valid PlayerStart.
- Unreal (and other UE1) substrate drivers — the design is game-agnostic (D7) but only the DeusEx
  `CleanFrameForPreview` is built + verified now.
- A "hero shot" auto-composer (auto-pick flattering angles) — this spec gives *manual* free posing;
  auto-composition can layer on top later.
- Video/flythrough capture (multi-frame animation) — single stills only for now.
- Interactive/live-drive beyond `--keep-alive` (hand off to VNC) — dev-debug only.
