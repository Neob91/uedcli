# Spec DRAFT — PF_FakeBackdrop support in `level photo --native`

Status: draft for owner review. The recommended v1 treatment (Option A below) needs an explicit
yes — see `questions/v1-visual-treatment.md`. This is a pre-spec: it settles what's known, lays out
the options, and stops short of a plan until that question is answered.

## Goal

Give `PF_FakeBackdrop` surfaces a better draft-tier render than "draw the assigned texture flatly,
like any other opaque face" — the current, deliberate v1 behavior — without pretending to full
byte-for-byte sky-zone parallax fidelity, which this repo has no RE grounding for yet (see
"Real UE1 semantics" below).

## Current state

- **The bit**: `PF_FakeBackdrop = 0x80` (bit 7). Settled and consistent everywhere it appears:
  `uedcli/query.py:19` (`PF_NAMES`, the CLI-facing flag name `fakebackdrop`), `uedcli-native/src/light.rs:25`
  (`PF_FAKE_BACKDROP`), `dev/docs/unrealed/leveldesign/kb/textures.md:40`,
  `dev/docs/unrealed/leveldesign/kb/asset-pipeline.md:75`. No conflicting value found.
- **Current renderer behavior**: `level photo --native` does CSG/UV work in Python
  (`uedcli/preview_native.py`) and passes flat `RenderPoly`s (carrying the merged `poly_flags`)
  across the FFI to Rust, which owns every cull/blend/draw decision
  (`uedcli-native/src/render.rs`). No `PF_FAKE_BACKDROP` constant exists in `render.rs` today — a
  FakeBackdrop face is not special-cased at all; it draws through the same opaque path as any
  textured face. Confirmed in three independent places: `docs/reference/level/photo.md`'s "sky
  projection do not render (draft tier)", `spikes/2026-07-16-native-preview-anchor/perf.md:38`
  ("correct v1 behavior: `PF_FakeBackdrop` renders its texture like any face; no sky-zone
  projection"), and the original `de-containerization-follow-on-spec-items/spec.md:242-243`, which
  explicitly scoped sky-zone projection OUT of v1.
- **The pattern other flags use** (what a change here would follow): `render.rs:303-340`
  (`render_poly`) backface-culls unless `poly_flags & (PF_TwoSided | PF_Portal) != 0`
  (`light_in_front`, `uedcli-native/src/light.rs:77-80`) — a face draws only from the side its
  normal faces, with `PF_TwoSided`/`PF_Portal` exempted. Blend-mode dispatch (`render.rs:120-149`,
  `blend_mode`) reads `poly_flags` for `PF_Translucent`/`PF_Modulated`/`PF_Mirrored` and routes the
  poly into the opaque, blended, or one-bounce-mirror pass. `RenderPoly.poly_flags`
  (`render.rs:63-67`) already carries every flag needed — no new FFI plumbing required to add a
  `PF_FakeBackdrop` branch.
- **The lightmap-skip mask is a separate, already-correct, disassembly-verified use of this same
  bit** (`light.rs:33-46`, `PF_NO_LIGHTMAP = PF_UNLIT | PF_INVISIBLE | PF_FAKE_BACKDROP`, verified
  against `Editor.dll 0x100a6031`/`0x100a4ae7`): a FakeBackdrop surf gets no lightmap record. That's
  the editor's lighting *build*, unrelated to the rasterizer's draw path — nothing to change there.

## Real UE1 semantics — what's known vs. not

- **Tutorial-corpus level** (📖, not disassembly-verified): a `PF_FakeBackdrop` surface "draws the
  skybox through this surface" and needs a companion `Unlit` flag or "the sky draws
  lit/wrong" (`dev/docs/unrealed/leveldesign/kb/textures.md:40,61`). The real mechanism is a sealed
  sky room elsewhere in the map holding a `SkyZoneInfo` actor as the parallax viewpoint
  (`docs/leveldesign/general/recipes/skybox.md`) — also tutorial-level knowledge, not RE.
- **No RE/disassembly documentation of the actual sky-projection algorithm exists in this repo.**
  Grepped `dev/docs/unrealed/*.md` and `dev/docs/unrealed/unrealscript/` for `SkyZoneInfo`/
  `parallax`/"sky zone": zero hits. How `URender` actually draws the `SkyZoneInfo`'s view through a
  `PF_FakeBackdrop` surf — parallax formula, whether it's a second scene render like the mirror
  path, camera-relative offset, zone-crossing behavior — is **not established** here. (General
  UE1 familiarity suggests something like rendering the sky zone's own geometry from the
  `SkyZoneInfo`'s fixed viewpoint, clipped to the backdrop surface's screen footprint, at
  effectively infinite depth — but that's unverified against this repo's own evidentiary bar and
  must not be treated as fact without a live probe, per `NATIVE-MATERIALIZE.md`'s standard.)
- **Consequence**: a *faithful* implementation is a real RE project (a live UED22/game probe of a
  skybox level), not a spec-and-build task. This spec's options below separate the CHEAP,
  RE-free draft improvements (available now) from the FAITHFUL option (needs new RE work first).

## Design — options

### A. Render the sky zone's own geometry as the backdrop, unlit, no parallax (recommended v1)

Treat a `PF_FakeBackdrop` face as a second, small render: reuse the existing one-bounce mirror
machinery's shape (`render.rs`'s `Blend::Mirror` path already re-renders the scene from a
transformed camera and composites the result onto the source face) but aim the second camera from
the level's `SkyZoneInfo` actor (found by resolving the surf's containing zone, same zone-actor
resolution `uedcli/native/materialize.py`'s `resolve_zone_actors` already does for the
native-materialize campaign) instead of a mirror-reflected camera, and composite it onto the
`PF_FakeBackdrop` face's screen footprint unlit (skip the lumel-bake lighting pass for this
composite, matching `Unlit`'s existing meaning elsewhere in the renderer).

This is NOT true parallax (the sky-zone camera doesn't track the main camera's relative motion
within the zone — it renders from a single fixed vantage each shot) and is NOT claimed as faithful
— it's a draft-tier approximation in the same spirit as the existing "procedural texture gets one
static draft frame" precedent (`docs/reference/level/photo.md`'s `--faces textured` section). But it
replaces a flat, static, obviously-wrong texture with an actual rendering of what's behind the
backdrop, which is a real visual improvement for any level with a built-out sky room.

Tradeoff: needs the same per-face "resolve this face's zone → find its `SkyZoneInfo`" step
`native/materialize.py` already has a pattern for, plus one extra `render_poly` sub-render per
FakeBackdrop face per shot (bounded cost — mirrors already pay this once per mirrored face). No new
RE work required to ship this.

### B. Cull FakeBackdrop faces entirely (treat as invisible)

Simplest possible change: skip drawing a `PF_FakeBackdrop` face altogether, same as `PF_Invisible`
already works (`uedcli/preview_native.py:40`, `PF_INVISIBLE`). Whatever is geometrically behind the
face (usually nothing, since the sky room is sealed) shows through as background — which for most
real levels means the shot's clear-color / empty-world background, not a rendering of the sky room.

Tradeoff: trivial, no new RE work, no per-face sub-render cost — but strictly *removes* information
a viewer currently has (the flat texture, however wrong, at least fills the space) rather than
improving it. Reasonable fallback if A's implementation cost isn't justified yet, but not a real
visual upgrade.

### C. Full faithful sky-zone parallax projection (future work, needs an RE spike first)

The real engine mechanism, once established by a live probe (same method as this campaign's other
RE breakthroughs — a `winedbg`-instrumented UED22/game capture of a skybox level, `NATIVE-MATERIALIZE.md`'s
established playbook). Out of scope for this item; file as its own RE spike
(`dev/docs/rules/spikes.md`) if the owner wants full fidelity later. Options A/B do not block or
foreclose this — A's sky-zone-camera plumbing (zone resolution, unlit sub-render) is a reusable
foundation if C is later attempted.

### Recommendation

Ship **A**. It is the only option that actually shows the player something resembling the real sky
room, costs no new RE work, and reuses machinery (`Blend::Mirror`'s sub-render, zone-actor
resolution) already proven in this codebase. Keep **C** as a filed-later RE spike, not blocking.
**B** is the fallback only if A's implementation turns out to need more than the mirror-reuse
sketched above.

## Edge cases

- A `PF_FakeBackdrop` face whose zone has no resolvable `SkyZoneInfo` (malformed/incomplete level,
  or a level that never sets one) — must degrade to Option B's behavior (skip/cull) for that face
  specifically, not error the whole shot. `level materialize`'s own rule against silent fallbacks
  (`CLAUDE.md` "No fallbacks") applies to whole-command behavior, not to a per-face draft-render
  degradation already documented as a known simplification (same class as the existing "procedural
  class nothing draws renders flat red" rule in `docs/reference/level/photo.md`).
- A mirrored `PF_FakeBackdrop` face (both flags set) — confirm which sub-render wins, or whether the
  two compose (skybox seen inside a mirror). Needs a decision during planning, not blocking the spec.
- Recursion/cost bound: if the sky zone itself contains a `PF_FakeBackdrop` face (a backdrop seen
  from within the sky room), cap sub-render depth the same way the existing mirror path caps mirror
  recursion ("a mirror seen inside another mirror's reflection draws as a plain textured face
  instead of recursing again," `docs/reference/level/photo.md`) — apply the identical one-level cap.
- `Unlit` interaction: real UE1 requires `Unlit` alongside `FakeBackdrop` or "the sky draws
  lit/wrong" (tutorial-corpus fact, `textures.md:40`). Option A renders the sub-scene unlit
  regardless of whether the surf's own `Unlit` bit is set, matching intended real-world usage; a
  level author who forgot `Unlit` on their FakeBackdrop surf gets the same result either way (v1
  doesn't need to reproduce the "renders lit/wrong" mistake case).

## Tests

- A synthetic two-room fixture (a small enclosed level + a sealed sky room with a `SkyZoneInfo` and
  a couple of brushes/textures) exercising Option A end to end: one `PF_FakeBackdrop` face renders
  the sky room's geometry, not its own assigned texture.
- The zone-with-no-`SkyZoneInfo` degrade-to-cull edge case, pinned as its own test.
- Existing `level photo`/`preview_native` goldens must stay unchanged for every level with NO
  `PF_FakeBackdrop` surf (this change must be a no-op off that flag).
- If real corpus content already has skybox rooms (check `dev/games`'s showcase trunks and
  `uned/UnrealAssets`'s retail Unreal-1 levels — several, e.g. `SkyTown`/`SkyBase`/`TheSunspire`,
  are plausible candidates by name), add one real-content regression shot once A is built.

## Open questions

- `questions/v1-visual-treatment.md` — ship Option A (sky-zone sub-render) or B (cull) as v1? Blocks
  planning either way; B can ship first as a stopgap with A following if the owner wants staged
  delivery instead.
