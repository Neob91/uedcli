+++
priority = "p2"
kind = "chore"
summary = "[OWNER — approve] The FindBestSplit reference port in the 2026-06-26 spike has the wrong GOOD stride (/10, should be /20) and builds the splitting plane from the winding; both need owner approval to edit"
+++

# The `FindBestSplit` reference port in the 2026-06-26 spike is stale

`dev/docs/spikes/2026-06-26-bsp-partition-heuristic-from-binary.md` and its harness are described as
"the reference the offline engine should build `SplitPolyList` on top of". Two things in them now
disagree with both the binary and `uedcli-native`. They live under `dev/docs/spikes/`, so they need
the owner's yes before anyone edits them.

1. **GOOD stride is `NumPolys/20`, not `/10`.** `harness/find_best_split.py:107` (`_inc_for`) and §2a
   of the doc both say `num // 10`. `Editor.dll 0x1003369e` is `mov eax,0x66666667; imul esi; sar
   edx,3` — `sar 3` makes it `>>35` = `/20`; `/10` would be `sar 2`. The spike's own corroborating
   number agrees with `/20`: a soup of 2449 gives stride 122, not 244. The code has always used
   `/20`, and the geometry spec's §5.2 text has been corrected in place.
2. **The splitting plane comes from the poly's STORED base+normal.** The port's `FPoly.plane()`
   recomputes the normal from the winding. `Editor.dll 0x10033799`..`0x100337b3` copies `[ebx+0x0..8]`
   (Base) and `[ebx+0xc]` (Normal) straight into the `FPlane` constructor. The doc already flags this
   as a deliberate deviation (§2d note 2), so this one is a judgement call — but a "reference port"
   that a faithful implementation must deviate from is a trap for the next reader.

Both were re-read from the shipped DLLs on 2026-08-25 during the `find_best_split_exact` audit (see
the Front-2 item). Everything else in the port was checked against the binary in the same pass and
matches: slot advance, window scan, the `0x28`-only pre-pass, the inner classify stride and `j == i`
skip, the score term order, the portal x16 and portal-candidate bonus, and the strict-`<` tie-break.
