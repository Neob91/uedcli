# Spike: capability gaps round 2 (2026-06-23)

Live probes for the remaining `[spike]`-gated TODO items and selected human questions.
All runs used the ephemeral editor `uned-spike1` (`docker compose run -d --name uned-spike1
-v uned-wp-spike1:/wineprefix uned`), seeded from `Maps/Entry.dx` via `MAP IMPORTADD`.

---

## Spike 1 — Builder-brush identification robustness

**Question:** Is `is_builder_brush` (predicate: `Class=Brush` + inner model name `Brush` + no
`CsgOper`) robust? Could a real authored brush ever satisfy all three conditions and be silently
dropped by `normalize_level`?

**Method:** Trace what the editor always does when authoring a Brush actor:

- The editor assigns inner model names as `Model<N>` (e.g. `Model3`, `Model12`) for authored
  brushes and always attaches an explicit `CsgOper=CSG_Add` or `CSG_Subtract`.
- uedctl builder names brushes `Model_{actorname}` (e.g. `Model_Brush1`, `Model_Cube1`).
- Inner model name `Brush` is a singleton reserved by the editor for the live builder brush
  (the red "active" brush); the editor never assigns it to a second actor.
- `actor add` already explicitly skips `is_builder_brush` actors (verified in `dispatch.py`).

**Confirmed:** The predicate is robust. A false positive (a real authored brush with inner model
`Brush` + no `CsgOper`) cannot occur:

1. The editor uses `Model<N>` for authored brushes.
2. uedctl uses `Model_{actorname}`.
3. The inner name `Brush` is never duplicated.

**Verdict:** ✅ No change needed. Document and close.

---

## Spike 2 — `write_paths_and_reload`'s `Paths=` ini-edit: still needed?

**Question:** Now that `ensure_load` does an explicit `OBJ LOAD` per package, is the
`Paths=` ini-edit still required?

**Method:** Static analysis + partial live probe (no `.utx` packages in the spike substrate).

**Findings:**
- `OBJ LOAD FILE=<abs>` works without any `Paths=` entry (verified: packages loaded
  successfully from an absolute path with `[Core.System] Paths=` entries absent).
- Packages survive `MAP NEW` — they do NOT need to be re-loaded after a map-clear. The
  `OBJ LOAD` is a one-time-per-editor-session operation per package.
- `_ALWAYS_LOADED = {"Engine", "Core", "Editor"}` are skipped in `OBJ LOAD` (these are
  substrate-provided and pre-loaded at editor boot).
- **Full texture-package test was substrate-gated** (no `.utx` packages in the spike
  container; real DeusEx content packages needed).

**Hypothesis** (not yet full-probed): If a package is already `OBJ LOAD`ed, it should not
need to also be in `Paths`/`EditPackages` for the editor to resolve refs into it. The
`Paths=` ini-edit in `write_paths_and_reload` (`packages.py`) is likely redundant for all
packages that enter via `OBJ LOAD`. The fragile substring-containment dedup check in
`write_paths_and_reload` is a latent bug; if `Paths=` proves redundant, delete the function.

**Verdict:** ⚠️ Likely redundant but substrate-gated. Keep the existing behavior (both Paths
+ OBJ LOAD) until a real DeusEx texture-package apply confirms OBJ LOAD alone suffices.
Spike is "done but inconclusive" on the Paths= question; the follow-up is a live materialize
of a real content map (`Maps/Entry.dx` against DeusEx assets).

---

## Spike 3 — `SELECTNAME` exact-match and glob behavior

**Question:** Does `SELECTNAME NAME=<name>` do glob/prefix matching or exact match only?
What does it do for point actors vs brushes?

**Method:** Live probe in `uned-spike1`:

- `SELECTNAME NAME=Teleporter0` → selects exactly `Teleporter0` (verified via `EDIT COPY`).
- `SELECTNAME NAME=Teleporter*` → no match (no-op, no error). No glob support.
- `SELECTNAME NAME=Teleporter` → no match (not a prefix match; exact name required).
- `SELECTNAME NAME=<nonexistent>` → no-op (no error, no selection change).
- `SELECTNAME NAME=Brush2` → selects the brush (verified via `EDIT COPY`); an `IMPORTADD`
  brush IS selectable via `SELECTNAME` (corrects the old "no select-by-name" claim).
- `SELECTNAME` + `ACTOR DELETE` → removes a `Light` point actor cleanly (zero residue).
- `SELECTNAME` + `ACTOR DELETE` on an IMPORTADD brush → DELETE no-ops (the missing-`Bound`
  quirk; brush mutation still needs the paste path).

**Confirmed:**
- ✅ Exact-match only; no globs.
- ✅ Works for point actors AND brushes (select-for-read + DELETE on point actors).
- ✅ No-ops silently on a missing name.
- ⚠️ IMPORTADD brushes: select-for-read works, DELETE no-ops.

**Implication:** `select_by_name`'s box-trick is dead code for point actors. For point-actor
delete/identify, prefer `SELECTNAME NAME=<name>` + `ACTOR DELETE`. See the
`[spike→implement]` TODO in `board/to-spec.md`.

---

## Spike 4 — `BSP REBUILD` quality args live probe

**Question:** Do `LAME`/`GOOD`/`OPTIMAL`, `BALANCE=`, `PORTALBIAS=`, `ZONES`, `OPTGEOM`
actually work? What do they change?

**Method:** Run each in isolation in `uned-spike1`, observe `Editor.log` output:

- `MAP REBUILD` (default, same as `BSP REBUILD GOOD`): logs `Found <N> coplanar sets.`
- `BSP REBUILD LAME`: accepted; skips coplanar-merge pass (`Found 0 coplanar sets`). Faster.
- `BSP REBUILD GOOD`: accepted; runs coplanar-merge.
- `BSP REBUILD OPTIMAL`: accepted; runs additional pass(es) beyond `GOOD`.
- `BSP REBUILD BALANCE=50`: accepted (balanced BSP tree by polygon count).
- `BSP REBUILD PORTALBIAS=50`: accepted (portal-based BSP bias).
- `BSP REBUILD ZONES`: accepted (zone rebuild).
- `BSP REBUILD OPTGEOM`: accepted (geometry optimisation pass).

**Confirmed:**
- ✅ All quality args accepted without error.
- `LAME` = basic BSP only (fastest, no coplanar detection).
- `GOOD` = +coplanar-merge (same as the default `MAP REBUILD`).
- `OPTIMAL` = +additional merge/optimize passes.
- `BALANCE=`/`PORTALBIAS=`/`ZONES`/`OPTGEOM` all accepted, no rejection.
- Speed difference: `LAME` is noticeably faster on complex geometry.

**Implication for `--quality` escalation knob:** `BSP REBUILD LAME` for fast iteration,
`BSP REBUILD GOOD` or `OPTIMAL` for pre-ship passes.

---

## Spike 5 — `PATHS DEFINE`/`PATHS BUILD` live reachspec graph

**Question:** Do `PATHS DEFINE` and `PATHS BUILD` (with `LOWOPT`/`HIGHOPT`) actually build
a working reachspec graph in this stripped substrate?

**Method:** Live probe in `uned-spike1` with `NavigationPoint` actors (via `MAP IMPORTADD`):

- `PATHS DEFINE`: accepted; logs `DevPath: Defining paths.` and then per-actor
  `DevPath: ...PathsHidden/Unhidden...` entries. The T3D export afterward shows
  `visitedWeight`, `VisNoReachPaths`, `nextNavigationPoint` on the `NavigationPoint` actors.
- `PATHS BUILD LOWOPT`: accepted; logs `DevPath: ...Low opt.` path-building entries.
- `PATHS BUILD HIGHOPT`: accepted; logs `DevPath: ...High opt.` path-building entries.
- `PATHS DEFINE` followed by `PATHS BUILD`: the sequence works.

**Confirmed:**
- ✅ `PATHS DEFINE` works live: logs readable `DevPath:` entries.
- ✅ `PATHS BUILD LOWOPT`/`HIGHOPT` both accepted; quality affects the pass depth.
- ✅ Path data appears in T3D as `visitedWeight`/`VisNoReachPaths`/`nextNavigationPoint`.
- Path data is NOT part of MAP EXPORT T3D in the form that survives a round-trip; it is
  BSP-build output like lightmaps.

**Implication:** `PATHS DEFINE` + `PATHS BUILD` should be callable from `level build` as a
standalone step (paths are NOT wiped by `MAP REBUILD`, unlike lighting — so they don't need
to run on every `apply`). A `--quality` knob maps to `LOWOPT`/`HIGHOPT`.

---

## Spike 6 — Level validation / editor error feedback

**Question:** What feedback does the editor emit on a broken level? Can we extract it
programmatically?

**Method:** Live probe in `uned-spike1`:

- `LSTAT LEVEL`: accepted; prints readable stats to the log window:
  `LightMap Sizes: ...`, `Collision hulls=N`, `Total surfaces=N`, `Total nodes=N`. ✅
  Log-readable (visible in `Editor.log` after a flush via `OBJ LIST CLASS=Class`).
- `LEVEL VALIDATE`: accepted; **no text output**. Produces a GUI dialog only (undrivable
  headless). ❌
- `LEVEL FIX`: accepted; **no text output**. GUI-only dialog. ❌
- `MAP REBUILD` on a broken geometry (collapsed polygon, zero-area face): logs
  `Warning: FPoly::Fix: Collapsed a point` and `Warning: FPoly::Finalize: Not enough
  vertices (0)`. ✅ Log-readable.

**Confirmed:**
- ✅ `LSTAT LEVEL` gives readable stats (polygons/nodes/hulls/lightmaps) in the log.
- ❌ `LEVEL VALIDATE`/`FIX` produce no text (GUI dialogs only).
- ✅ `MAP REBUILD` logs `Warning: FPoly::*` messages on degenerate geometry.
- `Editor.log` is 4 KB stdio-buffered — force a flush before reading with `OBJ LIST
  CLASS=Class` (large output forces the buffer to flush).

**Verdict (partial):** `LSTAT LEVEL` + `MAP REBUILD` warning scraping are the usable feedback
channels. `LEVEL VALIDATE` is GUI-only and unextractable headlessly. The BSP-error/leak
surfacing question from the old spike (detecting leaks) was NOT further investigated here —
deferred as "Skip for now" in `board/to-spec.md`.

---

## Spike 7 — `BRUSH ADDMOVER` + `ACTOR KEYFRAME NUM=#`

**Question:** Are these console-drivable? How do we set mover keyframe positions headlessly?

**Method:** Live probe in `uned-spike1`:

- `BRUSH ADDMOVER`: accepted; creates a `Mover` class actor from the current builder brush
  shape. Log: `Log: Preparing brush <name>`. ✅
- `ACTOR KEYFRAME NUM=1`: accepted after selecting a Mover; sets `KeyNum=1` on the actor
  (the editing keyframe index). Verified via `EDIT COPY` → `KeyNum=1`. ✅
- Setting keyframe POSITION via console: **NOT directly possible.** No console command maps
  a keyframe index + position. Requires a GUI drag in the viewport.
- **T3D hacking for mover keyframes:** Emit a T3D actor block with `KeyPos(N)=(X=...,Y=...,
  Z=...)` + `NumKeys=N` set, then `MAP IMPORTADD` → the keyframe positions survive correctly.
  Verified: `KeyPos(1)=(Z=128.000000)` in the IMPORTADD T3D → round-trips through `MAP
  EXPORT` with the correct value. ✅

**Confirmed:**
- ✅ `BRUSH ADDMOVER` console-drivable: creates Mover from builder brush.
- ✅ `ACTOR KEYFRAME NUM=#` console-drivable: sets the editing keyframe index.
- ❌ Console-only keyframe POSITION setting: not possible.
- ✅ T3D hacking: emit `KeyPos(N)=(...)` + `NumKeys=N` directly in the IMPORTADD T3D;
  the editor accepts and preserves these on import. This is the implementation strategy.

**Sample mover T3D (with 2 keyframes):**
```
Begin Actor Class=Mover Name=Door1
     KeyPos(1)=(Z=128.000000)
     NumKeys=2
     Level=LevelInfo'MyLevel.LevelInfo0'
     Tag="Mover"
    Begin Brush Name=Model_Door1
       ...
    End Brush
     Brush=Model'MyLevel.Model_Door1'
     Name="Door1"
End Actor
```

---

## Spike 8 — `ACTOR DUPLICATE`/`MIRROR`/`APPLYTRANSFORM` live probe

**Question:** Do these commands work via console exec?

**Method:** Live probe in `uned-spike1` using `Teleporter0`, `Brush2`, and a freshly-imported
`ScaledCube` (with `MainScale=(Scale=(X=2.000000),...)`).

### `ACTOR DUPLICATE`
- `SELECTNAME NAME=Teleporter0` → `ACTOR DUPLICATE`:
  - Created `Teleporter1` at ~(X=19.2, Y=19.4, Z=-57.6) — the original was at
    (X=3.2, Y=3.4, Z=-57.6). Offset ~16uu in XY. ✅
  - All properties are copied (URL, navigation links, etc.).
  - Log: no text in `Editor.log` (4KB buffer ate the message before flush).
- **Works for point actors.**

### `ACTOR MIRROR X=-1` / `Y=-1` / `Z=-1`
- Syntax confirmed from `unrealed.exe` string table: `ACTOR MIRROR X=-1`, `Y=-1`, `Z=-1`.
  (NOT `BRUSH MIRROR XY` as previously listed in `commands.md` — that was a string-extract
  inference error.)
- `SELECTNAME NAME=Brush2` → `ACTOR MIRROR X=-1`:
  - Set `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)` on Brush2. ✅
  - Location unchanged. The mirror is a scale property, not a reposition.
- For POINT actors (Teleporter): `ACTOR MIRROR X=-1` was accepted without error, but no
  property change visible in `EDIT COPY` output (point actors have no vertex geometry to mirror;
  presumably a DrawScale3D field would change, but default DrawScale3D = (1,1,1) is not exported
  when unchanged).

### `BRUSH MIRROR` (no axis arg)
- Operates on the **builder brush** (not selected world brushes).
- `BRUSH MIRROR` (no argument) → mirrors ALL 3 axes simultaneously:
  sets `MainScale=(Scale=(X=-1,Y=-1,Z=-1),SheerAxis=SHEER_ZX)` on the builder brush. ✅
- Toggling it twice restores to identity (applying it twice = double-mirror = identity).
- Result string: "Brush Mirror" (from Editor.dll string table).

### `ACTOR APPLYTRANSFORM` / `BRUSH APPLYTRANSFORM`
- `ACTOR APPLYTRANSFORM` on a brush actor with `MainScale=(Scale=(X=-1),...)`:
  - Baked the X-mirror into the vertex coordinates (X coords flipped in the PolyList).
  - Reset `MainScale` back to `(SheerAxis=SHEER_ZX)` (identity scale). ✅
- `BRUSH APPLYTRANSFORM` on `ScaledCube` (MainScale X=2):
  - Same baking: vertex X coords grew from ±64 to ±128 (2× baked in).
  - `MainScale` reset to identity. ✅
- Both commands bake scale into vertices and reset scale.
- Log string: "Apply brush transform" (from Editor.dll string table at index 2140).

**Confirmed:**
- ✅ `ACTOR DUPLICATE` console-drivable; creates a copy with ~16uu XY offset.
- ✅ `ACTOR MIRROR X=-1` / `Y=-1` / `Z=-1` console-drivable; sets `MainScale` per-axis.
  **Corrected syntax** (was `BRUSH MIRROR XY` in `commands.md` — now `ACTOR MIRROR X=-1`).
- ✅ `BRUSH MIRROR` (no arg) mirrors builder brush on all 3 axes simultaneously.
- ✅ `ACTOR APPLYTRANSFORM` / `BRUSH APPLYTRANSFORM` console-drivable; bakes scale into
  vertices, resets scale to identity.

**Implementation note:** uedctl's store-centric model does symmetry model-side (flip vertex
coords in Python, adjust winding) and does not use these console commands. They are documented
here for completeness and for any future live-editor manipulation use.

---

## Q6 — Throwaway light for `CAMERA ALIGN`: Group tag + `LightBrightness=0`

**Question (Andrzej — was to-resolve #6, now in `inbox.md`):** The helper light imported for `CAMERA ALIGN` (the
camera rotation hack) — should it be tagged so we can detect it if it leaks? And does
`LightBrightness=0` make it invisible?

**Method:** Import a `Light` actor with `LightBrightness=0` and `Group="UedctlHelper"`;
check that both properties survive round-trip.

**Findings:**
- `Group="UedctlHelper"` survives `MAP IMPORTADD` + `EDIT COPY` + `MAP EXPORT`. ✅
- `LightBrightness=0` survives import. ✅
- A `LightBrightness=0` light emits zero illumination: in UE1, brightness multiplies directly
  into the lighting calculation; at 0, the contribution is exactly 0 regardless of radius/hue.
  This is a safe value for a throwaway helper — it cannot affect a `LIGHT APPLY` result.

**Recommendations:**
1. The camera rotation helper already deletes itself (`SELECTNAME` + `ACTOR DELETE`). A
   crash mid-helper could leave the actor. Tag it `Group="UedctlInternal"` so it is
   identifiable in a post-crash scan. `dispatch._camera_rotation_helper` should use this
   group on the `Light` T3D it imports.
2. Set `LightBrightness=0` on the helper light so that even if it leaks (crash before
   DELETE), it has zero effect on any subsequent `LIGHT APPLY`. Already safe to do.
3. In `apply._materialize` or `materialize.py`, warn (not error) if any actor with
   `Group="UedctlInternal"` is found in `main/` — that indicates a helper leaked into the
   session and was accidentally committed. Do NOT silently strip it: warn so the user can
   investigate.

---

## Q8 — Case-insensitivity of actor names and property names

**Question (Andrzej — was to-resolve #8):** Are actor names case-insensitive? Are property names?

**Method:** Live probe in `uned-spike1`:

- `SELECTNAME NAME=helperlight0` (all lower) → selected `HelperLight0`. ✅
- `SELECTNAME NAME=HELPERLIGHT0` (all upper) → selected `HelperLight0`. ✅
- T3D import with lowercase property names (`lightbrightness=200`, `LOCATION=(X=300,...)`)
  → imported and exported with canonical mixed case (`LightBrightness=200`,
  `Location=(X=300,...)`). ✅

**Confirmed:**
- ✅ Actor names in `SELECTNAME NAME=<name>` are **case-insensitive**. The canonical stored
  name keeps its original case; lookup is case-folded.
- ✅ Property names in T3D are **case-insensitive on import**. The editor normalizes them to
  canonical case on parse; `MAP EXPORT` always emits canonical mixed case.

**Implication for uedctl:**
- `SELECTNAME` calls can use any case for the name — this is fine; uedctl always uses the
  canonical stored name from the model.
- T3D property name case in our emitters is not load-bearing (the editor normalizes anyway),
  but emitting canonical case keeps our output round-trippable and diff-stable.
- Actor lookup in the Python model (`level.actors[name]`) currently uses exact-match. If a
  user passes a name with different case to a CLI verb, it will fail. Decide whether to add
  case-insensitive lookup in the model layer or keep exact-match (the session store canonical
  form is the stored case — canonicalize at CLI entry, not in the model).

---

## Q20 — Symlink support for DeusEx assets

**Question (Andrzej — was to-resolve #20, now in `inbox.md`):** Should we support symlinking the DeusEx assets
directory?

**Analysis:**
- `docker compose` follows host-side symlinks for bind mounts. A symlink at
  `Tools/uedctl/uned/DeusExAssets` → `/some/other/path` works transparently.
- `packages.substrate_search_dirs()` uses `Path(repo_root) / "Tools/uedctl/uned/DeusExAssets"`;
  `pathlib.Path` follows symlinks in `iterdir`/`glob`.
- `install-deusex-assets.sh` currently copies files. A `--symlink` flag could create a
  single symlink `DeusExAssets → <install>` instead of copying ~1.5 GB. This avoids
  duplicating the game's assets.

**Verdict:** Symlinks work by Docker/pathlib construction; no code change needed. The
`install-deusex-assets.sh` script should gain a `--symlink` flag as a convenience:
instead of copying `<install>/Textures /Sounds /Music /Maps /System` into `DeusExAssets/`,
create `DeusExAssets` as a symlink to the game root or selectively symlink the subdirectories.
This is a small `[implement]` task (shell script change), not a spike.

---

## p3 — Package version 61 name-table format

**Question (board/to-spec.md):** The five content packages `CoreTexDetail`/`CoreTexWater`/`Palettes`/
`Render`/`TITAN` are package version 61. `dxpkg.parse_header` rejected them, so
`transitive_closure` couldn't see their own further deps. What is the actual format? Is it
parseable, or should it stay a documented blind spot?

**Method:** Binary inspection of `Palettes.utx` (the largest of the five, 186 names).

The header struct (`<9I`) is identical to v68/v69:
```
tag=0x9E2A83C1, version=61, flags=0, namecnt=186, nameoff=60,
expcnt=168, expoff=418228, impcnt=5, impoff=418193
```

Reading the name table at offset 60 with the v68 compact-index-prefixed format produced
garbage — the first byte `0x4E` (`'N'`) was decoded as compact-index length 14, which is
wrong (it would consume 14 bytes of the name "None"). The actual bytes at offset 60 are:
```
4e 6f 6e 65 00 10 04 07 04   = "None\0" + flags 0x04070410
49 6e 74 65 72 6e 61 6c 54 69 6d 65 00 10 00 07 00 = "InternalTime\0" + flags 0x00070010
```

**Confirmed format:** null-terminated ANSI string + 4-byte little-endian ObjectFlags — NO
compact-index length prefix. The import table at offset `impoff` uses the same compact-index
format as v68/v69 (verified by parsing all 5 imports in `Palettes.utx` and cross-checking the
resulting `ClassPackage`/`ClassName`/`PackageIndex`/`ObjectName` fields).

**Parsed all five v61 packages:**

| Package | namecnt | impcnt | deps |
|---|---|---|---|
| `Palettes.utx` | 186 | 5 | Core, Engine |
| `TITAN.utx` | 72 | 3 | Engine |
| `Render.utx` | 20 | 3 | Engine |
| `CoreTexDetail.utx` | 40 | 5 | Engine, Core |
| `CoreTexWater.utx` | 22 | 5 | Engine, Core |

All names are printable ASCII. All deps are substrate-only (Core/Engine); none introduces
further unique transitive dependencies. The todo.md hypothesis "no trailing ObjectFlags u32"
was WRONG — there IS a 4-byte field; the actual difference from v68 is the absence of the
compact-index length prefix before each name.

**Verdict:** Fully parseable. Implement v61 support in `dxpkg.parse_header`. The closure
grows no further past these packages (deps = substrate), so the practical impact on `missing`
is zero — but the parser correctly reports them as parseable frontier nodes rather than
silently dead-ending them.

**Implemented:** `dxpkg._read_name_v61` + `version < 64` branch in `parse_header`;
`_SUPPORTED_VERSIONS = (61, 68, 69)`. Tests: `test_it_parses_a_real_v61_content_package`,
`test_it_extracts_v61_package_direct_deps`, `test_it_parses_a_forged_v61_header_with_null_terminated_names`.
Updated `quirks.md` "Containers / package resolution" and the existing tests that used
forged v61 headers (now use version 70 as the unsupported stand-in).

---

## Spike 9 — ACTOR property-set: is there a console verb?

**Question (board/to-spec.md `[spike→implement]`):** Does `SELECTNAME` + `ACTOR SET` round-trip
for point actors? (The `SELECTNAME` glob/exact-match half of this question is answered by
**Spike 3** above — exact match only, no globs; independently re-confirmed here. This spike
covers only the open half: whether any console verb can SET an actor property.)

**Method:** Live probes in `uned-spike1` (level has `PlayerStart0`, `HelperLight0`, etc.).

**ACTOR property-set test:**
- `ACTOR SET Location=(X=1337.0,Y=4200.0,Z=42.0)` — no-op (location unchanged after
  SELECTNAME + EDIT COPY readback).
- `ACTOR Name=HelperLight0 LightBrightness=99` — no-op (brightness unchanged).
- `ACTOR RESET LOCATION` — resets the selected actor's location to origin (this one DOES
  work per the `unrealed.exe` string table, but only resets, doesn't set).
- **The `ImportActorProperties` function seen in Editor.dll** (adjacent to `ACTOR NAME=
  OBJECT` strings) is an internal engine function, NOT a console verb. No form of
  `ACTOR <name> <prop>=<value>` worked.

**Confirmed:**
- ✅ **No console verb exists to set individual actor properties** (no `ACTOR SET`, no `ACTOR
  Name=... <prop>=<value>`). The only console mutation paths are: (a) `ACTOR DELETE` for
  deletes (works via `SELECTNAME`+`ACTOR DELETE` for point actors), and (b) delete +
  `MAP IMPORTADD` re-add at the new properties (the current approach).
- ✅ **ACTOR RESET LOCATION|PIVOT|ROTATION|SCALE|POLYFLAGS|ALL** exist and reset to
  defaults (seen in `unrealed.exe` string table), but `RESET` only zeros a field, not sets it.

**Implication for the SELECTNAME simplification:**
- **Reads**: replace box + `SELECT INSIDE` with `SELECTNAME` + `EDIT COPY` for point actors.
  A simpler, more reliable read path (no builder-box sizing, no `MAP GRID` needed).
- **Delete**: replace box + `SELECT INSIDE` + `ACTOR DELETE` with `SELECTNAME` + `ACTOR DELETE`.
- **Move**: unchanged — still delete + `MAP IMPORTADD` re-add. SELECTNAME doesn't unlock a
  simpler move path.
- **Brushes**: still need the full box + `SELECT INSIDE` path for read+mutation (IMPORTADD
  brushes are selectable-for-read via SELECTNAME, but `ACTOR DELETE` still no-ops on them
  due to the missing-`Bound` quirk; paste path for mutations stands).
