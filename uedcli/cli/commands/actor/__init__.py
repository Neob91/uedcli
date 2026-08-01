"""The `actor` command family — a package because its parser has sibling command-group namespaces
(`folder`, `label`, `prop`) below `actor` (spec "Target structure").

`cli.dispatch` enters the family through `routes.run`, which handles the subverbs that have moved
here and hands the rest back to the transitional dispatch branches. Slice 8 moves only `preview`;
`routes.py` imports only the selected feature module. Docstring-only initializer: no imports or
re-exports (see `test_import_boundary.py`).
"""
