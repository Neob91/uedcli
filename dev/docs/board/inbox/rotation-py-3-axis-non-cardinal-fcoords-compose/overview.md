+++
priority = "p3"
kind = "debug"
summary = "Disassembly-confirmed: the real editor composes a brush Rotation via THREE sequential float32 FCoords multiplies (Roll, then Pitch, then Yaw), not the single double-precision matmul rotation.py/brush_marshal.py use. For a brush with 2+ simultaneously non-cardinal axes this can diverge by up to 1 ULP. Only 2 brushes in the whole 21-level cached corpus hit this (Vandenberg Gas Brush2/Brush246); their level's residual is already attributed elsewhere. Does NOT explain Area51/NSFHQ04/NYC747/OceanLab's open node-count residuals — those brushes' rotations are cardinal or at-most-1-axis-non-cardinal, proven bit-exact. Not measured live; no fix shipped."
+++

# rotation.py's rotation-matrix compose is not the real editor's algorithm for a genuine 2+-axis non-cardinal FRotator

Dispatched to check the standing "rotated-brush transform FP-order" hypothesis for the open
Area51/NSFHQ04/NYC747/OceanLab Lab/Training Final node-count residuals (`native-materialize-findings.md`,
search "Full `bspAddNode` decompile" and "INDEPENDENT PASS — full-breadth decompile" — both already
confirmed the CSG/BSP pipeline itself is faithful, leaving vertex/normal transform precision as the
remaining named hypothesis). Full write-up: `native-materialize-findings.md`, search "rotated-brush
Transform math".

## What was checked

1. **`FPoly::Transform` (`Engine.dll` RVA `0x152360`) itself** — `angr`-decompiled fresh. Its
   vertex path (`Base`/verts: `Location + R·(v − PrePivot)`, one `FVector::TransformVectorBy` call
   per point) matches `fpoly.rs::FPoly::transform` exactly, including op-order. Confirmed
   (independently of the already-known §92 §52 finding) that it ALSO applies a second
   `SafeNormalSlow` to the rotated Normal unconditionally, on every poly — `fpoly.rs::transform`
   itself does not (the caller, `bspcsg.rs`, applies it selectively per the existing Subtract-only
   rule; not revisited here, since §53 already measured that the whole normal-precision campaign
   moves node-plane SET by zero).

2. **How the rotation MATRIX (the `rot` fed to `FPoly::transform`) is actually built.** Located
   `ABrush::BuildCoords` (`Engine.dll` RVA `0x111390`) via raw disassembly (`rdis.py dis`) →
   `FCoords::operator*(FRotator)` (`core.dll` RVA `0x179d0`) → the real workhorse,
   `FCoords::operator*=(FRotator)` (`core.dll` RVA `0x18a10`). It reads the GMath sine table (same
   `(x>>2)&0x3fff` indexing already ported in `uedcli/rotation.py`) for Roll, Pitch, Yaw in that
   ORDER, builds one single-axis `FCoords` per angle, and chains THREE calls to
   `FCoords::operator*=(FCoords)` (`core.dll` RVA `0x17df0`) — `this = ((this*Roll)*Pitch)*Yaw`,
   entirely in **scalar float32 SSE** (`mulss`/`addss`, no double anywhere).

   `uedcli/rotation.py::euler_to_matrix_uu` instead computes `matmul(Rz(yaw), matmul(Ry(pitch),
   Rx(roll)))` as ONE Python-**double** 3×3 product, cast to f32 only when it crosses the
   `brush_marshal.py` → Rust FFI boundary. Structurally a different algorithm: 3 chained f32
   matrix products vs. 1 double product. The module's own header already flags this exact gap
   ("a genuine NON-cardinal multi-axis FRotator ... is ULP-approximate") but asserts "DX content has
   NONE" of it — **that assertion is false**, see below.

## The real corpus does contain the gap case — but only twice, and not on any open-residual brush

`scan_noncardinal.py`/`scan_brush_3axis.py` (this dir) scanned every cached `_scratch/geo-confirm-*`
trunk's `Rotation=` field. Two-or-more-simultaneously-non-cardinal axes: 421 hits (mostly point actors —
weapons/lights/cameras — plus 4 real brushes: OceanLab Lab `Brush1849`/`Brush1081`/`Brush2409`, NYC
Underground04 `Brush134`). THREE-simultaneously-non-cardinal (the case that actually needs all 3 chained
f32 multiplies to be non-trivial): exactly **2 brushes total**, both in Vandenberg Gas —
`Brush2` (`Pitch=-15272,Yaw=-56480,Roll=-344`) and `Brush246` (`Pitch=1024,Yaw=-10160,Roll=16688`).

`check_multiaxis_noncardinal.py` (this dir) computes `rotation.py`'s actual double-then-cast matrix vs a
genuine per-step-f32 compose for each real case found:
- All 4 real 2-axis-non-cardinal brushes (OceanLab/NYCu04): **0 ULP difference**, every strategy agrees
  bit-for-bit (expected — with the third axis at 0/cardinal, that axis's matrix is an exact ±1/0
  signed-permutation matrix, and multiplying by one introduces no rounding regardless of precision).
- Vandenberg Gas `Brush2`: **0 ULP** (its angles happen to round-trip identically anyway).
- Vandenberg Gas `Brush246`: **1 ULP** divergence in matrix entry `[0][1]`
  (`0x3cfd8b2e` double-then-cast vs `0x3cfd8b2d` f32-stepwise) — a genuine, reproducible difference.
- Synthetic 3-axis stress angles (not real content) reproduce the same 1-ULP-class divergence readily,
  confirming this is a real, not a fluke, precision gap.

**Caveat: the per-step-f32 simulation in `check_multiaxis_noncardinal.py` is NOT a byte-exact port of
`FCoords::operator*=`** — it approximates the real algorithm's row-vector-times-matrix shape and
Roll→Pitch→Yaw order but was not built by fully decoding the three per-axis stack-buffer layouts at
`0x18a10` (only the shared `operator*=(FCoords)` kernel at `0x17df0` was fully read). So "1 ULP" is a
strong, disassembly-grounded estimate of the divergence's ORDER OF MAGNITUDE, not a byte-for-byte
reproduction of the editor's own bits. Closing that gap needs either the remaining stack-layout decode
or a live gdb capture of `FCoords::operator*=(FRotator)`'s actual output for `Brush246`.

## Why this does not explain the currently-open residuals

- **Area51 Entrance `Brush1852`**: `Rotation=(Yaw=-49152)` ≡ `Yaw=16384` mod 65536 — a single-axis,
  EXACTLY cardinal (90°) rotation. Its matrix is a signed-permutation matrix (entries in {-1,0,1});
  no floating-point rounding occurs in ANY compose order. Provably bit-exact regardless of which
  algorithm builds it. (The other 3 placements of the same prop, `Brush1849`/`1850`/`1851`, carry no
  `Rotation=` at all — already known to build byte-exact.)
- **NSFHQ04 `Brush842`**: findings ledger already live-gdb-proved its own classify-BSP descent is
  byte-exact vs the editor (19/19 calls match) — not a transform-precision case at all, and its
  rotation is likewise a cardinal 180°-flip.
- **NYC 747 / OceanLab Lab / Training Final**: their surf counts are already exact (face set
  correct); the open residual is node/leaf-COUNT only. OceanLab Lab does contain 2-axis
  non-cardinal brushes, but those are proven 0-ULP above. No 3-axis-non-cardinal brush exists in
  any of these three levels' trunks (only Vandenberg Gas has any).
- **Vandenberg Gas** is the one level that DOES contain the gap case, but its own node-count
  residual is already attributed to a DIFFERENT, disassembly-confirmed mechanism this session
  (`CsgOper::Active`, shipped) plus the vertex-ring-pooling threshold (gated,
  `UEDCLI_BSPCSG_RING_NEAR`) — neither investigation flagged rotation precision. Per the project's
  own `§92 §53` finding (closing an even larger, whole-campaign normal-precision gap moved UNATCO's
  node-plane SET by exactly zero, because sub-ULP differences round to the SAME plane key), a
  single 1-ULP matrix-entry difference on 2 of Vandenberg's ~1,343 brushes is very unlikely to flip
  any `FindBestSplit` tie-break — but this was NOT measured live this round (no live editor/cached
  golden rebuild was run with a candidate fix; budget was spent on the disassembly instead).

## Conclusion

**Negative result for the task's core hypothesis**: the rotated-brush transform math is bit-exact
for every brush actually implicated in an open node/leaf-count residual (Area51, NSFHQ04, NYC 747,
OceanLab Lab) — their rotations are cardinal or at-most-one-axis-non-cardinal, and the vertex/normal
application in `FPoly::Transform` itself is a confirmed-faithful port. The ONE genuine, disassembly-
confirmed gap found (rotation.py's double-compose vs the editor's chained-float32 compose) exists but
is real-content-relevant in exactly 2 brushes total, in a level whose residual is already explained by
other, unrelated, already-fixed/gated mechanisms.

## Left undone (for whoever picks this up)

- Full byte-exact decode of `FCoords::operator*=(FRotator)`'s 3 per-axis stack layouts at `core.dll
  0x18a10` (only the shared `operator*=(FCoords)` kernel at `0x17df0` was read in full).
- A live/cached-golden measurement of Vandenberg Gas node/leaf counts with a corrected chained-f32
  rotation compose, to confirm the (expected, per §92 §53's precedent) zero effect rather than
  assume it.
- Porting the chained-f32 compose to `rotation.py`/Rust generally is LOW priority: it is a genuine
  correctness improvement (matches the real algorithm) but has no known content it would change
  the observable output for beyond the 2 Vandenberg Gas brushes, and even there the effect is
  unmeasured/expected-zero.

## Harness

`dev/docs/spikes/2026-09-02-rotated-brush-transform/harness/`: `decompile_transform.py` (angr decompile
of `FPoly::Transform`/`CalcNormal`, `Engine.dll`), `scan_noncardinal.py` / `scan_brush_3axis.py` (corpus
scan for non-cardinal FRotator combinations), `check_multiaxis_noncardinal.py` (double-vs-f32-stepwise
matrix compose diff for every real hit found). Raw disassembly of `ABrush::BuildCoords` /
`FCoords::operator*(FRotator)` / `operator*=(FRotator)` / `operator*=(FCoords)` was done interactively
via the existing `dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/rdis.py dis Core <rva>`
tool, not saved to a script (no new tool needed — `rdis.py` already exists and is generic).
