# Original (1998/Gold) Unreal `.unr` (package v61) `UModel`/brush geometry decode

**Result: root-caused and fixed faithfully.** `level import` on a v61 `.unr` failed `brush_of`
("truncated map body") because `native.umodel.parse_model_body` only ever implemented the ver>61
(DX/UT99/UnrealGold-later) `UModel` layout. v61 is a genuinely different layout in two independent
ways, both confirmed against the REAL v61 engine source and against 6173 real retail brushes across
8 maps.

## The two format differences

Found by cross-referencing `fgsfdsfgs/UE1` — a leaked/reconstructed ORIGINAL Unreal engine source
tree whose own `PACKAGE_FILE_VERSION` is 61 (`Source/Core/Inc/UnObjVer.h`), i.e. this is not a
reconstruction guess, it is (as best determined) the actual source that wrote these bytes.

**1. `FSphere` drops its `W` float at `Ar.Ver()<=61`.** `Engine/Inc/UnMath.h`:

```cpp
friend FArchive& operator<<( FArchive &Ar, FSphere &S )
{
	// BUG: this used to be declared as operator<<( FArchive&, FPlane& ),
	// so spheres were never properly serialized in old versions of ue
	if (Ar.Ver() <= 61) // unreal v200 and probably up to gold?
		Ar << (FVector&)S;
	else
		Ar << (FVector&)S << S.W;
	return Ar;
}
```

The `UPrimitive` prefix (`ci(None)` + `FBox` 25B + `FSphere`) is therefore **38 bytes at v61**, not
42 — a real, dated engine bug (the comment is the original author's), not an uedcli
misunderstanding. Every downstream field was 4 bytes off, which is what the "truncated … at offset
X" errors were actually complaining about (the reported offset moves depending on how far the
parser had already desynced by the time it ran out of buffer).

**2. `Vectors`/`Points`/`Nodes`/`Surfs`/`Verts`/`Polys` are separate exports, not inline arrays.**
`Engine/Inc/UnObj.h`'s `UModel` (`ENGINE_API class UModel`) declares them as typed pointers to
`UDatabase` subclasses (`UVectors`, `UBspNodes`, `UBspSurfs`, `UVerts`, `UPolys`), and
`Engine/Src/UnModel.cpp`'s `UModel::Serialize`:

```cpp
Ar << Vectors << Points << Nodes << Surfs << Verts << Polys;
Ar << LightMap << LightBits;
Ar << Bounds;
Ar << LeafHulls << Leaves << Lights << LeafZone << LeafLeaf;
```

`Ar << SomePointer` on a `UObject*`-typed member serializes as a compact-index OBJECT REF, not the
object's own bytes — so at v61 the private brush model's body is nearly empty (six small refs to
five OTHER exports, one of them the `UPolys` list `brush_of` actually wants) instead of holding the
Vectors/Points/Nodes/Surfs/Verts data inline. Each referenced export is its own `UDatabase`
(`Engine/Inc/UnObj.h` + `UnModel.cpp`): `[None-terminated property list][i32 DbNum][i32
DbMax][DbNum × element]`, plus `UBspNodes` (`NumZones` + `Zones[]`) and `UVerts`
(`NumSharedSides`) each carry one more trailing field of their own.

`LeafZone`/`LeafLeaf` (refs to a `UBitArray`/`UBitMatrix`) also exist at this point in the v61
layout, right before `RootOutside`/`Linked` — a pair `ver>61` no longer serializes at all (dropped
from the format sometime after v61).

Everything ELSE in the model body — `FBox`, `FLeaf`, `FLightMapIndex` (at `Ar.Ver()>=53`, which
covers 61), the `TArray<BYTE>`/`TArray<INT>` encodings, and `FPoly` itself
(`Engine/Inc/UnObj.h`'s `FPoly::operator<<`) — is **byte-identical** to the ver>61 path. `FPoly`'s
only version gate (`Ar.Ver()<45`, a 2-byte pad) doesn't apply at 61. Confirmed by feeding a
resolved v61 `Polys` export straight into the existing, UNMODIFIED `mapimport.decode_upolys` — it
worked on the first try, no changes needed.

## Why this wasn't the same shape as the sibling `RemapAnimVerts` mesh fix

That fix (commit `d160e864`, same session) was one optional TRAILING field on an otherwise-fixed
mesh layout. This is bigger: the model's TOP-LEVEL array section is a different data model (object
refs to five separate exports vs. inline `TArray`s) layered on top of a narrower field-width bug
(`FSphere`). Still, it fits the SAME extension shape the session's working hypothesis expected —
one coherent, evidence-backed `version<=61` branch inside the existing `parse_model_body`, not a
forked module — because every ELEMENT-level structure (`FPoly`, `FBox`, `FLeaf`, `FLightMapIndex`)
is unchanged; only the section that locates Vectors/Points/Nodes/Surfs/Verts/Polys differs.

## Why the fix is scoped to `Polys` only

`brush_of` (the only production caller of `parse_model_body` that would hit a v61 map) never reads
`m.vectors`/`m.nodes`/`m.surfs`/`m.verts` — its whole job is a brush's AUTHORED polygon list, which
lives entirely behind the `Polys` ref. The v61 branch therefore:

- Parses the full top-level model body (all six refs, all six inline arrays, the two extra object
  refs, the trailing i32 pair) and self-checks to EOF, matching the same "consume to exact end"
  oracle the ver>61 path already relies on — so a genuinely wrong byte offset still trips a hard
  error, not a silently short read.
- Records `Vectors`/`Points`/`Nodes`/`Surfs`/`Verts` refs (`Model.vectors_ref` etc, new fields) but
  does NOT recursively decode the exports they point at — no production code needs their contents
  yet.

A full v61 WORLD-model reader (recursively decoding a `UBspNodes`/`UBspSurfs`/`UVerts` export's own
body — needed only if `level import` is later extended to reproduce a v61 map's BUILT BSP, not just
its authored brushes) is real, scoped-out follow-up work — filed as
`dev/docs/board/inbox/v61-world-model-nodes-surfs-verts-recursive/`.

## Evidence

- `harness/decode_v61_model.py` — the byte-level trace (prefix width, six object refs, each ref's
  own `UDatabase` header) against a real map, run manually to find the layout.
- `harness/sweep_v61_brushes.py` — corpus sweep via the PRODUCTION `brush_of`/`decode_upolys`.
  2026-09-11, 8 real retail maps (53 KB – 9.8 MB, package versions 60–61), 6173 `Engine.Brush`
  actors: **0 failures**, every `Polys` ref resolved and decoded to EOF.
- `uedcli/tests/test_v61_model_decode.py` — the pinned regression (real-map fixture, skip-gated on
  the gitignored install like the sibling mesh test).

## Architecture question, answered

Same UE1 data — BSP nodes, surfaces, points, zones — across every version, but NOT the same byte
layout: v61's Vectors/Points/Nodes/Surfs/Verts/Polys are separate exported objects; ver>61 collapsed
them into one inline body. `umodel.py`'s existing "one decoder, narrow `if version<=N`
branches" shape (mirroring `umesh.py`'s `RemapAnimVerts` handling) is still the right architecture —
confirmed, not just assumed — because the change is CONFINED to how the top-level sections are
located, not to what any individual element looks like. A parallel v61-specific module would have
duplicated every element-level parser (`_parse_node`, `_parse_surf`, `_parse_leaf`, `_parse_a8`,
`_parse_c0`, `_parse_cc`, `_parse_e4`) for zero benefit, since all of them are reused unchanged.
