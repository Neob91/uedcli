+++
priority = "p3"
kind = "debug"
summary = "Fully decoded FSpanBuffer::MergeWith (render.dll 0x1001e3b0) and live-verified visible_surfs.rs's merge_into matches it exactly; MergeWith ruled out as the cause of Wanchai's zone-crossing missed-pair share."
depends-on = ["port-urender-getvisiblesurfs-so-each-light-gets", "getvisiblesurfs-wanchai-run-gap-root-cause"]
spikes = ["dev/docs/spikes/2026-08-29-unatco-repart-live-diff/"]
+++

# `MergeWith` fully decoded, confirms `merge_into` correct

Resumes the leading open suspect for Wanchai's residual light-run gap (`native-light-apply-bake-
where-it-stands-and`'s lead 1): `visible_surfs.rs::merge_into` was flagged since early in this
session as "a reasonable interval union, not proven bit-identical" to the real editor's
`FSpanBuffer::MergeWith` (`render.dll` file RVA `0x1001e3b0`, the portal-merge-into-far-zone op),
and `getvisiblesurfs-wanchai-run-gap-root-cause` named it "still relevant" for the ~20% of Wanchai's
missed (surf,light) pairs that cross a zone boundary. This item decodes it.

## Static disassembly

`rdis.py dis Render 0x1001e3b0 0x400` (`dev/docs/spikes/2026-08-27-native-light-apply-parity/
harness/`) gives the complete function body, prologue to `ret 4`, no gaps. `MergeWith(this, Other)`:

1. If `Other`'s `[StartY,EndY)` row range isn't already contained in `this`'s own range, grow
   `this->Index` (the per-row linked-list-head pointer array) to cover the union of both ranges,
   copying the old array into its new offset and zero-filling the newly extended rows. Irrelevant to
   this port — `SpanBuf` always allocates the full `[0,RES)` range up front and never needs to grow.
2. For each row `y` in `Other`'s range, merge the two sorted disjoint 12-byte `{X0,X1,Next}`-node
   interval lists — `this->Index[y]` and `Other->Index[y-Other.StartY]` — into one new sorted
   disjoint list written back to `this->Index[y]`: a standard two-sorted-list merge,
   `FMemStack`-allocating a fresh node for anything not already owned by `this` (an Other-only run,
   or a `this`-chain member absorbed further into a growing merged run — `this`'s FIRST node in a
   merged run is mutated in place, never reallocated). Two intervals that only TOUCH
   (`OtherX1 == ThisX0`, half-open boundary) still merge (`jge`, not `jg`, at the overlap test).

`this+8` (`ValidLines`, per the pre-existing `FSpanBuffer` struct-layout note — `StartY@0 EndY@4
ValidLines@8 Index@0xc Mem@0x10`) turns out to be a total INTERVAL-NODE count (±1 per node
alloc/absorb), not a per-ROW count as `SpanBuf::valid_lines` assumes (only flips ±1 on a row's
empty↔non-empty transition). This does NOT matter functionally: every consumer
(`SpanBuf::any_visible`, the real `ValidLines <= 0` zone-reachability test) only tests `>0`/`<=0`,
which both countings agree on (zero iff the buffer is genuinely empty).

## Live capture

`mergewith_live_check.py` (new, same harness dir) breaks at `MergeWith`'s real runtime address
during a genuine Wanchai `LIGHT APPLY`, dumping `this`/`Other`'s struct fields and one row's raw
`Index[]` linked-list content before and after each hit.

**First finding, not previously known**: render.dll does NOT load at its preferred image base
`0x10000000` in this wine process — it actually loads at `0x015b0000` (confirmed via `/proc/PID/
maps`; Engine.dll and core.dll are also relocated, to `0x01620000`/`0x019a0000`). Only Editor.dll
keeps its preferred slot. Every prior live gdb capture in this codebase happened to target
Editor.dll addresses, so this gap was latent — a live breakpoint at any previously-cited
"render.dll 0x1001XXXX" address would have silently broken into the wrong code. The real live VA is
`render_base + (static_va - 0x10000000)`, resolved fresh from `/proc/PID/maps` every run (the script
never assumes a fixed base). Verified via `--probe`: raw bytes at the computed live address match
the static prologue exactly, including a relocated absolute operand (the SEH-handler push).

10 real `MergeWith` calls captured during one `LIGHT APPLY`: 7 were a pure append (this row empty,
Other contributes one node — output equals Other's node verbatim); 3 were a genuine merge, including
two touching-boundary cases (`(978,980)` + row content `(976,978)` → `(976,980)`; `(974,991)` +
`(971,974)` → `(971,991)`) and one interior overlap (`(315,316)` + `(316,317)` → `(315,317)`). All 10
match, node for node, what `merge_into` independently computes from the same captured inputs.

## Conclusion

`merge_into` needed no fix — it already reproduces `MergeWith`'s real row-merge algorithm exactly,
including the touching-boundary merge rule, for every case sampled. Ported the finding into
`visible_surfs.rs`'s doc comments (`SUBTRACT_OCCLUSION` and `merge_into` itself) and added
`merge_into_matches_the_real_editors_output`, a regression test pinning the 3 live-captured merge
cases. No functional code change: `regression_gate.py` unaffected (UNATCO 6314/6314, Wanchai
11648/11648, both exact, before and after — this is a doc-comment + `#[cfg(test)]`-only diff, cannot
change the compiled extension's behavior). `bin/test -k visible_surfs` 88/88 green; full `bin/test`
green.

**Leaves the ~20% zone-crossing share of Wanchai's missed pairs unexplained.** `MergeWith` is ruled
out as the cause here, not identified as fixed — the real cause of that residual is still open for a
future round.
