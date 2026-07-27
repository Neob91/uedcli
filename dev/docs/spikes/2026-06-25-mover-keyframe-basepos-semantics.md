# Mover keyframe semantics — `BasePos`/`BaseRot` are derived, `Location` tracks the selected keyframe

**Date:** 2026-06-25
**Method:** live probe in `uned-spike1` (UED22 under wine). Authored mover T3Ds with known
`BasePos`/`BaseRot`/`KeyPos(N)`/`KeyRot(N)`/`KeyNum`/`Location`/`Rotation`, `MAP IMPORTADD`'d
them, switched the editing keyframe via `ACTOR KEYFRAME NUM=#`, and read every field back via
`MAP EXPORT`. Also verified the mover survives uedcli's `EDIT PASTE` materialize path.
**Confidence:** ✅ live-verified (every value below is a `MAP EXPORT` readback).

This closes the design fork raised while speccing offline mover support: "when `actor move`/
`actor rotate` change a mover's `Location`/`Rotation`, how do we keep `BasePos`/`BaseRot` from
drifting?" Answer: **uedcli does not author `BasePos`/`BaseRot` at all** — the editor derives
them. See "Design consequences" below.

---

## The model (all confirmed)

A `Mover`'s **`Location`/`Rotation` are a DERIVED view of the currently-selected keyframe's
world pose** — not a stable anchor:

```
Location = BasePos + KeyPos[KeyNum]
Rotation = BaseRot + KeyRot[KeyNum]      (FRotator field-addition, same as actor rotate)
```

and **`BasePos`/`BaseRot` are themselves DERIVED from the imported `Location`/`Rotation`** (the
pose at key 0). An authored `BasePos`/`BaseRot` in import T3D is **ignored/overwritten**.

- **`KeyPos[0]` / `KeyRot[0]` are `(0,0,0)` by definition** — key 0 *is* the base pose.
- **`KeyPos[i]` / `KeyRot[i]` (i ≥ 1) are offsets from base**, preserved verbatim as authored.
- **`NumKeys` default = 2** (omitted on export when 2).
- `OldLocation` is computed too (tracks `Location`).

## The four tests

**B — `ACTOR KEYFRAME NUM=#` recomputes `Location`.** Imported `KeyNum=0`, `KeyPos(1)=(Z=256)`,
`Location=0`. Export: `Location` omitted (=0). `ACTOR KEYFRAME NUM=1` → export shows
`KeyNum=1`, **`Location=(Z=256)`**. Back to `NUM=0` → `Location` returns to 0. So switching the
editing keyframe live moves `Location` to `BasePos + KeyPos[KeyNum]`.

**C — import reconciles `Location` to the keyframe.** Imported a *deliberately inconsistent*
mover: `KeyNum=1`, `KeyPos(1)=(Z=256)`, `Location=(0,0,0)`. Export: the editor **overwrote
`Location` to `(Z=256)`**, surviving `MAP REBUILD`. The authored `Location` for a non-zero
`KeyNum` is discarded in favour of `BasePos + KeyPos[KeyNum]`.

**D — authored `BasePos` is discarded.** Imported `BasePos=(Z=100)`, `KeyPos(1)=(Z=256)`,
`KeyNum=1`, `Location=0`. Expected `Location=356` if `BasePos` were honoured. Got **`Location=
(Z=256)` and no `BasePos`** — i.e. `BasePos := imported Location (0)`, then `Location := 0 +
KeyPos[1] = 256`. `BasePos`/`BaseRot` cannot be set independently via T3D.

**E — author the base pose via `Location` with `KeyNum=0` (the clean path).** Imported
`KeyNum=0`, `Location=(Z=100)`, `Rotation=(Yaw=8192)`, `KeyPos(1)=(Z=256)`, `KeyRot(1)=
(Yaw=16384)`. Export E0: **`BasePos=(Z=100)`, `BaseRot=(Yaw=8192)`** (derived from
`Location`/`Rotation`), `KeyPos(1)`/`KeyRot(1)` preserved, `Location=(Z=100)`. After
`ACTOR KEYFRAME NUM=1`, export E1: **`Location=(Z=356)` (=100+256), `Rotation=(Yaw=24576)`
(=8192+16384)**, `BasePos`/`BaseRot` unchanged. Exactly the additive model above.

## Materialize path (`EDIT PASTE`) — movers are fine

uedcli materializes brushes via `EDIT PASTE` (not `MAP IMPORTADD`). Pasting a `Mover` block:
`KeyPos(1)`/`KeyRot(1)` are preserved and **survive `MAP REBUILD`**; the mover brush carries
**no `CsgOper`** (default `CSG_Active` = 0) → it stays out of the world BSP/CSG, matching the
collision spike (`2026-06-24-bsp-collision-solidity-movers-from-binary.md` §3 — movers use the
dynamic collision hash, not world CSG). The usual `EDIT PASTE` **+32uu drift on all 3 axes**
applies (`Location`/`BasePos` came back +32 each) — uedcli's existing −32 pre-shift cancels it,
same as for any brush.

## Design consequences (for the mover spec)

1. **uedcli authors movers at `KeyNum=0` and stores the base pose in the ordinary
   `Location`/`Rotation` fields** — exactly like every other actor — plus `KeyPos(N)`/`KeyRot(N)`
   offset arrays for keys 1..N-1. **uedcli never emits `BasePos`/`BaseRot`**; the editor derives
   them from `Location`/`Rotation` at materialize.
2. **The fork dissolves: `actor move`/`actor rotate` need NO mover special-casing.** They edit
   `Location`/`Rotation` (the base pose at `KeyNum=0`); the editor re-derives `BasePos`/`BaseRot`
   from them. The `BasePos == Location` invariant is maintained by the editor for free, given
   stored `KeyNum=0`. (Neither "recompute `BasePos` at emit" nor "sync inside move/rotate" is
   needed.)
3. **`normalize.COMPUTED_PROPS` must strip `BasePos`, `BaseRot`, `OldLocation`** (and `OldRot`
   if it appears) — they are editor-computed from `Location`/`Rotation`, so a uedcli-authored
   mover (which lacks them) and its re-exported form (which has them = `Location`/`Rotation`)
   must canonicalize equal, or H3 post-verify and the canonical hash spuriously differ.
4. **`KeyPos(N)`/`KeyRot(N)` are the `Foo(N)` indexed-array lines** the model currently drops —
   the indexed-array round-trip fix (`board/to-spec/`) is the hard prerequisite; `KeyNum`/`NumKeys`
   are plain scalars and already round-trip.
5. **`mover key list` resolves a key's world pose** as `Location + KeyPos[i]` /
   `Rotation + KeyRot[i]` (base = `Location`/`Rotation`, since stored `KeyNum=0`).
6. **Reading existing maps (THEIRS):** a mapper may leave a mover at `KeyNum≠0`, so `Location`
   for that actor is `base + offset`, not the base. **uedcli canonicalizes such a mover back to
   `KeyNum=0` on ingest** (`movers.canonicalize_mover`; rationale in `decisions.md` 2026-06-25 mover
   entry) — folding the selected-key offset
   out of `Location`/`Rotation` and dropping `KeyNum` — rather than preserving `KeyNum≠0`
   verbatim. (An earlier draft of this note said "preserve verbatim"; that round-trips WRONG: on
   the next `EDIT PASTE` materialize the editor would set `BasePos := imported Location = base+
   offset`, then `Location := BasePos + KeyPos[KeyNum] = base + 2·offset` — drift. The
   `KeyNum≠0`-via-`EDIT PASTE` drift is an extrapolation from test D's `MAP IMPORTADD` result,
   confirmed by the spec's integration step.) The computed `BasePos`/`BaseRot` are stripped by (3);
   for uedcli-authored movers `KeyNum` is always 0.

## Notes / loose ends

- `BRUSH ADDMOVER` on the default (empty) builder brush after `MAP NEW` produced an empty mover
  (no PolyList, no `Brush=` ref) — irrelevant to authoring (uedcli emits the brush model-side),
  but it confirms `BRUSH ADDMOVER`/`ACTOR KEYFRAME` are a dead end for *authoring* (Spike 7,
  2026-06-23): keyframe values are T3D-authored regardless.
- The `EDIT PASTE` test produced two mover actors from a one-mover clipboard (an auto-naming
  artifact of pasting a `Begin Map` block); uedcli controls clipboard content + names (D6) so
  this is not a concern for the real materialize path.
## Follow-up: `KeyPos[i]` is world-additive even when `BaseRot≠0` (✅ resolved 2026-07-07)

The one loose end above — whether `KeyPos[i]` is added in **world axes** or first **rotated by
`BaseRot`** when the base is rotated — is now closed: **`KeyPos[i]` is world-additive**
(`Location = BasePos + KeyPos[i]`, the offset is **NOT** rotated by `BaseRot`). Confirmed two
independent ways:

- **Live measurement:** a 90°-yaw base mover with `KeyPos(1)=(X=256)` moved along **world +X**
  (not +Y, which a `BaseRot`-rotated offset would give).
- **Disassembled transform code:** the editor's own mover transform adds `KeyPos[i]` to
  `BasePos` directly, with no rotation applied.

The companion **rotation** question was never actually open: test E above already verified
`Rotation = BaseRot + KeyRot[i]` live (`Yaw=8192 + Yaw=16384 = Yaw=24576`), and FRotator addition
is componentwise integer addition — the same `rotation.compose_uu`/`subtract_uu` path `actor
rotate` uses for every actor, with no world-vs-object subtlety. So uedcli's v1 assumption (both
offsets stored plainly, no `BaseRot` special-casing) was correct on both axes.

**Consequence:** the interim `mover key add/move/rotate` stderr caution on a base-rotated mover was
pure noise and has been removed (`dispatch.py`; regression test
`test_it_does_not_warn_on_a_base_rotated_mover_key_op`). See `decisions.md` 2026-07-07 12:11 UTC.
