# Native `LIGHT APPLY` — the surface-lightmap bake, fully reverse-engineered

**Goal of this section.** Re-implement UnrealEd's `LIGHT APPLY` (the world-surface
lightmap bake) in pure Python, so `level materialize` can produce a game-valid,
lit `.dx`/`.unr` **without running the editor**. This section pins the complete
pipeline, every stored byte, and the exact math — decoded from the UED22 DLLs
(`Editor.dll`/`Engine.dll`, image base `0x10000000`) and reconciled against real
built Deus Ex maps.

**Confidence markers:** ✅ = verified against this binary AND real `.dx` bytes ·
🔬 = derived from disassembly, not yet cross-checked live · 📖 = engine
vocabulary/semantics inferred (render-side, not exercised by the bake).

---

## 0. The one decisive finding (read this first)

**The bake stores VISIBILITY BITS, not light intensities or colours.** ✅

For every lit surface the editor stores, per light that reaches it, a **1-bit-per-lumel
shadow mask** (`1` = that lumel has clear line-of-sight to that light and is inside the
light's radius; `0` = shadowed or out of range). It stores **no** brightness, hue,
saturation, attenuation, or `LE_Negative` sign. Those are all applied by the **game at
render time** from the light actor's properties (which already live in the T3D). The bake
is therefore **purely geometric**: radius cut-off + BSP line-of-sight. A native baker does
**not** need the attenuation/colour model to produce byte-valid output — it only needs to
reproduce the bitmasks and the descriptors that index them.

This collapses "native lighting" from "port the engine's light-transport" to "port a
per-lumel BSP ray test", which is a far smaller job.

---

## 1. Entry point and pipeline

`LIGHT APPLY` (exec verb, `Editor.dll`) dispatches to
`UEditorEngine::shadowIlluminateBsp(ULevel*, INT selected, INT changedOnly)` —
export `?shadowIlluminateBsp@UEditorEngine@@UAEXPAVULevel@@HH@Z`, **RVA `0xa5e10`**. ✅
The source is `C:\GameDev\UnrealTournament\Editor\Src\UnShadow.cpp` (embedded assert
path). ✅ Progress strings in order: `"Rebuilding lighting"`, `"Computing visibility"`,
`"Allocating meshes"`, `"Raytracing"`. ✅

Ordered pipeline (`Level->Model` is at `ULevel+0x98`): ✅

1. **Reset.** Empty `Model->LightMap` (`UModel+0xa8`, the `FLightMapIndex` array,
   40-byte elements) and `Model->LightBits` (`UModel+0xb4`, the `BYTE` array); set every
   `FBspSurf.iLightMap` (`surf+0x18`) to `-1`.
2. **Gather lights** (`"Computing visibility"`, internal fn `Editor 0x100a4ba0`). Iterate
   the level's actors; for each participating light, ask the renderer which surfaces it
   can see and mark them. Builds a transient per-surface light list
   (`Lights.Num()==Level->Model->Surfs.Num()` — asserted). ✅
3. **Allocate meshes** (`"Allocating meshes"`, internal fn `Editor 0x100a5bf0`). For each
   lightable surface, compute its lumel-grid dimensions/scale/pan from the surface's
   texture-space extent and store an `FLightMapIndex`; set `surf.iLightMap` to its index.
4. **Raytrace** (`"Raytracing"`, internal fn `Editor 0x100a5010`, called once per lit
   static surface and once per mover surface). For each lumel × each light in the
   surface's list, do the radius test + BSP line check and pack the resulting bit.
   Concatenate all lights' bitmaps at the surface's `DataOffset` in `LightBits`.
5. Populate `Model->Lights` (`UModel+0xe4`, `TArray<AActor*>`) as the flattened,
   NULL-terminated per-surface light lists; each `FLightMapIndex.iLightActors` indexes it.

Functions (all `Editor.dll`, add image base `0x10000000` for VA):

| RVA | Role |
|---|---|
| `0xa5e10` | `shadowIlluminateBsp` — top orchestrator ✅ |
| `0xa4ba0` | gather-lights / mark-visible-surfaces pass ✅ |
| `0xa5bf0` | **grid allocator** — computes USize/VSize/UScale/VScale/Pan (§4) ✅ |
| `0xa5010` | **per-surface raytrace** — packs the shadow bits (§3, §5) ✅ |

---

## 2. Storage layout — the four Model arrays and the surf link

All offsets are the in-memory `UModel` field offsets; the serial order and element
formats are in `spikes/2026-06-25-umodel-serialize-format.md` /
`2026-06-28-umodel-serialize-byte-exact.md`. The bake writes/links exactly these:

```
FBspSurf.iLightMap   (surf mem +0x18; 7th serialized field)  -> index into LightMap, or -1
UModel+0xa8  LightMap   TArray<FLightMapIndex>  (40-byte elems)   §4
UModel+0xb4  LightBits  TArray<BYTE>            (the shadow-bit planes)   §3
UModel+0xe4  Lights     TArray<AActor*>         (ci obj-refs, NULL-terminated runs)   §5
```

> ⚠️ **Parser mislabel to fix.** `bspspike/umodel_parser.py` `_parse_surf` names the
> field at serial position 7 / mem `+0x18` `i_actor` and the one at `+0x24` `i_field_0x24`.
> Per `UModel::GetLightMapIndex` (`Engine 0x1127c0`), **`surf+0x18` is `iLightMap`** (it is
> `<<6`-indexed into `Surfs`, read as the LightMap index, and reset to `-1` by the bake).
> `+0x24` is the brush `Actor` ref. Rename for clarity; the byte layout is unchanged. ✅

**Linkage (proven ✅).** For a lit surface *s*:
`s.iLightMap` → `LightMap[iLightMap]` (an `FLightMapIndex` *L*); `L.iLightActors` → the run
`Lights[iLightActors], Lights[iLightActors+1], …` up to (not including) the first `0`
(NULL) entry — that run **is** the surface's light list; its length **N** = number of
bit-planes; `L.DataOffset` → the first of `N × ceil(USize/8) × VSize` bytes in `LightBits`.

Non-lightmapped surfaces (PF_Unlit / PF_Invisible / fake-backdrop / portal) get
`iLightMap = -1` and **no** `FLightMapIndex` (on `00_Intro`: 4573 surfs, 4211 records,
362 with `iLightMap=-1`). ✅ Lightmapped-but-dark surfaces (reached by 0 lights) get a
record with `DataOffset=0`, `iLightActors=-1`, and **0** bytes (857/4211 on `00_Intro`). ✅

---

## 3. `LightBits` (UModel+0xb4) — the exact byte encoding ✅ PROVEN

Per surface, its `N` lights' bit-planes are stored **consecutively** starting at
`FLightMapIndex.DataOffset`. Each plane is a `USize × VSize` grid of 1-bit lumels:

- **Row-major in V**: `VSize` rows, each row is `ceil(USize/8)` bytes (rows are
  byte-aligned — a partial final byte in a row is flushed and padded). ✅
- **Within a row**, lumel `u` is bit `(u & 7)` of byte `u>>3` (÷8, **not** `u>>8`)… i.e.
  **LSB-first**: the first lumel is mask `0x01`, then `0x02`, `0x04`, … `0x80`, then the next
  byte. (Builder packs with `bl` starting at `1` and `add bl,bl`.) ✅
- **Bit value**: `1` = lumel is **lit** by that light (clear LOS **and** within radius);
  `0` = shadowed or out of range. ✅ (Confirmed on an isolated 2-row surface: near row
  fully lit, far row fully dark → far-row byte `0x00`, near-row byte all-ones. Note: bits
  **above `USize`** in a row's final byte are not guaranteed cleared — a porter must mask to
  `USize` on read and may leave high bits either value on write; only bits `0..USize-1` are
  meaningful.)

**Bytes per surface** = `N × ceil(USize/8) × VSize`, where `N` = number of lights in its
list (0 for a dark record).

**Reconciliation that pins this (harness `lightmap_reconcile.py`):** for every
unique-offset record on `00_Intro`/`01_NYC_UNATCOHQ`/`02_NYC_Bar`, the byte span to the
next record's offset is **exactly divisible** by `ceil(USize/8) × VSize`
(**2867/2867, 2293/2293, 621/621 — zero exceptions**), and the quotient (=N) is a sane
1..30 light-count distribution. Independently, `iLightActors`-run length (to the NULL in
`Lights`) equals that same **N** for **every** record (**2867/2867, 621/621, zero
mismatches**). Two independent measures of N agree → the format is closed. ✅

There is **no** RGB and **no** multi-byte-per-lumel. Deus Ex's coloured lighting is the
render step applying each light's hue/saturation to its (mono) bit-plane. ✅

---

## 4. `FLightMapIndex` (UModel+0xa8) — 40-byte element, every field ✅

Serialized by `FLightMapIndex::Serialize` (`Engine 0x1016f9f0`); in-memory 40 (`0x28`)
bytes. Serial ORDER differs from memory order — the table below is by **memory offset**
(what a struct-writer must emit); the serializer writes them
`+0x00, +0x08(Pan), +0x1c, +0x20, +0x14, +0x18, +0x04` (see the encoder in §8).

| mem off | serial prim | field | meaning | evidence |
|---|---|---|---|---|
| `+0x00` | raw i32 | **DataOffset** | byte offset of this surf's first bit-plane in `LightBits` | ✅ |
| `+0x04` | raw i32 | **iLightActors** | index into `Model->Lights` (`+0xe4`); start of NULL-terminated light run; **`-1` if surf reached by no light** | ✅ |
| `+0x08` | 3×f32 | **Pan** (X,Y,Z) | lumel-grid origin in the **BASE-RELATIVE** texture frame: `Pan.X = Umin − 0.125`, `Pan.Y = Vmin − 0.125`, `Pan.Z = 0`, where **`Umin/Vmin = min of (vertex − Base)·TextureU / (vertex − Base)·TextureV`** over the surf (`Base = Points[pBase]`). ⚠️ NOT the raw world dot — see §16. | ✅ |
| `+0x14` | raw f32 | **UScale** | world units per lumel, U = `extent_U / (USize−1)` | ✅ |
| `+0x18` | raw f32 | **VScale** | world units per lumel, V = `extent_V / (VSize−1)` | ✅ |
| `+0x1c` | ci | **USize** (UClamp) | lumels across U, `∈ [2, 256]` | ✅ |
| `+0x20` | ci | **VSize** (VClamp) | lumels down V | ✅ |
| `+0x24` | (not serialized) | runtime ptr | ignore when writing | ✅ |

**Grid-sizing formula** (from `Editor 0x100a5bf0`, args = `(FLightMapIndex* out, DWORD
PolyFlags, float Umin, float Vmin, float Umax, float Vmax)`; the U/V texture extents come
from projecting the surface's node vertices onto the surf's `TextureU`/`TextureV` vectors —
**offset by the surf base's own projection**: `U = (vertex − Base)·TextureU`, no normalisation.
The `extent = Umax − Umin` is base-invariant so USize/UScale are unaffected; **Pan is not** — it
lives in the base-relative frame (§16)): ✅

```
# lightmap resolution (world units per lumel) chosen from PolyFlags:
if   (PolyFlags & 0x808000) == 0x808000: scale = 128   # HighShadowDetail & LowShadowDetail
elif  PolyFlags & 0x00800000:            scale = 16     # PF_HighShadowDetail
elif  PolyFlags & 0x00008000:            scale = 64     # PF_LowShadowDetail
else:                                    scale = 32     # DEFAULT
# per axis (U shown; V identical with Vmin/Vmax) — Umin/Umax are BASE-RELATIVE:
#   base_u = Base·TextureU;  U(vertex) = vertex·TextureU - base_u
extent = Umax - Umin
USize  = int((extent - 0.25) / scale - 0.5) + 1      # C truncation toward zero
USize  = max(USize, 2)                                # clamp lower
# (if USize > 256 the editor bails out of storing UScale — treat 256 as the hard cap)
UScale = extent / (USize - 1)
Pan.X  = Umin - 0.125                                 # base-relative, small/local (§16)
```

Constants read from `.rdata`: `0.25` (`0x100de968`), `0.5` (`0x100de978`), `0.125`
(`0x100fe180`). ✅ Verified: reconstructing `USize` from the stored `UScale`/`USize` with
the flags-derived `scale` reproduces the stored `USize` on ~90% of axes; the residual is
float32 round-trip noise at interval boundaries (the stored `UScale` is a rounded copy of
the original extent), not a formula error. ✅ Max observed `USize/VSize` = 231/250 (< 256,
consistent with the cap). ✅

---

## 5. The raytrace — attenuation, shadow ray, participation (`Editor 0x100a5010`)

Signature `illuminateSurf(this, AActor* mover /*0 for static*/, INT iSurf, INT meshIndex)`.
It loads the surface's `pBase` point (`Points[surf.pBase]`), `Normal`/`TextureU`/`TextureV`
(`Vectors[surf.v*]`), and `&LightMap[surf.iLightMap]`. ✅

**Per-lumel loop** (`v` in `0..VSize`, `u` in `0..USize`, packed 8-at-a-time, §3): for each
light `Li` in the surface's list, compute the lumel's **world position** `P` (§6), then:

1. **Radius cut-off** ✅
   ```
   d2 = |P − Li.Location|^2                 # Li.Location = actor+0xd0 (FVector)
   R  = Li.WorldLightRadius()               # virtual; see below
   if R*R <= d2:  bit = 0    # out of range → dark, skip the ray
   ```
   `AActor::WorldLightRadius` (`Engine 0x116b50`): **`R = (LightRadius + 1) × 25.0`** world
   units, where `LightRadius` is the `BYTE` at `actor+0x1a1` (the classic UE1 ×25 radius
   scale). ✅ **This radius is the ONLY light property the bake reads** besides Location.
2. **Shadow ray (BSP line-of-sight)** ✅
   ```
   hit = Level->Model->LineCheck(FCheckResult, actor=NULL,
                                 end=Li.Location, start=P, extent=0, flags)
   bit = 1 if line is CLEAR else 0
   ```
   Call is the `Model` vtable slot at `+0x58` → `UModel::LineCheck`
   (`?LineCheck@UModel@@UAE...`, `Engine 0x1ae4c0`; base `UPrimitive::LineCheck`
   `0x192e20`). It traces the ray against the built BSP `Nodes`, treating **solid**
   surfaces as occluders; non-solid / semisolid / portal / masked surfaces do **not**
   block (standard `LineCheck` collision-flag behaviour — flags passed in `eax`). The
   editor uses the built world Model, so the ray test is a pure BSP node walk. ✅ (Port:
   `UModel::FastLineCheck`, `Engine 0x1ada40`, is the boolean-only variant to mirror.)
3. **Self-shadow bias.** The trace/lumel origin is pushed off the surface by
   **`Normal × 4`** world units (constant `4.0` at `0x100de9a8`) to avoid the surface
   shadowing itself. ✅

No `LightBrightness`, `LightHue`, `LightSaturation`, `LightType`, `LightEffect`, or
`bSpecialLit` is read in this loop. ✅ → they are **render-time** inputs, not bake inputs.

**Which lights participate** (gather pass `Editor 0x100a4ba0`): an actor contributes to the
static bake when its light-type field (`actor+0x19c`, checked `!= 0` — i.e. `LightType !=
LT_None`) is set and it passes the actor cast/flag filter; the renderer then reports the
set of surfaces each light can see, culled by radius. 🔬 Static-world lights bake into the
mask; **movers that carry lights are handled by a second loop** in `shadowIlluminateBsp`
that calls the same raytrace with `mover != 0` and the mover-surf index — their surfaces
are lit in the mover's base pose. 🔬 Dynamic/animated relighting (`LightType` animations)
is a runtime effect and is **not** part of this static bake. 📖

---

## 6. Lumel → world position (for the ray) — mechanism + residual

The lumel grid lives in the surface's texture frame. Per the raytrace and grid code the
ingredients are: the surface plane basis `TextureU`, `TextureV`, `Normal` (world vectors,
un-normalised, from `Vectors[]`), the base point `Base = Points[pBase]`, the texture-space
origin `Pan=(Umin−0.125, Vmin−0.125)`, and per-lumel spacing `UScale`/`VScale`. Lumel
`(u,v)` maps to texture coords `texU = Pan.X + u·UScale`, `texV = Pan.Y + v·VScale`, and its
world position solves `P·TextureU = texU`, `P·TextureV = texV`, `P·Normal = Base·Normal`
(a 3×3 inverse of `[TextureU; TextureV; Normal]`), then `P += Normal×4` bias. 🔬

**Residual — two DISTINCT items with different blast radius (don't conflate them):**
1. **Sub-lumel sample offset** (corner `u`, centre `u+0.5`, or the 2×2 supersample implied by
   the `0.25` constant at `0x100dcb00`). Affects **only where inside a lumel** the ray is cast
   → shadow-edge antialiasing. Genuinely cosmetic; a `u+0.5` centre-sample approximation is
   fine to ship.
2. **The inverse-basis assembly** (the exact `[TextureU; TextureV; Normal]` 3×3 inverse that
   turns `(texU,texV)` back into a world point). This is **NOT AA-only** — a wrong basis shifts
   **every** lumel's world position systematically, corrupting shadows across the whole surface
   (and every ray origin). It must be **validated against one real baked surface before any
   shadow output is trusted** — it is the one lighting item that can be silently, broadly wrong.
**To close both:** finish disassembling the grid-position loop at `Editor 0x100a5220–0x100a57ff`
(it already shows `divsd` by `(USize−1)`/`(VSize−1)` and `×0.25`), AND diff one baked surface's
bits against a Python trace for a hand-built room (the differential check gates item 2). Neither
blocks *load* — lighting is regenerable build output, never hashed — but item 2 blocks
"shadows are correct", so it is an N-4 correctness gate, not a cosmetic nicety. ✅ (non-block
for load; item 2 IS a correctness gate for shadows — see master spec §6)

---

## 7. Render-time meaning of the bits (documented for completeness — NOT baked) 📖

At level load / render the engine expands the bit-planes into the RGB lightmap the player
sees. For each surface, for each light `Li` and each lumel with bit=1:
`contribution = Attenuation(|P−Li.Location|, R) × Brightness(Li) × Colour(Li.Hue,
Li.Saturation)`, summed over lights; `LE_Negative` lights subtract. UE1's radial
attenuation is the classic falloff over `[0, R]` (≈ `1 − dist/R`, smootherstepped),
`Brightness` from `LightBrightness` (0–255), colour from `LightHue`/`LightSaturation` via
HSV→RGB. 📖 A native baker does **not** implement any of this — it is the game's job and
all its inputs are the light actors already in the T3D.

---

## 8. What a Python baker must emit (feeds the proven serializer)

The serializer (`bspspike/umodel_serialize.py`) currently **splices `0xa8`/`0xb4`/`0xe4`
raw**. To bake natively, replace those splices with encoders that emit, given the built
`Model` (BSP nodes/surfs/verts already generated by D2) and the level's `Light` actors:

**Algorithm:**
```
for each surf s (index i):
    if s.PolyFlags & (PF_Unlit|PF_Invisible|PF_FakeBackdrop|PF_Portal): s.iLightMap = -1; continue
    compute texture-space extent (Umin/Umax/Vmin/Vmax) from s's node verts · TextureU/V
    USize,VSize,UScale,VScale,Pan = grid_formula(s.PolyFlags, extents)   # §4
    lights = [L for L in level.lights if L.LightType!=LT_None
              and |lumelcentroid - L.Location| within (L.LightRadius+1)*25   # coarse cull
              and renderer/BSP says L sees s]                                 # §5 gather
    planes = b""
    for L in lights:
        for v in range(VSize):
            for byte in range(ceil(USize/8)):
                acc = 0
                for bit in range(8):
                    u = byte*8+bit
                    if u>=USize: break
                    P = lumel_world_pos(s, u, v) + Normal*4                   # §6
                    if |P-L.Location|^2 < ((L.LightRadius+1)*25)^2 and Model.LineCheck(P,L.Location) clear:
                        acc |= (1<<bit)
                planes += bytes([acc])
    if lights:
        L_rec.DataOffset   = len(LightBits); LightBits += planes
        L_rec.iLightActors = len(Lights);    Lights += [exportref(L) for L in lights] + [0]  # NULL term
    else:
        L_rec.DataOffset = 0; L_rec.iLightActors = -1                          # dark record
    L_rec.Pan=Pan; L_rec.UScale=UScale; L_rec.VScale=VScale; L_rec.USize=USize; L_rec.VSize=VSize
    s.iLightMap = len(LightMap); LightMap.append(L_rec)
```

**Encoders to add to `umodel_serialize.py`:**

- `enc_lightmapindex(L)` → in SERIAL order:
  `raw_i32(L.DataOffset)  +  f32(Pan.X)+f32(Pan.Y)+f32(Pan.Z)  +  ci(L.USize)+ci(L.VSize)
   +  f32(L.UScale)+f32(L.VScale)+raw_i32(L.iLightActors)`.
  Array: `ci(count) + concat(enc_lightmapindex(L) for L in LightMap)`.  ✅ (matches
  `Engine 0x1016f9f0`)
- `LightBits` array: `ci(len(bytes)) + bytes`.  ✅
- `Lights` array (`0xe4`): `ci(count) + concat(ci(objref) for ref in Lights)` — object
  refs are `.dx` export/import indices of the `Light` actors, with `ci(0)` NULL
  terminators between per-surf runs.  ✅
- `FBspSurf` encoder: write the (now correctly-named) `iLightMap` in field slot 7.  ✅

**Ordering/consistency the game requires (no absolute offsets — all self-contained):**
`DataOffset` and `iLightActors` are indices into the same-object arrays and can be assigned
sequentially by the baker; `surf.iLightMap` must equal the record's array index (the game
does `LightMap[surf.iLightMap]` directly, `Engine 0x1127c0`). Byte-exactness vs the editor
is **not** required (lighting is regenerable build output, never in the level hash) — only
internal consistency. ✅

---

## 9. Harness (this spike)

`dev/docs/spikes/2026-07-15-native-materialize/harness/`:
- `pe.py` — capstone/pefile disasm helpers (copied from `bspspike/`).
- `adis.py` — annotated disassembler (resolves call targets, floats, strings; accepts VA
  or RVA). `python adis.py Editor 0xa5bf0 0x400`.
- `lightmap_decode.py` — parses `Model` `0xa8`/`0xb4` arrays out of a real `.dx`; the
  `FLightMapIndex` field decoder.
- `lightmap_reconcile.py` — the `N × ceil(USize/8) × VSize` byte reconciliation + the
  `iLightActors`-run cross-check (the proof in §3).

Reproduce the proof:
```
cd dev/docs/spikes/2026-07-15-native-materialize/harness
<re-venv>/bin/python lightmap_reconcile.py /path/to/Maps/00_Intro.dx
```

## 10. Status / residuals

**Fully closed (✅):** entry point & pipeline; the four Model arrays + surf link; the
`LightBits` 1-bit/lumel/light row-byte-aligned encoding (double-proven); every
`FLightMapIndex` field + the grid-sizing formula and its constants; the radius model
(`(LightRadius+1)×25`); the shadow-ray function (`UModel::LineCheck`) and self-shadow bias
(`×4`); the light-list linkage (`iLightActors` → NULL-terminated `Lights` run); the encoder
spec for the serializer.

**Residual (🔬, §6):** TWO items — (1) sub-lumel sample offset = shadow-edge AA only,
cosmetic; (2) the lumel→world **inverse-basis assembly** = systematic (a wrong basis mis-places
every sample), so it is a **shadow-correctness gate**, not cosmetic — validate against one real
baked surface before trusting shadows. Neither affects any array size/offset/format or blocks
*load*. Close by finishing the `0x100a5220–0x57ff` grid-position disasm AND a one-surface live
diff.

**Documented but out of scope for the baker (📖, §7):** the render-time attenuation/colour
model — the game computes it from the light actors; the bake neither stores nor needs it.

---

## 11. The bake is DONE and byte-correct — but the LIT RENDER path needs a fuller Model (⚠️ live 2026-07-15)

> ⚠️ **PREMISE SUPERSEDED 2026-07-16 — see §12.** This section blamed the lit-render crash on **Model
> completeness** (missing `bspOptGeom` side pool / node `Bounds`) and proposed porting them. That is
> **WRONG**: a from-`Render.dll`-disassembly trace of the entire lit path proved it dereferences
> **NEITHER** the side pool (`iSide`/`NumSharedSides`) **NOR** node `Bounds` — do **not** port them for
> lighting. And a live re-test showed the crash is **LIT-ONLY**: a *dark*-record map (`iLightActors=-1`)
> now renders **clean** (the "NativeDark crashes" claim below predates the collision fix and is stale).
> Read §12 for the corrected root-cause hunt; the text below is kept for history only.

The native baker (§8) is **implemented and shipped** (`uedcli-native/src/light.rs` + `linecheck.rs`,
FFI `bake_lighting`, Python orchestration in `materialize.py`/`assemble.py`). It produces lightmap
output that is **field-for-field identical to real DeusEx maps**: decoding `NativeLit.dx` (our single
subtracted room + one steady Light) beside `00_Intro.dx` shows the same unit texture basis, the same
`FLightMapIndex` shape (`USize`/`VSize`/`UScale`/`Pan` in range), the same `N×⌈U/8⌉×V` bit-plane
sizing, and the same positive-export light refs + `0` NULL terminators in `Model->Lights`. The map
**loads, possesses the player, and the pawn stands** (`phys=Walking`).

**But the DeusEx software renderer faults per-frame when ANY surface is lightmapped.** ⚠️ The crash
stack (from the game's `Render.dll`, NOT `Engine.dll`) is
`URender::DrawFrame → FLightManager::SetupForSurf → SetupNormalSurface`, logged as
`Log: Anomalous singularity in URender::DrawWorld` (DrawWorld's `__except` swallows it, so the
headless game survives and the TCP link keeps answering — but no valid frame is produced, so
screenshots are black/garbage). The `SetupNormalSurface` guard string is at `Render.dll` VA
`0x10b2a350`, pushed at code VA `0x10b07136` (base `0x10b00000`).

**Isolation (live, 2026-07-15) — it is NOT the bake data, it is Model completeness:**
- **`NativeUnlit`** (the Light actor present, but every surf `iLightMap=-1`, no lightmap arrays): renders **CLEAN**, 0 singularities. → the light *actor* is fine; lightmaps are the trigger.
- **`NativeDark`** (every surf lightmapped, but all **DARK** records — `iLightActors=-1`, 0 bit-planes, empty `Lights`): **CRASHES** identically. → it is **not** the bits or the light iteration; a lightmapped surface *at all* triggers it.
- **`DXOnly.dx`** (a real single-box map that ALSO has all-dark records) renders with **0 singularities**.

So the difference between our crashing dark-record map and a rendering dark-record map is **Model
completeness**, decoded side by side (both: 6 surfs / 6 nodes / single subtracted box):

| | `DXOnly` (renders) | `NativeDark` (crashes) |
|---|---|---|
| `num_shared_sides` | **16** | **0** |
| vert `iSide` | **4…15 (real side-pool links)** | **all −1** |
| node `iCollisionBound` / `iRenderBound` | **52 / 4 (real Bounds indices)** | **−1 / −1 (empty Bounds)** |
| verts | 48 | 24 |

The native build ships a **minimal Model**: `passes::bsp_build_bounds` writes EMPTY Bounds arrays
(`iColl`/`iRend = −1`, the correct "skip" sentinel for `URender::OccludeBsp` — the section-50 fix)
and `bspOptGeom` (the T-junction / shared-side pass that fills `num_shared_sides` + `iSide`) is
**not ported** (§ section 10 §7.2/§10). The **UNLIT** render path tolerates all of this (that is why
`NativeCSG.dx` renders clean); the **LIT** path (`FLightManager::SetupForSurf` /
`SetupNormalSurface`) does **not**. Which of the two — the node **Bounds** or the **side pool** — is
the load-bearing requirement is not yet separated to instruction level (both differ; the software
renderer + struct layouts live in `Render.dll`, base `0x10b00000`, which now needs its own decode).

**Disposition.** `run_materialize_native` defaults **`no_light=True`** (renderable unlit build); the
bake is opt-in via `no_light=False` and gated behind this render dependency. **Next slice (own board
item):** decode `Render.dll`'s `SetupNormalSurface`/`SetupForSurf` to pin whether real node **Bounds**
(`bspBuildBounds` proper, + serialize the `c0`/`cc` arrays our writer currently drops) or the
**`bspOptGeom` side pool** (or both) is required for the lit render, then port the minimum needed.
This revises the section-50 premise that a *minimal* Model suffices — it suffices for **unlit** render
only.

---

## 12. Lit-render crash — corrected root-cause hunt (🔬 live + disasm, 2026-07-16)

§11's "Model completeness" premise is **refuted**. Two independent findings this session:

**(A) The lit path reads neither the side pool nor node Bounds (📖 `Render.dll` disasm).** A full trace
of `FLightManager::SetupForSurf` (`0x10b06c90`, `SetupNormalSurface` inlined; guard str `0x10b2a350`)
and its callees (`AddLight 0x10b08b30`, `Illuminate 0x10b05fa0`) shows the lit path dereferences ONLY:
- the surf's texture basis — `Surf.{pBase,vNormal,vTextureU,vTextureV}` → `Model.Points`/`Model.Vectors`
  (`0x10b1a995` in the lit drawer `0x10b1a2d0`), and
- `Surf.iLightMap` → `Model.LightMap` (`+0xa8`, `FLightMapIndex` stride `0x28`), `Model.LightBits`
  (`+0xb4`), `Model.Lights` (`+0xe4`).

It **never** loads `Model.Verts.iSide`, `Model.NumSharedSides`, or the node `Bounds`
(`iCollisionBound`/`iRenderBound`). **So porting `bspOptGeom` / real `bspBuildBounds` does nothing for
lighting** — the §11 "next slice" is void. Model offsets confirmed: Vectors `+0x78`, Points `+0x88`,
LightMap `+0xa8` (Num `+0xac`), LightBits `+0xb4`, Lights `+0xe4`.

**(B) The crash is LIT-ONLY (🔬 live, 2026-07-16).** Booted via `uplayctl session start --map`:
- **`NativeDark`** (every surf lightmapped but all-DARK records: `iLightActors=-1`, `LightBits` empty,
  `Lights` empty): renders **CLEAN** — 0 `Anomalous singularity`, player possessed. *(This overturns
  §11's "NativeDark CRASHES"; that was measured before the collision-topology fix landed.)*
- **`NativeLit`** (real lit records, `iLightActors>=0`, 128 B `LightBits`, `Lights=[9,0,...]`): crashes
  **every frame** — `Critical: SetupNormalSurface → FLightManager::SetupForSurf → URender::DrawFrame`,
  `Log: Anomalous singularity in URender::DrawWorld` (a caught per-frame SEH; the headless game
  survives but every screenshot is black).

The ONLY per-record difference between dark (renders) and lit (crashes) is `iLightActors` going from
`-1` (light loop skipped) to `>=0` (light loop runs). **So the fault is in the light-application path
that runs only for `iLightActors>=0`:** the light loop `0x10b070c6..0x10b070fc` (reads
`Model.Lights[iLightActors+i]` as an `AActor*`, calls `AddLight`, advances a bit-plane pointer
`LightBits.Data + DataOffset + i*bytesPerLight` where `bytesPerLight = VSize*ceil(USize/8)`).

**Ruled out (so the fix is narrow):** our lightmap arrays are internally well-formed — grid sizing
(`axis_grid`) matches `DXOnly` byte-for-byte (`(USize-1)*UScale == extent`, e.g. a 1024-wide wall →
`USize=32, UScale=33.04`); `Model.Lights` runs are NULL-terminated; every `DataOffset + bytesPerLight`
stays within `LightBits`; the surf texture basis is non-degenerate (unit vectors, `|U×V|=1`). And the
geometry-completeness fields are irrelevant per (A).

**(C) Full lit-path trace — `LightBits` format ELIMINATED; fault is the `Model.Lights` POINTER chain
(📖 `Render.dll` disasm, 2026-07-16).** A second exhaustive trace of the entire lit path settled it:

- **The renderer NEVER reads our baked `LightBits`, and re-raytraces the lightmap from scratch every
  frame** (this is *why* a lightmapped surface faults *per-frame*). The bit-plane pointer `esi =
  LightBits.Data + DataOffset + i*bytesPerLight` is computed and stored into the light-pool entry
  (`0x10b070f1 mov [edx-0x68],esi`) but **never read back** in `SetupNormalSurface`. So the
  **`LightBits`/1-bit-vs-1-byte question is moot** — (B)'s "prime suspect" is DEAD. Two proofs: (i) the
  renderer's own size formula `bytesPerLight = ceil(USize/8)·VSize` (`0x10b06ea2..0x10b06ed5`) already
  equals our 1-bit encoding; (ii) the stored bit-plane pointer is dead — the live path raytraces via
  `Illuminate` (`0x10b05fa0`) from the light actors instead.
- **The compute path is bounds-safe** with our data: the per-lumel raytrace consumer (`0x10b073bb`)
  writes a freshly-allocated `pow2(USize)·pow2(VSize)` buffer (our 8/16 sizes are powers of two → exact
  fit); the colour-ramp reads (`0x10b0784c`, base = `Illuminate`'s 256-entry table) are index-clamped
  `[0,255]`; all FP→int conversions are guarded. No overflow.
- **By elimination the fault is one of two unguarded runtime-pointer derefs in the `Model.Lights`
  chain**, which run ONLY for a lit record: `0x10b070d6 mov eax,[Model.Lights.Data + iLightActors*4]`
  (AV if `Lights.Data` is NULL/garbage or the index is past the loaded `Num`), or `0x10b08b4a mov
  al,[light+0x1e0]` inside `AddLight` (AV if the array element is not a resolved `AActor*`).
  **`Model.Lights` (`UModel+0xe4`) is the ONLY lightmap input whose *contents* are dereferenced** — the
  `FLightMapIndex` fields are read only as scalars, and `LightBits` is never read. So the malformed
  thing is `Model.Lights` **at runtime**: the on-disk bytes decode correctly (`[9,0,…]`, ref9→export8→
  `Light`, indices in-range, NULL-terminated) and the referenced `Light` export **is** a live spawned
  actor (in `ULevel.Actors`; the *dark* path already `AddLight`s it fine via the engine's own
  per-surface list `[arg3+0x40]`), yet reading it back through `Model.Lights` at render time faults.
  So the failure is in the **load-time array parse / element fix-up** of `Model.Lights`, not the bake
  and not the actor.

**Next step (the one decisive check): a live faulting-address dump.** At the crash, read `[Model+0xe4]`
(Lights.Data), `[Model+0xe8]` (Lights.Num), and `[Data + iLightActors*4]`. This distinguishes in one
shot: `Data==NULL` → the array didn't load at that stream position; `Num` short → index OOB; element a
non-pointer (e.g. the raw int `9`) → the loader read the refs but did **not** resolve them to
`AActor*`. Capture via `WINEDEBUG=+seh` (logs the first-chance AV EIP even though `DrawWorld`'s
`__except` swallows it): EIP `0x10b070d6` ⇒ NULL/short `Model.Lights`; EIP `0x10b08b4a` ⇒ unresolved
element. Then the fix is on the serialize/assembly side (`model_write.rs` Lights position/encoding vs
the *game's* `UModel::Serialize`, or the export-ref resolution), NOT the bake. `run_materialize_native`
stays `no_light=True` (renderable unlit) until it lands.

**(D) It is an FP SINGULARITY (divide-by-zero / invalid-op), NOT a pointer access violation
(🔬 live `WINEDEBUG=+seh`, 2026-07-16).** Booted NativeLit under wine SEH tracing and let it crash-loop
(260+ `Anomalous singularity` lines in `DeusEx.log`). The `+seh` channel logged **NO `c0000005`
(EXCEPTION_ACCESS_VIOLATION)** for those frames — so the fault is **not** a bad-pointer deref. This
refutes (C)'s "unguarded `Model.Lights` pointer deref" as the *mechanism* (the pointer chain is likely
fine after all). The name is literal: `URender::DrawWorld` **unmasks the x87 FP exceptions** and its
`__except` filter (logs the string at `Render.dll 0x10b1ced0`) catches a **`STATUS_FLOAT_*`** raised by
a **divide-by-zero / invalid-op in the lit lightmap math** — a *degenerate/singular* computed value,
per-frame, only for lit records. This matches the `fdiv` sites found in the lit region:
`0x10b07696 fdiv st(1)` = `d² / (a²+b²+c²)` where `V=(a,b,c)` is a lightmap basis/attenuation vector
written at `0x10b075c2` as `(edx,eax,edx)` — if `|V|²==0` the divide raises the FP exception. (Also
`0x10b076f3`, `0x10b07979`, `0x10b079d7`.) **So the fix is to make our lit-surface lightmap inputs
produce a non-degenerate divisor** — the open step is tracing `V`'s components (from the light
position / lumel basis / `Illuminate`'s attenuation-coeff build at `0x10b05fa0`) back to which of our
emitted values (surf `Pan`/`UScale`/`VScale`, or the `Light` actor's missing `LightHue`/`LightSaturation`
defaults, or a light-to-lumel distance/normal) is zero for our single-room+center-light case. Confirm
by re-capturing with a broad `+seh` filter (`code=|except|addr=`, not just `c0000005`/`eip=`) to read
the exact `STATUS_FLOAT_*` code + faulting VA, then port the guard the editor's bake implicitly
satisfies. Still `no_light=True` until it lands.

**Net corrected picture (what the next session should NOT re-investigate):** it is lit-only; it is an
FP singularity in the render-time lightmap math, not a geometry/Model-completeness gap (side pool &
Bounds are never read), not a `LightBits` format issue (never read — the renderer re-raytraces), and
(per the `+seh` evidence) not a `Model.Lights` pointer AV. The hunt is a **degenerate divisor in the
lit lightmap transform**; the fix is in the bake / light-actor property emission, never a BSP port.

**(E) The singular divisor is a matrix-transformed lightmap-projection vector (📖, 2026-07-16).** The
`fdiv` divisor `|V|²` at `0x10b07696` uses `V = [ebp-0x4c/-0x48/-0x44]`, copied (`0x10b075bc`) from the
vector local `[ebp-0x30/-0x2c/-0x28]`, which is itself copied (`0x10b0745f`) from `[ebp-0xd4/-0xd0/-0xcc]`
— the OUTPUT of a 3×3 matrix·vector transform (`0x10b07408..0x10b07450`, multiplying by an `FCoords`-style
matrix at `[edx+0xc..0x2c]`). So the "singularity" is a **degenerate lightmap-space → screen projection**
(the transformed basis vector collapses to length 0), consistent with the message's literal meaning. The
un-pinned link is which input (`[ebp-0xd4]` pre-transform, or the `[edx+0xc]` matrix) is degenerate for
our single-room+center-light lit surfaces — that needs the **live faulting register dump** (broad `+seh`
`code=|except|addr=`, or a winedbg breakpoint at `0x10b07696`), which the boot/console-link infra
blocked this session. NOT a bake byte-format bug; likely a light-actor property or a lightmap-basis the
editor's bake sets up that our synthesized inputs don't. `no_light=True` remains the safe default.

**(F) DEFINITIVE: it IS a `c0000005` access violation at `AddLight` — and a REAL lit map renders,
so OUR synthesized map is malformed (🔬 live, 2026-07-16).** A broad `WINEDEBUG=+seh` capture (my
earlier narrow filter `c0000005|eip=` missed it — wine logs `code=c0000005 … ip=`, not `eip=`) caught,
every crash frame:
```
011c:trace:seh:dispatch_exception code=c0000005 flags=0 addr=10B08B4A ip=10b08b4a
011c:warn:seh:dispatch_exception EXCEPTION_ACCESS_VIOLATION exception (code=c0000005) raised
```
So (D)'s "FP singularity" is WRONG — it is a genuine **access violation at `Render.dll 0x10b08b4a`** =
`AddLight`'s `mov al,[ebx+0x1e0]`, where `ebx = Model.Lights[iLightActors]` (§(C) chain). `ebx` is a
**bad light pointer** (it was read successfully — the fault is dereferencing it — so `Model.Lights[i]`
holds a non-NULL bad value: an unresolved raw ref like `9`, or a wrong/too-small object).

**The decisive control: a REAL lit map renders CLEAN in the SAME headless software renderer.** The boot
map **`DX.dx`** (26 surfs, **3 lit records** `iLightActors>=0`, 192 B `LightBits`, **37** `Model.Lights`
entries referencing 5 `Light` exports) possesses the player and renders with **0 singularities** before
the travel to `NativeLit`. Its `Model.Lights` is the SAME FORM as ours (positive `Light` export-refs +
`0` terminators, e.g. lit run `[8,2,4,7,0]`). So the software renderer handles lit maps fine, the game
DOES resolve `Model.Lights` to valid `AActor*` (else `DX.dx` would fault identically), and **our
synthesized map is the malformed one** — a `native/assemble` (light-export or `Model.Lights`) emission
bug, NOT the bake math, NOT geometry, NOT `LightBits`.

**The last inch (blocked this session by tooling):** need the runtime value of `ebx` at `0x10b08b4a`
(raw ref `9` ⇒ the game didn't resolve OUR Lights array; a heap pointer ⇒ resolved to a wrong/partial
object). This headless crash-looping wine env gave no stable debugger: **no `gdb`**, and `winedbg`
attach was intermittent (it CAN list procs — DeusEx.exe was winpid `0x118` — but the batch
`attach;break *0x10b08b4a;cont;info reg` produced no output before the game restarted). **Next session:
on a fresh boot (before the crash-loop wedges wine), `winedbg` `attach <winpid>; break *0x10b08b4a;
cont; info reg` to read `ebx`; then diff OUR light-export table entry + `Model.Lights` serialize against
`DX.dx`'s** (both parse offline via `native/umodel.py` + `pkg_write.py`; `DX.dx` light exports are
`Engine.Light`, `outer=0`, positive refs — identical in every field we've checked, so the divergence is
subtle: candidate = load-order/`Preload` of the light export when `Model.Lights` resolves it, or a
light-body property-tag that leaves the constructed object partial). `no_light=True` stays the default.

**(G) `Region` prop RULED OUT (🔬 live, 2026-07-16).** A real light carries a `Region`
(PointRegion) prop and a `Tag`/`OldLocation`; our synthesized light carried none. Hypothesis: the
missing `Region` caused the bad-pointer crash. **Tested and DISPROVEN** — added a `Region`
placeholder (`Zone=None, iLeaf=-1, ZoneNumber=0`) to every placed actor
(`materialize._trunk_to_actorspecs`), rebuilt `NativeLit`, booted: **still 239 singularities**.
Confirms §(F)'s logic — a byte-read `[light+0x1e0]` faulting means `light` is a bad *pointer*, which
props (object-size-invariant) can't change. The `Region` addition is KEPT as a fidelity improvement
(real maps all have it; the engine recomputes it), but it is NOT the render fix. So the remaining
candidate is squarely **`Model.Lights` element resolution / light-actor lifetime at render time** —
needs the runtime `ebx` value (§(F) next step).

**(H) Every static aspect is verified correct — the light IS retained (🔬, 2026-07-16).** To rule
out a GC/lifetime cause of the bad pointer: decoded `NativeLit.dx`'s `ULevel.Actors` array =
`[LevelInfo(exp0), Brush0-default(exp3), RoomA-brush(exp6), PlayerStart(exp7), Light(exp8)]` — the
**Light (export 8) IS referenced by `Actors`**, so the engine retains it (not collected). Combined
with §(F)/§(G): the light export's class (`Engine.Light`), flags (`0x02070001`), `outer` (`0`), the
`Model.Lights` ref (`9→export8`), its indices, NULL-termination, AND its `Actors` membership all
match a rendering real map. **So the bad pointer is a pure RUNTIME phenomenon with no offline
signature** — `Model.Lights[iLightActors]` resolves to bad memory at render despite a byte-correct,
fully-cross-referenced on-disk package. The ONLY remaining way forward is the live `ebx` read at
`0x10b08b4a` (§(F) next step) — everything statically checkable has been checked and matches.

**(I) Serialization RULED OUT — our UModel body is byte-exact vs the game's `UModel::Serialize`
(📖 disasm, 2026-07-16).** Decoded the game's real `UModel::Serialize` (Engine.dll vtable slot 10 →
`0x103acaa0`; the `v>61` branch at `cmp [Ar+4],0x3d / jg`). Field order it reads (== our
`model_write.rs`): UPrimitive prefix (bbox, via Super `0x10303c0b`) → Vectors(+0x78) → Points(+0x88)
→ Nodes(+0x58) → Surfs(+0x98) → Verts(+0x68) → **NumSharedSides(+0xfc, i32)** → **NumZones(+0x100,
i32) + Zones inline[0..N] (+0x104, 0x18 B each)** → Polys(+0x54, objref) → LightMap(+0xa8) →
LightBits(+0xb4) → Bounds(+0xc0) → LeafHulls(+0xcc) → Leaves(+0xd8) → **Lights(+0xe4)** → trailing.
Per-zone serialize (`FZoneProperties::Serialize 0x103aed30`) = `Ar<<ZoneActor`(objref) + 8 B
Connectivity + 8 B Visibility — **exactly our `ci(actor_ref)+u64+u64`**. And the **Lights array
serializer (`0x103a14f0`)** reads a compact-index count then, per element (loop body `0x103a15a8`),
`Ar << (UObject*&)` via **archive vtable+0x18** — i.e. it **RESOLVES each compact-index ref to an
`AActor*` pointer** at load. So our `Model.Lights=[ci9,ci0,…]` is read as `[Light*,NULL,…]`, the same
as DX.dx. **Every array's order and encoding matches the game byte-for-byte.**

**Net:** geometry-completeness, LightBits format, FP, Region/props, GC, AND serialization are all
RULED OUT. The `Model.Lights[iLightActors]` bad pointer at `AddLight 0x10b08b4a` is a genuine
**runtime** phenomenon (resolution/lifetime) with **no static/offline signature** — a byte-exact,
fully-cross-referenced package whose light ref resolves fine for DX.dx but to bad memory for ours.
The ONLY remaining diagnostic is the live `ebx` value at the fault (or the `AddLight` caller — the
`Model.Lights` lit-loop `0x10b070e2` vs the engine relevant-light-list walk `0x10b07112`), which this
environment's debuggers cannot deliver (§ engine-internals/gotchas.md §4). Candidate next hypotheses
to test EMPIRICALLY (each a boot): the light needs `bStatic`/light-registration props so the engine's
per-surface relevant-light list is well-formed; or it must be a DeusEx light subclass not base
`Engine.Light`; or `Model.Lights` should dedup the repeated ref. None are confirmed.

## 13. Live register capture cracks it: the fault is an FP singularity in `SetupForSurf`, NOT the `Model.Lights` pointer (🔬 live binary-patch, 2026-07-16)

§12's whole framing — "the `Model.Lights[iLightActors]` bad pointer is the crash" — is **overturned**
by live evidence obtained with a NEW capture technique that sidesteps the tooling walls.

**(A) The reproduction is reliable and fast (✅ live).** `bin/uplayctl`-style boot (`game-entrypoint.sh`
now RELAUNCHES DeusEx.exe until the console link binds — see it + `engine-internals/gotchas.md`; this
beat the wine boot-deadlock that blocked §12) → travel to a lit native map → `grep -c "Anomalous
singularity" DeusEx.log`. NativeLit reliably logs ~239–261 caught exceptions within ~90 s of boot,
then **double-faults** (`Exit: Double fault in object ShutdownAfterError`) — the render does NOT
survive per-frame as §11/§B implied; it dies after the initial burst, so you cannot drive frames
post-crash (the console link is dead by then).

**(B) The live-value capture technique that finally works (🔬).** Both prior routes are dead here:
ptrace-`INT3` yields **0 SIGTRAPs** (wine's `__except` around `DrawWorld` swallows the guest breakpoint
before the host tracer sees it), and `WINEDEBUG=+seh` logs only `code= addr= ip=` (no registers, no
access address). The route that works — **binary-patch the faulting instruction in the live process to
STORE a register to a scratch `.data` global, then early-return before the fault** (no guest exception
raised, so `__except` never fires):
- Patch `AddLight` (`Render.dll` @ base `0x10b00000`): `0x10b08b4a` `8A 83 E0 01 00 00`
  (`mov al,[ebx+0x1e0]`) → `89 1D <addr>` (`mov [scratch],ebx`, exactly 6 B); `0x10b08b50` `84 C0`
  (`test al,al`) → `30 C0` (`xor al,al`, so the following `je 0x10b08c62` returns before the 2nd read).
  Scratch = `0x10b5c800` (`.data` BSS tail, verified 0). `/proc/<pid>/mem` writes to `.text` bypass page
  RO with `SYS_PTRACE`. To patch safely, apply it **while on the clean boot map** (`DX_MAP=DX`, link
  alive, render pid stable — Render.dll byte@`0x10b08b4a`==`0x8a`), then `TravelToLevel NativeLit`.
  Harness: `spikes/.../harness/game_capture_patch.py` (+ `capture2.py` orchestration).
  **CAUTION:** the render byte `0x8a` appears BEFORE `UPlayCtlLink` binds `:7777` — gate the capture on
  `:7777` listening too, or the console travel throws `ConnectionRefused`.

**(C) `Model.Lights[iLightActors]` resolves to a VALID, MAPPED `AActor*` (🔬 — kills §12(F)/(H)).**
Captured `ebx = Model.Lights.Data[iLightActors] = 0x07c9ce80`, and `[ebx+0x1e0]` **IS mapped**. So the
array element is a real resolved object pointer, **not** an unresolved raw ref (`9`) and not obviously
garbage. The disassembled caller confirms the read: lit-loop `0x10b070c8` does `edx=FLightMapIndex.iLightActors
(+4); ecx=Model.Lights.Data (Model+0xe4); eax=[ecx+edx*4]; test eax,eax; je (NULL ends run); push eax;
call AddLight`. `AddLight` prologue: `mov ebx,[esp+0x14]; mov al,[ebx+0x1e0]`. With a mapped `ebx`, that
read cannot AV — so §12(F)'s "definitive AV at `AddLight`" was NOT the whole story (likely a per-boot
heap-layout artifact on some frames, or a misattribution). **`Model.Lights` is fine.**

**(D) Neutering the `AddLight` read does NOT stop the crash — the fault is in `SetupForSurf` itself
(🔬 DECISIVE).** With `AddLight` patched to store-and-return (so its `[ebx+0x1e0]`/`[ebx+0x1e2]` reads
never execute), NativeLit STILL logs `Anomalous singularity in URender::DrawWorld → SetupNormalSurface
→ FLightManager::SetupForSurf`. So the caught exception is raised in `SetupForSurf`'s own body, NOT in
`AddLight`, NOT via the `Model.Lights` element. The prime candidate is §12(D)/(E)'s **FP divide-by-zero**:
`0x10b07696 fdiv st(1)` where `st(1) = |V|²` accumulated at `0x10b0764d..0x10b07668` from
`V=([ebp-0x4c],[ebp-0x48],[ebp-0x44])`; `V=(0,0,0)` ⇒ FP singularity (the message is literal).
`V`'s source (`0x10b07453..0x10b07470`): `V = ([ebp-0xd4],[ebp-0xd0],[ebp-0xcc])`, itself the output of a
**3×3 `FCoords`·vector transform** at `0x10b07482..0x10b074c1` (`M = [ebp-0xe4]` per-surface matrix,
`g = *0x10b49e10` a fixed vector). So `V=0` means the per-surface **lightmap-basis matrix `M` is
degenerate** (or `g` zero). This runs in a per-lumel double loop (`USize×VSize`), so ONE degenerate
lumel faults the frame.

**(E) It is NOT the light's position/symmetry (🔬 — tested).** Hypothesis "our light sits at the exact
symmetric room centre `(0,0,96)`, perpendicular through a lumel ⇒ `V=0`" — **DISPROVEN**: an off-centre,
non-axis-aligned light `(137,89,96)` produces an identical lit bake (6 surfs, 128 B, 870 set bits) and
**still crashes with 239 singularities**. So `V=0` comes from the **surface / lightmap-basis geometry we
emit**, independent of the light. (Our surf bases are unit+orthogonal and `Pan`/`UScale`/`VScale` are
sane vs `DXOnly`/`Entry` — but note `DXOnly`'s records are all DARK `iLA=-1`, so its lit-path FP math
never runs; it is NOT a valid "lit renders clean" control. `Entry.dx` has 3 genuine `iLA>=0` lit records
and renders clean — it is the control to diff against.)

**Net (supersedes §12's pointer framing):** the lit-render crash is a **runtime FP singularity in
`FLightManager::SetupForSurf`** (`fdiv` by a zero-length lightmap-projection vector `V=M·g`), NOT the
`Model.Lights` pointer (which resolves valid), NOT the light position, NOT the bake byte-format (still
byte-exact). The open step is to identify which emitted per-surface lightmap input makes the projection
matrix `M` (`[ebp-0xe4]`, built from the surf's texture basis + `Pan`/`UScale`/`VScale` + lumel grid)
degenerate for our surfaces but not for `Entry.dx`'s lit records. Two concrete next moves: (i) capture
`M`/`g` live at `0x10b07453` with the same store-to-scratch patch (it's 9 floats → store to
`0x10b5c800..` and read back); (ii) field-by-field diff our `iLA>=0` `FLightMapIndex` + surf basis
against `Entry.dx`'s 3 lit records (`iLA` 22/27/32). `run_materialize_native` stays `no_light=True`.

## 14. ACTUAL ROOT CAUSE + FIX: `FBspSurf` had `iLightMap`/`iActor` serial-swapped (✅ FIXED, 2026-07-16)

**§13's "FP singularity" conclusion was WRONG** — a red herring. Two clean checks settled it:

**(A) The fault is unambiguously the `AddLight` AV, not FP (✅ `WINEDEBUG=+seh`, direct NativeLit boot).**
A clean boot straight to NativeLit under `+seh` logged **254 exceptions, 100% `code=c0000005` (access
violation) at `ip=0x10b08b4a`** (`AddLight`'s `mov al,[ebx+0x1e0]`), and **ZERO `STATUS_FLOAT_*`**. The
`0x10b07696 fdiv` never faults (that branch isn't taken). §13's "neutering AddLight still crashes" was a
**contaminated run** (it then travelled to `DXONLY` and hit an unrelated `Critical` in `PostLoad`), and
§13's "`Model.Lights` resolves to valid `0x07c9ce80`" was a **stale scratch-global read** — `capture2`
never cleared the scratch after travel, so it read a leftover **DX.dx** light pointer, not NativeLit's.
Lesson: clear the capture slot AFTER confirming the target level; don't trust a value that could predate
the travel.

**(B) The bug: `FBspSurf` on-disk field order (✅ verified vs `DXOnly`/`DX`/`Entry`).** Raw-decoding real
maps' surf bytes shows the true order is:
```
Texture, PolyFlags, pBase, vNormal, vTextureU, vTextureV,
  iLightMap (slot 7, ci),  iBrushPoly (ci),  iZone[0] (u16), iZone[1] (u16),  iActor (last, ci)
```
Proof: in real maps the **slot-7** value increments per surface (`0,1,2,3,…` = one `FLightMapIndex`
record per lit surf) while the **last** value is constant and **resolves to a `Brush` export** (the owning
brush). Our emitter (`umodel._enc_surf` + Rust `model_write.rs::put_surf`) had them **reversed**: it wrote
`iActor` in slot 7 and `iLightMap` last. So the game read `surf.iLightMap` from our `iActor` value —
`7` (the RoomA brush export ref) — which is **out of range** of our 6-record `Model.LightMap` →
`LightMap[7]` is garbage → its `iLightActors` is garbage → `Model.Lights[garbage]` is a **bad pointer** →
the AV in `AddLight`. This is exactly the §12(F) signature, now explained. It was invisible to the
self-check because `_enc_surf`/`_parse_surf` shared the same wrong order and still reached EOF (the widths
are unchanged — EOF validates SIZE, never field SEMANTICS; this is the second time an EOF-passing order
bug bit us — cf. the collision node-child swap in §50/§60).

**(C) The fix.** Swap the two fields in all three emitters/parsers, byte-identical: `umodel._enc_surf`,
`umodel._parse_surf`, and Rust `model_write.rs::put_surf` → real order above. Rebuilt the extension
(`maturin develop --release`); offline suite **156 passed** incl. the gate-5 Rust==Python golden.
Rebuilt NativeLit now decodes with `iLightMap = 0..5` (in-bounds) and `iActor = 7 → Brush RoomA` — matching
the real-map pattern. The `Model.Lights` array, the light export, the bake bytes, and geometry were all
correct all along; **only the surf field order was wrong.**

**Meta:** §13's whole FP investigation (and the `V=M·g` disasm, the `M`/`g` capture plan, the
light-symmetry test) chased a branch that never executes. Kept above only as a record of the wrong turn;
the `AddLight`/`Model.Lights` framing of §12(F)/(I) was right — the missing piece was simply the surf
serial order, found by diffing our surf bytes against real maps field-by-field (the check §12 never did:
it verified the Model ARRAY order byte-exactly but not the per-`FBspSurf` FIELD order semantically).

## 15. Complex-map confirm (the CASTLE) + texture/asset wiring the real map needs (✅ 2026-07-16)

After the §14 surf fix, `run_materialize_native` now **defaults `no_light=False` (lit)**; NativeLit renders
clean. Verifying on the **real castle** (`_scratch/castle/uedcli/maps/foobar`, 161 actors → **418 lit
surfs, 90 brushes**) surfaced — and fixed — two ASSET-WIRING gaps that a textured map hits but the
textureless NativeLit never did:

**(A) Texture imports were missing the GROUP and had the wrong ClassPackage (both verified vs the
editor-built `Test_Castle.dx`).** A trunk poly stores a 2-part `Texture=LUM_CoreTex.concrete_02`, but the
real texture lives in a **group** (`LUM_CoreTex.Concrete.concrete_02`), and a UE1 import's **ClassPackage
must name the class's defining package (`Engine` for `Texture`), NOT the object's package**. Our
`content_ref` emitted `LUM_CoreTex.concrete_02` with `ClassPackage=LUM_CoreTex` → the game raised
`Can't find Texture in file 'Texture LUM_CoreTex.concrete_02'` and refused to load the level. Fixes in
`native/pkgref.py`: (i) `build_texture_group_index(pkg_dirs)` scans the `.utx` on the search path and
maps `(package, name) -> group chain`, so `object_ref` re-attaches the group (`run_materialize_native`
gained a `pkg_dirs` arg; the index is threaded through `assemble_level(texture_groups=…)`); (ii)
`content_ref` now emits `ClassPackage="Engine"`. Result: our imports are byte-shaped like the editor's
(`Engine`/`Texture`, outer chain `LUM_CoreTex.Concrete.concrete_02`) and the castle **loads with 0
`Can't find Texture`**.

**(B) The headless game needs the project's OVERLAY packages.** The castle imports `LUM_CoreTex.utx`
(a custom LUM package in `DX/LUM/Textures`, not in the base game install the container mounts).
`game-entrypoint.sh` now makes `$R/Textures` a symlink FARM (was a bare dir symlink) and, if `/overlay`
is mounted, symlinks the overlay's `Textures/*.utx` (shadowing base by stem) and `System/*.u`/`*.utx`
into the game root — the composed search path (project shadows base). Boot scripts mount `DX/LUM` at
`/overlay`.

**(C) Result.** The castle **boots to `READY map=NativeCastle`, textures all resolve (0 errors), renders
with 0 `Anomalous singularity`**, player possessed — the surf fix + lighting generalize to a 418-lit-surf,
90-brush, real-textured map. Static cross-check: all 418 lit surfs have in-range `iLightMap`, all 90
`iActor` refs resolve to `Brush` exports. *(Remaining, orthogonal: like NativeLit, a console-`open`ed
custom map renders then DROPS TO THE MAIN MENU (DXONLY backdrop) — a headless game-session flow limit,
not a render bug; a first-person still needs a real New-Game session then in-game `open` — see board.)*

## 16. `FLightMapIndex.Pan` is BASE-RELATIVE, not raw world — the RAINBOW bug (✅ FIXED, 2026-07-16)

After §14/§15 the lit castle **loaded and rendered without crashing**, but every surface was smeared
with a smooth **rainbow gradient** (orange→red→green→blue bands across walls/roofs/floors) instead of
the editor's subtle tinted stone. Building the SAME map UNLIT rendered clean, so geometry/textures/zones
were fine — only the lightmap **sampling transform** was wrong.

**Root cause: `Pan` was computed as the raw world dot `min(vertex·TextureU)`, but the editor (and the
renderer that samples against it) work in the surface's **base-relative** texture frame
`min((vertex − Base)·TextureU)`** (`Base = Points[pBase]`). Spike §4 originally mis-stated this as "raw
dot products" — WRONG.

**Proof (field-for-field vs `Test_Castle.dx`, the editor oracle).** For every lit surf, the stored
`Pan` equals `base-relative Umin/Vmin − 0.125`, never the raw world value. E.g. editor surf#0:
stored `Pan.Y = −210.12`; `(vertex−Base)·TextureV` min = `−210.00` ✓; raw `vertex·TextureV` min =
`0.00` ✗. Holds across all 484 records (the raw and base values coincide only on axes where
`Base·TextureAxis ≈ 0`, which masked the bug on some surfs).

**Why it made a rainbow.** With raw dots, `Pan` landed at world coordinates (e.g. `Pan.Y = −1150`) while
the renderer computes each world point's lumel index in the **base-relative** frame `((P−Base)·Tex −
Pan)/Scale`. A `Pan` off by ~1150 world units, divided by a ~32-unit lumel pitch on a grid only ~14–72
lumels tall, pushed the sample tens of lumels out of the surf's own plane → it read **adjacent surfaces'
bit-planes / neighbouring lights** in `LightBits`, blending all the castle's coloured lights (orange
hue≈28 + cyan hue≈156) into a continuous spectrum.

**The fix (`uedcli-native/src/light.rs`, `bake_surf`).** Project vertices base-relative:
`base_u = Base·TextureU; u = vertex·TextureU − base_u` (same for V). `extent = Umax − Umin` is unchanged
(base-invariant) so **USize/UScale/VSize/VScale are untouched** — only `Pan = Umin − 0.125` moves into
the small/local base-relative frame. The per-lumel raytrace still needs **world** positions, so
`lumel_world` receives `tex_u + base_u` (converting the base-relative grid coord back to the world dot
`P·TextureU`) — world sample positions, shadow LOS, and radius culling are byte-identical to before; only
the STORED `Pan` changed.

**Before → after (native castle, comparable surf).** `pan=(−0.1, −1150.1)` (world) → base-relative
`Pan == base(Umin,Vmin) − 0.125` for every surf (e.g. `(−0.12, −0.12)`, `(−420.12, −2300.12)`), grids
unchanged (U/V ∈ 2..72), matching the editor's rule exactly.

**Verified live.** Rebuilt `NativeCastle.dx`, booted headless (`uplayctl session start --map
NativeCastle`): **0 `Anomalous singularity`, 0 double faults**, player possessed, first-person render is
clean light-grey stone + orange wood/torches with subtle shading — visually indistinguishable in lighting
character from the editor's `Test_Castle.dx` (A/B captured same session). **No rainbow.** The light COLOUR
path needed no change — the light actors already carry correct `LightHue`/`LightSaturation`/
`LightBrightness` (§0: colour is applied render-side from the actors), confirmed by the correctly-tinted
result. Offline suite stays green (1240 passed).

## 17. Native lighting was FLATTER than the editor — the missing BACKFACE CULL (✅ FIXED, 2026-07-17)

After §16 the lit castle rendered with correct colour and no rainbow, but an 80-shot in-game A/B
(`NativeCastle.dx` vs the editor oracle `Test_Castle.dx` at identical poses) showed the native
lighting was **flatter and weaker** — less falloff, washed-out contrast, some interiors too dark or
oddly green — versus the editor's moodier depth (bright near lights, dark in corners).

**Root cause: our bake had NO backface cull; the editor's does.** The bake assigns, per surface, the
list of lights that illuminate it (`Model.Lights` runs, indexed by `FLightMapIndex.iLightActors`).
A light only belongs on a surface's list if it is on the **front side of the surface's plane** — the
side the face looks toward. Measured directly on the two built maps (`_scratch/backface.py`), for
every `(surf, light)` list entry the signed distance `d = (Light.Location − Base)·vNormal`
(`vNormal` is unit-length, so `d` is the true perpendicular distance):

| | (surf,light) pairs | back-facing (`d ≤ 0`) | lights per lit surf |
|---|---|---|---|
| **Editor `Test_Castle.dx`** | 3497 | **0 (0.0 %)** | mean 7.95, median 7 |
| **Native (before fix)** | 5486 | **2586 (47 %)** | mean 13.58, median 12 |
| **Native (after fix)** | 2900 | **0 (0.0 %)** | mean 7.73, median 7 |

The editor **never** lists a light behind a surface's plane; our bake listed a back-side light on
~47 % of assignments — nearly **doubling** the lights per surface. Each spurious back-side light adds
a dim, broad, roughly-uniform contribution at render time (the game applies its attenuation to every
lumel the light's plane touches), which **raises the floor everywhere and collapses the contrast** —
exactly the "flatter, weaker falloff" symptom. Removing the back lights drops native's lights/surf
from 13.58 → 7.73, matching the editor's 7.95 (the small residual is the editor's slightly different
BSP splitting the surfaces differently, not a lighting difference).

**Why our per-lumel BSP line-of-sight didn't already cull them.** Clear line-of-sight to a surface's
FRONT face is *geometrically impossible* from behind its plane, so for **correct** geometry backface
and LOS coincide and the cull looks redundant — which is why §5/§7 didn't flag it. But our native
`linecheck::line_clear` traces against a **not-yet-fully-portalized BSP** that **leaks**: rays slip
through gaps and reach lights that are geometrically behind the surface. The editor's gather pass
(`Editor 0xa4ba0`) sidesteps this with renderer-visibility (disasm confirms it delegates to
renderer vtable calls; the **front-side** conclusion is measured from the oracle's 0/3497, not read
from source), so a leaky ray test can never over-include. This corrects §0/§5's implicit "radius +
LOS is the whole participation test": **front-side plane test + radius + LOS** is.

**Latent generic-UE1 gap (not a castle regression).** The cull assumes single-sided surfaces. A
`PF_TwoSided` surface renders its one lightmap from *both* faces, so the editor could legitimately
list a light on the "back" side; the strict plane test would drop it, making that surface darker than
the editor. `Test_Castle` has zero such cases (the 0/3497 basis), so this is untested for other maps —
tracked in `board/inbox.md`. Do not add two-sided handling speculatively without an oracle for it.

**The fix (`uedcli-native/src/light.rs`).** In `bake_surf`, before a light does any per-lumel work,
skip it unless it is strictly in front of the surface plane:
```rust
fn light_in_front(normal: &Vec3, base: &Vec3, light: &Vec3) -> bool {
    light.sub(base).dot(normal) > 0.0   // strict: editor min front-dist observed = +1.96, back = 0
}
```
Applied per surface (all lumels of a planar surf share the plane), so it also saves the per-lumel LOS
work for culled lights. No other lighting input changed — colour/brightness/attenuation stay
render-side from the actors (§0), and the light actors are byte-identical between the two maps
(verified: all 62 lights match on `LightBrightness`/`LightRadius`/`LightHue`/`LightSaturation`/
`LightType`/`LightEffect`; only 3 carry a default-valued animation `LightPhase`/`LightPeriod` the
editor omits — no visual effect).

**Verified in-game (2026-07-17).** Rebuilt `NativeCastle.dx`, re-shot the A/B at the matched poses
(`_scratch/shots/lightfix{,-ed}/`, pairs in `_scratch/shots/lightfix_pairs/`). Native walls now carry
the editor's brightness, contrast and warm/grey balance — the flat, dark, greenish cast is gone
(clearest on the marble hall `s34` and the stone corridor `s01`/`s07`). Remaining A/B differences are
the **black backdrop / fragmented geometry** in wide shots (`s49`, parts of `s07`) — the sky/zone
portalization issue owned by a separate work item, NOT lighting. Rust light tests + offline suite green.

## 18. The last black surfaces were BSP OVER-OCCLUSION, not a lighting bug — fixed by shipping the `bspcsg` core (✅ 2026-07-17)

After §17 the walls matched, but ~58 interior floor/ledge surfaces still rendered PURE BLACK in-game
where UnrealEd shows lit grey. This is NOT a lighting-input bug: the light actors are byte-identical,
zone ambient is 0 in both maps, and the bake math is correct. The cause is the **BSP the bake's LOS
runs against**.

**Mechanism.** For each lumel the bake pushes the ray origin off the surface by `+Normal*4` (the
`SELF_SHADOW_BIAS`, `light.rs`) and calls `linecheck::line_clear(origin → light)`. The default
(`build_geometry`, coarse) core's merge-then-single-rebuild partition LEAKS some solid cells: the
space just ~4uu above certain interior ledges is wrongly classified **SOLID**, so the biased origin
lands *inside solid*, `line_clear` returns occluded for EVERY light, the record bakes all-dark, and
the surface renders `texture × 0 = black`. Confirmed with a point-in-solid probe mirroring
`linecheck::is_csg` + the terminal-cell rule: on the coarse model the `+4`-above-ledge point is
SOLID; on the `bspcsg` model it is EMPTY.

**Fix = route the shipping lit build through the `bspcsg` core** (`build_geometry_bspcsg`, the
incremental `bspBrushCSG` port that reproduces the editor's cleaner BSP: 485 surfs / ~99.97%
solidity vs coarse 438). `materialize._build_level_model` / `run_materialize_native` gained a
`core=` selector defaulting to `"bspcsg"`; `"coarse"` stays for the byte-identity pinning test. Both
cores emit the same UModel shape and both run `passes::bsp_build_bounds`, so assemble + N-4 bake +
zones + collision are unchanged and the pawn still walks (phys=1, verified live).

**Measured (castle):** fully-dark surfs coarse=63 → bspcsg=59 (editor=55). Rebuilt `NativeCastle.dx`,
re-shot the A/B (`_scratch/shots/occlusionfix{,-ed}/`, pairs in `_scratch/shots/occlusionfix_pairs/`).
Black-pixel fraction dropped map-wide; s34 floor and much of s76 now render lit grey matching the
editor.

**Residual (open) — CORRECTED diagnosis (2026-07-17, evidence below).** The remaining s76/s69/s07
render-black is **NOT** a bspcsg solidity / light-LOS over-occlusion problem, and NOT the byte-identity
"solidity residual". Four independent measurements on the shipped `NativeCastle.dx` vs the editor's
`Test_Castle.dx` disprove the over-occlusion hypothesis:

1. **BSP solidity MATCHES the editor.** A point-in-solid sweep (mirroring `linecheck::is_csg` + the
   terminal-cell rule) through the exact nook geometry where surfaces stay dark returns the *identical*
   solid/empty pattern in both maps (e.g. `x`-sweep at `y=-144, z∈{54,80,108}`: char-for-char equal).
   There is no wrongly-solid cell in bspcsg that the editor lacks — so nothing to "fix" in solidity.
2. **The +4 self-shadow-bias origin is NOT in solid** for essentially all dark up-facing surfaces on
   the bspcsg model (`solid_above=False`), so the coarse-core mechanism §16-era hunts assumed
   (origin lands in wrongly-solid space) is already gone with bspcsg.
3. **Only ~1 surface is a genuine native-dark-but-editor-lit lighting regression** once the dark test
   is done correctly. (Trap: an *empty* light run is encoded as `iLightMap` present but
   `iLightActors → 0`-terminator with zero set bits — NOT `iLightActors == -1`. Testing only
   `== -1` under-counts editor-dark surfaces and manufactures false regressions. Correct dark test =
   walk the light run and check for any set bit.) Correct dark counts: native **59** vs editor **55**;
   the ONE clean regression is surf#278 (a wall), a hard bake edge case, not a solidity divergence.
4. **The LARGEST native-dark surfaces are dark in the editor too.** The skybox faces (`#461–466`,
   area ~1.05M each, z≈2488–3512) and the exterior tower faces (`#369–421`, area ~16k each, at
   `±800,±800`) — the surfaces that dominate any wide view — are dark-baked in BOTH maps. NO large
   native-dark surface has a lit editor counterpart. And a raycast of s76's black pixels lands on
   surfaces that *have* baked lightmaps (`dark=False`), i.e. the black is not from a dark lightmap.

**Actual cause (strongly indicated):** the render-black is a **render/zone-portalization** difference,
not lighting. `NativeCastle` ships with incomplete zone/sky portalization (see the handoff commit
"needs zone portalization"); the editor map's proper zones/sky render the same geometry lit/backdropped
where native renders it black. Fixing the last render parity is therefore the **zones/portalization**
work item, NOT a bspcsg solidity change. (Harness for all four measurements lived in `_scratch/` during
the session: `darkcount.py`, `solidprobe.py`, the nook sweep, `s76ray.py`.)

## 19. DEFINITIVE: the residual black is NOT lighting and NOT missing geometry — it is the game's BSP RENDER-TRAVERSAL skipping present, baked-LIT surfaces (✅ 2026-07-17)

This closes the three-way contradiction (lighting-bake vs BSP-solidity vs zone-portalization) with a
**geometry-matched, value-level** method + a **camera raycast**, superseding §18's "strongly indicated".
All harness is committed: `harness/blackcause_{geo_match,raycast,normal_check,surf278}.py` (run against
`NativeCastle.dx` + the editor oracle `Test_Castle.dx`; loaders `native/umodel.parse_model_body` +
`utexture_decode.load_package`).

**Method fix that unlocked it.** Prior agents matched surfaces by ARRAY INDEX, but the two 485-surf
Models order their surfs differently, so index-matching manufactured false regressions. The correct
match is by GEOMETRY — same plane (unit-normal `cos > 0.999`, plane-dist ≤ 2u), same texture name,
nearest centroid. And the correct render-DARK test walks the light run and counts SET BITS (not
`iLightActors == -1`: an empty run is `iLightActors≥0` with a `0`/NULL terminator and zero bits — §18
trap). A surf renders black iff it is lightmapped AND its planes have **0 set bits**.

**(A) Lighting bake — REFUTED (`blackcause_geo_match.py`).** Native vs editor render-dark counts are
**54 vs 54** (identical). Of 485 native surfs, **459 match an editor twin by geometry**; among matched
pairs **409 both-lit, 48 both-dark, and exactly ONE** true native-dark-but-editor-lit regression
(surf#278, a 24u `grey_stone_tile` wall at `(144,60,88)`) plus one inverse. The big native-dark
surfaces (skybox `ColorStars_A` ~700–835u, exterior tower `grey_stone_tile`/`ClassicRoof_01` at
`±800,±800`) are dark in **both** maps. So the ~15–32 % frame-black is **not** a lightmap-content
regression — the lightmaps are, value-for-value, the editor's.

**(B) Missing geometry / BSP-solidity — REFUTED (`blackcause_raycast.py`).** Firing the EXACT game
camera rays (`rotation.euler_to_matrix_uu` basis, 75° H-FOV, the four task poses) into the NATIVE
Model and taking the nearest surf hit: at **every** pose the native geometry is **100 % LIT surfaces
in view — 0 % baked-dark, 0 % void** (s76/s34/s07 = 100 % lit; s69 = 66.7 % lit + 33.3 % *unlit*
fake-backdrop, still 0 dark/0 void). Yet the SAME poses rendered in-game are **s76 32.1 %, s34 14.4 %,
s69 18.2 %, s07 16.3 % BLACK**. So under every black pixel there IS a native surface, it IS present
(not void → BSP solidity/geometry is fine), and it IS baked lit (→ lightmap is fine). Normals are fine
too: `blackcause_normal_check.py` finds only 3 marginal flipped-normal twins (spurious cross-matches),
so it is **not** a bspcsg surf-normal inversion either.

**(C) THE MECHANISM: the game does not DRAW those present, lit surfaces** — `URender`'s BSP
front-to-back walk / occlusion skips them, showing the black backdrop. This is a **render-topology /
portalization** difference, pinned to concrete structural gaps between the two built Models
(`native/umodel` decode):

| | node.i_zone top | node_flags | leaves (main interior) |
|---|---|---|---|
| **Editor** | `(0,2)×1058` | `8×598, 0×535, 13×9, 16×7, 24×5` | zone 2 = 359 |
| **Native** | `(0,0)×450, (0,1)×279, (1,1)×384` | `0×1163, 5×8` | zone 1 = 397 |

Native leaves **450 nodes assigned to the solid/outside zone 0 on both sides** and sets **essentially
no node render-flags** (the editor's `NF_*` = 8/13/16/24 are absent), so the renderer's per-node
zone/occlusion decisions differ and it drops interior surfaces from the frame. The s69 band is the
`ClenCloudBank_A` **fake-backdrop** (surf#4, `PF_FakeBackdrop|PF_Portal`) — present in both maps but
rendered black by native for lack of a drawn sky. (The `bluewater` portal sheets #365–368 are the
extra native `iLightMap=-1` surfs.)

**Resolution of the contradiction.** "Zone visibility RULED OUT" was about the `Visibility` MASK
(`0xffff…` on all zones) — but that mask is *never computed* even on real maps (§70 §0), so it was
never the mechanism. The mechanism is the node-level **portalization** (iZone/iLeaf/node_flags/leaf
structure), which IS materially different. So of the three prior diagnoses, **zone/render-portalization
was correct**; lighting-bake and BSP-solidity are falsified with the numbers above.

**Fix ownership (out of this file's scope).** The fix is the zone/leaf/node-flags portalization port
(`zones.rs`/`passes.rs`/`build.rs`/`model_write.rs`), tracked as the portalization work item and under
active concurrent development — NOT a `light.rs` (bake) or bspcsg surf-normal change. The lone lighting
regression surf#278 is a `linecheck`/bspcsg LOS **over-occlusion** edge case (22 in-front, in-range
lights, e.g. `Light_659hfb` at 86u clear, yet every lumel's `+Normal*4` ray bakes occluded — case (b)
of §5, not backface/radius); it is one 24u tile that moves no black metric and its cause is also in
`linecheck`/bspcsg, not `light.rs`. **`light.rs` needs no change for the residual black.**

## 20. RESOLVED — the interior render-black is cleared by fixing `zones.rs` Pass D + FBspSurf.iZone (✅ 2026-07-18)

The §19 diagnosis was correct and the fix landed in `zones.rs` (full write-up +
byte/instruction evidence in `sections/70-zones-portalization.md §9`). Two bugs, both node-level
portalization:

1. **Pass D used a subtree-descent guess** ("grab any leaf under the child"), zoning ~450 interior
   wall nodes `(0,0)` solid/solid → their `ZoneMask` carried no interior bit → `URender` dropped
   them. Replaced with **PointRegion sampling of each node's own face centroid** (nudged `±0.5uu`
   off the plane), matching the editor's `AssignAllZones`. Node iZone `(0,0)×450→×2`; `(0,interior)`
   now dominant, distribution matches the editor.
2. **Native was writing `FBspSurf.iZone`; the editor leaves it (0,0)** (the game recomputes at load,
   trusting a non-zero stored value as stale). Fixed to emit `(0,0)`.

**In-game A/B (both maps rendered `--game`, black-pixel fraction):**

| pose | baseline | after fix | editor |
|---|---|---|---|
| s76 | 32.1 % | **3.8 %** | 4.0 % |
| s34 | 14.4 % | **0.0 %** | 0.0 % |
| s07 | 16.3 % | **0.0 %** | 0.0 % |
| s69 | 18.2 % | 20.7 % | 0.0 % |

The three interior poses reach editor parity. **s69 (looking down into the water pool) is NOT
cleared** — it is the pre-existing water-portal/pool-pit render gap (the fake-backdrop is a `Z=420`
ceiling plane, behind the s69 camera; not the cause), which remains the separate water/sky
portalization item. Collision unchanged (pawn walks `phys=1`). Offline suite green for the native
core (the concurrent config-session failures in `test_packages`/`test_qualify` are unrelated).

## 21. RAW-BYTE gap in the three light sections — the DOMINANT gap is the missing per-leaf permeating light lists (🔬 golden + disasm, 2026-07-18)

Sections 11–20 chased the lit-**render** to parity (crash → colour → contrast → occlusion → zones).
This section is about the **RAW on-disk bytes** of the three light sections, measured by
`harness/ground_truth_bytediff.py` (native `NativeCastle.dx` vs editor oracle `Test_Castle.dx`, no
normalization). Starting state:

| section | native | editor | note |
|---|---|---|---|
| `Lights` (e4) | 3928 entries | **11392** | the big gap (~3963 bytes) |
| `LightMap` (a8) | 480 recs | **484** | 120-byte gap |
| `LightBits` (b4) | 48015 B | **49513** | ~1498-byte gap |

Harness for the decomposition: **`harness/lights_run_diff.py`** (walks each `FLightMapIndex.iLightActors`
run and each `FLeaf.iPermeating` run; committed).

### (A) The `Lights` (e4) gap = native OMITS the whole per-LEAF permeating light region ✅

`Model.Lights` (`UModel+0xe4`) is **not** just the per-surface shadow runs. It has **two regions**,
proven by walking every index that references it:

- **Region 1 — `[0, 7455)` in the editor: per-LEAF permeating light lists**, indexed by
  **`FLeaf.iPermeating`** (`Model.Leaves`, the classic UE1 `FLeaf{iZone, iPermeating, iVolumetric,
  iVisibilityMask}` — "lights permeating this convex volume considering shadowing"). Editor: 366 of
  384 leaves carry a real NULL-terminated run here; the runs tile `[0, 7455)` **monotonically in leaf
  index order**. `iVolumetric` is `-1` for every leaf on this map (no volumetric-flagged lights).
- **Region 2 — `[7455, 11392)`: the per-surface shadow runs**, indexed by
  `FLightMapIndex.iLightActors` — this is the region native reproduces (its `LightBits` bit-planes are
  1:1 with these run entries; both maps reconcile exactly `run_len·⌈U/8⌉·V == LightBits`).

**Native emits ONLY region 2** (3928 entries) and never computes region 1. Worse, `zones.rs`
currently stubs **every** leaf's `iPermeating = 0` (all 384 point at `Lights[0]`, a *surface* shadow
run — semantically wrong garbage the game would `AddLight` onto any dynamic actor standing in a leaf).
The editor's region 1 is 7455 entries → **this omission is the entire ~7500-entry `Lights` gap.**

**The per-leaf list is a genuine volumetric flood, not derivable cheaply.** Two geometric predicates
are now REFUTED (harness `perm_region_decode.py`, decode confirmed 2026-07-18):
- "leaf's permeating set = union of the shadow-run lights of the surfaces bounding that leaf (via
  `node.iLeaf`)" — **Jaccard 0.427**, only 9/366 exact; interior leaves with *zero* bounding surfaces
  still carry runs (lit through portals).
- "light `i` permeates leaf `L` iff `dist(centroid_L, loc_i) < worldRadius_i (+ leaf radius)`" — even
  worse, **Jaccard 0.312**, 0/366 exact. A pure radius reach over-includes occluded leaves and
  under-includes leaves lit around corners.

So region 1 is a genuine **shadowed volumetric flood** (radius reach **AND** BSP line-of-sight through
portals) — UnrealEd's `shadowIlluminateBsp` per-leaf gather — and reproducing it requires porting that
gather, **including the editor's exact within-run ORDER**, which is the gather-DISCOVERY order, not
sorted: leaf0 = export refs `[2,1,3,6,7,11,12]` = participating-light indices `[44,43,42,39,19,13,12]`
(so the byte-level order is gather-order *in export-ref space*, coupling this to the export-renumber
blocker (C1)). Decode facts pinned by `perm_region_decode.py`: region 1 = `Lights[0,7455)`, region 2 =
`[7455,11392)` (clean split); 366/384 leaves carry a run (18 have `iPermeating=-1`); run lengths 2–39
(mode ~11); the ref→light-index map is 0-unmatched (the set is expressible in native's index space).
This is a sizeable **separate port** (tracked on the board), NOT a `light.rs` one-liner, and — see (C) —
cannot reach raw-byte identity on its own until export renumbering (C1) also lands. **Deferred**: a
wrong SET is worse than the honest `iPermeating=0` stub, so it stays stubbed until the gather is ported.

### (B) The `LightMap`/`LightBits` gap — FIXED the `PF_Portal` over-cull ✅

Native marked **5** surfaces unlightmapped (`iLightMap=-1`); the editor marks **1** (surf#4,
`UNLIT|FAKEBACKDROP`). The 4 extra were the map's **two-sided water-portal sheets** (PolyFlags
`0x0400010c` = `Portal|TwoSided|NotSolid|Translucent`), which the editor **does** lightmap (real lit
records, run-lengths 5/8/6/6). Native's `PF_NO_LIGHTMAP` wrongly included `PF_Portal`.

**Grounded twice:** (i) the oracle `Test_Castle.dx` lightmaps all 4 portals; (ii) UnrealEd's
allocate-meshes pass at **`Editor 0x100a6031`** gates the `push 0x28` (=40 = `sizeof FLightMapIndex`)
allocation with `test dword ptr [surf+0x1b0], 0x400081` → stores `iLightMap=-1` (`surf+0x1c8`) when
nonzero. The mask is **`0x400081 = PF_Unlit(0x400000) | PF_FakeBackdrop(0x80) | PF_Invisible(0x1)`** —
**no `PF_Portal`**. (`0x0400010c & 0x400081 = 0` → kept; surf#4 `0x00400080 & 0x400081 ≠ 0` → skipped.)
Earlier §8's pseudo-code that listed `PF_Portal` was wrong. Pinned by the Rust regression
`lightmap_skip_mask_matches_editor_disasm` (asserts the mask `== 0x400081`).

**Fix + measured effect** (`light.rs`, drop `PF_PORTAL` from `PF_NO_LIGHTMAP`):

| section | before | after | editor |
|---|---|---|---|
| `LightMap` (a8) | 480 recs / 14408 B | **484 recs / 14528 B** | 484 / **14528** (length now EQUAL) |
| `LightBits` (b4) | 48015 B | **48431 B** (gap 1498→**1082**) | 49513 |
| `Lights` (e4) | 3928 | **3955** (+4 portal shadow runs) | 11392 |

The residual `LightBits` gap (1082 B) is now (a) native's strict `light_in_front` backface cull giving
the **two-sided** portals fewer lights than the editor's two-sided treatment (the latent gap §17 flagged
in `board/inbox.md`), and (b) surf-order divergence — see (C).

### (C) Why NONE of the three sections can reach raw-byte IDENTITY from `light.rs` alone ⚠️

Two upstream blockers make positional byte-identity of these sections **impossible** to fix purely in
the bake, independent of how correct the content is:

1. **Object-ref renumbering.** `Lights` (e4) entries are compact-index refs into each file's own
   export table, numbered by a session-global counter the trunk can't reproduce (see `wrapper_diff.py`
   and `ground_truth_bytediff.py`'s own caveat). Even an identical light *set* serializes to different
   bytes until export numbering matches — a **wrapper-level** concern, not the bake.
2. **BSP surf/leaf ORDER.** `LightBits` and the region-2 runs follow the `LightMap` array order;
   region-1 follows leaf order. Native's `bspcsg` enumerates surfs/leaves in a **different order** than
   the editor historically (same 485 surfs, different indices). With the surf pool now editor-ordered,
   the *content* of each record is correct but its **on-disk emission order** is what must match — see
   (E), which pins that order. The residual per-record CONTENT gap (grid size ±1, `u/v_scale` FP
   divergence, run-length) is the remaining bspBrushCSG/FP byte-identity work item, not lighting order.

**Net honest state of raw-byte parity for the three light sections:**
- `LightMap` (a8): **length now matches (14528==14528)**; per-record content is correct; positional
  bytes differ only by surf-order (blocker 2).
- `LightBits` (b4): gap cut to 1082 B; residual = two-sided portal light count + surf-order.
- `Lights` (e4): still 3955 vs 11392 — **dominated by the un-ported per-leaf permeating region (A)**;
  even after that port, bytes stay non-identical until (1)+(2) land.

So `light.rs`'s reachable contribution is making the sections **structurally complete + content-correct**
(done for LightMap/LightBits records; region-1 leaf lists is the remaining structural piece); positional
byte-identity is gated on export-renumbering + BSP-order parity owned elsewhere.

### (D) FP-determinism assessment

The current bake is deterministic: `rayon` parallelizes per-surface but concatenates in **surf-index
order** (serial `bakes.into_iter().flatten()`), so offsets are thread-schedule-independent; all math is
plain `f32` with fixed iteration order and no RNG. **The `PF_Portal` fix adds no float paths** — it only
lets 4 more surfaces through the existing deterministic bake. **A future per-leaf permeation port MUST
preserve this:** iterate leaves in index order, iterate lights in a fixed order, accumulate with a fixed
reduction, and **replicate the editor's exact within-run gather order** — any set-based dedup or parallel
reduction that reorders would forfeit the (already order-gated) byte parity and could even vary run-to-run.
No FP-nondeterminism hazard exists in the shipped bake today.

### (E) LightMap array order = editor BSP **tree-walk** order, NOT surf order ✅ (2026-07-18, `light.rs`)

(C) point 2 above assumed `LightMap` was "emitted in native surf-iteration order" and that closing the
gap was a bspBrushCSG concern. **Decoding the editor golden `Test_Castle.dx` refuted the surf-order
premise**: with the surf pool already editor-ordered, the editor's `LightMap` array is **still not in
surf order** — its record→surf sequence is `[102, 324, 267, 191, 17, 297, 5, 179, …]`, emphatically not
`[0, 1, 2, 3, …]`. The order is a **BSP tree walk**: descend from the root — **visit the node's surf
(allocate its record the first time each lightmappable surf is seen), recurse the BACK subtree, then the
FRONT subtree, then step to the next coplanar node along the `iPlane` chain**. A surf is marked seen on
first visit regardless of lightmappability (so the one unlit surf #4 is skipped without disturbing the
sequence). This walk **reproduces the editor's 484-record `LightMap` order byte-exactly** (harness
`ground_truth_bytediff.py` + a decode walk; the mechanism is UnrealEd's shadow/mesh-allocate node
descent). `LightBits` DataOffsets and the per-surf `Lights` region-2 runs follow the `LightMap` array, so
emitting `LightMap` in walk order aligns all three positionally.

**Fix** (`light.rs`, `bake`): compute `lightmap_emit_order(model)` (the walk above) and concat records in
that order instead of surf-index order; a defensive surf-order sweep afterward catches any lightmappable
surf a disconnected BSP might miss (keeps the record count exact). Runs serially after the parallel
per-surf bake, so it adds no FP/nondeterminism. Pinned by the Rust regression
`lightmap_array_is_in_bsp_walk_order_not_surf_order` (asserts `bake`'s record→surf order equals an
independent reference walk).

**Measured effect** (clean A/B on one build, all non-light sections held constant, RAW
`ground_truth_bytediff.py` section match; harness `_scratch` `ab.py`):

| section | surf-order (before) | walk-order (after) | editor |
|---|---|---|---|
| `LightMap` (a8) | 4291/14528 = **29.5%** | 11066/14528 = **76.2%** | length-exact 14528 / 484 recs |
| `LightBits` (b4) | 26525/48434 = **53.6%** | 22048/48434 = **44.5%** | 49516 B |

The `LightMap` jump (+46.7 pp) is the real win — records now sit at the editor's positions. The
`LightBits` section % *drops*, but this is **not a real regression**: with records finally aligned
per-surf, the flat bit-blob's positional match is destroyed by a **cascade** — the first record whose
grid dims or run-length differ shifts every downstream byte. The surf-order 53.6% was **coincidental**
byte-agreement of *mis*-ordered records. The honest per-record measure (same surf on both sides) is
**74.2% aligned bits**; the residual is CONTENT, not order:
- **grid dims:** 350/484 records match `(u_size, v_size)`; native is 1 smaller on 75 (`u`) / 106 (`v`).
- **`u/v_scale`:** 0/484 byte-match — differ by ~0.25-scale amounts traceable to upstream vertex/extent
  FP (Points/Verts), the x87-vs-SSE class of divergence (spike §41), NOT the bake.
- **run-length:** 393/484 match; native 3525 total run entries vs editor 3497 (backface/two-sided-portal
  count, the latent §17 gap).
- **`Pan`:** 484/484 match. ✅

So walk order is the correct, editor-verified layout and is **required** for byte parity; the remaining
`LightMap`/`LightBits` gap is upstream grid/FP/run-length content, owned outside `light.rs`. Whole-body
RAW positional match dips slightly (~43.6%→~42%) purely because the `LightBits` cascade shifts everything
after it — an artifact of the length-difference content gap, not of the order fix.

## 22. LightMap grid-sizing rule PINNED byte-exact — `ceil(extent/scale)` + subtract-base-first extent (✅ FIXED, 2026-07-18, `light.rs`)

§21 (E) left the residual `LightMap`/`LightBits` gap as "per-record CONTENT (grid size ±1, `u/v_scale`
FP)". This section closes the **integer** part of that gap completely and the float part down to a small
upstream-geometry residual — the editor's grid-descriptor formula is now decoded byte-for-byte from the
golden `Test_Castle.dx`.

**Evidence (golden decode).** `harness/lightmap_grid_diff.py` aligns native and editor `LightMap`
records by walk order (record *k* = same lit surf on both sides, §21 (E)) and, independently, predicts
each of the editor's 484 stored records from that record's **own** surf geometry. Three findings, each
484/484 exact against the golden:

1. **Grid dim = `Clamp(ceil(extent / lumel_scale), 2, 256)`**, NOT the old
   `trunc((extent−0.25)/scale − 0.5) + 1`. Decisive teeth: an **exact multiple** of the lumel scale
   takes NO extra texel — extent 64 at scale 32 → `ceil(2.0)=2` (old form gave 2, but a non-multiple
   like extent 80 → `ceil(2.5)=3` where the old form gave 2). Extent 1024 at scale 32 → 32, not 33. The
   old truncation under-counted every non-multiple by exactly 1, which is why §21 measured native "1
   smaller on 75 (u) / 106 (v)" — **134 of 484 records**. With `ceil`: `UClamp` 484/484, `VClamp`
   484/484.

2. **Texel scale = `(extent + 0.25) / (size − 1)`**, NOT `extent / (size − 1)`. The grid spans
   `[min − 0.125, max + 0.125]` (a half-lumel pad each side, matching `Pan = min − 0.125`), so the
   `size − 1` steps cover `extent + 0.25`. This is why §21 saw `u/v_scale` **0/484** even on records
   whose dims matched — the scale formula itself was wrong, not (only) upstream FP. With the `+0.25`:
   `u_scale` 484/484 byte-exact.

3. **Extent is `(vert − Base)·Tex`, subtract-base PER-VERTEX BEFORE the dot** — NOT the algebraically
   equal `vert·Tex − Base·Tex`. On an **angled** `TextureU/V` (a rotated surface) the two orderings
   round differently in f32; the editor subtracts first. Reproduces the golden's stored `Pan`/`VScale`
   on **484/484** records vs **412/484** for the dot-then-subtract form. Axis-aligned axes collapse to
   `v.x − Base.x` under both orderings (no rounding difference), which is exactly why only the 75
   angled-**V** surfaces diverged while **U** was already clean. `Vec3::dot` accumulates `x+y+z`
   left-to-right in f32, matching the engine's `FVector operator|`.

**Native code (`light.rs`).** `axis_grid` now returns `size = (extent/scale).ceil().clamp(2.0,256.0)`
and `uscale = (extent + 0.25)/(size − 1)`; `bake_surf`'s extent loop computes `let d = v.sub(&base);
d.dot(&tu) / d.dot(&tv)`. Regression `axis_grid_matches_editor_ceil_rule` pins the ceil rule + scale +
the exact-multiple boundary against a red test.

**RAW positional result (native vs editor golden, `ground_truth_bytediff.py`), per-section over min length:**

| section | before (§21) | after (§22) | notes |
|---|---|---|---|
| `LightMap` (a8) | 11066/14528 = **76.2%** | 12638/14528 = **87.0%** | length-exact 14528 / 484 recs (unchanged) |
| `LightBits` (b4) | 22048/48434 = **44.5%** | 22355/49516 = **45.15%** | native length 48434 B → 49701 B (was −1082 vs editor, now +185) |

`UClamp`/`VClamp` 484/484, `u_scale` 484/484, `Pan.x` 484/484.

**Residual (quantified, "and similar").** `Pan.y`/`VScale` reach **427/484** exact, NOT 484. This is
**not** a lightmap-code defect: native's descriptor reproduces its stored `Pan` from its **own** geometry
484/484 (self-consistent — same as the editor), and all **57** remaining records are exactly those whose
native **base-point or TextureV vector differs from the editor** by f32 (the Points/Vectors sections are
still not byte-exact — owned outside `light.rs`, spike §41 x87-vs-SSE class). As Points/Vectors reach
parity these follow for free; no `light.rs` change can move them.

**Why `LightBits` barely rose despite exact grid dims.** With `⌈UClamp/8⌉·VClamp` now exact per record,
the residual `LightBits` gap is no longer grid dims — it is the shadow **content**: which lights reach
each surf (the `Lights` region native 3960 vs editor 11392 reflects the per-leaf permeating-light region
native still omits, §21 (A)) and the per-lumel LOS/backface bits (§17, ~74% aligned). Those are separate,
larger levers (portalization + per-leaf light lists), not the grid descriptor this section closed.
