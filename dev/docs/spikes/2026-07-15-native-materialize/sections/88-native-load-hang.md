# 88 — Native real-level load: TWO stacked blockers (Engine-package import fast-fail, then a CPU-bound hang loading DeusEx mesh/decoration packages)

**Status:** Blocker 1 **FIXED 2026-07-19** (see "Blocker 1 — RESOLUTION" below); blocker 2 still
LOCALIZED, open. **Date:** 2026-07-19.
**Scope:** originally DIAGNOSIS only (four harness scripts + this writeup + a board item); the
blocker-1 fix was then implemented (`pkgref.py`/`assemble.py`/`materialize.py` + a regression).

### Confidence legend
✅ live-verified this session (bounded headless boots + captured `DeusEx.log`).

---

## 1. TL;DR — the reported hang is real, but it sits BEHIND a second, front-running fault

Booting a native real level surfaces **two independent blockers, stacked**:

- **Blocker 1 (front) — Engine-package import fast-fail.** The native build imports **every** actor
  class under the `Engine` package. Correct for genuine Engine classes; fatal for the DeusEx-package
  classes a real level instantiates (`DeusExMover`, `ATM`, furniture, NPCs…). The engine's linker
  aborts on the first missing class and reverts to the boot map — **in under a second, NOT a hang**:
  ```
  Log: Loading: Package NativeUnatco
  Warning: Failed to load 'NativeUnatco': Can't find Class in file 'Class Engine.DeusExMover'
  Log: LoadMap: DX.dx …                         ← reverted to boot map
  ```
  This is what a fresh `NativeUnatco.dx` does today, so the "5.5-min 95 %-CPU spin" is not currently
  reproducible from a stock build — blocker 1 short-circuits it.

- **Blocker 2 (behind it) — CPU-bound hang in the load-time RENDER path.** With the class imports
  CORRECTED (§4), the same trunk's map gets past linking and **spins one thread ~92 % CPU for
  minutes**, log frozen mid-line at `Log: Loading: Pack…`, never reaching "Bringing Level … up for
  play". A `winedbg` backtrace of the single spinning thread (§4) puts it in the DeusEx
  **render/Extension path** (`deusex`-mainloop → `extension` → `engine` render → `softdrv` / `core`
  / `windrv::BitBlt`), **NOT** in the object linker or GC. It reproduces on a WORLD-ONLY build (no
  DeusEx actors), and the BSP is structurally sound (no cyclic/out-of-range indices), so this is the
  software renderer looping on the over-split world during the load-time frame draw. Matches the
  original ~5.5-min report. ✅

So correct solidity + correct imports are both necessary and still not sufficient; blocker 2 is the
original CPU loop, unmasked.

## 2. Blocker 1 — the exact defect, in code ✅

- `uedctl/native/pkgref.py::_package_of_class` returns `default_package` ("Engine") whenever
  `uprops.package_of_class` is missing — and **it is missing** (`hasattr(uprops,
  "package_of_class") == False`), so it is missing for EVERY class:
  ```python
  pkg = getattr(uprops, "package_of_class", lambda _c: None)(classname)  # -> None, always
  return default_package                                                  # -> "Engine", always
  ```
- `materialize._collect_actors` (~L329) passes the trunk's **bare** class (`a.cls == "DeusExMover"`)
  — the trunk stores unqualified class names — so `qualified_class_ref` never takes its
  `"." in qualified` branch and always lands on the Engine default. Net: `Engine.<AnyClass>`.
- The linker verifies imports in order and throws on the first missing class. `Engine.DeusExMover`
  is import[5] (first non-Engine class); strip the movers and it's `Engine.ATM` (§4). Module to fix:
  **`pkgref.py`** (class→package resolution). No Rust involved.

**Why it was never caught:** the whole native corpus was validated on `Test_Castle.dx` + tiny
synthetic maps, which **only instantiate genuine Engine classes** (`PlayerStart`, `SkyZoneInfo`,
`ZoneInfo`, `Level`), so `Engine.<class>` is always correct for them and they load/render. The bug
is structurally invisible until a build instantiates a DeusEx-package actor — i.e. the first real
level. (This is also the root of the 9 355 "not in class schema (skipped)" prop warnings:
`default_schema_lookup` early-returns `{}` for any bare class — same missing-qualification cause.)

### Blocker 1 — RESOLUTION (implemented 2026-07-19) ✅

Fixed by giving the native build a real class→package oracle instead of the `Engine` default:

- **`pkgref.build_class_package_index(dirs)`** scans the game's real `.u` CODE packages on the
  composed search path (`packages.schema_search_dirs`, the SAME seam `default_schema_lookup` uses)
  and maps `classname.casefold() -> defining-package-stem` (a UClass export = one whose own
  class-ref resolves to `Class`/0). Memoized per dir-set. Cross-checked against the golden
  `03_NYC_UNATCOHQ.dx` import table: **all 95 real actor classes match** (`DeusExMover`/`ATM`/
  `AllianceTrigger`/`AnnaNavarre`→`DeusEx`, `PlayerStart`/`ZoneInfo`/`AmbientSound`→`Engine`). The
  4 non-matches (`Model`/`Polys`/`Level`/`TextBuffer`) are native pseudo-classes with no normal
  UClass export; they fall back to the caller's `default_package` — `Engine`, which is correct
  (and `Model`/`Polys`/`Level` are emitted qualified elsewhere anyway).
- The index is threaded `materialize.default_class_packages()` → `assemble_level(class_packages=…)`
  → `Resolver`, and consulted by `Resolver._package_of_class` (which no longer calls the phantom
  `uprops.package_of_class`; a bare class → its indexed package, else the `default_package`
  `Engine`). A trunk that already stores qualified classes (the **castle** — `Engine.Brush`, …) is
  untouched: its classes already carry a `.`, so `_package_of_class` is never called and its import
  table stays byte-identical (verified: 9 class imports, all `Engine`/`Core`; Model body still
  43.04% / 485 surfs / 1156 nodes / 283624 B).
- **Result on `NativeUnatco.dx`:** `DeusExMover`/`ATM` now import as `DeusEx.*` (77 `DeusEx` + 13
  `Engine` class imports, zero misclassed, was all-`Engine`). Boot-confirmed: the `Can't find Class
  Engine.DeusExMover` linker abort is GONE and the game loads UNATCO's real texture packages
  (`UNATCO`/`NYCBar`/`Constructor`/`NewYorkCity`/…) — it now reaches **blocker 2** (the render CPU
  loop) instead of fast-failing on the class.
- A bare class the index can't resolve (defining package absent from the search path) still falls
  back to `Engine.<X>` but now emits a **named warning** rather than silently mis-linking — except
  the benign `Level`/`LevelInfo` pseudo-classes.
- **DELIBERATELY NOT done here (scoped out):** qualifying the bare class for the SCHEMA lookup too
  (to close the 9 355 "not in class schema (skipped)" prop warnings + restore the 17 Sound/1 Music
  imports). That was tried and REVERTED: once props resolve, object-property refs to sibling actors
  (`Region.Zone=LevelInfo'MyLevel.LevelInfo0'`, `Base=`, …) emit a bogus `MyLevel` package import,
  and the game then fails the load with `Can't find file for package 'MyLevel'` (a NEW, worse
  failure than blocker 2). Intra-level object refs must resolve to LOCAL export refs, not imports —
  a separate feature. The prop-skip-warning closure therefore stays a follow-up, gated on that. So
  the class-import fix here leaves the props exactly as before (skipped).

**Regression:** `tests/test_native_materialize.py::test_class_package_index_resolves_deusex_classes_
to_real_packages` (index oracle: `DeusExMover`/`ATM`/`AllianceTrigger`→`DeusEx`, `PlayerStart`/
`ZoneInfo`→`Engine`) and `::test_real_deusex_class_imports_as_deusex_not_engine` (end-to-end: a
synthetic 1-DeusEx-actor build emits `DeusEx.DeusExMover`, not `Engine.*`). Both read the real
configured install (`~/.uedctl/config.toml` `[games.deusex].paths`, or `$UEDCTL_GAME_SYSTEM`) and
skip when no install is present.

## 3. It is level-independent — every real level has it, none "hangs" at blocker 1 ✅

Offline import-table inspection (`bsp_health_check.py`/inline) of the existing native builds — the
load outcome is a deterministic function of the import table:

| native build | instantiated classes mis-imported as `Engine.X` (count) |
|---|---|
| `NativeUnatco.dx` | 83 (`DeusExMover`, `ATM`, `AllianceTrigger`, `AnnaNavarre`, …) |
| `NativeCatacombs.dx` | 89 (`BreakableGlass`, `BreakableWall`, `DeusExMover`, `ATM`, …) |
| `NativeHKMarket.dx` | 133 (`BreakableGlass`, `DeusExMover`, `ATM`, `AcousticSensor`, …) |
| `NativeCastle.dx` + all tiny maps | 0 (only genuine-Engine `PlayerStart`/`ZoneInfo`/`Level`) |

The task's "does HK/Catacombs hang too (size vs structure)?" is therefore **moot at blocker 1**: all
three real levels fast-fail identically on their first DeusEx-package class; none reach a hang there.
(UNATCO boot-confirmed; Catacombs/HK follow by the identical import fault — abort-on-first-missing is
not size-dependent.)

## 4. Blocker 2 — LOCALIZED to a main-thread render loop over the world, during load ✅

`build_native_unatco_qualified.py` derives each class's TRUE package from the golden
`03_NYC_UNATCOHQ.dx` import table and **runtime-patches** `uprops.package_of_class` (no production
file edited), so `DeusExMover→DeusEx`, `ATM→DeusEx`, and the still-Engine classes (`PatrolPoint`,
`Teleporter`, `Trigger`, `PlayerStart`, `Level`) are all genuinely Engine. The resulting
`NativeUnatcoQual.dx` has **zero wrong class imports** and clears blocker 1 — then hangs:

| sample | cpu | rss | log lines | last log line |
|---|---|---|---|---|
| t+0:50 | 79 % | 193 MB | 130 | `Log: Loading: Pack` |
| t+2:00 | 91 % | 189 MB | 130 (frozen 5×) | `Log: Loading: Pack` |
| t+5:00 | 92 % | 115 MB | 130 (frozen 19×) | `Log: Loading: Pack` |

**What it is NOT:**
- **Not the DeusEx decoration/NPC actors.** `--strip-nonengine` (229 DeusEx-package actors removed;
  `NativeUnatcoWorld.dx`, world brushes + Engine-class actors + PlayerStart) **hangs identically** —
  same ~90 % CPU, same frozen point right after `Log: Loading: Package Paris` → `Log: Loading: P`.
  So the hang is the WORLD, not the furniture/NPCs. (All referenced texture packages — `Paris`,
  `Constructor`, `Mobile_Camp`, `NewYorkCity`, `V_Com_Center`, `area51textures`, `CoreTex*` — are
  present in the container, so it is not a missing package either.)
- **Not a malformed BSP.** `bsp_health_check.py` finds no cyclic or out-of-range node-child, leaf,
  zone, surf, or vert-pool index on `NativeUnatcoQual` / editor 03 / castle — so it is not an
  infinite point-region/filter descent over a bad tree.
- **Not the linker / GC.** A `winedbg` attach shows a SINGLE spinning thread (Linux tid 537, ~200 s
  of userspace time; all 10 other threads idle). Its backtrace, sampled repeatedly, is consistently
  in the **render / Extension path**, never the loader:
  ```
  softdrv (+0x28444)  |  core (+0x2ec78 …)  |  engine render (+0x69124/+0x90162/+0xa56c5)
    → windrv::BitBlt (gdi32 → win32u → NtGdiBitBlt)
    → engine (+0x9117e)
    → extension (+0x266df)          ← present in EVERY sample (the DeusEx UI/render extension)
    → deusex (+0x1487a → +0x97f9 → +0x215ea)   ← the game's main loop / WinMain
  ```

**Reading:** the game is stuck in the DeusEx main loop's per-iteration **frame render** (the
loading-screen / first-frame draw through the software renderer, `SoftDrv` + `engine` render +
`BitBlt`) — a render call that never returns, so the load never advances and the log line never
completes. The trigger is in the WORLD the renderer walks: the native world is uniformly BSP
over-split (Nodes +33 %, Leaves +30 %, over-zoned 20 vs 7 — §84) and this is the software renderer
looping on that geometry during load (an `OccludeBsp`-class pathology; cf. the "Anomalous
singularity" render loop that a bad node `iZone` caused on the castle, board 2026-07-17). A related
world-texture-reference defect is also possible (native emits 124 texture imports vs editor's 133,
some group-less), since the render path touches texture data — see §7. (Native also drops the
editor's 17 `Sound` + 1 `Music` imports — an unrelated actor-property omission.)

## 5. Responsible modules / scope of fixes

- **Blocker 1 — `pkgref._package_of_class`. DONE 2026-07-19** (see "Blocker 1 — RESOLUTION" above).
  Implemented as `pkgref.build_class_package_index` (scan the composed `.u` set + memoize), threaded
  through `assemble_level` into `Resolver._package_of_class`. Boot-confirmed past the class abort.
  The prop-skip-warning closure was scoped OUT (it surfaces a separate `MyLevel` local-object-ref
  defect — see RESOLUTION). Regression in `tests/test_native_materialize.py`.
- **Blocker 2 — the WORLD build (software-renderer input), most likely the BSP over-split, possibly
  a world-texture reference.** The loop is in the software renderer walking the native world during
  the load-time draw (§4), and it reproduces with zero DeusEx actors — so the responsible output is
  the **world Model** (`bspcsg.rs`/`passes.rs` BSP, the +33 % over-split / 20-vs-7 over-zoning of
  §84/§85) and/or the **world-surface texture references** (`pkgref`/`materialize` texture emit; 124
  vs 133 imports, some group-less). **Effort: unknown until §7 pins renderer-BSP vs texture.**

## 6. Reproduce
```
cd Tools/uedctl
. "$HOME/.cargo/env" && .venv/bin/maturin develop --release -m uedctl-native/Cargo.toml   # if core changed
H=dev/docs/spikes/2026-07-15-native-materialize/harness
# Blocker 1 — fast-fail on Engine.DeusExMover:
.venv/bin/python $H/build_native_unatco.py         ; $H/load_hang_probe.sh NativeUnatco 7
# Blocker 1 — strip movers => next class Engine.ATM:
.venv/bin/python $H/build_native_unatco_variant.py --strip-movers ; $H/load_hang_probe.sh NativeUnatcoNoMov 7
# Blocker 2 — correct class packages => clears blocker 1, HANGS at DeusEx mesh-pkg load:
.venv/bin/python $H/build_native_unatco_qualified.py ; $H/load_hang_probe.sh NativeUnatcoQual 8
# Blocker 2 isolation — strip DeusEx-package actors:
.venv/bin/python $H/build_native_unatco_qualified.py --strip-nonengine --out DX/Maps/NativeUnatcoWorld.dx
$H/load_hang_probe.sh NativeUnatcoWorld 7
# BSP structural health (no cycles / bad indices):
.venv/bin/python $H/bsp_health_check.py DX/Maps/NativeUnatcoQual.dx DX/Maps/03_NYC_UNATCOHQ.dx
```
Boot transcripts + copied `DeusEx.log`s land in `harness/_out/` (gitignored).

## 7. Next decisive test (blocker 2) — renderer-BSP vs world-texture
The loop is world-only and in the render path. Two candidates remain; discriminate cheaply:
1. **Renderer-BSP (leading).** Build a much SMALLER native subset of the UNATCO world (e.g. a
   spatial slice / first N brushes) qualified, and boot: if the small subset loads and a large one
   hangs, and the hang scales with node/leaf count, it is the software renderer choking on the
   over-split/over-zoned tree — fold into the existing over-split (§84) / over-zoning (§70) lanes,
   and re-check once those close. Corroborate with a native build whose `find_best_split` is tuned
   toward the editor's node count.
2. **World texture.** Re-texture every world surface to one known-good base texture (bypass the
   per-surface `Texture=` emit) and boot: if THAT loads while the real-texture build hangs, the
   defect is the world-surface texture reference emit (`pkgref.texture_ref` / group resolution;
   pin the offending 9 missing / group-less refs vs editor 03).
The `winedbg` attach recipe used here (`printf "attach 0x20\nthread 0x24\nbacktrace\ndetach\nquit\n"
| DISPLAY=:99 winedbg`, wine PID from `info process`) resolves the spinning frame to the exact
`engine`/`softdrv` offset for symbolication against the DLLs (see `unrealed/extracting-from-dll.md`).
