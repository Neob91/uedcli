+++
priority = "p1"
kind = "implement"
summary = "Collapse 6 files (7 duplicate decoders) of UE1 package-header parsing into one Rust core"
+++

# Unify UE1 package read primitives into one Rust core

This consolidation was prompted by `upackage-load-package-has-zero-caching-3404`
(load_package reparses the same handful of packages 3,404 times rendering one photo) and its
sibling `port-ue1-package-primitive-decode-to-rust-61m` (the same decode is a 61M-call pure-Python
hot loop). Investigating those two surfaced that the duplication is wider than either item scoped:
6 files carry 7 independent read-side decoders of UE1 compact-index/name-table/header-table
decoding (`upackage.py`, `dxpkg.py`, `utexture.py`, `proceduraltex.py`, `native/pkg_write.py`, and
`uscript/gate.py` — which alone carries two, a header struct and a separate name-table walk); plus
2 more Rust files (`model_read.rs`/`model_write.rs`) scoped to `UModel` bodies only, left untouched
here (different concern). Two more board items already tracked slices of this without acting on
them: `migrate-utexture-py-dxpkg-py-onto-the-unified` (to-spec) and
`proceduraltex-py-correctness-and-duplication` (inbox).

Owner ruling, confirmed via `AskUserQuestion` in the 2026-09-11 design session that produced this
spec: do this once, properly, in Rust — read path only (not the write path, not the Model-body BSP
codec, which stays its own deliberate Rust/Python oracle pair). See `spec.md`.

This item supersedes (moved to `stale/`):
- `upackage-load-package-has-zero-caching-3404`
- `port-ue1-package-primitive-decode-to-rust-61m`
- `migrate-utexture-py-dxpkg-py-onto-the-unified`

It also resolves ONE of four unrelated findings in `proceduraltex-py-correctness-and-duplication`
(the `_compact_index` duplication) — that item stays in `inbox/`, its other three findings
untouched and still open.
