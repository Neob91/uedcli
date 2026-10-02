+++
priority = "p2"
kind = "bug"
summary = "autonomous struct-class compile diverges from UCC (Struct name +0x400; struct member next_field unchained)"
+++

# autonomous struct-class compile diverges from UCC

Found while building the autonomous compiler + `perm_gate` (commit `49bb638`). A class with a
`struct` member compiled autonomously does NOT match a real UCC golden — two distinct pre-existing
`compile.py` gaps, both surfaced by `perm_gate` against a UCC-compiled golden of:

    class UscSt expands Object;
    struct SPoint { var int X; var int Y; };
    var SPoint Pt;
    var int Solo;

## A — the `Struct` name misses the `+0x400` (RF_HighlightName) flag

UCC flags the `Struct` name `0x04070410`; uedcli emits `0x04070010`. `_STRUCTURAL_NAMES` in
`compile.py` (the `+0x400` set) is `{None, Class, Package, Function}`; the RF_HighlightName pool
also includes at least `Struct` (and, by the same reasoning, likely `Enum`, `Const`, `State`).
Derivable the same way as the RF_Native pool — the names carrying `0x400` across stock `.u` tables.

NOTE: the current build task's spec explicitly enumerated the `+0x400` set as `{None, Class,
Package, Function}`, so widening it is an owner decision, not a silent fix (per direction/process).

## B — struct member properties are not chained via `next_field`

UCC links a struct's member UProperties `X -> Y -> 0` (same as class Children). uedcli leaves each
struct member's `next_field = 0` (`X.next == none`, should be `Y`). `_build_exports` builds
`next_lookup` from the class chain + each function's child chain only — it never adds struct member
chains. The struct's `Children` head is set, but the sibling chain is broken.

## Scope / status

Neither is in the 4 controlled classes (UscHello/UscVars/UscFn/UscW) the compiler is validated on,
and both are pre-existing (untouched by `49bb638`). `perm_gate`'s struct-default canonicalization
(`c06302b`) is in place, so once A+B land a struct class should reach byte parity. Repro harness:
`ucc_compile` the source above, `perm_gate(serialize(compile_package(src, env)), golden)`.
