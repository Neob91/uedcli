## Question

Gate `test_mapimport_stale_class_package.py::test_retail_unreal_gold_maps_import_fully` (and any
similarly-shaped real-corpus test) behind an opt-in marker, deselected from the default `bin/test`
run?

It costs 173s (11%) of the measured 26.5-minute pytest run, decoding 8 real retail Unreal Gold
`.unr` maps end to end — genuine coverage, not a fixture artifact, but the reason `bin/test` is slow
enough that `dev/docs/rules/tests.md`'s "run it before every commit" default gets skipped in
practice.

## Answer
