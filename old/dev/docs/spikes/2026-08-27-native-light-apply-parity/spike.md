# Spike: bake `LIGHT APPLY` natively, byte-for-byte against the editor (2026-08-27)

**Question.** `level materialize`'s editor-free path (`UEDCLI_NATIVE_MATERIALIZE=1`) carves the
world BSP in process but ships no lighting, so every surface renders fullbright and no mesh actor
draws at all. Can we bake the lightmaps ourselves, to the byte-identity bar
`direction/materialize.md` sets for the native build?

## TL;DR — yes, to 99% of the shadow bytes, and the rest is not the bake's

The bake reproduces the editor's own `LIGHT APPLY` output on `03_NYC_UNATCOHQ` (mislabeled
`01_NYC_UNATCOHQ` throughout this session's docs until 2026-08-31, see
`unatco-baseline-trunk-is-actually-03-nyc`): the same 3345
`FLightMapIndex` records in the same array order, the same 271 unlightmapped surfaces, grid
descriptors exact on 3345/3345 records, **8162 of 8246 per-(surface, light) shadow bit-planes
byte-identical**, and 99.988% of 3,978,275 individual lumel bits equal. A full lit build of that
1437-actor trunk takes 12 s. Three gaps remain and none of them is in `light.rs`.

The mechanism, every rule, and its disassembly evidence live in
`2026-07-15-native-materialize/sections/20-lighting-bake.md`, which this spike corrected in four
places and extended with a new §23. This file records what that section does not: how to build a
lighting oracle you can actually compare against, and where the work stands.

## The hard part was the ORACLE, not the bake

A lightmap comparison is positional. `Model.LightMap` holds one record per lit surface in BSP
tree-walk order, `LightBits` offsets follow that array, and the per-surface light runs follow it
again — so if the two builds disagree about what the surfaces ARE, record *k* describes a different
piece of world on each side and no byte comparison means anything.

Two false starts, both worth knowing:

1. **The production editor path is not a usable oracle.** `level materialize` assembles an unbuilt
   package and `MAP LOAD`s it. On the UNATCO trunk, world-only either way, that yields 3705 surfs /
   6254 nodes / 776 leaves — while `MAP NEW` + `EDIT PASTE` of the same 734 brushes yields 3616 /
   6314 / 762, which is what the native CSG core reproduces exactly. Same editor, same brushes, same
   bare `MAP REBUILD`; only the way the brushes entered the level differs. Not actor-set
   contamination either: cutting the trunk down to LevelInfo + PlayerStart + the 734 brushes gives
   the same 3705, and every world surf on both sides is owned by an `Engine.Brush` across the same
   719 owners. Board: `map-load-and-edit-paste-build-different-world`.
2. **The geometry golden builder cannot simply be run with lighting on.** Its `--world-only` filter
   keeps `Brush` + `LevelInfo`, so there are no lights to bake; drop the filter and `_re_add` pastes
   every brush-bearing actor as a WORLD brush, movers included, which changes the geometry.

So the oracle is a third pipeline: `harness/build_ued_lit_golden.py`, the paste-based golden with an
actor filter that keeps `Brush` + `LevelInfo` + **every class the bake itself treats as a light**,
derived from the trunk through `gather_lights`. Deriving it is not fussiness: hardcoding `Light`
dropped `09_HONGKONG_WANCHAI_MARKET`'s 13 `Engine.Spotlight`s and the first comparison read as
native inventing 13 lights out of nowhere. Any kept class that carries a brush is refused outright.

One engine quirk the oracle depends on: `shadowIlluminateBsp` empties `Model->LightMap` and
`Model->LightBits` but never `Model->Lights` (§21 (A)), so a second `LIGHT APPLY` with no rebuild
between appends a third region and orphans the previous one. A golden must come from a full rebuild.

## What was wrong in the bake, and what each fix was worth

The bake had been editor-parity-validated only against `Test_Castle.dx` — 95 brushes, axis-aligned,
one lumel scale. Seven rules were wrong or missing at real scale. Each was taken from fresh
`Editor.dll`/`render.dll` disassembly and then measured against the oracle; the disassembly VAs are
in section 20.

| fix                                                      | measured effect on the UNATCO oracle |
|----------------------------------------------------------|---
| grid dim `ceil((extent − 0.25)/scale)`, not `ceil(e/s)`  | grid dims 3209/3345 → 3345/3345 records exact |
| `>256` doubles the lumel scale instead of clamping       | unobserved here; a wrong grid on the first surface that needs it |
| participation needs `bStatic` or `bNoDelete`             | 7 `SecurityCamera`s the editor bakes nowhere, gone |
| `bSpecialLit` PARTITIONS lights against `PF_SpecialLit`  | one light alone was listed on 130 surfaces it must not touch |
| the shadow ray exempts `NF_NotVisBlocking` nodes         | lumels the editor lights and native did not: 54157 → 3902 |
| `PF_BrightCorners` insets the grid and passes `0x14`     | 3902 → 442; those surfaces 33.6% → ~99% plane-identical |
| backface keeps `PlaneDot >= -1.0`, never culls two-sided | (surface, light) pairs native was MISSING: 146 → 7 |

Two of those deserve singling out because they are not the kind of thing a reasonable
reimplementation guesses:

- **`NF_NotVisBlocking`** is an `ExtraNodeFlags` bit the shadow ray passes so nodes the CSG build
  marked non-visibility-blocking stop occluding. 160 of UNATCO's 6314 nodes carry it and native was
  treating every one as an occluder, which cast large wedge-shaped shadows the editor does not have.
  It surfaced from printing the SHAPE of one diverging plane rather than from aggregate percentages:
  native's lit region was a clean wedge cut out of the editor's, which is an occluder edge, not
  noise. Worth reusing — the aggregate numbers had been flat for three fixes running.
- **`PF_BrightCorners`** (`0x00080000`) does two unrelated things: it insets the sample grid by
  0.25, and it raises the ray's `ExtraNodeFlags` to `0x14`, where bit `0x10` makes a trace that
  STARTS inside solid report clear. That matters because a lumel grid is the surface's texture-space
  BOUNDING BOX, so on any non-rectangular or corner-adjacent face a lot of lumels sit inside
  neighbouring brushes. It accounted for 84% of the residual: surfaces without the flag were already
  99.2% plane-identical while surfaces with it were 33.6%.

Two intermediate guesses the disassembly then corrected, recorded so nobody re-derives them: the
trailing padding bits above `USize` are the LAST ray's result, not a re-trace of the extrapolated
lumels (a differential fit preferred the re-trace, and it was wrong); and the `0.25` constant
section 20 §6 flagged as implying a 2×2 supersample is the `PF_BrightCorners` inset — there is
exactly one ray per lumel, at the grid corner.

## Where it stands

| measure                                    | UNATCO (records align 1:1)  | WANCHAI (geometry-matched) |
|--------------------------------------------|-----------------------------|---
| world brushes / trunk actors               | 734 / 1437                  | 1304 / 2288 |
| native lit build time                      | 12 s                        | 37 s |
| grid descriptors exact                     | 3345 / 3345                 | 4239 / 4252 = 99.7% |
| records byte-identical                     | 2518 / 3345                 | — (trees differ) |
| per-(surface, light) planes byte-identical | 8162 / 8246 = 99.0%         | 3716 / 3905 = 95.2% |
| lumel bits equal                           | 99.988%                     | 99.08% |
| light runs identical incl. order           | 2977 / 3345                 | 3911 / 4252 = 92.0% |
| light actors listed on a surface           | 189 / 189, none either-only | 0 native-dark-editor-lit surfaces |

`09_HONGKONG_WANCHAI_MARKET` had to be matched by geometry because its BSP tree does NOT agree with
the editor's — 11381 vs 11648 nodes, 3240 vs 3371 leaves — which is itself a finding this spike
produced: the BSP parity reached earlier is a UNATCO result, not a general one. Board:
`native-bsp-matches-the-editor-on-unatco-but-not`.

## The three gaps, all owned elsewhere

1. **The per-surface light RUN** — 368 records, and one-sided: native adds 618 (surface, light)
   pairs and misses 7. The editor does not use a geometric predicate at all. Per light it opens a
   1024×1024 offscreen viewport at the light's position and calls `URender::GetVisibleSurfs`, which
   rasterizes **six cube-map faces** and keeps a surface iff at least one pixel span survives
   against accumulated per-zone span buffers. A surface with clear line of sight is still rejected
   when a nearer opaque polygon already claimed every pixel it covers. Fully decoded, with a port
   sketch, in `port-urender-getvisiblesurfs-so-each-light-gets`. This is the only remaining gap that
   is the bake's own.
2. **`Model.Lights` region 1** — 11368 vs 16263 entries. The missing 5405 is the per-leaf permeating
   light lists, produced by the ZONING build (`csgRebuild` → `TestVisibility` → `Portalize`), not by
   the bake. `zones.rs` also stubs every leaf's `iPermeating` to `0`, which points each leaf at a
   per-SURFACE run — wrong data rather than missing data. Board:
   `port-the-per-leaf-permeating-light-lists-model`.
3. **`Pan` / `UScale` / `VScale` on 160 / 111 / 94 records** — exactly the records whose surf base
   point or texture vector differs from the editor by f32, i.e. the upstream `Points` residual
   (10758 vs 10752). No lighting change can move them. Board:
   `unatco-verts-points-residual-after-the-zone`.

Not chased, and the largest single source of the remaining shadow-bit disagreement (466 bits, 487 of
them at shadow edges against 24 in solid blobs): `lumel_axes` computes `det = tu·(tv×normal)` while
`FCoords::Inverse` expands the same determinant in a different term grouping. Algebraically equal,
not f32-identical, and every accumulated lumel position inherits the ulp.

## Harness

| script                    | what it answers |
|---------------------------|---
| `build_ued_lit_golden.py` | builds the lit oracle (the pipeline above) |
| `lightparity.py`          | sections, per-record fields, runs; object-refs resolved to export names |
| `bit_asymmetry.py`        | which DIRECTION the bits err, and edge vs solid-blob |
| `run_diff.py`             | which light actors are extra/missing, per surface count |
| `light_geomatch.py`       | the same comparison when the two BSP trees disagree |
| `lights_regions.py`       | splits `Model.Lights` into its per-leaf and per-surface regions |
| `grid_formula_fit.py`     | refits the grid rule against one oracle, no native side involved |
| `zero_planes.py`          | does the editor ever store an all-zero plane? (no: 0 of 17688) |
| `pair_geometry.py`        | classifies diverging pairs by radius and zone |

Plus the disassembly drivers the decode needed: `adis.py`, `adis_iat.py` (IAT thunk resolution,
which is what makes these function bodies readable), `pe.py`, `rdis.py`, `xref.py`, `xrefs.py`,
`vtable.py`, `wstr.py`, `fieldscan.py`, `actor_layout.py`.

Reproduce, from the repo root, for either trunk:

```
H=dev/docs/spikes/2026-08-27-native-light-apply-parity/harness
.venv/bin/python $H/build_ued_lit_golden.py --trunk <trunk> --out golden.dx --overwrite
UEDCLI_NATIVE_MATERIALIZE=1 bin/uedcli --project <proj> level materialize \
    --tree level/<lvl> --out native.dx --overwrite --no-verify
.venv/bin/python $H/lightparity.py native.dx golden.dx
```

Trunks: `_scratch/bsp-parity-proj/maps/unatco` and `dev/games/trunks/tmp-wanchai-market`. Both carry
fully qualified actor classes, which `gather_lights` needs to resolve class defaults.
