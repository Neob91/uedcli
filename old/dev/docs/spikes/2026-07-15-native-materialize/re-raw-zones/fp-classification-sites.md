# RE: per-site FP characterization of the CSG classification/pool hot path — 2026-07-17

**Purpose.** Phase-0 gate 2 (the FP crux). For **every** floating-point site the port's
classification + vertex-pool path touches, record the actual instructions (x87 80-bit vs
SSE-scalar 32-bit vs rsqrt/x87-reciprocal) so we know whether literal byte-identity is reachable in
Rust `f32`. This is the instruction-level evidence behind `81-phase0-feasibility.md`.

**Method.** Static disassembly of the *shipping* UED22 DLLs
(`uned/UED22/{Editor,Engine,core}.dll`) with capstone/pefile via `harness/pe.py`. ImageBase
`0x10000000`; all addresses VAs. 🔬 = disassembled this session.

**Which binary is the oracle (settled).** The `dx-lum-uned` container's `/opt/UED22/Editor.dll`
and `Engine.dll` are **MD5-identical** to the repo `uned/UED22/` copies
(`3bd1fd82…` / `625d33…`). MAP REBUILD (which built the castle golden `Test_Castle.dx`) runs inside
that container, so **the binaries decoded here are the exact editor that produces the golden.** 🔬

**Build provenance (settled — overturns the "1999 MSVC6/x87" premise).** All three DLLs report
**linker version 14.32 (MSVC 19.32 / VS2022)**, `TimeDateStamp` **2022-10-29**, Machine `0x14c`
(i386). These are a **2022 MSVC rebuild** (UT-v469/OldUnreal lineage), NOT the 1999 retail binaries.
32-bit MSVC defaults to `/arch:SSE2` since VS2012 ⇒ scalar float is emitted as `movss/addss/mulss/
divss/comiss` on XMM, each op rounding to IEEE-754 binary32 immediately. There is no `fld/faddp`
80-bit accumulation. (Whole-`.text` census in `../41-fp-model-x87-vs-sse.md`: **zero `fldcw/
fnstcw`**, zero FMA, SSE:x87 ≈ 2600:1.) 🔬

---

## Per-site table (classification + pool path)

| # | Site | Module / VA | What it computes | Instructions | Verdict |
|---|---|---|---|---|---|
| 1 | `FPlane::PlaneDot` | core `0x24e60` | `X·PX+Y·PY+Z·PZ−W` (per-vertex plane distance) | `movups/mulps/shufps 0xb1/addps/movhlps/addss`, result `movss`; lone `fld dword` = 32-bit-return ABI only | **SSE** (packed reduction) |
| 2 | `FPoly::SplitWithPlane` classify | Engine `0x1518b0` | per-vertex dist `subss/mulss/addss`; band test `comiss` vs `±0.25` (`[0x10206780]`/`[0x1020b580]`) | 33 SSE-scalar, 0 x87 | **SSE** |
| 3 | `FPoly::SplitWithPlaneFast` classify | Engine `0x151f90` | `FindBestSplit`'s classify; `comiss` ×3 vs 0.25 | SSE; 1 `fstp dword` = narrows PlaneDot's st(0) return to f32 (removes precision) | **SSE** |
| 4 | **split-param `t = num/den`** | Engine `0x1506f0` @ **`0x150780`** | `t = (plane·(A−pt))/(plane·(B−A))` then `P=A+t·(B−A)` | num/den via `subss/mulss/addss`; **`divss xmm5,xmm1`**; `P` via `mulss/addss` | **SSE** (`divss` = IEEE, == Rust `f32/f32`) |
| 5 | `FPoly::CalcNormal` (Newell) | Engine `0x150510` | Σ edge cross-products → `FVector::operator^` + `operator+=`, then normalize | all SSE; delegates normalize to #6 | **SSE** |
| 6 | **`FVector::NormalizeSlow`** (surf-normal normalize) | core `0x249d0` | `|n|² (f32) → cvtps2pd → sqrtsd (f64) → cvtsd2ss (f32) → 1.0f/s (divss)` | SSE + **f64 `sqrtsd`**, **no rsqrt, no x87** | **reproducible**: `((sumsq as f64).sqrt() as f32)` then `1.0f32/·` |
| 7 | `bspAddPoint` dedup | Editor `0x35430` → `UModel::FindNearestVertex` Engine `0x1adeb0` → recursive `0x1adb60` | nearest existing point via BSP descent; **descent pruning** on **squared** dist `dx²+dy²+dz²` (`subss/mulss/addss`, no sqrt); on the winning candidate the **returned** distance is `appSqrt` (core `0x31720`, `sqrtsd` f64→f32); `bspAddPoint` accepts if that real `dist ≤ thresh` (`0.002` worldspace / `0.015` local — a real distance, NOT squared) | SSE-scalar + f64 `sqrtsd` on accept; `PlaneDot` picks descent side; **no x87/rsqrt** | **SSE**, deterministic (returns **nearest**, not first) |
| 8 | `bspAddVector` dedup | Editor `0x35530` → helper `0x31ae0` | vector dedup, thresh `2e-05` / `4e-04` | SSE (same shape as #7) | **SSE** |
| 9 | `FindBestSplit` score | **Editor** `0x335d0` | `Balance`/`Splits`/`|F−B|` counting (integer) + `PortalBias/100.0` (`cvtdq2ps`/`divss [100.0]`) | 0 x87, `cvtdq2ps`+`divss`, integer-dominant | **SSE** / integer |

**The lone x87 site anywhere near geometry — and why it does NOT gate the surf normals.**
`FVector::Normalize` (core `0x24940`, distinct from `NormalizeSlow` #6) computes its reciprocal in
**x87**: `call appSqrt` (`0x31720`, an `sqrtsd`) then `fld1 ; fdivrp st(1) ; fstp dword` — a
`1.0/sqrt` done in 80-bit then rounded to f32. **`CalcNormal` calls `NormalizeSlow` (#6, all-SSE),
NOT `Normalize`**, so the stored `FBspSurf.vNormal` is on the reproducible path. `Normalize`
(`0x24940`) is a residual to xref during the port (confirm no CSG-build caller reaches it); the
Tier-S differential will catch it if one does.

---

## Load-bearing disassembly excerpts 🔬

### #4 split-param division — `FPoly` split-edge helper `0x1506f0` (Engine)
```
0x1015075d..0x1015077c: build num (xmm5) and den (xmm1) via subss/mulss/addss   ; SSE dot products
0x10150780: divss    xmm5, xmm1          ; t = num / den   <-- the f=prevd/(prevd-thisd) split param
0x10150784: movaps   xmm0, xmm5
0x10150787: mulss    xmm0, xmm6          ; t*(B-A).x
0x1015078b: addss    xmm0, [ecx]         ; + A.x
0x1015078f: movss    [eax], xmm0         ; store intersection.x   (serialized verbatim as f32)
0x10150793..0x101507ae: same for y,z via mulss/addss
```
No x87, no reciprocal-approx. `divss` is IEEE-754 correctly-rounded ⇒ bit-identical to Rust
`num / den` on the same `f32` inputs.

### #6 `FVector::NormalizeSlow` (core 0x249d0) — the surf-normal normalize
```
sumsq (f32): mulss/addss of the 3 components -> xmm1
0x10024a19: comiss   xmm1, [0x100a0a40]  ; if |n|^2 < SMALL_NUMBER -> return 0 (skip)
0x10024a22: cvtps2pd xmm0, xmm1          ; widen f32 sumsq -> f64
0x10024a2e: sqrtsd   xmm0, xmm0          ; f64 sqrt   (IEEE; no rsqrt)
0x10024a39: movss    xmm1, [0x100a0a70]  ; 1.0f
0x10024a46: cvtsd2ss xmm0, xmm0          ; sqrt f64 -> f32
0x10024a4a: divss    xmm1, xmm0          ; inv = 1.0f / s     (f32 division)
0x10024a4e..: mulss each component by inv
```
Rust replica (bit-exact): `let s = (sumsq as f64).sqrt() as f32; let inv = 1.0f32 / s; comp*inv`.

### #7 `bspAddPoint` dedup — thresholds + the `FindNearestVertex` call (Editor 0x35430)
```
0x1003546b: movss xmm0, [0x100dcaf8]     ; worldspace thresh = 0.002
0x10035475: movss xmm0, [0x100dcafc]     ; local     thresh = 0.015
0x10035498: call [0x100cee1c]            ; Engine!UModel::FindNearestVertex(pt,&out,thresh,&idx)
0x1003549e: fstp  [ebp+8]                ; 32-bit-return narrow of the returned distance
0x100354ab: comiss xmm1, [0x100dcaec=0]  ; dist<0  (sentinel -1) -> add new
0x100354b4: comiss xmm0, xmm1            ; thresh<dist -> add new; else reuse idx
```
`FindNearestVertex` (Engine `0x1adeb0`) returns `-1.0` (`0xbf800000`) when the model is empty, else
recurses `0x1adb60` down the BSP by `PlaneDot` sign. The **descent pruning** compares **squared**
distances (`subss; mulss xmm,xmm; addss`, no sqrt); on the winning candidate (`0x1adced`) it computes
the **returned** distance via `call [0x101f987c]` = `Core.dll!appSqrt` (`0x31720`, `sqrtsd` f64 → f32
return). So `bspAddPoint`'s accept test (`comiss thresh, dist`) is against a **real f64-sqrt distance**
vs the `0.002`/`0.015` thresholds — NOT a squared-vs-squared compare. A faithful port must apply
f64-sqrt to the winning squared distance before the threshold compare. All SSE + `sqrtsd`, **no x87,
no rsqrt.** It returns the **nearest** vertex (order-unambiguous), so the Points/Vectors pool ORDER is
a pure function of the node-emission order.

### #9 `FindBestSplit` score prologue (Editor 0x335d0)
```
0x10033638: cvtdq2ps xmm0, xmm0
0x1003363b: divss    xmm0, [0x100dcb38]  ; PortalBias / 100.0
0x10033643: movss    [ebp-0x50], xmm0
```
No x87; balance/split counting is integer (`../41`).

---

## Normal provenance (deliverable d) — PRESERVE, not recompute 🔬

`FPoly::Finalize` (Engine `0x150ac0`, called by MAP IMPORT per poly):
```
0x10150af5: call 0x10150da0              ; RemoveColinears
0x10150afa: NumVertices >= 3 check
0x10150b4e: ebx = &Normal (esi+0xc)
0x10150b51..0x10150b7f:  if Normal.X!=0 || Normal.Y!=0 || Normal.Z!=0  -> jmp 0x10150bed  (SKIP recompute)
0x10150b85: call 0x10150510  (CalcNormal)   ; reached ONLY when Normal == (0,0,0)
0x10150bed..: same zero-test on TextureU/V (esi+0x18..+0x2c); recompute base only if all zero
```
So the editor **keeps the authored T3D `Normal` byte-for-byte** whenever it is non-zero. The
castle diagonal wall's authored `Normal=(-0.707107,+0.707107,0)` is preserved as parsed — the
editor does NOT overwrite it with `CalcNormal`'s `0.70710677`. The native `FPoly::new` already
stores the parsed normal (`lib.rs`), so it matches. (SplitWithPlane copies the parent Normal to both
fragments — no per-fragment recompute.) Same rule for `pBase`/`vTextureU`/`vTextureV`.

---

## Editor determinism (deliverable / gate 3) — static argument

No empirical double-build was run (the editor is crash-prone and the static case is decisive). The
geometry/pool emission has **no non-deterministic input**:
- `SplitPolyList`/`FindBestSplit` iterate `PolyList` by index; `FindBestSplit` takes **min score,
  first candidate on a tie** — a fixed tie-break, no pointer/address ordering.
- `bspAddNode`/`bspAddPoint`/`bspAddVector` append to arrays in tree-walk order; dedup via
  `FindNearestVertex` returns the **nearest** (unique) existing point — no first-vs-nearest race.
- `bspRefresh` (`0x36cd0`, decoded `../42`) compacts by a reachability DFS from node 0 — order fixed.
- No hash-map iteration, no RNG, no uninitialized-slack serialization (arrays serialize by `.Num`).

The **only** per-save-varying bytes are the package **GUID** (`appCreateGuid`, random 16 bytes at
file offset 36 — `harness/guid_generations.py` confirms it is not echoed elsewhere) and the
**TimeDateStamp** — both **excluded from the byte-identity scope**. ⇒ editor-vs-editor byte-identity
of the `UModel` body + tables holds by construction. **Recommended corroboration** (cheap once the
port branch exists): materialize the castle trunk through the editor twice and diff, masking the
16-byte GUID — not run here to avoid the crash-prone editor consuming the spike budget.
