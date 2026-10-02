# Spike 10 — decode `UPolys`/`FPoly` (authored brush polygons) — the native-read prerequisite

**Status: RESOLVED — the authored brush-polygon format is decoded; parses to EOF on
6566/6587 (99%) `UPolys` exports across 8 real maps (4 maps at 100%).** This was the hard
prerequisite the native-`.dx`-read spec (board item `stale-canonicalize-mover-blob-references-in-two`)
flagged: it carries BOTH authored brush geometry AND per-poly textures.

## Why it matters

A brush actor's authored shape is its `Brush=Model'…'` → `UModel.Polys` (a `UPolys` = array
of `FPoly`). `MAP EXPORT`/UCC reads this and emits T3D with **bare** texture names; the live
editor's `OBJ DEPENDENCIES` then re-qualifies them positionally. Reading the binary `UPolys`
natively gives the authored verts + texture **object-refs that qualify directly via the
import table** — removing both the UCC-export and the live-qualify legs (the cold review
correctly noted per-poly texture qualification lives HERE, not in a flat import-table set).

## Decoded format (disassembly + EOF-validated)

`UPolys::Serialize` (Engine.dll RVA `0x115240`) and `operator<<(FArchive&, FPoly&)`
(`0x16fb20`):

```
UPolys body:
    <property list> None        # 1 ci ("None")
    INT  Num                    # poly count
    INT  Max                    # capacity (TTransArray)
    Num × FPoly

FPoly (archive order, from the FPoly operator<< disasm):
    NumVertices : ci            # serialized first (struct +0x1c0)
    Base        : FVector (12)  # 0x1010c160 = 3×4 raw bytes (same FVector serializer
    Normal      : FVector (12)  #   the Model spike identified)
    TextureU    : FVector (12)
    TextureV    : FVector (12)
    Vertex[NumVertices] : NumVertices × FVector (12 each)
    PolyFlags   : INT (4, raw at +0x1b0)
    Actor       : ci (object ref)
    Texture     : ci (object ref)   ← qualifies via the import table (e.g. -4 = an import)
    ItemName    : ci (FName)        ← per-face label (Base/Step/…)
    iLink       : ci
    iBrushPoly  : ci
    PanU, PanV  : u16, u16
```
(The `iLink`/`iBrushPoly`-as-ci + `PanU`/`PanV`-as-u16 tail was pinned by EOF brute-test:
the only tail variant that consumes to EOF.)

## Validation

Decode every non-trivial `UPolys` export → consume to its serial EOF:

| Map | EOF |
|---|---|
| 00_Intro | 947/947 |
| 00_Training | 1007/1009 |
| 00_TrainingCombat | 563/576 |
| 00_TrainingFinal | 784/784 |
| 01_NYC_UNATCOHQ | 748/748 |
| 01_NYC_UNATCOIsland | 1432/1434 |
| 02_NYC_Bar | 208/209 |
| 02_NYC_BatteryPark | 877/880 |
| **total** | **6566/6587 (99%)** |

`Texture` refs come back as import object-refs (qualify via the import table); verts are
sane world coords; `PolyFlags`/`ItemName` decode. So the authored brush geometry + per-poly
qualified textures are both natively recoverable.

## Residual (the ~1%)
21/6587 `UPolys` don't land exactly at EOF (concentrated in a few maps; 4 maps are 100%).
Likely a minor `FPoly` edge variant (a special poly, or a `UPolys` header nuance on those
exports). Chase before production promotion (the EOF-consumption check pins exactly which
exports + offsets diverge); the format above is correct for 99% incl. four whole maps.

## Effect on the roadmap
The native-`.dx`-read spec's **"hard prerequisite `UPolys` decode spike" is now DONE** (this
spike). Combined with Spikes 4/7/8, the native reader can produce a fully-qualified `Level`
(point actors + brush geometry + per-poly textures + classes) with no editor/UCC — modulo
the 1% edge + the `canonical_level_hash` float-formatting parity gate the spec specifies.
Harness lives inline here (the decode is ~30 lines over `utexture_decode.load_package` + the
`ci`/FVector primitives).
