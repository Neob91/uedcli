+++
priority = "p2"
kind = "debug"
summary = "brush build cylinder/cone --sides 0 --align-to-side crashes with ZeroDivisionError"
+++

# brush build cylinder/cone --sides 0 --align-to-side crashes with ZeroDivisionError

Fixed: `_build_brushes` now rejects `--sides < 3` at the CLI (naming the flag) before the
`180/sides` `--align-to-side` conversion, matching the spiral D12 precedent. Regression test in
`test_generators.py`.
