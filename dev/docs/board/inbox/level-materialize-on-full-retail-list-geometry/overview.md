+++
priority = "p1"
kind = "debug"
summary = "level materialize wedged every retail map: the typed MAP SAVE raced a slow MAP REBUILD. FIXED by batching the write drive into one EXEC <file>; geometry gate downgraded to warn. Verify texture-match bug remains (tracked separately)."
+++

# `level materialize` on the full retail map list — two blockers

Goal: `level import` every OG Deus Ex map to a trunk, then `level materialize` the trunk back to a
`.dx`, across all 88 shipped maps. Baseline run (2026-08-23) on the live install
(`dev/games/deusex`), scratch project `_scratch/matall`.

## Import is reliable

All 88 maps `level import` to a trunk with no failures (slowest 84 s). Nested struct properties
(`PostScale=(Scale=(X=…))`) survive — the native-writer nested-struct limitation does not apply on
this path.

## Blocker 1 — the pre-import geometry gate refuses retail brushes

`materialize()` runs `geometry.validate_brush` on every brush before importing. Retail content
fails it: **48 of 89 levels** contain at least one brush with a non-planar poly (a vertex >0.5 uu
off its own face plane). It is a small share of geometry — 228 refused brushes of 77,118 (0.30 %) —
but one refusal aborts the whole build, so the per-level failure rate is 48/89.

- Every refusal is class `non-planar`; zero coincident, zero degenerate, zero parse errors.
- Off-plane distance: min 0.501, median 1.414, max 506.3 uu. Not a tolerance-tuning problem — the
  long tail is genuinely warped faces, and the min sits right on the 0.5 tol.
- The editor itself accepts these brushes: it built the original maps. `doctor` already reports the
  same condition as a WARN (`category="planar"`), not an error.
- Worst: `06_hongkong_versalife` 27, `03_nyc_747` 18, `15_area51_bunker` 16.

Open question for the owner: should the pre-import gate refuse non-planar brushes at all, or warn
and let the editor build them (matching `doctor`'s WARN severity)? Filed as a question, not changed.

## Blocker 2 — `MAP SAVE` wedges on the re-import path

`02_NYC_Bar` (small, 953 surfs, a spike-proven-buildable map) fails materialize: after the FULL
RE-IMPORT + `MAP REBUILD`, `MAP SAVE` never produces a file within the 600 s bound (run ~645 s).

- **Not the spike's lighting/viewport crash**: skipping `LIGHT APPLY` changes nothing — Bar wedges
  the save with lighting OFF too (both ~645 s).
- The spike's own harness builds Bar because it `MAP LOAD`s the prebuilt `.dx` (geometry already
  built); production re-imports the trunk (`MAP NEW` → `EDIT PASTE` 204 brushes → `MAP REBUILD`) and
  wedges at save. The live editor log shows the rebuild completing early (~1 min, Bar's 1620 nodes);
  the ~10 min is the save poll timing out.
### It is the recipe, not the environment — proven

- `06_hongkong_wanchai_garage` (clean, 201 brushes, 1004 surfs) via production re-import: the editor
  grinds `MAP REBUILD`, floods the log with `Warning: Node side limit reached`, freezes at ~849 log
  lines (log truncated mid-line), stays alive at ~20 % CPU, and never emits a save file. The CSG
  BSP explodes on the re-imported geometry. Deterministic — same freeze point every run, and with
  the whole machine to itself (no CPU contention).
- The spike harness (`ucc_materialize.py`, `MAP LOAD` of the prebuilt `.dx` + rebuild) built the
  SAME garage map in **34 s**, 1004 surfaces, in the SAME editor image and game assets. So the
  environment and the editor are fine; production's FULL RE-IMPORT recipe is the sole difference.
- A tiny level (`dxonly`, 1 brush) DID build and save (166 s) — failing only at post-verify (`Brush3
  MISSING from the built map`). So the save path itself works; the explosion is CSG-scale-dependent.
- Garage's trunk classes are all correctly qualified (`Engine.Brush`, `DeusEx.DeusExMover`, …), so
  the explosion is NOT the spike's "bare class carves" cause.

### Root cause of blocker 2 — CONFIRMED: `MAP SAVE` keystroke lost during a slow `MAP REBUILD`

Not a CSG explosion and not lighting. `driver.rebuild()` is fire-and-forget (`exec("MAP REBUILD")`,
0.3 s settle, return). On a retail-scale level the rebuild runs ~90 s+; `map_save` types `MAP SAVE`
**while the rebuild is still executing**, and the GUI editor drops that keystroke (quirks.md "a
reused editor loses the next MAP SAVE"). The rebuild finishes (`Log: BspOptGeom end` →
`Processed N T-points`), the editor sits IDLE at ~15 % CPU, and `map_save` polls its full 600 s for
a file that will never be written because the command never registered.

Proof: at the "stuck" point I issued `MAP SAVE` by hand to the same editor — a 674 KB `.dx` appeared
in seconds. The editor was never hung.

Why the controls behaved as they did:
- `dxonly` (1 brush) builds: its rebuild is instant, so `MAP SAVE` lands after it.
- Brush ENTRY is irrelevant: `EDIT PASTE` and `MAP IMPORTADD` both fail identically (both race the
  same slow rebuild).
- The spike builds because `UCC.exe ExecCommandlet` runs the script SYNCHRONOUSLY — each verb
  completes before the next — so there is no keystroke race. Production drives the GUI editor with
  async xdotool keystrokes.

### The fix, as shipped: batch the write drive into ONE `EXEC <file>`

Owner decisions (2026-08-23): (A) geometry gate → WARN, not refuse; (B) harden the GUI-editor drive.

The keystroke race is not fixed verb-by-verb (an early attempt waited for the editor log to go idle
after each slow verb; it closed the `MAP SAVE`-after-`MAP REBUILD` case but left the same race
between every other pair — `02_NYC_Bar` still shipped an EMPTY BSP because the `MAP REBUILD`
keystroke was lost behind a still-running `EDIT PASTE`). Instead the whole write-only drive is
submitted as one command file, the mechanism the `2026-07-18-exec-file-console-batch` spike proved:
`OBJ LOAD`s → `MAP NEW` → `MAP IMPORTADD` → `EDIT PASTE` → `MAP REBUILD` → `LIGHT APPLY` →
`MAP SAVE`, all in one `EXEC Z:\work\<uuid>.txt`. The engine runs the file through its OWN exec loop
(not the Command-box UI path), so no verb can drop the next verb's keystroke and it sails through the
GC "Cleaning up..." dialog. `Driver.begin_script` buffers each `exec`-routed verb; eager
side-effects (the ini `Paths` edit, the IMPORTADD source files, the paste clipboard) still run live
so the script's inputs exist before it runs; `run_script` submits the `EXEC` and awaits the `MAP
SAVE` .dx via the completion check factored out of `map_save` (`_await_written_file`).

Geometry gate: `validate_brush(planar_fatal=False)` returns the non-planar diagnostic instead of
raising; materialize warns and builds it. Coincident/degenerate stay fatal. Verify sync ceilings
(`dump_obj_dependencies` 20→180 s, `_read_loaded_classes` 90→180 s) raised for retail-scale walks.

Live-verified: `02_NYC_Bar` builds nodes 1620 / surfs 953 / zones 3, lit 758/953 — matching the
spike's MAP-LOAD ground truth (758/953). `06_HongKong_WanChai_Garage` builds lit 576/1083.

### Still open (tracked separately)

1. `materialize-verify-qualify-level-textures`: the post-verify's `qualify_level_textures` cannot
   match some retail brushes to their `OBJ DEPENDENCIES` block (garage `Brush126`, 24/202 blocks
   unclaimed), so the DEFAULT (verified) build of a real map still fails at verify though the build
   is correct. Plus the built map carries the editor's viewport `Camera`s, which the verify also
   objects to. Both block verified retail builds.
2. Lighting's Camera/save-fault (spike §1) is allocation-layout dependent; not observed on the maps
   built here, but untouched.

Harness: `$CLAUDE_JOB_DIR/tmp` — `scan_geometry.py` (the corpus geometry scan), `prod_one.sh` /
`prod_corpus.sh` (the shipped-CLI build sweep). Config: `~/.uedcli/config.toml` repointed at the
live install; `$UEDCLI_HOME` must sit under `/workspace` because the docker daemon here cannot
bind-mount `/home/agent` (the stub-cache mount).
