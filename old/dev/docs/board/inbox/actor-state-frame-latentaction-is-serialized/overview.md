+++
priority = "p1"
kind = "unknown"
summary = "UnrealEd cannot reproduce its OWN output byte-for-byte: two independent builds of one trunk differ in 4 bytes at body offset 10-13 of 933 of 1416 `RF_HasStack` (actor) exports, plus the GUID and one elapsed-time float. The bytes sit where `FStateFrame`'s `LatentAction` INT goes and look like uninitialized heap pointers. A hard ceiling on the full-byte-parity goal: those bytes are unmatchable by anything, native included, so they have to be excluded from the parity definition."
depends-on = ["texture-ref-i-actor-divergence-traced-to-golden"]
+++

# Actor `RF_HasStack` state frames carry 4 uninitialized bytes each — the editor is not byte-deterministic

Found in round 8 of `texture-ref-i-actor-divergence-traced-to-golden`, while testing whether the
editor's object numbering is reproducible across sessions. It is; this is not.

## Measurement

Two independent self-builds of the same UNATCO trunk, separate fresh editor containers, identical
input, both 2533794 bytes: `/tmp/uedcli-widen-test/unatco_widened.dx` and `unatco_widened_run2.dx`
(round 2 left them). 1603 bytes differ, in exactly three places:

| where | bytes | what |
|---|---:|---|
| offset 36 | 16 | package GUID — already excluded from the parity goal |
| body offset 10-13 of actor exports | ~1585 | see below |
| inside `MyLevel` | 2 | a float32, `102.62` vs `102.57` — an elapsed-time field |

Everything else is identical: the name table (3357 entries, same ORDER), the import table (289), the
export table (2890 rows, every field including serial offsets), and the 1.65 MB world BSP `Model2`.

The actor bytes correlate perfectly with `RF_HasStack` (`0x02000000`): **933 of 1416** `RF_HasStack`
exports differ, versus **1 of 1474** without it (that one is `MyLevel`, the elapsed-time float
above). Every differing actor differs at body offset 10-13 and nowhere else. Each body opens:

    90 90 ff ff ff ff ff ff ff ff <4 bytes>

with the 4 bytes changing every run — `14 00 01 00` vs `e0 79 46 0d` for `Light9`, `08 00 02 17` vs
`10 f2 e1 10` for `Brush14`. They read as heap pointers.

## Reading

UE1 serializes an `RF_HasStack` object's `FStateFrame` first: `Node`, `StateNode` (both compact
indices — the two `90` bytes, i.e. import ref -16 twice), `ProbeMask` (QWORD — the eight `ff`), then
`LatentAction` (INT). That puts the four varying bytes exactly on `LatentAction`, serialized
uninitialized.

**Layout-inferred, not disassembly-confirmed.** Confirming it means finding the `FStateFrame`
serializer in `Core.dll`/`Engine.dll` and checking whether `LatentAction` is initialized on the
editor's actor-creation path. Same family as the already-tracked uninitialized-memory finding in
`node-flags-0x40-0x80-divergence-from-movers-no`. The 483 `RF_HasStack` exports that happen to match
between the two runs fit garbage that sometimes collides.

## Why it matters

The standing goal is full BYTE parity on 30% of the 21-level OG corpus. This says the oracle is not
byte-stable against itself: ~4 bytes per actor are unmatchable by any producer, native included. On
UNATCO that is ~1416 actors ≈ 5.6 KB. So the parity definition needs these bytes excluded the same
way the GUID and save timestamps are, or "full byte parity" is unreachable by construction.

Not urgent for the current comparison path — `parity_report.py` compares decoded
nodes/surfs/leaves/lightmaps, never raw actor bodies — but it is load-bearing for any future
whole-file byte comparison, and it should be reflected wherever the parity goal is written down.
Deciding that is the owner's call, not something to fold in silently.
