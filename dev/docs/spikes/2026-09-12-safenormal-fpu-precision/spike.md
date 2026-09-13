# SafeNormal FPU precision-control probe — hypothesis REFUTED

**Result: `FVector::SafeNormal`'s x87 precision-control field is `10` (double, 53-bit), exactly what
native's Rust `f64` model already assumes. The "PC=11 extended-precision" hypothesis for the
UNATCO N=226 / Island N=332 sub-ULP tie is ruled out.** No code change. Board items:
`unatco-n-226-leaf-12-gets-a-permeating-light157`, `island-n-332-leaf-273-permeating-light-vertex-tie`.

## What was run

`harness/fctrl_probe.py` against the cached Island N=332 subset trunk
(`_scratch/actor-parity/01_nyc_unatcoisland/N332/maps/01_nyc_unatcoisland`), using the already-built
`dx-lum-uned-dbg:latest` debug-editor image. One gdb breakpoint at `SafeNormal`'s entry
(`core.dll 0x10051090`) and one at its exit (`core.dll 0x1005112f`), reading `$fctrl` (the x87 control
word) at each hit during a real `MAP IMPORT` / `MAP REBUILD` / `LIGHT APPLY`.

Fixed a stale bug in the probe before it would run: `ROOT = Path(__file__).resolve().parents[4]`
resolved to the `dev/` directory, not the repo root (off by one), so `editor_tree_oracle` failed to
import. Changed to `parents[5]`. No other change needed — the entry/exit addresses and gdb template
matched the current binary and `editor_tree_oracle` API without modification.

## Result

30/30 hits (varied input vectors — axis unit vectors from CSG face normals) report:

    fctrl=0x27f

Log: `logs/fctrl-probe-island-n332.log`.

## Interpretation

`0x027F` decodes as: exception masks all set (bits 0-5), reserved bit6=1, **PC (bits 8-9) = `10`
(double, 53-bit mantissa)**, RC (bits 10-11) = `00` (round to nearest). This is the standard MSVC
CRT default control word (Windows sets double precision at process start; it is NOT the x87
hardware-reset default of `0x037F`/PC=`11` that DOS-era/bare-metal code inherits).

Per the probe's own documented decision rule (`fctrl_probe.py`'s docstring, and both board items'
"next step" notes): `0x027f` **refutes** the hypothesis, `0x037f` would have confirmed it. The
measured value is `0x027f`, refuting it — and consistently so, since the PC field is written nowhere
in the four relevant DLLs (per the 2026-09-12 census in both board items) and can't change mid-process.

**Consequence:** `SafeNormal`'s sqrt+reciprocal chain runs at 53-bit (double) precision in the real
editor, which is exactly what `uedcli-native/src/fpoly.rs::safe_normal`'s Rust `f64` sqrt +
`f64` reciprocal already models. There is no widening to port — the x87-extended-precision theory for
the UNATCO N=226 / Island N=332 residual is dead. The sub-ULP tie's real mechanism (an unreplicated
operation-order or register-allocation effect somewhere in the `FLinePlaneIntersection`/`SafeNormal`
chain, per both board items' 2026-09-12 notes) is still unidentified. No fix attempted; none was
warranted by this evidence.

## Next step for whoever picks this up

The FPU-precision line of inquiry is closed. The remaining candidate is a genuine instruction-level
difference in operation order/register allocation between native's port and the real compiled code —
confirming it needs single-stepping the real `SafeNormal`/`FLinePlaneIntersection` call chain at the
exact `162->275` (Island) or `102->13`/`13->12` (UNATCO) crossing and diffing intermediate register
values against native's own trace, not another control-word read.
