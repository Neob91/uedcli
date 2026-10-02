+++
priority = "p3"
kind = "chore"
summary = "Two tests in `test_engine_facts.py` don't test what they claim (pre-existing)"
+++

# Two tests in `test_engine_facts.py` don't test what they claim (pre-existing)

`test_collision_box_is_twice_the_half_height` is `radius, half_height = 22.0, 40.0` then
`assert 2 * half_height == 80.0` — a tautology over its own literals that imports nothing from
uedcli and can never fail. `test_the_sheer_axis_enum_matches_the_real_core_package` docstrings "It
must match `Core.u`'s real `ESheerAxis` ordering" but never opens a package, though the real names
are in the committed `uned/UED22/core.u`. Both predate this work; surfaced by a round-4 reviewer
reading the file the new regression was added to. (2026-07-25.)
