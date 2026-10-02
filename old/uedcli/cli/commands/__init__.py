"""Command-family handlers, one module (or package) per top-level command family.

`cli.dispatch` selects a family with an explicit function-local import and calls its entry
function; a family imports orchestrators, resources and lower services, never another family or the
router. Docstring-only initializer: no imports or re-exports (see `test_import_boundary.py`).
"""
