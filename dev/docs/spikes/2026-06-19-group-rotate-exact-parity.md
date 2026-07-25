# Spike: group-rotate EXACT trig parity + the GMath sine table (2026-06-19)

**Goal:** drive the residual of uedctl's rotation math against UED22 to ZERO and explain it, for a
HETEROGENEOUS multi-actor selection (brushes + several point-actor classes). Builds on, and
resolves the open residual from, the two existing rotation spikes:
[`2026-06-19-frotator-convention.md`](2026-06-19-frotator-convention.md) (per-actor matrix
convention) and [`2026-06-19-multiactor-rotate-groundtruth.md`](2026-06-19-multiactor-rotate-groundtruth.md)
(group orbit/compose; ~0.005uu float residual). Run live on an EPHEMERAL `uned-rotspike`
container (never `dx-lum-uned`).

## TL;DR (verified)

- **The editor's FRotator→world transform is driven by the GMath INTEGER SINE LOOKUP TABLE, not
  float trig.** Proven to ~1e-5uu (emit precision) on two fields; float-`math.sin` is ~0.07uu off.
  The table is `core.dll`'s `FGlobalMath` (exported `SinTab(int)`, `CosTab(int)`, `SinFloat`,
  `CosFloat`, global `GMath`). **Indexing is `idx = (field >> 2) & 16383` over a 16384-entry table,
  `TrigFLOAT[i] = sin(i·2π/16384)`** — i.e. the 16-bit FRotator field is right-shifted by 2
  (TRUNCATION, not rounding) to a 14-bit index. Both `sin` and `cos` use the SAME truncated index.
- **EXACT-match parameter:** for a stored field `F`, the editor's effective trig is
  `sin/cos(((F>>2)&16383)·2π/16384)`. Drive the offline matrix from THAT (table-driven), and a brush
  world corner matches the editor to ~1e-5uu (the table's float32 storage + the editor's 6-dp emit
  rounding — there is no larger residual floor). Float-sin at the full-precision angle
  `F/65536·360°` is wrong by up to ~0.074uu whenever `F` is not a multiple of 4.
- **The prior 0.005uu residual is a DIFFERENT cause** (not the table): that case used field −7080
  (a multiple of 4, so `>>2` loses nothing → table == float there). Its residual is the
  **mouse-drag free angle** — the editor orbited Location with the raw float mouse angle
  (−38.8903°) but stored `Rotation` as the rounded integer field −7080 (= −38.8916°). The orbit and
  the stored field disagree by the rounding, so a mouse drag can NEVER be byte-reproduced from the
  stored field alone. This is moot for uedctl (it computes Location AND Rotation from the same
  exact field).
- **The rule is uniform across actor types** — the group orbit applies one matrix to every actor's
  `Location` regardless of class, and the per-actor materialize transform routes through the same
  engine `GMath` for brushes and point actors. No per-type difference found. (Brush vs point
  orbit-of-Location is identical matvec; verified the brush per-actor transform here, point orbit in
  the prior spike.)
- **Gizmo (CORRECTED 2026-06-19):** the synthetic Ctrl+RMB actor-rotate **works with NO VNC** on
  the primed `dx-lum-uned` (all three axes, reproducing the groundtruth tables). The earlier
  "could not reproduce / needs a VNC prime" claim below was **WRONG** — see the correction in
  "Gizmo". The real cause of the ephemeral failure was boot floating windows covering the Top pane,
  not VNC. The end-to-end mixed-cluster group rotate was then captured directly (Task 3 of the
  follow-up verification).

## The sine table — extracted + verified

`dev/docs/unrealed/extracting-from-dll.md`: the math symbols are ASCII C++ export names (not wide
string literals), found in `core.dll`:

```
?SinTab@FGlobalMath@@QAEMH@Z     // float SinTab(int)  — M=float ret, H=int arg
?CosTab@FGlobalMath@@QAEMH@Z     // float CosTab(int)
?SinFloat@FGlobalMath@@QAEMM@Z   // float SinFloat(float)
?CosFloat@FGlobalMath@@QAEMM@Z
?GMath@@3VFGlobalMath@@A         // FGlobalMath GMath  (the global)
```

`Engine.dll` references the same `GMath`. The table is built in the `FGlobalMath` ctor at runtime
(no static-data string to dump), as the standard UE1 `TrigFLOAT[NUM_ANGLES]`, `NUM_ANGLES=16384`,
`ANGLE_SHIFT=2`. The **indexing/truncation** was pinned LIVE, not assumed.

### Live verification (DEINTERSECTION world-geometry readout)

Method = the frotator spike's capture (the materialize path's geometry): paste a `CSG_Subtract`
box carrying a `Rotation` field → `MAP REBUILD` (engine applies the field to the local PolyList →
world cavity) → big enclosing builder → `BRUSH FROM DEINTERSECTION` → `BRUSH EXPORT` = the world
geometry of a field-rotated brush. Box = 512(X)×64(Y)×64(Z) local at Location origin (long arm =
big signal). Two fields chosen to discriminate the trig model:

**`Yaw=16383`** (just under 90°): editor corner `(+31.901876, −256.012238)`.

| offline model | effective angle | corner | worst err vs editor |
|---|---|---|---|
| float-full `math.sin(16383/65536·2π)` | 89.99451° | (31.975456, −256.003067) | **0.0736uu** |
| **table `SinTab[(16383>>2)&16383]=idx 4095`** | 89.97803° | (31.901823, −256.012253) | **0.000053uu** ✅ |

**`Yaw=4095`** (discriminates TRUNCATE vs ROUND: trunc→idx 1023, round→idx 1024):

| offline model | idx | worst err vs editor |
|---|---|---|
| float-full | — | 0.0716uu |
| table ROUND (idx 1024) | 1024 | 0.086–0.095uu |
| **table TRUNCATE (idx 1023 = `4095>>2`)** | 1023 | **0.000005–0.000011uu** ✅ |

⇒ The editor uses `SinTab[(field >> 2) & 16383]` with **arithmetic-shift truncation**, 16384 entries,
`sin(idx·2π/16384)`; cos uses the same truncated idx (the `Yaw=4095` case mixes sin and cos
non-trivially and still matches to 1e-5). Verdict: **table-driven, not float.**

Reproduced against the production code path (`uedctl/rotation.py`) in
`_scratch/rotspike/compare_trig.py`:

```
Yaw=16383: production(float) worst err = 0.073580uu | table-driven worst err = 0.000053uu
Yaw=4095 : production(float) worst err = 0.071553uu | table-driven worst err = 0.000011uu
```

## Why the prior spike's 0.005uu floor is unrelated to the table

Prior yaw case: `LA (256,0,0)` → editor `(199.257538, −160.724960)`. Solving the exact angle from
the editor Location gives **−38.8903°** (field −7079.77); the editor STORED `Rotation` field
**−7080** (= −38.8916°). Field −7080 is `−1770·4`, so `>>2` is lossless ⇒ table == float for this
field. The 0.0044uu residual is purely `(−7079.77 vs −7080)`: the mouse drag orbited Location with
the raw float angle but quantized the stored field to an integer. **Two different precisions in one
op.** uedctl is immune: it derives a single integer field `F` from the user's angle, then orbits
Location AND stores `Rotation` from that same `F` (dispatch `actor rotate` does exactly this — one
`R = euler_to_matrix(uu_to_deg(delta_uu))`, one `compose_uu`).

## Heterogeneous selection (what was built)

Mixed set, all off the rotation axes so every actor moves on every axis drag (built offline via
`uedctl.builders.cube` + `emit`, `_scratch/rotspike/build_input.py`):

| actor | class | Location | note |
|---|---|---|---|
| CubeA | Brush | (256, 0, 0) | 64³ additive cube |
| CubeB | Brush | (0, 256, 0) | 64³ additive cube |
| LightA | Light | (0, 0, 256) | |
| LightB | Light | (256, 256, 0) | `Rotation=(Yaw=8192)` (tests compose) |
| PathA | PathNode | (128, 256, 0) | second point class — confirms type-agnostic |

Loaded type-correctly: **point actors (Light×2 + PathNode) via `MAP IMPORTADD`**, **brushes via
`EDIT PASTE`** (clipboard + paste, −32uu pre-shift) → `MAP REBUILD`. All five enter, and
**`ACTOR SELECT ALL` selects exactly those five as one group** (LevelInfo + the red builder brush
are excluded from `EDIT COPY`). **PrePivot:** the editor assigned PrePivot=0 to the pasted cubes
(none emitted), and uedctl's builders are PrePivot-free, so offline and editor agree trivially —
the `Location + R·(v − PrePivot)` transform reduces to `Location + R·v` here.

### Group moves as one unit (verified), uniform across types

`Ctrl+LMB` drag in the Top ortho moved ALL FIVE actors identically (e.g. +260 X on every
Location, brushes and points alike), reading back as one selection. This confirms the
heterogeneous selection is a single manipulable group and that Location translation is type-agnostic.

## Gizmo: synthetic Ctrl+RMB actor-rotate — CORRECTED (it works; VNC was a red herring)

> **CORRECTION 2026-06-19** (follow-up live verification): the conclusion in this section was WRONG.
> The synthetic Ctrl+RMB actor-rotate drives the gizmo fine with **NO VNC** on `dx-lum-uned`, on all
> three axes (yaw/pitch/roll), reproducing the groundtruth tables exactly (e.g. yaw drag LA
> `(256,0,0)`→`(244.632904,−75.438087)`, `Yaw=−3120`; LB field-add `8192→5072`). The end-to-end
> mixed-cluster group rotate was captured directly (worst Location err 4.6e-5uu, integer-exact
> Rotation fields, unchanged PolyLists).
>
> **The real cause of the ephemeral failure (diagnosed, not guessed):** in the fresh ephemeral
> editor, three **boot floating windows sat OVER the Top pane** — the Log Window, the Textures
> browser, and an `xmessage` dialog — so a drag at pane-centre (590,320) landed on a window and fell
> through to nothing. Proven both ways in ONE ephemeral container: strays present → selection
> unchanged (reproduces the failure); after `wmctrl`-ing them off-screen → the gizmo rotates
> perfectly. The window was already maximized to 1600×1158, so size was NOT the cause. The
> groundtruth spike succeeded because its recipe shoves the strays off-screen first.
>
> **Prerequisite for any synthetic gizmo work:** shove the Log Window / Textures browser / xmessage
> off-screen (`wmctrl -ir <id> -e 0,2000,2000,…`) BEFORE dragging — see `rendering.md` (the same
> stray-window cleanup the screenshot path needs). VNC is NOT required.

Original (now-corrected) write-up: in a FRESH ephemeral `uned-rotspike` the drag did NOT rotate at
pane-centre (590,320), dx=400, and the cause was *misattributed* to a missing VNC prime. (It was the
boot floats above.) Recorded for provenance.

## Recommendation for `actor rotate`

1. **uedctl is store-authoritative; the editor recomputes world geometry from the stored `Rotation`
   field at materialize.** So the brush's WORLD geometry the player sees always uses the editor's
   GMath table regardless of uedctl's offline trig — uedctl only needs to store the right integer
   field, which it does. **No table needed for materialize correctness.**
2. **For uedctl's OWN model-side world consumers** (`world_vertices`/`level_bounds`/`preview`/
   `poly`/`vertex list`), `rotation.py` currently uses full-precision float sin, which differs from
   what the editor will render by up to ~0.074uu for fields not a multiple of 4. This is a
   measurement/preview discrepancy, NOT stored-geometry corruption. **Recommendation: make
   `rotation.py`'s trig table-driven** (a tiny `gmath_sin(uu)=sin(((uu>>2)&16383)·2π/16384)`,
   `gmath_cos` likewise) so uedctl's previews/bounds match exactly what the editor will produce.
   Cheap, removes a class of "preview vs editor differs by a hair" confusion, and makes the
   integration round-trip test assert at ~1e-5 instead of needing a 0.1uu tolerance.
3. **Parity test tolerance:** with table-driven trig, compare at **1e-4uu** (covers float32 table
   storage + 6-dp emit). With float trig, any parity test must use **≥0.1uu**, which is loose enough
   to hide real sign/index bugs — another reason to go table-driven.
4. **Compose stays field-add** (unchanged from the multiactor spike; parity-first decision already
   in `rotation.compose_uu`). **Orbit stays matrix** (unchanged). The ONLY change is the trig
   source feeding `euler_to_matrix`.

Net: float trig is *adequate for stored correctness* (the editor re-derives), but a **UU-indexed
GMath sine table is required for bit-exact offline parity** of uedctl's own world-geometry readouts
and for a tight parity test. Recommend adopting the table.

## Reproduce

```bash
# offline input + comparison (host)
cd /home/human/src/dx_lum && .venv-uedctl/bin/python _scratch/rotspike/build_input.py
.venv-uedctl/bin/python _scratch/rotspike/compare_trig.py   # prints float vs table err

# live world-geometry readout (ephemeral editor)
cd Tools/uedctl/uned
docker compose run -d --name uned-rotspike \
  --entrypoint "/usr/bin/tini -- bash /repo/Tools/uedctl/uned/entrypoint.sh" \
  -v uned-wp-rotspike:/wineprefix uned          # image entrypoint path is stale → override
ex(){ docker exec uned-rotspike python3 /repo/Tools/uedctl/uned/wine_ctl.py "$@"; }
# poll status until alive=True AND window=...
ex exec "MAP NEW"; ex exec "MAP GRID X=1 Y=1 Z=1"
docker exec -i -e DISPLAY=:99 uned-rotspike xclip -selection clipboard -i < /repo/_scratch/rotspike/rotbox_paste.t3d
ex exec "EDIT PASTE"; ex exec "MAP REBUILD"
ex exec 'BRUSH IMPORT FILE=Z:\repo\_scratch\rotspike\builder_big.t3d'
ex exec "BRUSH FROM DEINTERSECTION"
ex exec 'BRUSH EXPORT FILE=Z:\repo\_scratch\rotspike\deint.t3d'   # world verts of the Yaw=16383 box
docker rm -f uned-rotspike; docker volume rm uned-wp-rotspike      # ALWAYS tear down
```

> NOTE: the committed `dx-lum-uned:latest` image (2 days old) bakes the OLD entrypoint path
> `/repo/Extra/AI/entrypoint.sh`; uedctl moved it to `/repo/Tools/uedctl/uned/entrypoint.sh`. Until
> the image is rebuilt, ephemeral `compose run` MUST override `--entrypoint` as above, or the
> container exits immediately. (Flag for the user — see below.)
