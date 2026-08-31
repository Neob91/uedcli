+++
priority = "p2"
kind = "debug"
summary = "test_dxonly_fbspnode_semantics_pinned raises IndexError instead of skipping when the repo is checked out shallowly"
+++

# `test_dxonly_fbspnode_semantics_pinned` raises `IndexError` on a shallow checkout

The real-map locator in `uedcli/tests/test_native_materialize.py` is written to return `None` when it
cannot find `DXOnly.dx`, so the test can skip. It cannot: the lookup itself throws first.

```python
cand = Path(__file__).resolve().parents[5] / "Maps" / "DXOnly.dx"   # .../DX/Maps/DXOnly.dx
return cand if cand.is_file() else None
```

`parents[5]` assumes the file sits at least six levels deep, which holds for the intended
`…/DX/Tools/uedcli/uedcli/tests/` layout. With the repo checked out at `/workspace/uedcli` the path is
`/workspace/uedcli/uedcli/tests/test_native_materialize.py` — parents 0–4 only — so it raises:

```
IndexError: 5
  .../python3.12/pathlib.py:282
FAILED uedcli/tests/test_native_materialize.py::test_dxonly_fbspnode_semantics_pinned
```

**Pre-existing and environment-dependent, not caused by any recent change.** The test predates the
`actor diagram --faces` work and that feature does not touch the file. It is invisible when `bin/test`
runs from a **worktree** — `.claude/worktrees/<slug>/uedcli/tests/` is one level deeper, so `parents[5]`
resolves and the test skips cleanly. It only fails from the main checkout, which is why it surfaced at
merge time rather than during the build.

**Fix:** guard the index rather than assuming the depth — walk up looking for a `Maps/DXOnly.dx`, or
catch `IndexError` and return `None`. Either way the "no real map available → skip" path becomes
reachable, which is what the locator was written for. `UEDCLI_TEST_REALMAP` already provides the
explicit override and works fine.

The same suite carries a second environment-dependent failure with a different cause, tracked
separately: `the-class-name-unique-scan-counts-ue1-none`.
