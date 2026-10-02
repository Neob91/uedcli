+++
priority = "p1"
kind = "debug"
summary = "FIXED: `build_texture_group_index` now scans `*.u` too, purely additive over the existing `*.utx` scan; `DX.dx`'s 26/26 `texture_ref` diffs are 0."
+++

# `build_texture_group_index` never scanned `.u` packages — FIXED

Widened to scan `*.u` (code packages) after the existing `*.utx` scan, both `index.setdefault`-ing
so `.u` can only fill names `.utx` left unresolved — no existing resolution can change. Added
`.u`/multi-level-group cost (293 MB / 38 files) is ~1.3 s, on top of the ~1.3 s
`build_class_package_index` already pays scanning the same files (uncached across the two, one-time
per `materialize` run). `parity_report.py`: `DX.dx` `texture_ref` 26 → **0** (surfs residual now
`p_base` only, the unrelated §10.20 Points-order thread); `02_NYC_Bar`/`03_NYC_UNATCOHQ` `texture_ref`
diff LISTS byte-identical before/after (139 and 0) — zero regression. Detail, cost/collision-safety
evidence, and the full per-level table: `dev/docs/native-materialize-findings.md` §6 (search
"texture-group-index-misses-textures-inside-u — FIXED"). Tests: `uedcli/tests/test_pkgref.py`.
