# PF_FakeBackdrop rendering — how `URender` actually does it

RE spike for `dev/docs/board/to-spike/add-pf-fakebackdrop-support-to-level-photo/` (owner ruling
2026-09-12: RE the real engine instead of shipping a draft approximation). All five questions
answered from **static disassembly alone** — no live probe was needed, every call target resolved
statically, including the one indirect call (a `URender` vtable slot). Every fact below is pinned
byte-exact against the committed `uned/UED22/*.dll`/`.exe` in `uedcli/tests/test_engine_facts.py`
(`test_pf_fakebackdrop_*`, 36 assertions total split across three tests).

## Setup

`render.dll` is built from `UnRender.cpp` (assert-filename string at `render.dll +0x36ba0`
confirms the source path: `C:\GameDev\UnrealTournament\Render\Src\UnRender.cpp`). The per-surface
PolyFlags dispatch is **not** in `URender::DrawWorld` — `DrawWorld` (`+0x17680`) only calls
`OccludeFrame` → `OccludeBsp` (`+0x18e10`) and then `DrawFrame` (`+0x15090`). All the flag-testing
lives in **`URender::OccludeBsp`**.

Struct offsets used below, each independently confirmed by reading the actual field-access bytes
(not assumed from source-code guesses): `FSceneNode` +0x14 `iSurf`, +0x18 `iZone`, +0x1c
`Recursion`. `AActor` +0x88 `Region` (`{Zone, iLeaf, ZoneNumber@+0x90}`), +0xd0 `Location`, +0xdc
`Rotation`. `APlayerPawn` +0x47c `ShowFlags` (matches `Engine.u`'s own `PlayerPawn` var
declaration order, read straight out of the package). `AZoneInfo` +0x278 `SkyZone` — derived from
two independent facts agreeing exactly: `Engine.u`'s `ZoneInfo` class declares `SkyZone` as its
28th own var (0x6c bytes into `ZoneInfo`'s own var block), and `Engine.dll`'s `UClass` constructor
call for `AActor` passes `InSize = 0x20c`; `0x20c + 0x6c == 0x278`.

## 1. The core projection: renders a whole second scene, not a texture swap

The flag test itself is easy to miss with a naive byte scan: the compiler emits
`PolyFlags & PF_FakeBackdrop` (`0x80`) as a **sign test of AL**, not a `test`/`and` against the
literal `0x80`:

```
render.dll +0x19c3d   mov  eax, [ebp-0x8c0]   ; PolyFlags
render.dll +0x19c43   test al, al             ; == PolyFlags & 0x80
render.dll +0x19c45   jns  +0x19c7a           ; bit clear -> falls to the PF_Mirrored test
```

Taking the branch (bit set): the code resolves the surf's zone actor
(`ULevel::GetZoneActor(iZone)`), null-checks its `SkyZone` field (+0x278), and — on a non-NULL
`SkyZoneInfo` — builds a child scene:

```
render.dll +0x19d67   SkyCoords = Frame->Coords                          (FCoords copy)
render.dll +0x19d7e   SkyCoords.Origin -= Frame->Coords.Origin           (-> zero)
render.dll +0x19d8a   SkyCoords /= SkyZone->Rotation                     (compose sky-zone rotation)
render.dll +0x19d9d   SkyCoords.Origin += SkyZone->Location              (place camera AT SkyZoneInfo)
render.dll +0x19e55   call [edx+0x68]                                   (URender::CreateChildFrame)
render.dll +0x19e60   jmp  +0x1a7eb                                     (skip this surf's own draw)
```

So the camera for the child scene sits **exactly at the `SkyZoneInfo` actor's location**, with the
**viewer's rotation composed with the sky zone's own rotation** — camera *position* inside the sky
zone never changes with the main camera (no parallax at all: `Origin -= Frame->Coords.Origin` zeros
out the translation before the sky zone's own location is added back), while camera *rotation*
does track the main view. `[edx+0x68]` is `URender`'s vtable slot 0x68, confirmed (without needing
an export/symbol lookup) by disassembling the callee: its entry-point bytes are the same
push-ebp/SEH-frame prologue as `CreateChildFrame`'s own exported symbol.

**The fake-backdrop face itself is never drawn.** The branch jumps to the same "skip this surf,
keep walking the BSP" target that `PF_Invisible` uses. `CreateChildFrame` allocates a scene node,
copies the sky `FCoords`, sets its `iZone` to the sky zone's own `Region.ZoneNumber`, and links it
under the parent frame's `Child` list; `OccludeFrame`/`DrawFrame` then walk `Child`/`Sibling`
recursively, drawing children **before** the parent's own surfaces — the sky paints in behind
everything else. `CreateChildFrame` also **de-duplicates**: its first act is a reuse loop over the
parent's existing children matching `{Level, iSurf, Parent, NearClip, iZone}` — on a match it just
merges span buffers via `FSpanBuffer::MergeWith` instead of creating a second child, so multiple
`PF_FakeBackdrop` surfaces resolving to the same sky zone under one parent share **one** sky render
whose visible region is the union of their screen spans.

## 2. `PF_Mirrored` + `PF_FakeBackdrop`: mutually exclusive, backdrop wins

One `if / else if / else if` chain, not independent tests:

| order | flag tested | on no-match, falls to |
|---|---|---|
| 1 | `PF_FakeBackdrop` (0x80) | the `PF_Mirrored` test |
| 2 | `PF_Mirrored` (0x8000000) | the `PF_Portal` test |
| 3 | `PF_Portal` (0x4000000) | the normal opaque-draw path |

A surface with both `PF_FakeBackdrop` and `PF_Mirrored` set takes the backdrop branch — no
reflection, and (since backdrop skips the draw entirely) its own texture never shows either. The
one exception: if the backdrop branch's own gate fails (its zone's `SkyZone` is NULL, or the
recursion/`ShowFlags` gates below reject it), execution falls through to the `PF_Mirrored` test, so
in a zone with no sky room a `PF_FakeBackdrop|PF_Mirrored` surface renders as a plain mirror.

Two gates guard both the backdrop and mirror branches identically:

- **`Frame->Recursion < 3`** (+0x1c) — see §5.
- **`ShowFlags & 0x800`** (`APlayerPawn`/editor-viewport +0x47c). This bit is **not** `SHOW_Backdrop`
  (that's `0x4`, confirmed from the editor's own "Show Backdrop" toolbar toggle, `ShowFlags ^= 4`)
  — it's the "Realtime Preview" toggle (`ShowFlags ^= 0x800`, confirmed the same way). In the
  shipped game the default viewport `ShowFlags` is `0x480c`, which already contains `0x800`, so
  **in-game the sky always renders**; only the *editor* needs the extra toggle on to preview it.

## 3. Missing `SkyZoneInfo`: explicit null check, benign fall-through — not a crash

```
render.dll +0x19c5f   cmp dword [eax+0x278], 0    ; ZoneActor->SkyZone
render.dll +0x19c66   jne +0x19d08                ; non-NULL -> do the sky
                                                    ; NULL -> falls to +0x19c7a (the mirror test)
```

With `SkyZone == NULL`, the surface is handled by the rest of the same chain and — absent
`PF_Mirrored`/`PF_Portal` — **draws as an ordinary opaque textured surface**. This is exactly
`uedcli-native`'s current (draft) behavior; the RE work here establishes that it is only correct
for this specific fallback case, not the engine's general behavior.

One editor-only wrinkle (an OldUnreal/UED22 addition, not stock UT): under `GIsEditor`, the branch
substitutes a global `pSkyZoneInfo` (read out of the object table) instead of resolving one per
zone, and asserts it non-null (`UnRender.cpp:1553`, the literal assert-expression string
`pSkyZoneInfo` is embedded at `render.dll +0x36d68`). The editor's own toolbar guards the relevant
toggles with a message scanning `Model->Surfs` for `PolyFlags & 0x80`
(`unrealed.exe +0x33f89`, message string `"Can't enable SHOW_Backdrop, PF_Fakebackdrop is set in a
Skyzone!"`) — the editor UI's own error text calls the bit `PF_Fakebackdrop`, matching this
codebase's naming.

## 4. `Unlit`: irrelevant — the tutorial-corpus rule is workflow folklore, not an engine dependency

The FakeBackdrop branch never touches lighting and never forces `PF_Unlit` (0x400000). It draws no
surface at all (§1), so there's no lighting decision to make for the surf itself; the sky zone's
own geometry, once rendered by the child frame, goes through the ordinary lit path like any other
world surface. Two independent confirmations that `PF_Unlit` and `PF_FakeBackdrop` are unrelated in
the renderer:

- `render.dll +0x7c3b`: the light-setup code's only PolyFlags test is `PF_Unlit`; `PF_FakeBackdrop`
  never appears there.
- `Editor.dll +0xa4ae7`: the lighting-build's lightmap allocator skips
  `PolyFlags & (PF_Invisible|PF_FakeBackdrop|PF_Unlit)` = `0x400081` — a `PF_FakeBackdrop` surf
  simply never gets a lightmap (`iLightMap == -1`) regardless of `PF_Unlit`, and
  `render.dll +0x15690`'s `DrawFrame` skips the light manager whenever `iLightMap == -1`.

So a fake-backdrop surface "looking unlit" in the NULL-`SkyZone` fallback case (§3) is a side effect
of it never having a lightmap in the first place — not something the level author's `Unlit` flag
causes. The "needs a companion Unlit flag" rule in the tutorial corpus
(`dev/docs/unrealed/leveldesign/kb/textures.md`) is level-author folklore, not a real code
dependency; it likely persists because a level author expects a sky face to look flat/lit-from-the-
sky rather than lit like an interior wall, and setting `Unlit` on it is (redundant but) harmless.

## 5. Recursion: a shared, per-frame depth counter, cap 3

The sky sub-render does re-enter the same dispatch — `OccludeFrame` walks `Frame->Child`/`Sibling`
and calls `OccludeBsp` again for each, so a `PF_FakeBackdrop` surface inside the sky zone itself
spawns another sky frame. The guard is **`FSceneNode::Recursion`** (+0x1c), threaded per-frame, not
a global counter:

- `CreateMasterFrame` (+0x14e13): `Recursion = 0` for the root frame.
- `CreateChildFrame` (+0x14b64): `Child->Recursion = Parent->Recursion + 1`.
- All three arms (backdrop +0x19d24, mirror +0x19c98, portal +0x1a083) use the identical
  `cmp [Frame+0x1c], 3` / `jge`-style guard.

**`PF_Mirrored` has no separate one-bounce cap of its own** — this repo's `render.rs` comment
describing mirrors as "capped at one reflection deep" is consistent in outcome (since a mirror
inside a mirror inside a mirror does eventually stop) but the real mechanism is this single shared
depth budget across backdrop/mirror/portal kinds together, not a mirror-specific counter: a
sky-then-mirror-then-sky nesting is allowed up to depth 3 the same as three mirrors in a row would
be. The only other bound is `CreateChildFrame`'s own reuse/merge loop (§1), which collapses
duplicate children of the same parent rather than creating a fresh one each time.

## What this means for `uedcli-native/src/render.rs`

Today's behavior (draw a `PF_FakeBackdrop` face's assigned texture like any opaque face) is the
real engine's behavior **only** for a surface whose zone has no `SkyZoneInfo` — for the general
case, the real fix is: drop the face's own draw, resolve its zone's `SkyZoneInfo`, and render a
child scene from that actor's location (viewer rotation, sky-zone position — no parallax)
composited into the face's screen footprint, sharing one child render per zone per frame and
capped by the same recursion depth `PF_Mirrored` already needs. `PF_Unlit` requires no special
handling. This becomes the implementation plan once written; see the board item.

## Harness

`harness/verify_fakebackdrop_facts.py` re-asserts all 36 facts (a superset of the 12 pinned as
pytest regressions in `uedcli/tests/test_engine_facts.py`) via `pefile`+`capstone` against the live
binaries — run `python3 dev/docs/spikes/2026-09-12-pf-fakebackdrop-re/harness/verify_fakebackdrop_facts.py`
from the repo root. `harness/*.asm` are the full annotated disassembly dumps of `OccludeBsp`,
`DrawFrame`, `OccludeFrame`, and `CreateChildFrame` this spike was read from. `harness/disx.py` is a
disassembler with call-target/IAT/export resolution and PolyFlags-immediate annotation (deliberately
not named `dis.py` — that shadows the stdlib `dis` module and breaks `capstone`'s own imports).
`harness/classsize.py` recovers `AActor`'s size from its `UClass` constructor call site (used to
derive the `SkyZone` field offset in the Setup section above). `harness/scanflags.py` is a linear
immediate-byte scanner kept for provenance; it mis-syncs across variable-length x86 instructions and
missed the actual `PF_FakeBackdrop` test (the sign-test encoding in §1) — the byte-pattern-plus-
backward-resync method `classsize.py` uses is the reliable one; the AL-sign-test surprise in §1 is
exactly the kind of miss a naive linear scan produces, which is why the pinned regression tests read
exact bytes at exact RVAs rather than re-deriving them by pattern search each run.
