# `bspBuild`'s partition-plane heuristic — decoded; the offline-port gating risk is retired

**Date:** 2026-06-24
**Method:** static disassembly of `Editor.dll` (the `capstone`+`pefile` harness in
`_scratch/bspspike/`).
**Why:** the offline-BSP-engine decision (`decisions.md` 2026-06-24 09:07 UTC) named **one gating
unknown** — `bspBuild`'s partition-plane selection (`FindBestSplit`), the piece the render-hole
spike left out of scope and on which the whole tree (hence which faces split/survive) hinges.
This spike decodes it and answers: **is a faithful Python port realistic? Yes.**
**Confidence:** decompiled facts (read from the compiled code) for everything with an address.

---

## 1. The call chain

`UEditorEngine::bspBuild` (Editor.dll `0x35ef0`) → the recursive splitter **`SplitPolyList`**
(static `0x34020`/`0x34530`, self-recursive, calls `SplitWithPlane`/`SplitInHalf`/`Reverse`/
`RemoveColinears`) → the scorer **`FindBestSplit`** (static `0x335d0`). `FindBestSplit` is the
heuristic; it is the only place `SplitWithPlaneFast` (Engine.dll `0x151f90`) is called, in a
double loop, with the score constant `100.0` (`0x100dcb38`).

## 2. `FindBestSplit` — fully decoded (Editor.dll `0x335d0`)

Signature (from the disassembly): `FindBestSplit(INT NumPolys, FPoly** PolyList, INT
Optimization, INT BalancePortal)`. `BalancePortal` packs two bytes: **`Balance = arg & 0xFF`**,
**`PortalBias = ((arg >> 8) & 0xFF) / 100.0`** (so the editor passes Balance 0–100 in the low
byte and PortalBias·100 in the second byte).

```python
def FindBestSplit(NumPolys, PolyList, Optimization, BalancePortal):
    Balance    = BalancePortal & 0xFF                 # int 0..100
    PortalBias = ((BalancePortal >> 8) & 0xFF) / 100.0 # float

    # candidate/classify STEP by optimization level (BSP_Lame/Good/Optimal):
    #   Optimal(2) -> 1            (try every poly; exact)
    #   Good(1)    -> NumPolys/10  (signed /10 via the 0x66666667 magic-mul)
    #   Lame(0)    -> NumPolys/4
    Inc = {2: 1, 1: NumPolys // 10}.get(Optimization, NumPolys // 4)
    Inc = max(Inc, 1)

    best, bestScore = None, +inf
    for i in range(0, NumPolys, Inc):                 # candidate splitter PolyList[i]
        P = PolyList[i]
        # (structural-splitter preference: PF mask 0x28 = PF_Semisolid|PF_NotSolid; a first pass
        #  at 0x336d2 sets an "all polys are semi/nonsolid" flag, and the candidate loop skips
        #  semi/nonsolid candidates unless that flag is set — see §4, partially decoded.)
        Front = Back = Coplanar = Splits = 0
        plane = P.plane                               # FPlane(base=P.verts[0], normal=P.normal)
        for j in range(0, NumPolys, Inc):             # NB: classification is ALSO stepped by Inc
            if j == i:
                continue
            c = PolyList[j].SplitWithPlaneFast(plane) # 0=Coplanar 1=Front 2=Back 3=Split
            if   c == 1: Front += 1
            elif c == 2: Back  += 1
            elif c == 0: Coplanar += 1
            else:        Splits += 16 if PolyList[j].IsPortal() else 1   # portal split ×16

        # the classic UE1 score, computed in float32 (SSE movss/mulss/addss):
        Score = (100.0 - Balance) * Splits + Balance * abs(Front - Back)
        if P.IsPortal():                              # prefer splitting ON a portal plane
            Score -= (100.0 - Balance) * Splits * PortalBias

        if Score < bestScore:                         # STRICT '<' → first/earliest wins ties
            best, bestScore = P, Score
    return best
```

Confirmed details (each from a specific instruction):
- **Score formula** `(100−Balance)·Splits + Balance·|Front−Back|` — `0x33843`–`0x33878`
  (`100.0` at `0x33848`, `subss` Balance, `mulss` Splits, `mulss` |Front−Back|, `addss`).
- **Portal candidate bonus** `Score −= (100−Balance)·Splits·PortalBias` — `0x33881`–`0x33896`
  (`test [cand+0x1b0], 0x4000000` = `PF_Portal`, then `mulss PortalBias` / `subss`).
- **Portal split penalty ×16** — `0x33814` (`test [poly+0x1b0], 0x4000000`; portal split does
  `add Splits, 0x10` vs `inc Splits`).
- **`SplitWithPlaneFast` return map** (jump table `0x33934`): `0`→Coplanar, `1`→Front, `2`→Back,
  `3`→Split.
- **Increment by optimization** — `0x3366f`–`0x336c8` (`==2`→1; `==1`→`/10` via `0x66666667`;
  else `/4`; `max(·,1)`). The **classification loop steps by the same `Inc`** (`0x337d7`
  `add edi, [ebp-0x18]`), so Good/Lame score a *subsample* — Optimal (Inc=1) is exact.
- **Tie-break** — `0x338a0` `comiss best, Score; ja take` plus a "first candidate always taken"
  (`[ebp-0x2c]==0`) → strict `<`, earliest candidate wins. Deterministic.
- **`PolyFlags` at `[poly+0x1b0]`**; `PF_Portal = 0x04000000`; structural mask `0x28 =
  PF_Semisolid|PF_NotSolid`.

## 3. Verdict: a faithful port is realistic — the gating risk is retired

`FindBestSplit` is a **small, bounded, fully-deterministic** function with no hidden state, no
RNG, and no data-structure exotica — now decoded end-to-end above. That was the one piece flagged
as possibly infeasible; it is not. The remaining engine-port work is **volume, not unknowns**:

- `SplitPolyList` recursion + node emission (`bspAddNode`), coincident-plane handling, leaf/bound
  build (`bspBuildBounds`, the collision leaf/zone structure) — mechanical, all disassemblable
  with this same harness.
- `SplitWithPlaneFast` and the `FPoly` ops — the render spike already pinned the precise
  `SplitWithPlane` (±0.25/±0.01 bands) and `Fix`/`RemoveColinears`/`CalcNormal`; Fast is a sibling.
- **Float32 discipline:** the score is float32 SSE math. Risk is **low** — Splits/Front/Back/
  Balance are integers, so the only fractional term is the PortalBias bonus; ties are rare and the
  `<`/earliest rule is deterministic. Port the score in float32 (same approach as `rotation`'s
  GMath table) and the differential harness catches any boundary drift.

## 4. Small open items before the port (none are showstoppers)

1. **The structural-splitter skip** (`0x336d2`, `0x3373b`–`0x33760`): the candidate loop prefers
   non-(semisolid|nonsolid) polys and has an "all are semi/nonsolid" fallback flag. The gist is
   decoded (mask `0x28`); one more read pins the exact skip for byte-exactness.
2. **`bspBuild`'s defaults for `MAP REBUILD` — PINNED (2026-06-24, closes this open item).** The
   `BSP REBUILD` exec parser (`Editor.dll 0x65220`) decodes to **Balance=50, PortalBias=70,
   Optimization=2 (OPTIMAL → `Inc=1`, exact)** when no quality keyword is given (the GOOD/OPTIMAL
   *label* only selects which cleanup passes run, not the partition step). NOT the "classically 15"
   folklore. Recorded in `commands.md` and the slices-1b spike §1a; the offline port uses these.
3. **`SplitWithPlaneFast` exactness** — port and diff against `SplitWithPlane` (its precise
   sibling, already decoded) on the corpus.

## 5. Implication for the plan

Proceed with the offline BSP engine (`decisions.md` 2026-06-24 09:07 UTC). The heuristic gate is
cleared; the project is now a (large but mechanical) faithful port + the differential harness
(editor as test oracle). Suggested first implementation slice: port `FPoly` + `SplitWithPlaneFast`
+ `FindBestSplit` + a minimal `SplitPolyList`, build a few hand brushes, and diff the resulting
node planes/counts against a real `MAP REBUILD` export — proving the tree-shape parity on small
inputs before scaling to the full CSG filter and collision build.
