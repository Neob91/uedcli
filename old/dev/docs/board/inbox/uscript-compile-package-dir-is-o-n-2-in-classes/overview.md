+++
priority = "p2"
kind = "implement"
summary = "uscript compile_package_dir is O(N^2) in classes per package"
+++

# uscript compile_package_dir is O(N^2) in classes per package

`compile_package_dir` (`uedcli/uscript/compile.py:1602-1649`) calls `_finalize_multi(override=None)`
per added class (1633-1642). `_finalize_multi` (1874-1955) rebuilds the entire package from every
accumulated unit/prop/enum/const/func — not just the new class — then `_serialize(pkg)` writes the
full partial package to disk. The next iteration then constructs a brand-new
`ClassGraph(base_paths + [partial])` (`natives.py:326`), discarding the prior iteration's
`class_sig`/`_struct_cache` memoization and re-running `_build_index()` over all of Core.u/Engine.u's
export tables from scratch. For N classes in a package this is O(N²) work in package size.

This directly blocks the campaign's stated growth axis: `USCRIPT-COMPILER.md`'s "path to 30
packages" plan needs multi-class corpus packages, and this is exactly the axis that scales quadratically
today.

Fix: finalize incrementally (append the new class's exports instead of rebuilding all), and reuse one
`ClassGraph` across iterations with an incremental update for the partial package. Needs care: the
table-ordering algorithm this campaign already reverse-engineered (global-index gather order, CRT
`qsort` by refcount) must still produce byte-identical output — this is a perf fix on the internals of
a byte-parity-critical path, not a free rewrite.

Found by: 2026-09-12 performance audit (subagent-driven, uscript-compiler scope).
