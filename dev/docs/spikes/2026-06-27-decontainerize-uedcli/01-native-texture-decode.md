# Spike 1 — native texture decode (no wine / no UCC)

**Status: RESOLVED — native decode is pixel-EXACT vs `UCC batchexport`, across the
entire Deus Ex install corpus (package versions 61, 68, 69).** Harness:
[`harness/utexture_decode.py`](harness/utexture_decode.py); the pixel-exact comparison
against UCC PCX is committed + reproducible in
[`harness/tex_compare.py`](harness/tex_compare.py) (re-verified 2026-06-27).

> **Corpus pinning:** all numbers below are against the RETAIL install at
> `Tools/uedcli/uned/DeusExAssets/{Textures,System}` (v61/v68). Do NOT run the harness
> against `uned/UED22/*.u` — those are v69 *stubs* and produce different counts.

## Question

Can uedcli extract textures from `.utx`/`.u` packages in **pure Python**, replacing
the only current path — `UCC.exe batchexport <pkg> Texture pcx Z:\…` run in a wine
container (`uedcli/texture.py`)? This is the explicit "reverse-engineer texture
extraction to minimize `.exe` dependency" ask.

## Answer: yes, completely. Proven pixel-exact.

A from-scratch pure-Python decoder reads the package, finds every `Texture` export,
decodes its `UTexture` serial body + the referenced `UPalette`, and produces mip-0
RGB. Validation: decode each texture natively AND `UCC batchexport` it to PCX, decode
the PCX with Pillow, compare bytes.

| Package | Version | Textures | Result vs UCC |
|---|---|---|---|
| `CoreTexMetal.utx` | 68 | 175 | **175/175 pixel-EXACT** |
| `CoreTexDetail.utx` | 61 | 17 | **17/17 pixel-EXACT** |
| `DeusExItems.u` | 68 | 185 | **185/185 pixel-EXACT** |

Full-corpus sweep (56 `.utx` + the code `.u`): **every texture in every package
decodes as `P8` with the serial body consuming exactly to its declared EOF, zero
failures** once the v61 layout difference (below) is handled. Format histogram is
`P8=100%` — Deus Ex content has no `RGBA7`/`DXT`/`RGB8` *content* textures (those
formats exist for engine-internal lightmaps that live inside the `Model`, not as
`Texture` exports in content packages).

## The on-disk format (reverse-engineered + verified to EOF)

A UE1 object's serial body = a **tagged-property list** (terminated by the name
`None`) then **class-specific trailing data**.

### `UTexture` body
```
<tagged property list>          # see FPropertyTag below; carries Format, Palette, …
None                            # property-list terminator (a name-table compact)
Mips : TArray<FMipmap>          # ci count, then count × FMipmap (trailing data)
```
Relevant properties read from the tag list:
- `Format` — `ByteProperty`, the `ETextureFormat` ordinal. `0 = P8` (palettized),
  `1=RGBA7 2=RGB16 3=DXT1 4=RGB8 5=RGBA8`.
- `Palette` — `ObjectProperty`, a compact object-ref to a `UPalette` export.

### `FMipmap` (per mip)
```
WidthOffset : uint32   # absolute file offset just past the pixel-data array.
                       # PRESENT in Ar.Ver >= 63 (v68/69); ABSENT in v61.  ← the
                       # single version difference; was the v61 decode failure.
DataCount   : ci       # number of pixel bytes in this mip (USize*VSize for P8)
Data        : byte[DataCount]   # palette indices (P8)
USize       : uint32   # mip width
VSize       : uint32   # mip height
UBits       : uint8
VBits       : uint8
```
Mip 0 is full resolution. For v68/69 the `WidthOffset` gives a free internal check:
after reading `Data`, the cursor must equal `WidthOffset`. For v61 (no offset) the
whole-body-to-EOF check is the integrity guard instead.

### `UPalette` body
```
<tagged property list> None     # normally empty (just None)
Colors : TArray<FColor>         # ci count (=256), then 256 × {R,G,B,A} bytes
```
Decode P8: `rgb[i] = Colors[Data[i]][:3]`.

### FPropertyTag (the tagged-property encoding)
Per property, until a `None` name:
```
Name : ci                       # index into the name table; "None" => end
Info : uint8                    # bits 0-3 = type, bits 4-6 = size code, bit 7 = array/bool
[if type==Struct(10)] StructName : ci
size = {0:1,1:2,2:4,3:12,4:16, 5:<u8>,6:<u16>,7:<u32>}[size code]
[if bit7 and type!=Bool] array index : 1/2/4-byte special encoding
value : size bytes              # (Bool's value IS bit 7; no value bytes)
```
Type nibble (on disk): `1 Byte, 2 Int, 3 Bool, 4 Float, 5 Object, 6 Name, 7 Str,
10 Struct`. Generic size-skipping means we never need to understand a value type to
step over it — only `Format` (Byte) and `Palette` (Object) are interpreted.

## Why this matters for de-containerization

`uedcli/texture.py` is one of the container's reasons to exist (`texture sync` →
`docker exec … wine UCC.exe batchexport … pcx` → `cp_out` → Pillow). This decoder
removes that entire seam: **no wine, no Docker, no PCX intermediate, no ImageMagick**
— and it yields *more* than UCC did (all mip levels, the palette, exact dimensions,
the format) directly from bytes uedcli already knows how to read (`dxpkg`).

The production form reuses `dxpkg._read_compact_index` + the export-table reader from
the `2026-06-26-uproperty-typed-decode` harness (`load_package`); the `texture sync`
pipeline replaces its batchexport+cp_out+Pillow-PCX legs with `decode_texture` +
`mip0_to_rgb`, keeping the existing catalog/hash/color-derivation on top.

## Residual / deferred
- **Non-P8 formats** (`RGBA7`/`DXT1`/`RGB8`/`RGBA8`): no occurrences in DeusEx
  content, so not decoded yet. Add a per-format mip decoder only if a target
  substrate (e.g. a UT install) uses them. The format is already read and reported.
- **Group component of the ref**: UCC writes group-prefixed PCX (`Metal.Foo.pcx`);
  the native path can read the texture's `Group`/outer for the catalog's 3-part-ref
  disambiguation (same rule as today) — not needed for decode, only for `ref` naming.
- Promotion to `uedcli/` (a `utexture.py` module + wiring into `texture sync`) is a
  build task for the roadmap, not this spike.
