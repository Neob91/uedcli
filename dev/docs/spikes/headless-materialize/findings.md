# Spike — can the map build run HEADLESS, and can it run without Wine?

*Run 2026-07-26. Live-probed against the committed UED22 substrate (`uned/UED22/`) both inside the
`dx-lum-uned` image and under plain host Wine 6.0.3. Harnesses in this directory:
`headless_build.py`, `probe_variants.py`. The empirical case for why this matters is the companion
friction log [`../levelbuild-friction/README.md`](../levelbuild-friction/README.md).*

> **Confidence markers** (repo convention): ✅ = uedcli-used / live-verified · 🔬 = live-probed in
> this spike · 📖 = extracted from the binary string/import tables (vocabulary real, semantics
> inferred). Every engine claim below carries the observation it rests on.

---

## 0. The question, and the answer in one paragraph

**Question.** `level materialize` today boots a Docker container that runs `unrealed.exe` (the
GUI editor) under Wine on a virtual X display, types console commands into its window with
`xdotool`, and tears the container down. It is slow, it leaks containers, and it wedges silently.
Can we instead drive UnrealEd's *map-build* code path headlessly — ideally by loading
`Core.dll`/`Engine.dll`/`Editor.dll` directly, with no Wine at all?

**Answer.** Loading the DLLs directly on Linux with no Wine is **not real** — see §7; the binaries
need 310 distinct Win32 entry points across 12 system DLLs including the whole windowing and GDI
stack, and reimplementing that is reimplementing Wine. **But the premise underneath the question —
"we only need the build, not the GUI" — is completely real, and the engine already ships the door:
`UCC.exe Editor.ExecCommandlet <script>` runs the full editor engine with no GUI, no window and no
X server, executing a file of ordinary console verbs.** 🔬 On this machine it built a real
28-actor level's geometry + BSP and saved the `.dx` in **1.4–3.7 s** (in the container) and
**2.78 s** (under host Wine, no Docker at all), against **106 s** for the same level through
today's GUI path — which on its second run wedged past 600 s and leaked its container. The
headless route has three real gaps (no lighting, no movers, brush actor names lost — §4, §6), so it
is **not a drop-in replacement**; it is an excellent *fast unlit build* and an excellent *BSP
oracle*. Meanwhile the **native Rust core built the same level, with lighting, paths and its mover,
in 1.22 s and with no Wine whatsoever** — it is already the strongest option on every axis except
byte-parity with UnrealEd. See §10 for the ranked recommendation.

---

## 1. The numbers (all measured on this machine, 2026-07-26, 4 cores)

The level is `basement` from the LUM project (28 actors: 17 CSG brushes, 1 Mover, 8 Lights,
1 PlayerStart, 1 LevelInfo).

| Route                                                  | Wall time                           | Needs Docker | Needs X | Lighting | Movers | Brush actor names
|--------------------------------------------------------|-------------------------------------|--------------|---------|----------|--------|---
| **`level materialize` today** (GUI editor, container)  | **106 s**                           | yes          | yes     | yes      | yes    | preserved
| same, second run                                        | **wedged >600 s**, container leaked | yes          | yes     | —        | —      | —
| **`Editor.ExecCommandlet`, in the editor image**       | **1.4–3.7 s**                       | one-shot `docker run --rm` | **no** | **no** (§4c) | **no** (§6b) | **lost** (§6a)
| **`Editor.ExecCommandlet`, host Wine, no container**   | **2.78 s**                          | **no**       | **no**  | **no**   | **no** | **lost**
| **native Rust `run_materialize_native`**               | **1.22 s**                          | **no**       | **no**  | **yes**  | **yes** | preserved

🔬 The GUI-path numbers are my own runs, not hearsay: `level materialize --tree level/basement`
took 106.08 s and then failed post-verify; a second run with `--no-verify` was still running at
600 s when I killed it, and left `uned-019f9b87-…` behind (I removed the container and its
wineprefix volume myself). That is the leak `../levelbuild-friction/README.md` §2 documents from
the other direction — teardown lives only in `apply.run_materialize`'s `finally`, so a killed or
wedged run always strands its container. That log also counts **19 occurrences** of
`OBJ DEPENDENCIES … within 20 attempts (20s)` and a `MAP SAVE never produced a finished file
(after 600s)`; §2 below shows the first of those failure modes does not exist at all in the
commandlet.

🔬 **The headless build is deterministic across substrates.** The `.dx` produced inside the
container and the one produced by a *separate* host-Wine run against a *separate* copy of the
substrate with a *fresh* wineprefix have a **byte-identical 48,783-byte world `Model` body**. The
whole file differs in only 76 bytes: the 16-byte package GUID plus 25 scattered 1–3-byte per-actor
fields (all below offset 12,495 in a 103,246-byte file — i.e. inside the actor bodies, not the
BSP).

🔬 The headless output passes the repo's own structural BSP check
(`spikes/2026-07-15-native-materialize/harness/bsp_health_check.py`): 305 nodes, 154 surfs, 112
leaves, 2 zones, **`refs/leaf = 1.00`** and no child/leaf/zone/surf range or cycle violations.

---

## 2. The commandlet route — what it is and how to invoke it

**UnrealEngine 1 ships a batch host called `UCC.exe`** ("UnrealOS execution environment"). It runs
a *commandlet*: a class deriving from `Core.Commandlet` whose `Main(params)` gets the command line.
Commandlets run with no window and no GUI frontend.

📖 The UED22 `Editor.dll` string table contains **21 native commandlet classes**, among them
`UExecCommandlet`, whose `Main` carries exactly three strings, at consecutive offsets:

```
'File name not specified'
'ini:Engine.Engine.EditorEngine'
'Could not initialize editor'
```

That middle string is the giveaway: `UExecCommandlet` instantiates the **editor engine** named by
`[Engine.Engine] EditorEngine=` in the ini (`Editor.EditorEngine` in our substrate) and then execs
the named file. It is, in other words, the console-script runner *without the console*.

🔬 **`ucc exec` does NOT work — you must name the class.** `UCC.exe` resolves a commandlet name
through the `Object=(Name=…,MetaClass=Core.Commandlet)` declarations in the `.int` files, and
`editor.int` declares only 10 of the 21 (`master`, `make`, `conform`, `batchexport`, `mergedxt`,
`packageflag`, `datarip`, `ps2convert`, `updateumod`, `checksumpackage`). `ExecCommandlet` is not
among them, so `wine UCC.exe exec <file>` answers `Commandlet exec not found`. The
**fully-qualified class name works and is the invocation to use**:

```
wine UCC.exe Editor.ExecCommandlet 'Z:\work\build.txt'
```

🔬 Observed behaviour of that invocation:

- It prints the whole engine log **to stdout** (`Bound to Editor.dll`, `Editor engine initialized`,
  `Execing …`, the per-rebuild `Nodes: N -> M` lines, `Moving 'Save.tmp' to '<out>'`,
  `Success - 0 error(s), 0 warnings`) and **exits by itself**. There is no window, no message pump
  to drive, nothing to poll, nothing to tear down.
- Fixed engine-init cost ≈ **1.3 s**; a whole trivial build (import → rebuild → save) finished in
  **3.9 s** including process start.
- Script lines execute **in order, synchronously**, and the run ends when the file ends.
- ✅ Verbs verified working headlessly: `MAP GRID`, `MAP NEW`, `MAP IMPORT`, `MAP IMPORTADD`,
  `MAP LOAD`, `MAP REBUILD`, `MAP SAVE`, `MAP EXPORT`, `MAP SETBRUSH`, `BRUSH IMPORT`,
  `BRUSH MOVETO`, `BRUSH ROTATETO`, `BRUSH ADD`, `BRUSH SUBTRACT`, `ACTOR SELECT …`,
  `ACTOR APPLYTRANSFORM`, `LEVEL FIX`, `LIGHT APPLY`, `PATHS BUILD`, `OBJ DEPENDENCIES`.

🔬 **`OBJ DEPENDENCIES PACKAGE=MyLevel` works headless and its output lands on stdout.** This
matters directly: that command is the single most common failure in production — **19 occurrences**
of `did not complete within 20 attempts (20s)` in `../levelbuild-friction/README.md` §3. The retry
loop exists because in the GUI editor the answer has to be scraped out of a 4 KB-buffered
`Editor.log` over `docker exec` (`unrealed/quirks.md` "Stability"). Under the commandlet the answer
is simply on the process's stdout, in order, with an exit code — the entire failure mode
disappears, along with the `wmctrl -l` / window-manager queries the same log records failing.

---

## 3. What actually requires Win32, and what requires X — measured, not guessed

Two different questions that are easy to conflate.

**(a) Does the BUILD need a display?** 🔬 **No.** The container run had `DISPLAY=:99` set with *no
X server behind it* (`/tmp/.X11-unix` did not exist) and the host run had `DISPLAY` unset entirely.
Both completed a full import → CSG → BSP → save. So the geometry build is pure computation; the
GUI is only how we *drive* it today.

**(b) Does it need Win32?** 🔬 **Yes, unavoidably, including the windowing stack.** Two hard
observations:

- The commandlet's own log shows it initialising and shutting down the *client*:
  `DirectDraw initialized successfully` → `Client initialized` → … → `Windows client shut down`,
  and `Unbound to WinDrv.dll` / `Unbound to Window.dll` at exit. The editor engine constructs a
  `UWindowsClient` even in a commandlet.
- `LIGHT APPLY` logs `Input system initialized for WindowsViewport0` / `Opened temporary viewport`
  — the lighting pass really does create a viewport object.

📖 The static import surface (from `pefile` over `Core.dll`, `Engine.dll`, `Editor.dll`,
`Window.dll`, `Render.dll`, `WinDrv.dll`, `Fire.dll`, `IpDrv.dll`, `UCC.exe`):

| System DLL             | Symbols  | What of
|------------------------|----------|---
| kernel32.dll           | 132      | files, heaps, threads, TLS, SEH, `LoadLibraryW`/`GetProcAddress`
| user32.dll             | 102      | `RegisterClassExW`, `CreateWindowExW`, the message pump, MDI, dialogs, menus, cursors, **raw input**, the clipboard
| gdi32.dll              | 28       | DIB sections, fonts, `GetGlyphOutlineW`, blits
| ws2_32.dll             | 27       | IpDrv sockets
| winmm.dll              | 6        | `timeGetTime`, timer resolution
| ole32/oleaut32/shell32 | 3 / 3 / 3| `CoCreateGuid` (the package GUID), BSTRs, `CommandLineToArgvW`
| comdlg32.dll           | 3        | file/colour dialogs
| comctl32.dll           | 1        | `InitCommonControlsEx`
| advapi32.dll           | 1        | `GetUserNameW`
| imm32.dll              | 1        | IME
| **total**              | **310**  | plus whatever is reached dynamically — `Core.dll` imports `LoadLibraryW`/`GetProcAddress`, and `ddraw`/`opengl32` are loaded that way

📖 Notably `Editor.dll` links against `Window.dll` for 79 symbols, all `WWindow`/`WProperties`
members (the properties dialogs and the log window). Those code paths are only *reached* by GUI
verbs, but a loader must **resolve** them at load time, so `Window.dll` must load, which drags in
its own 73 user32 + comctl32 + comdlg32 imports.

---

## 4. What BREAKS in the headless commandlet (the three real limits)

Each was probed with a deliberate variant script; the matrix is reproducible with
`probe_variants.py`.

### (a) The clipboard is dead — so `EDIT COPY`/`EDIT PASTE` do nothing 🔬

Variant **K**: import a brush → `ACTOR SELECT ALL` → `EDIT COPY` → `MAP NEW` → `EDIT PASTE` →
`MAP EXPORT`. The exported level contains **only `LevelInfo0` and the red builder brush** — the
paste produced nothing. Variant **H** (`EDIT CUT` then `EDIT PASTE`) likewise left the level
unchanged. 📖 Consistent with `Core.dll`'s user32 imports
(`OpenClipboard`/`GetClipboardData`/`SetClipboardData`/`GetActiveWindow`): with no window there is
no active window to own the clipboard.

**This is the single most consequential finding for uedcli**, because `writes._re_add` adds every
brush with `EDIT PASTE` (the only add verb that yields a CSG-participating brush — see
`unrealed/quirks.md` "How brushes enter the level"). uedcli's current materialize sequence
therefore **cannot** simply be replayed in a commandlet. §5 is the way around it.

### (b) `CAMERA OPEN` cannot create a window 🔬

`CAMERA OPEN NAME=EdCam XR=64 YR=64 REN=6` fails with `CreateWindowEx failed` under the null
display driver. So **`level preview`'s editor-screenshot path can never move to the commandlet** —
it genuinely needs a display. (That path is already retired in favour of the in-game and native
renderers, so this costs nothing; it is recorded so nobody re-proposes it.)

### (c) `LIGHT APPLY` poisons the level: the following `MAP SAVE` GPFs 🔬 — HARD BLOCKER

`LIGHT APPLY` itself runs fine and correctly (`8 Lights, 154 Polys, 316 Pairs, 5821 Rays`), and a
subsequent `MAP EXPORT` succeeds. But the subsequent **`MAP SAVE` dies with a general protection
fault**, always at the same place:

```
General protection fault!
History: FArchiveSaveTagExports<<Obj <- FPropertyTag::SerializeTaggedProperty <- SaveStream
  <- UStruct::SerializeTaggedProperties <- (Player[0]) <- UObject::Serialize
  <- (Camera MyLevel.Camera0) <- AActor::Serialize <- … <- UObject::SavePackage
  <- (MAP SAVE FILE=…) <- UExecCommandlet::Main
```

**Mechanism (inferred from the log + the trace):** `LIGHT APPLY` opens a *temporary* viewport for
its occlusion pass (`Opened temporary viewport`); creating it spawns a `Camera` actor into
`Level->Actors`; closing it destroys the viewport but leaves the zombie `Camera0` in the actor list
with a dangling `Player` reference, which the package serializer then follows.

**Nine workarounds were tried and ALL failed** — this is not "we didn't look hard enough":

| Attempt after `LIGHT APPLY`                                    | Result
|-----------------------------------------------------------------|---
| plain `MAP SAVE`                                                 | GPF (above)
| `ACTOR SELECT OFCLASS CLASS=Camera` + `ACTOR DELETE`             | GPF in `edactDeleteSelected` → `UStruct::CleanupDestroyed`
| the same plus `OBJ GARBAGE`                                      | GPF in `ACTOR DELETE`
| `OBJ GARBAGE` then `MAP SAVE`                                    | GPF
| `OBJ DELETE CLASS=Camera NAME=Camera0` then `MAP SAVE`           | GPF
| `LEVEL FIX` then `MAP SAVE`                                      | GPF
| `MAP SENDTO LAST` then `MAP SAVE`                                | GPF
| `PATHS BUILD` then `MAP SAVE`                                    | GPF *inside `PATHS BUILD`* (`FPathBuilder::definePaths` → `CleanupDestroyed` → the same `Camera0`) — the level is globally poisoned, not just the save
| pre-opening a viewport with `CAMERA OPEN` before `LIGHT APPLY`   | `CreateWindowEx failed` (§4b)
| `LIGHT APPLY SELECTED=0 VISIBLEONLY=0`                           | GPF

🔬 **And it is not a null-display artifact:** the same script under a *real* Xvfb `:99` inside the
container GPFs identically, and so does a completely independent host-Wine run. The GUI editor is
fine because its viewports (and their Cameras) are long-lived and owned by the frontend; the
commandlet's temporary one is not.

**Consequence:** a commandlet build can produce **geometry + BSP + zones + paths**, but not a
**lit** map. Lighting must come from somewhere else (the GUI editor, or the native Rust bake —
`uedcli_native.bake_lighting` already exists and works).

---

## 5. The clipboard-free way to add a brush — `BRUSH IMPORT` + `BRUSH ADD`/`SUBTRACT` 🔬

Since `EDIT PASTE` is unavailable, the spike hunted for another way to get a brush that CSG
actually applies. The measured matrix (BSP node count in the saved `.dx`; **0 nodes = the world was
never carved**, the offline tell from `unrealed/quirks.md`):

| Variant | Sequence                                                                  | Nodes | Verdict
|---------|---------------------------------------------------------------------------|-------|---
| A       | `MAP IMPORTADD` → `MAP REBUILD`                                           | **0** | uncarved (reconfirms the known quirk)
| B       | `MAP IMPORT` (full replace) → `MAP REBUILD`                               | **0** | the full-replace importer is no better
| C       | **`BRUSH IMPORT` → `BRUSH MOVETO` → `BRUSH SUBTRACT` → `MAP REBUILD`**    | **6** | **works**
| D       | `MAP IMPORTADD` → `ACTOR SELECT ALL` → `ACTOR APPLYTRANSFORM` → rebuild   | **0** | does not repair it
| E       | `MAP IMPORTADD` → save → `MAP LOAD` that file → rebuild                   | **0** | a save/load round-trip does not repair it
| F       | `MAP IMPORTADD` → `ACTOR SELECT ALL` → `MAP SETBRUSH CSGOPER=2` → rebuild | **0** | does not repair it
| G       | `MAP IMPORTADD` → `LEVEL FIX` → rebuild                                   | **0** | does not repair it
| H       | `MAP IMPORTADD` → `EDIT CUT` → `EDIT PASTE` → rebuild                     | **0** | clipboard dead (§4a)

**So `BRUSH IMPORT` + `BRUSH ADD`/`BRUSH SUBTRACT` is the only clipboard-free add path**, and it is
fully console-drivable:

```
BRUSH IMPORT FILE=Z:\work\<name>.polys.t3d     ← a bare  Begin PolyList … End PolyList
BRUSH ROTATETO PITCH=.. YAW=.. ROLL=..         ← optional, sets the builder brush's rotation
BRUSH MOVETO X=.. Y=.. Z=..                    ← the actor Location
BRUSH SUBTRACT            (or BRUSH ADD)
MAP SETBRUSH SETFLAGS=<PolyFlags>              ← solidity, on the just-added brush
```

✅ This is consistent with the already-recorded fact that "the paste method == the GUI
`BRUSH SUBTRACT`, proven by full-level export diff" (`unrealed/quirks.md` "CSG model") — the two
add paths were known to be geometrically equivalent; what is new is that one of them needs no
clipboard and therefore no GUI. Note ⚠️ **`BRUSH IMPORT` does NOT drift by +32 uu** the way
`EDIT PASTE` does, so the −32 uu pre-shift `writes._shift_for_paste` applies must **not** be
carried over to this path (the same trap that bit the intersect/deintersect spec — `decisions.md`
2026-07-25).

`headless_build.py` in this directory implements the whole trunk → script translation.

---

## 6. What the commandlet route still costs (the honest gap list)

### (a) Brush actor NAMES are assigned by the editor 🔬

`BRUSH ADD`/`SUBTRACT` names the new actor `Brush<N>` in add order. Measured on the basement build:
the 8 Lights, the PlayerStart and the LevelInfo kept their trunk names (they arrive via
`MAP IMPORTADD`, which preserves everything), but all 17 brushes came out `Brush1`…`Brush17`
(`Brush0` being the red builder brush, which is also saved). The trunk's per-actor identity is lost
for brushes, so the H3 post-verify — which compares by canonical actor name — cannot run unchanged.

Three ways out, none free: (i) map trunk name → `Brush<N>` positionally, since add order is ours
and the numbering is deterministic; (ii) rewrite the names in the saved package offline (uedcli
already owns a complete UE1 package reader/writer in `uedcli/native/pkg_write.py` +
`assemble.py`); (iii) accept editor names in the artifact and re-base the compare.

### (b) Movers cannot be built this way 🔬

A `Mover`'s keyframes (`KeyPos`/`KeyRot`/`NumKeys`/…) are **authored actor properties**, and
✅ "there is no console verb for setting individual actor properties" (`unrealed/commands.md`).
`MAP IMPORTADD` *would* carry them faithfully, but an IMPORTADD'd brush actor gets no CSG-side
preparation — and while a mover does not participate in world CSG, its own model's BSP (built by
the add path) is what the game collides against, so IMPORTADD is not obviously safe for it either.
`BRUSH ADDMOVER` creates a `Mover` from the builder brush but leaves no way to author the
keyframes. **`headless_build.py` therefore skips movers and says so** — the basement build is
missing its door.

### (c) `PrePivot`, `MainScale`/`PostScale`, `SheerRate` 📖

`BRUSH SCALE` / `BRUSH SHEER SHEER= SHEERAXIS=` exist in the parser and would presumably set the
builder brush's scale before the add, but their argument grammar was **not verified live** in this
spike, and there is no `PrePivot` setter at all. `headless_build.py` reports these actors as
degraded rather than silently mis-building them. D8 (`PrePivot` is load-bearing) makes silently
dropping one unacceptable.

### (d) No lighting — see §4c.

---

## 7. Loading the PE DLLs on Linux without Wine — NO 🔬📖

The idea: `dlopen`-style load `Core.dll`/`Engine.dll`/`Editor.dll` into a Linux process with a PE
loader, stub the Win32 imports, and call `csgRebuild` directly. Assessment against the measured
facts:

- **310 distinct Win32 entry points** must resolve before any of this code runs (§3), and they are
  not a decorative fringe: `RegisterClassExW`/`CreateWindowExW`/`PeekMessageW`/`DispatchMessageW`,
  MDI, dialogs, raw input, the clipboard, DIB sections and `GetGlyphOutlineW`. `Window.dll` is a
  *link-time* dependency of `Editor.dll`, so it must load even for a pure build.
- The engine really does construct a client and (for lighting) a viewport at run time (§3), so the
  windowing stubs would have to be *functional*, not merely present.
- These are 32-bit MSVC C++ DLLs (`Machine=0x14c`) using C++ exceptions, SEH, TLS callbacks and
  `LoadLibraryW`/`GetProcAddress` at run time — a loader must implement all of that.
- Existing minimal PE-on-Linux loaders (`wibo` and friends) target *console* MSVC toolchain
  executables with a few dozen kernel32 imports; none carry user32/gdi32/ddraw. *(Untested
  reasoning — no such loader was tried here; the 310-symbol surface above is the measured part.)*

**Verdict: writing that loader is writing a subset of Wine, for no gain over Wine.** ❌ And the
gain being sought — "no Wine" — is *already* available on a different axis: the native Rust core
(§9) needs no Windows binaries at all. Wine-elimination should come from replacing the *algorithm*,
not from re-hosting the *binary*.

One caveat worth recording: Wine is not free either. Host Wine 6.0.3 needed a ~454 MB wineprefix
(created once, reusable) and the run rewrites ini files in the substrate dir, which is why the
spike ran against a hardlinked scratch copy rather than the tracked `uned/UED22/`.

---

## 8. Headless Wine WITHOUT X — already proven, and what the container could become

🔬 Confirmed twice over (§3a): no X server is needed for the build. Three consequences:

- **The editor image could shrink drastically for build work.** Today it installs Xvfb, fluxbox,
  x11vnc, noVNC, xdotool, wmctrl, xclip, imagemagick and mesa purely to host and drive a GUI. A
  build-only image needs `wine` + the substrate. (The GUI image stays for interactive debugging.)
- **The container becomes disposable in the honest sense.** `docker run --rm` around a process that
  exits by itself in ~3 s cannot leak the way a long-lived detached editor does: there is no
  readiness wait, no `ensure_editor` retry loop, no `stop_editor` that a killed parent might skip,
  no wineprefix volume to garbage-collect. The 9-containers-in-an-hour leak
  (`../levelbuild-friction/README.md` §2) is a property of the *detached GUI editor*, not of Docker.
- ⚠️ **Not to be confused with running the GUI editor under Wine's null display driver.** The GUI
  editor still needs a real display: `CAMERA OPEN` fails without one (§4b), and the driver's
  `xdotool`/`xclip`/`wmctrl` plumbing is X by construction.

---

## 9. What the native Rust path still lacks — and why it is nevertheless ahead

`uedcli/native/` + `uedcli-native/` already contain a complete editor-free build: CSG
(`bspcsg.rs`, the ported `bspBrushCSG`), BSP, zones/portalisation, `bspOptGeom`, a lightmap bake
(`light.rs`), path building (`paths.rs`), and a full UE1 package writer. 🔬 It built the basement
level end to end in **1.22 s** including lighting (140 lightmaps) and its mover, with **no Wine, no
container and no display**. It is wired into `level preview --native` but **not** into
`level materialize` — there is no `level materialize --native` flag today.

What it still lacks:

- **Byte-parity with UnrealEd on large maps.** The castle reference is byte-identical (Model body,
  GUID aside); UNATCO is not — whole-map byte agreement sits at ~19 %, with two open fronts:
  committed-tree *pass staging* (which brushes are structural vs detail) and an axis-aligned
  **repartition over-split** in `bsp_build`. See
  `spikes/2026-07-15-native-materialize/PARITY-STATUS.md`. On basement the native build emitted 465
  BSP nodes where the editor emitted 305 — divergent, though both are 2-zone and both valid.
- **Byte-parity is a fidelity target, not a functional one** (`direction.md`): the native build is
  already playable, and this spike's own measurement is that it is *complete* (lighting, movers,
  names, paths) where the headless-editor route is not.

**So the relationship between this spike and the native work is not competition — it is that the
headless commandlet is the cheapest possible ORACLE for it.** Today a parity golden costs a GUI
editor session driven through `build_ued_golden.py`, i.e. the fragile, minutes-long,
container-leaking path this spike set out to replace. A `BRUSH IMPORT`-based commandlet script
produces an UnrealEd-built `.dx` in ~3 s, deterministically, from a plain trunk — that turns
"regenerate a golden" from an afternoon into a test fixture, and it is the fastest way to attack
the two open parity fronts. (⚠️ One caveat to check first: goldens must be built the way they are
today, and `BRUSH ADD` vs `EDIT PASTE` are *geometrically* equivalent but were never compared
*byte-for-byte* on a real level. That comparison is the first thing to run — see §11.)

---

## 10. Options, ranked by (effort × risk) vs payoff

| # | Option                                                                                        | Effort × risk | Payoff | Verdict
|---|-----------------------------------------------------------------------------------------------|---------------|--------|---
| 1 | **Wire `level materialize --native`** to the existing `run_materialize_native`                 | **low** — the code exists, is exercised by harnesses, and self-checks | 1.2 s builds, no Wine/Docker/X, no wedges, no leaks, full lighting + movers | **DO THIS FIRST**
| 2 | **Use `Editor.ExecCommandlet` as the golden/oracle path** (replace `build_ued_golden.py`'s GUI drive) | **low–medium** — harness exists here; needs the paste-vs-add byte comparison first | parity goldens go from minutes + wedges to ~3 s; unblocks the two open parity fronts | **DO THIS SECOND**
| 3 | **Shrink the editor container to a one-shot build image** (no Xvfb/VNC/xdotool), driven with `docker run --rm` | low | kills the container leak and the readiness-retry loop for any commandlet work | do it alongside #2
| 4 | **Make the commandlet route a real `materialize` backend** (unlit)                             | **medium–high** — needs the name mapping (§6a), the mover story (§6b), scale/PrePivot verbs (§6c) | a 3 s UnrealEd-faithful *unlit* build | only if #1 stalls on parity
| 5 | **Get lighting working in the commandlet**                                                     | **high, possibly impossible** — 9 workarounds failed (§4c); what is left needs a custom native commandlet or binary patching | would make #4 a full replacement | **not now**
| 6 | **Native PE loader, no Wine**                                                                  | **very high, near-certain failure** (§7) | none over Wine | **NO**
| 7 | **Keep the GUI editor for materialize**                                                        | zero | status quo: 106 s, wedges, leaks | only as the fallback while #1 lands

**Recommendation.** Stop trying to make the GUI editor fast, and stop looking for a Wine-free way
to run *its binaries* — both are dead ends. The Wine-free build already exists in this repo; it is
the native Rust core, and the cheapest big win available is to expose it as
`level materialize --native`. Then use `Editor.ExecCommandlet` for what UnrealEd is uniquely needed
for — being the *reference* — where a 3-second deterministic golden is worth more than a 3-second
build.

---

## 11. Open questions this spike deliberately did not close

- **Is `BRUSH IMPORT`+`BRUSH ADD` byte-identical to `EDIT PASTE`+rebuild on a real level?** Known
  geometrically equivalent (✅, `unrealed/quirks.md`), never byte-compared. This gates option #2.
  *Test:* build one trunk both ways and diff the `Model` bodies.
- **Where is `Save.tmp` created?** The headless log answers a question `unrealed/commands.md` left
  open ("Inferred, not extracted: where `Save.tmp` is created"): 🔬 the move line reads
  `Moving 'Z:\work\Save.tmp' to 'Z:\work\out.dx'` — i.e. **in the destination's own directory**, as
  suspected. Two concurrent saves into one directory would therefore collide. (Recorded here; the
  doc it belongs in is `unrealed/commands.md`, which this spike was not permitted to edit.)
- **What exactly makes an `IMPORTADD` brush invisible to CSG?** Four repair attempts failed (§5
  D/E/F/G); the mechanism is still "the add path prepares something T3D does not carry". Likely the
  brush's own model BSP (`Brush->Nodes`), which `bspBrushCSG`'s phase 2 needs — untested.
- **`BRUSH SCALE`/`SHEER` argument grammar** (§6c).
- **A pre-existing `basement` post-verify failure**, unrelated to this spike: `level materialize`
  reported `actor 'RoomA_jwvaq0' differs in GEOMETRY at line 7: built "Vertex …" / intended
  "Pan U=0 V=0"` — the two sides look line-shifted rather than genuinely different. Same family as
  `../levelbuild-friction/README.md` §1 (post-verify rejecting good builds), different cause.

## 12. Reproducing this

```bash
# the variant matrix of §4/§5
python3 dev/docs/spikes/headless-materialize/probe_variants.py /tmp/probe
cd uned && docker compose run --rm --entrypoint bash -v /tmp/probe:/work uned -c \
  'cd /opt/UED22; for v in A B C D E F G H J K; do
     wine UCC.exe Editor.ExecCommandlet Z:\\work\\$v.txt 2>&1 | grep -a "Nodes: \|Success\|protection"; done'

# a whole trunk, headless
python3 dev/docs/spikes/headless-materialize/headless_build.py \
    --project <project-root> --level <level> --workdir /tmp/hb --no-light
cd uned && docker compose run --rm --entrypoint bash -v /tmp/hb:/work uned -c \
  'cd /opt/UED22 && wine UCC.exe Editor.ExecCommandlet Z:\\work\\build.txt'

# structural check of the result
python3 dev/docs/spikes/2026-07-15-native-materialize/harness/bsp_health_check.py /tmp/hb/headless.dx
```

Under host Wine instead of Docker: copy `uned/UED22` somewhere writable (never run against the
tracked tree — Wine rewrites the inis), point `WINEPREFIX` at a scratch 32-bit prefix, and call
`wine 'Z:\<abs>\UED22\UCC.exe' Editor.ExecCommandlet 'Z:\<abs>\build.txt'` with `DISPLAY` unset.
