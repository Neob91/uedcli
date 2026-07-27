+++
priority = "p?"
kind = "unknown"
summary = "Native brush SCALE applied in `_build_brush_input`"
+++

# Native brush SCALE applied in `_build_brush_input`

— BUILT 2026-07-19 (root cause of native
over-solidification on real DX levels; spike `2026-07-15-native-materialize/sections/87` §9–§10).
`materialize._build_brush_input` was silently DROPPING every brush's `MainScale`/`PostScale`, so
scaled brushes built at UNIT size and scaled-up SUBTRACTs carved tiny holes (room interiors stayed
SOLID). Fix bakes the full linear map `L = PostScale·R·MainScale` (`rotation.actor_linear`) into
the Rust core's `rot`, gated on non-identity scale (unscaled brushes untouched → castle
byte-identical). The cold-review gate surfaced a MIRROR case (`det(L)<0`, HK has 30): the ring is
pre-reversed (as `transform.bake`) so a mirrored subtract isn't built inside-out. Real-level `[A]`
(editor-empty→native-solid, `shatter_probe.py`): HK 74.5%→**0.3%** (surfs 2664→5572/5224 golden,
leaf-blobs 131→21), UNATCO 15.3%→1.1% (3581→4056, 44→18), Catacombs 9.7%→0.9%. Committed regression
`tests/test_native_scale.py` (4 tests: scaled-vs-explicit differential + MainScale leg + mirror +
unscaled-gate — real-level trunks are gitignored `_scratch/`; each verified red on the buggy
path). 1811 offline green. **p2 remnants:** (a) exclude Mover-class actors from `csg_order` —
residual leaf-blob/zone shatter (§9.4); (b) texture-axis transform under scale rides forward `L`
(editor uses inverse-transpose covector — byte-parity/appearance only, needs live editor evidence);
(c) native-ingest nits — `det(L)=0` scaled brush silently drops polys (no `SCALE_EPS` guard here),
sheer_rate in `(0,0.05]` deadzone needlessly loses byte-parity. NativeUnatco headless-boot payoff
(does correct solidity clear the documented UNATCO load-hang) — see §87 §10.3.
