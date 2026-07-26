# UnrealEd 2.2 — console command reference

The exec verbs uedcli drives, plus a catalog of the **full** editor/engine exec vocabulary
extracted from the binaries. Setup: the `dx-lum-uned` container runs UED22 under wine on Xvfb
`:99` + fluxbox, driven by `wine_ctl.py` over `docker exec`. Substrate = committed
`Tools/uedcli/uned/UED22` (EditPackages stripped to the engine/builder set; `DeusEx*`/LUM commented out).

For *weird behaviors* see [`quirks.md`](quirks.md); for producing an image see
[`rendering.md`](rendering.md); for **how this catalog was extracted** see
[`extracting-from-dll.md`](extracting-from-dll.md).

> **Confidence:** ✅ = uedcli-used / live-verified · 🔬 = live-probed this session · 📖 =
> extracted from the binary string table (token + arg keys real; exact semantics inferred).

## Driving the editor (`wine_ctl.py`)
- Commands go into the bottom **"Command:" box** via XTEST: `windowactivate` then
  `xdotool type/key/click` **without `--window`** (wine ignores synthetic `--window` events).
  The box is cleared with `End`, `Shift+Home`, `Delete` — **NOT `Ctrl+A`** (UnrealEd binds
  Ctrl+A to "select all actors").
- Reads: `MAP EXPORT` (whole-level T3D) and `EDIT COPY` → X clipboard via `xclip`
  (selection-scoped, **no coordinate offset**).
- The **log window** is a separate engine console (`>` prompt) reaching `GET`/`SET`/`OBJ`.
- **Liveness/crash check on every command** (`_assert_alive`) → `DriverError`, never a silent
  no-op. Recover a wedged editor: `docker compose up -d --force-recreate` (~60–90 s).
- **Driving is FIRE-AND-FORGET — a returned `exec` does NOT mean the verb finished.** ✅ `wine_ctl
  exec` types the line, presses Return, sleeps **0.3 s** (only to catch a crash dialog) and returns,
  so it is back while a `MAP REBUILD` / `MAP SAVE` is still running; **no console verb reports
  completion or a result back to the caller**. Anything that must observe a verb's OUTPUT has to
  wait for that output itself: for a file-producing verb, poll the file until its size is non-zero,
  has STOPPED CHANGING for several reads, and — because a part-written file's size holds just as
  steady as a finished one's — until the BYTES say it is complete (`driver.map_save` checks the
  written package's header via `driver.package_header_problem`; see "`MAP SAVE` writes `Save.tmp`"
  below for what a part-written `.dx` can actually look like); for a
  log-producing verb, read `Editor.log` forward past a
  guaranteed-noisy settle command (`qualify.dump_obj_dependencies`) — never a fixed sleep. Ignoring
  this produced a live failure: "`MAP SAVE`/`docker cp` … fail 'nothing written'" (2026-07-18
  UnrealEd-golden spike). *(A second alleged instance — "a truncated `Leaves` array captured from a
  half-written `.dx`" — was RETRACTED: `spikes/2026-07-15-native-materialize/sections/`
  `91-leaves-overproduction.md` re-built the same golden behind a far more generous idle barrier and
  got a byte-identical Model body, so the 762-leaf array is a deterministic property of the headless
  `IMPORT→REBUILD→SAVE`, not a truncation. The wait rule stands on the first failure and on the save
  mechanism below; it never had two instances.)* See
  `quirks.md` §"a reused editor … loses the next `MAP SAVE`" and the 4 KB log-buffering entry.
- **`MAP SAVE` writes `Save.tmp` and MOVES it onto the destination — the header is patched LAST.**
  📖 Extracted 2026-07-25 from the editor's own `core.dll` string table
  (`spikes/2026-07-25-map-save-mechanism/`, `extracting-from-dll.md` method): the
  `UObject::SavePackage` literals `SaveExports → SaveImportMap → SaveExportMap → RewriteSummary`,
  then `Save.tmp`, then `Moving '%s' to '%s'`, sit at consecutive offsets IN THAT ORDER in the string
  table, from which the phase sequence is inferred — the package is serialized into
  a temp file, its SUMMARY (the 36-byte header carrying every table's count+offset) is rewritten LAST
  inside that temp, and only then is the temp moved onto the target path. Consequence for anyone
  waiting on a save: a crash mid-serialize leaves the destination ABSENT, **or the previous file
  untouched — still complete, still carrying its old mtime**, which is why a wait must compare
  against a PRE-SAVE stat and not merely check that a file is there.
  - **NOT known: whether that move is a rename or a byte copy** — and therefore whether a truncated
    file can ever appear at the destination at all. The import table settles nothing: `core.dll`
    imports no `MoveFile*`/`CopyFile*`, but it also imports **no `ReadFile`** and no file-mapping
    API, while it demonstrably READS packages — so its file I/O does not go through the import table
    (it imports `GetProcAddress`/`LoadLibrary*`) and the absence of `MoveFile*` proves nothing. (For
    the record its file-API imports are `CreateFileW`, `WriteFile`, `SetFilePointerEx`,
    `FlushFileBuffers`, `GetFileInformationByHandle`, `GetFileType`, plus the
    `FindFirstFileExW`/`FindNextFileW` directory walk — no read, move or copy among them.)
    `driver.map_save` therefore treats its header check as insurance, not as a known-live failure
    mode; **no truncated destination has ever been observed** (the one report was retracted — see
    the paragraph above). Both halves are pinned by `test_engine_facts.py`.
  - **Inferred, not extracted: where `Save.tmp` is created.** The string is a bare `Save.tmp` with
    no directory, so it is presumably the target's directory (UE1 builds the temp path beside the
    destination) — but the string table does not show it, and it has not been checked live. If it
    is, the fixed name means two saves into one directory collide and a crashed save leaves a stray
    `Save.tmp` (`board/inbox.md` chore — verify by driving a big `MAP SAVE` and listing `/work`
    mid-save).
- GUI menu/dialog driving is fragile (menus paint black) — **prefer console verbs.**

## `MAP` ✅
| Verb | Effect |
|---|---|
| `MAP GRID X=1 Y=1 Z=1` | snap grid — **set to 1 before `IMPORTADD`** for exact coords |
| `MAP ROTGRID PITCH= YAW= ROLL=` | rotation snap grid |
| `MAP EXPORT FILE=<Z:\…>` | whole-level T3D (the query read path) |
| `MAP IMPORT` / `MAP IMPORTADD FILE=<Z:\…>` | replace / add actors from T3D; **point actors enter this way** |
| `MAP REBUILD` | rebuild geometry/BSP **only** (wipes lighting) |
| `MAP NEW` | empty level — its `MAP EXPORT` holds exactly `LevelInfo` + the builder brush; **no viewport `Camera` actors enter the level** (🔬 2026-06-28; the 4 editor viewports are UI objects, not level actors — so materialize/`level apply` post-verify never sees a spurious `Camera`) |
| `MAP SAVE` / `MAP LOAD FILE=<Z:\…>` | save/open `.dx` (preserves BSP/lightmaps/myLevel). ✅ `SAVE` answers NOTHING over the console and does not block the caller — wait for the written file to reach a stable non-zero size AND for its 36-byte header to describe a complete package before reading it (see "Driving is fire-and-forget" + "`MAP SAVE` writes `Save.tmp`" above; `driver.map_save` does this) |
| `MAP SENDTO FIRST\|LAST` | reorder selected brush in CSG order (no uedcli caller — CSG order is authored as `order_value` in the trunk) |
| `MAP SELECT ADDS\|SUBTRACTS\|SEMISOLIDS\|NONSOLIDS` | select brushes by CSG type (no uedcli caller — selection by CSG op is a model-side `actor find` query) |
| `MAP SETBRUSH …` 📖 | set brush props (`CSGOPER=`, `COLOR=`, `SETFLAGS=`, `CLEARFLAGS=`, `GROUP=`) |

## `BRUSH` ✅ 🔬
`ADD` (additive, selectable) · `SUBTRACT` (subtractive — identical to authoring
`CsgOper=CSG_Subtract`+paste, see `quirks.md`) · `FROM INTERSECTION` / `FROM DEINTERSECTION`
(the `tests/editor_oracle.py` golden regenerator issues these directly; there are no `Driver` wrappers — the shipping verbs are native) · `IMPORT`/`EXPORT FILE=` (red builder polylist) · `LOAD`/`SAVE` ·
`MOVETO X= Y= Z=` / `MOVEREL` · `ROTATETO`/`ROTATEREL PITCH= YAW= ROLL=` 📖 ·
`SCALE`/`SHEER SHEER= SHEERAXIS=` 📖 · **`BRUSH MIRROR` 🔬** (operates on the **builder
brush**, not selected world brushes; no axis arg → mirrors ALL 3 axes simultaneously, setting
`MainScale=(Scale=(X=-1,Y=-1,Z=-1),...)`; result string: "Brush Mirror") ·
`RESET` 📖 · `NEW` 📖 ·
**`BRUSH ADDMOVER` 🔬** (creates `Mover` class actor from current builder brush shape; log:
`Preparing brush <name>`; keyframe positions set via T3D hacking, not this verb — see Spike 7,
and the 2026-06-25 mover data-model spike
[`../spikes/2026-06-25-mover-keyframe-basepos-semantics.md`](../spikes/2026-06-25-mover-keyframe-basepos-semantics.md):
keyframe values are AUTHORED T3D props, so uedcli authors movers model-side via `brush build
--mover-class` + the `mover key` verbs — no editor) ·
**`BRUSH APPLYTRANSFORM` 🔬** (bakes the builder brush's **full transform — `MainScale` +
`Rotation` + `PostScale`** — into world-space vertex coords and resets all three to identity;
log: "Apply brush transform"; also works on selected world brush actors. See `ACTOR APPLYTRANSFORM`
below + `../spikes/2026-06-25-mainscale-postscale-applytransform.md`).
**`BRUSH CLIP` is GUI-marker-only** (FLIP/SPLIT/DELMARKERS),
not console-drivable → uedcli clips model-side (`clip.py`). ⚠️ **`BRUSHCLIP`
(one token, no space) 🔬 reproducibly crashes the editor (3/3 attempts, GPF on
the next command) — never use it** (`2026-06-17-brush-clip.md`).

## `ACTOR` / selection ✅ 🔬
- `ACTOR SELECT NONE|ALL|INSIDE|INVERT|UNSELECTED` · `OFCLASS CLASS=` / `OFSUBCLASS` 📖 ·
  `MATCHING` (TEXTURE/ITEMS/ADJACENT/COPLANARS/...) 📖 · `DELETED` 📖.
- **`ACTOR DUPLICATE` 🔬** — duplicates all selected actors in place with a small XY offset
  (~16 uu). Log: no text output observed (4 KB buffer). Works for point actors and brushes.
- **`ACTOR MIRROR X=-1|Y=-1|Z=-1` 🔬** — mirrors selected brush actors by setting
  `MainScale.Scale.<axis> = -1`. Point actors are accepted without error but show no visible
  property change (no geometry to mirror). Combine with `ACTOR APPLYTRANSFORM` to bake the
  mirror into vertex coordinates. Confirmed syntax from `unrealed.exe` string table — the
  earlier `BRUSH MIRROR XY` entry in this doc was a mis-inference.
- **`ACTOR APPLYTRANSFORM` 🔬** — bakes the brush actor's **ENTIRE transform — `MainScale` +
  `Rotation` + `PostScale`** — into world-space vertex coordinates and resets all three to identity
  (verified 2026-06-25, `../spikes/2026-06-25-mainscale-postscale-applytransform.md`: MainScale is
  local/pre-rotation, PostScale is world/post-rotation, `world = Location + PostScale·R·MainScale·
  (v−PrePivot)`; corrects the earlier "MainScale only" claim). The bake is
  `v' = T·v`, **`PrePivot' = T·PrePivot` (transformed, NOT zeroed)**, `Location` UNCHANGED
  (`T = PostScale·R·MainScale`; verified live, `../spikes/2026-06-25-scale-transform-mechanics.md`).
  Because it **rewrites `PrePivot`**, it must NOT be run on a `Mover` implicitly — the PrePivot is
  the swing axis (D8); and it bakes geometry but **leaves `KeyPos`/`KeyRot`**, so scaling a mover
  this way desyncs its travel from its brush. Works on selected brush actors,
  **including `MAP IMPORTADD` ones** (unlike `ACTOR DELETE`). For a **negative** scale axis (mirror)
  it reverses polygon winding so the baked brush stays CSG-valid. Log: "Apply brush transform".
  Use after `ACTOR MIRROR X=-1` to produce a properly-wound mirrored brush with neutral transform.
- `ACTOR RESET` 📖 · `ALIGN SNAPTOGRID` 📖 · `HIDE`/`UNHIDE` 📖 ·
  **`ACTOR KEYFRAME NUM=#` 🔬** (sets editing keyframe index `KeyNum=N` on a selected Mover;
  recomputes that mover's `Location`/`Rotation` to `BasePos + KeyPos[KeyNum]` — the derived-view
  model, spike `../spikes/2026-06-25-mover-keyframe-basepos-semantics.md`. NOT a uedcli authoring
  path: keyframe poses are authored in T3D, so uedcli sets them model-side via `mover key`) ·
  `BAKEPREPIVOT` 📖.
- **There is no console verb for setting individual actor properties directly** (🔬 2026-06-24).
  Neither `ACTOR SET Location=...` nor `ACTOR Name=<n> <prop>=<value>` nor any other syntax
  moved an actor via the console. The only mutation paths are (a) `ACTOR DELETE` to remove
  a selected point actor (confirmed working via `SELECTNAME`+`ACTOR DELETE`) and (b) delete
  + `MAP IMPORTADD` re-add at the new position. There is no `ImportActorProperties` console
  equivalent — it is an internal editor function, not a console verb.
- **`SELECTNAME NAME=<name>` 🔬 — real select-by-name (corrects the old "no select-by-name"!).**
  Verified: it sets the editor selection to exactly the named actor (read back via `EDIT
  COPY`); works for **point actors AND brushes, including `MAP IMPORTADD` brushes** that
  `SELECT INSIDE` can't reach. It **replaces** the selection (not additive) and **no-ops on a
  missing name**. **Case-insensitive** (🔬 2026-06-23): `NAME=helperlight0` and `NAME=HELPERLIGHT0`
  both select `HelperLight0`; the canonical stored name is unchanged. Exact match only — no
  globs, no prefix match (🔬). Actionable for **point actors** (`SELECTNAME` + `ACTOR DELETE`
  removes a Light); **IMPORTADD brushes** select-for-read but `ACTOR DELETE` still no-ops on
  them (the missing-`Bound` quirk — brush *mutation* still needs the paste/`BRUSH ADD` path).
  See the simplification lead in `../board/to-spec.md`.
- `SELECT MEMORY` / `UNION` / `INTERSECT` / `XOR` / `RECALL` 📖 — selection-set algebra
  ("And/Or/Xor With Memory").

## `POLY` / surfaces 📖 ✅
Surface (BSP-poly) ops. They act on the **built** `Model`'s surfaces, so they need a `MAP REBUILD`
first. ⚠ Only **`POLY TEXALIGN`** has been disassembled and driven: *it* walks `Model->Surfs`, acts
only on the ones carrying `PF_Selected`, and writes each result back down into the originating brush
polygon via `polyUpdateMaster` — which is why a `MAP EXPORT` reads it back. **Do not assume the same
of the other `POLY` verbs**: `SELECT` obviously does not (it *sets* the selection), and nothing here
establishes the selection-scoping or the master write-back for `TEXPAN`/`TEXSCALE`/`SETFLAGS=`/the
detail verbs.
- **Selection** — `POLY SELECT NONE` ✅ / `ALL` ✅ (both driven live 2026-07-26) · `REVERSE` 📖 ·
  `MATCHING GROUPS|ITEMS|BRUSH|TEXTURE|POLYFLAGS` 📖 ·
  `ADJACENT ALL|COPLANARS|WALLS|FLOORS|CEILINGS|SLANTS` 📖 ·
  `MEMORY SET|RECALL|UNION|INTERSECT|XOR` 📖 · `ZONE` 📖. (Only `NONE`/`ALL` have been driven; the
  rest is the string-table vocabulary, semantics inferred.)
- **Flags/texture** 📖 `SETFLAGS=`/`CLEARFLAGS=` · `TEXTURE DEFAULT|SET` · `MAKETEXTURECURRENT` ·
  `TEXTURENAME` · `TEXINFO` · `TESSELLATE`.
- **Texture transform** 📖 `TEXPAN [RELATIVE] U= V=` · `TEXSCALE [RELATIVE] UU= UV= VU= VV=` ·
  `TEXMULT`.
- **Texture ALIGNMENT** ✅ — **`POLY TEXALIGN
  DEFAULT|FLOOR|WALLDIR|WALLPAN|WALLCOLUMN|ONETILE|WALLX|WALLY|CLAMP [TEXELS=<n>]`**. NINE mode
  tokens (this entry used to list six — `DEFAULT`, `WALLPAN` and `WALLCOLUMN` were missing), and
  `TEXELS=` is **parsed but never read**. `ONETILE` and `WALLCOLUMN` are **no-ops in UED22** —
  there is no fit-a-tile-to-a-face operation in this editor. The measured per-mode semantics
  (formulas, guard thresholds, anchors, and how they differ from uedcli's `brush poly align`) are in
  **[`texalign.md`](texalign.md)**; evidence
  `../spikes/2026-07-26-unrealed-texalign-semantics/`, live 2026-07-26.
- **Detail textures** 📖 `SETDETAIL`/`CLEARDETAIL`/`APPLYDETAIL`/`REPLACEDETAIL`/`BATCHAPPLY` ·
  `REMIP` · `CULL`.

(uedcli edits surface attrs model-side instead — see `quirks.md`.)

## `EDIT` ✅
`EDIT COPY` (selection→clipboard, no offset) · `EDIT PASTE` (clipboard→level, **+32uu drift**,
see `quirks.md`) · `EDIT CUT` · `PASTEPOS`/`PIVOT HERE|SNAPPED` 📖.

## `EXEC <file>` ✅ — run a command-script file (batch N commands in ONE submission)
Live-verified 2026-07-18 (spike `../spikes/2026-07-18-exec-file-console-batch/`; regression
`test_driver_integration.py::test_exec_file_runs_script_and_continues_past_errors`). The file is
imported as a TextBuffer (`Editor.log`: `Execing <file>` + a `FactoryCreateText` line) and its
lines execute **in order, synchronously**:
- **Path:** a relative filename resolves against the **System dir** (`/opt/UED22`), NOT the CWD
  or `/work` — always pass an absolute `Z:\work\...` path. **LF and CRLF both work** (the
  CRLF-only trap is the ini parser, not this).
- **Errors do NOT abort:** an unrecognized verb or a failing command (bad `OBJ LOAD`, garbage
  `MAP IMPORTADD`) is skipped and the script continues — and there is NO per-command feedback,
  so completion/errors are detected by effects (marker files, log, liveness), exactly like the
  typed console. Pattern: make the LAST line a marker write (e.g. `MAP EXPORT
  FILE=Z:\work\<uuid>-done.t3d`) and poll for it.
- **The GC "Cleaning up..." `xmessage` dialog does NOT stall a script** — a `MAP NEW` mid-script
  pops it, and the following script lines still execute while it's up (it blocks the Command-BOX
  input path, not the engine's exec loop; dismiss it before the NEXT typed submission as usual —
  see `quirks.md` Stability). This makes a script drive strictly more dialog-robust than typing
  the same commands one at a time.
- **Nested `EXEC` works** (inner script runs, outer continues).
- **~6× less drive overhead** than per-command typing (6 cmds: 7.05s typed vs 1.20s scripted,
  incl. file write + completion poll) — the focus/type/settle pantomime is paid once.
- Untested: script lines with spaces in paths, very long lines, hundreds-of-line scripts, true
  modal (non-`xmessage`) dialogs mid-script.

## `CAMERA` ✅ 🔬 — viewport windows
Parser in `Editor.dll`; frontend `printf` usages in `unrealed.exe`.
- **Subcommands:** `OPEN`, `CLOSE`, `UPDATE`, `ALIGN`, `LEVEL`, `REDRAW`, `LINKS`, `STANDARD`,
  `HIDESTANDARD`, `FREE`.
- **`CAMERA OPEN` args:** `NAME=` (viewport name; used by `UPDATE`/`CLOSE`/`ALIGN`), `XR=`/`YR=`
  (pixel w/h), `REN=` (render mode), `FLAGS=` (show-flags), `MISC1=`/`MISC2=` (mode-specific),
  `HWND=` (parent window handle — embeds the camera; **omit → free-floating top-level window**),
  `NAMEFILTER=` + `PACKAGE=`/`GROUP=`/`MESH=` (browser modes only).
- **`REN=` enum** (= `[U2Viewport*] RendMap`): `1`=Wire, `2`=Zones, `3`=Polys, `5`=DynLight,
  `6`=PlainTex, `13/14/15`=Orth XY/XZ/YZ, `16`=TexView, `17`=TexBrowser, `18`=MeshView.
- **`CAMERA UPDATE`** re-renders a named camera and can change its `REN=`/`FLAGS=`/`MISC*`; the
  frontend uses it for the browsers, e.g.
  `CAMERA UPDATE FLAGS=%d MISC1=%d MISC2=%d REN=%d NAME=TextureBrowser PACKAGE="…" GROUP="…" NAMEFILTER="…"`
  and `CAMERA UPDATE NAME=MeshBrowser MESH="…" FLAGS=%d REN=%d MISC1=%d MISC2=%d`.
- **`CAMERA ALIGN [NAME=…]`** ✅ re-centers all viewports on the selection (or named object).
  **⛔ For a POINT actor it sets camera POSITION only** — it *stores* the actor's `Rotation` on the
  camera but that rotation **never reaches the headless render** (calibration spike 2026-07-12,
  `spikes/2026-07-12-preview-pose-calibration/`; decision 2026-07-12 07:37). The earlier "adopts the
  FULL FRotator" claim (live 2026-06-20, `Pitch=-4096,Yaw=49152,Roll=8192` round-tripped through a
  `MAP SAVE` readback) was true of the *stored* value but NOT of pixels — a 9-pose sweep rendered the
  identical view every time. So **there is no console rotation-pose for a headless shot**; the removed
  `level preview --rotate` / `dispatch._camera_rotation_helper` wiring is GONE.
  **✅ For a BRUSH actor it does a look-at/FRAME** — repositions AND aims the camera to frame that
  brush, and the render DOES reflect it (distance ∝ the brush's size, canonical angle). This is the
  ONLY console aiming primitive that works headless, and is what `level preview` auto-frames with:
  `SELECTNAME` a brush → `CAMERA ALIGN NAME=` it. Result/error strings: "Aligned camera on the current
  target." / "…on named object."; errors "Missing name" / "Can't find target (viewport or selected
  actor)". (Old note, now inverted by the finding: the builder brush "does NOT work" as a *rotation*
  target — correct, because brushes frame instead of adopting rotation; framing is exactly what we
  now use.) See `specs/2026-06-18-uedcli-camera-rotation-no-mouse-design.md` (superseded notice) and the
  `uned-camera-rotate-via-align` memory note for the full recipe and caveats.
- **`CAMERA CLOSE NAME=…`** — reliably closes only the **frontend-managed browser cameras**
  (`TextureBrowser`, `MeshBrowser`, `MeshViewer`, `TEXREPLACE1/2`), opened with an `HWND=`
  parent. 🔬 It did **not** destroy an ad-hoc console-opened standalone window in testing.
- **`STANDARD` / `HIDESTANDARD` / `FREE` / `LEVEL` / `REDRAW` / `LINKS`** 📖 — toggle the
  standard 4-pane layout / detach / per-level redraw + show "Level links:".
- **Live (🔬):** `CAMERA OPEN NAME=ShotCam XR=480 YR=360 REN=6` spawns a standalone window
  that renders the level **immediately** at the requested size+mode (log:
  `ResizeViewport(0, 480, 360, 4)`, the `4`=32bpp; `Galaxy SetViewport: ShotCam` ⇒ `NAME=`
  registered). This is the clean no-mouse shaded-shot path — see [`rendering.md`](rendering.md).
- **Window title encodes the view** 🔬: `REN=6`→**"Viewport"**, `REN=1`→**"Perspective map"**,
  `REN=13`→**"Overhead map"** (so `wmctrl -l | grep` for the right title per mode).
- **⚠️ `CAMERA UPDATE` blanks the window to black under headless SoftDrv** 🔬. A `CAMERA OPEN`
  window paints correctly **only on initial creation**; any *re-render* — `CAMERA UPDATE NAME=`,
  or a show-flag toggle like `SHOWACTORRADII` on the current viewport — repaints it solid black
  (the software re-paint isn't produced offscreen). Proven by control: fresh ortho cam mean=169
  (grid) → `CAMERA UPDATE` alone → mean=0. ⇒ **open the camera in its FINAL mode/flags and
  capture once; don't `UPDATE`.** To change mode/flags, open a NEW camera.

## `RMODE` ✅ — current viewport's render mode (`REN=` enum)
`RMODE <n>`. **The console can't make the perspective pane current** (needs a mouse click) →
prefer `CAMERA OPEN REN=<n>`. See [`rendering.md`](rendering.md).

## Camera position
`JUMPTO X,Y,Z` ✅ centers viewports on a coord (**position only**, no repaint). Setting live
camera **rotation** by a direct/dedicated verb is still not possible — `SET`/`GET Camera
Rotation` touch the class default, `CAMERAMOVE`/`CAMERAZOOM` are mode switches, and
`MyLevel.Camera0–5` isn't in `MAP EXPORT`. But **`CAMERA ALIGN`** (above) reaches the same
end pose-by-proxy and IS console-only: pose a `Light` point actor with the desired
`Rotation=`, `SELECTNAME` it, `CAMERA ALIGN NAME=` it. See the `CAMERA ALIGN` entry above.

## `MODE` 📖 — editor edit-mode + tool settings
`MODE` switches the active tool — `CAMERAMOVE`, `CAMERAZOOM`, `BRUSHROTATE`, `BRUSHSHEER`,
`BRUSHSCALE`, `BRUSHSTRETCH`, `BRUSHSNAP`, `TEXTUREPAN`, `TEXTUREROTATE`, `TEXTURESCALE`,
`FACEDRAG`, `VERTEXEDIT` — and carries tool settings: `GRID=`, `ROTGRID=`, `SNAPVERTEX=`,
`SPEED=`, `SNAPDIST=`, `TEXTURELOCK=`, `SELECTIONLOCK=`, `AFFECTREGION=`, `MAPEXT=`.

## Build pipeline ✅ 🔬
- `MAP REBUILD` = geometry/BSP only (same as `BSP REBUILD GOOD`). **`BSP REBUILD` quality
  options 🔬** (all confirmed live 2026-06-23):
  - `LAME` — fastest: basic BSP only, skips coplanar-detection (`Found 0 coplanar sets`).
  - `GOOD` (default when using `MAP REBUILD`) — adds coplanar-merge pass.
  - `OPTIMAL` — additional merge/optimize passes beyond `GOOD`.
  - `BALANCE=<n>` — balanced BSP tree by polygon count.
  - `PORTALBIAS=<n>` — portal-based BSP bias.
  - `ZONES` — zone rebuild pass.
  - `OPTGEOM` — geometry-optimization pass.
  Use `LAME` for fast iteration, `GOOD`/`OPTIMAL` for final/pre-ship passes.
  - **Default parameters when no keyword is given** (decompiled from the exec parser
    `Editor.dll 0x65220`, 2026-06-24): `BALANCE=` absent → **50**, `PORTALBIAS=` absent → **70**
    (packed as `Balance | (PortalBias<<8)`), and the numeric Optimization the builder receives
    is **OPTIMAL (2)** — so `FindBestSplit` tries every candidate (the `GOOD`/`OPTIMAL` label
    governs which *cleanup* passes run, not the partition step). See
    `../spikes/2026-06-24-offline-bsp-engine-slices1b-2-3-parity.md` §1a.
- **`LIGHT APPLY`** ✅ (`SELECTED=`, `VISIBLEONLY=`, `SHOWINV`) builds lighting (a `MAP REBUILD`
  wipes it). `LIGHT` actors: `LightBrightness`/`LightRadius`/`LightHue`/`LightSaturation`
  (saturation inverted — see `rendering.md`). **`LightBrightness=0` emits zero light 🔬** —
  safe value for a throwaway helper `Light` used by `CAMERA ALIGN`.
- **`PATHS` 🔬** (verbs confirmed live 2026-06-23; the DEFINE-vs-BUILD split corrected by
  disassembly 2026-07-15): **`PATHS BUILD`** is what constructs the **reachspec graph** — its
  `FPathBuilder::buildPaths` runs `definePaths` (place markers) → **`createPaths`** (build all
  `FReachSpec`s) → `Prune`; `LOWOPT`/`HIGHOPT` set the optimization level (opt 0/2, default 1).
  **`PATHS DEFINE`** (`FPathBuilder::definePaths`) only **spawns auto-marker NavigationPoints** (an
  `InventorySpot` under each `Inventory`, a `WarpZoneMarker` under each `WarpZoneInfo`) and touches
  **no** reachspecs; it logs `DevPath: Defining paths.`. (The earlier "PATHS DEFINE builds the
  reachspec graph" conflated the two — DEFINE alone yields no edges; BUILD is the reachspec build.
  See `spikes/2026-07-15-native-materialize/sections/30-ulevel-paths-assembly.md` §4.) Reachspecs
  are the `ULevel.ReachSpecs` array; per-node `Paths`/`upstreamPaths`/`prunedPaths` index into it.
  Paths are NOT wiped by `MAP REBUILD` (unlike lighting). Also: `PATHS UNDEFINE`/`SHOW`/`HIDE`/
  `REMOVE` 📖.

## `TRANSACTION` 📖
`TRANSACTION UNDO` / `TRANSACTION REDO`.

## Objects / packages / assets 📖
- `OBJ LIST CLASS=Texture` ✅ → `Package.Group.Name` (to the log window). Also `OBJ
  LOAD`/`SAVE`/`IMPORT`/`EXPORT`/`DELETE`/`GETPROPERTIES` with `CLASS=`/`PACKAGE=`/`FILE=`/`NAME=`.
- **`OBJ DEPENDENCIES PACKAGE=MyLevel` 🔬 — reads a surface's bound texture PACKAGE.** Walks the
  loaded level's object graph and prints every referenced object **fully qualified**
  (`Texture CoreTexMetal.Metal.Area51Wall_A`). One `Class Engine.Polys` block **per brush**, each
  listing that brush's per-poly textures **in poly order** — so it recovers the package even when
  the bare `Texture=` name collides across packages (`MAP EXPORT`/`EDIT COPY` only ever emit the
  bare name). Run in a **fresh** editor with exactly one level loaded — `MAP NEW`/`MAP LOAD` don't
  purge the prior level's objects, so a reused editor accumulates stale textures. Don't narrow with
  `CLASS=Model` (that hits the BSP Model default, not the per-poly bindings). Other `OBJ` reflection
  (`REFS`/`LINKERS`/`CLASSES`) does not surface per-surface textures. See
  `../spikes/2026-06-19-read-surface-texture-package.md`.
- Mesh/anim import (UCC-style): `MESH MODELIMPORT MESH= MODELFILE= LODSTYLE= …`, `MESHMAP
  SETTEXTURE`, `ANIM IMPORT ANIMFILE= …`, `SEQUENCE … SEQ= STARTFRAME= NUMFRAMES=`, `FONT
  IMPORT`, `BOUNDINGBOX XMIN=…ZMAX=`, `LODPARAMS MINVERTS= …`.
- Texture tools: `TEXTURE` `REPLACE`/`ADD`/`EXTRACT`/`MUGSHOT`/`DISASSEMBLE` (`DEST=`, `SRC=`,
  `MASTER=`, `REF=`, `REFSIZE=`, `MASTERRECURSE=`).
- **Texture → PNG (recipe):** `wine /opt/UED22/UCC.exe batchexport <pkg>.u Texture pcx
  "Z:\<dir>"` (outdir **must** be `Z:\`) → `convert *.pcx *.png`. `Engine.DefaultTexture` is the
  brightest surface texture in the stripped substrate.
- **Level → T3D (recipe):** `wine /opt/UED22/UCC.exe batchexport <map>.dx Level T3D "Z:\<dir>"`.
  ✅ Content-equivalent to `MAP EXPORT`. ⚠️ **Output file is named after the Level object, NOT the
  package stem** — a `spike13.dx` writes `<dir>/MyLevel.T3D` (the level object is always
  `MyLevel`); read `<outdir>/MyLevel.T3D`, never `<stem>.T3D`. Package prefix in
  self-referential refs differs from `MAP EXPORT` (`spike13.LevelInfo0` vs `MyLevel.LevelInfo0`)
  — normalize it away before hashing (✅ `spikes/2026-06-18-ucc-level-export.md`).
  ⚠️ **`Commandlet batchexport not found`** means that editor's UCC didn't load `Editor` from
  its `EditPackages` (so the commandlet class never registered — `ucc help` then lists only
  `HelloWorld`). Not a syntax problem: run it in a **clean substrate container**, not a
  repurposed/mis-configured one. Seen 2026-06-28 against a standing `dx-lum-uned` that another
  agent had replaced with an OldUnreal `469c` build; a fresh `docker compose run uned` exported
  the same `.dx` cleanly (🔬 2026-06-28).

## `APP` / properties dialogs / misc 📖
- `APP SET`, `APP BROWSECLASS`, `APP NOTECURRENT`/`USECURRENT`, progress (`PROGRESSBAR=`,
  `PROGRESSTEXT=`, `PROGRESSDLG=`).
- Open property windows: `ACTORPROPERTIES`, `LEVELPROPERTIES`, `TEXTUREPROPERTIES`,
  `CLASSPROPERTIES`, `MESHPROPERTIES` (GUI dialogs — paint poorly headless).
- `PREFERENCES`, `QUERY`, `GETSYSTEMINI`, `GETUSERINI`, `RELAUNCHSUPPORT`, `LOGWINDOWSUPPORT`.
- `SCRIPT MAKE` (compile scripts), `CLASS SPEW`/`PARENT=`, `LEVEL VALIDATE`/`FIX`,
  `MAYBEAUTOSAVE`, `HOOK`, `PLAYMAP`/`PLAY`, `SETCURRENTCLASS`, `MAKETEXTURECURRENT`,
  `DUMPINT`, `GETCHILDREN`, `EXISTS`, `NUMANIMSEQS`, `ANIMSEQ`, `CURRENTTEXTURE`.
- **`LSTAT LEVEL`** ✅ → lighting/collision stats to the log window. `LEVEL VALIDATE` logs
  nothing (GUI dialog); `Editor.log` is buffered — no clean text feedback channel yet.

## Engine-level exec (`Engine.dll` — `UEngine`/`UClient`/`ULevel`/`UViewport`) 📖
Reachable in the editor where relevant; most are game-runtime. Useful ones:
- `RMODE <n>` (above), `SHOT`/`SSHOT` (screenshot), `FLUSH` (flush caches), `BRIGHTNESS`,
  `SHOWALL`, `EXEC <file>` ✅ (run a command script — semantics verified, see the dedicated
  `EXEC <file>` section above), `GETPING`/`GETLOSS`/`FPS`,
  `DEMOREC`/`DEMOPLAY`/`STOPDEMO`, `OBJ`/`OBJCLEAN`, `SAVEGAME`, `DEBUG`.
- **Actor-display toggles 🔬** (`UViewport::Exec`/`ExecMacro`, no args): `SHOWACTORS`/
  `HIDEACTORS` and **`SHOWACTORRADII`/`HIDEACTORRADII`** — the **View → Actors** menu family
  (Full Actor View / Icon View / **Radii View** / Hide Actors). `SHOWACTORRADII` flips the
  **current viewport's** show-flags to draw each actor's collision radius/height + light radius
  as wireframe overlays; `HIDEACTORRADII` reverts. **Caveats** (both verified live): (1) it
  targets `GCurrentViewport` — like `RMODE`, the console can't aim it at a chosen `CAMERA OPEN`
  window, and a fresh camera opens with default flags (no radii inheritance); (2) toggling it is
  a *re-render*, which **blanks the headless SoftDrv camera to black** (see the `CAMERA UPDATE`
  caveat above) — so toggle-then-recapture can't show the radii. **The way that works:** open a
  camera with the radii bit already in `FLAGS=` so it's on at first paint — **`SHOW_ActorRadii =
  0x02`** (confirmed by parallel bit-knockout); use `CAMERA OPEN … FLAGS=127` (a fully-chromed
  view) or minimally `FLAGS=0x0A` (`SHOW_ActorRadii|SHOW_Actors`). Selected actors then draw a
  **red** collision cylinder. See the ShowFlags table in [`rendering.md`](rendering.md).
- Game/network (not editor): `OPEN`, `START`, `SERVER`, `SERVERTRAVEL`, `SAY`, `DISCONNECT`,
  `RECONNECT`, `JOIN`, `LOGIN`, `EXIT`/`QUIT` (`URL=`, `GAME=`, `CLASS=`, `PASSWORD=`, …).

## BrushBuilders are not console commands ✅
GUI-dialog-driven (`WDlgBrushBuilder::OnBuild` → builder `Build()`) → uedcli replicates them
model-side (`builders.py`). See `../architecture.md` "Builders".
