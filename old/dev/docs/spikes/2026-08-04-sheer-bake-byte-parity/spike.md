# Spike: sheer bake byte-parity for complex brushes & every SheerAxis (2026-08-04)

**Question.** Does uedcli's offline sheer bake (`transform.bake`) + FScale emission (`transform.emit_fscale`)
reproduce the real editor's `ACTOR APPLYTRANSFORM` + `MAP EXPORT` for COMPLEX multi-poly brushes and
every `SheerAxis` — not just the single cube already covered? The scale work flagged the gap: the
combined scale+sheer matrix ORDER (`Sheer·Scale`) was validated only for the cube differential.

## Status: STILL BLOCKED — but NOT by the resource cap. The sheer question stays OPEN.

The resource cap the first run blamed is gone: a fresh ephemeral container now reports
`pids.max=2048`, `mem.max=16 GiB` (was 512 / 6 GiB). The full live run
(`harness.py --container …`, 2026-08-05) was re-attempted anyway and **all 27 cases errored** —
`parity=ERROR emit=ERROR` on every case. **No parity numbers were produced and none are fabricated.**

The crash is a GUI GPF, not a resource cap and not a sheer-bake defect. At the first driven console
command the editor pops a `Critical Error` dialog (captured live, `evidence/gpf-syntaxhighlighting.png`):

```
General protection fault!
History: SyntaxHighlighting::AddQuote <- SyntaxHighlighting::Setup <- WCodeFrame::OnCreate <- WM_CREATE
```

pids at the crash were **157 / 2048** — nowhere near a cap (`evidence/live-caps-and-gpf.txt`). So the
first run's "hit the 512 PID cap on `MAP NEW`" diagnosis was **wrong**: lifting the cap changed
nothing. `WCodeFrame` is UnrealEd's syntax-highlighted code/log window; the fault is in its creation.

Relaunching the editor **without `-log`** (no Log Window) reproduces the *identical* GPF, so the code
frame is built at startup regardless. This is the same fault already filed in
`board/inbox/dx-lum-uned-image-missing-rendering-md-editor` — the shipped `dx-lum-uned` image GPFs in
`SyntaxHighlighting`/`WCodeFrame` on any window-creating op under this arm64/qemu/wine/Mesa host. The
documented ini fixes are untested against it and "may be deeper than the ini fixes reach".

The harness itself is sound: it builds + bakes all 27 cases offline with no error
(`harness.py --offline`). It will produce the parity table only once the image's GUI GPF is fixed
(rebuild per `unrealed/rendering.md`) — or the harness is reworked onto the headless
`Editor.ExecCommandlet` path (no GUI, no `WCodeFrame`), the path that already yields byte-exact
texture parity. **Whether uedcli's sheer bake matches the editor for complex brushes remains
unanswered.**

## What was built (ready to run once the image's GUI GPF is fixed)

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
- `evidence/gpf-syntaxhighlighting.png` — the live `SyntaxHighlighting`/`WCodeFrame` GPF dialog (2026-08-05).
- `evidence/live-caps-and-gpf.txt` — the lifted caps (2048 PIDs / 16 GiB) + 157/2048 pids at the crash.
- `evidence/env-blocked.txt` — the first run's (wrong) PID-cap snapshot, kept for the record.
