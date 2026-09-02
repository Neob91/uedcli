+++
priority = "p2"
kind = "owner-question"
summary = "They do not die — both PASS at HEAD"
+++

# They do not die — both PASS at HEAD

to-build #9.5's premise was FALSE — I did NOT mark the two tests skipped, and here is
what I did instead.` The item (and `direction/process.md`, 2026-07-24 21:58 UTC item 5) says
`test_native_materialize.py`'s `test_box_sweep_lands_on_native_floor` and
`test_point_below_floor_is_solid_after_hulls` die importing the spike harness, so mark them
SKIPPED. **They do not die — both PASS at HEAD** (verified on a clean `bin/test`: 2389 passed, 1
skipped, 0 failed, before I touched anything). The harness moved into the spikes tree
(`fafe58e2f`/`322d696f1`) and `line_check.py` self-inserts the sibling 2026-06-27 harness dir on
`sys.path`, so `utexture_decode` imports fine here. Marking two GREEN tests skipped would have
deleted live coverage of the "pawn falls through the floor" bug, so I did **not** do it. What I
built instead (commit `291c8f6e4`): `_load_line_check()` converts a HARNESS-side `ImportError`
into a `pytest.skip` whose reason names the spike env, while an `ImportError` from `uedcli` itself
still propagates (a regression in the code under test must stay red). Net effect: green here,
a clean skip (never an ERROR) on a checkout where the harness's hardcoded absolute paths don't
resolve. **Confirm this reading, or tell me to hard-skip the two tests as originally written.**
Related latent fragility, un-fixed: `line_check.py` hardcodes
`ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")` — it only imports at all
on this machine's checkout path.
