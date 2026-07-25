# Spike: UnrealEd MULTI-ACTOR group-rotate ground truth (2026-06-19)

**Goal:** capture how UED22 rotates a multi-actor selection via the mouse gizmo — pivot,
Location orbit, and Rotation compose — the ground truth for uedctl's planned `actor rotate`
verb. Driven live on `dx-lum-uned` (UED22 under wine), measured from `EDIT COPY` T3D. This
closes the gap left open by [`2026-06-19-frotator-convention.md`](2026-06-19-frotator-convention.md)
("the GROUP-rotate semantics are NOT verified against the editor").

## TL;DR (verified)

- **The gizmo IS drivable headless** via `wine_ctl drag … --modifier ctrl --button 3` (Ctrl+RMB)
  aimed at an embedded ortho pane — the earlier "driving the gizmo headless failed" note is
  **superseded**. The previous failure was wrong coords / a floating window obscuring the pane,
  not an intrinsic limitation.
- **Pivot = the GRID ORIGIN `(0,0,0)`** for console-driven selections (NOT the selection bbox
  centre, centroid, or any actor). Verified to ~0.003uu with all actors off-origin. (Caveat: the
  editor rotates about its *pivot widget*; console `ACTOR SELECT…` leaves the widget at origin. A
  GUI click-select would place the widget on the selection — see "Pivot caveat".)
- **Location orbit = `pivot + R·(Location − pivot)`** using the **verified per-actor matrices**
  (yaw = textbook `Rz`; pitch `Ry` and roll `Rx` with sin sign FLIPPED). Confirmed to ~0.005uu on
  all three axes (yaw/pitch/roll), each captured from the corresponding ortho pane.
- **Rotation compose = naive per-component FRotator ADDITION**, NOT matrix composition.
  A single-axis ortho drag adds its delta into exactly ONE FRotator field
  (`new.Pitch = old.Pitch + Δpitch`, etc.) and leaves the other two untouched. Verified across
  5 compose cases including two-field existing rotations.
  **This DIVERGES from uedctl's planned matrix `compose_uu`** whenever the existing rotation has
  a field that doesn't commute with the delta axis — see "Compose divergence" and the plan
  reconciliation below.
- **`MAP ROTGRID` does NOT snap the synthetic gizmo drag** — angles come out free (e.g. a
  dx=400 drag → 17.14°, dx=900 → 38.89°), regardless of `ROTGRID PITCH/YAW/ROLL=16384`. The
  derivation doesn't need a round angle; it solves the matrix from whatever angle landed.

## Setup

```
MAP NEW; MAP GRID X=1 Y=1 Z=1; MAP ROTGRID PITCH=16384 YAW=16384 ROLL=16384
MAP IMPORTADD FILE=Z:\repo\Temp\spike_multi.t3d      # wine Z: = host /, so /repo → Z:\repo
ACTOR SELECT OFCLASS CLASS=Light                     # 3 Lights only (drops the builder brush)
```

`/repo/Temp/spike_multi.t3d` = 3 Lights: `LA (256,0,0)`, `LB (0,256,0) Rotation=(Yaw=8192)`,
`LC (0,0,128)`. (Selecting `OFCLASS Light` rather than `SELECT ALL` keeps the red builder
brush out of the selection so the readout is clean.)

**Important path gotcha:** wine's `Z:` maps to host `/`, NOT to `/repo`. The correct import
path is `Z:\repo\Temp\spike_multi.t3d`; `Z:\Temp\…` silently resolves to nothing and IMPORTADD
no-ops (matches `driver.to_z_path`). This bit the first attempt.

### Driving the gizmo (the binding that worked)

`docker exec dx-lum-uned python3 /repo/Tools/uedctl/uned/wine_ctl.py drag <x> <y> <dx> <dy> --modifier ctrl --button 3 --steps 40`

- `--modifier ctrl --button 3` = **Ctrl+RMB = actor-rotate** (plain RMB = camera rotate).
- `<x> <y>` are MAIN-window-relative; aim at the centre of the ortho pane whose perpendicular
  axis you want to rotate about. **The rotate axis is the one perpendicular to the dragged
  ortho**, and only a HORIZONTAL drag rotates (a vertical drag in an ortho does nothing).
- The paced relative-motion drag (per the drag-sensitivity findings) is required; this is the
  same `drag` verb that spec added.

**Pane centres** (main window 1600×1158 at root (0,38); standard 4-pane layout):

| pane (window-rel centre) | dragging horizontally rotates | observed delta field |
|---|---|---|
| **Top (XY)** ≈ (590, 320) | about **Z** | `Yaw` |
| **Front (XZ)** ≈ (1330, 320) | about **Y** | `Pitch` |
| **Side (YZ)** ≈ (1330, 855) | about **X** | `Roll` |
| Perspective ("Dynamic Light") = bottom-left | — | not used |

A **floating `<?int?WinDrv.General.ViewXY?>` top-level window** (512×512 at root ~(4,42))
overlaps the embedded Top pane and the Front quadrant paints black on boot. Shove the stray
windows off-screen first: `wmctrl -ir <id> -e 0,2000,2000,512,512` for the `ViewXY` float and
the Log Window. After that all four embedded panes are clickable. (Sign: a `wine_ctl shot` of
the main window shows the labelled panes — see `_scratch/multirotate_layout2.png`, gitignored.)

## Evidence — raw `EDIT COPY` captures

All deltas are the *field value the editor wrote into the dragged axis*; `θ = delta/65536·360°`.

### Yaw (Top XY pane, dx=900 → Yaw delta −7080 = −38.89°)

| actor | before (X,Y,Z) | after (editor) | predicted `pivot+Rz·(p−pivot)`, pivot=origin |
|---|---|---|---|
| LA | (256,0,0) | (199.257538, −160.724960, 0) | (199.254, −160.729, 0) |
| LB | (0,256,0) | (160.724960, 199.257538, 0) | (160.729, 199.254, 0) |
| LC | (0,0,128) | (0, 0, 128) — unchanged | (0,0,128) — on the pivot axis |
| LB Rotation | Yaw=8192 | **Yaw=1112** | 8192 + (−7080) = 1112 |

### Pitch (Front XZ pane, dx=400 → Pitch delta −3120 = −17.14°)

| actor | before | after (editor) | predicted (verified flipped-sin `Ry`), pivot=origin |
|---|---|---|---|
| LA | (256,0,0) | (244.632904, 0, −75.438087) | (244.632, 0, −75.439) |
| LC | (0,0,128) | (37.719044, 0, 122.316452) | (37.720, 0, 122.316) |
| LB | (0,256,0) | unchanged (on pitch axis) | (0,256,0) |
| LB Rotation | Yaw=8192 | **(Pitch=−3120, Yaw=8192)** | field-add: Pitch 0→−3120 |

### Roll (Side YZ pane, dx=400 → Roll delta −3120 = −17.14°)

| actor | before | after (editor) | predicted (verified flipped-sin `Rx`), pivot=origin |
|---|---|---|---|
| LA | (256,0,0) | unchanged (on roll axis) | (256,0,0) |
| LB | (0,256,0) | (0, 244.632904, 75.438087) | (0, 244.632, 75.439) |
| LC | (0,0,128) | (0, −37.719044, 122.316452) | (0, −37.720, 122.316) |
| LB Rotation | Yaw=8192 | **(Yaw=8192, Roll=−3120)** | field-add: Roll 0→−3120 |

Predictions match the editor to ≈0.005uu on every actor and axis. ⇒ **group orbit uses the
SAME per-actor matrices verified in the FRotator spike, about the grid origin.**

> **The ≈0.005uu floor is EXPLAINED and removable** — see
> [`2026-06-19-group-rotate-exact-parity.md`](2026-06-19-group-rotate-exact-parity.md). The editor's
> trig is the **GMath integer sine table** (`SinTab[(field>>2)&16383]`, 16384 entries), not float
> `math.sin`. Here the fields are multiples of 4 (lossless `>>2`), so table == float and the residual
> is instead the **mouse-drag free angle vs the rounded integer field stored** (the orbit used the
> raw float angle, the field is its integer round). uedctl avoids this by deriving Location AND
> Rotation from one integer field; a table-driven matrix then matches the editor to ~1e-5uu.

## Pivot — it's the grid origin, decisively

To rule out "origin happened to be the bbox/centroid", a 2-Light set with NEITHER actor on any
axis through origin (`LA (512,256,0)`, `LB (256,512,0)`; bbox centre (384,384), centroid (384,384))
was yaw-dragged (dx=400 → Yaw −3120 = −17.14°):

| candidate pivot | max position error vs editor |
|---|---|
| **origin (0,0)** | **0.003uu** ✅ |
| bbox centre / centroid (384,384) | 161.8uu |
| LA (512,256) | 170.6uu |
| LB (256,512) | 170.6uu |

Editor after: `LA → (564.703796, 93.756660)`, `LB → (395.509186, 413.827698)`; both match the
rigid orbit about (0,0,0). **Pivot = grid origin.**

### Pivot caveat (scope of the origin claim)

The editor rotates about its **pivot widget**, not a hardcoded origin. Console `ACTOR SELECT
ALL` / `OFCLASS` / `SELECTNAME` all leave the widget at origin (reproduced: re-selecting via
single-`SELECTNAME`-then-`OFCLASS` gave the identical origin-pivot result). A human GUI
click-select would drop the widget on the clicked actor / selection, moving the pivot. So
"pivot = origin" is the measured behavior **for console-driven selection** (the only path
relevant headless). It is moot for uedctl anyway: uedctl defines its OWN pivot (best-grid
vertex, a design choice) and need not match the editor's widget.

## Compose — per-component FRotator ADDITION, not matrix compose

The Rotation compose is the one place the editor surprises. Five cases, all consistent with
**field-wise addition** `new = old + delta` (delta confined to the dragged axis's field):

| existing (P,Y,R) | delta (P,Y,R) | editor wrote | field-add prediction |
|---|---|---|---|
| (0, 8192, 0) | (0, −7080, 0) | (0, 1112, 0) | (0, 1112, 0) ✅ |
| (0, 8192, 0) | (−3120, 0, 0) | (−3120, 8192, 0) | (−3120, 8192, 0) ✅ |
| (0, 8192, 0) | (0, 0, −3120) | (0, 8192, −3120) | (0, 8192, −3120) ✅ |
| (4096, 8192, 0) | (0, 0, −3120) | (4096, 8192, −3120) | (4096, 8192, −3120) ✅ |
| (4096, 0, 0) | (0, −3120, 0) | (4096, −3120, 0) | (4096, −3120, 0) ✅ |

It is NOT a single matrix product. Compared against the verified `Rz·Ry·Rx` convention, the
field-add result coincides with **`R_existing · R_delta` (local/right)** for a *roll* delta and
with **`R_delta · R_existing` (world/left)** for a *yaw-onto-pitch* delta — i.e. it matches
neither product consistently. The decisive case is **yaw delta onto an existing `Pitch=4096`**:
the editor wrote `(Pitch=4096, Yaw=−3120)`, whose matrix equals `R_delta · R_existing` and
**differs** from local `R_existing · R_delta`:

```
editor field-add (4096,-3120,0): +0.883 +0.295 -0.366 ; -0.272 +0.956 +0.113 ; +0.383 0 +0.924
matrix R_e·R_d (local)         : +0.883 +0.272 -0.383 ; -0.295 +0.956 0      ; +0.366 +0.113 +0.924   ← DIFFERS
matrix R_d·R_e (world)         : +0.883 +0.295 -0.366 ; -0.272 +0.956 +0.113 ; +0.383 0 +0.924         ← == editor here
```

Mechanism: this is the classic UnrealEd `FRotator += FRotator` componentwise add. It happens
to equal a matrix product only when the existing rotation lives entirely in field slots that
commute with the delta in the `Rz·Ry·Rx` nesting (e.g. a Roll delta is innermost, so adding it
is exactly right-multiply by `Rx`; a Yaw delta is outermost, so adding it is exactly
left-multiply by `Rz`). For a general 2+-field existing rotation, field-add is its own thing and
suffers gimbal coupling. (Location, by contrast, is a *proper* rigid orbit — the editor is
matrix-correct for positions, Euler-naive for orientations.)

## Reconciliation with uedctl's plan

- **Location orbit — adopt as planned.** `pivot + R·(Location − pivot)` with the verified
  matrices is exactly what the editor does (modulo pivot choice, which uedctl owns). No change.
- **Rotation compose — DECISION NEEDED.** uedctl's plan composes via matrix (`compose_uu`,
  matrix-correct). The editor does **Euler field-addition**, which is *not* matrix-correct and
  differs for multi-field existing rotations. Two honest options:
  1. **Match the editor (byte parity):** compose by per-component FRotator addition. Bit-identical
     to a mouse group-rotate, but inherits UnrealEd's gimbal coupling (rotating a tilted actor by
     yaw does not spin it about world-Z).
  2. **Stay matrix-correct (uedctl's plan):** `compose_uu` matrix product. Geometrically "more
     correct", diverges from the editor for tilted actors, but uedctl already defines its own
     pivot and is store-authoritative (the editor is only a build target), so it isn't bound to
     byte-match the mouse path. The per-actor *world geometry* on materialize is still governed by
     the verified per-actor matrix regardless of which FRotator we store, so either choice
     round-trips through `MAP IMPORTADD`/export.

  Recommendation: **field-addition for the common axis-aligned case is identical to matrix**, so
  for the overwhelmingly common "rotate upright actors about one axis" the two agree. Reach for a
  decision only if uedctl must rotate already-tilted actors. Document the divergence in
  `actor rotate` and pick matrix-correct (option 2) unless explicit editor byte-parity is a
  requirement — it's the safer default and matches the rest of the store-centric design (the
  editor isn't the source of truth).

## What changed vs the FRotator spike

That spike said group-rotate "could NOT be captured headless" and left pivot/orbit/compose open.
This spike captured all three: the gizmo IS drivable (`drag --modifier ctrl`), orbit uses the
spike's verified matrices, pivot is the grid origin (console selection), and **compose is Euler
field-addition, not matrix** — the one genuine surprise, flagged for the plan. The per-actor
matrix conclusions in the FRotator spike are unchanged and corroborated (the group orbit is
literally those matrices applied per actor).

## Reproduce

```bash
ct=dx-lum-uned
ex(){ docker exec $ct python3 /repo/Tools/uedctl/uned/wine_ctl.py "$@"; }
ex exec "MAP NEW"; ex exec "MAP GRID X=1 Y=1 Z=1"
ex exec 'MAP IMPORTADD FILE=Z:\repo\Temp\spike_multi.t3d'
ex exec 'ACTOR SELECT OFCLASS CLASS=Light'
# move stray windows off-screen (ids from `wmctrl -l`): ViewXY float + Log Window
ex drag 590 320 400 0 --modifier ctrl --button 3 --steps 40   # yaw  (Top XY pane)
# ex drag 1330 320 400 0 --modifier ctrl --button 3 --steps 40 # pitch (Front XZ pane)
# ex drag 1330 855 400 0 --modifier ctrl --button 3 --steps 40 # roll  (Side YZ pane)
ex edit-copy
```
