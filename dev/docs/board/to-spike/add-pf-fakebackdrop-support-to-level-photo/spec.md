# Spec — PF_FakeBackdrop support in `level photo --native`

Status: **direction confirmed by the owner (2026-09-12)** — go faithful, not draft-approximate.
Next action is the RE spike below, not a plan; this stays in `to-spec`/becomes a `to-spike` item
until the spike lands the facts, then a plan can be written against real evidence instead of the
inferred sketch that follows.

## Goal

Give `PF_FakeBackdrop` surfaces a **faithful** render in `level photo --native`, matching what
UED22/the real engine actually does — not an approximation. Current behavior (draws the assigned
texture flatly, like any other opaque face) is a known, documented v1 simplification; this item
replaces it with the real mechanism, established by RE, not guessed.

## Owner's decision (2026-09-12)

Asked four questions; all four answers point the same way — RE the real engine behavior instead of
shipping an approximation, and treat it as high priority:

- **V1 treatment**: invest in the RE spike now (rejected the cheap draft approximation in the
  original draft of this spec, Option A/B below).
- **Mirrored + FakeBackdrop combo**: RE UED22 to see how it actually resolves this, rather than
  picking a convenient default.
- **Missing `SkyZoneInfo`**: do what UED22 does — also an RE question, not a policy call for us to
  invent.
- **Priority**: bumped p3 → **p1**.

This settles the *direction*; it does not yet answer the *facts* — those are exactly what the spike
below has to establish.

## What's already known (from the original draft spec)

- **The bit**: `PF_FakeBackdrop = 0x80` (bit 7). Settled and consistent everywhere it appears:
  `uedcli/query.py:19` (`PF_NAMES`, the CLI-facing flag name `fakebackdrop`),
  `uedcli-native/src/light.rs:25` (`PF_FAKE_BACKDROP`),
  `dev/docs/unrealed/leveldesign/kb/textures.md:40`,
  `dev/docs/unrealed/leveldesign/kb/asset-pipeline.md:75`. No conflicting value found.
- **Current renderer behavior**: `level photo --native` does CSG/UV work in Python
  (`uedcli/preview_native.py`) and passes flat `RenderPoly`s (carrying the merged `poly_flags`)
  across the FFI to Rust, which owns every cull/blend/draw decision
  (`uedcli-native/src/render.rs`). No `PF_FAKE_BACKDROP` constant exists in `render.rs` today — a
  FakeBackdrop face draws through the same opaque path as any textured face, confirmed in
  `docs/reference/level/photo.md`, `spikes/2026-07-16-native-preview-anchor/perf.md:38`, and the
  original `de-containerization-follow-on-spec-items/spec.md:242-243` (explicitly scoped sky-zone
  projection OUT of v1).
- **The pattern other flags use** (a template for wiring in whatever the spike finds):
  `render.rs:303-340` (`render_poly`) backface-culls unless
  `poly_flags & (PF_TwoSided | PF_Portal) != 0` (`light_in_front`, `light.rs:77-80`). Blend-mode
  dispatch (`render.rs:120-149`, `blend_mode`) reads `poly_flags` for
  `PF_Translucent`/`PF_Modulated`/`PF_Mirrored` and routes into the opaque, blended, or
  one-bounce-mirror pass. The mirror pass is the closest existing analog to a sky-zone sub-render:
  it already re-renders the scene from a transformed camera and composites onto the source face.
  `RenderPoly.poly_flags` (`render.rs:63-67`) already carries every flag needed — no new FFI
  plumbing required regardless of what the spike finds.
- **The lightmap-skip mask is a separate, already-correct, disassembly-verified use of this same
  bit** (`light.rs:33-46`, `PF_NO_LIGHTMAP = PF_UNLIT | PF_INVISIBLE | PF_FAKE_BACKDROP`, verified
  against `Editor.dll 0x100a6031`/`0x100a4ae7`) — the editor's lighting *build*, unrelated to the
  rasterizer's draw path. Nothing to change there.
- **Tutorial-corpus level, not disassembly-verified**: a `PF_FakeBackdrop` surface "draws the
  skybox through this surface" and needs a companion `Unlit` flag or "the sky draws lit/wrong"
  (`dev/docs/unrealed/leveldesign/kb/textures.md:40,61`). The real mechanism is a sealed sky room
  elsewhere in the map holding a `SkyZoneInfo` actor as the parallax viewpoint
  (`docs/leveldesign/general/recipes/skybox.md`) — also tutorial-level knowledge, not RE.
- **No RE/disassembly documentation of the actual sky-projection algorithm exists in this repo**
  (grepped `dev/docs/unrealed/*.md` and `dev/docs/unrealed/unrealscript/` for `SkyZoneInfo`/
  `parallax`/"sky zone": zero hits). This is the gap the spike closes.

## RE spike scope

Method: the same live-probe playbook this campaign already uses elsewhere (`NATIVE-MATERIALIZE.md`'s
`winedbg`-instrumented UED22/game capture — see e.g. the ordering-algorithm and lighting-bake RE work
under `dev/docs/board/to-build/native-materialize/` for precedent). Read `dev/docs/rules/spikes.md`
before starting: **run it to completion, no deferred questions**, commit the harness under
`dev/docs/spikes/<date>-pf-fakebackdrop-re/`, pin every checkable finding with a regression test.

Questions the spike must answer, all against a live UED22 (or in-game) capture of a real skybox
level — not inferred from source-reading or general UE1 knowledge:

1. **The core projection.** How does `URender` draw a `SkyZoneInfo`'s view through a
   `PF_FakeBackdrop` surface? Is it a second scene render (like the mirror path) or a different
   mechanism entirely? What's the actual parallax formula — is the sky-zone camera's position
   locked, offset from the main camera, or scaled by some factor? Does it track camera rotation
   only, or position too?
2. **Mirrored + FakeBackdrop combo.** When a face carries both `PF_Mirrored` and
   `PF_FakeBackdrop`, which one does the engine actually apply — does one flag take precedence, do
   they compose (sky room rendered, then that result mirrored), or is this combination simply not
   meaningful in practice (e.g. never occurs in real content, or the engine treats it as one flag
   silently overriding the other via `PolyFlags` bit-processing order)?
3. **Missing `SkyZoneInfo`.** What does the real engine do when a `PF_FakeBackdrop` surface's zone
   has no `SkyZoneInfo` actor (or an unreachable/misconfigured one)? Renders nothing? Falls back to
   the raw texture (i.e. today's behavior might already BE what it does in this case)? Crashes/logs
   a warning? This determines our error-handling policy directly from evidence, not convention.
4. **`Unlit` interaction** — confirm or correct the tutorial-corpus claim that `FakeBackdrop`
   without `Unlit` "renders lit/wrong"; if so, what does "wrong" actually look like (useful for
   deciding whether v1 needs to reproduce the mistake-case too, or can assume well-formed content).
5. **Recursion**: does a `PF_FakeBackdrop` face inside the sky zone itself (a backdrop seen from
   within the sky room) recurse, cap, or is this simply not valid content the engine has to handle?

## Design — implementation sketch (provisional, pending spike facts)

Not a plan — a placeholder shape so the spike has a concrete target to confirm or overturn. The
mirror-render pattern (`render.rs`'s `Blend::Mirror`, aiming a second camera and compositing the
sub-render onto the source face) is the most likely reusable shape for whatever the spike finds,
given it is the only existing "render the scene again from another vantage and composite" mechanism
in this codebase — zone-actor resolution to find the `SkyZoneInfo` would reuse
`uedcli/native/materialize.py`'s `resolve_zone_actors` pattern. **Do not build against this sketch
until the spike confirms or replaces it** — per the owner's decision above, guessing the mechanism
and shipping an approximation is explicitly what we're avoiding here.

## Tests

- Whatever the spike finds gets a regression test per `dev/docs/rules/spikes.md` (an engine-facts
  assertion, e.g. `test_engine_facts.py`, back-referencing the spike).
- A synthetic two-room fixture (enclosed level + sealed sky room with `SkyZoneInfo`) exercising the
  confirmed mechanism end to end, once implemented.
- Existing `level photo`/`preview_native` goldens must stay unchanged for every level with NO
  `PF_FakeBackdrop` surf (this change must be a no-op off that flag).
- Real corpus content check once implemented: `dev/games`'s showcase trunks and
  `uned/UnrealAssets`'s retail Unreal-1 levels (`SkyTown`/`SkyBase`/`TheSunspire` are plausible
  skybox-room candidates by name) for a real-content regression shot.

## Open questions

None outstanding on direction — see "Owner's decision" above. The RE spike's five questions (above)
are the remaining work, not owner decisions.
