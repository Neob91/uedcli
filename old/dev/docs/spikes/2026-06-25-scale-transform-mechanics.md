# Scale / sheer / apply-transform mechanics (MainScale, PostScale, FScale)

**Date:** 2026-06-25
**Method:** live probes in `uned-spike1` (UED22 under wine) — author brushes with known
`MainScale`/`PostScale`/`Rotation`/`PrePivot`, `MAP IMPORTADD`, optionally `ACTOR APPLYTRANSFORM`,
read back via `MAP EXPORT` — PLUS static disassembly of `core.dll` (`capstone`+`pefile`,
`_scratch/bspspike` harness) for the sheer coefficient.
**Confidence:** ✅ live-verified (every coordinate is a `MAP EXPORT` readback) · 🔬 disassembled
(constants/branches read from the compiled code). Extends
[`2026-06-25-mainscale-postscale-applytransform.md`](2026-06-25-mainscale-postscale-applytransform.md)
(which established MainScale=local/pre-rotation, PostScale=world/post-rotation,
`world = Location + PostScale·R·MainScale·(v − PrePivot)`, and that `APPLYTRANSFORM` bakes all three).

This is the substrate uedcli's **scale support** needs (preview/bounds, clip/vertex-move inverse,
the offline `apply-transform`). It removes ALL gating unknowns the scale design flagged.

---

## 1. Scale-field emission format (H3-critical) ✅

Imported brushes with known scale and `MAP EXPORT`'d immediately (no transform). The editor's exact
serialization — uedcli must reproduce it byte-for-byte or H3 post-verify fails on every
authored-scale brush:

```
<Field>=( [Scale=( [X=<v>][,Y=<v>][,Z=<v>] ),] [SheerRate=<r>,] SheerAxis=<AXIS> )
```
- A `Scale` axis is written **iff ≠ 1.0** (identity components dropped; negatives ARE written, e.g.
  `Scale=(X=-1.000000)`). The whole `Scale=(...)` is omitted if all three are 1.0.
- `SheerRate=` written **iff ≠ 0.0**.
- `SheerAxis=` is **always** present (default `SHEER_ZX`). 6-dp throughout.

Evidence: `2,2,2`→`Scale=(X=2.000000,Y=2.000000,Z=2.000000)`; `2,1,1`→`Scale=(X=2.000000)`;
identity→`(SheerAxis=SHEER_ZX)` (matches uedcli's current default emit); mirror→`Scale=(X=-1.000000)`;
combined `2,0.5,1`+rate0.3+`SHEER_YZ`→`Scale=(X=2.000000,Y=0.500000),SheerRate=0.300000,SheerAxis=SHEER_YZ`.

## 2. `ACTOR APPLYTRANSFORM` bake formula ✅

For the full transform `T = PostScale·R·MainScale`, the bake is:
```
v'        = T · v
PrePivot' = T · PrePivot        (transformed, NOT zeroed)
Location' = Location            (UNCHANGED)
MainScale, Rotation, PostScale  → identity
```
Derivation: `world = Location + T·(v − PrePivot) = Location + T·v − T·PrePivot`, rewritten as
`Location + I·(v' − PrePivot')`. Verified live two ways:
- scale-only: `Location=(100)`, `PrePivot=(64)`, `MainScale=2` → baked verts ×2, `PrePivot=128`
  (=2·64), Location kept; world position preserved.
- rotation+PrePivot: `Location=(100)`, `PrePivot=(64)`, `Rotation=Yaw=90°` → verts `=R·v` (X/Y
  extents swap), `PrePivot=(≈0,64)=R·(64,0,0)`, Location kept (float residue ~6e-6 from the GMath
  table, within `CLEAN_EPS`).

Because the bake **rewrites `PrePivot`** (its explicit intent), it must NOT be applied to a `Mover`
implicitly (PrePivot = swing axis, D8).

## 3. Sheer — axis semantics ✅ + the exact coefficient law 🔬

**Axis rule (live, all pairs):** `SheerAxis=SHEER_AB` shears **axis B by axis A**: `B_new = B + k·A`,
all other axes unchanged; one off-diagonal term. (SHEER_XY→Y by X; SHEER_ZX→X by Z; SHEER_YZ→Z by Y;
SHEER_XZ→Z by X.)

**Coefficient `k = f(SheerRate)` — exact closed form, disassembled and validated.** In `core.dll`,
`FCoords::operator*(FScale)` (export `??KFCoords@@QBE?AV0@ABVFScale@@@Z`, RVA 0x17a50) → worker
0x18bb0: it divides the coords axes by `Scale` (clean per-axis, no quantization), then derives the
sheer coefficient from **`0x1001e7c0(SheerRate)`** and writes `−coeff` into the off-diagonal selected
by a 6-way `SheerAxis` jump table. `0x1001e7c0` is a pure piecewise function (antisymmetric in
`r = SheerRate`):
```
f(r) = 0                       if |r| <= 0.05            (deadzone)
     = sign(r) * (|r| - 0.05)  if 0.05 < |r| <= 0.55
     = sign(r) * 0.5           if 0.55 < |r| <= 0.65     (snap-to-0.5 band)
     = sign(r) * (|r| - 0.15)  if |r| > 0.65
```
(`.rdata` constants ±0.05, ±0.55, ±0.5, ±0.65, ±0.15; deadzone returns `fldz`.) It's a deliberate
**GUI snap** (deadzone + a snap-to-0.5 notch), and it lives in the coords math, so it applies to
**both rendering and APPLYTRANSFORM** — i.e. it is the *effective* sheer.

**Validated against a 20-point live scan** (SHEER_XY, cube X half-extent 1024, APPLYTRANSFORM,
`k=(newY−32)/1024`) — exact match at every point, including the plateau:

| rate | .05 | .10 | .50 | .55 | .60 | .65 | .70 | 1.0 | 2.0 |
|---|---|---|---|---|---|---|---|---|---|
| k=f(rate) | .00 | .05 | .45 | .50 | **.50** | **.50** | .55 | .85 | 1.85 |

(The `.55–.65 → .50` plateau is the snap-to-0.5 band. The plateau was re-confirmed with 3s sleeps +
import-verification, so it's genuine editor behavior, not a stale export.)

**Consequence for uedcli:** offline sheer = apply `f(SheerRate)` for the coefficient, place per
`SHEER_AB ⇒ B += k·A`. **No lookup table needed** — exact editor parity by construction. Validate the
exact sign/off-diagonal placement against the differential harness.

## 4. Mirror, mover, rotate-distortion ✅

- **Mirror** = a negative scale axis (`Scale=(X=-1)`); no separate verb needed. The bake reverses
  polygon winding when `det(T) < 0` (odd # of −1 axes) → CSG-valid; `det` must include the shear term.
  **Confirmed from code** 🔬: `FPoly::Transform(coords, preSub, postAdd, FLOAT Orientation)`
  (Engine.dll RVA 0x152360) transforms the verts, then `if Orientation < 0` runs a loop swapping
  vertex `[i] ↔ [N−1−i]` (vertex-order reversal). The caller passes the transform determinant sign as
  `Orientation`. (Live test D corroborates: a mirror bakes to a brush that survives `MAP REBUILD`.)
- **Mover + scale:** importing a `Mover` with `MainScale` keeps it as a FIELD (brush verts local,
  `KeyPos` preserved) — scaling a mover's brush is benign; travel (`KeyPos`/`KeyRot`, world units) is
  independent of brush scale. `APPLYTRANSFORM` on a mover bakes the geometry but **leaves `KeyPos`** →
  geometry scales, animation travel doesn't (a desync). So: allow `actor scale` on a mover (warn
  travel won't scale); reject/defer `apply-transform` on a mover.
- **Rotate distorts a non-uniform-`PostScale` brush** (confirmed): `PostScale·R·PostScale⁻¹` is a
  non-uniform-scale-conjugated rotation = rotation + shear. Live: cube + `PostScale X=2` + 45° yaw,
  APPLYTRANSFORM → corner distances 81.6 & 137.6 (unequal = sheared parallelogram); the same with
  `MainScale X=2` → all corners 131.9 (rigid rectangle). `MainScale` (pre-rotation) and uniform
  `PostScale` rotate cleanly. Inherent UE1 behavior (the engine's transform order), so UnrealEd's own
  rotate gizmo distorts identically — silently.

## 5. Net for the scale design

Every gating unknown the scale `to-spec` item listed is resolved: emission rules (§1), bake formula
incl. PrePivot/Location (§2), sheer axis + exact closed form (§3), mover handling and rotate-distortion
(§4). The design can be specced with no remaining live unknowns; the only implementation care is
matching the editor's emit omission rules and the sheer snap exactly (both pinned here), validated by
the differential parity harness.
