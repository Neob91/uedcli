+++
priority = "p2"
kind = "debug"
summary = "Asset-dependent test crashes instead of skipping: parents[5] IndexError in _dxonly_map_path"
+++

# Asset-dependent test crashes instead of skipping: parents[5] IndexError in _dxonly_map_path

`bin/test` is **red on a checkout that has no game assets beside it**:

```
FAILED uedcli/tests/test_native_materialize.py::test_dxonly_fbspnode_semantics_pinned
E   IndexError: 5
/…/python3.12/lib/python3.12/pathlib.py:282: IndexError
```

The test is *meant* to skip when the map is absent — it has the guard:

```python
path = _dxonly_map_path()
if path is None:
    pytest.skip("DXOnly.dx not available (set UEDCLI_TEST_REALMAP to a real .dx to run)")
```

but the guard never runs, because the helper raises first
(`uedcli/tests/test_native_materialize.py:571`):

```python
cand = Path(__file__).resolve().parents[5] / "Maps" / "DXOnly.dx"  # .../DX/Maps/DXOnly.dx
```

`parents[5]` assumes the repo is nested at least five levels below the filesystem root — true
under the old `…/dx_lum/Tools/uedcli/` layout, false for a checkout at e.g. `/workspace/uedcli`,
where `uedcli/tests/…` has only four parents above it. `parents[N]` raises `IndexError` rather
than returning the root.

**Fix:** compute the candidate defensively — wrap in `try/except IndexError`, or walk up with a
bounded loop, or anchor off the repo root the way the rest of the suite does — so a missing asset
skips as designed.

**Why this matters beyond one test:** `dev/docs/direction/process.md` rules that "a
permanently-red test is repaired or skipped, never left red — a suite that is always red trains
everyone to ignore red". Any checkout not five levels deep currently has a permanently-red
`bin/test`.

**Pre-existing and unrelated** to the 2026-07-27 `CLAUDE.md` de-bloat restructure — verified by
re-running the test with that change stashed, where it fails identically. Logged from that
change's review round rather than fixed there, because it is a code defect in a test helper and
that pass touched only markdown.
