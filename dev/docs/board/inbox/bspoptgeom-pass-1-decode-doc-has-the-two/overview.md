+++
priority = "p3"
kind = "docfix"
summary = "42-bspoptgeom-decode.md pass-1 pseudocode lists AddPointLink(pA) then AddPointLink(pB); the DLL (0x100369b8-0x100369f4) welds pB (current vertex B) first, pA (A=B-1) second. Fixed in code (bspoptgeom.rs, commit ade7efb) with the disassembly cited; the spike doc still shows the reversed order. Editing the spike doc needs owner approval."
+++

# `42-bspoptgeom-decode.md` pass-1 has the two `AddPointLink` calls reversed

The Pass-1 pseudocode in `dev/docs/spikes/2026-07-15-native-materialize/42-bspoptgeom-decode.md`
(`0x36939` loop) reads:

```
AddPointLink(Model, table, root=0, pA)  # 0x325e0
AddPointLink(Model, table, root=0, pB)  # 0x325e0
```

The real order is the reverse. Re-disassembled 2026-09-04 (`Editor.dll 0x100369b8`-`0x100369f4`):
the first call pushes `Verts[iVertPool + [ebp-0x30]]` where `[ebp-0x30]` = `B` (the CURRENT vertex),
the second pushes `[ebp-0x28]` = `A = B-1`. So the editor welds **`pB` (current) first, `pA`
(previous) second**.

Observable: when one edge's two endpoints each trigger a final ring re-append into two different
nodes, the order sets their `iVertPool` offsets. The reversed native order swapped the two rings —
WanChai N=5 nodes 4/17 `iVertPool` 282<->288, the sole N=5 parity residual. Fixed in
`uedcli-native/src/bspoptgeom.rs` (`eliminate_tjunctions`, commit `ade7efb`); the code comment
carries the disassembly.

Action: correct the pseudocode in the spike doc (swap the two lines, note the current-then-previous
order). Editing `dev/docs/spikes/` needs the owner's yes, so this is filed rather than done.
