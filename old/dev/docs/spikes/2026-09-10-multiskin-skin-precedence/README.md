# `Skin` vs `MultiSkins[i]` vs the mesh's own `Textures[i]` — which one paints a mesh material slot

**Question.** A mesh actor can name a skin for material slot *i* three ways: `Actor.MultiSkins[i]`
(a per-slot override array), `Actor.Skin` (one scalar override for the whole mesh), and the mesh's
own `UMesh::Textures[i]`. Which wins when more than one is set? `uedcli`'s native mesh preview
(`meshrender.resolve_skins`) has to reproduce the engine's answer; nothing had established it.

**Answer (✅ disassembly-exact + 🔬 live-probed, UED22 2026-09-10).** One function decides it for
every mesh class, and the order it applies depends on whether the slot index is zero:

```c
UTexture* UMesh::GetTexture(INT Count, AActor* Owner)   // Engine.dll RVA 0x1129a0
{
    if (Owner && Owner->MultiSkins[Count]) return Owner->MultiSkins[Count];
    if (Count && Textures[Count])          return Textures[Count];
    if (Owner && Owner->Skin)              return Owner->Skin;
    return Textures[Count];
}
```

- **slot 0:** `MultiSkins[0]` → `Skin` → `Textures[0]`
- **slot i ≠ 0:** `MultiSkins[i]` → `Textures[i]` → `Skin` (`Skin` only reaches a non-zero slot
  when the mesh itself has no texture there)

So `MultiSkins[i]` beats `Skin` at every slot, and `Skin` is a *slot-0-first* fallback, not a
whole-mesh override.

Two facts that fall out and matter to a re-implementation:

- **`Count` is the mesh's TEXTURE index, not the material ordinal.** `URender::DrawLodMesh`
  (`render.dll` RVA 0xd050) loops `i` over `Mesh->Textures.Num()` calling `GetTexture(i, Owner)`,
  caches the results, and a triangle then picks `cache[Materials[tri.MaterialIndex].TextureIndex]`.
  `MultiSkins` is indexed by that same texture index.
- **The `MultiSkins` read in `GetTexture` is UNBOUNDED.** `AActor::GetSkin(int)` (RVA 0x12d270) is a
  bounds-checked accessor (`Count < 8`, else NULL), but `UMesh::GetTexture` does not call it — it
  reads `[Owner + Count*4 + 0x164]` inline with no check, while `DrawLodMesh` allows up to 16
  texture slots (it `appFailAssert`s above 16). A mesh with 9+ texture slots therefore reads past
  `MultiSkins[7]` into the actor's sound fields. Not a uedcli concern (nothing in the DX corpus hits
  it) but do not "helpfully" clamp differently: slots 0–7 are what a faithful port needs.

## Method

### 1. Static — the whole decision is one small function

`harness/pedis.py` (pefile + capstone) and `harness/vtslot.py`, run on the committed
`uned/UED22/*.dll` (ImageBase `0x10000000`).

`?GetSkin@AActor@@UAEPAVUTexture@@H@Z` @ RVA `0x12d270`:

```
55                   push ebp
8bec                 mov ebp, esp
8b4508               mov eax, [ebp+8]                 ; Count
83f808               cmp eax, 8
730b                 jae  out_of_range
8b848164010000       mov eax, [ecx + eax*4 + 0x164]   ; this->MultiSkins[Count]
5d c20400            pop ebp / ret 4
out_of_range: 33c0   xor eax, eax
5d c20400            pop ebp / ret 4
```

It is a dumb accessor — no `Skin`, no fallback. It is also `virtual` (slot 35, byte disp `0x8c`, in
all 49 `AActor`-subclass vtables in `Engine.dll`) and has **no call site anywhere in the DLL set**:
`harness/findvcalls.py` plus a scan for direct `E8` calls finds none, in `Engine`/`Editor`/`Render`/
`Core`/the render drivers. The precedence is therefore in the *caller* of the skin decision, which
is `UMesh::GetTexture`.

`?GetTexture@UMesh@@UAEPAVUTexture@@HPAVAActor@@@Z` @ RVA `0x1129a0` (`this`=ecx=`UMesh*`,
esi=`Count`, edx=`Owner`; `[UMesh+0xd8]` = `Textures.Data`, `[UMesh+0xdc]` = `Textures.ArrayNum`):

```
8b550c   mov edx,[ebp+0xc]              ; Owner
8b7508   mov esi,[ebp+8]                ; Count
85d2 740b                               ; Owner == NULL -> skip
8b84b264010000  mov eax,[edx+esi*4+0x164]   ; Owner->MultiSkins[Count]   (INLINED, unbounded)
85c0 7533                               ; non-NULL -> return it
85f6 7415                               ; Count == 0 -> skip the Textures probe
8b81d8000000 / c1e602 / 8b0406          ; eax = Textures[Count]
85c0 7408                               ; NULL -> fall through to Skin
5e 5d c20800                            ; return Textures[Count]
c1e602                                  ; (Count == 0 path)
85d2 740a                               ; Owner == NULL -> skip
8b8230010000    mov eax,[edx+0x130]     ; Owner->Skin
85c0 7509                               ; non-NULL -> return it
8b81d8000000 / 8b0406                   ; return Textures[Count]
```

It is **not overridden**: slot 29 (byte disp `0x74`) of `??_7UMesh@@6B@` (`0x1fd0d4`),
`??_7ULodMesh@@6B@` (`0x1fd154`) and `??_7USkeletalMesh@@6B@` (`0x1fd1d8`) all hold `0x101129a0`.
Every mesh kind in the engine resolves skins here. `Editor.dll` imports the same symbol for its own
mesh drawing, and `render.dll` reaches it through that vtable slot.

**Proving `[Actor+0x130]` is `Skin` and not a neighbouring texture field.** Three independent
anchors plus the class's own source:

| Offset | Field | Evidence |
|--------|-------|----------|
| `0x124` | `DrawType` | `URender::DrawActorSprite` (`render.dll` 0x1f0a0) tests it as a byte against `1` and `7` — `DT_Sprite` / `DT_SpriteAnimOnce` in `Actor.uc`'s own `EDrawType` |
| `0x12c` | `Texture` | the sprite bitmap that same routine draws |
| `0x130` | **`Skin`** | the field between them |
| `0x134` | `Mesh` | `URender::DrawLodMesh` does `mov esi,[esi+0x134]` to turn the Actor into the `UMesh` it then calls `GetTexture` on |
| `0x13c`, `0x14c` | `DrawScale`, `ScaleGlow` | floats read by `DrawActorSprite` |
| `0x164` | `MultiSkins[8]` | `AActor::GetSkin`'s base |

`harness/dump_script.py` pulls `Engine.Actor`'s stored `ScriptText` out of `uned/UED22/Engine.u`;
its Display block declares, in order, `DrawType` (byte), `Style` (byte), `Sprite`, `Texture`,
`Skin`, `Mesh`, `Brush`, `DrawScale`, `PrePivot`, `ScaleGlow`, `VisibilityRadius`,
`VisibilityHeight`, `AmbientGlow`, `Fatness`, `SpriteProjForward`, 18 bools (one packed DWORD),
`MultiSkins[8]`. Laid out with C alignment from `DrawType` at `0x124`, that puts `MultiSkins` at
exactly `0x164` — the offset `GetSkin` reads. The chain closes on itself, so `Sprite`/`Texture`/
`Skin`/`Mesh` are `0x128`/`0x12c`/`0x130`/`0x134` and `[Actor+0x130]` is `Skin`.

### 2. Live — the editor actually paints it that way

`harness/live_probe.py` + `harness/run_all_configs.sh`, one FRESH ephemeral `docker compose run`
editor per config (`harness/respawn.sh`; never the persistent `dx-lum-uned`). Per config: `MAP NEW`
→ `OBJ LOAD` the mesh packages → `MAP IMPORTADD` **the same 48-actor grid of mesh actors**, differing
only in their `Skin` / `MultiSkins(N)` lines → `CAMERA OPEN … REN=6` (PlainTex fullbright, capture
once at the fixed default pose) → capture that window. Identical geometry across configs means any
pixel difference is the skin decision and nothing else. Probe skins are unmistakable:
`Engine.DefaultTexture` (mean RGB ~131,140,122, BRIGHT) vs `Engine.Border` (~19,17,11, DARK).

Slot 0, on `DeusExDeco.CrateUnbreakableLarge` (sha256 of the captures, `evidence-sha256.txt`):

| Config | `Skin` | `MultiSkins(0)` | rendered | capture |
|-------------------------|--------|-----------------|----------|---------|
| A | BRIGHT | DARK | **DARK** | `e21e6230…` |
| E | DARK | — | DARK | `e21e6230…` (byte-identical to A) |
| B | DARK | BRIGHT | **BRIGHT** | `a7cbfc60…` |
| C | BRIGHT | — | BRIGHT | `a7cbfc60…` (byte-identical to B) |
| D | — | BRIGHT | BRIGHT | `a7cbfc60…` (byte-identical to B) |
| F | — | — | the mesh's own `Textures(0)` | `71a3ebaf…` |

A renders exactly like "DARK alone" and B exactly like "BRIGHT alone" — `MultiSkins(0)` wins over
`Skin`, and with neither set the mesh's own texture shows.

Slot 1, on `DeusExDeco.Earth` (480 faces on texture slot 0, 480 on slot 1, both plain-flagged — the
one substrate mesh that makes a non-zero slot visible):

| Config | property | result |
|--------|----------|--------|
| L | — | the two Earth textures (`evidence/L_earth_neither.png`) |
| M | `Skin=BRIGHT` | **unchanged** apart from the sliver of slot-0 faces (`evidence/M_earth_skin-bright.png`) |
| N | `MultiSkins(1)=BRIGHT` | the visible sphere goes bright (`evidence/N_earth_multi1-bright.png`) |

N proves slot 1 is both visible and overridable; M proves `Skin` does **not** reach it. That is the
`if (Count && Textures[Count])` branch, live.

(Configs G/H/J/K in the harness ran the same test on `DeusExDeco.Faucet` first and were
inconclusive — every visible face there is on texture slot 0, so `MultiSkins(1)` changed nothing.
`harness/find_multitex_mesh.py` is what found a mesh where slot 1 is actually on screen.)

## Reproducing

```
bash harness/respawn.sh uned-skinprobe                     # fresh isolated editor (+ content mounts)
bash harness/run_all_configs.sh out/ A_skin-bright_multi-dark B_skin-dark_multi-bright …
python3 harness/pedis.py dis ../../../../uned/UED22/Engine.dll 0x1129a0 40
```

Traps worth knowing, all cost real time here:

- The baked ini's relative `Paths=` entries do not resolve in this container — every content package
  needs an explicit `OBJ LOAD FILE=Z:\...`. A ref the editor cannot bind is **silently dropped** on
  import, so always `MAP EXPORT` and check the property came back.
- `DeusExDeco` needs only Core/Engine/Effects/DeusExItems. `DeusEx.u` has no native DLL in this
  substrate and cannot load; a `Class=Decoration` actor crashes the editor outright, so the probe
  actors are `Class=Light` with `DrawType=DT_Mesh` + `bUnlit=True`.
- A `CAMERA OPEN` window opens at (4,42) **under** the main editor frame, and X11 here has no
  backing store, so `import -window` returns the editor's toolbar pixels. Raising it does not help;
  parking every *other* window off-screen does (`harness/park_others.sh`) — and then you must wait
  ~20 s for the now-exposed camera window to repaint itself before capturing.

## Pinned

`uedcli/tests/test_engine_facts.py::test_umesh_gettexture_skin_precedence` (and
`…::test_aactor_getskin_is_a_bounds_checked_multiskins_accessor`) assert the two function bodies
byte-for-byte in the committed `Engine.dll`, and that all three mesh vtables still point slot 29 at
`UMesh::GetTexture`. A substrate swap that changes the precedence trips them.

## Files

- `harness/pedis.py` — export list / disassembly / xref search over a PE
- `harness/vtslot.py`, `harness/findvcalls.py`, `harness/impxrefs.py` — vtable slot of a virtual,
  `call [reg+disp]` sites, call sites of an imported symbol
- `harness/ctx.py` — linear disassembly of a byte range
- `harness/dump_script.py` — a class's stored `ScriptText` out of a `.u` (this is what the offset
  table above is built on); `harness/actor_layout.py` — the same from the `.u` `Children` chain,
  kept as a NEGATIVE result: that chain is not the C++ declaration order and does not reproduce the
  DLL's offsets
- `harness/list_exports.py`, `harness/tex_means.py`, `harness/scan_meshes.sh`,
  `harness/find_multitex_mesh.py` — picking probe assets
- `harness/respawn.sh`, `harness/wait_ready.sh`, `harness/logtail.sh`, `harness/probe_step.py`,
  `harness/import_t3d.py`, `harness/park_others.sh`, `harness/live_probe.py`,
  `harness/run_all_configs.sh` — the live probe
- `evidence/`, `evidence-sha256.txt` — the captures the tables above cite
