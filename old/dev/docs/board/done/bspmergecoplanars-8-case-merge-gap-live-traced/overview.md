+++
priority = "p2"
kind = "debug"
summary = "bspMergeCoplanars 8-case merge gap: RESOLVED — RemoveColinears has a 3rd stage (reflex-vertex convexity gate) the port missed"
+++

# bspMergeCoplanars 8-case merge gap — RESOLVED

Follow-up session pinned the root mechanism this item had left open. `RemoveColinears`
(`Engine.dll 0x151090`) has a THIRD stage no prior pass caught: for each vertex where the simple
colinear-normal test doesn't already flag it, the engine classifies the WHOLE ring against that
vertex's own tangent plane (`SplitWithPlane`) and REJECTS THE WHOLE MERGE if the classification is
`Front` or `Split` — i.e. a reflex (non-convex) vertex anywhere in the candidate ring aborts the
merge outright, not just that vertex. Confirmed at instruction level: fresh disassembly
(cross-checked against `Engine.dll`'s own PE export table), a corrected live capture (breakpoint on
`RemoveColinears`'s real runtime entry, resolved via the live IAT slot — `Engine.dll` rebases
~`-0xF00000` at runtime, `Editor.dll` doesn't — filtered by the exact `TryToMerge` caller return
address so it can't catch the OTHER, far-more-frequent call site) that reproduced the real ring
byte-for-byte, and direct x86 emulation (`unicorn`) of the real machine code bytes against that
ring, which reproduces the live `rc_eax=0` reject exactly.

Fixed in `uedcli-native/src/fpoly.rs` `remove_colinears` (restructured to the real 3-stage
algorithm); 2 new regression tests (`remove_colinears_rejects_a_reflex_merge_ring`,
`remove_colinears_still_merges_a_plain_convex_ring`); `cargo test --release` 57/57. Re-measured
full UNATCO: soup size now **2514, exactly matching the editor's own 2514** (was 2504); all 8
previously-divergent `iLink`s now match the editor's documented fragment shapes exactly (verified
against `logs/repart-soup-full-unatco.log`). Final repartitioned tree moved `6366`→`6364` nodes
(editor's real golden: `6314`) — the remaining ~50-node gap is the ALREADY-SEPARATELY-DIAGNOSED
fragment-reorder / `GOOD`-mode stride-sampling sensitivity from `findbestsplit-divergence-forensic-dive-17-real`,
not a fragment-shape issue; this item owned the shape divergence only, which is now fully closed.

Spec updated: `dev/docs/board/inbox/unrealed-geometry-build-map-rebuild-bsp-rebuild/spec.md` §4.

Harness scripts committed under
`dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/`:
`removecolinears_entry_unatco.py` (the live gdb capture) and `emulate_removecolinears.py` (the
`unicorn`-based machine-code emulation that reproduced the live reject) — both durable per
`dev/docs/rules/spikes.md`. The finding itself is pinned by the spec citation + the regression test,
not by either harness script alone.
