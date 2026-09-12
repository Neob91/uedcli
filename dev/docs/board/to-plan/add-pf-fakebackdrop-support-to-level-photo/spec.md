# Spec — PF_FakeBackdrop support in `level photo --native`

Status: **RE spike done (2026-09-12)** — `dev/docs/spikes/2026-09-12-pf-fakebackdrop-re/spike.md`
answers all five owner-directed RE questions from static disassembly, pinned as 36 byte-exact
regression assertions (12 as pytest in `uedcli/tests/test_engine_facts.py::test_pf_fakebackdrop_*`,
the full 36 re-runnable via the spike's own harness script). Next action is a plan, not more spec —
this moves `to-spike` → `to-plan`.

## Goal

Give `PF_FakeBackdrop` surfaces a **faithful** render in `level photo --native`, matching what
UED22/the real engine actually does. Current behavior (draws the assigned texture flatly, like any
other opaque face) is the real engine's behavior ONLY when the surf's zone has no `SkyZoneInfo` —
for every other case it's wrong, per the confirmed mechanism below.

## Owner's decision (2026-09-12)

RE the real engine behavior instead of shipping an approximation (all four of that day's questions
pointed the same way — see the spike for the answers); bumped p3 → **p1**.

## Confirmed mechanism (from the spike — cite it, don't re-derive)

`URender::OccludeBsp` (`render.dll +0x18e10`) tests `PolyFlags & PF_FakeBackdrop` first in an
if/else-if chain (before `PF_Mirrored`, then `PF_Portal`). On a match:

1. The face is **never drawn** — same skip target `PF_Invisible` uses.
2. Resolve the face's zone actor, read its `SkyZone` field (`AZoneInfo +0x278`). **NULL → fall
   through** to the `PF_Mirrored` test (today's flat-texture behavior is this fallback, and only
   this fallback).
3. Non-NULL → build a child scene: camera at the `SkyZoneInfo` actor's `Location`, using the
   VIEWER's rotation composed with the sky zone's own `Rotation` — **no parallax** (translation is
   discarded, not carried over). Render it (`CreateChildFrame` + the normal `OccludeFrame`/
   `DrawFrame` recursion) clipped to the backdrop face's screen footprint.
4. `CreateChildFrame` de-dupes: multiple `PF_FakeBackdrop` faces resolving to the same zone under
   one parent share ONE child render (spans merged), not one render per face.
5. `PF_Mirrored` on the same face is moot if `PF_FakeBackdrop` took its branch (mutually exclusive,
   backdrop wins) — only reachable as a plain mirror if that face's `SkyZone` is NULL.
6. `PF_Unlit` is irrelevant to this branch — no lighting decision happens for a face that isn't
   drawn; the child scene's own geometry lights normally.
7. Recursion (a backdrop face visible from within its own sky zone) is guarded by a **shared,
   per-frame depth counter** (`FSceneNode::Recursion`, cap 3) — the SAME counter/cap
   `PF_Mirrored`/`PF_Portal` frames use, not a separate one.

## Design — implementation plan sketch

Reuse `render.rs`'s existing `Blend::Mirror` shape (the only "render the scene again from another
vantage, composite onto the source face" mechanism already in this codebase) as the skeleton, but
drive it from the confirmed mechanism above rather than mirror math:

- Add `PF_FAKE_BACKDROP = 0x80` to `render.rs` (mirroring `light.rs`'s existing constant) and test it
  **before** the existing `PF_Mirrored`/`PF_Portal` checks in whatever dispatch `render_poly`/
  `blend_mode` do today, matching the real engine's if/else-if order (step 5 above — this only
  matters for the rare both-flags-set case, but it's a one-line ordering fix to get right the first
  time).
- Zone resolution: reuse `uedcli/native/materialize.py`'s `resolve_zone_actors` pattern to find the
  face's zone, then read that zone's `SkyZone` reference the same way `AZoneInfo.SkyZone` is
  resolved elsewhere in this codebase's property-reading code (check `uprops`/`classdefaults` for
  the existing zone-actor-property read pattern before writing a new one).
- NULL `SkyZone` → today's existing flat-texture path, unchanged (it's now KNOWN correct for this
  case, not just a placeholder).
- Non-NULL → a sub-render: camera at `SkyZone.Location`, basis = compose(viewer rotation, `SkyZone
  .Rotation`) — no camera-position offset at all (this is simpler than the mirror path, which does
  need a reflected position; backdrop only needs a rotation compose and a fixed position). Clip to
  the face's screen footprint the same way the mirror pass already clips its sub-render.
- De-dup (step 4): cache the sub-render per `(zone, parent frame)` within one shot instead of
  per-face, same as `CreateChildFrame`'s reuse loop — needed for correctness (not just performance)
  once more than one backdrop face shares a zone, or the sky renders as many separate stills that
  won't tile at their shared screen boundary.
- Recursion cap (step 7): thread a depth counter through the sub-render call, shared with whatever
  counter/parameter already caps `PF_Mirrored` recursion in `render.rs` (check whether one already
  exists there, or whether the "capped at one reflection deep" comment in `render.rs`'s module doc
  is enforced by a literal counter or just an implicit non-recursive call structure — if the latter,
  this item needs to ADD the real shared counter, which the real engine has and today's mirror code
  apparently doesn't).

This section is a plan SKETCH for whoever writes the actual task-by-task plan (`writing-plans`
skill) — it is not itself the plan.

## Tests

- The 12 `test_pf_fakebackdrop_*` engine-facts regressions already landed (this spike) stay green
  regardless of implementation — they pin the REAL ENGINE's behavior via the binaries, not this
  codebase's port of it.
- A synthetic two-room fixture (enclosed level + sealed sky room with `SkyZoneInfo`) exercising the
  confirmed mechanism end to end, once implemented: camera-in-sky-zone-with-no-parallax, the
  NULL-`SkyZone` fallback, the mutual-exclusion-with-Mirrored case, and the shared-zone de-dup.
- Existing `level photo`/`preview_native` goldens must stay unchanged for every level with NO
  `PF_FakeBackdrop` surf (this change must be a no-op off that flag).
- Real corpus content check once implemented: `dev/games`'s showcase trunks and
  `uned/UnrealAssets`'s retail Unreal-1 levels (`SkyTown`/`SkyBase`/`TheSunspire` are plausible
  skybox-room candidates by name) for a real-content regression shot.

## Open questions

None. Direction and the underlying engine facts are both settled; next step is a plan.
