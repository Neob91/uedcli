# Mover `SavedPos`/`SavedRot` are engine-stamped sentinels, never authored content

**Date:** 2026-07-25
**Question:** `level materialize`'s H3 post-verify aborted on every map containing a mover. The
rebuilt map's re-export carries two properties the authored T3D trunk never emitted —
`SavedPos=(X=-12345.000000,Y=-12345.000000,Z=-12345.000000)` and
`SavedRot=(Pitch=123,Yaw=456,Roll=789)` — so the two sides never compare equal and the build
refuses to write. Are these *authored content* (which would make dropping them a data-loss bug), or
*engine/editor-injected runtime state* (which would make dropping them the correct fix)?
**Answer:** purely engine-injected. `AMover::PostLoad()` overwrites both with a fixed sentinel on
**every load of a Mover object**, unconditionally, before anything can read what the map file
stored. No authored value can ever survive a round trip, so there is nothing to lose.
**Confidence:** ✅ — disassembled out of two independent shipped engine binaries, corroborated by
the whole committed export corpus and by every retail map file that contains a mover, and confirmed
end-to-end by a live `level materialize`.

**Harness** (in this directory):
- `disasm_postload.py` — locates the exported `?PostLoad@AMover@@UAEXXZ` **by name** in any UE1
  `Engine.dll` and disassembles it, annotating the sentinel stores (`pefile` + `capstone`).
- `scan_corpus.py` — sweeps a tree of editor-exported `*.t3d` for the `Saved*` fields (counts,
  per-class breakdown, **distinct values**), and counts the raw sentinel byte patterns in a
  directory of binary `.dx`/`.unr` maps. No uedctl imports; runs on a bare Python 3.

---

## 1. What the properties are

`Engine.Mover` declares three "saved" properties, all inherited by `DeusEx.DeusExMover`,
`DeusEx.BreakableGlass`, `DeusEx.BreakableWall`, … (`uprops.resolve_class_properties`):

| Property       | Kind                          | Declared on the mover chain by |
|----------------|-------------------------------|---|
| `SavedPos`     | `StructProperty` (`FVector`)  | `Engine.Mover` |
| `SavedRot`     | `StructProperty` (`FRotator`) | `Engine.Mover` |
| `SavedTrigger` | `ObjectProperty` (`Actor`)    | `Engine.Mover` |

(Two *unrelated* classes also declare their own property of the same name — that matters for the
fix, and is worked through in §6.3.)

They are engine **runtime** state: the pose a mover is restored to. **None of them is a class
default** — `uprops.resolve_class_defaults` returns 50 defaults for `Engine.Mover`, 75 for
`DeusEx.DeusExMover`, 78 for `DeusEx.BreakableGlass`, and not one of them mentions `Saved*` or the
sentinel values. Independently: the byte patterns `float32(-12345.0)` (`00 E4 40 C6`) and the
`int32` triple `(123, 456, 789)` appear **nowhere** in any shipped `.u` package, in either the
game's v68 `System/*.u` or UED22's v69 set. So an omitted `SavedPos`/`SavedRot` resolves to the
**type zero** — which is why the typed compare sees "trunk says `(0,0,0)` / built map says
`(-12345,-12345,-12345)`" and reports a mismatch.

## 2. The mechanism: `AMover::PostLoad()` (the decisive evidence)

`PostLoad` is UE1's "this object has just been loaded" hook. It is an exported virtual, so it is
located by **name**, not by a guessed address.

**UED22 `Engine.dll`** (`Tools/uedctl/uned/UED22/Engine.dll`), `?PostLoad@AMover@@UAEXXZ` @ RVA
`0x171140`:

```
0x171140  push   ebp                              ; prologue
...
0x171175  call   0x12d7b0                         ; Super::PostLoad()
0x17117a  mov    dword ptr [ebp - 0x34], 0xc640e400   ; FVector temp = -12345.0f
0x171181  mov    dword ptr [ebp - 0x30], 0xc640e400   ;                -12345.0f
0x171188  mov    dword ptr [ebp - 0x2c], 0xc640e400   ;                -12345.0f
0x17118f  mov    dword ptr [esi + 0x3a0], 0xc640e400  ; this->SavedPos.X = -12345.0f
0x171199  mov    dword ptr [esi + 0x3a4], 0xc640e400  ; this->SavedPos.Y = -12345.0f
0x1711a3  mov    dword ptr [esi + 0x3a8], 0xc640e400  ; this->SavedPos.Z = -12345.0f
0x1711ad  mov    dword ptr [ebp - 0x28], 0x7b         ; FRotator temp .Pitch = 123
0x1711b4  mov    dword ptr [ebp - 0x24], 0x1c8        ;               .Yaw   = 456
0x1711bb  mov    eax, 0x315                           ;               .Roll  = 789
0x1711c0  mov    dword ptr [ebp - 0x20], eax
0x1711c3  movq   xmm0, qword ptr [ebp - 0x28]
0x1711c8  movq   qword ptr [esi + 0x3c4], xmm0        ; this->SavedRot.{Pitch,Yaw}
0x1711d0  mov    dword ptr [esi + 0x3cc], eax         ; this->SavedRot.Roll
0x1711d6  mov    eax, dword ptr [esi + 0x138]         ; ...then: Brush->Polys
0x1711e8  ...    mov [eax+ecx+0x1c4], edx / inc edx   ; for(i..) Polys(i).iLink = i
0x171225  ret
```

Reconstructed source (the standard UE1 shape):

```cpp
void AMover::PostLoad()
{
    Super::PostLoad();
    SavedPos = FVector(-12345, -12345, -12345);
    SavedRot = FRotator(123, 456, 789);
    if (Brush && Brush->Polys)
        for (INT i = 0; i < Brush->Polys->Element.Num(); i++)
            Brush->Polys->Element(i).iLink = i;
}
```

Three things follow, and each of them matters:

1. **There is no guard.** No `if (GIsEditor)`, no test of the stored value, no branch at all — the
   stores sit unconditionally between `Super::PostLoad()` and the poly loop. Whatever a `.dx` or a
   T3D file supplies for these two properties is destroyed the instant the object loads.
2. **`SavedTrigger` is NOT touched** by `PostLoad`.
3. The same function also renumbers the mover brush's polygon `iLink` to `0..N-1` — which gives an
   independent corpus fingerprint for "this mover went through `PostLoad`" (see §4).

**Nothing anywhere ever READS the constant.** A "not saved yet" marker invites the worry that some
code branches on `SavedPos == sentinel`, in which case writing `(0,0,0)` instead would be
*observable*. It does not. Searching the raw byte patterns across every shipped binary and package:

| Binary / package                | `float32(-12345.0)` | `int32 (123,456,789)` |
|---------------------------------|--------------------:|----------------------:|
| UED22 `Engine.dll`              | 6 — **all six inside `AMover::PostLoad`** | 0 |
| UED22 `Editor.dll`, `core.dll`  | 0                   | 0 |
| DX `Engine.dll`                 | 3 — all inside `AMover::PostLoad` | 0 |
| DX `Editor.dll`                 | 0                   | 0 |
| every `.u` package (both sets)  | 0                   | 0 |

So the constant exists at exactly one site in the whole system: the write. No editor code, no engine
code outside `PostLoad`, and no UnrealScript bytecode ever compares against it. Whatever the value
was intended for, nothing in the shipped product consumes it — which is what makes omitting it from
the trunk unobservable rather than merely probably-harmless.

**The DX-shipped `Engine.dll`** (`DX/System/Engine.dll`) does exactly the same. Its exports are
`jmp` thunks, so `?PostLoad@AMover@@UAEXXZ` @ RVA `0x1816` chases to `0xaf7e0`; the field offsets
differ (`this+0x4ac` / `this+0x4d0` — a different `AActor` layout) but the two stores and their
constants are identical. So the sentinel is **not a UED22 artifact**: the retail game engine
stamps it too, which is why every shipped map carries it.

## 3. Corpus evidence — 487 occurrences each, ONE distinct value

`scan_corpus.py --t3d <repo>` over the mod repo's `*.t3d` files. The numbers below are the
**git-tracked** ones — 84 committed `.t3d`, 7 of which hold movers that have been through a package
load — because those are what a later reader can reproduce. (Running the same script over an
unwiped working tree reports 651 of each instead of 487: the extra 164 come from `_scratch/`, which
`CLAUDE.md` defines as throwaway and wiped, so they are not quoted as the finding.)

| Field          | Occurrences | Distinct | The value(s) seen |
|----------------|------------:|---------:|---|
| `SavedPos`     | 487         | **1**    | `(X=-12345.000000,Y=-12345.000000,Z=-12345.000000)` — and nothing else, ever |
| `SavedRot`     | 487         | **1**    | `(Pitch=123,Yaw=456,Roll=789)` — and nothing else, ever |
| `SavedTrigger` | 0           | 0        | never appears at all |
| `BasePos`      | 1649        | **224**  | the CONTROL: a genuinely per-actor derived field, so it varies |

All four are declared on `Engine.Mover`, and the two sentinels are the only ones that never vary.
`SavedPos` and `SavedRot` have byte-identical breakdowns — `BreakableGlass` 268, `DeusExMover` 159,
`Mover` 60 — i.e. they occur **only** on Mover-derived classes, and always as a matched pair. They do
NOT occur on every such actor, though: §4 shows 244 mover-derived actors that carry `BasePos` and no
`Saved*` at all. That is the tell, and it is what §4 explains.

`BasePos` is the control: it is *derived per actor* from that mover's own `Location`, so it takes
224 different values. `SavedPos`/`SavedRot` take exactly **one** each, across four classes and 198
files. A field that were authored content would vary; these never do.

`scan_corpus.py --maps DX/Maps` over the 130 retail Deus Ex map files (`.dx` + `.unr`), 81 of
which contain a mover: **6861** `float32(-12345.0)`
patterns against **2287** `(123,456,789)` int triples — a ratio of exactly **3.00**, i.e. one
three-component `SavedPos` plus one `SavedRot` per mover, in every shipped map without exception.
The retail maps were built by Ion Storm's own UnrealEd against the v68 engine above; the values were
stamped by `PostLoad` and then serialized by `MAP SAVE` precisely *because* they differ from the
class default of zero.

## 4. The one apparent counter-example, and why it confirms the model

Two corpus files (`Temp/downtown_export.t3d`, `Temp/downtown_export_aligned.t3d`) hold 122
Mover-derived actors that carry `BasePos` but **no** `SavedPos`/`SavedRot`. That looked like
evidence the stamp is conditional. It is the opposite: those movers had simply never been *loaded*.
Cross-checking `PostLoad`'s **other** side effect separates the two populations cleanly:

| File                       | Movers | with `Saved*` | polygon `Link` |
|----------------------------|-------:|--------------:|---|
| `Temp/downtown.t3d`        | 78     | 78            | `0..N-1` per mover (74/74 measured) — `PostLoad` renumbered them |
| `Temp/downtown_export.t3d` | 122    | 0             | global BSP indices (`17958`, `17959`, …) on 122/122 — never renumbered |

Both effects are produced by the same function body, and in the corpus they are 100 % correlated.
The `Saved*`-free movers are ones created live in an editor session (import/paste) and exported
without the map ever being saved and re-loaded; the moment a package round-trip happens, `PostLoad`
runs and both fingerprints appear together.

That is exactly `level materialize`'s situation: the post-verify does **not** read the live editor's
export, it reads an offline UCC batchexport of the **saved** `.dx`
(`store_export.export_dx_level`). Loading that package runs `AMover::PostLoad` on every mover, so
the "built" side is *guaranteed* to carry the sentinels while the trunk side never does. The
post-verify failure was deterministic, not flaky.

## 5. Live confirmation — the full chain, measured (2026-07-25)

A throwaway project under `_scratch/` held one subtracted room plus one `DeusEx.DeusExMover` brush,
both produced by `brush build` — so the trunk provably contains **0** `SavedPos`/`SavedRot` lines.
Materializing it and then re-running the post-verify's own reader by hand gives every link in the
chain:

| Stage                                                   | `SavedPos`/`SavedRot` present? |
|--------------------------------------------------------|---|
| the git-tracked T3D trunk (`brush build --mover-class`) | **no** — 0 lines |
| the built `probe.dx` (editor `MAP IMPORT` + `MAP SAVE`) | **no** — 0 sentinel byte patterns |
| an offline `UCC batchexport` of that same `probe.dx`    | **YES** — both, on the mover and nothing else |

The middle row is the §4 model doing its work in miniature: the mover was created inside the editor
session and never *loaded*, so `PostLoad` did not run, `SavedPos` stayed at the class default of
zero, and `MAP SAVE` default-diffed it out of the file entirely. The sentinel is not in the map's
bytes at all — it materializes at the moment the **post-verify's reader** loads the package. Its
`PostLoad` twin confirms it: the mover's six polygons come back `Link=0..5` (renumbered), while the
world brush carries none.

The mover's whole re-exported property list is `BasePos`, `SavedPos`, `SavedRot`, `MainScale`,
`PostScale`, `Level`, `Tag`, `Region`, `Location`, `bSelected`, `Brush`, `Name` — i.e. after this
fix every injected field on it is already in `COMPUTED_PROPS` or already handled. There is no
*third* mover field waiting behind these two, which matches the disassembly exactly (`PostLoad`
writes these two properties and `iLink`, and `iLink` is dropped because `emit_actor` never
writes it).

With `SavedPos`/`SavedRot` in `normalize.COMPUTED_PROPS`, `level materialize` on that level
**passes the H3 post-verify and writes the `.dx`**; before the fix it aborted on `SavedPos` with
nothing written.

A second run added the two things the original bug report flagged as unchecked — `NumKeys=3` with a
`KeyPos(1)=(Z=112.000000)` keyframe, and `bDynamicLightMover=True`. It **also passes**, and its
re-export shows both come back **verbatim**:

```
NumKeys=3                     <- authored, verbatim
bDynamicLightMover=True       <- authored, verbatim (a real var() bool, NOT injected)
KeyPos(1)=(Z=112.000000)      <- authored, verbatim (no echo, no drift)
BasePos=(Y=-400.000000,Z=-200.000000)          <- derived  (already stripped)
SavedPos=(X=-12345.000000,...)                 <- stamped  (stripped by this change)
SavedRot=(Pitch=123,Yaw=456,Roll=789)          <- stamped  (stripped by this change)
Level=… / Tag=… / Region=… / bSelected=True    <- already stripped / already handled
```

So `bDynamicLightMover` and the `KeyPos[]`/`KeyRot[]` arrays — the two things the original bug
report named as unchecked ("check `bDynamicLightMover`, `KeyPos[]` echoes") — are **authored content
and must not be stripped**; the suspicion that they might also be injected is disproved, and the mover injected-field set is
closed at `BasePos`, `BaseRot`, `SavedPos`, `SavedRot`.

One incidental result worth keeping, because it bears on the native-build **byte-identity** goal:
UnrealEd's own `MAP SAVE` of a trunk-authored mover writes **no** `SavedPos`/`SavedRot` into the
`.dx` (measured: zero sentinel byte patterns in `probe.dx`), because in-session movers never went
through `PostLoad` and the fields still hold the class default. A native writer that likewise omits
them therefore matches UnrealEd's bytes; emitting the sentinel would *not*.

## 6. Consequences

1. **`normalize.COMPUTED_PROPS` gains `SavedPos` and `SavedRot`.** They join `BasePos`/`BaseRot` as
   editor/engine-managed mover fields that the compare and the durable trunk emit both drop.
2. **Dropping them from the trunk emit is safe, not merely convenient.** `normalize_actor` also
   feeds the git-tracked trunk and the `MAP IMPORT` payload, where omitting a property means "use
   the class default" — the trap that silently mis-built an `Engine.Camera` and a `TNM.Trestkon`
   `Tag` (see `normalize.normalize_actor`'s docstring). Here the class default is the type zero,
   and `PostLoad` overwrites zero with the sentinel on the very next load anyway, so the omission is
   unobservable by construction.
3. **`SavedTrigger` is left out — and must STAY out.** `COMPUTED_PROPS` is keyed by BARE NAME
   across every class, so a name may be added only when stripping it is right for *every* class
   that declares it. Auditing every shipped `.u` for the three names:

   | Property       | Declared by | Safe to strip globally? |
   |----------------|-------------|---|
   | `SavedPos`     | `Engine.Mover` only | **yes** — exact |
   | `SavedRot`     | `Engine.Mover`; also `DeusEx.LaserIterator` | **yes** — `LaserIterator` is `RenderIterator -> Core.Object`, NOT an `Actor`, so it can never appear in a level T3D |
   | `SavedTrigger` | `Engine.Mover`; also `Engine.TriggerLight` | **NO** — `TriggerLight` is `Light -> Actor`, a placeable actor whose `SavedTrigger` would be silently erased from the durable trunk emit |

   So `SavedTrigger` is excluded for a hard reason, not merely a cautious one — and it costs
   nothing, since `PostLoad` never touches it and it appears zero times in the corpus, so it cannot
   cause a mismatch either way. (The cautious reason still applies too: the same
   "no unverified-symbol guesses" rule that keeps `OldRot` out — spike 2026-06-25 §3.)

## 7. Pinned regressions

- `tests/test_engine_facts.py::test_amover_postload_unconditionally_stamps_the_savedpos_savedrot_sentinels`
  — asserts the 92-byte store sequence is uniquely present in the committed `uned/UED22/Engine.dll`
  **and sits inside the `?PostLoad@AMover@@UAEXXZ` export body**, and that neither sentinel appears
  in `Engine.u` (i.e. it is a stamp, not a class default). A UED22 rebuild that changes or guards
  the stamp trips it.
- `tests/test_normalize.py::test_a_trunk_mover_compares_equal_to_its_editor_reexport_carrying_the_saved_sentinels`
  — the materialize regression itself: a trunk mover and its sentinel-carrying re-export produce an
  equal `compare_view`.
- `tests/test_normalize.py::test_it_strips_the_engine_stamped_mover_saved_sentinels` and
  `…::test_savedtrigger_is_deliberately_NOT_treated_as_computed`.
