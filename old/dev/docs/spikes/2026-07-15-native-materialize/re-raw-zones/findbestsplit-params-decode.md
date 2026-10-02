# RE: the ACTUAL `FindBestSplit` params — Balance=12, PortalBias=0, Opt=GOOD — 2026-07-17

**Binary:** `uned/UED22/Editor.dll` (ImageBase `0x10000000`). All addresses are VAs. Decoded with
`harness/adis.py Editor 0x<rva> 0x<len>`. 🔬 = disassembled this session.

## The load-bearing correction

The prior decode (`bspbuild-splitpolylist-decode.md`, `bspbrushcsg-filter-decode.md §5`, `sections/82
§5`) asserted the from-scratch **repartition** `bspBuild`/`SplitPolyList`/`FindBestSplit` runs with
**Balance=50, PortalBias=70, Opt=OPTIMAL (stride 1)** and called that "byte-verified". **That is
wrong on all three counts.** Instruction-level decode of the actual call chain
`csgRebuild → bspRepartition → bspBuild → SplitPolyList → FindBestSplit` shows the repartition uses:

| param | prior (WRONG) | **actual (this decode)** |
|---|---|---|
| Balance | 50 | **12** (`0xc`) |
| PortalBias | 70 | **0** |
| Opt (EBspOptimization) | OPTIMAL (2) → stride 1 | **GOOD (1)** → stride `max(NumPolys/10, 1)` |

The native `bspcsg.rs` (`const BALANCE=50; const PORTAL_BIAS=70;` + `find_best_split_exact` iterating
**all** candidates at stride 1) faithfully implements the *prior, wrong* params — so its tree-builder
is faithful to the decoded algorithm but fed the wrong constants. This is the **first-divergence**
root cause (see `sections/82 §5`).

## Evidence 1 — `bspRepartition` @`0x49fc0` calls `bspBuild` (vtbl+0x1fc) 🔬

```
0x1004a029  push  [ebp+0xc]        ; -> bspBuild arg5 slot (RebuildSimplePolys source)
0x1004a02c  push  [ebp+0x10]       ; -> bspBuild arg4 slot (unused tail)
0x1004a02f  push  0xc              ; -> BalancePacked = 12
0x1004a031  push  1                ; -> Opt = 1 (GOOD)
0x1004a039  push  [Model]          ; -> Model  (GEditor->…->Model)
0x1004a041  call  [edx+0x1fc]      ; bspBuild
```
So `bspBuild(Model, Opt=1, BalancePacked=0xc, RebuildSimplePolys=[ebp+0xc], …)`. (`csgRebuild
0x4a89a` calls `bspRepartition(…, 0, 0)`, so `RebuildSimplePolys=0`.)

## Evidence 2 — `bspBuild` @`0x35ef0` forwards to `SplitPolyList` @`0x34530` 🔬

```
0x10035f30  mov eax,[ebp+0x14]; cmp eax,1     ; [ebp+0x14] = RebuildSimplePolys (==1 EmptyModel(1,0))
...
0x10035fd1  push [ebp+0x14]   ; -> SplitPolyList +0x24 RebuildSimplePolys
0x10035fd4  push [ebp+0x10]   ; -> SplitPolyList +0x20 BalancePacked = 0xc = 12
0x10035fd7  push [ebp+0xc]    ; -> SplitPolyList +0x1c Opt = 1
0x10035fda  push edi          ; PolyList
0x10035fdb  push ecx          ; NumPolys
0x10035fdc  push 3            ; NODE_Root
0x10035fde  push -1           ; iParent
0x10035fe0  push esi          ; Model
0x10035fe1  call 0x10034530   ; SplitPolyList
```
`bspBuild`'s 4-value signature is really `bspBuild(Model, Opt, BalancePacked, RebuildSimplePolys)` —
**BalancePacked is already packed by the caller** (there is NO separate PortalBias arg; the prior
"5-arg with PortalBias" reading was wrong). So `Opt=[ebp+0xc]=1`, `BalancePacked=[ebp+0x10]=0xc=12`.

## Evidence 3 — `FindBestSplit` @`0x335d0` unpacks Balance/PortalBias + Opt→stride 🔬

```
0x10033629  mov  ecx,[ebp+0x14]          ; ecx = BalancePacked (= 12)
0x1003362e  sar  eax,8; movzx eax,al     ; PortalBias = (packed>>8)&0xff = 0
0x1003363b  divss xmm0,[100]             ;   /100.0
0x10033648  movzx eax,cl                 ; Balance = packed & 0xff = 0x0c = 12
0x1003366f  mov  eax,[ebp+0x10]          ; eax = Opt (= 1)
0x10033672  cmp  eax,2; jne 0x10033699   ; Opt==2 OPTIMAL -> stride 1; else ->
0x10033699  cmp  eax,1; jne 0x100336b1   ; Opt==1 GOOD ->
0x1003369e  mov  eax,0x66666667; imul esi; sar edx,3   ; Inc = NumPolys / 10
             (else LAME: Inc = NumPolys / 4)
0x100336bd  cmp ebx,1; cmovle ebx,1      ; Inc = max(Inc,1)
```
So for the repartition (`Opt=1`): **`Inc = max(NumPolys/10, 1)`**, and the score is
`Score = 12·|Front−Back| + 88·Splits` (`Balance=12`, `100−Balance=88`), with **no portal discount**
(`PortalBias=0`). Both the candidate loop and the inner counting loop stride by `Inc`.

## Evidence 4 — the TEMP brush BSP is a different call (`bspBrushCSG` @`0x35b83`) 🔬

```
0x10035b83  push 0            ; -> bspBuild arg tail
0x10035b85  push 1            ; -> RebuildSimplePolys = 1
0x10035b87  push 0            ; -> BalancePacked = 0  (Balance=0, PortalBias=0)
0x10035b89  push 0            ; -> Opt = 0 (LAME)  -> stride NumPolys/4
0x10035b8b  push [edi+0xac]   ; TempModel
0x10035b93  call [eax+0x1fc]  ; bspBuild
```
The brush's convex temp BSP (used by `FilterWorldThroughBrush` to cut world faces) is built with
`Opt=LAME(0), Balance=0, PortalBias=0, RebuildSimplePolys=1` — pure split-minimization (`Score =
100·Splits`). This affects **soup content** (which world faces get cut), not the final tree ORDER
(which is the repartition's job). The `bspcsg.rs` comment "PortalBias=1" is a misread of
`RebuildSimplePolys=1`; PortalBias here is 0.

## Empirical confirmation (harness/validate_params.py + spl_reorder.py)

Faithful Python `SplitPolyList`+`FindBestSplit` re-run on the **editor's own repartition soup**
(reconstructed from each golden's `Model.Polys` export, `upolys_decode`) with the corrected params:

- **Balance=12, PB=0, GOOD** reproduces the editor golden **node-for-node** at N=2, 4, 6 (and within
  1 node at N=5,7,8, residual = soup-reconstruction at wider stride). **Balance=50 does NOT** (N=2:
  22 vs 14). **Balance=15 does NOT** (N=4: 26 vs 25) — this UED22 build uses **12**, not the classic
  Unreal 15.
- **Full castle** repartition soup (853 fpolys, `Test_Castle.dx` `Model.Polys`), SplitPolyList node
  count: Bal50/OPTIMAL(native) **1607** → Bal12/OPTIMAL **1091** → Bal12/GOOD(correct) **1112**
  (editor golden 1156, the +44 being TestVisibility zone splits + semisolid LOOP3 not in this soup).
  **Balance is the dominant term (~500 nodes); stride secondary (~150).**
