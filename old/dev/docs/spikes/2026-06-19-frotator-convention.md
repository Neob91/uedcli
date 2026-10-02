# Spike: UnrealEd FRotator convention for `actor rotate` (2026-06-19)

**Goal:** pin UE1/UED22's exact FRotator behavior so uedcli's `actor rotate` matches the editor
(parity-first). Run live on `dx-lum-uned` (UED22 under wine). Method: drive the editor, capture
geometry, derive the convention from observed coordinates — no assumptions.

## TL;DR (verified)

- **Rotation is stored in the actor `Rotation` field; the brush `PolyList` stays LOCAL** (verts
  unchanged). Confirmed by `BRUSH ROTATETO` → `BRUSH ADD` → `MAP EXPORT` (exported
  `Rotation=(Yaw=…)` with the box verts still at their local `±128/±32`). This is the "UnrealEd
  way" the design chose — **confirmed correct**.
- **The `Rotation` field unit is the standard `2^16` (65536 = 360°): `16384 = 90°`.** Round-trips
  faithfully through `MAP IMPORTADD`/`MAP EXPORT`, and values **normalize mod 65536** (an imported
  `Yaw=4194304 = 64·65536` re-exported as `0`). So uedcli's `deg_to_uu`/`uu_to_deg` at **65536 is
  correct** — the original plan was right.
- **`BRUSH ROTATETO`'s *input* is ×256 vs the field** (`ROTATETO YAW=16384` stores
  `Yaw=4194304`; to get a 90° field value you'd pass `YAW=64`). This is a console-input quirk of
  `ROTATETO` only — **uedcli never uses `ROTATETO`** (it writes the field directly), so it's a
  non-issue, recorded to avoid confusion.
- **The rotation matrices (axis + sign), corner-tracked from captured world geometry:**
  - **Yaw (about Z):** `(x,y) → (-y, x)` — matches the standard `Rz` **unchanged**.
  - **Pitch (about Y):** `(x,z) → (-z, x)` — the **OPPOSITE sign** to the textbook `Ry`.
  - **Roll (about X):** `(y,z) → (z, -y)` — the **OPPOSITE sign** to the textbook `Rx`.
  - **Compose order:** `R = Rz(yaw) · Ry(pitch) · Rx(roll)` (a point is rolled, then pitched, then
    yawed) — confirmed by a combined `Pitch=16384,Yaw=16384` capture (all 8 corners matched
    `yaw∘pitch`). Order matches the plan.
- **Net plan correction:** the compose order, the unit, and yaw were right; **pitch and roll need
  their sin-sign flipped** (`_ry` and `_rx`). See "Corrected matrices".

## Method (what worked, what didn't)

- **`BRUSH EXPORT` does NOT bake rotation** — it always emits the builder's untransformed local
  PolyList. **`BRUSH APPLYTRANSFORM` is a no-op** in this build (an earlier "no change" was a red
  herring: `ROTATETO YAW=16384` → field `4194304` = 64 turns = 0° net, so there was nothing to
  bake). Neither can read world geometry.
- **`MAP IMPORTADD` of a `CSG_Subtract` brush does NOT carve** (the known IMPORTADD-brush quirk:
  no `Bound`, not CSG-active). The capture failed (empty).
- **What works — paste-carve + CSG capture:** `EDIT PASTE` a `CSG_Subtract` box that carries the
  `Rotation` field → `MAP REBUILD` (the engine applies the field rotation to the local PolyList,
  producing the **world** cavity) → set the builder to a large enclosing box → `BRUSH FROM
  DEINTERSECTION` (builder ∩ empty = the rotated cavity) → `BRUSH EXPORT` = the **world geometry**
  of a field-rotated brush. This is exactly the materialize path's geometry, so it's a true parity
  readout. (Two gotchas: paste adds a `+32uu` drift on all axes — subtract it; and the enclosing
  builder must be big enough in EVERY axis, or pitch/roll results are silently CLIPPED — the first
  pitch/roll capture was wrong for this reason, re-run with a 768³ box.)

## Evidence (de-drifted; local box X[0,256] Y[0,64] Z[0,64])

| field rotation | local corner | → world corner | ⇒ rule |
|---|---|---|---|
| `Yaw=16384` | `+X(256,0,0)` | `(0,256,0)` | `+X→+Y` |
| `Yaw=16384` | `+Y(0,64,0)` | `(-64,0,0)` | `+Y→-X`  ⇒ `(x,y)→(-y,x)` |
| `Pitch=16384` | `+X(256,0,0)` | `(0,0,256)` | `+X→+Z` |
| `Pitch=16384` | `+Z(0,0,64)` | `(-64,0,0)` | `+Z→-X`  ⇒ `(x,z)→(-z,x)` |
| `Roll=16384` | `+Y(0,64,0)` | `(0,0,-64)` | `+Y→-Z` |
| `Roll=16384` | `+Z(0,0,64)` | `(0,64,0)` | `+Z→+Y`  ⇒ `(y,z)→(z,-y)` |
| `Pitch=16384,Yaw=16384` | all 8 corners | match `Rz·Ry` | order = `yaw∘pitch` |

## Corrected matrices (degrees → 3×3, to match the editor)

```python
def _rz(rad):  # yaw (Z) — UNCHANGED from textbook
    c, s = cos(rad), sin(rad); return [[c,-s,0],[s,c,0],[0,0,1]]
def _ry(rad):  # pitch (Y) — sin SIGN FLIPPED vs textbook
    c, s = cos(rad), sin(rad); return [[c,0,-s],[0,1,0],[s,0,c]]
def _rx(rad):  # roll (X) — sin SIGN FLIPPED vs textbook
    c, s = cos(rad), sin(rad); return [[1,0,0],[0,c,s],[0,-s,c]]
# euler_to_matrix(pitch,yaw,roll) = _rz(yaw) @ _ry(pitch) @ _rx(roll)   (order confirmed)
```

## What is verified vs NOT (be honest about scope)

**VERIFIED — the per-actor engine matrix** (the core parity risk: how the engine turns a `Rotation`
field into world geometry). This is what catches catastrophic bugs and it did (pitch/roll signs).
Solid.

**NOW VERIFIED against the editor — the GROUP-rotate semantics**, in
[`2026-06-19-multiactor-rotate-groundtruth.md`](2026-06-19-multiactor-rotate-groundtruth.md)
(this section's "could not be captured headless" is **superseded**). Summary: the gizmo IS
drivable headless via `wine_ctl drag --modifier ctrl --button 3` (Ctrl+RMB) into an embedded
ortho pane; **pivot = grid origin** (console selection); **Location orbit uses the per-actor
matrices verified below** (corroborating them); but **Rotation compose is per-component FRotator
ADDITION, not matrix composition** — the one surprise, flagged there for the `actor rotate` plan.
Original (now-corrected) notes kept for context:
- **There is NO console verb that rotates a multi-actor selection.** `BRUSH ROTATEREL`/`ROTATETO`
  only transform the red **builder** brush — verified: `ACTOR SELECT ALL` + `BRUSH ROTATEREL
  YAW=64` left three selected `Light`s' Location/Rotation **unchanged** (only the builder picked up
  `Yaw=16384`). So the editor's group-rotate is the **mouse gizmo only** — and that gizmo IS now
  drivable (see the linked spike).
- ~~Driving the gizmo headless failed.~~ **Corrected:** the earlier `Ctrl+RMB` attempt used wrong
  coords / hit a floating window obscuring the pane. With the right pane centre + the paced
  `drag` verb it rotates reliably (see the linked spike).

**What that leaves genuinely open (narrow):** orbit-Location-about-a-pivot + compose-each-Rotation
is standard rigid-body math, not editor-magic — any correct rigid group rotation does exactly that,
and **uedcli defines its OWN pivot** (best-grid vertex, a design choice), so it needn't match the
editor's pivot. The only truly editor-specific unknowns are (a) the editor's *default* pivot
(irrelevant to uedcli's chosen pivot) and (b) how the editor **composes a delta onto an
already-rotated actor** (matrix vs additive, gimbal handling) — which only matters for
byte-identical-to-mouse parity, not for a correct rotate (uedcli uses matrix compose, which is
correct). uedcli's correctness rests on the VERIFIED per-actor matrix + standard group math.

**Editor parity is now CLOSED** (no human-VNC step needed): the multi-actor pivot/orbit/compose
were captured headless via the `drag` verb — see
[`2026-06-19-multiactor-rotate-groundtruth.md`](2026-06-19-multiactor-rotate-groundtruth.md).
Note `MAP ROTGRID` does NOT snap the synthetic gizmo drag, so the angle comes out free; the
derivation solves the matrix from whatever angle landed rather than relying on a clean 90°.

## Trig source — the GMath sine table (exact parity)

The per-actor matrices above are the right AXES and SIGNS, but the editor evaluates sin/cos via the
**GMath integer sine LOOKUP TABLE** (`core.dll` `FGlobalMath::SinTab`/`CosTab`), not float trig:
`idx = (field >> 2) & 16383`, `value = sin(idx·2π/16384)` (16384-entry table, `>>2` TRUNCATION). A
brush world corner matches the editor to ~1e-5uu under this model and ~0.07uu under float-`math.sin`
for fields not a multiple of 4. Full proof + the `actor rotate` recommendation (make `rotation.py`
table-driven for exact offline parity) in
[`2026-06-19-group-rotate-exact-parity.md`](2026-06-19-group-rotate-exact-parity.md).

## Plumbing still owed
- `matrix_to_euler` must invert THESE (sign-flipped) matrices; re-derive against the corrected
  `_ry`/`_rx` (or compose in matrix form and convert once at the end), enforced by the
  convention-independent round-trip test (incl. the gimbal-lock poles at pitch=±90°).
- Combined-order confirmation covered only `yaw∘pitch`; `yaw∘roll`/`pitch∘roll` are low-risk
  leftovers (per-axis matrices + the one combined case are consistent).

## Decisions folded into the plan

`euler_to_matrix` uses the corrected `_ry`/`_rx` (pitch/roll sin-flipped); unit stays 65536;
storage stays the `Rotation` field; the paste-carve+DEINTERSECTION capture is the integration
verification (Task 6). The `ROTATETO` ×256 input quirk is documented and avoided.
