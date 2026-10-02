+++
priority = "p2"
kind = "debug"
summary = "Asset-dependent test crashes instead of skipping: parents[5] IndexError in _dxonly_map_path"
+++

# Asset-dependent test crashes instead of skipping: parents[5] IndexError in _dxonly_map_path

Fixed: `_dxonly_map_path` in `test_native_materialize.py` now wraps the `parents[5]` lookup in
`try/except IndexError` returning `None`, so a checkout not nested >=5 levels below root (e.g.
`/workspace/uedcli`) SKIPS as designed instead of erroring. Only occurrence of the assumption in the
file. `test_dxonly_fbspnode_semantics_pinned` now skips cleanly.
