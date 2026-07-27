+++
priority = "p2"
kind = "debug"
summary = "Native-preview post-build review findings (two cold reviewers, 2026-07-16) — gate OPEN, fixes deferred on Andrzej's \"switch to --game first\" hold"
+++

# Native-preview post-build review findings (two cold reviewers, 2026-07-16) — gate OPEN, fixes deferred on Andrzej's "switch to --game first" hold

p2. The confirmed real ones:
(1) HIGH `preview_native.add_poly` crashes with AttributeError on the out-of-range-owner GREY
path (`poly.flags` read before the None check) — the guard the join promises; its test
exercises only `_node_polys`, false coverage; (2) HIGH `--size` above 16384 (or ≥2^32) leaks a
raw `BuildError`/`OverflowError` traceback (`render_frame` call not wrapped; no upper bound in
dispatch); (3) MED `img.save` unwrapped — disk-full / out-dir removed / `shot-01.png` squatted
by a directory → raw OSError; (4) MED negative `PolyFlags` in a trunk → PyO3 OverflowError
(materialize masks with `& 0xFFFFFFFF`, preview dropped the mask); (5) MED `utexture` resolver
can raise IndexError/MemoryError on hostile mip counts/sizes (cap dims, wrap `mip0_to_rgb`);
(6) MED `--fov`/orbit-`elev` unvalidated (fov 0/nan → NaN garbage frames exit 0; |elev|>90
silently aims away); (7) LOW u32 overflow in `lib.rs` texture length check (do it in u64);
(8) LOW scale-gate regex fails OPEN on exponent-notation scales; (9) LOW one-axis-missing
texture axes discard BOTH authored axes; (10) LOW shading uses |N·L| where spec §5 said
max(0,N·L) — doc the deviation; (11) LOW `query.py` missing blank lines after the
`overview_brush` deletion; architecture.md says "never an IndexError" (false until (1)) and
cites the golden at `tests/fixtures/…` (actual: `uedcli/tests/fixtures/…`); (12) test gaps:
BuildError-wrap test can pass vacuously, no mover-scale-rejection test, no over-limit --size
test. Full reports in the session transcript 2026-07-16; fix before calling the native tier
done.
