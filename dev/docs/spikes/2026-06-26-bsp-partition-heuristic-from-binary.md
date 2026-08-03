# UnrealEd 2.2's BSP partition-plane heuristic (`FindBestSplit`) — decoded, byte-verified, and the open items closed

**Date:** 2026-06-26
**Method:** static disassembly of the shipped UED22 DLLs (`capstone`+`pefile`; no editor run).
Independently re-disassembled `Editor.dll`'s `FindBestSplit` and the `MAP REBUILD` exec parser,
and `Engine.dll`'s `SplitWithPlaneFast`; pinned every load-bearing instruction to a specific
address and **byte sequence**, and committed a harness that re-asserts those bytes against the
binary so the doc can't silently go stale.
**Confidence:** **decompiled facts** — every claim with an address was read out of the compiled
code, and every numeric/threshold/branch claim is backed by a passing byte-level assertion in
`harness/verify_heuristic.py` (24/24 checks pass against the committed UED22 DLLs).

> **Why this spike exists.** The offline-BSP-engine decision (board item `bsp-issue-detector`) named
> **one gating unknown**: `bspBuild`'s partition-plane
> selection — `FindBestSplit`, the `Balance`/`PortalBias` scorer that decides which polygon
> plane splits each BSP node. The whole BSP tree — hence which faces split, survive, or drop —
> hinges on this one heuristic, and it was flagged as the piece NOT yet disassembled. An earlier
> same-lineage spike (`2026-06-24-bspbuild-partition-heuristic-from-binary.md`) had in fact
> already decoded the bulk of it but left three "small open items" (§4 there): the
> structural-splitter candidate skip was only *partially* decoded, `SplitWithPlaneFast` was
> unread, and the score's float32/sign details were asserted from the textbook rather than the
> bytes. **This spike closes all three, re-verifies the rest at the byte level, and ships a
> reproducible verification harness + a faithful reference port of the heuristic.** It is the
> gate the BSP-engine project was waiting on.

---

## 0. Read this first — vocabulary

- **BSP build** — UnrealEd indexes the world's polygons into a binary tree of planes. At each
  tree node it must pick ONE polygon's plane to partition the remaining polygons into "front of
  this plane" and "behind this plane". `FindBestSplit` is the function that scores the candidate
  planes and picks the partitioner; `SplitPolyList` is the recursion that uses it and emits nodes.
- **`FPoly`** — the engine's in-memory convex polygon (≤16 verts, a normal, texture vectors,
  a 32-bit `PolyFlags` field at byte offset `0x1b0`).
- **Front / Back / Coplanar / Split** — how one poly sits relative to a candidate plane: entirely
  in front, entirely behind, lying in the plane (within a tolerance band), or straddling it (must
  be cut). `SplitWithPlaneFast` returns exactly this 4-way classification.
- **`Balance`** — an integer knob (0–100) trading off tree *balance* (how evenly front/back split)
  against the number of *splits* a plane causes. **`PortalBias`** — a separate knob that makes the
  builder prefer to partition on portal/zone planes. Both come from the `MAP REBUILD` command.
- **`PolyFlags` bits used here:** `PF_Portal = 0x04000000` (a zone-portal face); `PF_Semisolid
  (0x20) | PF_NotSolid (0x08) = 0x28` — the "structural" mask: a poly with either bit is a
  non-solid/semisolid surface that the builder prefers NOT to partition on.

All addresses below are **file RVAs as `pefile` reports them** (ImageBase `0x10000000` for both
DLLs); subtract nothing.

---

## 1. The call chain (where the heuristic lives)

```
UEditorEngine::bspBuild            Editor.dll 0x35ef0   the BSP-build driver
  └─ SplitPolyList (recursive)     Editor.dll 0x34530   pick best plane, partition, emit nodes, recurse
       └─ FindBestSplit            Editor.dll 0x335d0   THE HEURISTIC (this spike)
            └─ FPoly::SplitWithPlaneFast  Engine.dll 0x151f90   the front/back/coplanar/split classifier
```

Verified `bspBuild` → `SplitPolyList` call (Editor `0x35fe1`):
`bspBuild` pushes `(model, -1, 3, PolyList, NumPolys, arg_c, arg_10, arg_14)` and `call 0x34530`
— the last three are `bspBuild`'s own `(BalancePortal, Optimization, …)` params, threaded down to
`FindBestSplit`. (This confirms the prior spike's §1b arg-threading.)

---

## 2. `FindBestSplit` — fully decoded (Editor.dll `0x335d0`)

**Signature** (from the disassembly): `FindBestSplit(INT NumPolys, FPoly** PolyList, INT
Optimization, INT BalancePortal)`.

`BalancePortal` packs two bytes — decoded at `0x10033629`–`0x10033651`:
- **`Balance = BalancePortal & 0xFF`** (`movzx eax, cl`).
- **`PortalBias = ((BalancePortal >> 8) & 0xFF) / 100.0`** (`sar eax,8; movzx eax,al; cvtdq2ps;
  divss [100.0]`). So the caller passes Balance in the low byte and PortalBias·100 in byte 1.

### 2a. The candidate/classify step (`Inc`) — by optimization level

`0x1003369e`–`0x100336c8`:
- **OPTIMAL (2) → `Inc = 1`** (`lea ebx,[eax-1]` with eax=2): try every poly — **exact**.
- **GOOD (1) → `Inc = NumPolys / 10`** (signed, via the `0x66666667` magic-multiply idiom).
- **LAME (0) → `Inc = NumPolys / 4`** (signed `(n + (n>>31 & 3)) >> 2`).
- Floored at 1 (`cmp ebx,1; mov eax,1; cmovle ebx,eax`).

The **classification inner loop steps by the SAME `Inc`** (`0x100337d7 add edi,[ebp-0x18]`), so
GOOD/LAME score against a *subsample* of polys. Only OPTIMAL (Inc=1) is exact.

### 2b. The structural-splitter candidate skip — **fully decoded (closes prior §4.1)**

This was the prior spike's only *partially*-decoded item. The exact mechanism, now read end-to-end:

1. **Pre-pass** (`0x100336cb`–`0x100336ef`): walk `PolyList` for the first poly **without** the
   `0x28` structural mask (`test byte [eax+0x1b0],0x28; je found`). Set a flag
   **`all_structural = (no such poly found)`** = (every poly is semisolid/notsolid).
   (`setge al` on "index reached NumPolys" → `[ebp-0x40]`.)
2. **Per-candidate skip** (`0x1003374b`–`0x10033760`):
   ```
   test al, 0x28               ; cand.flags & (PF_Semisolid|PF_NotSolid)
   je   keep                   ; not structural -> always a candidate
   test eax, 0x4000000         ; PF_Portal
   jne  keep                   ; a portal is always a candidate
   cmp  [ebp-0x40], 0          ; the all_structural flag
   je   skip-this-candidate    ; skip a structural non-portal UNLESS everything is structural
   ```

So: **a structural (semisolid/notsolid) poly is skipped as a candidate splitter, unless it is a
portal, or unless the whole list is structural** (in which case the builder has no choice and
considers them all). Non-structural polys and portals are always eligible.

### 2c. The score

The classification counters live at: Front `[ebp-0x1c]`, Back `[ebp-0x20]`, Coplanar `[ebp-0x30]`,
Splits `[ebp-0x14]`. The `SplitWithPlaneFast` return value indexes a jump table at `0x10033934`
that increments exactly one of them — table values **byte-verified**:
`0 (Coplanar)→0x337ce`, `1 (Front)→0x337df`, `2 (Back)→0x337fa`, `3 (Split)→0x3380e`.

- **Portal split ×16** (`0x33814`/`0x33832`): a *split* poly that is a portal does `add Splits,
  0x10`; otherwise `inc Splits`. (Byte-verified `test [eax+0x1b0],0x04000000` + `add eax,0x10`.)
- **Score** (`0x33843`–`0x33878`), in float32 SSE (`f3 0f …` scalar ops, byte-verified):
  ```
  Score = (100.0 - Balance) * Splits  +  Balance * |Front - Back|
  ```
  `|Front-Back|` is the `cdq; xor; sub` abs idiom at `0x33862`–`0x3386b`. `100.0` is the constant
  at `0x100dcb38` (byte-verified = 100.0).
- **Portal candidate bonus** (`0x33881`–`0x33896`): if the *candidate* poly is a portal,
  ```
  Score -= (100.0 - Balance) * Splits * PortalBias
  ```
  (`test [ebx+0x1b0],0x04000000`, then `mulss xmm2,[ebp-0x50]` (= the reused `(100-Balance)*Splits`
  term) `* PortalBias`, `subss`). Byte-verified.
- **Tie-break** (`0x338a0`–`0x338b6`): `comiss best,Score; ja take` plus a "first candidate is
  always taken" guard (`[ebp-0x2c]==0`). This is a **strict `<`** — the **earliest** candidate
  wins a tie. Fully deterministic; no RNG, no hidden state.

### 2d. The reference port

`harness/find_best_split.py` is a faithful, self-contained port of §2a–§2c (candidate selection,
`Inc`, the float32 score, the earliest-tie rule) plus `SplitWithPlaneFast` (§3). It is the
reference the offline engine should build `SplitPolyList` on top of.

**The candidate loop is NOT a plain `range(0, num, inc)`** — that was a first-cut simplification
and is wrong for `inc>1`. The binary (`0x336ff`–`0x33772`, loop-back `0x338c1`) processes
consecutive **slots** k = 0,1,2,…: slot k spans candidate indices `[k·inc, (k+1)·inc)`, and the
candidate actually used is the **first ELIGIBLE poly in that window** (a structural-non-portal
poly is skipped, scanning forward within the same window; a fully-structural window yields no
candidate). For `inc=1` (OPTIMAL — the default `MAP REBUILD`) each window is one poly, so this
reduces to "every eligible poly". For GOOD/LAME the chosen positions are the first eligible poly
at-or-after each `inc`-boundary, not the boundary itself — a plain strided loop picks the wrong
subsample positions. The port models the slots faithfully:

```python
def find_best_split(polys, *, optimization=OPTIMAL, balance=50, portal_bias=70) -> int:
    num = len(polys)
    if num <= 1: return 0
    inc = _inc_for(optimization, num)                 # OPTIMAL->1, GOOD->num//10, LAME->num//4, >=1
    pbias = _f32(portal_bias / 100.0)
    all_structural = all(p.is_structural() for p in polys)   # the prepass flag (§2b)
    best_i = best_score = None
    slot_start = 0
    while slot_start < num:                            # slot k = [slot_start, slot_start+inc)
        cand_i = None
        for k in range(slot_start, min(slot_start + inc, num)):
            p = polys[k]
            if p.is_structural() and not p.is_portal() and not all_structural:
                continue                              # structural skip: scan within the window
            cand_i = k; break                         # first eligible poly in the window
        slot_start += inc
        if cand_i is None: continue                   # fully-structural window -> no candidate
        i = cand_i; cand = polys[i]; plane = cand.plane()
        front = back = splits = 0
        for j in range(0, num, inc):                  # inner classify loop IS a plain stride
            if j == i: continue
            c = split_with_plane_fast(polys[j], plane)
            if   c == FRONT: front += 1
            elif c == BACK:  back  += 1
            elif c == SPLIT: splits += 16 if polys[j].is_portal() else 1
        split_term = _f32(_f32(100.0 - balance) * splits)
        score = _f32(split_term + _f32(balance * abs(front - back)))
        if cand.is_portal():
            score = _f32(score - _f32(split_term * pbias))
        if best_score is None or score < best_score:  # strict < -> earliest wins ties
            best_i, best_score = i, score
    return best_i if best_i is not None else 0         # see note 3 below on the no-candidate case
```

Three port-vs-binary notes for whoever builds `SplitPolyList` on this:
1. **The binary returns an `FPoly*`, not an index.** The win pointer at `[ebp-0x2c]` is the
   poly pointer `[edi+esi*4]`; the port returns the equivalent list index (a bijection over the
   list), which is the convenient form for the recursion. Equivalent, just adapted.
2. **The binary builds the candidate's splitting plane from the poly's STORED `Normal` + base
   vertex** (`0x337b3`, the `FPlane(base, normal)` constructor), then classifies against that.
   The port's `FPoly.plane()` recomputes the normal from vertex winding. These agree for
   well-formed polys (the codebase's "winding is authoritative" stance); they can differ for a
   poly whose stored `Normal` disagrees with its winding or a near-degenerate face. A faithful
   `SplitPolyList` should classify against the stored plane to be byte-exact.
3. **No-candidate case:** if no candidate is ever selected, the binary **asserts** (`Best`,
   `UnBsp.cpp:476`) — it does NOT silently fall back to the first poly. That is unreachable for
   `num>1` with ≥1 eligible poly (the `all_structural` flag makes everything eligible when needed);
   the port returns `0` defensively.

---

## 3. `SplitWithPlaneFast` — decoded (Engine.dll `0x151f90`) — **closes prior §4.3**

The classifier `FindBestSplit` calls per (candidate, other-poly) pair. Per-vertex
(`0x10151ff6`–`0x1015206e`):

1. `d = FPlane::PlaneDot(plane, vert[i])` — the signed distance (the editor calls `PlaneDot`
   here, not the `FPlane::operator|`; same value).
2. `comiss d, 0; jb back` — `d < 0` → the back branch; else the front branch.
3. **Front branch:** mark the vertex's side `0`; set the **`has_front` flag only if `d > +0.25`**
   (`comiss d,[0x10206780]; jbe skip` — byte-verified the constant is `+0.25`).
4. **Back branch:** mark the vertex's side `1`; set the **`has_back` flag only if `d < -0.25`**
   (`comiss [-0.25], d; cmova` — byte-verified the constant is `-0.25`).

A vertex with `-0.25 ≤ d ≤ +0.25` is "on" the plane and sets **neither** flag. Return
(`0x10152070`–`0x101520a9`):

| has_front | has_back | return | meaning |
|---|---|---|---|
| no | no | `0` | **Coplanar** (every vertex inside the ±0.25 band) |
| no | yes | `2` | **Back** |
| yes | no | `1` | **Front** |
| yes | yes | `3` | **Split** (proceeds to compute the actual fragments) |

The **vertex SIDE used for the actual split** is the strict `d < 0 → back, else front` from step 2
(the ±0.25 band only gates the front/back/coplanar *decision*, not where the cut vertices land).
This matches the ±0.25 `THRESH_SPLIT_POLY_WITH_PLANE` band the hole-mechanism spike documented for
the slower `SplitWithPlane` — `Fast` is the precise sibling, same band, no fragment output in the
classify path.

---

## 4. `MAP REBUILD` build parameters — byte-verified (Editor.dll `0x65220`)

The `BSP REBUILD` exec handler's defaults, read from the parser and **byte-verified**:
- **`Balance` absent → 50** (`mov edx, 0x32; cmove ecx, edx` at `0x1006530b`).
- **`PortalBias` absent → 70** (`mov edx, 0x46; cmove ecx, edx` at `0x1006533c`), then
  `shl ecx, 8` (`0x1006534c`) packs it into the high byte → the `BalancePortal` word.
- **Optimization** for a bare `MAP REBUILD` resolves to **OPTIMAL (2) → `Inc = 1`, exact** (the
  `GOOD`/`OPTIMAL` *label* governs which cleanup passes run, not the partition step).

So a default `MAP REBUILD` runs `FindBestSplit` with **`Balance=50, PortalBias=0.70,
Optimization=OPTIMAL`** — every candidate tried, every other poly classified. (Confirms the prior
spike's §1a; here pinned to the exact bytes. The "classically 15" folklore is wrong for this
binary.)

---

## 5. The verification harness (committed, reproducible)

`harness/` holds everything needed to re-derive and re-assert the above without the throwaway
`_scratch/`:

- **`pe.py`** — `pefile`+`capstone` helpers (export map, RVA↔offset, byte/float reads, disasm).
- **`verify_heuristic.py`** — asserts every load-bearing byte/threshold/branch against the UED22
  DLLs: the ±0.25 constants, `100.0`, the four score SSE ops, the portal bonus + ×16 penalty, the
  structural prepass + candidate-skip tests, the `SplitWithPlaneFast` threshold compares + indirect
  call, the classify→counter jump table, and the `MAP REBUILD` `0x32`/`0x46`/`shl 8` defaults.
  **24/24 checks pass** (each tests a distinct, load-bearing byte sequence or value). Run:
  ```
  UED22=/home/human/src/dx_lum/Tools/uedcli/uned/UED22 \
      /home/human/src/dx_lum/.venv-uedcli/bin/python verify_heuristic.py
  ```
- **`find_best_split.py`** — the faithful reference port (§2d + §3), runnable as a sanity demo.
- **`sim_candidate_loop.py`** — an instruction-level simulator of the candidate-selection loop
  (tracing `esi`/`threshold`/`inc` exactly as decoded), and **`diff_harness.py`** — fuzzes 200,000
  random `(num, inc, structural/portal)` configs and asserts the port's chosen-candidate sequence
  matches the asm simulator (0 mismatches). These guard the §2d slot-scan correction — the one
  place the port's first cut diverged from the binary for `inc>1`.

The DLLs themselves are NOT committed (they live in `uned/UED22/`); the harness reads them from
`$UED22`.

---

## 6. Implications for the offline BSP engine — feasibility verdict

**The partition heuristic is fully decoded, byte-verified, and ported. The #1 gating unknown is
retired — a faithful offline port of `FindBestSplit` is feasible with HIGH confidence.** Concretely:

- **No unknowns remain in the heuristic itself.** It is a small, bounded, deterministic function:
  a slot-scanned candidate loop, a strided classify loop, an integer-dominated float32 score, a
  strict-`<` earliest-wins tie-break, a fully-decoded candidate-eligibility rule, and no
  RNG/hidden state. The reference port in `harness/find_best_split.py` covers all of it — including
  the slot-scan candidate selection that makes GOOD/LAME's subsample positions correct (an earlier
  cut got those wrong; see §2d). The default `MAP REBUILD` path is OPTIMAL (`inc=1`), the simplest
  case, where the slot logic reduces to "every eligible poly".
- **Float32 risk is LOW.** Splits/Front/Back/Balance are integers; the only fractional term is the
  PortalBias bonus, computed in float32 in the port exactly as the SSE code does. Ties resolve
  deterministically by index, so even an exact tie can't pick a different plane than the binary.
  This matches the GMath-table discipline uedcli already uses elsewhere.
- **The residual risk is NOT the heuristic — it's the surrounding machinery**, which is *volume,
  not unknowns*, and was already located by the prior slices spike:
  1. **`SplitPolyList` (Editor `0x34530`) node emission + coplanar-node placement** — the
     recursion that consumes `FindBestSplit`. The prior parity work showed the textbook recursion
     over-splits non-convex regions vs the editor's coplanar-node chaining (`overlapping_subtracts_L`:
     24 vs 18 nodes). Closing it is a mechanical disassembly of `0x34530`, the obvious next slice.
  2. **The CSG world-surface build (`bspBrushCSG` / the leaf-filter `0x32bf0`/`0x32030`)** —
     produces the poly soup that `bspBuild` partitions. Additive-inside-subtractive isn't yet
     faithful (`room_with_pillar`). Also mechanical.
  3. **Node-PLANE parity (beyond counts) needs a binary `UModel` parser** — there is no console
     oracle for the built node planes (T3D doesn't carry the BSP; `bspNodeToFPoly` is an internal
     virtual, not an exec). Deferred; count + leaf parity is the gate the engine decision set.

**Verdict: BUILD-GATE CLEARED for the heuristic.** The offline BSP engine's feasibility was
gated on this one piece; it is decoded, verified, and ported. The remaining engine work is the
faithful `SplitPolyList` recursion and the CSG filter — both mechanical, both with the differential
editor harness as the oracle (board item `bsp-issue-detector`). The single point where the
disassembly cannot self-resolve is **node-plane parity**, which needs a `UModel` binary parser
(out of scope here, flagged); counts + leaves remain a sufficient gate and already discriminate the
known divergences.

### If ambiguity is ever hit at a specific point
The one place a *differential editor run* (not more disassembly) would add value: confirming the
`SplitPolyList` coplanar-node chaining behaviour on a hand-built non-convex case — i.e. feed the
ported `FindBestSplit` + a candidate `SplitPolyList` a known brush, `MAP REBUILD` the same brush
live, and diff the `Nodes:`/`Portalized:` log counts (the slices-spike harness already does this).
The heuristic itself needs no live probe — it is byte-exact.

---

## 7. Relationship to prior spikes

- Supersedes the "open items" in `2026-06-24-bspbuild-partition-heuristic-from-binary.md` §4:
  the structural-splitter skip (§4.1) and `SplitWithPlaneFast` exactness (§4.3) are now fully
  decoded and byte-verified here; the `MAP REBUILD` defaults (§4.2) were already pinned and are
  re-verified at the byte level. That spike's core decode stands and is corroborated.
- Builds on `2026-06-24-bsp-csg-hole-mechanism-from-binary.md` (the ±0.25/±0.01 bands, `Finalize`/
  `RemoveColinears`/`CalcNormal` survival gates) and the slices-1b/2/3 parity spike (the
  `SplitPolyList`/CSG-filter gaps located in §6 above).
