+++
priority = "p2"
kind = "implement"
summary = "Adopt `EXEC <file>` batch driving for write-only editor sequences"
+++

# Adopt `EXEC <file>` batch driving for write-only editor sequences

Shipped (`73b69a5f`): `level materialize`'s write-only drive (`OBJ LOAD`s, `MAP NEW`, `MAP IMPORTADD`,
`EDIT PASTE`, `MAP REBUILD`, `LIGHT APPLY`, `MAP SAVE`) is buffered by `Driver.begin_script` and
submitted as one `EXEC <file>`, fixing the wedge where a slow verb dropped the next typed keystroke
on retail-scale maps. `uedcli/driver.py`, `uedcli/apply.py`, `uedcli/tests/test_driver.py`.
