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

- [ ] **Step 1: Write the failing test**

```python
# uedcli/tests/test_preview_native.py (add near the existing camera_basis test)
import math
from uedcli.preview_native import camera_basis, sky_camera_basis
from uedcli.rotation import euler_to_matrix_uu, matmul, inverse, deg_to_uu, matvec

def test_sky_camera_basis_divides_by_the_sky_rotation_not_multiplies():
    """A non-zero SkyZoneInfo.Rotation must produce a DIFFERENT basis than the viewer's own —
    and specifically the basis you get by right-multiplying the viewer's matrix by the sky
    rotation's INVERSE, not its plain matrix (which would be the wrong operator and would only
    show up as a bug for a rotated sky actor, per spike `2026-09-12-pf-fakebackdrop-re`)."""
    pitch_deg, yaw_deg = 10.0, 45.0
    sky_pitch_uu, sky_yaw_uu, sky_roll_uu = 0, deg_to_uu(90.0), 0

    fwd, right, up = sky_camera_basis(pitch_deg, yaw_deg, sky_pitch_uu, sky_yaw_uu, sky_roll_uu)

    viewer_R = euler_to_matrix_uu(deg_to_uu(pitch_deg), deg_to_uu(yaw_deg), 0)
    sky_R = euler_to_matrix_uu(sky_pitch_uu, sky_yaw_uu, sky_roll_uu)
    expected_R = matmul(viewer_R, inverse(sky_R))
    expected_fwd = matvec(expected_R, (1.0, 0.0, 0.0))
    expected_right = matvec(expected_R, (0.0, 1.0, 0.0))
    expected_up = matvec(expected_R, (0.0, 0.0, 1.0))

    for got, want in [(fwd, expected_fwd), (right, expected_right), (up, expected_up)]:
        for g, w in zip(got, want):
            assert abs(g - w) < 1e-5, f"{got} != {want}"

    # Sanity: with a non-zero sky rotation, the sky basis must differ from the viewer's own —
    # proves this isn't accidentally just returning camera_basis(pitch_deg, yaw_deg) unchanged.
    viewer_fwd, _, _ = camera_basis(pitch_deg, yaw_deg)
    assert any(abs(fwd[i] - viewer_fwd[i]) > 1e-3 for i in range(3))


def test_sky_camera_basis_matches_viewer_when_sky_rotation_is_zero():
    """A zero SkyZoneInfo.Rotation (the common authored case) must reproduce the viewer's own
    basis exactly — dividing by the identity rotation is a no-op."""
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
    engine — a right-multiply by the INVERSE of the sky rotation, NOT a plain compose/multiply;
    see `dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section). Camera POSITION is handled
    separately by the caller (the sky actor's own `Location`, with no dependency on the viewer's
    position at all — see spec `add-pf-fakebackdrop-support-to-level-photo`)."""
    from .rotation import euler_to_matrix_uu, matmul, inverse, matvec, deg_to_uu
    viewer_r = euler_to_matrix_uu(deg_to_uu(pitch_deg), deg_to_uu(yaw_deg), 0)
    sky_r = euler_to_matrix_uu(sky_pitch_uu, sky_yaw_uu, sky_roll_uu)
    composed = matmul(viewer_r, inverse(sky_r))
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
of this task. Add an explicit depth-reached assertion (e.g. render at increasing recursion budgets
and confirm behavior changes between depth-1 and depth-3 renders — output must differ, proving the
extra recursion actually happened, not just "didn't crash").

- [ ] **Step 2: Run test to verify it fails**

Run: `cd uedcli-native && cargo test facing_mirrors_do_not_hang_and_cap_recursion -- --nocapture`
Expected: FAIL (old cap-1 behavior doesn't match the new depth-3 assertions)

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

Run: `cd uedcli-native && cargo test -- --nocapture 2>&1 | tail -40`
Expected: PASS, including every OTHER existing render.rs test (no unrelated regressions)

- [ ] **Step 5: Commit**

```bash
git add uedcli-native/src/render.rs docs/reference/level/photo.md
git commit -m "Generalize mirror recursion cap 1 -> 3 (real engine's shared budget)"
```

---

### Task 3: Rust — `Blend::Backdrop` sky sub-render

**Files:**
- Modify: `uedcli-native/src/render.rs` (`blend_mode` ~line 139, `group_mirror_clusters` ~line
  196-215, `render_impl` ~line 465-560, add a `Sky` struct + const near the other `PF_*` consts at
  line 120-122)

**Interfaces:**
- Consumes: `recursion_depth: u32` from Task 2.
- Produces:
  - `pub struct Sky { pub location: Vec3, pub forward: Vec3, pub right: Vec3, pub up: Vec3 }`
    (same shape as `Camera` minus `fov_deg` — the sky sub-render reuses the primary camera's FOV).
  - `render_impl`/`render` gain a new parameter `sky: Option<&Sky>`.
  - `blend_mode(poly_flags: u32, has_sky: bool) -> Blend` (signature CHANGES — was
    `blend_mode(poly_flags: u32)`; every call site must pass `has_sky`).
  - `Blend` gains a `Backdrop` variant.
- Task 4/5 (Python) produce the `Sky` value this task's FFI wiring (Task 6) will need — this task
  only needs `Option<&Sky>` to exist as a Rust-side concept; wiring it through PyO3 is Task 6.

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

Run: `cd uedcli-native && cargo test backdrop -- --nocapture`
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

Update `Blend` enum (near line 133) to add `Backdrop`.

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

Update `group_mirror_clusters` (line ~196): it calls `blend_mode(poly.poly_flags)` at its filter
check — change to `blend_mode(poly.poly_flags, has_sky)` and thread `has_sky: bool` as a new
parameter into the function (so a `PF_FakeBackdrop|PF_Mirrored` face with a resolvable sky is
correctly excluded from mirror clustering, matching `render_impl`'s own classification of it as
`Backdrop`).

Update `render_impl` (line 465) to accept `sky: Option<&Sky>`, pass `sky.is_some()` to every
`blend_mode`/`group_mirror_clusters` call, and add the backdrop sub-render — modeled directly on
the existing mirror-cluster loop (lines ~504-552), but simpler: ONE sub-render for ALL backdrop
polys together (there's exactly one sky, not one per mirror plane), no clipping (a sky camera has
no "wrong side" to clip away — it's not a reflection), and it uses `sky`'s own `location`/
`forward`/`right`/`up` directly as the sub-render's `Camera` (same `fov_deg` as the primary):

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
                                    recursion_depth + 1, sky);   // sky threads through recursion too
        for &idx in &backdrop_indices {
            render_poly(&polys[idx], Blend::Backdrop, textures, camera, half_w, half_h, focal,
                       &mut img, &mut zbuf, w, h, Some(&secondary), false);
        }
    }
}
```

(`render_poly`'s existing signature already accepts a `Some(&secondary)` buffer + a `tint: bool` —
pass `false` for tint, since backdrop has no translucent-tint-over-reflection concept the way
mirror does; confirm this compiles against `render_poly`'s actual current parameter list, which
may differ slightly from the mirror call site shown at line ~547 — read it directly before wiring
this up.)

Update the `Blend::Opaque => render_poly(...)` match arm and the recursion-cap check (Task 2's
`if mode == Blend::Mirror && recursion_depth >= MAX_RECURSION` becomes `if (mode == Blend::Mirror
|| mode == Blend::Backdrop) && recursion_depth >= MAX_RECURSION { mode = Blend::Opaque; }` — a
backdrop face that hits the recursion cap falls back to drawing its OWN texture, same fallback
mirror already uses).

Update `pub fn render(...)` (line ~449) to accept and forward `sky: Option<&Sky>`.

**Signature-consistency fix (`render_impl` now takes 7 params, not Task 2's 6):** Task 2 added
`recursion_depth` as `render_impl`'s 6th parameter; this task adds `sky: Option<&Sky>` as a 7th.
EVERY call site must be updated to match, including the ones Task 2 already wrote:
- `pub fn render(...)`'s call (`render_impl(polys, textures, camera, width, height, 0, sky)`).
- The mirror-cluster loop's recursive call (Task 2's `render_impl(&clipped_scene, textures,
  &refl_camera, width, height, recursion_depth + 1)`) — add `sky` as its 7th argument too, e.g.
  `render_impl(&clipped_scene, textures, &refl_camera, width, height, recursion_depth + 1, sky)`.
  This is not optional: it's how a mirror that reflects a view of the sky (a real, spec-documented
  nested case) actually shows the sky inside the reflection instead of a flat texture.
- This task's own new backdrop recursive call (shown above) already passes `sky` correctly — use
  it as the reference for the other two call sites' argument order.

Run `cargo build` after this change and fix every compile error from the new parameter before
moving to Step 4 — a mismatched call site is a compile-time error, not a silent bug, so there is no
ambiguity about whether every site got updated.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd uedcli-native && cargo test -- --nocapture 2>&1 | tail -60`
Expected: PASS, all three new tests plus every pre-existing `render.rs` test still green.

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
    assert actor.props.get("bHighDetail") in (True, "True", 1)  # match this codebase's prop-value convention
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

```python
def find_sky_actor(level, index):
    """The level's sky actor (an `Engine.SkyZoneInfo` or subclass), or `None` if the level has
    none — a port of `Engine.u`'s `ZoneInfo::LinkToSkybox()` OUTCOME (see
    `dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section): the real engine picks by
    `bHighDetail == Level.bHighDetailMode`, a runtime client setting `level photo` has no
    equivalent of — deterministically prefer a `bHighDetail=True` actor if any exists, else the
    first `SkyZoneInfo` found. There is at most one sky actor for a whole level (not per-zone)."""
    candidates = [
        a for a in level.actors.values()
        if index.descends_from(a.class_fqcn, "Engine.SkyZoneInfo")
    ]
    if not candidates:
        return None
    for a in candidates:
        if a.props.get("bHighDetail"):
            return a
    return candidates[0]
```

(Adjust field/method names — `a.class_fqcn`, `a.props.get(...)`, `index.descends_from(...)` — to
match whatever this codebase's ACTUAL `Actor`/`ClassIndex` API is; these are educated guesses from
the codebase's naming conventions elsewhere, not verified against the real class definitions. Read
`uedcli/classindex.py` and wherever `level.actors` is defined before finalizing this.)

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test uedcli/tests/test_preview_native.py -k find_sky_actor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "Add find_sky_actor: level-global SkyZoneInfo resolution"
```

---

### Task 5: Python — wire the sky camera through `build_scene`/`render_shots` and the FFI

**Files:**
- Modify: `uedcli/preview_native.py:362` (`build_scene`), `:630-662` (`render_shots`)
- Modify: `uedcli-native/src/lib.rs:663` (`render_frame` — add the `sky` parameter, thread into
  `render::render(...)`)
- Test: `uedcli/tests/test_preview_native.py` (end-to-end, real render)

**Interfaces:**
- Consumes: `sky_camera_basis` (Task 1), `find_sky_actor` (Task 4), `Sky` struct + `render`'s new
  `sky` parameter (Task 3).
- Produces: `render_frame`'s Python-facing signature gains an optional sky camera argument.

- [ ] **Step 1: Write the failing test**

```python
# uedcli/tests/test_preview_native.py
def test_pf_fakebackdrop_face_renders_sky_zone_geometry(tmp_path):
    """End-to-end: a two-room fixture (a normal room + a sealed sky room containing a
    SkyZoneInfo), one face of the normal room flagged PF_FakeBackdrop and textured differently
    from the sky room's own walls. The rendered shot must show the SKY ROOM's texture through
    that face, not the face's own assigned texture."""
    # Build the fixture using the same synthetic-actor-splicing pattern as Task 4's tests, PLUS
    # actual brush geometry for both rooms (mirror test_native_roundtrip.py's `_room_t3d()`
    # pattern — a sealed box brush for the sky room, positioned far from the main room so there's
    # no visual overlap, containing one SkyZoneInfo actor with a NON-zero Rotation to also
    # exercise Task 1's formula end-to-end, not just in isolation).
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
`Some` (mirroring how `camera` is already unpacked into `render::Camera` at line ~731), and pass
`sky_val.as_ref()` into `render::render(...)`'s new parameter (Task 3). Run the existing
`render_frame`-calling tests after this change specifically to confirm they still pass unmodified
(they should — `sky=None` is the default).

In `uedcli/preview_native.py`'s `build_scene` (line 362): call `find_sky_actor(level, index)`
once, return it (or its resolved `Location`/`Rotation`) alongside `polys, textures` — check the
function's current return type (`tuple[list, list]`) and widen it (e.g. `tuple[list, list, Actor |
None]`), updating `build_scene`'s ONE caller (`render_shots`, line 643) to match.

In `render_shots` (line 630): after computing `fwd, right, up = camera_basis(rs.pitch, rs.yaw)`
per shot (line 658), if a sky actor was found, additionally compute `sky_fwd, sky_right, sky_up =
sky_camera_basis(rs.pitch, rs.yaw, *sky_actor's rotation fields in UU)` and pass `(tuple(float(c)
for c in sky_actor.location), sky_fwd, sky_right, sky_up)` as the new `sky` argument to
`uedcli_native.render_frame(...)`; pass `None` when there's no sky actor.

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test uedcli/tests/test_preview_native.py -k pf_fakebackdrop -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add uedcli/preview_native.py uedcli-native/src/lib.rs uedcli/tests/test_preview_native.py
git commit -m "Wire the sky camera through build_scene/render_shots and the FFI"
```

---

### Task 6: Real-corpus check, docs, and the full suite

**Files:**
- Modify: `docs/reference/level/photo.md` (add a `PF_FakeBackdrop` paragraph — see spec's "Docs"
  section for exactly what to say; match the style of the existing mirror/masked/translucent
  paragraphs in the same file)
- No new source files — this task is verification + the docs update Task 2 didn't already cover.

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

- [ ] **Step 3: Add the docs/reference update**

Write the `PF_FakeBackdrop` paragraph in `docs/reference/level/photo.md`, matching the existing
`--faces textured` section's style (see the current `PF_Mirrored`/masked/translucent paragraphs
there for the expected level of detail — this is user-facing documentation of BEHAVIOR, not an RE
writeup; it should read like "a PF_FakeBackdrop face now renders the level's sky room... falls
back to its own texture when there's no SkyZoneInfo", not reproduce the spike's evidence).

- [ ] **Step 4: Run the whole offline suite once**

Run: `bin/test` (no args — the full suite, per `dev/docs/rules/tests.md`)
Expected: only the previously-documented pre-existing failures (check
`dev/docs/board/inbox/offline-suite-has-10-undocumented-pre-existing/` and
`NATIVE-MATERIALIZE.md`/`USCRIPT-COMPILER.md`'s testing sections for the current known-red list) —
no new, unexplained failures.

- [ ] **Step 5: Commit**

```bash
git add docs/reference/level/photo.md
git commit -m "Document PF_FakeBackdrop rendering in level photo --native"
```

---

## Self-Review Notes (for whoever runs this plan)

- **Spec coverage:** Task 1 = rotation formula (spec §2 rotation-order warning). Task 2 = recursion
  cap generalization (spec §5, owner-approved). Task 3 = the core Rust render mechanism (spec §2-4,
  §3's `blend_mode` dispatch fix). Task 4 = sky-actor resolution (spec §1, the corrected mechanism
  replacing the false `SkyZone`-property-read premise). Task 5 = the FFI/Python wiring (spec §2's
  "per-shot parameter" requirement). Task 6 = spec's "Tests" real-corpus check and "Docs" section.
  Edge cases from the spec (no SkyZoneInfo, both flags set, recursion, unsealed sky room) are
  covered by Tasks 3-5's tests; the "unsealed sky room can leak" edge case is a documented known
  limitation (spec's own wording), not something to add a guard for.
- **Placeholder scan:** Task 4's exact `Actor`/`ClassIndex` field/method names
  (`class_fqcn`/`props.get`/`descends_from`) are EXPLICITLY flagged as educated guesses to verify
  against the real API, not invented placeholders to fill in later — the implementer must read
  `uedcli/classindex.py` and the `Actor` type before finalizing, per the step's own instructions.
  This is a plan-quality risk worth knowing about going in, not a gap to silently paper over.
- **Type consistency:** `Sky` (Rust, Task 3) ↔ the `sky` FFI parameter (Task 5) ↔
  `sky_camera_basis`'s return shape (Task 1) all agree on `(forward, right, up)` as 3-tuples of
  3-tuples, matching `camera_basis`'s existing established shape exactly.
