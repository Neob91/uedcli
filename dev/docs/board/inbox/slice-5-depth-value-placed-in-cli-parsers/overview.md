+++
priority = "p3"
kind = "chore"
summary = "Slice 5: depth_value placed in cli/parsers/_arguments.py"
+++

# Slice 5: `depth_value` placed in `cli/parsers/_arguments.py`

`depth_value` (the `class list`/`class show` `--depth` converter) is used only by the `class`
family, so "keep family-only helpers with the registrar" would put it in `classes.py`. I placed it
in `_arguments.py` instead, reading the spec/plan phrase "`_arguments.py` owns the scalar argument
converters" as covering every scalar `type=` converter, not just the shared ones. This keeps all
scalar converters in one place. Parser equivalence is unaffected (the baseline compares converters by
`__name__`). If the owner prefers strict family-locality, move it to `classes.py` and repoint
`tests/test_class_discovery.py`.
