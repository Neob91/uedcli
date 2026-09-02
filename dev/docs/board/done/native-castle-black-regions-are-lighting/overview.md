+++
priority = "p?"
kind = "debug"
summary = "CORRECTED and RESOLVED: the black regions were a zone mis-assignment in zones.rs, not lighting and not a sky/backdrop gap."
+++

# Native-castle "black no-sky regions" are LIGHTING, not sky/backdrop/zones (2026-07-17)

> **CORRECTED + RESOLVED 2026-07-18.** This 2026-07-17 "it's lighting" premise was **wrong** — it was
> disproven by §19 of `sections/20-lighting-bake.md` (native vs editor render-DARK counts are 54 vs
> 54, lightmaps value-for-value equal; the black is present, lit geometry the game does not DRAW) and
> then FIXED in `zones.rs` (`sections/70-zones-portalization.md §9` + `20-lighting-bake.md §20`): node
> Pass D was a subtree-descent guess mis-zoning ~450 walls `(0,0)`, and native wrongly wrote
> `FBspSurf.iZone` (editor leaves it 0). After the fix the three interior poses hit editor parity
> (s76 32.1 %→3.8 %, s34/s07 →0.0 %). Residual: **s69 (water pool) ~20 %** is the pre-existing
> water-portal/pool-pit gap (separate item), NOT lighting. Collision unchanged (`phys=1`).

Investigated the reported defect: `NativeCastle.dx` renders large BLACK areas in-game where
`Test_Castle.dx` (editor) shows lit surfaces (poses s57 `at:400,400,20;rot:25,225`, s69
`at:0,455,10;rot:-15,90`, s76 `at:0,0,120;rot:-89,0`; A/B pairs `_scratch/shots/ab80/pairs/`).
The task hypothesised a **sky/backdrop / zone-portalization coverage gap**. **That premise is not
borne out — the geometry, zones, SkyZone, and FakeBackdrop are all correct and complete.** The
black is **unlit geometry** (a lightmap-bake defect, `light.rs` — owned by the concurrent lighting
line). Evidence (all offline, repro scripts under the scratchpad / `_scratch/shots/nat_flat/`):

- **Geometry is complete.** The native software rasterizer (`preview_native`, same CSG core + same
  built `Model`, **no lighting, no zone cull**) renders s69 and s76 with **full coverage** — the
  entire ground plane (s69) and the whole room floor+walls+crate (s76), zero holes. The in-game
  black areas have geometry there.
- **Zones are membership-correct.** Native's interior/water/sky partition matches the editor
  (renumbered): interior zone conn `0x6` ↔ water conn `0x6`, sky **isolated** conn `0x8` — identical
  to `Test_Castle`. Native sky zone sits cleanly ABOVE the castle (z≥420, skybox at z2488–3512); **no
  interior surface is wrongly assigned to the isolated sky/solid zone**, so nothing is zone-culled.
  Part of one convex room renders lit while part is black in-game ⇒ not a per-zone cull.
- **FakeBackdrop identical.** Exactly 1 FakeBackdrop surf (#4, flags `0x00400080`) in BOTH maps;
  native DOES render the starfield where the backdrop is in view. Backdrop pipeline is fine.
- **Lightmaps present.** native 433/438 surfs lit, editor 484/485 — the black is wrong per-surface
  bake VALUES, not missing lightmaps or structure.
- Native has 438 surfs vs editor 485 (over-consolidated coplanar fragments from the un-ported
  `bspOptGeom` trim, documented in `build.rs::find_best_split`) — but this is **coverage-equivalent**
  (rasterizer proves it) and does NOT cause black. No fix made: nothing in the sky/zone/geometry
  scope (`zones.rs`/`materialize.py`/`assemble.py`) is wrong. **Redirect to the lighting line.**
