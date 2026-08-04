# Spike: sheer bake byte-parity for complex brushes & every SheerAxis (2026-08-04)

**Question.** Does uedcli's offline sheer bake (`transform.bake`) + FScale emission (`transform.emit_fscale`)
reproduce the real editor's `ACTOR APPLYTRANSFORM` + `MAP EXPORT` for COMPLEX multi-poly brushes and
every `SheerAxis` — not just the single cube already covered? The scale work flagged the gap: the
combined scale+sheer matrix ORDER (`Sheer·Scale`) was validated only for the cube differential.

## Status: ENV-BLOCKED — could not boot-and-drive a live editor on this box.

The editor image (`dx-lum-uned`) **boots** (window resolves, `wine_ctl status` answers) but **GPFs on
the first driven console command, `MAP NEW`**, before any geometry is imported — so the crash is
environmental, not a sheer-bake defect. Three fresh ephemeral containers, same result. **No parity
numbers were produced and none are fabricated.**

### Evidence (`evidence/env-blocked.txt`)

At the crash on a fresh container:
```
pids.current=480  pids.max=512        # hit the 512 PID cap during MAP NEW's GC thread spawn
mem.current=4.42 GiB  mem.max=6.0 GiB
memory.events: max=70752 oom=0 oom_kill=0   # heavy reclaim, NO oom-kill (pressure, not OOM)
host MemAvailable=43.6 GiB            # host is fine; the caps are the rootless-VM slice's
```
- Open X windows at the crash: `Critical Error` (UnrealEd GPF dialog) + a stuck `xmessage` (the GC
  "Cleaning up" modal). `Editor.log` frozen at the OpenGL boot banner — no console command ever
  produced output.
- Repeated `docker exec` failures during the run: `fork/exec … resource temporarily unavailable`
  (EAGAIN — the 512 PID cap left no room to fork the exec'd process). Idle-after-boot the editor
  already sits at ~450/512 PIDs; `MAP NEW`'s garbage-collection thread spawn tips it over.

### Caps are unraisable from here

Same class of blocker as `spikes/2026-08-04-deusex-boot-wedge` (that one is the *game* wedging at
boot; this is the *editor* GPFing on first command — both are rootless-VM resource caps):
- A compose `pids_limit: 16384` override was **ignored** — `pids.max` stayed 512.
- `docker info` reports `Cgroup Driver: none`, rootless; `--memory`/`--pids-limit` write no cgroup
  limit (the 6 GiB / 512-PID caps come from a parent slice in the rootless daemon VM, unreachable).

The harness is sound: it builds + bakes all 27 cases offline with no error (`harness.py --offline`).
Given headroom (a lower-pressure moment, as the box had on 2026-08-03), the same invocation drives the
editor and prints the parity table.

## What was built (ready to run when the box has headroom)

- `harness.py` — spins the corpus through a named editor container, per case checking (a) world-vertex
  parity `transform.bake` vs editor `ACTOR APPLYTRANSFORM` (worst |Δ| ≤ 1e-4, same corner count) and
  (b) `emit_fscale` substring byte-match in the editor's un-baked re-export. `--offline` builds+bakes
  only. `--container <name>` drives live. `--only a,b` selects cases.
- The corpus is defined ONCE in `uedcli/tests/test_scale_integration.py` (`_CASES`) and imported by the
  harness, so the runnable spike and the committed regression can never drift.

### Corpus (27 cases; the 8 cube cases pre-existed, 19 new)

- **All six SheerAxis pairs** (`SHEER_XY/XZ/YX/YZ/ZX/ZY`, rate 0.3 → `sheer_coeff` k=0.25) on a
  **16-gon cylinder** (`cyl_*`) and a **6-step staircase** (`stair_*`) — the shapes with the most
  non-axis-aligned faces, the ones a bad matrix/order would break.
- **sheer × non-uniform Scale** (`cyl_sheer_scale` Scale=(2,3,1)+SHEER_XY; `stair_sheer_scale`
  (2,3,1)+SHEER_YZ) — the `Sheer·Scale` ORDER test, the specific gap flagged.
- **sheer × yaw** (`cyl_sheer_yaw`), **sheer × PrePivot** (`cyl_sheer_prepivot`), **PostScale-sheer**
  vs MainScale-sheer (`cyl_sheer_post`).
- **`sheer_coeff` snap boundaries**: deadzone |r|≤0.05 → k=0 (`cyl_sheer_deadzone`, kept a real
  transform via Scale=(2,1,1)) and the ~0.6 notch → k=0.5 (`cyl_sheer_notch`).

## Regression pin

`test_scale_integration.py` (`-m integration`, deselected by default) now parametrizes both
`test_offline_bake_matches_editor_applytransform` and `test_emission_byte_matches_editor_reexport`
over all 27 cases (54 tests collect). They assert bake-vs-editor parity ≤1e-4 and `emit_fscale`
byte-match, so a future `fscale_matrix` order/axis regression trips red the next time the suite runs
against a live editor.

## Files

- `harness.py` — the runnable corpus driver (offline + live modes).
- `evidence/env-blocked.txt` — the crash-state cgroup/PID/memory snapshot.
