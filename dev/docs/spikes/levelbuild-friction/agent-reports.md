# Agent-reported friction (appended live by the level-building agents)

Each agent appends its own entries here as it hits them. Format:

    ## <level> — <short title>
    **What I tried:** <the exact command>
    **What happened:** <exact error / wrong output / silence>
    **What I expected:** <why I thought it would work>
    **Workaround:** <what I did instead, or "none found">

Append only; never edit or delete another agent's entry.

---

## DiveBar — `class show` cannot show a class's DEFAULT property values
**What I tried:** `bin/uedcli class show Engine.ZoneInfo --category ZoneLight` and then, guessing, `bin/uedcli class show Engine.ZoneInfo --category ZoneLight --defaults`
**What happened:** The first prints only the property NAMES and types (`AmbientBrightness: ByteProperty`). The second exits 2 with `uedcli: error: unrecognized arguments: --defaults` — and the usage it prints is the TOP-LEVEL `uedcli` usage, not `class show`'s, so it doesn't even show you which flags do exist.
**What I expected:** To be able to see the engine default of `AmbientBrightness` on `Engine.ZoneInfo`. I was diagnosing a room that had gone fullbright immediately after 8 `Engine.ZoneInfo` actors were added, and the whole question was "does a freshly-placed ZoneInfo carry a nonzero ambient by default?". There is no way to answer that from the CLI: `actor prop get` only prints properties that were explicitly SET, so a newly built actor shows just `Location=`, and `class show` only prints names. The only route left is an expensive in-game render experiment.
**Workaround:** Explicitly set `AmbientBrightness=0 AmbientSaturation=255 AmbientHue=0` on every ZoneInfo and re-render to see if anything changed — i.e. binary-search by screenshot, at ~5-10 min per iteration.

## DiveBar — `level preview --game --rebuild` fails where `level materialize` succeeds
**What I tried:** `bin/uedcli level preview --game --rebuild --out-dir .../shots/diag --size 800x600 "at:960,96,88;look:256,760,96;name:d1-bar-wide" ...` (twice, back to back)
**What happened:** Both times, after ~40s: `materialize for preview failed: materialize failed (nothing written): OBJ DEPENDENCIES PACKAGE=MyLevel did not complete within 20 attempts (20s)`. Immediately afterwards `bin/uedcli level materialize --no-verify --out .../maps/diag.dx --overwrite` succeeded on the FIRST attempt with the identical trunk.
**What I expected:** The same build to succeed or fail the same way in both verbs — they materialize the same trunk.
**Workaround:** `level materialize` to an explicit `.dx`, then `level preview --game --map <that .dx>`. Two commands instead of one, but reliable. It would help a lot if `preview`'s internal materialize retried the way the docs tell the human to retry (`sleep 30 && retry, up to 5x`) instead of surfacing the raw failure.

## DiveBar — `level preview --game` gives no progress output and no queue feedback while blocked on the shared container lock
**What I tried:** `bin/uedcli level preview --game --map .../maps/diag.dx --out-dir .../shots/diag --size 800x600 "<3 shots>"`
**What happened:** Complete silence for 10 minutes (only repeated `XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)` lines from the X stack), then my harness timeout killed it. `docker ps` showed `uedcli-game-preview-1000  Up 2 seconds` — i.e. another agent's preview had just claimed the container, and mine was silently waiting behind a lock. Killing and re-running apparently loses your place in the queue, so retrying makes it worse.
**What I expected:** A line on stderr like `waiting for the game container lock (held by another session)…` and/or `booting container… / travelling… / shooting 1/3`. With zero output there is no way to tell "blocked on a lock" from "wedged" from "slowly booting", which is exactly the distinction you need to decide whether to wait or to kill it.
**Workaround:** Run the preview as a tracked background job and poll the output file, rather than blocking a foreground tool call that a timeout will kill.

## TubePlatform — `actor show` refuses several names, unlike every sibling verb
**What I tried:** `bin/uedcli actor show StationBore_6cuhtp TrackTrench_rg0hvt RoomPlant_kov79m PassPlant_h2uryd NicheBay_1rpd5c VentDuct_lu0a6o`
**What happened:**
```
usage: uedcli [-h] [--project PROJECT] {actor,brush,...} ...
uedcli: error: unrecognized arguments: TrackTrench_rg0hvt RoomPlant_kov79m PassPlant_h2uryd NicheBay_1rpd5c VentDuct_lu0a6o
```
**What I expected:** `actor bbox` takes `<names…|->` and the whole CLI philosophy is "a verb over a SET takes the set", so `actor show` reading several names looked like the obvious spelling. `docs/usage.md` writes its signature as `actor show <name|glob|->` — a single positional — but the distinction from `actor bbox <names…|->` two rows above is easy to miss when scanning the table.
**Workaround:** `printf 'A\nB\nC\n' | bin/uedcli actor show -`. Worked first try. The usage line dumps the *top-level* parser usage, not `actor show`'s own, so it doesn't show you the accepted form; a message naming the verb ("actor show takes ONE name/glob — pipe a list with `-`") would have saved the lookup.

## TubePlatform — `--folder` lives on the generator, not on `actor add`
**What I tried:** `bin/uedcli actor build DeusEx.CageLight --at 700,608,254 | bin/uedcli actor add - --folder props.plant`
**What happened:**
```
uedcli: error: unrecognized arguments: --folder props.plant
Exception ignored in: <_io.TextIOWrapper name='<stdout>' mode='w' encoding='utf-8'>
BrokenPipeError: [Errno 32] Broken pipe
```
**What I expected:** `actor add` is the verb that writes the trunk, and the folder is trunk-side (uedcli sidecar) state, so I assumed the consumer owned it. It is actually on `actor build`, which rides it through as a `// uedcli-folder:` comment.
**Workaround:** move `--folder PATH` onto the `actor build` side. Note the failure also leaks a `BrokenPipeError` traceback from the *producer* half of the pipeline onto stderr — that is a raw Python exception reaching the CLI user, which `CLAUDE.md` forbids, and it made the real (clear) argparse error harder to spot in a batch of six commands.

## TubePlatform — piping `brush poly find` with `2>&1` feeds the stderr summary into `poly set`
**What I tried:** `bin/uedcli brush poly find PlantConsole_lm6lng --facing +Y 2>&1 | bin/uedcli brush poly set - --texture Airfield.AF_CommPanel_A`
**What happened:** `surface selector must be BRUSH:SELECTOR, got '1 face(s) matched'`
**What I expected:** my own mistake (the `2>&1` was left over from a debugging invocation), but it is worth recording because the producer/consumer convention makes it a trap that costs a minute every time: the human-readable count on stderr is *syntactically plausible* as a selector line, so the error surfaces as a confusing "your selector is wrong" rather than "that came from stderr".
**Workaround:** drop the `2>&1`. The error text is accurate; adding a hint ("did you merge stderr into the pipe?") when the offending token matches the summary format would make it self-diagnosing.

## TubePlatform — `class show` hides every property name by default, with no route to the one you want
**What I tried:** `bin/uedcli class show DeusEx.DataCube`, then `bin/uedcli class show DeusEx.DataCube --all`
**What happened:** the bare form prints only
```
DeusEx.DataCube  [concrete, placeable]
  super: DeusEx.InformationDevices -> ... -> Core.Object

(+142 inherited, in 16 more categories: Advanced, Collision, Conversation, Decoration, DeusExDecoration, Display, Events, Filter, InformationDevices, LightColor, Lighting, Movement, Networking, Object, Smell, Sound)
```
— i.e. **no property names at all**, because `DataCube` declares none of its own. `--all` is not a flag and was silently swallowed by my `grep`, so it looked like the property simply didn't exist.
**What I expected:** `docs/leveldesign/deusex/classes.md` says "`class show DeusEx.NanoKey` — property names + types", which reads as though the bare invocation lists them. For a class whose props are all inherited it lists nothing, and the category list gives no clue which of the 16 categories holds `textTag`.
**Workaround:** `class show DeusEx.DataCube --category InformationDevices` (guessed from the superclass name), or `--depth all`. Suggest the empty-own-props case print a one-line hint: `no own properties — use --depth all or --category NAME`.

## TubePlatform — `level materialize` post-verify rejects a good build (known)
**What I tried:** `bin/uedcli level materialize --out .../TubePlatform.dx --overwrite`
**What happened:** pre-warned by my brief that the post-verify wrongly rejects when the engine stamps `Base=LevelInfo'MyLevel.LevelInfo0'` onto an actor resting in the level.
**What I expected:** a clean build to verify clean.
**Workaround:** `--no-verify` on every `materialize`, then `level preview --game --map <that file>` rather than letting `--game` materialize internally — because `level preview --game` has **no `--no-verify` escape** (`docs/usage.md` says so explicitly). That is the sharp edge: with the verify bug live, the documented default path (`level preview --game` with no `--map`) is unusable, and the only way through is to know the two-step materialize/preview split. Worth a mention in `usage.md`'s preview section.

## ContainerYard — `level preview --game` has no `--no-verify`, so a false post-verify failure blocks ALL in-game rendering
**What I tried:**
```
bin/uedcli level preview --game --out-dir $P/shots --size 800x600 \
  "at:1120,64,56;rot:0,16384;name:m3-1-gate" ... (5 shots)
```
**What happened:** six retries over ~25 minutes, every one dying inside the implicit materialize:
```
materialize for preview failed: materialize failed (nothing written): post-verify mismatch:
on-disk /work/061d7d2b5944463abf1c0087c08ff4ab.dx does not match the intended level —
actor 'BridgeA_4i3uoi' is in the intended level but MISSING from the built map
```
(interleaved with `OBJ DEPENDENCIES PACKAGE=MyLevel did not complete within 20 attempts (20s)`).
No PNG was ever written. `level doctor` reports the level clean (0 error, 0 warn).
**What I expected:** `level materialize` has `--no-verify` for exactly this class of false
rejection, but `level preview --game` — which runs the same materialize internally — does not
expose it (`level preview --help` lists `--map`, `--rebuild`, `--keep-alive`, no `--no-verify`).
So the one verb that produces the deliverable picture has no escape hatch from its own verifier.
**Workaround:** split the pipeline in two — `level materialize --no-verify --out build/CY.dx
--overwrite`, then `level preview --game --map build/CY.dx …`. Works first time, and has the
bonus that N shots reuse one build instead of re-materializing per retry. Either add
`--no-verify` to `level preview`, or make the two-step the documented pattern in `docs/usage.md`.

## ContainerYard — post-verify says an actor is "MISSING from the built map" with no next step
**What I tried:** (as above) any `level materialize` of a level containing a 512x128x32 additive
catwalk brush whose two ends are embedded 64 uu into neighbouring container stacks.
**What happened:** `post-verify mismatch: … actor 'BridgeA_4i3uoi' is in the intended level but
MISSING from the built map`, exit non-zero, **nothing written** — so I could not even look at the
built map to judge whether the actor was really gone.
**What I expected:** the message is accurate-sounding but actionable-free: it does not say whether
this is a real BSP drop or a verifier false positive, does not name a repair move (the
`geometry-and-bsp.md` repair list — reorder / flip solidity / nudge — is not referenced), and it
throws away the artifact that would let me check. `level doctor` — the verb whose whole job is
"tell me what is wrong with this level" — says the level is clean, so the two disagree.
**Workaround:** `--no-verify`, then render and look. The catwalk is present and correct in the
in-game render, so this was a false positive. Suggest: keep the .dx on verify failure (e.g.
`--out` still written plus a warning), and have the message point at the repair list.

## ContainerYard — a materialize failure costs ~25 min because the retry re-materializes every time
**What I tried:** the natural retry loop the task brief recommends — re-run the same
`level preview --game …` up to 6 times, sleeping 20-30 s between.
**What happened:** each retry re-ran the full trunk materialize (192 actors) inside the container
before failing again on the same deterministic post-verify mismatch. ~25 minutes of wall clock for
zero output. A deterministic failure is not worth retrying at all, but nothing distinguishes it
from the transient `OBJ DEPENDENCIES … did not complete within 20 attempts`, which *is*.
**What I expected:** the two failure modes to be distinguishable in the exit status or message
class ("transient, retry" vs "deterministic, do not retry").
**Workaround:** materialize once to a file, then aim every preview at `--map <file>`. Re-shooting
badly framed cameras afterwards then costs seconds instead of a full rebuild.

## ContainerYard — `texture list` hides the texture Group, which is load-bearing for DX ladders
**What I tried:**
```
bin/uedcli texture list | grep -i "ladd\|ladr"
```
**What happened:**
```
CoreTexMetal.LadrBrwnMetal	256x256	unclassified
CoreTexMetal.ladder_a	128x64	unclassified
```
Two-part refs, no group shown. `docs/leveldesign/deusex/classes.md` says "A ladder is any surface
textured with a texture whose **`Group` is `Ladder`**" — so the group is the single fact that
decides whether my brush is climbable, and the discovery verb does not print it.
**What I expected:** `texture list`/`texture search` to surface the group, or a `texture show
<ref>` verb. `texture show` does not exist:
```
uedcli texture: error: argument sub: invalid choice: 'show' (choose from sync, list, search, tags, classify)
```
**Workaround:** grep the raw catalog JSON —
`python3 -c "import json; d=json.load(open('texture-catalog/CoreTexMetal.json')); …"` — where the
key is `"Ladder.LadrBrwnMetal"` and carries `"group": "Ladder"` while `"ref"` is the group-less
`CoreTexMetal.LadrBrwnMetal`. Took ~10 minutes to establish that the ladder texture really is in
the reserved group.

## ContainerYard — `brush build --at` is silently discarded by `brush replace`, moving geometry off its intended box
**What I tried:** (inherited from the previous session's `02c_fixes.sh`, whose comment says the
intent was to push the stash interior clear of the container's west face)
```
bin/uedcli brush build cube --csg subtract --width 520 --breadth 112 --height 112 --at 2164,704,64 \
  | bin/uedcli brush replace ObjIn_cdfzhi -
```
**What happened:** the replaced brush ended up spanning X 1912..2432, not the intended
X 1904..2424 — `brush replace` keeps the *target actor's* existing Location (2172) and only takes
the incoming PolyList, so the `--at 2164` was dropped. The 8 uu difference silently deleted the
container's entire east wall, turning a sealed container into an open-ended tube. Nothing warned;
`level doctor` stayed clean.
**What I expected:** either the `--at` to be honoured, or a warning that it was ignored. It *is*
documented in `brush replace --help` ("Only the incoming PolyList is used; its own
Location/PrePivot/Name are ignored") — but the generator's `--at` reads as "put it here", and the
composed pipeline gives no feedback that half the command was thrown away.
**Workaround:** always follow `brush replace` with an explicit `actor move <name> --to X,Y,Z`, and
verify with `actor bbox`. A warning on stderr when a discarded `--at` is non-default would have
saved the earlier session a silent geometry bug.

## ContainerYard — nothing flags two semisolid brushes that touch
**What I tried:** inherited crate steps from `03_detail.sh`:
```
brush build cube --csg add --width 96 --breadth 96 --height 24 --at 1424,160,12 …
brush build cube --csg add --width 48 --breadth 96 --height 48 --at 1496,160,24 …
```
(the generator's default solidity is used elsewhere in that script for semisolids)
**What happened:** `actor bbox` shows them at X 1376..1472 and X 1472..1520 — exactly touching.
`geometry-and-bsp.md` is emphatic that "A semisolid must NOT touch another semisolid… This
reliably wrecks the local BSP", yet `level doctor` — which does check "solidity misuse" per its own
blurb — reported 0 warnings.
**What I expected:** `level doctor` to flag touching/overlapping semisolid pairs, since it is a
named, deterministic, purely model-side rule and doctor already walks every brush's bbox.
**Workaround:** compute it by hand — dump `actor bbox` for every semisolid and check the pairs.

## headless-materialize spike — a killed `level materialize` strands its container, and I reproduced it in one run
**What I tried:** `bin/uedcli --project <LUM> level materialize --tree level/basement --no-verify --out _scratch/.../gui_basement.dx --overwrite`, to get a GUI-built reference for the spike.
**What happened:** the run was still going at 600 s (the previous, identical run had finished in 106 s) so I killed it. It left `uned-019f9b87-d5d2-7856-ab74-1cbd9b3fbebc` and its `uned-wp-…` volume behind; I had to `docker rm -f` + `docker volume rm` by hand. Teardown lives only in `apply.run_materialize`'s `finally`, which a SIGKILL never reaches — so **every killed or externally-timed-out materialize leaks a container plus a ~0.5 GB wineprefix volume.** This is §2 of `README.md` observed from the producing side rather than the counting side.
**What I expected:** either the ephemeral container to be reaped (a label + startup sweep would do it), or the tool to be interruptible without leaking.
**Workaround:** none from inside the tool. Manually: `docker ps --format '{{.Names}}\t{{.CreatedAt}}'`, match the creation time to your own run (do NOT reap by prefix — other sessions' editors share it), then `docker rm -f <name>; docker volume rm uned-wp-<uuid>`.

## headless-materialize spike — post-verify diff prints two sides that look line-shifted, not different
**What I tried:** `bin/uedcli --project <LUM> level materialize --tree level/basement --out … --overwrite` (with verify on).
**What happened:** after 106 s:
```
post-verify mismatch: … actor 'RoomA_jwvaq0' differs in GEOMETRY at line 7:
    built:    Vertex   +00192.000000,-00160.000000,-00096.000000
    intended: Pan      U=0 V=0
```
**What I expected:** the two sides of a "differs at line N" report to be the *same kind of line*. A `Vertex` opposite a `Pan` means the two texts are offset relative to each other, so the reported line is not where the semantic difference is — which makes the message actively misleading about the cause. (Different from `README.md` §1's `Base` case: that one names a real property; this one names a line number in two texts of different length.)
**Workaround:** `--no-verify`. Not chased further — outside this spike's scope, recorded so it is not lost.

## headless-materialize spike — `bsp_health_check.py` and the native harnesses hardcode an absolute `ROOT`
**What I tried:** `python3 dev/docs/spikes/2026-07-15-native-materialize/harness/bsp_health_check.py <map.dx>`
**What happened:** `ModuleNotFoundError: No module named 'uedcli'` — the harness sets `ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")`, which is the checkout it was written in, not this one. `build_native_castle.py` and `spike_classindex.py` have the same hardcoded root, and `build_native_castle.py` additionally imports `spike_classindex` from a `2026-06-27-decontainerize-uedcli/harness` path that no longer exists (the file lives under `2026-07-15-native-materialize/harness`).
**What I expected:** a committed harness to run from the repo it is committed in. `CLAUDE.md` "Commit the harness" makes these durable artifacts, so they are worth being path-independent.
**Workaround:** `sys.path.insert` the real root and `exec()` the harness, or sed the constant. Suggest deriving `ROOT` from `Path(__file__).resolve().parents[N]` in all three.

## ContainerYard — `actor rotate` pivots about the bbox MIN CORNER, not the actor's centre
**What I tried:** flip a 128x128 sign sheet 180 degrees so its face pointed at the player instead
of away:
```
bin/uedcli actor rotate Sign_r03nug --by 0,32768,0
```
**What happened:**
```
rotated 1 actor(s) about ('1056.0', '228.0', '112.0')
```
The sheet had been at X 1056..1184, Z 112..240; afterwards `actor bbox` reports X 928..1056 — it
swung a whole width sideways and landed on top of a gate post. It also picked up float error:
`min 928,227.999994,112 / max 1056,228.000006,240` on a brush that was exactly on Y=228.
**What I expected:** an in-place flip. Rotating a sign to face the other way is the single most
common reason to call `actor rotate` on a decoration, and the natural pivot for that is the
actor's own origin/centre. The message does print the pivot it used, which is good — but only
after the fact, and `actor rotate --help` gave me no way to choose one.
**Workaround:** follow every rotate with an `actor move … --to` to put it back, and re-check with
`actor bbox`. A `--about center|origin|X,Y,Z` option (or just defaulting to the actor Location)
would make this a one-liner. The float dust on an exactly-on-grid brush is a second concern given
how emphatic `geometry-and-bsp.md` is about staying out of the tolerance bands — for a nonsolid
sheet it is harmless, but the same call on a solid would seed exactly the off-grid coordinates the
doc warns about.

## ContainerYard — the DX guides imply computers are HackableDevices; they are not
**What I tried:**
```
bin/uedcli actor build DeusEx.ComputerSecurity --at 1616,112,52 --rotate 0,16384,0 \
   --prop Views.0.cameraTag=GateCam --prop Views.0.doorTag=YardGate \
   --prop bHackable=True --prop hackStrength=0.25
```
**What happened:**
```
actor build: unknown property bHackable on class DeusEx.ComputerSecurity
```
The script was `set -e`, so it aborted mid-way through a 60-actor batch.
**What I expected:** `docs/leveldesign/deusex/gameplay-wiring.md` repeatedly says the camera feed
"renders inside that computer's console UI **when the player hacks or logs into it**", and
`classes.md` frames hacking as the generic DX route ("Most share the `HackableDevices` base
(`bHackable`, `hackStrength`)"). Neither doc says computers are on a *different* branch. The real
chain is `ComputerSecurity -> Computers -> ElectronicDevices -> DeusExDecoration`, i.e. a sibling
of `HackableDevices`; a computer is entered against its `UserList[8]` (`userName` / `Password` /
`accessLevel`) plus the Computer skill, and has no hack strength at all.
**Workaround:** `class show DeusEx.Computers --category Computers` reveals `UserList`,
`titleString`, `nodeName`, `lockoutDelay`; and `actor build … --prop UserList.0.userName=x` prints
the whole struct with its defaults (`(userName=x,Password=SECURITY,accessLevel=0)`), which is a
nice way to discover struct members. Worth one sentence in `classes.md`: "computers are NOT
`HackableDevices` — they take logins, not `hackStrength`."

## ContainerYard — a `--prop` typo aborts a whole `set -e` batch script with no partial-progress signal
**What I tried:** a ~60-actor build script that accumulates `actor build` output into one T3D and
does a single `actor add` at the end. One actor deep in the middle had a bad `--prop`.
**What happened:** the script died at that line. Because the `actor add` is at the *end*, nothing
from the `a()` accumulator had landed — but three earlier movers piped straight to `actor add -`
HAD landed, so the trunk was half-applied and re-running the script would have duplicated them.
**What I expected:** nothing from uedcli specifically — but a `--dry-run`/validate mode on
`actor build` (or an `actor add --if-absent`) would make batch scripts re-runnable, which matters
a lot when a level build is a sequence of shell scripts.
**Workaround:** guard the direct-to-trunk section with
`if [ -z "$(uedcli actor find --name 'YardGate_*')" ]; then … fi`, and validate every new class's
props with a throwaway `actor build … | head` before putting it in the script.

## DiveBar — a far-away skybox brush silently collapses `actor preview` to an unreadable dot
**What I tried:** `bin/uedcli actor find | bin/uedcli actor preview - --annotate name --size 900 --out .../shots/wire-m5-final.png` — the exact invocation the level-build brief recommends.
**What happened:** The PNG rendered fine (exit 0) but the level was a ~40px smudge in the bottom-left of each quad, because the set included `SKYROOM` (a subtract at 12000,12000,6000) and `SkyZoneInfo` (same). The quad views auto-fit the bounding box of the whole set, and one distant sky brush is ~15x the level's own extent. Output dropped from 65KB to 10KB — the only hint anything was wrong.
**What I expected:** Something usable, or at least a warning that one actor was inflating the fit by an order of magnitude.
**Workaround:** `bin/uedcli actor find | grep -v -e SKYROOM -e SkyZoneInfo | bin/uedcli actor preview - ...`. A `--fit` / `--exclude` option, or auto-dropping the sky-zone island from the framing, would make the documented one-liner just work — every DX level has a distant skybox.

## DiveBar — `level materialize --no-verify` reports SUCCESS after writing a broken, unlit map (this is what "the room went fullbright" actually was)
**What I tried:** `bin/uedcli level materialize --no-verify --out .../maps/diag.dx --overwrite`
**What happened:** It printed exactly two lines and exited 0:

    materializing level 'DiveBar' (from $UEDCLI_LEVEL)
    materialized /home/neob91/Documents/Dev/uedcli/_scratch/levelbuild/dive-bar/maps/diag.dx

The file it wrote was **23,126 bytes**. A correct build of the same, unchanged trunk is **191,332 bytes** — and the level's own blockout-only build back at milestone 1 was already 96,870 bytes. Nothing in the output distinguished the two. Immediately after, the same command WITH verify failed six times in a row with `materialize failed (nothing written): OBJ DEPENDENCIES PACKAGE=MyLevel did not complete within 20 attempts (20s)`, then a later `--no-verify` run of the identical trunk produced the correct 191KB map. So `--no-verify` does not merely "skip the check" — when the underlying editor build goes wrong it **writes the partial result and calls it success.**
**What I expected:** `--no-verify`'s help says "skip the post-build verify and write the .dx even if it would NOT match the intended level — for debugging, or when verify is known-buggy". I read that as "the build is fine, only the comparison is skipped". It actually means "you will not be told when the build itself was garbage", which is a very different bargain — especially since the level-build brief tells agents to reach for `--no-verify` whenever verify blocks them.
**Why this matters more than it looks:** this is almost certainly the *entire* "the bar room went FULLBRIGHT" regression I was handed. The previous session's milestone-4 map is 176,132 bytes; my correct build of essentially the same trunk is 191,332. The ~15KB difference is the baked lightmap. Its map had geometry but no light bake, so every BSP surface rendered at full texture brightness — which looks exactly like "someone added ambient light everywhere". I burned well over an hour chasing `ZoneInfo.AmbientBrightness`, per-light radii, and `PF_Unlit` polyflags before noticing that the *file size* was the tell.
**How discoverable was it:** essentially zero. There is no signal anywhere that a materialized map is missing its lighting — not in `level status`, not in `level doctor` (which is explicitly trunk-only and static), not in the materialize output, and of course not in `--native` previews (which never light anything). The only way I found it was `ls -la` on the built `.dx` next to older builds. Suggestions, in order of value: (1) make `--no-verify` still *report* what verify would have said, on stderr, instead of printing an unqualified `materialized <path>`; (2) have materialize sanity-check the built map (byte size vs. the previous build of the same level, or presence of lightmap data) and refuse/warn on a gross regression; (3) surface "lighting was/was not baked" as a line in materialize's output, since that is the single most expensive thing to discover from a screenshot.
**Workaround:** Never trust a `--no-verify` build without checking `stat -c%s` on the output and comparing it to the previous good build of the same level. Retry the build until you get a plausibly-sized map.

## DiveBar — `ZoneInfo` ambient turned out NOT to be the fullbright cause, but ruling it out was needlessly hard
**What I tried:** to answer "does a default `Engine.ZoneInfo` add ambient light?", the obvious first suspect when 8 ZoneInfos are added and the level goes fullbright in the same step.
**What happened:** `actor prop get ZONE_BAR_13z13z` prints only `Location=(...)` — explicitly-set properties only — so a freshly placed ZoneInfo looks like it has no properties at all. `class show Engine.ZoneInfo --category ZoneLight` prints only names and types. Neither tells you the default. The answer (`AmbientBrightness=0`, i.e. ZoneInfos are innocent) only exists in `docs/leveldesign/deusex/classes.md`, in one parenthetical:

    `class show` prints names and types only. To read a **default value**, decode it offline:
    `actor build DeusEx.<Class> | actor add - | actor prop get - <Prop>` (an unset property resolves to its class default).

i.e. you must *place a throwaway actor into your level*, query one named property at a time, then delete it. That paragraph lives in the DX class catalog, not in `lighting.md`, `zones-and-performance.md`, or `class show --help`, so I did not find it until I had already spent a preview cycle testing the hypothesis blind.
**What I expected:** `class show <Class>` to print `AmbientBrightness: ByteProperty = 0`, or `actor prop get <actor> <Prop>` to be advertised in `--help` as default-resolving.
**Workaround:** `T=$(uedcli actor build Engine.ZoneInfo --base-name TMPPROBE --at ... | uedcli actor add -); uedcli actor prop get "$T" AmbientBrightness; uedcli actor delete "$T"` — and note this also trips `warning: 2 actors share Location`, since the natural place to probe is next to the real actor.
**Also worth fixing in the docs:** `docs/leveldesign/general/lighting.md` says you can darken a space by "lowering the zone's `AmbientBrightness` (keep it <= ~32 so surfaces don't go flat)". That reads as though ambient starts somewhere above zero and is a knob you turn down. It starts at 0 — there is nothing to lower — and saying so explicitly would have removed my prime suspect in ten seconds.

## ContainerYard — `level preview --game` gives no signal that it is queued behind another user's lock
**What I tried:**
```
bin/uedcli level preview --game --map $P/build/CY.dx --out-dir $P/shots --size 800x600 <7 shots>
```
**What happened:** the process sat with no output for 31+ minutes (`ps -o etime` on the python
process was the only way to tell it was alive). Three agents share
`uedcli-game-preview-1000` and the verb serialises on it, but the waiting process prints nothing —
not "waiting for the shared preview container", not a queue position, not a heartbeat. It is
indistinguishable from a hang, which is exactly the state where the documented advice is "sleep 30 s
and retry" — and retrying makes the contention worse.
**What I expected:** one line on stderr when the lock is not immediately available, e.g.
`waiting for shared game container (held by another process, waited 45s)`, repeated on a slow
heartbeat. Even better, a `--lock-timeout` so a batch can fail fast instead of blocking a whole
session.
**Workaround:** poll `ps -o etime= -p <pid>` and the output directory by hand; never retry a
preview that is merely slow. Note this interacts badly with the earlier entry about deterministic
materialize failures — with no output at all you cannot tell "queued" from "failing and retrying".

## DiveBar — `class list` and `actor build` happily accept classes from a package the editor cannot load; you only find out at materialize
**What I tried:** `bin/uedcli class list --flat --subclass-of DeusEx.DeusExDecoration` listed `Endemia.Ashtray`, `Endemia.AshtraySmall_1a`..`_1f`, `Endemia.GlassBottle`, `Endemia.Candle1`, `Endemia.ToiletPaper`, `Endemia.TrashCan5`, `TNM.NapalmCanister` alongside the `DeusEx.*` ones, so I placed several: `bin/uedcli actor build Endemia.AshtraySmall_1b --at 192,176,44 --folder props | bin/uedcli actor add -`
**What happened:** Every one of those `actor build | actor add` calls succeeded and printed `added 1 actor(s)`. The level then refused to build, on every retry:

    materialize failed (nothing written): level references v68 code package(s) with no v69 stub: Endemia — the v69 editor cannot load a v68 `.u` directly; build the stub(s) first (`uedcli substrate stub <pkg>`) or the referencing level cannot materialize

**What I expected:** `class list` to either not offer classes the level cannot actually use, or to mark them; and `actor build Endemia.X` to refuse (or at minimum warn) at build time rather than 20 minutes later at materialize. The error message itself is genuinely good — it names the package AND the fix — but it fires at the wrong end of the pipeline, after the class is already scattered through the trunk.
**Extra sting:** the *previous* session on this level had already tried the same classes inside a shell helper that redirected stderr (`... 2>/dev/null | actor add - >/dev/null 2>&1 || echo "failed"`), so ~15 `Endemia.*` props were silently dropped and the level shipped without them and without anyone noticing. Two different agents lost time to the same package in two different ways. Note also that `bin/uedcli class list --flat` (unfiltered) reports the substrate packages as `DeusEx, DXOgg, Engine, TNM` — `Endemia` is not in that list, yet `--subclass-of` returns `Endemia.*` classes. Those two views disagree.
**Workaround:** grep the trunk for the offending package and delete/replace by hand:
`grep -rl "Class=Endemia" $UEDCLI_PROJECT/maps/<LEVEL>/actors/*/actor.t3d` then `actor delete`, substituting `DeusEx.LiquorBottle` / `DeusEx.WineBottle` / `DeusEx.Sodacan` for the Endemia clutter. A `level doctor` check for "references a package with no stub" would have caught this offline in a second.

## DiveBar — ~15 props were reported as "added" and then did not exist in the level (silent no-op placement, `Endemia.*`)
**What I tried:** the previous session on this level placed a batch of bar clutter with a helper of this shape (verbatim from `_scratch/levelbuild/dive-bar/build-03-detail.sh`):

    D() { c=$1; x=$2; y=$3; z=$4; yaw=${5:-0}; shift 5
      $U actor build "$c" --at $x,$y,$z --rotate 0,$yaw,0 --folder props "$@" | $U actor add - >/dev/null 2>&1 \
       || echo "  !! failed: $c"; }
    ...
    D Endemia.AshtraySmall_1a 208 656 60; D Endemia.AshtraySmall_1a 464 176 44
    for Y in 240 336 432 528 624; do D Endemia.WoodStool1 744 $Y 16 0; done
    for Y in 288 320 352 400 448 496 544 576; do D Endemia.GlassBottle 1072 $Y 92; done
    for Y in 300 340 420 470 520 560; do D Endemia.GlassBottle 1072 $Y 132; done
    for Y in 260 460 660; do D Endemia.GlassBottle 812 $Y 64; done
    D Endemia.Dumpster 448 -500 36 0
    D Endemia.SinkSmall 1400 300 60 49152; D Endemia.SinkSmall 1470 300 60 49152
    D Endemia.HandDry 1540 306 84 49152

**What happened:** roughly **15 `Endemia.*` props — every stool at the bar, every bottle on the back-bar shelves, both washroom sinks, the hand dryer, the alley dumpster, two ashtrays — are simply not in the level.** `bin/uedcli actor find` over all 275 actors returns **zero** names matching `WoodStool`, `GlassBottle`, `AshtraySmall`, `Dumpster`, `SinkSmall` or `HandDry`; `grep -rl "Class=Endemia" maps/DiveBar/actors/*/actor.t3d` returned nothing. The script's own `|| echo "  !! failed"` guard never fired, so nothing in its output said anything was wrong, and the milestone-3 screenshots were taken and accepted without anyone noticing the bar had no stools and the shelves no bottles. (The later `LiquorBottle`/`WineBottle`/`Liquor40oz` actors that ARE present are `DeusEx.*` classes the agent evidently substituted by hand afterwards, presumably having spotted the empty shelves in a render.)

**What I then did, and what it cost:** not knowing this history, I placed more of the same clutter with the same class names — this time WITHOUT stderr suppression:

    bin/uedcli actor build Endemia.AshtraySmall_1b --at 192,176,44 --folder props | bin/uedcli actor add -

Every call printed `editing level 'DiveBar' (from $UEDCLI_LEVEL)` / `added 1 actor(s)` and exited 0. `bin/uedcli level status` went from `actors: 275` to `actors: 290`, i.e. the tool agreed the actors were there. They were written into the trunk (`grep -rl "Class=Endemia"` found all 8 of mine). The problem surfaced only at build time, and then on every single retry:

    materialize failed (nothing written): level references v68 code package(s) with no v69 stub: Endemia — the v69 editor cannot load a v68 `.u` directly; build the stub(s) first (`uedcli substrate stub <pkg>`) or the referencing level cannot materialize

So the level had become **unbuildable**, and the only clue tying the failure to the eight `actor add` calls I had made twenty minutes earlier was the package name in that message.

**What I expected:** that `actor build <Package.Class>` for a package the toolchain cannot use would fail at `actor build` time, naming the package and pointing at `substrate stub` — the same excellent text materialize eventually produced, just emitted at the point where I could act on it in one second. Failing that, I expected `actor add` to be the gate. What I did not expect was for both to report success.

**Why this is the worst-shaped defect I hit:** the two failure modes are *opposite* and neither is visible.
- Under stderr suppression (the previous agent's case) the placement is a **silent no-op** — the tool says nothing, the actor count does not move, and you get a level that is quietly missing a third of its dressing. Nothing downstream ever complains, because a level with no `Endemia` reference builds fine.
- Without stderr suppression (my case) the placement **appears to succeed**, the actor count *does* move, and the trunk is poisoned — every subsequent build of the level fails until you find and delete the actors by hand.
Either way, the verb reports success while the outcome is wrong, and the discovery is deferred to the slowest, most expensive step in the pipeline.

**Also inconsistent:** `bin/uedcli class list --flat --subclass-of DeusEx.DeusExDecoration` cheerfully lists `Endemia.Ashtray`, `Endemia.AshtraySmall_1a`..`_1f`, `Endemia.GlassBottle`, `Endemia.Candle1`, `Endemia.ToiletPaper`, `Endemia.TrashCan5` and `TNM.NapalmCanister` interleaved with the usable `DeusEx.*` classes, with no marking. That listing is where I (and the previous agent) got the class names from. Yet unfiltered `bin/uedcli class list --flat` reports the substrate packages as only `DeusEx, DXOgg, Engine, TNM` — `Endemia` is not among them. Two views of the same catalog disagree about whether the package exists.

**Workaround:** `grep -rl "Class=Endemia" $UEDCLI_PROJECT/maps/<LEVEL>/actors/*/actor.t3d` to find them, `actor delete` each, and substitute `DeusEx.LiquorBottle` / `DeusEx.WineBottle` / `DeusEx.Sodacan`. Suggested fixes, in order of value: (1) reject the class at `actor build` with the message materialize already has; (2) mark or omit unstubbed packages in `class list`; (3) add a `level doctor` check for "trunk references a package with no v69 stub", so it is catchable offline in a second instead of after a multi-minute editor round-trip.

## TubePlatform — `level doctor` is clean while additive brushes block three doorways
**What I tried:** `bin/uedcli level doctor` after every geometry change. It reported `TubePlatform: no issues found.` throughout.
**What happened:** the level had **four** separate additive semisolid brushes occluding subtracted passages, none of which `doctor` sees:
- `CableTray_iwk14w` (a wall conduit, z60..76) crossed **all three** wall openings — the plant-room door, the service-niche mouth, and the exit passage — at 20..36 uu above a floor at z=40. `MaxStepHeight` is 25, so the top at 36 is an unsteppable bar across every route in the level.
- `AdPanel_4fniyy` sat across the plant-room doorway, cutting a 128-uu opening down to 56 uu (crouch-only).
- `AdPanel_hkhimd` sat across the service-niche mouth — the mouth of the vent crawl route.
- two crates stood directly in front of the vent mouth.

**What I expected:** `docs/usage.md` says `level doctor` "statically checks the level for the BSP/geometry problems that cause holes, HOMs, and **invisible walls** — fully offline". An additive brush hanging across a subtracted opening is exactly an invisible wall from the player's point of view, and it is trivially checkable offline: intersect each additive brush against each subtractive brush's volume and report the remaining free cross-section. Nothing in `doctor`'s categories covers it, and nothing in the docs warns that it does not.
**Workaround:** none from the tool — I found all four **only by reading `--game` renders and then hand-deriving the arc geometry in Python** (converting each brush corner to polar coordinates and testing it against the passage boxes). That took the better part of an hour, and two of the four were invisible in the wireframe schematic because `actor preview` draws brush outlines with no notion of solid-vs-void.
**Suggested check:** a `doctor` category like `occlusion` — for every additive/semisolid brush that intersects a subtracted volume, report the minimum free width and height through that volume, flagging anything below the player's standing box (and anything that leaves a lip taller than `MaxStepHeight` across a passage floor). This is the single highest-value check that could have been run on this level.

## TubePlatform — `brush poly list --json` centroid is a bare array and polys have no index field
**What I tried:**
```
bin/uedcli brush poly list AdPanel_ndtk5h --json | python3 -c "... d['polys'] ... p['centroid']['x'] ... p['index'] ..."
```
**What happened:** `TypeError: list indices must be integers or slices, not str`
**What I expected:** the text table prints `idx` and a `centroid` rendered as `(517,1102,152)`, and `actor bbox --json` emits its vectors as `{"x":…,"y":…,"z":…}` objects. I assumed `poly list --json` used the same vector shape and carried the `idx` column. It does neither: `centroid` is `[x, y, z]`, and there is no `index`/`idx` key — poly identity is positional in the array.
**Workaround:** `for i, p in enumerate(d['polys']): c = p['centroid']; ... c[0], c[1]`. Worth either aligning the vector encoding with `actor bbox --json` or documenting the difference in `docs/usage.md`'s `--json` note, since the two verbs are used together constantly.

## TubePlatform — no way to select a face by "which way does it point on a curve"
**What I tried:** `bin/uedcli brush poly find <AdPanel> --facing +Y` on a panel built with `--rotate 0,-4096,0`
**What happened:** matched nothing useful — every face of a yaw-rotated box reports `facing: slant`, so `--facing` is unusable on any brush that follows a curve. The same is true of every brush the `revolve`-built bore needed.
**What I expected:** `--facing` snaps to `±X/±Y/±Z or slant`, which is fine for axis-aligned work, but this level is an arc: **almost every detail brush is rotated**, so the one semantic face selector effectively does not apply to the whole map.
**Workaround:** dump `brush poly list --json` and pick the face with the largest `hypot(centroid.x, centroid.y)` (i.e. the one furthest from the arc centre) — I did this repeatedly. A `--facing outward/inward` relative to the brush's own centre, or `brush poly find --extreme +radius|+x|…`, would have removed most of the Python I wrote for this level.

## ContainerYard — `level materialize --no-verify` reports SUCCESS while writing a truncated, unusable map
**What I tried:**
```
bin/uedcli level materialize --out $P/build/CY.dx --overwrite --no-verify
```
on a 265-actor level (148 brush / 117 point).
**What happened:** it printed
```
materialized /home/neob91/.../container-yard/build/CY.dx
```
and exited 0 — but the file was **14,452 bytes**. The same level's previous good build was
**331,029 bytes**, and the other two agents' comparable maps are 190-254 KB. So the map was a stub:
essentially no BSP. Every `level preview --game --map <that file>` afterwards then sat for 10+
minutes per attempt producing nothing, and I lost roughly 70 minutes chasing what looked like
container contention before thinking to compare file sizes. Running the same materialize **with**
verify immediately showed the real cause:
```
materialize failed (nothing written): OBJ DEPENDENCIES PACKAGE=MyLevel did not complete within 20 attempts (20s)
```
**What I expected:** `--no-verify` to skip the *actor-identity* post-check (the documented false
positive it exists for), not to also suppress "the editor never finished the build". A success
message plus a written file is a promise that the build happened.
**Workaround:** never trust `--no-verify` alone — always assert on output size, e.g.
`[ "$(stat -c%s $MAP)" -gt 100000 ]`, and retry the materialize until it passes. Suggest either a
sanity floor inside materialize (a level with N brushes cannot produce a k-byte package) or
splitting the flag into `--no-verify-actors` vs the build-completed check, which should never be
skippable. This one is the single most expensive thing that happened in this session, because it
is silent and it *looks* like the documented transient.

## ContainerYard — `brush build sheet` produces a MIRRORED texture, and neither rotating nor re-aligning obviously fixes it
**What I tried:** a signboard on a fence, built with the documented sheet generator:
```
bin/uedcli brush build sheet --plane xz --width 128 --height 32 --flag masked \
  --at 1600,262,176 --texture Dockyard.dy_sign_04 | bin/uedcli actor add -
```
**What happened:** in the `--game` render the sign's lettering was **mirrored** (readable only
right-to-left). `brush poly find --json` showed the face `"facing": "+Y"`, i.e. we were behind it,
so I rotated it 180 degrees — after which `--json` correctly reported `"facing": "-Y"` and we were
in front of it, **and the lettering was still mirrored**, because the yaw rotates the TextureU axis
along with the geometry. Net zero.
**What I expected:** a way to flip the texture's U axis. `brush poly set --help` offers texture and
pan; there is no `--flip-u` / `--mirror` / negative-scale option, and the generator has no
`--facing`/`--flip` either. Nothing in `textures-and-surfaces.md` mentions that a sheet's texture
comes out reversed on one side, which is a 50% chance every time you place a sign.
**Workaround:** `brush poly align <BRUSH>:0 --wall --fresh-frame` DOES rebuild the frame from the
face normal and killed the mirroring — but it also re-derived the texel scale, so the 128x32 sign
came back tiling the texture instead of showing it once. Usable, but it changed two things when I
wanted one. For lettered textures on sheets the reliable move ended up being "pick a texture with
no lettering". A `--flip-u` on `brush poly set`, or a `--facing +Y|-Y` on `brush build sheet`,
would make signage a one-liner instead of three renders of trial and error.

## ContainerYard (polish pass) — every `brush build sheet` renders its texture HALF-SHIFTED

**What I tried:** placed six sheet signs with `brush build sheet --plane xz`, each on a texture
whose pixel size exactly matched the sheet (`Dockyard.dy_sign_05` 128x32 on a 128x32 sheet).
**What happened:** the sign rendered cut in half — the right half of the image on the left of the
panel and vice versa, with a hard seam down the middle. Same on every sheet in the level.
**Why:** the generator emits `Origin` at the sheet's **geometric centre** with `TextureU=+X`,
`TextureV=-Z`, so texel 0 lands in the MIDDLE of the panel and each quadrant wraps around to the
opposite side. `--at` centres the brush (documented) but nothing says the texture frame is centred
too.
**Workaround:** pan by half the sheet, in texels:
`brush poly find <Sign> | brush poly set - --pan-to <width/2>,<height/2>`.
**Cost:** this is invisible on tiling metal/concrete, which is why it survives; it only shows up the
moment a texture has lettering or a border, and then it looks like the sign is broken. A sheet whose
texture frame started at a CORNER would need no pan at all.

## ContainerYard (polish pass) — sheet mirroring IS deterministic and a 180-degree yaw DOES fix it

Refines the earlier "`brush build sheet` produces a MIRRORED texture" entry above, which concluded
that rotating 180 degrees was net zero. It is not, and the rule is simple:

> A `--plane xz` sheet reads **correctly from the +Y side** (camera at higher Y, looking in -Y) and
> **mirrored from the -Y side**. Add `--rotate 0,32768,0` (or `actor rotate <S> --to 0,32768,0`
> afterwards) for any sign that will be read from the -Y side.

**Evidence, all `--game` shots this session:**
- unrotated sheet at `y=772`, camera at `y=880` looking -Y -> "Ammunition Storage" reads correctly;
- unrotated sheet at `y=892`, camera at `y=760` looking +Y -> lettering mirrored; after
  `actor rotate --to 0,32768,0` (same camera) the replacement sign reads "DANGER DO NOT ENTER"
  correctly;
- gate sign rebuilt with `--rotate 0,32768,0`, read from the -Y side -> "Base Commander" correct.

The earlier report's step that fails is the *combination*: rotating AND then walking round to the
other side keeps you in front of the same mirrored image. Keep the viewer where the sign is meant to
be read from and the yaw is the whole fix. Vertex geometry is unaffected because a centred sheet is
symmetric under a 180-degree yaw. A `--facing` flag on `brush build sheet` would still be nicer than
knowing this.

## ContainerYard (polish pass) — `brush poly align --wall --fresh-frame` does not repair a rotated sheet frame

**What I tried:** a sheet whose stored frame was `TextureU=(0,0,1)`, `TextureV=(1,0,0)` — U running
VERTICALLY, so a 128x32 sign tiled four times and rendered its lettering on its side.
`--fresh-frame` says it "synthesize[s] a canonical texture frame from the face normal", which is
exactly what was wanted.
**What happened:** `brush poly align <Sign> --wall --fresh-frame` reported
`aligned 1 face target(s)` and exit 0, and the T3D came back **byte-identical**: still
`TextureU=(0,0,1) TextureV=(1,0,0)`. For a face whose local normal is +Y the "canonical" frame it
synthesises is the vertical-U one, so a rotated frame is a fixed point of the operation.
**Workaround:** rebuild the sheet with `brush build sheet` (whose emitted frame is the horizontal-U
one) and delete the old actor. Two verbs and a lost Name instead of one align.

## ContainerYard (polish pass) — a datacube's text package CAN be built offline; here is the whole loop

The datacube recipe says the text package is "outside uedcli" and stops there, which reads like a
dead end. It is not — the round trip works and is worth writing down:

```
ln -s <proj>/text /tmp/DX/ContainerYardText     # Classes/<Pkg>.uc + the .txt files
cp /tmp/DX/System/DeusEx.ini /tmp/DX/System/CYTextBuild.ini
# append EditPackages=ContainerYardText to the copy, NOT to the shared DeusEx.ini
cd /tmp/DX/System && wine ./UCC.exe make -ini=CYTextBuild.ini   # -> System/ContainerYardText.u
```

Two traps: `wine UCC.exe` fails with `L"C:\\windows\\system32\\UCC.exe" not found` — it must be
`wine ./UCC.exe`; and the path must be short (`/tmp/DX`, symlinks to the real tree), which is why
that working copy exists. Then drop the built `.u` into a dir listed in the project's `paths=` and
`level preview --game` mounts it like any other package (`project show` confirms it). `#exec
DEUSEXTEXT IMPORT NAME=...` normalises the object name's case (`06_DataCube01` -> `06_Datacube01`);
harmless, since Unreal names are case-insensitive.

## ContainerYard (polish pass) — texture-vs-sheet size mismatch is silent, and can hide 3/4 of a sign

Two signs used `CoreTexMisc.CautHardHats_A` / `CautStepWatch_A`, which are **256x256**, on **128x128**
sheets. The result shows one quadrant of the image — and because those textures put the artwork in
one quadrant and index-0 transparency in the rest, the signs rendered as a mostly-empty panel with a
sliver of lettering. `texture list` prints the size, so the data is there, but nothing warns when a
sheet's world size is not a whole multiple of its texture's pixel size. A warning on
`brush build sheet --texture` when `width % texW != 0` would have caught both.

## ContainerYard (polish pass) — `level materialize` wedged for the full 600 s bound, then succeeded unchanged

One run ended `MAP SAVE never produced a finished file ... no file appeared (after 601s, bound 600s)`
after 11 min of wall clock. Nothing was written (good), the trunk was untouched, and an identical
re-run 30 s later succeeded in ~90 s. Worth knowing that the failure mode is a *full-bound* stall,
not a fast error: budget 10 minutes of nothing before you learn you have to retry, and do not
interpret the stall as "the level is too big".

## TubePlatform (polish pass) — every builder-emitted face has U x V = +N, so lettered textures render MIRRORED

The single most expensive thing in this level's polish pass. Four ad panels and an RATP roundel
rendered their text **backwards**, and there is no verb that flips a texture axis.

Root cause is systematic, not per-brush: `builders._tex_basis(normal)` computes `v = cross(normal, u)`,
so **every** face any generator emits (cube, sheet, revolve, extrude...) satisfies `U x V = +N`.
`brush poly align --wall --fresh-frame` calls the *same* `_tex_basis`, so it cannot fix it either —
which is worth knowing before spending a render cycle on it, as this agent nearly did. The engine
draws a face with that handedness mirrored, so a lettered texture is backwards on every uedcli-built
surface. Symmetric wall/floor textures hide it; the moment a texture contains text, it is obvious.

The only lever that changes it is **`brush scale --by -1,1,1` + `brush apply-transform`**: the bake
transforms texture axes by the inverse-transpose and reverses winding on `det < 0`, which flips the
face's handedness while leaving a symmetric brush's geometry identical. For a brush whose local
vertices are already rotated (anything from `revolve`, or a baked `actor rotate`), the mirror also
re-orients the solid, so it needs a compensating `actor rotate --to 0,YAW,0` afterwards, where
`YAW = radial_angle - local_face_normal_angle` read back from the T3D. Verify with `actor bbox`
before/after: the box must be unchanged to <0.05 uu.

Two traps inside that workaround, both of which cost a full build+render cycle here:
- `--by -1,1,1` **reflects** the texture axes about local X; it only *negates* U when U happens to
  lie along local X. On a rotated brush it is a reflection about a different in-plane axis, so the
  net effect can be a 180-degree rotation rather than a mirror. Read the render, do not assume.
- `--by -1,1,-1` has `det = +1`, so it is a pure rotation and never un-mirrors anything.

A `brush poly set --flip-u` / `--flip-v` would collapse all of this into one command.

## TubePlatform (polish pass) — a texture-vs-face size mismatch reads as a black "+" cross, not as a crop

Related to the ContainerYard note above but with a different visible signature. `MolePeople.MP_doortrim`
is **128x256** on a 128x128 mover leaf; at the default 1 texel/uu the V window is `[-64,64]`, which
**wraps** and shows the texture's top 64 rows joined to its bottom 64 rows. Because a door texture
puts its trim at top and bottom and a dark panel in the middle, the result is a bright "+" of trim
with four black quadrants — which reads in-game as a *lighting* bug ("the mover is rendering black"),
and sent this agent chasing `bDynamicLightMover` and adding lights before spotting it was a wrap.
`brush poly set --pan-to 64,128` centres the window and fixes it. Rule of thumb: a symmetric
`u[-w/2,+w/2]` window on a texture wider/taller than the face always wraps; pan by half the face
size to get a non-wrapping window.

Also: setting `bDynamicLightMover=True` on a mover made it render *darker* in a static
`level preview --game` capture, not brighter — the doc's "black door" advice is about a moving door,
and the flag is not a fix for a rest-pose capture.

## TubePlatform (polish pass) — a shortened mover open-pose can still protrude through a curved wall

Shortening a slide so the leaf stays partly visible (the polish brief's rule) is not sufficient on
its own: the leaf's *pocket* has to be solid. This level's plant door slid +Y into what was solid
rock at the door plane but became station void 84 uu further along, because the station wall is a
`revolve` arc and the wall crosses X=1000 at Y=692. The open door therefore floated as a black slab
on the platform. Sliding it -Y instead put the pocket entirely inside rock. When a mover's pocket is
next to swept/curved geometry, check the pocket against the arc's radius, not against a bounding box —
`actor bbox` on a revolve brush spans the whole arc and tells you nothing about which side is solid.

Verifying an open pose at all needs a workaround: `level preview --game` renders movers at their rest
pose, so the only way to photograph the open pose is to `actor move` the mover by its key-1 offset,
materialize a throwaway map, shoot it, and move it back.

## TubePlatform (polish pass) — `Masked` is opt-in and nothing prompts you, but blanket-adding it PUNCHES HOLES

Confirming the cross-level finding: this level shipped with zero `Masked` polys, so
`MolePeople.WirePanel` on the vent grille drew its index-0 cut-outs as flat black and read as a solid
slab. `brush poly set <grille>:all --add-flag Masked` fixed it outright (before/after:
`_scratch/levelbuild/tube-platform/shots/polish/BEFORE-vent-grille.png` vs `AFTER-vent-grille.png` —
the black regions become the lit machinery behind the mesh).

The important qualifier: **the same texture was also on the vent DUCT, which is a `CSG_Subtract`, and
masking a subtract brush's wall faces would have made the room's own walls see-through into unbuilt
space (HOM).** Same for the exit shaft's `phbs_ladder_a` face, which is a shaft wall rather than a
separate ladder brush. `Masked` is only ever correct on a face that has real geometry *behind* it:
a mover leaf, an added detail brush mounted against a wall, a sheet. Deciding that needs the brush's
`CsgOper`, which `brush poly find` does not print — worth checking with `actor show` before flagging.
Here it meant flagging the grille mover, the gate mover and the added `TrackLadder` box, and
deliberately NOT flagging the two subtract walls that use the very same textures.

Two smaller notes from the same pass:
- **The texture catalog cannot tell you whether a texture has index-0 transparency.** The per-package
  JSON carries width/height/colors/image_hash but no palette or "has transparency" field, and the
  exported images are not kept on disk, so there is no offline way to predict whether `Masked` will
  do anything. The only test is a `--game` render. A `has_index0`/`masked_candidate` field in the
  manifest would turn a whole build+render cycle into a `texture list` lookup. (Flagging
  `Paris.pa_gate_a` turned out to be a no-op — its gaps are painted, not index 0 — which is exactly
  the guess that field would remove.)
- **A retry loop that size-checks the output must `rm` it first.** `timeout 480 ... --overwrite` that
  gets killed mid-build leaves the PREVIOUS good file in place, so the size check passes on stale
  bytes and the loop breaks with a false success — the runt-detection advice inverted. Delete the
  target before each attempt and check the mtime, not just the size.

## DiveBar — the `.con` import failure is ONE header field, and it is a derivable byte count

`dxlogue` compiled a `.con` that `ucc make`'s `DConImport` would not import, in two guises: with
`_mission_unrecognized1: 0` it imported nothing while `ucc` printed `Success - 0 error(s), 0
warnings`, and with the retail `Intro` value `51` copied in by hand it wedged `ucc` in an unbounded
loop (`UCC.log` frozen at 0 bytes). A previous pass had reduced the hang to "actor-table content"
and left the predicate open.

**It is not the actor table.** `MissionFile.unrecognized1` — documented as "◻ container artifact, no
runtime class; echo verbatim" — is the **byte length of the four name tables that follow it**
(`actors` + `flags` + `skills` + `objects`, each `4 + Σ(4 + len(name))`). Checked against every
`.con` on this machine (149 distinct files after content-dedup): **127 of 127 real ConEdit-produced
files match exactly**, across four independent producers (retail DEED-reconstructed, the DX SDK,
TNM/ConEditPlus, Confix). The only `fileVersion=28` file that disagrees is the one dxlogue wrote.
Retail `Intro` = 51 = `4 + (4+7) + (4+12)` for `[BobPage, WaltonSimons]` + three empty tables.

The "table chars ≤ 19 imports, ≥ 20 hangs" pattern from the earlier reduction was an artifact: 19
chars is exactly where the true block size equals the 51 being copied out of `Intro`. Once the
stored value and the true block size disagree by a little, `DConImport` resumes mid-record, reads a
garbage string length and loops forever; disagree by a lot (`0`, or 51 against a 67-byte block) and
it lands somewhere yielding zero conversations and writes an empty 217 B `Text.u`. Verified
irrelevant: name length, case, underscores, known-vs-unknown actor names, and `.con` size — a 369 B
file hangs while 370 B and 429 B import.

**Confirmed by construction.** Setting the field to the computed value, changing nothing else:
the 369 B hang shape → imports (`Text.u` 959 B); the 3-actor silent-skip shape → imports; and the
real DiveBar tree at `_mission_unrecognized1: 523` → **imports**, `DeusExConText.u` 33,418 B with
all four conversations and their spoken lines verified present in the bytes.

Two things worth carrying forward for anyone driving `ucc make` from a tool:

- **A hang with a zero-byte log is the worst failure mode available**, and it cost the previous pass
  hours of chasing a full disk, wine-prefix contention and a suspected truncated `System` copy. The
  harness that actually cracked it is cheap and belongs in any future spike: a pre-populated build
  root (`/tmp/dxbar`, a copy of `DX/System` with every dependency package symlinked and its `.u`
  future-dated so only the package under test recompiles) plus an isolated `WINEPREFIX`. One
  parameterised source → `ucc make` → verdict takes **~6 s** for an import and a bounded `timeout`
  for a hang, which turns "each build is slow, budget 4" into a 15-experiment sweep.
- **Never trust `ucc`'s exit code or its `Success` line** — both were clean for every single
  failure above, including the ones that produced no package at all. The only usable oracle is the
  artifact: `.u` size, plus grepping the built package for a known source string.

**A second defect surfaced the moment the first was fixed** (it had never been reachable before):
`DConImport` imported only **21 of 97** mp3s for DiveBar and still reported success —
`DeusExConAudioDiveBar.u` holds `ConAudioDiveBar_0 … _20` alone, though all 97 files were staged
correctly (1,882,448 B) and the `.con` carries 97 distinct paths. Because the audio list binds by
index and must be dense, that package is fully desynced past the 21st line. Not a missing-file
problem, not an mp3-format problem (all 44100 Hz mono 64 kbps), and not a plain path-length cutoff
(the 97 full paths span 47–58 chars and no prefix of that distribution sums to 21). Still open, and
it is what now blocks landing DiveBar's audio.

---

## DiveBar polish pass (2026-07-26) — friction

- **`level materialize --out <existing> --overwrite` can silently reuse the CACHED build.** It
  printed `materialized …` and exited 0, but the file's mtime never moved: 38 minutes of edits
  (surface flags, a mirrored sheet) were simply not in the map I then previewed. There is no
  `--rebuild` on `materialize` (that flag is `level preview --game`-only), so the only reliable way
  to force a fresh carve is a **new output filename**. `--overwrite` governs whether the *file* may
  be clobbered, not whether the *build* is redone — worth saying so in `--help`, because "overwrite"
  reads as "rebuild in place". **Check the mtime, not just the size**: the runt check in POLISH.md
  catches a truncated build but not a stale one, and a stale build is byte-identical in size.
- **The runt trap is real and reproducible.** One `materialize` of a 291-actor level wrote
  **23,845 bytes** (good build: ~209,000) and reported success with exit 0. The very next identical
  invocation wrote 209,263. So the failure is transient, not deterministic — a retry loop plus a
  size floor is the only safe pattern.
- **A retry loop must distinguish transient from terminal failures.** Mine burned all five attempts
  (and 2.5 min of `sleep`) on `refusing to overwrite existing file`, which no amount of retrying
  fixes. Retry on container errors (`docker exec … wmctrl -l returned 1`, `sed … returned 4`), not
  on refusals.
- **`brush poly set` has no texture SCALE control** — only `--pan-to/--pan-by` and
  `brush poly align --wall|--floor|--ring`. When a texture reads at the wrong size (brick courses
  too coarse for the surface) the only lever is *choosing a different texture*. Worth naming in
  `docs/leveldesign/general/textures-and-surfaces.md`, which currently implies alignment can fix
  scale.
- **`brush poly show` does not exist** (it is `brush poly list`); the error is clear, but `list`
  vs `find` vs `show` is the one place the verb naming diverges from `actor`.
- **There is no ladder/climb class in this DX substrate.** `class list --flat --depth all` (1,345
  classes) matches nothing on `ladder|climb|stair`. A level whose only cellar access is a vertical
  shaft is therefore a one-way trap; the fix is a `StandOpenTimed` `Engine.Mover` lift. Worth a line
  in `docs/leveldesign/deusex/` — a designer will reach for a ladder and find none.
- **`CoreTexMetal.ladder_a` carries a masked lattice**, so painting it straight onto a *solid* shaft
  wall renders the void through the rungs. It needs to be a sheet standing off the wall, or the
  `masked` flag has to come off. Same class of trap as the sheet-mirroring note above.
- **Finding buried lights is a scriptable check uedcli could own.** Five of this level's 40 lights
  sat strictly inside a solid brush (two inside their own door mover, one inside a structural
  column, two inside a floor dais) and therefore lit nothing — the visible symptom was pure-black
  doors and an unlit cellar. Point-in-brush-bbox over `Engine.Light` found all five in seconds, and
  it is exactly the sort of thing `level doctor` could report next to its `csg_order` findings.
- **`level doctor` flags a skybox as a stray subtract.** `SKYROOM … overlaps no other brush` is
  correct-by-construction for a sealed sky room with a `SkyZoneInfo` in it; it is the level's only
  finding, so it trains you to ignore the one line doctor prints.

## Conversation audio: `DConImport` synthesizes the mp3 filename (2026-07-26)

- **A DiveBar build imported 21 of 97 conversation mp3s while `ucc` printed `Success - 0 error(s),
  0 warnings`.** The 21 were exactly the ChoiceOption clips; all 76 Speech clips were dropped. The
  reason is in `System/UCC.log` at `Log:` level, once per dropped line — *not* in `ucc`'s summary,
  and not counted as a warning:
  `Log: ImportSpeechAudio Failed: ..\DeusExConversations\Audio\DiveBar\divebar_keep\DiveBarKeep\divebar_keep01.mp3`.
- **`DConImport` never reads the `mp3` path stored in the `.con`. It builds the filename itself.**
  From `ConSys.dll` (`DConImport::ImportSpeechAudio` RVA `0xe0d0`, `ImportChoiceAudio` `0xe3c0`,
  `ImportAudio` `0xdd40`): `..\<importPkg>\Audio\<audioPackage>\<owner>\<conversation>\<base>.mp3`,
  with `<base>` = `<speaker actor name><NN>` for a Speech (`NN` = 1-based counter per conversation
  per speaker, advanced in **event order** over every Speech event) and `Choice<NN><letter>` for a
  choice option (`NN` = ordinal of the Choice event in the conversation, letter = `'a'+index`).
  Speech in an **infolink** conversation uses `InfoLink\<conversation>\` instead of
  `<owner>\<conversation>\`; choice audio does **not** — an engine asymmetry.
  dxlogue's DiveBar source had hand-picked bases (`Keep01`, `JC01`, `Bum01`, …), so every Speech
  lookup missed; the Choice clips happened to already use the engine's own `Choice<NN><letter>`
  convention, which is the entire explanation for "21".
- **Verified by rebuilding, not by exit code.** Re-staging the *byte-identical* `.con` with the 97
  clips renamed to the derived names gave `DeusExConAudioDiveBar.u` = 1,887,781 B with
  `ConAudioDiveBar_0 … _96` (97 dense sounds), zero `ImportSpeechAudio Failed`, and all 97 mp3
  payloads byte-present. The failing build: 288,059 B, `_0 … _20`.
- **Lesson for the pipeline generally:** `ucc make`'s `Success - 0 error(s), 0 warnings` covers only
  the UnrealScript compile. Everything a `#exec` commandlet does — conversation import, audio import,
  texture import — reports at `Log:` level and cannot fail the build. Any build wrapper must diff the
  *artifact* (object count, package size, named objects) against what was staged.
- A failed audio slot is **not** a shifted list: `ImportAudio` returns `-1` and that `-1` is written
  into that speech's `soundID` in the same pass, so the symptom is one silent line, provided the Text
  and Audio packages are built in the same run.

## ContainerYard (masking/sheet fix pass, 2026-07-26) — grep is why the level looked broken, and the real bug was the inverse

I was sent in to fix two "already root-caused" faults: chain-link rendering opaque because **no poly
in the level carries `Masked`**, and six sheet brushes rendering one-sided because **none carry
`TwoSided`**. Neither premise held — both had been fixed in an earlier pass. What had not changed was
the *way the level was inspected*.

**Why the premise looked true.** The T3D trunk stores surface flags as a **number** on the
`Begin Polygon` line: `Flags=2` is `masked`, `Flags=266` is `masked|notsolid|twosided`. The word
`Masked` appears nowhere in the file, so `grep -r Masked maps/` returns nothing on a level that is
fully masked. Meanwhile the one thing that *does* grep is `PolyFlags=32` — which is the **actor-level
solidity** property (semisolid) and is never a surface flag. So the search that "proves" no flags are
set finds only the property that cannot be one. `brush poly list` decodes to names and answers it in
one call. Actual state: 21 chain-link polys all `masked`, all six sheets `masked,notsolid,twosided`,
all six signs legible and correctly facing in `--game`. **Worth a line in
`docs/leveldesign/general/textures-and-surfaces.md`: surface flags are numeric in T3D — audit them
with `brush poly list`, never with grep.**

### The real defect was the inverse of the briefed one: a cut-out texture on a SOLID face

`CoreTexMetal.ladder_a` is a masked-lattice texture, and it had been painted across the **full
512x128 north flank** of two stacked, solid, additive containers (`Cont_9v40jz:2`, `Cont_si1i03:2`).
It renders see-through **with no surface flag at all** — in UE1 the texture's own flags are OR'ed
into the surface's at render time. The result: standing north of the container stack you look
*straight through two solid containers* into the yard. That is the reported "some polys are just
invisible", and auditing `Masked` could never have found it: the offending polys decode to
`flags: none`.

This is the same trap the DiveBar pass logged ("`ladder_a` carries a masked lattice, so painting it
onto a solid shaft wall renders the void through the rungs"), reached independently here. That is
**two levels out of three**, so it deserves promoting out of this log and into the surface docs: *a
cut-out texture is a hole-punch wherever it lands, flag or no flag — it belongs only on a face with
real geometry behind it.*

### `level preview --native` is a FREE oracle for "does this texture have index-0 transparency"

The DiveBar pass logged that the catalog cannot predict whether `Masked` will do anything and that
"the only test is a `--game` render". There is a much cheaper one, and it falls straight out of the
documented `--native` caveat: **`--native` renders masked faces opaque, so a cut-out texture shows
its index-0 key as raw magenta.** One offline, container-free, few-second render settles it
(`_scratch/levelbuild/container-yard/shots/fix-round/native-ladder.png` — solid magenta between the
rungs; `before-ladder-game.png`, the `--game` shot at the identical pose, shows the yard through the
same pixels). The doc line "`--native` will lie to you about masking" is true, and is exactly what
makes it a detector.

A second, even cheaper signal: the catalog's auto-derived dominant `colors` already encodes this.
Every cut-out texture in this level lists **`pink`** (`ClenChainlink_B`, `ladder_a`,
`DangDoNoEnter_A`); none of the other 42 textures the level uses does. That is the
`has_index0`/`masked_candidate` field the DiveBar note asked for — already in the manifest, just not
named. A `texture list --cutout` filter over it would turn the whole question into a lookup.

### Blanket-flagging leaves a mechanically detectable trail

Cross-referencing every texture the level uses against its catalog entry and its flag sets took one
script and found the other defect immediately: `CoreTexMetal.ShipGrayMetal_A` (dominant colour
*brown*, no cut-out signature) was `masked` on 12 polys — both gate posts, all six faces each — and
unflagged on its other 15 uses in the same level. A texture that is masked on some faces and not
others, with no cut-out signature, is a blanket `--add-flag` that swallowed a whole brush.
**`level doctor` could own this**: it already reasons about solidity misuse, and both "masked on a
face whose texture has no index-0 key" and "same texture, inconsistent mask flags" are statically
decidable from the trunk plus the catalog.

### This trunk deterministically wedges the editor, and the bounds are not reachable from the CLI

**Twelve `level materialize` attempts over ~90 minutes, zero successes**, every one writing nothing
(which is the right behaviour — the last known-good map was never at risk). Two failure shapes, and
both are documented here as *transients*:

- `OBJ DEPENDENCIES PACKAGE=MyLevel did not complete within 20 attempts (20s)` — 9 times, fast.
- `MAP SAVE never produced a finished file ... (after 601s, bound 600s)` — 3 times, i.e. ten minutes
  of nothing before the error.

They are not transient here. The decisive evidence is a **control build**: `TubePlatform` in the same
install, on the same box, materialized fine in the middle of the run (it reached post-verify and only
tripped the known `Base=LevelInfo'MyLevel.LevelInfo0'` false positive). So the harness, the
containers and the wine prefix are all healthy — this one trunk is not buildable. Two further probes
narrowed it: removing the only two actors edited since the last good build did not help, and neither
did rebuilding from an isolated project whose `paths` drops the level's own `packages/System`. The
failure also **predates any edit of mine** (first failure 05:33, first edit 05:55), and the level's
last good build was 04:34 with the trunk edited at 04:36.

Two things worth acting on:

- **`max_attempts`/`poll_interval` in `dump_obj_dependencies` (`uedcli/qualify.py`) are hardcoded
  defaults with no CLI or env override**, as is the 600 s `MAP SAVE` bound. When a level crosses
  whatever threshold this one crossed, an agent has no lever at all short of editing uedcli source —
  which is exactly what a level-building agent must not do. A `--build-timeout`/
  `UEDCLI_BUILD_TIMEOUT` escape hatch would have turned a hard stop into a slow build.
- **The retry advice in this file needs a bound.** "Retry after ~30 s" is right for a genuine
  transient, but a deterministic failure is indistinguishable from one until you have burned an hour.
  The cheap discriminator is the control build: **materialize a known-good different level before
  the third retry.** Two minutes there replaces an hour of retrying, and it is what finally told me
  the box was fine.

Also worth a number: this box has **4 cores**, and it spent much of the run at **load average 63 with
170 MB of 7.9 GB free**, from roughly a dozen concurrent `dx-lum-uned` containers belonging to other
agent sessions. `dev/docs/parallel-editors.md` should carry a hard ceiling, because past it every
session's builds fail in ways that read as level defects rather than as contention. Editor containers
also **outlive their driving process** — several were still up 4+ hours later holding memory, and a
failed materialize reliably leaves one behind. A `uedcli` reaper for `uned-*` containers with no live
parent would recover the box without a human having to work out which container belongs to which
session, which an agent cannot safely do since it must not kill containers it did not create.
