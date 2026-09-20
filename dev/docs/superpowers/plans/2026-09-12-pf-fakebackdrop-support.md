# PF_FakeBackdrop Support in `level photo --native` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `level photo --native` render `PF_FakeBackdrop` (skybox) surfaces the way the real
UE1/Deus Ex engine does — a second scene rendered from the level's sky actor, composited into the
face, instead of the face's own flat texture — for every level that has a `SkyZoneInfo` actor.

**Architecture:** Python (`uedcli/preview_native.py`) gains a level-global sky-actor lookup and,
per shot, computes the composed sky-camera basis (viewer rotation divided by the sky actor's own
rotation — pure matrix algebra, no new FRotator conversion). Rust (`uedcli-native/src/render.rs`)
gains a `Blend::Backdrop` render mode that renders ONE extra scene from the sky camera and samples
it per backdrop face, reusing the existing mirror sub-render machinery, and generalizes the
existing one-bounce mirror recursion cap to the real engine's shared cap of 3.

**Tech Stack:** Rust (PyO3 FFI, `uedcli-native`), Python 3.12 (`uedcli`), pytest, `cargo test`.

**Spec:** `dev/docs/board/to-plan/add-pf-fakebackdrop-support-to-level-photo/spec.md` (read it in
full — this plan implements it; `dev/docs/spikes/2026-09-12-pf-fakebackdrop-re/spike.md` and
`dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section are the RE evidence the spec argues
from).

## Global Constraints

- No new per-poly FFI field: `RenderPoly.poly_flags` already carries `PF_FakeBackdrop` (0x80) —
  only a new, OPTIONAL, per-shot "sky camera" parameter is added to the render entry point.
- No FRotator conversion in Rust — this codebase's standing rule (`render.rs`'s own module doc,
  `preview_native.py`'s `camera_basis` docstring: "Rust NEVER converts FRotator angles... the
  camera convention is single-sourced"). The sky-rotation compose is pure 3×3 matrix algebra done
  in Python with `uedcli/rotation.py`'s existing `matmul`/`inverse`/`euler_to_matrix_uu`, producing
  a plain basis tuple exactly like `camera_basis` already does for the viewer.
- `AZoneInfo.SkyZone` is NOT a readable/authored property — there is exactly one sky actor (or
  none) per level, found by scanning for `Engine.SkyZoneInfo`-class actors, tie-broken by
  `bHighDetail`. Do not write code that reads a `SkyZone` field off any actor.
- The recursion cap on backdrop/mirror child renders is a SHARED depth counter, cap **3** (not 1) —
  an intentional, owner-approved change to `render.rs`'s EXISTING mirror behavior. Every place that
  currently assumes "mirrors recurse at most once" must be updated, not just the new backdrop code.
- `ShowFlags` gating is dropped entirely — `level photo --native` always renders the sky when one
  resolves and a `PF_FakeBackdrop` face exists, matching the shipped game's default (not the
  editor's opt-in toggle) and this project's rule against environment-dependent behavior.
- Every existing `level photo`/`preview_native`/mirror-recursion test must stay green EXCEPT the
  ones this plan explicitly updates for the cap-1→3 change (Task 2) — no other behavior regresses.
- Run tests via `bin/test`, never bare `pytest`. Run only the scoped tests named in each task while
  iterating; run the whole `bin/test` suite once before the final task's commit (per
  `dev/docs/rules/tests.md`).

---

### Task 1: Rotation compose — pin and unit-test the sky-camera basis formula

**Files:**
- Modify: `uedcli/preview_native.py` (add a new function near `camera_basis`, line ~329)
- Test: `uedcli/tests/test_preview_native.py` (or wherever `camera_basis` is already tested — grep
  for `camera_basis` in `uedcli/tests/` and add alongside it)

**Interfaces:**
- Produces: `sky_camera_basis(pitch_deg: float, yaw_deg: float, sky_pitch_uu: int, sky_yaw_uu:
  int, sky_roll_uu: int) -> tuple[tuple[float,float,float], tuple[float,float,float],
  tuple[float,float,float]]` — `(forward, right, up)`, same shape `camera_basis` already returns.
  Later tasks (Task 5) call this once per shot.

This is the highest-risk piece of math in the whole feature (the spec and spike both flag it: a
zero-rotation `SkyZoneInfo` — the common case — hides a divide-vs-multiply mistake completely,
because dividing or multiplying by the identity rotation is the same operation). Isolate it in its
own function with its own test using a NON-zero sky rotation, before touching anything else.

The real engine: `SkyCoords = Frame->Coords` (copies the viewer's full basis), then `SkyCoords /=
SkyZone->Rotation` — an `FCoords::operator/=(const FRotator&)`, i.e. right-multiply by the INVERSE
of the sky rotation's matrix (a `/=` divides the calling object BY the argument — the calling
object's basis is composed with the argument's inverse, not the other way around).
`uedcli/rotation.py` already has `euler_to_matrix_uu`, `matmul`, `inverse`, `deg_to_uu` — use them,
do not hand-roll matrix math.

**Formula derivation — do not skip this, it's where the plan's first draft got it backwards.**
`FCoords` holds its basis as ROWS (confirmed by `uedcli/rotation.py`'s own `_fcoords_mul_axes`:
`new_row[j] = row · B[j]`, i.e. `rows_new = rows · Bᵀ`; `render.rs:366-368`'s `rel.dot(&camera.
forward)` uses the SAME row/world-to-camera-projection convention). `camera_basis` returns the
COLUMNS of `R = euler_to_matrix_uu(...)` — which, for an orthonormal `R`, means the ROW-matrix
`M_viewer` those columns actually represent is `Rᵀ`. Composing (§ mechanism: `SkyCoords =
Frame->Coords` then `SkyCoords /= SkyZone->Rotation`) gives, in row form:
`M_sky = M_viewer · R_sky⁻¹ = R_viewerᵀ · R_sky⁻¹`. Transposing both sides (since we want this
back in `camera_basis`'s COLUMN convention to return): `M_skyᵀ = R_sky · R_viewer` (using
`(R_sky⁻¹)ᵀ = R_sky` for an orthonormal `R_sky`). So the matrix whose COLUMNS give
`(forward, right, up)` is `composed = matmul(transpose(inverse(sky_r)), viewer_r)` — this reduces
to `R_sky · R_viewer` (not `R_viewer · R_sky⁻¹`, which is what an implementer would guess from the
prose "viewer rotation divided by sky rotation" without doing this derivation — the naive guess
has BOTH the operand order and the inverse placement backwards).

- [ ] **Step 1: Write the failing test**

Use a HAND-WORKED expected value, not one derived by calling the same matrix helpers the
implementation calls — a test that re-derives its own expectation via `matmul`/`inverse` the same
way the implementation does cannot fail for a wrong operand order (this is exactly the mistake the
plan's own first draft made here).

```python
# uedcli/tests/test_preview_native.py (add near the other pose/camera tests)
from uedcli.preview_native import camera_basis, sky_camera_basis
from uedcli.rotation import deg_to_uu

def test_sky_camera_basis_viewer_identity_sky_yaw_90():
    """Hand-worked, not re-derived from the implementation's own matrix helpers: viewer looking
    straight down UE1 +X (pitch=0, yaw=0, the identity rotation) with a SkyZoneInfo rotated +90
    degrees of yaw. `composed = R_sky · R_viewer = R_sky` here (viewer is the identity), and
    `R_sky`'s own first column (= `forward`, `camera_basis`'s established convention) for a pure
    +90-degree yaw is exactly world +Y: `(0, 1, 0)`. If an implementation instead computes
    `R_viewer · inverse(R_sky)` (the plan's first-draft bug — wrong operand order AND wrong
    inverse placement), this yields `(0, -1, 0)` instead — the opposite direction. See
    `dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section for why it's a divide of the
    VIEWER's rotation by the sky's, not the other way around."""
    fwd, right, up = sky_camera_basis(0.0, 0.0, 0, deg_to_uu(90.0), 0)
    assert abs(fwd[0] - 0.0) < 1e-4 and abs(fwd[1] - 1.0) < 1e-4 and abs(fwd[2] - 0.0) < 1e-4, fwd


def test_sky_camera_basis_matches_viewer_when_sky_rotation_is_zero():
    """A zero SkyZoneInfo.Rotation (the common authored case) must reproduce the viewer's own
    basis exactly — composing with the identity rotation is a no-op, so THIS case alone cannot
    distinguish a correct formula from the backwards one (see the identity+yaw-90 test above,
    which can)."""
    pitch_deg, yaw_deg = -15.0, 200.0
    fwd, right, up = sky_camera_basis(pitch_deg, yaw_deg, 0, 0, 0)
    viewer_fwd, viewer_right, viewer_up = camera_basis(pitch_deg, yaw_deg)
    for got, want in [(fwd, viewer_fwd), (right, viewer_right), (up, viewer_up)]:
        for g, w in zip(got, want):
            assert abs(g - w) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test uedcli/tests/test_preview_native.py -k sky_camera_basis -v`
Expected: FAIL with `ImportError: cannot import name 'sky_camera_basis'`

- [ ] **Step 3: Write minimal implementation**

Add to `uedcli/preview_native.py`, right after `camera_basis` (line ~337):

```python
def sky_camera_basis(pitch_deg: float, yaw_deg: float,
                     sky_pitch_uu: int, sky_yaw_uu: int, sky_roll_uu: int):
    """(forward, right, up) world basis for the sky sub-render's camera: the viewer's own
    rotation divided by the sky actor's own rotation (`FCoords::operator/=(FRotator)` in the real
    engine). NOT `matmul(viewer_r, inverse(sky_r))` — that guess has both the operand order and
    the inverse placement backwards; see this task's derivation comment in the plan/spec for why
    it's `matmul(transpose(inverse(sky_r)), viewer_r)`, which reduces to `sky_r · viewer_r` for an
    orthonormal `sky_r`. Camera POSITION is handled separately by the caller (the sky actor's own
    `Location`, with no dependency on the viewer's position at all)."""
    from .rotation import euler_to_matrix_uu, matmul, inverse, transpose, matvec, deg_to_uu
    viewer_r = euler_to_matrix_uu(deg_to_uu(pitch_deg), deg_to_uu(yaw_deg), 0)
    sky_r = euler_to_matrix_uu(sky_pitch_uu, sky_yaw_uu, sky_roll_uu)
    composed = matmul(transpose(inverse(sky_r)), viewer_r)
    return (tuple(matvec(composed, (1.0, 0.0, 0.0))),
            tuple(matvec(composed, (0.0, 1.0, 0.0))),
            tuple(matvec(composed, (0.0, 0.0, 1.0))))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test uedcli/tests/test_preview_native.py -k sky_camera_basis -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "Add sky_camera_basis: sky-rotation compose for PF_FakeBackdrop, pinned"
```

---

### Task 2: Rust — generalize the mirror recursion cap from 1 to the shared cap-3

**Files:**
- Modify: `uedcli-native/src/render.rs:35-37` (module doc), `:465-503` (`render_impl`'s
  `mirror_depth` parameter and cap checks), test around line 1402-1417
  (`facing_mirrors_do_not_hang_and_cap_recursion`)
- Modify: `docs/reference/level/photo.md:74-78` (mirror recursion description)

**Interfaces:**
- Produces: `render_impl`'s recursion parameter renamed `mirror_depth` → `recursion_depth`
  (`u32`), cap constant `3` (was implicit `> 0` / `== 0`, now `>= 3` / `< 3`). Task 3 depends on
  this being generalized (backdrop recursion reuses the SAME parameter and cap).

Do this BEFORE Task 3 so the recursion machinery is proven correct (still terminates, still passes
existing mirror tests except the one deliberately updated) before backdrop code starts sharing it.

- [ ] **Step 1: Write the failing test (update the existing one)**

Read the current test first: `sed -n '1390,1420p' uedcli-native/src/render.rs`. It currently
asserts termination at depth 1. Change the assertion to allow depth up to 3 and verify it actually
reaches 3 for a facing-mirrors scene (not just "terminates at *some* depth ≤ old cap") — a test
that only checks termination would pass even if the cap silently stayed at 1, defeating the point
of this task.

**There is no public-API way to observe the recursion depth reached** — `render()` always starts
at depth 0 and `MAX_RECURSION` is an internal const. The test module is `mod tests { use super::*;
}` in the SAME file, so it can call the private `render_impl` directly with an explicit STARTING
depth — use this to prove the cap moved, not just that nothing crashed: call `render_impl(&polys,
&[], &cam, 32, 32, 2)` (only 1 more level of budget available from here — reproduces the OLD cap-1
behavior, since starting 2 away from a cap-3 ceiling leaves exactly one more recursion) and compare
its output to `render_impl(&polys, &[], &cam, 32, 32, 0)` (the full new cap-3 budget, 3 more
levels available). For a facing-mirrors scene, more available recursion depth changes what's
visible in the deepest reflection — the two outputs must DIFFER. If they don't differ, the cap
generalization didn't actually take effect (e.g. `MAX_RECURSION` still gates at 1 somewhere).

```rust
#[test]
fn facing_mirrors_do_not_hang_and_cap_recursion() {
    // Two mirrors facing each other between the camera: without a recursion cap this would
    // either hang or blow the stack. Rendering must complete (this test finishing at all IS part
    // of the regression check) and show something other than the flat background.
    let cam = cam_at_origin_looking_plus_x(90.0);
    let mut near_mirror = wall(20.0, 100.0, -1);
    near_mirror.poly_flags = PF_MIRRORED;
    let mut far_mirror = wall_facing_away(-20.0, 100.0, -1);
    far_mirror.poly_flags = PF_MIRRORED;
    let polys = [near_mirror, far_mirror];
    let img = render(&polys, &[], &cam, 32, 32);
    assert_eq!(img.len(), 32 * 32 * 3);
    assert!(img.chunks_exact(3).any(|p| p != BACKGROUND));
}

#[test]
fn recursion_cap_generalized_to_3_not_still_1() {
    // Starting 2 away from the cap-3 ceiling leaves exactly ONE more recursion (the OLD cap-1
    // behavior from depth 0); starting at depth 0 leaves THREE more. If the cap were still
    // effectively 1 (e.g. a leftover `> 0` check somewhere), these two renders would be pixel-
    // identical -- this test fails loudly in that case instead of just "not crashing".
    let cam = cam_at_origin_looking_plus_x(90.0);
    let mut near_mirror = wall(20.0, 100.0, -1);
    near_mirror.poly_flags = PF_MIRRORED;
    let mut far_mirror = wall_facing_away(-20.0, 100.0, -1);
    far_mirror.poly_flags = PF_MIRRORED;
    let polys = [near_mirror, far_mirror];
    let shallow = render_impl(&polys, &[], &cam, 32, 32, 2);   // 1 more level available (old cap)
    let deep = render_impl(&polys, &[], &cam, 32, 32, 0);      // 3 more levels available (new cap)
    assert_ne!(shallow, deep, "cap-3 budget produces the same image as the old cap-1 budget");
}
```

(`wall`/`wall_facing_away`/`cam_at_origin_looking_plus_x`/`BACKGROUND` already exist in this same
test module — read them to confirm the exact scene these two mirrors describe before assuming the
"more recursion changes the image" premise holds; adjust the scene geometry if the two mirrors as
currently defined don't actually produce depth-dependent differences, e.g. by giving them visibly
different textures/colors so a third bounce shows something a first bounce doesn't.)

- [ ] **Step 2: Run test to verify it fails**

Run: `source bin/_venv.sh && _ensure_build_image && _rust_build_run cargo test recursion_cap_generalized -- --nocapture`
(there is no `bin/cargo` — Rust runs in a Docker build image via `bin/_venv.sh`'s
`_rust_build_run`/`_ensure_build_image`, not a bare `cargo` on the host; `which cargo` finds
nothing here)
Expected: FAIL to compile (`render_impl` isn't called with the new parameter list this task adds —
or, once Task 3 lands, may fail for a different reason; run this task's changes standalone before
Task 3 touches the same function)

- [ ] **Step 3: Write minimal implementation**

In `render_impl` (`render.rs:465-503`):

```rust
fn render_impl(
    polys: &[RenderPoly],
    textures: &[RenderTexture],
    camera: &Camera,
    width: u32,
    height: u32,
    recursion_depth: u32,          // was mirror_depth — now shared with PF_FakeBackdrop (Task 3)
) -> Vec<u8> {
    const MAX_RECURSION: u32 = 3;  // the real engine's FSceneNode::Recursion cap (spike 2026-09-12)
    ...
    if mode == Blend::Mirror && recursion_depth >= MAX_RECURSION {
        mode = Blend::Opaque;
    }
    ...
    if recursion_depth < MAX_RECURSION {
        for cluster in group_mirror_clusters(polys) {
            ...
            let secondary = render_impl(&clipped_scene, textures, &refl_camera, width, height,
                                        recursion_depth + 1);
            ...
        }
    }
```

Update the two call sites that currently pass `0`/`mirror_depth`: `pub fn render(...)` (line ~456,
`render_impl(polys, textures, camera, width, height, 0)` — unchanged, 0 is still the root) and the
recursive call inside the mirror-cluster loop (shown above).

Update the module doc (`render.rs:35-37`): replace "Capped at one reflection deep... a
hall-of-mirrors is a real UE1 case this draft renderer does not attempt" with a note that
recursion is capped at 3 (the real engine's shared budget across mirror and — new — backdrop
frames), matching `MAX_RECURSION`.

Update `docs/reference/level/photo.md`'s mirror paragraph (around line 74-78): change "Capped at
one reflection deep" to "Capped at three levels deep (the real engine's shared recursion budget)".

- [ ] **Step 4: Run test to verify it passes**

Run (redirect to a file and check the exit code separately — never pipe a long cargo run through
`tail`, it masks the exit code, per `NATIVE-MATERIALIZE.md`'s testing note):

```bash
source bin/_venv.sh && _ensure_build_image && _rust_build_run cargo test --quiet > /tmp/cargo_out.txt 2>&1
echo "EXIT: $?"
tail -n 60 /tmp/cargo_out.txt
```

Expected: `EXIT: 0`, both new tests plus every OTHER existing `render.rs` test still green (no
unrelated regressions).

- [ ] **Step 5: Commit**

```bash
git add uedcli-native/src/render.rs docs/reference/level/photo.md
git commit -m "Generalize mirror recursion cap 1 -> 3 (real engine's shared budget)"
```

---

### Task 3: Rust — `Blend::Backdrop` sky sub-render

**Files:**
- Modify: `uedcli-native/src/render.rs` (`blend_mode` ~line 139, `group_mirror_clusters` ~line
  204-228, `raster_tri`'s match ~line 662, `render_impl` ~line 465-560, `pub fn render` ~line 449,
  add a `Sky` struct + const near the other `PF_*` consts at line 120-122)
- Modify: `uedcli-native/src/lib.rs:738` (its existing `render::render(...)` call site — must pass
  `None` for the new parameter now, or this task's own `cargo build` fails; Task 5 replaces the
  `None` with the real resolved value)

**Interfaces:**
- Consumes: `recursion_depth: u32` from Task 2.
- Produces:
  - `pub struct Sky { pub location: Vec3, pub forward: Vec3, pub right: Vec3, pub up: Vec3 }`
    (same shape as `Camera` minus `fov_deg` — the sky sub-render reuses the primary camera's FOV).
  - `render_impl`/`render` gain a new parameter `sky: Option<&Sky>`.
  - `blend_mode(poly_flags: u32, has_sky: bool) -> Blend` (signature CHANGES — was
    `blend_mode(poly_flags: u32)`; every call site must pass `has_sky`, including the existing test
    at line ~1286-1288).
  - `Blend` gains a `Backdrop` variant, and its derive gains `Debug`.
- Task 4/5 (Python) produce the `Sky` value this task's FFI wiring (Task 5) will need — this task
  only needs `Option<&Sky>` to exist as a Rust-side concept and `lib.rs:738` passing `None`;
  wiring the real value through PyO3 is Task 5.

`PF_FakeBackdrop = 0x0000_0080` — add as a local `const` in `render.rs` (matching the existing
local-const style for `PF_TRANSLUCENT`/`PF_MODULATED`/`PF_MIRRORED` at lines 120-122; do not import
`light.rs`'s private const of the same name).

- [ ] **Step 1: Write the failing test**

Add to `render.rs`'s `#[cfg(test)]` module (near the existing mirror tests):

```rust
#[test]
fn backdrop_face_renders_the_sky_scene_not_its_own_texture() {
    // A single quad flagged PF_FakeBackdrop, textured solid red. A Sky is provided pointing at
    // a DIFFERENT scene (a solid blue quad, positioned so it fills the backdrop face's screen
    // footprint from the sky camera's vantage). The backdrop face must show BLUE, not its own
    // red texture.
    let backdrop_poly = /* construct a RenderPoly, poly_flags = PF_FAKE_BACKDROP, tex_index
                            pointing at a solid-red RenderTexture, facing the camera, filling
                            the frame */;
    let sky_scene_poly = /* a solid-blue RenderPoly, positioned/oriented so that rendered from
                             the Sky's location+basis it fills the frame */;
    let sky = Sky { location: /* ... */, forward: /* ... */, right: /* ... */, up: /* ... */ };
    let img = render(&[backdrop_poly], &textures_with_both_colors, &camera, W, H, Some(&sky));
    // sample the center pixel: must be blue (the sky sub-render), not red (the face's own texture)
    let center = ((H / 2) as usize * W as usize + (W / 2) as usize) * 3;
    assert_eq!(&img[center..center + 3], BLUE_RGB);
}

#[test]
fn backdrop_face_falls_back_to_its_own_texture_with_no_sky() {
    // Same backdrop-flagged red quad, but `sky: None` — must draw its OWN texture (today's
    // existing behavior), matching the real engine's NULL-SkyZone fallback.
    let backdrop_poly = /* same as above */;
    let img = render(&[backdrop_poly], &textures, &camera, W, H, None);
    let center = /* ... */;
    assert_eq!(&img[center..center + 3], RED_RGB);
}

#[test]
fn backdrop_wins_over_mirrored_when_a_sky_is_present() {
    let poly = /* poly_flags = PF_FAKE_BACKDROP | PF_MIRRORED, textured red */;
    assert_eq!(blend_mode(poly.poly_flags, true), Blend::Backdrop);
    assert_eq!(blend_mode(poly.poly_flags, false), Blend::Mirror);  // no sky -> falls through
}
```

(Fill in the exact `RenderPoly`/`Vec3`/`Camera`/`RenderTexture` construction using the patterns
already visible in `render.rs`'s existing tests in the same `#[cfg(test)]` module — e.g.
`render_poly_end_to_end_uses_lightmap_when_present` around line 1236 builds a full poly/texture/
camera set from scratch; copy that scaffolding rather than inventing a new one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `source bin/_venv.sh && _ensure_build_image && _rust_build_run cargo test backdrop -- --nocapture`
(no bare `cargo` on this host — see Task 2's note)
Expected: FAIL to compile (`Sky` doesn't exist, `render`/`render_impl`/`blend_mode` signatures
don't match, `Blend::Backdrop` doesn't exist)

- [ ] **Step 3: Write minimal implementation**

Add near the other `PF_*` consts (render.rs:120-122):

```rust
const PF_FAKE_BACKDROP: u32 = 0x0000_0080;

/// The sky sub-render's camera — the level's `SkyZoneInfo` actor's own `Location`, and a basis
/// composed from the viewer's rotation divided by the sky actor's own rotation (computed
/// Python-side, `preview_native.sky_camera_basis` — see `dev/docs/unrealed/rendering.md`'s
/// `PF_FakeBackdrop` section for why this is a divide, not a multiply). `None` when the level has
/// no `SkyZoneInfo` (the real engine's own NULL-SkyZone fallback: every `PF_FakeBackdrop` face
/// then draws its own texture, unchanged from this renderer's pre-existing behavior).
pub struct Sky {
    pub location: Vec3,
    pub forward: Vec3,
    pub right: Vec3,
    pub up: Vec3,
}
```

Update `Blend`'s derive (line 131, `#[derive(Clone, Copy, PartialEq, Eq)]`) to ALSO derive `Debug`
— this test's `assert_eq!` (and any future one) needs it; the existing tests avoid `assert_eq!` on
`Blend` and use `assert!(a == b)` instead for exactly this reason (see `render.rs:1286-1288`), but
there's no reason to keep avoiding it once `Debug` is added. Then add the `Backdrop` variant.

Update `blend_mode` (line 139) — mirrors the real engine's if/else-if order exactly (spike
`2026-09-12-pf-fakebackdrop-re`, `dev/docs/unrealed/rendering.md`):

```rust
fn blend_mode(poly_flags: u32, has_sky: bool) -> Blend {
    if poly_flags & PF_FAKE_BACKDROP != 0 && has_sky {
        Blend::Backdrop
    } else if poly_flags & PF_MIRRORED != 0 {
        Blend::Mirror
    } else if poly_flags & PF_TRANSLUCENT != 0 {
        Blend::Translucent
    } else if poly_flags & PF_MODULATED != 0 {
        Blend::Modulated
    } else {
        Blend::Opaque
    }
}
```

**`blend_mode` has THREE existing call sites, not two** — all three need the new `has_sky`
argument or this won't compile: `group_mirror_clusters` (line ~207), `render_impl`'s per-poly
classification (line ~487), AND the existing test `mirror_flag_takes_precedence_over_translucent`
(line ~1286-1288, three calls: `blend_mode(PF_MIRRORED | PF_TRANSLUCENT)` etc. — update each to
`blend_mode(PF_MIRRORED | PF_TRANSLUCENT, false)`, since that test has no sky in play and its
whole point is Mirror-vs-Translucent precedence, unaffected by `has_sky`).

Update `group_mirror_clusters` (line 204) to take a new `has_sky: bool` parameter, threading it
into its own `blend_mode(poly.poly_flags, has_sky)` call (so a `PF_FakeBackdrop|PF_Mirrored` face
with a resolvable sky is correctly excluded from mirror clustering, matching `render_impl`'s own
classification of it as `Backdrop` — without this, such a face gets BOTH a mirror cluster AND a
backdrop sub-render).

Update `raster_tri`'s `match blend { ... }` (around line 662 — the block handling
`Blend::Opaque`/`Translucent`/`Modulated`/`Mirror` per-pixel; **this match is exhaustive over
`Blend`'s variants, so skipping this step is a compile error**, not a runtime gap) to add a
`Blend::Backdrop` arm. Behaves like `Blend::Mirror`'s arm MINUS the `mirror_tint` compositing (a
backdrop face shows only what's behind it — there's no "own texture blended over the sky" concept
the way `PF_Mirrored|PF_Translucent` blends over a reflection):

```rust
Blend::Backdrop => {
    // Like Blend::Mirror but with no tint pass — a backdrop face shows ONLY the sky
    // sub-render, never its own texture (unless mirror_src is None, the defensive
    // fallback below, which real callers never hit).
    zbuf[pi] = inv_d;
    let (mut mr, mut mg, mut mb) = (sr, sg, sb);
    if let Some(src) = mirror_src {
        let so = pi * 3;
        mr = src[so] as f32;
        mg = src[so + 1] as f32;
        mb = src[so + 2] as f32;
    }
    img[o] = mr as u8;
    img[o + 1] = mg as u8;
    img[o + 2] = mb as u8;
}
```

Update `render_impl` (line 465) to accept `sky: Option<&Sky>` as its 7th parameter, pass
`sky.is_some()` to every `blend_mode`/`group_mirror_clusters` call, and fix the per-poly
classification match — it currently ends `_ => blended.push((poly, mode, poly_depth(poly,
camera)))` (line ~499), a catch-all that a `Blend::Backdrop` poly would silently fall into
(drawing it AGAIN, wrongly, as a plain translucent-list opaque poly on top of the sky). Add an
explicit arm BEFORE the catch-all:

```rust
match mode {
    Blend::Opaque => render_poly(
        poly, Blend::Opaque, textures, camera, half_w, half_h, focal, &mut img, &mut zbuf,
        w, h, None, false,
    ),
    Blend::Mirror => {}    // drawn below, once per mirror plane, after every opaque poly
    Blend::Backdrop => {}  // drawn below, once for the whole sky, after the mirror clusters
    _ => blended.push((poly, mode, poly_depth(poly, camera))),
}
```

Then add the backdrop sub-render — modeled on the existing mirror-cluster loop (lines ~503-551),
but simpler: ONE sub-render for ALL backdrop polys together (there's exactly one sky, not one per
mirror plane), no plane clip (a sky camera has no "wrong side" to clip away — it's not a
reflection), using `sky`'s own `location`/`forward`/`right`/`up` directly as the sub-render's
`Camera` (same `fov_deg` as the primary). **Place this block AFTER the mirror-cluster loop and
BEFORE the `blended.sort_by(...)` / draw loop** (line ~552) — a backdrop face must be resolved
before any translucent/modulated layer composites on top of it, same ordering constraint the
mirror clusters already respect:

```rust
if let Some(sky) = sky {
    let backdrop_indices: Vec<usize> = polys.iter().enumerate()
        .filter(|(_, p)| blend_mode(p.poly_flags, true) == Blend::Backdrop)
        .map(|(i, _)| i)
        .collect();
    if !backdrop_indices.is_empty() && recursion_depth < MAX_RECURSION {
        let sky_camera = Camera {
            location: sky.location, forward: sky.forward, right: sky.right, up: sky.up,
            fov_deg: camera.fov_deg,
        };
        // Whole scene, no plane clip (unlike mirror) — a sky camera has no "wrong side"; see
        // the spec's "known simplification" note (no zone culling exists in this renderer).
        let secondary = render_impl(polys, textures, &sky_camera, width, height,
                                    recursion_depth + 1, Some(sky));  // sky threads through recursion
        for &idx in &backdrop_indices {
            render_poly(&polys[idx], Blend::Backdrop, textures, camera, half_w, half_h, focal,
                       &mut img, &mut zbuf, w, h, Some(&secondary), false);
        }
    }
}
```

(Note `Some(sky)`, not `sky` — `sky` is already `&Sky` inside the `if let Some(sky) = sky` block,
and `render_impl`'s parameter type is `Option<&Sky>`; passing the bare reference is a type error.)

Update the recursion-cap check from Task 2 (`if mode == Blend::Mirror && recursion_depth >=
MAX_RECURSION`) to also cover backdrop: `if (mode == Blend::Mirror || mode == Blend::Backdrop) &&
recursion_depth >= MAX_RECURSION { mode = Blend::Opaque; }` — a backdrop face that hits the
recursion cap falls back to drawing its OWN texture, same fallback mirror already uses.

**Signature-consistency fix (`render_impl` now takes 7 params, not Task 2's 6) — EVERY call site,
across BOTH this task and Task 2, must match:**
- `pub fn render(...)` (line ~449) — add and forward its own new `sky: Option<&Sky>` parameter:
  `render_impl(polys, textures, camera, width, height, 0, sky)`.
- The mirror-cluster loop's recursive call (Task 2 wrote `render_impl(&clipped_scene, textures,
  &refl_camera, width, height, recursion_depth + 1)`) — add `sky` as its 7th argument too:
  `render_impl(&clipped_scene, textures, &refl_camera, width, height, recursion_depth + 1, sky)`.
  Not optional: a mirror that reflects a view containing the sky (a real, spec-documented nested
  case) needs `sky` threaded through to show it, instead of a flat texture inside the reflection.
- This task's own new backdrop recursive call (above) already passes `Some(sky)` correctly.
- **`uedcli-native/src/lib.rs:738`** — `render_frame`'s existing body calls
  `render::render(&rpolys, &rtex, &cam, width, height)`. This is NOT in Task 5's scope (Task 5 adds
  the PyO3-level `sky` parameter) — for THIS task to compile and its own tests to pass, update this
  call site NOW to pass `None` for the new parameter: `render::render(&rpolys, &rtex, &cam, width,
  height, None)`. Task 5 changes this `None` into the real resolved value.

Run `source bin/_venv.sh && _ensure_build_image && _rust_build_run cargo build` after ALL of the
above and fix every compile error from the new parameter/variant before moving to Step 4 — a
mismatched call site or a non-exhaustive match is a compile-time error, not a silent bug, so there
is no ambiguity about whether every site got updated.

**Add three more tests before moving on — the spec asks for these and no earlier step covers
them:**

```rust
#[test]
fn backdrop_camera_ignores_viewer_position_no_parallax() {
    // The spike's single most distinctive finding: the sky camera's LOCATION never depends on
    // the viewer's position, only its rotation. Render the same backdrop-flagged scene from two
    // different camera POSITIONS (same rotation) and confirm the backdrop pixels are identical —
    // only geometry/parallax-dependent content (there is none here but the backdrop face itself)
    // would differ if the sky camera incorrectly tracked the viewer's position.
    let sky = Sky { location: /* fixed point */, forward: /* ... */, right: /* ... */, up: /* ... */ };
    let cam_a = Camera { location: /* position A */, ..base_camera() };
    let cam_b = Camera { location: /* position B, far from A */, ..base_camera() };
    let img_a = render(&[backdrop_poly.clone()], &textures, &cam_a, W, H, Some(&sky));
    let img_b = render(&[backdrop_poly.clone()], &textures, &cam_b, W, H, Some(&sky));
    // sample the pixel(s) where the backdrop face projects in EACH camera's frame and confirm
    // they show the same sky content despite the viewer having moved.
}

#[test]
fn backdrop_only_recursion_respects_the_shared_cap() {
    // A PF_FakeBackdrop face visible from within its own sky room (the sky sub-render's OWN
    // scene also contains a backdrop-flagged face pointing back at more sky) must not
    // infinitely recurse — same MAX_RECURSION=3 budget as mirrors, no separate backdrop-only cap.
    // Construct a scene where the sky's own content is ALSO backdrop-flagged and confirm
    // rendering terminates (finishing the test IS part of the check) within the shared depth.
}

#[test]
fn mixed_backdrop_and_mirror_recursion_shares_one_budget() {
    // A mirror that reflects a view containing a backdrop face (or vice versa) consumes the SAME
    // shared depth counter — confirm a mirror-then-backdrop-then-mirror nesting terminates at
    // depth 3 total, not 3 mirror bounces PLUS 3 backdrop bounces independently.
}
```

(These three need real scene construction, same as this step's first three tests — use the same
scaffolding pattern from `render_poly_end_to_end_uses_lightmap_when_present`. The exact assertions
are sketched above; fill them in against the real `RenderPoly`/`Camera` types before treating this
step as done.)

- [ ] **Step 4: Run test to verify it passes**

Run (never pipe a long cargo run through `tail` — it masks the exit code):

```bash
source bin/_venv.sh && _ensure_build_image && _rust_build_run cargo test --quiet > /tmp/cargo_out.txt 2>&1
echo "EXIT: $?"
tail -n 80 /tmp/cargo_out.txt
```

Expected: `EXIT: 0`, all six new tests plus every pre-existing `render.rs` test still green.

- [ ] **Step 5: Commit**

```bash
git add uedcli-native/src/render.rs
git commit -m "Add PF_FakeBackdrop sky sub-render (Blend::Backdrop)"
```

---

### Task 4: Python — find the level's sky actor (LinkToSkybox port)

**Files:**
- Modify: `uedcli/preview_native.py` (new function, near `build_scene` at line ~362)
- Test: `uedcli/tests/test_preview_native.py`

**Interfaces:**
- Produces: `find_sky_actor(level, index) -> Actor | None` — returns the level's resolved sky
  actor (an `Engine.SkyZoneInfo`-class actor, or its subclass), or `None` if the level has none.
  Task 5 calls this once per `build_scene` invocation.

Do NOT read a `SkyZone` field off any actor — per the spec, that property is never authored in a
T3D. This scans the level's own actors for the RIGHT CLASS.

- [ ] **Step 1: Write the failing test**

```python
# uedcli/tests/test_preview_native.py
from uedcli.preview_native import find_sky_actor

def test_find_sky_actor_returns_none_with_no_skyzoneinfo(a_level_with_no_actors, an_index):
    assert find_sky_actor(a_level_with_no_actors, an_index) is None

def test_find_sky_actor_finds_the_one_skyzoneinfo(a_level_with_one_skyzoneinfo, an_index):
    actor = find_sky_actor(a_level_with_one_skyzoneinfo, an_index)
    assert actor is not None
    assert actor.name == "SkyZoneInfo0"  # whatever the fixture names it

def test_find_sky_actor_prefers_bhighdetail_true_among_several(
    a_level_with_two_skyzoneinfos_one_highdetail, an_index,
):
    actor = find_sky_actor(a_level_with_two_skyzoneinfos_one_highdetail, an_index)
    # actor.props is a list[tuple[str, str]], not a dict — no .get(); prop VALUES are strings
    # ("True"/"False"), so a plain truthiness check on the raw string is wrong (a stated
    # `bHighDetail="False"` is a truthy Python string). Match the fixture's actor by name instead
    # of re-reading its own props back (that would just restate what find_sky_actor already read).
    assert actor.name == "SkyZoneInfoHighDetail"  # whatever the fixture names its bHighDetail=True actor
```

(Build the three fixtures using whatever pattern `uedcli/tests/test_native_roundtrip.py` already
uses to splice a synthetic zone/actor block into a T3D — grep that file for how it constructs
`Engine.ZoneInfo`/`DeusEx.WaterZone` actors around lines 679-728, and mirror it for
`Engine.SkyZoneInfo`. Use whatever this codebase's real `level.actors`/`ClassIndex.descends_from`
API actually is — read `uedcli/classindex.py`'s `descends_from` and how `preview_native.py` already
gets an `index` parameter into `build_scene`, rather than inventing a different lookup mechanism.)

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test uedcli/tests/test_preview_native.py -k find_sky_actor -v`
Expected: FAIL with `ImportError: cannot import name 'find_sky_actor'`

- [ ] **Step 3: Write minimal implementation**

The plan's first draft guessed at this codebase's `Actor`/`ClassIndex` API instead of reading it,
and got it wrong in six places. Use the REAL API, verified against `uedcli/model.py`'s `Actor`
(`name`, `cls: str`, `props: list[tuple[str, str]]` — NOT a dict, no `.get()`), and
`uedcli/native/materialize.py`'s `_is_zone_actor_class`/`resolve_zone_actors` (lines ~450-506),
which already solves the exact same "is this actor's class a descendant of X, safely, including
bare class names" problem for `ZoneInfo` — mirror its pattern for `Engine.SkyZoneInfo`:

```python
def find_sky_actor(level, index):
    """The level's sky actor (an `Engine.SkyZoneInfo` or subclass), or `None` if the level has
    none — a port of `Engine.u`'s `ZoneInfo::LinkToSkybox()` OUTCOME (see
    `dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section): the real engine assigns
    `SkyZone` on every match, so the WINNER is the LAST actor in `AllActors` order whose
    `bHighDetail` matches — `level photo` has no runtime `Level.bHighDetailMode` client setting to
    match against, so this deterministically prefers the LAST `bHighDetail=True` actor found (in
    `level.order`, the trunk order this codebase already uses for zone-actor resolution — NOT
    `level.actors.values()`, an alphabetical dict that has a NAMED regression for exactly this
    class of bug, `test_native_roundtrip.py`'s NYC_Bar N=70 case), else the LAST `SkyZoneInfo`
    found if none states `bHighDetail=True`. There is at most one sky actor for a whole level (not
    per-zone)."""
    from . import classindex
    from .uprops import resolve_class_defaults

    best = None
    for name in level.order:
        a = level.actors[name]
        if not _is_sky_zone_actor_class(index, (a.cls or "").strip()):
            continue
        instance = {k.casefold(): v for k, v in a.props}
        defaults = resolve_class_defaults(a.cls, resolver=index.resolver())
        high_detail = instance.get("bhighdetail", defaults.get(("bHighDetail", 0)))
        if str(high_detail or "False").strip() == "True":
            return a          # a bHighDetail match wins outright, last one in trunk order
        if best is None:
            best = a           # remember the first SkyZoneInfo as the no-bHighDetail fallback
    return best


def _is_sky_zone_actor_class(index, cls: str) -> bool:
    """`Engine.SkyZoneInfo` ancestry check, decided by resolved class chain not spelling — same
    shape as `uedcli/native/materialize.py`'s `_is_zone_actor_class` (mirror that function's bare-
    class-name handling and `ClassRefError`-on-undecidable behavior EXACTLY, including its
    docstring's rationale: answering `False` for an undecidable chain silently drops a real actor,
    which is the class of bug that function's own docstring documents being bitten by once
    already). Do not answer `False` for a bare (undotted) class name without first trying
    `index.bare_to_fqcn()` the way that function does."""
    ...  # implementer: copy materialize._is_zone_actor_class's body, swap ZONE_INFO_BASE/
         # LEVEL_INFO_BASE's role for "Engine.SkyZoneInfo" ancestry (no LevelInfo exclusion needed
         # here — LevelInfo is never a SkyZoneInfo). Confirm `index.ancestry`/`index.bare_to_fqcn`/
         # `ClassRefError`'s exact import path from `uedcli/classindex.py` before finalizing.
```

(`resolve_class_defaults`'s exact signature and the `instance = {k.casefold(): v for k, v in
a.props}` pattern are copied verbatim from `preview_native.py`'s own existing `field()` helper,
lines ~195-218 — read that function fully before writing this one, it's the established
instance-else-class-default resolution idiom this whole codebase uses for actor properties.)

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test uedcli/tests/test_preview_native.py -k find_sky_actor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "Add find_sky_actor: level-global SkyZoneInfo resolution"
```

---

### Task 5: Python — wire the sky camera through `render_shots` and the FFI

**Files:**
- Modify: `uedcli/preview_native.py:630-662` (`render_shots` only — `build_scene`'s signature is
  NOT touched, see Step 3)
- Modify: `uedcli-native/src/lib.rs:663` (`render_frame` — add the `sky` parameter, thread into
  `render::render(...)`)
- Test: `uedcli/tests/test_preview_native.py` (end-to-end, real render)

**Interfaces:**
- Consumes: `sky_camera_basis` (Task 1), `find_sky_actor` (Task 4), `Sky` struct + `render`'s new
  `sky` parameter (Task 3).
- Produces: `render_frame`'s Python-facing signature gains an optional sky camera argument.

- [ ] **Step 1: Write the failing test**

`uedcli/tests/test_preview_native.py` builds its `Level` fixtures with its OWN helper (`_level(*
actors)`, line ~64) — NOT `test_native_roundtrip.py`'s `_room_t3d()`. Use `_level(...)` (or
whatever this file's own established actor/level-fixture helper actually is; read the top of
`test_preview_native.py` before writing this test) for consistency with every other test in this
file, plus real brush geometry for both rooms (grep this same file for an existing test that
builds actual CSG-solved geometry, not just actors, since this test needs both).

```python
# uedcli/tests/test_preview_native.py
def test_pf_fakebackdrop_face_renders_sky_zone_geometry(tmp_path):
    """End-to-end: a two-room fixture (a normal room + a sealed sky room containing a
    SkyZoneInfo), one face of the normal room flagged PF_FakeBackdrop and textured differently
    from the sky room's own walls. The rendered shot must show the SKY ROOM's texture through
    that face, not the face's own assigned texture."""
    # Build the fixture using this file's OWN level/actor construction helpers (see note above),
    # PLUS actual brush geometry for both rooms — a sealed box brush for the sky room, positioned
    # far from the main room so there's no visual overlap, containing one SkyZoneInfo actor with a
    # NON-zero Rotation to also exercise Task 1's formula end-to-end, not just in isolation. This
    # fixture is the single largest unwritten piece of work in this whole plan — budget real time
    # for it, don't treat it as a one-line stub.
    ...
    written = render_shots(level=level, shots=[shot], out_dir=tmp_path, index=index,
                           defaults=defaults)
    assert written == 1
    img = Image.open(tmp_path / "shot-01.png")
    # sample the pixel where the PF_FakeBackdrop face is known to project, assert its color
    # matches the sky room's texture, not the face's own.
    ...

def test_pf_fakebackdrop_face_falls_back_with_no_skyzoneinfo_in_level(tmp_path):
    """The SAME PF_FakeBackdrop face, but the level has no SkyZoneInfo actor at all — must
    render its own assigned texture (today's pre-existing behavior, now confirmed correct for
    this specific case)."""
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test uedcli/tests/test_preview_native.py -k pf_fakebackdrop -v`
Expected: FAIL (render_frame doesn't accept a sky argument yet / face renders its own texture in
the has-sky case)

- [ ] **Step 3: Write minimal implementation**

**This is a breaking-signature risk — check first:** `uedcli_native.render_frame` is called
POSITIONALLY with today's 4-argument signature from several existing tests
(`uedcli/tests/test_preview_native.py` lines ~215, ~318, ~456, ~846, ~908 — grep to confirm the
current count before starting). Adding a required 5th positional parameter breaks every one of
them. This codebase has no existing `#[pyo3(signature = ...)]` precedent (checked: `render_frame`
is a plain `#[pyfunction]`) — add one so `sky` is optional and defaults to `None`, keeping every
existing call site source-compatible:

```rust
#[pyfunction]
#[pyo3(signature = (polys, textures, camera, size, sky=None))]
fn render_frame(
    py: Python<'_>,
    polys: Vec<RenderPolyTuple>,
    textures: Vec<(u32, u32, Vec<u8>, Vec<u8>)>,
    camera: ([f32; 3], [f32; 3], [f32; 3], [f32; 3], f32),
    size: (u32, u32),
    sky: Option<([f32; 3], [f32; 3], [f32; 3], [f32; 3])>,   // location, forward, right, up
) -> PyResult<Py<PyBytes>> {
```

Construct `render::Sky { location: ..., forward: ..., right: ..., up: ... }` from `sky` when
`Some` (mirroring how `camera` is already unpacked into `render::Camera` at line ~731), name the
local binding to match (`sky` in, `sky.as_ref()` or an equivalently-named local out — don't
introduce an unexplained `sky_val` rename), and pass it into `render::render(...)`'s new
parameter (Task 3). Run the existing `render_frame`-calling tests after this change specifically
to confirm they still pass unmodified (they should — `sky=None` is the default).

**Do NOT widen `build_scene`'s return type.** `build_scene` is called 41 times across
`uedcli/tests/test_preview_native.py` (production has exactly one caller, `render_shots`, but the
test suite has forty), almost all unpacking a 2-tuple (`polys, textures = pn.build_scene(...)`).
Widening the return to 3 values breaks every one of them with `ValueError: too many values to
unpack` — a change disproportionate to what this task needs, and one that would violate this
plan's own Global Constraint that only the cap-1→3 tests (Task 2) are allowed to change existing
test behavior. `render_shots` already has BOTH `level` and `index` in scope (they're its own
parameters) — call `find_sky_actor(level, index)` directly inside `render_shots`, once, separately
from `build_scene`, and leave `build_scene`'s signature exactly as it is today:

```python
# inside render_shots, once, near where `polys, textures = build_scene(...)` already is:
sky_actor = find_sky_actor(level, index)
```

In `render_shots` (line 630): after computing `fwd, right, up = camera_basis(rs.pitch, rs.yaw)`
per shot (line 658), if `sky_actor` is not `None`, additionally compute the sky basis and pass it
through:

```python
sky = None
if sky_actor is not None:
    from .rotation import actor_rotation_uu
    sky_pitch_uu, sky_yaw_uu, sky_roll_uu = actor_rotation_uu(sky_actor)
    sky_fwd, sky_right, sky_up = sky_camera_basis(rs.pitch, rs.yaw,
                                                  sky_pitch_uu, sky_yaw_uu, sky_roll_uu)
    sky_loc = sky_actor.location or (0.0, 0.0, 0.0)   # Actor.location is Vec3 | None
    sky = (tuple(float(c) for c in sky_loc), sky_fwd, sky_right, sky_up)
rgb = uedcli_native.render_frame(polys, textures, camera, (int(size[0]), int(size[1])), sky)
```

(`rotation.actor_rotation_uu` — confirm its exact name/import path in `uedcli/rotation.py` before
finalizing; it's the established accessor for an actor's rotation as `(pitch, yaw, roll)` UU
fields, matching `sky_camera_basis`'s parameter order.)

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test uedcli/tests/test_preview_native.py -k pf_fakebackdrop -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add uedcli/preview_native.py uedcli-native/src/lib.rs uedcli/tests/test_preview_native.py
git commit -m "Wire the sky camera through render_shots and the FFI"
```

---

### Task 6: Real-corpus check, mirror-cost spot-check, docs, and the full suite

**Files:**
- Modify: `docs/reference/level/photo.md` (add a `PF_FakeBackdrop` paragraph AND fix the now-stale
  "sky do NOT render lit" line — see spec's "Docs" section for exactly what to say; match the
  style of the existing mirror/masked/translucent paragraphs in the same file)
- Modify: `dev/docs/unrealed/rendering.md` (drop the "planned, not yet implemented" qualifier)
- No new source files — this task is verification + the docs updates Task 2 didn't already cover.

**Interfaces:** None new — this task only verifies and documents what Tasks 1-5 built.

- [ ] **Step 1: Find a real skybox-room level**

Check `dev/games`'s showcase trunks and `uned/UnrealAssets`'s retail Unreal-1 levels for a
`PF_FakeBackdrop` surface with a real `SkyZoneInfo` — `SkyTown`/`SkyBase`/`TheSunspire` are named
candidates (per the spec) but UNVERIFIED; grep/inspect for the actual flag+actor combination
before assuming one of these qualifies. If none of the existing corpus has a working example, skip
this step and note it in the commit message — do not author a new fixture level just for this
check (Task 5's synthetic fixture already covers correctness).

- [ ] **Step 2: Render it and eyeball the result**

`bin/uedcli --project <the project> level photo --tree level/<name> "<some shot>" --out-dir
<scratch dir>` — confirm the sky renders as actual geometry, not a flat texture, and doesn't look
obviously broken (a leak, a black screen, an upside-down sky).

- [ ] **Step 3: Mirror-cost spot-check (spec §5's own ask, not yet covered by any task)**

The cap-1→3 change (Task 2) makes mirror-heavy levels do meaningfully more work per shot.
`render.rs`'s `group_mirror_clusters` doc already names `Terraniux.unr` as the reference
mirror-heavy case (`DecayedS.Floor.dmFlor2a`, 2 clusters). Render it before and after this plan's
changes (or just note the wall-clock time now, post-change, if a clean "before" isn't easy to get)
and confirm it's not unreasonably slower — this is an offline draft tool, not a real-time budget,
so "somewhat slower" is fine; "hangs" or "orders of magnitude slower" is not. Note the numbers in
the commit message.

- [ ] **Step 4: Add the docs/reference update**

Write the `PF_FakeBackdrop` paragraph in `docs/reference/level/photo.md`, matching the existing
`--faces textured` section's style (see the current `PF_Mirrored`/masked/translucent paragraphs
there for the expected level of detail — this is user-facing documentation of BEHAVIOR, not an RE
writeup; it should read like "a PF_FakeBackdrop face now renders the level's sky room... falls
back to its own texture when there's no SkyZoneInfo", not reproduce the spike's evidence). The
SAME page currently says (around line 82-83) "...and sky do NOT render lit" — that line is now
wrong too; fix it in the same edit, not just add a new paragraph next to a stale one.

Also update `dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section, which currently ends
"Consumed by (planned, not yet implemented as of this writing) `uedcli-native/src/render.rs`" —
drop the "planned, not yet implemented" qualifier now that it is. This is a small factual
correction to a doc already written and committed as part of this same campaign (not a new
direction/architecture claim), consistent with the standing "keep dev docs accurate" expectation —
if in doubt, flag it rather than silently skip it.

- [ ] **Step 5: Run the whole offline suite once**

Run: `bin/test` (no args — the full suite, per `dev/docs/rules/tests.md`)
Expected: only the previously-documented pre-existing failures (check
`dev/docs/board/inbox/offline-suite-has-10-undocumented-pre-existing/` and
`NATIVE-MATERIALIZE.md`/`USCRIPT-COMPILER.md`'s testing sections for the current known-red list) —
no new, unexplained failures.

- [ ] **Step 6: Commit**

```bash
git add docs/reference/level/photo.md dev/docs/unrealed/rendering.md
git commit -m "Document PF_FakeBackdrop rendering in level photo --native"
```

---

## Self-Review Notes (for whoever runs this plan)

**This plan went through an independent Opus review of its FIRST draft, which found it was not
executable as written** — the notes below reflect what that review actually caught, not a
generic self-check. Trust this section; the plan text above already has the fixes folded in.

- **Critical, now fixed:** the first draft's rotation formula was mathematically backwards (wrong
  operand order AND wrong inverse placement — `matmul(viewer_r, inverse(sky_r))` instead of
  `matmul(transpose(inverse(sky_r)), viewer_r)`), and its OWN test could not have caught this: it
  re-derived its "expected" value using the same matrix helpers the implementation called, so a
  wrong formula and its test would agree with each other. Task 1 above now uses a hand-worked
  numeric expectation instead (viewer identity + sky yaw 90° ⇒ forward exactly `(0,1,0)`).
- **Critical, now fixed:** Task 3's first draft would not compile — `raster_tri`'s exhaustive
  `match` over `Blend` had no arm for the new variant, `render_impl`'s classification match had a
  silent `_ =>` catch-all that would double-draw a backdrop face, and `lib.rs`'s existing
  `render::render(...)` call site (outside this task's original file list) breaks the moment
  `render`'s arity changes. All three are now explicit steps in Task 3.
- **Critical, now fixed:** the first draft would have widened `build_scene`'s return type, breaking
  ~39 existing test call sites that unpack its 2-tuple return (`test_preview_native.py` calls
  `build_scene` 41 times total). Task 5 now calls `find_sky_actor` separately inside `render_shots`
  instead, touching zero other call sites.
- **Critical, now fixed:** Task 4's first draft guessed at this codebase's `Actor`/`ClassIndex` API
  instead of reading it, and two of its three guessed names (`class_fqcn`, `props.get(...)`) don't
  exist — the real API is `Actor.cls` and `Actor.props: list[tuple[str, str]]`. It also missed the
  class-default fallback for `bHighDetail`, read prop values as Python truthiness instead of the
  string `"True"` comparison this codebase's own convention uses, iterated an alphabetical dict
  instead of `level.order` (this repo has a NAMED regression test for exactly that bug shape,
  NYC_Bar N=70), and would have silently answered "not a sky actor" for any bare (undotted) class
  name instead of raising, per this project's "no silent half-answers" convention. Task 4 now
  mirrors `uedcli/native/materialize.py`'s `_is_zone_actor_class` pattern, which already solves
  this exact problem correctly for `ZoneInfo`.
- **Important, now fixed:** `cargo` is not installed on this host — every Rust command in the first
  draft (`cd uedcli-native && cargo test ...`) would fail with `cargo: command not found`. Rust
  runs in a Docker build image via `bin/_venv.sh`'s `_rust_build_run`/`_ensure_build_image`; every
  Task 2/3 command above uses that invocation instead. Also fixed: piping a long cargo run through
  `tail` (masks the exit code, per `NATIVE-MATERIALIZE.md`'s own testing note) — replaced with
  redirect-to-file-then-check-exit-code.
- **Important, now fixed:** `Blend` had no `Debug` derive, so the first draft's `assert_eq!` on it
  wouldn't compile; `blend_mode` has THREE call sites (including an existing test), not two, all of
  which need the new `has_sky` argument; Task 2's recursion-depth test had no actual mechanism to
  observe the depth reached (there's no public API for it) — Task 2 now calls the private
  `render_impl` directly with explicit starting depths and compares outputs.
- **Spec coverage, corrected:** the first draft's tests didn't actually cover the spec's own list —
  no no-parallax test, no backdrop-only or mixed backdrop/mirror recursion-cap test, and Task 6 had
  no mirror-cost spot-check despite the spec explicitly asking for one before merge (the cap-1→3
  change is a real perf-shape change to existing mirror-heavy levels). Task 3 and Task 6 now
  include these.
- **Type consistency:** `Sky` (Rust, Task 3) ↔ the `sky` FFI parameter (Task 5) ↔
  `sky_camera_basis`'s return shape (Task 1) all agree on `(forward, right, up)` as 3-tuples of
  3-tuples, matching `camera_basis`'s existing established shape exactly. `render_impl`'s
  parameter list is now consistently 7 args (`polys, textures, camera, width, height,
  recursion_depth, sky`) across every call site introduced across Tasks 2 and 3.
- **Residual risk, honestly stated:** Task 4's `_is_sky_zone_actor_class` helper is specified as
  "mirror `_is_zone_actor_class`'s pattern," not written out in full — the implementer still needs
  to actually copy and adapt that function's body (imports, `ClassRefError`, `bare_to_fqcn`) rather
  than treating the one-line stub in Task 4's snippet as done. Task 5's end-to-end fixture (a
  two-room level with real CSG geometry and a rotated `SkyZoneInfo`) is also specified by
  description rather than fully written code — it is, honestly, sized like a task of its own; treat
  it as the highest-effort single step in this plan, not a quick fixture reuse.
