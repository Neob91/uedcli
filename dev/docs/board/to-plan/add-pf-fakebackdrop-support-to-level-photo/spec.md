# Spec — PF_FakeBackdrop support in `level photo --native`

Status: **RE spike done, independently reviewed, spec revised per review (2026-09-12).** The first
draft of this spec was itself reviewed and found to rest on two false premises (`SkyZone` as a
per-zone readable property; the mirror path having no recursion counter) — both are fixed below.
Next action is a real task-by-task plan.

## Goal

Give `PF_FakeBackdrop` surfaces a **faithful** render in `level photo --native`, matching the real
engine's mechanism (`dev/docs/spikes/2026-09-12-pf-fakebackdrop-re/spike.md`,
`dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section).

## Owner's decisions

- 2026-09-12: RE the real engine instead of shipping a draft approximation; bumped p3 → p1.
- 2026-09-12 (after spec review): the recursion cap on backdrop/mirror child renders adopts the
  real engine's **shared cap-3** budget, not a cheaper cap-1-mirror-plus-separate-backdrop-cap
  shortcut. This is a deliberate, known behavior change to `render.rs`'s EXISTING mirror
  rendering (mirrors could now recurse 3 deep instead of 1) — see "Recursion" below for the blast
  radius (perf, tests, docs) this carries.

## Confirmed mechanism (cite the spike/doc, don't re-derive)

`URender::OccludeBsp` tests `PolyFlags & PF_FakeBackdrop` FIRST in an if/else-if chain (before
`PF_Mirrored`, then `PF_Portal`, then `PF_Invisible`). On a match, with a resolvable level sky
actor: the face itself is **never drawn**; a second scene renders from that actor's `Location`,
using the viewer's rotation divided by (NOT multiplied by) the sky actor's own `Rotation` — camera
*translation* is fully discarded (no parallax at all). On no resolvable sky actor, the surface
falls through to the `PF_Mirrored` test and, absent that flag too, draws as an ordinary opaque
textured face (today's `render.rs` behavior — correct ONLY for this fallback, not the general
case). Recursion (a backdrop face inside its own sky room) shares ONE per-frame depth counter with
`PF_Mirrored`/`PF_Portal`, capped at 3. `PF_Unlit` is irrelevant to any of this.

**Critical correction from the spec review, now load-bearing for this design:** `AZoneInfo.SkyZone`
is NOT an authored, per-zone, T3D-readable property. `Engine.u`'s `ZoneInfo` declares
`var skyzoneinfo SkyZone;` (no editor category — never exposed, never in a T3D) and resolves it at
level start via `LinkToSkybox()`: a level-global `foreach AllActors(class'SkyZoneInfo', T) if
(T.bHighDetail == Level.bHighDetailMode) SkyZone = T`, run from every `ZoneInfo`'s (and, since
`LevelInfo extends ZoneInfo`, every unzoned region's) `PreBeginPlay()`. Every zone in a level
therefore ends up pointing at the SAME sky actor. **There is no per-face or per-zone resolution
step to implement — there is exactly one sky actor (or none) per level.** A design built around
"resolve the face's zone, then read its SkyZone" (the first draft of this spec) is a permanent
no-op: that property is always `None` on anything read from a trunk.

## Design — implementation plan sketch

### 1. Finding the sky actor (Python, `uedcli/preview_native.py`'s `build_scene`)

Port `LinkToSkybox`'s OUTCOME, not the per-zone mechanism it happens to be spelled as: scan the
level's actors for `Engine.SkyZoneInfo` instances (a class-descent check, same kind
`resolve_zone_actors`-style code elsewhere in this codebase already does against `ClassIndex`), and
if more than one exists, pick by `bHighDetail` (prefer one with `bHighDetail=True` if any — `level
photo` has no runtime "client detail setting" to match against, so this is a deterministic stand-in
for the real engine's `Level.bHighDetailMode` comparison; document the simplification, it's a
one-line implementation-detail decision, not a design fork). Zero results → no sky, every
`PF_FakeBackdrop` face falls back to today's flat-texture behavior (exactly the real engine's own
NULL-`SkyZone` case). One actor (the overwhelmingly common real-content case) → that's the sky.
This runs ONCE per shot (or once per trunk if `build_scene`'s output is reused across shots in one
`level photo` invocation — check which; either is fine since the sky actor doesn't move).

`uedcli/native/materialize.py`'s `resolve_zone_actors` is NOT the right tool here (that resolves
PER-ZONE actors; this is level-global) — do not force-fit it; write the small, level-global
`SkyZoneInfo` scan directly.

### 2. Data crossing the FFI (`uedcli-native/src/lib.rs`, `render.rs`)

**No new per-poly field is needed.** `RenderPoly.poly_flags` already crosses the FFI and already
carries `PF_FakeBackdrop` (0x80) exactly like `PF_Mirrored`/`PF_Translucent` do today — Rust can
read it the same way. What's missing is the SKY CAMERA itself: the sky actor's `Location` (a
`Vec3`) and its `Rotation`, expressed as a basis the SAME way the existing `Camera` struct already
carries `forward`/`right`/`up` (Python computes these via `rotation.euler_to_matrix_uu` per this
codebase's own rule that Rust never converts FRotator angles). Add this as a new, OPTIONAL
parameter to the render entry point (`render_frame` in `lib.rs`, threaded into `render_impl`) —
`Option<(Vec3, [Vec3; 3])>` (location + basis), `None` when `build_scene` found no sky actor. It
must be a PER-CALL parameter, not baked into the poly list: the composed sky-camera basis depends
on the VIEWER's rotation (divided by the sky's own), which is only known per `render_frame` call
(one call per shot), not at `build_scene` time (which runs once and is shared across shots in a
batch — check `preview_native.py`'s actual call structure to confirm this timing, per the design
note above).

The rotation compose itself is pure matrix algebra once both bases are already matrices (viewer's,
from the existing per-shot `Camera`; sky's own, computed once in Python) — `SkyCoords /=
SkyZone->Rotation` is right-multiplication by the sky rotation matrix's INVERSE, and a rotation
matrix's inverse is its transpose, so this needs no new FRotator handling anywhere: `sky_camera_basis
= viewer_basis · sky_basis^T` (confirm operand order against the spike's `.asm` — `FCoords::
operator/=` divides the CALLING object by the argument, so get the multiplication side right, not
just "some transpose is involved somewhere"). Whether this compose happens Python-side (recompute
per shot, pass the final basis) or Rust-side (pass both bases, compose in `render_impl`) is a
plan-level implementation choice, not a design fork — either keeps the "no FRotator math in Rust"
rule intact since both bases are already matrices by the time Rust would see them.

### 3. Dispatch order (`render.rs`'s `blend_mode`)

Mirror the real engine's if/else-if chain exactly, closing the review's "NULL-fallback contradicts
mutual-exclusion" and "no routing point exists" findings in one move — add a `has_sky: bool`
parameter (or equivalent) so a `PF_FakeBackdrop` face with NO resolvable sky actor falls through to
the mirror test, exactly like the real engine's NULL-`SkyZone` case:

```
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

`blend_mode` is called from two sites today (`render_impl` and `group_mirror_clusters`) — both must
receive `has_sky` so a `PF_FakeBackdrop|PF_Mirrored` face is consistently classified as `Backdrop`
in both places (otherwise `group_mirror_clusters` would still cluster it as a mirror in addition to
`render_impl` treating it as backdrop). `PF_Portal` is not handled by `blend_mode` today and stays
out of scope for this item (it's a backface-cull exemption only, `light.rs`'s `light_in_front`).

### 4. The sky sub-render itself

Because there is exactly ONE sky actor per level (§1), there is exactly ONE sky sub-render per
shot — no per-face or per-zone clustering/dedup machinery is needed (the first draft of this spec
mis-framed multi-face dedup as a correctness requirement; with one global sky actor it never
arises). Render the WHOLE scene once from the sky camera (same `render_impl` recursion the mirror
path already uses, at `recursion_depth + 1`), with NO zone/BSP filtering — `render.rs`'s rasterizer
has no zone-culling concept anywhere today (confirmed: `RenderPoly` carries no zone data, and
`preview_native.py`'s poly-building already discards each `BspNode`'s zone), and the mirror path
sets the precedent of rendering the whole scene (clipped only by its own reflection plane, which a
sky render doesn't even need — there's no "wrong side" to clip away for a camera sitting inside a
sealed sky room). Document this as a known simplification (parity with how mirror already works),
not a blocker: a sky room that isn't actually sealed from the rest of the level could leak, exactly
as an unsealed mirror wall already can today. Every `Blend::Backdrop` poly then samples this ONE
buffer at its own screen pixel — same mechanism `render_poly`'s existing `Some(&secondary)` mirror
path already implements, minus the reflection-specific transform/clip and the translucent-tint
combination logic (a backdrop face doesn't reflect the scene, it just shows what's behind it, so no
per-poly plane math is needed — every backdrop poly across the whole shot shares the identical
sub-render).

### 5. Recursion (owner-approved: adopt the real shared cap-3)

Generalize `render.rs`'s existing `mirror_depth: u32` parameter (currently threaded through
`render_impl`, capped at 1 — `if mode == Blend::Mirror && mirror_depth > 0 { mode = Blend::Opaque;
}`, mirror clusters only render `if mirror_depth == 0`) into a shared `recursion_depth: u32`
covering BOTH mirror and backdrop, capped at 3 to match the real engine. This is a real, intended
behavior change to EXISTING mirror rendering:

- `render.rs`'s module doc (currently: "Capped at one reflection deep... a hall-of-mirrors is a
  real UE1 case this draft renderer does not attempt") needs updating — a hall-of-mirrors up to 3
  deep IS now attempted.
- The existing test `facing_mirrors_do_not_hang_and_cap_recursion` needs updating for the new cap
  (still must terminate — 3 is still finite — but the specific "caps at 1" assertion changes).
- `docs/reference/level/photo.md`'s "one bounce deep" mirror description needs updating to say 3,
  and to add the backdrop behavior.
- Cost is real and multiplicative: `group_mirror_clusters`'s own doc already flags no per-cluster
  cap exists, and each recursion level re-renders the (clipped) scene once per cluster — a
  level with mirrors AND a sky could now do meaningfully more work per shot than today. Not a
  blocker (this is `level photo`, an offline draft tool, not a real-time budget), but worth a perf
  spot-check against a real mirror-heavy level (`Terraniux.unr`, already used as the mirror-cluster
  reference case) before merging.

### 6. `ShowFlags` — commit to the game's behavior, no environment branching

The real engine additionally gates backdrop/mirror/portal frames on `ShowFlags & 0x800` (in-game:
always on; editor: off until "Realtime Preview" is toggled). `level photo --native` is a screenshot
tool with no equivalent runtime setting and no "am I the editor or the game" distinction to make —
per this project's own convention against environment-dependent behavior, it should behave as if
this gate is always satisfied (the game's behavior), unconditionally. No new flag, no config knob.

## Edge cases

- **No `SkyZoneInfo` in the level**: every `PF_FakeBackdrop` face falls back to today's flat-texture
  render (§1) — the real engine's own behavior for this case, not a punt.
- **Multiple `SkyZoneInfo` actors**: pick by `bHighDetail` (§1's simplification) — a plan-level
  detail, not blocking.
- **A face with both `PF_FakeBackdrop` and `PF_Mirrored`**: `blend_mode`'s ordering (§3) makes this
  automatic — backdrop wins whenever a sky actor resolves, falls through to mirror otherwise,
  exactly matching the real engine.
- **Recursion** (a backdrop face visible from within the sky room itself, or nested
  mirror/backdrop combinations): the shared `recursion_depth` cap-3 (§5) bounds this the same way
  it now bounds mirror-in-mirror.
- **Sky room not actually sealed**: whole-scene rendering (§4) can leak world geometry into the sky
  view, same class of issue mirror already has for an unsealed mirror wall — not a regression this
  item introduces, a pre-existing renderer limitation it inherits.

## Tests

- **Rust unit tests** (`render.rs`'s own `#[cfg(test)]` block, mirroring its existing
  mirror-behavior tests): `blend_mode`'s dispatch order (backdrop-with-sky wins over mirror;
  backdrop-without-sky falls through to mirror); the recursion cap actually stops at 3 for a
  backdrop-only, mirror-only, and MIXED backdrop/mirror recursive case; no-parallax (a moved camera
  produces an unchanged sky sub-render vantage; only rotation changes it).
- **A synthetic fixture with a real `SkyZoneInfo` actor** (not a `SkyZone=` property — that field
  can't be authored, per the corrected mechanism) — `uedcli/tests/test_native_roundtrip.py` already
  splices synthetic zone actors into a T3D fixture (`_room_t3d()`) for other zone-actor tests; a
  `PF_FakeBackdrop`-flagged surface plus an `Engine.SkyZoneInfo` actor is the same pattern.
  - MUST include a fixture with a **non-zero** `SkyZoneInfo.Rotation`, not just the common
    zero-rotation case — a zero rotation hides a divide-vs-multiply mistake entirely (§2's
    "get the operand order right" note), so a passing zero-rotation-only test proves nothing about
    that formula.
- Existing `level photo`/`preview_native` goldens must stay unchanged for every level with NO
  `PF_FakeBackdrop` surf AND no change in mirror recursion depth reached (i.e. levels whose mirrors
  never recursed past depth 1 anyway are unaffected by §5's cap change).
- Real corpus check once implemented: `dev/games`'s showcase trunks and `uned/UnrealAssets`'s
  retail Unreal-1 levels (`SkyTown`/`SkyBase`/`TheSunspire` are plausible skybox-room candidates by
  name) for a real-content regression shot.

## Docs

Update `docs/reference/level/photo.md` in the same change (this project's convention: the matching
user-facing reference page changes alongside the behavior): the mirror recursion depth (1 → 3) and
a new paragraph on `PF_FakeBackdrop` rendering, matching the style of the existing mirror/masked/
translucent paragraphs there.

## Open questions

None. Direction, the underlying engine facts, and the two previously-open design forks (recursion
cap; where zone/sky resolution belongs) are all settled above.
