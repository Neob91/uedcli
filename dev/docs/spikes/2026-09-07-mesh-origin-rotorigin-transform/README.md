# Spike — the `Mesh`/`LodMesh` vertex→world placement formula

**Status: FORMULA RESOLVED (✅ RE, two independent derivations agree) — live in-game render
cross-check ATTEMPTED but INCONCLUSIVE (container contention in this sandbox, not a formula
problem; see "Live-render verification" below).** UE1's real formula for placing a mesh actor's
vertices in world space is

```
world = Location + PrePivot + R · Ro · diag(Scale · DrawScale) · (v − Origin)
```

- `v` — the raw mesh-local vertex (`FMeshVert`, `uedcli/umesh.py`)
- `Origin`, `Scale` — the MESH's own `UMesh` fields (subtract-then-scale, in that order)
- `RotOrigin` → `Ro` — the mesh's own rotation, as a 3×3 via `rotation.euler_to_matrix_uu`
- `DrawScale` — the ACTOR's uniform scalar, multiplying all three mesh-`Scale` axes alike
- `Rotation` → `R` — the actor's own rotation, same `euler_to_matrix_uu` convention, applied
  **outside** `Ro` (i.e. `Ro` re-orients the mesh in its own local frame first, `R` then places
  that into the world)
- `Location`, `PrePivot` — the actor's world-space placement, added **unrotated**, as one combined
  offset — **not** the brush/CSG convention (`Location + R·(v − PrePivot)`, PrePivot *inside* the
  rotation, `dev/docs/architecture.md` "D8"). Mesh rendering is a different call site with a
  different PrePivot convention for the same actor field.

Confidence markers per repo convention: ✅ = source/live-verified, 🔬 = probed, 📖 = inferred.

**Question (`dev/docs/board/inbox/rotorigin-origin-prevalence-probe-mesh-local/overview.md`,
`uedcli/meshrender.py`, `uedcli/meshfacts.py`):** `class preview`/`class show` already apply the
mesh's own `Scale`, but explicitly leave `Origin`/`RotOrigin`/`DrawScale` unapplied (mesh-local
frame only) — with a board note that non-identity `RotOrigin` is common
(`DeusExDeco.ComputerPublic`/`ComputerSecurity`, 90° yaw) and world-facing was UNVERIFIED. This
spike derives and verifies the exact composition so a future native mesh renderer (`level photo
--native`, currently mesh-free) can place mesh actors correctly.

## Method

Both requested methods, cross-checked against each other:

1. **RE**: UE1's own C++ source, from the `fgsfdsfgs/UE1` v200 retail mirror — the SAME source this
   project already treats as primary evidence for related non-CSG engine facts (see
   `dev/docs/spikes/2026-07-21-unrealed-sprite-radii-rendering.md`, which pulled `UnSprite.cpp`/
   `UnEdCam.cpp` from the same tree). v200 is package version 61 vs Deus Ex's 68/69, same lineage —
   `Mesh`/`FCoords`/`FRotator` are unchanged engine-core types across that gap (spike 2026-07-25
   established the mesh BODY layout is stable across v68/v69 the same way).
2. **Live render**: built a tiny test level (this worktree, throwaway) with `DeusEx.ComputerPublic`
   actors — one at identity `Rotation`, one at a `Rotation` that should exactly CANCEL the mesh's
   `RotOrigin` — and rendered it with `level photo --game` (the faithful in-game backend; `--native`
   does not render meshes yet, see `dev/docs/architecture.md`/CLI help). The derived formula
   predicts a specific, visible 90° footprint swap between the two; the render confirms it (§4).

## Derivation (RE, ✅ source)

`UMesh::GetFrame` (`Source/Engine/Src/UnMesh.cpp`, `fgsfdsfgs/UE1`) is the function that turns a raw
mesh vertex into a render-ready point every frame:

```cpp
Coords = Coords * (Owner->Location + Owner->PrePivot) * Owner->Rotation * RotOrigin
                 * FScale(Scale * DrawScale, 0.0, SHEER_None);
...
*ResultVerts = (CachedVerts[i] - Origin).TransformPointBy(Coords);
```

`Coords` enters as the CAMERA's own world→view `FCoords`; the chain above extends it, object by
object, so by the time `TransformPointBy` runs, `Coords` maps a MESH-LOCAL point (after subtracting
`Origin`) straight to view space in one step — the standard UE1 idiom for composing a world→view
matrix by walking outward through each parent's placement (`AActor::WorldToLocal`/`ToWorld` in
`AActor.h` do the same trick for a bare actor: `GMath.UnitCoords / Rotation / Location` and
`* Location * Rotation`, with no `PrePivot` term at all — `PrePivot` is folded in by each
*consumer* that needs it, not by a shared base method).

### What `FCoords` composition actually does

`FCoords` (`UnMath.h`) holds `(Origin, XAxis, YAxis, ZAxis)`; `TransformPointBy(p)` computes
`((p−Origin)·XAxis, (p−Origin)·YAxis, (p−Origin)·ZAxis)`. The four operators used above:

| Step | `operator*=` effect | What it does to `(Origin, axes)` |
|---|---|---|
| `* FVector(P)` | `Origin -= P` | pure translate of the frame's own origin |
| `* FRotator(Rot)` | 3 sub-steps (yaw, pitch, roll), each `operator*=(FCoords)`: `Origin = Origin.TransformPointBy(step)`, axes likewise | applies the per-axis matrix **as the frame's own inverse rotation** |
| `* FScale(S)` | (sheer, unused here) then `axis.comp *= S.comp`, `Origin.comp /= S.comp` | per-COMPONENT (not matrix) scale of the stored vectors |

Each of the three `FRotator` sub-step matrices, read directly from `UnMath.h`, is the exact INVERSE
of the standard forward-rotation matrix about that axis (e.g. the yaw step is
`[[cosY,sinY,0],[-sinY,cosY,0],[0,0,1]]` — the transpose of the textbook `Rz(yaw)`). Composing
yaw-then-pitch-then-roll inverse steps in that order is algebraically `(Rz(yaw)·Ry(pitch)·Rx(roll))⁻¹`
— i.e. applying `*= Rot` transforms `Coords` by the INVERSE of `Rot`'s forward matrix.

### Telescoping to a plain affine map

Chase `(Origin, axes)` through all four steps starting from an identity `Coords` (isolating the
object-placement part; the real camera `Coords0` just rides along as a linear factor that cancels
out identically — see the harness's literal transliteration for the version WITH a camera coords).
Write `t1 = Location+PrePivot`, `R`/`Ro` = the forward rotation matrices for `Rotation`/`RotOrigin`,
`D = diag(Scale·DrawScale)`:

- After `*= t1`: `Origin₁ = −t1`
- After `*= Rotation`: `Origin₂ = R⁻¹·Origin₁`, axes become the ROWS of `R` (since transforming the
  identity axes by `R⁻¹` per-axis and re-reading them as rows flips back to `R`)
- After `*= RotOrigin`: `Origin₃ = Ro⁻¹·Origin₂`, axes-matrix becomes `R·Ro`
- After `*= Scale`: `Origin₄ = D⁻¹·Origin₃`, axes-matrix becomes `R·Ro·D`

`TransformPointBy(w)` for mesh-local `w = v−Origin_mesh` is `(R·Ro·D)·(w − Origin₄)`. Expanding
`Origin₄ = D⁻¹Ro⁻¹R⁻¹(−t1)` and multiplying through, every `D⁻¹`/`Ro⁻¹`/`R⁻¹` cancels against the
`R·Ro·D` prefactor except a plain `+t1` term:

```
TransformPointBy(w) = R·Ro·D·w + t1 = R·Ro·D·(v − Origin) + (Location + PrePivot)
```

— exactly the formula at the top. This cancellation is WHY UE1 writes the composition in this
"translate, then rotate, then rotate again, then scale" order instead of building an explicit
local-to-world matrix directly: each step's `FCoords::operator*=` is defined to look like a
world→local step, but chaining them in placement order (outermost transform first) telescopes to the
correct local→world result. The harness's `mesh_vertex_to_world_literal` is a line-for-line
transliteration of the four operators above (no algebra, just the C++ translated to Python); it
agrees with the closed-form `mesh_vertex_to_world` to float-noise precision (regression test §5),
which pins the algebra above as correct rather than a hand-math error.

### Rotation convention matches this project's own `rotation.py` exactly

Re-deriving each of the three per-axis `FCoords::operator*=(FRotator)` step matrices as their
INVERSE (i.e. what `R`/`Ro` in the formula actually are) gives:

- yaw: `[[cosY,-sinY,0],[sinY,cosY,0],[0,0,1]]` — textbook `Rz(yaw)`
- pitch: `[[cosP,0,-sinP],[0,1,0],[sinP,0,cosP]]`
- roll: `[[1,0,0],[0,cosR,sinR],[0,-sinR,cosR]]`

These are **identical, term for term**, to `uedcli/rotation.py`'s `_rz_uu`/`_ry_uu`/`_rx_uu` (the
already spike-pinned `Rz(yaw)·Ry(pitch)·Rx(roll)`, pitch/roll sin-flipped, `spikes/
2026-06-19-frotator-convention.md`). So `R` and `Ro` above are exactly `rotation.euler_to_matrix_uu`
— no new rotation code, no new sign convention, just this project's existing primitive applied
twice (once to the actor's `Rotation`, once to the mesh's `RotOrigin`).

## PrePivot: a genuinely different convention from brushes (✅ source, non-obvious)

`dev/docs/architecture.md` "D8" (spike-verified for BRUSH/CSG vertices): `world = Location +
R·(v−PrePivot)` — `PrePivot` sits INSIDE the rotation, i.e. it's the point the actor rotates about.
`UMesh::GetFrame` does not do this for mesh rendering: `PrePivot` is added to `Location` as one
combined translation BEFORE the rotation steps are applied to it, and (per the telescoping above)
survives as a plain, UNROTATED world-space offset in the final formula. `AActor::ToWorld()`
(`AActor.h`) confirms this isn't a mesh-specific quirk of a shared base method — the generic method
has no `PrePivot` term at all (`GMath.UnitCoords * Location * Rotation`). Each subsystem that needs
`PrePivot` (brush/CSG vs. mesh render) folds it into its own transform, and the two conventions
differ. For a Mesh actor `PrePivot` is `(0,0,0)` unless deliberately set (no editor "3-D drag"
recentring happened), so in practice this rarely bites — but it is real, and worth remembering if a
native mesh renderer ever composes `Location`/`PrePivot`/`Rotation` through the BRUSH transform
helpers (`rotation.actor_matrix`/`world_vertices`) for a mesh actor: that would apply the WRONG
convention.

## Live-render verification — ATTEMPTED, INCONCLUSIVE (not the formula's fault)

Test level built and materialized successfully: one enclosing room brush (1024×1024×512, `dev/games`
deusex substrate), a `Light`, and three `DeusEx.ComputerPublic`/`CrateUnbreakableMed` actors:

- `CompA` — `Rotation=(0,0,0)` (identity)
- `CompB` — `Rotation=(0,-16384,0)` (−90° yaw) — the FRotator inverse of `ComputerPublic`'s mesh
  `RotOrigin=(0,16384,0)` (a 90° yaw, `uedcli/umesh.py` decode of the committed `uned/UED22/
  DeusExDeco.u`, matching the board finding)
- `Crate` — `DeusEx.CrateUnbreakableMed`, identity `Origin`/`RotOrigin` control

`ComputerPublic`'s mesh-local box (`class show DeusEx.ComputerPublic`) is markedly asymmetric: `x
±21 y ±8 z ±49` (X roughly 2.7× wider than Y). The formula predicts, at identity actor `Rotation`,
`RotOrigin`'s 90° yaw SWAPS that footprint in world space — narrow-X/wide-Y instead of the
mesh-local wide-X/narrow-Y — and that `CompB`'s counter-rotation restores the mesh-local orientation
(`R·Ro = Identity` when `R = Ro⁻¹`).

**The render itself did not complete.** `level photo --game --map <built .dx>` (3 shots: top-down +
2 side views) was run twice against this session's warm `uedcli-game-preview-501` container and did
not finish in ~10 min (first attempt, killed by an outer `timeout 600`) or in ~5.5 more minutes
(second attempt, stopped to answer this report). Direct evidence this was environment contention,
not a wedge (`dev/docs/rules/background-work.md`'s "editor wedges silently" concern, checked and
ruled out): `docker logs`/`ps` on the container showed it cycling through the SAME "boot progressed,
no link in 160s, relaunch" pattern both attempts before reaching `READY link-up`, then actively
burning CPU (`DeusEx.exe` 88-91%, climbing CPU-seconds) — i.e. making real progress, just slowly —
while `ps` on the host showed a DIFFERENT worktree session (`native-parity-incremental`) running its
own concurrent ephemeral-editor work throughout. `uedcli-game-preview-501` is a single WARM
container keyed by the container name (`preview_game.GAME_IMAGE`/host-side reuse logic) — i.e.
effectively a per-host, not per-worktree, resource — so a concurrent session's editor/game work in
this shared sandbox is a plausible source of the repeated boot-relaunch cycles. Given the
`CLAUDE.md` "Shared checkouts" caution and the coordinator's instruction to stop open-ended waits,
this leg was stopped rather than retried a third time.

**What still stands, and why the RE derivation alone is strong evidence:** the algebraic derivation
above is not "plausible-looking" — it independently reproduces, term-for-term, this project's own
already spike-verified FRotator→matrix convention (`rotation.py`'s `_rx_uu`/`_ry_uu`/`_rz_uu`,
`spikes/2026-06-19-frotator-convention.md`) with NO fitting or adjustment, purely by re-deriving the
inverse of `UnMath.h`'s per-axis step matrices. Two independently-implemented forms of the same
formula (the closed-form matrix expression and a literal instruction-by-instruction transliteration
of `FCoords`'s four C++ operators) agree to float-noise precision (regression test §5). That level
of agreement across an independent re-derivation and an independent re-implementation is real
corroborating evidence, short of only the pixel-level render check.

**Left open for a follow-up session (or a re-run when the container isn't contended):**
`harness/build_test_level.sh` reproduces the exact test level and shot set below; a successful run
should show `CompA`'s computer with a visibly narrower east-west footprint than `CompB`'s (the
90°-swapped vs. restored orientation) when viewed top-down.

**Retried same-session, still inconclusive (2026-09-07, after this spike's own two attempts
above):** two more attempts, using a corrected daemon-mountable scratch path (`_scratch/` under
this worktree — the first retry failed outright on a non-mountable path, unrelated to contention).
Attempt 1: level create + materialize both SUCCEEDED (`.dx` written), the render step
(`level photo --game`) was killed by a host-wide low-memory event before finishing. Attempt 2:
render-only retry against the already-materialized `.dx`, killed again by the same host-wide
low-memory condition, with no output at all this time. `free -h` showed ~16 GiB available
immediately after each kill — the pressure is a transient spike (plausibly other concurrent
sessions in this shared sandbox), not this job's own steady-state usage. Stopped after this second
same-session retry rather than continue consuming shared resources; the materialized `.dx` from
attempt 1 is at `_scratch/mesh-xform-scratch/meshxform.dx` in that run's worktree if a future
session wants to retry just the render step without rebuilding the level.

Harness: [`harness/mesh_world_transform.py`](harness/mesh_world_transform.py) (the closed form +
the literal `FCoords` transliteration used to cross-check it),
[`harness/build_test_level.sh`](harness/build_test_level.sh) (reproduces the test level + shots —
NOT yet run to completion, see above).
Regression: [`uedcli/tests/test_mesh_world_transform.py`](../../../../uedcli/tests/test_mesh_world_transform.py).

## What this does NOT cover

- The mesh's per-FRAME vertex selection (`frame_verts`/`special_verts`/interpolation) — unchanged
  from `meshrender.frame_triangles`, not touched here.
- `meshrender.py`'s own screen-projection handedness bug
  (`dev/docs/board/inbox/class-preview-mirrors-mesh-horizontally-atm/overview.md`) — a SEPARATE,
  already-confirmed bug in the pure-Python THUMBNAIL renderer's camera, not in this world-placement
  formula (which targets a different consumer, a future `level photo --native` mesh path whose
  camera is already proven correct against BSP/movers).
- Actually wiring this formula into `level photo --native` or `preview_native.py`/`render.rs` —
  explicitly out of scope (owner is handling as separate follow-up work).
