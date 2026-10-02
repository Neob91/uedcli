"""The `brush` command family — a package because its parser has sibling command-group namespaces
(`build` shapes, `poly`, `vertex`) below `brush` (spec "Target structure").

`cli.dispatch` enters the family through `routes.run`, which routes the stateless generators
(`build`, `intersect`/`deintersect`) directly and resolves the single trunk source once for the
source-consuming verbs before handing off to the owning feature module. `routes.py` imports only the
selected feature module. Docstring-only initializer: no imports or re-exports (see
`test_import_boundary.py`).
"""
