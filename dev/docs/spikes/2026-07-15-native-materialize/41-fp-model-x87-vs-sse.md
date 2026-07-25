# SPIKE 41 — FP model of the UED22 CSG math: x87 (80-bit) vs SSE scalar (32-bit)

**Date:** 2026-07-15. **Method:** static disassembly of the actual shipping UED22 DLLs
(`uned/UED22/{Engine.dll,Editor.dll,core.dll}`, image base `0x10000000`) with capstone/pefile.
**Harness:** `harness/fp_classify.py` (per-function FP taxonomy) + `harness/fp_scan_text.py`
(whole-`.text` census); both reuse `spikes/bspspike/pe.py`. Reproduce:
`/tmp/re/bin/python3.12 fp_classify.py <dll> <rva_hex> <len_hex> <name>`.

---

## VERDICT (decisive) 🔬

**The UED22 CSG/geometry math is SSE2 scalar/packed — TRUE 32-bit float, with NO x87 extended
precision, NO x87 control-word rounding tricks, and NO FMA contraction.** A Rust `f32` port **can be
bit-exact** at the ±0.25 CSG threshold boundaries. The `#1 unproven risk` framing in spec §5/§8.1
("if the 1999 build used x87 80-bit intermediates, even Rust `f32` diverges and needs
extended-precision emulation") **does not apply to this build** — because the build is **not 1999**.

**Root cause / the load-bearing correction to the spec's premise:** these DLLs are **not the 1999
retail binaries.** They are a **2022 MSVC rebuild** (OldUnreal-style): `Engine.dll` and `Editor.dll`
carry **linker version 14.32** (Visual Studio 2022 / MSVC 19.32) and `TimeDateStamp` **2022-10-29**.
32-bit MSVC has defaulted to `/arch:SSE2` since VS2012, so *all* scalar float math is emitted as
`movss/addss/mulss/subss/divss/comiss` on XMM registers — each op rounds to IEEE-754 binary32
immediately. There is no `fld/fmul/faddp` accumulation chain to carry 80 bits between operations.

This is a **better** outcome than the spec feared: parity is a reachable engineering target, not a
precision-emulation problem.

---

## Evidence

### 1. Build provenance (why the x87 worry is moot)

| DLL | Linker ver | TimeDateStamp | Meaning |
|---|---|---|---|
| `Engine.dll` | 14.32 | 2022-10-29 12:41 UTC | MSVC 2022 rebuild → `/arch:SSE2` default |
| `Editor.dll` | 14.32 | 2022-10-29 12:42 UTC | same |
| `core.dll` | (same toolchain) | — | holds `FPlane::PlaneDot` (below) |

**The functions live in Engine.dll, not Editor.dll.** The spec/task cited the four CSG RVAs "(Editor.dll)",
but Editor.dll's `.text` ends at RVA `0xcd23b`, and all four RVAs (`0x1518b0`/`0x151f90`/`0x150510`/`0x335d0`)
are **beyond** it — they sit in **Engine.dll**'s `.text` (`0x1000`–`0x1f830b`). Disassembling them against
Editor.dll yields garbage (`.rdata`); against Engine.dll they decode as clean function prologues. (Recorded
so the port's RE cites the right module.)

### 2. Per-function FP taxonomy (Engine.dll)

| Function | RVA | x87 arith | x87 ctrl | SSE scalar | SSE packed | verdict |
|---|---|---|---|---|---|---|
| `FPoly::SplitWithPlane` | `0x1518b0` | 0 | 0 | 33 (`movss/subss/mulss/addss`, `comiss`×6) | 5 (`xorps/movaps`) | **SSE** |
| `FPoly::SplitWithPlaneFast` | `0x151f90` | 1 | 0 | 5 (`movss`, `comiss`×3) | 1 (`xorps`) | **SSE** |
| `FPoly::CalcNormal` | `0x150510` | 0 | 0 | 21 (`movss`×15, `subss`×6) | 0 | **SSE** |
| `FindBestSplit` | `0x335d0` | 0 | 0 | 0 (in first-ret block) | 0 | integer balance/split counting; float score is elsewhere/inlined-callee — not FP-bearing here |

The single `x87` op in `SplitWithPlaneFast` is **not** an arithmetic accumulate: it is
`fstp dword ptr [ebp-0x70]` at `0x10152013`, which **narrows** the `st(0)` return of `PlaneDot` to a
32-bit slot (see §3) — the value is immediately reloaded with `movss xmm0` and all classification runs
in XMM. That `fstp dword` *removes* precision (stores 32-bit), it does not add it.

### 3. The dot-product accumulation — `FPlane::PlaneDot` (`core.dll` `0x24e60`) is fully SSE

The CSG classify atom (`SplitWithPlaneFast`) computes each vertex's plane distance by **calling**
`FPlane::PlaneDot(FVector)`. That callee is where the actual `X·PX + Y·PY + Z·PZ − W` accumulation
happens — and it is **100% SSE**:

```
movups  xmm0, [ecx]                 ; plane (PX,PY,PZ,PW)
movss   xmm2, [eax+8] ; movlhps ; movlps [eax] ; orps [const]   ; build (X,Y,Z,1)
mulps   xmm2, xmm0                  ; packed 32-bit lane multiply
movaps  xmm1, xmm2 ; shufps xmm1, xmm2, 0xb1 ; addps xmm0, xmm2 ; movhlps ; addss xmm1, xmm0  ; horizontal sum
movss   [ebp+8], xmm1               ; result already 32-bit
fld     dword ptr [ebp+8]           ; load into st(0) ONLY to satisfy the 32-bit float-return ABI
ret 4
```

The lone `fld dword` exists **only** because the 32-bit MSVC calling convention returns a float in
`st(0)`; the value loaded is an already-rounded binary32. **No 80-bit intermediate ever exists.**

### 4. Whole-`.text` census (rules out x87 anywhere on the geometry path)

Linear sweep of the entire `.text` section (`fp_scan_text.py`; some data mis-decodes, but the ratio is
robust):

| DLL | x87 arith | **x87 ctrl (`fldcw`/`fnstcw`)** | SSE scalar | SSE packed | **FMA** |
|---|---|---|---|---|---|
| `Engine.dll` | 15 | **0** | 1 494 | 38 097 | **0** |
| `Editor.dll` | 6 | **0** | 382 | 165 | **0** |

The ~15/6 stray `x87` hits are linear-sweep noise (data decoded as `fld`), swamped 2600:1 by SSE.
Decisive negatives: **zero `fldcw`/`fnstcw`** anywhere → the build never touches the x87 precision-control
word (no "set 24-bit rounding then compute" tricks). **Zero FMA** → the compiler never fused `a*b+c`
into a single differently-rounded op.

### 5. The ±0.25 threshold is real and compared in SSE

`SplitWithPlaneFast` classifies each vertex with SSE compares against constants
`+0.25` (`[0x10206780]`) and `−0.25` (`[0x1020b580]`) via `comiss` — confirming the ±0.25 CSG split
threshold the spec's parity concern centers on, and that the comparison itself is a 32-bit `comiss`, not
an 80-bit `fcomp`.

---

## Consequence for the port's parity strategy (concrete)

1. **Bit-exact geometry parity IS reachable in Rust `f32`.** Use native `f32`; do **not** build an
   extended-precision (f64/f80) emulation layer — it would be *wrong* here (it would diverge from the
   engine's true-32-bit rounding, not converge to it). This validates the spec's `f32.rs` plan and
   *retires* the "x87 → needs extended-precision emulation" branch of §8.1 for this substrate.

2. **The remaining parity work is operation-ORDER fidelity, not precision.** Because every op rounds to
   32-bit, the result depends on the **order** of the multiply/add tree. The port must replicate the
   engine's order where it is observable — notably `PlaneDot`'s horizontal reduction is a specific
   pairwise tree (`mulps` → `shufps 0xb1` → `addps` → `movhlps` → `addss`), **not** a left-to-right
   `x*px + y*py + z*pz - w`. Port `PlaneDot` to match that shuffle/add shape (or verify the naive order
   yields identical bits for the plane magnitudes in range). This is ordinary faithful-port work and is
   *deterministic* — the whole point vs. x87, where order fidelity still would not have sufficed.

3. **Forbid FMA in the Rust build.** The engine emits none. Rust never auto-contracts `f32` `a*b+c`
   into `mul_add` (unlike `-ffast-math` C), so the default is already safe — but do **not** hand-write
   `f32::mul_add` in the hot math, and keep `codegen-units`/opt flags from enabling `fma` target
   features on the geometry crate. (Guard is trivial; noted so it isn't introduced by accident.)

4. **Parity target is unambiguously THIS build.** The retail maps in the trunk were (re)built by *this*
   UED22 editor's `MAP REBUILD`; `materialize` reproduces that editor's output; and the game only
   *loads* pre-built BSP (it does not re-run CSG). So there is no second, x87-era FP model hiding
   downstream to also match — the SSE2 build here is the sole oracle.

**Net:** SPIKE 41 turns the spec's "designed-for, not established; #1 unproven risk" on FP parity from a
*precision-model* unknown into a *reproduce-the-op-order* engineering task. The differential gate (§6
Tier-S) remains the proof that the order is right, but the foundation — "can `f32` even match?" — is now
answered **yes**, with binary evidence. Confidence: 🔬 (live-probed by disassembly of the shipping
binaries; the verdict rests on the linker version + the SSE-only instruction census + the fully-SSE
`PlaneDot`, three independent tells).

### Residual / follow-on (non-blocking)
- `FindBestSplit`'s float **score** computation wasn't isolated here (its first-ret block is integer
  balance/coplanar counting; the score math is in a later block or an inlined callee). Not parity-critical
  for solid/void correctness, but when porting the split *heuristic*, disassemble its score expression to
  match op order too. Cited for N-1.
- Op-order fidelity beyond `PlaneDot` (e.g. `SplitWithPlane`'s interpolation of split vertices, `CalcNormal`'s
  cross-product + normalize) must each be order-matched during the N-1 port and proven by the Tier-S
  differential — this spike establishes *feasibility*, the differential establishes *achievement*.
