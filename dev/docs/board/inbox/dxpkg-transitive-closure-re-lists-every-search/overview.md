+++
priority = "p3"
kind = "implement"
summary = "dxpkg transitive_closure re-lists every search dir per package name"
+++

# dxpkg transitive_closure re-lists every search dir per package name

`_find_package_file` (`uedcli/dxpkg.py:181-192`) does `os.listdir(d)` fresh for each package being
resolved, for each search dir, with no memoization across the walk. `transitive_closure`
(195-247) calls this once per package in a closure the module's own docstring measures at 6-65
packages for real maps, across however many search dirs are composed
(`config.composed_dirs`, typically several) — O(packages × dirs) redundant directory scans of
directories whose contents don't change mid-call. Used at 3 call sites per
`dev/docs/architecture.md` (materialize's manifest resolution, `store_export.py`, `verify.py`), so
it's on the `level materialize` hot path too.

Fix: build one `dict[str, str]` (casefolded name → path) per search dir up front in
`transitive_closure`, reuse it for every `_find_package_file` lookup.

Found by: 2026-09-12 performance audit (subagent-driven, CLI/package-I/O scope).
