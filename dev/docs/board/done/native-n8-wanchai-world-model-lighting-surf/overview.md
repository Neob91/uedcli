+++
priority = "p2"
kind = "bug"
summary = "native N8 WanChai world Model lighting surf-visibility diverges (LightMap iLightActors -1 vs 30)"
+++

# native N8 WanChai world Model lighting surf-visibility diverges

WanChai `06_HongKong_WanChai_Market` fails the parity gate at N=8 (N=1-7 pass). The sole residual is the
world `Model Model2` body. Geometry is byte-exact: `Vectors`(13), `Points`(68), `Nodes`(47) all IDENTICAL
native==ued. The divergence is entirely in the LIGHTING bake.

## Symptoms

- `Model.Lights` array: native 30 entries, ued 31 — identical content (`light57`/`None` interleaved) plus
  ONE extra trailing `None` in ued.
- `LightMap` record 11 differs: native `DataOffset=0, iLightActors=-1` (surf treated as UNLIT, no lightmap
  data) vs ued `DataOffset=16, iLightActors=30` (surf lightmapped; light-list starts at Lights[30]). All
  other 17 LightMap records match.
- Gate token stream: native 1150 tokens vs ued 1151 (the extra `Lights` None); first literal byte diff is
  the `LightMap` rec-11 `DataOffset` (0x00 vs 0x10) and `iLightActors` (0xffffffff vs 0x1e).

## Root cause (partial)

native's light bake (`uedcli-native/src/light.rs`, `bake`/`bake_surf`; `rec.i_light_actors` set at
`light.rs:463`) computes ONE world surf (LightMap rec 11) as having NO visible lights, where UED22's bake
lightmaps it and appends its light-list slot to `Model.Lights` (growing the array by the trailing None +
setting `iLightActors=30`, `DataOffset=16`). i.e. a surf-light VISIBILITY / assignment divergence, not a
geometry difference (geometry is byte-exact) and not pure GC slack (the `iLightActors` and `DataOffset`
values genuinely differ; the surf is lightmapped in ued, blank in native).

Not yet pinned: which light and which surf (rec 11), and whether native's shadow/visibility test
(`visible_per_light` in `light.rs`) rejects a light the editor accepts, or native fails to allocate a
blank lightmap slot the editor always writes for a lightmappable surf. Needs a light.rs-level dig against
`dev/docs/unrealed/` lighting notes.

## Evidence

`_scratch/cmp_lights.py`, `_scratch/cmp_lightmap.py`, `_scratch/diag_model.py`, `_scratch/diff_off.py`
(worktree `native-parity-incremental`). Fresh native_N8 rebuild reproduces.

## Recommendation: FIX (not exclude)

A surf that is lightmapped in UED22 but blank in native is a real rendered-lighting difference — NOT a
GC/per-save artifact, NOT excludable. (The trailing `Lights` None on its own would be GC-slack-class, but
it is a symptom of the same missing lightmap record, not an independent artifact.) Fix native's bake so
rec-11's surf gets the same light assignment / lightmap slot as the editor. Root cause in `light.rs` needs
finishing before a port; owner decision on approach.

## RESOLVED (2026-09-05)

Fixed in `light.rs`. The editor's gather pass (`Editor 0x100a4ba0`, decoded `0x100a4e60`-`0x100a4f10`)
allocates a lightmap RUN for a surf iff a light passes: special_lit partition + `GetVisibleSurfs` +
backface + `WorldLightRadius >= |PlaneDot(light)|` (the PERPENDICULAR light-to-surf-plane distance,
`FPlane::PlaneDot` at `0x100a4ec6` / `comiss ... jb` at `0x100a4ef7`) — NOT the per-lumel radius. A surf
so listed but whose every lumel then fails the per-lumel radius/LOS gets an EMPTY run (a lone `-1`
terminator, 0 bytes), not a `-1` dark record. Native folded the per-lumel radius into the slot decision;
now it emits the empty run when `visible_to_any_light`. The plane-distance term is essential: a pure
`GetVisibleSurfs`-membership predicate spuriously slots rec 6/9 (native's `GetVisibleSurfs` over-includes
them, but they fail the plane test). WanChai N=8 now `PARITY: YES`; the other 23 lockstep cells
(UNATCO/WanChai/NYC_Bar × N=1..8) are byte-structurally unchanged (no regression). Regression pinned by
`emit_record_populated_empty_and_dark_encodings` in `light.rs`.
